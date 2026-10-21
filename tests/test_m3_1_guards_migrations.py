"""Exact C35 → G36 preservation, refusal and disposable C/G schema controller."""

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations
from generic_pg_schema import current_snapshot
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_m2_1_models import event
from test_m2_1_postgres import command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_1_schema_postgres import _migrate
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_migrations import C_COLUMNS, definitions, digest
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import execute, incoming
from test_m3_1_guards_postgres import accepted, fresh
from test_m3_1_migrations import names
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
C = "c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5"
G_COLUMNS = {
    **C_COLUMNS,
    "platform.conversation_control_receipts": C_COLUMNS["platform.conversation_control_receipts"]
    + ("guard_profile",),
    "platform.messaging_jobs": C_COLUMNS["platform.messaging_jobs"] + ("guard_rejection",),
    "platform.turn_guard_receipts": tuple(
        "workspace_id job_id winning_claim_token connection_id conversation_id client_id turn_id turn_revision resume_receipt_id input_control_generation activation_fence_seq input_context_version snapshot_digest consumer request_fingerprint result_text outcome accepted_at intent_context_version message_id outbox_id send_job_id namespace kind step direction content_type send_kind".split()
    ),
}
assert len(C_COLUMNS) == 35 and len(G_COLUMNS) == 36


async def assert_schema(c, revision):
    assert revision in ("0009", "0010")
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == revision
    expected = C_COLUMNS if revision == "0009" else G_COLUMNS
    assert await names(c) == set(expected)
    for table, columns in expected.items():
        actual = tuple(
            (
                await c.execute(
                    text(
                        "SELECT attname FROM pg_attribute WHERE attrelid=CAST(:table AS regclass) AND attnum>0 AND NOT attisdropped ORDER BY attnum"
                    ),
                    {"table": table},
                )
            ).scalars()
        )
        assert actual == columns, (table, actual, columns)


async def fingerprints(c, *, revision="0010", projection=False):
    assert revision in ("0009", "0010")
    result = {}
    for table, columns in (C_COLUMNS if projection or revision == "0009" else G_COLUMNS).items():
        if projection and table == "platform.alembic_version":
            continue
        select = ",".join('"' + name + '"' for name in columns)
        rows = (
            await c.execute(text(f"SELECT to_jsonb(p) FROM (SELECT {select} FROM {table}) p"))
        ).scalars()
        encoded = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = {
            "count": len(encoded),
            "sha256": hashlib.sha256("\n".join(encoded).encode()).hexdigest(),
        }
    return result


async def no_backfill(c):
    for table, clause in (
        ("platform.turn_guard_receipts", "true"),
        ("platform.conversation_control_receipts", "guard_profile IS NOT NULL"),
        (
            "platform.messaging_jobs",
            "kind='SEND_GUARDED_TEXT' OR step='GUARDED_TEXT' OR guard_rejection IS NOT NULL",
        ),
        ("app.outbox_events", "kind='SEND_GUARDED_TEXT'"),
    ):
        assert (
            await c.execute(text(f"SELECT count(*) FROM {table} WHERE {clause}"))
        ).scalar_one() == 0


def migration():
    spec = importlib.util.spec_from_file_location(
        "m31_guards", Path("migrations/versions/0010_conversation_guards.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def assert_refusal(c, *, revision="0010"):
    from sqlalchemy.exc import DBAPIError

    before, ddl = await fingerprints(c), await definitions(c)
    current = await current_snapshot(c) if revision == "0013" else None
    module, executed = migration(), []

    def execute(statement):
        executed.append(statement)
        return op.execute(statement)

    module.op = SimpleNamespace(execute=execute)
    with pytest.raises(DBAPIError) as caught:
        async with c.begin_nested():

            def downgrade(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.downgrade()

            await c.run_sync(downgrade)
    assert caught.value.orig.sqlstate == "55000"
    assert len(executed) == 2 and executed[0].startswith("LOCK TABLE")
    assert executed[1].startswith("DO $$ BEGIN")
    if revision == "0013":
        assert await current_snapshot(c) == current
    elif revision == "0011":
        from test_m3_2_escalations_migrations import assert_schema as assert_e_schema

        await assert_e_schema(c)
    else:
        await assert_schema(c, "0010")
    assert await fingerprints(c) == before and await definitions(c) == ddl


async def test_clean_populated_c_cycle_fixed35_projection_and_exact_definitions(control):
    h = control
    try:
        await h.runtime.engine.dispose()
        await _migrate("downgrade", "0009")
        cid, _, _ = await incoming(h)
        await command(h, cid, "old pending exact", "c-pending")
        await execute(h, cid, "RESUME", "c-legacy-resume")
        await ingest(h, event(event_id="c-pending-inbox", message_id="c-pending-inbox"))
        with pytest.raises(RuntimeError, match="schema"):
            await h.runtime.check()
        async with h.migrator.connect() as c:
            await assert_schema(c, "0009")
            old, ddl = await fingerprints(c, revision="0009"), await definitions(c)
        for _ in range(2):
            await _migrate("upgrade", "0010")
            await _migrate("upgrade", "0010")
            # Current E source must refuse G/0010; the historical cycle stays G.
            with pytest.raises(RuntimeError, match="schema"):
                await h.runtime.check()
            async with h.migrator.connect() as c:
                await assert_schema(c, "0010")
                await no_backfill(c)
                assert await fingerprints(c, projection=True) == {
                    k: v for k, v in old.items() if k != "platform.alembic_version"
                }
            # Replay never promotes a historical NULL activation to GUARDS.
            rec = (
                await query(
                    h,
                    "SELECT result FROM platform.conversation_control_receipts WHERE idempotency_key='c-legacy-resume'",
                )
            )[0]["result"]
            from asm.conversations.http_models import ControlCommandRequest

            replay = await execute(
                h,
                cid,
                "RESUME",
                "c-legacy-resume",
                ControlCommandRequest(
                    expected_client_id=rec["client_id"],
                    expected_control_generation=rec["previous_generation"],
                    expected_context_version=rec["context_version"],
                ),
            )
            assert replay["code"] == "REPLAY"
            await _migrate("downgrade", "0009")
            async with h.migrator.connect() as c:
                await assert_schema(c, "0009")
                assert await fingerprints(c, revision="0009") == old
                assert await definitions(c) == ddl
    finally:
        await _migrate("upgrade", "head")
        await h.runtime.engine.dispose()


@pytest.mark.parametrize("usage", ["profile", "step", "receipt", "terminal_rejection"])
async def test_any_guard_usage_refuses_before_ddl_and_preserves_full_g(control, usage):
    h = control
    if usage == "profile":
        cid, _, _ = await incoming(h)
        await execute(h, cid, "RESUME", "profile-only")
    elif usage == "step":
        cid, claim = await fresh(h)
        await execute(h, cid, "TAKEOVER", "before-prepare")
        assert (await h.kernel.prepare_guarded_turn(claim)).code == "STALE"
    else:
        cid, _, _, _, send = await accepted(h)
        if usage == "terminal_rejection":
            await execute(h, cid, "TAKEOVER", "before-dispatch")
            await h.kernel.begin_guarded_send(send)
    async with h.migrator.begin() as c:
        await assert_refusal(c, revision="0013")


COMMIT_ACK_LOSS_MARKER = "GUARDS_UPGRADE_COMMITTED_RESULT_LOST"
COMMIT_ACK_LOSS = """
import os,sys
from alembic import command
from alembic.config import Config
assert os.environ['ASM_ENVIRONMENT'] in ('LOCAL','TEST')
command.upgrade(Config('alembic.ini'), '0010')
if len(sys.argv)==4 and sys.argv[1]=='--guards-schema-phase':
 from pathlib import Path
 import json
 path=Path(sys.argv[3]); saved=json.loads(path.read_text())
 saved['lost_result_process']={'pid':os.getpid(),'namespace':os.readlink('/proc/self/ns/pid'),
  'start_ticks':int(Path('/proc/self/stat').read_text().rpartition(')')[2].split()[19]),
  'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
 path.write_text(json.dumps(saved,sort_keys=True,indent=2)+'\\n'); path.chmod(0o600)
print('GUARDS_UPGRADE_COMMITTED_RESULT_LOST', flush=True)
os._exit(86)
"""


async def fresh_observation(url):
    fresh_engine = create_async_engine(url, hide_parameters=True, poolclass=NullPool)
    try:
        async with fresh_engine.connect() as c:
            revision = (
                await c.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one()
            await assert_schema(c, revision)
            data = dict(
                (
                    await c.execute(
                        text(
                            "SELECT current_user AS role,current_database() AS database,(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,inet_server_addr()::text AS server_address,pg_postmaster_start_time()::text AS postmaster_started,pg_backend_pid() AS backend_pid"
                        )
                    )
                )
                .mappings()
                .one()
            )
            return {
                **data,
                "revision": revision,
                "reader_pid": os.getpid(),
                "reader_namespace": os.readlink("/proc/self/ns/pid"),
                "reader_start_ticks": int(
                    Path("/proc/self/stat").read_text().rpartition(")")[2].split()[19]
                ),
                "reader_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            }
    finally:
        await fresh_engine.dispose()


async def test_guards_commit_ack_loss_fresh_reader_observes_actual_0010(messaging):
    h = messaging
    try:
        await _migrate("downgrade", "0009")
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            COMMIT_ACK_LOSS,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(child.communicate(), 30)
        finally:
            if child.returncode is None:
                child.kill()
                await child.wait()
        assert child.returncode == 86 and out.strip() == COMMIT_ACK_LOSS_MARKER.encode(), (out, err)
        observed = await fresh_observation(os.environ["ASM_MIGRATION_DATABASE_URL"])
        assert (
            observed["revision"] == "0010"
            and observed["role"] == "asm_migrator"
            and observed["database"] == "asm_test"
        )
        assert observed["reader_pid"] != child.pid
        # Lost ACK is still observed as actual G, which E correctly refuses.
        with pytest.raises(RuntimeError, match="schema"):
            await h.runtime.check()
    finally:
        await _migrate("upgrade", "head")
        await h.runtime.engine.dispose()


async def schema_controller(action, state_path):
    """Explicit isolated LOCAL migrator seeds T; runtime is admitted only at C/9."""
    import base64
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

    import httpx
    from asm.conversations.turns import TurnSnapshot, consume
    from asm.files.config import StorageSettings
    from asm.files.models import UploadPermit
    from asm.files.storage import S3ObjectStorage
    from asm.foundation import RuntimeDatabase, Settings
    from asm.messaging.adapter import ControlledAdapter
    from asm.messaging.database import MessagingDatabase
    from asm.messaging.worker import Worker
    from asm.tenancy import AuthenticatedAccount

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

    async def sql(statement, **params):
        async with migrator.begin() as c:
            return (await c.execute(text(statement), params)).scalar_one()

    async def identity():
        async with migrator.connect() as c:
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

    def save():
        path.write_text(json.dumps(saved, sort_keys=True, indent=2) + "\n")
        path.chmod(0o600)

    async def admitted(job, statement, **extra):
        async with migrator.begin() as c:
            args = {"job": job["job_id"], "token": job["claim_token"], **extra}
            await c.execute(text("SELECT platform.messaging_admit(:job,:token)"), args)
            return (await c.execute(text(statement), args)).scalar_one()

    async def claim():
        position = None
        async with asyncio.timeout(30):
            while True:
                scan = await sql(
                    "SELECT platform.messaging_claim('guards-schema-seed',:until,:at,:id)",
                    until=position["scan_until"] if position else None,
                    at=position["at"] if position else None,
                    id=position["id"] if position else None,
                )
                if scan["step"] == "CLAIMED":
                    return scan["claim"]
                if scan["step"] in {"TERMINALIZED", "BUSY"}:
                    # READY media supersedes the original GROUP job. Traverse
                    # the retained four-argument queue ABI, including its scan
                    # position, instead of treating maintenance as END/error.
                    position = scan
                    continue
                assert scan["step"] == "END", scan
                position = None
                due = await sql(
                    "SELECT min(available_at) FROM platform.messaging_jobs WHERE status='READY'"
                )
                if due is None:
                    return None
                await asyncio.sleep(max(0, (due - datetime.now(UTC)).total_seconds()))

    async def consume_job(job):
        value = await admitted(job, "SELECT platform.turn_execute(:job,:token)")
        if value["code"] == "SNAPSHOT":
            result = await sql(
                "SELECT platform.turn_consumer_finalize(:job,:token,CAST(:result AS jsonb))",
                job=job["job_id"],
                token=job["claim_token"],
                result=consume(TurnSnapshot.model_validate(value)).model_dump_json(),
            )
            assert result["code"] == "OBSERVED"

    async def manual(key):
        async with migrator.begin() as c:
            await c.execute(
                text(
                    "SELECT set_config('asm.actor_kind','user_account',true),set_config('asm.actor_id',:owner,true),set_config('asm.workspace_id',:ws,true),set_config('asm.correlation_id',:corr,true),set_config('asm.context_xid',pg_current_xact_id()::text,true)"
                ),
                {"owner": saved["owner"], "ws": saved["workspace"], "corr": str(uuid4())},
            )
            return (
                await c.execute(
                    text(
                        "SELECT platform.messaging_request_text(:conv,'control schema exact',:key)"
                    ),
                    {"conv": saved["conversation"], "key": key},
                )
            ).scalar_one()

    try:
        if action == "observe":
            print(json.dumps(await fresh_observation(url)), flush=True)
            return
        if action == "seed9":
            assert not saved
            async with migrator.begin() as c:
                await assert_schema(c, "0009")
                empty = await fingerprints(c, revision="0009")
                assert all(
                    r["count"] == int(t == "platform.alembic_version") for t, r in empty.items()
                )
                ws, owner, business, conn = (uuid4() for _ in range(4))
                params = dict(ws=ws, owner=owner, business=business, conn=conn)
                for statement in (
                    "INSERT INTO platform.workspaces(id) VALUES(:ws)",
                    "INSERT INTO platform.user_accounts(id) VALUES(:owner)",
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:owner,'OWNER')",
                    "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:business,'control schema')",
                    "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) VALUES(:ws,:conn,:business,'CONTROLLED','guards-schema-bot','guards-schema-connection')",
                    "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:conn,'CONTROLLED','guards-schema-bot','guards-schema-connection')",
                    "SELECT platform.initialize_local_messaging_billing(:ws,'CONTROL LOCAL','2000-01-01T00:00:00Z','2100-01-01T00:00:00Z')",
                ):
                    await c.execute(text(statement), params)
            saved.update(
                identity=await identity(), workspace=str(ws), owner=str(owner), connection=str(conn)
            )
            image = await sql(
                "SELECT platform.messaging_ingest('CONTROLLED','guards-schema-bot',CAST(:event AS jsonb),:corr)",
                event=event(
                    event_id="t-image",
                    message_id="t-image",
                    bot_identity="guards-schema-bot",
                    external_connection_id="guards-schema-connection",
                    image_file_id="private-image",
                ).encoded(),
                corr=uuid4(),
            )
            job = await claim()
            assert job["job_id"] == image["job_id"]
            projected = await admitted(job, "SELECT platform.messaging_process_inbox(:job,:token)")
            saved["conversation"] = str(
                await sql(
                    "SELECT conversation_id FROM app.messages WHERE id=:id",
                    id=projected["message_id"],
                )
            )
            fetch = await claim()
            assert fetch["kind"] == "FETCH_IMAGE"
            content = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
            )
            manifest = dict(
                mime_type="image/png",
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                width=1,
                height=1,
            )
            raw = await admitted(
                fetch,
                "SELECT platform.files_prepare_upload(:job,:token,CAST(:manifest AS jsonb))",
                manifest=json.dumps(manifest),
            )
            permit = UploadPermit.model_validate(raw)
            storage = S3ObjectStorage(StorageSettings())
            try:
                await storage.put(permit, content)
                assert await storage.get(permit.storage_key) == content
                async with httpx.AsyncClient(trust_env=False) as http:
                    unsigned = await http.get(
                        os.environ["ASM_STORAGE_ENDPOINT"]
                        + "/asm-private-local/"
                        + permit.storage_key
                    )
                assert unsigned.status_code == 403
            finally:
                await storage.close()
            await sql(
                "SELECT platform.files_finish_fetch(:job,:token,:intent)",
                job=fetch["job_id"],
                token=fetch["claim_token"],
                intent=permit.intent_id,
            )
            saved["object"] = {"key": permit.storage_key, "sha256": manifest["sha256"]}
            while (job := await claim()) is not None:
                assert job["kind"] == "PROCESS_TURN"
                await consume_job(job)
            assert await sql("SELECT count(*) FROM platform.turn_consumer_receipts") == 1
            saved["unknown"] = await manual("t-unknown")
            job = await claim()
            assert job["kind"] == "SEND_MANUAL_TEXT"
            permit = await admitted(job, "SELECT platform.messaging_begin_send(:job,:token)")
            result = await sql(
                "SELECT platform.messaging_finish_send(:job,:token,:attempt,'UNKNOWN',NULL,'UNKNOWN_EXTERNAL_RESULT',NULL)",
                job=job["job_id"],
                token=job["claim_token"],
                attempt=permit["attempt_id"],
            )
            assert result["status"] == "UNKNOWN"
            saved["pending"] = await manual("t-pending")
            saved["legacy"] = await sql(
                "SELECT platform.messaging_ingest('CONTROLLED','guards-schema-bot',CAST(:event AS jsonb),:corr)",
                event=event(
                    event_id="t-pending-inbox",
                    message_id="t-pending-inbox",
                    bot_identity="guards-schema-bot",
                    external_connection_id="guards-schema-connection",
                ).encoded(),
                corr=uuid4(),
            )
            async with migrator.begin() as c:
                await c.execute(
                    text(
                        "SELECT set_config('asm.actor_kind','user_account',true),set_config('asm.actor_id',:actor,true),set_config('asm.workspace_id',:ws,true),set_config('asm.correlation_id',:corr,true),set_config('asm.context_xid',pg_current_xact_id()::text,true)"
                    ),
                    {"actor": saved["owner"], "ws": saved["workspace"], "corr": str(uuid4())},
                )
                old = (
                    (
                        await c.execute(
                            text("SELECT * FROM app.conversations WHERE id=:id"),
                            {"id": saved["conversation"]},
                        )
                    )
                    .mappings()
                    .one()
                )
                saved["legacy_resume"] = (
                    await c.execute(
                        text(
                            "SELECT platform.conversation_control_execute(:conv,:client,'RESUME','old-c-resume',:gen,:version)"
                        ),
                        {
                            "conv": old["id"],
                            "client": old["client_id"],
                            "gen": old["control_generation"],
                            "version": old["version"],
                        },
                    )
                ).scalar_one()
            async with migrator.connect() as c:
                saved.update(
                    full9=await fingerprints(c, revision="0009"),
                    projection9=await fingerprints(c, projection=True),
                    definitions9=digest(await definitions(c)),
                )
            save()
        elif action in {"check9", "check10", "fresh", "refuse"}:
            assert await identity() == saved["identity"]
            async with migrator.connect() as c:
                await assert_schema(c, "0009" if action == "check9" else "0010")
                if action == "check9":
                    assert await fingerprints(c, revision="0009") == saved["full9"]
                    assert digest(await definitions(c)) == saved["definitions9"]
                elif action == "check10":
                    assert await fingerprints(c, projection=True) == saved["projection9"]
                    await no_backfill(c)
            storage = S3ObjectStorage(StorageSettings())
            try:
                assert (
                    hashlib.sha256(await storage.get(saved["object"]["key"])).hexdigest()
                    == saved["object"]["sha256"]
                )
            finally:
                await storage.close()
            if action == "check10":
                assert await manual("t-pending") == {**saved["pending"], "code": "REPLAY"}
                assert (
                    await sql(
                        "SELECT status FROM app.outbox_events WHERE message_id=:id",
                        id=saved["unknown"]["message_id"],
                    )
                    == "UNKNOWN"
                )
                assert (
                    await sql(
                        "SELECT status FROM app.outbox_events WHERE message_id=:id",
                        id=saved["pending"]["message_id"],
                    )
                    == "PENDING"
                )
                saved["committed_upgrade_retained"] = {
                    "tables": 35,
                    "data_projection": 34,
                    "old_receipt_replay": "EXACT",
                    "pending": "PENDING",
                    "unknown": "UNKNOWN",
                    "private_s3": "SHA256_MATCH",
                    "no_backfill": True,
                }
                save()
            elif action == "fresh":
                runtime = RuntimeDatabase(Settings())
                try:
                    await runtime.check()
                    kernel = MessagingDatabase(runtime.engine)
                    adapter = ControlledAdapter(environment="LOCAL")
                    worker = Worker(kernel, adapter)
                    async with asyncio.timeout(30):
                        while await sql(
                            "SELECT count(*) FROM platform.messaging_jobs WHERE status IN ('READY','RUNNING')"
                        ):
                            if not await worker.run_once():
                                await asyncio.sleep(0.05)
                    assert adapter.calls == adapter.effects == 1
                    before = await sql(
                        "SELECT to_jsonb(c) FROM app.conversations c WHERE id=:id",
                        id=saved["conversation"],
                    )
                    async with runtime.tenancy.transaction(
                        AuthenticatedAccount(UUID(saved["owner"])),
                        UUID(saved["workspace"]),
                        uuid4(),
                    ) as unit:
                        args = (
                            UUID(saved["conversation"]),
                            UUID(before["client_id"]),
                            "RESUME",
                            "schema-guards",
                            int(before["control_generation"]),
                            int(before["version"]),
                        )
                        accepted = await unit.conversation_control_execute(*args)
                    assert accepted["code"] == "ACCEPTED"
                    async with runtime.tenancy.transaction(
                        AuthenticatedAccount(UUID(saved["owner"])),
                        UUID(saved["workspace"]),
                        uuid4(),
                    ) as unit:
                        assert await unit.conversation_control_execute(*args) == {
                            **accepted,
                            "code": "REPLAY",
                        }
                    captured = await kernel.ingest_event(
                        adapter.source("guards-schema-bot"),
                        event(
                            event_id="g-fresh",
                            message_id="g-fresh",
                            bot_identity="guards-schema-bot",
                            external_connection_id="guards-schema-connection",
                        ),
                        uuid4(),
                    )
                    async with asyncio.timeout(30):
                        while await sql(
                            "SELECT count(*) FROM platform.messaging_jobs WHERE status IN ('READY','RUNNING')"
                        ):
                            if not await worker.run_once():
                                await asyncio.sleep(0.05)
                    assert (
                        await sql(
                            "SELECT turn_control_mode FROM platform.inbox_events WHERE id=:id",
                            id=captured.inbox_id,
                        )
                        == "AI"
                    )
                    assert (
                        await sql(
                            "SELECT status FROM app.outbox_events WHERE message_id=:id",
                            id=saved["unknown"]["message_id"],
                        )
                        == "UNKNOWN"
                    )
                    assert (
                        await sql(
                            "SELECT status FROM app.outbox_events WHERE message_id=:id",
                            id=saved["pending"]["message_id"],
                        )
                        == "SENT"
                    )
                    assert adapter.calls == adapter.effects == 2
                    assert (
                        await sql(
                            "SELECT count(*) FROM platform.turn_guard_receipts WHERE outcome='ACCEPTED'"
                        )
                        == 1
                    )
                    assert (
                        await sql(
                            "SELECT count(*) FROM app.outbox_events WHERE kind='SEND_GUARDED_TEXT' AND status='SENT'"
                        )
                        == 1
                    )
                    assert (
                        await sql(
                            "SELECT count(*) FROM platform.messaging_jobs WHERE step='GUARDED_TEXT' AND status='SUCCEEDED' AND turn_outcome='ACCEPTED'"
                        )
                        == 1
                    )
                    assert (
                        await sql(
                            "SELECT count(*) FROM platform.conversation_control_receipts WHERE guard_profile='CONTROLLED_GUARDS_V1'"
                        )
                        == 1
                    )
                    assert (
                        await sql("SELECT count(*) FROM platform.messaging_command_receipts") == 2
                    )
                    saved["forward_delivery"] = {
                        "calls": 2,
                        "effects": 2,
                        "guarded_calls": 1,
                        "guarded_effects": 1,
                        "guarded_receipts": 1,
                        "unknown": "UNKNOWN",
                        "pending": "SENT",
                        "command_receipts": 2,
                        "control_receipts": 2,
                    }
                    async with migrator.connect() as c:
                        saved["full10_populated"] = await fingerprints(c)
                    save()
                finally:
                    await runtime.close()
            elif action == "refuse":
                async with migrator.begin() as c:
                    assert await fingerprints(c) == saved["full10_populated"]
                    await assert_refusal(c)
                saved["populated_refusal"] = "PASS"
                save()
        else:
            raise AssertionError("EXPLICIT_GUARDS_SCHEMA_PHASE_REQUIRED")
        print("GUARDS_SCHEMA_" + action.upper() + "_PASS", flush=True)
    finally:
        await migrator.dispose()


if __name__ == "__main__":
    assert len(sys.argv) == 4 and sys.argv[1] == "--guards-schema-phase"
    try:
        if sys.argv[2] == "upgrade-lost-result":
            exec(COMMIT_ACK_LOSS)
        else:
            asyncio.run(schema_controller(sys.argv[2], sys.argv[3]))
    except BaseException as error:
        import traceback

        # Error locations/types only: no SQL parameters, cookies, claim tokens,
        # object keys or environment values enter the retained public report.
        detail = {
            "action": sys.argv[2],
            "type": type(error).__name__,
            "sqlstate": getattr(getattr(error, "orig", None), "sqlstate", None),
            "frames": [
                {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(error.__traceback__)
            ],
        }
        failed = Path(sys.argv[3]).with_name("controller-failure.json")
        failed.write_text(json.dumps(detail, sort_keys=True) + "\n")
        failed.chmod(0o600)
        raise
