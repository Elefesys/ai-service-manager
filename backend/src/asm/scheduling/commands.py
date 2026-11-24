"""Commands for issued scheduling options, reservation holds, and owner blocks."""

import json
import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BeforeValidator, Field, model_validator

from asm.billing.validation import KEY_PATTERN, CanonicalUUID
from asm.configuration.models import ConfigurationModel
from asm.configuration.permissions import require_owner
from asm.scheduling.availability import calculate_windows
from asm.scheduling.models import Instant, LocalDate, ScheduleSnapshot, TimeWindow, TimeZoneName
from asm.scheduling.offer_store import OfferStore
from asm.scheduling.service import (
    AcceptedMaterial,
    SelectedSession,
    accepted_minutes,
    selected_terms,
)
from asm.service_requests.errors import AffectedAllocation, ServiceRequestCode, ServiceRequestError
from asm.tenancy import TenantUnitOfWork

OFFER_OPTION_LIMIT = 8


class TrustedSchedulingClient(ConfigurationModel):
    """Identity supplied by the caller after verifying the client's action."""

    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID


class OfferedTime(TimeWindow):
    option_id: CanonicalUUID


class AvailabilityOffer(ConfigurationModel):
    offer_id: CanonicalUUID | None
    date: LocalDate
    timezone: TimeZoneName | None
    expires_at: Instant | None
    options: list[OfferedTime] = Field(max_length=OFFER_OPTION_LIMIT)


class HoldResult(ConfigurationModel):
    outcome: Literal["HELD", "EXPIRED", "RELEASED"]
    hold_id: CanonicalUUID
    allocation_id: CanonicalUUID
    timezone: TimeZoneName
    expires_at: Instant
    visit_start: Instant
    visit_end: Instant


class ClientTime(ConfigurationModel):
    visit_start: Instant
    visit_end: Instant


class SelectionUnavailable(ConfigurationModel):
    outcome: Literal["OPTION_UNAVAILABLE", "SESSION_HELD"]
    date: LocalDate
    timezone: TimeZoneName | None
    windows: list[ClientTime] = Field(max_length=OFFER_OPTION_LIMIT)


type SelectionResult = HoldResult | SelectionUnavailable


def _explicit_instant(value: object) -> object:
    if (
        isinstance(value, datetime)
        or isinstance(value, str)
        and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value,
        )
    ):
        return value
    raise ValueError("An absolute date and time with UTC offset is required")


BlockInstant = Annotated[Instant, BeforeValidator(_explicit_instant)]


class CalendarBlockInput(ConfigurationModel):
    start: BlockInstant
    end: BlockInstant

    @model_validator(mode="after")
    def forward(self) -> Self:
        try:
            start, end = self.start.astimezone(UTC), self.end.astimezone(UTC)
        except OverflowError:
            raise ValueError("Block interval is outside the supported date range") from None
        if start >= end:
            raise ValueError("Block must end after it starts")
        return self


class CalendarBlock(CalendarBlockInput):
    block_id: CanonicalUUID
    outcome: Literal["BLOCKED", "RELEASED"]


class BlockConflict(ConfigurationModel):
    outcome: Literal["CALENDAR_CONFLICT"]
    affected: list[AffectedAllocation]


def _stored[M: ConfigurationModel](model: type[M], value: object) -> M:
    try:
        return model.model_validate_json(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError):
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None


def _check_key(key: str) -> None:
    if re.fullmatch(KEY_PATTERN, key) is None:
        raise ServiceRequestError(ServiceRequestCode.INVALID_INPUT)


def _client_scope(
    unit: TenantUnitOfWork, client: TrustedSchedulingClient, selection: SelectedSession
) -> None:
    if (
        client.workspace_id != selection.workspace_id
        or client.workspace_id != str(unit.context.workspace_id)
        or client.business_id != selection.business_id
        or client.conversation_id != selection.conversation_id
        or client.client_id != selection.client_id
    ):
        raise ServiceRequestError(ServiceRequestCode.NOT_FOUND)


def _minutes(terms: AcceptedMaterial) -> int:
    minutes = accepted_minutes(terms)
    if minutes is None:
        raise ServiceRequestError(ServiceRequestCode.DURATION_UNAVAILABLE)
    return minutes


def _absolute_times(window: TimeWindow) -> tuple[datetime, ...]:
    return tuple(
        instant.astimezone(UTC)
        for instant in (window.visit_start, window.visit_end, window.busy_start, window.busy_end)
    )


async def issue_offer(
    unit: TenantUnitOfWork, selection: SelectedSession, day: date | None, key: str
) -> AvailabilityOffer:
    _check_key(key)
    terms = await selected_terms(unit, selection)
    store = OfferStore(unit)
    schedule = await store.owner_state(selection, day)
    windows = calculate_windows(schedule, _minutes(terms))[:OFFER_OPTION_LIMIT]
    saved = await store.issue(selection, day, key, windows)
    return _stored(AvailabilityOffer, saved)


async def select_option(
    unit: TenantUnitOfWork,
    client: TrustedSchedulingClient,
    selection: SelectedSession,
    option_id: UUID,
    key: str,
) -> SelectionResult:
    _check_key(key)
    _client_scope(unit, client, selection)
    store = OfferStore(unit)
    client_id, conversation_id = UUID(client.client_id), UUID(client.conversation_id)
    state = await store.client_state(selection, client_id, conversation_id, option_id)
    option = _stored(OfferedTime, state.get("option"))
    schedule = _stored(ScheduleSnapshot, state.get("schedule"))
    terms = _stored(AcceptedMaterial, state.get("terms"))
    minutes = _minutes(terms)
    # Use the same working-hours projection as preview. Allocation and expiry
    # checks use the locked resource and the current clock in the SQL write.
    offered_times = _absolute_times(option)
    work_hours = schedule.model_copy(update={"occupancy": []})
    eligible = any(
        _absolute_times(window) == offered_times
        for window in calculate_windows(work_hours, minutes)
    )
    result = await store.select(selection, client_id, conversation_id, option_id, key, eligible)
    outcome = result.get("outcome")
    if outcome not in ("OPTION_UNAVAILABLE", "SESSION_HELD"):
        return _stored(HoldResult, result)

    # The response contains the remaining times for this session alone.
    current = await store.client_state(selection, client_id, conversation_id, option_id)
    schedule = _stored(ScheduleSnapshot, current.get("schedule"))
    windows = calculate_windows(schedule, minutes)[:OFFER_OPTION_LIMIT]
    return SelectionUnavailable(
        outcome=outcome,
        date=schedule.date,
        timezone=schedule.timezone,
        windows=[
            ClientTime(visit_start=window.visit_start, visit_end=window.visit_end)
            for window in windows
        ],
    )


async def release_hold(
    unit: TenantUnitOfWork,
    client: TrustedSchedulingClient,
    selection: SelectedSession,
    hold_id: UUID,
    key: str,
) -> HoldResult:
    _check_key(key)
    _client_scope(unit, client, selection)
    result = await OfferStore(unit).release(
        selection, UUID(client.client_id), UUID(client.conversation_id), hold_id, key
    )
    return _stored(HoldResult, result)


async def create_block(
    unit: TenantUnitOfWork, business: UUID, block: CalendarBlockInput, key: str
) -> CalendarBlock | BlockConflict:
    _check_key(key)
    await require_owner(unit)
    result = await OfferStore(unit).block(business, key, start=block.start, end=block.end)
    if result.get("outcome") == "CALENDAR_CONFLICT":
        return _stored(BlockConflict, result)
    return _stored(CalendarBlock, result)


async def release_block(
    unit: TenantUnitOfWork, business: UUID, block_id: UUID, key: str
) -> CalendarBlock:
    _check_key(key)
    await require_owner(unit)
    result = await OfferStore(unit).block(business, key, block_id=block_id)
    return _stored(CalendarBlock, result)
