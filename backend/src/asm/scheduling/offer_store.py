"""Persist scheduling commands through scoped PostgreSQL capabilities."""

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from asm.scheduling.models import ScheduleSnapshot, TimeWindow
from asm.scheduling.service import SelectedSession
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.tenancy import TenantUnitOfWork


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
    return value


class OfferStore:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    async def owner_state(self, selection: SelectedSession, day: date | None) -> ScheduleSnapshot:
        state = await self.unit.scheduling_offer(selection.model_dump(mode="json"), "state", day)
        return ScheduleSnapshot.model_validate_json(json.dumps(_object(state), allow_nan=False))

    async def issue(
        self, selection: SelectedSession, day: date | None, key: str, windows: list[TimeWindow]
    ) -> dict[str, Any]:
        return _object(
            await self.unit.scheduling_offer(
                selection.model_dump(mode="json"),
                "issue",
                day,
                key,
                [window.model_dump(mode="json") for window in windows],
            )
        )

    async def client_state(
        self, selection: SelectedSession, client_id: UUID, conversation_id: UUID, option_id: UUID
    ) -> dict[str, Any]:
        return _object(
            await self.unit.scheduling_client_action(
                selection.model_dump(mode="json"), client_id, conversation_id, "state", option_id
            )
        )

    async def select(
        self,
        selection: SelectedSession,
        client_id: UUID,
        conversation_id: UUID,
        option_id: UUID,
        key: str,
        eligible: bool,
    ) -> dict[str, Any]:
        return _object(
            await self.unit.scheduling_client_action(
                selection.model_dump(mode="json"),
                client_id,
                conversation_id,
                "select",
                option_id,
                key,
                eligible,
            )
        )

    async def release(
        self,
        selection: SelectedSession,
        client_id: UUID,
        conversation_id: UUID,
        hold_id: UUID,
        key: str,
    ) -> dict[str, Any]:
        return _object(
            await self.unit.scheduling_client_action(
                selection.model_dump(mode="json"),
                client_id,
                conversation_id,
                "release",
                hold_id,
                key,
            )
        )

    async def block(
        self,
        business: UUID,
        key: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        block_id: UUID | None = None,
    ) -> dict[str, Any]:
        return _object(await self.unit.scheduling_block(business, key, start, end, block_id))
