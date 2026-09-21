"""Bounded typed projection. Provider extras are discarded, never authority."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import EventKind, NormalizedEventV1, identifier, scalar_text, timestamp


def invalid() -> MessagingError:
    return MessagingError(Code.INVALID_INPUT)


def numeric_id(value: object) -> str:
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise invalid()
    return str(value)


def object_value(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise invalid()
    return value


def boolean(value: object) -> bool:
    if type(value) is not bool:
        raise invalid()
    return value


def date_value(value: object) -> datetime:
    if type(value) is not int or not 0 <= value <= 253402300799:
        raise invalid()
    return datetime.fromtimestamp(value, UTC)


def strict_json(raw: bytes, maximum: int = 262144) -> dict[str, Any]:
    if not raw or len(raw) > maximum:
        raise invalid()

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise invalid()
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise invalid()

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 32:
            raise invalid()
        if isinstance(value, str):
            if "\0" in value:
                raise invalid()
            value.encode("utf-8", errors="strict")
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(key, depth + 1)
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs, parse_constant=constant
        )
        walk(value)
        return object_value(value)
    except (ValueError, UnicodeError, RecursionError):
        raise invalid() from None


def connection_fields(value: object) -> dict[str, Any]:
    data = object_value(value)
    rights = object_value(data["rights"]) if "rights" in data else {}
    return {
        "external_connection_id": identifier(data.get("id")),
        "owner_user_id": numeric_id(object_value(data.get("user")).get("id")),
        "is_enabled": boolean(data.get("is_enabled")),
        "can_reply": boolean(rights.get("can_reply", False)),
        "lifecycle_date": timestamp(date_value(data.get("date"))),
    }


def normalize_update(bot_identity: str, update: dict[str, Any]) -> dict[str, Any]:
    # bot_identity is server configuration, not provider input.
    if (
        not bot_identity.isascii()
        or not bot_identity.isdecimal()
        or str(int(bot_identity)) != bot_identity
    ):
        raise invalid()
    numeric_id(int(bot_identity))
    event_id = numeric_id(update.get("update_id"))
    known = [
        k
        for k in (
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        )
        if k in update
    ]
    if len(known) > 1:
        raise invalid()
    projection: dict[str, Any] = dict.fromkeys(
        (
            "update_id",
            "kind",
            "external_connection_id",
            "event",
            "owner_user_id",
            "deleted_message_ids",
            "sender_business_bot_id",
            "is_enabled",
            "can_reply",
            "lifecycle_date",
            "deleted_chat_id",
        )
    )
    projection.update(update_id=event_id, kind="UNSUPPORTED")
    if not known:
        return projection
    name = known[0]
    value = object_value(update[name])
    projection["kind"] = name.upper()
    if name == "business_connection":
        projection.update(connection_fields(value))
        return projection
    connection = identifier(value.get("business_connection_id"))
    projection["external_connection_id"] = connection
    chat = object_value(value.get("chat"))
    chat_id = numeric_id(chat.get("id"))
    if name == "deleted_business_messages":
        ids = value.get("message_ids")
        if type(ids) is not list or not 1 <= len(ids) <= 100:
            raise invalid()
        projection["deleted_chat_id"] = chat_id
        projection["deleted_message_ids"] = [numeric_id(item) for item in ids]
        return projection
    message_id = numeric_id(value.get("message_id"))
    occurred_at = date_value(value.get("date"))
    sender_id = None
    sender_bot = False
    if "from" in value:
        sender = object_value(value["from"])
        sender_id = numeric_id(sender.get("id"))
        sender_bot = boolean(sender.get("is_bot"))
    if "sender_business_bot" in value:
        projection["sender_business_bot_id"] = numeric_id(
            object_value(value["sender_business_bot"]).get("id")
        )
    if "text" in value and ("photo" in value or "caption" in value):
        raise invalid()
    content = scalar_text(value["text"], 4096, 16384) if "text" in value else None
    image = None
    if "photo" in value:
        photos = value["photo"]
        if type(photos) is not list or not 1 <= len(photos) <= 100 or "document" in value:
            raise invalid()
        sizes = []
        for raw in photos:
            photo = object_value(raw)
            width, height = photo.get("width"), photo.get("height")
            if (
                type(width) is not int
                or type(height) is not int
                or not 0 < width <= 2147483647
                or not 0 < height <= 2147483647
            ):
                raise invalid()
            fid = identifier(photo.get("file_id"), image=True)
            sizes.append((width * height, width, height, fid))
        image = max(sizes)[3]
        content = scalar_text(value["caption"], 4096, 16384) if "caption" in value else None
    elif "caption" in value:
        scalar_text(value["caption"], 4096, 16384)
    unsupported = (
        chat.get("type") != "private"
        or sender_id != chat_id
        or sender_bot
        or any(
            key in value
            for key in (
                "document",
                "video",
                "sticker",
                "animation",
                "audio",
                "voice",
                "sender_chat",
                "guest_bot_caller_user",
                "guest_bot_caller_chat",
            )
        )
        or (not content and image is None)
    )
    kind = EventKind.UNSUPPORTED if unsupported else EventKind.CLIENT_MESSAGE
    if name == "edited_business_message":
        kind = EventKind.MESSAGE_EDITED
    event = NormalizedEventV1(
        "TELEGRAM",
        bot_identity,
        event_id,
        kind,
        connection,
        chat_id,
        message_id,
        sender_id,
        occurred_at,
        content,
        image,
        identifier(value["media_group_id"]) if "media_group_id" in value else None,
    )
    projection["event"] = event.values()
    return projection


def update_fingerprint(bot_identity: str, projection: dict[str, Any]) -> str:
    event = projection["event"]
    event_hash = None
    if event is not None:
        raw = b"asm:m2:normalized_event:v1\n"
        for key in NormalizedEventV1.__dataclass_fields__:
            value = event[key]
            raw += _part(value)
        event_hash = hashlib.sha256(raw).hexdigest()
    values = [
        bot_identity,
        *(
            projection[k]
            for k in (
                "update_id",
                "kind",
                "external_connection_id",
                "owner_user_id",
                "sender_business_bot_id",
            )
        ),
        *(
            str(projection[k]).lower() if projection[k] is not None else None
            for k in ("is_enabled", "can_reply")
        ),
        projection["lifecycle_date"],
        event_hash,
        projection["deleted_chat_id"],
        ",".join(projection["deleted_message_ids"])
        if projection["deleted_message_ids"] is not None
        else None,
    ]
    return hashlib.sha256(
        b"asm:m2:telegram_update:v1\n" + b"".join(_part(v) for v in values)
    ).hexdigest()


def _part(value: str | None) -> bytes:
    if value is None:
        return b"-1:\n"
    raw = value.encode("utf-8")
    return str(len(raw)).encode("ascii") + b":" + raw + b"\n"
