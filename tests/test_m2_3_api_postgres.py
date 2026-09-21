"""M2-A03/A08/A12: real cookie/auth HTTP through guarded asm_runtime PostgreSQL."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
import pytest_asyncio
from asm.auth.http import install_auth
from asm.billing.http import install_billing
from asm.billing.service import KNOWN_KEYS
from asm.billing.validation import decode_cursor, encode_cursor
from asm.files.storage import ReadGrant
from asm.messaging.http import install_messaging
from asm.messaging.http_models import ConnectionsPage, ConversationsPage, MessagesPage
from asm.messaging.models import OutcomeKind
from asm.tenancy import current_workspace_context
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m2_1_models import event
from test_m2_1_postgres import CA, cleanup, conversation, counts, query, receive
from test_m2_1_postgres import messaging as messaging
from test_m2_2_db_postgres import image, ready
from test_tenancy_postgres import UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


class LocalSigner:
    """Local signing seam; real S3 HTTP evidence is in the transport integration suite."""

    def __init__(self):
        self.calls = 0

    def presign_get(self, manifest):
        assert current_workspace_context().workspace_id == manifest.workspace_id
        self.calls += 1
        return ReadGrant(
            url="https://private.invalid/test-signed-locator",
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )


@pytest_asyncio.fixture
async def api(auth, messaging):
    async with auth.migrator.begin() as connection:
        assert (
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_messaging_billing(:ws,'Synthetic API','2000-01-01T00:00:00Z','2100-01-01T00:00:00Z')"
                ),
                {"ws": A},
            )
        ).scalar_one() == "CREATED"
    app, signer = FastAPI(), LocalSigner()
    install_auth(app, auth.service, auth.settings)
    install_billing(app, auth.service, auth.settings)
    install_messaging(app, auth.service, auth.settings, environment="TEST", storage=signer)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=auth.client.base_url
        ) as client:
            response = await login(auth, client=client)
            assert response.status_code == 200
            yield SimpleNamespace(
                **vars(messaging),
                client=client,
                app=app,
                signer=signer,
                service=auth.service,
                settings=auth.settings,
                csrf=response.json()["csrf_token"],
            )
    finally:
        # Remove Message receipts before shared Audit rows, then the billing aggregate.
        await cleanup(auth.migrator)
        async with auth.migrator.begin() as connection:
            for table in (
                "platform.billing_contact_command_receipts",
                "app.audit_events",
                "platform.workspace_service_modes",
                "platform.workspace_subscriptions",
                "platform.workspace_billing_accounts",
            ):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id=:ws"), {"ws": A}
                )


def route(suffix, workspace=A):
    return f"/api/v1/workspaces/{workspace}/{suffix}"


async def send(h, cid, value=" Exact e\u0301\n", key="api-intent", **kwargs):
    return await h.client.post(
        route(f"conversations/{cid}/messages"),
        json={"text": value},
        headers={**headers(h.client, h.csrf), "Idempotency-Key": key},
        **kwargs,
    )


def grant_path(row, workspace=A, conversation_id=None, message_id=None, file_id=None):
    return route(
        f"conversations/{conversation_id or row['conversation_id']}/messages/{message_id or row['message_id']}/files/{file_id or row['id']}/read-grant",
        workspace,
    )


async def test_five_routes_return_strict_private_dtos_and_current_delivery(api):
    h = api
    cid = await conversation(h)
    connections = await h.client.get(route("channel-connections"))
    assert connections.status_code == 200
    items = ConnectionsPage.model_validate(connections.json()).items
    assert len(items) == 2 and {item.provider for item in items} == {"CONTROLLED"}
    assert all(item.observed_at is None and item.state == "AVAILABLE" for item in items)
    conversations = await h.client.get(route("conversations"))
    assert conversations.status_code == 200
    dto = ConversationsPage.model_validate(conversations.json())
    assert dto.items[0].reply_window_expires_at is None
    accepted = await send(h, cid)
    assert accepted.status_code == 202 and accepted.json()["outcome"] == "ACCEPTED"
    history = await h.client.get(route(f"conversations/{cid}/messages"))
    assert history.status_code == 200
    rows = MessagesPage.model_validate(history.json()).items
    assert rows[0].text == " Exact e\u0301\n" and rows[0].delivery.status == "PENDING"
    assert rows[0].file is None and rows[1].delivery is None
    h.adapter.outcome = OutcomeKind.UNKNOWN
    assert await h.worker.run_once()
    history = await h.client.get(route(f"conversations/{cid}/messages"))
    assert history.json()["items"][0]["delivery"]["status"] == "UNKNOWN"
    assert history.json()["items"][0]["delivery"]["error_code"] == "UNKNOWN_EXTERNAL_RESULT"
    assert not await h.worker.run_once() and h.adapter.calls == 1
    row, _, _ = await ready(
        h, event_id="image-event", message_id="image-message", chat_id="image-chat"
    )
    granted = await h.client.post(grant_path(row), json={}, headers=headers(h.client, h.csrf))
    assert granted.status_code == 200 and set(granted.json()) == {"url", "expires_at"}
    assert h.signer.calls == 1
    public = json.dumps(history.json())
    assert all(
        name not in public
        for name in (
            "provider_chat_id",
            "request_fingerprint",
            "outbox_id",
            "storage_key",
            "bot_identity",
        )
    )
    assert connections.headers["cache-control"] == "no-store"
    assert (
        h.service.store.engine.pool.checkedout() == h.service.tenancy._engine.pool.checkedout() == 0
    )


async def test_all_collection_pages_have_scoped_exact_anchors_and_creation_order(api):
    h = api
    first = await conversation(h)
    await receive(
        h,
        event(
            event_id="event-two",
            message_id="message-two",
            chat_id="other-chat",
            sender_id="other-client",
        ),
    )
    await receive(
        h,
        event(
            event_id="event-three",
            message_id="message-three",
            occurred_at=datetime(2000, 1, 1, tzinfo=UTC),
        ),
    )
    for suffix, model, identity in (
        ("channel-connections", ConnectionsPage, "connection_id"),
        ("conversations", ConversationsPage, "conversation_id"),
        (f"conversations/{first}/messages", MessagesPage, "message_id"),
    ):
        response = await h.client.get(route(suffix) + "?limit=1")
        assert response.status_code == 200
        page = model.model_validate(response.json())
        assert page.next_cursor is not None
        following = await h.client.get(
            route(suffix), params={"cursor": page.next_cursor, "limit": 1}
        )
        assert following.status_code == 200
        next_page = model.model_validate(following.json())
        assert getattr(next_page.items[0], identity) != getattr(page.items[0], identity)
        assert next_page.next_cursor is None
        cursor = decode_cursor(page.next_cursor)
        for mutation in (
            {"id": str(UUID(int=99999))},
            {"created_at": "2001-01-01T00:00:00.000000Z"},
            {"workspace_id": str(B)},
        ):
            bad = await h.client.get(
                route(suffix), params={"cursor": encode_cursor({**cursor, **mutation})}
            )
            assert bad.status_code == 422 and bad.json() == {"error": {"code": "INVALID_REQUEST"}}
    rows = (await h.client.get(route(f"conversations/{first}/messages"))).json()["items"]
    assert rows[0]["occurred_at"].startswith("2000-")
    assert rows[0]["created_at"] >= rows[1]["created_at"]
    other = next(
        row["conversation_id"]
        for row in (await h.client.get(route("conversations"))).json()["items"]
        if row["conversation_id"] != str(first)
    )
    cursor = (await h.client.get(route(f"conversations/{first}/messages") + "?limit=1")).json()[
        "next_cursor"
    ]
    wrong = await h.client.get(route(f"conversations/{other}/messages"), params={"cursor": cursor})
    assert wrong.status_code == 422


async def test_concurrent_exact_replay_one_intention_then_restriction_and_unknown(api):
    h = api
    cid = await conversation(h)
    before = await counts(h)
    responses = await asyncio.gather(*(send(h, cid) for _ in range(4)))
    assert {response.status_code for response in responses} == {202}
    assert sorted(response.json()["outcome"] for response in responses) == [
        "ACCEPTED",
        "REPLAY",
        "REPLAY",
        "REPLAY",
    ]
    assert len({response.json()["receipt_id"] for response in responses}) == 1
    after = await counts(h)
    for table in (
        "app.messages",
        "app.outbox_events",
        "app.audit_events",
        "platform.messaging_command_receipts",
        "platform.messaging_jobs",
    ):
        assert after[table] == before[table] + 1
    conflict = await send(h, cid, value="Exact é\n")
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    )
    h.adapter.outcome = OutcomeKind.UNKNOWN
    assert await h.worker.run_once()
    await query(
        h,
        "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED' WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
    )
    await query(
        h,
        "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws AND id=:id RETURNING id",
        ws=A,
        id=CA,
    )
    replay = await send(h, cid)
    assert replay.status_code == 202 and replay.json()["outcome"] == "REPLAY"
    assert replay.json()["accepted_at"] == responses[0].json()["accepted_at"]
    denied = await send(h, cid, key="new-intention")
    assert denied.status_code == 409 and denied.json() == {"error": {"code": "NOT_ALLOWED"}}
    assert h.adapter.calls == 1 and await counts(h) == after


@pytest.mark.parametrize(
    "mode,expected", [("NORMAL", 202), ("GRACE", 202), ("LIMITED", 202), ("SUSPENDED", 409)]
)
async def test_public_controlled_product_modes_use_real_service_with_frozen_billing_get(
    api, mode, expected
):
    h = api
    cid = await conversation(h)
    await query(
        h,
        "UPDATE platform.workspace_service_modes SET mode=:mode,reason_code=:reason WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
        mode=mode,
        reason="PROVISIONED_LOCAL" if mode == "NORMAL" else "TEST_" + mode,
    )
    response = await send(h, cid)
    assert response.status_code == expected
    billing = await h.client.get(route("billing"))
    assert billing.status_code == 200
    assert [item["key"] for item in billing.json()["decisions"]] == list(KNOWN_KEYS)
    assert (await h.client.get(route(f"conversations/{cid}/messages"))).status_code == 200


@pytest.mark.parametrize("case", ["missing", "expired_subscription", "future_mode"])
async def test_public_policy_structural_and_inactive_states_have_distinct_envelopes(api, case):
    h = api
    cid = await conversation(h)
    if case == "missing":
        await query(
            h,
            "DELETE FROM platform.workspace_service_modes WHERE workspace_id=:ws RETURNING workspace_id",
            ws=A,
        )
    elif case == "expired_subscription":
        await query(
            h,
            "UPDATE platform.workspace_subscriptions SET effective_from='1990-01-01',effective_until='1991-01-01' WHERE workspace_id=:ws RETURNING workspace_id",
            ws=A,
        )
    else:
        await query(
            h,
            "UPDATE platform.workspace_service_modes SET effective_from='2101-01-01',effective_until='2102-01-01' WHERE workspace_id=:ws RETURNING workspace_id",
            ws=A,
        )
    response = await send(h, cid)
    assert response.status_code == (503 if case == "missing" else 409)
    assert response.json() == (
        {"error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": "BILLING_STATE_MISSING"}}
        if case == "missing"
        else {"error": {"code": "NOT_ALLOWED"}}
    )
    assert (await h.client.get(route("channel-connections"))).status_code == 200


@pytest.mark.parametrize(
    "case", ["ADMIN", "PROVIDER", "revoked_membership", "revoked_session", "cross_workspace"]
)
async def test_all_five_routes_require_current_session_and_live_owner(api, case):
    h = api
    cid = await conversation(h)
    row, _, _ = await ready(h, event_id="private", message_id="private")
    accepted = await send(h, cid)
    assert accepted.status_code == 202
    if case in ("ADMIN", "PROVIDER"):
        await query(
            h,
            "UPDATE platform.workspace_memberships SET role=:role WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
            role=case,
            ws=A,
            actor=UA,
        )
    elif case == "revoked_membership":
        await query(
            h,
            "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
            ws=A,
            actor=UA,
        )
    elif case == "revoked_session":
        await query(
            h,
            "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:actor RETURNING user_account_id",
            actor=UA,
        )
    workspace = B if case == "cross_workspace" else A
    paths = [
        ("GET", route("channel-connections", workspace), None),
        ("GET", route("conversations", workspace), None),
        ("GET", route(f"conversations/{cid}/messages", workspace), None),
        ("POST", route(f"conversations/{cid}/messages", workspace), {"text": " Exact e\u0301\n"}),
        ("POST", grant_path(row, workspace), {}),
    ]
    for method, path, body in paths:
        response = await h.client.request(
            method,
            path,
            json=body,
            headers={**headers(h.client, h.csrf), "Idempotency-Key": "api-intent"},
        )
        assert response.status_code == (401 if case == "revoked_session" else 403)


async def test_grants_require_exact_private_relations_ready_state_and_no_billing(api):
    h = api
    pending = await image(h)
    response = await h.client.post(grant_path(pending), json={}, headers=headers(h.client, h.csrf))
    assert response.status_code == 404
    row, _, _ = await ready(
        h, event_id="ready", message_id="ready", chat_id="private-two", sender_id="client-two"
    )
    for overrides in (
        {"conversation_id": pending["conversation_id"]},
        {"message_id": pending["message_id"]},
        {"file_id": pending["id"]},
        {"file_id": UUID(int=9999)},
    ):
        response = await h.client.post(
            grant_path(row, **overrides), json={}, headers=headers(h.client, h.csrf)
        )
        assert response.status_code == 404 and response.json() == {"error": {"code": "NOT_FOUND"}}
    await query(
        h,
        "DELETE FROM platform.workspace_service_modes WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
    )
    response = await h.client.post(grant_path(row), json={}, headers=headers(h.client, h.csrf))
    assert response.status_code == 200 and h.signer.calls == 1
    history = await h.client.get(route(f"conversations/{row['conversation_id']}/messages"))
    file = MessagesPage.model_validate(history.json()).items[0].file
    assert file.status == "READY" and file.manifest.size_bytes == "67"
    assert file.manifest.width == file.manifest.height == 1


async def test_actual_http_security_and_strict_queries_body_headers(api):
    h = api
    cid = await conversation(h)
    path = route(f"conversations/{cid}/messages")
    for body in (
        b'{"text":"one","text":"two"}',
        b'{"text":"ok","extra":1}',
        b'{"text":"\\ud800"}',
        b'{"text":"  "}',
    ):
        response = await h.client.post(
            path,
            content=body,
            headers={
                **headers(h.client, h.csrf),
                "Content-Type": "application/json",
                "Idempotency-Key": "bad",
            },
        )
        assert response.status_code == 422
    valid = {
        **headers(h.client, h.csrf),
        "Content-Type": "application/json",
        "Idempotency-Key": "bad",
    }
    for changes, expected in (
        ({"Origin": "https://evil.invalid"}, 403),
        ({"X-CSRF-Token": "bad"}, 403),
        ({"If-Match": "1"}, 422),
        ({"Idempotency-Key": "bad key"}, 422),
    ):
        response = await h.client.post(path, json={"text": "ok"}, headers={**valid, **changes})
        assert response.status_code == expected
    duplicate = await h.client.post(
        path, json={"text": "ok"}, headers=[*valid.items(), ("Idempotency-Key", "other")]
    )
    assert duplicate.status_code == 422
    for suffix in ("channel-connections", "conversations", f"conversations/{cid}/messages"):
        for query_string in ("extra=1", "limit=1&limit=2", "cursor=bad=="):
            assert (await h.client.get(route(suffix) + "?" + query_string)).status_code == 422
    assert (await send(h, cid, params={"extra": "1"})).status_code == 422


async def test_response_loss_after_commit_recovers_original_intention(api):
    h = api
    cid = await conversation(h)
    original = h.service.workspace
    once = True

    @asynccontextmanager
    async def lost_response(token, workspace):
        nonlocal once
        async with original(token, workspace) as unit:
            yield unit
        if once:
            once = False
            raise RuntimeError("synthetic postcommit response loss")

    h.service.workspace = lost_response
    try:
        lost = await send(h, cid)
        assert lost.status_code == 500
        accepted_count = await counts(h)
        replay = await send(h, cid)
        assert replay.status_code == 202 and replay.json()["outcome"] == "REPLAY"
        assert await counts(h) == accepted_count
    finally:
        h.service.workspace = original


@pytest.mark.parametrize(
    "table", ["app.audit_events", "app.outbox_events", "platform.messaging_jobs"]
)
async def test_http_intention_rollback_is_atomic_at_durable_links(api, table):
    h = api
    cid = await conversation(h)
    before = await counts(h)
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "CREATE FUNCTION platform.test_m23_api_abort() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic abort'; END $$"
            )
        )
        await connection.execute(
            text(
                f"CREATE TRIGGER test_m23_api_abort BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION platform.test_m23_api_abort()"
            )
        )
    try:
        response = await send(h, cid)
        assert response.status_code == 503
        assert await counts(h) == before
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(text(f"DROP TRIGGER test_m23_api_abort ON {table}"))
            await connection.execute(text("DROP FUNCTION platform.test_m23_api_abort()"))
    assert (await send(h, cid)).status_code == 202
