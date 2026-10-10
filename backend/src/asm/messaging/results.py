"""Private typed kernel results, not new messaging HTTP DTOs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class InboxReceipt(Result):
    code: Literal["ACCEPTED", "DUPLICATE"]
    workspace_id: UUID
    inbox_id: UUID
    job_id: UUID
    accepted_at: datetime


class JobClaim(Result):
    job_id: UUID
    kind: Literal["PROCESS_INBOX", "SEND_MANUAL_TEXT", "FETCH_IMAGE", "PROCESS_TURN"]
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
    step: Literal["GROUP", "MEDIA", "TEST_CONSUME"]


def parse_claim(value: object) -> JobClaim:
    if isinstance(value, dict) and value.get("kind") == "PROCESS_TURN":
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
