"""M7.1B proof through owner HTTP and real concurrent scheduling commands."""

import asyncio
import json
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from asm.scheduling.commands import (
    AvailabilityOffer,
    CalendarBlock,
    CalendarBlockInput,
    HoldResult,
    SelectionUnavailable,
    create_block,
    issue_offer,
    release_hold,
    select_option,
)
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.tenancy import AuthenticatedAccount
from asm.tenancy.database import TenantDatabase
from m5_knowledge_search_fixtures import owner_unit
from m7_scheduling_fixtures import POLICY, ZONE, accept_pair, accept_two_clients
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import scalar
from test_m6_owner_decisions_postgres import owner_get, owner_post
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
from test_tenancy_postgres import BA, BA2, UA, A

pytestmark = pytest.mark.integration
WEEK = [{"weekday": day, "start_minute": 600, "end_minute": 960} for day in range(7)]
POLICY = POLICY | {"buffer_before_minutes": 15, "buffer_after_minutes": 10}
CREATE_BLOCK = f"/api/v1/workspaces/{A}/businesses/{BA}/scheduling/blocks"


def receipt(case, **fields):
    print("M7.1B PostgreSQL", json.dumps({"case": case, **fields}, default=str))


async def client_effects(h):
    return await scalar(
        h,
        """SELECT jsonb_build_object(
        'outbox',(SELECT count(*) FROM app.outbox_events),
        'messages',(SELECT count(*) FROM app.messages WHERE direction='OUTBOUND'),
        'send_jobs',(SELECT count(*) FROM platform.messaging_jobs WHERE outbox_id IS NOT NULL),
        'dated_sessions',(SELECT count(*) FROM app.service_sessions WHERE scheduled_at IS NOT NULL),
        'appointments',(SELECT count(*) FROM app.appointments))""",
    )


async def assert_no_client_effects(h, before):
    after = await client_effects(h)
    assert after == before
    assert after["dated_sessions"] == 0
    return {"appointments": 0, "outbox": 0, "outbound_messages": 0, "send_jobs": 0}


async def occupancy(h):
    return await scalar(
        h,
        """SELECT jsonb_build_object(
          'offers',(SELECT count(*) FROM app.availability_offers),
          'options',(SELECT count(*) FROM app.availability_options),
          'holds',(SELECT count(*) FROM app.reservation_holds),
          'active_allocations',(SELECT count(*) FROM app.resource_allocations WHERE released_at IS NULL))""",
    )


async def configure(h, auth, token, work, *, policy=POLICY):
    preview = await owner_get(auth, work.preview_url())
    scheduled = await owner_post(
        auth,
        work.preview_url(),
        token,
        {
            "action": "schedule",
            "timezone": ZONE,
            "week": WEEK,
            "expected_version": preview["schedule_version"],
        },
    )
    day = date.fromisoformat(scheduled["date"])
    return day, await owner_post(
        auth,
        work.preview_url(day=day),
        token,
        policy | {"expected_version": scheduled["schedule_version"]},
    )


@pytest_asyncio.fixture
async def clients(scheduling_pg, auth):
    h = scheduling_pg
    token, a, b = await accept_two_clients(h, auth)
    return h, token, a, b


def choice(offer, index):
    return UUID(offer.options[index].option_id)


async def offer(h, work, day, key):
    async with owner_unit(h) as unit:
        return await issue_offer(unit, work.selection, day, key)


async def pick(h, work, option_id, key):
    async with owner_unit(h) as unit:
        return await select_option(unit, work.identity, work.selection, option_id, key)


async def release(h, work, hold, key):
    async with owner_unit(h) as unit:
        return await release_hold(unit, work.identity, work.selection, UUID(hold.hold_id), key)


async def backend_pid(unit):
    return (await unit._execute("SELECT pg_backend_pid()", {})).scalar_one()


async def blocked_by(h, waiter, holder):
    async with asyncio.timeout(1.5):
        while not await scalar(
            h, "SELECT :holder = ANY(pg_blocking_pids(:waiter))", holder=holder, waiter=waiter
        ):
            await asyncio.sleep(0.01)
    return await scalar(h, "SELECT clock_timestamp()")


async def compete(h, first, second):
    committed = asyncio.Event()
    started = asyncio.get_running_loop().create_future()

    async def contender():
        await committed.wait()
        async with owner_unit(h) as unit:
            started.set_result(await backend_pid(unit))
            return await second(unit)

    pending = asyncio.create_task(contender())
    try:
        async with owner_unit(h) as unit:
            winner = await first(unit)
            committed.set()
            waiter = await asyncio.wait_for(started, 3)
            moment = await blocked_by(h, waiter, await backend_pid(unit))
        return winner, await pending, moment
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


def selecting(work, option, key):
    async def run(unit):
        return await select_option(unit, work.identity, work.selection, option, key)

    return run


async def command_http(auth, token, endpoint, key, body):
    response = await auth.client.post(endpoint, headers=token | {"Idempotency-Key": key}, json=body)
    assert response.headers["cache-control"] == "no-store"
    return response


def offer_http(work):
    return (
        work.preview_url().split("?", 1)[0].removesuffix("/availability") + "/availability-offers"
    )


def local_interval(window):
    return {
        name: getattr(window, name).astimezone(ZoneInfo(ZONE)).isoformat()
        for name in ("visit_start", "visit_end", "busy_start", "busy_end")
    }


@pytest.mark.parametrize("second_option", [0, 5], ids=["visit-overlap", "buffer-only-overlap"])
async def test_s3_two_clients_choose_overlapping_options(clients, auth, second_option):
    h, token, a, b = clients
    day, preview = await configure(h, auth, token, a)
    before = await client_effects(h)
    assert len(preview["windows"]) > 2
    assert await occupancy(h) == {"offers": 0, "options": 0, "holds": 0, "active_allocations": 0}
    body = a.selection.model_dump(include={"client_id", "quote_id", "order_id"}) | {
        "date": str(day)
    }
    response = await command_http(auth, token, offer_http(a), "offer-a", body)
    assert response.status_code == 200, response.text
    offer_a = AvailabilityOffer.model_validate_json(response.content)
    assert await offer(h, a, day, "offer-a") == offer_a
    offer_b = await offer(h, b, day, "offer-b")
    assert offer_a.offer_id != offer_b.offer_id and offer_a.expires_at and offer_b.expires_at
    assert choice(offer_a, 0) != choice(offer_b, 0)
    assert await occupancy(h) == {"offers": 2, "options": 16, "holds": 0, "active_allocations": 0}

    win, lost, blocked = await compete(
        h,
        selecting(a, choice(offer_a, 0), "hold-a"),
        selecting(b, choice(offer_b, second_option), "hold-b"),
    )
    assert isinstance(win, HoldResult) and win.outcome == "HELD"
    assert isinstance(lost, SelectionUnavailable) and lost.outcome == "OPTION_UNAVAILABLE"
    assert blocked < win.expires_at
    assert lost.expires_at is not None and blocked < lost.expires_at
    after_conflict = {"offers": 3, "options": 24, "holds": 1, "active_allocations": 1}
    assert await occupancy(h) == after_conflict
    assert await pick(h, b, choice(offer_b, second_option), "hold-b") == lost
    assert await occupancy(h) == after_conflict

    stored = await scalar(
        h,
        """SELECT jsonb_build_object(
          'client',f.client_id,'session',f.session_id,'expires',f.expires_at,
          'options',jsonb_agg(o.id ORDER BY o.visit_start))
        FROM app.availability_offers f JOIN app.availability_options o
          ON (o.workspace_id,o.business_id,o.offer_id)=(f.workspace_id,f.business_id,f.id)
        WHERE (f.workspace_id,f.business_id,f.session_id)=(:ws,:business,:session)
          AND f.command_key IS NULL GROUP BY f.client_id,f.session_id,f.expires_at""",
        ws=A,
        business=BA,
        session=UUID(b.selection.session_id),
    )
    assert stored["client"] == b.identity.client_id and stored["session"] == b.selection.session_id
    assert stored["options"] == [window.option_id for window in lost.windows]
    assert datetime.fromisoformat(stored["expires"]) == lost.expires_at
    first, second = offer_a.options[0], offer_b.options[second_option]
    if second_option == 5:
        assert first.visit_end <= second.visit_start
    else:
        assert second.visit_start < first.visit_end
    assert second.busy_start < first.busy_end and first.busy_start < second.busy_end
    assert lost.windows and {window.visit_start for window in lost.windows}.isdisjoint(
        {item.visit_start for item in offer_b.options[:6]}
    )
    assert lost.windows[0].visit_start == offer_b.options[6].visit_start
    serialized = lost.model_dump_json()
    assert all(
        identifier not in serialized
        for identifier in (
            win.hold_id,
            win.allocation_id,
            a.identity.client_id,
            a.selection.session_id,
            offer_a.offer_id,
            first.option_id,
        )
    )
    assert all(
        set(row) == {"option_id", "visit_start", "visit_end"}
        for row in lost.model_dump()["windows"]
    )

    # The second application check is only one line of defence. Verify the
    # exclusion constraint itself with an independent direct transaction.
    resource = UUID(preview["resource_id"])
    with pytest.raises(DBAPIError) as collision:
        async with h.migrator.begin() as conn:
            await conn.execute(
                text("""
                INSERT INTO app.resource_allocations(workspace_id,business_id,resource_id,kind,occupied,created_at)
                VALUES(:ws,:business,:resource,'BLOCK',tstzrange(:starts,:ends,'[)'),clock_timestamp())
                """),
                {
                    "ws": A,
                    "business": BA,
                    "resource": resource,
                    "starts": second.busy_start,
                    "ends": second.busy_end,
                },
            )
    assert collision.value.orig.sqlstate == "23P01"
    assert collision.value.orig.diag.constraint_name == "resource_allocation_no_overlap"

    for identity, selection, option_id in (
        (b.identity, a.selection, choice(offer_a, 0)),
        (b.identity, b.selection, choice(offer_a, 0)),
        (b.identity, b.selection.model_copy(update={"business_id": str(BA2)}), choice(offer_b, 0)),
    ):
        with pytest.raises(ServiceRequestError) as denied:
            async with owner_unit(h) as unit:
                await select_option(unit, identity, selection, option_id, "wrong-client")
        assert denied.value.code is ServiceRequestCode.NOT_FOUND
    # 11:45 proves exact adjacency in the buffer-only case. For overlapping
    # visits choose 12:15, which exists only in the returned alternatives.
    wanted = "11:45" if second_option == 5 else "12:15"
    chosen = next(
        window for window in lost.windows if window.visit_start.strftime("%H:%M") == wanted
    )
    assert chosen.option_id not in {option.option_id for option in offer_b.options}
    if second_option != 5:
        assert chosen.visit_start not in {option.visit_start for option in offer_b.options}
    with pytest.raises(ServiceRequestError) as denied:
        await pick(h, a, UUID(chosen.option_id), "other-customer-alternative")
    assert denied.value.code is ServiceRequestCode.NOT_FOUND

    next_hold = await pick(h, b, UUID(chosen.option_id), "pick-alternative")
    assert isinstance(next_hold, HoldResult) and next_hold.outcome == "HELD"
    assert next_hold.visit_start == chosen.visit_start
    assert await pick(h, b, UUID(chosen.option_id), "pick-alternative") == next_hold
    assert await pick(h, b, choice(offer_b, second_option), "hold-b") == lost
    assert await pick(h, a, choice(offer_a, 0), "hold-a") == win
    after_pick = after_conflict | {"holds": 2, "active_allocations": 2}
    assert await occupancy(h) == after_pick

    active = await scalar(
        h,
        """SELECT jsonb_agg(jsonb_build_object(
          'hold_id',h.id,'allocation_id',r.id,'option_id',h.option_id,
          'busy_start',lower(r.occupied),'busy_end',upper(r.occupied),'expires',h.expires_at)
          ORDER BY lower(r.occupied))
        FROM app.resource_allocations r JOIN app.reservation_holds h
          ON (h.workspace_id,h.business_id,h.allocation_id)=(r.workspace_id,r.business_id,r.id)
        WHERE (r.workspace_id,r.business_id)=(:ws,:business) AND r.released_at IS NULL""",
        ws=A,
        business=BA,
    )
    for row, result, option_id in zip(
        active, (win, next_hold), (first.option_id, chosen.option_id), strict=True
    ):
        assert (row["hold_id"], row["allocation_id"], row["option_id"]) == (
            result.hold_id,
            result.allocation_id,
            option_id,
        )
        assert datetime.fromisoformat(row["expires"]) == result.expires_at
        for bound in ("busy_start", "busy_end"):
            row[bound] = datetime.fromisoformat(row[bound]).astimezone(ZoneInfo(ZONE)).isoformat()
    if second_option == 5:
        assert active[0]["busy_end"] == active[1]["busy_start"]
    else:
        assert active[0]["busy_end"] < active[1]["busy_start"]
    receipt(
        "R1-buffer-competition-adjacent" if second_option == 5 else "C0-M7.1B-01",
        first_client=a.identity.client_id,
        second_client=b.identity.client_id,
        original_b=[
            window.visit_start.astimezone(ZoneInfo(ZONE)).isoformat() for window in offer_b.options
        ],
        conflict_second=local_interval(second),
        alternative_expiry=lost.expires_at,
        offered_option_ids=stored["options"],
        chosen=chosen.model_dump(mode="json"),
        active=active,
        exact_replay=True,
        wait_observed_at=blocked,
        exclusion=collision.value.orig.sqlstate,
        after_conflict=after_conflict,
        after_pick=after_pick,
        **(await assert_no_client_effects(h, before)),
    )

    # A simultaneous window in a different business has a different resource,
    # even inside the same workspace.
    async with owner_unit(h) as unit:
        await unit.scheduling_owner_command(
            BA2,
            a.material["service_id"],
            "schedule",
            {"timezone": ZONE, "week": WEEK, "expected_version": 0},
        )
        independent = await create_block(
            unit,
            BA2,
            CalendarBlockInput(start=first.busy_start, end=first.busy_end),
            "other-business",
        )
    assert isinstance(independent, CalendarBlock) and independent.outcome == "BLOCKED"
    receipt(
        "S3-other-business",
        exact_adjacency=second_option == 5,
        second_hold=next_hold.hold_id,
        second_busy_start=active[1]["busy_start"],
        other_business_block=independent.block_id,
        interval=local_interval(first),
        **(await assert_no_client_effects(h, before)),
    )


async def test_r1_fully_occupied_day_returns_empty_alternatives(clients, auth):
    h, token, a, b = clients
    day, configured = await configure(h, auth, token, a)
    await owner_post(
        auth,
        a.preview_url(day=day),
        token,
        {
            "action": "exception",
            "date": str(day),
            "windows": [{"start_minute": 600, "end_minute": 690}],
            "expected_version": configured["schedule_version"],
        },
    )
    before = await client_effects(h)
    first = await offer(h, a, day, "only-window-a")
    second = await offer(h, b, day, "only-window-b")
    assert len(first.options) == len(second.options) == 1
    winner, lost, _ = await compete(
        h,
        selecting(a, choice(first, 0), "only-hold-a"),
        selecting(b, choice(second, 0), "only-hold-b"),
    )
    assert isinstance(winner, HoldResult) and winner.outcome == "HELD"
    assert isinstance(lost, SelectionUnavailable) and lost.outcome == "OPTION_UNAVAILABLE"
    assert (
        lost.date == day
        and lost.timezone == ZONE
        and lost.expires_at is None
        and lost.windows == []
    )
    assert all(
        identifier not in lost.model_dump_json()
        for identifier in (
            winner.hold_id,
            winner.allocation_id,
            a.selection.session_id,
            first.options[0].option_id,
        )
    )
    assert await pick(h, b, choice(second, 0), "only-hold-b") == lost
    counts = await occupancy(h)
    assert counts == {"offers": 2, "options": 2, "holds": 1, "active_allocations": 1}
    receipt(
        "R1-fully-occupied-day",
        allocated=local_interval(first.options[0]),
        response=lost.model_dump(mode="json"),
        exact_replay=True,
        counts=counts,
        **(await assert_no_client_effects(h, before)),
    )


async def test_r1_empty_issuance_is_idempotent_after_opening_day(clients, auth):
    h, token, a, _ = clients
    endpoint = offer_http(a)
    references = a.selection.model_dump(include={"client_id", "quote_id", "order_id"})
    before = await client_effects(h)
    zero = {"offers": 0, "options": 0, "holds": 0, "active_allocations": 0}
    missing = await command_http(auth, token, endpoint, "before-calendar", references)
    assert missing.status_code == 200, missing.text
    assert missing.json()["timezone"] is None and missing.json()["options"] == []
    assert await occupancy(h) == zero

    day, configured = await configure(h, auth, token, a)
    earlier = await command_http(auth, token, endpoint, "before-calendar", references)
    assert earlier.status_code == 200 and earlier.json() == missing.json()
    request = references | {"date": str(day)}
    preview_url = a.preview_url(day=day)
    closed = await owner_post(
        auth,
        preview_url,
        token,
        {
            "action": "exception",
            "date": str(day),
            "windows": [],
            "expected_version": configured["schedule_version"],
        },
    )
    empty = await command_http(auth, token, endpoint, "closed-day", request)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {
        "offer_id": None,
        "date": str(day),
        "timezone": ZONE,
        "expires_at": None,
        "options": [],
    }
    assert await occupancy(h) == zero
    await owner_post(
        auth,
        preview_url,
        token,
        {
            "action": "exception",
            "date": str(day),
            "windows": None,
            "expected_version": closed["schedule_version"],
        },
    )

    repeated = await command_http(auth, token, endpoint, "closed-day", request)
    assert repeated.status_code == 200 and repeated.json() == empty.json()
    assert await occupancy(h) == zero
    changed = await command_http(
        auth,
        token,
        endpoint,
        "closed-day",
        request | {"date": str(day + timedelta(days=1))},
    )
    assert (
        changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    )
    assert await occupancy(h) == zero
    fresh = await command_http(auth, token, endpoint, "reopened-day", request)
    assert fresh.status_code == 200, fresh.text
    issued = AvailabilityOffer.model_validate_json(fresh.content)
    assert issued.date == day and issued.expires_at is not None and len(issued.options) == 8
    counts = await occupancy(h)
    assert counts == zero | {"offers": 1, "options": 8}
    receipt(
        "C0-M7.1B-02",
        date=str(day),
        closed=empty.status_code,
        exact_repeat_status=repeated.status_code,
        exact_repeat_options=len(repeated.json()["options"]),
        different_date_status=changed.status_code,
        different_date_error=changed.json()["error"]["code"],
        new_key_status=fresh.status_code,
        new_key_first=local_interval(issued.options[0]),
        expiry=issued.expires_at,
        before=zero,
        after=counts,
        **(await assert_no_client_effects(h, before)),
    )


async def test_s3_two_disjoint_options_of_same_session(scheduling_pg, auth):
    h = scheduling_pg
    token, a, other_work = await accept_pair(h, auth)
    assert (
        a.identity == other_work.identity
        and a.selection.session_id != other_work.selection.session_id
    )
    day, _ = await configure(h, auth, token, a)
    before = await client_effects(h)
    options = await offer(h, a, day, "options-for-a")
    assert options.options[0].busy_end == options.options[6].busy_start
    with pytest.raises(ServiceRequestError) as other_session:
        await pick(h, other_work, choice(options, 0), "wrong-work")
    assert other_session.value.code is ServiceRequestCode.NOT_FOUND
    win, lost, _ = await compete(
        h,
        selecting(a, choice(options, 0), "session-first"),
        selecting(a, choice(options, 6), "session-other"),
    )
    assert isinstance(win, HoldResult) and win.outcome == "HELD"
    assert isinstance(lost, SelectionUnavailable) and lost.outcome == "SESSION_HELD"
    assert (await occupancy(h))["holds"] == (await occupancy(h))["active_allocations"] == 1
    receipt(
        "S3-same-session",
        first=win.hold_id,
        second=lost.outcome,
        windows=[local_interval(options.options[i]) for i in (0, 6)],
        expires_at=win.expires_at,
        **(await assert_no_client_effects(h, before)),
    )


@pytest.mark.parametrize(
    "block_first", [True, False], ids=["block-before-hold", "hold-before-block"]
)
async def test_s4_hold_and_block_and_close_day(clients, auth, block_first):
    h, token, a, _ = clients
    day, preview = await configure(h, auth, token, a)
    before = await client_effects(h)
    proposed = await offer(h, a, day, "issue")
    chosen = proposed.options[0]
    block_body = {"start": chosen.busy_start.isoformat(), "end": chosen.busy_end.isoformat()}
    block = CalendarBlockInput.model_validate_json(json.dumps(block_body))
    hold = selecting(a, choice(proposed, 0), "selection")

    async def block_time(unit):
        return await create_block(unit, BA, block, "blocking")

    if block_first:
        winner, denied, _ = await compete(h, block_time, hold)
        assert isinstance(winner, CalendarBlock) and winner.outcome == "BLOCKED"
        assert isinstance(denied, SelectionUnavailable) and denied.outcome == "OPTION_UNAVAILABLE"
        assert winner.block_id not in denied.model_dump_json()
        assert (await occupancy(h))["holds"] == 0
        assert len((await owner_get(auth, a.preview_url(day=day)))["windows"]) < len(
            preview["windows"]
        )
        endpoint = f"{CREATE_BLOCK}/{winner.block_id}/release"
        response = await command_http(auth, token, endpoint, "unblock", {})
        assert response.status_code == 200 and response.json()["outcome"] == "RELEASED"
        assert (await owner_get(auth, a.preview_url(day=day)))["windows"] == preview["windows"]
        assert (await pick(h, a, choice(proposed, 0), "old-option")).outcome == "OPTION_UNAVAILABLE"
        fresh = await offer(h, a, day, "fresh")
        winner_hold = await pick(h, a, choice(fresh, 0), "after-block")
        assert isinstance(winner_hold, HoldResult) and winner_hold.outcome == "HELD"
        late = await command_http(auth, token, endpoint, "unblock", {})
        assert late.json() == response.json()
        assert (await occupancy(h))["active_allocations"] == 1
        receipt(
            "S4-block-first",
            blocked=winner.block_id,
            rejected=denied.outcome,
            interval=local_interval(chosen),
            held_after_release=winner_hold.model_dump(mode="json"),
            **(await assert_no_client_effects(h, before)),
        )
    else:
        winner_hold, denied, _ = await compete(h, hold, block_time)
        assert isinstance(winner_hold, HoldResult) and winner_hold.outcome == "HELD"
        assert denied.model_dump()["outcome"] == "CALENDAR_CONFLICT"
        affected = [{"kind": "HOLD", "id": winner_hold.hold_id}]
        response = await command_http(auth, token, CREATE_BLOCK, "blocking", block_body)
        assert response.status_code == 409 and response.json()["error"]["affected"] == affected
        endpoint = a.preview_url(day=day)
        for body in (
            {"action": "exception", "date": str(day), "windows": []},
            {"action": "schedule", "timezone": ZONE, "week": []},
        ):
            closed = await auth.client.post(
                endpoint,
                headers=token,
                json=body | {"expected_version": preview["schedule_version"]},
            )
            assert closed.status_code == 409 and closed.json()["error"]["affected"] == affected
        current = await owner_get(auth, endpoint)
        assert current["exception"] is None and current["week"] == WEEK
        assert current["schedule_version"] == preview["schedule_version"]
        await owner_post(
            auth,
            endpoint,
            token,
            POLICY
            | {
                "expected_version": preview["schedule_version"],
                "hold_ttl_minutes": 1,
            },
        )
        assert await pick(h, a, choice(proposed, 0), "selection") == winner_hold
        released = await release(h, a, winner_hold, "release")
        assert released.outcome == "RELEASED" and released.expires_at == winner_hold.expires_at
        assert await release(h, a, winner_hold, "release") == released
        response = await command_http(auth, token, CREATE_BLOCK, "blocking-fresh", block_body)
        assert response.status_code == 200 and response.json()["outcome"] == "BLOCKED"
        assert await release(h, a, winner_hold, "release") == released
        assert (await occupancy(h))["active_allocations"] == 1
        receipt(
            "S4-hold-first",
            hold=winner_hold.model_dump(mode="json"),
            interval=local_interval(chosen),
            conflicts=affected,
            released=released.outcome,
            later_block=response.json()["block_id"],
            **(await assert_no_client_effects(h, before)),
        )


async def expiry_boundary(h, hold, resource):
    moment = hold.expires_at
    async with h.migrator.connect() as connection:
        async with connection.begin():
            checks = []
            for delta in (-1, 0, 1):
                when = moment + timedelta(microseconds=delta)
                params = {
                    "ws": A,
                    "business": BA,
                    "resource": resource,
                    "when": when,
                    "hold": UUID(hold.hold_id),
                }
                present = (
                    await connection.execute(
                        text("""
                    SELECT count(*) FROM platform.scheduling_active_allocations(:ws,:business,:resource,:when)
                    """),
                        params,
                    )
                ).scalar_one()
                nested = await connection.begin_nested()
                await connection.execute(
                    text("""
                    SELECT platform.scheduling_expire_holds(:ws,:business,:resource,a.occupied,h.session_id,:when)
                    FROM app.reservation_holds h JOIN app.resource_allocations a
                      ON (a.workspace_id,a.business_id,a.id)=(h.workspace_id,h.business_id,h.allocation_id)
                    WHERE h.workspace_id=:ws AND h.business_id=:business AND h.id=:hold
                    """),
                    params,
                )
                state = (
                    await connection.execute(
                        text("""
                    SELECT release_reason FROM app.resource_allocations
                    WHERE (workspace_id,business_id,id)=(:ws,:business,:allocation)
                    """),
                        params | {"allocation": UUID(hold.allocation_id)},
                    )
                ).scalar_one()
                await nested.rollback()
                checks.append(
                    {"at": when, "delta_us": delta, "read_active": present, "write_state": state}
                )
    assert [(row["read_active"], row["write_state"]) for row in checks] == [
        (1, None),
        (0, "EXPIRED"),
        (0, "EXPIRED"),
    ]
    return checks


async def test_s4_expiry_after_wait_restart_and_late_replay(clients, auth):
    h, token, a, b = clients
    day, preview = await configure(h, auth, token, a, policy=POLICY | {"hold_ttl_minutes": 1})
    before = await client_effects(h)
    offer_a = await offer(h, a, day, "issue-a")
    offer_b = await offer(h, b, day, "issue-b")
    assert offer_a.options[0].busy_start == offer_b.options[0].busy_start
    first = await pick(h, a, choice(offer_a, 0), "choose-a")
    assert isinstance(first, HoldResult) and first.outcome == "HELD"
    assert first.expires_at - await scalar(
        h, "SELECT created_at FROM app.reservation_holds WHERE id=:id", id=UUID(first.hold_id)
    ) == timedelta(minutes=1)

    # Simulate a lost response, then reconstruct the connection pool and app
    # transaction. Persistence must supply the exact same hold and TTL.
    restarted_engine = create_async_engine(h.runtime.engine.url, hide_parameters=True)
    try:
        restarted = TenantDatabase(restarted_engine)
        async with restarted.transaction(AuthenticatedAccount(UA), A, UUID(first.hold_id)) as unit:
            result = await select_option(
                unit, a.identity, a.selection, choice(offer_a, 0), "choose-a"
            )
            two_tabs = await select_option(
                unit, a.identity, a.selection, choice(offer_a, 0), "tab-2"
            )
            assert result == two_tabs == first
        with pytest.raises(ServiceRequestError) as mismatch:
            async with owner_unit(h) as unit:
                await select_option(unit, a.identity, a.selection, choice(offer_a, 1), "choose-a")
        assert mismatch.value.code is ServiceRequestCode.IDEMPOTENCY_KEY_CONFLICT
    finally:
        await restarted_engine.dispose()

    resource = UUID(preview["resource_id"])
    boundary = await expiry_boundary(h, first, resource)
    begin = asyncio.Event()
    started = asyncio.get_running_loop().create_future()

    async def next_client():
        await begin.wait()
        async with owner_unit(h) as unit:
            started.set_result(await backend_pid(unit))
            return await select_option(
                unit, b.identity, b.selection, choice(offer_b, 0), "choose-b"
            )

    pending = asyncio.create_task(next_client())
    try:
        async with h.migrator.begin() as lock:
            await lock.execute(
                text("SELECT pg_sleep_until(:at)"), {"at": first.expires_at - timedelta(seconds=1)}
            )
            holder = (
                await lock.execute(
                    text("""
                SELECT pg_backend_pid() FROM app.scheduling_resources
                WHERE (workspace_id,business_id,id)=(:ws,:business,:resource) FOR UPDATE
                """),
                    {"ws": A, "business": BA, "resource": resource},
                )
            ).scalar_one()
            begin.set()
            waiting = await blocked_by(h, await asyncio.wait_for(started, 3), holder)
            assert waiting < first.expires_at
            await lock.execute(
                text("SELECT pg_sleep_until(:at)"),
                {"at": first.expires_at + timedelta(milliseconds=100)},
            )
        second = await pending
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    assert (
        isinstance(second, HoldResult)
        and second.outcome == "HELD"
        and second.hold_id != first.hold_id
    )
    second_created = second.expires_at - timedelta(minutes=1)
    assert second_created >= first.expires_at
    assert second_created < offer_b.expires_at
    replay = await pick(h, a, choice(offer_a, 0), "choose-a")
    assert replay == first.model_copy(update={"outcome": "EXPIRED"})
    assert await pick(h, a, choice(offer_a, 0), "late-tab") == replay
    assert await release(h, a, first, "late-release") == replay
    assert await pick(h, b, choice(offer_b, 0), "choose-b") == second
    active = await scalar(
        h,
        """
        SELECT jsonb_build_object('id',h.id,'owner',f.client_id,'expires_at',h.expires_at)
        FROM app.resource_allocations a JOIN app.reservation_holds h
          ON (a.workspace_id,a.business_id,a.id)=(h.workspace_id,h.business_id,h.allocation_id)
        JOIN app.availability_options o ON (o.workspace_id,o.business_id,o.id)=(h.workspace_id,h.business_id,h.option_id)
        JOIN app.availability_offers f ON (f.workspace_id,f.business_id,f.id)=(o.workspace_id,o.business_id,o.offer_id)
        WHERE a.released_at IS NULL
        """,
    )
    assert active["id"] == second.hold_id and active["owner"] == b.identity.client_id
    assert datetime.fromisoformat(active["expires_at"]) == second.expires_at
    assert (await occupancy(h))["holds"] == 2 and (await occupancy(h))["active_allocations"] == 1
    receipt(
        "S4-expiry-after-lock",
        interval=local_interval(offer_a.options[0]),
        first=first.model_dump(mode="json"),
        next=second.model_dump(mode="json"),
        exact_boundary=boundary,
        waited_before_expiry=waiting,
        acquired_after_expiry=second_created,
        late_result=replay.outcome,
        winning_offer_expires_at=offer_b.expires_at,
        active=active,
        **(await assert_no_client_effects(h, before)),
    )


async def test_s4_changed_schedule_and_upgrade_preserve_agreement(clients, auth):
    h, token, a, _ = clients
    # Build the operational calendar and close a date on the preceding
    # revision, with real accepted M6 work present.
    await _migrate("downgrade", "0032")
    try:
        day, preview = await configure(h, auth, token, a)
        endpoint = a.preview_url(day=day)
        closed = await owner_post(
            auth,
            endpoint,
            token,
            {
                "action": "exception",
                "date": str(day),
                "windows": [],
                "expected_version": preview["schedule_version"],
            },
        )
    finally:
        try:
            await _migrate("upgrade", "0033")
            assert (await scalar(h, "SELECT platform.scheduling_hold_schema_profile()"))["valid"]
        finally:
            await _migrate("upgrade", "0039")
    assert await owner_get(auth, endpoint) == closed
    assert (await owner_get(auth, a.url + "/quote"))["agreement"] == a.agreement
    before = await client_effects(h)
    opened = await owner_post(
        auth,
        endpoint,
        token,
        {
            "action": "exception",
            "date": str(day),
            "windows": None,
            "expected_version": closed["schedule_version"],
        },
    )
    original = await offer(h, a, day, "old-issued-option")
    closed_again = await owner_post(
        auth,
        endpoint,
        token,
        {
            "action": "exception",
            "date": str(day),
            "windows": [],
            "expected_version": opened["schedule_version"],
        },
    )
    stale = await pick(h, a, choice(original, 0), "old-pick")
    assert isinstance(stale, SelectionUnavailable) and stale.outcome == "OPTION_UNAVAILABLE"
    assert not stale.windows and (await occupancy(h))["holds"] == 0
    await owner_post(
        auth,
        endpoint,
        token,
        {
            "action": "exception",
            "date": str(day),
            "windows": None,
            "expected_version": closed_again["schedule_version"],
        },
    )
    assert (
        await pick(h, a, choice(original, 0), "retry-not-fresh")
    ).outcome == "OPTION_UNAVAILABLE"
    new = await offer(h, a, day, "fresh-issued-option")
    selected = await pick(h, a, choice(new, 0), "fresh-pick")
    assert isinstance(selected, HoldResult) and selected.outcome == "HELD"
    receipt(
        "S4-in-place-migration-and-fresh-option",
        session=a.selection.session_id,
        old_option=original.options[0].option_id,
        fresh_option=new.options[0].option_id,
        outcome=selected.outcome,
        expires_at=selected.expires_at,
        window=local_interval(new.options[0]),
        **(await assert_no_client_effects(h, before)),
    )
