"""Physical 0007 isolation, immutable provisioning and exact 0006 preservation."""

import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import command, query
from test_m2_1_postgres import messaging as messaging
from test_m2_1_schema_postgres import HistoricalScanDatabase, _migrate
from test_m2_1_schema_postgres import migrator as migrator
from test_m2_2_db_postgres import ready
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER, ingress, observed, projection, receive
from test_m2_3_db_postgres import telegram as telegram
from test_tenancy_postgres import BA, BB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


def migration():
    path = Path("migrations/versions/0007_telegram_api.py")
    spec = importlib.util.spec_from_file_location("m23_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_only_two_new_tables_forced_rls_no_runtime_control_access(migrator):
    module = migration()
    async with migrator.connect() as c:
        for table in module.TABLES:
            row = (
                await c.execute(
                    text(
                        "SELECT r.rolname,t.relrowsecurity,t.relforcerowsecurity,has_table_privilege('asm_runtime',t.oid,'SELECT'),has_table_privilege('asm_runtime',t.oid,'INSERT'),has_table_privilege('asm_runtime',t.oid,'UPDATE'),has_table_privilege('asm_runtime',t.oid,'DELETE') FROM pg_class t JOIN pg_roles r ON r.oid=t.relowner WHERE t.oid=CAST(:table AS regclass)"
                    ),
                    {"table": table},
                )
            ).one()
            assert row == ("asm_migrator", True, True, False, False, False, False)
        for signature in (*module.PUBLIC_FUNCTIONS, *module.PRIVATE_FUNCTIONS):
            row = (
                await c.execute(
                    text(
                        "SELECT has_function_privilege('asm_runtime',CAST(:fn AS regprocedure),'EXECUTE'),p.proconfig FROM pg_proc p WHERE p.oid=CAST(:fn AS regprocedure)"
                    ),
                    {"fn": signature},
                )
            ).one()
            assert row[0] == (signature in module.PUBLIC_FUNCTIONS)
            assert row[1] == ["search_path=pg_catalog, pg_temp"]
        columns = (
            (
                await c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='platform' AND table_name='telegram_update_receipts' ORDER BY ordinal_position"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert columns == [
            "id",
            "bot_identity",
            "update_id",
            "fingerprint",
            "kind",
            "result_code",
            "workspace_id",
            "connection_id",
            "inbox_id",
            "received_at",
        ]


async def test_operator_binding_is_exact_repeat_only_and_owner_identity_immutable(telegram):
    h = telegram
    statement = "SELECT platform.initialize_telegram_connection(:ws,:business,:bot,:external,:owner,CAST(:o AS jsonb))"
    args = {
        "ws": A,
        "business": BA,
        "bot": BOT,
        "external": EXTERNAL,
        "owner": OWNER,
        "o": json.dumps(observed()),
    }
    async with h.migrator.begin() as c:
        assert (await c.execute(text(statement), args)).scalar_one() == {
            "code": "NOOP",
            "connection_id": str(h.telegram_connection),
        }
        for replacement in (
            {"ws": B},
            {"owner": "8000002", "o": json.dumps(observed(owner_user_id="8000002"))},
            {"bot": "9000002"},
        ):
            with pytest.raises(DBAPIError):
                async with c.begin_nested():
                    await c.execute(text(statement), {**args, **replacement})
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():
                await c.execute(
                    text(
                        "UPDATE platform.telegram_connection_state SET owner_user_id='8000002' WHERE connection_id=:id"
                    ),
                    {"id": h.telegram_connection},
                )
        assert caught.value.orig.sqlstate == "23514"
    async with h.runtime.engine.begin() as c:
        with pytest.raises(DBAPIError) as caught:
            await c.execute(text(statement), args)
        assert caught.value.orig.sqlstate == "42501"


async def test_concurrent_fresh_provisioning_serializes_exact_repeat_and_identity_conflicts(
    telegram,
):
    h = telegram
    binding_sql = text(
        "SELECT platform.initialize_telegram_connection(:ws,:business,:bot,:external,:owner,CAST(:o AS jsonb))"
    )
    binding = {
        "ws": B,
        "business": BB,
        "bot": BOT,
        "external": "concurrent-fresh-business-B",
        "owner": "8000002",
        "o": json.dumps(
            observed(external_connection_id="concurrent-fresh-business-B", owner_user_id="8000002")
        ),
    }
    billing_sql = text(
        "SELECT platform.initialize_local_messaging_billing(:ws,'Concurrent TEST',:start,:end)"
    )
    billing = {"ws": B, "start": h.billing_interval[0], "end": h.billing_interval[1]}
    release = asyncio.Event()
    loop = asyncio.get_running_loop()
    first_ready = loop.create_future()
    tasks = []

    async def setup(hold=False, started=None):
        try:
            async with h.migrator.begin() as c:
                pid = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                if started is not None:
                    started.set_result(pid)
                account_result = (await c.execute(billing_sql, billing)).scalar_one()
                connection_result = (await c.execute(binding_sql, binding)).scalar_one()
                if hold:
                    first_ready.set_result(pid)
                    await release.wait()
                return account_result, connection_result
        except BaseException as error:
            if hold and not first_ready.done():
                first_ready.set_exception(error)
            raise

    async def conflicting_binding(overrides, started):
        try:
            async with h.migrator.begin() as c:
                started.set_result((await c.execute(text("SELECT pg_backend_pid()"))).scalar_one())
                await c.execute(binding_sql, {**binding, **overrides})
        except DBAPIError as error:
            return error.orig.sqlstate, error.orig.diag.message_primary
        raise AssertionError("Conflicting binding unexpectedly committed")

    try:
        # The first transaction has both rows but has not committed. Independent
        # connections still see a fresh B and must contend on the actual DB locks.
        tasks.append(asyncio.create_task(setup(hold=True)))
        first_pid = await asyncio.wait_for(first_ready, 5)
        starts = [loop.create_future() for _ in range(3)]
        tasks.extend(
            (
                asyncio.create_task(setup(started=starts[0])),
                asyncio.create_task(
                    conflicting_binding(
                        {
                            "owner": "8000003",
                            "o": json.dumps(
                                observed(
                                    external_connection_id=binding["external"],
                                    owner_user_id="8000003",
                                )
                            ),
                        },
                        starts[1],
                    )
                ),
                asyncio.create_task(conflicting_binding({"ws": A, "business": BA}, starts[2])),
            )
        )
        pids = await asyncio.wait_for(asyncio.gather(*starts), 5)
        assert len({first_pid, *pids}) == 4
        async with h.migrator.connect() as observer:
            async with asyncio.timeout(5):
                for pid, task in zip(pids, tasks[1:], strict=True):
                    while True:
                        blockers = (
                            await observer.execute(
                                text("SELECT pg_blocking_pids(:pid)"), {"pid": pid}
                            )
                        ).scalar_one()
                        if first_pid in blockers:
                            break
                        if task.done():
                            await task
                            raise AssertionError(
                                "Provisioning did not wait for the uncommitted setup"
                            )
                        await asyncio.sleep(0.01)
        release.set()
        created, repeated, owner_conflict, workspace_conflict = await asyncio.wait_for(
            asyncio.gather(*tasks), 10
        )
        assert created[0] == "CREATED" and created[1]["code"] == "CREATED"
        assert repeated == ("NOOP", {**created[1], "code": "NOOP"})
        assert owner_conflict == workspace_conflict == ("P2001", "NOT_ALLOWED")
        counts = (
            await query(
                h,
                "SELECT "
                "(SELECT count(*) FROM platform.workspace_billing_accounts WHERE workspace_id=:ws) AS accounts,"
                "(SELECT count(*) FROM platform.workspace_subscriptions WHERE workspace_id=:ws) AS subscriptions,"
                "(SELECT count(*) FROM platform.workspace_service_modes WHERE workspace_id=:ws) AS modes,"
                "(SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='WORKSPACE_BILLING_PROVISIONED') AS audits,"
                "(SELECT count(*) FROM app.channel_connections WHERE workspace_id=:ws AND provider='TELEGRAM') AS connections,"
                "(SELECT count(*) FROM platform.channel_routes WHERE workspace_id=:ws AND provider='TELEGRAM') AS routes,"
                "(SELECT count(*) FROM platform.telegram_connection_state WHERE workspace_id=:ws) AS states",
                ws=B,
            )
        )[0]
        assert counts == {
            "accounts": 1,
            "subscriptions": 1,
            "modes": 1,
            "audits": 1,
            "connections": 1,
            "routes": 1,
            "states": 1,
        }
        state = (
            await query(
                h,
                "SELECT connection_id::text AS connection_id,owner_user_id,generation,observation_version "
                "FROM platform.telegram_connection_state WHERE workspace_id=:ws",
                ws=B,
            )
        )[0]
        assert state == {
            "connection_id": created[1]["connection_id"],
            "owner_user_id": binding["owner"],
            "generation": 1,
            "observation_version": 1,
        }
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # The existing messaging fixture removes B's state/route/connection chain.
        # This test owns only B's fresh billing rows and their provisioning audit.
        async with h.migrator.begin() as c:
            for table in (
                "platform.billing_contact_command_receipts",
                "app.audit_events",
                "platform.workspace_service_modes",
                "platform.workspace_subscriptions",
                "platform.workspace_billing_accounts",
            ):
                suffix = (
                    " AND event_type='WORKSPACE_BILLING_PROVISIONED'"
                    if table == "app.audit_events"
                    else ""
                )
                await c.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id=:ws" + suffix), {"ws": B}
                )


async def test_composite_refs_reject_forged_workspace_connection_and_inbox(telegram):
    h = telegram
    await ingress(h, projection())
    async with h.migrator.begin() as c:
        for statement in (
            "INSERT INTO platform.telegram_connection_state(workspace_id,connection_id,bot_identity,external_connection_id,owner_user_id) VALUES(:other,:conn,:bot,:external,:owner)",
            "INSERT INTO platform.telegram_update_receipts(bot_identity,update_id,fingerprint,kind,result_code,workspace_id,connection_id) VALUES(:bot,'801',sha256('x'::bytea),'BUSINESS_CONNECTION','LIFECYCLE_INVALIDATED',:other,:conn)",
            "INSERT INTO platform.telegram_update_receipts(bot_identity,update_id,fingerprint,kind,result_code,workspace_id,connection_id,inbox_id) VALUES(:bot,'802',sha256('x'::bytea),'BUSINESS_MESSAGE','QUEUED',:ws,:conn,:fake)",
        ):
            with pytest.raises(DBAPIError) as caught:
                async with c.begin_nested():
                    await c.execute(
                        text(statement),
                        {
                            "ws": A,
                            "other": B,
                            "conn": h.telegram_connection,
                            "bot": BOT,
                            "external": EXTERNAL,
                            "owner": OWNER,
                            "fake": uuid4(),
                        },
                    )
            assert caught.value.orig.sqlstate == "23503"


async def test_fresh_only_catalog_initializer_repeats_without_old_catalog_changes(telegram):
    h = telegram
    args = {"ws": A, "start": h.billing_interval[0], "end": h.billing_interval[1]}
    async with h.migrator.begin() as c:
        before = (
            await c.execute(
                text(
                    "SELECT to_jsonb(p) FROM platform.plan_entitlements p ORDER BY plan_revision_id,capability_key"
                )
            )
        ).all()
        assert (
            await c.execute(
                text(
                    "SELECT platform.initialize_local_messaging_billing(:ws,'Telegram TEST',:start,:end)"
                ),
                args,
            )
        ).scalar_one() == "NOOP"
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():
                await c.execute(
                    text(
                        "SELECT platform.initialize_local_messaging_billing(:ws,'different contact',:start,:end)"
                    ),
                    args,
                )
        assert caught.value.orig.sqlstate == "P1301"
        assert (
            await c.execute(
                text(
                    "SELECT to_jsonb(p) FROM platform.plan_entitlements p ORDER BY plan_revision_id,capability_key"
                )
            )
        ).all() == before
        # An existing M1 workspace is never repinned to the new test product catalog.
        assert (
            await c.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'M1 original','ACTIVE','COMPED',:start,:end,'NORMAL')"
                ),
                {**args, "ws": B},
            )
        ).scalar_one() == "INITIALIZED"
        old = (
            await c.execute(
                text(
                    "SELECT to_jsonb(s) FROM platform.workspace_subscriptions s WHERE workspace_id=:ws"
                ),
                {"ws": B},
            )
        ).all()
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():
                await c.execute(
                    text(
                        "SELECT platform.initialize_local_messaging_billing(:ws,'M1 original',:start,:end)"
                    ),
                    {**args, "ws": B},
                )
        assert caught.value.orig.sqlstate == "P1301"
        assert (
            await c.execute(
                text(
                    "SELECT to_jsonb(s) FROM platform.workspace_subscriptions s WHERE workspace_id=:ws"
                ),
                {"ws": B},
            )
        ).all() == old
        await c.rollback()


async def test_downgrade_refuses_55000_before_first_destructive_statement(telegram):
    h = telegram
    await receive(h)
    before = await query(h, "SELECT id,fingerprint FROM platform.telegram_update_receipts")
    async with h.migrator.begin() as c:
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():

                def downgrade(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        migration().downgrade()

                await c.run_sync(downgrade)
        assert caught.value.orig.sqlstate == "55000"
        assert (
            await c.execute(text("SELECT version_num FROM platform.alembic_version"))
        ).scalar_one() == "0008"  # Direct 0007 refusal preserves the current head too.
        assert (
            await c.execute(text("SELECT count(*) FROM platform.telegram_connection_state"))
        ).scalar_one() == 1
    assert await query(h, "SELECT id,fingerprint FROM platform.telegram_update_receipts") == before


async def test_0006_exact_data_file_winner_unknown_and_billing_survive_full_cycle(messaging):
    h = messaging
    # The cycle below belongs to 0006 -> 0007, using those revisions' scan ABI.
    h.kernel = HistoricalScanDatabase(h.runtime.engine)
    tables = (
        "app.channel_connections",
        "app.conversations",
        "app.messages",
        "platform.inbox_events",
        "platform.messaging_jobs",
        "app.outbox_events",
        "platform.messaging_command_receipts",
        "app.file_objects",
        "platform.file_object_uploads",
        "app.audit_events",
        "platform.workspace_billing_accounts",
        "platform.workspace_subscriptions",
        "platform.workspace_service_modes",
    )

    async def snapshot():
        async with h.migrator.connect() as c:
            return {
                table: (
                    await c.execute(
                        text(
                            f"SELECT to_jsonb(t)-ARRAY['last_client_inbound_at','last_retry_after_seconds','last_retry_due','telegram_probe_claim','telegram_probe_generation','telegram_probe_version'] FROM {table} t ORDER BY to_jsonb(t)::text"
                        )
                    )
                ).all()
                for table in tables
            }

    try:
        await _migrate("downgrade", "0006")
        image, _, _ = await ready(h)
        send = await command(h, image["conversation_id"], "keep unknown exact", "m23-cycle")
        claim = await h.kernel.claim_job("cycle-unknown")
        assert claim is not None and claim.kind == "SEND_MANUAL_TEXT"
        await h.kernel.begin_send(claim)
        await query(
            h,
            "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
        await h.kernel.recover_expired()
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'Preserve M1','ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
                ),
                {"ws": A},
            )
        before = await snapshot()
        assert before["app.file_objects"] and before["platform.file_object_uploads"]
        assert (
            await query(
                h, "SELECT status FROM app.outbox_events WHERE message_id=:id", id=send.message_id
            )
        )[0]["status"] == "UNKNOWN"
        await _migrate("upgrade", "0007")
        await _migrate("upgrade", "0007")
        assert await snapshot() == before
        assert (await query(h, "SELECT last_client_inbound_at FROM app.conversations")) == [
            {"last_client_inbound_at": None}
        ]
        await _migrate("downgrade", "0006")
        assert await snapshot() == before
        await _migrate("upgrade", "0007")
        assert await snapshot() == before
    finally:
        await _migrate("upgrade", "head")
        async with h.migrator.begin() as c:
            for table in (
                "platform.billing_contact_command_receipts",
                "app.audit_events",
                "platform.workspace_service_modes",
                "platform.workspace_subscriptions",
                "platform.workspace_billing_accounts",
            ):
                suffix = (
                    " AND event_type<>'MESSAGE_SEND_REQUESTED'"
                    if table == "app.audit_events"
                    else ""
                )
                await c.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id=:ws" + suffix), {"ws": A}
                )
