"""Strict wire/boundary and orchestration checks; real SQL evidence is separate."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from asm.auth.config import AuthSettings
from asm.auth.crypto import RateLimiter, csrf_value, new_token
from asm.auth.http import AuthBoundary, install_auth
from asm.billing.errors import BillingUnavailable
from asm.billing.validation import encode_cursor
from asm.messaging.errors import Code, MessagingError
from asm.messaging.http import collection_query, install_messaging
from asm.messaging.http_models import ManualTextRequest, MessageResponse, ReadGrantRequest
from asm.messaging.http_service import ConnectionObservation, OwnerMessagingService
from asm.messaging.models import text_fingerprint
from asm.tenancy import MembershipRole
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.requests import Request
from test_m2_3_policy import WS, messaging_snapshot

ACTOR, CONVERSATION = UUID(int=50), UUID(int=60)
ORIGIN = "http://localhost:8000"
PATH = f"/api/v1/workspaces/{WS}/conversations/{CONVERSATION}/messages"


@pytest.mark.parametrize("value", [None, True, 1, "", " \t\n", "a\0b", "\ud800", "a" * 4097])
def test_exact_text_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        ManualTextRequest.model_validate({"text": value})


def test_exact_text_and_nullable_objects_have_no_hidden_fields():
    value = " \n e\u0301 \U0001f980\t"
    assert ManualTextRequest.model_validate({"text": value}).text == value
    assert ManualTextRequest.model_validate({"text": "\U0001f980" * 4096}).text.endswith(
        "\U0001f980"
    )
    for model, payload in (
        (ManualTextRequest, {"text": "one", "provider": "TELEGRAM"}),
        (ReadGrantRequest, {"ttl": 600}),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(payload)
    schema = MessageResponse.model_json_schema()
    assert schema["additionalProperties"] is False
    assert {"file", "delivery", "text"}.issubset(schema["required"])
    assert {"bot_identity", "provider_chat_id", "storage_key", "outbox_id"}.isdisjoint(
        schema["properties"]
    )


def request_query(value):
    return Request({"type": "http", "query_string": value.encode(), "headers": []})


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "limit=true", "limit=1&limit=2", "extra=x", "cursor=", "cursor=e30="],
)
def test_strict_collection_query(query):
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        collection_query(request_query(query), "MESSAGES", str(WS), str(CONVERSATION))


@pytest.mark.parametrize(
    "change", ["bool", "workspace", "conversation", "endpoint", "extra", "timestamp"]
)
def test_cursor_canonical_scope_and_shape(change):
    payload = {
        "v": 1,
        "endpoint": "MESSAGES",
        "workspace_id": str(WS),
        "direction": "DESC",
        "created_at": "2026-09-21T00:00:00.000000Z",
        "id": str(UUID(int=70)),
        "conversation_id": str(CONVERSATION),
    }
    if change == "bool":
        payload["v"] = True
    elif change == "workspace":
        payload["workspace_id"] = str(ACTOR)
    elif change == "conversation":
        payload["conversation_id"] = str(ACTOR)
    elif change == "endpoint":
        payload["endpoint"] = "CONVERSATIONS"
    elif change == "extra":
        payload["extra"] = 1
    else:
        payload["created_at"] = "2026-09-21T00:00:00Z"
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        collection_query(
            request_query("cursor=" + encode_cursor(payload)),
            "MESSAGES",
            str(WS),
            str(CONVERSATION),
        )


async def run_boundary(path, method, size, *, streamed=False):
    async def inner(scope, receive, send):
        body = await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": str(len(body["body"])).encode()})

    settings = AuthSettings(auth_origins=(ORIGIN,))
    app = AuthBoundary(inner, settings, RateLimiter(60))
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        if streamed:

            async def chunks():
                yield b" " * 2000
                yield b" " * (size - 2000)

            body = chunks()
        else:
            body = b" " * size
        return await client.request(
            method,
            path,
            content=body,
            headers={"Origin": ORIGIN, "Content-Type": "application/json"},
        )


@pytest.mark.parametrize("streamed", [False, True])
async def test_only_exact_post_messages_gets_64k_actual_and_declared_cap(streamed):
    response = await run_boundary(PATH, "POST", 65536, streamed=streamed)
    assert response.status_code == 200 and response.text == "65536"
    assert (await run_boundary(PATH, "POST", 65537, streamed=streamed)).status_code == 413
    for path, method in (
        (PATH, "GET"),
        (PATH + "/", "POST"),
        (PATH + "/extra", "POST"),
        ("/api/v1/auth/bootstrap", "POST"),
        (f"/api/v1/workspaces/{WS}/billing-account", "PATCH"),
    ):
        assert (await run_boundary(path, method, 4097, streamed=streamed)).status_code == 413


class Unit:
    def __init__(self, auth):
        self.auth = auth
        self.context = SimpleNamespace(
            workspace_id=WS, actor=SimpleNamespace(user_account_id=ACTOR)
        )

    async def messaging_membership_role(self):
        self.auth.trace.append("owner")
        return self.auth.role

    async def messaging_prepare_text(self, conversation, value, key):
        self.auth.trace.append("prepare")
        if self.auth.receipt:
            result = dict(self.auth.receipt)
            result["code"] = "REPLAY"
            return result
        return {
            "code": "NEW",
            "provider": self.auth.provider,
            "probe": None
            if self.auth.provider == "CONTROLLED"
            else {
                "workspace_id": str(WS),
                "connection_id": str(UUID(int=80)),
                "bot_identity": "123",
                "external_connection_id": "opaque",
                "owner_user_id": "456",
                "generation": 1,
                "observation_version": 1,
            },
        }

    async def messaging_lock_billing(self):
        self.auth.trace.append("billing-lock")

    async def billing_snapshot(self):
        self.auth.trace.append("billing")
        return self.auth.billing

    async def telegram_owner_observe(self, *args):
        self.auth.trace.append("observe")
        return {"code": self.auth.observation_result, "generation": 1, "observation_version": 2}

    async def messaging_request_text(self, conversation, value, key):
        self.auth.trace.append("request")
        self.auth.receipt = receipt(value)
        return self.auth.receipt


def receipt(value="exact"):
    return {
        "code": "ACCEPTED",
        "workspace_id": str(WS),
        "receipt_id": str(UUID(int=90)),
        "message_id": str(UUID(int=91)),
        "outbox_id": str(UUID(int=92)),
        "audit_event_id": str(UUID(int=93)),
        "accepted_at": datetime(2026, 9, 21, tzinfo=UTC),
        "request_fingerprint": text_fingerprint(WS, ACTOR, CONVERSATION, value),
    }


class Auth:
    def __init__(self, provider="TELEGRAM"):
        self.provider, self.trace, self.active = provider, [], False
        self.billing, self.receipt, self.role = messaging_snapshot(), None, MembershipRole.OWNER
        self.observation_result = "OBSERVED"

    @asynccontextmanager
    async def workspace(self, token, workspace):
        assert not self.active
        self.active = True
        self.trace.append("begin")
        try:
            yield Unit(self)
        except BaseException:
            self.trace.append("rollback")
            raise
        else:
            self.trace.append("commit")
        finally:
            self.active = False


class Refresher:
    def __init__(self, auth, callback=None):
        self.auth, self.callback = auth, callback

    async def refresh(self, probe):
        assert not self.auth.active
        self.auth.trace.append("network")
        if self.callback:
            self.callback(self.auth)
        return ConnectionObservation(
            bot_identity="123",
            external_connection_id="opaque",
            owner_user_id="456",
            is_enabled=True,
            can_reply=True,
            error_code=None,
        )


async def test_telegram_uses_two_auth_units_with_network_outside_and_replay_before_cas():
    auth = Auth()
    service = OwnerMessagingService(auth, "TEST", Refresher(auth))
    result = await service.send("cookie", WS, CONVERSATION, "exact", "key")
    assert result.code == "ACCEPTED" and auth.trace.count("begin") == 2
    assert auth.trace.index("commit") < auth.trace.index("network") < auth.trace.index("observe")
    auth.billing = {"accounts": [], "modes": [], "history": []}
    auth.trace.clear()
    replay = await service.send("cookie", WS, CONVERSATION, "exact", "key")
    assert replay.code == "REPLAY"
    assert auth.trace == ["begin", "owner", "prepare", "commit"]


async def test_concurrent_replay_wins_before_stale_observation_or_restricted_plan():
    auth = Auth()

    def during_refresh(state):
        state.receipt = receipt()
        state.billing = {}
        state.observation_result = "UNAVAILABLE"

    result = await OwnerMessagingService(auth, "TEST", Refresher(auth, during_refresh)).send(
        "cookie", WS, CONVERSATION, "exact", "key"
    )
    assert result.code == "REPLAY" and "observe" not in auth.trace and "billing" not in auth.trace


@pytest.mark.parametrize("code", ["UNAVAILABLE", "NOT_ALLOWED"])
async def test_observation_denial_commits_then_returns_bounded_failure(code):
    auth = Auth()
    auth.observation_result = code
    with pytest.raises(MessagingError) as failure:
        await OwnerMessagingService(auth, "TEST", Refresher(auth)).send(
            "cookie", WS, CONVERSATION, "exact", "key"
        )
    assert failure.value.code == (
        Code.NOT_ALLOWED if code == "NOT_ALLOWED" else Code.DEPENDENCY_UNAVAILABLE
    )
    assert auth.trace[-1] == "commit" and "request" not in auth.trace and auth.receipt is None


async def test_structural_billing_is_503_and_commits_observation_without_intention():
    auth = Auth()
    auth.billing["accounts"] = []
    with pytest.raises(BillingUnavailable, match="BILLING_STATE_UNAVAILABLE"):
        await OwnerMessagingService(auth, "TEST", Refresher(auth)).send(
            "cookie", WS, CONVERSATION, "exact", "key"
        )
    assert auth.trace[-1] == "commit" and "request" not in auth.trace


async def test_controlled_one_unit_uses_real_policy_and_never_provider():
    auth = Auth("CONTROLLED")
    result = await OwnerMessagingService(auth, "TEST", Refresher(auth)).send(
        "cookie", WS, CONVERSATION, "exact", "key"
    )
    assert result.code == "ACCEPTED" and auth.trace.count("begin") == 1
    assert "billing" in auth.trace and "network" not in auth.trace
    auth.receipt = None
    auth.billing["modes"][0].update(mode="SUSPENDED", reason_code="TEST_SUSPENDED")
    with pytest.raises(MessagingError, match="NOT_ALLOWED"):
        await OwnerMessagingService(auth, "TEST", Refresher(auth)).send(
            "cookie", WS, CONVERSATION, "exact", "other"
        )
    assert auth.receipt is None


async def test_replayed_receipt_still_requires_current_owner():
    auth = Auth()
    auth.receipt, auth.role = receipt(), MembershipRole.ADMIN
    with pytest.raises(MessagingError, match="ACCESS_DENIED"):
        await OwnerMessagingService(auth, "TEST", Refresher(auth)).send(
            "cookie", WS, CONVERSATION, "exact", "key"
        )
    assert "prepare" not in auth.trace


async def test_http_exact_text_large_escaped_json_and_cors():
    auth, settings, app = Auth("CONTROLLED"), AuthSettings(auth_origins=(ORIGIN,)), FastAPI()
    install_auth(app, auth, settings)
    install_messaging(app, auth, settings, environment="TEST")
    token = new_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        client.cookies.set(settings.auth_cookie_name, token)
        text = "\U0001f980" * 4096
        response = await client.post(
            PATH,
            content=json.dumps({"text": text}),
            headers={
                "Origin": ORIGIN,
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_value(token),
                "Idempotency-Key": "astral",
            },
        )
        assert response.status_code == 202
        assert set(response.json()) == {
            "workspace_id",
            "receipt_id",
            "message_id",
            "accepted_at",
            "outcome",
        }
        assert response.json()["accepted_at"].endswith(".000000Z")
        for origin, status in ((ORIGIN, 200), ("https://evil.invalid", 400)):
            preflight = await client.options(
                PATH,
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-csrf-token,idempotency-key",
                },
            )
            assert preflight.status_code == status
            assert (preflight.headers.get("access-control-allow-origin") == ORIGIN) == (
                status == 200
            )
