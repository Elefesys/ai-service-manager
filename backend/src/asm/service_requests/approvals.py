"""Frozen terms and the narrow owner decision contract for one service request."""

from typing import Literal, Self

from pydantic import Field, model_validator

from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal, Timestamp
from asm.configuration.models import (
    ConfigurationModel,
    DepositPolicy,
    Nonblank,
    OccupiedMinutes,
    PriceMinor,
)
from asm.intake.models import Fact, FieldId
from asm.service_requests.assessment import ComplexWork
from asm.service_requests.models import IntentSource

ApprovalAction = Literal["PREPARE_QUOTE"]
ApprovalVersion = Literal["1", "2"]


class OpenApproval(ConfigurationModel):
    expected_revision: PositiveDecimal


class DecideApproval(ConfigurationModel):
    expected_version: ApprovalVersion
    action: ApprovalAction
    operation: Literal["APPROVE", "CLARIFY", "DECLINE", "WITHDRAW"]
    amount_minor: PriceMinor | None = None
    occupied_minutes: OccupiedMinutes | None = None
    note: Nonblank | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def permitted_input(self) -> Self:
        if self.operation != "APPROVE" and (
            self.amount_minor is not None or self.occupied_minutes is not None
        ):
            raise ValueError("Only approval sets commercial values")
        if self.operation == "CLARIFY" and self.note is None:
            raise ValueError("A clarification requires a question")
        if self.operation == "WITHDRAW" and self.note is not None:
            raise ValueError("Withdrawal has no decision text")
        return self


class ApprovalBasis(ConfigurationModel):
    service_name: Nonblank = Field(max_length=100)
    release_id: CanonicalUUID
    activation_version: LimitDecimal
    deposit: DepositPolicy
    facts: list[Fact] = Field(max_length=5)
    unavailable_fields: list[FieldId] = Field(max_length=5)
    intent_source: IntentSource
    intent_current: bool
    question: Nonblank | None = Field(max_length=300)
    assessment_id: CanonicalUUID
    assessment_outcome: Literal["FEASIBLE", "NEEDS_DATA", "NEEDS_OWNER", "DECLINED"]
    assessment_reason: str = Field(max_length=40)
    complex_work: ComplexWork | None
    price_calculation_id: CanonicalUUID
    price_reason: str = Field(max_length=40)
    amount_minor: PriceMinor | None
    occupied_minutes: OccupiedMinutes | None
    can_approve: bool


class ApprovedTerms(ConfigurationModel):
    currency: Literal["RUB"]
    amount_minor: PriceMinor
    occupied_minutes: OccupiedMinutes
    price_reference_id: CanonicalUUID
    duration_reference_id: CanonicalUUID


class OwnerDecision(ConfigurationModel):
    decision_id: CanonicalUUID
    actor_user_account_id: CanonicalUUID
    submitted: DecideApproval
    decided_at: Timestamp
    authorized_action: ApprovalAction | None
    terms: ApprovedTerms | None


class ApprovalView(ConfigurationModel):
    approval_id: CanonicalUUID
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    request_id: CanonicalUUID
    request_revision: PositiveDecimal
    version: ApprovalVersion
    action: ApprovalAction
    assignee_user_account_id: CanonicalUUID
    basis: ApprovalBasis
    created_at: Timestamp
    expires_at: Timestamp
    status: Literal[
        "PENDING", "APPROVED", "CLARIFICATION", "DECLINED", "EXPIRED", "STALE", "REVOKED"
    ]
    decision: OwnerDecision | None
    can_resolve: bool
    authorization_current: bool
    related_escalation_id: CanonicalUUID | None

    @model_validator(mode="after")
    def frozen_decision(self) -> Self:
        if (self.version == "2") != (self.decision is not None):
            raise ValueError("Decision version mismatch")
        if self.can_resolve and self.status != "PENDING":
            raise ValueError("Only a pending request can be resolved")
        if self.authorization_current != (self.status == "APPROVED"):
            raise ValueError("Approval validity mismatch")
        if self.decision is not None:
            decision = self.decision
            if (
                decision.actor_user_account_id != self.assignee_user_account_id
                or decision.submitted.action != self.action
                or decision.submitted.expected_version != "1"
                or decision.submitted.operation == "WITHDRAW"
                or (decision.terms is not None) != (decision.submitted.operation == "APPROVE")
                or (decision.authorized_action == self.action) != (decision.terms is not None)
            ):
                raise ValueError("Decision does not match its authorization")
            if decision.terms is not None and (
                decision.terms.price_reference_id
                != (
                    self.basis.price_calculation_id
                    if self.basis.amount_minor is not None
                    else decision.decision_id
                )
                or decision.terms.duration_reference_id
                != (
                    self.basis.assessment_id
                    if self.basis.occupied_minutes is not None
                    else decision.decision_id
                )
                or decision.terms.amount_minor
                != (self.basis.amount_minor or decision.submitted.amount_minor)
                or decision.terms.occupied_minutes
                != (self.basis.occupied_minutes or decision.submitted.occupied_minutes)
            ):
                raise ValueError("Terms do not match the recorded bases")
        return self


class ApprovalPage(ConfigurationModel):
    items: list[ApprovalView] = Field(max_length=20)
    next_before_id: CanonicalUUID | None
