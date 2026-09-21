"""Finite Telegram parsing/wire classifications; PostgreSQL recovery is tested separately."""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from asm.files.models import FetchPermit
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind, timestamp
from asm.messaging.results import SendPermit
from asm.telegram.client import TelegramClient, TelegramError
from asm.telegram.config import TelegramSettings
from asm.telegram.normalization import normalize_update, strict_json, update_fingerprint
from asm.telegram.webhook import install_webhook
from fastapi import FastAPI
from pydantic import ValidationError

BOT, OWNER, CHAT = 9911, 9912, 9913
EXTERNAL = "opaque-connection_01"
TOKEN = "9911:synthetic_secret_123456789"
SECRET = "synthetic_webhook_secret_123456789"


def config():
    return TelegramSettings(
        ASM_ENVIRONMENT="TEST",
        ASM_TELEGRAM_ENABLED=True,
        TG_BOT_TOKEN=TOKEN,
        TG_WEBHOOK_SECRET=SECRET,
        ASM_TELEGRAM_EXPECTED_BOT_ID=str(BOT),
        ASM_TELEGRAM_WEBHOOK_URL="https://test.invalid/webhooks/telegram",
    )


def business_connection(enabled=True, reply=True):
    return {
        "id": EXTERNAL,
        "user": {"id": OWNER, "is_bot": False},
        "user_chat_id": OWNER,
        "date": 1789990000,
        "is_enabled": enabled,
        "rights": {"can_reply": reply},
    }


def update(uid=123, **changes):
    message = {
        "message_id": 77,
        "business_connection_id": EXTERNAL,
        "date": int(datetime.now(UTC).timestamp()),
        "from": {"id": CHAT, "is_bot": False},
        "chat": {"id": CHAT, "type": "private"},
        "text": "  exact e\u0301 🎨  ",
    }
    message.update(changes)
    return {"update_id": uid, "business_message": message}


def permit():
    return SendPermit(
        code="PERMITTED",
        job_id=UUID(int=1),
        claim_token=UUID(int=2),
        attempt_id=UUID(int=3),
        workspace_id=UUID(int=4),
        connection_id=UUID(int=5),
        provider="TELEGRAM",
        bot_identity=str(BOT),
        external_connection_id=EXTERNAL,
        chat_id=str(CHAT),
        text="  exact e\u0301 🎨  ",
    )


def fetch_permit():
    return FetchPermit(
        job_id=UUID(int=1),
        claim_token=UUID(int=2),
        workspace_id=UUID(int=3),
        connection_id=UUID(int=4),
        file_id=UUID(int=5),
        message_id=UUID(int=6),
        conversation_id=UUID(int=7),
        provider="TELEGRAM",
        bot_identity=str(BOT),
        external_connection_id=EXTERNAL,
        image_file_id="opaque-photo",
    )


def test_projection_exact_unicode_opaque_photo_order_and_delete_chat():
    raw = update()
    projected = normalize_update(str(BOT), raw)
    assert projected["event"]["text"] == raw["business_message"]["text"]
    assert projected["event"]["external_connection_id"] == EXTERNAL
    raw["ignored_extra"] = {"other": "irrelevant"}
    assert update_fingerprint(str(BOT), normalize_update(str(BOT), raw)) == update_fingerprint(
        str(BOT), projected
    )
    photos = [
        {"width": 10, "height": 20, "file_id": "A"},
        {"width": 20, "height": 10, "file_id": "Z"},
        {"width": 20, "height": 10, "file_id": "B"},
    ]
    raw = update(photo=photos, caption=" caption ", media_group_id="opaque_album")
    del raw["business_message"]["text"]
    first = normalize_update(str(BOT), raw)
    raw["business_message"]["photo"].reverse()
    assert normalize_update(str(BOT), raw) == first
    assert first["event"]["image_file_id"] == "Z" and first["event"]["text"] == " caption "
    raw = {
        "update_id": 125,
        "deleted_business_messages": {
            "business_connection_id": EXTERNAL,
            "chat": {"id": CHAT, "type": "private"},
            "message_ids": [2, 1],
        },
    }
    first = normalize_update(str(BOT), raw)
    assert first["event"] is None and first["deleted_message_ids"] == ["2", "1"]
    raw["deleted_business_messages"]["chat"]["id"] += 1
    assert update_fingerprint(str(BOT), first) != update_fingerprint(
        str(BOT), normalize_update(str(BOT), raw)
    )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"update_id":1,"update_id":2}',
        b'{"update_id":1,"x":"\\ud800"}',
        b'{"update_id":NaN}',
        b"\xff",
        b'{"x":"\\u0000"}',
    ],
)
def test_json_rejects_duplicate_keys_unicode_and_non_json_numbers(raw):
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        strict_json(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("update_id", True),
        ("update_id", 1.0),
        ("update_id", "1"),
        ("update_id", 0),
        ("update_id", 2**63),
    ],
)
def test_numeric_id_never_coerces_bool_float_or_string(field, value):
    raw = update()
    raw[field] = value
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        normalize_update(str(BOT), raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"from": {"id": CHAT + 1, "is_bot": False}},
        {"from": {"id": CHAT, "is_bot": True}},
        {"document": {"file_id": "photo-document"}},
        {"chat": {"id": CHAT, "type": "group"}},
    ],
)
def test_unsupported_sender_or_document_cannot_be_client_input(changes):
    assert normalize_update(str(BOT), update(**changes))["event"]["kind"] == "UNSUPPORTED"


def test_lifecycle_boolean_and_ambiguous_discriminator_are_strict():
    raw = {"update_id": 10, "business_connection": business_connection()}
    p = normalize_update(str(BOT), raw)
    assert p["is_enabled"] is True and p["can_reply"] is True and p["owner_user_id"] == str(OWNER)
    raw["business_connection"]["rights"]["can_reply"] = 1
    with pytest.raises(MessagingError):
        normalize_update(str(BOT), raw)
    raw = update()
    raw["deleted_business_messages"] = {}
    with pytest.raises(MessagingError):
        normalize_update(str(BOT), raw)


@pytest.mark.parametrize(
    "status,body,kind,delay",
    [
        (
            200,
            {
                "ok": True,
                "result": {
                    "message_id": 9,
                    "chat": {"id": CHAT, "type": "private"},
                    "business_connection_id": EXTERNAL,
                },
            },
            OutcomeKind.SUCCESS,
            None,
        ),
        (
            200,
            {
                "ok": True,
                "result": {
                    "message_id": 9,
                    "chat": {"id": CHAT + 1, "type": "private"},
                    "business_connection_id": EXTERNAL,
                },
            },
            OutcomeKind.UNKNOWN,
            None,
        ),
        (
            400,
            {"ok": False, "error_code": 400, "description": "bad"},
            OutcomeKind.NOT_SENT_PERMANENT,
            None,
        ),
        (
            401,
            {"ok": False, "error_code": 401, "description": "bad"},
            OutcomeKind.NOT_SENT_PERMANENT,
            None,
        ),
        (
            403,
            {"ok": False, "error_code": 403, "description": "bad"},
            OutcomeKind.NOT_SENT_PERMANENT,
            None,
        ),
        (
            429,
            {
                "ok": False,
                "error_code": 429,
                "description": "later",
                "parameters": {"retry_after": 17},
            },
            OutcomeKind.NOT_SENT_RETRYABLE,
            17,
        ),
        (
            429,
            {
                "ok": False,
                "error_code": 429,
                "description": "later",
                "parameters": {"retry_after": True},
            },
            OutcomeKind.NOT_SENT_PERMANENT,
            None,
        ),
        (
            500,
            {"ok": False, "error_code": 500, "description": "possibly sent"},
            OutcomeKind.UNKNOWN,
            None,
        ),
        (302, {"ok": True, "result": {}}, OutcomeKind.UNKNOWN, None),
    ],
)
async def test_send_exact_body_no_retry_validated_outcome(status, body, kind, delay):
    calls = []

    async def handler(request):
        calls.append(request)
        assert json.loads(request.content) == {
            "business_connection_id": EXTERNAL,
            "chat_id": str(CHAT),
            "text": permit().text,
        }
        return httpx.Response(status, json=body, headers={"Location": "https://evil.invalid"})

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.send(permit())
        assert result.kind == kind and result.retry_after_seconds == delay
        assert len(calls) == 1 and calls[0].url.host == "api.telegram.org"
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "error,kind",
    [
        (httpx.ConnectError, OutcomeKind.NOT_SENT_RETRYABLE),
        (httpx.PoolTimeout, OutcomeKind.NOT_SENT_RETRYABLE),
        (httpx.WriteTimeout, OutcomeKind.UNKNOWN),
        (httpx.ReadTimeout, OutcomeKind.UNKNOWN),
        (httpx.ReadError, OutcomeKind.UNKNOWN),
    ],
)
async def test_wire_phase_classification_and_no_secret_diagnostics(error, kind, caplog):
    calls = []

    async def handler(request):
        calls.append(request)
        logging.getLogger("httpx").info("secret %s", TOKEN)
        logging.getLogger("httpcore.connection").error("secret %s", TOKEN)
        raise error(TOKEN + SECRET, request=request)

    with caplog.at_level(logging.DEBUG):
        client = TelegramClient(config(), transport=httpx.MockTransport(handler))
        try:
            assert (await client.send(permit())).kind == kind
            assert len(calls) == 1
            assert TOKEN not in caplog.text and SECRET not in caplog.text
            assert TOKEN not in repr(config()) and SECRET not in repr(config())
        finally:
            await client.aclose()


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.invalid/x",
        "//evil/x",
        "../x",
        "a/../x",
        "a//x",
        "a/./x",
        "a%2fb",
        "a\\b",
        "a?token=x",
        "a#x",
        "",
    ],
)
async def test_get_file_rejects_hostile_paths_without_second_request(path):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"ok": True, "result": {"file_id": "opaque-photo", "file_path": path}}
        )

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MessagingError, match="INVALID_INPUT"):
            _ = [chunk async for chunk in client.open_image(fetch_permit())]
        assert len(calls) == 1
    finally:
        await client.aclose()


async def test_image_rejects_encoded_response_before_reading_or_decoding():
    calls = []

    class EncodedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Encoded image body must not be read")
            yield b""  # pragma: no cover

    async def handler(request):
        calls.append(request)
        assert request.headers["Accept-Encoding"] == "identity"
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {"file_id": "opaque-photo", "file_path": "photo/a.jpg"},
                },
            )
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=EncodedStream())

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MessagingError, match="INVALID_INPUT"):
            _ = [chunk async for chunk in client.open_image(fetch_permit())]
        assert len(calls) == 2
    finally:
        await client.aclose()


async def test_provider_bounded_json_and_observation_error_never_contains_secret():
    async def handler(request):
        return httpx.Response(200, content=b"x" * 65537)

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        observation = await client.observe(str(BOT), EXTERNAL, str(OWNER))
        assert observation == dict(
            bot_identity=None,
            external_connection_id=None,
            owner_user_id=None,
            is_enabled=None,
            can_reply=None,
            error_code="INVALID_INPUT",
        )
        assert (await client.send(permit())).kind == OutcomeKind.UNKNOWN
    finally:
        await client.aclose()


async def test_disabled_webhook_and_secret_verified_before_parsing():
    class Ingress:
        calls = 0

        async def ingest(self, projection, correlation):
            self.calls += 1

    ingress = Ingress()
    app = FastAPI()
    install_webhook(app, config(), ingress)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for headers in ({}, {"X-Telegram-Bot-Api-Secret-Token": "wrong"}):
            assert (
                await client.post("/webhooks/telegram", content=b"invalid", headers=headers)
            ).status_code == 403
        headers = [("X-Telegram-Bot-Api-Secret-Token", SECRET)] * 2 + [
            ("Content-Type", "application/json")
        ]
        assert (
            await client.post("/webhooks/telegram", json=update(), headers=headers)
        ).status_code == 403
        assert ingress.calls == 0
        headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"}
        assert (
            await client.post("/webhooks/telegram", json=update(), headers=headers)
        ).status_code == 200
        assert ingress.calls == 1
        for raw, expected in ((b"invalid", 422), (b"x" * 262145, 413)):
            assert (
                await client.post("/webhooks/telegram", content=raw, headers=headers)
            ).status_code == expected
        assert ingress.calls == 1
    app = FastAPI()
    install_webhook(app, TelegramSettings(ASM_TELEGRAM_ENABLED=False), None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/webhooks/telegram", json=update())).status_code == 503


def test_config_and_retry_delay_fail_closed():
    assert not TelegramSettings(ASM_TELEGRAM_ENABLED=False).enabled
    with pytest.raises(ValidationError):
        TelegramSettings(ASM_TELEGRAM_ENABLED=True)
    with pytest.raises(TelegramError):
        TelegramClient(config(), test_origin="http://evil.invalid")
    from asm.messaging.models import SendOutcome

    for value in (0, True, -1, 86401):
        with pytest.raises(MessagingError):
            SendOutcome(
                OutcomeKind.NOT_SENT_RETRYABLE,
                error_code=Code.DEPENDENCY_UNAVAILABLE,
                retry_after_seconds=value,
            )
    assert timestamp(datetime(2026, 9, 21, tzinfo=UTC)) == "2026-09-21T00:00:00.000000Z"
