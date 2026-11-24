"""Real PostgreSQL and Console owner API proof for the M7.1A slice."""

import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
from m7_scheduling_fixtures import POLICY, WEEK, ZONE, Work, accept_pair
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


async def effects(harness):
    return await scalar(
        harness,
        """SELECT jsonb_build_object(
        'outbox',(SELECT count(*) FROM app.outbox_events),
        'outbound',(SELECT count(*) FROM app.messages WHERE direction='OUTBOUND'),
        'booked_sessions',(SELECT count(*) FROM app.service_sessions WHERE scheduled_at IS NOT NULL),
        'booking_tables',(SELECT count(*) FROM pg_tables WHERE schemaname IN ('app','platform')
            AND tablename IN ('reservation_holds','resource_allocations','appointments','availability_offers'))
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
        assert empty["occupied_minutes"] == 65 and empty["deposit"] == work.material["deposit"]
        assert {key: empty[key] for key in work.proof()} == work.proof()

    before, triples = await effects(h), await counts(h)
    body = {"action": "schedule", "timezone": ZONE, "week": WEEK}
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
    configured = await owner_post(auth, endpoint, token, POLICY)
    assert (await owner_post(auth, endpoint, token, POLICY))["policy"] == configured["policy"]
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
        auth, left.preview_url(), token, {"action": "exception", "date": str(day), "windows": []}
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
        assert (await auth.client.post(endpoint, headers=token, json=POLICY)).status_code == 403
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
    assert before["booked_sessions"] == before["booking_tables"] == 0
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


async def test_m7_preview_replacement_break_notice_horizon_and_missing_duration(
    scheduling_pg, auth
):
    h = scheduling_pg
    token, work, _ = await accept_pair(h, auth)
    opened = await owner_post(
        auth, work.preview_url(), token, {"action": "schedule", "timezone": ZONE, "week": WEEK}
    )
    day = date.fromisoformat(opened["date"])
    endpoint = work.preview_url(day=day)
    await owner_post(auth, endpoint, token, POLICY)
    replace = {
        "action": "exception",
        "date": str(day),
        "windows": [
            {"start_minute": 600, "end_minute": 660},
            {"start_minute": 675, "end_minute": 780},
        ],
    }
    changed = await owner_post(auth, work.preview_url(), token, replace)
    assert [row["visit_start"][11:16] for row in changed["windows"]] == ["11:30", "11:45"]
    assert (await owner_get(auth, work.preview_url(day=day + timedelta(days=15))))["windows"] == []
    late = await owner_post(auth, endpoint, token, POLICY | {"minimum_notice_minutes": 4320})
    assert late["reason"] == "NO_WINDOWS" and not late["windows"]

    await owner_post(
        auth,
        endpoint,
        token,
        POLICY | {"step_minutes": 5, "buffer_before_minutes": 0, "buffer_after_minutes": 0},
    )
    adjacent = await owner_post(
        auth,
        work.preview_url(),
        token,
        replace
        | {
            "windows": [
                {"start_minute": 600, "end_minute": 665},
                {"start_minute": 665, "end_minute": 730},
            ]
        },
    )
    assert len(adjacent["windows"]) == 2
    assert adjacent["windows"][0]["busy_end"] == adjacent["windows"][1]["busy_start"]
    restored = await owner_post(auth, work.preview_url(), token, replace | {"windows": None})
    assert restored["exception"] is None and restored["windows"]

    # A damaged historical terms snapshot cannot silently fall back to the
    # current service settings. Use the migrator only to emulate missing data.
    quote_id = work.agreement["quote"]["quote_id"]
    async with h.migrator.begin() as connection:
        await connection.execute(text("ALTER TABLE app.quotes DISABLE TRIGGER quote_immutable"))
        await connection.execute(
            text("""
            UPDATE app.quotes SET material=material-'occupied_minutes'-'duration_reference_id'
            WHERE (workspace_id,id)=(:ws,CAST(:id AS uuid))
        """),
            {"ws": A, "id": quote_id},
        )
        await connection.execute(text("ALTER TABLE app.quotes ENABLE TRIGGER quote_immutable"))
    unavailable = await owner_get(auth, endpoint)
    assert unavailable["reason"] == "DURATION_UNAVAILABLE"
    assert unavailable["occupied_minutes"] is unavailable["duration_reference_id"] is None
    assert not unavailable["windows"]
    proof(
        "boundaries",
        replacement=changed["windows"],
        adjacent=adjacent["windows"],
        horizon="NO_WINDOWS",
        notice=late["reason"],
        unknown=unavailable["reason"],
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
    current = await scalar(h, "SELECT platform.scheduling_availability_schema_profile()")
    assert current["schema_revision"] == "0032" and current["valid"] is True
    assert await counts(h) == before == (2, 2, 2)
    for work in (left, right):
        assert (await read(h, auth, work.url))["agreement"] == work.agreement
        empty = await owner_get(auth, work.preview_url())
        assert {key: empty[key] for key in work.proof()} == work.proof()
        assert empty["reason"] == "NO_WORKING_HOURS" and not empty["windows"]
    proof("0031-to-0032", A=left.proof(), B=right.proof(), accepts=2, orders=2, sessions=2)
