"""Actual G/0010 → E/0011: exact profiles, RLS, old36 projections and refusal."""

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_models import event
from test_m2_1_postgres import command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_1_schema_postgres import _migrate
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_migrations import definitions
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import execute, incoming
from test_m3_1_guards_migrations import G_COLUMNS
from test_m3_1_guards_migrations import assert_schema as assert_g_schema
from test_m3_1_guards_postgres import accepted
from test_m3_1_migrations import names
from test_m3_2_escalations_postgres import created, decide
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
G = "c502d5fd258aef15bb5549e1529df8d038a4fb9b"
E_COLUMNS = {
    **G_COLUMNS,
    "app.audit_events": G_COLUMNS["app.audit_events"]
    + ("escalation_object_id", "escalation_operation"),
    "platform.messaging_jobs": G_COLUMNS["platform.messaging_jobs"]
    + ("escalation_id", "escalation_outcome"),
    "app.escalations": tuple(
        "workspace_id id namespace conversation_id client_id connection_id turn_id source_job_id source_job_kind source_job_step source_claim_token turn_revision resume_receipt_id control_generation activation_fence_seq input_context_version waiting_context_version request_snapshot context_fingerprint request_fingerprint creation_result reason assignee_user_account_id question policy created_at due_at second_reminder_at expires_at first_reminded_at second_reminded_at version status closure_reason completed_at answer_text decided_by_user_account_id".split()
    ),
    "platform.escalation_command_receipts": tuple(
        "workspace_id id namespace idempotency_key escalation_id conversation_id client_id actor_user_account_id correlation_id operation expected_version expected_control_generation expected_context_version accepted_version accepted_status accepted_context_version request_fingerprint audit_event_id audit_event_type accepted_at result".split()
    ),
}
assert len(G_COLUMNS) == 36 and len(E_COLUMNS) == 38


def migration():
    spec = importlib.util.spec_from_file_location(
        "escalations_e", Path("migrations/versions/0011_escalations.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def assert_schema(c):
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == "0011"
    assert await names(c) == set(E_COLUMNS)
    for table, columns in E_COLUMNS.items():
        actual = tuple(
            (
                await c.execute(
                    text(
                        "SELECT attname FROM pg_attribute WHERE attrelid=CAST(:t AS regclass) AND attnum>0 AND NOT attisdropped ORDER BY attnum"
                    ),
                    {"t": table},
                )
            ).scalars()
        )
        assert actual == columns, (table, actual, columns)


async def fingerprints(c, *, projection=False):
    result = {}
    for table, columns in (G_COLUMNS if projection else E_COLUMNS).items():
        if projection and table == "platform.alembic_version":
            continue
        selected = ",".join('"' + column + '"' for column in columns)
        rows = (
            await c.execute(text(f"SELECT to_jsonb(p) FROM (SELECT {selected} FROM {table}) p"))
        ).scalars()
        canonical = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = {
            "count": len(canonical),
            "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
        }
    return result


async def no_backfill(c):
    for sql in (
        "SELECT count(*) FROM app.escalations",
        "SELECT count(*) FROM platform.escalation_command_receipts",
        "SELECT count(*) FROM platform.messaging_jobs WHERE escalation_id IS NOT NULL OR escalation_outcome IS NOT NULL OR step='ESCALATE_OWNER' OR kind='ESCALATION_TIMER'",
        "SELECT count(*) FROM app.audit_events WHERE escalation_object_id IS NOT NULL OR escalation_operation IS NOT NULL",
    ):
        assert (await c.execute(text(sql))).scalar_one() == 0


async def assert_refusal(c):
    before, ddl = await fingerprints(c), await definitions(c)
    with pytest.raises(DBAPIError) as caught:
        async with c.begin_nested():

            def down(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    migration().downgrade()

            await c.run_sync(down)
    assert caught.value.orig.sqlstate == "55000"
    await assert_schema(c)
    assert await fingerprints(c) == before and await definitions(c) == ddl


async def test_clean_populated_g_cycles_exact36_rows_definitions_and_new_38_inventory(control):
    h = control
    try:
        await h.runtime.engine.dispose()
        await _migrate("downgrade", "0010")
        cid, _, _ = await incoming(h)
        await command(h, cid, "pending saved text", "g-pending")
        await execute(h, cid, "RESUME", "g-resume")
        await ingest(
            h,
            event(event_id="g-history", message_id="g-history", text="CONTROLLED ESCALATION TEST"),
        )
        async with h.migrator.connect() as c:
            await assert_g_schema(c, "0010")
            before, ddl = await fingerprints(c, projection=True), await definitions(c)
        with pytest.raises(RuntimeError, match="schema"):
            await h.runtime.check()
        for _ in range(2):
            await _migrate("upgrade", "0011")
            await _migrate("upgrade", "0011")
            await h.runtime.check()
            async with h.migrator.connect() as c:
                await assert_schema(c)
                await no_backfill(c)
                assert await fingerprints(c, projection=True) == before
            await _migrate("downgrade", "0010")
            async with h.migrator.connect() as c:
                await assert_g_schema(c, "0010")
                assert (
                    await fingerprints(c, projection=True) == before and await definitions(c) == ddl
                )
    finally:
        await _migrate("upgrade", "head")
        await h.runtime.engine.dispose()


async def test_old_guards_usage_does_not_block_unused_e_reverse(control):
    h = control
    try:
        await _migrate("downgrade", "0010")
        await accepted(h)
        async with h.migrator.connect() as c:
            before, ddl = await fingerprints(c, projection=True), await definitions(c)
        await _migrate("upgrade", "0011")
        async with h.migrator.connect() as c:
            await no_backfill(c)
            assert await fingerprints(c, projection=True) == before
        await _migrate("downgrade", "0010")
        async with h.migrator.connect() as c:
            assert await fingerprints(c, projection=True) == before and await definitions(c) == ddl
    finally:
        await _migrate("upgrade", "head")
        await h.runtime.engine.dispose()


@pytest.mark.parametrize("terminal", [False, True])
async def test_used_e_refuses_before_ddl_even_after_terminal_decision(control, terminal):
    h = control
    e, _, _ = await created(h)
    if terminal:
        await decide(h, e)
    async with h.migrator.begin() as c:
        await assert_refusal(c)


async def test_exact_e_profiles_private_clock_forced_rls_and_no_runtime_raw_access(control):
    h = control
    module = migration()
    async with h.migrator.connect() as c:
        await assert_schema(c)
        for table in ("app.escalations", "platform.escalation_command_receipts"):
            row = (
                await c.execute(
                    text(
                        "SELECT r.rolname,c.relrowsecurity,c.relforcerowsecurity,has_table_privilege('asm_runtime',c.oid,'SELECT'),has_table_privilege('asm_runtime',c.oid,'INSERT'),has_table_privilege('asm_runtime',c.oid,'UPDATE'),has_table_privilege('asm_runtime',c.oid,'DELETE') FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE c.oid=CAST(:t AS regclass)"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == ("asm_migrator", True, True, False, False, False, False)
        inventory = (
            (
                await c.execute(
                    text(
                        "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='platform' AND p.proname LIKE 'escalation_%'"
                    )
                )
            )
            .scalars()
            .all()
        )
        # regprocedure spells timestamp with time zone, so compare OID resolution
        # of the fixed eleven signatures rather than string aliases.
        expected = {
            (
                await c.execute(text("SELECT CAST(:fn AS regprocedure)::oid"), {"fn": sig})
            ).scalar_one()
            for sig in (*module.PUBLIC_FUNCTIONS, *module.PRIVATE_FUNCTIONS)
        }
        observed = set(
            (
                await c.execute(
                    text(
                        "SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='platform' AND p.proname LIKE 'escalation_%'"
                    )
                )
            ).scalars()
        )
        assert len(inventory) == 11 and observed == expected
        for sig in (*module.PUBLIC_FUNCTIONS, *module.PRIVATE_FUNCTIONS):
            row = (
                await c.execute(
                    text(
                        "SELECT r.rolname,p.prosecdef,p.provolatile,p.proisstrict,p.proconfig,has_function_privilege('asm_runtime',p.oid,'EXECUTE'),EXISTS(SELECT 1 FROM aclexplode(p.proacl) WHERE grantee=0) FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=CAST(:fn AS regprocedure)"
                    ),
                    {"fn": sig},
                )
            ).one()
            invoker = sig.startswith(
                ("platform.escalation_now(", "platform.escalation_command_fingerprint(")
            )
            volatility = (
                "i"
                if "fingerprint(" in sig
                else "s"
                if "validity(" in sig or "request_replay(" in sig
                else "v"
            )
            assert row == (
                "asm_migrator",
                not invoker,
                volatility,
                False,
                ["search_path=pg_catalog, pg_temp"],
                sig in module.PUBLIC_FUNCTIONS,
                False,
            )
        for removed in (
            "platform.messaging_claim(text)",
            "platform.messaging_recover_expired(integer)",
        ):
            assert (
                await c.execute(text("SELECT to_regprocedure(:fn)"), {"fn": removed})
            ).scalar_one() is None
        fks = (
            await c.execute(
                text(
                    "SELECT conrelid::regclass::text,confrelid::regclass::text,condeferrable,confdeltype FROM pg_constraint WHERE contype='f' AND (conrelid IN ('app.escalations'::regclass,'platform.escalation_command_receipts'::regclass) OR conname IN ('messaging_escalation_fkey','audit_events_escalation_fkey'))"
                )
            )
        ).all()
        assert len(fks) == 12 and all(not row[2] and row[3] == "r" for row in fks)
    for table in ("app.escalations", "platform.escalation_command_receipts"):
        for operation in (f"SELECT * FROM {table}", f"DELETE FROM {table}"):
            async with h.runtime.engine.begin() as c:
                with pytest.raises(DBAPIError) as caught:
                    async with c.begin_nested():
                        await c.execute(text(operation))
                assert caught.value.orig.sqlstate == "42501"
    async with h.runtime.engine.begin() as c:
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():
                await c.execute(text("SELECT platform.escalation_now()"))
        assert caught.value.orig.sqlstate == "42501"


async def test_terminal_audit_identity_and_receipt_foreign_keys_bind_client_actor_and_exact_audit(
    control,
):
    h = control
    e, _, _ = await created(h)
    await decide(h, e)
    async with h.migrator.connect() as c:
        for name, local, remote in (
            (
                "audit_events_escalation_fkey",
                ["workspace_id", "escalation_object_id"],
                ["workspace_id", "id"],
            ),
            (
                "messaging_escalation_fkey",
                ["workspace_id", "escalation_id", "connection_id"],
                ["workspace_id", "id", "connection_id"],
            ),
        ):
            row = (
                await c.execute(
                    text(
                        "SELECT ARRAY(SELECT attname FROM unnest(conkey) WITH ORDINALITY k(n,i) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.n ORDER BY i),ARRAY(SELECT attname FROM unnest(confkey) WITH ORDINALITY k(n,i) JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.n ORDER BY i) FROM pg_constraint c WHERE conname=:name"
                    ),
                    {"name": name},
                )
            ).one()
            assert row == (local, remote)
        edges = (
            await c.execute(
                text(
                    "SELECT ARRAY(SELECT attname FROM unnest(conkey) WITH ORDINALITY k(n,i) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.n ORDER BY i) FROM pg_constraint c WHERE contype='f' AND conrelid='platform.escalation_command_receipts'::regclass AND confrelid='app.audit_events'::regclass"
                )
            )
        ).scalar_one()
        assert edges == [
            "workspace_id",
            "audit_event_id",
            "escalation_id",
            "accepted_version",
            "actor_user_account_id",
            "operation",
            "audit_event_type",
        ]
        # An Audit can refer to the immutable identity without a backwards FK.
        assert (
            await c.execute(
                text(
                    "SELECT count(*) FROM pg_constraint WHERE conrelid='app.escalations'::regclass AND confrelid='app.audit_events'::regclass"
                )
            )
        ).scalar_one() == 0
    before = (await query(h, "SELECT to_jsonb(e) row FROM app.escalations e"))[0]
    for field in ("request_snapshot", "creation_result"):
        with pytest.raises(DBAPIError) as caught:
            await query(
                h,
                f"UPDATE app.escalations SET {field}={field}||jsonb_build_object('forged',true),context_fingerprint=sha256(convert_to(({field}||jsonb_build_object('forged',true))::text,'UTF8')) WHERE id=:id RETURNING *",
                id=e["id"],
            )
        assert caught.value.orig.sqlstate == "23514"
    assert (await query(h, "SELECT to_jsonb(e) row FROM app.escalations e"))[0] == before


async def canonical_residual_timers(c, saved):
    """Complete canonical set after API/worker/scheduler drain; no kind/count waiver."""
    request = (
        (
            await c.execute(
                text("SELECT * FROM app.escalations WHERE workspace_id=:ws AND id=:id"),
                {"ws": saved["workspace"], "id": saved["escalation"]["escalation_id"]},
            )
        )
        .mappings()
        .one()
    )
    assert request["status"] == "RESOLVED" and request["version"] == 2
    rows = (
        (
            await c.execute(
                text(
                    "SELECT to_jsonb(j) FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY id"
                ),
                {"id": request["id"]},
            )
        )
        .scalars()
        .all()
    )
    expected = {row["id"]: row for row in saved["timers"]}
    assert len(rows) == len(expected) == 3 and {row["id"] for row in rows} == set(expected)
    due = {
        "REMIND_1": request["due_at"],
        "REMIND_2": request["second_reminder_at"],
        "EXPIRE": request["expires_at"],
    }
    ready = []
    for row in rows:
        original = expected[row["id"]]
        for field in (
            "workspace_id",
            "id",
            "connection_id",
            "kind",
            "escalation_id",
            "step",
            "available_at",
            "correlation_id",
            "created_at",
        ):
            assert row[field] == original[field], field
        assert row["workspace_id"] == saved["workspace"] and row["connection_id"] == str(
            request["connection_id"]
        )
        assert row["escalation_id"] == str(request["id"]) and row["kind"] == "ESCALATION_TIMER"
        from datetime import datetime

        assert datetime.fromisoformat(row["available_at"]) == due[row["step"]]
        assert row["claim_token"] is row["lease_until"] is row["worker_id"] is None
        assert all(
            row[field] is None
            for field in (
                "inbox_id",
                "outbox_id",
                "file_id",
                "turn_id",
                "turn_revision",
                "turn_input",
                "turn_outcome",
                "guard_rejection",
            )
        )
        if row["status"] == "READY":
            assert row == original and row["attempt_count"] == 0 and row["first_started_at"] is None
            ready.append(row)
        else:
            assert (
                row["status"] == "SUCCEEDED"
                and row["escalation_outcome"] == "NOOP_TERMINAL"
                and row["error_code"] is None
            )
            assert (
                row["attempt_count"] == 1
                and row["first_started_at"] is not None
                and row["completed_at"] is not None
            )
    remaining = (
        (
            await c.execute(
                text(
                    "SELECT to_jsonb(j) FROM platform.messaging_jobs j WHERE status IN ('READY','RUNNING') ORDER BY id"
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining == ready  # complete inventory, not just known-kind inclusion
    return rows


async def phase_fingerprint(c, saved):
    """All E data except the precisely bound three timer rows (checked separately)."""
    result = {}
    for table, columns in E_COLUMNS.items():
        selected = ",".join('"' + column + '"' for column in columns)
        suffix = (
            " WHERE id<>ALL(CAST(:ids AS uuid[]))" if table == "platform.messaging_jobs" else ""
        )
        rows = (
            await c.execute(
                text(f"SELECT to_jsonb(p) FROM (SELECT {selected} FROM {table}{suffix}) p"),
                {"ids": [r["id"] for r in saved["timers"]]},
            )
        ).scalars()
        canonical = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = {
            "count": len(canonical),
            "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
        }
    return result


async def schema_controller(action, state_path):
    """G image produces its baseline; E only observes G, then uses normal E API/worker.

    Called solely by the proposed, separately reviewed disposable controller.
    No clock substitution, future-job mutation/deletion or production endpoint.
    """
    import asyncio
    from uuid import uuid4

    import httpx
    from asm.auth.crypto import PASSWORD_HASHER, new_token
    from asm.conversations.escalations import MARKER
    from asm.files.config import StorageSettings
    from asm.files.storage import S3ObjectStorage
    from asm.foundation import RuntimeDatabase, Settings, create_app
    from asm.messaging.adapter import ControlledAdapter
    from asm.messaging.database import MessagingDatabase
    from asm.messaging.worker import Worker
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from test_m3_1_control_migrations import digest

    url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    target = make_url(url)
    assert (target.username, target.database, target.host) == (
        "asm_migrator",
        "asm_local",
        "postgres",
    )
    assert os.environ["ASM_ENVIRONMENT"] == "LOCAL"
    migrator = create_async_engine(url, hide_parameters=True, poolclass=NullPool)
    path = Path(state_path)
    saved = json.loads(path.read_text()) if path.exists() else {}

    def save():
        path.write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
        path.chmod(0o600)

    async def sql(statement, **params):
        async with migrator.begin() as c:
            return (await c.execute(text(statement), params)).scalar_one()

    async def identity(c):
        return dict(
            (
                await c.execute(
                    text(
                        "SELECT current_database() AS database,(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,inet_server_addr()::text AS server_address,pg_postmaster_start_time()::text AS postmaster_started"
                    )
                )
            )
            .mappings()
            .one()
        )

    try:
        if action == "observe":
            async with migrator.connect() as c:
                revision = (
                    await c.execute(text("SELECT version_num FROM platform.alembic_version"))
                ).scalar_one()
                assert revision in ("0010", "0011")
                if revision == "0011":
                    await assert_schema(c)
                else:
                    await assert_g_schema(c, "0010")
                observed = {
                    **await identity(c),
                    "role": "asm_migrator",
                    "revision": revision,
                    "backend_pid": (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one(),
                    "reader_pid": os.getpid(),
                    "reader_namespace": os.readlink("/proc/self/ns/pid"),
                    "reader_start_ticks": int(
                        Path("/proc/self/stat").read_text().rpartition(")")[2].split()[19]
                    ),
                    "reader_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                }
            print(json.dumps(observed), flush=True)
            return
        if action == "seed10":
            # The unchanged G controller already ran fresh through its own image.
            assert saved["forward_delivery"]["calls"] == saved["forward_delivery"]["effects"] == 2
            async with migrator.connect() as c:
                await assert_g_schema(c, "0010")
                assert await identity(c) == saved["identity"]
                from test_m3_1_guards_migrations import fingerprints as g_fingerprints

                assert await g_fingerprints(c) == saved["full10_populated"]
                saved.update(
                    projection10=await fingerprints(c, projection=True),
                    definitions10=digest(await definitions(c)),
                    source10=G,
                )
            save()
        else:
            async with migrator.connect() as c:
                assert await identity(c) == saved["identity"] and saved["source10"] == G
                if action == "check10":
                    await assert_g_schema(c, "0010")
                    from test_m3_1_guards_migrations import fingerprints as g_fingerprints

                    assert (
                        await g_fingerprints(c) == saved["full10_populated"]
                        and digest(await definitions(c)) == saved["definitions10"]
                    )
                else:
                    await assert_schema(c)
                if action == "check11":
                    assert await fingerprints(c, projection=True) == saved["projection10"]
                    await no_backfill(c)
            storage = S3ObjectStorage(StorageSettings())
            try:
                assert (
                    hashlib.sha256(await storage.get(saved["object"]["key"])).hexdigest()
                    == saved["object"]["sha256"]
                )
            finally:
                await storage.close()
            assert (
                await sql(
                    "SELECT status FROM app.outbox_events WHERE message_id=:id",
                    id=saved["unknown"]["message_id"],
                )
                == "UNKNOWN"
            )
            if action == "fresh":
                settings = Settings()
                runtime = RuntimeDatabase(settings)
                await runtime.check()
                adapter = ControlledAdapter(environment="LOCAL")
                worker = Worker(MessagingDatabase(runtime.engine, environment="LOCAL"), adapter)
                password = new_token()
                await sql(
                    "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) VALUES(:actor,'escalation-schema-owner',:password) RETURNING user_account_id",
                    actor=saved["owner"],
                    password=PASSWORD_HASHER.hash(password),
                )
                app = create_app(settings, runtime)
                base = settings.auth_origins[0]
                async with (
                    app.router.lifespan_context(app),
                    httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url=base
                    ) as client,
                ):
                    boot = await client.post(
                        "/api/v1/auth/bootstrap",
                        json={},
                        headers={"Origin": base, "X-CSRF-Bootstrap": "1"},
                    )
                    assert boot.status_code == 200
                    login = await client.post(
                        "/api/v1/auth/login",
                        json={"login": "escalation-schema-owner", "password": password},
                        headers={"Origin": base, "X-CSRF-Token": boot.json()["csrf_token"]},
                    )
                    assert login.status_code == 200
                    headers = {"Origin": base, "X-CSRF-Token": login.json()["csrf_token"]}
                    root = f"/api/v1/workspaces/{saved['workspace']}"
                    conversation = root + f"/conversations/{saved['conversation']}"
                    current = (await client.get(conversation + "/control")).json()
                    response = await client.post(
                        conversation + "/resume",
                        json={
                            "expected_client_id": current["client_id"],
                            "expected_control_generation": current["control_generation"],
                            "expected_context_version": current["context_version"],
                        },
                        headers=headers | {"Idempotency-Key": "escalation-schema-resume"},
                    )
                    assert response.status_code == 200
                    incoming = event(
                        event_id="e-marker",
                        message_id="e-marker",
                        bot_identity="guards-schema-bot",
                        external_connection_id="guards-schema-connection",
                        text=MARKER,
                    )
                    one, two = await asyncio.gather(
                        *(
                            worker.database.ingest_event(
                                adapter.source("guards-schema-bot"), incoming, uuid4()
                            )
                            for _ in range(2)
                        )
                    )
                    assert {one.code, two.code} == {
                        "ACCEPTED",
                        "DUPLICATE",
                    } and one.job_id == two.job_id
                    async with asyncio.timeout(30):
                        while await sql("SELECT count(*) FROM app.escalations") == 0:
                            await worker.run_once()
                            await asyncio.sleep(0.02)
                    request = await sql("SELECT creation_result FROM app.escalations")
                    # Finish other ordinary ready work through the worker. Only
                    # this request's three future canonical timers may remain.
                    async with asyncio.timeout(30):
                        while await sql(
                            "SELECT count(*) FROM platform.messaging_jobs WHERE status IN ('READY','RUNNING') AND escalation_id IS DISTINCT FROM CAST(:id AS uuid)",
                            id=request["escalation_id"],
                        ):
                            await worker.run_once()
                            await asyncio.sleep(0.02)
                    endpoint = root + "/escalations/" + request["escalation_id"]
                    page = await client.get(root + "/escalations")
                    assert page.status_code == 200 and len(page.json()["items"]) == 1
                    view = (await client.get(endpoint)).json()
                    assert view["waiting"] == "WAITING_FOR_HUMAN" and view["can_resolve"]
                    answer = {
                        "expected_conversation_id": view["conversation_id"],
                        "expected_client_id": view["client_id"],
                        "expected_escalation_version": view["version"],
                        "expected_control_generation": view["current_context"][
                            "control_generation"
                        ],
                        "expected_context_version": view["current_context"]["context_version"],
                        "answer_text": " Exact LOCAL internal e\u0301 🎨\n",
                    }
                    first = await client.post(
                        endpoint + "/resolve",
                        json=answer,
                        headers=headers | {"Idempotency-Key": "e-resolution"},
                    )
                    replay = await client.post(
                        endpoint + "/resolve",
                        json=answer,
                        headers=headers | {"Idempotency-Key": "e-resolution"},
                    )
                    assert first.status_code == replay.status_code == 200
                    assert replay.json() == {"outcome": "REPLAY", "result": first.json()["result"]}
                    terminal = (await client.get(endpoint)).json()
                    assert (
                        terminal["status"] == "RESOLVED"
                        and terminal["resolution"]["answer_text"] == answer["answer_text"]
                        and terminal["waiting"] is None
                    )
                    file = await sql(
                        "SELECT to_jsonb(f) FROM app.file_objects f WHERE status='READY'"
                    )
                    grant = await client.post(
                        root
                        + f"/conversations/{file['conversation_id']}/messages/{file['message_id']}/files/{file['id']}/read-grant",
                        json={},
                        headers=headers,
                    )
                    assert grant.status_code == 200
                    async with httpx.AsyncClient(trust_env=False) as wire:
                        signed = await wire.get(grant.json()["url"])
                        anonymous = await wire.get(grant.json()["url"].split("?", 1)[0])
                    assert (
                        signed.status_code == 200
                        and hashlib.sha256(signed.content).hexdigest() == saved["object"]["sha256"]
                        and anonymous.status_code == 403
                    )
                    assert adapter.calls == adapter.effects == 0
                    saved["escalation"] = request
                    saved["decision"] = first.json()
                    saved["private_s3"] = "SIGNED_GET_200_UNSIGNED_403_SHA256_MATCH"
                async with migrator.connect() as c:
                    saved["timers"] = (
                        (
                            await c.execute(
                                text(
                                    "SELECT to_jsonb(j) FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY id"
                                ),
                                {"id": request["escalation_id"]},
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert len(saved["timers"]) == 3 and all(
                        t["status"] == "READY" and t["attempt_count"] == 0 for t in saved["timers"]
                    )
                    await canonical_residual_timers(c, saved)
                    saved["protected11"] = await phase_fingerprint(c, saved)
                save()
            elif action == "refuse":
                async with migrator.begin() as c:
                    saved["observed_timers"] = await canonical_residual_timers(c, saved)
                    assert await phase_fingerprint(c, saved) == saved["protected11"]
                    await assert_refusal(c)
                saved["populated_refusal"] = "PASS"
                save()
            elif action not in ("check10", "check11"):
                raise AssertionError("EXPLICIT_ESCALATION_SCHEMA_PHASE_REQUIRED")
        print("ESCALATION_SCHEMA_" + action.upper() + "_PASS", flush=True)
    finally:
        await migrator.dispose()


if __name__ == "__main__":
    assert len(sys.argv) == 4 and sys.argv[1] == "--escalation-schema-phase"
    try:
        if sys.argv[2] == "upgrade-lost-result":
            from alembic import command as alembic_command
            from alembic.config import Config

            assert os.environ["ASM_ENVIRONMENT"] == "LOCAL"
            alembic_command.upgrade(Config("alembic.ini"), "0011")
            path = Path(sys.argv[3])
            saved = json.loads(path.read_text())
            saved["lost_result_process"] = {
                "pid": os.getpid(),
                "namespace": os.readlink("/proc/self/ns/pid"),
                "start_ticks": int(
                    Path("/proc/self/stat").read_text().rpartition(")")[2].split()[19]
                ),
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            }
            path.write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
            path.chmod(0o600)
            print("ESCALATION_UPGRADE_COMMITTED_RESULT_LOST", flush=True)
            os._exit(86)
        else:
            import asyncio

            asyncio.run(schema_controller(sys.argv[2], sys.argv[3]))
    except BaseException as error:
        import traceback

        detail = {
            "action": sys.argv[2],
            "type": type(error).__name__,
            "sqlstate": getattr(getattr(error, "orig", None), "sqlstate", None),
            "frames": [
                {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                for f in traceback.extract_tb(error.__traceback__)
            ],
        }
        failed = Path(sys.argv[3]).with_name("controller-failure.json")
        failed.write_text(json.dumps(detail, sort_keys=True) + "\n")
        failed.chmod(0o600)
        raise


@pytest.mark.parametrize("wrong", ["client", "actor", "audit"])
async def test_actual_receipt_foreign_keys_reject_forged_terminal_links(control, wrong):
    """Real FK rejection: production-created request, Audit and receipt, intact guards."""
    from uuid import uuid4

    h = control
    e, _, _ = await created(h)
    await decide(h, e, "RESOLVE")
    async with h.migrator.begin() as c:
        original = (
            await c.execute(text("SELECT to_jsonb(r) FROM platform.escalation_command_receipts r"))
        ).scalar_one()
        changed = dict(original)
        field = {
            "client": "client_id",
            "actor": "actor_user_account_id",
            "audit": "audit_event_id",
        }[wrong]
        changed[field] = str(uuid4())
        if field in changed["result"]:
            changed["result"] = {**changed["result"], field: changed[field]}
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():
                # Delete only inside the rolled-back savepoint to avoid a unique
                # key collision masking the FK. No FK/trigger is disabled.
                await c.execute(
                    text("DELETE FROM platform.escalation_command_receipts WHERE id=:id"),
                    {"id": original["id"]},
                )
                await c.execute(
                    text(
                        "INSERT INTO platform.escalation_command_receipts SELECT (jsonb_populate_record(NULL::platform.escalation_command_receipts,CAST(:row AS jsonb))).*"
                    ),
                    {"row": json.dumps(changed)},
                )
        assert caught.value.orig.sqlstate == "23503"
        assert (
            await c.execute(text("SELECT to_jsonb(r) FROM platform.escalation_command_receipts r"))
        ).scalar_one() == original
