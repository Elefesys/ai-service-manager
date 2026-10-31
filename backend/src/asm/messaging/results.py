"""Private typed kernel results, not new messaging HTTP DTOs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from asm.billing.validation import MAX_BIGINT, Timestamp


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


ContextPermanentReason = Literal[
    "CONTEXT_POLICY_PAUSED",
    "CONTEXT_CONFIRMATION_REQUIRED",
    "CONTEXT_UNRESOLVED",
    "NEW_OBSERVATION",
    "CONTEXT_INPUT_UNRESOLVED",
    "CONTEXT_COVERAGE_REQUIRED",
    "CONTEXT_TOO_LARGE",
]


class ContextWorkResultBase(Result):
    """Historical scheduling decision, never an action or a send permit."""

    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0, le=MAX_BIGINT, strict=True)
    outbox_id: UUID | None
    recorded_at: Timestamp

    @field_validator("job_id", "turn_id", "outbox_id", mode="before")
    @classmethod
    def canonical_identity(cls, value: object) -> object:
        if (
            value is not None
            and type(value) is not UUID
            and (type(value) is not str or str(UUID(value)) != value)
        ):
            raise ValueError("Invalid context work identity")
        return value


class ContextWait(ContextWorkResultBase):
    code: Literal["CONTEXT_WAIT"]
    status: Literal["READY"]
    reason: Literal["CONTEXT_INPUT_PENDING"]
    available_at: Timestamp


class ContextWaitExhausted(ContextWorkResultBase):
    code: Literal["CONTEXT_WAIT_EXHAUSTED"]
    status: Literal["DEAD"]
    reason: Literal["CONTEXT_WAIT_EXHAUSTED"]
    available_at: None


class ContextHold(ContextWorkResultBase):
    code: Literal["CONTEXT_HOLD"]
    status: Literal["DEAD"]
    reason: ContextPermanentReason
    available_at: None


ContextWorkResult = Annotated[
    ContextWait | ContextWaitExhausted | ContextHold, Field(discriminator="code")
]
CONTEXT_WORK_CODES = frozenset(("CONTEXT_WAIT", "CONTEXT_WAIT_EXHAUSTED", "CONTEXT_HOLD"))
_context_work: TypeAdapter[ContextWorkResult] = TypeAdapter(ContextWorkResult)


def parse_context_work(value: object) -> ContextWait | ContextWaitExhausted | ContextHold:
    return _context_work.validate_python(value)


class InboxReceipt(Result):
    code: Literal["ACCEPTED", "DUPLICATE"]
    workspace_id: UUID
    inbox_id: UUID
    job_id: UUID
    accepted_at: datetime


class JobClaim(Result):
    job_id: UUID
    kind: Literal[
        "PROCESS_INBOX",
        "SEND_MANUAL_TEXT",
        "SEND_GUARDED_TEXT",
        "FETCH_IMAGE",
        "PROCESS_TURN",
        "ESCALATION_TIMER",
    ]
    workspace_id: UUID
    connection_id: UUID
    inbox_id: UUID | None
    outbox_id: UUID | None
    file_id: UUID | None = None
    claim_token: UUID = Field(repr=False)
    lease_until: datetime
    correlation_id: UUID
    attempt_count: int


class TurnJobClaim(JobClaim):
    kind: Literal["PROCESS_TURN"]
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    step: Literal["GROUP", "MEDIA", "TEST_CONSUME", "GUARDED_TEXT", "ESCALATE_OWNER"]


class AIJobClaim(JobClaim):
    """Explicit DB-only AI work; never a CONTROLLED turn consumer."""

    kind: Literal["PROCESS_TURN"]
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    step: Literal["AI_GENERATE"]
    inbox_id: None
    outbox_id: None
    file_id: None = None


class EscalationTimerClaim(JobClaim):
    kind: Literal["ESCALATION_TIMER"]
    escalation_id: UUID
    step: Literal["REMIND_1", "REMIND_2", "EXPIRE"]
    inbox_id: None
    outbox_id: None
    file_id: None = None


def parse_claim(value: object) -> JobClaim:
    if isinstance(value, dict) and value.get("kind") == "ESCALATION_TIMER":
        return EscalationTimerClaim.model_validate(value)
    if isinstance(value, dict) and value.get("kind") == "PROCESS_TURN":
        if value.get("step") == "AI_GENERATE":
            return AIJobClaim.model_validate(value)
        return TurnJobClaim.model_validate(value)
    return JobClaim.model_validate(value)


class ScanStep(Result):
    """Private SQL scan envelope; never exposed through owner APIs."""

    step: Literal["CLAIMED", "TERMINALIZED", "RECOVERED", "BUSY", "END"]
    scan_until: datetime
    at: datetime | None = None
    id: UUID | None = None
    claim: dict[str, object] | None = Field(default=None, repr=False)


class InboxProcessingResult(Result):
    code: Literal[
        "PROCESSED",
        "DUPLICATE",
        "IGNORED_NATIVE_OWNER_MESSAGE",
        "IGNORED_MESSAGE_EDITED",
        "IGNORED_MESSAGE_DELETED",
        "IGNORED_UNSUPPORTED",
        "MESSAGE_ID_CONFLICT",
        "CONVERSATION_IDENTITY_CONFLICT",
    ]
    inbox_id: UUID
    message_id: UUID | None
    status: Literal["PROCESSED", "IGNORED", "FAILED"]


class MutationInboxProcessingResult(Result):
    code: Literal["MATERIAL_PROCESSED"]
    inbox_id: UUID
    message_id: None
    status: Literal["PROCESSED"]


def parse_inbox_result(value: object) -> InboxProcessingResult | MutationInboxProcessingResult:
    if isinstance(value, dict) and value.get("code") == "MATERIAL_PROCESSED":
        return MutationInboxProcessingResult.model_validate(value)
    return InboxProcessingResult.model_validate(value)


class SendReceipt(Result):
    code: Literal["ACCEPTED", "REPLAY"]
    workspace_id: UUID
    receipt_id: UUID
    message_id: UUID
    outbox_id: UUID
    audit_event_id: UUID
    accepted_at: datetime
    request_fingerprint: str = Field(pattern="^[0-9a-f]{64}$", repr=False)


class SendPermit(Result):
    code: Literal["PERMITTED"]
    job_id: UUID
    claim_token: UUID = Field(repr=False)
    attempt_id: UUID = Field(repr=False)
    workspace_id: UUID
    connection_id: UUID
    provider: Literal["CONTROLLED", "TELEGRAM"]
    bot_identity: str = Field(repr=False)
    external_connection_id: str = Field(repr=False)
    chat_id: str = Field(repr=False)
    text: str = Field(repr=False)


class TerminalRejection(Result):
    code: Literal["NOT_ALLOWED", "UNAVAILABLE"]
    status: Literal["FAILED", "PENDING"]


class FinalizeResult(Result):
    code: Literal["FINALIZED", "ALREADY_FINALIZED"]
    status: Literal["SENT", "PENDING", "FAILED", "UNKNOWN"]
    job_id: UUID
    outbox_id: UUID
    attempt_id: UUID
    retry_after_seconds: int | None = None
    available_at: datetime | None = None
