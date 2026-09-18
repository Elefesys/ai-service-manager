"""M1.2 API/security regressions on the real isolated PostgreSQL runtime identity."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
import pytest_asyncio
from asm.auth.crypto import PASSWORD_HASHER, csrf_value, new_token, token_verifier
from asm.auth.models import AuthCode, AuthError
from asm.auth.store import AuthStore
from asm.foundation import Settings, create_app
from asm.tenancy import Permission, TenancyError, current_workspace_context
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from test_tenancy_postgres import BA, BB, MEMBER_A, UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:8000"
LOGIN = "synthetic.owner"


@dataclass(repr=False)
class Harness:
    runtime: object
    migrator: object
    app: object
    client: object
    settings: object
    password: SecretStr = field(repr=False)

    @property
    def service(self):
        return self.app.state.auth_service


@asynccontextmanager
async def browser(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=settings.auth_origins[0]
        ) as client:
            yield app, client


@pytest_asyncio.fixture
async def auth(seeded):
    runtime, migrator = seeded
    config = Settings(
        auth_origins=(ORIGIN,),
        auth_peer_limit=1000,
        auth_global_limit=10000,
        auth_login_limit=1000,
    )
    password = SecretStr(new_token())
    encoded = PASSWORD_HASHER.hash(password.get_secret_value())
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) "
                "VALUES (:id,:login,:encoded)"
            ),
            {"id": UA, "login": LOGIN, "encoded": encoded},
        )
    try:
        async with browser(config) as (app, client):
            yield Harness(runtime, migrator, app, client, config, password)
    finally:
        async with migrator.begin() as connection:
            # This fixture inherits the real asm_test-only guard from M1.1 seeded/db.
            await connection.execute(text("DELETE FROM platform.auth_sessions"))
            await connection.execute(
                text("DELETE FROM platform.auth_credentials WHERE user_account_id=:id"), {"id": UA}
            )


async def bootstrap(client):
    response = await client.post(
        "/api/v1/auth/bootstrap",
        json={},
        headers={"Origin": str(client.base_url).rstrip("/"), "X-CSRF-Bootstrap": "1"},
    )
    assert response.status_code == 200, response.status_code
    return response


async def login(auth, client=None, login_value=LOGIN, password=None):
    client = client or auth.client
    challenge = await bootstrap(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"login": login_value, "password": (password or auth.password).get_secret_value()},
        headers={
            "Origin": str(client.base_url).rstrip("/"),
            "X-CSRF-Token": challenge.json()["csrf_token"],
        },
    )
    return response


def headers(client, csrf):
    return {"Origin": str(client.base_url).rstrip("/"), "X-CSRF-Token": csrf}


def cookie(auth, client=None):
    return (client or auth.client).cookies.get(auth.settings.auth_cookie_name)


async def test_real_login_rotates_preauth_and_reads_business_through_accepted_uow(auth):
    challenge = await bootstrap(auth.client)
    previous = SecretStr(cookie(auth))
    response = await auth.client.post(
        "/api/v1/auth/login",
        json={"login": "  Synthetic.Owner\t", "password": auth.password.get_secret_value()},
        headers=headers(auth.client, challenge.json()["csrf_token"]),
    )
    assert response.status_code == 200
    different = cookie(auth) != previous.get_secret_value()
    assert different
    payload = response.json()
    assert payload["user_account_id"] == str(UA)
    assert payload["memberships"] == [
        {"workspace_id": str(A), "role": "OWNER", "permissions": ["tenancy:read", "tenancy:write"]}
    ]
    businesses = await auth.client.get(f"/api/v1/workspaces/{A}/businesses")
    assert businesses.status_code == 200
    assert BA in {UUID(row["id"]) for row in businesses.json()["businesses"]}
    assert businesses.headers["cache-control"] == "no-store"
    with pytest.raises(AuthError, match="SESSION_REQUIRED"):
        await auth.service.current(previous.get_secret_value())
    async with auth.migrator.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT token_hash,revoked_at FROM platform.auth_sessions WHERE token_hash=:hash"
                    ),
                    {"hash": token_verifier(previous.get_secret_value())},
                )
            )
            .mappings()
            .one()
        )
        assert row["revoked_at"] is not None
        stored_safe = row["token_hash"] != previous.get_secret_value()
        assert stored_safe
    with pytest.raises(TenancyError):
        current_workspace_context()


@pytest.mark.parametrize("case", ["wrong", "unknown", "disabled"])
async def test_credentials_fail_identically_without_issuing_authenticated_session(auth, case):
    if case == "disabled":
        async with auth.migrator.begin() as connection:
            await connection.execute(
                text("UPDATE platform.user_accounts SET status='DISABLED' WHERE id=:id"), {"id": UA}
            )
    response = await login(
        auth,
        login_value="synthetic.absent" if case == "unknown" else LOGIN,
        password=SecretStr(new_token()) if case == "wrong" else auth.password,
    )
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "INVALID_CREDENTIALS"}}
    assert "set-cookie" not in response.headers
    async with auth.migrator.connect() as connection:
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM platform.auth_sessions WHERE user_account_id IS NOT NULL"
                )
            )
        ).scalar_one() == 0


async def test_sessions_persist_between_two_independent_app_instances(auth):
    response = await login(auth)
    assert response.status_code == 200
    async with browser(auth.settings) as (_, other):
        other.cookies.update(auth.client.cookies)
        session = await other.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json()["user_account_id"] == str(UA)
        result = await other.get(f"/api/v1/workspaces/{A}/businesses/{BA}")
        assert result.status_code == 200 and result.json()["id"] == str(BA)


@pytest.mark.parametrize(
    "case", ["anonymous", "forged", "expired", "revoked", "account-disabled", "credential-version"]
)
async def test_invalid_identity_never_reads_business(auth, case):
    if case == "forged":
        auth.client.cookies.set(auth.settings.auth_cookie_name, new_token())
    elif case != "anonymous":
        assert (await login(auth)).status_code == 200
        async with auth.migrator.begin() as connection:
            if case == "expired":
                statement = (
                    "UPDATE platform.auth_sessions SET created_at=clock_timestamp()-interval '2 hours', "
                    "expires_at=clock_timestamp()-interval '1 hour' WHERE user_account_id=:id"
                )
            elif case == "revoked":
                statement = "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() WHERE user_account_id=:id"
            elif case == "account-disabled":
                statement = "UPDATE platform.user_accounts SET status='DISABLED' WHERE id=:id"
            else:
                statement = "UPDATE platform.auth_credentials SET version=version+1 WHERE user_account_id=:id"
            await connection.execute(text(statement), {"id": UA})
    for path in ("/api/v1/auth/session", f"/api/v1/workspaces/{A}/businesses/{BA}"):
        result = await auth.client.get(path)
        assert result.status_code == 401
        assert "set-cookie" not in result.headers
        assert result.json() == {"error": {"code": "SESSION_REQUIRED"}}


async def test_rotation_and_logout_revoke_old_tokens_without_extending_expiry(auth):
    logged = await login(auth)
    assert logged.status_code == 200
    old = SecretStr(cookie(auth))
    rotated = await auth.client.post(
        "/api/v1/auth/rotate", json={}, headers=headers(auth.client, logged.json()["csrf_token"])
    )
    assert rotated.status_code == 200
    assert rotated.json()["expires_at"] == logged.json()["expires_at"]
    changed = cookie(auth) != old.get_secret_value()
    assert changed
    with pytest.raises(AuthError, match="SESSION_REQUIRED"):
        await auth.service.current(old.get_secret_value())
    new = SecretStr(cookie(auth))
    logged_out = await auth.client.post(
        "/api/v1/auth/logout", json={}, headers=headers(auth.client, rotated.json()["csrf_token"])
    )
    assert logged_out.status_code == 204
    assert "Max-Age=0" in logged_out.headers["set-cookie"]
    assert "HttpOnly" in logged_out.headers["set-cookie"]
    with pytest.raises(AuthError, match="SESSION_REQUIRED"):
        await auth.service.current(new.get_secret_value())
    assert (await auth.client.get("/api/v1/auth/session")).status_code == 401


async def test_foreign_ids_and_claimed_actor_role_do_not_authorize(auth):
    assert (
        await auth.client.get(
            f"/api/v1/workspaces/{A}/businesses/{BA}?actor={UA}&role=OWNER",
            headers={"X-User-Id": str(UA), "X-Role": "OWNER"},
        )
    ).status_code == 401
    challenge = await bootstrap(auth.client)
    forged = await auth.client.post(
        "/api/v1/auth/login",
        json={
            "login": LOGIN,
            "password": auth.password.get_secret_value(),
            "user_account_id": str(UA),
            "role": "OWNER",
        },
        headers=headers(auth.client, challenge.json()["csrf_token"]),
    )
    assert forged.status_code == 422
    assert (await login(auth)).status_code == 200
    assert (await auth.client.get(f"/api/v1/workspaces/{B}/businesses/{BB}")).status_code == 403
    assert (await auth.client.get(f"/api/v1/workspaces/{A}/businesses/{BB}")).status_code == 404
    assert (await auth.client.get("/api/v1/ops/accounts")).status_code == 404


async def test_membership_downgrade_and_revoke_are_live_business_member_role_is_not_authority(auth):
    assert (await login(auth)).status_code == 200
    async with auth.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='PROVIDER' "
                "WHERE workspace_id=:ws AND user_account_id=:id"
            ),
            {"ws": A, "id": UA},
        )
        await connection.execute(
            text(
                "UPDATE app.business_members SET user_account_id=:user,role='OWNER' "
                "WHERE workspace_id=:ws AND id=:member"
            ),
            {"user": UA, "ws": A, "member": MEMBER_A},
        )
    response = await auth.client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["memberships"][0]["permissions"] == ["tenancy:read"]
    async with auth.service.workspace(cookie(auth), A) as unit:
        assert unit.context.permissions == {Permission.READ}
        with pytest.raises(TenancyError, match="ACCESS_DENIED"):
            await unit.rename_business(BA, "must not change", 1)
    async with auth.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET status='REVOKED' "
                "WHERE workspace_id=:ws AND user_account_id=:id"
            ),
            {"ws": A, "id": UA},
        )
    assert (await auth.client.get("/api/v1/auth/session")).json()["memberships"] == []
    assert (await auth.client.get(f"/api/v1/workspaces/{A}/businesses/{BA}")).status_code == 403


@pytest.mark.parametrize("path", ["login", "logout", "rotate"])
@pytest.mark.parametrize("case", ["missing", "wrong", "other-session"])
async def test_csrf_is_required_for_login_logout_rotation_and_bound_to_session(auth, path, case):
    challenge = await bootstrap(auth.client) if path == "login" else await login(auth)
    assert challenge.status_code == 200
    origin_headers = {"Origin": ORIGIN}
    if case != "missing":
        origin_headers["X-CSRF-Token"] = (
            "not-a-proof" if case == "wrong" else csrf_value(new_token())
        )
    body = {"login": LOGIN, "password": auth.password.get_secret_value()} if path == "login" else {}
    result = await auth.client.post(f"/api/v1/auth/{path}", json=body, headers=origin_headers)
    assert result.status_code == 403
    assert result.json() == {"error": {"code": "CSRF_REJECTED"}}
    assert "set-cookie" not in result.headers
    if path != "login":
        assert (await auth.client.get("/api/v1/auth/session")).status_code == 200


@pytest.mark.parametrize(
    "origin", [None, "null", "http://attacker.invalid", "http://localhost:8000.attacker.invalid"]
)
async def test_mutation_origin_is_strict_even_with_valid_csrf(auth, origin):
    challenge = await bootstrap(auth.client)
    request_headers = {
        "X-CSRF-Token": challenge.json()["csrf_token"],
        "X-Forwarded-Host": "localhost:8000",
        "X-Forwarded-Proto": "https",
    }
    if origin is not None:
        request_headers["Origin"] = origin
    result = await auth.client.post(
        "/api/v1/auth/login",
        json={"login": LOGIN, "password": auth.password.get_secret_value()},
        headers=request_headers,
    )
    assert result.status_code == 403
    assert result.json() == {"error": {"code": "ORIGIN_DENIED"}}


async def test_bootstrap_protocol_cookie_flags_cors_and_fixed_proxy_host(auth):
    denied = await auth.client.post("/api/v1/auth/bootstrap", json={}, headers={"Origin": ORIGIN})
    assert denied.status_code == 403
    assert (await auth.client.get("/api/v1/auth/bootstrap")).status_code == 405
    response = await bootstrap(auth.client)
    attributes = response.headers["set-cookie"].split("; ")[1:]
    assert "HttpOnly" in attributes and "SameSite=lax" in attributes and "Path=/" in attributes
    assert "Secure" not in attributes and not any(
        x.lower().startswith("domain=") for x in attributes
    )
    assert (await login(auth)).status_code == 200
    assert (
        await auth.client.get("/api/v1/auth/session", headers={"Host": "api:8000"})
    ).status_code == 200
    assert (
        await auth.client.get("/api/v1/auth/session", headers={"Host": "localhost:8000"})
    ).status_code == 200
    wrong_port = await auth.client.get("/api/v1/auth/session", headers={"Host": "localhost:9999"})
    assert wrong_port.status_code == 403
    assert wrong_port.json() == {"error": {"code": "ORIGIN_DENIED"}}
    assert "set-cookie" not in wrong_port.headers
    for malformed_host in ("localhost:8000?", "localhost:8000#"):
        malformed = await auth.client.get("/api/v1/auth/session", headers={"Host": malformed_host})
        assert malformed.status_code == 403
        assert malformed.json() == {"error": {"code": "ORIGIN_DENIED"}}
        assert "set-cookie" not in malformed.headers
    assert (
        await auth.client.get("/api/v1/auth/session", headers={"Host": "attacker@localhost"})
    ).status_code == 403
    allowed = await auth.client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    hostile = await auth.client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://attacker.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert hostile.status_code == 400
    assert "access-control-allow-origin" not in hostile.headers


async def test_tls_cookie_is_secure_and_no_forwarded_header_can_change_it(auth):
    tls = Settings(
        database_url=auth.settings.database_url,
        environment="TEST",
        auth_origins=("https://console.localhost",),
    )
    async with browser(tls) as (_, client):
        response = await client.post(
            "/api/v1/auth/bootstrap",
            json={},
            headers={
                "Origin": "https://console.localhost",
                "X-CSRF-Bootstrap": "1",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-Host": "attacker.invalid",
            },
        )
        assert response.status_code == 200
        assert response.headers["set-cookie"].startswith("__Host-asm_session=")
        attributes = response.headers["set-cookie"].split("; ")[1:]
        assert {"Secure", "HttpOnly", "SameSite=lax", "Path=/"} <= set(attributes)
        assert not any(item.lower().startswith("domain=") for item in attributes)


async def test_input_bounds_duplicate_cookie_and_redacted_errors_logs(auth, caplog):
    challenge = await bootstrap(auth.client)
    good_headers = headers(auth.client, challenge.json()["csrf_token"])
    large = await auth.client.post(
        "/api/v1/auth/login",
        content="x" * 4097,
        headers={**good_headers, "Content-Type": "application/json"},
    )
    assert large.status_code == 413
    malformed = await auth.client.post(
        "/api/v1/auth/login",
        json={"password": auth.password.get_secret_value()},
        headers=good_headers,
    )
    assert malformed.status_code == 422 and malformed.json() == {
        "error": {"code": "INVALID_REQUEST"}
    }
    wrong_type = await auth.client.post(
        "/api/v1/auth/login", content="login=value", headers=good_headers
    )
    assert wrong_type.status_code == 415
    token = SecretStr(cookie(auth))
    duplicate = await auth.client.get(
        "/api/v1/auth/session",
        headers={
            "Cookie": f"{auth.settings.auth_cookie_name}={token.get_secret_value()}; "
            f"{auth.settings.auth_cookie_name}={token.get_secret_value()}"
        },
    )
    assert duplicate.status_code == 401
    safe = all(
        value not in caplog.text + malformed.text + large.text
        for value in (
            auth.password.get_secret_value(),
            token.get_secret_value(),
            token_verifier(token.get_secret_value()),
            auth.settings.database_url.get_secret_value(),
        )
    )
    assert safe


async def test_login_throttle_normalizes_identifier_and_does_not_trust_forwarded_ip(auth):
    limited = Settings(
        database_url=auth.settings.database_url,
        environment="TEST",
        auth_origins=(ORIGIN,),
        auth_login_limit=2,
        auth_peer_limit=1000,
        auth_global_limit=10000,
    )
    async with browser(limited) as (_, client):
        challenge = await bootstrap(client)
        for index, expected in enumerate((401, 401, 429)):
            response = await client.post(
                "/api/v1/auth/login",
                json={"login": LOGIN.upper() if index % 2 else LOGIN, "password": new_token()},
                headers={
                    **headers(client, challenge.json()["csrf_token"]),
                    "X-Forwarded-For": f"192.0.2.{index}",
                },
            )
            assert response.status_code == expected
        assert "Retry-After" in response.headers
    peer_limited = Settings(
        database_url=auth.settings.database_url,
        environment="TEST",
        auth_origins=(ORIGIN,),
        auth_peer_limit=1,
        auth_global_limit=10000,
    )
    async with browser(peer_limited) as (_, client):
        await bootstrap(client)
        response = await client.post(
            "/api/v1/auth/bootstrap",
            json={},
            headers={"Origin": ORIGIN, "X-CSRF-Bootstrap": "1", "X-Forwarded-For": "192.0.2.99"},
        )
        assert response.status_code == 429


async def test_version_recheck_after_real_password_verification_outside_transaction(
    auth, monkeypatch
):
    original = auth.service.hash_budget.run
    checked = False

    async def verify_then_change(operation):
        nonlocal checked
        assert auth.service.store.engine.pool.checkedout() == 0
        result = await original(
            operation
        )  # Actual supported Argon2 verification, not a substitute.
        async with auth.migrator.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform.auth_credentials SET version=version+1 "
                    "WHERE user_account_id=:id"
                ),
                {"id": UA},
            )
        checked = True
        return result

    monkeypatch.setattr(auth.service.hash_budget, "run", verify_then_change)
    response = await login(auth)
    assert checked and response.status_code == 401
    async with auth.migrator.connect() as connection:
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM platform.auth_sessions WHERE user_account_id IS NOT NULL"
                )
            )
        ).scalar_one() == 0


async def test_revocation_waits_for_admitted_uow_then_blocks_next_operation(auth):
    assert (await login(auth)).status_code == 200
    async with auth.service.workspace(cookie(auth), A) as unit:
        with pytest.raises(DBAPIError) as caught:
            async with auth.migrator.begin() as connection:
                await connection.execute(text("SET LOCAL lock_timeout='100ms'"))
                await connection.execute(
                    text(
                        "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() "
                        "WHERE user_account_id=:id"
                    ),
                    {"id": UA},
                )
        assert caught.value.orig.sqlstate == "55P03"
        assert (await unit.get_business(BA))["id"] == BA
    async with auth.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.auth_sessions SET revoked_at=clock_timestamp() "
                "WHERE user_account_id=:id"
            ),
            {"id": UA},
        )
    assert (await auth.client.get(f"/api/v1/workspaces/{A}/businesses/{BA}")).status_code == 401


async def test_concurrent_rotation_has_one_winner_stale_logout_is_not_false_success(auth):
    assert (await login(auth)).status_code == 200
    previous = SecretStr(cookie(auth))
    submitted = asyncio.Event()
    count = 0

    def observe(connection, cursor, statement, parameters, context, executemany):
        nonlocal count
        if "platform.auth_rotate(" in statement:
            count += 1
            if count == 2:
                submitted.set()

    engine = auth.service.store.engine
    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    tasks = []
    try:
        async with auth.migrator.begin() as connection:
            await connection.execute(
                text("SELECT 1 FROM platform.auth_sessions WHERE token_hash=:hash FOR UPDATE"),
                {"hash": token_verifier(previous.get_secret_value())},
            )
            tasks = [
                asyncio.create_task(auth.service.rotate(previous.get_secret_value()))
                for _ in range(2)
            ]
            await asyncio.wait_for(submitted.wait(), 2)
        results = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe)
        await asyncio.gather(*tasks, return_exceptions=True)
    winners = [result for result in results if isinstance(result, tuple)]
    losers = [result for result in results if isinstance(result, AuthError)]
    assert len(winners) == len(losers) == 1
    assert losers[0].code == AuthCode.SESSION_REQUIRED
    with pytest.raises(AuthError, match="SESSION_REQUIRED"):
        await auth.service.logout(previous.get_secret_value())
    current = winners[0][1]
    assert (await auth.service.current(current)).user_account_id == UA
    await auth.service.logout(current)
    with pytest.raises(AuthError, match="SESSION_REQUIRED"):
        await auth.service.current(current)


@pytest.mark.parametrize("mode", ["constructor", "execution_options", "driver"])
async def test_auth_rejects_real_driver_autocommit_without_publishing_identity(auth, mode):
    store = AuthStore(auth.settings.database_url.get_secret_value())
    await store.close()
    options = {"isolation_level": "AUTOCOMMIT"} if mode == "constructor" else {}
    if mode == "driver":
        options["connect_args"] = {"autocommit": True}
    root = create_async_engine(
        auth.runtime.engine.url, pool_size=1, max_overflow=0, hide_parameters=True, **options
    )
    store.engine = (
        root.execution_options(isolation_level="AUTOCOMMIT")
        if mode == "execution_options"
        else root
    )
    try:
        with pytest.raises(AuthError, match="UNAVAILABLE"):
            async with store.transaction():
                pytest.fail("AUTOCOMMIT reached auth body")
        assert store.engine.pool.checkedout() == 0
    finally:
        await store.close()


async def test_runtime_has_only_specific_auth_execute_no_table_crud_or_internal_helper(auth):
    statements = ["SELECT platform.auth_lock_session(NULL,false)", "SET ROLE asm_migrator"]
    for table in ("auth_credentials", "auth_sessions"):
        statements += [
            f"SELECT * FROM platform.{table}",
            f"DELETE FROM platform.{table}",
            f"INSERT INTO platform.{table} DEFAULT VALUES",
        ]
    for statement in statements:
        with pytest.raises(DBAPIError) as caught:
            async with auth.runtime.engine.begin() as connection:
                await connection.execute(text(statement))
        assert caught.value.orig.sqlstate == "42501"
    async with auth.runtime.engine.connect() as connection:
        assert (await connection.execute(text("SELECT current_user"))).scalar_one() == "asm_runtime"
        assert (
            await connection.execute(
                text("SELECT * FROM platform.auth_password_lookup(:login)"),
                {"login": "nonexistent.account"},
            )
        ).all() == []
        assert (await connection.execute(text("SELECT * FROM app.businesses"))).all() == []


@pytest.mark.parametrize("db_timezone", ["UTC", "Etc/UTC", "Europe/Moscow", "America/New_York"])
async def test_cookie_timezone_bootstrap_login_rotate_uses_database_expiry(auth, db_timezone):
    """Real PG, fixture-local connection TimeZone; no ALTER ROLE/DATABASE/global state."""
    assert auth.settings.environment == "TEST"
    url = make_url(auth.settings.database_url.get_secret_value())
    assert url.database == "asm_test" and url.username == "asm_runtime"
    options = url.query.get("options", "")
    assert isinstance(options, str)
    # An isolated app gets its own auth/runtime pools. Keep any existing options,
    # change only this app's connection startup timezone, and dispose at fixture exit.
    zoned_url = url.update_query_dict({"options": f"{options} -c timezone={db_timezone}".strip()})
    settings = Settings(
        **auth.settings.model_dump(exclude={"database_url"}),
        database_url=SecretStr(zoned_url.render_as_string(hide_password=False)),
    )
    async with browser(settings) as (app, client):
        service = app.state.auth_service
        async with service.store.transaction() as connection:
            assert (await connection.execute(text("SHOW TimeZone"))).scalar_one() == db_timezone
            assert (
                await connection.execute(text("SELECT current_user"))
            ).scalar_one() == "asm_runtime"

        async def check_cookie_and_persisted_expiry(response, token, expected_ttl):
            # Status must not be a masked post-commit cookie-formatting exception.
            assert response.status_code == 200
            cookies = SimpleCookie()
            cookies.load(response.headers["set-cookie"])
            cookie_date = parsedate_to_datetime(cookies[settings.auth_cookie_name]["expires"])
            payload_date = datetime.fromisoformat(response.json()["expires_at"])
            async with service.store.transaction() as connection:
                session = await service.store.session(connection, token.get_secret_value())
                assert session is not None
                authoritative_expiry = session.expires_at
                assert authoritative_expiry.utcoffset() == payload_date.utcoffset()
                assert (await connection.execute(text("SHOW TimeZone"))).scalar_one() == db_timezone
            # Separately committed session must match HTTP, including on non-UTC connections.
            assert payload_date == authoritative_expiry
            assert cookie_date.tzinfo is UTC
            assert cookie_date.timestamp() == int(authoritative_expiry.timestamp())
            assert cookie_date.timestamp() <= authoritative_expiry.timestamp()
            async with auth.migrator.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT created_at, expires_at, revoked_at FROM platform.auth_sessions "
                                "WHERE token_hash=:verifier"
                            ),
                            {"verifier": token_verifier(token.get_secret_value())},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["revoked_at"] is None
                assert row["expires_at"] == authoritative_expiry
                lifetime = row["expires_at"] - row["created_at"]
                if expected_ttl is not None:
                    assert lifetime == timedelta(seconds=expected_ttl)
                else:
                    assert (
                        timedelta(0)
                        < lifetime
                        <= timedelta(seconds=settings.auth_session_ttl_seconds)
                    )
            return authoritative_expiry

        challenge = await bootstrap(client)
        prelogin = SecretStr(client.cookies.get(settings.auth_cookie_name))
        await check_cookie_and_persisted_expiry(
            challenge, prelogin, settings.auth_prelogin_ttl_seconds
        )
        logged = await client.post(
            "/api/v1/auth/login",
            json={"login": LOGIN, "password": auth.password.get_secret_value()},
            headers=headers(client, challenge.json()["csrf_token"]),
        )
        assert logged.status_code == 200
        active = SecretStr(client.cookies.get(settings.auth_cookie_name))
        initial_expiry = await check_cookie_and_persisted_expiry(
            logged, active, settings.auth_session_ttl_seconds
        )
        async with service.store.transaction() as connection:
            assert await service.store.session(connection, prelogin.get_secret_value()) is None
        rotated = await client.post(
            "/api/v1/auth/rotate",
            json={},
            headers=headers(client, logged.json()["csrf_token"]),
        )
        assert rotated.status_code == 200
        replacement = SecretStr(client.cookies.get(settings.auth_cookie_name))
        changed = replacement.get_secret_value() != active.get_secret_value()
        assert changed
        # Rotation has a new created_at but preserves the original absolute expiry.
        final_expiry = await check_cookie_and_persisted_expiry(rotated, replacement, None)
        assert final_expiry == initial_expiry
        with pytest.raises(AuthError, match="SESSION_REQUIRED"):
            await service.current(active.get_secret_value())
        with pytest.raises(AuthError, match="SESSION_REQUIRED"):
            await service.current(prelogin.get_secret_value())
        # Old-token API denial and new-token business read prove usable browser state.
        client.cookies.clear()
        client.cookies.set(settings.auth_cookie_name, active.get_secret_value())
        assert (await client.get("/api/v1/auth/session")).status_code == 401
        client.cookies.clear()
        client.cookies.set(settings.auth_cookie_name, replacement.get_secret_value())
        assert (await client.get("/api/v1/auth/session")).status_code == 200
        assert (await client.get(f"/api/v1/workspaces/{A}/businesses/{BA}")).status_code == 200
        logged_out = await client.post(
            "/api/v1/auth/logout",
            json={},
            headers=headers(client, rotated.json()["csrf_token"]),
        )
        assert logged_out.status_code == 204
        assert (await client.get("/api/v1/auth/session")).status_code == 401
