"""Private LOCAL/TEST guarded consumer; no owner principal or provider callback."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from asm.conversations.turns import TurnSnapshot
from asm.messaging.models import manual_text
from asm.messaging.results import Result

GUARD_TEXT = "CONTROLLED GUARDS TEST"


class GuardedTurnSnapshot(TurnSnapshot):
    conversation_id: UUID
    client_id: UUID
    business_id: UUID
    activation_fence_seq: int = Field(gt=0, strict=True)
    resume_receipt_id: UUID
    consumer: Literal["CONTROLLED_GUARDS_V1"]


class GuardTextResult(Result):
    consumer: Literal["CONTROLLED_GUARDS_V1"] = "CONTROLLED_GUARDS_V1"
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$", strict=True)
    text: str = Field(repr=False, strict=True)

    @field_validator("text")
    @classmethod
    def exact_text(cls, value: str) -> str:
        return manual_text(value)


class GuardReceipt(Result):
    code: Literal["ACCEPTED", "STALE", "SUPERSEDED", "NOT_ALLOWED"]
    workspace_id: UUID
    job_id: UUID
    connection_id: UUID
    conversation_id: UUID
    client_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0, strict=True)
    resume_receipt_id: UUID
    input_control_generation: int = Field(gt=0, strict=True)
    activation_fence_seq: int = Field(gt=0, strict=True)
    input_context_version: int = Field(gt=0, strict=True)
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$", strict=True)
    consumer: Literal["CONTROLLED_GUARDS_V1"]
    request_fingerprint: str = Field(pattern="^[0-9a-f]{64}$", repr=False, strict=True)
    result_text: str = Field(repr=False, strict=True)
    accepted_at: datetime
    intent_context_version: int | None = Field(gt=0, strict=True)
    message_id: UUID | None
    outbox_id: UUID | None
    send_job_id: UUID | None

    @model_validator(mode="after")
    def intent_shape(self) -> Self:
        refs = (self.intent_context_version, self.message_id, self.outbox_id, self.send_job_id)
        if self.code == "ACCEPTED":
            if (
                any(ref is None for ref in refs)
                or self.intent_context_version != self.input_context_version + 1
            ):
                raise ValueError("Invalid accepted intent")
        elif any(ref is not None for ref in refs):
            raise ValueError("Rejected result contains an intent")
        manual_text(self.result_text)
        return self


class GuardProgress(Result):
    code: Literal["SUPERSEDED", "STALE", "NOT_ALLOWED", "ALREADY_ACCEPTED"]
    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0, strict=True)
    accepted_job_id: UUID | None
    message_id: UUID | None
    outbox_id: UUID | None
    send_job_id: UUID | None

    @model_validator(mode="after")
    def prior_intent(self) -> Self:
        refs = (self.accepted_job_id, self.message_id, self.outbox_id, self.send_job_id)
        if (self.code == "ALREADY_ACCEPTED" and any(ref is None for ref in refs)) or (
            self.code != "ALREADY_ACCEPTED" and any(ref is not None for ref in refs)
        ):
            raise ValueError("Invalid prior intent")
        return self


def consume_guarded(snapshot: GuardedTurnSnapshot) -> GuardTextResult:
    """Pure computation; admission and idempotency are owned by PostgreSQL."""
    if type(snapshot) is not GuardedTurnSnapshot:
        raise TypeError("A guarded snapshot is required")
    return GuardTextResult(snapshot_digest=snapshot.snapshot_digest, text=GUARD_TEXT)
