"""Read and change resource settings inside a scoped owner transaction."""

import json
from datetime import date
from uuid import UUID

from asm.scheduling.models import LocalSpan, PolicyInput, ScheduleSnapshot, WeeklyInterval
from asm.tenancy import TenantUnitOfWork


class SchedulingRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    async def read(
        self, business_id: UUID, service_id: str, local_date: date | None = None
    ) -> ScheduleSnapshot:
        state = await self.unit.scheduling_owner_read(business_id, service_id, local_date)
        return ScheduleSnapshot.model_validate_json(json.dumps(state, allow_nan=False))

    async def put_schedule(
        self,
        business_id: UUID,
        service_id: str,
        timezone: str,
        week: list[WeeklyInterval],
    ) -> None:
        await self.unit.scheduling_owner_command(
            business_id,
            service_id,
            "schedule",
            {"timezone": timezone, "week": [span.model_dump() for span in week]},
        )

    async def activate_policy(
        self, business_id: UUID, service_id: str, policy: PolicyInput
    ) -> None:
        await self.unit.scheduling_owner_command(
            business_id, service_id, "policy", policy.model_dump(exclude={"action"})
        )

    async def put_exception(
        self,
        business_id: UUID,
        service_id: str,
        local_date: date,
        windows: list[LocalSpan] | None,
    ) -> None:
        await self.unit.scheduling_owner_command(
            business_id,
            service_id,
            "exception",
            {
                "date": local_date.isoformat(),
                "windows": None if windows is None else [span.model_dump() for span in windows],
            },
        )
