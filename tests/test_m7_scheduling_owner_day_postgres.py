"""M7.3A owner day over real PostgreSQL and the ordinary booking commands."""

import json
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from asm.scheduling.commands import HoldResult
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from m5_knowledge_search_fixtures import owner_unit
from m7_scheduling_fixtures import ZONE, accept_pair_with_modes, accept_work, booking_contract
from sqlalchemy import text
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import scalar
from test_m6_owner_decisions_postgres import owner_get, owner_post
from test_m6_pricing_postgres import publish, sign_in
from test_m7_scheduling_holds_postgres import (
    CREATE_BLOCK,
    WEEK,
    client_effects,
    command_http,
    configure,
    occupancy,
    offer,
    pick,
)
from test_m7_scheduling_postgres import approval_pg as approval_pg
from test_m7_scheduling_postgres import assessment_pg as assessment_pg
from test_m7_scheduling_postgres import auth as auth
from test_m7_scheduling_postgres import db as db
from test_m7_scheduling_postgres import intake_pg as intake_pg
from test_m7_scheduling_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m7_scheduling_postgres import pricing_pg as pricing_pg
from test_m7_scheduling_postgres import scheduling_pg as scheduling_pg
from test_m7_scheduling_postgres import search_pg as search_pg
from test_m7_scheduling_postgres import seeded as seeded
from test_m7_scheduling_postgres import service_request_pg as service_request_pg
from test_m7_scheduling_reschedule_postgres import (
    NO_BUFFERS,
    RESCHEDULE_REASON,
    assert_visit,
    block_time,
    cancel,
    initial_appointment,
    job_count,
    legacy_facts,
    move,
    no_effects,
    option_at,
    owner_booking,
    reschedule_offer,
    submit,
    wall,
)
from test_tenancy_postgres import BA, BA2, BB, PROVIDER, UA, A, B

pytestmark = pytest.mark.integration


def day_route(day=None, *, workspace=A, business=BA):
    path = f"/api/v1/workspaces/{workspace}/businesses/{business}/scheduling/day"
    return f"{path}?date={day}" if day is not None else path


def conflicts_route(*, workspace=A, business=BA, **ids):
    path = day_route(workspace=workspace, business=business).removesuffix("/day") + "/conflicts"
    return f"{path}?{urlencode(ids, doseq=True)}" if ids else path


def receipt(case, **values):
    print("M7.3A PostgreSQL", json.dumps({"case": case, **values}, ensure_ascii=False, default=str))


def assert_work(row, work, booking):
    assert row["selection"] == work.selection.model_dump(exclude={"workspace_id", "business_id"})
    assert row["booking"] == booking


def bookable_times(preview):
    return {wall(window["visit_start"]) for window in preview["windows"]}


async def create_hold(h, work, day, *, start="12:00"):
    option = option_at(await offer(h, work, day, "owner-day-hold"), start)
    hold = await pick(h, work, UUID(option.option_id), "owner-day-hold-choice")
    assert isinstance(hold, HoldResult) and hold.outcome == "HELD"
    return hold


async def shorten_hold_fixture(h, hold, *, seconds=2):
    # The read must use PostgreSQL's clock while the allocation is still stored
    # as active. Move the synthetic deadline close without scheduling a job.
    async with h.migrator.begin() as connection:
        await connection.execute(
            text("ALTER TABLE app.reservation_holds DISABLE TRIGGER scheduling_fact_immutable")
        )
        shortened = (
            await connection.execute(
                text("""
                    UPDATE app.reservation_holds SET expires_at=clock_timestamp()+make_interval(secs=>:seconds)
                    WHERE (workspace_id,business_id,id)=(:ws,:business,:id) RETURNING expires_at
                """),
                {"ws": A, "business": BA, "id": UUID(hold.hold_id), "seconds": seconds},
            )
        ).scalar_one()
        await connection.execute(
            text("ALTER TABLE app.reservation_holds ENABLE TRIGGER scheduling_fact_immutable")
        )
    return shortened


async def test_r1_owner_can_close_an_empty_date_and_cannot_remove_a_commitment(scheduling_pg, auth):
    h = scheduling_pg
    token = await sign_in(auth)
    async with owner_unit(h) as unit:
        for business in (BA, BA2):
            await unit.scheduling_owner_command(
                business,
                "schedule",
                "schedule",
                {"timezone": ZONE, "week": WEEK, "expected_version": 0},
            )
    today = await owner_get(auth, day_route())
    day = date.fromisoformat(today["date"]) + timedelta(days=1)
    empty = await owner_get(auth, day_route(day))
    assert empty["exception"] is None and empty["working_intervals"]
    assert empty["entries"] == empty["history"] == []
    assert await scalar(h, "SELECT count(*) FROM app.service_requests") == 0
    route = day_route() + "/exception"
    request = {
        "resource_id": empty["resource_id"],
        "expected_version": empty["schedule_version"],
        "date": str(day),
        "windows": [],
    }
    assert (await auth.client.post(route, json=request)).status_code == 403
    foreign = await owner_get(auth, day_route(day, business=BA2))
    for path, body, status, code in (
        (route, request | {"resource_id": foreign["resource_id"]}, 409, "STALE_STATE"),
        (day_route(business=BA2) + "/exception", request, 409, "STALE_STATE"),
        (day_route(business=BB) + "/exception", request, 404, "NOT_FOUND"),
        (day_route(workspace=B, business=BB) + "/exception", request, 403, "ACCESS_DENIED"),
    ):
        refusal = await auth.client.post(path, headers=token, json=body)
        assert (refusal.status_code, refusal.json()) == (status, {"error": {"code": code}})
        assert refusal.headers["cache-control"] == "no-store"
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE (workspace_id,user_account_id)=(:ws,:actor)"
            ),
            {"ws": A, "actor": UA},
        )
    try:
        refusal = await auth.client.post(route, headers=token, json=request)
        assert (refusal.status_code, refusal.json()) == (403, {"error": {"code": "ACCESS_DENIED"}})
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE (workspace_id,user_account_id)=(:ws,:actor)"
                ),
                {"ws": A, "actor": UA},
            )

    closed = await owner_post(auth, route, token, request)
    assert closed["resource_id"] == empty["resource_id"]
    assert closed["schedule_version"] == empty["schedule_version"] + 1
    assert closed["exception"] == {"date": str(day), "windows": []}
    assert closed["entries"] == closed["history"] == closed["working_intervals"] == []
    assert (await owner_get(auth, day_route(day))) | {"now": closed["now"]} == closed
    stale = await auth.client.post(route, headers=token, json=request | {"windows": None})
    assert (stale.status_code, stale.json()) == (409, {"error": {"code": "STALE_STATE"}})
    assert (await owner_get(auth, day_route(day)))["exception"] == closed["exception"]
    assert (await owner_get(auth, day_route(day, business=BA2))) | {
        "now": foreign["now"]
    } == foreign

    await publish(h, booking_contract("NONE"))
    work = await accept_work(h, auth, token, "20 mm")
    await publish(h, booking_contract("FIXED_DEPOSIT"))
    second = await accept_work(h, auth, token, "21 mm")
    plan = await owner_post(
        auth,
        work.preview_url(day=day),
        token,
        NO_BUFFERS | {"expected_version": closed["schedule_version"]},
    )
    preview = await owner_get(auth, work.preview_url(day=day))
    assert preview == plan and preview["reason"] == "DATE_CLOSED" and preview["windows"] == []
    reopened = await owner_post(
        auth,
        route,
        token,
        request | {"expected_version": plan["schedule_version"], "windows": None},
    )
    assert (
        reopened["exception"] is None
        and reopened["working_intervals"] == empty["working_intervals"]
    )
    assert (await owner_get(auth, day_route(day))) | {"now": reopened["now"]} == reopened
    assert "10:00" in bookable_times(await owner_get(auth, work.preview_url(day=day)))

    hold_day = day + timedelta(days=1)
    appointment, _ = await initial_appointment(h, work, await offer(h, work, day, "r1-appointment"))
    hold = await create_hold(h, second, hold_day, start="10:00")
    protected = [
        (work, day, "APPOINTMENT", appointment.appointment_id),
        (second, hold_day, "HOLD", hold.hold_id),
    ]
    facts = await legacy_facts(h)
    refusals = {}
    for booking_work, booking_date, kind, identifier in protected:
        before = await owner_get(auth, day_route(booking_date))
        card = await owner_booking(auth, booking_work)
        assert len(before["entries"]) == 1 and before["entries"][0]["kind"] == kind
        assert_work(before["entries"][0], booking_work, card["booking"])
        refusal = await auth.client.post(
            route,
            headers=token,
            json=request
            | {"date": str(booking_date), "expected_version": before["schedule_version"]},
        )
        assert refusal.status_code == 409 and refusal.headers["cache-control"] == "no-store"
        error = refusal.json()["error"]
        assert error == {
            "code": "CALENDAR_CONFLICT",
            "affected": [{"kind": kind, "id": identifier}],
        }
        lookup = await owner_get(auth, conflicts_route(**{f"{kind.lower()}_id": identifier}))
        assert lookup["entries"] == before["entries"]
        assert (await owner_get(auth, day_route(booking_date))) | {"now": before["now"]} == before
        assert await owner_booking(auth, booking_work) == card
        refusals[kind] = error
    assert await legacy_facts(h) == facts
    receipt(
        "S7-R1-close-and-restore",
        closed=closed["exception"],
        preview=preview["reason"],
        restored=reopened["working_intervals"],
        protected=refusals,
        stale=stale.json()["error"],
        foreign_business=404,
        foreign_workspace=403,
    )


async def test_r1_resolves_all_affected_bookings_on_an_intermediate_date(scheduling_pg, auth):
    h = scheduling_pg
    assert (await auth.client.get(conflicts_route(appointment_id=uuid4()))).status_code == 401
    token = await sign_in(auth)
    await publish(h, booking_contract("NONE"))
    work = await accept_work(h, auth, token, "20 mm")
    other_work = await accept_work(h, auth, token, "20 mm")
    assert work.identity.client_id != other_work.identity.client_id
    first_date, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    booking_date = first_date + timedelta(days=1)
    last_date = first_date + timedelta(days=2)
    first, _ = await initial_appointment(
        h, work, await offer(h, work, booking_date, "r1-block-first"), key="r1-block-first-choice"
    )
    second, _ = await initial_appointment(
        h,
        other_work,
        await offer(h, other_work, booking_date, "r1-block-second"),
        start="13:00",
        key="r1-block-second-choice",
    )
    assert not (await owner_get(auth, day_route(first_date)))["entries"]
    assert not (await owner_get(auth, day_route(last_date)))["entries"]
    entries = (await owner_get(auth, day_route(booking_date)))["entries"]
    assert len(entries) == 2 and entries[0]["work_label"] == entries[1]["work_label"]
    for row, selected in zip(entries, (work, other_work), strict=True):
        assert_work(row, selected, (await owner_booking(auth, selected))["booking"])

    expected = [first.appointment_id, second.appointment_id]
    spans = [
        (block_time(booking_date, "10:15"), block_time(booking_date, "10:25"), expected[:1]),
        (block_time(booking_date, "13:15"), block_time(booking_date, "13:25"), expected[1:]),
        (block_time(first_date, "15:00"), block_time(last_date, "10:00"), expected),
    ]
    for index, (start, end, matching) in enumerate(spans):
        refusal = await command_http(
            auth, token, CREATE_BLOCK, f"r1-conflict-{index}", {"start": start, "end": end}
        )
        assert refusal.status_code == 409
        error = refusal.json()["error"]
        assert error["code"] == "CALENDAR_CONFLICT"
        assert {item["id"] for item in error["affected"]} == set(matching)
        assert {item["kind"] for item in error["affected"]} == {"APPOINTMENT"}
        lookup = await owner_get(
            auth, conflicts_route(appointment_id=[item["id"] for item in error["affected"]])
        )
        assert lookup["entries"] == [
            row for row in entries if row["booking"]["appointment_id"] in matching
        ]

    assert (await owner_get(auth, conflicts_route(business=BA2, appointment_id=expected)))[
        "entries"
    ] == []
    assert (await owner_get(auth, conflicts_route(hold_id=expected, block_id=expected)))[
        "entries"
    ] == []
    assert (
        await owner_get(auth, conflicts_route(appointment_id=expected + [expected[0], uuid4()]))
    )["entries"] == entries
    for query, status in (
        (conflicts_route(workspace=B, business=BB, appointment_id=expected), 403),
        (conflicts_route(business=BB, appointment_id=expected), 404),
        (conflicts_route(), 422),
        (conflicts_route(date=str(booking_date), appointment_id=expected), 422),
        (conflicts_route(appointment_id=[expected[0]] * 32, hold_id=expected[1]), 422),
    ):
        refusal = await auth.client.get(query)
        assert refusal.status_code == status and refusal.headers["cache-control"] == "no-store"
        assert all(value not in refusal.text for value in expected)
    with pytest.raises(ServiceRequestError) as denied:
        async with owner_unit(h, actor=PROVIDER) as unit:
            await unit.scheduling_owner_day(BA, None, [{"kind": "APPOINTMENT", "id": expected[0]}])
    assert denied.value.code is ServiceRequestCode.ACCESS_DENIED

    assert (await submit(h, cancel(other_work, second))).outcome == "CANCELLED"
    now = await owner_get(auth, day_route(booking_date))
    assert now["entries"] == entries[:1] and len(now["history"]) == 1
    assert (await owner_get(auth, conflicts_route(appointment_id=expected)))["entries"] == (
        now["entries"] + now["history"]
    )
    receipt(
        "S7-R1-scoped-conflicts",
        dates=[first_date, booking_date, last_date],
        matching_appointments=expected,
        selections=[row["selection"] for row in entries],
        work_label=entries[0]["work_label"],
        cancelled=now["history"][0]["booking"]["appointment_id"],
    )


async def test_s7_owner_day_matches_each_work_before_and_after_changes_and_expiry(
    scheduling_pg, auth
):
    h = scheduling_pg
    token, a, b = await accept_pair_with_modes(h, auth, "NONE", "FIXED_DEPOSIT")
    initial_day = await owner_get(auth, day_route())
    assert initial_day["resource_id"] is None and initial_day["timezone"] is None
    assert (
        initial_day["working_intervals"] == initial_day["entries"] == initial_day["history"] == []
    )
    day, plan = await configure(h, auth, token, a, policy=NO_BUFFERS | {"buffer_after_minutes": 5})
    original, _ = await initial_appointment(h, a, await offer(h, a, day, "owner-day-original"))
    hold = await create_hold(h, b, day)
    before, jobs = await client_effects(h), await job_count(h)
    untouched = await occupancy(h)
    initial = await owner_get(auth, day_route(day))
    start, held = initial["entries"]
    assert initial["schedule_version"] == plan["schedule_version"]
    assert initial["resource_id"] == plan["resource_id"] and initial["history"] == []
    assert start["kind"] == "APPOINTMENT" and start["successor"] is None
    assert held["kind"] == "HOLD"
    assert_work(start, a, (await owner_booking(auth, a))["booking"])
    assert_work(held, b, (await owner_booking(auth, b))["booking"])
    assert start["selection"]["client_id"] == held["selection"]["client_id"]
    assert start["selection"]["conversation_id"] == held["selection"]["conversation_id"]
    assert start["work_label"] != held["work_label"] and "swallow" in held["work_label"]
    assert_visit(start["booking"], "10:00", "11:05", busy_end="11:10")
    assert await occupancy(h) == untouched
    await no_effects(h, before, jobs)

    closed = {
        "action": "exception",
        "date": str(day),
        "windows": [],
        "expected_version": initial["schedule_version"],
    }
    refusal = await auth.client.post(a.preview_url(day=day), json=closed, headers=token)
    assert refusal.status_code == 409
    detail = refusal.json()["error"]
    assert detail["code"] == "CALENDAR_CONFLICT"
    assert {row["id"] for row in detail["affected"]} == {original.appointment_id, hold.hold_id}
    free_day = day + timedelta(days=1)
    assert "10:00" in bookable_times(await owner_get(auth, a.preview_url(day=free_day)))
    await owner_post(auth, a.preview_url(day=free_day), token, closed | {"date": str(free_day)})
    day_off = await owner_get(auth, day_route(free_day))
    assert day_off["exception"] == {"date": str(free_day), "windows": []}
    assert day_off["working_intervals"] == day_off["entries"] == []
    assert bookable_times(await owner_get(auth, a.preview_url(day=free_day))) == set()

    options = await reschedule_offer(h, a, original, day, "owner-day-options")
    target = option_at(options, "10:30")
    added = await command_http(
        auth,
        token,
        CREATE_BLOCK,
        "owner-day-block",
        {"start": block_time(day, "11:10"), "end": block_time(day, "11:20")},
    )
    assert added.status_code == 200
    block_id = added.json()["block_id"]
    appointment_route = a.booking_url().partition("?")[0] + "/" + original.appointment_id
    refs = a.selection.model_dump(include={"client_id", "quote_id", "order_id"})
    request = refs | {"option_id": target.option_id, "reason": RESCHEDULE_REASON}
    refused = await command_http(
        auth, token, appointment_route + "/reschedule", "owner-day-denied", request
    )
    assert (refused.status_code, refused.json()) == (
        409,
        {"error": {"code": "CALENDAR_CONFLICT", "affected": [{"kind": "BLOCK", "id": block_id}]}},
    )
    conflicting = await owner_get(auth, day_route(day))
    assert conflicting["entries"] == [
        start,
        {
            "kind": "BLOCK",
            "block_id": block_id,
            "start": block_time(day, "11:10"),
            "end": block_time(day, "11:20"),
        },
        held,
    ]
    assert conflicting["history"] == []
    block_lookup = await owner_get(auth, conflicts_route(block_id=block_id))
    assert block_lookup["entries"] == conflicting["entries"][1:2]
    released = await command_http(
        auth, token, f"{CREATE_BLOCK}/{block_id}/release", "owner-day-unblock", {}
    )
    assert released.status_code == 200 and released.json()["outcome"] == "RELEASED"
    assert (await owner_get(auth, day_route(day)))["entries"] == [start, held]
    assert await owner_get(auth, conflicts_route(block_id=block_id)) == block_lookup
    moved = await command_http(
        auth, token, appointment_route + "/reschedule", "owner-day-move", request
    )
    assert moved.status_code == 200
    successor = moved.json()["booking"]
    shifted = await owner_get(auth, day_route(day))
    assert_work(shifted["entries"][0], a, successor)
    assert_visit(successor, "10:30", "11:35", busy_end="11:40")
    assert shifted["entries"][1] == held
    assert shifted["history"][0]["successor"] == {
        "appointment_id": successor["appointment_id"],
        "date": str(day),
    }
    assert_work(shifted["history"][0], a, (await owner_booking(auth, a))["history"][0])
    reason = refs | {"reason": "Отмена визита"}
    stale = await command_http(
        auth, token, appointment_route + "/cancel", "owner-day-stale", reason
    )
    assert (stale.status_code, stale.json()) == (409, {"error": {"code": "STALE_STATE"}})
    assert (await owner_booking(auth, a))["booking"] == successor
    new_route = a.booking_url().partition("?")[0] + "/" + successor["appointment_id"]
    cancelled = await command_http(auth, token, new_route + "/cancel", "owner-day-cancel", reason)
    assert cancelled.status_code == 200 and cancelled.json()["outcome"] == "CANCELLED"
    cancelled_day = await owner_get(auth, day_route(day))
    assert cancelled_day["entries"] == [held]
    card = await owner_booking(auth, a)
    assert [item["booking"] for item in cancelled_day["history"]] == list(reversed(card["history"]))
    assert "10:00" in bookable_times(await owner_get(auth, a.preview_url(day=day)))
    assert "12:00" not in bookable_times(await owner_get(auth, b.preview_url(day=day)))

    deadline = await shorten_hold_fixture(h, hold)
    current = await owner_get(auth, day_route(day))
    assert current["entries"][0]["booking"]["outcome"] == "HELD"
    assert datetime.fromisoformat(current["entries"][0]["booking"]["expires_at"]) == deadline
    live_facts = await legacy_facts(h)
    await scalar(
        h,
        "SELECT pg_sleep(greatest(extract(epoch FROM :deadline - clock_timestamp()),0)+0.02)",
        deadline=deadline,
    )
    expired = await owner_get(auth, day_route(day))
    assert expired["entries"] == [] and len(expired["history"]) == 3
    assert datetime.fromisoformat(expired["now"]) >= deadline
    expired_hold = expired["history"][-1]
    assert_work(expired_hold, b, (await owner_booking(auth, b))["booking"])
    assert expired_hold["booking"] == current["entries"][0]["booking"] | {"outcome": "EXPIRED"}
    assert "12:00" in bookable_times(await owner_get(auth, b.preview_url(day=day)))
    assert await legacy_facts(h) == live_facts
    receipt(
        "S7-two-works-conflict-cancel-expiry",
        date=day,
        initial=initial["entries"],
        conflict=refused.json(),
        stale=stale.json(),
        after_move=shifted["entries"],
        cancelled=[entry["booking"]["appointment_id"] for entry in cancelled_day["history"]],
        hold_at_expiry=expired_hold["booking"],
        windows_restored=["10:00", "12:00"],
        **(await no_effects(h, before, jobs, confirmed=1)),
    )


async def test_s7_owner_scope_and_both_local_dates_at_repeated_midnight(scheduling_pg, auth):
    h = scheduling_pg
    assert (await auth.client.get(day_route())).status_code == 401
    token = await sign_in(auth)
    utc_day = await owner_get(auth, day_route())
    for path, status in (
        (day_route(workspace=B, business=BB), 403),
        (day_route(business=BB), 404),
        (day_route("2026-02-30"), 422),
        (day_route("2026-12-01") + "&date=2026-12-02", 422),
    ):
        response = await auth.client.get(path)
        assert response.status_code == status and response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"error"}
    with pytest.raises(ServiceRequestError) as denied:
        async with owner_unit(h, actor=PROVIDER) as unit:
            await unit.scheduling_owner_day(BA, None)
    assert denied.value.code is ServiceRequestCode.ACCESS_DENIED

    timezone = "America/Havana"
    zone = ZoneInfo(timezone)
    next_year = datetime.fromisoformat(utc_day["now"]).year + 1
    early_november = datetime(next_year, 11, 1, 0, 10)
    sunday = early_november + timedelta(days=(6 - early_november.weekday()) % 7)
    repeated = sunday.replace(tzinfo=zone)
    assert repeated.utcoffset() != repeated.replace(fold=1).utcoffset()
    first_day = sunday.date() - timedelta(days=1)
    second_day = sunday.date()
    start = (sunday - timedelta(minutes=20)).replace(tzinfo=zone)
    end_of_first_midnight = repeated
    async with owner_unit(h) as unit:
        for business in (BA, BA2):
            await unit.scheduling_owner_command(
                business,
                "schedule",
                "schedule",
                {"timezone": timezone, "week": WEEK, "expected_version": 0},
            )
    second_block_route = CREATE_BLOCK.replace(str(BA), str(BA2))
    first = await command_http(
        auth,
        token,
        CREATE_BLOCK,
        "owner-day-midnight-first",
        {"start": start.isoformat(), "end": end_of_first_midnight.isoformat()},
    )
    assert first.status_code == 200
    later = repeated.replace(fold=1)
    second = await command_http(
        auth,
        token,
        second_block_route,
        "owner-day-midnight-second",
        {"start": later.isoformat(), "end": (later + timedelta(hours=1)).isoformat()},
    )
    assert second.status_code == 200
    first_block = {
        "kind": "BLOCK",
        "block_id": first.json()["block_id"],
        "start": start.isoformat(),
        "end": repeated.isoformat(),
    }
    before_midnight = await owner_get(auth, day_route(first_day))
    after_midnight = await owner_get(auth, day_route(second_day))
    assert before_midnight["entries"] == after_midnight["entries"] == [first_block]
    assert not (await owner_get(auth, day_route(second_day + timedelta(days=1))))["entries"]
    second_business = await owner_get(auth, day_route(second_day, business=BA2))
    assert second_business["resource_id"] != after_midnight["resource_id"]
    assert [block["block_id"] for block in second_business["entries"]] == [
        second.json()["block_id"]
    ]
    assert second_business["entries"][0]["start"] == later.isoformat()
    today = await owner_get(auth, day_route())
    assert today["date"] == datetime.fromisoformat(today["now"]).astimezone(zone).date().isoformat()
    receipt(
        "S7-scope-midnight",
        timezone=timezone,
        dates=[first_day, second_day],
        crossing_block=first_block,
        other_business_entries=second_business["entries"],
        denied={"foreign_workspace": 403, "foreign_business": 404, "provider": 403},
    )


async def test_s7_upgrade_0035_keeps_operational_day_and_history(scheduling_pg, auth):
    h = scheduling_pg
    token, a, b = await accept_pair_with_modes(h, auth, "NONE", "FIXED_DEPOSIT")
    await publish(h, booking_contract("NONE"))
    c = await accept_work(h, auth, token, "20 mm")
    day, _ = await configure(h, auth, token, a, policy=NO_BUFFERS)
    next_day = day + timedelta(days=1)
    await _migrate("downgrade", "0035")
    try:
        original, _ = await initial_appointment(h, a, await offer(h, a, day, "legacy-visit"))
        held = await create_hold(h, b, day)
        replacement = option_at(await reschedule_offer(h, a, original, next_day), "10:30")
        moved = await submit(h, move(a, original, replacement))
        original_c, _ = await initial_appointment(
            h, c, await offer(h, c, day, "legacy-cancelled"), key="legacy-cancel-choice"
        )
        legacy_cancelled = await submit(h, cancel(c, original_c))
        assert legacy_cancelled.outcome == "CANCELLED"
        block = await command_http(
            auth,
            token,
            CREATE_BLOCK,
            "legacy-block",
            {"start": block_time(day, "14:00"), "end": block_time(day, "14:15")},
        )
        assert block.status_code == 200
        before = await legacy_facts(h)
        original_a, original_b, original_c = [await owner_booking(auth, work) for work in (a, b, c)]
    finally:
        await _migrate("upgrade", "0036")
    try:
        profile = await scalar(h, "SELECT platform.scheduling_owner_day_schema_profile()")
        assert profile["schema_revision"] == "0036" and profile["valid"] is True
        assert await legacy_facts(h) == before
        agreements = [
            (await owner_get(auth, work.url + "/quote"))["agreement"] for work in (a, b, c)
        ]
    finally:
        await _migrate("upgrade", "0037")
    try:
        upgraded = await scalar(h, "SELECT platform.scheduling_intent_schema_profile()")
        assert upgraded["schema_revision"] == "0037" and upgraded["valid"] is True
    finally:
        await _migrate("upgrade", "0039")
    assert [
        (await owner_get(auth, work.url + "/quote"))["agreement"] for work in (a, b, c)
    ] == agreements
    assert await legacy_facts(h) == before
    receipt(
        "S8-0036-0037",
        agreements=[work.proof() for work in (a, b, c)],
        preserved={key: len(rows) for key, rows in before.items()},
        schema=upgraded,
    )
    previous = await owner_get(auth, day_route(day))
    following = await owner_get(auth, day_route(next_day))
    hold, kept_block = previous["entries"]
    assert_work(hold, b, original_b["booking"])
    assert datetime.fromisoformat(hold["booking"]["expires_at"]) == held.expires_at
    assert kept_block == {
        "kind": "BLOCK",
        "block_id": block.json()["block_id"],
        "start": block_time(day, "14:00"),
        "end": block_time(day, "14:15"),
    }
    history = {row["selection"]["session_id"]: row for row in previous["history"]}
    assert len(history) == 2
    assert_work(history[a.selection.session_id], a, original_a["history"][0])
    assert_work(history[c.selection.session_id], c, original_c["booking"])
    assert history[c.selection.session_id]["successor"] is None
    assert history[a.selection.session_id]["successor"] == {
        "appointment_id": moved.booking.appointment_id,
        "date": str(next_day),
    }
    assert len(following["entries"]) == 1
    assert_work(following["entries"][0], a, original_a["booking"])
    assert await legacy_facts(h) == before
    receipt(
        "S7-0035-0036",
        previous_day=previous,
        following_day=following,
        preserved_receipt_count=len(before["receipts"]),
        schema=profile,
    )
