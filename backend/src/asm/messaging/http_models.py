"""Strict owner wire projections; provider and durable-kernel references stay private."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from asm.billing.models import CommonCode, StrictModel
from asm.billing.validation import CanonicalUUID, PositiveDecimal, Timestamp
from asm.messaging.errors import MessagingError
from asm.messaging.models import manual_text

Endpoint = Literal["CHANNEL_CONNECTIONS", "CONVERSATIONS", "MESSAGES"]
FileError = Literal[
    "INVALID_INPUT", "DEPENDENCY_TIMEOUT", "DEPENDENCY_UNAVAILABLE", "RETRY_EXHAUSTED"
]
DeliveryError = Literal[
    "INVALID_INPUT",
    "NOT_ALLOWED",
    "RETRY_EXHAUSTED",
    "DEPENDENCY_TIMEOUT",
    "DEPENDENCY_UNAVAILABLE",
    "UNKNOWN_EXTERNAL_RESULT",
]


class MessagingErrorDetail(StrictModel):
    code: CommonCode | Literal["NOT_ALLOWED"]


class MessagingErrorResponse(StrictModel):
    error: MessagingErrorDetail


class ManualTextRequest(StrictModel):
    text: str = Field(
        min_length=1,
        max_length=4096,
        repr=False,
        description="Exact 1..4096 Unicode scalars, <=16384 UTF-8 bytes; no NUL, surrogates or whitespace-only text. No trim or normalization.",
    )

    @field_validator("text")
    @classmethod
    def exact_text(cls, value: str) -> str:
        try:
            return manual_text(value)
        except MessagingError:
            raise ValueError("Invalid text") from None


class ReadGrantRequest(StrictModel):
    pass


class ConnectionResponse(StrictModel):
    connection_id: CanonicalUUID
    business_id: CanonicalUUID
    provider: Literal["CONTROLLED", "TELEGRAM"]
    state: Literal["AVAILABLE", "DISABLED", "RIGHTS_MISSING", "UNVERIFIED", "UNAVAILABLE"]
    observed_at: Timestamp | None
    created_at: Timestamp
    version: PositiveDecimal

    @model_validator(mode="after")
    def controlled_observation(self) -> Self:
        if self.provider == "CONTROLLED" and (
            self.observed_at is not None or self.state not in ("AVAILABLE", "DISABLED")
        ):
            raise ValueError("Invalid controlled state")
        return self


class ConversationResponse(StrictModel):
    conversation_id: CanonicalUUID
    connection_id: CanonicalUUID
    business_id: CanonicalUUID
    client_id: CanonicalUUID
    created_at: Timestamp
    version: PositiveDecimal
    reply_window_expires_at: Timestamp | None


class FileManifestResponse(StrictModel):
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: PositiveDecimal
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if int(self.size_bytes) > 10_485_760 or self.width * self.height > 20_000_000:
            raise ValueError("Invalid image bounds")
        return self


class FileResponse(StrictModel):
    file_id: CanonicalUUID
    status: Literal["PENDING", "READY", "FAILED"]
    error_code: FileError | None
    manifest: FileManifestResponse | None

    @model_validator(mode="after")
    def state(self) -> Self:
        if (self.status == "READY") != (self.manifest is not None) or (
            (self.status == "FAILED") != (self.error_code is not None)
        ):
            raise ValueError("Invalid file state")
        return self


class DeliveryResponse(StrictModel):
    status: Literal["PENDING", "DISPATCHING", "SENT", "FAILED", "UNKNOWN"]
    error_code: DeliveryError | None
    completed_at: Timestamp | None
    version: PositiveDecimal

    @model_validator(mode="after")
    def state(self) -> Self:
        if (self.status in ("SENT", "FAILED", "UNKNOWN")) != (self.completed_at is not None):
            raise ValueError("Invalid delivery completion")
        if self.status == "SENT" and self.error_code is not None:
            raise ValueError("Invalid sent error")
        if self.status in ("FAILED", "UNKNOWN") and self.error_code is None:
            raise ValueError("Missing delivery error")
        return self


class MessageResponse(StrictModel):
    message_id: CanonicalUUID
    conversation_id: CanonicalUUID
    direction: Literal["INBOUND", "OUTBOUND"]
    content_type: Literal["TEXT", "IMAGE_REFERENCE"]
    text: str | None = Field(max_length=4096, repr=False)
    occurred_at: Timestamp
    created_at: Timestamp
    version: PositiveDecimal
    file: FileResponse | None
    delivery: DeliveryResponse | None

    @model_validator(mode="after")
    def relations(self) -> Self:
        if (self.content_type == "IMAGE_REFERENCE") != (self.file is not None):
            raise ValueError("Invalid file relation")
        if (self.direction == "OUTBOUND") != (self.delivery is not None):
            raise ValueError("Invalid delivery relation")
        return self


class SendResponse(StrictModel):
    workspace_id: CanonicalUUID
    receipt_id: CanonicalUUID
    message_id: CanonicalUUID
    accepted_at: Timestamp
    outcome: Literal["ACCEPTED", "REPLAY"]


class ReadGrantResponse(StrictModel):
    url: str = Field(min_length=1, repr=False)
    expires_at: Timestamp


class ConnectionsPage(StrictModel):
    items: list[ConnectionResponse] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=1024)


class ConversationsPage(StrictModel):
    items: list[ConversationResponse] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=1024)


class MessagesPage(StrictModel):
    items: list[MessageResponse] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=1024)


class CursorFields(StrictModel):
    v: Literal[1]
    endpoint: Endpoint
    workspace_id: CanonicalUUID
    direction: Literal["DESC"]
    created_at: Timestamp
    id: CanonicalUUID

    @field_validator("v", mode="before")
    @classmethod
    def version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid cursor version")
        return value


class CollectionCursor(CursorFields):
    endpoint: Literal["CHANNEL_CONNECTIONS", "CONVERSATIONS"]


class MessagesCursor(CursorFields):
    endpoint: Literal["MESSAGES"]
    conversation_id: CanonicalUUID
