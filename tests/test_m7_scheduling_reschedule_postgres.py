"""M7.2B owner booking changes on PostgreSQL through the ordinary commands."""

import asyncio
import json
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from asm.scheduling.commands import (
    AppointmentResult,
    HoldResult,
    SelectionUnavailable,
    cancel_appointment,
    issue_reschedule_offer,
    reschedule_appointment,
)
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.tenancy import AuthenticatedAccount
from asm.tenancy.database import TenantDatabase
from m5_knowledge_search_fixtures import owner_unit
from m7_scheduling_fixtures import ZONE, accept_pair_with_modes, accept_two_clients
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import scalar
from test_m6_owner_decisions_postgres import owner_get
from test_m7_scheduling_appointments_postgres import assert_effects
from test_m7_scheduling_holds_postgres import (
    CREATE_BLOCK,
    POLICY,
    backend_pid,
    blocked_by,
    client_effects,
    command_http,
    configure,
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
from test_tenancy_postgres import BA, UA, A

pytestmark = pytest.mark.integration
NO_BUFFERS = POLICY | {"buffer_before_minutes": 0, "buffer_after_minutes": 0}
RESCHEDULE_REASON = "По просьбе клиента"
CANCEL_REASON = "Клиент отменил визит"


def proof(case, **details):
    print(
        "M7.2B PostgreSQL", json.dumps({"case": case, **details}, default=str, ensure_ascii=False)
    )


def wall(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(ZoneInfo(ZONE)).strftime("%H:%M")


def option_at(windows, start):
    return next(option for option in windows.options if wall(option.visit_start) == start)


def assert_visit(record, start, end, *, busy_start=None, busy_end=None):
    assert record["timezone"] == ZONE
    assert (wall(record["visit_start"]), wall(record["visit_end"])) == (start, end)
    assert (wall(record["busy_start"]), wall(record["busy_end"])) == (
        busy_start or start,
        busy_end or end,
    )


async def owner_booking(auth, work):
    result = await owner_get(auth, work.booking_url())
    assert {key: result[key] for key in ("request_id", "quote_id", "order_id", "session_id")} == (
        work.selection.model_dump(include={"request_id", "quote_id", "order_id", "session_id"})
    )
    assert (await owner_get(auth, work.url + "/quote"))["agreement"] == work.agreement
    return result


async def initial_appointment(h, work, issued, start="10:00", key="initial-choice"):
    option = option_at(issued, start)
    result = await pick(h, work, UUID(option.option_id), key)
    assert isinstance(result, AppointmentResult) and result.outcome == "CONFIRMED"
    assert result.session_id == work.selection.session_id
    return result, option


async def reschedule_offer(h, work, appointment, day, key="reschedule-offer"):
    async with owner_unit(h) as unit:
        return await issue_reschedule_offer(
            unit, work.selection, UUID(appointment.appointment_id), day, key
        )


def move(work, appointment, option, key="reschedule", reason=RESCHEDULE_REASON):
    async def execute(unit):
        return await reschedule_appointment(
            unit,
            work.selection,
            UUID(appointment.appointment_id),
            UUID(option.option_id),
            reason,
            key,
        )

    return execute


def cancel(work, appointment, key="cancel", reason=CANCEL_REASON):
    async def execute(unit):
        return await cancel_appointment(
            unit, work.selection, UUID(appointment.appointment_id), reason, key
        )

    return execute


async def submit(h, command):
    async with owner_unit(h) as unit:
        return await command(unit)


async def submit_reschedule_result(h, work, appointment, option, key):
    async with owner_unit(h) as unit:
        return await unit.scheduling_owner_appointment(
            work.selection.model_dump(mode="json"),
            "reschedule",
            UUID(appointment.appointment_id),
            {"key": key, "option_id": option.option_id, "reason": RESCHEDULE_REASON},
        )


async def facts(h, work):
    return await scalar(
        h,
        """SELECT jsonb_build_object(
          'appointments',coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id) FROM app.appointments p
            WHERE (p.workspace_id,p.session_id)=(:ws,:session)),'[]'::jsonb),
          'allocations',coalesce((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM app.resource_allocations a
            WHERE (a.workspace_id,a.session_id)=(:ws,:session)),'[]'::jsonb),
          'owner_receipts',coalesce((SELECT jsonb_agg(c.command_key ORDER BY c.command_key)
            FROM platform.scheduling_command_receipts c
            WHERE c.workspace_id=:ws AND c.subject_kind='OWNER'
              AND c.payload->>'session_id'=CAST(:session AS text)),'[]'::jsonb))""",
        ws=A,
        session=UUID(work.selection.session_id),
    )


async def job_count(h):
    return await scalar(h, "SELECT count(*) FROM platform.messaging_jobs")


async def no_effects(h, before, jobs, *, confirmed=0):
    assert await job_count(h) == jobs
    return (await assert_effects(h, before, confirmed=confirmed)) | {"reminders": 0}


async def test_s6_self_overlap_lost_response_same_time_and_explicit_cancel(scheduling_pg, auth):
    h = scheduling_pg
    token, work, other = await accept_two_clients(h, auth, first_mode="NONE")
    day, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    initial_offer = await offer(h, work, day, "initial-offer")
    original, first_option = await initial_appointment(h, work, initial_offer)
    second_tab = UUID(option_at(initial_offer, "10:45").option_id)
    already = await pick(h, work, second_tab, "saved-second-tab")
    assert already.outcome == "ALREADY_CONFIRMED"
    assert already.appointment_id == original.appointment_id
    shown = await owner_booking(auth, work)
    assert shown["history"] == [] and shown["booking"]["appointment_id"] == original.appointment_id
    assert_visit(shown["booking"], "10:00", "11:05")
    before, jobs = await client_effects(h), await job_count(h)
    original_facts = await facts(h, work)
    ordinary = await owner_get(auth, work.preview_url(day=day))
    assert "10:30" not in {wall(window["visit_start"]) for window in ordinary["windows"]}
    alternatives = await reschedule_offer(h, work, original, day)
    same = await submit(h, move(work, original, option_at(alternatives, "10:00"), key="same-time"))
    assert same.outcome == "UNCHANGED" and same.booking.appointment_id == original.appointment_id
    for relation in ("appointments", "allocations"):
        assert (await facts(h, work))[relation] == original_facts[relation]
    assert await owner_booking(auth, work) == shown

    target = option_at(alternatives, "10:30")
    command = move(work, original, target)

    class LostReply(Exception):
        pass

    async def commit_then_lose():
        result = await submit(h, command)
        assert result.outcome == "RESCHEDULED"
        raise LostReply

    with pytest.raises(LostReply):
        await commit_then_lose()
    fresh = create_async_engine(h.runtime.engine.url, hide_parameters=True)
    try:
        async with TenantDatabase(fresh).transaction(AuthenticatedAccount(UA), A, BA) as unit:
            recovered = await command(unit)
    finally:
        await fresh.dispose()
    assert recovered == await submit(h, command)
    successor = recovered.booking
    assert recovered.outcome == "RESCHEDULED" and recovered.session_id == work.selection.session_id
    assert successor.outcome == "CONFIRMED" and successor.hold_id is None
    assert successor.appointment_id != original.appointment_id
    assert successor.allocation_id != original.allocation_id
    assert successor.previous_appointment_id == original.appointment_id
    assert successor.reschedule_option_id == target.option_id
    assert await reschedule_offer(h, work, original, day) == alternatives
    with pytest.raises(ServiceRequestError) as wrong_key:
        await submit(h, move(work, original, target, reason="Другой повод"))
    assert wrong_key.value.code is ServiceRequestCode.IDEMPOTENCY_KEY_CONFLICT

    moved = await owner_booking(auth, work)
    assert moved["booking"] == successor.model_dump(mode="json")
    assert_visit(moved["booking"], "10:30", "11:35")
    assert len(moved["history"]) == 1
    previous = moved["history"][0]
    assert (
        previous["appointment_id"] == original.appointment_id and previous["outcome"] == "CANCELLED"
    )
    assert previous["cancelled_by"] == str(UA) and previous["cancel_reason"] == RESCHEDULE_REASON
    assert_visit(previous, "10:00", "11:05")
    after_move = await facts(h, work)
    assert len(after_move["appointments"]) == 2
    active = [a for a in after_move["allocations"] if a["released_at"] is None]
    assert [a["id"] for a in active] == [successor.allocation_id]
    assert not await scalar(
        h,
        """SELECT EXISTS(SELECT 1 FROM app.resource_allocations
          WHERE workspace_id=:ws AND released_at IS NULL AND occupied && tstzrange(:start,:end,'[)'))""",
        ws=A,
        start=first_option.busy_start,
        end=target.busy_start,
    )

    late_select = await pick(h, work, UUID(first_option.option_id), "initial-choice")
    late_release = await release(h, work, original, "late-original-hold-release")
    assert late_select.outcome == late_release.outcome == "CANCELLED"
    assert late_select.appointment_id == original.appointment_id
    assert await pick(h, work, second_tab, "saved-second-tab") == late_select
    assert await owner_booking(auth, work) == moved
    assert await facts(h, work) == after_move

    action_url = work.booking_url().split("?", 1)[0] + f"/{successor.appointment_id}/cancel"
    body = work.selection.model_dump(include={"client_id", "quote_id", "order_id"})
    response = await command_http(
        auth, token, action_url, "cancel", body | {"reason": CANCEL_REASON}
    )
    assert response.status_code == 200, response.text
    cancelled = response.json()
    assert (
        cancelled["outcome"] == "CANCELLED" and cancelled["session_id"] == work.selection.session_id
    )
    assert cancelled == (await submit(h, cancel(work, successor))).model_dump(mode="json")
    assert cancelled["booking"]["appointment_id"] == successor.appointment_id
    assert cancelled["booking"]["cancel_reason"] == CANCEL_REASON
    assert cancelled["booking"]["cancelled_by"] == str(UA) and cancelled["booking"]["cancelled_at"]
    assert await submit(h, command) == recovered
    after_cancel = await owner_booking(auth, work)
    assert after_cancel["booking"] == cancelled["booking"]
    assert after_cancel["history"] == [cancelled["booking"], previous]
    final = await facts(h, work)
    assert len(final["appointments"]) == 2 and all(
        a["status"] == "CANCELLED" for a in final["appointments"]
    )
    assert all(a["released_at"] is not None for a in final["allocations"])
    assert await pick(h, work, UUID(first_option.option_id), "initial-choice") == late_select
    assert await release(h, work, original, "late-original-hold-release") == late_release
    old_unselected = UUID(option_at(initial_offer, "10:15").option_id)
    stale_option = await pick(h, work, old_unselected, "unselected-old-option")
    assert stale_option.outcome == "CANCELLED"
    assert await facts(h, work) == final

    effects = await no_effects(h, before, jobs, confirmed=1)
    new_slot = option_at(await offer(h, other, day, "released-for-other"), "10:00")
    replacement = await pick(h, other, UUID(new_slot.option_id), "other-takes-released")
    assert (
        replacement.outcome == "CONFIRMED" and replacement.session_id == other.selection.session_id
    )
    assert (await owner_booking(auth, work)) == after_cancel
    proof(
        "S6-overlap-replay-cancel",
        **work.proof(),
        before=shown["booking"],
        after=moved["booking"],
        history=moved["history"],
        previous=after_cancel["history"],
        cancel_result=cancelled,
        new_active=active,
        idempotency_conflict=wrong_key.value.code.value,
        late_original_select=late_select.outcome,
        late_original_release=late_release.outcome,
        unselected_old_option=stale_option.outcome,
        other_appointment=replacement.model_dump(mode="json"),
        **effects,
    )


def block_time(day, time):
    return datetime.fromisoformat(f"{day}T{time}:00").replace(tzinfo=ZoneInfo(ZONE)).isoformat()


async def test_s6_new_block_conflict_and_successor_fault_leave_original_unchanged(
    scheduling_pg, auth
):
    h = scheduling_pg
    token, work, _ = await accept_two_clients(h, auth, first_mode="NONE")
    day, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    original, _ = await initial_appointment(h, work, await offer(h, work, day, "old"))
    candidate = option_at(await reschedule_offer(h, work, original, day), "10:30")
    shown = await owner_booking(auth, work)
    saved = await facts(h, work)
    before, jobs = await client_effects(h), await job_count(h)
    interval = {"start": block_time(day, "11:10"), "end": block_time(day, "11:20")}
    block = await command_http(auth, token, CREATE_BLOCK, "block-new-time", interval)
    assert block.status_code == 200, block.text
    block_id = block.json()["block_id"]
    conflict = await submit_reschedule_result(h, work, original, candidate, "block-conflict")
    assert conflict == {
        "outcome": "CALENDAR_CONFLICT",
        "affected": [{"kind": "BLOCK", "id": block_id}],
    }
    refused_facts = saved | {"owner_receipts": sorted([*saved["owner_receipts"], "block-conflict"])}
    assert await facts(h, work) == refused_facts
    assert await owner_booking(auth, work) == shown
    unblocked = await command_http(
        auth, token, f"{CREATE_BLOCK}/{block_id}/release", "release-block", {}
    )
    assert unblocked.status_code == 200, unblocked.text
    assert (
        await submit_reschedule_result(h, work, original, candidate, "block-conflict") == conflict
    )
    assert await facts(h, work) == refused_facts
    fault_url = work.booking_url().split("?", 1)[0] + f"/{original.appointment_id}/reschedule"
    request = work.selection.model_dump(include={"client_id", "quote_id", "order_id"}) | {
        "option_id": candidate.option_id,
        "reason": RESCHEDULE_REASON,
    }

    async with h.migrator.begin() as connection:
        await connection.execute(
            text("""CREATE FUNCTION platform.s6_fail_successor() RETURNS trigger
              LANGUAGE plpgsql AS $$ BEGIN IF NEW.previous_appointment_id IS NOT NULL
                THEN RAISE EXCEPTION 'S6_FORCED_SUCCESSOR_FAILURE' USING ERRCODE='23514'; END IF;
                RETURN NEW; END $$""")
        )
        await connection.execute(
            text("""CREATE TRIGGER s6_fail_successor BEFORE INSERT ON app.appointments
              FOR EACH ROW EXECUTE FUNCTION platform.s6_fail_successor()""")
        )
    try:
        injected = await command_http(auth, token, fault_url, "forced-fault", request)
        assert injected.status_code == 503 and injected.json() == {"error": {"code": "UNAVAILABLE"}}
        assert await owner_booking(auth, work) == shown
        assert await facts(h, work) == refused_facts
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(text("DROP TRIGGER s6_fail_successor ON app.appointments"))
            await connection.execute(text("DROP FUNCTION platform.s6_fail_successor()"))

    recovered = await command_http(auth, token, fault_url, "forced-fault", request)
    assert recovered.status_code == 200 and recovered.json()["outcome"] == "RESCHEDULED"
    assert_visit(recovered.json()["booking"], "10:30", "11:35")
    moved_facts = await facts(h, work)
    assert (
        await submit_reschedule_result(h, work, original, candidate, "block-conflict") == conflict
    )
    assert await facts(h, work) == moved_facts
    proof(
        "S6-block-and-fault-rollback",
        **work.proof(),
        before=shown["booking"],
        conflict=conflict["outcome"],
        block_interval=interval,
        affected=conflict["affected"],
        fault=injected.json()["error"]["code"],
        fault_http_status=injected.status_code,
        identical_after_block_and_fault=saved,
        recovered=recovered.json(),
        recovered_http_status=recovered.status_code,
        **(await no_effects(h, before, jobs, confirmed=1)),
    )


@pytest.mark.parametrize("mode", ["NONE", "FIXED_DEPOSIT"], ids=["appointment", "hold"])
async def test_s6_same_client_second_work_is_protected_by_buffers(scheduling_pg, auth, mode):
    h = scheduling_pg
    token, work, other = await accept_pair_with_modes(h, auth, "NONE", mode)
    assert work.selection.client_id == other.selection.client_id
    assert work.selection.conversation_id == other.selection.conversation_id
    assert work.selection.session_id != other.selection.session_id
    day, _ = await configure(h, auth, token, work, policy=POLICY)
    regular_offer = await offer(h, work, day, "regular")
    original, regular = await initial_appointment(h, work, regular_offer, "10:15")
    option = option_at(await reschedule_offer(h, work, original, day), "10:45")
    before, jobs = await client_effects(h), await job_count(h)
    competing_option = option_at(await offer(h, other, day, "neighbor"), "12:00")
    assert option.visit_end <= competing_option.visit_start
    assert competing_option.busy_start < option.busy_end
    competitor = await pick(h, other, UUID(competing_option.option_id), "neighbor")
    shown, other_before = await owner_booking(auth, work), await owner_booking(auth, other)
    assert_visit(shown["booking"], "10:15", "11:20", busy_start="10:00", busy_end="11:30")
    assert_visit(other_before["booking"], "12:00", "13:05", busy_start="11:45", busy_end="13:15")
    saved, other_facts = await facts(h, work), await facts(h, other)
    for invalid in (regular, competing_option):
        with pytest.raises(ServiceRequestError) as foreign:
            await submit(h, move(work, original, invalid, key="wrong-option"))
        assert foreign.value.code is ServiceRequestCode.NOT_FOUND
    with pytest.raises(ServiceRequestError) as wrong_client_option:
        await pick(h, work, UUID(option.option_id), "owner-only-option")
    assert wrong_client_option.value.code is ServiceRequestCode.NOT_FOUND
    with pytest.raises(ServiceRequestError) as wrong_work:
        await submit(h, cancel(other, original, key="wrong-work"))
    assert wrong_work.value.code is ServiceRequestCode.NOT_FOUND
    conflict = await submit_reschedule_result(h, work, original, option, "same-client-conflict")
    if mode == "NONE":
        assert isinstance(competitor, AppointmentResult)
        affected = {"kind": "APPOINTMENT", "id": competitor.appointment_id}
    else:
        assert isinstance(competitor, HoldResult) and competitor.outcome == "HELD"
        affected = {"kind": "HOLD", "id": competitor.hold_id}
    assert conflict == {"outcome": "CALENDAR_CONFLICT", "affected": [affected]}
    refused = saved | {"owner_receipts": sorted([*saved["owner_receipts"], "same-client-conflict"])}
    assert await facts(h, work) == refused and await facts(h, other) == other_facts
    assert await owner_booking(auth, work) == shown
    assert await submit(h, cancel(work, original))
    assert await owner_booking(auth, other) == other_before
    assert await facts(h, other) == other_facts
    effects = await no_effects(h, before, jobs, confirmed=int(mode == "NONE"))
    if mode == "FIXED_DEPOSIT":
        released = await release(h, other, competitor, "release-ordinary-hold")
        assert released.outcome == "RELEASED"
        assert (await owner_booking(auth, other))["booking"]["outcome"] == "RELEASED"
        assert option_at(await offer(h, work, day, "ordinary-window-freed"), "12:00")
    proof(
        "S6-buffer-only-neighbor",
        **work.proof(),
        neighbor_session_id=other.selection.session_id,
        original=shown["booking"],
        conflicting_option=option.model_dump(mode="json"),
        neighbor=other_before["booking"],
        affected=affected,
        neighbor_preserved_after_cancel=True,
        cross_work_denial=wrong_work.value.code.value,
        **effects,
    )


async def race(h, work, first, second):
    saved = await facts(h, work)
    started = asyncio.get_running_loop().create_future()
    contenders_ready = asyncio.Event()

    async def contend():
        try:
            await contenders_ready.wait()
            async with owner_unit(h) as unit:
                started.set_result(await backend_pid(unit))
                return await second(unit)
        except ServiceRequestError as error:
            return error

    pending = asyncio.create_task(contend())
    try:
        async with owner_unit(h) as unit:
            winner = await first(unit)
            assert await facts(h, work) == saved
            contenders_ready.set()
            waiter = await asyncio.wait_for(started, 3)
            blocked_at = await blocked_by(h, waiter, await backend_pid(unit))
            assert await facts(h, work) == saved
        return winner, await pending, blocked_at
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("first", ["cancel", "reschedule"])
async def test_s6_cancel_move_both_orders_follow_expected_appointment(scheduling_pg, auth, first):
    h = scheduling_pg
    token, work, _ = await accept_two_clients(h, auth, first_mode="NONE")
    day, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    original, _ = await initial_appointment(h, work, await offer(h, work, day, "old"))
    option = option_at(await reschedule_offer(h, work, original, day), "10:30")
    commands = {"reschedule": move(work, original, option), "cancel": cancel(work, original)}
    other = "cancel" if first == "reschedule" else "reschedule"
    before, jobs = await client_effects(h), await job_count(h)
    winner, loser, blocked = await race(h, work, commands[first], commands[other])
    assert isinstance(loser, ServiceRequestError) and loser.code is ServiceRequestCode.STALE_STATE
    assert winner == await submit(h, commands[first])
    shown = await owner_booking(auth, work)
    assert shown["booking"] == winner.booking.model_dump(mode="json")
    history = shown["history"]
    assert len(history) == 1 and history[0]["appointment_id"] == original.appointment_id
    if first == "reschedule":
        assert_visit(shown["booking"], "10:30", "11:35")
        assert winner.outcome == "RESCHEDULED"
        assert winner.booking.appointment_id != original.appointment_id
        assert winner.booking.previous_appointment_id == original.appointment_id
    else:
        assert_visit(shown["booking"], "10:00", "11:05")
        assert winner.outcome == "CANCELLED" and shown["booking"] == history[0]
    after = await facts(h, work)
    assert [a["id"] for a in after["allocations"] if a["released_at"] is None] == (
        [winner.booking.allocation_id] if first == "reschedule" else []
    )
    assert other not in after["owner_receipts"]
    proof(
        "S6-cancel-reschedule-race",
        **work.proof(),
        winner=first,
        result=winner.model_dump(mode="json"),
        history=history,
        rejected=loser.code.value,
        resource_lock_wait=blocked,
        **(await no_effects(h, before, jobs, confirmed=int(first == "reschedule"))),
    )


@pytest.mark.parametrize("challenger_time", ["10:00", "10:45"], ids=["old-time", "new-time"])
async def test_s6_other_client_cannot_take_interval_during_replacement(
    scheduling_pg, auth, challenger_time
):
    h = scheduling_pg
    token, work, other = await accept_two_clients(h, auth, first_mode="NONE")
    day, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    pre_issued = await offer(h, other, day, "competing-before-old")
    original, _ = await initial_appointment(h, work, await offer(h, work, day, "old"))
    option = option_at(await reschedule_offer(h, work, original, day), "10:30")
    competitor = option_at(pre_issued, challenger_time)
    before, jobs = await client_effects(h), await job_count(h)
    winner, rejected, blocked = await race(
        h,
        work,
        move(work, original, option),
        selecting(other, UUID(competitor.option_id), "competing-lane"),
    )
    assert winner.outcome == "RESCHEDULED"
    assert isinstance(rejected, SelectionUnavailable) and rejected.outcome == "OPTION_UNAVAILABLE"
    assert (await owner_booking(auth, other))["booking"] is None
    assert (await owner_booking(auth, work))["booking"] == winner.booking.model_dump(mode="json")
    assert (await facts(h, other))["allocations"] == []
    proof(
        "S6-client-waits-through-replacement",
        **work.proof(),
        original_appointment_id=original.appointment_id,
        challenger_time=challenger_time,
        winner=winner.model_dump(mode="json"),
        rejected=rejected.outcome,
        resource_lock_wait=blocked,
        **(await no_effects(h, before, jobs, confirmed=1)),
    )


async def legacy_facts(h):
    return await scalar(
        h,
        """SELECT jsonb_build_object(
          'appointments',(SELECT jsonb_agg(jsonb_strip_nulls(to_jsonb(p)) ORDER BY p.id) FROM app.appointments p),
          'holds',(SELECT jsonb_agg(to_jsonb(h) ORDER BY h.id) FROM app.reservation_holds h),
          'allocations',(SELECT jsonb_agg(to_jsonb(a) ORDER BY a.id) FROM app.resource_allocations a),
          'offers',(SELECT jsonb_agg(jsonb_strip_nulls(to_jsonb(f)) ORDER BY f.id) FROM app.availability_offers f),
          'options',(SELECT jsonb_agg(to_jsonb(o) ORDER BY o.id) FROM app.availability_options o),
          'receipts',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.subject_kind,c.subject_id,c.command_key)
            FROM platform.scheduling_command_receipts c))""",
    )


async def test_s6_upgrade_0034_preserves_appointment_hold_block_and_receipts(scheduling_pg, auth):
    h = scheduling_pg
    token, work, other = await accept_two_clients(
        h, auth, first_mode="NONE", second_mode="FIXED_DEPOSIT"
    )
    day, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    await _migrate("downgrade", "0034")
    try:
        original, first_option = await initial_appointment(
            h, work, await offer(h, work, day, "legacy")
        )
        other_option = option_at(await offer(h, other, day, "legacy-hold"), "12:00")
        hold = await pick(h, other, UUID(other_option.option_id), "legacy-hold-choice")
        assert isinstance(hold, HoldResult) and hold.outcome == "HELD"
        interval = {"start": block_time(day, "14:00"), "end": block_time(day, "14:15")}
        block = await command_http(auth, token, CREATE_BLOCK, "legacy-block", interval)
        assert block.status_code == 200, block.text
        old_facts = await legacy_facts(h)
    finally:
        await _migrate("upgrade", "0036")
    assert (await scalar(h, "SELECT platform.scheduling_owner_day_schema_profile()"))["valid"]
    assert await legacy_facts(h) == old_facts
    first = await owner_booking(auth, work)
    assert first["history"] == [] and first["booking"]["appointment_id"] == original.appointment_id
    assert_visit(first["booking"], "10:00", "11:05")
    assert await pick(h, work, UUID(first_option.option_id), "initial-choice") == original
    assert await pick(h, other, UUID(other_option.option_id), "legacy-hold-choice") == hold
    before, jobs = await client_effects(h), await job_count(h)
    option = option_at(await reschedule_offer(h, work, original, day), "10:30")
    moved = await submit(h, move(work, original, option))
    assert moved.outcome == "RESCHEDULED"
    assert moved.booking.previous_appointment_id == original.appointment_id
    assert (await owner_booking(auth, work))["booking"] == moved.booking.model_dump(mode="json")
    kept_hold = (await owner_booking(auth, other))["booking"]
    assert kept_hold["hold_id"] == hold.hold_id and kept_hold["allocation_id"] == hold.allocation_id
    assert datetime.fromisoformat(kept_hold["expires_at"]) == hold.expires_at
    replayed_block = await command_http(auth, token, CREATE_BLOCK, "legacy-block", interval)
    assert replayed_block.status_code == 200 and replayed_block.json() == block.json()
    after = await legacy_facts(h)
    with pytest.raises(AssertionError, match="SCHEDULING_RESCHEDULE_DURABLE_DATA"):
        await _migrate("downgrade", "0034")
    assert await legacy_facts(h) == after
    proof(
        "S6-operational-upgrade",
        **work.proof(),
        original=first["booking"],
        kept_hold=kept_hold,
        kept_block=block.json(),
        successor=moved.model_dump(mode="json"),
        preserved_receipt_count=len(old_facts["receipts"]),
        **(await no_effects(h, before, jobs, confirmed=1)),
    )
