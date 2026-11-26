"""Resolve a current scheduling request and render committed domain outcomes."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from asm.scheduling.availability import calculate_windows
from asm.scheduling.commands import OFFER_OPTION_LIMIT, OfferedTime, _absolute_times, _stored
from asm.scheduling.models import ScheduleSnapshot
from asm.scheduling.service import AcceptedMaterial, accepted_minutes

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from asm.ai.contracts import SchedulingIntentResult, SchedulingPeriod

DATE_QUESTION = "На какую дату посмотреть варианты?"
PERIOD_QUESTION = "В какое время посмотреть варианты: утром, после обеда или вечером?"
WORK_QUESTION = "Для какой согласованной работы посмотреть время?"
CODE_QUESTION = "Какой вариант вы выбираете? Пришлите «Выбираю S-…» с кодом из сообщения."
UNKNOWN_CODE = "Этот вариант недоступен. На какую дату подобрать свежие окна?"
LIST_LIMIT = min(4, OFFER_OPTION_LIMIT)

_RELATIVE_DAYS = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
_DATE = re.compile(r"\b(сегодня|завтра|послезавтра|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_OTHER_DATES = re.compile(
    r"\b(?:понедельник|вторник|сред[ау]|четверг|пятниц[ау]|суббот[ау]|воскресенье"
    r"|на неделе|на выходных|через \d+|\d{1,2}[./]\d{1,2})\b",
    re.IGNORECASE,
)
_PERIODS: dict[SchedulingPeriod, re.Pattern[str]] = {
    "MORNING": re.compile(r"\b(?:утром|с утра|до обеда|первая половина дня)\b"),
    "AFTERNOON": re.compile(r"\b(?:после обеда|днём|днем|во второй половине дня)\b"),
    "EVENING": re.compile(r"\b(?:вечером|под вечер|после работы)\b"),
}
_HOURS = {"ANY": (0, 24), "MORNING": (0, 12), "AFTERNOON": (12, 18), "EVENING": (18, 24)}


def _day(text: str, occurred: datetime, timezone: str) -> date | None:
    dates = _DATE.findall(text.casefold())
    if len(dates) != 1 or _OTHER_DATES.search(text):
        return None
    word = dates[0]
    try:
        if word in _RELATIVE_DAYS:
            return occurred.astimezone(ZoneInfo(timezone)).date() + timedelta(
                days=_RELATIVE_DAYS[word]
            )
        return date.fromisoformat(word)
    except (ValueError, OverflowError):
        return None


def _period(text: str, candidate: SchedulingPeriod | None) -> SchedulingPeriod | None:
    found = [period for period, pattern in _PERIODS.items() if pattern.search(text.casefold())]
    if len(found) > 1:
        return None
    resolved = found[0] if found else "ANY"
    if candidate is not None and resolved != candidate:
        return None
    return resolved


def _label(value: str) -> str:
    return " ".join(value.split())


def _work(text: str, works: list[dict[str, str]]) -> dict[str, str] | None:
    words = " ".join(re.findall(r"\w+", text.casefold()))

    # Exact design terms, with a bounded accusative form for common Russian names.
    def mentioned(work: dict[str, str]) -> bool:
        name = " ".join(re.findall(r"\w+", work["title"].casefold()))
        if not name:
            return False
        names = [name]
        if len(name) > 2 and name[-1] in "ая":
            names.append(name[:-1] + ("у" if name[-1] == "а" else "ю"))
        return any(f" {item} " in f" {words} " for item in names)

    matches = [work for work in works if mentioned(work)]
    if len(matches) == 1:
        return matches[0]
    if not matches and len(works) == 1:
        return works[0]
    return None


def _windows(
    schedule: ScheduleSnapshot,
    minutes: int,
    period: SchedulingPeriod,
    seen: list[str] | tuple[()] = (),
) -> list[dict[str, Any]]:
    if schedule.timezone is None:
        return []
    low, high = _HOURS[period]
    zone = ZoneInfo(schedule.timezone)
    options = [
        window
        for window in calculate_windows(schedule, minutes)
        if low <= window.visit_start.astimezone(zone).hour < high
    ]
    seen_starts = {datetime.fromisoformat(instant) for instant in seen}
    options.sort(key=lambda window: window.visit_start.astimezone(UTC) in seen_starts)
    return [window.model_dump(mode="json") for window in options[:LIST_LIMIT]]


def _visit(visit_start: str, visit_end: str, timezone: str) -> str:
    zone = ZoneInfo(timezone)
    start, end = (
        datetime.fromisoformat(instant).astimezone(zone) for instant in (visit_start, visit_end)
    )
    # Include offsets even when two local starts look identical at a DST fold.
    return f"{start:%d.%m.%Y %H:%M %z} — {end:%d.%m.%Y %H:%M %z} ({timezone})"


def _deadline(instant: str, timezone: str) -> str:
    date_time = datetime.fromisoformat(instant).astimezone(ZoneInfo(timezone))
    return f"{date_time:%d.%m.%Y %H:%M:%S %z} ({timezone})"


def _heading(work: dict[str, str]) -> str:
    return f"«{_label(work['title'])}» · {_label(work['service_name'])}"


def _list_text(work: dict[str, str], offered: dict[str, Any], *, conflict: bool = False) -> str:
    prefix = "Это время уже занято или срок варианта истёк.\n" if conflict else ""
    if not offered["options"]:
        day = date.fromisoformat(offered["date"])
        return (
            f"{prefix}{_heading(work)}. На {day:%d.%m.%Y} подходящих окон нет. "
            "На какую другую дату или время посмотреть?"
        )
    timezone = offered["timezone"]
    lines = [
        f"{option['code']} · {_visit(option['visit_start'], option['visit_end'], timezone)}"
        for option in offered["options"]
    ]
    expires = _deadline(offered["expires_at"], timezone)
    return "\n".join(
        [
            f"{prefix}{_heading(work)}. Свободные варианты:",
            *lines,
            f"Варианты действуют до {expires}. До выбора окна доступны другим клиентам. "
            "Чтобы выбрать окно, ответьте «Выбираю S-…» с его кодом.",
        ]
    )


def _result_text(work: dict[str, str], result: dict[str, Any]) -> str:
    outcome = result["outcome"]
    if outcome == "SESSION_HELD":
        return f"{_heading(work)}. Для этой работы уже есть действующее удержание."
    if outcome in {"EXPIRED", "RELEASED", "CANCELLED"}:
        return f"{_heading(work)}. Этот вариант больше не действует. На какую дату подобрать окна?"
    visit = _visit(result["visit_start"], result["visit_end"], result["timezone"])
    if outcome in {"CONFIRMED", "ALREADY_CONFIRMED"}:
        return f"{_heading(work)}. Визит подтверждён. {visit}."
    if outcome == "HELD":
        expires = _deadline(result["expires_at"], result["timezone"])
        return (
            f"{_heading(work)}. {visit}. Время удержано до {expires}. "
            "Для подтверждения записи нужна предоплата."
        )
    raise ValueError("Unexpected scheduling outcome")


async def finish_scheduling_intent(
    intent: SchedulingIntentResult,
    command: Callable[[str, dict[str, object]], Awaitable[Any]],
) -> Any:
    opened = await command("OPEN", intent.scheduling.model_dump(mode="json"))
    kind = opened["kind"]
    reply: str | None
    if kind == "LIST":
        reply = await _offer(intent, opened, command)
    elif kind == "SELECT":
        reply = await _select(opened, command)
    else:
        reply = {
            "NEEDS_CODE": CODE_QUESTION,
            "UNKNOWN_CODE": UNKNOWN_CODE,
            "REPEAT": None,
        }[kind]
    return await command("FINISH", {"text": reply})


async def _offer(
    intent: SchedulingIntentResult,
    opened: dict[str, Any],
    command: Callable[[str, dict[str, object]], Awaitable[Any]],
) -> str:
    from asm.ai.contracts import ListAvailability

    assert isinstance(intent.scheduling, ListAvailability)
    work = _work(opened["text"], opened["works"])
    if work is None:
        return WORK_QUESTION if opened["works"] else "Для какой работы уточнить запись у мастера?"
    timezone = opened["timezone"]
    if timezone is None:
        return f"{_heading(work)}. Рабочие часы ещё не настроены. Хотите уточнить время у мастера?"
    day = _day(opened["text"], datetime.fromisoformat(opened["occurred_at"]), timezone)
    period = _period(opened["text"], intent.scheduling.period)
    if day is None:
        return DATE_QUESTION
    if period is None:
        return PERIOD_QUESTION
    raw = await command(
        "LIST_STATE",
        {
            "request_id": work["request_id"],
            "day": day.isoformat(),
            "period": period,
        },
    )
    state = _stored(ScheduleSnapshot, raw["schedule"])
    minutes = accepted_minutes(_stored(AcceptedMaterial, raw["terms"]))
    if minutes is None:
        return f"{_heading(work)}. Для подбора времени мастеру нужно уточнить длительность."
    offer = await command("ISSUE", {"windows": _windows(state, minutes, period)})
    return _list_text(work, offer)


async def _select(
    opened: dict[str, Any],
    command: Callable[[str, dict[str, object]], Awaitable[Any]],
) -> str | None:
    work, state = opened["work"], opened["state"]
    minutes = accepted_minutes(_stored(AcceptedMaterial, state["terms"]))
    if minutes is None:
        return UNKNOWN_CODE
    schedule = _stored(ScheduleSnapshot, state["schedule"])
    option = _stored(OfferedTime, state["option"])
    # Check opening hours independently of other occupancy. The locked selection
    # rechecks the current allocation rows and the expiry using PostgreSQL time.
    unoccupied = schedule.model_copy(update={"occupancy": []})
    start = _absolute_times(option)
    eligible = any(
        _absolute_times(window) == start for window in calculate_windows(unoccupied, minutes)
    )
    selected = await command("SELECT", {"eligible": eligible})
    if selected["kind"] == "REPEAT":
        return None
    if selected["kind"] == "NEEDS_ALTERNATIVES":
        current = _stored(ScheduleSnapshot, selected["schedule"])
        offered = await command(
            "ALTERNATIVES",
            {
                "windows": _windows(current, minutes, opened["period"], selected["seen"]),
            },
        )
        return _list_text(work, offered, conflict=True)
    if selected["kind"] == "ALTERNATIVES":
        return _list_text(work, selected["offer"], conflict=True)
    return _result_text(work, selected["result"])
