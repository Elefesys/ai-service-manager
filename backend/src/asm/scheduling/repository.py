"""Read and change resource settings inside a scoped owner transaction."""

import json
from datetime import date
from uuid import UUID

from asm.scheduling.models import AvailabilityCommand, ScheduleSnapshot
from asm.tenancy import TenantUnitOfWork


class SchedulingRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    async def read(
        self, business_id: UUID, service_id: str, local_date: date | None = None
    ) -> ScheduleSnapshot:
        state = await self.unit.scheduling_owner_read(business_id, service_id, local_date)
        return ScheduleSnapshot.model_validate_json(json.dumps(state, allow_nan=False))

    async def change(
        self, business_id: UUID, service_id: str, command: AvailabilityCommand
    ) -> None:
        await self.unit.scheduling_owner_command(
            business_id,
            service_id,
            command.action,
            command.model_dump(mode="json", exclude={"action"}),
        )
