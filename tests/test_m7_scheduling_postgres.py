"""Real PostgreSQL and Console owner API proof for the M7.1A slice."""

import asyncio
import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
from m7_scheduling_fixtures import POLICY, WEEK, ZONE, Work, accept_pair, remove_historical_duration
from m7_scheduling_fixtures import scheduling_pg as scheduling_pg
from sqlalchemy import text
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import scalar
from test_m6_owner_decisions_postgres import owner_get, owner_post
from test_m6_quote_acceptance_postgres import approval_pg as approval_pg
from test_m6_quote_acceptance_postgres import assessment_pg as assessment_pg
from test_m6_quote_acceptance_postgres import auth as auth
from test_m6_quote_acceptance_postgres import counts, read, ready_two_works
from test_m6_quote_acceptance_postgres import db as db
from test_m6_quote_acceptance_postgres import intake_pg as intake_pg
from test_m6_quote_acceptance_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_quote_acceptance_postgres import pricing_pg as pricing_pg
from test_m6_quote_acceptance_postgres import search_pg as search_pg
from test_m6_quote_acceptance_postgres import seeded as seeded
from test_m6_quote_acceptance_postgres import service_request_pg as service_request_pg
from test_tenancy_postgres import BA2, BB, UA, A, B

pytestmark = pytest.mark.integration


def proof(label, **fields):
    print("M7.1A PostgreSQL", json.dumps({"case": label, **fields}, ensure_ascii=False))


def at_version(command, snapshot):
    return command | {"expected_version": snapshot["schedule_version"]}


def assert_stale(reply):
    assert reply.status_code == 409 and reply.json() == {"error": {"code": "STALE_STATE"}}
    assert reply.headers["cache-control"] == "no-store"


async def effects(harness):
    return await scalar(
        harness,
        """SELECT jsonb_build_object(
        'outbox',(SELECT count(*) FROM app.outbox_events),
        'outbound',(SELECT count(*) FROM app.messages WHERE direction='OUTBOUND'),
        'booked_sessions',(SELECT count(*) FROM app.service_sessions WHERE scheduled_at IS NOT NULL),
        'offers',(SELECT count(*) FROM app.availability_offers),
        'appointments',(SELECT count(*) FROM app.appointments),
        'holds',(SELECT count(*) FROM app.reservation_holds),
        'allocations',(SELECT count(*) FROM app.resource_allocations)
    )""",
    )


async def test_m7_owner_scope_buffers_and_persisted_day_off(scheduling_pg, auth):
    h = scheduling_pg
    prepared = await ready_two_works(h, auth)
    _, draft_url, quote, _, _ = prepared
    pending = Work(
        draft_url, {"quote": quote, "order_id": str(uuid4()), "session_id": str(uuid4())}
    )
    refused = await auth.client.get(pending.preview_url())
    assert refused.status_code == 404 and refused.json() == {"error": {"code": "NOT_FOUND"}}
    token, left, right = await accept_pair(h, auth, prepared)
    assert left.material["client_id"] == right.material["client_id"]
    assert left.material["conversation_id"] == right.material["conversation_id"]
    assert all(left.proof()[key] != right.proof()[key] for key in left.proof())
    for work in (left, right):
        empty = await owner_get(auth, work.preview_url())
        assert empty["reason"] == "NO_WORKING_HOURS" and empty["windows"] == []
        assert empty["schedule_version"] == 0
        assert empty["occupied_minutes"] == 65 and empty["deposit"] == work.material["deposit"]
        assert {key: empty[key] for key in work.proof()} == work.proof()

    before, triples = await effects(h), await counts(h)
    body = {"action": "schedule", "timezone": ZONE, "week": WEEK, "expected_version": 0}
    missing_csrf = await auth.client.post(
        left.preview_url(), headers={"Origin": token["Origin"]}, json=body
    )
    assert missing_csrf.status_code == 403
    other_client = str(
        await scalar(h, "INSERT INTO app.clients(workspace_id) VALUES(:ws) RETURNING id", ws=A)
    )
    invalid = {
        "session": (left.preview_url(session_id=right.agreement["session_id"]), 404),
        "quote": (left.preview_url(quote_id=right.agreement["quote"]["quote_id"]), 404),
        "order": (left.preview_url(order_id=right.agreement["order_id"]), 404),
        "client": (left.preview_url(client_id=other_client), 404),
        "business": (left.preview_url(business_id=BA2), 404),
        "workspace": (left.preview_url(workspace_id=B, business_id=BB), 403),
    }
    for endpoint, status in invalid.values():
        for reply in (
            await auth.client.get(endpoint),
            await auth.client.post(endpoint, headers=token, json=body),
        ):
            assert reply.status_code == status and set(reply.json()) == {"error"}, reply.text
            assert reply.headers["cache-control"] == "no-store"
            assert all(value not in reply.text for value in left.proof().values())
    assert await scalar(h, "SELECT count(*) FROM app.scheduling_resources") == 0

    scheduled = await owner_post(auth, left.preview_url(), token, body)
    assert scheduled["reason"] == "NO_ACTIVE_POLICY"
    day = date.fromisoformat(scheduled["date"])
    endpoint = left.preview_url(day=day)
    configured = await owner_post(auth, endpoint, token, at_version(POLICY, scheduled))
    assert await owner_post(auth, endpoint, token, at_version(POLICY, configured)) == configured
    assert configured["reason"] is None and configured["timezone"] == ZONE
    windows = configured["windows"]
    assert [value["visit_start"] for value in windows] == [
        f"{day}T10:{minutes}:00+07:00" for minutes in ("15", "30", "45")
    ]
    assert windows[0] == {
        "visit_start": f"{day}T10:15:00+07:00",
        "visit_end": f"{day}T11:20:00+07:00",
        "busy_start": f"{day}T10:05:00+07:00",
        "busy_end": f"{day}T11:25:00+07:00",
    }
    second = await owner_get(auth, right.preview_url(day=day))
    assert second["windows"] == windows
    assert {key: second[key] for key in right.proof()} == right.proof()
    closed = await owner_post(
        auth,
        left.preview_url(),
        token,
        at_version({"action": "exception", "date": str(day), "windows": []}, configured),
    )
    assert closed == (await owner_get(auth, endpoint))
    assert closed["reason"] == "DATE_CLOSED" and closed["windows"] == []
    assert (await owner_get(auth, right.preview_url(day=day)))["windows"] == []
    other = await owner_get(auth, left.preview_url(day=day + timedelta(days=1)))
    assert [value["visit_start"][11:16] for value in other["windows"]] == [
        "10:15",
        "10:30",
        "10:45",
    ]

    # The previous signed-in owner loses both read and write access after demotion.
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": A, "actor": UA},
        )
    try:
        assert (await auth.client.get(endpoint)).status_code == 403
        denied = await auth.client.post(endpoint, headers=token, json=at_version(POLICY, closed))
        assert denied.status_code == 403
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor"
                ),
                {"ws": A, "actor": UA},
            )
    for work in (left, right):
        assert (await read(h, auth, work.url))["agreement"] == work.agreement
    assert await effects(h) == before and await counts(h) == triples == (2, 2, 2)
    assert all(
        before[k] == 0
        for k in ("booked_sessions", "offers", "appointments", "holds", "allocations")
    )
    proof(
        "S1-S2",
        A=left.proof(),
        B=right.proof(),
        client=left.material["client_id"],
        conversation=left.material["conversation_id"],
        date=str(day),
        windows=windows,
        after=closed["windows"],
        other_date=other["date"],
        other_windows=len(other["windows"]),
        denied={key: status for key, (_, status) in invalid.items()},
        sends=0,
        holds=0,
        bookings=0,
    )


async def test_m7_stale_date_week_and_policy_preserve_first_save(scheduling_pg, auth):
    h = scheduling_pg
    token, left, right = await accept_pair(h, auth)
    initial = await owner_get(auth, left.preview_url())
    assert initial["schedule_version"] == 0
    assert (await owner_get(auth, right.preview_url()))["schedule_version"] == 0
    schedule = {"action": "schedule", "timezone": ZONE, "week": WEEK}
    first_saves = await asyncio.gather(
        auth.client.post(left.preview_url(), headers=token, json=at_version(schedule, initial)),
        auth.client.post(right.preview_url(), headers=token, json=at_version(schedule, initial)),
    )
    created, rejected = sorted(first_saves, key=lambda reply: reply.status_code)
    assert created.status_code == 200 and created.json()["schedule_version"] == 1
    assert_stale(rejected)
    assert await scalar(h, "SELECT count(*) FROM app.scheduling_resources") == 1

    day = date.fromisoformat(created.json()["date"])
    left_url, right_url = left.preview_url(day=day), right.preview_url(day=day)
    configured = await owner_post(auth, left_url, token, at_version(POLICY, created.json()))
    stale_date = await owner_get(auth, right_url)
    assert stale_date["schedule_version"] == configured["schedule_version"] == 2
    assert [row["visit_start"][11:16] for row in stale_date["windows"]] == [
        "10:15",
        "10:30",
        "10:45",
    ]
    first_date = {"action": "exception", "date": str(day), "windows": []}
    closed = await owner_post(auth, left_url, token, at_version(first_date, configured))
    replacement = first_date | {"windows": [{"start_minute": 600, "end_minute": 750}]}
    date_reply = await auth.client.post(
        right_url, headers=token, json=at_version(replacement, stale_date)
    )
    assert_stale(date_reply)
    reloaded_date = await owner_get(auth, right_url)
    assert reloaded_date["schedule_version"] == closed["schedule_version"] == 3
    assert reloaded_date["reason"] == "DATE_CLOSED" and not reloaded_date["windows"]
    assert reloaded_date["exception"] == closed["exception"] == {"date": str(day), "windows": []}

    first_week = [
        row | {"end_minute": 660} if row["weekday"] == day.weekday() else row for row in WEEK
    ]
    next_weekday = (day + timedelta(days=1)).weekday()
    second_week = [
        row | {"end_minute": 750} if row["weekday"] == next_weekday else row for row in WEEK
    ]
    changed_week = await owner_post(
        auth,
        left_url,
        token,
        at_version(schedule | {"timezone": "UTC", "week": first_week}, closed),
    )
    week_reply = await auth.client.post(
        right_url,
        headers=token,
        json=at_version(schedule | {"week": second_week}, reloaded_date),
    )
    assert_stale(week_reply)
    reloaded_week = await owner_get(auth, right_url)
    assert reloaded_week["week"] == first_week and reloaded_week["timezone"] == "UTC"
    assert reloaded_week["schedule_version"] == changed_week["schedule_version"] == 4
    assert reloaded_week["exception"] == closed["exception"]

    first_policy = POLICY | {"buffer_before_minutes": 25}
    changed_policy = await owner_post(auth, left_url, token, at_version(first_policy, changed_week))
    policy_reply = await auth.client.post(
        right_url,
        headers=token,
        json=at_version(POLICY | {"buffer_after_minutes": 20}, reloaded_week),
    )
    assert_stale(policy_reply)
    reloaded_policy = await owner_get(auth, right_url)
    assert reloaded_policy["policy"] == changed_policy["policy"]
    assert reloaded_policy["policy"]["buffer_before_minutes"] == 25
    assert reloaded_policy["policy"]["buffer_after_minutes"] == 5
    assert reloaded_policy["schedule_version"] == changed_policy["schedule_version"] == 5
    assert (
        await owner_post(auth, right_url, token, at_version(first_policy, reloaded_policy))
        == reloaded_policy
    )
    assert await scalar(h, "SELECT count(*) FROM app.scheduling_policy_revisions") == 2
    proof(
        "C0-M7.1A-01",
        A=left.proof(),
        B=right.proof(),
        first_saves=[created.status_code, rejected.status_code],
        stale_codes={
            "exception": date_reply.status_code,
            "schedule": week_reply.status_code,
            "policy": policy_reply.status_code,
        },
        date={
            "local_date": str(day),
            "version": reloaded_date["schedule_version"],
            "reason": reloaded_date["reason"],
            "windows": len(reloaded_date["windows"]),
        },
        week={
            "version": reloaded_week["schedule_version"],
            "timezone": reloaded_week["timezone"],
            "week": reloaded_week["week"],
        },
        policy={"version": reloaded_policy["schedule_version"], **reloaded_policy["policy"]},
    )


async def test_m7_preview_replacement_break_notice_horizon_and_missing_duration(
    scheduling_pg, auth
):
    h = scheduling_pg
    token, work, _ = await accept_pair(h, auth)
    empty = await owner_get(auth, work.preview_url())
    opened = await owner_post(
        auth,
        work.preview_url(),
        token,
        at_version({"action": "schedule", "timezone": ZONE, "week": WEEK}, empty),
    )
    day = date.fromisoformat(opened["date"])
    endpoint = work.preview_url(day=day)
    configured = await owner_post(auth, endpoint, token, at_version(POLICY, opened))
    replace = {
        "action": "exception",
        "date": str(day),
        "windows": [
            {"start_minute": 600, "end_minute": 660},
            {"start_minute": 675, "end_minute": 780},
        ],
    }
    changed = await owner_post(auth, work.preview_url(), token, at_version(replace, configured))
    assert [row["visit_start"][11:16] for row in changed["windows"]] == ["11:30", "11:45"]
    horizon = await owner_get(auth, work.preview_url(day=day + timedelta(days=15)))
    assert horizon["reason"] == "NO_WINDOWS" and not horizon["windows"]
    late = await owner_post(
        auth, endpoint, token, at_version(POLICY | {"minimum_notice_minutes": 4320}, changed)
    )
    assert late["reason"] == "NO_WINDOWS" and not late["windows"]

    no_buffer = await owner_post(
        auth,
        endpoint,
        token,
        at_version(
            POLICY | {"step_minutes": 5, "buffer_before_minutes": 0, "buffer_after_minutes": 0},
            late,
        ),
    )
    adjacent = await owner_post(
        auth,
        work.preview_url(),
        token,
        at_version(
            replace
            | {
                "windows": [
                    {"start_minute": 600, "end_minute": 665},
                    {"start_minute": 665, "end_minute": 730},
                ]
            },
            no_buffer,
        ),
    )
    assert len(adjacent["windows"]) == 2
    assert adjacent["windows"][0]["busy_end"] == adjacent["windows"][1]["busy_start"]
    restored = await owner_post(
        auth, work.preview_url(), token, at_version(replace | {"windows": None}, adjacent)
    )
    assert restored["exception"] is None and restored["windows"]

    single_day = {"action": "schedule", "timezone": ZONE, "week": [WEEK[day.weekday()]]}
    week = await owner_post(auth, endpoint, token, at_version(single_day, restored))
    assert week["windows"]
    next_day = day + timedelta(days=1)
    next_endpoint = work.preview_url(day=next_day)
    missing_hours = await owner_get(auth, next_endpoint)
    assert missing_hours["policy"] == week["policy"] and missing_hours["exception"] is None
    assert missing_hours["reason"] == "NO_WORKING_HOURS" and not missing_hours["windows"]
    on_next_day = replace | {"date": str(next_day)}
    next_closed = await owner_post(
        auth, next_endpoint, token, at_version(on_next_day | {"windows": []}, missing_hours)
    )
    assert next_closed["reason"] == "DATE_CLOSED" and not next_closed["windows"]
    next_short = await owner_post(
        auth,
        next_endpoint,
        token,
        at_version(
            on_next_day | {"windows": [{"start_minute": 600, "end_minute": 645}]}, next_closed
        ),
    )
    assert next_short["reason"] == "NO_WINDOWS" and not next_short["windows"]
    next_working = await owner_post(auth, next_endpoint, token, at_version(on_next_day, next_short))
    assert next_working["reason"] is None and next_working["windows"]
    assert (await owner_get(auth, endpoint))["exception"] is None
    assert (await owner_get(auth, work.preview_url(day=next_day + timedelta(days=1))))[
        "reason"
    ] == "NO_WORKING_HOURS"

    # A damaged historical terms snapshot cannot silently fall back to the
    # current service settings. Use the migrator only to emulate missing data.
    quote_id = work.agreement["quote"]["quote_id"]
    async with h.migrator.begin() as connection:
        await remove_historical_duration(connection, A, quote_id)
    unavailable = await owner_get(auth, endpoint)
    assert unavailable["reason"] == "DURATION_UNAVAILABLE"
    assert unavailable["occupied_minutes"] is unavailable["duration_reference_id"] is None
    assert not unavailable["windows"]
    quote = await auth.client.get(work.url + "/quote")
    assert quote.status_code == 409 and quote.json() == {"error": {"code": "DURATION_UNAVAILABLE"}}
    assert quote.headers["cache-control"] == "no-store"

    # An unrelated malformed field keeps the general error, even on this quote.
    async with h.migrator.begin() as connection:
        await connection.execute(text("ALTER TABLE app.quotes DISABLE TRIGGER quote_immutable"))
        result = await connection.execute(
            text("""
            UPDATE app.quotes SET material=material||'{"service_name":""}'::jsonb
            WHERE (workspace_id,id)=(:ws,CAST(:id AS uuid))
            """),
            {"ws": A, "id": quote_id},
        )
        await connection.execute(text("ALTER TABLE app.quotes ENABLE TRIGGER quote_immutable"))
        assert result.rowcount == 1
    broken = await auth.client.get(work.url + "/quote")
    assert broken.status_code == 503 and broken.json() == {"error": {"code": "UNAVAILABLE"}}
    assert broken.headers["cache-control"] == "no-store"
    assert await counts(h) == (2, 2, 2)
    proof(
        "boundaries",
        replacement=changed["windows"],
        adjacent=adjacent["windows"],
        horizon=horizon["reason"],
        notice=late["reason"],
        unconfigured=missing_hours["reason"],
        explicit_day_off=next_closed["reason"],
        short_interval=next_short["reason"],
        replacement_date=next_working["date"],
        replacement_date_windows=len(next_working["windows"]),
        unknown={"preview": unavailable["reason"], "quote_http": quote.status_code},
        unrelated_quote_error=broken.status_code,
    )


async def test_m7_upgrade_0031_preserves_accepted_work_and_session(scheduling_pg, auth):
    h = scheduling_pg
    await _migrate("downgrade", "0031")
    try:
        old = await scalar(h, "SELECT platform.service_intent_schema_profile()")
        assert old["schema_revision"] == "0031" and old["valid"] is True
        _, left, right = await accept_pair(h, auth)
        before = await counts(h)
    finally:
        await _migrate("upgrade", "0032")
    try:
        current = await scalar(h, "SELECT platform.scheduling_availability_schema_profile()")
        assert current["schema_revision"] == "0032" and current["valid"] is True
        assert await counts(h) == before == (2, 2, 2)
        for work in (left, right):
            assert (await read(h, auth, work.url))["agreement"] == work.agreement
            empty = await owner_get(auth, work.preview_url())
            assert {key: empty[key] for key in work.proof()} == work.proof()
            assert empty["reason"] == "NO_WORKING_HOURS" and not empty["windows"]
        proof("0031-to-0032", A=left.proof(), B=right.proof(), accepts=2, orders=2, sessions=2)
    finally:
        await _migrate("upgrade", "0039")
