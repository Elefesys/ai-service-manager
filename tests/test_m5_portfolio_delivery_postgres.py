"""Actual PG guards/effects/recovery; only named S3 case claims actual S3."""

import asyncio
import hashlib
from uuid import uuid4

import httpx
import pytest
from asm.ai.context import ContextBuilder
from asm.ai.runtime_contracts import PortfolioDeliveryRuntimeReceipt
from asm.messaging.errors import MessagingError
from asm.messaging.http_models import PortfolioMessageResponse
from asm.messaging.http_service import OwnerAPIRepository
from asm.messaging.models import OutcomeKind
from asm.messaging.results import AIJobClaim
from asm.portfolio.repository import PortfolioRepository
from asm.tenancy import AuthenticatedAccount
from m5_portfolio_delivery_fixtures import CAPTION, application, revoke
from m5_portfolio_delivery_fixtures import db as db
from m5_portfolio_delivery_fixtures import photo_pg as photo_pg
from m5_portfolio_delivery_fixtures import portfolio_runtime_pg as portfolio_runtime_pg
from m5_portfolio_delivery_fixtures import search_pg as search_pg
from m5_portfolio_delivery_fixtures import seeded as seeded
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, incoming, scalar
from test_m3_1_turns_postgres import seal
from test_m4_runtime_postgres import COUNTER, owner
from test_tenancy_postgres import BA, UA, A

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def status(h, delivery):
    return await scalar(
        h, "SELECT status FROM app.outbox_events WHERE id=:id", id=delivery["outbox_id"]
    )


async def send(h, worker, delivery):
    claim = await claim_job(h, delivery["send_job_id"])
    await worker.execute(claim)
    return claim


@pytest.mark.parametrize("photo", [True, False])
async def test_one_chosen_photo_or_text_actual_intent_counted_effect_and_owner_inbox(
    photo_pg, photo
):
    h = photo_pg
    cid, worker, model, claim, delivery, _ = await application(h, photo=photo)
    assert len(model.requests) == 2
    assert delivery["selected_kind"] == ("portfolio_photo" if photo else "reply")
    saved = (await query(h, "SELECT * FROM platform.ai_runs WHERE id=:id", id=delivery["run_id"]))[
        0
    ]
    assert saved["reads_used"] == 1
    if photo:
        assert saved["delivery_read_audit"]["shown_refs"] == [saved["result"]["selection"]]
        assert saved["delivery_read_audit"]["context_sha256"]
    await send(h, worker, delivery)
    assert await status(h, delivery) == "SENT"
    assert h.adapter.calls == h.adapter.effects == 1
    assert h.adapter.photo_payloads == (
        [(hashlib.sha256(h.photo_content).hexdigest(), CAPTION)] if photo else []
    )
    assert h.photo_store.gets == int(photo)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        messages = (await OwnerAPIRepository(unit).messages(cid, 100, None)).items
        item = next(m for m in messages if m.message_id == str(delivery["message_id"]))
        assert item.delivery.status == "SENT"
        assert isinstance(item, PortfolioMessageResponse) is photo
        if photo:
            assert (
                item.content_type == "PORTFOLIO_PHOTO"
                and item.file is None
                and item.text == CAPTION
            )
            assert item.portfolio.asset_version_id == str(h.photo_source["id"])
            assert (
                item.current.schema_version == 2
                and item.current.image_availability == "PORTFOLIO_AVAILABLE"
            )
            permit = await PortfolioRepository(unit).preview(
                BA, h.photo_source["asset_id"], h.photo_source["id"]
            )
    if photo:
        assert await h.photo_store.get(permit.storage_key) == h.photo_content
    # Immutable committed result receipt is reusable without a new call/effect.
    receipt = await worker.ai.database.replay(claim, worker.ai.config)
    assert isinstance(receipt, PortfolioDeliveryRuntimeReceipt)
    await worker.execute(claim)
    assert len(model.requests) == 2 and h.adapter.effects == 1
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.outbox_events WHERE message_id=:id",
            id=delivery["message_id"],
        )
        == 1
    )


@pytest.mark.parametrize("photo_pg", ["s3"], indirect=True)
async def test_actual_private_s3_exact_original_photo_and_authorized_owner_preview(photo_pg):
    await test_one_chosen_photo_or_text_actual_intent_counted_effect_and_owner_inbox(photo_pg, True)
    storage = photo_pg.photo_store.storage
    assert storage is not None
    url = (
        storage._settings.endpoint
        + "/"
        + storage._settings.bucket
        + "/"
        + photo_pg.photo_source["storage_key"]
    )
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
        response = await client.get(url)
    assert response.status_code in {401, 403}


@pytest.mark.parametrize("change", ["revoke", "human", "owner", "connection"])
@pytest.mark.parametrize("after_read", [False, True])
async def test_fresh_guard_loss_before_or_after_s3_read_prevents_dispatch(
    photo_pg, change, after_read
):
    h = photo_pg
    cid, worker, model, _, delivery, _ = await application(h)

    async def mutate():
        if change == "revoke":
            await revoke(h)
        elif change == "human":
            await owner(h, cid, "TAKEOVER")
        elif change == "owner":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:u RETURNING 1",
                ws=A,
                u=UA,
            )
        else:
            await scalar(
                h,
                "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws AND id=:c RETURNING 1",
                ws=A,
                c=await scalar(
                    h, "SELECT connection_id FROM app.conversations WHERE id=:id", id=cid
                ),
            )

    try:
        if after_read:
            h.photo_store.after_get = mutate
        else:
            await mutate()
        await send(h, worker, delivery)
        assert await status(h, delivery) == "FAILED"
        assert h.adapter.calls == h.adapter.effects == 0
        assert h.photo_store.gets == int(after_read)
        assert len(model.requests) == 2
    finally:
        if change == "owner":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:u RETURNING 1",
                ws=A,
                u=UA,
            )


async def test_hash_mismatch_is_unavailable_before_dispatch_no_replacement_or_fallback(photo_pg):
    h = photo_pg
    _, worker, model, _, delivery, _ = await application(h)
    h.photo_store.corrupt = True
    await send(h, worker, delivery)
    assert await status(h, delivery) == "FAILED"
    assert h.adapter.calls == h.adapter.effects == 0 and len(model.requests) == 2
    assert await scalar(
        h, "SELECT attempt_id IS NULL FROM app.outbox_events WHERE id=:id", id=delivery["outbox_id"]
    )


async def test_model_photo_before_read_has_no_intent_and_never_falls_back_to_text(photo_pg):
    h = photo_pg
    _, _, model, _, delivery, _ = await application(h, direct=True)
    assert len(model.requests) == 1 and delivery["selected_kind"] is None
    assert delivery["outbox_id"] is None and h.adapter.calls == 0


async def test_server_rejects_changed_source_after_local_result_validation(photo_pg):
    h = photo_pg

    def poison(database):
        original = database._command

        async def command(claim, operation, **payload):
            if operation == "COMMIT":
                payload["result"]["selection"]["asset_version_id"] = str(uuid4())
            return await original(claim, operation, **payload)

        database._command = command

    _, _, model, _, delivery, _ = await application(h, db_hook=poison)
    assert len(model.requests) == 2 and delivery["selected_kind"] is None
    assert delivery["outbox_id"] is None and h.adapter.calls == 0


async def test_lost_result_ack_reuses_committed_intent_without_model_repeat(photo_pg):
    h = photo_pg
    losses = []

    def lose(database):
        original = database._command

        async def command(claim, operation, **payload):
            value = await original(claim, operation, **payload)
            if operation == "COMMIT":
                losses.append(True)
                raise SQLAlchemyError("synthetic committed photo result ACK loss")
            return value

        database._command = command

    _, worker, model, claim, delivery, _ = await application(h, db_hook=lose)
    assert delivery["selected_kind"] == "portfolio_photo" and len(losses) == 1
    await worker.execute(claim)
    assert len(model.requests) == 2
    await send(h, worker, delivery)
    assert h.adapter.calls == h.adapter.effects == 1 and await status(h, delivery) == "SENT"


async def test_dispatch_ack_loss_restart_reclaim_preserves_unknown_without_send(photo_pg):
    h = photo_pg
    _, worker, model, _, delivery, _ = await application(h)
    claim = await claim_job(h, delivery["send_job_id"])

    async def lost(name):
        if name == "start_after_commit":
            raise SQLAlchemyError("synthetic dispatch ACK loss")

    h.kernel._barrier = lost
    try:
        with pytest.raises(SQLAlchemyError):
            await worker.execute(claim)
    finally:
        h.kernel._barrier = None
    assert await status(h, delivery) == "DISPATCHING" and h.adapter.calls == 0
    await scalar(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING 1",
        id=claim.job_id,
    )
    await h.kernel.recover_expired()
    assert await status(h, delivery) == "UNKNOWN"
    with pytest.raises(MessagingError):
        await worker.execute(claim)
    assert h.adapter.calls == 0 and len(model.requests) == 2


@pytest.mark.parametrize("outcome", [OutcomeKind.UNKNOWN, OutcomeKind.NOT_SENT_RETRYABLE])
async def test_external_outcome_keeps_unknown_or_only_proven_unsent_retryable(photo_pg, outcome):
    h = photo_pg
    _, worker, model, _, delivery, _ = await application(h)
    h.adapter.outcome = outcome
    claim = await send(h, worker, delivery)
    assert h.adapter.calls == 1 and h.adapter.effects == int(outcome == OutcomeKind.UNKNOWN)
    assert await status(h, delivery) == ("UNKNOWN" if outcome == OutcomeKind.UNKNOWN else "PENDING")
    with pytest.raises(MessagingError):
        await worker.execute(claim)
    assert h.adapter.calls == 1 and len(model.requests) == 2
    if outcome == OutcomeKind.NOT_SENT_RETRYABLE:
        await revoke(h)
        await scalar(
            h,
            "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING 1",
            id=claim.job_id,
        )
        await send(h, worker, delivery)
        assert await status(h, delivery) == "FAILED" and h.adapter.calls == 1


async def test_cancel_after_counted_effect_records_unknown_and_no_resend(photo_pg):
    h = photo_pg
    _, worker, model, _, delivery, _ = await application(h)

    async def cancel(stage):
        if stage == "after_effect":
            raise asyncio.CancelledError

    h.adapter.barrier = cancel
    with pytest.raises(asyncio.CancelledError):
        await send(h, worker, delivery)
    h.adapter.barrier = None
    assert await status(h, delivery) == "UNKNOWN" and h.adapter.calls == h.adapter.effects == 1
    await h.kernel.recover_expired()
    assert h.adapter.effects == 1 and len(model.requests) == 2


async def test_next_text_turn_has_explicit_photo_history_and_legacy_shapes_stay_closed(photo_pg):
    h = photo_pg
    cid, worker, _, _, delivery, scope = await application(h)
    await send(h, worker, delivery)
    await incoming(h, next(COUNTER), **(scope | {"text": "Спасибо за работу"}))
    turn = (
        await query(
            h,
            "SELECT id FROM app.conversation_turns WHERE conversation_id=:c AND state='COLLECTING' ORDER BY id DESC LIMIT 1",
            c=cid,
        )
    )[0]
    grouped = await seal(h, turn["id"])
    source = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE turn_id=:t AND turn_revision=:r AND step='TEST_CONSUME'",
        t=turn["id"],
        r=grouped.turn_revision,
    )
    await worker.execute(await claim_job(h, source))
    claim = await h.kernel.claim_job("photo-history", ai=True)
    assert isinstance(claim, AIJobClaim)
    run = await worker.ai.database.prepare(
        claim, worker.ai.config, deadline=worker.ai.settings.expires_at
    )
    assert run.snapshot["schema_version"] == 4
    view = ContextBuilder().build(run.snapshot, run.binding).view
    history = next(v for v in view.recent if v.text == CAPTION)
    assert (
        history.content_type == "PHOTO"
        and not history.image_read
        and history.image_availability == "HIDDEN"
    )
    assert history.origin == "CONTROLLED_AUTOMATION" and history.delivery_status == "SENT"
    assert "storage_key" not in view.model_dump_json()
    from asm.conversations.turns import TurnSnapshotV3
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TurnSnapshotV3.model_validate(run.snapshot)


async def test_same_business_shared_work_can_be_sent_to_two_distinct_clients(photo_pg):
    h = photo_pg
    first = await application(h)
    await send(h, first[1], first[4])
    second = await application(h)
    assert first[0] != second[0]
    await send(h, second[1], second[4])
    assert await status(h, first[4]) == await status(h, second[4]) == "SENT"
    assert h.adapter.effects == h.adapter.calls == 2
    assert h.adapter.photo_payloads == [(hashlib.sha256(h.photo_content).hexdigest(), CAPTION)] * 2


async def test_runtime_private_table_acl_and_forged_claim_do_not_read_bytes(photo_pg):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    h = photo_pg
    _, worker, _, _, delivery, _ = await application(h)
    async with h.runtime.engine.begin() as connection:
        with pytest.raises(DBAPIError):
            await connection.execute(text("SELECT * FROM platform.portfolio_delivery_intents"))
    send_claim = await claim_job(h, delivery["send_job_id"])
    forged = send_claim.model_copy(update={"claim_token": uuid4()})
    with pytest.raises(MessagingError):
        await worker.portfolio_delivery.read(forged)
    assert h.photo_store.gets == 0 and await status(h, delivery) == "PENDING"


async def test_used_downgrade_refuses_and_preserves_dispatching_receipts(photo_pg):
    import sys

    h = photo_pg
    _, worker, _, ai_claim, delivery, _ = await application(h)
    send_claim = await claim_job(h, delivery["send_job_id"])
    media, _ = await worker.portfolio_delivery.read(send_claim)
    permitted = await worker.portfolio_delivery.begin(send_claim, media, None, None)
    assert permitted.code == "PERMITTED" and await status(h, delivery) == "DISPATCHING"
    before = await worker.ai.database.replay(ai_claim, worker.ai.config)
    intents = await query(
        h, "SELECT * FROM platform.portfolio_delivery_intents WHERE workspace_id=:ws", ws=A
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "downgrade",
        "0021",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    assert process.returncode != 0 and b"PORTFOLIO_DELIVERY_DURABLE_DATA" in stdout + stderr
    assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0033"
    assert await status(h, delivery) == "DISPATCHING"
    assert await worker.ai.database.replay(ai_claim, worker.ai.config) == before
    assert (
        await query(
            h, "SELECT * FROM platform.portfolio_delivery_intents WHERE workspace_id=:ws", ws=A
        )
        == intents
    )
    assert h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize("rights", [True, False])
async def test_actual_pg_synthetic_telegram_photo_fresh_rights_and_own_echo(photo_pg, rights):
    from datetime import UTC, datetime
    from email.parser import BytesParser
    from email.policy import default

    from asm.telegram.client import TelegramClient
    from asm.telegram.config import TelegramSettings
    from asm.telegram.database import TelegramIngress
    from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER

    h = photo_pg
    calls = []
    photo_chat = None

    async def handler(request):
        nonlocal photo_chat
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append(method)
        if method == "getBusinessConnection":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "id": EXTERNAL,
                        "user": {"id": int(OWNER), "is_bot": False},
                        "user_chat_id": int(OWNER),
                        "date": 1789990000,
                        "is_enabled": True,
                        "rights": {"can_reply": True if calls.count(method) == 1 else rights},
                    },
                },
            )
        assert method == "sendPhoto"
        body = BytesParser(policy=default).parsebytes(
            b"Content-Type: "
            + request.headers["content-type"].encode()
            + b"\r\n\r\n"
            + await request.aread()
        )
        parts = {p.get_param("name", header="content-disposition"): p for p in body.iter_parts()}
        assert parts["photo"].get_payload(decode=True) == h.photo_content
        photo_chat = int(parts["chat_id"].get_payload(decode=True))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 8899,
                    "business_connection_id": EXTERNAL,
                    "chat": {"id": photo_chat, "type": "private"},
                    "date": int(datetime.now(UTC).timestamp()),
                    "caption": CAPTION,
                    "photo": [
                        {
                            "file_id": "synthetic-sent-photo",
                            "file_unique_id": "synthetic-photo-unique",
                            "width": 64,
                            "height": 64,
                        }
                    ],
                },
            },
        )

    client = TelegramClient(
        TelegramSettings(
            ASM_ENVIRONMENT="TEST",
            ASM_TELEGRAM_ENABLED=True,
            TG_BOT_TOKEN=BOT + ":synthetic_token_123456789",
            TG_WEBHOOK_SECRET="synthetic_webhook_secret_123",
            ASM_TELEGRAM_EXPECTED_BOT_ID=BOT,
            ASM_TELEGRAM_WEBHOOK_URL="https://test.invalid/webhooks/telegram",
        ),
        transport=httpx.MockTransport(handler),
    )
    try:
        cid, worker, model, _, delivery, _ = await application(
            h, telegram=True, telegram_client=client
        )
        assert delivery["selected_kind"] == "portfolio_photo" and len(model.requests) == 2
        before = (
            await query(
                h,
                "SELECT control_mode,control_generation,version,human_observation_epoch FROM app.conversations WHERE id=:c",
                c=cid,
            )
        )[0]
        await send(h, worker, delivery)
        assert await status(h, delivery) == ("SENT" if rights else "FAILED")
        assert calls == ["getBusinessConnection", "getBusinessConnection"] + (
            ["sendPhoto"] if rights else []
        )
        if rights:
            before = (
                await query(
                    h,
                    "SELECT control_mode,control_generation,version,human_observation_epoch FROM app.conversations WHERE id=:c",
                    c=cid,
                )
            )[0]
            receipt = await TelegramIngress(h.kernel, BOT).ingest_update(
                {
                    "update_id": next(COUNTER),
                    "business_message": {
                        "message_id": 8899,
                        "business_connection_id": EXTERNAL,
                        "date": int(datetime.now(UTC).timestamp()),
                        "from": {"id": int(OWNER), "is_bot": False},
                        "sender_business_bot": {"id": int(BOT), "is_bot": True},
                        "chat": {"id": photo_chat, "type": "private"},
                        "caption": CAPTION,
                        "photo": [
                            {
                                "file_id": "echo-photo",
                                "file_unique_id": "echo-unique",
                                "width": 64,
                                "height": 64,
                            }
                        ],
                    },
                },
                uuid4(),
            )
            assert receipt.result_code == "IGNORED_ECHO"
            after = (
                await query(
                    h,
                    "SELECT control_mode,control_generation,version,human_observation_epoch FROM app.conversations WHERE id=:c",
                    c=cid,
                )
            )[0]
            assert after == before
            assert (
                await scalar(
                    h,
                    "SELECT count(*) FROM app.outbox_events WHERE message_id=:id",
                    id=delivery["message_id"],
                )
                == 1
            )
    finally:
        await client.aclose()
