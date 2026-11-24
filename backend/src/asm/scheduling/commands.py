"""Commands for issued scheduling options, reservation holds, and owner blocks."""

import json
import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BeforeValidator, Field, computed_field, model_validator

from asm.billing.validation import KEY_PATTERN, CanonicalUUID
from asm.configuration.models import ConfigurationModel
from asm.configuration.permissions import require_owner
from asm.scheduling.availability import calculate_windows
from asm.scheduling.models import (
    BookingProjection,
    Instant,
    LocalDate,
    ScheduleSnapshot,
    SessionBooking,
    TimeWindow,
    TimeZoneName,
    ZonedVisit,
)
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


class HoldResult(ZonedVisit):
    outcome: Literal["HELD", "EXPIRED", "RELEASED", "CONVERTED"]
    hold_id: CanonicalUUID
    allocation_id: CanonicalUUID
    expires_at: Instant

    @computed_field
    def message(self) -> str:
        if self.outcome == "HELD":
            deadline = self.expires_at.astimezone(ZoneInfo(self.timezone))
            return (
                f"Время удержано до {deadline:%d.%m.%Y %H:%M:%S} ({self.timezone}), "
                "запись не подтверждена."
            )
        return {
            "EXPIRED": "Срок удержания истёк.",
            "RELEASED": "Удержание снято.",
            "CONVERTED": "Запись подтверждена.",
        }[self.outcome]


class AppointmentResult(ZonedVisit):
    outcome: Literal["CONFIRMED"]
    appointment_id: CanonicalUUID
    hold_id: CanonicalUUID
    allocation_id: CanonicalUUID
    session_id: CanonicalUUID

    @computed_field
    def message(self) -> str:
        return "Запись подтверждена."


class ClientTime(ConfigurationModel):
    visit_start: Instant
    visit_end: Instant


class ClientOption(ClientTime):
    option_id: CanonicalUUID


class SelectionUnavailable(ConfigurationModel):
    outcome: Literal["OPTION_UNAVAILABLE", "SESSION_HELD"]
    date: LocalDate
    timezone: TimeZoneName | None


class AlternativeOptions(SelectionUnavailable):
    outcome: Literal["OPTION_UNAVAILABLE"] = "OPTION_UNAVAILABLE"
    expires_at: Instant | None
    windows: list[ClientOption] = Field(max_length=OFFER_OPTION_LIMIT)


class SessionHeld(SelectionUnavailable):
    outcome: Literal["SESSION_HELD"] = "SESSION_HELD"
    expires_at: None = None
    windows: list[ClientTime] = Field(max_length=OFFER_OPTION_LIMIT)


type SelectionResult = AppointmentResult | HoldResult | AlternativeOptions | SessionHeld


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


def _client_alternatives(offer: AvailabilityOffer) -> AlternativeOptions:
    windows: list[ClientOption] = []
    if offer.options:
        if offer.expires_at is None or offer.timezone is None or offer.offer_id is None:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        zone = ZoneInfo(offer.timezone)
        windows.extend(
            ClientOption(
                option_id=option.option_id,
                visit_start=option.visit_start.astimezone(zone),
                visit_end=option.visit_end.astimezone(zone),
            )
            for option in offer.options
        )
    return AlternativeOptions(
        date=offer.date,
        timezone=offer.timezone,
        windows=windows,
        expires_at=offer.expires_at,
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
    """Use the caller's transaction. Expose the selection result after its commit."""
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
    if outcome == "CONFIRMED":
        appointment = _stored(AppointmentResult, result)
        if terms.deposit.mode != "NONE" or appointment.session_id != selection.session_id:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        return appointment
    if outcome not in ("OPTION_UNAVAILABLE", "SESSION_HELD"):
        return _stored(HoldResult, result)
    if outcome == "OPTION_UNAVAILABLE" and "alternatives" in result:
        return _client_alternatives(_stored(AvailabilityOffer, result["alternatives"]))

    # Build alternatives from the current locked calendar, then save them
    # on the selection receipt before the same transaction commits.
    current = await store.client_state(selection, client_id, conversation_id, option_id)
    schedule = _stored(ScheduleSnapshot, current.get("schedule"))
    windows = calculate_windows(schedule, minutes)[:OFFER_OPTION_LIMIT]
    if outcome == "OPTION_UNAVAILABLE":
        saved = await store.alternatives(
            selection, client_id, conversation_id, option_id, key, windows
        )
        return _client_alternatives(_stored(AvailabilityOffer, saved))

    return SessionHeld(
        date=schedule.date,
        timezone=schedule.timezone,
        windows=[
            ClientTime(visit_start=window.visit_start, visit_end=window.visit_end)
            for window in windows
        ],
    )


async def read_booking(unit: TenantUnitOfWork, selection: SelectedSession) -> SessionBooking:
    await require_owner(unit)
    raw = await unit.scheduling_owner_booking(selection.model_dump(mode="json"))
    projection = _stored(BookingProjection, raw)
    if projection.session_id != selection.session_id:
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
    return SessionBooking(
        request_id=selection.request_id,
        quote_id=selection.quote_id,
        order_id=selection.order_id,
        session_id=projection.session_id,
        booking=projection.booking,
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
