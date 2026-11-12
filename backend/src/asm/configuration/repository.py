"""Typed capability results on the caller's trusted tenant transaction."""

from typing import Literal
from uuid import UUID

from asm.configuration.errors import ConfigurationCode, ConfigurationError
from asm.configuration.models import ActiveProjection, CommandResponse, DraftState
from asm.configuration.validation import validate_bundle
from asm.tenancy import TenantUnitOfWork


class ConfigurationRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    def _scope(self, workspace: str, business: str, expected: UUID) -> None:
        if workspace != str(self.unit.context.workspace_id) or business != str(expected):
            raise ConfigurationError(ConfigurationCode.UNAVAILABLE)

    async def draft(self, business: UUID) -> DraftState:
        value = DraftState.model_validate(await self.unit.configuration_owner_read(business))
        self._scope(value.workspace_id, value.business_id, business)
        return value

    async def active(self, business: UUID) -> ActiveProjection:
        value = ActiveProjection.model_validate(await self.unit.configuration_active_read(business))
        self._scope(value.workspace_id, value.business_id, business)
        if value.bundle is not None and not validate_bundle(value.bundle).valid:
            raise ConfigurationError(ConfigurationCode.UNAVAILABLE)
        return value

    async def command(
        self,
        business: UUID,
        operation: Literal["EDIT", "PUBLISH", "ROLLBACK"],
        key: str,
        body: dict[str, object],
    ) -> CommandResponse:
        value = CommandResponse.model_validate(
            await self.unit.configuration_command(business, operation, key, body)
        )
        self._scope(value.result.workspace_id, value.result.business_id, business)
        if value.result.operation != operation:
            raise ConfigurationError(ConfigurationCode.UNAVAILABLE)
        return value
