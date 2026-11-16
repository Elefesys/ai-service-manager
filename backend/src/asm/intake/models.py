"""Closed M5.3A shapes. A preliminary intake is never an order or assessment."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal
from asm.configuration.models import ConfigurationModel, Identifier, Nonblank, Text

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FieldId = Literal["idea", "placement", "approximate_size", "style", "references"]
Category = Literal["NEW_TATTOO", "COVER_UP", "OTHER_COMPLEX", "FAQ_ONLY", "AMBIGUOUS"]
Value = Annotated[Nonblank, Field(max_length=300)]
Minutes = Annotated[int, Field(gt=0, le=100000)]
ComponentMinutes = Annotated[int, Field(ge=0, le=100000)]


class Source(ConfigurationModel):
    message_id: CanonicalUUID
    source_version: Digest
    quote: Text = Field(max_length=500)
    analysis_id: CanonicalUUID | None
    analysis_sha256: Digest | None

    @model_validator(mode="after")
    def analysis_pair(self) -> Self:
        if (self.analysis_id is None) != (self.analysis_sha256 is None):
            raise ValueError("Incomplete analysis source")
        return self


class CandidateFact(ConfigurationModel):
    field: FieldId
    value: Value
    status: Literal["client-stated", "observed"]
    source: Source
    explicit_correction: bool


class CandidateSet(ConfigurationModel):
    service_id: Identifier | None
    category: Category
    switch_request: bool
    facts: tuple[CandidateFact, ...] = Field(max_length=5)

    @model_validator(mode="after")
    def unique_fields(self) -> Self:
        if len({f.field for f in self.facts}) != len(self.facts):
            raise ValueError("Duplicate intake field")
        if self.category in ("FAQ_ONLY", "AMBIGUOUS") and self.facts:
            raise ValueError("Unresolved request cannot merge facts")
        return self


class Fact(ConfigurationModel):
    field: FieldId
    value: Value
    status: Literal["client-stated", "observed", "owner-confirmed"]
    source: Source
    confirmed_by: CanonicalUUID | None
    conflict: bool


class SourceMessage(ConfigurationModel):
    message_id: CanonicalUUID
    source_version: Digest
    text: Text = Field(max_length=4096)


class IntakeProjection(ConfigurationModel):
    revision: Literal["preliminary_intake_v1"]
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    service_id: Identifier | None
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    template_revision: Literal["tattoo_intake_v1"] | None
    control_generation: PositiveDecimal
    context_version: PositiveDecimal
    version: LimitDecimal
    category: Category
    facts: list[Fact] = Field(max_length=5)
    missing: list[FieldId] = Field(max_length=5)
    conflicts: list[FieldId] = Field(max_length=5)
    status: Literal["NOT_STARTED", "CLARIFY", "OWNER_HANDOFF", "PRELIMINARILY_COMPLETE"]
    question: Nonblank | None = Field(max_length=300)
    sources: list[SourceMessage] = Field(max_length=64)
    fingerprint: Digest
    preliminary: Literal[True]


class IntakeCommand(ConfigurationModel):
    expected_version: LimitDecimal
    expected_fingerprint: Digest
    field: FieldId
    value: Value
    source: Source


class CaseAsset(ConfigurationModel):
    asset_id: CanonicalUUID
    asset_version_id: CanonicalUUID


class DurationCaseInput(ConfigurationModel):
    description: Nonblank = Field(max_length=500)
    asset: CaseAsset | None
    width_mm: Annotated[int, Field(gt=0, le=3000)] | None
    height_mm: Annotated[int, Field(gt=0, le=3000)] | None
    placement: Value | None
    style: Value | None
    detail: Value | None
    fill: Value | None
    provider: Value | None
    working_minutes: Minutes | None
    occupied_minutes: Minutes | None
    setup_minutes: ComponentMinutes | None
    stencil_minutes: ComponentMinutes | None
    break_minutes: ComponentMinutes | None
    cleanup_minutes: ComponentMinutes | None
    treatment: Literal["INCLUDED", "EXCLUDED", "UNKNOWN"]
    session_count: Annotated[int, Field(gt=0, le=20)] | None
    session_minutes: list[Minutes] | None = Field(max_length=20)
    explanation: Text | None = Field(max_length=500)

    @model_validator(mode="after")
    def consistent_measurements(self) -> Self:
        if self.working_minutes is not None and self.occupied_minutes is not None:
            if self.occupied_minutes < self.working_minutes:
                raise ValueError("Occupied time cannot be less than working time")
            components = [
                self.setup_minutes,
                self.stencil_minutes,
                self.break_minutes,
                self.cleanup_minutes,
            ]
            if self.treatment == "INCLUDED" and all(v is not None for v in components):
                if (
                    self.working_minutes + sum(v for v in components if v is not None)
                    != self.occupied_minutes
                ):
                    raise ValueError("Inconsistent occupied-time components")
        if self.session_minutes is not None:
            if not self.session_minutes or self.session_count != len(self.session_minutes):
                raise ValueError("Session count must match recorded durations")
            if (
                self.occupied_minutes is not None
                and sum(self.session_minutes) != self.occupied_minutes
            ):
                raise ValueError("Session durations must match occupied minutes")
        return self


class DurationCase(ConfigurationModel):
    case_id: CanonicalUUID
    version: PositiveDecimal
    state: Literal["DRAFT", "CONFIRMED", "REVOKED"]
    data: DurationCaseInput
    confirmed_by: CanonicalUUID | None
    source_current: bool


class CaseCommand(ConfigurationModel):
    expected_version: LimitDecimal
    case_id: CanonicalUUID | None
    data: DurationCaseInput | None


class CaseMatch(ConfigurationModel):
    case: DurationCase
    matches: list[str] = Field(max_length=4)
    differences: list[str] = Field(max_length=4)
    unknown: list[str] = Field(max_length=4)


class CasePage(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    items: list[DurationCase] = Field(max_length=20)


class CaseSearch(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    items: list[CaseMatch] = Field(max_length=5)


class IntakeReceipt(ConfigurationModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    receipt_id: CanonicalUUID
    version: PositiveDecimal
