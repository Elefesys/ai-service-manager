"""Telegram owner HTTP admission: real auth/PG with controlled readonly observations."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from asm.auth.http import install_auth
from asm.messaging.http import install_messaging
from asm.messaging.http_service import ConnectionObservation
from asm.telegram.normalization import normalize_update
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m2_1_postgres import counts, query
from test_m2_1_postgres import messaging as messaging
from test_m2_3_transport import BOT, EXTERNAL, OWNER, business_connection
from test_m2_3_wire_postgres import inbound
from test_m2_3_wire_postgres import telegram_case as telegram_case
from test_tenancy_postgres import UA, A
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


class Refresher:
    def __init__(self, auth, kernel):
        self.auth, self.kernel = auth, kernel
        self.calls = 0
        self.during_refresh = None
        self.result = ConnectionObservation(
            bot_identity=str(BOT),
            external_connection_id=EXTERNAL,
            owner_user_id=str(OWNER),
            is_enabled=True,
            can_reply=True,
            error_code=None,
        )

    async def refresh(self, probe):
        self.calls += 1
        # Both connections used by auth.workspace have been released, including
        # the session/account admission lock, before any external observation.
        assert self.auth.service.store.engine.pool.checkedout() == 0
        assert self.auth.service.tenancy._engine.pool.checkedout() == 0
        assert self.kernel.runtime.engine.pool.checkedout() == 0
        assert probe.workspace_id == A and probe.connection_id == self.kernel.telegram_connection
        if self.during_refresh is not None:
            await self.during_refresh(self.calls)
        return self.result


@pytest_asyncio.fixture
async def telegram_api(auth, telegram_case):
    h = telegram_case
    refresher, app = Refresher(auth, h), FastAPI()
    install_auth(app, auth.service, auth.settings)
    install_messaging(app, auth.service, auth.settings, environment="TEST", telegram=refresher)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=auth.settings.auth_origins[0]
    ) as client:
        signed_in = await login(auth, client=client)
        assert signed_in.status_code == 200
        _, cid = await inbound(h)
        yield SimpleNamespace(
            **vars(h),
            client=client,
            auth=auth,
            refresher=refresher,
            csrf=signed_in.json()["csrf_token"],
            cid=cid,
        )


async def post(h, text="Telegram exact e\u0301\n", key="telegram-api"):
    return await h.client.post(
        f"/api/v1/workspaces/{A}/conversations/{h.cid}/messages",
        json={"text": text},
        headers={**headers(h.client, h.csrf), "Idempotency-Key": key},
    )


async def state(h):
    return (
        await query(
            h,
            "SELECT generation,observation_version FROM platform.telegram_connection_state WHERE connection_id=:id",
            id=h.telegram_connection,
        )
    )[0]


async def connection_state(h):
    response = await h.client.get(f"/api/v1/workspaces/{A}/channel-connections")
    assert response.status_code == 200
    return next(
        item
        for item in response.json()["items"]
        if item["connection_id"] == str(h.telegram_connection)
    )


async def test_new_telegram_http_intention_has_two_auth_units_no_network_under_admission(
    telegram_api,
):
    h = telegram_api
    original = h.auth.service.workspace
    entries = []

    @asynccontextmanager
    async def recorded(token, workspace):
        entries.append("begin")
        async with original(token, workspace) as unit:
            yield unit
        entries.append("commit")

    h.auth.service.workspace = recorded
    try:
        before = await state(h)
        response = await post(h)
        assert response.status_code == 202 and response.json()["outcome"] == "ACCEPTED"
        assert entries == ["begin", "commit", "begin", "commit"] and h.refresher.calls == 1
        after = await state(h)
        assert after["observation_version"] == before["observation_version"] + 1
        assert h.adapter.calls == 0
        replay = await post(h)
        assert replay.status_code == 202 and replay.json()["outcome"] == "REPLAY"
        assert h.refresher.calls == 1
        assert entries[-2:] == ["begin", "commit"] and len(entries) == 6
    finally:
        h.auth.service.workspace = original


async def test_concurrent_receipt_wins_before_stale_refresh_cas_and_new_restrictions(telegram_api):
    h = telegram_api
    waiting, release = asyncio.Event(), asyncio.Event()

    async def between(call):
        if call == 1:
            waiting.set()
            await asyncio.wait_for(release.wait(), 4)

    h.refresher.during_refresh = between
    first = asyncio.create_task(post(h))
    try:
        await asyncio.wait_for(waiting.wait(), 2)
        second = await post(h)
        assert second.status_code == 202 and second.json()["outcome"] == "ACCEPTED"
        observed = await state(h)
        await query(
            h,
            "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' WHERE workspace_id=:ws RETURNING workspace_id",
            ws=A,
        )
        await query(
            h,
            "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws AND id=:id RETURNING id",
            ws=A,
            id=h.telegram_connection,
        )
        release.set()
        replay = await first
        assert replay.status_code == 202 and replay.json()["outcome"] == "REPLAY"
        assert replay.json()["receipt_id"] == second.json()["receipt_id"]
        assert replay.json()["accepted_at"] == second.json()["accepted_at"]
        assert await state(h) == observed
        receipts = await query(
            h,
            "SELECT id FROM platform.messaging_command_receipts WHERE workspace_id=:ws",
            ws=A,
        )
        assert len(receipts) == 1 and h.refresher.calls == 2
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)


async def test_lifecycle_invalidation_during_refresh_causes_503_without_new_intention(telegram_api):
    h = telegram_api
    before = await counts(h)

    async def invalidate(_):
        await h.ingress.ingest(
            normalize_update(
                str(BOT), {"update_id": 900001, "business_connection": business_connection()}
            ),
            uuid4(),
        )

    h.refresher.during_refresh = invalidate
    response = await post(h)
    assert response.status_code == 503 and response.json() == {"error": {"code": "UNAVAILABLE"}}
    assert await counts(h) == before and (await connection_state(h))["state"] == "UNVERIFIED"


@pytest.mark.parametrize("case", ["disabled", "rights", "timeout"])
async def test_bounded_refresh_denials_commit_observation_and_show_honest_status(
    telegram_api, case
):
    h = telegram_api
    if case == "timeout":
        h.refresher.result = ConnectionObservation.unavailable(timeout=True)
    else:
        h.refresher.result = h.refresher.result.model_copy(
            update={
                "is_enabled": case != "disabled",
                "can_reply": case != "rights",
            }
        )
    before, old_state = await counts(h), await state(h)
    response = await post(h)
    assert response.status_code == (503 if case == "timeout" else 409)
    assert response.json() == {
        "error": {"code": "UNAVAILABLE" if case == "timeout" else "NOT_ALLOWED"}
    }
    assert await counts(h) == before
    assert (await state(h))["observation_version"] == old_state["observation_version"] + 1
    dto = await connection_state(h)
    assert (
        dto["state"]
        == {"disabled": "DISABLED", "rights": "RIGHTS_MISSING", "timeout": "UNAVAILABLE"}[case]
    )


@pytest.mark.parametrize("case", ["owner", "session", "product"])
async def test_live_authority_and_product_revocation_between_two_units(telegram_api, case):
    h = telegram_api
    before = await counts(h)

    async def revoke(_):
        # A real UPDATE would block on an accidentally retained auth admission lock.
        async with asyncio.timeout(2):
            if case == "owner":
                await query(
                    h,
                    "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
                    ws=A,
                    actor=UA,
                )
            elif case == "session":
                await query(
                    h,
                    "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:actor RETURNING user_account_id",
                    actor=UA,
                )
            else:
                await query(
                    h,
                    "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' WHERE workspace_id=:ws RETURNING workspace_id",
                    ws=A,
                )

    h.refresher.during_refresh = revoke
    response = await post(h)
    assert response.status_code == {"owner": 403, "session": 401, "product": 409}[case]
    assert await counts(h) == before and h.refresher.calls == 1
