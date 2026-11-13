"""Current exact0015 catalog, retained0014 data and guarded migration lifecycle."""

import asyncio
import itertools
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.ai.fake import FakeAdapter
from asm.foundation import RuntimeDatabase, Settings, create_worker
from asm.messaging.results import TurnJobClaim
from generic_pg_schema import assert_current_schema, current_snapshot, historical_native_check
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_m2_1_postgres import command
from test_m3_1_native_context_postgres import claim_job, incoming, migrate, scalar
from test_m4_agent import config
from test_m4_delivery_postgres import application, enrollment, run_turn, source_turn
from test_m4_runtime_postgres import COUNTER, intent
from test_m4_runtime_postgres import pg as pg

from scripts.m4_runtime_db import preparation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


async def probe_checks(h):
    async with h.migrator.begin() as c:
        return dict(
            (
                await c.execute(
                    text(
                        "SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='platform.messaging_jobs'::regclass AND conname IN ('messaging_jobs_telegram_probe_check','messaging_jobs_telegram_probe_generation_check','messaging_jobs_telegram_probe_version_check')"
                    )
                )
            ).all()
        )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def schema15(pg):
    # Retain a real0014 AIRun/result, not merely an empty predecessor table.
    _, claim, _ = await intent(pg)
    cfg = config()
    receipt = await pg.ai.execute(
        claim, cfg, FakeAdapter(cfg.route), deadline=datetime.now(UTC) + timedelta(seconds=30)
    )
    before = await scalar(
        pg, "SELECT to_jsonb(r) FROM platform.ai_runs r WHERE id=:id", id=receipt.run_id
    )
    pg.probe_checks_0014 = await probe_checks(pg)
    assert len(pg.probe_checks_0014) == 3
    await migrate("upgrade", "0019")
    await migrate("upgrade", "0019")
    assert (
        await scalar(
            pg,
            "SELECT to_jsonb(r)-'knowledge_pin'-'active_projection'-'knowledge_release_id' FROM platform.ai_runs r WHERE id=:id",
            id=receipt.run_id,
        )
        == before
    )
    assert await scalar(pg, "SELECT count(*) FROM platform.ai_deliveries") == 0
    assert (
        await scalar(pg, "SELECT to_jsonb(c) FROM app.conversations c WHERE id=:id", id=pg.retained)
        == pg.retained_before
    )
    pg.schema_revision = "0019"
    return pg


async def test_unused_successor_downgrade_restore_and_exact_readiness(schema15):
    h = schema15
    runtime = RuntimeDatabase(Settings())
    try:
        async with h.migrator.begin() as c:
            before = await current_snapshot(c)
        await runtime.check()
        with pytest.raises(RuntimeError, match="schema"):
            await historical_native_check(runtime)
        await migrate("downgrade", "0014")
        assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0014"
        assert await probe_checks(h) == h.probe_checks_0014
        with pytest.raises(RuntimeError, match="schema"):
            await runtime.check()
        assert await scalar(h, "SELECT to_regclass('platform.ai_deliveries')") is None
        await migrate("upgrade", "0019")
        await runtime.check()
        async with h.migrator.begin() as c:
            assert await current_snapshot(c) == before
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    "damage",
    [
        "ALTER TABLE platform.ai_deliveries NO FORCE ROW LEVEL SECURITY",
        "GRANT SELECT ON platform.ai_deliveries TO asm_runtime",
        "GRANT EXECUTE ON FUNCTION platform.ai_delivery_schema_profile() TO PUBLIC",
        "ALTER FUNCTION platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs) RESET search_path",
        "ALTER TABLE platform.ai_deliveries DROP CONSTRAINT ai_deliveries_selected_kind_check",
        "CREATE FUNCTION platform.unapproved_ai() RETURNS int LANGUAGE sql AS 'SELECT 1'",
    ],
)
async def test_current_catalog_refuses_body_acl_rls_constraint_and_extra_capability(
    schema15, damage
):
    h = schema15
    async with h.migrator.connect() as c:
        transaction = await c.begin()
        try:
            await c.execute(text(damage))
            with pytest.raises(Exception) as caught:
                await assert_current_schema(c)
            assert type(caught.value).__name__ in {"AssertionError", "Refusal"}
        finally:
            await transaction.rollback()
    async with h.migrator.begin() as c:
        await assert_current_schema(c)


async def test_durable_enrollment_blocks_downgrade_before_any_mutation(schema15):
    h = schema15
    _, source, _ = await source_turn(h)
    worker, _ = application(h)
    await worker.execute(source)
    assert (await enrollment(h, source))["selected_kind"] is None
    async with h.migrator.begin() as c:
        before = await current_snapshot(c)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "downgrade",
        "0014",
        env=dict(os.environ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode != 0 and b"AI_DELIVERY_DURABLE_DATA" in stderr
    async with h.migrator.begin() as c:
        assert await current_snapshot(c) == before


async def test_probe_check_shape_and_old_ai_rejection_on_real_jobs(schema15):
    h = schema15
    _, source, _ = await source_turn(h)
    worker, fake = application(h)
    assert worker.ai is not None
    _, d = await run_turn(h, worker, source)
    assert d["selected_kind"] == "reply" and len(fake.requests) == 1
    # Use genuine send kinds and their Outbox FKs, not a kind-only row rewrite.
    _, _, manual_cid = await incoming(
        h, next(COUNTER), chat_id=str(uuid4()), external_connection_id="conn-a2"
    )
    manual = await command(h, manual_cid, key=str(uuid4()))
    manual_job = await scalar(
        h, "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id", id=manual.outbox_id
    )
    guarded_cid, guarded_source, _ = await source_turn(h)
    guarded_job = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE turn_id=:id AND turn_revision=:revision AND step='GUARDED_TEXT'",
        id=guarded_source.turn_id,
        revision=guarded_source.turn_revision,
    )
    guarded_worker = create_worker(h.kernel, h.adapter, environment="TEST")
    assert guarded_worker.ai is None
    guarded_claim = await claim_job(h, guarded_job)
    assert isinstance(guarded_claim, TurnJobClaim)
    assert (
        guarded_claim.job_id,
        guarded_claim.workspace_id,
        guarded_claim.turn_id,
        guarded_claim.turn_revision,
        guarded_claim.step,
    ) == (
        guarded_job,
        guarded_source.workspace_id,
        guarded_source.turn_id,
        guarded_source.turn_revision,
        "GUARDED_TEXT",
    )
    await guarded_worker.execute(guarded_claim)
    guarded_receipt = await scalar(
        h,
        "SELECT to_jsonb(r) FROM platform.turn_guard_receipts r WHERE job_id=:id",
        id=guarded_job,
    )
    assert guarded_receipt["outcome"] == "ACCEPTED"
    assert guarded_receipt["consumer"] == "CONTROLLED_GUARDS_V1"
    guarded_send = await scalar(
        h,
        "SELECT j.id FROM platform.messaging_jobs j JOIN app.outbox_events o ON (o.workspace_id,o.id)=(j.workspace_id,j.outbox_id) JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE m.conversation_id=:id AND j.kind='SEND_GUARDED_TEXT'",
        id=guarded_cid,
    )
    assert guarded_receipt["send_job_id"] == str(guarded_send)
    assert await scalar(
        h, "SELECT outbox_id FROM platform.messaging_jobs WHERE id=:id", id=guarded_send
    ) == UUID(guarded_receipt["outbox_id"])
    assert await scalar(
        h,
        "SELECT message_id FROM app.outbox_events WHERE id=:id",
        id=UUID(guarded_receipt["outbox_id"]),
    ) == UUID(guarded_receipt["message_id"])
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.ai_deliveries WHERE source_job_id=:id",
            id=guarded_job,
        )
        == 0
    )
    jobs = {
        "SEND_AI_TEXT": d["send_job_id"],
        "SEND_MANUAL_TEXT": manual_job,
        "SEND_GUARDED_TEXT": guarded_send,
        "PROCESS_TURN": source.job_id,
    }
    for kind, job in jobs.items():
        assert (
            await scalar(h, "SELECT kind FROM platform.messaging_jobs WHERE id=:id", id=job) == kind
        )
    async with h.migrator.begin() as c:
        before = await current_snapshot(c)
    checks = await probe_checks(h)
    name = "messaging_jobs_telegram_probe_check"
    assert checks[name] != h.probe_checks_0014[name]
    assert {k: v for k, v in checks.items() if k != name} == {
        k: v for k, v in h.probe_checks_0014.items() if k != name
    }
    update = text(
        "UPDATE platform.messaging_jobs SET telegram_probe_claim=:claim,telegram_probe_generation=:generation,telegram_probe_version=:version WHERE id=:job"
    )
    async with h.migrator.connect() as c:
        transaction = await c.begin()
        try:
            # Real jobs and installed CHECKs; each successful/failed mutation rolls back.
            for kind in ("SEND_MANUAL_TEXT", "SEND_AI_TEXT", "SEND_GUARDED_TEXT", "PROCESS_TURN"):
                for present in itertools.product((False, True), repeat=3):
                    params = dict(
                        kind=kind,
                        claim=uuid4() if present[0] else None,
                        generation=1 if present[1] else None,
                        version=1 if present[2] else None,
                        job=jobs[kind],
                    )
                    allowed = (
                        not any(present)
                        or all(present)
                        and kind in {"SEND_MANUAL_TEXT", "SEND_AI_TEXT"}
                    )
                    savepoint = await c.begin_nested()
                    try:
                        if allowed:
                            assert (await c.execute(update, params)).rowcount == 1
                        else:
                            with pytest.raises(IntegrityError) as caught:
                                await c.execute(update, params)
                            assert caught.value.orig.sqlstate == "23514"
                            assert caught.value.orig.diag.constraint_name == name
                    finally:
                        await savepoint.rollback()
            for field in ("generation", "version"):
                for invalid in (0, -1):
                    params = dict(
                        kind="SEND_AI_TEXT",
                        claim=uuid4(),
                        generation=1,
                        version=1,
                        job=d["send_job_id"],
                    )
                    params[field] = invalid
                    savepoint = await c.begin_nested()
                    try:
                        with pytest.raises(IntegrityError) as caught:
                            await c.execute(update, params)
                        assert caught.value.orig.sqlstate == "23514"
                        assert (
                            caught.value.orig.diag.constraint_name
                            == f"messaging_jobs_telegram_probe_{field}_check"
                        )
                    finally:
                        await savepoint.rollback()
            # Causal old-DDL control, not a runtime readiness attempt against drift.
            await c.execute(
                text(
                    f"ALTER TABLE platform.messaging_jobs DROP CONSTRAINT {name}, ADD CONSTRAINT {name} {h.probe_checks_0014[name]}"
                )
            )
            savepoint = await c.begin_nested()
            try:
                with pytest.raises(IntegrityError) as caught:
                    await c.execute(
                        update,
                        dict(
                            kind="SEND_AI_TEXT",
                            claim=uuid4(),
                            generation=1,
                            version=1,
                            job=d["send_job_id"],
                        ),
                    )
                assert caught.value.orig.sqlstate == "23514"
                assert caught.value.orig.diag.constraint_name == name
                preparation(
                    "OLD_CHECK_REJECTION",
                    sqlstate=caught.value.orig.sqlstate,
                    constraint_name=caught.value.orig.diag.constraint_name,
                )
            finally:
                await savepoint.rollback()
        finally:
            await transaction.rollback()
    async with h.migrator.begin() as c:
        assert await current_snapshot(c) == before
