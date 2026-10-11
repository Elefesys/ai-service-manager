"""Exact T/0008 → C/0009 preservation and disposable migration-role controller."""

import asyncio
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
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_m2_1_models import event
from test_m2_1_postgres import command, finish_text_turns, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_1_schema_postgres import _migrate
from test_m2_2_db_postgres import ready
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import execute, incoming, process_receipt
from test_m3_1_migrations import names
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
T = "ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad"

# Fixed from accepted T DDL, never computed from a database/intersection.
T_COLUMNS = {
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
    "app.conversation_turn_messages": (
        "workspace_id",
        "message_id",
        "turn_id",
        "conversation_id",
        "connection_id",
        "direction",
        "content_type",
        "origin_inbox_id",
        "turn_ingress_at",
        "turn_ingress_seq",
        "file_id",
    ),
    "app.conversation_turns": (
        "workspace_id",
        "id",
        "conversation_id",
        "connection_id",
        "provider_chat_id",
        "revision",
        "control_generation",
        "state",
        "policy_version",
        "debounce_ms",
        "group_ms",
        "media_ms",
        "max_members",
        "member_count",
        "media_group_id",
        "first_ingress_at",
        "last_ingress_at",
        "hard_at",
        "quiet_at",
        "media_deadline_at",
        "seal_time",
        "closed_at",
        "ready_at",
        "readiness",
        "error_code",
        "created_at",
    ),
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
        "control_mode",
        "control_generation",
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
        "turn_ingress_at",
        "turn_ingress_seq",
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
        "turn_id",
        "turn_revision",
        "step",
        "turn_outcome",
        "turn_input",
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
    "platform.turn_consumer_receipts": (
        "workspace_id",
        "job_id",
        "connection_id",
        "kind",
        "turn_id",
        "turn_revision",
        "step",
        "consumer",
        "winning_claim_token",
        "input_context_version",
        "input_control_generation",
        "snapshot_digest",
        "result",
        "accepted_at",
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

C_COLUMNS = {
    **T_COLUMNS,
    "app.conversations": T_COLUMNS["app.conversations"] + ("activation_fence_seq",),
    "platform.inbox_events": T_COLUMNS["platform.inbox_events"]
    + ("turn_control_generation", "turn_control_mode", "turn_activation_fence_seq"),
    "app.conversation_turns": T_COLUMNS["app.conversation_turns"]
    + ("ingress_control_mode", "activation_fence_seq"),
    "app.audit_events": T_COLUMNS["app.audit_events"]
    + ("conversation_object_id", "conversation_control_generation"),
    "platform.conversation_control_receipts": tuple(
        "workspace_id id operation_namespace operation idempotency_key conversation_id client_id actor_user_account_id correlation_id expected_generation expected_context_version previous_mode accepted_mode previous_generation accepted_generation context_version activation_fence_seq request_fingerprint audit_event_id audit_event_type accepted_at result".split()
    ),
}


async def assert_schema(c, revision):
    assert revision in ("0008", "0009")
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == revision
    columns = T_COLUMNS if revision == "0008" else C_COLUMNS
    assert await names(c) == set(columns)
    for table, expected in columns.items():
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
        assert actual == expected, (table, actual, expected)


async def fingerprints(c, *, projection=False):
    result = {}
    for table, columns in (T_COLUMNS if projection else C_COLUMNS).items():
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


async def t_fingerprint(c):
    result = await fingerprints(c, projection=True)
    assert len(result) == 33
    rows = (await c.execute(text("SELECT to_jsonb(t) FROM platform.alembic_version t"))).scalars()
    encoded = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
    result["platform.alembic_version"] = {
        "count": len(encoded),
        "sha256": hashlib.sha256("\n".join(encoded).encode()).hexdigest(),
    }
    return result


async def definitions(c):
    # Closed app/platform catalogs; includes bodies, ACL/security, types/defaults,
    # named constraints/indexes/triggers/policies, relation ownership and sequence.
    statements = {
        "functions": "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid),p.proacl::text,pg_get_userbyid(p.proowner) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app','platform') AND p.prokind='f' ORDER BY 1,2,3",
        "relations": "SELECT n.nspname,c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,c.relacl::text,pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform') AND c.relkind IN ('r','S') ORDER BY 1,2",
        "columns": "SELECT n.nspname,c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,a.attacl::text,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_attrdef d ON (d.adrelid,d.adnum)=(a.attrelid,a.attnum) WHERE n.nspname IN ('app','platform') AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,3",
        "constraints": "SELECT n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid),k.convalidated FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform') ORDER BY 1,2,3",
        "indexes": "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname IN ('app','platform') ORDER BY 1,2,3",
        "triggers": "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('app','platform') AND NOT t.tgisinternal ORDER BY 1,2,3",
        "policies": "SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname IN ('app','platform') ORDER BY 1,2,3",
        "sequences": "SELECT schemaname,sequencename,sequenceowner,data_type,start_value,min_value,max_value,increment_by,cycle,cache_size FROM pg_sequences WHERE schemaname IN ('app','platform') ORDER BY 1,2",
    }
    return {
        name: [tuple(row) for row in (await c.execute(text(sql))).all()]
        for name, sql in statements.items()
    }


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


async def no_backfill(c):
    for table, clause in (
        (
            "platform.inbox_events",
            "turn_control_generation IS NOT NULL OR turn_control_mode IS NOT NULL OR turn_activation_fence_seq IS NOT NULL",
        ),
        (
            "app.conversation_turns",
            "ingress_control_mode IS NOT NULL OR activation_fence_seq IS NOT NULL",
        ),
        (
            "app.conversations",
            "control_mode<>'HUMAN' OR control_generation<>1 OR activation_fence_seq IS NOT NULL",
        ),
        (
            "app.audit_events",
            "conversation_object_id IS NOT NULL OR conversation_control_generation IS NOT NULL",
        ),
        ("platform.conversation_control_receipts", "true"),
    ):
        assert (
            await c.execute(text(f"SELECT count(*) FROM {table} WHERE {clause}"))
        ).scalar_one() == 0, table


def migration():
    spec = importlib.util.spec_from_file_location(
        "m31_control", Path("migrations/versions/0009_conversation_control.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def assert_refusal(c):
    before, schema = await fingerprints(c), await definitions(c)
    with pytest.raises(DBAPIError) as caught:
        async with c.begin_nested():

            def downgrade(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    migration().downgrade()

            await c.run_sync(downgrade)
    assert caught.value.orig.sqlstate == "55000"
    await assert_schema(c, "0009")
    assert await fingerprints(c) == before
    assert await definitions(c) == schema


async def test_control_clean_populated_t_cycle_all_columns_definitions_and_receipts(messaging):
    h = messaging
    try:
        await h.runtime.engine.dispose()
        await _migrate("downgrade", "0008")
        image, _, _ = await ready(h, event_id="t-image", message_id="t-image")
        await finish_text_turns(h)
        observed = await query(
            h, "SELECT to_jsonb(r) AS row FROM platform.turn_consumer_receipts r"
        )
        assert len(observed) == 1
        unknown = await command(h, image["conversation_id"], "old exact", "t-unknown")
        claim = await h.kernel.claim_job("t-unknown")
        assert claim.kind == "SEND_MANUAL_TEXT"
        await h.kernel.begin_send(claim)
        await query(
            h,
            "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
        assert await h.kernel.recover_expired() == 1
        pending = await command(h, image["conversation_id"], "old exact", "t-pending")
        await ingest(h, event(event_id="old-pending", message_id="old-pending"))
        async with h.migrator.connect() as c:
            await assert_schema(c, "0008")
            old, schema = await t_fingerprint(c), await definitions(c)
        for _ in range(2):
            await _migrate("upgrade", "0009")
            async with h.migrator.connect() as c:
                await assert_schema(c, "0009")
                await no_backfill(c)
                assert await fingerprints(c, projection=True) == {
                    k: v for k, v in old.items() if k != "platform.alembic_version"
                }
            replay = await command(h, image["conversation_id"], "old exact", "t-pending")
            assert replay.model_dump() == {**pending.model_dump(), "code": "REPLAY"}
            assert (
                await query(h, "SELECT to_jsonb(r) AS row FROM platform.turn_consumer_receipts r")
                == observed
            )
            assert (
                await query(
                    h,
                    "SELECT status FROM app.outbox_events WHERE message_id=:id",
                    id=unknown.message_id,
                )
            )[0]["status"] == "UNKNOWN"
            await _migrate("downgrade", "0008")
            async with h.migrator.connect() as c:
                await assert_schema(c, "0008")
                assert await t_fingerprint(c) == old
                assert await definitions(c) == schema
    finally:
        await _migrate("upgrade", "head")
        await h.runtime.engine.dispose()


@pytest.mark.parametrize(
    "blocker", ["capture", "human_generation", "ai_fence", "receipt", "audit_only", "turn_only"]
)
async def test_control_populated_refusal_preserves_full_35_table_snapshot(control, blocker):
    h = control
    if blocker == "capture":
        await incoming(h, process=False)
    else:
        # Create a valid pre-CONTROL conversation, so generation/fence blockers
        # are tested independently of fresh ingress metadata.
        await _migrate("downgrade", "0008")
        try:
            cid, _, _ = await incoming(h)
        finally:
            await _migrate("upgrade", "0009")
        if blocker == "human_generation":
            await query(
                h,
                "UPDATE app.conversations SET control_generation=2 WHERE id=:id RETURNING id",
                id=cid,
            )
        elif blocker == "ai_fence":
            await query(
                h,
                "UPDATE app.conversations SET control_mode='AI',control_generation=2,activation_fence_seq=nextval('platform.turn_ingress_seq') WHERE id=:id RETURNING id",
                id=cid,
            )
        elif blocker == "turn_only":
            # An independently valid terminal Turn is sufficient to refuse even
            # with no fresh Inbox capture, transition, CONTROL receipt or Audit.
            await query(
                h,
                "INSERT INTO app.conversation_turns SELECT (jsonb_populate_record(NULL::app.conversation_turns,to_jsonb(t)||jsonb_build_object('id',gen_random_uuid(),'state','FAILED','error_code','INVALID_INPUT','member_count',0,'ingress_control_mode','HUMAN'))).* FROM app.conversation_turns t WHERE t.conversation_id=:cid RETURNING id",
                cid=cid,
            )
        else:
            await execute(h, cid)
            if blocker == "audit_only":
                await query(
                    h,
                    "DELETE FROM platform.conversation_control_receipts WHERE conversation_id=:id RETURNING id",
                    id=cid,
                )
                await query(
                    h,
                    "UPDATE app.conversations SET control_generation=1 WHERE id=:id RETURNING id",
                    id=cid,
                )
    async with h.migrator.begin() as c:
        await assert_refusal(c)


@pytest.mark.parametrize("provider", ["CONTROLLED", "TELEGRAM"])
@pytest.mark.parametrize("old_mode", ["LEGACY_NULL", "HUMAN", "AI"])
async def test_late_old_origin_cannot_close_or_join_current_generation(control, provider, old_mode):
    h = control
    try:
        if old_mode == "LEGACY_NULL":
            await _migrate("downgrade", "0008")
        cid, _, _ = await incoming(h, provider)
        if old_mode == "AI":
            await execute(h, cid, "RESUME", "old-ai")
        old = await incoming(h, provider, 2, process=False)
        older = await h.kernel.claim_job("hold-old-origin")
        old_job = old["job_id"] if isinstance(old, dict) else old.job_id
        assert str(older.job_id) == str(old_job) and older.kind == "PROCESS_INBOX"
        if old_mode == "LEGACY_NULL":
            await _migrate("upgrade", "0009")
        accepted = await execute(h, cid, "RESUME", "new-ai")
        fresh = await incoming(h, provider, 3, process=False)
        new_message = await process_receipt(h, fresh)
        newer = (
            await query(
                h,
                "SELECT t.* FROM app.conversation_turns t JOIN app.conversation_turn_messages m ON (m.workspace_id,m.turn_id)=(t.workspace_id,t.id) WHERE m.message_id=:id",
                id=new_message.message_id,
            )
        )[0]
        assert newer["ingress_control_mode"] == "AI"
        assert newer["control_generation"] == int(accepted["result"]["accepted_generation"])
        assert newer["state"] == "COLLECTING" and newer["member_count"] == 1
        late_message = await h.kernel.process_inbox(older)
        late = (
            await query(
                h,
                "SELECT t.* FROM app.conversation_turns t JOIN app.conversation_turn_messages m ON (m.workspace_id,m.turn_id)=(t.workspace_id,t.id) WHERE m.message_id=:id",
                id=late_message.message_id,
            )
        )[0]
        assert late["id"] != newer["id"] and late["state"] == "READY" and late["member_count"] == 1
        assert late["control_generation"] == (2 if old_mode == "AI" else 1)
        assert late["ingress_control_mode"] == (None if old_mode == "LEGACY_NULL" else old_mode)
        assert (
            await query(h, "SELECT * FROM app.conversation_turns WHERE id=:id", id=newer["id"])
        )[0] == newer
        assert (
            await query(
                h,
                "SELECT platform.conversation_turn_activation_matches(workspace_id,id) AS eligible FROM app.conversation_turns WHERE id=:id",
                id=late["id"],
            )
        )[0]["eligible"] is False
    finally:
        await _migrate("upgrade", "head")


COMMIT_ACK_LOSS_EXIT = 86
COMMIT_ACK_LOSS_MARKER = "CONTROL_UPGRADE_COMMITTED_RESULT_LOST"
COMMIT_ACK_LOSS = """
import os,sys
from alembic import command
from alembic.config import Config
assert os.environ['ASM_ENVIRONMENT'] in ('LOCAL','TEST')
command.upgrade(Config('alembic.ini'), '0009')
if len(sys.argv)==4 and sys.argv[1]=='--control-schema-phase':
 from pathlib import Path
 import json
 path=Path(sys.argv[3]); saved=json.loads(path.read_text())
 saved['lost_result_process']={'pid':os.getpid(),'namespace':os.readlink('/proc/self/ns/pid')}
 path.write_text(json.dumps(saved,sort_keys=True,indent=2)+'\\n'); path.chmod(0o600)
print('CONTROL_UPGRADE_COMMITTED_RESULT_LOST', flush=True)
os._exit(86)
"""


async def fresh_observation(url):
    fresh = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    try:
        async with fresh.connect() as c:
            await assert_schema(c, "0009")
            return dict(
                (
                    await c.execute(
                        text(
                            "SELECT current_user AS role,current_database() AS database,pg_backend_pid() AS backend_pid,(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,inet_server_addr()::text AS server_address,pg_postmaster_start_time()::text AS postmaster_started"
                        )
                    )
                )
                .mappings()
                .one()
            ) | {
                "revision": "0009",
                "reader_pid": os.getpid(),
                "reader_namespace": os.readlink("/proc/self/ns/pid"),
            }
    finally:
        await fresh.dispose()


async def test_control_commit_ack_loss_fresh_reader_selects_exact_0009(messaging):
    h = messaging
    try:
        await _migrate("downgrade", "0008")
        with pytest.raises(Exception):
            await h.runtime.check()
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
        assert observed["role"] == "asm_migrator" and observed["database"] == "asm_test"
        assert observed["reader_pid"] != child.pid
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
    from sqlalchemy.engine import make_url

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
                    "SELECT platform.messaging_claim('control-schema-seed',:until,:at,:id)",
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
        if action == "seed8":
            assert not saved
            async with migrator.begin() as c:
                await assert_schema(c, "0008")
                empty = await t_fingerprint(c)
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
                    "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) VALUES(:ws,:conn,:business,'CONTROLLED','control-schema-bot','control-schema-connection')",
                    "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:conn,'CONTROLLED','control-schema-bot','control-schema-connection')",
                    "SELECT platform.initialize_local_messaging_billing(:ws,'CONTROL LOCAL','2000-01-01T00:00:00Z','2100-01-01T00:00:00Z')",
                ):
                    await c.execute(text(statement), params)
            saved.update(
                identity=await identity(), workspace=str(ws), owner=str(owner), connection=str(conn)
            )
            image = await sql(
                "SELECT platform.messaging_ingest('CONTROLLED','control-schema-bot',CAST(:event AS jsonb),:corr)",
                event=event(
                    event_id="t-image",
                    message_id="t-image",
                    bot_identity="control-schema-bot",
                    external_connection_id="control-schema-connection",
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
                "SELECT platform.messaging_ingest('CONTROLLED','control-schema-bot',CAST(:event AS jsonb),:corr)",
                event=event(
                    event_id="t-pending-inbox",
                    message_id="t-pending-inbox",
                    bot_identity="control-schema-bot",
                    external_connection_id="control-schema-connection",
                ).encoded(),
                corr=uuid4(),
            )
            async with migrator.connect() as c:
                saved.update(
                    full8=await t_fingerprint(c),
                    projection8=await fingerprints(c, projection=True),
                    definitions8=digest(await definitions(c)),
                )
            save()
        elif action in {"check8", "check9", "fresh", "refuse"}:
            assert await identity() == saved["identity"]
            async with migrator.connect() as c:
                await assert_schema(c, "0008" if action == "check8" else "0009")
                if action == "check8":
                    assert await t_fingerprint(c) == saved["full8"]
                    assert digest(await definitions(c)) == saved["definitions8"]
                elif action == "check9":
                    assert await fingerprints(c, projection=True) == saved["projection8"]
                    await no_backfill(c)
            storage = S3ObjectStorage(StorageSettings())
            try:
                assert (
                    hashlib.sha256(await storage.get(saved["object"]["key"])).hexdigest()
                    == saved["object"]["sha256"]
                )
            finally:
                await storage.close()
            if action == "check9":
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
                    "tables": 34,
                    "data_projection": 33,
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
                            "schema-control",
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
                        adapter.source("control-schema-bot"),
                        event(
                            event_id="c-fresh",
                            message_id="c-fresh",
                            bot_identity="control-schema-bot",
                            external_connection_id="control-schema-connection",
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
                    assert adapter.calls == adapter.effects == 1
                    assert (
                        await sql("SELECT count(*) FROM platform.messaging_command_receipts") == 2
                    )
                    saved["forward_delivery"] = {
                        "calls": 1,
                        "effects": 1,
                        "unknown": "UNKNOWN",
                        "pending": "SENT",
                        "command_receipts": 2,
                        "control_receipts": 1,
                    }
                    async with migrator.connect() as c:
                        saved["full9_populated"] = await fingerprints(c)
                    save()
                finally:
                    await runtime.close()
            elif action == "refuse":
                async with migrator.begin() as c:
                    assert await fingerprints(c) == saved["full9_populated"]
                    await assert_refusal(c)
                saved["populated_refusal"] = "PASS"
                save()
        else:
            raise AssertionError("EXPLICIT_CONTROL_SCHEMA_PHASE_REQUIRED")
        print("CONTROL_SCHEMA_" + action.upper() + "_PASS", flush=True)
    finally:
        await migrator.dispose()


if __name__ == "__main__":
    assert len(sys.argv) == 4 and sys.argv[1] == "--control-schema-phase"
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
