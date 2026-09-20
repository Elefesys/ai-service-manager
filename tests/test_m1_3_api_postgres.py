"""Real HTTP adapters, accepted auth admission and asm_runtime PostgreSQL UOW."""

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import pytest
import pytest_asyncio
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
    finally:
        release.set()
    response = await asyncio.wait_for(task, 2)
    assert response.status_code == 200
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:id"
            ),
            {"id": UA},
        )
    assert (await patch(h)).status_code == 401
    assert (await state(h))[1] == 2 and (await state(h))[3:] == (1, 2)


@pytest.mark.parametrize("case", ["same_intent", "same_key_conflict", "different_keys"])
async def test_real_concurrent_http_claims_and_cas_have_one_changing_winner(
    billing, monkeypatch, case
):
    h = billing
    entered = asyncio.Event()
    pids = []
    original = TenantUnitOfWork.billing_contact

    async def capture_pid(self, *args):
        pids.append((await self._execute("SELECT pg_backend_pid()", {})).scalar_one())
        if len(pids) == 2:
            entered.set()
        return await original(self, *args)

    monkeypatch.setattr(TenantUnitOfWork, "billing_contact", capture_pid)
    tasks = []
    try:
        async with h.migrator.begin() as blocker:
            await blocker.execute(
                text(
                    "SELECT 1 FROM platform.workspace_billing_accounts WHERE workspace_id=:ws FOR NO KEY UPDATE"
                ),
                {"ws": A},
            )
            tasks = [
                asyncio.create_task(patch(h, "Winner", key="first")),
                asyncio.create_task(
                    patch(
                        h,
                        "Winner" if case == "same_intent" else "Other",
                        key="second" if case == "different_keys" else "first",
                    )
                ),
            ]
            await asyncio.wait_for(entered.wait(), 2)

            async def blocked():
                while True:
                    async with h.runtime.engine.connect() as connection:
                        waiting = (
                            await connection.execute(
                                text(
                                    "SELECT count(*) FROM pg_stat_activity WHERE pid IN (:a,:b) AND usename=current_user "
                                    "AND wait_event_type='Lock' AND cardinality(pg_blocking_pids(pid))>0"
                                ),
                                {"a": pids[0], "b": pids[1]},
                            )
                        ).scalar_one()
                    if waiting == 2:
                        return
                    assert all(not task.done() for task in tasks)
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(blocked(), 2)
        responses = await asyncio.wait_for(asyncio.gather(*tasks), 2)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
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
