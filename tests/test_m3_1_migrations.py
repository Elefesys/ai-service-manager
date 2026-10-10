"""Exact H/0007 preservation and I/0008 schema phase; no production updater."""

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from asm.foundation import RuntimeDatabase, Settings
from asm.messaging.database import MessagingDatabase
from asm.telegram.database import TelegramReceipt
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_models import event
from test_m2_1_postgres import command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_1_schema_postgres import HistoricalScanDatabase, _migrate
from test_m2_2_db_postgres import ready
from test_m2_3_db_postgres import ingress, projection
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_turns_postgres import claim_exact, receive, seal, snapshot, turns
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
HISTORICAL = "754f1c883e5a94a7fc9e729af2605424f949ba33"

# Fixed H column projection from immutable 0001--0007, checked against physical
# PostgreSQL before upgrade. Never infer acceptable columns from a candidate DB.
H_COLUMNS = {
    "app.audit_events": (
        "workspace_id",
        "audit_event_id",
        "occurred_at",
        "actor_kind",
        "actor_user_account_id",
        "correlation_id",
        "event_type",
        "object_type",
        "object_id",
        "object_version",
        "payload",
        "billing_account_object_id",
        "message_object_id",
    ),
    "app.business_members": (
        "workspace_id",
        "id",
        "business_id",
        "user_account_id",
        "name",
        "role",
        "status",
        "version",
        "created_at",
    ),
    "app.businesses": ("workspace_id", "id", "name", "status", "version", "created_at"),
    "app.channel_connections": (
        "workspace_id",
        "id",
        "business_id",
        "provider",
        "bot_identity",
        "external_connection_id",
        "status",
        "version",
        "created_at",
    ),
    "app.client_identities": (
        "workspace_id",
        "id",
        "client_id",
        "provider",
        "external_user_id",
        "created_at",
    ),
    "app.clients": ("workspace_id", "id", "version", "created_at"),
    "app.conversations": (
        "workspace_id",
        "id",
        "connection_id",
        "business_id",
        "client_id",
        "identity_id",
        "provider_chat_id",
        "version",
        "created_at",
        "last_client_inbound_at",
    ),
    "app.file_objects": (
        "workspace_id",
        "id",
        "message_id",
        "connection_id",
        "conversation_id",
        "required_direction",
        "required_content_type",
        "status",
        "winner_intent_id",
        "winner_state",
        "storage_key",
        "mime_type",
        "size_bytes",
        "sha256",
        "width",
        "height",
        "error_code",
        "version",
        "created_at",
        "completed_at",
    ),
    "app.locations": (
        "workspace_id",
        "id",
        "business_id",
        "name",
        "status",
        "version",
        "created_at",
    ),
    "app.messages": (
        "workspace_id",
        "id",
        "conversation_id",
        "connection_id",
        "provider_chat_id",
        "provider_message_id",
        "direction",
        "content_type",
        "text",
        "image_file_id",
        "media_group_id",
        "occurred_at",
        "projection_fingerprint",
        "version",
        "created_at",
    ),
    "app.outbox_events": (
        "workspace_id",
        "id",
        "connection_id",
        "message_id",
        "kind",
        "required_direction",
        "status",
        "attempt_id",
        "provider_message_id",
        "error_code",
        "completed_at",
        "version",
        "created_at",
    ),
    "platform.alembic_version": ("version_num",),
    "platform.auth_credentials": (
        "user_account_id",
        "login",
        "password_hash",
        "version",
        "created_at",
    ),
    "platform.auth_sessions": (
        "token_hash",
        "user_account_id",
        "credential_version",
        "account_version",
        "created_at",
        "expires_at",
        "revoked_at",
    ),
    "platform.billing_contact_command_receipts": (
        "workspace_id",
        "receipt_id",
        "billing_account_id",
        "operation",
        "idempotency_key",
        "request_fingerprint",
        "expected_version",
        "status",
        "result_version",
        "result_outcome",
        "created_at",
        "completed_at",
    ),
    "platform.channel_routes": (
        "workspace_id",
        "id",
        "connection_id",
        "provider",
        "bot_identity",
        "route_key",
        "created_at",
    ),
    "platform.file_object_uploads": (
        "workspace_id",
        "id",
        "file_id",
        "job_id",
        "claim_token",
        "storage_key",
        "mime_type",
        "size_bytes",
        "sha256",
        "width",
        "height",
        "status",
        "cleanup_claim_token",
        "cleanup_lease_until",
        "cleanup_attempts",
        "next_check_at",
        "last_checked_at",
        "cleanup_outcome",
        "version",
        "created_at",
    ),
    "platform.inbox_events": (
        "workspace_id",
        "id",
        "connection_id",
        "provider",
        "bot_identity",
        "external_connection_id",
        "required_direction",
        "event_id",
        "normalized_event",
        "event_fingerprint",
        "correlation_id",
        "received_at",
        "status",
        "result_code",
        "message_id",
        "completed_at",
        "version",
    ),
    "platform.messaging_command_receipts": (
        "workspace_id",
        "id",
        "operation",
        "idempotency_key",
        "request_fingerprint",
        "actor_user_account_id",
        "correlation_id",
        "message_id",
        "outbox_id",
        "audit_event_id",
        "accepted_at",
    ),
    "platform.messaging_jobs": (
        "workspace_id",
        "id",
        "connection_id",
        "kind",
        "inbox_id",
        "outbox_id",
        "correlation_id",
        "status",
        "available_at",
        "claim_token",
        "lease_until",
        "worker_id",
        "attempt_count",
        "first_started_at",
        "error_code",
        "completed_at",
        "last_attempt_id",
        "last_claim_token",
        "last_outcome",
        "last_provider_message_id",
        "last_error_code",
        "version",
        "created_at",
        "file_id",
        "last_retry_after_seconds",
        "last_retry_due",
        "telegram_probe_claim",
        "telegram_probe_generation",
        "telegram_probe_version",
    ),
    "platform.plan_entitlements": (
        "plan_revision_id",
        "capability_key",
        "value_kind",
        "enabled",
        "limit_value",
        "criticality",
        "created_at",
    ),
    "platform.saas_plan_revisions": (
        "plan_revision_id",
        "plan_id",
        "revision",
        "publication_state",
        "published_at",
        "created_at",
    ),
    "platform.saas_plans": ("plan_id", "code", "display_name", "status", "created_at"),
    "platform.telegram_connection_state": (
        "workspace_id",
        "connection_id",
        "provider",
        "bot_identity",
        "external_connection_id",
        "owner_user_id",
        "generation",
        "observation_version",
        "observed_generation",
        "observed_at",
        "observation_xid",
        "is_enabled",
        "can_reply",
        "error_code",
    ),
    "platform.telegram_update_receipts": (
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
    ),
    "platform.user_accounts": ("id", "status", "version", "created_at"),
    "platform.workspace_billing_accounts": (
        "workspace_id",
        "billing_account_id",
        "contact_display_name",
        "version",
        "created_at",
        "updated_at",
    ),
    "platform.workspace_memberships": (
        "workspace_id",
        "user_account_id",
        "role",
        "status",
        "version",
        "created_at",
    ),
    "platform.workspace_service_modes": (
        "workspace_id",
        "service_mode_id",
        "mode",
        "reason_code",
        "effective_from",
        "effective_until",
        "version",
        "created_at",
        "updated_at",
    ),
    "platform.workspace_subscriptions": (
        "workspace_id",
        "subscription_id",
        "plan_revision_id",
        "required_publication_state",
        "status",
        "funding_mode",
        "effective_from",
        "effective_until",
        "version",
        "created_at",
        "updated_at",
    ),
    "platform.workspaces": ("id", "status", "version", "created_at"),
}
I_TABLES = set(H_COLUMNS) | {
    "app.conversation_turns",
    "app.conversation_turn_messages",
    "platform.turn_consumer_receipts",
}


def migration():
    spec = importlib.util.spec_from_file_location(
        "m31", Path("migrations/versions/0008_conversation_turns.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def names(c):
    return set(
        (
            await c.execute(
                text(
                    "SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname IN ('app','platform')"
                )
            )
        ).scalars()
    )


async def fingerprints(c, *, projection=False):
    result = {}
    tables = H_COLUMNS if projection else {name: None for name in sorted(await names(c))}
    for table, columns in tables.items():
        if projection and table == "platform.alembic_version":
            continue
        select = ",".join('"' + col + '"' for col in columns) if columns else "*"
        rows = (
            (await c.execute(text(f"SELECT to_jsonb(p) FROM (SELECT {select} FROM {table}) p")))
            .scalars()
            .all()
        )
        canonical = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = {
            "count": len(rows),
            "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
        }
    return result


async def definitions(c):
    functions = (
        await c.execute(
            text(
                "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid),p.proacl::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app','platform') AND p.prokind='f' ORDER BY 1,2,3"
            )
        )
    ).all()
    relations = (
        await c.execute(
            text(
                "SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform') AND c.relkind='r' ORDER BY 1,2"
            )
        )
    ).all()
    return functions, relations


async def assert_head(c, revision):
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == revision
    assert await names(c) == (set(H_COLUMNS) if revision == "0007" else I_TABLES)
    if revision == "0007":
        for table, expected in H_COLUMNS.items():
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
            assert actual == expected, table


async def test_0007_0008_clean_cycle_preserves_all_rows_functions_grants_and_versions(messaging):
    h = messaging
    current = h.kernel
    try:
        await _migrate("downgrade", "0007")
        h.kernel = HistoricalScanDatabase(h.runtime.engine)
        image, _, _ = await ready(h, event_id="legacy-image", message_id="legacy-image")
        unknown = await command(h, image["conversation_id"], "canonical unknown", "m3-old-unknown")
        claim = await h.kernel.claim_job("legacy-unknown")
        await h.kernel.begin_send(claim)
        await query(
            h,
            "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
        assert await h.kernel.recover_expired() == 1
        pending = await command(h, image["conversation_id"], "pending exact", "m3-old-pending")
        await ingest(h, event(event_id="unprocessed", message_id="unprocessed"))
        async with h.migrator.connect() as c:
            await assert_head(c, "0007")
            before = await fingerprints(c)
            projection = await fingerprints(c, projection=True)
            original = await definitions(c)
        await h.runtime.engine.dispose()
        await _migrate("upgrade", "head")
        await _migrate("upgrade", "head")
        async with h.migrator.connect() as c:
            await assert_head(c, "0008")
            assert await fingerprints(c, projection=True) == projection
            assert (
                await c.execute(
                    text(
                        "SELECT count(*) FROM platform.inbox_events WHERE turn_ingress_seq IS NOT NULL OR turn_ingress_at IS NOT NULL"
                    )
                )
            ).scalar_one() == 0
            assert (
                await c.execute(text("SELECT count(*) FROM app.conversation_turns"))
            ).scalar_one() == 0
            assert (
                await c.execute(
                    text(
                        "SELECT bool_and(control_mode='HUMAN' AND control_generation=1) FROM app.conversations"
                    )
                )
            ).scalar_one()
        # No current worker is admitted during this drained empty-M3 cycle.
        await _migrate("downgrade", "0007")
        async with h.migrator.connect() as c:
            await assert_head(c, "0007")
            assert await fingerprints(c) == before
            assert await definitions(c) == original
        assert unknown.message_id != pending.message_id
    finally:
        await _migrate("upgrade", "head")
        h.kernel = current
        await h.runtime.engine.dispose()


@pytest.mark.parametrize("conflicting", [False, True])
@pytest.mark.parametrize("provider", ["CONTROLLED", "TELEGRAM"])
async def test_legacy_pending_and_duplicate_first_preserve_fence_and_payload_winner(
    telegram, conflicting, provider
):
    h = telegram
    first_projection = projection(update="9011", message="5011")
    first_projection["event"]["text"] = "old"
    try:
        await _migrate("downgrade", "0007")
        if provider == "CONTROLLED":
            legacy = await ingest(h, event(event_id="legacy", message_id="same", text="old"))
        else:
            legacy = TelegramReceipt.model_validate(await ingress(h, first_projection))
    finally:
        await _migrate("upgrade", "head")
    assert not await turns(h)
    if provider == "CONTROLLED":
        duplicate = await ingest(
            h,
            event(
                event_id="fresh-duplicate", message_id="same", text="new" if conflicting else "old"
            ),
        )
    else:
        fresh_projection = projection(update="9012", message="5011")
        fresh_projection["event"].update(
            text="new" if conflicting else "old",
            occurred_at=first_projection["event"]["occurred_at"],
        )
        duplicate = TelegramReceipt.model_validate(await ingress(h, fresh_projection))
    # Post-cutover duplicate wins the M2 projection while the legacy namespace
    # still wins the M3 origin fence, including a conflicting old projection.
    message = await h.kernel.process_inbox(await claim_exact(h, duplicate.job_id))
    assert message.code == "PROCESSED" and not await turns(h)
    old = await h.kernel.process_inbox(await claim_exact(h, legacy.job_id))
    assert old.code == ("MESSAGE_ID_CONFLICT" if conflicting else "DUPLICATE")
    assert not await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='PROCESS_TURN'")
    assert (await query(h, "SELECT text,version FROM app.messages")) == [
        {"text": "new" if conflicting else "old", "version": 1}
    ]
    assert (await query(h, "SELECT version FROM app.conversations")) == [{"version": 2}]
    if provider == "CONTROLLED":
        await receive(h, event_id="fresh", message_id="fresh")
    else:
        fresh = TelegramReceipt.model_validate(
            await ingress(h, projection(update="9013", message="5013"))
        )
        await h.kernel.process_inbox(await claim_exact(h, fresh.job_id))
    assert len(await turns(h)) == 1


@pytest.mark.parametrize("stage", ["mark", "membership", "receipt"])
async def test_populated_refusal_is_before_destructive_ddl_and_preserves_exact_snapshot(
    messaging, stage
):
    h = messaging
    if stage == "mark":
        await ingest(h)
    else:
        await receive(h)
        if stage == "receipt":
            from asm.conversations.turns import consume

            turn = (await turns(h))[0]
            await seal(h, turn["id"])
            claim, value = await snapshot(h, turn["id"])
            await h.kernel.finish_turn(claim, consume(value))
    async with h.migrator.begin() as c:
        before, objects = await fingerprints(c), await definitions(c)
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():

                def downgrade(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        migration().downgrade()

                await c.run_sync(downgrade)
        assert caught.value.orig.sqlstate == "55000"
        await assert_head(c, "0008")
        assert await fingerprints(c) == before and await definitions(c) == objects
    # No M3 row is deleted to force a cycle; only the ordinary end-of-test
    # child-first tenant cleanup follows after refusal has been proved.


async def test_migration_capabilities_are_narrow_and_sequence_is_logged_cache_one(messaging):
    h = messaging
    module = migration()
    async with h.migrator.connect() as c:
        for signature in (*module.PUBLIC_FUNCTIONS, *module.PRIVATE_FUNCTIONS):
            row = (
                await c.execute(
                    text(
                        "SELECT has_function_privilege('asm_runtime',CAST(:fn AS regprocedure),'EXECUTE'),p.proconfig FROM pg_proc p WHERE p.oid=CAST(:fn AS regprocedure)"
                    ),
                    {"fn": signature},
                )
            ).one()
            assert row == (
                signature in module.PUBLIC_FUNCTIONS,
                ["search_path=pg_catalog, pg_temp"],
            )
        assert (
            await c.execute(
                text(
                    "SELECT to_regprocedure('platform.messaging_claim(text)'),to_regprocedure('platform.messaging_recover_expired(integer)')"
                )
            )
        ).one() == (None, None)
        seq = (
            await c.execute(
                text(
                    "SELECT c.relpersistence,s.seqcache,s.seqcycle,has_sequence_privilege('asm_runtime',c.oid,'USAGE,SELECT,UPDATE') FROM pg_class c JOIN pg_sequence s ON s.seqrelid=c.oid WHERE c.oid='platform.turn_ingress_seq'::regclass"
                )
            )
        ).one()
        assert seq == ("p", 1, False, False)


# Executed only by an explicit disposable TEST/LOCAL migrator subprocess. The
# exact nonzero exit occurs AFTER Alembic has returned from its committed DDL;
# the orchestrator cannot confuse an arbitrary migration failure with this cut.
COMMIT_ACK_LOSS_EXIT = 86
COMMIT_ACK_LOSS_MARKER = "M3_UPGRADE_COMMITTED_RESULT_LOST"
COMMIT_ACK_LOSS = """
import os
from alembic import command
from alembic.config import Config
assert os.environ['ASM_ENVIRONMENT'] in ('LOCAL','TEST')
command.upgrade(Config('alembic.ini'), '0008')
print('M3_UPGRADE_COMMITTED_RESULT_LOST', flush=True)
os._exit(86)
"""


async def test_upgrade_commit_ack_loss_observes_revision_before_runtime_choice(messaging):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    h = messaging
    await _migrate("downgrade", "0007")
    with pytest.raises(Exception):
        await h.runtime.check()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        COMMIT_ACK_LOSS,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, errors = await asyncio.wait_for(process.communicate(), 30)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == COMMIT_ACK_LOSS_EXIT, (output, errors)
    assert output.strip() == COMMIT_ACK_LOSS_MARKER.encode(), (output, errors)
    # No pre-existing pool/transaction or successful child exit is authoritative.
    fresh = create_async_engine(os.environ["ASM_MIGRATION_DATABASE_URL"], poolclass=NullPool)
    try:
        async with fresh.connect() as c:
            await assert_head(c, "0008")
    finally:
        await fresh.dispose()
    await h.runtime.check()


async def schema_controller(action, state_path):
    """Disposable LOCAL migration-role SQL controller. No I runtime on 0007."""
    from types import SimpleNamespace

    import httpx
    from asm.files.config import StorageSettings
    from asm.files.models import UploadPermit
    from asm.files.storage import S3ObjectStorage
    from asm.messaging.adapter import ControlledAdapter
    from asm.messaging.worker import Worker
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    target = make_url(url)
    assert (
        target.username == "asm_migrator"
        and target.database == "asm_local"
        and target.host == "postgres"
    )
    assert os.environ["ASM_ENVIRONMENT"] == "LOCAL"
    migrator = create_async_engine(url, hide_parameters=True)
    path = Path(state_path)
    state = json.loads(path.read_text()) if path.exists() else {}

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

    async def save():
        path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
        path.chmod(0o600)

    try:
        if action == "observe":
            # This controller is a NEW process with a NEW physical connection.
            async with migrator.connect() as c:
                observed = (
                    await c.execute(text("SELECT version_num FROM platform.alembic_version"))
                ).scalar_one()
                identity_row = (await c.execute(text("SELECT current_user,pg_backend_pid()"))).one()
                assert identity_row[0] == "asm_migrator"
            print(
                json.dumps(
                    {
                        "revision": observed,
                        "reader_pid": os.getpid(),
                        "backend_pid": identity_row[1],
                        "role": identity_row[0],
                    }
                ),
                flush=True,
            )
            return
        if action == "seed":
            assert not state
            async with migrator.begin() as c:
                await assert_head(c, "0007")
                assert all(
                    row["count"] == (table == "platform.alembic_version")
                    for table, row in (await fingerprints(c)).items()
                )
                ws, owner, business, conn = (uuid4() for _ in range(4))
                params = dict(ws=ws, owner=owner, business=business, conn=conn)
                for statement in (
                    "INSERT INTO platform.workspaces(id) VALUES(:ws)",
                    "INSERT INTO platform.user_accounts(id) VALUES(:owner)",
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:owner,'OWNER')",
                    "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:business,'schema fixture')",
                    "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) VALUES(:ws,:conn,:business,'CONTROLLED','schema-bot','schema-connection')",
                    "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:conn,'CONTROLLED','schema-bot','schema-connection')",
                ):
                    await c.execute(text(statement), params)
            state.update(
                identity=await identity(), workspace=str(ws), owner=str(owner), connection=str(conn)
            )

            async def legacy_ingest(key, **fields):
                value = event(
                    event_id=key,
                    message_id=key,
                    bot_identity="schema-bot",
                    external_connection_id="schema-connection",
                    **fields,
                )
                return await sql(
                    "SELECT platform.messaging_ingest('CONTROLLED','schema-bot',CAST(:event AS jsonb),:corr)",
                    event=value.encoded(),
                    corr=uuid4(),
                )

            image = await legacy_ingest("old-image", image_file_id="schema-image")
            async with migrator.begin() as c:
                job = (
                    await c.execute(text("SELECT platform.messaging_claim('schema-legacy-sql')"))
                ).scalar_one()
                assert job["job_id"] == image["job_id"]
                await c.execute(
                    text("SELECT platform.messaging_admit(:job,:token)"),
                    {"job": job["job_id"], "token": job["claim_token"]},
                )
                projected = (
                    await c.execute(
                        text("SELECT platform.messaging_process_inbox(:job,:token)"),
                        {"job": job["job_id"], "token": job["claim_token"]},
                    )
                ).scalar_one()
            conv = await sql(
                "SELECT conversation_id FROM app.messages WHERE id=:id", id=projected["message_id"]
            )
            state["conversation"] = str(conv)
            # A real private object and canonical READY file, with no DB transaction
            # held during S3 I/O. The bytes are a valid one-pixel PNG.
            import base64

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
            async with migrator.begin() as c:
                fetch = (
                    await c.execute(text("SELECT platform.messaging_claim('schema-legacy-sql')"))
                ).scalar_one()
                assert fetch["kind"] == "FETCH_IMAGE"
                args = {"job": fetch["job_id"], "token": fetch["claim_token"]}
                await c.execute(text("SELECT platform.messaging_admit(:job,:token)"), args)
                raw = (
                    await c.execute(
                        text(
                            "SELECT platform.files_prepare_upload(:job,:token,CAST(:manifest AS jsonb))"
                        ),
                        {**args, "manifest": json.dumps(manifest)},
                    )
                ).scalar_one()
            permit = UploadPermit.model_validate(raw)
            storage = S3ObjectStorage(StorageSettings())
            try:
                await storage.put(permit, content)
                assert await storage.get(permit.storage_key) == content
                async with httpx.AsyncClient(trust_env=False) as http:
                    response = await http.get(
                        os.environ["ASM_STORAGE_ENDPOINT"]
                        + "/asm-private-local/"
                        + permit.storage_key
                    )
                assert response.status_code == 403
            finally:
                await storage.close()
            await sql(
                "SELECT platform.files_finish_fetch(:job,:token,:intent)",
                **args,
                intent=permit.intent_id,
            )
            state["object"] = {"key": permit.storage_key, "sha256": manifest["sha256"]}

            async def manual(key):
                async with migrator.begin() as c:
                    await c.execute(
                        text(
                            "SELECT set_config('asm.actor_kind','user_account',true),set_config('asm.actor_id',:owner,true),set_config('asm.workspace_id',:ws,true),set_config('asm.correlation_id',:corr,true),set_config('asm.context_xid',pg_current_xact_id()::text,true)"
                        ),
                        {"owner": str(owner), "ws": str(ws), "corr": str(uuid4())},
                    )
                    return (
                        await c.execute(
                            text(
                                "SELECT platform.messaging_request_text(:conv,'schema exact manual',:key)"
                            ),
                            {"conv": conv, "key": key},
                        )
                    ).scalar_one()

            unknown = await manual("schema-unknown")
            async with migrator.begin() as c:
                job = (
                    await c.execute(text("SELECT platform.messaging_claim('schema-legacy-sql')"))
                ).scalar_one()
                args = {"job": job["job_id"], "token": job["claim_token"]}
                await c.execute(text("SELECT platform.messaging_admit(:job,:token)"), args)
                await c.execute(text("SELECT platform.messaging_begin_send(:job,:token)"), args)
            # No adapter call in the seed: the durable DISPATCHING recovery
            # conservatively proves UNKNOWN without a live external service.
            async with migrator.begin() as c:
                await c.execute(
                    text(
                        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:job"
                    ),
                    args,
                )
            assert (await sql("SELECT platform.messaging_recover_expired(100)"))["recovered"] == 1
            pending = await manual("schema-pending")
            legacy = await legacy_ingest("legacy-pending", text="legacy exact")
            state.update(unknown=unknown, pending=pending, legacy=legacy)
            async with migrator.connect() as c:
                state["full7"] = await fingerprints(c)
                state["projection7"] = await fingerprints(c, projection=True)
                state["definitions7"] = hashlib.sha256(
                    repr(await definitions(c)).encode()
                ).hexdigest()
            await save()
        elif action in {"check8", "check7", "refuse", "fresh"}:
            assert await identity() == state["identity"]
            revision = "0007" if action == "check7" else "0008"
            async with migrator.connect() as c:
                await assert_head(c, revision)
                if action == "check7":
                    assert await fingerprints(c) == state["full7"]
                    assert (
                        hashlib.sha256(repr(await definitions(c)).encode()).hexdigest()
                        == state["definitions7"]
                    )
                elif action == "check8":
                    assert await fingerprints(c, projection=True) == state["projection7"]
                    assert (
                        await c.execute(
                            text(
                                "SELECT count(*) FROM platform.inbox_events WHERE turn_ingress_seq IS NOT NULL"
                            )
                        )
                    ).scalar_one() == 0
                    assert (
                        await c.execute(text("SELECT count(*) FROM app.conversation_turns"))
                    ).scalar_one() == 0
                    assert (
                        await c.execute(
                            text(
                                "SELECT bool_and(control_mode='HUMAN' AND control_generation=1) FROM app.conversations"
                            )
                        )
                    ).scalar_one()
            storage = S3ObjectStorage(StorageSettings())
            try:
                assert (
                    hashlib.sha256(await storage.get(state["object"]["key"])).hexdigest()
                    == state["object"]["sha256"]
                )
            finally:
                await storage.close()
            if action == "check8":
                state["committed_upgrade_retained"] = {
                    "projection": "EXACT_M2_COLUMNS",
                    "private_s3_sha256": state["object"]["sha256"],
                    "pending": await sql(
                        "SELECT status FROM app.outbox_events WHERE message_id=:id",
                        id=state["pending"]["message_id"],
                    ),
                    "unknown": await sql(
                        "SELECT status FROM app.outbox_events WHERE message_id=:id",
                        id=state["unknown"]["message_id"],
                    ),
                    "command_receipts": await sql(
                        "SELECT count(*) FROM platform.messaging_command_receipts"
                    ),
                }
                assert state["committed_upgrade_retained"]["pending"] == "PENDING"
                assert state["committed_upgrade_retained"]["unknown"] == "UNKNOWN"
                assert state["committed_upgrade_retained"]["command_receipts"] == 2
                await save()
            if action == "fresh":
                runtime = RuntimeDatabase(Settings())
                try:
                    await runtime.check()
                    kernel = MessagingDatabase(runtime.engine)
                    h = SimpleNamespace(
                        runtime=runtime,
                        migrator=migrator,
                        kernel=kernel,
                        adapter=ControlledAdapter(environment="LOCAL"),
                    )
                    # Duplicate-first legacy fence via actual runtime on 0008.
                    duplicate = await kernel.ingest_event(
                        h.adapter.source("schema-bot"),
                        event(
                            event_id="fresh-duplicate",
                            message_id="legacy-pending",
                            bot_identity="schema-bot",
                            external_connection_id="schema-connection",
                            text="legacy exact",
                        ),
                        uuid4(),
                    )
                    # Arrange only fixture due time; no production priority filter.
                    selected = await claim_exact(h, duplicate.job_id)
                    await kernel.process_inbox(selected)
                    assert not await turns(h)
                    await kernel.ingest_event(
                        h.adapter.source("schema-bot"),
                        event(
                            event_id="fresh-turn",
                            message_id="fresh-turn",
                            bot_identity="schema-bot",
                            external_connection_id="schema-connection",
                        ),
                        uuid4(),
                    )
                    await query(
                        h,
                        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE status='READY' RETURNING id",
                    )
                    worker = Worker(kernel, h.adapter)
                    async with asyncio.timeout(30):
                        while not await query(
                            h, "SELECT job_id FROM platform.turn_consumer_receipts"
                        ):
                            worked = await worker.run_once()
                            if not worked:
                                await asyncio.sleep(0.05)
                    assert len(await turns(h)) == 1
                    assert (
                        await sql(
                            "SELECT status FROM app.outbox_events WHERE message_id=:id",
                            id=state["unknown"]["message_id"],
                        )
                    ) == "UNKNOWN"
                    assert h.adapter.calls == h.adapter.effects == 1
                    assert (
                        await sql(
                            "SELECT status FROM app.outbox_events WHERE message_id=:id",
                            id=state["pending"]["message_id"],
                        )
                        == "SENT"
                    )
                    assert (
                        await sql("SELECT count(*) FROM platform.messaging_command_receipts") == 2
                    )
                    state["forward_delivery"] = {
                        "calls": h.adapter.calls,
                        "effects": h.adapter.effects,
                        "pending": "SENT",
                        "unknown": "UNKNOWN",
                        "command_receipts": 2,
                    }
                    state["full8_populated"] = None
                    async with migrator.connect() as c:
                        state["full8_populated"] = await fingerprints(c)
                    await save()
                finally:
                    await runtime.close()
            elif action == "refuse":
                async with migrator.begin() as c:
                    before, objects = await fingerprints(c), await definitions(c)
                    assert before == state["full8_populated"]
                    with pytest.raises(DBAPIError) as caught:
                        async with c.begin_nested():

                            def downgrade(sync):
                                with Operations.context(MigrationContext.configure(sync)):
                                    migration().downgrade()

                            await c.run_sync(downgrade)
                    assert caught.value.orig.sqlstate == "55000"
                    assert await fingerprints(c) == before and await definitions(c) == objects
                    state["populated_refusal"] = "PASS"
                await save()
        else:
            raise AssertionError("EXPLICIT_SCHEMA_PHASE_REQUIRED")
        print("M3_SCHEMA_" + action.upper() + "_PASS", flush=True)
    finally:
        await migrator.dispose()


if __name__ == "__main__":
    assert len(sys.argv) == 4 and sys.argv[1] == "--schema-phase"
    if sys.argv[2] == "upgrade-lost-result":
        exec(COMMIT_ACK_LOSS)
    else:
        asyncio.run(schema_controller(sys.argv[2], sys.argv[3]))
