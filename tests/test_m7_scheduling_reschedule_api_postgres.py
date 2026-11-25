"""Owner HTTP replay of a rejected move on the durable PostgreSQL schedule."""

from dataclasses import replace

import pytest
from m7_scheduling_fixtures import accept_two_clients
from test_auth_postgres import browser
from test_m7_scheduling_holds_postgres import (
    CREATE_BLOCK,
    client_effects,
    command_http,
    configure,
    offer,
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
    facts,
    initial_appointment,
    job_count,
    no_effects,
    owner_booking,
    proof,
    wall,
)

pytestmark = pytest.mark.integration


async def test_owner_api_replays_conflict_after_block_release(scheduling_pg, auth):
    h = scheduling_pg
    token, work, _ = await accept_two_clients(h, auth, first_mode="NONE")
    day, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    original, _ = await initial_appointment(h, work, await offer(h, work, day, "owner-original"))
    shown = await owner_booking(auth, work)
    assert_visit(shown["booking"], "10:00", "11:05")
    assert shown["history"] == []
    before, jobs = await client_effects(h), await job_count(h)
    appointment_url = work.booking_url().partition("?")[0] + f"/{original.appointment_id}"
    refs = work.selection.model_dump(include={"client_id", "quote_id", "order_id"})
    issued = await command_http(
        auth,
        token,
        appointment_url + "/reschedule-offers",
        "owner-offer",
        refs | {"date": day.isoformat()},
    )
    assert issued.status_code == 200, issued.text
    options = {
        wall(option["visit_start"]): option["option_id"] for option in issued.json()["options"]
    }
    request = refs | {"option_id": options["10:30"], "reason": RESCHEDULE_REASON}
    key = "owner-move-conflict"
    move_url = appointment_url + "/reschedule"

    block = await command_http(
        auth,
        token,
        CREATE_BLOCK,
        "owner-block",
        {"start": block_time(day, "11:10"), "end": block_time(day, "11:20")},
    )
    assert block.status_code == 200, block.text
    block_id = block.json()["block_id"]
    conflict = {
        "error": {"code": "CALENDAR_CONFLICT", "affected": [{"kind": "BLOCK", "id": block_id}]}
    }
    first = await command_http(auth, token, move_url, key, request)
    assert (first.status_code, first.json()) == (409, conflict)
    assert await owner_booking(auth, work) == shown
    different_reason = request | {"reason": "Мастер изменил причину"}
    changed = await command_http(auth, token, move_url, key, different_reason)
    released = await command_http(
        auth, token, f"{CREATE_BLOCK}/{block_id}/release", "owner-release", {}
    )
    assert released.status_code == 200 and released.json()["outcome"] == "RELEASED", released.text

    # A separate application instance opens a fresh PostgreSQL pool. Replay the
    # same authenticated request, including the session cookie and CSRF token.
    async with browser(auth.settings) as (fresh_app, fresh_client):
        fresh_client.cookies.update(auth.client.cookies)
        fresh = replace(auth, app=fresh_app, client=fresh_client)
        replay = await command_http(fresh, token, move_url, key, request)
        after_replay = await owner_booking(fresh, work)
        active = [
            row["id"] for row in (await facts(h, work))["allocations"] if not row["released_at"]
        ]
        proof(
            "R1-owner-conflict-replay",
            **work.proof(),
            block=block.json(),
            initial_booking=shown,
            first=(first.status_code, first.json()),
            changed_reason=(changed.status_code, changed.json()),
            retry=(replay.status_code, replay.json()),
            booking_after_retry=after_replay,
            active_allocations=active,
        )
        assert (replay.status_code, replay.content) == (409, first.content)
        assert after_replay == shown
        assert active == [original.allocation_id]
        mismatch = {"error": {"code": "IDEMPOTENCY_KEY_CONFLICT"}}
        assert (changed.status_code, changed.json()) == (409, mismatch)
        changed = await command_http(fresh, token, move_url, key, different_reason)
        assert (changed.status_code, changed.json()) == (409, mismatch)
        changed_option = await command_http(
            fresh, token, move_url, key, request | {"option_id": options["10:45"]}
        )
        assert (changed_option.status_code, changed_option.json()) == (409, mismatch)
        assert await owner_booking(fresh, work) == shown

        moved = await command_http(fresh, token, move_url, "owner-new-move", request)
        assert moved.status_code == 200 and moved.json()["outcome"] == "RESCHEDULED", moved.text
        after_move = await owner_booking(fresh, work)
        successor = after_move["booking"]
        assert moved.json()["session_id"] == after_move["session_id"] == shown["session_id"]
        assert moved.json()["booking"] == successor
        assert successor["outcome"] == "CONFIRMED"
        assert successor["previous_appointment_id"] == original.appointment_id
        assert_visit(successor, "10:30", "11:35")
        assert [row["appointment_id"] for row in after_move["history"]] == [original.appointment_id]
        assert after_move["history"][0]["outcome"] == "CANCELLED"
        assert_visit(after_move["history"][0], "10:00", "11:05")
        late = await command_http(fresh, token, move_url, key, request)
        assert (late.status_code, late.content) == (409, first.content)
        assert await owner_booking(fresh, work) == after_move

    active = [row["id"] for row in (await facts(h, work))["allocations"] if not row["released_at"]]
    assert active == [successor["allocation_id"]]
    proof(
        "R1-owner-explicit-move",
        **work.proof(),
        changed_reason_after_release=(changed.status_code, changed.json()),
        changed_option=(changed_option.status_code, changed_option.json()),
        move=(moved.status_code, moved.json()),
        prior_key=(late.status_code, late.json()),
        booking_after_move=after_move,
        active_allocations=active,
        **(await no_effects(h, before, jobs, confirmed=1)),
    )
