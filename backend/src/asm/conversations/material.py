"""Closed material projections. Historical messages and V1 snapshots stay separate."""

import json
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from asm.billing.models import StrictModel
from asm.billing.validation import CanonicalUUID, PositiveDecimal, Timestamp
from asm.messaging.errors import MessagingError
from asm.messaging.models import identifier, scalar_text


class TextContent(StrictModel):
    kind: Literal["TEXT"]
    text: str = Field(min_length=1, max_length=4096, repr=False)

    @field_validator("text")
    @classmethod
    def bounded(cls, value: str) -> str:
        try:
            return scalar_text(value, 4096, 16384)
        except MessagingError:
            raise ValueError("Invalid content") from None


class PhotoContent(StrictModel):
    kind: Literal["PHOTO"]
    caption: str | None = Field(max_length=4096, repr=False)
    selected_file_id: str = Field(repr=False)
    selected_unique_id: str | None = Field(repr=False)

    @field_validator("selected_file_id", "selected_unique_id")
    @classmethod
    def opaque(cls, value: str | None) -> str | None:
        try:
            return identifier(value, image=True) if value is not None else None
        except MessagingError:
            raise ValueError("Invalid image identity") from None

    @field_validator("caption")
    @classmethod
    def bounded(cls, value: str | None) -> str | None:
        return TextContent.bounded(value) if value is not None else None


class UnsupportedContent(StrictModel):
    kind: Literal["UNSUPPORTED"]
    reason: Literal["UNSUPPORTED_MEDIA", "EMPTY_CONTENT"]


Content = Annotated[TextContent | PhotoContent | UnsupportedContent, Field(discriminator="kind")]


class Origin(StrictModel):
    sender_id: PositiveDecimal | None
    sender_is_bot: Literal["TRUE", "FALSE", "MISSING"]
    sender_business_bot_id: PositiveDecimal | None
    offline: Literal["TRUE", "MISSING"]

    @model_validator(mode="after")
    def sender(self) -> Self:
        if (self.sender_id is None) != (self.sender_is_bot == "MISSING"):
            raise ValueError("Invalid sender")
        return self


class TelegramProjectionV2(StrictModel):
    codec: Literal["TELEGRAM_PROVENANCE_V2"]
    bot: PositiveDecimal
    update_id: PositiveDecimal
    legacy_v1: dict[str, Any] = Field(repr=False)
    discriminator: Literal["NEW", "EDIT", "DELETE", "LIFECYCLE", "UNSUPPORTED"]
    connection: str | None = Field(repr=False)
    chat_id: PositiveDecimal | None = Field(repr=False)
    message_id: PositiveDecimal | None = Field(repr=False)
    sent_at: Timestamp | None
    edited_at: Timestamp | None
    chat_type: Literal["PRIVATE", "UNSUPPORTED"] | None
    origin: Origin | None
    content: Content | None
    unsupported_reason: Literal[
        "NONE",
        "NONPRIVATE",
        "BOT_SENDER",
        "SENDER_CHAT",
        "GUEST",
        "UNSUPPORTED_MEDIA",
        "EMPTY_CONTENT",
        "AMBIGUOUS_SENDER",
        "NONBUSINESS",
    ]

    @model_validator(mode="after")
    def closed(self) -> Self:
        p = self.legacy_v1
        fields = {
            "update_id",
            "kind",
            "external_connection_id",
            "event",
            "owner_user_id",
            "deleted_message_ids",
            "deleted_chat_id",
            "sender_business_bot_id",
            "is_enabled",
            "can_reply",
            "lifecycle_date",
        }
        kinds = {
            "NEW": "BUSINESS_MESSAGE",
            "EDIT": "EDITED_BUSINESS_MESSAGE",
            "DELETE": "DELETED_BUSINESS_MESSAGES",
            "LIFECYCLE": "BUSINESS_CONNECTION",
            "UNSUPPORTED": "UNSUPPORTED",
        }
        if (
            set(p) != fields
            or p["update_id"] != self.update_id
            or p["kind"] != kinds[self.discriminator]
            or p["external_connection_id"] != self.connection
        ):
            raise ValueError("Invalid legacy envelope")
        if self.discriminator != "UNSUPPORTED":
            try:
                identifier(self.connection)
            except MessagingError:
                raise ValueError("Invalid connection") from None
        elif self.connection is not None:
            raise ValueError("Invalid nonbusiness connection")
        for key in ("owner_user_id", "is_enabled", "can_reply", "lifecycle_date"):
            if (p[key] is not None) != (self.discriminator == "LIFECYCLE"):
                raise ValueError("Invalid lifecycle field")
        if self.discriminator == "LIFECYCLE":
            from pydantic import TypeAdapter

            TypeAdapter(PositiveDecimal).validate_python(p["owner_user_id"], strict=True)
            TypeAdapter(Timestamp).validate_python(p["lifecycle_date"], strict=True)
            if type(p["is_enabled"]) is not bool or type(p["can_reply"]) is not bool:
                raise ValueError("Invalid lifecycle flags")
        if self.discriminator == "DELETE":
            ids = p["deleted_message_ids"]
            if (
                type(ids) is not list
                or not 1 <= len(ids) <= 100
                or p["deleted_chat_id"] != self.chat_id
                or self.chat_id is None
            ):
                raise ValueError("Invalid delete")
            from pydantic import TypeAdapter

            TypeAdapter(list[PositiveDecimal]).validate_python(ids, strict=True)
        elif p["deleted_message_ids"] is not None or p["deleted_chat_id"] is not None:
            raise ValueError("Invalid delete fields")
        if self.discriminator in ("NEW", "EDIT"):
            e = p["event"]
            if (
                not isinstance(e, dict)
                or self.origin is None
                or self.content is None
                or self.chat_type is None
                or self.chat_id is None
                or self.message_id is None
                or self.sent_at is None
            ):
                raise ValueError("Missing message")
            from datetime import datetime

            from asm.messaging.models import EventKind, NormalizedEventV1

            try:
                event = NormalizedEventV1(
                    **(
                        e
                        | {
                            "kind": EventKind(e["kind"]),
                            "occurred_at": datetime.fromisoformat(e["occurred_at"]),
                        }
                    )
                )
            except (TypeError, KeyError, ValueError, MessagingError):
                raise ValueError("Invalid legacy message") from None
            if event.values() != e or (
                e["provider"],
                e["bot_identity"],
                e["event_id"],
                e["external_connection_id"],
                e["chat_id"],
                e["message_id"],
                e["occurred_at"],
                e["sender_id"],
                p["sender_business_bot_id"],
            ) != (
                "TELEGRAM",
                self.bot,
                self.update_id,
                self.connection,
                self.chat_id,
                self.message_id,
                self.sent_at,
                self.origin.sender_id,
                self.origin.sender_business_bot_id,
            ):
                raise ValueError("Legacy equality")
            expected_kind = (
                "MESSAGE_EDITED"
                if self.discriminator == "EDIT"
                else ("CLIENT_MESSAGE" if self.unsupported_reason == "NONE" else "UNSUPPORTED")
            )
            if e["kind"] != expected_kind:
                raise ValueError("Invalid legacy kind")
            if isinstance(self.content, TextContent) and (
                self.content.text != e["text"] or e["image_file_id"] is not None
            ):
                raise ValueError("Text equality")
            if isinstance(self.content, PhotoContent) and (
                self.content.caption != e["text"]
                or self.content.selected_file_id != e["image_file_id"]
            ):
                raise ValueError("Photo equality")
            if self.unsupported_reason == "NONBUSINESS":
                raise ValueError("Invalid reason")
            if self.chat_type == "UNSUPPORTED" and self.unsupported_reason != "NONPRIVATE":
                raise ValueError("Invalid chat reason")
            if (
                self.chat_type == "PRIVATE"
                and self.origin.sender_is_bot == "TRUE"
                and self.unsupported_reason != "BOT_SENDER"
            ):
                raise ValueError("Invalid bot reason")
            if self.unsupported_reason == "NONE" and (
                self.origin.sender_id != self.chat_id
                or self.origin.sender_is_bot != "FALSE"
                or isinstance(self.content, UnsupportedContent)
            ):
                raise ValueError("Invalid inbound eligibility")
        elif (
            p["event"] is not None
            or p["sender_business_bot_id"] is not None
            or any(
                x is not None
                for x in (
                    self.message_id,
                    self.sent_at,
                    self.edited_at,
                    self.chat_type,
                    self.origin,
                    self.content,
                )
            )
            or (self.discriminator != "DELETE" and self.chat_id is not None)
            or self.unsupported_reason
            != ("NONBUSINESS" if self.discriminator == "UNSUPPORTED" else "NONE")
        ):
            raise ValueError("Invalid nonmessage shape")
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 65536:
            raise ValueError("Projection too large")
        return self


class MessageCurrent(StrictModel):
    schema_version: Literal[1]
    state: Literal["VISIBLE", "DELETED", "ORDER_UNCERTAIN", "UNSUPPORTED_CONTENT"]
    content_type: Literal["TEXT", "PHOTO"] | None
    text: str | None = Field(max_length=4096, repr=False)
    image_availability: Literal[
        "NOT_APPLICABLE",
        "ORIGINAL_PENDING",
        "ORIGINAL_READY",
        "ORIGINAL_FAILED",
        "ORIGINAL_NOT_FETCHED",
        "MEDIA_REPLACED_UNAVAILABLE",
        "HIDDEN",
    ]
    changed: bool

    @field_validator("schema_version", mode="before")
    @classmethod
    def version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid current version")
        return value

    @field_validator("text")
    @classmethod
    def bounded(cls, value: str | None) -> str | None:
        return TextContent.bounded(value) if value is not None else None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.state != "VISIBLE":
            valid = (
                self.content_type is None
                and self.text is None
                and self.image_availability == "HIDDEN"
                and self.changed
            )
        elif self.content_type == "TEXT":
            valid = bool(self.text) and self.image_availability == "NOT_APPLICABLE"
        else:
            valid = self.content_type == "PHOTO" and self.image_availability in (
                "ORIGINAL_PENDING",
                "ORIGINAL_READY",
                "ORIGINAL_FAILED",
                "ORIGINAL_NOT_FETCHED",
                "MEDIA_REPLACED_UNAVAILABLE",
            )
            if self.image_availability in ("ORIGINAL_NOT_FETCHED", "MEDIA_REPLACED_UNAVAILABLE"):
                valid = valid and self.changed
        if not valid:
            raise ValueError("Invalid current shape")
        return self


class TargetResult(StrictModel):
    ordinal: int = Field(ge=1, le=100)
    code: Literal[
        "APPLIED",
        "NOOP_CONTENT",
        "STALE_EDIT",
        "ALREADY_DELETED",
        "ALREADY_UNCERTAIN",
        "DEFERRED_TARGET",
        "IDENTITY_CONFLICT",
    ]
    target_id: CanonicalUUID | None
    message_id: CanonicalUUID | None
    effect_id: CanonicalUUID | None
    audit_event_id: CanonicalUUID | None
    previous_version: PositiveDecimal | None
    accepted_version: PositiveDecimal | None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.code == "APPLIED":
            valid = all(
                x is not None
                for x in (
                    self.target_id,
                    self.message_id,
                    self.effect_id,
                    self.audit_event_id,
                    self.previous_version,
                    self.accepted_version,
                )
            ) and (int(self.accepted_version or "0") == int(self.previous_version or "0") + 1)
        elif self.code in ("DEFERRED_TARGET", "IDENTITY_CONFLICT"):
            valid = (self.target_id is not None) == (self.code == "DEFERRED_TARGET") and all(
                x is None
                for x in (
                    self.message_id,
                    self.effect_id,
                    self.audit_event_id,
                    self.previous_version,
                    self.accepted_version,
                )
            )
        else:
            valid = (
                self.target_id is not None
                and self.message_id is not None
                and self.effect_id is None
                and self.audit_event_id is None
                and self.previous_version is not None
                and self.previous_version == self.accepted_version
            )
        if not valid:
            raise ValueError("Invalid target result")
        return self
