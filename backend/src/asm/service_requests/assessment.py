"""Evaluate a selected draft against the active, locked publication."""

import re
from typing import Literal, Self

from pydantic import Field, model_validator

from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal
from asm.configuration.models import (
    ConfigurationModel,
    DurationPolicy,
    Identifier,
    OccupiedMinutes,
    Rule,
    Service,
    SizeMillimetres,
)
from asm.intake.models import Digest, Fact, FieldId
from asm.service_requests.models import IntentSource

Outcome = Literal["FEASIBLE", "NEEDS_DATA", "NEEDS_OWNER", "DECLINED"]
Reason = Literal[
    "FIXED_DURATION",
    "SIZE_DURATION_RULE",
    "MISSING_FACT",
    "CONFLICTING_FACT",
    "SOURCE_CHANGED",
    "SIZE_NEEDS_CONFIRMATION",
    "MIN_AGE_UNCONFIRMED",
    "SIZE_LIMIT_EXCEEDED",
    "OWNER_HANDOFF",
    "OWNER_DURATION",
    "SERVICE_UNAVAILABLE",
    "DURATION_UNPUBLISHED",
]
FACT_FIELDS: tuple[FieldId, ...] = ("idea", "placement", "approximate_size", "style", "references")


class AssessmentCommand(ConfigurationModel):
    expected_revision: PositiveDecimal


class ComplexWork(ConfigurationModel):
    category: Literal["COVER_UP", "OTHER_COMPLEX"]
    source: IntentSource
    source_current: bool


class AssessmentInputs(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    request_id: CanonicalUUID
    request_revision: PositiveDecimal
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    authority_sha256: Digest
    service: Service | None
    rules: list[Rule] = Field(max_length=12)
    owner_handoff: bool
    facts: list[Fact] = Field(max_length=5)
    unavailable_fields: list[FieldId] = Field(max_length=5)
    complex_work: ComplexWork | None = None


class AssessmentDecision(ConfigurationModel):
    outcome: Outcome
    reason: Reason
    field: FieldId | None = None
    rule_id: Identifier | None = None
    limit: SizeMillimetres | None = None
    size_mm: SizeMillimetres | None = None
    occupied_minutes: OccupiedMinutes | None = None

    @model_validator(mode="after")
    def minutes_require_approval(self) -> Self:
        if (self.occupied_minutes is not None) != (self.outcome == "FEASIBLE"):
            raise ValueError("Inconsistent occupied minutes")
        return self


class ArchivedDuration(ConfigurationModel):
    assessment_id: CanonicalUUID
    request_revision: PositiveDecimal
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    occupied_minutes: OccupiedMinutes


class ServiceAssessment(AssessmentDecision):
    assessment_id: CanonicalUUID
    request_id: CanonicalUUID
    request_revision: PositiveDecimal
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    current: bool
    duration_policy: DurationPolicy | None
    evidence: list[Fact] = Field(max_length=5)
    complex_work: ComplexWork | None = Field(default=None, exclude_if=lambda value: value is None)
    archived_duration: ArchivedDuration | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


def confirmed(fact: Fact | None) -> bool:
    return (
        fact is not None
        and not fact.conflict
        and fact.status in {"client-stated", "owner-confirmed"}
    )


def size_millimetres(value: str) -> int | None:
    """Read one explicit length, in whole millimetres or centimetres to a tenth."""
    match = re.fullmatch(r"([0-9]{1,4})(?:[.,]([0-9]))?[ \t]*(mm|мм|cm|см)", value.strip().lower())
    if match is None:
        return None
    whole, tenth, unit = match.groups()
    if unit in {"cm", "см"}:
        size = 10 * int(whole) + int(tenth or "0")
    elif tenth is None:
        size = int(whole)
    else:
        return None
    return size if 1 <= size <= 1000 else None


def evaluate(inputs: AssessmentInputs) -> AssessmentDecision:
    service = inputs.service
    if service is None:
        return AssessmentDecision(outcome="NEEDS_OWNER", reason="SERVICE_UNAVAILABLE")

    # An equally valued service restriction is more specific than the general one.
    rules = {
        rule.kind: rule
        for rule in sorted(inputs.rules, key=lambda rule: rule.service_id is not None)
    }
    handoff = rules.get("OWNER_HANDOFF")
    if inputs.owner_handoff or (handoff is not None and handoff.value is True):
        return AssessmentDecision(
            outcome="NEEDS_OWNER",
            reason="OWNER_HANDOFF",
            rule_id=handoff.id if handoff is not None and handoff.value is True else None,
        )

    maximum = rules.get("MAX_SIZE_MM")
    size_rule = service.duration.size_rule
    requires_size = maximum is not None or size_rule is not None
    required = {field.id for field in service.intake_fields if field.required}
    if requires_size:
        required.add("approximate_size")
    fields = [field for field in FACT_FIELDS if field in required]
    facts = {fact.field: fact for fact in inputs.facts}
    for field in fields:
        fact = facts.get(field)
        if fact is not None and fact.conflict:
            return AssessmentDecision(outcome="NEEDS_DATA", reason="CONFLICTING_FACT", field=field)
        if field in inputs.unavailable_fields:
            return AssessmentDecision(outcome="NEEDS_DATA", reason="SOURCE_CHANGED", field=field)

    size_fact = facts.get("approximate_size")
    size = (
        size_millimetres(size_fact.value)
        if requires_size and size_fact and confirmed(size_fact)
        else None
    )
    if (
        maximum is not None
        and type(maximum.value) is int
        and size is not None
        and size > maximum.value
    ):
        return AssessmentDecision(
            outcome="DECLINED",
            reason="SIZE_LIMIT_EXCEEDED",
            field="approximate_size",
            rule_id=maximum.id,
            limit=maximum.value,
            size_mm=size,
        )
    age = rules.get("MIN_AGE")
    if age is not None and type(age.value) is int:
        return AssessmentDecision(
            outcome="NEEDS_DATA", reason="MIN_AGE_UNCONFIRMED", rule_id=age.id, limit=age.value
        )

    for field in fields:
        if not confirmed(facts.get(field)):
            return AssessmentDecision(outcome="NEEDS_DATA", reason="MISSING_FACT", field=field)
    if requires_size and size is None:
        return AssessmentDecision(
            outcome="NEEDS_DATA", reason="SIZE_NEEDS_CONFIRMATION", field="approximate_size"
        )

    policy = service.duration
    if policy.mode == "FIXED" and policy.minutes is not None:
        return AssessmentDecision(
            outcome="FEASIBLE", reason="FIXED_DURATION", occupied_minutes=policy.minutes
        )
    if policy.mode == "CONFIGURED_RULE" and size_rule is not None and size is not None:
        return AssessmentDecision(
            outcome="FEASIBLE",
            reason="SIZE_DURATION_RULE",
            field="approximate_size",
            size_mm=size,
            occupied_minutes=(
                size_rule.at_or_below_minutes
                if size <= size_rule.threshold_mm
                else size_rule.above_minutes
            ),
        )
    if policy.mode == "OWNER_DEFINED":
        return AssessmentDecision(outcome="NEEDS_OWNER", reason="OWNER_DURATION")
    return AssessmentDecision(outcome="NEEDS_OWNER", reason="DURATION_UNPUBLISHED")
