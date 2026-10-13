"""Strict owner Escalation projections, commands and saved acceptances (§14.5)."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from asm.billing.models import CommonCode, StrictModel
from asm.billing.validation import CanonicalUUID, PositiveDecimal, Timestamp

Operation = Literal["RESOLVE", "CANCEL"]
Status = Literal["PENDING", "RESOLVED", "CANCELLED", "EXPIRED"]
StatusFilter = Literal["PENDING", "RESOLVED", "CANCELLED", "EXPIRED", "ALL"]
ClosureReason = Literal[
    "OWNER_CANCELLED", "CONTROL_CHANGED", "CONTEXT_CHANGED", "ASSIGNEE_REVOKED", "DEADLINE_ELAPSED"
]
QUESTION = "CONTROLLED ESCALATION TEST: требуется решение владельца."


def exact_answer(value: str) -> str:
    if (
        not 1 <= len(value) <= 512
        or not value.strip()
        or "\x00" in value
        or any(0xD800 <= ord(c) <= 0xDFFF for c in value)
        or len(value.encode("utf-8")) > 2048
    ):
        raise ValueError("Invalid answer")
    return value


class EscalationCancelRequest(StrictModel):
    expected_conversation_id: CanonicalUUID
    expected_client_id: CanonicalUUID
    expected_escalation_version: PositiveDecimal
    expected_control_generation: PositiveDecimal
    expected_context_version: PositiveDecimal


class EscalationResolveRequest(EscalationCancelRequest):
    answer_text: str = Field(min_length=1, max_length=512, repr=False)

    @field_validator("answer_text")
    @classmethod
    def answer(cls, value: str) -> str:
        return exact_answer(value)


class EscalationBoundContext(StrictModel):
    turn_revision: PositiveDecimal
    control_generation: PositiveDecimal
    context_version: PositiveDecimal
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class EscalationCurrentContext(StrictModel):
    control_mode: Literal["HUMAN", "AI"]
    control_generation: PositiveDecimal
    context_version: PositiveDecimal


class EscalationReminder(StrictModel):
    ordinal: Literal[1, 2]
    due_at: Timestamp
    recorded_at: Timestamp | None

    @field_validator("ordinal", mode="before")
    @classmethod
    def integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid ordinal")
        return value


class EscalationResolution(StrictModel):
    answer_text: str = Field(min_length=1, max_length=512, repr=False)
    actor_user_account_id: CanonicalUUID
    completed_at: Timestamp

    @field_validator("answer_text")
    @classmethod
    def answer(cls, value: str) -> str:
        return exact_answer(value)


class EscalationClosure(StrictModel):
    reason: ClosureReason
    actor_user_account_id: CanonicalUUID | None
    completed_at: Timestamp

    @model_validator(mode="after")
    def actor(self) -> Self:
        if (self.reason == "OWNER_CANCELLED") != (self.actor_user_account_id is not None):
            raise ValueError("Invalid closure actor")
        return self


class EscalationView(StrictModel):
    workspace_id: CanonicalUUID
    escalation_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    turn_id: CanonicalUUID
    assignee_user_account_id: CanonicalUUID
    reason: Literal["OWNER_DECISION_REQUIRED"]
    question: Literal["CONTROLLED ESCALATION TEST: требуется решение владельца."]
    policy: Literal["LOCAL_TEST_OWNER_WAIT_V1"]
    version: Literal["1", "2"]
    status: Status
    bound_context: EscalationBoundContext
    current_context: EscalationCurrentContext
    validity: Literal[
        "CURRENT", "CONTROL_CHANGED", "CONTEXT_CHANGED", "ASSIGNEE_REVOKED", "EXPIRED", "TERMINAL"
    ]
    waiting: Literal["WAITING_FOR_HUMAN"] | None
    created_at: Timestamp
    due_at: Timestamp
    second_reminder_at: Timestamp
    expires_at: Timestamp
    observed_at: Timestamp
    reminders: list[EscalationReminder] = Field(min_length=2, max_length=2)
    maintenance: Literal["SCHEDULED", "COMPLETE", "FAILED"]
    resolution: EscalationResolution | None
    closure: EscalationClosure | None
    can_resolve: bool
    can_cancel: bool

    @model_validator(mode="after")
    def shape(self) -> Self:
        pending = self.status == "PENDING"
        current = pending and self.validity == "CURRENT"
        if (
            self.version != ("1" if pending else "2")
            or (self.validity == "TERMINAL") == pending
            or (self.waiting is not None) != current
            or (self.resolution is not None) != (self.status == "RESOLVED")
            or (self.closure is not None) != (self.status in ("CANCELLED", "EXPIRED"))
            or [r.ordinal for r in self.reminders] != [1, 2]
            or [r.due_at for r in self.reminders] != [self.due_at, self.second_reminder_at]
            or not self.created_at < self.due_at < self.second_reminder_at < self.expires_at
            or (self.can_resolve and not current)
            or (
                self.can_cancel
                and (
                    not pending
                    or self.validity not in ("CURRENT", "ASSIGNEE_REVOKED")
                    or self.observed_at >= self.expires_at
                )
            )
        ):
            raise ValueError("Invalid Escalation projection")
        if self.closure and (
            (self.status == "EXPIRED") != (self.closure.reason == "DEADLINE_ELAPSED")
        ):
            raise ValueError("Invalid closure status")
        return self


class EscalationPage(StrictModel):
    items: list[EscalationView] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=1024)


class EscalationCursor(StrictModel):
    v: Literal[1]
    endpoint: Literal["ESCALATIONS"]
    workspace_id: CanonicalUUID
    direction: Literal["DESC"]
    status: StatusFilter
    created_at: Timestamp
    id: CanonicalUUID

    @field_validator("v", mode="before")
    @classmethod
    def version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid cursor version")
        return value


class EscalationAcceptedResult(StrictModel):
    workspace_id: CanonicalUUID
    escalation_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    receipt_id: CanonicalUUID
    audit_event_id: CanonicalUUID
    operation: Operation
    accepted_status: Literal["RESOLVED", "CANCELLED"]
    previous_version: Literal["1"]
    accepted_version: Literal["2"]
    accepted_context_version: PositiveDecimal
    control_generation: PositiveDecimal
    accepted_at: Timestamp

    @model_validator(mode="after")
    def transition(self) -> Self:
        if self.accepted_status != ("RESOLVED" if self.operation == "RESOLVE" else "CANCELLED"):
            raise ValueError("Invalid Escalation transition")
        return self


class EscalationCommandResponse(StrictModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: EscalationAcceptedResult


class EscalationErrorDetail(StrictModel):
    code: CommonCode | Literal["ESCALATION_EXPIRED", "ESCALATION_FINAL", "VERSION_EXHAUSTED"]


class EscalationErrorResponse(StrictModel):
    error: EscalationErrorDetail
