import pytest
from asm.foundation import Health, Settings, create_app
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError


class StubDatabase:
    def __init__(self, failed=False):
        self.failed = failed
        self.closed = False

    async def check(self):
        if self.failed:
            raise RuntimeError("sensitive-connection-details")

    async def close(self):
        self.closed = True


def settings():
    return Settings(
        environment="TEST",
        database_url=SecretStr("postgresql+psycopg://asm_runtime:test@localhost/asm_test"),
    )


def test_health_lifecycle_and_metadata():
    db = StubDatabase()
    with TestClient(create_app(settings(), db)) as client:
        assert client.get("/health/live").json() == {"status": "ok", "component": "api"}
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "component": "database"}
        assert client.get("/api/v1/system").json()["business_features_enabled"] is False
        assert client.get("/api/v1/workspaces").status_code == 404
    assert db.closed


def test_readiness_fails_closed_and_liveness_is_independent():
    with TestClient(create_app(settings(), StubDatabase(True))) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "sensitive" not in response.text
        assert response.json()["status"] == "unavailable"
        assert client.get("/health/live").status_code == 200


@pytest.mark.parametrize(
    "url", ["sqlite:///test.db", "postgresql+psycopg://asm_admin:x@localhost/asm_test", "not-a-url"]
)
def test_rejects_wrong_database_identity_or_driver(url):
    with pytest.raises(ValidationError):
        Settings(environment="TEST", database_url=SecretStr(url))


@pytest.mark.parametrize("environment", ["PRODUCTION", "STAGING"])
def test_shell_refuses_non_local_environments(environment):
    with pytest.raises(ValidationError):
        Settings(environment=environment, database_url=settings().database_url)


def test_schemas_are_strict():
    with pytest.raises(ValidationError):
        Health(status="ok", component="api", workspace_id="invented")


def test_settings_hide_connection_secret():
    assert "test@" not in repr(settings())


def test_runtime_database_head_is_independent_from_frozen_tenancy_contract():
    from asm.foundation import DATABASE_SCHEMA_REVISION
    from asm.tenancy import SCHEMA_REVISION

    assert SCHEMA_REVISION == "0003"
    # Current0015 readiness is distinct from the frozen tenancy.v1 head.
    assert DATABASE_SCHEMA_REVISION == "0018"


@pytest.fixture(scope="module")
def native_verifier_source():
    from scripts import native_context_db_catalog as runner

    return runner.source_catalog(runner.ROOT, "0018")["functions"][
        "platform.business_configuration_schema_profile()"
    ]


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "0012",
        "vector",
        "server",
        "rolsuper",
        "rolbypassrls",
        "rolinherit",
        "rolcreaterole",
        "rolcreatedb",
        "rolreplication",
        "membership",
        "owns_database",
        "owns_relation",
        "app_ddl",
        "platform_ddl",
        "assumed_role",
        "body",
        "public",
        "runtime",
        "language",
        "profile_digest",
        "profile_invalid",
        "profile_extra",
        "profile_bool",
    ],
)
async def test_native_readiness_exact_profile_and_unsafe_role_refusals(
    monkeypatch, native_verifier_source, damage
):
    from types import SimpleNamespace

    from asm import foundation

    source = native_verifier_source
    body = source["body"]
    assert source["language"] == "sql" and source["runtime_execute"] is False
    role = dict.fromkeys(
        (
            "rolsuper",
            "rolbypassrls",
            "rolinherit",
            "rolcreaterole",
            "rolcreatedb",
            "rolreplication",
            "assumed_role",
            "membership",
            "owns_database",
            "owns_relation",
            "app_ddl",
            "platform_ddl",
        ),
        False,
    )
    role["rolname"] = "asm_runtime"
    if damage in role:
        role[damage] = True
    metadata = {
        "body": body + (" " if damage == "body" else ""),
        "owner": "asm_migrator",
        "prosecdef": True,
        "provolatile": "s",
        "proisstrict": False,
        "proconfig": ["search_path=pg_catalog, pg_temp"],
        "lanname": "sql",
        "prokind": "f",
        "pronargs": 0,
        "result": "jsonb",
        "runtime": False,
        "public": False,
    }
    if damage in {"public", "runtime"}:
        metadata[damage] = True
    if damage == "language":
        metadata["lanname"] = "plpgsql"
    declared = {
        "schema_revision": "0018",
        "valid": True,
        "profile_sha256": foundation.NATIVE_CONTEXT_PROFILE_SHA256,
    }
    if damage == "profile_digest":
        declared["profile_sha256"] = "0" * 64
    elif damage == "profile_invalid":
        declared["valid"] = False
    elif damage == "profile_extra":
        declared["trusted"] = True
    elif damage == "profile_bool":
        declared["valid"] = 1
    statements = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, statement):
            sql = str(statement)
            statements.append(sql)
            if sql == body:
                value = declared
            elif "FROM pg_roles WHERE" in sql:
                value = role
            elif sql == "SELECT version_num FROM platform.alembic_version":
                value = "0012" if damage == "0012" else "0018"
            elif "extversion" in sql:
                value = "0.8.5" if damage == "vector" else "0.8.6"
            elif sql == "SHOW server_version_num":
                value = "170000" if damage == "server" else "180006"
            elif "p.prosrc AS body" in sql:
                value = metadata
            else:
                assert sql == "SET LOCAL search_path=pg_catalog,pg_temp"
                value = None
            return SimpleNamespace(
                scalar_one=lambda: value, mappings=lambda: SimpleNamespace(one=lambda: value)
            )

    from sqlalchemy.engine import make_url

    engine = SimpleNamespace(
        connect=lambda: Connection(), url=make_url(settings().database_url.get_secret_value())
    )
    monkeypatch.setattr(foundation, "create_async_engine", lambda *a, **k: engine)
    database = foundation.RuntimeDatabase(settings())
    if damage is None:
        await database.check()
        assert body in statements
        assert statements.index("SET LOCAL search_path=pg_catalog,pg_temp") < statements.index(body)
    else:
        with pytest.raises(RuntimeError):
            await database.check()
        if (
            damage in {"body", "public", "runtime", "language", "0012", "vector", "server"}
            or damage in role
        ):
            assert body not in statements
    # Runtime never obtains EXECUTE on the private migrator capability.
    assert "SELECT platform.business_configuration_schema_profile()" not in statements


@pytest.mark.parametrize("failed", [False, True])
def test_real_api_runtime_boundary_is_checked_before_admission(monkeypatch, failed):
    from unittest.mock import AsyncMock, Mock

    from asm.foundation import RuntimeDatabase

    monkeypatch.setenv("ASM_TELEGRAM_ENABLED", "false")
    # A real RuntimeDatabase type, with only I/O seams replaced. The startup
    # boundary cannot accidentally apply just to a separate health-only stub.
    db = RuntimeDatabase.__new__(RuntimeDatabase)
    db.tenancy = None
    db.check = AsyncMock(side_effect=RuntimeError("schema mismatch") if failed else None)
    db.close = AsyncMock()
    app = create_app(settings(), db, object_storage=Mock())
    if failed:
        with pytest.raises(RuntimeError, match="schema mismatch"):
            with TestClient(app):
                pytest.fail("No API admission before readiness")
    else:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/api/v1/system").status_code == 200
    db.check.assert_awaited_once()
    db.close.assert_awaited_once()


@pytest.fixture
def browser_lifetime_control(monkeypatch):
    """Real factories/disposal, offline I/O seams; not PostgreSQL evidence."""
    import socket
    import weakref
    from types import SimpleNamespace

    import test_auth_postgres as api
    from asm.auth.store import AuthStore
    from asm.foundation import RuntimeDatabase
    from fastapi.dependencies import models

    refs, closed = [], []
    caches = (
        models._is_gen_callable_cached,
        models._is_async_gen_callable_cached,
        models._is_coroutine_callable_cached,
    )

    def deny_network(*args, **kwargs):
        raise AssertionError("Offline lifetime control must not connect")

    async def checked(self):
        pass

    runtime_close, auth_close = RuntimeDatabase.close, AuthStore.close

    async def close_runtime(self):
        await runtime_close(self)
        closed.append("runtime")

    async def close_auth(self):
        await auth_close(self)
        closed.append("auth")

    def factory(config):
        database = RuntimeDatabase(config)
        app = create_app(config, database, object_storage=object())
        refs.append(
            tuple(
                weakref.ref(value)
                for value in (app, database, database.engine, app.state.auth_service.store.engine)
            )
        )
        return app

    monkeypatch.setenv("ASM_ENVIRONMENT", "TEST")
    monkeypatch.setenv("ASM_TELEGRAM_ENABLED", "false")
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(RuntimeDatabase, "check", checked)
    monkeypatch.setattr(RuntimeDatabase, "close", close_runtime)
    monkeypatch.setattr(AuthStore, "close", close_auth)
    monkeypatch.setattr(api, "create_app", factory)
    for cache in caches:
        cache.cache_clear()
    try:
        yield SimpleNamespace(
            api=api, refs=refs, closed=closed, caches=caches, database=RuntimeDatabase
        )
    finally:
        for cache in caches:
            cache.cache_clear()


def test_browser_fixture_releases_closed_objects_with_retaining_control(browser_lifetime_control):
    import asyncio
    import gc
    import json
    from contextlib import asynccontextmanager

    c = browser_lifetime_control
    policy = (gc.isenabled(), gc.get_threshold())

    @asynccontextmanager
    async def before_repair(config):
        # Exact former browser lifecycle, without the new cache cleanup.
        app = c.api.create_app(config)
        async with app.router.lifespan_context(app):
            async with c.api.AsyncClient(
                transport=c.api.ASGITransport(app=app), base_url=config.auth_origins[0]
            ) as client:
                yield app, client

    async def close_twelve(browser):
        for _ in range(12):
            async with browser(settings()):
                pass

    def alive():
        return [sum(refs[index]() is not None for refs in c.refs) for index in range(4)]

    asyncio.run(close_twelve(before_repair))
    # Explicit collection belongs only to this separate reachability control.
    gc.collect(2)
    baseline = alive()
    assert baseline == [0, 12, 12, 12]
    assert c.closed == ["auth", "runtime"] * 12
    for cache in c.caches:
        cache.cache_clear()
    gc.collect(2)
    assert alive() == [0, 0, 0, 0]
    c.refs.clear()
    c.closed.clear()

    asyncio.run(close_twelve(c.api.browser))
    gc.collect(2)
    repaired = alive()
    assert repaired == [0, 0, 0, 0]
    assert c.closed == ["auth", "runtime"] * 12
    assert all(cache.cache_info().currsize == 0 for cache in c.caches)
    assert (gc.isenabled(), gc.get_threshold()) == policy
    print("BROWSER_LIFETIME_CONTROL=" + json.dumps({"baseline": baseline, "repaired": repaired}))


@pytest.mark.parametrize(
    "failure_at",
    ["body", "cancel", "readiness", "client_setup", "resource_cleanup", "factory_setup"],
)
def test_browser_fixture_clears_closed_scope_without_hiding_errors(
    browser_lifetime_control, monkeypatch, failure_at
):
    import asyncio
    import gc

    from fastapi.dependencies import models

    c = browser_lifetime_control
    failure = RuntimeError("Offline lifecycle fault")

    async def readiness(self):
        raise failure

    def setup(*args, **kwargs):
        # Model a partial factory failure after classifier memoization.
        models._is_coroutine_callable(lambda: None)
        raise failure

    original_close = c.database.close

    async def close(self):
        await original_close(self)
        raise failure

    if failure_at == "readiness":
        monkeypatch.setattr(c.database, "check", readiness)
    elif failure_at == "resource_cleanup":
        monkeypatch.setattr(c.database, "close", close)
    elif failure_at in {"client_setup", "factory_setup"}:
        monkeypatch.setattr(
            c.api, "AsyncClient" if failure_at == "client_setup" else "create_app", setup
        )

    async def exercise():
        entered = asyncio.Event()

        async def scoped():
            async with c.api.browser(settings()):
                if failure_at == "body":
                    raise failure
                if failure_at == "cancel":
                    entered.set()
                    await asyncio.Future()

        task = asyncio.create_task(scoped())
        if failure_at == "cancel":
            await entered.wait()
            task.cancel()
        await task

    expected = asyncio.CancelledError if failure_at == "cancel" else RuntimeError
    with pytest.raises(expected) as caught:
        asyncio.run(exercise())
    if failure_at != "cancel":
        assert caught.value is failure
    del caught
    # The assertion's deliberately retained exception must not keep its frames.
    failure.__traceback__ = None
    gc.collect(2)
    assert all(ref() is None for group in c.refs for ref in group)
    assert all(cache.cache_info().currsize == 0 for cache in c.caches)
    assert c.closed == ([] if failure_at == "factory_setup" else ["auth", "runtime"])


def test_nested_browser_cache_cleanup_preserves_the_active_outer_app(browser_lifetime_control):
    import asyncio
    import gc

    c = browser_lifetime_control

    async def exercise():
        async with c.api.browser(settings()) as (outer, client):
            before = await client.get("/api/v1/system")
            async with c.api.browser(settings()) as (_, inner):
                assert (await inner.get("/health/live")).status_code == 200
            assert all(ref() is not None for ref in c.refs[0])
            assert client._transport.app is outer and not client.is_closed
            after = await client.get("/api/v1/system")
            assert before.status_code == after.status_code == 200
            assert before.json() == after.json()
        assert client.is_closed

    asyncio.run(exercise())
    gc.collect(2)
    assert all(ref() is None for group in c.refs for ref in group)
    assert c.closed == ["auth", "runtime"] * 2
    assert all(cache.cache_info().currsize == 0 for cache in c.caches)
