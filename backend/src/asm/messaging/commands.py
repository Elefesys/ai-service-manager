"""Append-only Owner intention and bounded, private kernel reads."""

from typing import cast
from uuid import UUID

from asm.messaging.database import require_uuid
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import command_key, manual_text, text_fingerprint
from asm.messaging.policy import Permission, require
from asm.messaging.results import SendReceipt
from asm.tenancy import AuthenticatedAccount, TenantDatabase, TenantUnitOfWork


async def request_manual_text(
    owner_unit: TenantUnitOfWork,
    conversation_id: UUID,
    exact_text: str,
    key: str,
) -> SendReceipt:
    await require(owner_unit, Permission.SEND)
    require_uuid(conversation_id)
    value, key = manual_text(exact_text), command_key(key)
    expected = text_fingerprint(
        owner_unit.context.workspace_id,
        owner_unit.context.actor.user_account_id,
        conversation_id,
        value,
    )
    result = SendReceipt.model_validate(
        await owner_unit.messaging_request_text(conversation_id, value, key)
    )
    if result.request_fingerprint != expected:
        raise MessagingError(Code.INVALID_INPUT)
    return result


async def send_manual_text(
    database: TenantDatabase,
    actor: AuthenticatedAccount,
    workspace_id: UUID,
    correlation_id: UUID,
    conversation_id: UUID,
    exact_text: str,
    key: str,
) -> SendReceipt:
    async with database.transaction(actor, workspace_id, correlation_id) as unit:
        result = await request_manual_text(unit, conversation_id, exact_text, key)
    # A receipt is accepted only once the enclosing command transaction commits.
    return result


class OwnerRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    @staticmethod
    def _limit(value: int) -> None:
        if type(value) is not int or not 1 <= value <= 100:
            raise MessagingError(Code.INVALID_INPUT)

    async def conversations(self, limit: int = 100) -> tuple[dict[str, object], ...]:
        await require(self.unit, Permission.READ)
        self._limit(limit)
        return tuple(await self.unit.messaging_conversations(limit))

    async def messages(
        self, conversation_id: UUID, limit: int = 100
    ) -> tuple[dict[str, object], ...]:
        await require(self.unit, Permission.READ)
        require_uuid(conversation_id)
        self._limit(limit)
        return tuple(await self.unit.messaging_messages(conversation_id, limit))

    async def delivery(self, message_id: UUID) -> dict[str, object]:
        await require(self.unit, Permission.READ)
        require_uuid(message_id)
        return cast(dict[str, object], await self.unit.messaging_delivery(message_id))

    async def inbox(self, inbox_id: UUID) -> dict[str, object]:
        await require(self.unit, Permission.READ)
        require_uuid(inbox_id)
        return cast(dict[str, object], await self.unit.messaging_inbox(inbox_id))
