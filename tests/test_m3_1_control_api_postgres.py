"""CONTROL HTTP → cookie admission → real PostgreSQL, including lock-time clocks."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from asm.auth.http import install_auth
from asm.billing.http import install_billing
from asm.billing.models import AuditPage
from asm.billing.service import KNOWN_KEYS, EntitlementService
from asm.conversations.http import install_control
from asm.conversations.http_models import ControlCommandResponse, ControlStateResponse
from asm.messaging.http import install_messaging
from asm.messaging.http_service import ConnectionObservation
from asm.tenancy import TenancyError, current_workspace_context
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import cookie, headers, login
from test_m2_1_postgres import messaging as messaging
from test_m2_1_postgres import query
from test_m2_3_db_postgres import observed
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_postgres import (
    body,
    counts_control,
    incoming,
    observe_wait,
    state,
    wait_blocked,
)
from test_m3_1_control_postgres import control as control
from test_tenancy_postgres import UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


class Refresher:
    """Observation seam only: these tests make no claim of Telegram wire evidence."""

    def __init__(self, auth):
        self.auth = auth
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.value = ConnectionObservation(**observed())

    async def refresh(self, probe):
        with pytest.raises(TenancyError):
            current_workspace_context()
        assert self.auth.service.tenancy._engine.pool.checkedout() == 0
        assert self.auth.service.store.engine.pool.checkedout() == 0
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return self.value


@pytest_asyncio.fixture
async def api(auth, control):
    app, refresher = FastAPI(), Refresher(auth)
    install_auth(app, auth.service, auth.settings)
    install_billing(app, auth.service, auth.settings)
    install_messaging(app, auth.service, auth.settings, environment="TEST", telegram=refresher)
    install_control(app, auth.service, auth.settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=auth.client.base_url) as c:
        logged = await login(auth, client=c)
        assert logged.status_code == 200
        yield SimpleNamespace(
            **vars(control),
            app=app,
            client=c,
            auth=auth,
            refresher=refresher,
            csrf=logged.json()["csrf_token"],
        )


def route(cid, operation="control", workspace=A):
    return f"/api/v1/workspaces/{workspace}/conversations/{cid}/{operation}"


async def post(h, cid, operation="takeover", key="intent", expected=None, client=None):
    c = client or h.client
    expected = expected or body(await state(h, cid)).model_dump()
    return await c.post(
        route(cid, operation), json=expected, headers={**headers(c, h.csrf), "Idempotency-Key": key}
    )


async def manual(h, cid, key="manual"):
    return await h.client.post(
        route(cid, "messages"),
        json={"text": " exact e\u0301\n"},
        headers={**headers(h.client, h.csrf), "Idempotency-Key": key},
    )


async def test_control_two_http_tabs_exact_replay_vs_current_state(api):
    h = api
    cid, _, _ = await incoming(h)
    initial = await h.client.get(route(cid))
    dto = ControlStateResponse.model_validate(initial.json())
    assert initial.status_code == 200 and dto.manual_delivery.model_dump() == {
        "has_dispatching": False,
        "has_unknown": False,
    }
    expected = body(await state(h, cid)).model_dump()
    async with AsyncClient(transport=ASGITransport(app=h.app), base_url=h.client.base_url) as tab:
        tab.cookies.update(h.client.cookies)
        outcomes = await asyncio.gather(
            post(h, cid, "resume", "same", expected),
            post(h, cid, "resume", "same", expected, client=tab),
        )
        assert [r.status_code for r in outcomes] == [200, 200]
        values = [ControlCommandResponse.model_validate(r.json()) for r in outcomes]
        assert {v.outcome for v in values} == {"ACCEPTED", "REPLAY"}
        assert values[0].result == values[1].result
        fresh = body(await state(h, cid)).model_dump()
        race = await asyncio.gather(
            post(h, cid, "takeover", "tab-a", fresh),
            post(h, cid, "resume", "tab-b", fresh, client=tab),
        )
        assert sorted(r.status_code for r in race) == [200, 409]
        assert next(r for r in race if r.status_code == 409).json() == {
            "error": {"code": "STALE_STATE"}
        }
    replay = await post(h, cid, "resume", "same", expected)
    assert replay.json() == {"outcome": "REPLAY", "result": outcomes[0].json()["result"]}
    current = (await h.client.get(route(cid))).json()
    assert int(current["control_generation"]) > int(replay.json()["result"]["accepted_generation"])
    before = await counts_control(h)
    assert (await post(h, cid, "takeover", "same", expected)).json() == {
        "error": {"code": "IDEMPOTENCY_KEY_CONFLICT"}
    }
    assert (
        await post(h, cid, "resume", "same", {**expected, "expected_context_version": "99"})
    ).status_code == 409
    assert await counts_control(h) == before and h.refresher.calls == h.adapter.calls == 0


async def test_control_auth_scope_body_and_live_owner_fail_closed(api):
    h = api
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid)).model_dump()
    before = await counts_control(h)
    async with AsyncClient(transport=ASGITransport(app=h.app), base_url=h.client.base_url) as anon:
        assert (await anon.get(route(cid))).status_code == 401
    for bad_headers in (
        {},
        {"Origin": "https://foreign.invalid", "X-CSRF-Token": h.csrf},
        {"Origin": str(h.client.base_url).rstrip("/"), "X-CSRF-Token": "wrong"},
    ):
        r = await h.client.post(
            route(cid, "takeover"),
            json=expected,
            headers={"Idempotency-Key": "security", **bad_headers},
        )
        assert r.status_code == 403
    good = {**headers(h.client, h.csrf), "Idempotency-Key": "bad-body"}
    for value in (
        {**expected, "extra": True},
        {**expected, "expected_context_version": 1},
        {**expected, "expected_control_generation": "01"},
        {},
    ):
        assert (
            await h.client.post(route(cid, "resume"), json=value, headers=good)
        ).status_code == 422
    for extra in ({"If-Match": "1"}, {"Idempotency-Key": " key "}):
        assert (
            await h.client.post(route(cid, "takeover"), json=expected, headers=good | extra)
        ).status_code == 422
    assert (await h.client.get(route(cid) + "?unknown=1")).status_code == 422
    assert (await h.client.get(route(cid, workspace=B))).status_code == 403
    assert (
        await post(h, cid, expected={**expected, "expected_client_id": str(uuid4())})
    ).status_code == 404
    assert await counts_control(h) == before
    accepted = await post(h, cid, expected=expected)
    assert accepted.status_code == 200
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        ws=A,
        actor=UA,
    )
    assert (await post(h, cid, expected=expected)).status_code == 403
    assert (await h.client.get(route(cid))).status_code == 403
    assert len(await query(h, "SELECT id FROM platform.conversation_control_receipts")) == 1


@pytest.mark.parametrize("target", ["subscription", "mode"])
@pytest.mark.parametrize("boundary", ["expiry", "activation"])
@pytest.mark.parametrize("caller", ["resume", "controlled", "telegram"])
async def test_post_lock_product_boundaries_with_actual_conversation_wait(
    api, target, boundary, caller
):
    h = api
    cid, _, _ = await incoming(h, "TELEGRAM" if caller == "telegram" else "CONTROLLED")
    expected = body(await state(h, cid)).model_dump()
    table = (
        "platform.workspace_subscriptions"
        if target == "subscription"
        else "platform.workspace_service_modes"
    )
    column = "effective_until" if boundary == "expiry" else "effective_from"
    before = await counts_control(h)
    # Login uses a separate AuthStore pool. Open the initially unused Workspace
    # pool through the real cookie/OWNER read before arming the short DB edge;
    # this case measures a product boundary crossed during a Conversation wait.
    ready = await h.client.get(route(cid))
    assert ready.status_code == 200, ready.json()
    assert await counts_control(h) == before
    assert h.auth.service.tenancy._engine.pool.checkedout() == 0
    assert h.auth.service.store.engine.pool.checkedout() == 0
    async with h.migrator.connect() as c:
        transaction = await c.begin()
        await c.execute(
            text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"), {"id": cid}
        )
        pid = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        # Finish fixture setup before starting the unchanged 1.1-second edge.
        # The product update commits on its own connection before the request;
        # only the Conversation blocker remains held while policy is evaluated.
        edge = (
            await query(
                h,
                f"UPDATE {table} SET {column}=clock_timestamp()+interval '1.1 seconds' WHERE workspace_id=:ws RETURNING {column} AS edge",
                ws=A,
            )
        )[0]["edge"]
        observe_wait("edge_committed", edge=edge, blocker_pid=pid)
        task = asyncio.create_task(
            post(h, cid, "resume", expected=expected) if caller == "resume" else manual(h, cid)
        )
        observe_wait(
            "request_scheduled", pending=task, engine=h.auth.service.tenancy._engine.sync_engine
        )
        try:
            await wait_blocked(c, pid, pending=task)
            blocked_at = (await c.execute(text("SELECT clock_timestamp()"))).scalar_one()
            observe_wait("blocked_clock", blocked_at=blocked_at)
            assert blocked_at < edge and not task.done()
            # Database wall time crosses the half-open bound. No data mutation,
            # fake clock, rescheduling or extended DB timeout releases this wait.
            await asyncio.sleep(max(0, (edge - blocked_at).total_seconds()) + 0.03)
            released_at = (await c.execute(text("SELECT clock_timestamp()"))).scalar_one()
            observe_wait("released_clock", released_at=released_at)
            assert edge <= released_at and (released_at - blocked_at).total_seconds() < 2
            await transaction.commit()
            observe_wait("blocker_commit_completed")
            response = await task
        finally:
            observe_wait("before_cleanup", pending=task)
            if transaction.is_active:
                await transaction.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            observe_wait("after_cleanup", pending=task)
    after = await state(h, cid)
    if boundary == "expiry":
        assert response.status_code == 409 and response.json() == {"error": {"code": "NOT_ALLOWED"}}
        assert await counts_control(h) == before
    else:
        assert response.status_code == (200 if caller == "resume" else 202), response.json()
        assert after["control_generation"] == int(expected["expected_control_generation"]) + 1
        assert after["version"] == int(expected["expected_context_version"]) + int(
            caller != "resume"
        )
        committed = await counts_control(h)
        await query(
            h,
            f"UPDATE {table} SET effective_until=clock_timestamp() WHERE workspace_id=:ws RETURNING workspace_id",
            ws=A,
        )
        replay = await (
            post(h, cid, "resume", expected=expected) if caller == "resume" else manual(h, cid)
        )
        assert replay.status_code == response.status_code and replay.json()["outcome"] == "REPLAY"
        assert await counts_control(h) == committed
    assert h.refresher.calls == int(caller == "telegram")


async def test_frozen_r4_clock_and_full_post_lock_snapshot_remain_distinct(api):
    h = api
    cid, _, _ = await incoming(h)
    async with h.auth.service.workspace(cookie(h.auth, h.client), A) as unit:
        old = dict(await unit.billing_snapshot())
        await asyncio.sleep(0.025)
        await unit.conversation_manual_prelock(cid, "exact", "snapshot")
        new = dict(await unit.post_lock_product_snapshot())
        retained = dict(await unit.billing_snapshot())
    assert old == retained and old["evaluated_at"] < new["evaluated_at"]
    assert new.keys() == old.keys() == {"evaluated_at", "accounts", "modes", "history"}
    for key in ("accounts", "modes", "history"):
        assert new[key] == old[key]
    assert EntitlementService().evaluate_product(A, new, "messaging.manual_send").type == "ENABLED"
    public = await h.client.get(f"/api/v1/workspaces/{A}/billing")
    assert public.status_code == 200
    assert sorted(d["key"] for d in public.json()["decisions"]) == list(KNOWN_KEYS)


@pytest.mark.parametrize(
    "change",
    [
        "suspended",
        "expired",
        "missing",
        "inactive_connection",
        "inactive_business",
        "closed_window",
    ],
)
async def test_control_product_channel_precedence_and_takeover_independence(api, change):
    h = api
    # A delayed provider event establishes its old inbound timestamp through
    # PROCESS_INBOX; never rewrite a committed Conversation clock for the case.
    at = datetime.now(UTC) - timedelta(days=2) if change == "closed_window" else None
    cid, _, _ = await incoming(h, "TELEGRAM", at=at)
    expected = body(await state(h, cid)).model_dump()
    statements = {
        "suspended": "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' WHERE workspace_id=:ws RETURNING workspace_id",
        "expired": "UPDATE platform.workspace_subscriptions SET effective_until=clock_timestamp() WHERE workspace_id=:ws RETURNING workspace_id",
        "missing": "DELETE FROM platform.workspace_service_modes WHERE workspace_id=:ws RETURNING workspace_id",
        "inactive_connection": "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:connection RETURNING id",
        "inactive_business": "UPDATE app.businesses SET status='ARCHIVED' WHERE workspace_id=:ws RETURNING id",
    }
    if change != "closed_window":
        await query(h, statements[change], ws=A, connection=h.telegram_connection)
    else:
        assert (await state(h, cid))["last_client_inbound_at"] == at
    before = await counts_control(h)
    # A stale expected generation cannot hide the structural/product verdict.
    stale = {**expected, "expected_control_generation": "99"}
    result = await post(h, cid, "resume", "policy", stale)
    code = (
        "BILLING_STATE_UNAVAILABLE"
        if change == "missing"
        else "STALE_STATE"
        if change == "closed_window"
        else "NOT_ALLOWED"
    )
    assert result.status_code == (503 if change == "missing" else 409)
    assert result.json()["error"]["code"] == code
    assert await counts_control(h) == before
    assert (await h.client.get(route(cid))).status_code == 200
    assert (await post(h, cid, "takeover", expected=expected)).status_code == 200
    if change == "closed_window":
        assert (await post(h, cid, "resume", "fresh-resume")).status_code == 200
    assert h.refresher.calls == h.adapter.calls == 0


async def wait_refresh_entered(refresher, send):
    """Require a held refresh; an early HTTP result is a failure, not the barrier."""
    entered = asyncio.create_task(refresher.entered.wait())
    try:
        await asyncio.wait((entered, send), return_when=asyncio.FIRST_COMPLETED)
        if send.done():
            response = send.result()  # Preserve an early request exception and traceback.
            try:
                payload = response.json()
            except ValueError:
                payload = None
            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            pytest.fail(
                f"manual completed before held refresh: HTTP {response.status_code}, "
                f"error={code}, entered={refresher.entered.is_set()}"
            )
        assert entered.result() is True and not refresher.release.is_set()
    finally:
        if not entered.done():
            entered.cancel()
        await asyncio.gather(entered, return_exceptions=True)


@pytest.mark.parametrize("status,code", [(202, None), (503, "UNAVAILABLE")])
async def test_refresh_entry_wait_rejects_early_http_result(status, code):
    # Orchestration only: no claim of PostgreSQL admission evidence here.
    refresher = SimpleNamespace(entered=asyncio.Event(), release=asyncio.Event())

    async def completed():
        return Response(status, json={"error": {"code": code}} if code else {"outcome": "ACCEPTED"})

    send = asyncio.create_task(completed())
    await asyncio.wait((send,))  # Completed, but its result has not been consumed.
    tasks = asyncio.all_tasks()
    try:
        async with asyncio.timeout(0.5):
            with pytest.raises(pytest.fail.Exception, match=f"HTTP {status}, error={code}"):
                await wait_refresh_entered(refresher, send)
        assert not refresher.entered.is_set()
        assert asyncio.all_tasks() == tasks
    finally:
        await asyncio.gather(send, return_exceptions=True)
    assert (await send).status_code == status


async def test_refresh_entry_wait_preserves_early_exception():
    refresher = SimpleNamespace(entered=asyncio.Event(), release=asyncio.Event())
    failure = RuntimeError("synthetic request failure before refresh")

    async def failed():
        raise failure

    send = asyncio.create_task(failed())
    await asyncio.wait((send,))
    tasks = asyncio.all_tasks()
    try:
        async with asyncio.timeout(0.5):
            with pytest.raises(RuntimeError) as caught:
                await wait_refresh_entered(refresher, send)
        assert caught.value is failure and not refresher.entered.is_set()
        assert asyncio.all_tasks() == tasks
    finally:
        await asyncio.gather(send, return_exceptions=True)
    assert send.exception() is failure


async def test_refresh_entry_wait_cancellation_reaps_event_waiter():
    refresher = SimpleNamespace(entered=asyncio.Event(), release=asyncio.Event())
    started = asyncio.Event()

    async def pending():
        started.set()
        await refresher.release.wait()

    send = asyncio.create_task(pending())
    await started.wait()
    tasks = asyncio.all_tasks()
    # A cancelled supervisor owns only its event waiter; the caller owns send.
    try:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.01):
                await wait_refresh_entered(refresher, send)
        assert not send.done() and not refresher.entered.is_set()
        assert asyncio.all_tasks() == tasks
    finally:
        send.cancel()
        await asyncio.gather(send, return_exceptions=True)
    assert send.cancelled()


@pytest.mark.parametrize("deny", [False, True])
async def test_manual_refresh_interleaving_commits_only_final_admitted_order(api, deny):
    h = api
    cid, _, _ = await incoming(h, "TELEGRAM")
    h.refresher.release.clear()
    send = asyncio.create_task(manual(h, cid))
    deadline = asyncio.timeout(3)
    phase = "refresh entry"
    try:
        async with deadline:
            await wait_refresh_entered(h.refresher, send)
            phase = "Resume commit while refresh is held"
            assert (await post(h, cid, "resume")).status_code == 200
            ai = await state(h, cid)
            assert ai["control_mode"] == "AI"
            if deny:
                phase = "SUSPENDED commit while refresh is held"
                await query(
                    h,
                    "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' WHERE workspace_id=:ws RETURNING workspace_id",
                    ws=A,
                )
            assert not send.done() and not h.refresher.release.is_set()
            h.refresher.release.set()
            phase = "final manual admission after refresh release"
            result = await send
    except TimeoutError:
        if not deadline.expired():
            raise
        pytest.fail(
            f"manual/refresh interleaving exceeded 3s during {phase}; "
            f"entered={h.refresher.entered.is_set()}, "
            f"send_done={send.done()}, send_cancelled={send.cancelled()}"
        )
    finally:
        h.refresher.release.set()
        if not send.done():
            send.cancel()
        # Always retrieve completion, including an early response/exception.
        await asyncio.gather(send, return_exceptions=True)
    final = await state(h, cid)
    if deny:
        assert result.status_code == 409 and final == ai
    else:
        assert result.status_code == 202
        assert final["control_mode"] == "HUMAN" and final["activation_fence_seq"] is None
        assert final["control_generation"] == ai["control_generation"] + 1
        assert final["version"] == ai["version"] + 1
        assert (await manual(h, cid)).json()["outcome"] == "REPLAY"
    assert h.refresher.calls == 1


async def test_mixed_audit_api_keeps_exact_large_decimal_control_versions(api):
    h = api
    cid, _, _ = await incoming(h)
    await query(
        h,
        "UPDATE app.conversations SET control_generation=9007199254740993 WHERE id=:id RETURNING id",
        id=cid,
    )
    assert (await post(h, cid, "resume", "audit-resume")).status_code == 200
    assert (await post(h, cid, "takeover", "audit-takeover")).status_code == 200
    assert (await manual(h, cid)).status_code == 202
    account = (
        await query(
            h,
            "SELECT version FROM platform.workspace_billing_accounts WHERE workspace_id=:ws",
            ws=A,
        )
    )[0]
    contact = await h.client.patch(
        f"/api/v1/workspaces/{A}/billing-account",
        json={"contact_display_name": "Changed", "expected_version": str(account["version"])},
        headers={**headers(h.client, h.csrf), "Idempotency-Key": "contact"},
    )
    assert contact.status_code == 200
    page = await h.client.get(f"/api/v1/workspaces/{A}/audit-events")
    assert page.status_code == 200
    events = AuditPage.model_validate(page.json()).items
    assert {event.event_type for event in events} == {
        "WORKSPACE_BILLING_PROVISIONED",
        "BILLING_ACCOUNT_CONTACT_UPDATED",
        "MESSAGE_SEND_REQUESTED",
        "CONVERSATION_TAKEN_OVER",
        "CONVERSATION_RESUMED",
    }
    resumed = next(event for event in events if event.event_type == "CONVERSATION_RESUMED")
    assert resumed.payload.previous_generation == "9007199254740993"
    assert resumed.payload.control_generation == "9007199254740994"


@pytest.mark.parametrize("revocation", ["membership", "session"])
async def test_control_revocation_committed_while_authority_waits(api, revocation):
    h = api
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid)).model_dump()
    before = await counts_control(h)
    async with h.migrator.connect() as c:
        tx = await c.begin()
        if revocation == "membership":
            await c.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor"
                ),
                {"ws": A, "actor": UA},
            )
        else:
            await c.execute(
                text(
                    "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:actor AND revoked_at IS NULL"
                ),
                {"actor": UA},
            )
        pid = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        task = asyncio.create_task(post(h, cid, expected=expected))
        try:
            await wait_blocked(c, pid)
            await tx.commit()
            result = await task
            assert result.status_code == (403 if revocation == "membership" else 401), result.json()
        finally:
            if tx.is_active:
                await tx.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    assert await counts_control(h) == before


async def test_control_read_reports_dispatching_and_unknown_without_recalling_intents(api):
    from asm.messaging.errors import Code
    from asm.messaging.models import OutcomeKind, SendOutcome

    h = api
    cid, _, _ = await incoming(h)
    accepted = await manual(h, cid)
    assert accepted.status_code == 202
    claim = await h.kernel.claim_job("delivery-control")
    assert claim.kind == "SEND_MANUAL_TEXT"
    permit = await h.kernel.begin_send(claim)
    assert (await h.client.get(route(cid))).json()["manual_delivery"] == {
        "has_dispatching": True,
        "has_unknown": False,
    }
    assert (await post(h, cid, "resume", "while-dispatching")).status_code == 200
    assert (await post(h, cid, "takeover", "stop")).status_code == 200
    generation = (await state(h, cid))["control_generation"]
    await h.kernel.finish_send(
        claim.job_id,
        claim.claim_token,
        permit.attempt_id,
        SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
    )
    current = (await h.client.get(route(cid))).json()
    assert current["manual_delivery"] == {"has_dispatching": False, "has_unknown": True}
    assert current["control_mode"] == "HUMAN" and int(current["control_generation"]) == generation
    assert (await manual(h, cid)).json()["outcome"] == "REPLAY"
    assert h.adapter.calls == 0


async def test_sequence_exhaustion_is_ambiguous_unavailable_and_preserves_replay(api):
    h = api
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid)).model_dump()
    accepted = await post(h, cid, "resume", "saved", expected)
    assert accepted.status_code == 200
    before = await counts_control(h)
    async with h.migrator.begin() as c:
        last = (
            await c.execute(text("SELECT last_value FROM platform.turn_ingress_seq"))
        ).scalar_one()
        await c.execute(text(f"ALTER SEQUENCE platform.turn_ingress_seq MAXVALUE {last}"))
    try:
        response = await post(h, cid, "resume", "exhausted")
        assert response.status_code == 503 and response.json() == {"error": {"code": "UNAVAILABLE"}}
        assert await counts_control(h) == before
        replay = await post(h, cid, "resume", "saved", expected)
        assert replay.json() == {**accepted.json(), "outcome": "REPLAY"}
    finally:
        async with h.migrator.begin() as c:
            await c.execute(
                text("ALTER SEQUENCE platform.turn_ingress_seq MAXVALUE 9223372036854775807")
            )


@pytest.mark.parametrize("product", ["missing", "false", "integer", "standard"])
async def test_resume_product_contract_matches_sql_and_replay_precedes_new_gates(api, product):
    from asm.billing.errors import BillingUnavailable
    from asm.conversations.control import ControlError
    from test_m3_1_control_postgres import execute

    h = api
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid)).model_dump()
    original = await post(h, cid, "resume", "valid-before-change", expected)
    assert original.status_code == 200
    async with h.migrator.begin() as c:
        plan = (
            await c.execute(
                text(
                    "INSERT INTO platform.saas_plans(code,display_name,status) VALUES(:code,'CONTROL product TEST','ACTIVE') RETURNING plan_id"
                ),
                {"code": "control_" + uuid4().hex},
            )
        ).scalar_one()
        revision = (
            await c.execute(
                text(
                    "INSERT INTO platform.saas_plan_revisions(plan_id,revision,publication_state) VALUES(:plan,1,'DRAFT') RETURNING plan_revision_id"
                ),
                {"plan": plan},
            )
        ).scalar_one()
        if product != "missing":
            await c.execute(
                text(
                    "INSERT INTO platform.plan_entitlements(plan_revision_id,capability_key,value_kind,enabled,limit_value,criticality) VALUES(:revision,'messaging.manual_send',:kind,:enabled,:limit,:criticality)"
                ),
                {
                    "revision": revision,
                    "kind": "INTEGER" if product == "integer" else "BOOLEAN",
                    "enabled": None if product == "integer" else product != "false",
                    "limit": 1 if product == "integer" else None,
                    "criticality": "STANDARD" if product == "standard" else "ESSENTIAL",
                },
            )
        await c.execute(
            text(
                "UPDATE platform.saas_plan_revisions SET publication_state='SEALED',published_at=clock_timestamp() WHERE plan_revision_id=:revision"
            ),
            {"revision": revision},
        )
        await c.execute(
            text(
                "UPDATE platform.workspace_subscriptions SET plan_revision_id=:revision WHERE workspace_id=:ws"
            ),
            {"revision": revision, "ws": A},
        )
    stale = {**expected, "expected_control_generation": "99"}
    before = await counts_control(h)
    response = await post(h, cid, "resume", "bad-product", stale)
    if product in ("integer", "standard"):
        assert response.status_code == 503 and response.json() == {
            "error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": "REVISION_INVALID"}
        }
        with pytest.raises(BillingUnavailable) as invalid:
            await execute(h, cid, "RESUME", "raw-bad-product")
        assert invalid.value.reason == "REVISION_INVALID"
    else:
        assert response.status_code == 409 and response.json() == {"error": {"code": "NOT_ALLOWED"}}
        with pytest.raises(ControlError, match="NOT_ALLOWED"):
            await execute(h, cid, "RESUME", "raw-bad-product")
    assert await counts_control(h) == before
    replay = await post(h, cid, "resume", "valid-before-change", expected)
    assert replay.json() == {**original.json(), "outcome": "REPLAY"}
    assert (await h.client.get(route(cid))).status_code == 200
    assert (await post(h, cid, "takeover", "safe-stop")).status_code == 200
    assert h.refresher.calls == 0


@pytest.mark.parametrize("mode,reason", [("GRACE", "TEST_GRACE"), ("LIMITED", "TEST_LIMITED")])
async def test_resume_accepts_valid_essential_product_in_available_modes(api, mode, reason):
    h = api
    cid, _, _ = await incoming(h)
    await query(
        h,
        "UPDATE platform.workspace_service_modes SET mode=:mode,reason_code=:reason WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
        mode=mode,
        reason=reason,
    )
    assert (await post(h, cid, "resume")).status_code == 200


async def test_automated_outbox_does_not_set_manual_delivery_flags_and_history_remains_visible(api):
    from asm.messaging.errors import Code
    from asm.messaging.models import OutcomeKind, SendOutcome
    from test_m3_1_guards_postgres import accepted, next_kind

    h = api
    cid, _, _, receipt, claim = await accepted(h)
    permit = await h.kernel.begin_guarded_send(claim)
    response = await h.client.get(route(cid))
    assert response.status_code == 200
    assert response.json()["manual_delivery"] == {"has_dispatching": False, "has_unknown": False}
    await h.kernel.finish_send(
        claim.job_id,
        claim.claim_token,
        permit.attempt_id,
        SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
    )
    response = await h.client.get(route(cid))
    assert response.json()["manual_delivery"] == {"has_dispatching": False, "has_unknown": False}
    history = await h.client.get(route(cid, "messages"))
    assert history.status_code == 200
    message = next(
        row for row in history.json()["items"] if row["message_id"] == str(receipt.message_id)
    )
    assert message["direction"] == "OUTBOUND" and message["delivery"]["status"] == "UNKNOWN"
    # Existing manual intent still takes HUMAN and sets only its own manual flag.
    assert (await manual(h, cid)).status_code == 202
    claim = await next_kind(h, "SEND_MANUAL_TEXT")
    await h.kernel.begin_send(claim)
    response = await h.client.get(route(cid))
    assert response.json()["manual_delivery"] == {"has_dispatching": True, "has_unknown": False}
