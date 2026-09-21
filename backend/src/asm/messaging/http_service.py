"""Owner API orchestration: replay first, bounded network between short auth units."""

import asyncio
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, model_validator

from asm.auth.service import AuthService
from asm.billing.errors import BillingUnavailable
from asm.billing.service import MANUAL_SEND_KEY, EntitlementService
from asm.billing.validation import encode_cursor, timestamp
from asm.messaging.commands import request_manual_text
from asm.messaging.errors import Code, MessagingError
from asm.messaging.http_models import (
    CollectionCursor,
    ConnectionResponse,
    ConnectionsPage,
    ConversationResponse,
    ConversationsPage,
    MessageResponse,
    MessagesCursor,
    MessagesPage,
)
from asm.messaging.models import command_key, identifier, manual_text, text_fingerprint
from asm.messaging.policy import Permission, require
from asm.messaging.results import Result, SendReceipt
from asm.tenancy import TenantUnitOfWork


class ConnectionProbe(Result):
    workspace_id: UUID
    connection_id: UUID
    bot_identity: str = Field(strict=True, repr=False)
    external_connection_id: str = Field(strict=True, repr=False)
    owner_user_id: str = Field(strict=True, repr=False)
    generation: int = Field(strict=True, ge=1)
    observation_version: int = Field(strict=True, ge=1)


class ConnectionObservation(Result):
    bot_identity: str | None = Field(strict=True, repr=False)
    external_connection_id: str | None = Field(strict=True, repr=False)
    owner_user_id: str | None = Field(strict=True, repr=False)
    is_enabled: bool | None = Field(strict=True)
    can_reply: bool | None = Field(strict=True)
    error_code: (
        Literal["DEPENDENCY_TIMEOUT", "DEPENDENCY_UNAVAILABLE", "NOT_ALLOWED", "INVALID_INPUT"]
        | None
    )

    @model_validator(mode="after")
    def coherent(self) -> Self:
        values = (
            self.bot_identity,
            self.external_connection_id,
            self.owner_user_id,
            self.is_enabled,
            self.can_reply,
        )
        if self.error_code is None:
            if any(value is None for value in values):
                raise ValueError("Incomplete observation")
            for value in values[:3]:
                identifier(value)
        elif any(value is not None for value in values):
            raise ValueError("Error observation contains provider data")
        return self

    @classmethod
    def unavailable(cls, *, timeout: bool = False) -> "ConnectionObservation":
        return cls(
            bot_identity=None,
            external_connection_id=None,
            owner_user_id=None,
            is_enabled=None,
            can_reply=None,
            error_code="DEPENDENCY_TIMEOUT" if timeout else "DEPENDENCY_UNAVAILABLE",
        )


class OwnerConnectionRefresher(Protocol):
    async def refresh(self, probe: ConnectionProbe) -> ConnectionObservation: ...


class NewIntention(Result):
    code: Literal["NEW"]
    provider: Literal["CONTROLLED", "TELEGRAM"]
    probe: ConnectionProbe | None

    @model_validator(mode="after")
    def binding(self) -> Self:
        if (self.provider == "TELEGRAM") != (self.probe is not None):
            raise ValueError("Invalid probe")
        return self


class ObservationResult(Result):
    code: Literal["OBSERVED", "UNAVAILABLE", "NOT_ALLOWED"]
    generation: int = Field(strict=True, ge=1)
    observation_version: int = Field(strict=True, ge=1)


async def prepare(
    unit: TenantUnitOfWork, conversation_id: UUID, value: str, key: str
) -> NewIntention | SendReceipt:
    await require(unit, Permission.SEND)
    raw = await unit.messaging_prepare_text(conversation_id, value, key)
    if raw["code"] == "NEW":
        new = NewIntention.model_validate(raw)
        if new.probe is not None and new.probe.workspace_id != unit.context.workspace_id:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        return new
    receipt = SendReceipt.model_validate(raw)
    expected = text_fingerprint(
        unit.context.workspace_id, unit.context.actor.user_account_id, conversation_id, value
    )
    if receipt.code != "REPLAY" or receipt.request_fingerprint != expected:
        raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
    return receipt


async def product_gate(unit: TenantUnitOfWork) -> None:
    # Locks precede the same validator/precedence used by the frozen R4 GET.
    await unit.messaging_lock_billing()
    decision = EntitlementService().evaluate_product(
        unit.context.workspace_id, dict(await unit.billing_snapshot()), MANUAL_SEND_KEY
    )
    if decision.type != "ENABLED":
        raise MessagingError(Code.NOT_ALLOWED)


class OwnerMessagingService:
    def __init__(
        self,
        auth: AuthService,
        environment: Literal["LOCAL", "TEST"],
        telegram: OwnerConnectionRefresher | None,
    ) -> None:
        self.auth, self.environment, self.telegram = auth, environment, telegram

    async def send(
        self, token: str, workspace: UUID, conversation: UUID, value: str, key: str
    ) -> SendReceipt:
        value, key = manual_text(value), command_key(key)
        async with self.auth.workspace(token, workspace) as unit:
            first = await prepare(unit, conversation, value, key)
            if isinstance(first, SendReceipt):
                result = first
            elif first.provider == "CONTROLLED":
                if self.environment not in ("LOCAL", "TEST"):
                    raise MessagingError(Code.NOT_ALLOWED)
                await product_gate(unit)
                result = await request_manual_text(unit, conversation, value, key)
            else:
                result = None
        if result is not None:
            return result
        if not isinstance(first, NewIntention) or first.probe is None:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        # Both the tenant checkout and shared auth/session lock have been released.
        observation = ConnectionObservation.unavailable()
        if self.telegram is not None:
            try:
                async with asyncio.timeout(5):
                    observation = await self.telegram.refresh(first.probe)
            except TimeoutError:
                observation = ConnectionObservation.unavailable(timeout=True)
        failure: MessagingError | BillingUnavailable | None = None
        async with self.auth.workspace(token, workspace) as unit:
            second = await prepare(unit, conversation, value, key)
            if isinstance(second, SendReceipt):
                result = second
            else:
                if (
                    second.probe is None
                    or second.probe.connection_id != first.probe.connection_id
                    or second.probe.workspace_id != first.probe.workspace_id
                ):
                    raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
                observed = ObservationResult.model_validate(
                    await unit.telegram_owner_observe(
                        conversation,
                        first.probe.generation,
                        first.probe.observation_version,
                        observation.model_dump(),
                    )
                )
                if observed.code != "OBSERVED":
                    failure = MessagingError(
                        Code.NOT_ALLOWED
                        if observed.code == "NOT_ALLOWED"
                        else Code.DEPENDENCY_UNAVAILABLE
                    )
                else:
                    try:
                        await product_gate(unit)
                    except (MessagingError, BillingUnavailable) as error:
                        # A bounded rejection deliberately commits the new observation.
                        failure = error
                    if failure is None:
                        result = await request_manual_text(unit, conversation, value, key)
        if failure is not None:
            raise failure
        if result is None:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        return result


_DATES = frozenset(
    ("created_at", "occurred_at", "observed_at", "reply_window_expires_at", "completed_at")
)


def wire_dates(row: Mapping[str, Any]) -> dict[str, Any]:
    """Format only timestamp fields of the exact SQL projection, without adding fields."""
    result = dict(row)
    for key, value in result.items():
        if key in _DATES and value is not None:
            result[key] = timestamp(
                datetime.fromisoformat(value) if isinstance(value, str) else value
            )
        elif isinstance(value, Mapping):
            result[key] = wire_dates(value)
    return result


class OwnerAPIRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    @staticmethod
    def anchor(
        cursor: CollectionCursor | MessagesCursor | None,
    ) -> tuple[datetime | None, UUID | None]:
        return (
            (datetime.fromisoformat(cursor.created_at), UUID(cursor.id))
            if cursor is not None
            else (None, None)
        )

    def next_cursor(
        self,
        endpoint: Literal["CHANNEL_CONNECTIONS", "CONVERSATIONS", "MESSAGES"],
        item: ConnectionResponse | ConversationResponse | MessageResponse,
        conversation: UUID | None = None,
    ) -> str:
        if isinstance(item, ConnectionResponse):
            identity = item.connection_id
        elif isinstance(item, ConversationResponse):
            identity = item.conversation_id
        else:
            identity = item.message_id
        value: dict[str, Any] = {
            "v": 1,
            "endpoint": endpoint,
            "workspace_id": str(self.unit.context.workspace_id),
            "direction": "DESC",
            "created_at": item.created_at,
            "id": identity,
        }
        if conversation is not None:
            value["conversation_id"] = str(conversation)
        return encode_cursor(value)

    async def connections(self, limit: int, cursor: CollectionCursor | None) -> ConnectionsPage:
        await require(self.unit, Permission.READ)
        rows = await self.unit.messaging_connections_page(limit + 1, *self.anchor(cursor))
        items = [ConnectionResponse.model_validate(wire_dates(row)) for row in rows[:limit]]
        return ConnectionsPage(
            items=items,
            next_cursor=self.next_cursor("CHANNEL_CONNECTIONS", items[-1])
            if len(rows) > limit
            else None,
        )

    async def conversations(self, limit: int, cursor: CollectionCursor | None) -> ConversationsPage:
        await require(self.unit, Permission.READ)
        rows = await self.unit.messaging_conversations_page(limit + 1, *self.anchor(cursor))
        items = [ConversationResponse.model_validate(wire_dates(row)) for row in rows[:limit]]
        return ConversationsPage(
            items=items,
            next_cursor=self.next_cursor("CONVERSATIONS", items[-1]) if len(rows) > limit else None,
        )

    async def messages(
        self, conversation: UUID, limit: int, cursor: MessagesCursor | None
    ) -> MessagesPage:
        await require(self.unit, Permission.READ)
        rows = await self.unit.messaging_messages_page(
            conversation, limit + 1, *self.anchor(cursor)
        )
        items = [MessageResponse.model_validate(wire_dates(row)) for row in rows[:limit]]
        return MessagesPage(
            items=items,
            next_cursor=self.next_cursor("MESSAGES", items[-1], conversation)
            if len(rows) > limit
            else None,
        )
