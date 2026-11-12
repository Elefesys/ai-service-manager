"""Owner orchestration; return only after the capability's outer commit."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from asm.auth.service import AuthService
from asm.configuration.errors import ConfigurationCode, ConfigurationError
from asm.configuration.models import (
    ActiveProjection,
    CommandResponse,
    DraftState,
    EditDraft,
    Preview,
    Publish,
    Rollback,
    ServicePreview,
)
from asm.configuration.permissions import require_owner
from asm.configuration.repository import ConfigurationRepository
from asm.configuration.validation import validate_bundle


class ConfigurationService:
    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    @asynccontextmanager
    async def _owner(self, token: str, workspace: UUID) -> AsyncIterator[ConfigurationRepository]:
        try:
            async with self.auth.workspace(token, workspace) as unit:
                await require_owner(unit)
                yield ConfigurationRepository(unit)
        except (SQLAlchemyError, ValidationError):
            raise ConfigurationError(ConfigurationCode.UNAVAILABLE) from None

    async def draft(self, token: str, workspace: UUID, business: UUID) -> DraftState:
        async with self._owner(token, workspace) as repository:
            value = await repository.draft(business)
        return value

    async def active(self, token: str, workspace: UUID, business: UUID) -> ActiveProjection:
        async with self._owner(token, workspace) as repository:
            value = await repository.active(business)
        return value

    async def preview(self, token: str, workspace: UUID, business: UUID) -> Preview:
        state = await self.draft(token, workspace, business)
        result = validate_bundle(state.bundle)
        services = []
        if state.bundle is not None:
            for service in state.bundle.services:
                handoff = (
                    not result.valid
                    or any(
                        i.severity == "WARNING" and i.path.startswith(f"services.{service.id}.")
                        for i in result.issues
                    )
                    or any(
                        r.kind == "OWNER_HANDOFF"
                        and r.value is True
                        and r.service_id in (None, service.id)
                        for r in state.bundle.rules
                    )
                )
                services.append(
                    ServicePreview(
                        service_id=service.id,
                        active=service.active,
                        owner_handoff=handoff,
                    )
                )
        return Preview(
            state=state, validation=result, services=services, structured_rules_authoritative=True
        )

    async def command(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        operation: Literal["EDIT", "PUBLISH", "ROLLBACK"],
        key: str,
        body: EditDraft | Publish | Rollback,
    ) -> CommandResponse:
        async with self._owner(token, workspace) as repository:
            value = await repository.command(business, operation, key, body.model_dump())
        return value
