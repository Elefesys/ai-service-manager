"""Closed capabilities; private completion needs a ticket, never owner authority."""

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from asm.knowledge.errors import KnowledgeCode, KnowledgeError, database_error
from asm.knowledge.models import (
    BuildApplication,
    EmbeddingCompletion,
    EmbeddingReservation,
    KnowledgeCommandResponse,
    KnowledgeOperation,
    KnowledgeProjection,
)
from asm.knowledge.validation import normalize_source, plan_source
from asm.messaging.database import physical_transaction
from asm.tenancy import TenantUnitOfWork


async def complete_embedding(
    connection: AsyncConnection, call: UUID, ticket: UUID, outcome: dict[str, Any]
) -> dict[str, Any]:
    """Accounting only: callable after authority loss, on a fresh runtime transaction.

    Tickets never cross the owner HTTP boundary. This does not apply vectors or
    authorize another request, and a lost completion ACK must not repeat HTTP.
    """
    try:
        await physical_transaction(connection)
        raw = (
            await connection.execute(
                text(
                    "SELECT platform.knowledge_embedding_complete(:call,:ticket,CAST(:body AS jsonb))"
                ),
                {
                    "call": call,
                    "ticket": ticket,
                    "body": json.dumps(outcome, ensure_ascii=False, allow_nan=False),
                },
            )
        ).scalar_one()
        result = EmbeddingCompletion.model_validate(raw)
        if result.call_id != str(call):
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
        return result.model_dump()
    except DBAPIError as error:
        raise database_error(error) from None
    except (ValidationError, ValueError, TypeError):
        raise KnowledgeError(KnowledgeCode.UNAVAILABLE) from None


class KnowledgeRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    def _scope(self, workspace: str, business: str, expected: UUID) -> None:
        if workspace != str(self.unit.context.workspace_id) or business != str(expected):
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE)

    async def state(self, business: UUID) -> KnowledgeProjection:
        value = KnowledgeProjection.model_validate(await self.unit.knowledge_owner_read(business))
        self._scope(value.workspace_id, value.business_id, business)
        for source in value.sources:
            head = source.head
            if (
                normalize_source(head.canonical_text) != head.canonical_text
                or hashlib.sha256(head.canonical_text.encode()).hexdigest() != head.canonical_sha256
                or source.preview.model_dump() != plan_source(head.canonical_text)
            ):
                raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
        return value

    async def command(
        self, business: UUID, operation: KnowledgeOperation, key: str, body: dict[str, Any]
    ) -> KnowledgeCommandResponse:
        value = KnowledgeCommandResponse.model_validate(
            await self.unit.knowledge_owner_command(business, operation, key, body)
        )
        self._scope(value.result.workspace_id, value.result.business_id, business)
        if value.result.operation != operation:
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
        return value

    async def reserve(self, business: UUID, build: UUID, batch: int) -> EmbeddingReservation:
        return EmbeddingReservation.model_validate(
            await self.unit.knowledge_build_reserve(business, build, batch)
        )

    async def apply(
        self, business: UUID, build: UUID, call: UUID, ticket: UUID, vectors: list[list[float]]
    ) -> BuildApplication:
        value = BuildApplication.model_validate(
            await self.unit.knowledge_build_apply(business, call, ticket, vectors)
        )
        if value.build_id != str(build):
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
        return value
