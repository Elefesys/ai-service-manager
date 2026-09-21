"""Exact byte vectors and strict, privacy-safe boundaries (no mocked DB evidence)."""

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from asm.billing.models import AuditPage
from asm.messaging.adapter import ControlledAdapter, TrustedSource
from asm.messaging.errors import MessagingError
from asm.messaging.models import (
    EventKind,
    NormalizedEventV1,
    command_key,
    manual_text,
    text_fingerprint,
)
from pydantic import ValidationError


def event(**changes):
    base = NormalizedEventV1(
        "CONTROLLED",
        "bot-a",
        "evt-1",
        EventKind.CLIENT_MESSAGE,
        "conn-a",
        "chat-a",
        "msg-1",
        "user-a",
        datetime(2026, 1, 2, 3, 4, 5, 6, UTC),
        "hello",
    )
    return replace(base, **changes)


def test_event_codec_exact_utf8_null_length_and_timezone():
    e = event(text=' é\ne\u0301 "🎨" ')
    raw = (
        b"asm:m2:normalized_event:v1\n10:CONTROLLED\n5:bot-a\n5:evt-1\n"
        b"14:CLIENT_MESSAGE\n6:conn-a\n6:chat-a\n5:msg-1\n6:user-a\n"
        b"27:2026-01-02T03:04:05.000006Z\n"
        + str(len(e.text.encode())).encode()
        + b":"
        + e.text.encode()
        + b"\n-1:\n-1:\n"
    )
    assert e.fingerprint_bytes() == raw
    assert e.fingerprint() == hashlib.sha256(raw).hexdigest()
    assert (
        replace(e, occurred_at=e.occurred_at.astimezone(timezone(timedelta(hours=7)))).fingerprint()
        == e.fingerprint()
    )
    assert replace(e, event_id="evt-2").fingerprint() != e.fingerprint()
    assert replace(e, event_id="evt-2").fingerprint_bytes(projection=True) == e.fingerprint_bytes(
        projection=True
    )
    assert replace(e, text=e.text.strip()).fingerprint() != e.fingerprint()


@pytest.mark.parametrize("value", [" e\u0301 ", "é", 'line\n"quote"\\', "🎨" * 4096, "\tword\n"])
def test_manual_fingerprint_exact_bytes_not_json_or_normalized(value):
    ws, actor, conversation = (UUID(int=n) for n in (1, 2, 3))
    expected = f"asm:m2:send_manual_text:v1\n{ws}\n{actor}\n{conversation}\n{value}".encode()
    assert manual_text(value) == value
    assert text_fingerprint(ws, actor, conversation, value) == hashlib.sha256(expected).hexdigest()
    assert (
        text_fingerprint(ws, actor, conversation, value + "x")
        != hashlib.sha256(expected).hexdigest()
        if len(value) < 4096
        else True
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "UNSUPPORTED_PROVIDER"},  # TELEGRAM is an accepted additive M2.3 provider.
        {"kind": "CLIENT_MESSAGE"},
        {"event_id": ""},
        {"sender_id": "bad\n"},
        {"bot_identity": "x\u0085"},
        {"chat_id": "a" * 257},
        {"event_id": "\ud800"},
        {"text": "\0"},
        {"text": "a" * 4097},
        {"text": "", "image_file_id": None},
        {"occurred_at": datetime(2026, 1, 1)},
        {"message_id": None},
        {"image_file_id": "x" * 1025},
    ],
)
def test_invalid_normalized_fields_fail_before_db(changes):
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        event(**changes)


@pytest.mark.parametrize("value", ["", " ", "\t\n\u00a0\u2028", "a\0", "\udfff", "a" * 4097])
def test_manual_rejects_empty_whitespace_nul_and_invalid_unicode(value):
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        manual_text(value)


@pytest.mark.parametrize("key", ["", "key with space", "x\n", "a" * 129, "ключ", None])
def test_command_key_has_an_exact_bounded_namespace(key):
    with pytest.raises(MessagingError):
        command_key(key)


def test_ignored_optional_fields_are_null_and_image_remains_reference():
    e = NormalizedEventV1("CONTROLLED", "bot", "event", EventKind.UNSUPPORTED, "connection")
    assert e.values()["sender_id"] is None
    assert (
        event(text=None, image_file_id="opaque-reference").values()["image_file_id"]
        == "opaque-reference"
    )
    assert "hello" not in repr(event())
    adapter = ControlledAdapter(environment="TEST")
    adapter.source("bot").validate()
    with pytest.raises(MessagingError, match="ACCESS_DENIED"):
        TrustedSource("CONTROLLED", "bot", object()).validate()
    with pytest.raises(MessagingError, match="NOT_ALLOWED"):
        ControlledAdapter(environment="PRODUCTION")


def message_audit():
    return dict(
        audit_event_id=str(UUID(int=1)),
        occurred_at="2026-01-01T00:00:00.000000Z",
        correlation_id=str(UUID(int=2)),
        object_type="MESSAGE",
        object_id=str(UUID(int=3)),
        object_version="1",
        event_type="MESSAGE_SEND_REQUESTED",
        actor_kind="USER_ACCOUNT",
        actor_user_account_id=str(UUID(int=4)),
        payload={"content_type": "TEXT"},
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"object_type": "WORKSPACE_BILLING_ACCOUNT"},
        {"object_version": "2"},
        {"actor_kind": "LOCAL_PROVISIONER"},
        {"actor_user_account_id": None},
        {"payload": {"content_type": "TEXT", "text": "private"}},
        {"payload": {"content_type": "IMAGE_REFERENCE"}},
        {"object_id": "bad"},
    ],
)
def test_message_audit_has_one_exact_typed_variant(changes):
    assert (
        AuditPage.model_validate({"items": [message_audit()], "next_cursor": None})
        .items[0]
        .object_type
        == "MESSAGE"
    )
    with pytest.raises(ValidationError):
        AuditPage.model_validate({"items": [{**message_audit(), **changes}], "next_cursor": None})
