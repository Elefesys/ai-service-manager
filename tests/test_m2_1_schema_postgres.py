"""Physical M2.1 schema, typed refs, capabilities, and 0004 data preservation."""

import asyncio
import json
import os
import sys
from uuid import uuid4

import pytest
import pytest_asyncio
from asm.messaging.database import MessagingDatabase, call
from asm.messaging.results import JobClaim
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
TABLES = {
    "app.channel_connections",
    "platform.channel_routes",
    "app.clients",
    "app.client_identities",
    "app.conversations",
    "app.messages",
    "platform.inbox_events",
    "app.outbox_events",
    "platform.messaging_jobs",
    "platform.messaging_command_receipts",
}
READABLE = {
    "app.channel_connections",
    "app.clients",
    "app.client_identities",
    "app.conversations",
    "app.messages",
}


class HistoricalScanDatabase(MessagingDatabase):
    """Explicit 0005--0007 test caller, never a runtime compatibility fallback."""

    async def claim_job(self, worker_id):
        async with self._transaction() as connection:
            assert await call(
                connection, "SELECT version_num FROM platform.alembic_version", {}
            ) in {"0005", "0006", "0007"}
            value = await call(
                connection, "SELECT platform.messaging_claim(:worker)", {"worker": worker_id}
            )
        return JobClaim.model_validate(value) if value is not None else None

    async def recover_expired(self, limit=100):
        async with self._transaction() as connection:
            assert await call(
                connection, "SELECT version_num FROM platform.alembic_version", {}
            ) in {"0005", "0006", "0007"}
            value = await call(
                connection, "SELECT platform.messaging_recover_expired(:limit)", {"limit": limit}
            )
        return value["recovered"]


@pytest_asyncio.fixture
async def migrator():
    url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert make_url(url).database == "asm_test"
    engine = create_async_engine(url, hide_parameters=True)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_messaging_physical_inventory_rls_no_direct_writer_or_control_access(migrator):
    async with migrator.connect() as connection:
        for table in sorted(TABLES):
            owner, enabled, forced = (
                await connection.execute(
                    text(
                        "SELECT r.rolname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c "
                        "JOIN pg_roles r ON r.oid=c.relowner WHERE c.oid=CAST(:table AS regclass)"
                    ),
                    {"table": table},
                )
            ).one()
            assert (owner, enabled, forced) == ("asm_migrator", True, True)
            privileges = (
                await connection.execute(
                    text(
                        "SELECT has_table_privilege('asm_runtime',:table,'SELECT'),"
                        "has_table_privilege('asm_runtime',:table,'INSERT'),"
                        "has_table_privilege('asm_runtime',:table,'UPDATE'),"
                        "has_table_privilege('asm_runtime',:table,'DELETE')"
                    ),
                    {"table": table},
                )
            ).one()
            assert privileges == (table in READABLE, False, False, False)
            assert (
                await connection.execute(
                    text(
                        "SELECT pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a "
                        "JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                        "WHERE a.attrelid=CAST(:table AS regclass) AND a.attname='id'"
                    ),
                    {"table": table},
                )
            ).scalar_one() == "uuidv7()"
        generated = (
            await connection.execute(
                text(
                    "SELECT attname,attgenerated FROM pg_attribute WHERE attrelid='app.audit_events'::regclass "
                    "AND attname IN ('billing_account_object_id','message_object_id') ORDER BY attname"
                )
            )
        ).all()
        assert generated == [("billing_account_object_id", "s"), ("message_object_id", "s")]
        indexes = set(
            (
                await connection.execute(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE indexname IN "
                        "('messaging_jobs_due_idx','messaging_jobs_expired_idx','messages_chronological_idx',"
                        "'audit_events_message_send_key')"
                    )
                )
            ).scalars()
        )
        assert indexes == {
            "messaging_jobs_due_idx",
            "messaging_jobs_expired_idx",
            "messages_chronological_idx",
            "audit_events_message_send_key",
        }


async def _base(connection):
    ws, other, actor, business, conn, conn2, client, client2, identity, conv, message = (
        uuid4() for _ in range(11)
    )
    values = locals().copy()
    values.pop("connection")
    statements = (
        "INSERT INTO platform.workspaces(id) VALUES(:ws),(:other)",
        "INSERT INTO platform.user_accounts(id) VALUES(:actor)",
        "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')",
        "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:business,'Schema test')",
        "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) VALUES(:ws,:conn,:business,'CONTROLLED',:conn::text,'first'),(:ws,:conn2,:business,'CONTROLLED',:conn::text,'second')",
        "INSERT INTO app.clients(workspace_id,id) VALUES(:ws,:client),(:ws,:client2)",
        "INSERT INTO app.client_identities(workspace_id,id,client_id,provider,external_user_id) VALUES(:ws,:identity,:client,'CONTROLLED','client')",
        "INSERT INTO app.conversations(workspace_id,id,connection_id,business_id,client_id,identity_id,provider_chat_id) VALUES(:ws,:conv,:conn,:business,:client,:identity,'chat')",
        "INSERT INTO app.messages(workspace_id,id,conversation_id,connection_id,provider_chat_id,provider_message_id,direction,content_type,text,occurred_at,projection_fingerprint) VALUES(:ws,:message,:conv,:conn,'chat','provider-message','INBOUND','TEXT','inbound',clock_timestamp(),sha256('projection'::bytea))",
    )
    for statement in statements:
        # CAST spelling avoids SQLAlchemy's parameter lexer ambiguities around ::.
        await connection.execute(
            text(statement.replace(":conn::text", "CAST(:conn AS text)")), values
        )
    return values


async def test_composite_refs_reject_cross_workspace_and_same_workspace_false_relations(migrator):
    async with migrator.begin() as connection:
        values = await _base(connection)
        invalid = (
            # Route identity must match every canonical connection binding field.
            "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:other,:conn,'CONTROLLED',CAST(:conn AS text),'first')",
            "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:conn,'CONTROLLED',CAST(:conn AS text),'second')",
            # Existing local client/identity individually valid, pair invalid.
            "INSERT INTO app.conversations(workspace_id,connection_id,business_id,client_id,identity_id,provider_chat_id) VALUES(:ws,:conn,:business,:client2,:identity,'other-chat')",
            # Existing local connection/conversation individually valid, pair invalid.
            "INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at) VALUES(:ws,:conv,:conn2,'chat','OUTBOUND','TEXT','forged',clock_timestamp())",
            # Outbox cannot send an inbound canonical Message.
            "INSERT INTO app.outbox_events(workspace_id,connection_id,message_id) VALUES(:ws,:conn,:message)",
            # Billing discriminator still demands a real billing account.
            "INSERT INTO app.audit_events(workspace_id,actor_kind,correlation_id,event_type,object_type,object_id,object_version,payload) VALUES(:ws,'LOCAL_PROVISIONER',gen_random_uuid(),'WORKSPACE_BILLING_PROVISIONED','WORKSPACE_BILLING_ACCOUNT',:message,1,'{}')",
            # Message Audit cannot point outside Workspace, even at a real Message ID.
            "INSERT INTO app.audit_events(workspace_id,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload) VALUES(:ws,'USER_ACCOUNT',:actor,gen_random_uuid(),'MESSAGE_SEND_REQUESTED','MESSAGE',:client2,1,'{\"content_type\":\"TEXT\"}')",
        )
        for statement in invalid:
            with pytest.raises(DBAPIError) as caught:
                async with connection.begin_nested():
                    await connection.execute(text(statement), values)
            assert caught.value.orig.sqlstate == "23503"
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "UPDATE app.channel_connections SET external_connection_id='replacement' WHERE workspace_id=:ws AND id=:conn"
                    ),
                    values,
                )
        assert caught.value.orig.sqlstate == "23514"
        await connection.rollback()


async def test_nullable_state_and_outcome_fields_cannot_bypass_checks(migrator):
    async with migrator.begin() as connection:
        values = await _base(connection)
        await connection.execute(
            text(
                "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) "
                "VALUES(:ws,:conn,'CONTROLLED',CAST(:conn AS text),'first')"
            ),
            values,
        )
        event = {
            "provider": "CONTROLLED",
            "bot_identity": str(values["conn"]),
            "event_id": "constraints",
            "kind": "UNSUPPORTED",
            "external_connection_id": "first",
            "chat_id": None,
            "message_id": None,
            "sender_id": None,
            "occurred_at": None,
            "text": None,
            "image_file_id": None,
            "media_group_id": None,
        }
        receipt = (
            await connection.execute(
                text(
                    "SELECT platform.messaging_ingest('CONTROLLED',:bot,CAST(:event AS jsonb),:corr)"
                ),
                {"bot": str(values["conn"]), "event": json.dumps(event), "corr": uuid4()},
            )
        ).scalar_one()
        values.update(inbox=receipt["inbox_id"], job=receipt["job_id"], outbound=uuid4())
        await connection.execute(
            text(
                "INSERT INTO app.messages(workspace_id,id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at) "
                "VALUES(:ws,:outbound,:conv,:conn,'chat','OUTBOUND','TEXT','outbound',clock_timestamp())"
            ),
            values,
        )
        await connection.execute(
            text(
                "INSERT INTO app.outbox_events(workspace_id,connection_id,message_id) VALUES(:ws,:conn,:outbound)"
            ),
            values,
        )
        invalid = (
            "UPDATE platform.inbox_events SET status='FAILED',completed_at=clock_timestamp() WHERE id=:inbox",
            "UPDATE platform.inbox_events SET status='IGNORED',completed_at=clock_timestamp() WHERE id=:inbox",
            "UPDATE platform.inbox_events SET status='PROCESSED',message_id=:message,completed_at=clock_timestamp() WHERE id=:inbox",
            "UPDATE platform.messaging_jobs SET status='DEAD',completed_at=clock_timestamp() WHERE id=:job",
            "UPDATE platform.messaging_jobs SET status='SUCCEEDED',completed_at=clock_timestamp() WHERE id=:job",
            "UPDATE app.outbox_events SET status='FAILED',error_code='UNKNOWN_EXTERNAL_RESULT',completed_at=clock_timestamp() WHERE message_id=:outbound",
            "UPDATE platform.messaging_jobs SET last_attempt_id=gen_random_uuid(),last_claim_token=gen_random_uuid() WHERE id=:job",
            "UPDATE platform.messaging_jobs SET error_code='UNBOUNDED_ERROR_BODY' WHERE id=:job",
            "UPDATE platform.messaging_jobs SET last_attempt_id=gen_random_uuid(),last_claim_token=gen_random_uuid(),last_outcome='NOT_SENT_PERMANENT',last_error_code='UNBOUNDED_ERROR_BODY' WHERE id=:job",
            "UPDATE platform.messaging_jobs SET status='RUNNING',lease_until=clock_timestamp()+interval '30 seconds',worker_id='missing-token' WHERE id=:job",
        )
        for statement in invalid:
            with pytest.raises(DBAPIError) as caught:
                async with connection.begin_nested():
                    await connection.execute(text(statement), values)
            assert caught.value.orig.sqlstate == "23514"
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "UPDATE platform.inbox_events SET status='PROCESSED',result_code='PROCESSED',"
                        "message_id=:outbound,completed_at=clock_timestamp() WHERE id=:inbox"
                    ),
                    values,
                )
        assert caught.value.orig.sqlstate == "23503"
        await connection.rollback()


@pytest.mark.parametrize(
    "occurred_at",
    [
        "now",
        "tomorrow",
        "2026-09-21",
        "2026-09-21T00:00:00Z",
        "2026-09-21T01:00:00.000000+01:00",
        "2026-02-30T00:00:00.000000Z",
        "2026-09-21T00:00:60.000000Z",
        "0000-01-01T00:00:00.000000Z",
    ],
)
async def test_public_ingestion_rejects_unstable_or_noncanonical_timestamp(migrator, occurred_at):
    event = {
        "provider": "CONTROLLED",
        "bot_identity": "timestamp-test",
        "event_id": "timestamp-test",
        "kind": "UNSUPPORTED",
        "external_connection_id": "timestamp-test",
        "chat_id": None,
        "message_id": None,
        "sender_id": None,
        "occurred_at": occurred_at,
        "text": None,
        "image_file_id": None,
        "media_group_id": None,
    }
    with pytest.raises(DBAPIError) as caught:
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "SELECT platform.messaging_ingest('CONTROLLED','timestamp-test',CAST(:event AS jsonb),:corr)"
                ),
                {"event": json.dumps(event), "corr": uuid4()},
            )
    assert caught.value.orig.sqlstate == "P2001"
    assert caught.value.orig.diag.message_primary == "INVALID_INPUT"
    event["occurred_at"] = "2026-09-21T00:00:00.123456Z"
    async with migrator.connect() as connection:
        # Exact canonical input survives unchanged, so the codec sees stable bytes.
        assert (
            await connection.execute(
                text("SELECT platform.messaging_validate_event(CAST(:event AS jsonb))"),
                {"event": json.dumps(event)},
            )
        ).scalar_one() == event


async def _migrate(*arguments):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 0, output.decode()


async def test_0004_data_survives_upgrade_repeat_downgrade_reupgrade(migrator):
    """M1 billing data and receipts retain their exact persisted values across 0005."""
    ws = uuid4()
    actor = uuid4()
    try:
        await _migrate("downgrade", "0004")
        async with migrator.begin() as connection:
            await connection.execute(
                text("INSERT INTO platform.workspaces(id) VALUES(:ws)"), {"ws": ws}
            )
            await connection.execute(
                text("INSERT INTO platform.user_accounts(id) VALUES(:actor)"), {"actor": actor}
            )
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
                ),
                {"ws": ws, "actor": actor},
            )
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'Cycle original','ACTIVE','COMPED',"
                    "'2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
                ),
                {"ws": ws},
            )
            await connection.execute(
                text(
                    "SELECT set_config('asm.actor_kind','user_account',true),set_config('asm.actor_id',CAST(:actor AS text),true),"
                    "set_config('asm.workspace_id',CAST(:ws AS text),true),set_config('asm.correlation_id',gen_random_uuid()::text,true),"
                    "set_config('asm.context_xid',pg_current_xact_id()::text,true)"
                ),
                {"ws": ws, "actor": actor},
            )
            await connection.execute(
                text(
                    "SELECT * FROM platform.update_billing_contact(1,'Cycle changed','cycle-preservation')"
                )
            )

        async def snapshot():
            async with migrator.connect() as connection:
                return [
                    (await connection.execute(text(sql), {"ws": ws})).all()
                    for sql in (
                        "SELECT billing_account_id,contact_display_name,version,created_at,updated_at FROM platform.workspace_billing_accounts WHERE workspace_id=:ws",
                        "SELECT receipt_id,request_fingerprint,status,result_version,result_outcome,created_at,completed_at FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws",
                        "SELECT audit_event_id,occurred_at,actor_kind,actor_user_account_id,correlation_id,event_type,object_type,object_id,object_version,payload FROM app.audit_events WHERE workspace_id=:ws ORDER BY audit_event_id",
                    )
                ]

        before = await snapshot()
        assert all(before)
        await _migrate("upgrade", "head")
        await _migrate("upgrade", "head")
        assert await snapshot() == before
        await _migrate("downgrade", "0004")
        assert await snapshot() == before
        await _migrate("upgrade", "head")
        assert await snapshot() == before
    finally:
        await _migrate("upgrade", "head")
        async with migrator.begin() as connection:
            for table in (
                "platform.billing_contact_command_receipts",
                "app.audit_events",
                "platform.workspace_service_modes",
                "platform.workspace_subscriptions",
                "platform.workspace_billing_accounts",
                "platform.workspace_memberships",
            ):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id=:ws"), {"ws": ws}
                )
            await connection.execute(
                text("DELETE FROM platform.user_accounts WHERE id=:actor"), {"actor": actor}
            )
            await connection.execute(
                text("DELETE FROM platform.workspaces WHERE id=:ws"), {"ws": ws}
            )
