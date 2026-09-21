"""0005 data, including UNKNOWN SEND and disconnected images, survives 0006."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from test_m2_1_models import event
from test_m2_1_postgres import CA2, command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_1_schema_postgres import _migrate
from test_tenancy_postgres import UA, A, raw_context
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


async def test_0005_exact_data_backfill_repeat_and_test_downgrade_reupgrade(messaging):
    h = messaging
    tables = (
        "app.messages",
        "app.conversations",
        "app.channel_connections",
        "platform.inbox_events",
        "app.outbox_events",
        "platform.messaging_command_receipts",
        "platform.workspace_billing_accounts",
        "platform.workspace_subscriptions",
        "platform.billing_contact_command_receipts",
        "app.audit_events",
    )

    async def snapshot():
        async with h.migrator.connect() as connection:
            values = {}
            for table in tables:
                values[table] = (
                    await connection.execute(
                        text(f"SELECT to_jsonb(t) AS row FROM {table} t ORDER BY to_jsonb(t)::text")
                    )
                ).all()
            # file_id is the only additive field on the retained kernel Job rows.
            values["platform.messaging_jobs"] = (
                await connection.execute(
                    text(
                        "SELECT to_jsonb(j)-'file_id' FROM platform.messaging_jobs j WHERE kind<>'FETCH_IMAGE' ORDER BY id"
                    )
                )
            ).all()
            return values

    async def receive_0005(value):
        receipt = await ingest(h, value)
        claim = await h.kernel.claim_job("upgrade-source")
        assert claim is not None and claim.job_id == receipt.job_id
        return receipt, await h.kernel.process_inbox(claim)

    async def assert_backfill(image_ids, correlation):
        rows = await query(
            h,
            "SELECT f.message_id,f.status,j.kind,j.file_id,j.correlation_id,j.attempt_count "
            "FROM app.file_objects f JOIN platform.messaging_jobs j ON (j.workspace_id,j.file_id)=(f.workspace_id,f.id) ORDER BY f.message_id",
        )
        assert len(rows) == 2 and {row["message_id"] for row in rows} == image_ids
        assert all(
            row["status"] == "PENDING"
            and row["kind"] == "FETCH_IMAGE"
            and row["attempt_count"] == 0
            and row["correlation_id"] is not None
            for row in rows
        )
        assert any(row["correlation_id"] == correlation for row in rows)
        assert not await query(h, "SELECT id FROM platform.file_object_uploads")

    try:
        await _migrate("downgrade", "0005")
        text_receipt, text_message = await receive_0005(event(text=" text é\n "))
        image_receipt, first = await receive_0005(
            event(
                event_id="image-active",
                message_id="image-active",
                text="caption",
                image_file_id="opaque-original-1",
            )
        )
        disconnected_receipt, second = await receive_0005(
            event(
                event_id="image-disconnected",
                message_id="image-disconnected",
                external_connection_id="conn-a2",
                image_file_id="opaque-original-2",
            )
        )
        await query(
            h,
            "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id",
            id=CA2,
        )
        # Cover migration fallback correlation for a legitimate 0005 image lacking Inbox.
        await query(
            h,
            "DELETE FROM platform.messaging_jobs WHERE inbox_id=:inbox RETURNING id",
            inbox=disconnected_receipt.inbox_id,
        )
        await query(
            h,
            "DELETE FROM platform.inbox_events WHERE id=:inbox RETURNING id",
            inbox=disconnected_receipt.inbox_id,
        )
        conversation = (
            await query(
                h,
                "SELECT conversation_id FROM app.messages WHERE id=:id",
                id=text_message.message_id,
            )
        )[0]["conversation_id"]
        send = await command(h, conversation, "Keep UNKNOWN exact", "migration-unknown")
        send_claim = await h.kernel.claim_job("upgrade-send")
        assert send_claim is not None and send_claim.kind == "SEND_MANUAL_TEXT"
        await h.kernel.begin_send(send_claim)
        await query(
            h,
            "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
            id=send_claim.job_id,
        )
        await h.kernel.recover_expired()
        assert (
            await query(
                h,
                "SELECT status,error_code FROM app.outbox_events WHERE message_id=:id",
                id=send.message_id,
            )
        ) == [{"status": "UNKNOWN", "error_code": "UNKNOWN_EXTERNAL_RESULT"}]
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_billing(:ws,'test',1,'Image migration','ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
                ),
                {"ws": A},
            )
            await connection.execute(
                text(
                    "SELECT set_config('asm.actor_kind','user_account',true),set_config('asm.actor_id',CAST(:actor AS text),true),set_config('asm.workspace_id',CAST(:ws AS text),true),set_config('asm.correlation_id',CAST(:correlation AS text),true),set_config('asm.context_xid',pg_current_xact_id()::text,true)"
                ),
                {"ws": A, "actor": UA, "correlation": uuid4()},
            )
            await connection.execute(
                text(
                    "SELECT * FROM platform.update_billing_contact(1,'Preserved billing contact','image-migration')"
                )
            )
        correlation = (
            await query(
                h,
                "SELECT correlation_id FROM platform.inbox_events WHERE id=:id",
                id=image_receipt.inbox_id,
            )
        )[0]["correlation_id"]
        image_ids = {first.message_id, second.message_id}
        before = await snapshot()
        assert before["app.messages"] and before["platform.billing_contact_command_receipts"]
        await _migrate("upgrade", "head")
        assert await snapshot() == before
        await assert_backfill(image_ids, correlation)
        file_ids = await query(h, "SELECT id,message_id FROM app.file_objects ORDER BY id")
        await _migrate("upgrade", "head")
        assert await snapshot() == before
        assert await query(h, "SELECT id,message_id FROM app.file_objects ORDER BY id") == file_ids
        await _migrate("downgrade", "0005")
        assert await snapshot() == before
        assert (
            await query(
                h,
                "SELECT to_regclass('app.file_objects') AS files,to_regclass('platform.file_object_uploads') AS uploads",
            )
        ) == [{"files": None, "uploads": None}]
        # Original owner reads still work with the restored 0005 capability definitions.
        async with h.runtime.engine.begin() as connection:
            await raw_context(connection)
            rows = (
                await connection.execute(
                    text("SELECT platform.messaging_read_messages(:conversation,100)"),
                    {"conversation": conversation},
                )
            ).scalar_one()
            assert any(row["message_id"] == str(send.message_id) for row in rows)
        await _migrate("upgrade", "head")
        assert await snapshot() == before
        await assert_backfill(image_ids, correlation)
        # Existing accepted event retains exactly the same Inbox identity after both cycles.
        replay = await ingest(h, event(text=" text é\n "))
        assert replay.inbox_id == text_receipt.inbox_id
    finally:
        await _migrate("upgrade", "head")
        async with h.migrator.begin() as connection:
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
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id=:ws" + suffix), {"ws": A}
                )
