"""Explicit wall-time, UTC and buffer boundaries for the M7.1A projection."""

from datetime import UTC, date, datetime, timedelta

from asm.scheduling.availability import calculate_windows
from asm.scheduling.models import (
    DateException,
    LocalSpan,
    PolicyView,
    ScheduleSnapshot,
    WeeklyInterval,
)

RESOURCE = "00000000-0000-4000-8000-000000000701"
POLICY = "00000000-0000-4000-8000-000000000702"
DAY = date(2026, 11, 24)


def snapshot(
    *intervals: tuple[int, int],
    day: date = DAY,
    now: datetime = datetime(2026, 11, 23, 6, tzinfo=UTC),
    timezone: str = "Asia/Novosibirsk",
    step: int = 15,
    before: int = 0,
    after: int = 0,
    notice: int = 0,
    horizon: int = 7,
) -> ScheduleSnapshot:
    return ScheduleSnapshot(
        now=now,
        date=day,
        timezone=timezone,
        resource_id=RESOURCE,
        week=[
            WeeklyInterval(weekday=day.weekday(), start_minute=start, end_minute=end)
            for start, end in intervals
        ],
        policy=PolicyView(
            policy_id=POLICY,
            step_minutes=step,
            buffer_before_minutes=before,
            buffer_after_minutes=after,
            minimum_notice_minutes=notice,
            horizon_days=horizon,
            offer_ttl_minutes=30,
            hold_ttl_minutes=10,
        ),
        exception=None,
    )


def starts(state: ScheduleSnapshot, occupied_minutes: int) -> list[str]:
    return [
        window.visit_start.isoformat(timespec="minutes")
        for window in calculate_windows(state, occupied_minutes)
    ]


def test_novosibirsk_exact_window_and_external_buffers():
    state = snapshot((600, 720), before=10, after=5, notice=120)
    assert starts(state, 65) == [
        "2026-11-24T10:15+07:00",
        "2026-11-24T10:30+07:00",
        "2026-11-24T10:45+07:00",
    ]
    first = calculate_windows(state, 65)[0]
    assert first.visit_end.isoformat(timespec="minutes") == "2026-11-24T11:20+07:00"
    assert first.busy_start.isoformat(timespec="minutes") == "2026-11-24T10:05+07:00"
    assert first.busy_end.isoformat(timespec="minutes") == "2026-11-24T11:25+07:00"


def test_breaks_and_exact_adjacency():
    state = snapshot((600, 660), (690, 780), before=10, after=5)
    assert starts(state, 65) == ["2026-11-24T11:45+07:00"]
    # Each working interval may be occupied exactly. Crossing the shared boundary would
    # take two separate intervals, even though they have no gap.
    state = snapshot((600, 660), (660, 720))
    assert starts(state, 60) == ["2026-11-24T10:00+07:00", "2026-11-24T11:00+07:00"]


def test_date_override_and_closed_day():
    state = snapshot((600, 660))
    assert starts(state, 60) == ["2026-11-24T10:00+07:00"]
    replacement = DateException(date=DAY, windows=[LocalSpan(start_minute=720, end_minute=780)])
    assert starts(state.model_copy(update={"exception": replacement}), 60) == [
        "2026-11-24T12:00+07:00"
    ]
    closed = DateException(date=DAY, windows=[])
    assert starts(state.model_copy(update={"exception": closed}), 60) == []


def test_horizon_requires_all_of_the_busy_interval():
    horizon_origin = datetime(2026, 11, 23, 11, 25, tzinfo=UTC)
    state = snapshot((600, 720), now=horizon_origin, timezone="UTC", before=10, after=5, horizon=1)
    assert starts(state, 65) == ["2026-11-24T10:15+00:00"]
    assert (
        starts(state.model_copy(update={"now": horizon_origin - timedelta(microseconds=1)}), 65)
        == []
    )


def test_minimum_notice_is_inclusive_for_visit_start_and_prep_must_be_in_future():
    origin = datetime(2026, 11, 24, 8, 15, tzinfo=UTC)
    state = snapshot((600, 720), now=origin, timezone="UTC", before=10, after=5, notice=120)
    assert len(calculate_windows(state, 65)) == 3
    after_origin = state.model_copy(update={"now": origin + timedelta(microseconds=1)})
    assert starts(after_origin, 65) == ["2026-11-24T10:30+00:00", "2026-11-24T10:45+00:00"]

    state = snapshot(
        (600, 720),
        now=datetime(2026, 11, 24, 10, 6, tzinfo=UTC),
        timezone="UTC",
        before=10,
        after=5,
    )
    assert starts(state, 65) == ["2026-11-24T10:30+00:00", "2026-11-24T10:45+00:00"]


def test_spring_skips_nonexistent_starts_and_measures_real_duration():
    state = snapshot(
        (60, 240),
        day=date(2026, 3, 29),
        now=datetime(2026, 3, 28, 6, tzinfo=UTC),
        timezone="Europe/Berlin",
        step=30,
    )
    assert starts(state, 60) == [
        "2026-03-29T01:00+01:00",
        "2026-03-29T01:30+01:00",
        "2026-03-29T03:00+02:00",
    ]
    transition = calculate_windows(state, 60)[1]
    assert transition.visit_end.isoformat(timespec="minutes") == "2026-03-29T03:30+02:00"
    assert transition.visit_end.astimezone(UTC) - transition.visit_start.astimezone(
        UTC
    ) == timedelta(minutes=60)


def test_autumn_both_offsets_and_disconnected_utc_ranges():
    state = snapshot(
        (120, 150),
        day=date(2026, 10, 25),
        now=datetime(2026, 10, 24, 6, tzinfo=UTC),
        timezone="Europe/Berlin",
    )
    assert starts(state, 30) == ["2026-10-25T02:00+02:00", "2026-10-25T02:00+01:00"]
    assert starts(state, 45) == []
