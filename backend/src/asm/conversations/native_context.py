"""Live OWNER context capabilities; PostgreSQL owns CAS, replay and the atom."""

import hashlib
from uuid import UUID

from pydantic import ValidationError

from asm.auth.service import AuthService
from asm.billing.validation import decode_cursor
from asm.conversations.control import ControlCode, ControlError, ControlPermission, require_control
from asm.conversations.native_context_http_models import (
    HumanContextState,
    ObservationCursor,
    ObservationPage,
    ReconcileRequest,
    ReconcileResponse,
)
from asm.messaging.models import command_key

CURSOR_KEYS = ("v", "ws", "C", "Client", "P", "through_N", "after_N")


def decode_observation_cursor(token: str) -> ObservationCursor:
    """Validate original bytes before jsonb discards order/spelling/duplicate keys."""
    value = decode_cursor(token)
    if tuple(value) != CURSOR_KEYS:
        raise ValueError("Invalid observation cursor keys")
    return ObservationCursor.model_validate(value)


def reconcile_fingerprint(
    workspace: UUID, actor: UUID, conversation: UUID, body: ReconcileRequest
) -> str:
    fields = (
        str(workspace),
        str(actor),
        str(conversation),
        body.expected_client_id,
        body.expected_control_generation,
        body.expected_context_version,
        body.expected_policy_epoch,
        body.expected_observation_epoch,
        body.expected_ingress_checkpoint,
        body.expected_input_state_hash,
        body.expected_revision_id,
        body.disposition,
        body.text,
        body.source_media,
        body.attestation,
    )
    encoded = b"asm:m3:human_context_reconcile:v1\n" + b"".join(
        b"-1:\n"
        if value is None
        else str(len(value.encode("utf-8"))).encode("ascii") + b":" + value.encode("utf-8") + b"\n"
        for value in fields
    )
    return hashlib.sha256(encoded).hexdigest()


class OwnerNativeContextService:
    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    async def read(self, token: str, workspace: UUID, conversation: UUID) -> HumanContextState:
        async with self.auth.workspace(token, workspace) as unit:
            await require_control(unit, ControlPermission.CONTROL)
            try:
                result = HumanContextState.model_validate(
                    await unit.human_context_read(conversation)
                )
            except ValidationError:
                raise ControlError(ControlCode.UNAVAILABLE) from None
            if result.workspace_id != str(workspace) or result.conversation_id != str(conversation):
                raise ControlError(ControlCode.UNAVAILABLE)
        return result

    async def observations(
        self,
        token: str,
        workspace: UUID,
        conversation: UUID,
        limit: int,
        cursor: ObservationCursor | None,
    ) -> ObservationPage:
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or (cursor is not None and type(cursor) is not ObservationCursor)
        ):
            raise ControlError(ControlCode.INVALID_REQUEST)
        async with self.auth.workspace(token, workspace) as unit:
            await require_control(unit, ControlPermission.CONTROL)
            raw = await unit.human_context_observations(
                conversation, limit, cursor.model_dump() if cursor else None
            )
            try:
                result = ObservationPage.model_validate(raw)
                if len(result.items) > limit or (
                    cursor is not None
                    and (
                        result.through_epoch != cursor.through_N
                        or any(int(i.epoch) <= int(cursor.after_N) for i in result.items)
                    )
                ):
                    raise ValueError("Invalid page bounds")
                if result.next_cursor is not None:
                    next_ = decode_observation_cursor(result.next_cursor)
                    if (
                        next_.ws != str(workspace)
                        or next_.C != str(conversation)
                        or next_.through_N != result.through_epoch
                        or next_.after_N != result.items[-1].epoch
                        or (
                            cursor is not None
                            and (next_.Client, next_.P) != (cursor.Client, cursor.P)
                        )
                    ):
                        raise ValueError("Invalid next cursor")
            except (ValidationError, ValueError, TypeError, RecursionError):
                raise ControlError(ControlCode.UNAVAILABLE) from None
        return result

    async def reconcile(
        self, token: str, workspace: UUID, conversation: UUID, body: ReconcileRequest, key: str
    ) -> ReconcileResponse:
        command_key(key)
        if type(body) is not ReconcileRequest:
            raise ControlError(ControlCode.INVALID_REQUEST)
        async with self.auth.workspace(token, workspace) as unit:
            await require_control(unit, ControlPermission.CONTROL)
            raw = await unit.human_context_reconcile(conversation, key, body.model_dump())
            try:
                result = ReconcileResponse.model_validate(raw)
            except ValidationError:
                raise ControlError(ControlCode.UNAVAILABLE) from None
            r = result.result
            if (
                r.workspace_id,
                r.conversation_id,
                r.client_id,
                r.control_generation,
                r.previous_context_version,
                r.policy_epoch,
                r.observation_epoch,
                r.reviewed_ingress_checkpoint,
                r.reviewed_input_state_hash,
                r.previous_revision_id,
                r.disposition,
                r.source_media,
            ) != (
                str(workspace),
                str(conversation),
                body.expected_client_id,
                body.expected_control_generation,
                body.expected_context_version,
                body.expected_policy_epoch,
                body.expected_observation_epoch,
                body.expected_ingress_checkpoint,
                body.expected_input_state_hash,
                body.expected_revision_id,
                body.disposition,
                body.source_media,
            ):
                raise ControlError(ControlCode.UNAVAILABLE)
        # Never expose acceptance/replay before the outer transaction commits.
        return result
