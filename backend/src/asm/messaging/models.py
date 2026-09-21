"""Exact normalized values and fingerprint codec shared with migration 0005."""

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from asm.messaging.errors import Code, MessagingError


class EventKind(StrEnum):
    CLIENT_MESSAGE = "CLIENT_MESSAGE"
    NATIVE_OWNER_MESSAGE = "NATIVE_OWNER_MESSAGE"
    MESSAGE_EDITED = "MESSAGE_EDITED"
    MESSAGE_DELETED = "MESSAGE_DELETED"
    UNSUPPORTED = "UNSUPPORTED"


def scalar_text(value: object, maximum: int, byte_maximum: int) -> str:
    if not isinstance(value, str) or "\0" in value or len(value) > maximum:
        raise MessagingError(Code.INVALID_INPUT)
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise MessagingError(Code.INVALID_INPUT) from None
    if len(encoded) > byte_maximum:
        raise MessagingError(Code.INVALID_INPUT)
    return value


def identifier(value: object, image: bool = False) -> str:
    result = scalar_text(value, 1024 if image else 256, 4096 if image else 1024)
    if not result or any(unicodedata.category(c) == "Cc" for c in result):
        raise MessagingError(Code.INVALID_INPUT)
    return result


def manual_text(value: object) -> str:
    result = scalar_text(value, 4096, 16384)
    if not result or not result.strip():
        raise MessagingError(Code.INVALID_INPUT)
    return result


def command_key(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value) is None:
        raise MessagingError(Code.INVALID_INPUT)
    return value


def timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MessagingError(Code.INVALID_INPUT)
    try:
        value = value.astimezone(UTC)
    except (ValueError, OverflowError):
        raise MessagingError(Code.INVALID_INPUT) from None
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class NormalizedEventV1:
    provider: str
    bot_identity: str
    event_id: str
    kind: EventKind
    external_connection_id: str
    chat_id: str | None = None
    message_id: str | None = None
    sender_id: str | None = None
    occurred_at: datetime | None = None
    text: str | None = field(default=None, repr=False)
    image_file_id: str | None = field(default=None, repr=False)
    media_group_id: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in {"CONTROLLED", "TELEGRAM"} or type(self.kind) is not EventKind:
            raise MessagingError(Code.INVALID_INPUT)
        for value in (self.bot_identity, self.event_id, self.external_connection_id):
            identifier(value)
        for optional in (self.chat_id, self.message_id, self.sender_id, self.media_group_id):
            if optional is not None:
                identifier(optional)
        if self.image_file_id is not None:
            identifier(self.image_file_id, image=True)
        if self.text is not None:
            scalar_text(self.text, 4096, 16384)
        if self.occurred_at is not None:
            timestamp(self.occurred_at)
        if self.kind == EventKind.CLIENT_MESSAGE and (
            any(
                v is None for v in (self.chat_id, self.message_id, self.sender_id, self.occurred_at)
            )
            or (not self.text and self.image_file_id is None)
        ):
            raise MessagingError(Code.INVALID_INPUT)
        if len(self.encoded().encode("utf-8")) > 65536:
            raise MessagingError(Code.INVALID_INPUT)

    def values(self) -> dict[str, str | None]:
        result = asdict(self)
        result["kind"] = self.kind.value
        result["occurred_at"] = timestamp(self.occurred_at) if self.occurred_at else None
        return result

    def encoded(self) -> str:
        return json.dumps(self.values(), ensure_ascii=False, separators=(",", ":"))

    def fingerprint_bytes(self, *, projection: bool = False) -> bytes:
        result = b"asm:m2:normalized_event:v1\n"
        for key, value in self.values().items():
            if projection and key == "event_id":
                continue
            if value is None:
                result += b"-1:\n"
            else:
                raw = value.encode("utf-8")
                result += str(len(raw)).encode("ascii") + b":" + raw + b"\n"
        return result

    def fingerprint(self) -> str:
        return hashlib.sha256(self.fingerprint_bytes()).hexdigest()


def text_fingerprint(workspace: UUID, actor: UUID, conversation: UUID, value: str) -> str:
    if any(type(v) is not UUID for v in (workspace, actor, conversation)):
        raise MessagingError(Code.INVALID_INPUT)
    value = manual_text(value)
    return hashlib.sha256(
        f"asm:m2:send_manual_text:v1\n{workspace}\n{actor}\n{conversation}\n{value}".encode()
    ).hexdigest()


class OutcomeKind(StrEnum):
    SUCCESS = "SUCCESS"
    NOT_SENT_RETRYABLE = "NOT_SENT_RETRYABLE"
    NOT_SENT_PERMANENT = "NOT_SENT_PERMANENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SendOutcome:
    kind: OutcomeKind
    provider_message_id: str | None = None
    error_code: Code | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not OutcomeKind:
            raise MessagingError(Code.INVALID_INPUT)
        if self.retry_after_seconds is not None and (
            self.kind != OutcomeKind.NOT_SENT_RETRYABLE
            or type(self.retry_after_seconds) is not int
            or not 1 <= self.retry_after_seconds <= 86400
        ):
            raise MessagingError(Code.INVALID_INPUT)
        if self.kind == OutcomeKind.SUCCESS:
            identifier(self.provider_message_id)
            if self.error_code is not None:
                raise MessagingError(Code.INVALID_INPUT)
        elif self.provider_message_id is not None or type(self.error_code) is not Code:
            raise MessagingError(Code.INVALID_INPUT)
