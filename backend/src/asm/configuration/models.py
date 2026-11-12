"""M5.1A v1: bounded general Business data, never private Client records."""

import json
import re
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from asm.auth.models import AuthCode
from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal, Timestamp
from asm.configuration.errors import ConfigurationCode


def scalar_text(value: str) -> str:
    if "\0" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("Scalar Unicode required")
    return value


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Nonblank text required")
    return value


def slug(value: str) -> str:
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", value) is None:
        raise ValueError("Invalid identifier")
    return value


Text = Annotated[str, AfterValidator(scalar_text)]
Nonblank = Annotated[Text, AfterValidator(nonblank)]
Identifier = Annotated[
    str, Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$", max_length=40), AfterValidator(slug)
]
Number = Annotated[int, Field(ge=0, le=100000000000)]
Mode = Annotated[Nonblank, Field(max_length=32)]
Note = Annotated[Text, Field(max_length=160)]


class ConfigurationModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class VersionedModel(ConfigurationModel):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Integer schema version required")
        return value


class IntakeField(ConfigurationModel):
    id: Identifier
    label: Nonblank = Field(max_length=100)
    required: bool


class PricePolicy(ConfigurationModel):
    mode: Mode
    amount_minor: Number | None = Field(description="Configured RUB kopecks; no Quote is created.")
    formula_note: Note | None


class DurationPolicy(ConfigurationModel):
    mode: Mode
    minutes: Number | None
    rule_note: Note | None


class DepositPolicy(ConfigurationModel):
    mode: Mode
    amount_minor: Number | None
    percent: Number | None


class Service(ConfigurationModel):
    id: Identifier
    name: Nonblank = Field(max_length=100)
    description: Text = Field(max_length=500)
    active: bool
    intake_fields: list[IntakeField] = Field(max_length=6)
    price: PricePolicy
    duration: DurationPolicy
    deposit: DepositPolicy


class Rule(ConfigurationModel):
    id: Identifier
    service_id: Identifier | None
    kind: Mode
    value: Number | bool


class FAQ(ConfigurationModel):
    id: Identifier
    service_id: Identifier | None
    question: Nonblank = Field(max_length=200)
    answer: Nonblank = Field(max_length=500)
    source: Text = Field(max_length=120)
    confirmed: bool
    rule_ids: list[Identifier] = Field(max_length=6)


class Bundle(VersionedModel):
    communication_style: Mode
    services: list[Service] = Field(max_length=8)
    rules: list[Rule] = Field(max_length=12)
    faqs: list[FAQ] = Field(max_length=12)

    @model_validator(mode="after")
    def bounded_bundle(self) -> Self:
        # PostgreSQL jsonb::text uses these separators. Key order cannot change
        # the byte count; floats/NUL/surrogates are excluded by the closed shape.
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode("utf-8")) > 4096:
            raise ValueError("Configuration bundle too large")
        return self


class ValidationIssue(ConfigurationModel):
    severity: Literal["ERROR", "WARNING"]
    code: Literal[
        "INVALID_SHAPE",
        "INVALID_STYLE",
        "NO_ACTIVE_SERVICE",
        "DUPLICATE_ID",
        "INVALID_MODE",
        "INVALID_POLICY",
        "INVALID_REFERENCE",
        "INVALID_RULE",
        "CONFLICTING_RULES",
        "UNCONFIRMED_FAQ",
        "OWNER_HANDOFF",
    ]
    path: str = Field(max_length=200)


class ValidationResult(ConfigurationModel):
    valid: bool
    issues: list[ValidationIssue] = Field(max_length=128)


class DraftState(VersionedModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    draft_version: LimitDecimal
    activation_version: LimitDecimal
    release_id: CanonicalUUID | None
    bundle: Bundle | None

    @model_validator(mode="after")
    def coherent_state(self) -> Self:
        if (self.draft_version == "0") != (self.bundle is None) or (
            (self.activation_version == "0") != (self.release_id is None)
        ):
            raise ValueError("Incoherent configuration state")
        return self


class ActiveProjection(VersionedModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    activation_version: LimitDecimal
    release_id: CanonicalUUID | None
    source_draft_version: PositiveDecimal | None
    published_by: CanonicalUUID | None
    published_at: Timestamp | None
    bundle: Bundle | None
    structured_rules_authoritative: Literal[True]

    @model_validator(mode="after")
    def coherent_release(self) -> Self:
        present = [self.source_draft_version, self.published_by, self.published_at, self.bundle]
        if self.release_id is None:
            if self.activation_version != "0" or any(v is not None for v in present):
                raise ValueError("Incoherent empty projection")
        elif self.activation_version == "0" or any(v is None for v in present):
            raise ValueError("Incomplete active projection")
        return self


class EditDraft(ConfigurationModel):
    expected_draft_version: LimitDecimal
    bundle: Bundle


class Publish(ConfigurationModel):
    expected_draft_version: LimitDecimal
    expected_activation_version: LimitDecimal


class Rollback(ConfigurationModel):
    expected_activation_version: LimitDecimal
    release_id: CanonicalUUID


class CommandResult(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    receipt_id: CanonicalUUID
    operation: Literal["EDIT", "PUBLISH", "ROLLBACK"]
    draft_version: PositiveDecimal
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    recorded_at: Timestamp


class CommandResponse(ConfigurationModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: CommandResult


class ServicePreview(ConfigurationModel):
    service_id: Identifier
    active: bool
    owner_handoff: bool


class Preview(ConfigurationModel):
    state: DraftState
    validation: ValidationResult
    services: list[ServicePreview]
    structured_rules_authoritative: Literal[True]


class ConfigurationErrorDetail(ConfigurationModel):
    code: ConfigurationCode | AuthCode


class ConfigurationErrorResponse(ConfigurationModel):
    error: ConfigurationErrorDetail
