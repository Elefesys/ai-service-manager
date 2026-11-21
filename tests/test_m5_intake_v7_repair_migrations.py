"""Preserve populated 0023 state and independently check both installed profiles."""

import importlib.util
import json
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job
from test_m5_intake_postgres import application, summary
from test_m5_intake_postgres import db as db
from test_m5_intake_postgres import intake_pg as intake_pg
from test_m5_intake_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m5_intake_postgres import search_pg as search_pg
from test_m5_intake_postgres import seeded as seeded
from test_tenancy_postgres import A, B

from scripts import native_context_db_catalog as catalog

OLD_DIGEST = "4732ea9f9b0039b8616daf081f78e0ce4731a63884605eb88fe22bfb5851179d"
OLD_VERIFIER_HASH = "87197672ba2e5476ec2657e5c1d96c49ef78eff6892c26258f0fb3eb8c07e899"
VERIFIERS = {"0023": "intake_schema_profile", "0024": "intake_v7_schema_profile"}


def repair():
    spec = importlib.util.spec_from_file_location(
        "intake0024", Path("migrations/versions/0024_intake_v7_repair.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute_repair(connection, direction):
    # Same operations and Alembic version witness within a rollback-only test.
    module = repair()
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, direction)()
    connection.execute(
        text("UPDATE platform.alembic_version SET version_num=:revision"),
        {"revision": "0023" if direction == "downgrade" else "0024"},
    )


def test_repair_has_exact_predecessor_and_leaves_historical_verifier_closed():
    module = repair()
    assert (module.revision, module.down_revision) == ("0024", "0023")
    old, new = [catalog.source_catalog(catalog.ROOT, rev) for rev in VERIFIERS]
    assert (len(old["functions"]), len(new["functions"])) == (318, 321)
    assert old["columns"] == new["columns"]
    for sig, definition in module.ORIGINAL.items():
        assert old["functions"][sig]["definition"] == definition
    assert set(module.ORIGINAL) == set(module.REPLACEMENTS)
    assert set(new["functions"]) - set(old["functions"]) == set(module.FUNCTIONS)
    sig = "platform.intake_schema_profile()"
    assert old["functions"][sig] == new["functions"][sig]
    assert old["functions"][sig]["body_sha256"] == OLD_VERIFIER_HASH
    sig = "platform.ai_provider_session(jsonb,boolean)"
    assert module.REPLACEMENTS[sig] == module.ORIGINAL[sig].replace(
        "platform.intake_schema_profile()", "platform.intake_v7_schema_profile()"
    )


async def checked_profile(c, revision):
    await c.execute(text("SET LOCAL search_path=pg_catalog,pg_temp"))
    profile = (await c.execute(text(f"SELECT platform.{VERIFIERS[revision]}()"))).scalar_one()
    full, nonfunction = (await c.execute(text(catalog.CATALOG_SQL))).one()
    expected = catalog.source_catalog(catalog.ROOT, revision)
    actual = [dict(r) for r in (await c.execute(text(catalog.FUNCTION_SQL))).mappings()]
    oids = dict(
        (
            await c.execute(
                text(
                    "SELECT sig,to_regprocedure(sig)::bigint FROM jsonb_array_elements_text(CAST(:s AS jsonb)) t(sig)"
                ),
                {"s": json.dumps(sorted(expected["functions"]))},
            )
        ).all()
    )
    digest, declaration = catalog.compare_catalog(
        expected, actual, oids, full, nonfunction, lambda: profile
    )
    assert declaration == profile
    return digest


@pytest_asyncio.fixture
async def at_0024(db):
    runtime, _ = db
    await runtime.engine.dispose()
    await _migrate("downgrade", "0024")
    try:
        yield
    finally:
        await _migrate("upgrade", "0029")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_actual_unused_downgrade_verified_0023_repeat_upgrade_and_reject_grant_drift(
    db, at_0024
):
    _, migrator = db
    async with migrator.connect() as c:
        outer = await c.begin()
        try:
            current = await checked_profile(c, "0024")
            await c.run_sync(execute_repair, "downgrade")
            assert await checked_profile(c, "0023") == OLD_DIGEST
            assert (
                await c.execute(
                    text("SELECT to_regprocedure('platform.intake_v7_schema_profile()') IS NULL")
                )
            ).scalar_one()
            await c.run_sync(execute_repair, "upgrade")
            assert await checked_profile(c, "0024") == current
            async with c.begin_nested() as savepoint:
                await c.execute(
                    text(
                        "GRANT EXECUTE ON FUNCTION platform.intake_source_current(uuid,uuid,uuid,uuid,jsonb) TO asm_runtime"
                    )
                )
                assert (
                    await c.execute(text("SELECT platform.intake_v7_schema_profile()->>'valid'"))
                ).scalar_one() == "false"
                await savepoint.rollback()
            assert await checked_profile(c, "0024") == current
        finally:
            await outer.rollback()


async def retained(h):
    targets = {
        "platform.intake_state": "workspace_id",
        "platform.intake_receipts": "workspace_id",
        "platform.intake_escalation_links": "workspace_id",
        "app.escalations": "workspace_id",
        "platform.escalation_command_receipts": "workspace_id",
        "platform.ai_runs": "workspace_id",
        "platform.ai_deliveries": "workspace_id",
        "platform.ai_provider_calls": "workspace_id",
        "platform.turn_guard_receipts": "workspace_id",
        "platform.messaging_jobs": "workspace_id",
        "app.outbox_events": "workspace_id",
    }
    return {
        table: [
            row["value"]
            for row in await query(
                h,
                f"SELECT to_jsonb(t) value FROM {table} t WHERE {column} IN (:a,:b) ORDER BY to_jsonb(t)::text",
                a=A,
                b=B,
            )
        ]
        for table, column in targets.items()
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_actual_populated_0023_upgrade_preserves_pending_unknown_and_fact_provenance(
    intake_pg, at_0024
):
    h = intake_pg
    await _migrate("downgrade", "0023")
    try:
        async with h.migrator.begin() as c:
            assert await checked_profile(c, "0023") == OLD_DIGEST
        cid, worker, model, _, delivery = await application(h, {"idea": "flower"})
        from m5_knowledge_search_fixtures import owner_unit
        from test_m5_portfolio_delivery_postgres import status
        from test_tenancy_postgres import BA

        send = await claim_job(h, delivery["send_job_id"])

        from asm.messaging.models import OutcomeKind

        h.adapter.outcome = OutcomeKind.UNKNOWN
        try:
            await worker.execute(send)
        finally:
            h.adapter.outcome = OutcomeKind.SUCCESS
        assert await status(h, delivery) == "UNKNOWN"
        prior = await summary(h, cid)
        fact = prior["facts"][0]
        async with owner_unit(h) as u:
            await u.intake_owner(
                BA,
                cid,
                "CONFIRM",
                "prior-owner-fact",
                {
                    "expected_version": prior["version"],
                    "expected_fingerprint": prior["fingerprint"],
                    "field": fact["field"],
                    "value": fact["value"],
                    "source": fact["source"],
                },
            )
        confirmed = await summary(h, cid)
        _, _, _, _, pending = await application(h, {"idea": "flower"}, category="COVER_UP")
        async with owner_unit(h) as u:
            assert (await u.escalation_read(pending["escalation_id"]))["status"] == "PENDING"
        before = await retained(h)
    finally:
        await _migrate("upgrade", "0024")
    await _migrate("upgrade", "0024")
    assert await retained(h) == before and await status(h, delivery) == "UNKNOWN"
    assert (await summary(h, cid))["facts"] == confirmed["facts"]
    async with h.migrator.connect() as c:
        transaction = await c.begin()
        try:
            current = await checked_profile(c, "0024")
            with pytest.raises(DBAPIError, match="INTAKE_V7_DURABLE_DATA"):
                async with c.begin_nested():
                    await c.run_sync(execute_repair, "downgrade")
            assert await checked_profile(c, "0024") == current
        finally:
            await transaction.rollback()
    assert await retained(h) == before
    await _migrate("upgrade", "0029")
    await h.runtime.check()
    from asm.messaging.errors import MessagingError

    with pytest.raises(MessagingError):
        await worker.execute(send)
    assert await status(h, delivery) == "UNKNOWN"
    assert len(model.requests) == 1 and h.adapter.calls == h.adapter.effects == 1
