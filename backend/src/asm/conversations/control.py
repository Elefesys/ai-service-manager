"""Owner CONTROL commands. Database locks, fingerprint and commit own admission."""

import hashlib
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import ValidationError

from asm.auth.service import AuthService
from asm.billing.models import StrictModel
from asm.billing.service import MANUAL_SEND_KEY, EntitlementService
from asm.conversations.http_models import (
    ControlAcceptedResult,
    ControlCommandRequest,
    ControlCommandResponse,
    ControlOperation,
    ControlStateResponse,
)
from asm.messaging.models import command_key
from asm.messaging.policy import Permission, require
from asm.tenancy import TenantUnitOfWork
from asm.tenancy.types import MembershipRole


class ControlPermission(StrEnum):
    CONTROL = "conversations:control"


class ControlCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    STALE_STATE = "STALE_STATE"
    NOT_ALLOWED = "NOT_ALLOWED"
    CONTROL_VERSION_EXHAUSTED = "CONTROL_VERSION_EXHAUSTED"
    UNAVAILABLE = "UNAVAILABLE"


class ControlError(Exception):
    def __init__(self, code: ControlCode) -> None:
        self.code = code
        super().__init__(code.value)


async def require_control(unit: TenantUnitOfWork, permission: ControlPermission) -> None:
    if type(permission) is not ControlPermission or (
        await unit.messaging_membership_role() != MembershipRole.OWNER
    ):
        raise ControlError(ControlCode.ACCESS_DENIED)


def control_fingerprint(
    workspace: UUID,
    actor: UUID,
    conversation: UUID,
    request: ControlCommandRequest,
    operation: ControlOperation,
) -> str:
    return hashlib.sha256(
        "\n".join(
            (
                "asm:m3:conversation_control:v1",
                str(workspace),
                str(actor),
                str(conversation),
                request.expected_client_id,
                operation,
                request.expected_control_generation,
                request.expected_context_version,
            )
        ).encode("utf-8")
    ).hexdigest()


class _New(StrictModel):
    code: Literal["NEW"]
    request_fingerprint: str


class _Saved(StrictModel):
    code: Literal["ACCEPTED", "REPLAY"]
    result: ControlAcceptedResult
    request_fingerprint: str


def _saved(
    raw: object,
    fingerprint: str,
    workspace: UUID,
    conversation: UUID,
    request: ControlCommandRequest,
    operation: ControlOperation,
) -> ControlCommandResponse:
    try:
        saved = _Saved.model_validate(raw)
    except ValidationError:
        raise ControlError(ControlCode.UNAVAILABLE) from None
    result = saved.result
    if (
        saved.request_fingerprint != fingerprint
        or result.workspace_id != str(workspace)
        or result.conversation_id != str(conversation)
        or result.client_id != request.expected_client_id
        or result.operation != operation
        or result.previous_generation != request.expected_control_generation
        or result.context_version != request.expected_context_version
    ):
        raise ControlError(ControlCode.UNAVAILABLE)
    return ControlCommandResponse(outcome=saved.code, result=result)


class OwnerControlService:
    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    async def read(self, token: str, workspace: UUID, conversation: UUID) -> ControlStateResponse:
        async with self.auth.workspace(token, workspace) as unit:
            await require(unit, Permission.READ)
            result = ControlStateResponse.model_validate(
                await unit.conversation_control_read(conversation)
            )
            if result.workspace_id != str(workspace) or result.conversation_id != str(conversation):
                raise ControlError(ControlCode.UNAVAILABLE)
        return result

    async def command(
        self,
        token: str,
        workspace: UUID,
        conversation: UUID,
        operation: ControlOperation,
        request: ControlCommandRequest,
        key: str,
    ) -> ControlCommandResponse:
        key = command_key(key)
        if operation not in ("TAKEOVER", "RESUME"):
            raise ControlError(ControlCode.INVALID_REQUEST)
        async with self.auth.workspace(token, workspace) as unit:
            await require_control(unit, ControlPermission.CONTROL)
            fingerprint = control_fingerprint(
                workspace, unit.context.actor.user_account_id, conversation, request, operation
            )
            arguments = (
                conversation,
                UUID(request.expected_client_id),
                operation,
                key,
                int(request.expected_control_generation),
                int(request.expected_context_version),
            )
            prepared = await unit.conversation_control_prepare(*arguments)
            if isinstance(prepared, dict) and prepared.get("code") == "REPLAY":
                result = _saved(prepared, fingerprint, workspace, conversation, request, operation)
            else:
                try:
                    new = _New.model_validate(prepared)
                except ValidationError:
                    raise ControlError(ControlCode.UNAVAILABLE) from None
                if new.request_fingerprint != fingerprint:
                    raise ControlError(ControlCode.UNAVAILABLE)
                if operation == "RESUME":
                    decision = EntitlementService().evaluate_product(
                        workspace, dict(await unit.post_lock_product_snapshot()), MANUAL_SEND_KEY
                    )
                    if decision.type != "ENABLED":
                        raise ControlError(ControlCode.NOT_ALLOWED)
                result = _saved(
                    await unit.conversation_control_execute(*arguments),
                    fingerprint,
                    workspace,
                    conversation,
                    request,
                    operation,
                )
        # Both ACCEPTED and REPLAY are returned only after the outer commit succeeds.
        return result
