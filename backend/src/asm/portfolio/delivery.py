"""Exact private original bytes before a separate durable photo admission."""

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from asm.files.models import ImageManifest
from asm.files.validation import ImageValidator
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import scalar_text
from asm.messaging.results import AISendPermit, JobClaim, Result, TerminalRejection

if TYPE_CHECKING:
    from asm.messaging.database import MessagingDatabase
    from asm.telegram.database import TelegramProbe

MAX_PHOTO_BYTES = 10_000_000


def photo_manifest(manifest: ImageManifest) -> ImageManifest:
    """Telegram's subset in addition to the unchanged private image validator."""
    manifest = ImageManifest.model_validate_json(manifest.model_dump_json())
    if (
        manifest.mime_type not in {"image/jpeg", "image/png"}
        or manifest.size_bytes > MAX_PHOTO_BYTES
        or manifest.width + manifest.height > 10000
        or max(manifest.width, manifest.height) > 20 * min(manifest.width, manifest.height)
    ):
        raise MessagingError(Code.INVALID_INPUT)
    return manifest


def photo_caption(value: object) -> str:
    value = scalar_text(value, 1024, 4096)
    if not value.strip():
        raise MessagingError(Code.INVALID_INPUT)
    return value


class PortfolioPhotoReadPermit(Result):
    code: Literal["MEDIA_READ_PERMITTED"]
    job_id: UUID
    claim_token: UUID = Field(repr=False)
    workspace_id: UUID
    connection_id: UUID
    conversation_id: UUID
    run_id: UUID
    intent_id: UUID
    outbox_id: UUID
    asset_id: UUID
    asset_version_id: UUID
    storage_key: str = Field(repr=False)
    manifest: ImageManifest
    read_ticket: UUID = Field(repr=False)

    @model_validator(mode="after")
    def exact_private_source(self) -> Self:
        photo_manifest(self.manifest)
        prefix = (
            f"workspaces/{self.workspace_id}/portfolio/{self.asset_id}"
            f"/versions/{self.asset_version_id}/uploads/"
        )
        if not self.storage_key.startswith(prefix):
            raise ValueError("PORTFOLIO_DELIVERY_SOURCE_INVALID")
        suffix = self.storage_key[len(prefix) :]
        if str(UUID(suffix)) != suffix:
            raise ValueError("PORTFOLIO_DELIVERY_SOURCE_INVALID")
        return self


class PortfolioPhotoSendPermit(AISendPermit):
    """Only final dispatch admission; a READ or RuntimeReceipt is insufficient."""

    portfolio_photo: Literal[True]
    provider_session_id: None = None
    intent_id: UUID
    asset_version_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest: ImageManifest

    @field_validator("text")
    @classmethod
    def caption(cls, value: str) -> str:
        return photo_caption(value)

    @model_validator(mode="after")
    def exact_source(self) -> Self:
        photo_manifest(self.manifest)
        if self.source_sha256 != self.manifest.sha256:
            raise ValueError("PORTFOLIO_DELIVERY_SOURCE_INVALID")
        return self


def check_photo_payload(permit: PortfolioPhotoSendPermit, data: bytes) -> None:
    if (
        type(permit) is not PortfolioPhotoSendPermit
        or type(data) is not bytes
        or len(data) != permit.manifest.size_bytes
        or hashlib.sha256(data).hexdigest() != permit.source_sha256
    ):
        raise MessagingError(Code.INVALID_INPUT)
    photo_manifest(permit.manifest)
    photo_caption(permit.text)


class PrivatePhotoStorage(Protocol):
    async def get(self, storage_key: str) -> bytes: ...


class PortfolioDelivery:
    """No storage URL, implicit source replacement, sender or independent queue."""

    def __init__(self, database: "MessagingDatabase", storage: PrivatePhotoStorage):
        self.database, self.storage = database, storage
        self.validator = ImageValidator()

    async def read(
        self, claim: JobClaim
    ) -> tuple[PortfolioPhotoReadPermit, bytes] | TerminalRejection:
        if claim.kind != "SEND_AI_PHOTO":
            raise MessagingError(Code.NOT_ALLOWED)
        async with self.database.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit._execute("SELECT platform.portfolio_delivery_read(:job,:token)")
        if raw.get("code") != "MEDIA_READ_PERMITTED":
            return TerminalRejection.model_validate(raw)
        permit = PortfolioPhotoReadPermit.model_validate(raw)
        if (
            permit.job_id,
            permit.claim_token,
            permit.workspace_id,
            permit.connection_id,
            permit.outbox_id,
        ) != (
            claim.job_id,
            claim.claim_token,
            claim.workspace_id,
            claim.connection_id,
            claim.outbox_id,
        ):
            raise MessagingError(Code.NOT_ALLOWED)
        # This transaction has committed. S3's own transport enforces that no
        # worker/owner transaction is held throughout external byte I/O.
        async with asyncio.timeout(15):
            content = await self.storage.get(permit.storage_key)
            if type(content) is not bytes or not 0 < len(content) <= MAX_PHOTO_BYTES:
                raise MessagingError(Code.INVALID_INPUT)
            manifest = await self.validator.validate(content)
            photo_manifest(manifest)
        if manifest != permit.manifest:
            raise MessagingError(Code.INVALID_INPUT)
        await self.database.checkpoint("photo_after_read")
        return permit, content

    async def begin(
        self,
        claim: JobClaim,
        media: PortfolioPhotoReadPermit,
        probe: "TelegramProbe | None",
        observation: dict[str, object] | None,
    ) -> PortfolioPhotoSendPermit | TerminalRejection:
        async with self.database.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit._execute(
                "SELECT platform.portfolio_delivery_begin(:job,:token,:ticket,:generation,:version,CAST(:observation AS jsonb),:sha256)",
                {
                    "ticket": media.read_ticket,
                    "generation": probe.generation if probe else None,
                    "version": probe.observation_version if probe else None,
                    "observation": json.dumps(observation) if observation is not None else None,
                    "sha256": media.manifest.sha256,
                },
            )
            result = (
                PortfolioPhotoSendPermit.model_validate(raw)
                if raw["code"] == "PERMITTED"
                else TerminalRejection.model_validate(raw)
            )
            if isinstance(result, PortfolioPhotoSendPermit) and (
                result.job_id,
                result.claim_token,
                result.workspace_id,
                result.connection_id,
                result.intent_id,
                result.asset_version_id,
                result.manifest,
            ) != (
                claim.job_id,
                claim.claim_token,
                claim.workspace_id,
                claim.connection_id,
                media.intent_id,
                media.asset_version_id,
                media.manifest,
            ):
                raise MessagingError(Code.NOT_ALLOWED)
            await self.database.checkpoint("start_before_commit")
        # A lost ACK here yields no permit to the caller. Durable DISPATCHING
        # recovery owns UNKNOWN, and this method never repeats the admission.
        await self.database.checkpoint("start_after_commit")
        return result

    async def close(self) -> None:
        await self.validator.close()
