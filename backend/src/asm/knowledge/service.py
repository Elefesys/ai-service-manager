"""Finite owner build: committed reserve, controlled HTTP, accounting, fresh apply."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from asm.auth.service import AuthService
from asm.knowledge.embeddings import EmbeddingClient, EmbeddingFailure, unavailable, validate_wire
from asm.knowledge.errors import KnowledgeCode, KnowledgeError
from asm.knowledge.models import (
    ConfirmSource,
    CreateBuild,
    KnowledgeCommandResponse,
    KnowledgeOperation,
    KnowledgeOwnerState,
    KnowledgeRequest,
    PublishKnowledge,
    RollbackKnowledge,
    SaveSource,
    WithdrawSource,
)
from asm.knowledge.repository import KnowledgeRepository, complete_embedding
from asm.tenancy import MembershipRole


class KnowledgeService:
    def __init__(self, auth: AuthService, embeddings: EmbeddingClient | None = None) -> None:
        if embeddings is not None and type(embeddings) is not EmbeddingClient:
            raise ValueError("CONTROLLED_EMBEDDING_CLIENT_REQUIRED")
        self.auth = auth
        self.embeddings = embeddings if embeddings is not None else EmbeddingClient()

    @asynccontextmanager
    async def _owner(self, token: str, workspace: UUID) -> AsyncIterator[KnowledgeRepository]:
        try:
            async with self.auth.workspace(token, workspace) as unit:
                if await unit.billing_membership_role() is not MembershipRole.OWNER:
                    raise KnowledgeError(KnowledgeCode.ACCESS_DENIED)
                yield KnowledgeRepository(unit)
        except (SQLAlchemyError, ValidationError, TimeoutError):
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE) from None

    async def state(self, token: str, workspace: UUID, business: UUID) -> KnowledgeOwnerState:
        async with self._owner(token, workspace) as repository:
            state = await repository.state(business)
        return KnowledgeOwnerState.model_validate(
            state.model_dump()
            | {"embedding_mode": "CONTROLLED" if self.embeddings.enabled else "DISABLED"}
        )

    async def command(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        operation: KnowledgeOperation,
        key: str,
        body: KnowledgeRequest,
        *,
        source: UUID | None = None,
    ) -> KnowledgeCommandResponse:
        expected = {
            "KNOWLEDGE_SAVE": SaveSource,
            "KNOWLEDGE_CONFIRM": ConfirmSource,
            "KNOWLEDGE_REVOKE": WithdrawSource,
            "KNOWLEDGE_DELETE": WithdrawSource,
            "KNOWLEDGE_BUILD_CREATE": CreateBuild,
            "KNOWLEDGE_PUBLISH": PublishKnowledge,
            "KNOWLEDGE_ROLLBACK": RollbackKnowledge,
        }
        scoped = operation in {"KNOWLEDGE_CONFIRM", "KNOWLEDGE_REVOKE", "KNOWLEDGE_DELETE"}
        if type(body) is not expected[operation] or scoped != (source is not None):
            raise KnowledgeError(KnowledgeCode.INVALID_INPUT)
        payload = body.model_dump()
        if source is not None:
            payload["source_id"] = str(source)
        async with self._owner(token, workspace) as repository:
            value = await repository.command(business, operation, key, payload)
        if operation == "KNOWLEDGE_BUILD_CREATE" and value.outcome == "ACCEPTED":
            if value.result.build_id is None:
                raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
            try:
                async with asyncio.timeout(30):
                    await self._build(token, workspace, business, UUID(value.result.build_id))
            except TimeoutError:
                raise KnowledgeError(KnowledgeCode.UNAVAILABLE) from None
        # This is the immutable creation receipt, not a build-state projection.
        return value

    async def _complete(self, call: UUID, ticket: UUID, outcome: dict[str, Any]) -> dict[str, Any]:
        try:
            # Deliberately no authenticated()/workspace() here. Accounting must
            # survive session/membership revocation while HTTP was in progress.
            async with self.auth.store.transaction() as connection:
                result = await complete_embedding(connection, call, ticket, outcome)
            return result
        except (SQLAlchemyError, ValidationError, TimeoutError):
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE) from None

    async def _build(self, token: str, workspace: UUID, business: UUID, build: UUID) -> None:
        async with self._owner(token, workspace) as repository:
            state = await repository.state(business)
        current = next((item for item in state.builds if item.build_id == str(build)), None)
        if current is None:
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
        # Same manifest under a new key may deduplicate to an old terminal or
        # in-progress build. It does not grant a new attempt.
        if current.state != "PLANNED":
            return
        batches = (current.chunk_count + 7) // 8
        if not 1 <= batches <= 4:
            raise KnowledgeError(KnowledgeCode.UNAVAILABLE)
        for batch in range(batches):
            async with self._owner(token, workspace) as repository:
                reservation = await repository.reserve(business, build, batch)
            if reservation.status == "REPLAY":
                return
            assert reservation.ticket is not None and reservation.wire is not None
            call, ticket = UUID(reservation.call_id), UUID(reservation.ticket)
            try:
                try:
                    validate_wire(reservation.wire)
                    outcome = await self.embeddings.complete(
                        reservation.wire,
                        deadline=datetime.strptime(
                            reservation.deadline, "%Y-%m-%dT%H:%M:%S.%fZ"
                        ).replace(tzinfo=UTC),
                        wire_sha256=reservation.wire_sha256,
                    )
                except EmbeddingFailure as error:
                    outcome = unavailable(error.code)
                completed = await self._complete(call, ticket, outcome)
            except asyncio.CancelledError:
                # Finite best effort; never regenerate or resend after cancellation.
                try:
                    async with asyncio.timeout(1):
                        await self._complete(call, ticket, unavailable("CANCELLED", unknown=True))
                except (Exception, asyncio.CancelledError):
                    pass
                raise
            if outcome["kind"] != "SUCCESS" or completed["state"] != "SUCCESS":
                return
            async with self._owner(token, workspace) as repository:
                applied = await repository.apply(business, build, call, ticket, outcome["vectors"])
            if not applied.applied or applied.state not in {"BUILDING", "READY"}:
                return
            if applied.state == "READY":
                return
