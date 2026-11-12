"""Actual runtime-role configuration publication, authority, isolation and replay."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from asm.tenancy import AuthenticatedAccount
from m5_configuration_fixtures import configuration_bundle
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_tenancy_postgres import BA, BA2, BB, PROVIDER, UA, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
TABLES = tuple("platform.business_configuration_" + n for n in ("state", "releases", "receipts"))


@pytest_asyncio.fixture
async def configuration(seeded):
    runtime, migrator = seeded
    async with migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": B, "actor": UB},
        )
    try:
        yield SimpleNamespace(runtime=runtime, migrator=migrator)
    finally:
        async with migrator.begin() as c:
            for table in TABLES:
                await c.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id IN (:a,:b)"), {"a": A, "b": B}
                )
            await c.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER',status='ACTIVE' WHERE workspace_id=:ws AND user_account_id=:actor"
                ),
                {"ws": A, "actor": UA},
            )


@asynccontextmanager
async def unit(h, ws=A, actor=UA):
    from uuid import uuid4

    async with h.runtime.tenancy.transaction(AuthenticatedAccount(actor), ws, uuid4()) as value:
        yield value


async def command(h, operation, value, key, business=BA, ws=A, actor=UA):
    async with unit(h, ws, actor) as u:
        return (
            await u._execute(
                "SELECT platform.configuration_command(:business,:op,:key,CAST(:value AS jsonb))",
                {"business": business, "op": operation, "key": key, "value": json.dumps(value)},
            )
        ).scalar_one()


async def read(h, business=BA, ws=A, actor=UA, active=False):
    async with unit(h, ws, actor) as u:
        name = "configuration_active_read" if active else "configuration_owner_read"
        return (
            await u._execute(f"SELECT platform.{name}(:business)", {"business": business})
        ).scalar_one()


async def edit(h, bundle=None, version=0, key="edit", **scope):
    return await command(
        h,
        "EDIT",
        {"expected_draft_version": str(version), "bundle": bundle or configuration_bundle()},
        key,
        **scope,
    )


async def publish(h, version=1, activation=0, key="publish", **scope):
    return await command(
        h,
        "PUBLISH",
        {"expected_draft_version": str(version), "expected_activation_version": str(activation)},
        key,
        **scope,
    )


async def counts(h):
    async with h.migrator.connect() as c:
        return tuple(
            [
                (await c.execute(text("SELECT count(*) FROM " + table))).scalar_one()
                for table in TABLES
            ]
        )


async def refuses(code, operation):
    with pytest.raises(DBAPIError) as caught:
        await operation
    assert caught.value.orig.sqlstate == "P2701"
    assert caught.value.orig.diag.message_primary == code


async def test_two_businesses_edit_preview_publish_active_and_draft_isolation(configuration):
    h = configuration
    for kind, business, ws, actor in (("tattoo", BA, A, UA), ("ceramics", BB, B, UB)):
        assert (await read(h, business, ws, actor, active=True))["bundle"] is None
        bundle = configuration_bundle(kind)
        assert (await edit(h, bundle, business=business, ws=ws, actor=actor))["result"][
            "draft_version"
        ] == "1"
        assert (await read(h, business, ws, actor))["bundle"] == bundle
        assert (await read(h, business, ws, actor, active=True))["release_id"] is None
        async with h.migrator.connect() as c:
            validation = (
                await c.execute(
                    text("SELECT platform.configuration_validate(CAST(:value AS jsonb))"),
                    {"value": json.dumps(bundle)},
                )
            ).scalar_one()
        assert validation["valid"] is True
        assert (any(v["severity"] == "WARNING" for v in validation["issues"])) == (
            kind == "ceramics"
        )
        accepted = await publish(h, business=business, ws=ws, actor=actor)
        active = await read(h, business, ws, actor, active=True)
        assert active["bundle"] == bundle and active["activation_version"] == "1"
        assert active["release_id"] == accepted["result"]["release_id"]
        assert active["source_draft_version"] == "1" and active["published_by"] == str(actor)
        assert active["structured_rules_authoritative"] is True
    assert (await read(h, active=True))["bundle"] != (await read(h, BB, B, UB, active=True))[
        "bundle"
    ]


async def test_replay_concurrency_cas_key_conflict_and_atomic_release(configuration):
    h = configuration
    await edit(h)
    results = await asyncio.gather(publish(h), publish(h), return_exceptions=True)
    assert all(isinstance(value, dict) for value in results), results
    assert {v["outcome"] for v in results} == {"ACCEPTED", "REPLAY"}
    assert results[0]["result"] == results[1]["result"]
    assert await counts(h) == (1, 1, 2)
    await refuses("IDEMPOTENCY_KEY_CONFLICT", publish(h, version=2))
    await refuses("STALE_STATE", edit(h, version=0, key="old-edit"))
    bundle = configuration_bundle()
    bundle["communication_style"] = "CONCISE"
    await edit(h, bundle, version=1, key="second-edit")
    replies = await asyncio.gather(
        publish(h, version=2, activation=1, key="tab-a"),
        publish(h, version=2, activation=1, key="tab-b"),
        return_exceptions=True,
    )
    assert sum(isinstance(v, dict) for v in replies) == 1
    failure = next(v for v in replies if isinstance(v, DBAPIError))
    assert failure.orig.sqlstate == "P2701" and failure.orig.diag.message_primary == "STALE_STATE"
    assert await counts(h) == (1, 2, 4)


@pytest.mark.parametrize(
    "bad", ["mode", "reference", "unconfirmed", "conflict", "inactive", "deposit"]
)
async def test_validation_error_preserves_previous_active_release_and_audit(configuration, bad):
    h = configuration
    await edit(h)
    await publish(h)
    previous = await read(h, active=True)
    value = configuration_bundle()
    if bad == "mode":
        value["services"][0]["price"]["mode"] = "MODEL_CHOICE"
    elif bad == "reference":
        value["faqs"][0]["rule_ids"] = ["missing"]
    elif bad == "unconfirmed":
        value["faqs"][0]["confirmed"] = False
    elif bad == "conflict":
        value["rules"].append(
            {"id": "other-age", "service_id": "consultation", "kind": "MIN_AGE", "value": 16}
        )
    elif bad == "inactive":
        value["services"][0]["active"] = False
    else:
        value["services"][0]["deposit"]["percent"] = 30
    await edit(h, value, version=1, key="bad-edit")
    before = await counts(h)
    await refuses("VALIDATION_FAILED", publish(h, version=2, activation=1, key="bad-publish"))
    assert await read(h, active=True) == previous and await counts(h) == before


async def test_rollback_monotonic_activation_and_old_replay_never_reactivates(configuration):
    h = configuration
    await edit(h)
    first = await publish(h)
    value = configuration_bundle()
    value["services"][0]["price"]["amount_minor"] = 150000
    await edit(h, value, version=1, key="edit-two")
    second = await publish(h, version=2, activation=1, key="publish-two")
    rollback = {"expected_activation_version": "2", "release_id": first["result"]["release_id"]}
    accepted = await command(h, "ROLLBACK", rollback, "rollback")
    assert accepted["result"]["activation_version"] == "3"
    assert (await read(h, active=True))["release_id"] == first["result"]["release_id"]
    assert (await command(h, "ROLLBACK", rollback, "rollback"))["result"] == accepted["result"]
    replay = await publish(h, version=2, activation=1, key="publish-two")
    assert replay == {"outcome": "REPLAY", "result": second["result"]}
    assert (await read(h, active=True))["activation_version"] == "3"
    assert await counts(h) == (1, 2, 5)


@pytest.mark.parametrize("changed", ["faq", "description", "service"])
async def test_rollback_never_restores_withdrawn_or_replaced_text(configuration, changed):
    h = configuration
    await edit(h)
    first = await publish(h)
    value = configuration_bundle()
    if changed == "faq":
        value["faqs"] = []
    elif changed == "description":
        value["services"][0]["description"] = "Replacement approved text"
    else:
        value["services"][0]["id"] = "replacement"
        value["faqs"][0]["service_id"] = "replacement"
    await edit(h, value, version=1, key="replace")
    await publish(h, version=2, activation=1, key="replace-publish")
    before = await read(h, active=True), await counts(h)
    await refuses(
        "ROLLBACK_NOT_ALLOWED",
        command(
            h,
            "ROLLBACK",
            {"expected_activation_version": "2", "release_id": first["result"]["release_id"]},
            "restore",
        ),
    )
    assert (await read(h, active=True), await counts(h)) == before


async def test_owner_admin_revoked_scope_shared_active_and_private_acl(configuration):
    h = configuration
    await edit(h)
    await publish(h)
    for table in TABLES:
        async with h.runtime.engine.begin() as c:
            with pytest.raises(DBAPIError) as caught:
                await c.execute(text("SELECT * FROM " + table))
            assert caught.value.orig.sqlstate == "42501"
    assert (await read(h, actor=PROVIDER, active=True))["bundle"] is not None
    await refuses("ACCESS_DENIED", read(h, actor=PROVIDER))
    await refuses("NOT_FOUND", read(h, BB))
    assert (await read(h, BA2, active=True))["bundle"] is None
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": A, "actor": UA},
        )
    await refuses("ACCESS_DENIED", publish(h))
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": A, "actor": UA},
        )
    assert (await publish(h))["outcome"] == "REPLAY"
    async with h.migrator.begin() as c:
        for table in TABLES:
            owner, rls, forced = (
                await c.execute(
                    text(
                        "SELECT relowner::regrole::text,relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)"
                    ),
                    {"name": table},
                )
            ).one()
            assert (owner, rls, forced) == ("asm_migrator", True, True)
        for table, column in ((TABLES[1], "body"), (TABLES[2], "result")):
            with pytest.raises(DBAPIError) as caught:
                async with c.begin_nested():
                    await c.execute(text(f"UPDATE {table} SET {column}={column}"))
            assert caught.value.orig.sqlstate == "23514"


async def test_owner_role_change_and_publish_serialize_in_both_orders(configuration):
    h = configuration
    await edit(h)
    async with unit(h) as u:
        result = (
            await u._execute(
                "SELECT platform.configuration_command(:business,'PUBLISH','first',CAST(:body AS jsonb))",
                {
                    "business": BA,
                    "body": json.dumps(
                        {"expected_draft_version": "1", "expected_activation_version": "0"}
                    ),
                },
            )
        ).scalar_one()

        async def revoke():
            async with h.migrator.begin() as c:
                await c.execute(
                    text(
                        "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor"
                    ),
                    {"ws": A, "actor": UA},
                )

        pending = asyncio.create_task(revoke())
        await asyncio.sleep(0.05)
        assert not pending.done()
    await pending
    assert result["outcome"] == "ACCEPTED"
    await refuses("ACCESS_DENIED", publish(h, key="first"))
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": A, "actor": UA},
        )
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": A, "actor": UA},
        )
        pending = asyncio.create_task(publish(h, version=1, activation=1, key="loser"))
        await asyncio.sleep(0.05)
        assert not pending.done()
    with pytest.raises(DBAPIError) as caught:
        await pending
    assert caught.value.orig.diag.message_primary == "ACCESS_DENIED"


async def test_late_receipt_failure_rolls_back_release_and_activation(configuration):
    h = configuration
    await edit(h)
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform.m5_test_fail_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic late failure'; END $$"
            )
        )
        await c.execute(
            text(
                "CREATE TRIGGER m5_test_fail_receipt BEFORE INSERT ON platform.business_configuration_receipts FOR EACH ROW EXECUTE FUNCTION platform.m5_test_fail_receipt()"
            )
        )
    try:
        before = await counts(h)
        with pytest.raises(DBAPIError):
            await publish(h)
        assert await counts(h) == before
        assert (await read(h, active=True))["bundle"] is None
    finally:
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "DROP TRIGGER m5_test_fail_receipt ON platform.business_configuration_receipts"
                )
            )
            await c.execute(text("DROP FUNCTION platform.m5_test_fail_receipt()"))
    assert (await publish(h))["outcome"] == "ACCEPTED"


async def test_populated_0017_upgrade_repeat_exact_unused_reverse_and_used_refusal(configuration):
    """Real catalog/data checks, rather than a relabelled historical readiness."""
    from pathlib import Path

    from test_m2_1_schema_postgres import _migrate

    from scripts import native_context_db_catalog as catalog

    h = configuration
    previous = catalog.source_catalog(Path.cwd(), "0017")

    async def rows():
        async with h.migrator.connect() as c:
            return {
                table: sorted(
                    json.dumps(v, sort_keys=True)
                    for v in (await c.execute(text(f"SELECT to_jsonb(t) FROM {table} t"))).scalars()
                )
                for table in previous["columns"]
                if table != "platform.alembic_version"
            }

    async def profile(revision):
        expected = catalog.source_catalog(Path.cwd(), revision)
        async with h.migrator.begin() as c:
            assert (
                await c.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one() == revision
            await c.execute(text("SET LOCAL search_path=pg_catalog,pg_temp"))
            functions = [dict(v) for v in (await c.execute(text(catalog.FUNCTION_SQL))).mappings()]
            resolved = dict(
                (
                    await c.execute(
                        text(
                            "SELECT sig,to_regprocedure(sig)::bigint FROM jsonb_array_elements_text(CAST(:s AS jsonb)) t(sig)"
                        ),
                        {"s": json.dumps(list(expected["functions"]))},
                    )
                ).all()
            )
            full, nonfunction = (await c.execute(text(catalog.CATALOG_SQL))).one()
            name = (
                "business_configuration_schema_profile"
                if revision == "0018"
                else "ai_reply_rights_schema_profile"
            )
            declared = (await c.execute(text(f"SELECT platform.{name}()"))).scalar_one()
            return catalog.compare_catalog(
                expected, functions, resolved, full, nonfunction, lambda: declared
            )

    before = await rows()
    current = await profile("0018")
    await h.runtime.engine.dispose()
    try:
        await _migrate("downgrade", "0017")
        assert (await profile("0017"))[1]["valid"] is True
        assert await rows() == before
        with pytest.raises(RuntimeError, match="schema"):
            await h.runtime.check()
    finally:
        await _migrate("upgrade", "0018")
    await _migrate("upgrade", "0018")
    assert await rows() == before and await profile("0018") == current
    await h.runtime.check()
    await edit(h)
    before_used = await counts(h)
    with pytest.raises(AssertionError, match="CONFIGURATION_DURABLE_DATA"):
        await _migrate("downgrade", "0017")
    assert await counts(h) == before_used
    await h.runtime.check()


@pytest.mark.parametrize(
    "variant",
    [
        "known",
        "formula",
        "unknown",
        "mode",
        "rule_scope",
        "conflict",
        "bool_number",
        "float",
        "source",
    ],
)
async def test_python_preview_and_authoritative_sql_validation_agree(configuration, variant):
    from asm.configuration.validation import validate_bundle

    value = configuration_bundle("ceramics" if variant == "formula" else "tattoo")
    if variant == "unknown":
        value["services"][0]["price"]["amount_minor"] = None
    elif variant == "mode":
        value["services"][0]["deposit"]["mode"] = "MODEL_DEPOSIT"
    elif variant == "rule_scope":
        value["faqs"][0]["service_id"] = None
        value["rules"][0]["service_id"] = "consultation"
    elif variant == "conflict":
        value["rules"].append(
            {"id": "other-age", "service_id": "consultation", "kind": "MIN_AGE", "value": 16}
        )
    elif variant == "bool_number":
        value["services"][0]["price"]["amount_minor"] = True
    elif variant == "float":
        value["services"][0]["duration"]["minutes"] = 90.0
    elif variant == "source":
        value["faqs"][0]["source"] = "\u00a0"
    async with configuration.migrator.connect() as c:
        sql = (
            await c.execute(
                text("SELECT platform.configuration_validate(CAST(:body AS jsonb))"),
                {"body": json.dumps(value)},
            )
        ).scalar_one()
    assert sql == validate_bundle(value).model_dump()
