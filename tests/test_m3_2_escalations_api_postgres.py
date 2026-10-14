"""Escalation owner HTTP on the retained cookie/Origin/CSRF and actual PG boundary."""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from asm.auth.http import install_auth
from asm.billing.http import install_billing
from asm.billing.models import AuditPage
from asm.billing.validation import decode_cursor, encode_cursor, timestamp
from asm.conversations.escalation_http import install_escalations
from asm.conversations.escalation_http_models import (
    EscalationCommandResponse,
    EscalationPage,
    EscalationView,
)
from asm.conversations.http import install_control
from asm.messaging.http import install_messaging
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m2_1_models import event
from test_m2_1_postgres import ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import incoming, process_receipt
from test_m3_2_escalations_postgres import body, created, facts, serial_clock
from test_tenancy_postgres import UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def escalation_api(auth, control):
    app = FastAPI()
    install_auth(app, auth.service, auth.settings)
    install_billing(app, auth.service, auth.settings)
    install_messaging(app, auth.service, auth.settings, environment="TEST")
    install_control(app, auth.service, auth.settings)
    install_escalations(app, auth.service, auth.settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=auth.client.base_url
    ) as client:
        logged = await login(auth, client=client)
        assert logged.status_code == 200
        yield SimpleNamespace(
            **vars(control), app=app, auth=auth, client=client, csrf=logged.json()["csrf_token"]
        )


def route(e=None, op=None, ws=A):
    return (
        f"/api/v1/workspaces/{ws}/escalations"
        + (f"/{e['id']}" if e else "")
        + (f"/{op}" if op else "")
    )


async def post(h, e, op="resolve", key="owner-decision", value=None, client=None):
    c = client or h.client
    value = (
        body(e, answer=" Exact e\u0301\n" if op == "resolve" else None).model_dump()
        if value is None
        else value
    )
    return await c.post(
        route(e, op), json=value, headers={**headers(c, h.csrf), "Idempotency-Key": key}
    )


async def test_live_http_two_tabs_replay_current_view_and_mixed_audit(escalation_api):
    h = escalation_api
    e, _, _ = await created(h)
    pending = await h.client.get(route(e))
    assert pending.status_code == 200
    assert EscalationView.model_validate(pending.json()).waiting == "WAITING_FOR_HUMAN"
    listed = await h.client.get(route())
    page = EscalationPage.model_validate(listed.json())
    assert len(page.items) == 1 and page.items[0].escalation_id == str(e["id"])
    assert page.items[0].can_resolve and page.items[0].can_cancel
    async with AsyncClient(transport=ASGITransport(app=h.app), base_url=h.client.base_url) as tab:
        tab.cookies.update(h.client.cookies)
        replies = await asyncio.gather(post(h, e), post(h, e, client=tab))
    assert [r.status_code for r in replies] == [200, 200]
    results = [EscalationCommandResponse.model_validate(r.json()) for r in replies]
    assert {r.outcome for r in results} == {"ACCEPTED", "REPLAY"} and results[0].result == results[
        1
    ].result
    await incoming(h, number=77)
    replay = await post(h, e)
    current = EscalationView.model_validate((await h.client.get(route(e))).json())
    assert replay.json() == {"outcome": "REPLAY", "result": results[0].result.model_dump()}
    assert int(current.current_context.context_version) > int(
        results[0].result.accepted_context_version
    )
    assert current.resolution.answer_text == " Exact e\u0301\n" and not current.can_resolve
    audit = await h.client.get(f"/api/v1/workspaces/{A}/audit-events?limit=100")
    assert audit.status_code == 200
    events = AuditPage.model_validate(audit.json()).items
    decision = [v for v in events if v.event_type == "ESCALATION_DECIDED"]
    assert len(decision) == 1 and decision[0].object_id == str(e["id"])
    assert decision[0].payload.model_dump() == {"operation": "RESOLVE", "status": "RESOLVED"}
    assert {v.event_type for v in events} >= {"ESCALATION_DECIDED", "CONVERSATION_RESUMED"}
    assert h.adapter.calls == 0


async def test_page_db_clock_empty_nonempty_keyset_and_read_only(escalation_api):
    h = escalation_api
    async with serial_clock(h) as (anchor, set_clock):
        before = await facts(h)
        empty = await h.client.get(route())
        assert empty.status_code == 200
        assert empty.json() == dict(items=[], next_cursor=None, observed_at=timestamp(anchor))
        assert await facts(h) == before

        # All three requests use normal ingress/Resume/worker, including a tied
        # created_at pair; no inserted Escalations or rescheduled timer Jobs.
        requests = []
        for i in range(3):
            if i == 2:
                await set_clock(anchor + timedelta(seconds=1))
            e, _, _ = await created(h, suffix=f"page-{i}", chat=f"page-chat-{i}")
            requests.append(e)
        ordered = sorted(requests, key=lambda e: (e["created_at"], e["id"]), reverse=True)
        moment = anchor + timedelta(seconds=30)
        await set_clock(moment)
        before = await facts(h)

        first = await h.client.get(route(), params={"limit": "2"})
        assert first.status_code == 200
        page = first.json()
        assert set(page) == {"items", "next_cursor", "observed_at"}
        assert page["observed_at"] == timestamp(moment)
        assert [item["escalation_id"] for item in page["items"]] == [
            str(e["id"]) for e in ordered[:2]
        ]
        assert all(item["observed_at"] == timestamp(moment) for item in page["items"])
        assert all(
            item["status"] == "PENDING" and item["waiting"] == "WAITING_FOR_HUMAN"
            for item in page["items"]
        )
        cursor = decode_cursor(page["next_cursor"])
        assert cursor == dict(
            v=1,
            endpoint="ESCALATIONS",
            workspace_id=str(A),
            direction="DESC",
            status="PENDING",
            created_at=timestamp(ordered[1]["created_at"]),
            id=str(ordered[1]["id"]),
        )

        moment += timedelta(seconds=1)
        await set_clock(moment)
        second = await h.client.get(route(), params={"limit": "2", "cursor": page["next_cursor"]})
        assert second.status_code == 200
        tail = second.json()
        assert set(tail) == {"items", "next_cursor", "observed_at"}
        assert tail["observed_at"] == timestamp(moment) and tail["next_cursor"] is None
        assert [item["escalation_id"] for item in tail["items"]] == [str(ordered[2]["id"])]
        assert tail["items"][0]["observed_at"] == timestamp(moment)

        moment += timedelta(seconds=1)
        await set_clock(moment)
        last_cursor = encode_cursor(
            cursor
            | {
                "created_at": timestamp(ordered[2]["created_at"]),
                "id": str(ordered[2]["id"]),
            }
        )
        last = await h.client.get(route(), params={"limit": "2", "cursor": last_cursor})
        assert last.status_code == 200
        assert last.json() == dict(items=[], next_cursor=None, observed_at=timestamp(moment))
        assert await facts(h) == before

        # An overdue read projects expiry without committing a lifecycle change.
        moment = anchor + timedelta(minutes=11)
        await set_clock(moment)
        expired = await h.client.get(route())
        assert expired.status_code == 200
        data = expired.json()
        assert set(data) == {"items", "next_cursor", "observed_at"}
        assert data["observed_at"] == timestamp(moment) and data["next_cursor"] is None
        assert [item["escalation_id"] for item in data["items"]] == [str(e["id"]) for e in ordered]
        assert all(
            item["observed_at"] == timestamp(moment)
            and item["status"] == "PENDING"
            and item["validity"] == "EXPIRED"
            and item["waiting"] is None
            and not item["can_resolve"]
            and not item["can_cancel"]
            for item in data["items"]
        )
        assert await facts(h) == before and h.adapter.calls == 0


async def test_auth_csrf_types_headers_relations_and_revoked_replay_fail_closed(escalation_api):
    h = escalation_api
    e, _, _ = await created(h)
    value = body(e, answer="answer").model_dump()
    before = await facts(h)
    async with AsyncClient(transport=ASGITransport(app=h.app), base_url=h.client.base_url) as anon:
        assert (await anon.get(route(e))).status_code == 401
    for bad in (
        {},
        {"Origin": "https://foreign.invalid", "X-CSRF-Token": h.csrf},
        {"Origin": str(h.client.base_url).rstrip("/"), "X-CSRF-Token": "wrong"},
    ):
        r = await h.client.post(
            route(e, "resolve"), json=value, headers={"Idempotency-Key": "bad", **bad}
        )
        assert r.status_code == 403
    good = {**headers(h.client, h.csrf), "Idempotency-Key": "bad"}
    for bad in (
        {**value, "answer_text": None},
        {**value, "answer_text": "\u00a0\t "},
        {**value, "answer_text": "\ud800"},
        {**value, "answer_text": "\u0000"},
        {**value, "expected_escalation_version": 1},
        {**value, "expected_context_version": "01"},
        {**value, "extra": True},
        {},
    ):
        # Escaped invalid scalars reach the strict JSON/Pydantic boundary.
        r = await h.client.post(
            route(e, "resolve"),
            content=json.dumps(bad),
            headers={**good, "Content-Type": "application/json"},
        )
        assert r.status_code == 422
    for raw in ('{"answer_text":"a","answer_text":"b"}', '{"answer_text":NaN}'):
        assert (
            await h.client.post(
                route(e, "resolve"),
                content=raw,
                headers={**good, "Content-Type": "application/json"},
            )
        ).status_code == 422
    for extra in ({"If-Match": "1"}, {"Idempotency-Key": " bad "}):
        assert (
            await h.client.post(route(e, "resolve"), json=value, headers=good | extra)
        ).status_code == 422
    assert (
        await h.client.post(
            route(e, "resolve"),
            json=value,
            headers=list(good.items()) + [("Idempotency-Key", "other")],
        )
    ).status_code == 422
    for suffix in ("?offset=0", "?limit=1&limit=1", "?status=pending", "?cursor=bad"):
        assert (await h.client.get(route() + suffix)).status_code == 422
    assert (await h.client.get(route(e) + "?limit=1")).status_code == 422
    assert (await h.client.get(route(e, ws=B))).status_code == 403
    for field in ("expected_client_id", "expected_conversation_id"):
        assert (await post(h, e, value=value | {field: str(uuid4())})).status_code == 404
    assert await facts(h) == before
    accepted = await post(h, e, value=value)
    assert accepted.status_code == 200
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='PROVIDER' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING *",
        ws=A,
        actor=UA,
    )
    assert (await post(h, e, value=value)).status_code == 403
    assert (await h.client.get(route(e))).status_code == 403


async def test_same_tenant_different_client_relation_and_cursor_filter_anchor(escalation_api):
    h = escalation_api
    e, _, _ = await created(h)
    receipt = await ingest(
        h,
        event(
            event_id="other-client",
            message_id="other-client",
            chat_id="other-chat",
            sender_id="other-user",
        ),
    )
    processed = await process_receipt(h, receipt)
    other = (
        await query(
            h,
            "SELECT c.* FROM app.conversations c JOIN app.messages m ON (m.workspace_id,m.conversation_id)=(c.workspace_id,c.id) WHERE m.id=:id",
            id=processed.message_id,
        )
    )[0]
    assert other["client_id"] != e["client_id"]
    assert (
        await post(
            h,
            e,
            value=body(e, answer="a").model_dump()
            | {
                "expected_client_id": str(other["client_id"]),
                "expected_conversation_id": str(other["id"]),
            },
        )
    ).status_code == 404
    from asm.billing.validation import encode_cursor, timestamp

    cursor = {
        "v": 1,
        "endpoint": "ESCALATIONS",
        "workspace_id": str(A),
        "direction": "DESC",
        "status": "PENDING",
        "created_at": timestamp(e["created_at"]),
        "id": str(e["id"]),
    }
    assert (await post(h, e, "cancel")).status_code == 200
    # Anchor's current status may differ from the saved filter.
    assert (await h.client.get(route() + "?cursor=" + encode_cursor(cursor))).status_code == 200
    for change in (
        {"id": str(uuid4())},
        {"created_at": "2020-01-01T00:00:00.000000Z"},
        {"status": "ALL"},
        {"workspace_id": str(B)},
        {"endpoint": "AUDIT_EVENTS"},
    ):
        assert (
            await h.client.get(route() + "?cursor=" + encode_cursor(cursor | change))
        ).status_code == 422


@pytest.mark.parametrize("target", ["terminal", "audit", "receipt", "context"])
async def test_db_fault_rolls_back_decision_audit_receipt_and_context(escalation_api, target):
    h = escalation_api
    e, _, _ = await created(h)
    before = await facts(h)
    table, check = {
        "terminal": ("app.escalations", "status='PENDING'"),
        "audit": ("app.audit_events", "event_type<>'ESCALATION_DECIDED'"),
        "receipt": ("platform.escalation_command_receipts", "false"),
        "context": (
            "app.conversations",
            f"id<>'{e['conversation_id']}'::uuid OR version<={e['waiting_context_version']}",
        ),
    }[target]
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                f"ALTER TABLE {table} ADD CONSTRAINT test_receipt_write_failure CHECK({check}) NOT VALID"
            )
        )
    try:
        response = await post(h, e)
        assert response.status_code == 503 and response.json() == {"error": {"code": "UNAVAILABLE"}}
        assert await facts(h) == before
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT test_receipt_write_failure"))
    assert (await post(h, e)).status_code == 200


async def test_inactive_billing_and_channel_do_not_block_owner_cancel_and_late_projection(
    escalation_api,
):
    h = escalation_api
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await query(
            h,
            "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws RETURNING *",
            ws=A,
        )
        await query(
            h,
            "DELETE FROM platform.workspace_subscriptions WHERE workspace_id=:ws RETURNING *",
            ws=A,
        )
        response = await h.client.get(route(e))
        assert response.status_code == 200 and response.json()["can_cancel"]
        await set_clock(anchor + timedelta(minutes=10))
        view = (await h.client.get(route(e))).json()
        assert (
            view["status"] == "PENDING"
            and view["validity"] == "EXPIRED"
            and view["waiting"] is None
        )
        assert not view["can_cancel"] and not view["can_resolve"]
        rejected = await post(h, e, "cancel")
        assert rejected.status_code == 409 and rejected.json() == {
            "error": {"code": "ESCALATION_EXPIRED"}
        }
