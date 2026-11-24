"""Owner scheduling settings and a computed session availability projection."""

from collections.abc import Sequence
from datetime import date
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BeforeValidator,
    Field,
    field_validator,
    model_validator,
)

from asm.billing.validation import CanonicalUUID
from asm.configuration.models import ConfigurationModel, DepositPolicy, Nonblank, OccupiedMinutes


def calendar_date(value: object) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    raise ValueError("Local date requires YYYY-MM-DD")


def zone_name(value: str) -> str:
    if value in {"localtime", "posixrules"} or value.startswith(("posix/", "right/")):
        raise ValueError("IANA time zone required")
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("IANA time zone required") from None
    return value


LocalDate = Annotated[date, BeforeValidator(calendar_date)]
TimeZoneName = Annotated[str, Field(min_length=1, max_length=128), AfterValidator(zone_name)]
Instant = Annotated[AwareDatetime, Field(strict=False)]
ScheduleVersion = Annotated[int, Field(ge=0, le=9_007_199_254_740_991)]
AvailabilityReason = Literal[
    "NO_WORKING_HOURS", "NO_ACTIVE_POLICY", "DURATION_UNAVAILABLE", "DATE_CLOSED", "NO_WINDOWS"
]


class LocalSpan(ConfigurationModel):
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=1, le=1440)

    @model_validator(mode="after")
    def forward(self) -> Self:
        if self.end_minute <= self.start_minute:
            raise ValueError("Work interval must end after it starts")
        return self


class WeeklyInterval(LocalSpan):
    weekday: int = Field(ge=0, le=6)


class PolicyInput(ConfigurationModel):
    step_minutes: int = Field(ge=1, le=1440)
    buffer_before_minutes: int = Field(ge=0, le=1440)
    buffer_after_minutes: int = Field(ge=0, le=1440)
    minimum_notice_minutes: int = Field(ge=0, le=525600)
    horizon_days: int = Field(ge=1, le=365)
    offer_ttl_minutes: int = Field(ge=1, le=525600)
    hold_ttl_minutes: int = Field(ge=1, le=525600)


class PolicyView(PolicyInput):
    policy_id: CanonicalUUID


class DateException(ConfigurationModel):
    date: LocalDate
    windows: list[LocalSpan] = Field(max_length=1440)


class ScheduleSnapshot(ConfigurationModel):
    now: Instant
    date: LocalDate
    timezone: TimeZoneName | None
    resource_id: CanonicalUUID | None
    schedule_version: ScheduleVersion
    week: list[WeeklyInterval] = Field(max_length=10080)
    policy: PolicyView | None
    exception: DateException | None

    @property
    def working_intervals(self) -> Sequence[LocalSpan]:
        if self.exception is not None:
            return self.exception.windows
        weekday = self.date.weekday()
        return [span for span in self.week if span.weekday == weekday]


class TimeWindow(ConfigurationModel):
    visit_start: Instant
    visit_end: Instant
    busy_start: Instant
    busy_end: Instant


class AvailabilityPreview(ConfigurationModel):
    request_id: CanonicalUUID
    quote_id: CanonicalUUID
    order_id: CanonicalUUID
    session_id: CanonicalUUID
    service_name: Nonblank = Field(max_length=100)
    occupied_minutes: OccupiedMinutes | None
    duration_reference_id: CanonicalUUID | None
    deposit: DepositPolicy
    date: LocalDate
    timezone: TimeZoneName | None
    resource_id: CanonicalUUID | None
    schedule_version: ScheduleVersion
    week: list[WeeklyInterval]
    policy: PolicyView | None
    exception: DateException | None
    reason: AvailabilityReason | None
    windows: list[TimeWindow]


class ScheduleCommand(ConfigurationModel):
    action: Literal["schedule"]
    expected_version: ScheduleVersion
    timezone: TimeZoneName
    week: list[WeeklyInterval] = Field(max_length=10080)

    @field_validator("week")
    @classmethod
    def non_overlapping_week(cls, week: list[WeeklyInterval]) -> list[WeeklyInterval]:
        ordered = sorted(week, key=lambda span: (span.weekday, span.start_minute))
        for first, second in zip(ordered, ordered[1:]):
            if first.weekday == second.weekday and first.end_minute > second.start_minute:
                raise ValueError("Weekly intervals must not overlap")
        return ordered


class PolicyCommand(PolicyInput):
    action: Literal["policy"]
    expected_version: ScheduleVersion


class ExceptionCommand(ConfigurationModel):
    action: Literal["exception"]
    expected_version: ScheduleVersion
    date: LocalDate
    windows: list[LocalSpan] | None = Field(max_length=1440)

    @field_validator("windows")
    @classmethod
    def non_overlapping_date(cls, windows: list[LocalSpan] | None) -> list[LocalSpan] | None:
        if windows is None:
            return None
        ordered = sorted(windows, key=lambda span: span.start_minute)
        if any(
            first.end_minute > second.start_minute for first, second in zip(ordered, ordered[1:])
        ):
            raise ValueError("Date intervals must not overlap")
        return ordered


AvailabilityCommand = Annotated[
    ScheduleCommand | PolicyCommand | ExceptionCommand, Field(discriminator="action")
]
