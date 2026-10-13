"""Owner decisions and private LOCAL/TEST producer. PostgreSQL owns authority."""

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Self
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from asm.auth.service import AuthService
from asm.billing.models import StrictModel
from asm.billing.validation import encode_cursor
from asm.conversations.escalation_http_models import (
    EscalationAcceptedResult,
    EscalationCancelRequest,
    EscalationCommandResponse,
    EscalationCursor,
    EscalationPage,
    EscalationResolveRequest,
    EscalationView,
    Operation,
    StatusFilter,
)
from asm.messaging.models import command_key
from asm.messaging.results import JobClaim, Result
from asm.tenancy import TenantUnitOfWork
from asm.tenancy.types import MembershipRole

if TYPE_CHECKING:
    from asm.messaging.database import MessagingDatabase

MARKER = "CONTROLLED ESCALATION TEST"


class EscalationPermission(StrEnum):
    READ = "escalations:read"
    DECIDE = "escalations:decide"


class EscalationCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    STALE_STATE = "STALE_STATE"
    ESCALATION_EXPIRED = "ESCALATION_EXPIRED"
    ESCALATION_FINAL = "ESCALATION_FINAL"
    VERSION_EXHAUSTED = "VERSION_EXHAUSTED"
    UNAVAILABLE = "UNAVAILABLE"


class EscalationError(Exception):
    def __init__(self, code: EscalationCode) -> None:
        self.code = code
        super().__init__(code.value)


async def require_escalation(unit: TenantUnitOfWork, permission: EscalationPermission) -> None:
    if type(permission) is not EscalationPermission or (
        await unit.messaging_membership_role() != MembershipRole.OWNER
    ):
        raise EscalationError(EscalationCode.ACCESS_DENIED)


def decision_fingerprint(
    workspace: UUID,
    actor: UUID,
    escalation: UUID,
    operation: Operation,
    request: EscalationCancelRequest,
) -> str:
    answer = request.answer_text if isinstance(request, EscalationResolveRequest) else None
    tail = "-1:" if answer is None else f"{len(answer.encode('utf-8'))}:{answer}"
    return hashlib.sha256(
        "\n".join(
            (
                "asm:m3:escalation_decision:v1",
                str(workspace),
                str(actor),
                str(escalation),
                request.expected_conversation_id,
                request.expected_client_id,
                operation,
                request.expected_escalation_version,
                request.expected_control_generation,
                request.expected_context_version,
                tail,
            )
        ).encode("utf-8")
    ).hexdigest()


class _Saved(StrictModel):
    code: Literal["ACCEPTED", "REPLAY"]
    result: EscalationAcceptedResult
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class OwnerEscalationService:
    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    async def read(self, token: str, workspace: UUID, escalation: UUID) -> EscalationView:
        async with self.auth.workspace(token, workspace) as unit:
            await require_escalation(unit, EscalationPermission.READ)
            try:
                result = EscalationView.model_validate(await unit.escalation_read(escalation))
            except ValidationError:
                raise EscalationError(EscalationCode.UNAVAILABLE) from None
            if result.workspace_id != str(workspace) or result.escalation_id != str(escalation):
                raise EscalationError(EscalationCode.UNAVAILABLE)
        return result

    async def list(
        self,
        token: str,
        workspace: UUID,
        limit: int,
        status: StatusFilter,
        cursor: EscalationCursor | None,
    ) -> EscalationPage:
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or status not in ("PENDING", "RESOLVED", "CANCELLED", "EXPIRED", "ALL")
        ):
            raise EscalationError(EscalationCode.INVALID_REQUEST)
        if cursor and (cursor.workspace_id != str(workspace) or cursor.status != status):
            raise EscalationError(EscalationCode.INVALID_REQUEST)
        async with self.auth.workspace(token, workspace) as unit:
            await require_escalation(unit, EscalationPermission.READ)
            raw = await unit.escalation_list(
                limit + 1,
                status,
                datetime.fromisoformat(cursor.created_at) if cursor else None,
                UUID(cursor.id) if cursor else None,
            )
            if not isinstance(raw, list) or len(raw) > limit + 1:
                raise EscalationError(EscalationCode.UNAVAILABLE)
            try:
                rows = [EscalationView.model_validate(row) for row in raw]
            except ValidationError:
                raise EscalationError(EscalationCode.UNAVAILABLE) from None
            if any(
                row.workspace_id != str(workspace) or (status != "ALL" and row.status != status)
                for row in rows
            ):
                raise EscalationError(EscalationCode.UNAVAILABLE)
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                next_cursor = encode_cursor(
                    EscalationCursor(
                        v=1,
                        endpoint="ESCALATIONS",
                        workspace_id=str(workspace),
                        direction="DESC",
                        status=status,
                        created_at=last.created_at,
                        id=last.escalation_id,
                    ).model_dump()
                )
            result = EscalationPage(items=rows[:limit], next_cursor=next_cursor)
        return result

    async def command(
        self,
        token: str,
        workspace: UUID,
        escalation: UUID,
        operation: Operation,
        request: EscalationCancelRequest,
        key: str,
    ) -> EscalationCommandResponse:
        command_key(key)
        if (
            (operation == "RESOLVE" and type(request) is not EscalationResolveRequest)
            or (operation == "CANCEL" and type(request) is not EscalationCancelRequest)
            or operation not in ("RESOLVE", "CANCEL")
        ):
            raise EscalationError(EscalationCode.INVALID_REQUEST)
        async with self.auth.workspace(token, workspace) as unit:
            await require_escalation(unit, EscalationPermission.DECIDE)
            expected_hash = decision_fingerprint(
                workspace, unit.context.actor.user_account_id, escalation, operation, request
            )
            raw = await unit.escalation_command(
                escalation,
                UUID(request.expected_conversation_id),
                UUID(request.expected_client_id),
                operation,
                key,
                int(request.expected_escalation_version),
                int(request.expected_control_generation),
                int(request.expected_context_version),
                request.answer_text if isinstance(request, EscalationResolveRequest) else None,
            )
            try:
                saved = _Saved.model_validate(raw)
            except ValidationError:
                raise EscalationError(EscalationCode.UNAVAILABLE) from None
            r = saved.result
            if (
                saved.request_fingerprint != expected_hash
                or r.workspace_id != str(workspace)
                or r.escalation_id != str(escalation)
                or r.conversation_id != request.expected_conversation_id
                or r.client_id != request.expected_client_id
                or r.operation != operation
                or r.previous_version != request.expected_escalation_version
                or int(r.accepted_context_version) != int(request.expected_context_version) + 1
                or r.control_generation != request.expected_control_generation
            ):
                raise EscalationError(EscalationCode.UNAVAILABLE)
            result = EscalationCommandResponse(outcome=saved.code, result=r)
        return result


class EscalationCreationResult(Result):
    code: Literal["ESCALATED"]
    workspace_id: UUID
    source_job_id: UUID
    escalation_id: UUID
    conversation_id: UUID
    client_id: UUID
    turn_id: UUID
    resume_receipt_id: UUID
    turn_revision: int = Field(gt=0, strict=True)
    input_context_version: int = Field(gt=0, strict=True)
    waiting_context_version: int = Field(gt=0, strict=True)
    control_generation: int = Field(gt=0, strict=True)
    context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_version: Literal[1]
    initial_status: Literal["PENDING"]
    created_at: datetime
    due_at: datetime
    second_reminder_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def origin(self) -> Self:
        if (
            self.waiting_context_version != self.input_context_version + 1
            or not self.created_at < self.due_at < self.second_reminder_at < self.expires_at
        ):
            raise ValueError("Invalid Escalation creation")
        return self


class EscalationProgress(Result):
    code: Literal[
        "ALREADY_ESCALATED",
        "WAITING_EXISTS",
        "ALREADY_ACCEPTED",
        "STALE",
        "SUPERSEDED",
        "NOT_ALLOWED",
    ]
    source_job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0, strict=True)
    escalation_id: UUID | None

    @model_validator(mode="after")
    def reference(self) -> Self:
        if (self.code in ("ALREADY_ESCALATED", "WAITING_EXISTS")) != (
            self.escalation_id is not None
        ):
            raise ValueError("Invalid Escalation progress")
        return self


class EscalationTimerResult(Result):
    job_id: UUID
    escalation_id: UUID
    step: Literal["REMIND_1", "REMIND_2", "EXPIRE"]
    status: Literal["SUCCEEDED", "DEAD"]
    error_code: Literal["INVALID_INPUT", "RETRY_EXHAUSTED"] | None
    outcome: Literal["REMINDED", "EXPIRED", "CANCELLED", "NOOP_TERMINAL"] | None
    recorded_at: datetime | None

    @model_validator(mode="after")
    def terminal(self) -> Self:
        if self.status == "DEAD":
            if self.error_code is None or self.outcome is not None or self.recorded_at is not None:
                raise ValueError("Invalid DEAD timer")
        elif self.error_code is not None or self.outcome is None or self.recorded_at is None:
            raise ValueError("Invalid successful timer")
        return self


class EscalationService:
    """The worker passes only its claim; no supplied Owner/context can grant creation."""

    def __init__(self, database: "MessagingDatabase") -> None:
        self.database = database

    async def request_for_turn(
        self, claim: JobClaim
    ) -> EscalationCreationResult | EscalationProgress:
        return await self.database.request_escalation(claim)
