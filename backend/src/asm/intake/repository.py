"""Narrow SQL capabilities, never caller-selected workspace authority."""

from uuid import UUID

from asm.intake.models import CasePage, IntakeProjection, IntakeReceipt
from asm.tenancy import TenantUnitOfWork


class IntakeRepository:
    def __init__(self, unit: TenantUnitOfWork):
        self.unit = unit

    async def summary(self, business: UUID, conversation: UUID) -> IntakeProjection:
        value = IntakeProjection.model_validate(
            await self.unit.intake_owner(business, conversation, "READ", "", {})
        )
        if (
            value.workspace_id != str(self.unit.context.workspace_id)
            or value.business_id != str(business)
            or value.conversation_id != str(conversation)
        ):
            raise ValueError("INTAKE_SCOPE")
        return value

    async def cases(self, business: UUID) -> CasePage:
        value = CasePage.model_validate(
            await self.unit.intake_owner(business, None, "CASES", "", {})
        )
        if value.workspace_id != str(self.unit.context.workspace_id) or value.business_id != str(
            business
        ):
            raise ValueError("INTAKE_SCOPE")
        return value

    async def command(
        self,
        business: UUID,
        conversation: UUID | None,
        operation: str,
        key: str,
        body: dict[str, object],
    ) -> IntakeReceipt:
        return IntakeReceipt.model_validate(
            await self.unit.intake_owner(business, conversation, operation, key, body)
        )
