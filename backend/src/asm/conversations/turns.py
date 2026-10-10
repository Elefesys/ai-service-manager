"""Private typed snapshots and an effect-free deterministic TEST consumer."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from asm.messaging.results import Result


class TurnFile(Result):
    file_id: UUID
    version: int = Field(gt=0)
    status: Literal["PENDING", "READY", "FAILED"]
    error_code: str | None
    wait_expired: bool


class TurnMember(Result):
    message_id: UUID
    message_version: int = Field(gt=0)
    content_type: Literal["TEXT", "IMAGE_REFERENCE"]
    ingress_at: datetime
    ingress_seq: int = Field(gt=0)
    file: TurnFile | None


class TurnSnapshot(Result):
    code: Literal["SNAPSHOT"]
    job_id: UUID
    workspace_id: UUID
    connection_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    context_version: int = Field(gt=0)
    control_generation: int = Field(gt=0)
    readiness: Literal["COMPLETE", "PARTIAL"]
    members: tuple[TurnMember, ...] = Field(min_length=1, max_length=64)
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$")


class TurnProgress(Result):
    code: Literal["GROUPED", "WAITING_MEDIA", "SUPERSEDED"]
    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)


class ConsumerResult(Result):
    consumer: Literal["TURN_TEST_V1"] = "TURN_TEST_V1"
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$")
    member_count: int = Field(ge=1, le=64)
    ready_file_count: int = Field(ge=0, le=64)
    wait_expired_count: int = Field(ge=0, le=64)


class ConsumerReceipt(Result):
    code: Literal["OBSERVED", "STALE"]
    job_id: UUID
    workspace_id: UUID
    connection_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    consumer: Literal["TURN_TEST_V1"]
    input_context_version: int = Field(gt=0)
    input_control_generation: int = Field(gt=0)
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$")
    accepted_at: datetime
    result: ConsumerResult


def consume(snapshot: TurnSnapshot) -> ConsumerResult:
    """Pure computation over saved refs. It cannot issue a send or fetch media."""
    return ConsumerResult(
        snapshot_digest=snapshot.snapshot_digest,
        member_count=len(snapshot.members),
        ready_file_count=sum(
            m.file is not None and m.file.status == "READY" for m in snapshot.members
        ),
        wait_expired_count=sum(
            m.file is not None and m.file.wait_expired for m in snapshot.members
        ),
    )
