"""Internal DB-issued file permits; identifiers never independently grant access."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from asm.messaging.results import Result


class ImageManifest(Result):
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(strict=True, gt=0, le=10_485_760)
    sha256: str = Field(pattern="^[0-9a-f]{64}$")
    width: int = Field(strict=True, gt=0, le=8192)
    height: int = Field(strict=True, gt=0, le=8192)

    @model_validator(mode="after")
    def bounded_pixels(self) -> Self:
        if self.width * self.height > 20_000_000:
            raise ValueError("IMAGE_LIMIT")
        return self


class FetchPermit(Result):
    job_id: UUID
    claim_token: UUID = Field(repr=False)
    workspace_id: UUID
    connection_id: UUID
    file_id: UUID
    message_id: UUID
    conversation_id: UUID
    provider: Literal["CONTROLLED", "TELEGRAM"]
    bot_identity: str = Field(repr=False)
    external_connection_id: str = Field(repr=False)
    image_file_id: str = Field(repr=False)


class UploadPermit(Result):
    intent_id: UUID
    job_id: UUID
    claim_token: UUID = Field(repr=False)
    workspace_id: UUID
    file_id: UUID
    storage_key: str = Field(repr=False)
    manifest: ImageManifest


class FileFinalizeResult(Result):
    code: Literal["FINALIZED", "ALREADY_FINALIZED"]
    status: Literal["READY"]
    job_id: UUID
    file_id: UUID
    intent_id: UUID


class CleanupClaim(Result):
    intent_id: UUID
    claim_token: UUID = Field(repr=False)
    workspace_id: UUID
    file_id: UUID
    storage_key: str = Field(repr=False)
    lease_until: datetime


class CleanupResult(Result):
    code: Literal["CHECKED", "RETRY_SCHEDULED"]
    intent_id: UUID
    next_check_at: datetime


class ReadManifest(Result):
    workspace_id: UUID
    conversation_id: UUID
    message_id: UUID
    file_id: UUID
    storage_key: str = Field(repr=False)
    manifest: ImageManifest
