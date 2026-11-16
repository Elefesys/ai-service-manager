"""Authenticated owner operations return only after durable transaction acceptance."""

from uuid import UUID

from asm.auth.service import AuthService
from asm.configuration.permissions import require_owner
from asm.intake.duration_cases import compare_cases
from asm.intake.models import (
    CaseCommand,
    CasePage,
    CaseSearch,
    IntakeCommand,
    IntakeProjection,
    IntakeReceipt,
)
from asm.intake.repository import IntakeRepository


class IntakeService:
    def __init__(self, auth: AuthService):
        self.auth = auth

    async def summary(
        self, token: str, workspace: UUID, business: UUID, conversation: UUID
    ) -> IntakeProjection:
        async with self.auth.workspace(token, workspace) as unit:
            await require_owner(unit)
            value = await IntakeRepository(unit).summary(business, conversation)
        return value

    async def cases(self, token: str, workspace: UUID, business: UUID) -> CasePage:
        async with self.auth.workspace(token, workspace) as unit:
            await require_owner(unit)
            value = await IntakeRepository(unit).cases(business)
        return value

    async def search(
        self, token: str, workspace: UUID, business: UUID, query: dict[str, str]
    ) -> CaseSearch:
        page = await self.cases(token, workspace, business)
        return CaseSearch(
            workspace_id=page.workspace_id,
            business_id=page.business_id,
            items=compare_cases(page.items, query),
        )

    async def command(
        self,
        token: str,
        workspace: UUID,
        business: UUID,
        conversation: UUID | None,
        operation: str,
        key: str,
        body: IntakeCommand | CaseCommand,
    ) -> IntakeReceipt:
        async with self.auth.workspace(token, workspace) as unit:
            await require_owner(unit)
            value = await IntakeRepository(unit).command(
                business, conversation, operation, key, body.model_dump(mode="json")
            )
        return value
