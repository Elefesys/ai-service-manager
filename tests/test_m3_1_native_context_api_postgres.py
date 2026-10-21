"""Module-installed HTTP/API on owned native0013; not application startup PASS.

Reuses the frozen native fixture including explicit owned reset/login/source
guards. No foundation readiness override, provider/LLM/S3 or external send.
"""

import json
import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.auth.config import AuthSettings
from asm.auth.crypto import PASSWORD_HASHER, new_token
from asm.auth.http import install_auth
from asm.auth.service import AuthService
from asm.auth.store import AuthStore
from asm.billing.http import install_billing
from asm.billing.models import AuditPage
from asm.billing.validation import encode_cursor
from asm.conversations.escalation_http import install_escalations
from asm.conversations.http import install_control
from asm.conversations.native_context import decode_observation_cursor, reconcile_fingerprint
from asm.conversations.native_context_http import install_native_context
from asm.conversations.native_context_http_models import (
    HumanContextState,
    ReconcileRequest,
    ReconcileResponse,
)
from asm.messaging.http import install_messaging
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from test_auth_postgres import headers, login
from test_m2_1_postgres import CA, query
from test_m2_3_db_postgres import OWNER
from test_m3_1_native_context_postgres import incoming, policy, read, reconcile_body, scalar
from test_m3_1_native_context_postgres import native as native
from test_tenancy_postgres import UA, A, B

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def native_api(native):
    h = native
    settings = AuthSettings(auth_peer_limit=1000, auth_global_limit=10000, auth_login_limit=1000)
    password = SecretStr(new_token())
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) VALUES(:id,'synthetic.owner',:hash)"
            ),
            {"id": UA, "hash": PASSWORD_HASHER.hash(password.get_secret_value())},
        )
    store = AuthStore(os.environ["ASM_DATABASE_URL"])
    auth = AuthService(store, h.runtime.tenancy, settings)
    app = FastAPI()
    install_auth(app, auth, settings)
    install_billing(app, auth, settings)
    install_messaging(app, auth, settings, environment="TEST")
    install_control(app, auth, settings)
    install_escalations(app, auth, settings)
    install_native_context(app, auth, settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost:8000"
        ) as client:
            h.client, h.settings, h.password, h.app = client, settings, password, app
            response = await login(h)
            assert response.status_code == 200
            h.csrf = response.json()["csrf_token"]
            yield h
    finally:
        await store.engine.dispose()


def route(cid, suffix="human-context", ws=A):
    return f"/api/v1/workspaces/{ws}/conversations/{cid}/{suffix}"


async def post(h, cid, body, key=None, suffix="human-context/reconcile"):
    return await h.client.post(
        route(cid, suffix),
        json=body,
        headers=headers(h.client, h.csrf) | {"Idempotency-Key": key or str(uuid4())},
    )


async def counts(h):
    return tuple(
        [
            await scalar(h, f"SELECT count(*) FROM {name}")
            for name in (
                "platform.human_context_reconciliations",
                "app.audit_events",
                "app.messages",
                "app.outbox_events",
                "platform.messaging_jobs",
            )
        ]
    )


async def test_native_routes_reconcile_hash_replacement_replay_and_mixed_audit(native_api):
    h = native_api
    _, _, cid = await incoming(h)
    await policy(h, CA)
    initial = await h.client.get(route(cid))
    state = HumanContextState.model_validate(initial.json())
    assert initial.status_code == 200 and state.review_status == "BOOTSTRAP_REQUIRED"
    first_body = reconcile_body(initial.json(), value=" exact e\u0301 🎨 owner handoff\n")
    first = await post(h, cid, first_body, "native-r1")
    accepted = ReconcileResponse.model_validate(first.json())
    assert first.status_code == 200 and accepted.outcome == "ACCEPTED"
    stored = await scalar(
        h,
        "SELECT encode(request_fingerprint,'hex') FROM platform.human_context_reconciliations WHERE id=:id",
        id=UUID(accepted.result.revision_id),
    )
    assert stored == reconcile_fingerprint(A, UA, cid, ReconcileRequest.model_validate(first_body))
    second_body = reconcile_body(
        (await h.client.get(route(cid))).json(), value="Replacement contains the whole agreement."
    )
    second = await post(h, cid, second_body, "native-r2")
    assert second.status_code == 200
    before = await counts(h)
    current = (await h.client.get(route(cid))).json()
    stale_r = await post(
        h,
        cid,
        reconcile_body(current) | {"expected_revision_id": accepted.result.revision_id},
        "same-c-stale-r",
    )
    assert stale_r.status_code == 409 and stale_r.json() == {"error": {"code": "STALE_STATE"}}
    conflict = await post(h, cid, first_body | {"text": "Different full body"}, "native-r1")
    assert conflict.status_code == 409 and conflict.json() == {
        "error": {"code": "IDEMPOTENCY_KEY_CONFLICT"}
    }
    replayed = await post(h, cid, first_body, "native-r1")
    assert replayed.json() == first.json() | {"outcome": "REPLAY"}
    assert (await h.client.get(route(cid))).json()["current_revision"][
        "revision_id"
    ] == second.json()["result"]["revision_id"]
    assert await counts(h) == before
    page = await h.client.get(f"/api/v1/workspaces/{A}/audit-events")
    events = AuditPage.model_validate(page.json()).items
    assert {"HUMAN_CONTEXT_RECONCILED", "HUMAN_CONTEXT_POLICY_COMMANDED"} <= {
        e.event_type for e in events
    }
    assert all(
        "reviewed_input_state_hash" not in e.payload.model_dump()
        and "text" not in e.payload.model_dump()
        for e in events
    )
    assert h.adapter.calls == 0


@pytest.mark.parametrize(
    "field",
    [
        "expected_control_generation",
        "expected_context_version",
        "expected_policy_epoch",
        "expected_observation_epoch",
        "expected_ingress_checkpoint",
        "expected_input_state_hash",
    ],
)
async def test_http_reconcile_full_cas_has_no_partial_write(native_api, field):
    h = native_api
    _, _, cid = await incoming(h)
    await policy(h, CA)
    body = reconcile_body((await h.client.get(route(cid))).json())
    body[field] = "f" * 64 if field.endswith("hash") else str(int(body[field]) + 1)
    before = await counts(h)
    result = await post(h, cid, body)
    assert result.status_code == 409 and result.json() == {"error": {"code": "STALE_STATE"}}
    assert await counts(h) == before and h.adapter.calls == 0


async def test_http_authority_revoke_cross_workspace_and_same_workspace_client_revision(native_api):
    h = native_api
    _, _, cid = await incoming(h)
    _, _, other = await incoming(
        h, 2, chat_id="other-native-client", sender_id="other-native-client"
    )
    await policy(h, CA)
    p = (await h.client.get(route(cid))).json()
    other_p = (await h.client.get(route(other))).json()
    other_r = await post(h, other, reconcile_body(other_p))
    assert other_r.status_code == 200
    before = await counts(h)
    for changed in (
        {"expected_client_id": other_p["client_id"]},
        {"expected_revision_id": other_r.json()["result"]["revision_id"]},
    ):
        response = await post(h, cid, reconcile_body(p) | changed)
        assert response.status_code == 404 and response.json() == {"error": {"code": "NOT_FOUND"}}
    assert (await h.client.get(route(cid, ws=B))).status_code == 403
    assert (await h.client.get(route(uuid4()))).status_code == 404
    await query(
        h,
        "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:id AND revoked_at IS NULL RETURNING user_account_id",
        id=UA,
    )
    assert (await h.client.get(route(cid))).status_code == 401
    assert (await post(h, cid, reconcile_body(p))).status_code == 401
    assert await counts(h) == before


async def test_http_cursor_snapshot_bounds_live_scope_and_policy_staleness(native_api):
    h = native_api
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    for number in (20, 21):
        await incoming(h, number, provider="TELEGRAM", sender=OWNER)
    first = await h.client.get(route(cid, "human-context/observations") + "?limit=1")
    assert first.status_code == 200 and first.json()["through_epoch"] == "2"
    saved = first.json()["next_cursor"]
    decoded = decode_observation_cursor(saved)
    await incoming(h, 22, provider="TELEGRAM", sender=OWNER)
    second = await h.client.get(
        route(cid, "human-context/observations") + "?limit=1&cursor=" + saved
    )
    assert second.status_code == 200
    assert second.json()["through_epoch"] == "2" and second.json()["current_epoch"] == "3"
    assert [i["epoch"] for i in second.json()["items"]] == ["2"] and second.json()[
        "next_cursor"
    ] is None
    for changes, status in (
        ({"ws": str(B)}, 403),
        ({"C": str(uuid4())}, 404),
        ({"Client": str(uuid4())}, 404),
        ({"through_N": "99"}, 422),
    ):
        token = encode_cursor(decoded.model_dump() | changes)
        assert (
            await h.client.get(route(cid, "human-context/observations") + "?cursor=" + token)
        ).status_code == status
    await policy(h, h.telegram_connection, "PAUSE")
    await policy(h, h.telegram_connection, "ENABLE")
    stale = await h.client.get(route(cid, "human-context/observations") + "?cursor=" + saved)
    assert stale.status_code == 409 and stale.json() == {"error": {"code": "CONTEXT_CURSOR_STALE"}}


async def test_http_raw_4096_cap_duplicates_query_and_paused_human_save(native_api):
    h = native_api
    _, _, cid = await incoming(h)
    await policy(h, CA)
    await policy(h, CA, "PAUSE")
    body = reconcile_body((await h.client.get(route(cid))).json())
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    exact = encoded + b" " * (4096 - len(encoded))
    good_headers = headers(h.client, h.csrf) | {
        "Content-Type": "application/json",
        "Idempotency-Key": "raw4096",
    }
    before = await counts(h)
    bad = await h.client.post(
        route(cid, "human-context/reconcile"), content=exact + b" ", headers=good_headers
    )
    assert bad.status_code == 413 and await counts(h) == before
    for payload in (encoded[:-1] + b',"text":"duplicate"}', b'{"x":NaN}'):
        r = await h.client.post(
            route(cid, "human-context/reconcile"), content=payload, headers=good_headers
        )
        assert r.status_code == 422 and await counts(h) == before
    for query_string in ("?limit=", "?limit=01", "?cursor=", "?limit=1&limit=2", "?unknown=x"):
        assert (
            await h.client.get(route(cid, "human-context/observations") + query_string)
        ).status_code == 422
    saved = await h.client.post(
        route(cid, "human-context/reconcile"), content=exact, headers=good_headers
    )
    assert saved.status_code == 200 and saved.json()["outcome"] == "ACCEPTED"
    assert (await h.client.get(route(cid))).json()["review_status"] == "POLICY_PAUSED"
    assert h.adapter.calls == 0


async def test_http_resume_corrected_semantic_mapping_and_replay_priority(native_api):
    h = native_api
    _, _, cid = await incoming(h)
    await policy(h, CA)

    def body(p):
        return dict(
            expected_client_id=p["client_id"],
            expected_control_generation=p["control_generation"],
            expected_context_version=p["context_version"],
        )

    missing = await post(h, cid, body(await read(h, cid)), suffix="resume")
    assert missing.status_code == 409 and missing.json() == {
        "error": {"code": "CONTEXT_CONFIRMATION_REQUIRED"}
    }
    assert (await post(h, cid, reconcile_body(await read(h, cid)))).status_code == 200
    expected = body(await read(h, cid))
    accepted = await post(h, cid, expected, "resume-saved", "resume")
    assert accepted.status_code == 200
    assert (await post(h, cid, body(await read(h, cid)), suffix="resume")).json() == {
        "error": {"code": "HUMAN_REQUIRED"}
    }
    await policy(h, CA, "PAUSE")
    paused = await post(h, cid, body(await read(h, cid)), suffix="resume")
    assert paused.json() == {"error": {"code": "CONTEXT_POLICY_PAUSED"}}
    replay = await post(h, cid, expected, "resume-saved", "resume")
    assert replay.json() == accepted.json() | {"outcome": "REPLAY"}


async def test_http_real_deferred_commit_failure_rolls_back_reconcile(native_api):
    h = native_api
    _, _, cid = await incoming(h)
    await policy(h, CA)
    body = reconcile_body(await read(h, cid))
    before = await counts(h)
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform.test_runtime_api_commit_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.human_context_revision_id IS DISTINCT FROM OLD.human_context_revision_id THEN RAISE EXCEPTION 'native test commit failure' USING ERRCODE='23514'; END IF; RETURN NULL; END $$"
            )
        )
        await c.execute(
            text(
                "CREATE CONSTRAINT TRIGGER test_runtime_api_commit_failure AFTER UPDATE ON app.conversations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.test_runtime_api_commit_failure()"
            )
        )
    try:
        failed = await post(h, cid, body, "commit-retry")
        assert failed.status_code == 503 and "result" not in failed.json()
        assert await counts(h) == before and (await read(h, cid))["current_revision"] is None
    finally:
        async with h.migrator.begin() as c:
            await c.execute(
                text("DROP TRIGGER test_runtime_api_commit_failure ON app.conversations")
            )
            await c.execute(text("DROP FUNCTION platform.test_runtime_api_commit_failure()"))
    assert (await post(h, cid, body, "commit-retry")).status_code == 200
