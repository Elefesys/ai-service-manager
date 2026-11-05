"""Real HTTP adapters, accepted auth admission and asm_runtime PostgreSQL UOW."""

import asyncio
import base64
import gc
import json
import sys
import threading
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from asm.billing import http as billing_http
from asm.billing import repository
from asm.billing.errors import BillingError
from asm.billing.models import AuditPage, BillingResponse, ContactResult
from asm.billing.validation import encode_cursor
from asm.tenancy import TenancyError, TenantUnitOfWork, current_workspace_context
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_auth_postgres import auth as auth
from test_auth_postgres import cookie, headers, login
from test_m1_3_service import VECTORS, WS
from test_tenancy_postgres import UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
TABLES = (
    "platform.billing_contact_command_receipts",
    "app.audit_events",
    "platform.workspace_service_modes",
    "platform.workspace_subscriptions",
    "platform.workspace_billing_accounts",
)


async def initialize(connection, workspace, name="Before"):
    # Explicit synthetic interval, independent of wall-clock test execution date.
    result = await connection.execute(
        text(
            "SELECT platform.initialize_local_billing(:ws,'test',1,:name,'ACTIVE','COMPED',"
            "'2000-01-01T00:00:00Z','2100-01-01T00:00:00Z','NORMAL')"
        ),
        {"ws": workspace, "name": name},
    )
    assert result.scalar_one() == "INITIALIZED"


@pytest_asyncio.fixture
async def billing(auth):
    async with auth.migrator.begin() as connection:
        await initialize(connection, A)
        await initialize(connection, B, "Foreign contact")
    response = await login(auth)
    assert response.status_code == 200
    auth.csrf = response.json()["csrf_token"]
    try:
        yield auth
    finally:
        async with auth.migrator.begin() as connection:
            for table in TABLES:
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id IN (:a,:b)"), {"a": A, "b": B}
                )


def route(suffix, workspace=A):
    return f"/api/v1/workspaces/{workspace}/{suffix}"


async def patch(h, name="After", version="1", key="intent-1", workspace=A, **kwargs):
    return await h.client.patch(
        route("billing-account", workspace),
        json={"expected_version": version, "contact_display_name": name},
        headers={**headers(h.client, h.csrf), "Idempotency-Key": key},
        **kwargs,
    )


async def state(h, workspace=A):
    async with h.migrator.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT contact_display_name,version,updated_at,"
                    "(SELECT count(*) FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws),"
                    "(SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws) "
                    "FROM platform.workspace_billing_accounts WHERE workspace_id=:ws"
                ),
                {"ws": workspace},
            )
        ).one_or_none()


@pytest.mark.parametrize("mode", ["NORMAL", "GRACE", "LIMITED", "SUSPENDED"])
async def test_get_real_coherent_snapshot_modes_and_administration_without_billing_gate(
    billing, mode
):
    h = billing
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_service_modes SET mode=:mode,reason_code=:reason WHERE workspace_id=:ws"
            ),
            {
                "ws": A,
                "mode": mode,
                "reason": "PROVISIONED_LOCAL" if mode == "NORMAL" else "TEST_" + mode,
            },
        )
        before = (await connection.execute(text("SELECT CURRENT_TIMESTAMP"))).scalar_one()
    statements = []
    engine = h.service.tenancy._engine

    def observe(connection, cursor, statement, parameters, context, executemany):
        if "WITH evaluation AS" in statement:
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    try:
        response = await h.client.get(route("billing"))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe)
    assert response.status_code == 200
    dto = BillingResponse.model_validate(response.json())
    async with h.migrator.connect() as connection:
        after = (await connection.execute(text("SELECT CURRENT_TIMESTAMP"))).scalar_one()
    assert before <= datetime.fromisoformat(dto.evaluated_at) <= after
    assert len(statements) == 1 and statements[0].count("CURRENT_TIMESTAMP") == 1
    assert dto.mode == mode and dto.mode_active and dto.availability == "ACTIVE"
    decisions = {d.key.rsplit(".", 1)[1]: d for d in dto.decisions}
    if mode == "NORMAL":
        assert (
            decisions["expensive_zero"].type == "LIMIT" and decisions["expensive_zero"].limit == "0"
        )
        assert decisions["expensive_positive"].limit == "3"
        assert decisions["standard_false"].reason == "NOT_ENTITLED"
    elif mode == "GRACE":
        assert decisions["standard_true"].type == "ENABLED"
        assert decisions["standard_false"].reason == "NOT_ENTITLED"
        assert decisions["expensive_zero"].reason == "SERVICE_MODE_RESTRICTED"
    elif mode == "LIMITED":
        assert decisions["essential_true"].type == "ENABLED"
        assert decisions["standard_true"].reason == "SERVICE_MODE_RESTRICTED"
    else:
        assert {d.reason for d in dto.decisions} == {"SERVICE_MODE_RESTRICTED"}
    assert response.headers["cache-control"] == "no-store"
    assert (await h.client.get(route("businesses"))).status_code == 200
    assert (await h.client.get("/api/v1/auth/session")).status_code == 200
    assert (await patch(h)).status_code == 200
    assert (await h.client.get(route("audit-events"))).status_code == 200
    with pytest.raises(TenancyError):
        current_workspace_context()
    assert h.service.store.engine.pool.checkedout() == engine.pool.checkedout() == 0


@pytest.mark.parametrize(
    "case", ["expired_subscription", "future_subscription", "expired_mode", "future_mode"]
)
async def test_independent_inactive_intervals_in_real_get(billing, case):
    h = billing
    table = (
        "workspace_subscriptions" if case.endswith("subscription") else "workspace_service_modes"
    )
    start, end = (
        ("1990-01-01", "1991-01-01") if case.startswith("expired") else ("2101-01-01", "2102-01-01")
    )
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                f"UPDATE platform.{table} SET effective_from=CAST(:start AS timestamptz),effective_until=CAST(:end AS timestamptz) WHERE workspace_id=:ws"
            ),
            {"ws": A, "start": start, "end": end},
        )
    response = await h.client.get(route("billing"))
    assert response.status_code == 200
    body = response.json()
    subscription = case.endswith("subscription")
    assert (body["subscription"] is None) == subscription
    assert body["mode_active"] == subscription
    assert body["availability"] == ("INACTIVE" if subscription else "ACTIVE")
    assert {d["reason"] for d in body["decisions"]} == {
        "SUBSCRIPTION_INACTIVE" if subscription else "SERVICE_MODE_INACTIVE"
    }


async def test_http_command_cas_noop_stale_conflict_replay_and_safe_audit(billing, caplog):
    h = billing
    before = await state(h)
    noop = await patch(h, "  Before  ", key="noop")
    assert noop.status_code == 200
    assert ContactResult.model_validate(noop.json()).outcome == "NOOP"
    after_noop = await state(h)
    assert after_noop[:3] == before[:3] and after_noop[3:] == (1, 1)
    first = await patch(h)
    assert first.status_code == 200
    assert first.json()["outcome"] == "UPDATED" and first.json()["result_version"] == "2"
    stale = await patch(h, "After", key="stale")
    assert stale.status_code == 409 and stale.json() == {"error": {"code": "STALE_STATE"}}
    assert (await state(h))[3:] == (2, 2)  # stale claim rolled back; stale-before-no-op
    conflict = await patch(h, "Changed intention")
    assert conflict.status_code == 409 and conflict.json() == {
        "error": {"code": "IDEMPOTENCY_KEY_CONFLICT"}
    }
    later = await patch(h, "Later", "2", "intent-2")
    assert later.status_code == 200 and later.json()["result_version"] == "3"
    assert (await patch(h)).json() == first.json()
    assert (await patch(h, "Before", key="noop")).json() == noop.json()
    current = (await h.client.get(route("billing"))).json()["account"]
    assert current["contact_display_name"] == "Later" and current["version"] == "3"
    page = await h.client.get(route("audit-events"))
    items = AuditPage.model_validate(page.json()).items
    assert len(items) == 3
    assert all(
        item.payload.model_dump() in ({}, {"changed_fields": ["contact_display_name"]})
        for item in items
    )
    assert (
        "Later" not in page.text
        and "request_fingerprint" not in page.text
        and "intent-1" not in page.text
    )
    assert "Changed intention" not in caplog.text
    assert (await state(h))[3:] == (3, 3)


@pytest.mark.parametrize(
    ("case", "status"),
    [
        ("ADMIN", 403),
        ("PROVIDER", 403),
        ("REVOKED", 403),
        ("account", 401),
        ("session", 401),
        ("expired", 401),
        ("workspace", 403),
        ("anonymous", 401),
        ("foreign", 403),
    ],
)
async def test_all_routes_repeat_live_authority_before_fingerprint_or_receipt(
    billing, monkeypatch, case, status
):
    h = billing
    assert (await patch(h)).status_code == 200
    before = await state(h)
    async with h.migrator.begin() as connection:
        if case in ("ADMIN", "PROVIDER"):
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role=:role WHERE workspace_id=:ws AND user_account_id=:actor"
                ),
                {"role": case, "ws": A, "actor": UA},
            )
        elif case == "REVOKED":
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor"
                ),
                {"ws": A, "actor": UA},
            )
        elif case == "account":
            await connection.execute(
                text("UPDATE platform.user_accounts SET status='DISABLED' WHERE id=:id"), {"id": UA}
            )
        elif case == "session":
            await connection.execute(
                text(
                    "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:id"
                ),
                {"id": UA},
            )
        elif case == "expired":
            await connection.execute(
                text(
                    "UPDATE platform.auth_sessions SET expires_at=created_at + interval '1 microsecond' WHERE user_account_id=:id"
                ),
                {"id": UA},
            )
        elif case == "workspace":
            await connection.execute(
                text("UPDATE platform.workspaces SET status='ARCHIVED' WHERE id=:id"), {"id": A}
            )
    if case == "anonymous":
        h.client.cookies.clear()

    def forbidden(*args, **kwargs):
        pytest.fail("Unauthorized caller reached fingerprint")

    monkeypatch.setattr(repository, "contact_fingerprint", forbidden)
    called = []
    engine = h.service.tenancy._engine

    def observe(connection, cursor, statement, parameters, context, executemany):
        if any(
            name in statement
            for name in (
                "WITH evaluation AS",
                "FROM app.audit_events",
                "platform.update_billing_contact(",
            )
        ):
            called.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    workspace = B if case == "foreign" else A
    try:
        responses = [
            await h.client.get(route("billing", workspace)),
            await h.client.get(route("audit-events", workspace)),
            await patch(h, workspace=workspace),
        ]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe)
    assert [r.status_code for r in responses] == [status] * 3
    assert all(
        r.json() == {"error": {"code": "SESSION_REQUIRED" if status == 401 else "ACCESS_DENIED"}}
        for r in responses
    )
    assert called == [] and await state(h) == before


@pytest.mark.parametrize("missing", ["workspace_service_modes", "workspace_subscriptions", "all"])
async def test_missing_state_is_structural_503_and_missing_account_patch_is_404(billing, missing):
    h = billing
    async with h.migrator.begin() as connection:
        tables = TABLES if missing == "all" else ("platform." + missing,)
        for table in tables:
            await connection.execute(text(f"DELETE FROM {table} WHERE workspace_id=:ws"), {"ws": A})
    response = await h.client.get(route("billing"))
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": "BILLING_STATE_MISSING"}
    }
    if missing == "all":
        response = await patch(h)
        assert response.status_code == 404 and response.json() == {"error": {"code": "NOT_FOUND"}}
        assert (await h.client.get(route("audit-events"))).json() == {
            "items": [],
            "next_cursor": None,
        }


@pytest.mark.parametrize("boundary", ["billing", "auth"])
async def test_both_503_variants_with_actual_postgres_read_failure(billing, boundary, caplog):
    h = billing
    engine = h.service.tenancy._engine if boundary == "billing" else h.service.store.engine

    def fail_query(connection, cursor, statement, parameters, context, executemany):
        selected = (
            "WITH evaluation AS" in statement
            if boundary == "billing"
            else "platform.auth_" in statement
        )
        return ("SELECT 1/0", {}) if selected else (statement, parameters)

    event.listen(engine.sync_engine, "before_cursor_execute", fail_query, retval=True)
    try:
        response = await h.client.get(route("billing"))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_query)
    assert response.status_code == 503
    expected = (
        {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": "DATABASE_UNAVAILABLE"}
        if boundary == "billing"
        else {"code": "UNAVAILABLE"}
    )
    assert response.json() == {"error": expected}
    assert "division" not in response.text + caplog.text and "SELECT" not in response.text
    assert (await h.client.get(route("billing"))).status_code == 200


@pytest.mark.parametrize("target", ["audit", "finalize", "outer"])
async def test_api_command_failure_rolls_back_account_receipt_and_audit(
    billing, monkeypatch, target
):
    h = billing
    before = await state(h)
    table, condition = {
        "audit": ("app.audit_events", "event_type <> 'BILLING_ACCOUNT_CONTACT_UPDATED'"),
        "finalize": ("platform.billing_contact_command_receipts", "status <> 'SUCCEEDED'"),
        "outer": (None, None),
    }[target]
    if table:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    f"ALTER TABLE {table} ADD CONSTRAINT m13_api_failure CHECK (workspace_id <> '{A}'::uuid OR {condition}) NOT VALID"
                )
            )
    else:
        original = BillingRepository_change = repository.BillingRepository.change_contact

        async def fail_after_command(self, body, key):
            await original(self, body, key)
            raise SQLAlchemyError("test outer failure")

        monkeypatch.setattr(repository.BillingRepository, "change_contact", fail_after_command)
    try:
        response = await patch(h)
    finally:
        if table:
            async with h.migrator.begin() as connection:
                await connection.execute(
                    text(f"ALTER TABLE {table} DROP CONSTRAINT m13_api_failure")
                )
        else:
            monkeypatch.setattr(
                repository.BillingRepository, "change_contact", BillingRepository_change
            )
    assert response.status_code == 503 and response.json() == {"error": {"code": "UNAVAILABLE"}}
    assert await state(h) == before
    assert (await patch(h)).status_code == 200


async def test_ambiguous_result_after_commit_recovers_same_intent_then_get(billing, monkeypatch):
    h = billing
    original = h.service.workspace

    @asynccontextmanager
    async def fail_after_commit(token, workspace):
        async with original(token, workspace) as unit:
            yield unit
        raise SQLAlchemyError("test response lost after commits")

    monkeypatch.setattr(h.service, "workspace", fail_after_commit)
    response = await patch(h)
    assert response.status_code == 503
    assert (await state(h))[1] == 2 and (await state(h))[3:] == (1, 2)
    monkeypatch.setattr(h.service, "workspace", original)
    # Accepted current-session/CSRF recovery, followed by the same intent/key/body.
    recovered = await h.client.get("/api/v1/auth/session")
    assert recovered.status_code == 200
    h.csrf = recovered.json()["csrf_token"]
    replay = await patch(h)
    assert replay.status_code == 200 and replay.json()["result_version"] == "2"
    assert (await state(h))[3:] == (1, 2)
    assert (await h.client.get(route("billing"))).json()["account"][
        "contact_display_name"
    ] == "After"


async def test_poisoned_uow_cannot_continue_after_billing_command_error(billing):
    h = billing
    before = await state(h)
    with pytest.raises(TenancyError, match="TRANSACTION_STATE"):
        async with h.service.workspace(cookie(h), A) as unit:
            with pytest.raises(BillingError) as stale:
                await unit.billing_contact(9, "After", "poison")
            assert stale.value.code == "STALE_STATE"
            with pytest.raises(TenancyError, match="TRANSACTION_STATE"):
                await unit.billing_snapshot()
    assert await state(h) == before


async def test_strict_raw_inputs_do_not_hash_claim_or_mutate(billing, monkeypatch):
    h = billing
    before = await state(h)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid input reached fingerprint")

    monkeypatch.setattr(repository, "contact_fingerprint", forbidden)
    valid = {"expected_version": "1", "contact_display_name": "After"}
    bodies = [
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"[]",
        b"null",
        b"{}",
        b'{"expected_version":"1","expected_version":"1","contact_display_name":"After"}',
        b'{"expected_version":"1","contact_display_name":"After","contact_display_name":"After"}',
    ]
    for value in [None, True, 1, "0", "01", "-1", "1.0", "9223372036854775808"]:
        bodies.append(json.dumps({**valid, "expected_version": value}).encode())
    for value in [None, True, 1, "", " ", "x" * 201, "x\n", "x\t", "\x00", "\x7f", "\ud800"]:
        bodies.append(json.dumps({**valid, "contact_display_name": value}).encode())
    for key in ("role", "workspace_id", "actor_id", "contact_email"):
        bodies.append(json.dumps({**valid, key: "untrusted"}).encode())
    common = {**headers(h.client, h.csrf), "Content-Type": "application/json"}
    for body in bodies:
        response = await h.client.patch(
            route("billing-account"), content=body, headers={**common, "Idempotency-Key": "invalid"}
        )
        assert response.status_code == 422 and response.json() == {
            "error": {"code": "INVALID_REQUEST"}
        }
    for keys in [
        [],
        [("Idempotency-Key", "")],
        [("Idempotency-Key", "a b")],
        [("Idempotency-Key", "a,b")],
        [("Idempotency-Key", "x" * 129)],
        [("Idempotency-Key", "one"), ("idempotency-key", "two")],
        [("Idempotency-Key", "one"), ("If-Match", "1")],
    ]:
        response = await h.client.patch(
            route("billing-account"), content=json.dumps(valid), headers=[*common.items(), *keys]
        )
        assert response.status_code == 422 and response.json() == {
            "error": {"code": "INVALID_REQUEST"}
        }
    assert (await h.client.get(route("billing") + "?key=unknown")).status_code == 422
    assert (await h.client.get(route("billing", str(A).upper()))).status_code == 422
    assert (await patch(h, key="good", params={"extra": "1"})).status_code == 422
    for overrides, status in [
        ({"Origin": "http://foreign.example"}, 403),
        ({"X-CSRF-Token": "invalid"}, 403),
        ({"Content-Type": "text/plain"}, 415),
    ]:
        response = await h.client.patch(
            route("billing-account"),
            content=json.dumps(valid),
            headers={**common, "Idempotency-Key": "valid", **overrides},
        )
        assert response.status_code == status
    assert await state(h) == before


async def test_name_and_bigint_boundaries_reach_real_command_without_precision_loss(billing):
    h = billing
    response = await patch(h, " " + "🎨" * 200 + " ", key="x" * 128)
    assert response.status_code == 200
    body = (await h.client.get(route("billing"))).json()
    assert body["account"]["contact_display_name"] == "🎨" * 200
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_billing_accounts SET version=9223372036854775807 WHERE workspace_id=:ws"
            ),
            {"ws": A},
        )
    response = await patch(h, "🎨" * 200, "9223372036854775807", "max-noop")
    assert (
        response.status_code == 200 and response.json()["result_version"] == "9223372036854775807"
    )
    before = await state(h)
    overflow = await patch(h, "Changed", "9223372036854775807", "max-change")
    assert overflow.status_code == 503 and overflow.json() == {"error": {"code": "UNAVAILABLE"}}
    assert await state(h) == before


@pytest.mark.parametrize(("name", "expected"), VECTORS)
async def test_eight_fingerprint_vectors_through_http_match_receipts(
    billing, name, expected, monkeypatch
):
    h = billing
    async with h.migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES(:ws)"), {"ws": WS}
        )
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
            ),
            {"ws": WS, "actor": UA},
        )
        await initialize(connection, WS)
        await connection.execute(
            text("UPDATE platform.workspace_billing_accounts SET version=7 WHERE workspace_id=:ws"),
            {"ws": WS},
        )
    hashes = []
    original = repository.contact_fingerprint

    def capture(*args):
        value = original(*args)
        hashes.append(value.hex())
        return value

    monkeypatch.setattr(repository, "contact_fingerprint", capture)
    try:
        response = await patch(h, name, "7", "vector", WS)
        assert response.status_code == 200 and hashes == [expected]
        async with h.migrator.connect() as connection:
            stored = (
                await connection.execute(
                    text(
                        "SELECT encode(request_fingerprint,'hex') FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws AND idempotency_key='vector'"
                    ),
                    {"ws": WS},
                )
            ).scalar_one()
        assert stored == expected
    finally:
        async with h.migrator.begin() as connection:
            for table in TABLES:
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE workspace_id=:ws"), {"ws": WS}
                )
            await connection.execute(
                text("DELETE FROM platform.workspace_memberships WHERE workspace_id=:ws"),
                {"ws": WS},
            )
            await connection.execute(
                text("DELETE FROM platform.workspaces WHERE id=:ws"), {"ws": WS}
            )


async def test_audit_keyset_tie_break_end_empty_and_strict_tenant_anchor(billing):
    h = billing
    for version in range(1, 4):
        assert (
            await patch(h, f"Change {version}", str(version), f"event-{version}")
        ).status_code == 200
    at = "2026-09-19T12:00:00.123456Z"
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE app.audit_events SET occurred_at=CAST(:at AS timestamptz) WHERE workspace_id=:ws"
            ),
            {"at": at, "ws": A},
        )
        expected = [
            str(value)
            for value in (
                await connection.execute(
                    text(
                        "SELECT audit_event_id FROM app.audit_events WHERE workspace_id=:ws ORDER BY occurred_at DESC,audit_event_id DESC"
                    ),
                    {"ws": A},
                )
            ).scalars()
        ]
        foreign = (
            await connection.execute(
                text(
                    "SELECT audit_event_id,occurred_at FROM app.audit_events WHERE workspace_id=:ws"
                ),
                {"ws": B},
            )
        ).one()
    first = await h.client.get(route("audit-events"), params={"limit": "2"})
    assert first.status_code == 200
    page = first.json()
    assert [i["audit_event_id"] for i in page["items"]] == expected[:2]
    cursor = page["next_cursor"]
    second = await h.client.get(route("audit-events"), params={"limit": "2", "cursor": cursor})
    assert second.status_code == 200 and second.json()["next_cursor"] is None
    assert [i["audit_event_id"] for i in second.json()["items"]] == expected[2:]
    anchor = dict(
        v=1,
        endpoint="AUDIT_EVENTS",
        workspace_id=str(A),
        direction="DESC",
        occurred_at=at,
        id=expected[-1],
    )
    end = await h.client.get(route("audit-events"), params={"cursor": encode_cursor(anchor)})
    assert end.json() == {"items": [], "next_cursor": None}
    invalid = ["!", cursor + "=", "A", "x" * 1025]
    for changes in [
        dict(workspace_id=str(B)),
        dict(id=str(uuid4())),
        dict(id=str(foreign.audit_event_id)),
        dict(v=2),
        dict(v=True),
        dict(endpoint="BILLING"),
        dict(direction="ASC"),
        dict(extra=1),
        dict(occurred_at="2026-09-19T12:00:00Z"),
        dict(occurred_at="2026-09-19T12:00:00.123457Z"),
        dict(id=expected[-1].upper()),
    ]:
        invalid.append(encode_cursor({**anchor, **changes}))
    missing = {k: v for k, v in anchor.items() if k != "id"}
    invalid.append(encode_cursor(missing))
    for raw in [b"\xff", b'{"v":1,"v":1}', json.dumps(anchor).encode()]:
        invalid.append(base64.urlsafe_b64encode(raw).decode().rstrip("="))
    for value in invalid:
        response = await h.client.get(route("audit-events"), params={"cursor": value})
        assert response.status_code == 422 and response.json() == {
            "error": {"code": "INVALID_REQUEST"}
        }
    for query in [
        "limit=0",
        "limit=101",
        "limit=1.0",
        "limit=true",
        "limit=-1",
        "limit=1&limit=2",
        "cursor=" + cursor + "&cursor=" + cursor,
        "other=1",
    ]:
        response = await h.client.get(route("audit-events") + "?" + query)
        assert response.status_code == 422
    # A permitted caller can choose another existing own anchor; it is not a signature.
    middle = await h.client.get(
        route("audit-events"), params={"cursor": encode_cursor({**anchor, "id": expected[0]})}
    )
    assert [i["audit_event_id"] for i in middle.json()["items"]] == expected[1:]


async def test_revocation_cannot_overtake_admitted_http_command_then_blocks_replay(
    billing, monkeypatch
):
    h = billing
    entered, release = asyncio.Event(), asyncio.Event()
    original = TenantUnitOfWork.billing_contact

    async def hold(self, *args):
        entered.set()
        await release.wait()
        return await original(self, *args)

    monkeypatch.setattr(TenantUnitOfWork, "billing_contact", hold)
    task = asyncio.create_task(patch(h))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        with pytest.raises(DBAPIError) as waiting:
            async with h.migrator.begin() as connection:
                await connection.execute(text("SET LOCAL lock_timeout='100ms'"))
                await connection.execute(
                    text(
                        "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:id"
                    ),
                    {"id": UA},
                )
        assert waiting.value.orig.sqlstate == "55P03"
        release.set()
        response = await asyncio.wait_for(task, 2)
        assert response.status_code == 200
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:id"
            ),
            {"id": UA},
        )
    assert (await patch(h)).status_code == 401
    assert (await state(h))[1] == 2 and (await state(h))[3:] == (1, 2)


class _BillingEarlyObservation:
    """One test/process only; never inspect frame locals or application values."""

    def __init__(self, event_loop, index, wall_start, cpu_start):
        self.loop, self.index = event_loop, index
        self.wall_start, self.cpu_start = wall_start, cpu_start
        self.thread_id = threading.get_ident()
        self.cpu_clock = None
        if hasattr(time, "pthread_getcpuclockid"):
            self.cpu_clock = time.pthread_getcpuclockid(self.thread_id)
        self.roots = (
            (str(Path(__file__).resolve().parents[1]) + "/", ""),
            (str(Path(asyncio.__file__).resolve().parents[1]) + "/", "stdlib/"),
        )
        self.samples, self.collections, self.controls = [], [], []
        self.errors = self.dropped = self.thread_samples = 0
        self.pending_gc = None
        self.active = False
        self.lock, self.stop = threading.RLock(), threading.Event()
        self.worker = None
        self.handle = None
        self.window_start = self.window_stop = None
        self.original_callbacks = tuple(gc.callbacks)
        self.original_gc = (gc.isenabled(), gc.get_threshold())

    def stamp(self):
        cpu = (
            time.thread_time()
            if threading.get_ident() == self.thread_id
            else time.clock_gettime(self.cpu_clock)
            if self.cpu_clock is not None
            else None
        )
        return {
            "wall": round(self.loop.time() - self.wall_start, 6),
            "thread_cpu": None if cpu is None else round(cpu - self.cpu_start, 6),
        }

    def stack(self, frame):
        frames = []
        while frame is not None and len(frames) < 8:
            name = frame.f_code.co_filename.replace("\\", "/")
            if "/site-packages/" in name:
                path = "site-packages/" + name.split("/site-packages/", 1)[1]
            else:
                path = next(
                    (
                        label + name[len(root) :]
                        for root, label in self.roots
                        if name.startswith(root)
                    ),
                    "generated" if name.startswith("<") else "external",
                )
            if path.startswith("/") or ".." in path.split("/"):
                path = "external"
            frames.append(
                {
                    "path": path[:360],
                    "function": frame.f_code.co_name[:120],
                    "line": frame.f_lineno,
                }
            )
            frame = frame.f_back
        return frames, frame is not None

    def sample(self, kind, frame, due=None):
        with self.lock:
            if not self.active:
                return
            if len(self.samples) >= 20:
                self.dropped += 1
                return
            # Reserve before allocating a payload: GC callbacks may re-enter
            # this method on the same thread, and still share the twenty slots.
            slot = len(self.samples)
            self.samples.append(None)
            try:
                stamp = self.stamp()
                frames, truncated = self.stack(frame)
                self.samples[slot] = {
                    "kind": kind,
                    **stamp,
                    "due": None if due is None else round(due - self.wall_start, 6),
                    "late": None if due is None else round(max(0, self.loop.time() - due), 6),
                    "request": self.index.get(None),
                    "sampled_loop_thread": kind == "watchdog"
                    or threading.get_ident() == self.thread_id,
                    "frames": frames,
                    "stack_missing": frame is None,
                    "stack_truncated": truncated,
                    "capture_end": round(self.loop.time() - self.wall_start, 6),
                }
            except BaseException:
                self.errors += 1

    def gc_event(self, phase, info):
        try:
            with self.lock:
                if not self.active:
                    return
                if phase == "start":
                    if len(self.collections) >= 10:
                        self.dropped += 1
                        return
                    self.pending_gc = {
                        "generation": info["generation"],
                        "collector_is_loop_thread": threading.get_ident() == self.thread_id,
                        "start": self.stamp(),
                        "stop": None,
                        "collector_cpu_start": time.thread_time(),
                    }
                    self.collections.append(self.pending_gc)
                    # The callback runs at collection start, even when a Python
                    # watchdog cannot acquire the GIL during the collection.
                    self.sample("gc_start", sys._getframe(1))
                elif phase == "stop" and self.pending_gc is not None:
                    self.pending_gc["stop"] = self.stamp()
                    self.pending_gc["collector_cpu_seconds"] = round(
                        time.thread_time() - self.pending_gc.pop("collector_cpu_start"), 6
                    )
                    self.pending_gc = None
        except BaseException:
            self.errors += 1

    def watch(self):
        due = self.loop.time()
        while not self.stop.wait(max(0, due - self.loop.time())):
            try:
                if self.thread_samples >= 16:
                    return
                frame = sys._current_frames().get(self.thread_id)
                try:
                    self.sample("watchdog", frame, due)
                finally:
                    del frame
                self.thread_samples += 1
                due = self.loop.time() + 0.1
            except BaseException:
                self.errors += 1
                return

    def control(self, due):
        if not self.active:
            return
        self.controls.append(
            {
                **self.stamp(),
                "due": round(due - self.wall_start, 6),
                "late": round(max(0, self.loop.time() - due), 6),
            }
        )
        if len(self.controls) < 20:
            due = self.loop.time() + 0.1
            self.handle = self.loop.call_at(due, self.control, due)

    def start(self):
        self.window_start = self.stamp()
        self.active = True
        gc.callbacks.append(self.gc_event)
        self.worker = threading.Thread(target=self.watch, daemon=True)
        self.worker.start()
        due = self.loop.time() + 0.05
        self.handle = self.loop.call_at(due, self.control, due)

    def stop_sampling(self):
        with self.lock:
            if self.active:
                self.window_stop = self.stamp()
            self.active = False
        self.stop.set()
        if self.handle is not None:
            self.handle.cancel()
        if self.gc_event in gc.callbacks:
            gc.callbacks.remove(self.gc_event)

    def finish(self):
        self.stop_sampling()
        if self.worker is not None and self.worker.ident is not None:
            self.worker.join(timeout=0.2)
        clean = {
            "thread_stopped": self.worker is None or not self.worker.is_alive(),
            "control_cancelled": self.handle is None or self.handle.cancelled(),
            "gc_callback_removed": self.gc_event not in gc.callbacks,
            "original_callbacks_preserved": tuple(gc.callbacks) == self.original_callbacks,
            "gc_policy_unchanged": (gc.isenabled(), gc.get_threshold()) == self.original_gc,
        }
        # Missing during-pause samples remain missing: a GIL/process pause can
        # also delay the watchdog. Never label a late sample as an earlier stack.
        samples = [sample for sample in self.samples if sample is not None]
        return {
            "samples": samples,
            "incomplete_samples": len(self.samples) - len(samples),
            "collections": self.collections,
            "controls": self.controls,
            "errors": self.errors,
            "dropped": self.dropped,
            "window": {"start": self.window_start, "stop": self.window_stop},
            "watchdog_limit_reached": self.thread_samples >= 16,
            "control_limit_reached": len(self.controls) >= 20,
            "cpu_clock_available": self.cpu_clock is not None,
            "open_collection": self.pending_gc is not None,
            "watchdog_gaps": [
                {"from": s["due"], "to": s["wall"], "prior_stack": "MISSING"}
                for s in samples
                if s["late"] is not None and s["late"] > 0.1
            ],
            "delayed_controls": [
                {
                    "due": c["due"],
                    "observed": c["wall"],
                    "sample_indices_in_interval": [
                        i
                        for i, s in enumerate(samples)
                        if c["due"] <= s["wall"] and s["capture_end"] < c["wall"]
                    ],
                }
                for c in self.controls
                if c["late"] > 0.05
            ],
            "cleanup": clean,
        }


@pytest.mark.parametrize("case", ["same_intent", "same_key_conflict", "different_keys"])
async def test_real_concurrent_http_claims_and_cas_have_one_changing_winner(
    billing, monkeypatch, capfd, case
):
    h = billing
    entered = asyncio.Event()
    pids = []
    original = TenantUnitOfWork.billing_contact
    loop = asyncio.get_running_loop()
    started = loop.time()
    cpu_started = time.thread_time()
    request_index = ContextVar("billing_concurrency_request")
    requests = [{"index": index, "times": {}, "thread_cpu": {}} for index in range(2)]
    observation = {"stage": "SETUP", "polls": 0, "last_wait": None}
    tasks = []

    early = _BillingEarlyObservation(loop, request_index, started, cpu_started)

    def mark(name):
        index = request_index.get(None)
        if index in (0, 1):
            stamp = early.stamp()
            requests[index]["times"][name] = elapsed()
            requests[index]["thread_cpu"][name] = stamp["thread_cpu"]

    # The pytest fixture also restores partial installation if setup raises.
    scoped = monkeypatch
    originals = []

    def wrap_async(target, attribute, label):
        original_call = getattr(target, attribute)

        async def observed(*args, **kwargs):
            mark(label + "_enter")
            try:
                result = await original_call(*args, **kwargs)
            except BaseException:
                mark(label + "_error")
                raise
            mark(label + "_return")
            return result

        originals.append((target, attribute, original_call))
        scoped.setattr(target, attribute, observed)

    def wrap_transaction(target, label):
        original_transaction = target.transaction

        @asynccontextmanager
        async def observed(*args, **kwargs):
            mark(label + "_enter")
            try:
                async with original_transaction(*args, **kwargs) as connection:
                    mark(label + "_ready")
                    yield connection
            except BaseException:
                mark(label + "_error")
                raise
            mark(label + "_exit")

        originals.append((target, "transaction", original_transaction))
        scoped.setattr(target, "transaction", observed)

    original_build = h.client.build_request

    def build_request(*args, **kwargs):
        mark("request_build_enter")
        try:
            result = original_build(*args, **kwargs)
        except BaseException:
            mark("request_build_error")
            raise
        mark("request_build_return")
        return result

    originals.append((h.client, "build_request", original_build))
    scoped.setattr(h.client, "build_request", build_request)
    wrap_async(h.client, "send", "http_send")
    wrap_async(h.client._transport, "app", "asgi")
    wrap_transaction(h.service.store, "auth_transaction")
    wrap_async(h.service.store, "authenticated", "authenticated")
    wrap_transaction(h.service.tenancy, "tenant_transaction")
    wrap_async(billing_http, "require", "http_permission")
    wrap_async(repository, "require", "repository_permission")

    def elapsed():
        return round(loop.time() - started, 6)

    def emit(boundary):
        # A finite test-only payload; no request/response bodies, SQL or secrets.
        payload = {
            "case": case,
            "boundary": boundary,
            "elapsed": elapsed(),
            "entered": entered.is_set(),
            "pid_count": len(pids),
            "requests": requests,
            "tasks": [
                "CANCELLED" if task.cancelled() else "DONE" if task.done() else "PENDING"
                for task in tasks
            ],
            "observation": observation,
            "observer_is_app_engine": h.runtime.engine is h.service.tenancy._engine,
        }
        # Keep PASS observations in the ordinary job log as well as failures.
        with capfd.disabled():
            print("BILLING_CONCURRENCY_DIAG=" + json.dumps(payload, sort_keys=True), flush=True)

    async def request(index, name, key):
        token = request_index.set(index)
        mark("http_wrapper_enter")
        try:
            response = await patch(h, name, key=key)
            mark("http_wrapper_return")
            requests[index]["http_status"] = response.status_code
            return response
        except BaseException:
            mark("http_wrapper_error")
            raise
        finally:
            request_index.reset(token)

    async def capture_pid(self, *args):
        record = requests[request_index.get()]
        mark("billing_contact_enter")
        # Test-local only. One observation deadline below both SQL deadlines
        # and the unchanged four-second outer auth admission deadline.
        await self._execute("SET LOCAL lock_timeout='3s'", {})
        await self._execute("SET LOCAL statement_timeout='3500ms'", {})
        mark("sql_timeouts_set")
        pid = (await self._execute("SELECT pg_backend_pid()", {})).scalar_one()
        pids.append(pid)
        record["pid"] = pid
        mark("backend_pid_captured")
        if len(pids) == 2:
            entered.set()
        mark("billing_command_enter")
        try:
            result = await original(self, *args)
        except BaseException:
            mark("billing_command_error")
            raise
        mark("billing_command_return")
        return result

    originals.append((TenantUnitOfWork, "billing_contact", original))
    scoped.setattr(TenantUnitOfWork, "billing_contact", capture_pid)
    try:
        observation["stage"] = "BLOCKER_ACQUIRE"
        observation["blocker_started"] = elapsed()
        async with h.migrator.begin() as blocker:
            await blocker.execute(
                text(
                    "SELECT 1 FROM platform.workspace_billing_accounts WHERE workspace_id=:ws FOR NO KEY UPDATE"
                ),
                {"ws": A},
            )
            observation["blocker_acquired"] = elapsed()

            async def blocked():
                while True:
                    for task in tasks:
                        if task.done():
                            response = await task
                            pytest.fail(
                                f"HTTP command ended before blocker release: {response.status_code}"
                            )
                    if entered.is_set():
                        observation["stage"] = "OBSERVER_CONNECT"
                        async with h.runtime.engine.connect() as connection:
                            observation["stage"] = "OBSERVER_QUERY"
                            rows = (
                                (
                                    await connection.execute(
                                        text(
                                            "SELECT pid,wait_event_type='Lock' AS lock_wait,"
                                            "cardinality(pg_blocking_pids(pid)) AS blockers,"
                                            "state='active' AS active FROM pg_stat_activity "
                                            "WHERE pid IN (:a,:b) AND usename=current_user ORDER BY pid"
                                        ),
                                        {"a": pids[0], "b": pids[1]},
                                    )
                                )
                                .mappings()
                                .all()
                            )
                        waiting = sum(
                            row["lock_wait"] is True and row["blockers"] > 0 for row in rows
                        )
                        observation["polls"] += 1
                        observation["last_wait"] = {
                            "elapsed": elapsed(),
                            "backends": [
                                {
                                    "pid": row["pid"],
                                    "lock_wait": row["lock_wait"],
                                    "blockers": row["blockers"],
                                    "active": row["active"],
                                }
                                for row in rows
                            ],
                            "blocked_count": waiting,
                        }
                        observation["stage"] = "OBSERVER_SAMPLED"
                        if waiting == 2:
                            return
                    await asyncio.sleep(0.01)

            try:
                observation["stage"] = "REQUESTS_STARTED"
                observation["observer_started"] = elapsed()
                async with asyncio.timeout(2):
                    early.start()
                    tasks = [
                        asyncio.create_task(request(0, "Winner", "first")),
                        asyncio.create_task(
                            request(
                                1,
                                "Winner" if case == "same_intent" else "Other",
                                "second" if case == "different_keys" else "first",
                            )
                        ),
                    ]
                    await blocked()
                observation["outcome"] = "BOTH_BLOCKED"
            except TimeoutError:
                observation["outcome"] = "TIMEOUT"
                raise
            except BaseException:
                observation["outcome"] = "ERROR"
                raise
            finally:
                early.stop_sampling()
                # Already captured state only, before blocker release/task cancellation.
                emit("BEFORE_BLOCKER_RELEASE")
        responses = await asyncio.wait_for(asyncio.gather(*tasks), 2)
    finally:
        early.stop_sampling()
        emit("BEFORE_TASK_CLEANUP")
        try:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 2)
        finally:
            measured = early.finish()
            scoped.undo()
            measured["cleanup"]["wrapped_functions_restored"] = all(
                getattr(target, attribute) == value for target, attribute, value in originals
            )
            measured["requests_after_cleanup"] = requests
            with capfd.disabled():
                print(
                    "BILLING_EARLY_DIAG=" + json.dumps({"case": case, **measured}, sort_keys=True),
                    flush=True,
                )
            if sys.exception() is None:
                assert all(measured["cleanup"].values()), "Early observation cleanup incomplete"
    if case == "same_intent":
        assert [r.status_code for r in responses] == [200, 200]
        assert responses[0].json() == responses[1].json()
    else:
        assert sorted(r.status_code for r in responses) == [200, 409]
        failure = next(r for r in responses if r.status_code == 409)
        assert failure.json() == {
            "error": {
                "code": "STALE_STATE" if case == "different_keys" else "IDEMPOTENCY_KEY_CONFLICT"
            }
        }
    final = await state(h)
    assert final[1] == 2 and final[3:] == (1, 2)
