"""Exact TEST MockTransport wire. No real Telegram or provider call."""

import asyncio
import hashlib
import io
from email.parser import BytesParser
from email.policy import default
from uuid import uuid4

import httpx
import pytest
from asm.files.validation import decode_image
from asm.messaging.models import OutcomeKind
from asm.portfolio.delivery import PortfolioPhotoSendPermit
from asm.telegram.client import TelegramClient
from PIL import Image
from test_m2_3_transport import BOT, CHAT, EXTERNAL, config, permit


def photo(image_format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 48), (31, 83, 151)).save(stream, image_format)
    content = stream.getvalue()
    value = PortfolioPhotoSendPermit.model_validate(
        permit().model_dump()
        | dict(
            text="Тестовая работа 🎨 <plain>",
            ai_delivery=True,
            portfolio_photo=True,
            intent_id=uuid4(),
            asset_version_id=uuid4(),
            source_sha256=hashlib.sha256(content).hexdigest(),
            manifest=decode_image(content),
        )
    )
    return value, content


def success(value):
    return {
        "ok": True,
        "result": {
            "message_id": 313,
            "business_connection_id": EXTERNAL,
            "chat": {"id": CHAT, "type": "private"},
            "date": 1794840000,
            "caption": value.text,
            "photo": [
                {
                    "file_id": "opaque-photo",
                    "file_unique_id": "opaque-unique",
                    "width": 32,
                    "height": 48,
                }
            ],
        },
    }


@pytest.mark.parametrize(
    "image_format,mime,filename",
    [("PNG", "image/png", "portfolio.png"), ("JPEG", "image/jpeg", "portfolio.jpg")],
)
async def test_exact_multipart_original_bytes_one_send_no_text_or_url(image_format, mime, filename):
    value, content = photo(image_format)
    requests = []

    async def handler(request):
        requests.append(request)
        assert request.url.host == "api.telegram.org"
        assert request.url.path.endswith("/sendPhoto")
        assert request.headers["accept-encoding"] == "identity"
        raw = await request.aread()
        parts = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + raw
        )
        payload = {p.get_param("name", header="content-disposition"): p for p in parts.iter_parts()}
        assert set(payload) == {"business_connection_id", "chat_id", "caption", "photo"}
        assert payload["business_connection_id"].get_payload(decode=True).decode() == EXTERNAL
        assert payload["chat_id"].get_payload(decode=True).decode() == str(CHAT)
        assert payload["caption"].get_payload(decode=True).decode() == value.text
        assert payload["photo"].get_payload(decode=True) == content
        assert payload["photo"].get_content_type() == mime
        assert payload["photo"].get_filename() == filename
        return httpx.Response(200, json=success(value))

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        assert (await client.send_photo(value, content)).kind == OutcomeKind.SUCCESS
        assert (await client.send(value)).kind == OutcomeKind.NOT_SENT_PERMANENT
    finally:
        await client.aclose()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        {"business_connection_id": "wrong"},
        {"chat": {"id": CHAT + 1, "type": "private"}},
        {"chat": {"id": CHAT, "type": "group"}},
        {"message_id": True},
        {"photo": []},
        {"photo": [{"file_id": "one"}]},
        {"photo": "url"},
        {"caption": "wrong"},
        {"date": True},
        {"text": "separate text"},
    ],
)
async def test_malformed_or_wrong_destination_success_is_unknown(mutation):
    value, content = photo()
    body = success(value)
    body["result"].update(mutation)
    client = TelegramClient(
        config(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    )
    try:
        assert (await client.send_photo(value, content)).kind == OutcomeKind.UNKNOWN
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (
            429,
            {
                "ok": False,
                "error_code": 429,
                "description": "limited",
                "parameters": {"retry_after": 3},
            },
            OutcomeKind.NOT_SENT_RETRYABLE,
        ),
        (
            429,
            {
                "ok": False,
                "error_code": 429,
                "description": "limited",
                "parameters": {"retry_after": True},
            },
            OutcomeKind.NOT_SENT_PERMANENT,
        ),
        (
            403,
            {"ok": False, "error_code": 403, "description": "denied"},
            OutcomeKind.NOT_SENT_PERMANENT,
        ),
        (503, {"ok": False, "error_code": 503, "description": "unavailable"}, OutcomeKind.UNKNOWN),
        (200, {"ok": True}, OutcomeKind.UNKNOWN),
        (200, {"ok": "true", "result": {}}, OutcomeKind.UNKNOWN),
        (302, {"ok": False}, OutcomeKind.UNKNOWN),
    ],
)
async def test_explicit_not_sent_and_ambiguous_outcomes_do_not_retry(status, body, expected):
    value, content = photo()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body, headers={"location": "https://other.invalid"})

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        result = await client.send_photo(value, content)
        assert result.kind == expected
        assert result.retry_after_seconds == (
            3 if expected == OutcomeKind.NOT_SENT_RETRYABLE else None
        )
    finally:
        await client.aclose()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ConnectError("unreachable"), OutcomeKind.NOT_SENT_RETRYABLE),
        (httpx.ConnectTimeout("connect"), OutcomeKind.NOT_SENT_RETRYABLE),
        (httpx.WriteTimeout("response lost"), OutcomeKind.UNKNOWN),
        (httpx.ReadTimeout("response lost"), OutcomeKind.UNKNOWN),
        (httpx.RemoteProtocolError("lost"), OutcomeKind.UNKNOWN),
    ],
)
async def test_transport_failure_classification_one_attempt(error, expected):
    value, content = photo()
    calls = []

    def handler(request):
        calls.append(request)
        raise error

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        assert (await client.send_photo(value, content)).kind == expected
    finally:
        await client.aclose()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "wire,headers",
    [
        (b"x" * 65537, {}),
        (b'{"ok":true,"ok":false}', {}),
        (b"{}", {"content-encoding": "gzip"}),
        (b"not json", {}),
    ],
)
async def test_response_guards_cannot_create_sent(wire, headers):
    value, content = photo()
    client = TelegramClient(
        config(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=wire, headers=headers)),
    )
    try:
        assert (await client.send_photo(value, content)).kind == OutcomeKind.UNKNOWN
    finally:
        await client.aclose()


async def test_unapproved_transport_bad_bytes_and_wrong_bot_never_call():
    value, content = photo()

    def forbidden(request):
        raise AssertionError("No wire admission")

    client = TelegramClient(config(), transport=httpx.MockTransport(forbidden))
    real = TelegramClient(config())
    try:
        assert (await real.send_photo(value, content)).kind == OutcomeKind.NOT_SENT_PERMANENT
        assert (
            await client.send_photo(value, content + b"x")
        ).kind == OutcomeKind.NOT_SENT_PERMANENT
        altered = PortfolioPhotoSendPermit.model_validate(
            value.model_dump() | {"bot_identity": str(BOT + 1)}
        )
        assert (await client.send_photo(altered, content)).kind == OutcomeKind.NOT_SENT_PERMANENT
        assert (await client.send_photo(permit(), content)).kind == OutcomeKind.NOT_SENT_PERMANENT
    finally:
        await client.aclose()
        await real.aclose()


async def test_cancel_propagates_no_retry_or_sent():
    value, content = photo()
    calls = []

    async def handler(request):
        calls.append(await request.aread())
        raise asyncio.CancelledError

    client = TelegramClient(config(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(asyncio.CancelledError):
            await client.send_photo(value, content)
    finally:
        await client.aclose()
    assert len(calls) == 1
