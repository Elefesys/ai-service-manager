"""Compute availability in absolute time from the resource's local work intervals."""

from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from asm.scheduling.models import LocalSpan, ScheduleSnapshot, TimeWindow

MINUTE = timedelta(minutes=1)


def _utc_instants(local: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    """Resolve a wall-clock minute, retaining both occurrences of a fold."""
    candidates = {local.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)}
    return tuple(
        instant
        for instant in sorted(candidates)
        if instant.astimezone(zone).replace(tzinfo=None) == local
    )


def _contiguous_ranges(minutes: Iterable[datetime]) -> list[tuple[datetime, datetime]]:
    ranges: list[tuple[datetime, datetime]] = []
    for instant in sorted(minutes):
        if ranges and ranges[-1][1] == instant:
            ranges[-1] = (ranges[-1][0], instant + MINUTE)
        else:
            ranges.append((instant, instant + MINUTE))
    return ranges


def calculate_windows(snapshot: ScheduleSnapshot, occupied_minutes: int) -> list[TimeWindow]:
    policy = snapshot.policy
    if snapshot.timezone is None or policy is None or occupied_minutes <= 0:
        return []

    now = snapshot.now.astimezone(UTC)
    horizon = now + timedelta(days=policy.horizon_days)
    # Offset changes can move the local date across a UTC day boundary.
    if not now.date() - timedelta(days=1) <= snapshot.date <= horizon.date() + timedelta(days=1):
        return []

    zone = ZoneInfo(snapshot.timezone)
    midnight = datetime.combine(snapshot.date, time.min)
    weekday = snapshot.date.weekday()
    spans: Iterable[LocalSpan] = (
        snapshot.exception.windows
        if snapshot.exception is not None
        else (span for span in snapshot.week if span.weekday == weekday)
    )
    duration = timedelta(minutes=occupied_minutes)
    before = timedelta(minutes=policy.buffer_before_minutes)
    after = timedelta(minutes=policy.buffer_after_minutes)
    notice = now + timedelta(minutes=policy.minimum_notice_minutes)
    step = policy.step_minutes
    windows: list[TimeWindow] = []
    for span in spans:
        wall_minutes = {
            minute: _utc_instants(midnight + minute * MINUTE, zone)
            for minute in range(span.start_minute, span.end_minute)
        }
        # A partial repeated hour can split a LocalSpan into separate UTC ranges.
        # Never fill the gap between these ranges or merge separate LocalSpans.
        work_ranges = _contiguous_ranges(
            instant for instants in wall_minutes.values() for instant in instants
        )
        first_start = (span.start_minute + step - 1) // step * step
        for minute in range(first_start, span.end_minute, step):
            for visit_start in wall_minutes[minute]:
                visit_end = visit_start + duration
                busy_start = visit_start - before
                busy_end = visit_end + after
                if (
                    visit_start >= notice
                    and now <= busy_start
                    and busy_end <= horizon
                    and any(start <= busy_start and busy_end <= end for start, end in work_ranges)
                ):
                    windows.append(
                        TimeWindow(
                            visit_start=visit_start.astimezone(zone),
                            visit_end=visit_end.astimezone(zone),
                            busy_start=busy_start.astimezone(zone),
                            busy_end=busy_end.astimezone(zone),
                        )
                    )
    return sorted(windows, key=lambda window: window.visit_start.astimezone(UTC))
