"""C0 regressions for existing R4 DB obligations missed by the first test matrix."""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

TABLES = (
    "platform.saas_plans",
    "platform.saas_plan_revisions",
    "platform.plan_entitlements",
    "platform.workspace_billing_accounts",
    "platform.workspace_subscriptions",
    "platform.workspace_service_modes",
    "app.audit_events",
    "platform.billing_contact_command_receipts",
)
INITIALIZE = text(
    "SELECT platform.initialize_local_billing(:ws,:code,:revision,:name,:status,"
    ":funding,'2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
)
COMMAND = text("SELECT * FROM platform.update_billing_contact(:version,:name,:key)")


def inputs(workspace, **overrides):
    return {
        "ws": workspace,
        "code": "test",
        "revision": 1,
        "name": "Before",
        "status": "ACTIVE",
        "funding": "COMPED",
        **overrides,
    }


@pytest_asyncio.fixture
async def engines():
    urls = (os.environ["ASM_MIGRATION_DATABASE_URL"], os.environ["ASM_DATABASE_URL"])
    assert all(make_url(url).database == "asm_test" for url in urls)
    migrator, runtime = (create_async_engine(url, hide_parameters=True) for url in urls)
    try:
        yield migrator, runtime
    finally:
        await runtime.dispose()
        await migrator.dispose()


@pytest_asyncio.fixture
async def billing_case(engines):
    migrator, runtime = engines
    workspace, actor = uuid4(), uuid4()
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:ws)"), {"ws": workspace}
        )
        await connection.execute(
            text("INSERT INTO platform.user_accounts(id) VALUES(:actor)"), {"actor": actor}
        )
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
            ),
            {"ws": workspace, "actor": actor},
        )
        assert (
            await connection.execute(INITIALIZE, inputs(workspace))
        ).scalar_one() == "INITIALIZED"
    return migrator, runtime, workspace, actor


async def context(connection, workspace, actor, *, with_kind=True):
    await connection.execute(
        text(
            "SELECT set_config('asm.workspace_id',:ws,true),set_config('asm.actor_id',:actor,true),"
            "set_config('asm.correlation_id',:corr,true),set_config('asm.context_xid',pg_current_xact_id()::text,true)"
        ),
        {"ws": str(workspace), "actor": str(actor), "corr": str(uuid4())},
    )
    if with_kind:
        await connection.execute(text("SELECT set_config('asm.actor_kind','user_account',true)"))


async def state(migrator, workspace):
    async with migrator.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT contact_display_name,version,updated_at,"
                    "(SELECT count(*) FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws),"
                    "(SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws) "
                    "FROM platform.workspace_billing_accounts WHERE workspace_id=:ws"
                ),
                {"ws": workspace},
            )
        ).one()


async def test_missing_actor_kind_is_denied_before_receipt_claim(billing_case):
    migrator, runtime, workspace, actor = billing_case
    before = await state(migrator, workspace)
    with pytest.raises(DBAPIError) as denied:
        async with runtime.begin() as connection:
            # Fresh physical connection: custom GUC is NULL, not an empty reset value.
            assert (
                await connection.execute(text("SELECT current_setting('asm.actor_kind',true)"))
            ).scalar_one() is None
            await context(connection, workspace, actor, with_kind=False)
            await connection.execute(
                COMMAND, {"version": 1, "name": "After", "key": "missing-kind"}
            )
    assert denied.value.orig.sqlstate == "42501"
    assert await state(migrator, workspace) == before


async def test_succeeded_receipt_rejects_null_outcome(billing_case):
    migrator, _, workspace, _ = billing_case
    with pytest.raises(DBAPIError) as invalid:
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO platform.billing_contact_command_receipts(workspace_id,billing_account_id,operation,"
                    "idempotency_key,request_fingerprint,expected_version,status,result_version,result_outcome,completed_at) "
                    "SELECT workspace_id,billing_account_id,'UPDATE_BILLING_CONTACT','null-outcome',"
                    "pg_catalog.sha256('probe'::bytea),1,'SUCCEEDED',1,NULL,CURRENT_TIMESTAMP "
                    "FROM platform.workspace_billing_accounts WHERE workspace_id=:ws"
                ),
                {"ws": workspace},
            )
    assert invalid.value.orig.sqlstate == "23514"


@pytest.mark.parametrize(
    "case", ["missing_workspace", "partial", "input", "null_code", "null_revision"]
)
async def test_initializer_conflict_has_no_catalog_or_workspace_side_effects(engines, case):
    migrator, _ = engines
    workspace = uuid4()
    async with migrator.connect() as connection:
        transaction = await connection.begin()
        try:
            # Transactional isolated catalog; rollback restores all existing test data.
            await connection.execute(
                text("TRUNCATE " + ",".join((*TABLES, "platform.messaging_command_receipts")))
            )
            if case != "missing_workspace":
                await connection.execute(
                    text("INSERT INTO platform.workspaces(id) VALUES(:ws)"), {"ws": workspace}
                )
            if case == "partial":
                await connection.execute(
                    text(
                        "INSERT INTO platform.workspace_billing_accounts(workspace_id,contact_display_name) VALUES(:ws,'Do not repair')"
                    ),
                    {"ws": workspace},
                )
            before = [
                (await connection.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
                for table in TABLES
            ]
            overrides = {
                "input": {"status": "TRIALING", "funding": "TRIAL"},
                "null_code": {"code": None},
                "null_revision": {"revision": None},
            }.get(case, {})
            result = (
                await connection.execute(INITIALIZE, inputs(workspace, **overrides))
            ).scalar_one()
            assert result.startswith("CONFLICT_")
            after = [
                (await connection.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
                for table in TABLES
            ]
            assert after == before, "bounded conflict must not leave a newly created catalog"
        finally:
            await transaction.rollback()


async def test_initializer_detects_provisioning_audit_drift(billing_case):
    migrator, _, workspace, _ = billing_case
    async with migrator.begin() as connection:
        await connection.execute(
            text("UPDATE app.audit_events SET object_version=2 WHERE workspace_id=:ws"),
            {"ws": workspace},
        )
        result = (await connection.execute(INITIALIZE, inputs(workspace))).scalar_one()
        assert result == "CONFLICT_STATE_DRIFT"
        assert (
            await connection.execute(
                text("SELECT object_version FROM app.audit_events WHERE workspace_id=:ws"),
                {"ws": workspace},
            )
        ).scalar_one() == 2


@pytest.mark.parametrize("target", ["audit", "finalize"])
async def test_command_failure_rolls_back_receipt_account_and_audit(billing_case, target):
    migrator, runtime, workspace, actor = billing_case
    before = await state(migrator, workspace)
    table, condition = {
        "audit": ("app.audit_events", "event_type <> 'BILLING_ACCOUNT_CONTACT_UPDATED'"),
        "finalize": ("platform.billing_contact_command_receipts", "status <> 'SUCCEEDED'"),
    }[target]
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                f"ALTER TABLE {table} ADD CONSTRAINT c0_injected_failure CHECK (workspace_id <> '{workspace}'::uuid OR {condition}) NOT VALID"
            )
        )
    try:
        with pytest.raises(DBAPIError) as failed:
            async with runtime.begin() as connection:
                await context(connection, workspace, actor)
                await connection.execute(
                    COMMAND, {"version": 1, "name": "After", "key": "rollback"}
                )
        assert failed.value.orig.sqlstate == "23514"
        assert await state(migrator, workspace) == before
    finally:
        async with migrator.begin() as connection:
            await connection.execute(
                text(f"ALTER TABLE {table} DROP CONSTRAINT c0_injected_failure")
            )


async def test_replay_after_later_change_rechecks_live_authorization(billing_case):
    migrator, runtime, workspace, actor = billing_case

    async def invoke(version, name, key):
        async with runtime.begin() as connection:
            await context(connection, workspace, actor)
            return dict(
                (await connection.execute(COMMAND, {"version": version, "name": name, "key": key}))
                .mappings()
                .one()
            )

    first = await invoke(1, "First", "original")
    await invoke(2, "Later", "later")
    before = await state(migrator, workspace)
    assert await invoke(1, "First", "original") == first
    assert await state(migrator, workspace) == before
    assert before[:2] == ("Later", 3)
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": workspace, "actor": actor},
        )
    for key in ("original", "never-seen"):
        with pytest.raises(DBAPIError) as denied:
            await invoke(1, "First", key)
        assert denied.value.orig.sqlstate == "42501"
    assert await state(migrator, workspace) == before


async def test_different_keys_share_fk_locks_and_have_one_cas_winner(billing_case):
    migrator, runtime, workspace, actor = billing_case
    tasks = []
    blocker = blocker_tx = None
    # AFTER INSERT barrier holds both actual command claims after their immediate
    # FK checks. Both transactions own the naturally acquired account KEY SHARE.
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "CREATE FUNCTION platform.c0_receipt_barrier() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN PERFORM pg_advisory_xact_lock_shared(1295070020,1); RETURN NEW; END $$"
            )
        )
        await connection.execute(
            text("REVOKE ALL ON FUNCTION platform.c0_receipt_barrier() FROM PUBLIC,asm_runtime")
        )
        await connection.execute(
            text(
                f"CREATE TRIGGER zz_c0_receipt_barrier AFTER INSERT ON platform.billing_contact_command_receipts FOR EACH ROW WHEN (NEW.workspace_id='{workspace}'::uuid) EXECUTE FUNCTION platform.c0_receipt_barrier()"
            )
        )

    async def command(key, pid):
        async with runtime.begin() as connection:
            await connection.execute(text("SET LOCAL lock_timeout='15s'"))
            await connection.execute(text("SET LOCAL statement_timeout='20s'"))
            await context(connection, workspace, actor)
            pid.set_result((await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one())
            return dict(
                (await connection.execute(COMMAND, {"version": 1, "name": key, "key": key}))
                .mappings()
                .one()
            )

    async def wait_for_barrier(task, pid, blocker_pid):
        async with asyncio.timeout(5):
            while True:
                if task.done():
                    await task  # Preserve primary SQLSTATE if it failed early.
                    pytest.fail("command finished before the receipt barrier")
                async with runtime.connect() as connection:
                    waiting = (
                        await connection.execute(
                            text(
                                "SELECT state='active' AND wait_event_type='Lock' AND wait_event='advisory' AND :blocker=ANY(pg_blocking_pids(pid)) FROM pg_stat_activity WHERE pid=:pid AND usename=current_user"
                            ),
                            {"pid": pid, "blocker": blocker_pid},
                        )
                    ).scalar_one_or_none()
                if waiting:
                    return
                await asyncio.sleep(0.02)

    try:
        blocker = await migrator.connect()
        blocker_tx = await blocker.begin()
        await blocker.execute(text("SELECT pg_advisory_xact_lock(1295070020,1)"))
        blocker_pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        for key in ("first-key", "second-key"):
            pid = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(command(key, pid))
            tasks.append(task)
            await wait_for_barrier(task, await asyncio.wait_for(pid, 5), blocker_pid)
        await blocker_tx.commit()
        outcomes = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
        successes = [result for result in outcomes if isinstance(result, dict)]
        errors = [result for result in outcomes if isinstance(result, DBAPIError)]
        assert len(successes) == len(errors) == 1
        assert errors[0].orig.sqlstate == "40001", (
            "losing CAS must be stale, never a FK lock-upgrade deadlock"
        )
        assert successes[0]["result_version"] == 2 and successes[0]["result_outcome"] == "UPDATED"
        after = await state(migrator, workspace)
        assert after[1] == 2 and after[3:] == (1, 2)
    finally:
        if blocker_tx is not None and blocker_tx.is_active:
            await blocker_tx.rollback()
        if blocker is not None:
            await blocker.close()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "DROP TRIGGER zz_c0_receipt_barrier ON platform.billing_contact_command_receipts"
                )
            )
            await connection.execute(text("DROP FUNCTION platform.c0_receipt_barrier()"))
