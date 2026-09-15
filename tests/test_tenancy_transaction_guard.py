"""C0's fail-before-yield contract on real PostgreSQL/psycopg connections."""

from uuid import uuid4

import pytest
from asm.tenancy import (
    AuthenticatedAccount,
    ErrorCode,
    TenancyError,
    TenantDatabase,
    current_workspace_context,
)
from asm.tenancy import database as tenancy_module
from psycopg.pq import TransactionStatus
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from test_tenancy_postgres import BA, BA2, UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration

BINDING_SQL = (
    "SELECT app.current_workspace_id() AS workspace_id, "
    "pg_current_xact_id_if_assigned()::text AS xid, "
    "NULLIF(current_setting('asm.context_xid', true), '') AS context_xid"
)


def assert_no_context():
    with pytest.raises(TenancyError, match="CONTEXT_REQUIRED"):
        current_workspace_context()


@pytest.fixture
def publications(monkeypatch):
    # Instrument Python publication only; delegate to the real ContextVar.
    # No PostgreSQL engine, connection, query or result is replaced.
    actual = tenancy_module._active
    published = []

    class PublicationProbe:
        def get(self):
            return actual.get()

        def set(self, unit):
            published.append(unit)
            return actual.set(unit)

        def reset(self, token):
            return actual.reset(token)

    monkeypatch.setattr(tenancy_module, "_active", PublicationProbe())
    yield published
    assert actual.get() is None


async def assert_empty_checkout(connection, expected_pid):
    driver = (await connection.get_raw_connection()).driver_connection
    assert driver.info.backend_pid == expected_pid
    assert driver.info.transaction_status == TransactionStatus.IDLE
    row = (await connection.execute(text(BINDING_SQL))).mappings().one()
    assert dict(row) == {"workspace_id": None, "xid": None, "context_xid": None}
    for key in ("workspace_id", "actor_id", "actor_kind", "correlation_id", "context_xid"):
        assert (
            await connection.execute(
                text("SELECT NULLIF(current_setting(:key, true), '')"), {"key": "asm." + key}
            )
        ).scalar_one() is None
    assert (await connection.execute(text("SELECT * FROM app.businesses"))).all() == []


@pytest.mark.parametrize("mode", ["constructor", "execution_options", "dbapi_connect_args"])
async def test_autocommit_rejected_before_body_and_publication_then_same_pool_recovers(
    seeded, publications, mode
):
    runtime, _ = seeded
    options = {}
    if mode == "constructor":
        options["isolation_level"] = "AUTOCOMMIT"
    elif mode == "dbapi_connect_args":
        options["connect_args"] = {"autocommit": True}
    engine = create_async_engine(
        runtime.engine.url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=1,
        hide_parameters=True,
        **options,
    )
    target = (
        engine.execution_options(isolation_level="AUTOCOMMIT")
        if mode == "execution_options"
        else engine
    )
    try:
        # Prove the mode of the actual connection, independently of SQLAlchemy options.
        async with target.connect() as connection:
            driver = (await connection.get_raw_connection()).driver_connection
            assert driver.autocommit is True
            pid = driver.info.backend_pid
        entered = False
        tenant = TenantDatabase(target)
        for _ in range(2):
            with pytest.raises(TenancyError) as caught:
                async with tenant.transaction(AuthenticatedAccount(UA), A, uuid4()):
                    entered = True
            assert caught.value.code == ErrorCode.CONTEXT_INVALID
            assert not entered
            assert publications == []
            assert_no_context()
            assert target.pool.checkedout() == 0
            async with target.connect() as connection:
                driver = (await connection.get_raw_connection()).driver_connection
                assert driver.autocommit is True  # The guard did NOT change engine/driver mode.
                await assert_empty_checkout(connection, pid)
        # Explicit test-side reconfiguration, never an implicit production fallback.
        # Reuse the very same pool and physical connection after the rejected UOWs.
        normal = target.execution_options(isolation_level="READ COMMITTED")
        assert normal.pool is target.pool
        async with TenantDatabase(normal).transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            driver = (await unit._connection.get_raw_connection()).driver_connection
            assert driver.info.backend_pid == pid
            assert not driver.autocommit
            assert driver.info.transaction_status == TransactionStatus.INTRANS
            row = (await unit._execute(BINDING_SQL, {})).mappings().one()
            assert row["workspace_id"] == unit.context.workspace_id == A
            assert row["xid"] and row["xid"] == row["context_xid"]
            await unit.rename_business(BA, "committed after refusal", 1)
        assert_no_context()
        assert target.pool.checkedout() == 0
        async with TenantDatabase(normal).transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            row = await unit.get_business(BA)
            assert row["name"] == "committed after refusal" and row["version"] == 2
        assert len(publications) == 2
        assert_no_context()
    finally:
        await engine.dispose()


async def test_real_binding_survives_statements_and_later_error_rolls_back_write(
    seeded, publications
):
    runtime, migrator = seeded
    engine = create_async_engine(
        runtime.engine.url, pool_size=1, max_overflow=0, hide_parameters=True
    )
    tenant = TenantDatabase(engine)
    try:
        with pytest.raises(RuntimeError, match="abort-after-write"):
            async with tenant.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
                driver = (await unit._connection.get_raw_connection()).driver_connection
                pid = driver.info.backend_pid
                assert not driver.autocommit
                assert driver.info.transaction_status == TransactionStatus.INTRANS
                before = (await unit._execute(BINDING_SQL, {})).mappings().one()
                assert before["workspace_id"] == current_workspace_context().workspace_id == A
                assert before["xid"] and before["xid"] == before["context_xid"]
                await unit.rename_business(BA, "not committed", 1)
                after = (await unit._execute(BINDING_SQL, {})).mappings().one()
                assert dict(after) == dict(before)
                # Separate real DB session must still observe the original committed row.
                async with migrator.connect() as observer:
                    assert (
                        await observer.execute(
                            text(
                                "SELECT name FROM app.businesses WHERE workspace_id=:ws AND id=:id"
                            ),
                            {"ws": A, "id": BA},
                        )
                    ).scalar_one() == "A"
                raise RuntimeError("abort-after-write")
        assert_no_context()
        assert engine.pool.checkedout() == 0
        async with engine.connect() as connection:
            await assert_empty_checkout(connection, pid)
        async with tenant.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            row = await unit.get_business(BA)
            assert row["name"] == "A" and row["version"] == 1
        assert len(publications) == 2
        assert_no_context()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("damaged", ["workspace_id", "context_xid"])
async def test_real_prepublication_binding_mismatch_rejects_and_rolls_back_setup(
    seeded, publications, damaged
):
    runtime, migrator = seeded
    if damaged == "workspace_id":
        # Make B a VALID but different DB Workspace for UA, so non-null alone cannot pass.
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) "
                    "VALUES (:ws,:actor,'PROVIDER')"
                ),
                {"ws": B, "actor": UA},
            )
    engine = create_async_engine(
        runtime.engine.url, pool_size=1, max_overflow=0, hide_parameters=True
    )
    identifier = uuid4()
    observed = []

    def damage_real_settings(connection, cursor, statement, parameters, context, executemany):
        if "set_config('asm.context_xid'" not in statement:
            return
        assert_no_context()
        # Fault injection executes real SQL inside the same real transaction.
        # Neither results nor driver state are mocked. No commit/session setter/DDL.
        cursor.execute(
            "INSERT INTO app.businesses(workspace_id,id,name) VALUES (%s,%s,%s)",
            (A, identifier, "must roll back with failed setup"),
        )
        cursor.execute(
            "SELECT set_config(%s,%s,true)",
            ("asm." + damaged, str(B) if damaged == "workspace_id" else "0"),
        )
        cursor.execute(BINDING_SQL)
        observed.append(cursor.fetchone())

    event.listen(engine.sync_engine, "after_cursor_execute", damage_real_settings)
    try:
        entered = False
        with pytest.raises(TenancyError) as caught:
            async with TenantDatabase(engine).transaction(AuthenticatedAccount(UA), A, uuid4()):
                entered = True
        assert caught.value.code == ErrorCode.TRANSACTION_STATE
        assert not entered and publications == []
        assert len(observed) == 1
        workspace, xid, fence = observed[0]
        assert xid
        if damaged == "workspace_id":
            assert workspace == B and xid == fence
        else:
            assert workspace is None and fence == "0" and xid != fence
        assert_no_context()
        assert engine.pool.checkedout() == 0
        event.remove(engine.sync_engine, "after_cursor_execute", damage_real_settings)
        async with TenantDatabase(engine).transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            assert {row["id"] for row in await unit.list_businesses()} == {BA, BA2}
            with pytest.raises(TenancyError, match="NOT_FOUND"):
                await unit.get_business(identifier)
        assert len(publications) == 1
        assert_no_context()
    finally:
        if event.contains(engine.sync_engine, "after_cursor_execute", damage_real_settings):
            event.remove(engine.sync_engine, "after_cursor_execute", damage_real_settings)
        await engine.dispose()
