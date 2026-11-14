"""Knowledge v1 owner wire; existing configuration v1 DTOs remain unchanged."""

from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from asm.auth.models import AuthCode
from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal, Timestamp
from asm.configuration.models import Identifier, Nonblank, Text
from asm.knowledge.errors import KnowledgeCode
from asm.knowledge.validation import source_text

Profile = Literal["polza_openai_text_embedding3small_1536_cosine_v1"]
SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", max_length=64)]
SourceText = Annotated[Text, Field(max_length=2048), AfterValidator(source_text)]
KnowledgeOperation = Literal[
    "KNOWLEDGE_SAVE",
    "KNOWLEDGE_CONFIRM",
    "KNOWLEDGE_REVOKE",
    "KNOWLEDGE_DELETE",
    "KNOWLEDGE_BUILD_CREATE",
    "KNOWLEDGE_PUBLISH",
    "KNOWLEDGE_ROLLBACK",
]
BuildState = Literal["PLANNED", "BUILDING", "READY", "ERROR", "UNKNOWN"]


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class KnowledgeVersioned(KnowledgeModel):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Integer schema version required")
        return value


class SaveSource(KnowledgeVersioned):
    source_id: CanonicalUUID | None
    expected_source_version: LimitDecimal
    title: Nonblank = Field(max_length=120)
    format: Literal["TEXT", "MARKDOWN"]
    text: SourceText
    source_label: Nonblank = Field(max_length=120)
    author_label: Text | None = Field(default=None, max_length=80)
    service_id: Identifier | None = None
    category: Identifier | None = None
    claim_key: Identifier | None = None
    effective_from: Timestamp | None = None
    effective_until: Timestamp | None = None

    @model_validator(mode="after")
    def dates(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("Invalid effective dates")
        return self


class ConfirmSource(KnowledgeVersioned):
    expected_source_version: PositiveDecimal
    revision_id: CanonicalUUID
    canonical_sha256: SHA256


class WithdrawSource(KnowledgeVersioned):
    expected_source_version: PositiveDecimal
    expected_activation_version: LimitDecimal


class CreateBuild(KnowledgeVersioned):
    expected_sources_hash: SHA256
    revision_ids: list[CanonicalUUID] = Field(max_length=8)

    @field_validator("revision_ids")
    @classmethod
    def unique_revisions(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Unique revisions required")
        return value


class PublishKnowledge(KnowledgeVersioned):
    expected_draft_version: PositiveDecimal
    expected_activation_version: LimitDecimal
    build_id: CanonicalUUID
    expected_build_version: PositiveDecimal


class RollbackKnowledge(KnowledgeVersioned):
    expected_activation_version: LimitDecimal
    release_id: CanonicalUUID


KnowledgeRequest = (
    SaveSource | ConfirmSource | WithdrawSource | CreateBuild | PublishKnowledge | RollbackKnowledge
)


class KnowledgeChunkPreview(KnowledgeModel):
    ordinal: int = Field(ge=0, le=3)
    text: Text = Field(min_length=1, max_length=512)
    sha256: SHA256


class KnowledgePreview(KnowledgeModel):
    chunks: list[KnowledgeChunkPreview] = Field(max_length=4)
    issues: list[Literal["INVALID_TEXT", "SOURCE_TOO_LARGE", "CHUNK_LIMIT"]] = Field(max_length=1)


class KnowledgeRevision(KnowledgeModel):
    revision_id: CanonicalUUID
    revision_no: PositiveDecimal
    title: Nonblank = Field(max_length=120)
    format: Literal["TEXT", "MARKDOWN"]
    canonical_text: SourceText
    canonical_sha256: SHA256
    source_label: Nonblank = Field(max_length=120)
    author_label: Text | None = Field(max_length=80)
    service_id: Identifier | None
    category: Identifier | None
    claim_key: Identifier | None
    effective_from: Timestamp | None
    effective_until: Timestamp | None
    confirmed: bool


class KnowledgeSource(KnowledgeModel):
    source_id: CanonicalUUID
    source_version: PositiveDecimal
    state: Literal["DRAFT", "CONFIRMED", "REVOKED"]
    head: KnowledgeRevision
    preview: KnowledgePreview


class KnowledgeBuild(KnowledgeModel):
    build_id: CanonicalUUID
    build_version: PositiveDecimal
    state: BuildState
    profile_id: Profile
    manifest_hash: SHA256
    revision_ids: list[CanonicalUUID] = Field(max_length=8)
    chunk_count: int = Field(ge=0, le=32)
    calls_reserved: int = Field(ge=0, le=4)
    calls_completed: int = Field(ge=0, le=4)
    error_code: Literal["EMBEDDING_ERROR", "EMBEDDING_UNKNOWN", "DEADLINE", "SOURCE_STALE"] | None


class KnowledgeRollbackTarget(KnowledgeModel):
    release_id: CanonicalUUID
    build_id: CanonicalUUID | None
    eligible: bool
    reason_code: Literal["ROLLBACK_NOT_ALLOWED"] | None


class KnowledgeProjection(KnowledgeVersioned):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    sources_hash: SHA256
    activation_version: LimitDecimal
    release_id: CanonicalUUID | None
    active_build_id: CanonicalUUID | None
    profile_id: Profile
    sources: list[KnowledgeSource] = Field(max_length=8)
    builds: list[KnowledgeBuild] = Field(max_length=8)
    rollback_targets: list[KnowledgeRollbackTarget] = Field(max_length=8)

    @model_validator(mode="after")
    def coherent_projection(self) -> Self:
        if (self.activation_version == "0") != (self.release_id is None) or (
            self.release_id is None and self.active_build_id is not None
        ):
            raise ValueError("Incoherent active knowledge")
        return self


class KnowledgeOwnerState(KnowledgeProjection):
    embedding_mode: Literal["DISABLED", "CONTROLLED"]


class KnowledgeCommandResult(KnowledgeModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    receipt_id: CanonicalUUID
    operation: KnowledgeOperation
    source_id: CanonicalUUID | None
    source_version: PositiveDecimal | None
    revision_id: CanonicalUUID | None
    build_id: CanonicalUUID | None
    build_version: PositiveDecimal | None
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    recorded_at: Timestamp
    request_hash: SHA256


class KnowledgeCommandResponse(KnowledgeVersioned):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: KnowledgeCommandResult


class EmbeddingReservation(KnowledgeModel):
    status: Literal["RESERVED", "REPLAY"]
    call_id: CanonicalUUID
    ticket: CanonicalUUID | None = Field(repr=False)
    wire: str | None = Field(repr=False, max_length=8192)
    wire_sha256: SHA256
    profile_id: Profile
    deadline: Timestamp
    reserved_cost: Literal["0.08"]
    currency: Literal["RUB"]

    @model_validator(mode="after")
    def coherent_reservation(self) -> Self:
        if self.status == "RESERVED":
            if self.ticket is None or self.wire is None:
                raise ValueError("Incomplete reservation")
        elif self.ticket is not None or self.wire is not None:
            raise ValueError("Replay cannot execute HTTP")
        return self


class EmbeddingCost(KnowledgeModel):
    status: Literal["CONFIRMED", "UNKNOWN"]
    amount: str | None
    currency: Literal["RUB"]


class EmbeddingIdentity(KnowledgeModel):
    status: Literal["CONFIRMED", "UNVERIFIED"]
    source: Literal["BODY", "HISTORY", "NONE"]
    provider: Literal["OpenAI"] | None
    model: str | None = Field(max_length=128)


class EmbeddingCompletion(KnowledgeModel):
    call_id: CanonicalUUID
    state: Literal["SUCCESS", "ERROR", "UNKNOWN"]
    vectors_sha256: SHA256 | None
    validation_error: (
        Literal[
            "INVALID_VECTOR", "USAGE_INVALID", "IDENTITY_UNVERIFIED", "COST_UNKNOWN", "COST_LIMIT"
        ]
        | None
    )
    usage: dict[str, Any]
    cost: EmbeddingCost
    identity: EmbeddingIdentity
    completion_tokens_state: Literal["NOT_APPLICABLE", "ZERO", "INVALID"]


class BuildApplication(KnowledgeModel):
    applied: bool
    build_id: CanonicalUUID
    build_version: PositiveDecimal
    state: BuildState
    reason_code: Literal["BUILD_NOT_READY", "DEADLINE", "SOURCE_STALE"] | None


class KnowledgeErrorDetail(KnowledgeModel):
    code: KnowledgeCode | AuthCode


class KnowledgeErrorResponse(KnowledgeModel):
    error: KnowledgeErrorDetail
