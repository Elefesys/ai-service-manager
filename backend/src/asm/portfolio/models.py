"""Closed owner wire DTOs and private DB-issued upload/analysis bindings."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, Field, ValidationInfo, field_validator, model_validator

from asm.ai.portfolio import MediaPin, PortfolioPin, PortfolioProjection
from asm.ai.vision_contracts import VisionResult
from asm.auth.models import AuthCode
from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal
from asm.configuration.models import ConfigurationModel, Identifier, VersionedModel
from asm.files.models import ImageManifest
from asm.portfolio.errors import PortfolioCode
from asm.portfolio.validation import canonical_text

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", max_length=64)]
Description = Annotated[
    str, Field(min_length=1, max_length=512), AfterValidator(lambda v: canonical_text(v, 512))
]
Origin = Literal["MY_WORK", "INSPIRATION"]
UploadState = Literal[
    "INIT",
    "RECEIVING",
    "PUT_RESERVED",
    "STORED",
    "UNKNOWN",
    "ERROR",
    "READY",
    "ABANDONED",
    "PURGE_PENDING",
    "PURGED",
]
BuildState = Literal["PLANNED", "BUILDING", "READY", "ERROR", "UNKNOWN"]
Operation = Literal[
    "PORTFOLIO_UPLOAD_CREATE",
    "PORTFOLIO_UPLOAD_FINALIZE",
    "PORTFOLIO_UPLOAD_ABANDON",
    "PORTFOLIO_SAVE",
    "PORTFOLIO_CONFIRM",
    "PORTFOLIO_REVOKE",
    "PORTFOLIO_DELETE",
    "PORTFOLIO_BUILD_CREATE",
    "PORTFOLIO_PUBLISH",
    "PORTFOLIO_ROLLBACK",
]


class EmptyRequest(VersionedModel):
    pass


class InitUpload(VersionedModel):
    asset_id: CanonicalUUID | None
    expected_asset_version: LimitDecimal
    origin: Origin
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0, le=10_485_760)
    sha256: Digest

    @model_validator(mode="after")
    def new_or_existing(self) -> Self:
        if (self.asset_id is None) != (self.expected_asset_version == "0"):
            raise ValueError("ASSET_VERSION_REQUIRED")
        return self


class FinishUpload(VersionedModel):
    expected_asset_version: PositiveDecimal


class Attributes(ConfigurationModel):
    subject: str | None = Field(max_length=80)
    styles: list[str] = Field(max_length=4)
    placement: str | None = Field(max_length=40)

    @field_validator("subject", "placement")
    @classmethod
    def bounded_scalar(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None:
            canonical_text(value, 80 if info.field_name == "subject" else 40)
        return value

    @field_validator("styles")
    @classmethod
    def bounded_styles(cls, value: list[str]) -> list[str]:
        for item in value:
            canonical_text(item, 40)
        if len(set(value)) != len(value):
            raise ValueError("DUPLICATE_STYLE")
        return value


class SaveItem(VersionedModel):
    item_id: CanonicalUUID | None
    expected_item_version: LimitDecimal
    asset_id: CanonicalUUID
    description: Description
    attributes: Attributes
    service_id: Identifier | None
    analysis_id: CanonicalUUID | None

    @model_validator(mode="after")
    def new_or_existing(self) -> Self:
        if (self.item_id is None) != (self.expected_item_version == "0"):
            raise ValueError("ITEM_VERSION_REQUIRED")
        return self


class ConfirmItem(VersionedModel):
    expected_item_version: PositiveDecimal
    revision_id: CanonicalUUID
    canonical_sha256: Digest
    confirm_my_work: Literal[True]
    show_permission: Literal[True]

    @field_validator("confirm_my_work", "show_permission", mode="before")
    @classmethod
    def explicit_boolean(cls, value: object) -> object:
        if value is not True:
            raise ValueError("EXPLICIT_CONFIRMATION_REQUIRED")
        return value


class RevokeItem(VersionedModel):
    expected_item_version: PositiveDecimal
    expected_activation_version: LimitDecimal


class DeleteAsset(VersionedModel):
    expected_asset_version: PositiveDecimal
    expected_activation_version: LimitDecimal


class CreateBuild(VersionedModel):
    expected_items_hash: Digest
    revision_ids: list[CanonicalUUID] = Field(max_length=8)

    @field_validator("revision_ids")
    @classmethod
    def unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("UNIQUE_REVISIONS_REQUIRED")
        return value


class PublishPortfolio(VersionedModel):
    expected_draft_version: PositiveDecimal
    expected_activation_version: LimitDecimal
    knowledge_build_id: CanonicalUUID | None
    expected_knowledge_build_version: PositiveDecimal | None
    portfolio_build_id: CanonicalUUID
    expected_portfolio_build_version: PositiveDecimal

    @model_validator(mode="after")
    def paired(self) -> Self:
        if (self.knowledge_build_id is None) != (self.expected_knowledge_build_version is None):
            raise ValueError("KNOWLEDGE_BUILD_VERSION_REQUIRED")
        return self


class RollbackPortfolio(VersionedModel):
    expected_activation_version: LimitDecimal
    release_id: CanonicalUUID


CommandRequest = (
    InitUpload
    | FinishUpload
    | SaveItem
    | ConfirmItem
    | RevokeItem
    | DeleteAsset
    | CreateBuild
    | PublishPortfolio
    | RollbackPortfolio
)


class PublicAnalysis(ConfigurationModel):
    analysis_id: CanonicalUUID
    analysis_sha256: Digest | None
    source_kind: Literal["OWNER_ASSET", "CLIENT_REFERENCE"]
    asset_version_id: CanonicalUUID | None
    source_sha256: Digest
    derivative_sha256: Digest | None
    vision_profile: Literal["polza_openai_gpt4omini_pixels_v1"]
    preprocessing: Literal["exif_contain_white_rgb_png256_strip_v1"]
    schema_revision: Literal["vision_result_v1"]
    state: Literal["RESERVED", "SUCCESS", "ERROR", "UNKNOWN"]
    applied: bool
    result: VisionResult | None


class DeclaredManifest(ConfigurationModel):
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0, le=10_485_760)
    sha256: Digest
    width: int | None = Field(ge=1, le=8192)
    height: int | None = Field(ge=1, le=8192)

    def decoded(self) -> ImageManifest:
        return ImageManifest.model_validate(self.model_dump())


class PublicVersion(ConfigurationModel):
    version_id: CanonicalUUID
    upload_id: CanonicalUUID
    state: UploadState
    manifest: DeclaredManifest
    expires_at: datetime


class PublicAsset(ConfigurationModel):
    asset_id: CanonicalUUID
    version: PositiveDecimal
    origin: Origin
    state: Literal["DRAFT", "READY"]
    epoch: LimitDecimal
    accepted_version_id: CanonicalUUID | None
    pending_version_id: CanonicalUUID | None
    versions: list[PublicVersion] = Field(max_length=2)
    analysis: PublicAnalysis | None


class PublicRevision(ConfigurationModel):
    revision_id: CanonicalUUID
    revision_no: PositiveDecimal
    asset_version_id: CanonicalUUID
    source_sha256: Digest
    description: Description
    attributes: Attributes
    service_id: Identifier | None
    analysis_id: CanonicalUUID | None
    canonical_sha256: Digest
    confirmed: bool


class PublicItem(ConfigurationModel):
    item_id: CanonicalUUID
    asset_id: CanonicalUUID
    version: PositiveDecimal
    epoch: LimitDecimal
    state: Literal["DRAFT", "CONFIRMED", "REVOKED"]
    show_permission: bool
    confirmed_revision_id: CanonicalUUID | None
    head: PublicRevision


class BuildSource(ConfigurationModel):
    item_id: CanonicalUUID
    revision_id: CanonicalUUID
    canonical_sha256: Digest
    asset_id: CanonicalUUID
    asset_version_id: CanonicalUUID
    source_sha256: Digest
    asset_epoch: LimitDecimal
    confirmed_epoch: LimitDecimal


class PublicBuild(ConfigurationModel):
    build_id: CanonicalUUID
    version: PositiveDecimal
    state: BuildState
    input_count: int = Field(ge=0, le=8)
    manifest_hash: Digest
    manifest: list[BuildSource] = Field(max_length=8)
    error_code: str | None = Field(max_length=64)
    eligible: bool


class PublicRelease(ConfigurationModel):
    release_id: CanonicalUUID
    portfolio_build_id: CanonicalUUID | None
    knowledge_build_id: CanonicalUUID | None
    published_at: datetime
    eligible: bool | None


class PendingPurge(ConfigurationModel):
    asset_id: CanonicalUUID
    version_id: CanonicalUUID
    state: Literal["PURGE_PENDING"]
    outcome: Literal["DEPENDENCY_TIMEOUT", "DEPENDENCY_UNAVAILABLE"] | None
    deadline: datetime | None


class PortfolioProjectionState(VersionedModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    items_hash: Digest
    assets: list[PublicAsset] = Field(max_length=8)
    items: list[PublicItem] = Field(max_length=8)
    builds: list[PublicBuild] = Field(max_length=16)
    releases: list[PublicRelease] = Field(max_length=16)
    pending_purges: list[PendingPurge] = Field(max_length=8)
    purges_omitted: int = Field(ge=0)
    active_release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    draft_version: LimitDecimal
    active_portfolio_build_id: CanonicalUUID | None
    active_knowledge_build_id: CanonicalUUID | None


class OwnerState(PortfolioProjectionState):
    vision_mode: Literal["CONTROLLED", "DISABLED"]
    embedding_mode: Literal["CONTROLLED", "DISABLED"]


class ConversationProjection(VersionedModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    media_pin: MediaPin
    portfolio_pin: PortfolioPin
    vision_analysis: PublicAnalysis | None
    matches: PortfolioProjection | None


class ConversationState(ConversationProjection):
    vision_mode: Literal["CONTROLLED", "DISABLED"]
    embedding_mode: Literal["CONTROLLED", "DISABLED"]


class PortfolioCommandResult(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    receipt_id: CanonicalUUID
    operation: Operation
    asset_id: CanonicalUUID | None
    asset_version: PositiveDecimal | None
    version_id: CanonicalUUID | None
    upload_id: CanonicalUUID | None
    upload_state: UploadState | None
    upload_expires_at: datetime | None
    item_id: CanonicalUUID | None
    item_version: PositiveDecimal | None
    revision_id: CanonicalUUID | None
    canonical_sha256: Digest | None
    build_id: CanonicalUUID | None
    build_version: PositiveDecimal | None
    build_state: BuildState | None
    knowledge_build_id: CanonicalUUID | None
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    recorded_at: datetime
    request_hash: Digest


CommandResult = PortfolioCommandResult


class PortfolioCommandResponse(VersionedModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: CommandResult


CommandResponse = PortfolioCommandResponse


class UploadResponse(VersionedModel):
    version_id: CanonicalUUID
    upload_id: CanonicalUUID
    state: UploadState
    recorded: Literal[True]


class PurgeResponse(VersionedModel):
    version_id: CanonicalUUID
    state: Literal["PURGE_PENDING", "PURGED"]
    outcome: Literal["DELETED", "DEPENDENCY_TIMEOUT", "DEPENDENCY_UNAVAILABLE"]


class AnalysisResponse(VersionedModel):
    outcome: Literal["DISABLED", "COMPLETE", "REPLAY", "UNAVAILABLE"]
    analysis_id: CanonicalUUID | None
    state: Literal["RESERVED", "SUCCESS", "ERROR", "UNKNOWN"] | None
    applied: bool


class PrivateVersion(ConfigurationModel):
    workspace_id: UUID
    business_id: UUID
    asset_id: UUID
    version_id: UUID
    upload_id: UUID
    state: UploadState
    ticket: UUID = Field(repr=False)
    storage_key: str | None = Field(default=None, repr=False)
    manifest: DeclaredManifest
    expires_at: datetime
    operation_deadline: datetime | None
    operation: Literal["HEAD_GET_ONLY", "OWNER_ACCEPTED_DELETE"] | None = None
    recovery_deadline: datetime | None = None
    purge_deadline: datetime | None = None


class PrivatePreview(ConfigurationModel):
    workspace_id: UUID
    business_id: UUID
    asset_id: UUID
    version_id: UUID
    state: Literal["READY"]
    storage_key: str = Field(repr=False)
    manifest: ImageManifest


class VisionReservation(ConfigurationModel):
    status: Literal["RESERVED", "REPLAY"]
    analysis_id: UUID
    state: Literal["RESERVED", "SUCCESS", "ERROR", "UNKNOWN"]
    ticket: UUID | None = Field(repr=False)
    storage_key: str | None = Field(repr=False)
    manifest: ImageManifest | None
    deadline: datetime
    source_kind: Literal["OWNER_ASSET", "CLIENT_REFERENCE"]
    identity_sha256: Digest
    workspace_id: UUID | None = None
    business_id: UUID | None = None
    asset_id: UUID | None = None
    asset_version_id: UUID | None = None
    media_pin: MediaPin | None = None
    source_sha256: Digest | None = None
    reserved_cost: Literal["3.89"] | None = None
    currency: Literal["RUB"] | None = None


class EmbeddingReservation(ConfigurationModel):
    status: Literal["RESERVED", "REPLAY"]
    call_id: UUID | None
    ticket: UUID | None = Field(repr=False)
    wire: str | None = Field(repr=False, max_length=8192)
    wire_sha256: Digest | None
    profile_id: Literal["polza_openai_text_embedding3small_1536_cosine_v1"]
    deadline: datetime | None
    reserved_cost: Literal["0.08", "0.00"]
    currency: Literal["RUB"]


class ErrorValue(ConfigurationModel):
    code: PortfolioCode | AuthCode


class PortfolioErrorResponse(ConfigurationModel):
    error: ErrorValue


ErrorResponse = PortfolioErrorResponse
