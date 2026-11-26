"""M7.2A acceptance, replay and allocation proof on real PostgreSQL."""

import asyncio
import json
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from asm.scheduling.commands import (
    AppointmentResult,
    CalendarBlock,
    CalendarBlockInput,
    HoldResult,
    SelectionUnavailable,
    create_block,
    select_option,
)
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.tenancy import AuthenticatedAccount
from asm.tenancy.database import TenantDatabase
from m5_knowledge_search_fixtures import owner_unit
from m7_scheduling_fixtures import (
    ZONE,
    Work,
    accept_pair,
    accept_two_clients,
    accept_work,
    booking_contract,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import scalar
from test_m6_owner_decisions_postgres import owner_get
from test_m6_pricing_postgres import publish, sign_in
from test_m7_scheduling_holds_postgres import (
    CREATE_BLOCK,
    POLICY,
    backend_pid,
    blocked_by,
    choice,
    client_effects,
    command_http,
    compete,
    configure,
    local_interval,
    occupancy,
    offer,
    pick,
    release,
    selecting,
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
from test_tenancy_postgres import BA, BA2, BB, UA, A, B

pytestmark = pytest.mark.integration


def proof(case, **details):
    print(
        "M7.2A PostgreSQL", json.dumps({"case": case, **details}, default=str, ensure_ascii=False)
    )


async def assert_effects(h, before, *, confirmed=0):
    assert await client_effects(h) == before | {"appointments": before["appointments"] + confirmed}
    assert before["dated_sessions"] == 0
    assert not await scalar(
        h,
        """SELECT count(*) FROM pg_tables WHERE schemaname='app' AND tablename IN
          ('payment_requests','payment_sessions','payment_transactions','payment_refunds')""",
    )
    return {"payments": 0, "outbox": 0, "outbound_messages": 0, "send_jobs": 0}


async def booking(auth, work):
    actual = await owner_get(auth, work.booking_url())
    assert {key: actual[key] for key in ("request_id", "quote_id", "order_id", "session_id")} == (
        work.selection.model_dump(include={"request_id", "quote_id", "order_id", "session_id"})
    )
    assert (await owner_get(auth, work.url + "/quote"))["agreement"] == work.agreement
    return actual["booking"]


async def historical_quote(h, auth, work):
    # The quote was genuinely accepted through M6. Shorten only its old
    # validity in this fixture so acceptance_at < expiry < choice time.
    async with h.migrator.begin() as connection:
        await connection.execute(text("ALTER TABLE app.quotes DISABLE TRIGGER quote_immutable"))
        adjusted = await connection.execute(
            text("""
            WITH expiry AS (
              SELECT accepted_at+interval '1 microsecond' AS moment
              FROM app.quote_acceptances WHERE (workspace_id,quote_id)=(:ws,:quote)
            )
            UPDATE app.quotes q SET expires_at=expiry.moment,
              terms_sha256=platform.quote_hash(jsonb_build_array('quote_v1',q.id,q.version,q.code,
                platform.quote_timestamp(expiry.moment),q.material,q.text))
            FROM expiry WHERE (q.workspace_id,q.id)=(:ws,:quote)
            RETURNING q.expires_at<clock_timestamp()
            """),
            {"ws": A, "quote": UUID(work.selection.quote_id)},
        )
        assert adjusted.scalar_one()
        await connection.execute(text("ALTER TABLE app.quotes ENABLE TRIGGER quote_immutable"))
    accepted = Work(work.url, (await owner_get(auth, work.url + "/quote"))["agreement"])
    assert accepted.selection == work.selection
    return accepted


async def original_hold_deadline(h, selection_result):
    hold = await scalar(
        h,
        "SELECT to_jsonb(h) FROM app.reservation_holds h WHERE (workspace_id,id)=(:ws,:id)",
        ws=A,
        id=UUID(selection_result.hold_id),
    )
    expires_at = datetime.fromisoformat(hold["expires_at"])
    assert expires_at - datetime.fromisoformat(hold["created_at"]) == timedelta(minutes=15)
    return expires_at


@pytest.mark.parametrize("mode", ["NONE", "FIXED_DEPOSIT", "PERCENT_DEPOSIT", "FULL_PREPAYMENT"])
async def test_s5_one_choice_uses_accepted_terms_after_quote_expiry(
    scheduling_pg, auth, monkeypatch, mode
):
    h = scheduling_pg
    other = None
    if mode == "FIXED_DEPOSIT":
        token, work, other = await accept_pair(h, auth)
        assert work.selection.client_id == other.selection.client_id
        assert work.selection.conversation_id == other.selection.conversation_id
        assert work.selection.session_id != other.selection.session_id
    else:
        await publish(h, booking_contract(mode))
        token = await sign_in(auth)
        work = await accept_work(h, auth, token, "20 mm")
    work = await historical_quote(h, auth, work)
    assert work.material["deposit"]["mode"] == mode
    if other is not None:
        assert other.material["deposit"]["mode"] == mode
        assert await booking(auth, other) is None
    replacement = None
    if mode != "NONE":
        replacement = await publish(h, booking_contract("NONE"))
        assert replacement["release_id"] != work.material["deposit_terms_version"]
    day, schedule = await configure(h, auth, token, work)
    assert await booking(auth, work) is None
    issued = await offer(h, work, day, "issue-s5")
    option = issued.options[0]
    before = await client_effects(h)

    def reject_http(*args, **kwargs):
        pytest.fail("Choosing an option must not call an HTTP provider")

    async def choose(selected_work, option_id, key):
        with monkeypatch.context() as isolated:
            isolated.setattr(httpx.Client, "send", reject_http)
            isolated.setattr(httpx.AsyncClient, "send", reject_http)
            return await pick(h, selected_work, option_id, key)

    result = await choose(work, choice(issued, 0), "one-explicit-choice")

    shown = await booking(auth, work)
    again = await booking(auth, work)
    assert shown == again
    assert shown["hold_id"] == result.hold_id
    assert shown["resource_id"] == schedule["resource_id"]
    assert shown["allocation_id"] == result.allocation_id
    assert shown["timezone"] == ZONE and shown["date"] == str(day) and result.date == day
    interval = local_interval(option)
    assert all(
        datetime.fromisoformat(shown[key]) == datetime.fromisoformat(value)
        for key, value in interval.items()
    )
    assert result.visit_start == option.visit_start and result.visit_end == option.visit_end
    assert await choose(work, choice(issued, 0), "one-explicit-choice") == result
    expires_at = await original_hold_deadline(h, result)
    if mode == "NONE":
        assert isinstance(result, AppointmentResult) and shown["outcome"] == "CONFIRMED"
        assert shown["appointment_id"] == result.appointment_id
        assert (
            result.session_id == work.selection.session_id
            and result.message == "Запись подтверждена."
        )
        stored = await scalar(
            h,
            "SELECT to_jsonb(a) FROM app.appointments a WHERE (workspace_id,id)=(:ws,:id)",
            ws=A,
            id=UUID(result.appointment_id),
        )
        assert datetime.fromisoformat(stored["visit_start"]) == result.visit_start
        assert datetime.fromisoformat(stored["visit_end"]) == result.visit_end
    else:
        assert isinstance(result, HoldResult) and shown["outcome"] == "HELD" == result.outcome
        assert datetime.fromisoformat(shown["expires_at"]) == expires_at == result.expires_at
        assert result.message == (
            f"Время удержано до {expires_at.astimezone(ZoneInfo(ZONE)):%d.%m.%Y %H:%M:%S} "
            f"({ZONE}), запись не подтверждена."
        )
        assert "appointment_id" not in shown

    if other is not None:
        assert await booking(auth, other) is None
        wrong = await auth.client.get(work.booking_url(session_id=other.selection.session_id))
        assert wrong.status_code == 404 and work.selection.session_id not in wrong.text
        assert replacement is not None
        assert other.material["deposit_terms_version"] != replacement["release_id"]
        second_offer = await offer(h, other, day, "issue-s5-second-work")
        second_option = second_offer.options[0]
        assert option.busy_end == second_option.busy_start
        assert second_option.visit_start.astimezone(ZoneInfo(ZONE)).strftime("%H:%M") == "11:45"
        second = await choose(other, choice(second_offer, 0), "choice-second-work")
        assert isinstance(second, HoldResult) and second.outcome == "HELD"
        assert second.hold_id != result.hold_id and second.allocation_id != result.allocation_id
        deadline = await original_hold_deadline(h, second)
        second_card = await booking(auth, other)
        assert second_card["outcome"] == "HELD" and "appointment_id" not in second_card
        assert second_card["hold_id"] == second.hold_id
        assert second_card["allocation_id"] == second.allocation_id
        assert second_card["resource_id"] == shown["resource_id"]
        assert second_card["date"] == str(day) and second_card["timezone"] == ZONE
        assert datetime.fromisoformat(second_card["expires_at"]) == deadline == second.expires_at
        second_interval = local_interval(second_option)
        assert all(
            datetime.fromisoformat(second_card[key]) == datetime.fromisoformat(value)
            for key, value in second_interval.items()
        )
        assert (
            second.visit_start == second_option.visit_start
            and second.visit_end == second_option.visit_end
        )
        assert await choose(other, choice(second_offer, 0), "choice-second-work") == second
        assert await choose(work, choice(issued, 0), "one-explicit-choice") == result
        assert await booking(auth, work) == shown and await booking(auth, other) == second_card
        counts = await occupancy(h)
        assert counts["holds"] == counts["active_allocations"] == 2
        proof(
            "R1-two-fixed-deposit-works",
            client_id=work.selection.client_id,
            conversation_id=work.selection.conversation_id,
            published_none_release=replacement["release_id"],
            rose={
                **work.proof(),
                "deposit": work.material["deposit"],
                "deposit_terms_version": work.material["deposit_terms_version"],
                "option_id": option.option_id,
                "result": result.model_dump(mode="json"),
                "owner_booking": shown,
                "hold_expires_at": expires_at,
                "interval": interval,
            },
            swallow={
                **other.proof(),
                "deposit": other.material["deposit"],
                "deposit_terms_version": other.material["deposit_terms_version"],
                "option_id": second_option.option_id,
                "result": second.model_dump(mode="json"),
                "owner_booking": second_card,
                "hold_expires_at": deadline,
                "interval": second_interval,
            },
            active_holds=counts["active_allocations"],
            new_appointments=0,
            external_calls=0,
            **(await assert_effects(h, before)),
        )
    for url, status in (
        (work.booking_url(client_id="00000000-0000-0000-0000-000000000999"), 404),
        (work.booking_url(business_id=BA2), 404),
        (work.booking_url(workspace_id=B, business_id=BB), 403),
    ):
        refused = await auth.client.get(url)
        assert refused.status_code == status and result.hold_id not in refused.text
    assert (await occupancy(h))["active_allocations"] == (2 if other is not None else 1)
    proof(
        "S5-expired-quote",
        mode=mode,
        **work.proof(),
        deposit_terms_version=work.material["deposit_terms_version"],
        quote_expires_at=work.agreement["quote"]["expires_at"],
        accepted_at=work.agreement["accepted_at"],
        option_id=option.option_id,
        result=result.model_dump(mode="json"),
        hold_expires_at=expires_at,
        interval=interval,
        external_calls=0,
        **(await assert_effects(h, before, confirmed=int(mode == "NONE"))),
    )


async def test_s5_after_lost_response_and_original_hold_expiry(scheduling_pg, auth):
    h = scheduling_pg
    token, work, competitor = await accept_two_clients(
        h, auth, first_mode="NONE", second_mode="FIXED_DEPOSIT"
    )
    day, schedule = await configure(h, auth, token, work, policy=POLICY | {"hold_ttl_minutes": 1})
    issued = await offer(h, work, day, "original-issue")
    other = await offer(h, competitor, day, "competitor-issue")
    original, different = choice(issued, 0), choice(issued, 6)
    before = await client_effects(h)

    class LostReply(Exception):
        pass

    async def choose_then_lose_reply():
        await pick(h, work, original, "same-choice")
        # pick returns only after commit and release of the connection.
        raise LostReply

    with pytest.raises(LostReply):
        await choose_then_lose_reply()
    saved = await booking(auth, work)
    assert saved["outcome"] == "CONFIRMED"
    first, second, waited = await compete(
        h, selecting(work, original, "same-choice"), selecting(work, original, "same-choice")
    )
    assert isinstance(first, AppointmentResult) and first == second
    assert first.appointment_id == saved["appointment_id"]
    assert await pick(h, work, original, "second-tab-new-key") == first
    with pytest.raises(ServiceRequestError) as mismatch:
        await pick(h, work, different, "same-choice")
    assert mismatch.value.code is ServiceRequestCode.IDEMPOTENCY_KEY_CONFLICT
    second_tab = await pick(h, work, different, "other-option")
    assert await pick(h, work, different, "other-option") == second_tab
    assert await pick(h, work, original, "same-choice") == first
    assert await booking(auth, work) == saved
    original_time, requested_time = (issued.options[index] for index in (0, 6))
    assert original_time.busy_end == requested_time.busy_start
    assert original_time.visit_start.astimezone(ZoneInfo(ZONE)).strftime("%H:%M") == "10:15"
    assert requested_time.visit_start.astimezone(ZoneInfo(ZONE)).strftime("%H:%M") == "11:45"
    preview = await owner_get(auth, competitor.preview_url(day=day))
    free_interval = local_interval(requested_time)
    assert free_interval in preview["windows"]
    counts = await occupancy(h)
    assert counts["holds"] == counts["active_allocations"] == 1
    proof(
        "R1-second-tab-different-option",
        **work.proof(),
        first_choice=first.model_dump(mode="json"),
        requested_option_id=requested_time.option_id,
        second_choice=second_tab.model_dump(mode="json"),
        owner_booking=saved,
        free_interval=free_interval,
        appointments=(await client_effects(h))["appointments"] - before["appointments"],
        active_allocations=counts["active_allocations"],
        **(await assert_effects(h, before, confirmed=1)),
    )
    assert isinstance(second_tab, AppointmentResult) and second_tab.outcome == "ALREADY_CONFIRMED"
    assert second_tab == first.model_copy(update={"outcome": "ALREADY_CONFIRMED"})
    assert second_tab.message == "Вы уже записаны на 10:15."
    assert second_tab.session_id == work.selection.session_id
    assert all(
        second_tab.model_dump(mode="json")[key] == saved[key]
        for key in (
            "appointment_id",
            "allocation_id",
            "hold_id",
            "date",
            "visit_start",
            "visit_end",
            "timezone",
        )
    )

    engine = create_async_engine(h.runtime.engine.url, hide_parameters=True)
    try:
        async with TenantDatabase(engine).transaction(AuthenticatedAccount(UA), A, BA) as unit:
            assert (
                await select_option(unit, work.identity, work.selection, original, "same-choice")
                == first
            )
    finally:
        await engine.dispose()

    expires_at = await scalar(
        h, "SELECT expires_at FROM app.reservation_holds WHERE id=:id", id=UUID(first.hold_id)
    )
    assert waited < expires_at
    await scalar(h, "SELECT pg_sleep_until(:after)", after=expires_at + timedelta(milliseconds=100))
    assert await pick(h, work, original, "same-choice") == first
    assert await pick(h, work, different, "other-option") == second_tab
    late = await release(h, work, first, "late-release")
    assert late.outcome == "CONVERTED" and late.expires_at == expires_at
    assert await release(h, work, first, "late-release") == late
    denied = await pick(h, competitor, choice(other, 0), "late-overlap")
    assert isinstance(denied, SelectionUnavailable) and denied.outcome == "OPTION_UNAVAILABLE"
    assert await booking(auth, work) == saved
    assert await booking(auth, competitor) is None
    occupied = await scalar(
        h,
        """SELECT jsonb_build_object('id',a.id,'kind',a.kind,'released_at',a.released_at,
             'busy_start',lower(a.occupied),'busy_end',upper(a.occupied))
          FROM app.resource_allocations a WHERE (a.workspace_id,a.business_id,a.id)=(:ws,:business,:allocation)""",
        ws=A,
        business=BA,
        allocation=UUID(first.allocation_id),
    )
    assert occupied["kind"] == "APPOINTMENT" and occupied["released_at"] is None
    assert datetime.fromisoformat(occupied["busy_start"]) == issued.options[0].busy_start
    assert datetime.fromisoformat(occupied["busy_end"]) == issued.options[0].busy_end
    assert (await occupancy(h))["holds"] == (await occupancy(h))["active_allocations"] == 1
    proof(
        "S5-replay-after-hold-expiry",
        **work.proof(),
        result=first.model_dump(mode="json"),
        owner_booking=saved,
        lock_wait_verified=waited,
        expires_at=expires_at,
        after_release=late.outcome,
        resource_id=schedule["resource_id"],
        allocation=occupied,
        overlapping_choice=denied.outcome,
        **(await assert_effects(h, before, confirmed=1)),
    )


@pytest.mark.parametrize("block_first", [True, False], ids=["block-first", "appointment-first"])
async def test_s4_appointment_and_buffer_only_block(scheduling_pg, auth, block_first):
    h = scheduling_pg
    await publish(h, booking_contract("NONE"))
    token = await sign_in(auth)
    work = await accept_work(h, auth, token, "20 mm")
    day, preview = await configure(h, auth, token, work)
    issued = await offer(h, work, day, "issue")
    option = issued.options[0]
    # This block touches only the leading buffer. Its end is the visit start.
    block = CalendarBlockInput(start=option.busy_start, end=option.visit_start)
    select = selecting(work, choice(issued, 0), "choice")
    before = await client_effects(h)

    async def block_time(unit):
        return await create_block(unit, BA, block, "blocking")

    if block_first:
        winner, denied, waited = await compete(h, block_time, select)
        assert isinstance(winner, CalendarBlock) and winner.outcome == "BLOCKED"
        assert denied.outcome == "OPTION_UNAVAILABLE"
        assert await booking(auth, work) is None
        assert (await occupancy(h))["holds"] == 0
        assert (await occupancy(h))["active_allocations"] == 1
        echoed = await command_http(
            auth, token, CREATE_BLOCK, "blocking", block.model_dump(mode="json")
        )
        assert echoed.status_code == 200 and echoed.json() == winner.model_dump(mode="json")
    else:
        winner, denied, waited = await compete(h, select, block_time)
        assert isinstance(winner, AppointmentResult) and winner.outcome == "CONFIRMED"
        affected = [{"kind": "APPOINTMENT", "id": winner.appointment_id}]
        assert denied.outcome == "CALENDAR_CONFLICT"
        blocked = await command_http(
            auth, token, CREATE_BLOCK, "blocking", block.model_dump(mode="json")
        )
        assert blocked.status_code == 409 and blocked.json()["error"]["affected"] == affected
        closed = await auth.client.post(
            work.preview_url(day=day),
            headers=token,
            json={
                "action": "exception",
                "date": str(day),
                "windows": [],
                "expected_version": preview["schedule_version"],
            },
        )
        assert closed.status_code == 409 and closed.json()["error"]["affected"] == affected
        assert (await booking(auth, work))["appointment_id"] == winner.appointment_id
        assert (await occupancy(h))["active_allocations"] == 1
    proof(
        "S4-appointment-block",
        block_first=block_first,
        **work.proof(),
        winner=winner.model_dump(mode="json"),
        denied=denied.model_dump(mode="json"),
        waited=waited,
        interval=local_interval(option),
        **(await assert_effects(h, before, confirmed=int(not block_first))),
    )


async def test_s4_legacy_hold_expires_while_waiting_for_resource(scheduling_pg, auth):
    h = scheduling_pg
    token, first, other = await accept_two_clients(
        h, auth, first_mode="NONE", second_mode="FIXED_DEPOSIT"
    )
    day, preview = await configure(h, auth, token, first, policy=POLICY | {"hold_ttl_minutes": 1})
    await _migrate("downgrade", "0033")
    try:
        first_offer = await offer(h, first, day, "legacy-option")
        other_offer = await offer(h, other, day, "waiting-option")
        assert first_offer.options[0].visit_start == other_offer.options[0].visit_start
        legacy = await pick(h, first, choice(first_offer, 0), "legacy-choice")
        assert isinstance(legacy, HoldResult) and legacy.outcome == "HELD"
    finally:
        await _migrate("upgrade", "0037")
    before = await client_effects(h)
    assert (await booking(auth, first))["outcome"] == "HELD"
    expiry = legacy.expires_at
    entered = asyncio.Event()
    started = asyncio.get_running_loop().create_future()

    async def replay():
        await entered.wait()
        async with owner_unit(h) as unit:
            started.set_result(await backend_pid(unit))
            return await select_option(
                unit, first.identity, first.selection, choice(first_offer, 0), "legacy-choice"
            )

    waiter = asyncio.create_task(replay())
    try:
        async with h.migrator.begin() as lock:
            await lock.execute(
                text("SELECT pg_sleep_until(:moment)"), {"moment": expiry - timedelta(seconds=1)}
            )
            holder = (
                await lock.execute(
                    text("""
                    SELECT pg_backend_pid() FROM app.scheduling_resources
                    WHERE (workspace_id,business_id,id)=(:ws,:business,:resource) FOR UPDATE
                    """),
                    {"ws": A, "business": BA, "resource": UUID(preview["resource_id"])},
                )
            ).scalar_one()
            entered.set()
            waited = await blocked_by(h, await asyncio.wait_for(started, 3), holder)
            assert waited < expiry
            await lock.execute(
                text("SELECT pg_sleep_until(:moment)"),
                {"moment": expiry + timedelta(milliseconds=100)},
            )
        expired = await waiter
    finally:
        if not waiter.done():
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
    assert expired == legacy.model_copy(update={"outcome": "EXPIRED"})
    assert (await booking(auth, first))["outcome"] == "EXPIRED"
    winner = await pick(h, other, choice(other_offer, 0), "new-hold")
    assert isinstance(winner, HoldResult) and winner.outcome == "HELD"
    assert winner.visit_start == legacy.visit_start
    assert await pick(h, first, choice(first_offer, 0), "legacy-choice") == expired
    assert await release(h, first, legacy, "late-release") == expired
    assert (await booking(auth, other))["hold_id"] == winner.hold_id
    assert (await occupancy(h))["active_allocations"] == 1
    proof(
        "S4-expiry-before-legacy-confirmation",
        **first.proof(),
        waited=waited,
        interval=local_interval(first_offer.options[0]),
        expired=expired.model_dump(mode="json"),
        new=winner.model_dump(mode="json"),
        **(await assert_effects(h, before)),
    )


async def durable_calendar(h):
    return await scalar(
        h,
        """SELECT jsonb_build_object(
          'offers',(SELECT jsonb_agg(jsonb_strip_nulls(to_jsonb(f)) ORDER BY f.id) FROM app.availability_offers f),
          'options',(SELECT jsonb_agg(to_jsonb(o) ORDER BY o.id) FROM app.availability_options o),
          'holds',(SELECT jsonb_agg(to_jsonb(h) ORDER BY h.id) FROM app.reservation_holds h),
          'allocations',(SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM app.resource_allocations a),
          'receipts',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.subject_id,r.command_key)
            FROM platform.scheduling_command_receipts r)
        )""",
    )


async def test_s5_0033_upgrade_preserves_operational_facts(scheduling_pg, auth):
    h = scheduling_pg
    token, first, other = await accept_two_clients(h, auth, first_mode="NONE")
    day, _ = await configure(h, auth, token, first)
    await _migrate("downgrade", "0033")
    try:
        first_offer = await offer(h, first, day, "legacy-first")
        other_offer = await offer(h, other, day, "legacy-other")
        legacy = await pick(h, first, choice(first_offer, 0), "legacy-choice")
        assert isinstance(legacy, HoldResult) and legacy.outcome == "HELD"
        released = await pick(h, other, choice(other_offer, 6), "other-choice")
        assert isinstance(released, HoldResult) and released.outcome == "HELD"
        removed = await release(h, other, released, "legacy-release")
        assert removed.outcome == "RELEASED"
        start = other_offer.options[-1].busy_end
        async with owner_unit(h) as unit:
            block = await create_block(
                unit,
                BA,
                CalendarBlockInput(start=start, end=start + timedelta(minutes=15)),
                "legacy-block",
            )
        assert isinstance(block, CalendarBlock)
        original = await durable_calendar(h)
    finally:
        await _migrate("upgrade", "0037")
    assert (await scalar(h, "SELECT platform.scheduling_intent_schema_profile()"))["valid"]
    assert await durable_calendar(h) == original
    assert not await scalar(
        h,
        "SELECT EXISTS(SELECT 1 FROM app.availability_offers WHERE replacement_appointment_id IS NOT NULL)",
    )
    before = await client_effects(h)
    assert before["appointments"] == 0
    assert (await booking(auth, first))["outcome"] == "HELD"
    assert (await booking(auth, other))["outcome"] == "RELEASED"
    result = await pick(h, first, choice(first_offer, 0), "legacy-choice")
    assert isinstance(result, AppointmentResult) and result.outcome == "CONFIRMED"
    assert result.hold_id == legacy.hold_id and result.allocation_id == legacy.allocation_id
    assert result.visit_start == legacy.visit_start and result.visit_end == legacy.visit_end
    assert await pick(h, other, choice(other_offer, 6), "other-choice") == removed
    updated = await booking(auth, first)
    assert updated["appointment_id"] == result.appointment_id
    assert (await occupancy(h))["active_allocations"] == 2
    proof(
        "S5-upgrade-with-legacy-holds",
        **first.proof(),
        preserved_offers=[first_offer.offer_id, other_offer.offer_id],
        preserved_block=block.block_id,
        preserved_deadline=legacy.expires_at,
        result=result.model_dump(mode="json"),
        old_released=removed.model_dump(mode="json"),
        **(await assert_effects(h, before, confirmed=1)),
    )


async def test_s5_failed_confirmation_rolls_back_hold_and_allocation(scheduling_pg, auth):
    h = scheduling_pg
    await publish(h, booking_contract("NONE"))
    token = await sign_in(auth)
    work = await accept_work(h, auth, token, "20 mm")
    day, _ = await configure(h, auth, token, work)
    issued = await offer(h, work, day, "issue")
    original = await durable_calendar(h)
    before = await client_effects(h)
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE app.appointments ADD CONSTRAINT synthetic_insert_fault CHECK (false) NOT VALID"
            )
        )
    try:
        with pytest.raises(ServiceRequestError) as failure:
            await pick(h, work, choice(issued, 0), "choice")
        assert failure.value.code is ServiceRequestCode.UNAVAILABLE
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text("ALTER TABLE app.appointments DROP CONSTRAINT synthetic_insert_fault")
            )
    assert await durable_calendar(h) == original
    assert await booking(auth, work) is None
    assert await client_effects(h) == before
    recovered = await pick(h, work, choice(issued, 0), "choice")
    assert isinstance(recovered, AppointmentResult) and recovered.outcome == "CONFIRMED"
    proof(
        "S5-atomic-rollback",
        result=recovered.model_dump(mode="json"),
        **(await assert_effects(h, before, confirmed=1)),
    )
