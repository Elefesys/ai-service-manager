"""Real runtime PostgreSQL boundaries for Telegram receipts, fences and policy."""

import asyncio
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.billing.errors import BillingUnavailable
from asm.billing.service import EntitlementService
from asm.tenancy import AuthenticatedAccount
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import messaging as messaging
from test_m2_1_postgres import query
from test_tenancy_postgres import BA, UA, A, B, raw_context
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
BOT, OWNER, CLIENT = "9000001", "8000001", "7000001"
EXTERNAL = "opaque-business-connection:+é"


def observed(**changes):
    return {
        "bot_identity": BOT,
        "external_connection_id": EXTERNAL,
        "owner_user_id": OWNER,
        "is_enabled": True,
        "can_reply": True,
        "error_code": None,
        **changes,
    }


def stamp(value=None):
    return (value or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def projection(update="101", message="201", at=None, **changes):
    return {
        "update_id": update,
        "kind": "BUSINESS_MESSAGE",
        "external_connection_id": EXTERNAL,
        "event": {
            "provider": "TELEGRAM",
            "bot_identity": BOT,
            "event_id": update,
            "kind": "CLIENT_MESSAGE",
            "external_connection_id": EXTERNAL,
            "chat_id": CLIENT,
            "message_id": message,
            "sender_id": CLIENT,
            "occurred_at": stamp(at),
            "text": " exact é\ne\u0301 🎨 ",
            "image_file_id": None,
            "media_group_id": None,
        },
        "owner_user_id": None,
        "deleted_message_ids": None,
        "deleted_chat_id": None,
        "sender_business_bot_id": None,
        "is_enabled": None,
        "can_reply": None,
        "lifecycle_date": None,
        **changes,
    }


def lifecycle(update="301", **changes):
    values = dict(
        kind="BUSINESS_CONNECTION",
        event=None,
        owner_user_id=OWNER,
        is_enabled=False,
        can_reply=False,
        lifecycle_date=stamp(),
    )
    return projection(update, **(values | changes))


async def sql(h, statement, **params):
    async with h.runtime.engine.begin() as connection:
        return (await connection.execute(text(statement), params)).scalar_one()


async def ingress(h, p=None, bot=BOT):
    return await sql(
        h,
        "SELECT platform.telegram_ingest(:bot,CAST(:p AS jsonb),:corr)",
        bot=bot,
        p=json.dumps(p or projection()),
        corr=uuid4(),
    )


async def owner_sql(h, statement, *, workspace=A, actor=UA, **params):
    async with h.runtime.engine.begin() as connection:
        await raw_context(connection, workspace, actor)
        return (await connection.execute(text(statement), params)).scalar_one()


async def worker_sql(h, claim, statement, **params):
    async with h.runtime.engine.begin() as connection:
        await connection.execute(
            text("SELECT platform.messaging_admit(:job,:claim)"),
            {"job": claim.job_id, "claim": claim.claim_token},
        )
        return (
            await connection.execute(
                text(statement),
                {"job": claim.job_id, "claim": claim.claim_token, **params},
            )
        ).scalar_one()


async def receive(h, p=None):
    receipt = await ingress(h, p)
    claim = await h.kernel.claim_job("telegram-receive")
    assert claim is not None and str(claim.job_id) == receipt["job_id"]
    result = await h.kernel.process_inbox(claim)
    rows = await query(
        h, "SELECT conversation_id FROM app.messages WHERE id=:id", id=result.message_id
    )
    return receipt, result, rows[0]["conversation_id"]


async def prepare(h, conversation, key="test-key", value=" exact reply "):
    return await owner_sql(
        h,
        "SELECT platform.messaging_prepare_text(:conv,:value,:key)",
        conv=conversation,
        value=value,
        key=key,
    )


async def observe_owner(h, conversation, probe, observation=None):
    return await owner_sql(
        h,
        "SELECT platform.telegram_owner_observe(:conv,:generation,:version,CAST(:observation AS jsonb))",
        conv=conversation,
        generation=probe["generation"],
        version=probe["observation_version"],
        observation=json.dumps(observation or observed()),
    )


async def request(h, conversation, key="test-key", value=" exact reply "):
    async with h.runtime.engine.begin() as connection:
        await raw_context(connection)
        result = (
            await connection.execute(
                text("SELECT platform.messaging_prepare_text(:conv,:value,:key)"),
                {"conv": conversation, "value": value, "key": key},
            )
        ).scalar_one()
        if result["code"] == "REPLAY":
            return result
        probe = result["probe"]
        result = (
            await connection.execute(
                text("SELECT platform.telegram_owner_observe(:conv,:g,:v,CAST(:o AS jsonb))"),
                {
                    "conv": conversation,
                    "g": probe["generation"],
                    "v": probe["observation_version"],
                    "o": json.dumps(observed()),
                },
            )
        ).scalar_one()
        assert result["code"] == "OBSERVED"
        return (
            await connection.execute(
                text("SELECT platform.messaging_request_text(:conv,:value,:key)"),
                {"conv": conversation, "value": value, "key": key},
            )
        ).scalar_one()


async def probe_worker(h, claim):
    return await worker_sql(h, claim, "SELECT platform.telegram_worker_probe(:job,:claim)")


async def begin_observed(h, claim, probe, observation=None):
    return await worker_sql(
        h,
        claim,
        "SELECT platform.telegram_begin_send(:job,:claim,:g,:v,CAST(:o AS jsonb))",
        g=probe["generation"],
        v=probe["observation_version"],
        o=json.dumps(observation or observed()),
    )


@pytest_asyncio.fixture
async def telegram(messaging):
    h = messaging
    start = datetime.now(UTC) - timedelta(days=1)
    end = start + timedelta(days=30)
    async with h.migrator.begin() as connection:
        h.telegram_connection = UUID(
            (
                await connection.execute(
                    text(
                        "SELECT platform.initialize_telegram_connection(:ws,:business,:bot,:external,:owner,CAST(:o AS jsonb))"
                    ),
                    {
                        "ws": A,
                        "business": BA,
                        "bot": BOT,
                        "external": EXTERNAL,
                        "owner": OWNER,
                        "o": json.dumps(observed()),
                    },
                )
            ).scalar_one()["connection_id"]
        )
        assert (
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_messaging_billing(:ws,'Telegram TEST',:start,:end)"
                ),
                {"ws": A, "start": start, "end": end},
            )
        ).scalar_one() == "CREATED"
    h.billing_interval = start, end
    try:
        yield h
    finally:
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


async def test_receipt_concurrent_dedupe_and_exact_conflict_precede_disconnection(telegram):
    h = telegram
    p = projection()
    results = await asyncio.gather(*(ingress(h, p) for _ in range(6)))
    assert {r["code"] for r in results} == {"ACCEPTED", "DUPLICATE"}
    assert (
        len({r["receipt_id"] for r in results})
        == len({r["inbox_id"] for r in results})
        == len({r["job_id"] for r in results})
        == 1
    )
    assert len({r["accepted_at"] for r in results}) == 1
    await query(
        h,
        "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id",
        id=h.telegram_connection,
    )
    duplicate = await ingress(h, p)
    assert duplicate["code"] == "DUPLICATE"
    conflict = copy.deepcopy(p)
    conflict["event"]["text"] += "different"
    with pytest.raises(DBAPIError) as caught:
        await ingress(h, conflict)
    assert caught.value.orig.diag.message_primary == "EVENT_ID_CONFLICT"
    assert len(await query(h, "SELECT id FROM platform.telegram_update_receipts")) == 1
    assert len(await query(h, "SELECT id FROM platform.inbox_events")) == 1
    assert len(await query(h, "SELECT id FROM platform.messaging_jobs")) == 1


async def test_unknown_binding_cross_bot_and_owner_do_not_write(telegram):
    h = telegram
    for p, bot, expected in (
        (
            projection(
                external_connection_id="unknown",
                event={**projection()["event"], "external_connection_id": "unknown"},
            ),
            BOT,
            "NOT_FOUND",
        ),
        (
            projection(event={**projection()["event"], "bot_identity": "9000002"}),
            "9000002",
            "NOT_FOUND",
        ),
        (lifecycle(owner_user_id="8000002"), BOT, "NOT_ALLOWED"),
    ):
        with pytest.raises(DBAPIError) as caught:
            await ingress(h, p, bot)
        assert caught.value.orig.diag.message_primary == expected
    assert not await query(h, "SELECT id FROM platform.telegram_update_receipts")
    assert not await query(h, "SELECT id FROM platform.inbox_events")


async def test_terminal_ignored_receipts_and_lifecycle_never_create_work(telegram):
    h = telegram
    native = projection("102")
    native["event"].update(sender_id=OWNER, chat_id=OWNER)
    echo = projection("103", sender_business_bot_id=BOT)
    edited = projection("104", kind="EDITED_BUSINESS_MESSAGE")
    edited["event"]["kind"] = "MESSAGE_EDITED"
    deleted = projection(
        "105",
        kind="DELETED_BUSINESS_MESSAGES",
        event=None,
        deleted_message_ids=["5", "6"],
        deleted_chat_id=CLIENT,
    )
    unsupported = projection("106", kind="UNSUPPORTED", external_connection_id=None, event=None)
    for p, expected in (
        (native, "IGNORED_NATIVE_OWNER_MESSAGE"),
        (echo, "IGNORED_ECHO"),
        (edited, "IGNORED_MESSAGE_EDITED"),
        (deleted, "IGNORED_MESSAGE_DELETED"),
        (unsupported, "IGNORED_UNSUPPORTED"),
    ):
        result = await ingress(h, p)
        assert (
            result["result_code"] == expected
            and result["inbox_id"] is None
            and result["job_id"] is None
        )
    before = (
        await query(
            h,
            "SELECT generation,observation_version,is_enabled,can_reply FROM platform.telegram_connection_state",
        )
    )[0]
    p = lifecycle()
    assert (await ingress(h, p))["result_code"] == "LIFECYCLE_INVALIDATED"
    after = (
        await query(
            h,
            "SELECT generation,observation_version,is_enabled,can_reply FROM platform.telegram_connection_state",
        )
    )[0]
    assert after == {
        **before,
        "generation": before["generation"] + 1,
        "observation_version": before["observation_version"] + 1,
    }
    assert (await ingress(h, p))["code"] == "DUPLICATE"
    assert (await query(h, "SELECT generation FROM platform.telegram_connection_state"))[0][
        "generation"
    ] == after["generation"]
    assert not await query(h, "SELECT id FROM platform.messaging_jobs")
    assert not await query(h, "SELECT id FROM app.messages")


@pytest.mark.parametrize(
    "relation",
    ["platform.inbox_events", "platform.messaging_jobs", "platform.telegram_update_receipts"],
)
async def test_any_ingress_write_failure_rolls_back_whole_receipt_inbox_job(telegram, relation):
    h = telegram
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform.m23_fail_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test write failure'; END $$"
            )
        )
        await c.execute(
            text(
                f"CREATE TRIGGER m23_fail AFTER INSERT ON {relation} FOR EACH ROW EXECUTE FUNCTION platform.m23_fail_insert()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            await ingress(h)
        for table in (
            "platform.inbox_events",
            "platform.messaging_jobs",
            "platform.telegram_update_receipts",
        ):
            assert not await query(h, f"SELECT id FROM {table}")
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text(f"DROP TRIGGER m23_fail ON {relation}"))
            await c.execute(text("DROP FUNCTION platform.m23_fail_insert()"))


async def test_window_clamps_future_to_first_receive_and_duplicates_never_extend(telegram):
    h = telegram
    at = datetime.now(UTC) + timedelta(days=90)
    p = projection(at=at)
    receipt, _, conv = await receive(h, p)
    first = (
        await query(h, "SELECT last_client_inbound_at FROM app.conversations WHERE id=:id", id=conv)
    )[0]["last_client_inbound_at"]
    assert first.isoformat() == datetime.fromisoformat(receipt["accepted_at"]).isoformat()
    await ingress(h, p)
    duplicate = copy.deepcopy(p)
    duplicate["update_id"] = duplicate["event"]["event_id"] = "102"
    _, result, _ = await receive(h, duplicate)
    assert result.code == "DUPLICATE"
    await receive(h, projection("103", "202", at=datetime.now(UTC) - timedelta(days=2)))
    assert (
        await query(h, "SELECT last_client_inbound_at FROM app.conversations WHERE id=:id", id=conv)
    )[0]["last_client_inbound_at"] == first


async def test_observation_cas_fences_invalidation_and_concurrent_refresh(telegram):
    h = telegram
    _, _, conv = await receive(h)
    probe = (await prepare(h, conv))["probe"]
    first = await observe_owner(h, conv, probe)
    assert first["code"] == "OBSERVED"
    second = await observe_owner(h, conv, probe, observed(can_reply=False))
    assert second["code"] == "UNAVAILABLE"
    assert (await query(h, "SELECT can_reply FROM platform.telegram_connection_state"))[0][
        "can_reply"
    ] is True
    newer = (await prepare(h, conv))["probe"]
    await ingress(h, lifecycle())
    assert (await observe_owner(h, conv, newer))["code"] == "UNAVAILABLE"
    stale = (await owner_sql(h, "SELECT platform.messaging_read_connections(101,NULL,NULL)"))[0]
    tg = next(
        row
        for row in await owner_sql(h, "SELECT platform.messaging_read_connections(101,NULL,NULL)")
        if row["provider"] == "TELEGRAM"
    )
    assert tg["state"] == "UNVERIFIED"
    assert stale
    probe = (await prepare(h, conv))["probe"]
    assert (await observe_owner(h, conv, probe, observed(can_reply=False)))["code"] == "NOT_ALLOWED"
    assert (await query(h, "SELECT can_reply FROM platform.telegram_connection_state"))[0][
        "can_reply"
    ] is False


async def test_new_intent_requires_same_uow_observation_and_replay_precedes_gates(telegram):
    h = telegram
    _, _, conv = await receive(h)
    probe = (await prepare(h, conv))["probe"]
    assert (await observe_owner(h, conv, probe))["code"] == "OBSERVED"
    with pytest.raises(DBAPIError) as caught:
        await owner_sql(
            h, "SELECT platform.messaging_request_text(:conv,' exact reply ','test-key')", conv=conv
        )
    assert caught.value.orig.diag.message_primary == "NOT_ALLOWED"
    original = await request(h, conv)
    await query(
        h,
        "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id",
        id=h.telegram_connection,
    )
    await query(
        h,
        "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' RETURNING workspace_id",
    )
    replay = await prepare(h, conv)
    assert replay == {**original, "code": "REPLAY"}
    with pytest.raises(DBAPIError) as caught:
        await prepare(h, conv, value="different")
    assert caught.value.orig.diag.message_primary == "IDEMPOTENCY_KEY_CONFLICT"
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        ws=A,
        actor=UA,
    )
    with pytest.raises(DBAPIError) as caught:
        await prepare(h, conv)
    assert caught.value.orig.diag.message_primary == "ACCESS_DENIED"


async def test_old_begin_and_unprobed_claim_cannot_bypass_telegram_preflight(telegram):
    h = telegram
    _, _, conv = await receive(h)
    await request(h, conv)
    claim = await h.kernel.claim_job("telegram-worker")
    assert claim is not None
    for statement, params in (
        ("SELECT platform.messaging_begin_send(:job,:claim)", {}),
        (
            "SELECT platform.telegram_begin_send(:job,:claim,1,2,CAST(:o AS jsonb))",
            {"o": json.dumps(observed())},
        ),
    ):
        with pytest.raises(DBAPIError) as caught:
            await worker_sql(h, claim, statement, **params)
        assert caught.value.orig.diag.message_primary in {"NOT_ALLOWED", "STALE_CLAIM"}
    probe = await probe_worker(h, claim)
    assert probe["connection_id"] == str(h.telegram_connection)
    await ingress(h, lifecycle())
    denied = await begin_observed(h, claim, probe)
    assert denied == {"code": "UNAVAILABLE", "status": "PENDING"}
    assert (await query(h, "SELECT status,attempt_id FROM app.outbox_events")) == [
        {"status": "PENDING", "attempt_id": None}
    ]
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE status='READY' RETURNING id",
    )
    new_claim = await h.kernel.claim_job("telegram-new-worker")
    assert new_claim is not None
    with pytest.raises(DBAPIError) as caught:
        await begin_observed(h, new_claim, probe)
    assert caught.value.orig.diag.message_primary == "STALE_CLAIM"
    fresh = await probe_worker(h, new_claim)
    permitted = await begin_observed(h, new_claim, fresh)
    assert permitted["code"] == "PERMITTED" and permitted["provider"] == "TELEGRAM"
    assert permitted["external_connection_id"] == EXTERNAL and permitted["chat_id"] == CLIENT


@pytest.mark.parametrize("change", ["owner", "business", "connection", "billing", "window"])
async def test_dispatch_rechecks_current_authority_business_billing_and_window(telegram, change):
    h = telegram
    _, _, conv = await receive(h)
    await request(h, conv)
    claim = await h.kernel.claim_job("recheck")
    assert claim is not None
    probe = await probe_worker(h, claim)
    statement = {
        "owner": "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        "business": "UPDATE app.businesses SET status='ARCHIVED' WHERE workspace_id=:ws RETURNING id",
        "connection": "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:conn RETURNING id",
        "billing": "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' WHERE workspace_id=:ws RETURNING workspace_id",
        "window": "UPDATE app.conversations SET last_client_inbound_at=clock_timestamp()-interval '24 hours' WHERE id=:conv RETURNING id",
    }[change]
    await query(h, statement, ws=A, actor=UA, conn=h.telegram_connection, conv=conv)
    assert await begin_observed(h, claim, probe) == {"code": "NOT_ALLOWED", "status": "FAILED"}
    assert (await query(h, "SELECT status,attempt_id FROM app.outbox_events")) == [
        {"status": "FAILED", "attempt_id": None}
    ]


async def test_429_finalized_delay_is_durable_replay_and_horizon_exhausts(telegram):
    h = telegram
    _, _, conv = await receive(h)
    await request(h, conv)
    claim = await h.kernel.claim_job("429-worker")
    assert claim is not None
    permit = await begin_observed(h, claim, await probe_worker(h, claim))
    params = {
        "job": claim.job_id,
        "claim": claim.claim_token,
        "attempt": UUID(permit["attempt_id"]),
        "delay": 120,
    }
    finish = "SELECT platform.messaging_finish_send(:job,:claim,:attempt,'NOT_SENT_RETRYABLE',NULL,'DEPENDENCY_UNAVAILABLE',:delay)"
    before = datetime.now(UTC)
    result = await sql(h, finish, **params)
    assert result["status"] == "PENDING" and result["retry_after_seconds"] == 120
    due = datetime.fromisoformat(result["available_at"])
    assert due >= before + timedelta(seconds=120)
    assert await sql(h, finish, **params) == {**result, "code": "ALREADY_FINALIZED"}
    with pytest.raises(DBAPIError) as caught:
        await sql(h, finish, **{**params, "delay": 121})
    assert caught.value.orig.diag.message_primary == "STALE_CLAIM"
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp(),first_started_at=clock_timestamp()-interval '14 minutes' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    claim2 = await h.kernel.claim_job("429-horizon")
    assert claim2 is not None
    permit2 = await begin_observed(h, claim2, await probe_worker(h, claim2))
    result2 = await sql(
        h,
        finish,
        job=claim2.job_id,
        claim=claim2.claim_token,
        attempt=UUID(permit2["attempt_id"]),
        delay=120,
    )
    assert result2["status"] == "FAILED"
    assert (
        await query(
            h,
            "SELECT status,error_code FROM platform.messaging_jobs WHERE id=:id",
            id=claim2.job_id,
        )
    ) == [{"status": "DEAD", "error_code": "RETRY_EXHAUSTED"}]


async def test_owner_cursor_projection_has_no_internal_ids_and_checks_exact_anchor(telegram):
    h = telegram
    _, _, conv = await receive(h)
    send = await request(h, conv)
    rows = await owner_sql(
        h, "SELECT platform.messaging_read_messages(:conv,101,NULL,NULL)", conv=conv
    )
    assert len(rows) == 2
    assert set(rows[0]) == {
        "message_id",
        "conversation_id",
        "direction",
        "content_type",
        "text",
        "occurred_at",
        "created_at",
        "version",
        "file",
        "delivery",
    }
    assert rows[0]["message_id"] == send["message_id"] and rows[0]["file"] is None
    assert set(rows[0]["delivery"]) == {"status", "error_code", "completed_at", "version"}
    page = await owner_sql(
        h,
        "SELECT platform.messaging_read_messages(:conv,1,:at,:id)",
        conv=conv,
        at=datetime.fromisoformat(rows[0]["created_at"]),
        id=UUID(rows[0]["message_id"]),
    )
    assert page == rows[1:]
    for workspace, anchor in ((A, uuid4()), (B, UUID(rows[0]["message_id"]))):
        with pytest.raises(DBAPIError) as caught:
            await owner_sql(
                h,
                "SELECT platform.messaging_read_messages(:conv,1,:at,:id)",
                workspace=workspace,
                conv=conv,
                at=datetime.fromisoformat(rows[0]["created_at"]),
                id=anchor,
            )
        assert caught.value.orig.diag.message_primary in {"INVALID_INPUT", "ACCESS_DENIED"}


def _fingerprint_vector(p):
    def packed(prefix, values):
        raw = prefix
        for value in values:
            if value is None:
                raw += b"-1:\n"
            else:
                encoded = value.encode()
                raw += str(len(encoded)).encode() + b":" + encoded + b"\n"
        return hashlib.sha256(raw).hexdigest()

    e = p["event"]
    event_digest = (
        None
        if e is None
        else packed(
            b"asm:m2:normalized_event:v1\n",
            [
                e[key]
                for key in (
                    "provider",
                    "bot_identity",
                    "event_id",
                    "kind",
                    "external_connection_id",
                    "chat_id",
                    "message_id",
                    "sender_id",
                    "occurred_at",
                    "text",
                    "image_file_id",
                    "media_group_id",
                )
            ],
        )
    )
    return packed(
        b"asm:m2:telegram_update:v1\n",
        [
            BOT,
            p["update_id"],
            p["kind"],
            p["external_connection_id"],
            p["owner_user_id"],
            p["sender_business_bot_id"],
            None if p["is_enabled"] is None else str(p["is_enabled"]).lower(),
            None if p["can_reply"] is None else str(p["can_reply"]).lower(),
            p["lifecycle_date"],
            event_digest,
            p["deleted_chat_id"],
            None if p["deleted_message_ids"] is None else ",".join(p["deleted_message_ids"]),
        ],
    )


async def test_db_receipt_codec_preserves_opaque_utf8_and_delete_chat(telegram):
    h = telegram
    p = projection(at=datetime(2026, 9, 21, 1, 2, 3, 4, UTC))
    await ingress(h, p)
    stored = (
        await query(
            h,
            "SELECT encode(fingerprint,'hex') AS fingerprint FROM platform.telegram_update_receipts WHERE update_id='101'",
        )
    )[0]
    assert stored["fingerprint"] == _fingerprint_vector(p)
    deleted = projection(
        "401",
        kind="DELETED_BUSINESS_MESSAGES",
        event=None,
        deleted_chat_id=CLIENT,
        deleted_message_ids=["1", "22", "3"],
    )
    await ingress(h, deleted)
    stored = (
        await query(
            h,
            "SELECT encode(fingerprint,'hex') AS fingerprint FROM platform.telegram_update_receipts WHERE update_id='401'",
        )
    )[0]
    assert stored["fingerprint"] == _fingerprint_vector(deleted)
    with pytest.raises(DBAPIError) as caught:
        await ingress(h, {**deleted, "deleted_chat_id": "7000002"})
    assert caught.value.orig.diag.message_primary == "EVENT_ID_CONFLICT"


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "forbidden"},
        {"update_id": True},
        {"update_id": "01"},
        {"update_id": "9223372036854775808"},
        {"sender_business_bot_id": 123},
        {"is_enabled": "false"},
        {"deleted_message_ids": ["1"]},
        {"owner_user_id": OWNER},
        {"lifecycle_date": "now"},
    ],
)
async def test_runtime_ingress_rejects_untyped_or_ambiguous_projection(telegram, change):
    with pytest.raises(DBAPIError) as caught:
        await ingress(telegram, projection(**change))
    assert caught.value.orig.diag.message_primary == "INVALID_INPUT"
    assert not await query(telegram, "SELECT id FROM platform.telegram_update_receipts")


async def test_structural_billing_absence_is_unavailable_before_any_new_intent(telegram):
    h = telegram
    _, _, conv = await receive(h)
    await query(
        h,
        "DELETE FROM platform.workspace_service_modes WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
    )
    with pytest.raises(DBAPIError) as caught:
        await request(h, conv)
    assert caught.value.orig.sqlstate == "P2301"
    assert caught.value.orig.diag.message_primary == "BILLING_STATE_UNAVAILABLE"
    assert caught.value.orig.diag.message_detail == "BILLING_STATE_MISSING"
    assert not await query(h, "SELECT id FROM app.messages WHERE direction='OUTBOUND'")
    assert not await query(h, "SELECT id FROM platform.messaging_command_receipts")


@pytest.mark.parametrize("malformed", ["INTEGER", "STANDARD"])
@pytest.mark.parametrize("scenario", ["current", "inactive", "historical"])
async def test_known_product_revision_type_precedes_gates_in_python_sql_and_worker(
    telegram, malformed, scenario
):
    h = telegram
    _, _, conv = await receive(h)
    accepted = await request(h, conv)
    # Publish a separate structurally legal catalog through its real lifecycle.
    # Its known product key violates the product contract, not generic R4 typing.
    # No SEALED row or guard is altered to construct this state.
    async with h.migrator.begin() as c:
        plan_id = (
            await c.execute(
                text(
                    "INSERT INTO platform.saas_plans(code,display_name,status) "
                    "VALUES(:code,'Malformed known product TEST','ACTIVE') RETURNING plan_id"
                ),
                {"code": "m23_parity_" + uuid4().hex},
            )
        ).scalar_one()
        revision_id = (
            await c.execute(
                text(
                    "INSERT INTO platform.saas_plan_revisions(plan_id,revision,publication_state) "
                    "VALUES(:plan,1,'DRAFT') RETURNING plan_revision_id"
                ),
                {"plan": plan_id},
            )
        ).scalar_one()
        await c.execute(
            text(
                "INSERT INTO platform.plan_entitlements(plan_revision_id,capability_key,value_kind,enabled,limit_value,criticality) "
                "VALUES(:revision,'messaging.manual_send',:kind,:enabled,:limit,:criticality)"
            ),
            {
                "revision": revision_id,
                "kind": "INTEGER" if malformed == "INTEGER" else "BOOLEAN",
                "enabled": None if malformed == "INTEGER" else True,
                "limit": 1 if malformed == "INTEGER" else None,
                "criticality": "ESSENTIAL" if malformed == "INTEGER" else "STANDARD",
            },
        )
        await c.execute(
            text(
                "UPDATE platform.saas_plan_revisions SET publication_state='SEALED',"
                "published_at=clock_timestamp() WHERE plan_revision_id=:revision"
            ),
            {"revision": revision_id},
        )
        if scenario == "historical":
            await c.execute(
                text(
                    "INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,required_publication_state,status,funding_mode,effective_from,effective_until) "
                    "VALUES(:ws,:revision,'SEALED','ACTIVE','COMPED',:start,:end)"
                ),
                {
                    "ws": A,
                    "revision": revision_id,
                    "start": h.billing_interval[0] - timedelta(days=3),
                    "end": h.billing_interval[0] - timedelta(days=2),
                },
            )
        else:
            await c.execute(
                text(
                    "UPDATE platform.workspace_subscriptions SET plan_revision_id=:revision "
                    "WHERE workspace_id=:ws"
                ),
                {"ws": A, "revision": revision_id},
            )
        if scenario != "current":
            await c.execute(
                text(
                    "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' "
                    "WHERE workspace_id=:ws"
                ),
                {"ws": A},
            )
        if scenario == "inactive":
            for table in ("platform.workspace_subscriptions", "platform.workspace_service_modes"):
                await c.execute(
                    text(
                        f"UPDATE {table} SET effective_from=:start,effective_until=:end WHERE workspace_id=:ws"
                    ),
                    {
                        "ws": A,
                        "start": h.billing_interval[1] + timedelta(days=1),
                        "end": h.billing_interval[1] + timedelta(days=2),
                    },
                )

    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        snapshot = await unit.billing_snapshot()
    with pytest.raises(BillingUnavailable) as python_error:
        EntitlementService().evaluate_product(A, snapshot, "messaging.manual_send")
    assert python_error.value.reason == "REVISION_INVALID"
    if scenario == "historical":
        assert len(snapshot["history"]) == 2
        assert next(row for row in snapshot["history"] if row["is_current"])[
            "plan_revision_id"
        ] != str(revision_id)
    elif scenario == "inactive":
        assert not any(row["is_current"] for row in snapshot["history"])
        assert snapshot["modes"][0]["is_active"] is False

    with pytest.raises(DBAPIError) as sql_error:
        await request(h, conv, key="malformed-product-must-not-enqueue")
    assert sql_error.value.orig.sqlstate == "P2301"
    assert sql_error.value.orig.diag.message_primary == "BILLING_STATE_UNAVAILABLE"
    assert sql_error.value.orig.diag.message_detail == python_error.value.reason
    assert (
        await query(h, "SELECT id::text AS id FROM app.messages WHERE direction='OUTBOUND'")
    ) == [{"id": accepted["message_id"]}]

    claim = await h.kernel.claim_job("structural-product-recheck")
    assert claim is not None
    result = await begin_observed(h, claim, await probe_worker(h, claim))
    assert result == {"code": "UNAVAILABLE", "status": "PENDING"}
    assert (await query(h, "SELECT status,attempt_id,error_code FROM app.outbox_events")) == [
        {"status": "PENDING", "attempt_id": None, "error_code": "DEPENDENCY_UNAVAILABLE"}
    ]
    assert (
        await query(
            h, "SELECT status,error_code FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
        )
    ) == [{"status": "READY", "error_code": "DEPENDENCY_UNAVAILABLE"}]


async def test_readonly_failure_observation_commits_unavailable_without_permission(telegram):
    h = telegram
    _, _, conv = await receive(h)
    probe = (await prepare(h, conv))["probe"]
    failure = dict.fromkeys(observed())
    failure["error_code"] = "DEPENDENCY_TIMEOUT"
    assert (await observe_owner(h, conv, probe, failure))["code"] == "UNAVAILABLE"
    rows = await owner_sql(h, "SELECT platform.messaging_read_connections(101,NULL,NULL)")
    assert next(r for r in rows if r["provider"] == "TELEGRAM")["state"] == "UNAVAILABLE"
    assert (
        await query(
            h, "SELECT is_enabled,can_reply,error_code FROM platform.telegram_connection_state"
        )
    ) == [{"is_enabled": None, "can_reply": None, "error_code": "DEPENDENCY_TIMEOUT"}]
