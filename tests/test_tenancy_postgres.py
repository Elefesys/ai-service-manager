"""Real PostgreSQL 18 tests. No SQLite, connection doubles or production data."""

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.foundation import RuntimeDatabase, Settings
from asm.tenancy import (
    AuthenticatedAccount,
    Permission,
    TenancyError,
    current_workspace_context,
)
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
TABLES = ("businesses", "business_members", "locations")
A, B, UA, UB, PROVIDER = (UUID(int=n) for n in range(1001, 1006))
BA, BB, BA2, MEMBER_A, MEMBER_B, LA, LB = (UUID(int=n) for n in range(2001, 2008))


@pytest_asyncio.fixture
async def db():
    settings = Settings()
    migration_url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert settings.environment == "TEST"
    assert make_url(settings.database_url.get_secret_value()).database == "asm_test"
    assert make_url(migration_url).database == "asm_test"
    runtime = RuntimeDatabase(settings, pool_size=2)
    migrator = create_async_engine(migration_url, hide_parameters=True)
    await runtime.check()
    try:
        yield runtime, migrator
    finally:
        await runtime.close()
        await migrator.dispose()


@pytest_asyncio.fixture
async def seeded(db):
    runtime, migrator = db
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.user_accounts (id) VALUES (:id)"),
            [{"id": value} for value in (UA, UB, PROVIDER)],
        )
        await connection.execute(
            text("INSERT INTO platform.workspaces (id) VALUES (:id)"),
            [{"id": value} for value in (A, B)],
        )
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_memberships "
                "(workspace_id, user_account_id, role) VALUES (:ws, :user, :role)"
            ),
            [
                {"ws": A, "user": UA, "role": "OWNER"},
                {"ws": B, "user": UB, "role": "ADMIN"},
                {"ws": A, "user": PROVIDER, "role": "PROVIDER"},
            ],
        )
        await connection.execute(
            text("INSERT INTO app.businesses (workspace_id, id, name) VALUES (:ws, :id, :name)"),
            [
                {"ws": A, "id": BA, "name": "A"},
                {"ws": A, "id": BA2, "name": "A2"},
                {"ws": B, "id": BB, "name": "B"},
            ],
        )
        await connection.execute(
            text(
                "INSERT INTO app.business_members "
                "(workspace_id, id, business_id, user_account_id, name, role) "
                "VALUES (:ws, :id, :business, :user, :name, 'PROVIDER')"
            ),
            [
                {"ws": A, "id": MEMBER_A, "business": BA, "user": None, "name": "A"},
                {"ws": B, "id": MEMBER_B, "business": BB, "user": UB, "name": "B"},
            ],
        )
        await connection.execute(
            text(
                "INSERT INTO app.locations (workspace_id, id, business_id, name) "
                "VALUES (:ws, :id, :business, :name)"
            ),
            [
                {"ws": A, "id": LA, "business": BA, "name": "A"},
                {"ws": B, "id": LB, "business": BB, "name": "B"},
            ],
        )
    try:
        yield runtime, migrator
    finally:
        async with migrator.begin() as connection:
            for table in ("locations", "business_members", "businesses"):
                await connection.execute(
                    text(f"DELETE FROM app.{table} WHERE workspace_id IN (:a, :b)"),
                    {"a": A, "b": B},
                )
            await connection.execute(
                text("DELETE FROM platform.workspace_memberships WHERE workspace_id IN (:a, :b)"),
                {"a": A, "b": B},
            )
            await connection.execute(
                text("DELETE FROM platform.workspaces WHERE id IN (:a, :b)"), {"a": A, "b": B}
            )
            await connection.execute(
                text("DELETE FROM platform.user_accounts WHERE id IN (:a, :b, :p)"),
                {"a": UA, "b": UB, "p": PROVIDER},
            )


async def raw_context(connection, workspace=A, actor=UA):
    # Explicitly test DML at the actual runtime SQL boundary, independently of UoW queries.
    assert (await connection.execute(text("SELECT current_user"))).scalar_one() == "asm_runtime"
    await connection.execute(
        text("""
            SELECT set_config('asm.workspace_id', :workspace, true),
                   set_config('asm.actor_id', :actor, true),
                   set_config('asm.actor_kind', 'user_account', true),
                   set_config('asm.correlation_id', :correlation, true),
                   set_config('asm.context_xid', pg_current_xact_id()::text, true)
        """),
        {"workspace": str(workspace), "actor": str(actor), "correlation": str(uuid4())},
    )


def insert_statement(table):
    if table == "businesses":
        return "INSERT INTO app.businesses (workspace_id, id, name) VALUES (:ws, :id, 'new')"
    extra = ", role" if table == "business_members" else ""
    value = ", 'PROVIDER'" if table == "business_members" else ""
    return (
        f"INSERT INTO app.{table} (workspace_id, id, business_id, name{extra}) "
        f"VALUES (:ws, :id, :business, 'new'{value})"
    )


@pytest.mark.parametrize("table", TABLES)
async def test_raw_crud_positive_and_cross_workspace_denial(seeded, table):
    runtime, _ = seeded
    # Both directions, including unfiltered statements: RLS, not WHERE alone.
    for ws, actor, business in ((A, UA, BA), (B, UB, BB)):
        other = B if ws == A else A
        async with runtime.engine.begin() as connection:
            await raw_context(connection, ws, actor)
            rows = (
                (await connection.execute(text(f"SELECT workspace_id FROM app.{table}")))
                .scalars()
                .all()
            )
            assert rows and set(rows) == {ws}
            for verb in (f"UPDATE app.{table} SET name = 'forged'", f"DELETE FROM app.{table}"):
                result = await connection.execute(
                    text(verb + " WHERE workspace_id = :other"), {"other": other}
                )
                assert result.rowcount == 0
            identifier = uuid4()
            await connection.execute(
                text(insert_statement(table)), {"ws": ws, "id": identifier, "business": business}
            )
            result = await connection.execute(
                text(f"UPDATE app.{table} SET name = 'updated' WHERE id = :id RETURNING name"),
                {"id": identifier},
            )
            assert result.scalar_one() == "updated"
            result = await connection.execute(
                text(f"DELETE FROM app.{table} WHERE id = :id"), {"id": identifier}
            )
            assert result.rowcount == 1
        for sql, params in (
            (insert_statement(table), {"ws": other, "id": uuid4(), "business": business}),
            (f"UPDATE app.{table} SET workspace_id = :ws", {"ws": other}),
        ):
            with pytest.raises(DBAPIError) as caught:
                async with runtime.engine.begin() as connection:
                    await raw_context(connection, ws, actor)
                    await connection.execute(text(sql), params)
            assert caught.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize(
    "bad", [None, "workspace", "actor", "kind", "correlation", "xid", "outsider"]
)
async def test_missing_and_malformed_context_fail_closed(seeded, table, bad):
    runtime, _ = seeded
    async with runtime.engine.begin() as connection:
        if bad is not None:
            await raw_context(connection)
            key, value = {
                "workspace": ("asm.workspace_id", "invalid-uuid"),
                "actor": ("asm.actor_id", "invalid-uuid"),
                "kind": ("asm.actor_kind", "ai"),
                "correlation": ("asm.correlation_id", "invalid-uuid"),
                "xid": ("asm.context_xid", "0"),
                "outsider": ("asm.actor_id", str(UB)),
            }[bad]
            await connection.execute(
                text("SELECT set_config(:key, :value, true)"), {"key": key, "value": value}
            )
        assert (await connection.execute(text(f"SELECT * FROM app.{table}"))).all() == []
        assert (await connection.execute(text(f"UPDATE app.{table} SET name='bad'"))).rowcount == 0
        assert (await connection.execute(text(f"DELETE FROM app.{table}"))).rowcount == 0
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(
                    text(insert_statement(table)), {"ws": A, "id": uuid4(), "business": BA}
                )
        assert caught.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("table", ["business_members", "locations"])
async def test_composite_business_fk_blocks_cross_tenant_and_workspace_business_confusion(
    seeded, table
):
    runtime, _ = seeded
    for forged_business in (BB, A, uuid4()):
        with pytest.raises(DBAPIError) as caught:
            async with runtime.engine.begin() as connection:
                await raw_context(connection)
                await connection.execute(
                    text(insert_statement(table)),
                    {"ws": A, "id": uuid4(), "business": forged_business},
                )
        assert caught.value.orig.sqlstate == "23503"
    with pytest.raises(DBAPIError) as caught:
        async with runtime.engine.begin() as connection:
            await raw_context(connection)
            await connection.execute(
                text(f"UPDATE app.{table} SET business_id = :foreign"), {"foreign": BB}
            )
    assert caught.value.orig.sqlstate == "23503"


async def test_optional_account_requires_same_workspace_membership_and_unique_link(seeded):
    runtime, _ = seeded
    async with runtime.engine.begin() as connection:
        await raw_context(connection)
        assert (
            await connection.execute(text("SELECT user_account_id FROM app.business_members"))
        ).scalar_one() is None
        for account in (UB, uuid4()):
            with pytest.raises(DBAPIError) as caught:
                async with connection.begin_nested():
                    await connection.execute(
                        text("UPDATE app.business_members SET user_account_id = :account"),
                        {"account": account},
                    )
            assert caught.value.orig.sqlstate == "23503"
        await connection.execute(
            text("UPDATE app.business_members SET user_account_id = :account"), {"account": UA}
        )
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO app.business_members (workspace_id,business_id,user_account_id,name,role) "
                        "VALUES (:ws,:business,:account,'duplicate','OWNER')"
                    ),
                    {"ws": A, "business": BA, "account": UA},
                )
        assert caught.value.orig.sqlstate == "23505"


async def test_forged_ids_and_same_workspace_wrong_business_are_not_found(seeded):
    runtime, _ = seeded
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert (await unit.get_business(BA))["workspace_id"] == A
        assert (await unit.get_business_member(BA, MEMBER_A))["user_account_id"] is None
        assert (await unit.get_location(BA, LA))["business_id"] == BA
        for call in (
            unit.get_business(BB),
            unit.get_business(A),
            unit.get_business(uuid4()),
            unit.get_location(BA, LB),
            unit.get_location(BA2, LA),
            unit.get_business_member(BA2, MEMBER_A),
            unit.get_business_member(BA, MEMBER_B),
            unit.rename_business(BB, "forged", 1),
        ):
            with pytest.raises(TenancyError, match="NOT_FOUND"):
                await call


async def test_membership_factory_rejects_forged_inactive_or_privileged_actor(seeded):
    runtime, migrator = seeded
    for actor, workspace in ((UA, B), (UB, A), (uuid4(), A), (UA, uuid4())):
        with pytest.raises(TenancyError, match="ACCESS_DENIED"):
            async with runtime.tenancy.transaction(AuthenticatedAccount(actor), workspace, uuid4()):
                pytest.fail("untrusted selector was accepted")
    with pytest.raises(TenancyError, match="CONTEXT_INVALID"):
        async with runtime.tenancy.transaction(
            {"kind": "ai", "permissions": ["OWNER"]}, A, uuid4()
        ):
            pytest.fail("AI cannot construct an Owner context")
    for table, column, value, status in (
        ("user_accounts", "id", UA, "DISABLED"),
        ("workspaces", "id", A, "ARCHIVED"),
        ("workspace_memberships", "user_account_id", UA, "REVOKED"),
    ):
        async with migrator.begin() as connection:
            await connection.execute(
                text(f"UPDATE platform.{table} SET status=:status WHERE {column}=:id"),
                {"status": status, "id": value},
            )
        with pytest.raises(TenancyError, match="ACCESS_DENIED"):
            async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()):
                pytest.fail("inactive identity was accepted")
        async with runtime.engine.begin() as connection:
            await raw_context(connection)
            assert (await connection.execute(text("SELECT * FROM app.businesses"))).all() == []
        async with migrator.begin() as connection:
            await connection.execute(
                text(f"UPDATE platform.{table} SET status='ACTIVE' WHERE {column}=:id"),
                {"id": value},
            )


async def test_permission_boundary_and_cas_are_not_replaced_by_rls(seeded):
    runtime, _ = seeded
    async with runtime.tenancy.transaction(AuthenticatedAccount(PROVIDER), A, uuid4()) as unit:
        assert unit.context.permissions == {Permission.READ}
        assert (await unit.get_business(BA))["name"] == "A"
        with pytest.raises(TenancyError, match="ACCESS_DENIED"):
            await unit.rename_business(BA, "forbidden", 1)
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        row = await unit.rename_business(BA, "renamed", 1)
        assert row["version"] == 2
        with pytest.raises(TenancyError, match="STALE_STATE"):
            await unit.rename_business(BA, "stale", 1)
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert (await unit.get_business(BA))["name"] == "renamed"


async def test_commit_rollback_same_physical_connection_and_stale_session_fence(seeded):
    _, _ = seeded
    runtime = RuntimeDatabase(Settings(), pool_size=1)
    try:
        async with runtime.engine.begin() as connection:
            pid = (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        for rollback in (False, True):
            try:
                async with runtime.tenancy.transaction(
                    AuthenticatedAccount(UA), A, uuid4()
                ) as unit:
                    assert current_workspace_context() == unit.context
                    await unit.rename_business(
                        BA, "rolled" if rollback else "committed", 2 if rollback else 1
                    )
                    if rollback:
                        raise RuntimeError("rollback")
            except RuntimeError as error:
                assert rollback and str(error) == "rollback"
            with pytest.raises(TenancyError, match="CONTEXT_REQUIRED"):
                current_workspace_context()
            with pytest.raises(TenancyError, match="TRANSACTION_STATE"):
                await unit.get_business(BA)
            async with runtime.engine.begin() as connection:
                assert (
                    await connection.execute(text("SELECT pg_backend_pid()"))
                ).scalar_one() == pid
                for name in (
                    "workspace_id",
                    "actor_id",
                    "actor_kind",
                    "correlation_id",
                    "context_xid",
                ):
                    assert (
                        await connection.execute(
                            text("SELECT NULLIF(current_setting(:key,true),'')"),
                            {"key": "asm." + name},
                        )
                    ).scalar_one() is None
                assert (await connection.execute(text("SELECT * FROM app.businesses"))).all() == []
        async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            assert (await unit.get_business(BA))["name"] == "committed"
        async with runtime.tenancy.transaction(AuthenticatedAccount(UB), B, uuid4()) as unit:
            assert [row["id"] for row in await unit.list_businesses()] == [BB]
        # Deliberately pollute a session as an adversarial test, never as application setup.
        async with runtime.engine.begin() as connection:
            await raw_context(connection)
            for key in ("workspace_id", "actor_id", "actor_kind", "correlation_id", "context_xid"):
                name = "asm." + key
                await connection.execute(
                    text("SELECT set_config(:key,current_setting(:key),false)"), {"key": name}
                )
        async with runtime.engine.begin() as connection:
            assert (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one() == pid
            await connection.execute(text("SELECT pg_current_xact_id()"))
            assert (await connection.execute(text("SELECT * FROM app.businesses"))).all() == []
    finally:
        await runtime.close()


async def test_concurrent_async_contexts_and_reuse_are_task_safe(seeded):
    runtime, _ = seeded
    barrier = asyncio.Barrier(2)

    async def operation(ws, actor, expected):
        async with runtime.tenancy.transaction(AuthenticatedAccount(actor), ws, uuid4()) as unit:
            await asyncio.wait_for(barrier.wait(), 3)
            assert current_workspace_context().workspace_id == ws
            assert {row["id"] for row in await unit.list_businesses()} == expected
            with pytest.raises(TenancyError, match="TRANSACTION_STATE"):
                await asyncio.create_task(unit.get_business(next(iter(expected))))
            with pytest.raises(TenancyError, match="TRANSACTION_STATE"):
                async with runtime.tenancy.transaction(AuthenticatedAccount(actor), ws, uuid4()):
                    pytest.fail("nested context")
        with pytest.raises(TenancyError, match="CONTEXT_REQUIRED"):
            current_workspace_context()

    await asyncio.gather(operation(A, UA, {BA, BA2}), operation(B, UB, {BB}))


async def test_cancellation_rolls_back_and_releases_pooled_connection(seeded):
    runtime, _ = seeded
    started = asyncio.Event()

    async def operation():
        async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            await unit.rename_business(BA, "cancelled", 1)
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(operation())
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert (await unit.get_business(BA))["name"] == "A"


async def test_runtime_roles_policies_functions_and_platform_surface(db):
    runtime, migrator = db
    async with runtime.engine.begin() as connection:
        role = (
            (await connection.execute(text("SELECT * FROM pg_roles WHERE rolname=current_user")))
            .mappings()
            .one()
        )
        assert role["rolname"] == "asm_runtime"
        assert not any(
            role[key]
            for key in (
                "rolsuper",
                "rolbypassrls",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
                "rolinherit",
            )
        )
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)"
                )
            )
        ).scalar_one() == 0
        tables = (
            (
                await connection.execute(
                    text(
                        "SELECT tablename, tableowner, rowsecurity FROM pg_tables WHERE schemaname='app'"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert {row["tablename"] for row in tables} == set(TABLES) | {
            "audit_events",
            "channel_connections",
            "clients",
            "client_identities",
            "conversations",
            "messages",
            "outbox_events",
        }
        assert all(row["tableowner"] == "asm_migrator" and row["rowsecurity"] for row in tables)
        for table in TABLES:
            assert (
                await connection.execute(
                    text(
                        "SELECT relforcerowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)"
                    ),
                    {"name": "app." + table},
                )
            ).scalar_one()
            policies = (
                (
                    await connection.execute(
                        text(
                            "SELECT roles, qual, with_check FROM pg_policies WHERE schemaname='app' AND tablename=:table"
                        ),
                        {"table": table},
                    )
                )
                .mappings()
                .all()
            )
            assert {tuple(row["roles"]) for row in policies} == {
                ("asm_runtime",),
                ("asm_migrator",),
            }
            assert all(row["qual"] and row["with_check"] for row in policies)
    denied = [
        "CREATE TABLE app.forbidden(id integer)",
        "CREATE TABLE platform.forbidden(id integer)",
        "CREATE TABLE public.forbidden(id integer)",
        "CREATE TEMP TABLE forbidden(id integer)",
        "CREATE SCHEMA forbidden",
        "CREATE ROLE forbidden",
        "ALTER ROLE asm_runtime BYPASSRLS",
        "ALTER TABLE app.businesses DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE app.businesses OWNER TO asm_runtime",
        "TRUNCATE app.businesses",
        "DROP POLICY workspace_isolation ON app.businesses",
        "SET ROLE asm_migrator",
        "SET ROLE asm_admin",
        "SET SESSION AUTHORIZATION asm_admin",
        "GRANT asm_migrator TO asm_runtime",
        "CREATE OR REPLACE FUNCTION app.current_workspace_id() RETURNS uuid LANGUAGE sql AS 'SELECT NULL::uuid'",
    ]
    for table in ("user_accounts", "workspaces", "workspace_memberships"):
        denied += [
            f"SELECT * FROM platform.{table}",
            f"DELETE FROM platform.{table}",
            f"UPDATE platform.{table} SET status='ACTIVE'",
            f"INSERT INTO platform.{table} DEFAULT VALUES",
        ]
    for sql in denied:
        with pytest.raises(DBAPIError) as caught:
            async with runtime.engine.begin() as connection:
                await connection.execute(text(sql))
        assert caught.value.orig.sqlstate == "42501", sql
    async with migrator.begin() as connection:
        functions = (
            (
                await connection.execute(
                    text("""
            SELECT p.proname, p.prosecdef, p.proconfig, r.rolname,
                   EXISTS(SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS public_execute,
                   has_function_privilege('asm_runtime', p.oid, 'EXECUTE') AS runtime_execute
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            JOIN pg_roles r ON r.oid=p.proowner
            WHERE n.nspname IN ('app','platform')
        """)
                )
            )
            .mappings()
            .all()
        )
        legacy_functions = {
            "current_workspace_id",
            "resolve_workspace_membership",
            "auth_lock_session",
            "auth_password_lookup",
            "auth_bootstrap",
            "auth_session",
            "auth_memberships",
            "auth_login",
            "auth_rotate",
            "auth_logout",
        }
        m1_3_profiles = {
            "guard_plan_revision": (False, False),
            "guard_entitlement": (False, False),
            "initialize_local_billing": (True, False),
            "update_billing_contact": (True, True),
        }
        # M2.1 adds typed messaging capabilities; M1 guard profiles stay frozen.
        m2_profiles = {
            name: (True, True)
            for name in (
                "current_messaging_owner_workspace_id",
                "messaging_ingest",
                "messaging_claim",
                "messaging_admit",
                "messaging_process_inbox",
                "messaging_request_text",
                "messaging_begin_send",
                "messaging_finish_send",
                "messaging_retry",
                "messaging_recover_expired",
                "messaging_read_conversations",
                "messaging_read_messages",
                "messaging_read_delivery",
                "messaging_read_inbox",
            )
        }
        m2_profiles.update(
            {
                name: (False, False)
                for name in (
                    "messaging_valid_id",
                    "messaging_validate_event",
                    "messaging_fingerprint",
                    "messaging_immutable",
                    "messaging_job_json",
                )
            }
        )
        m2_profiles.update(
            {
                name: (True, False)
                for name in (
                    "messaging_guard",
                    "messaging_reschedule",
                    "messaging_lock_owner",
                )
            }
        )
        assert {row["proname"] for row in functions} == legacy_functions | set(m1_3_profiles) | set(
            m2_profiles
        )
        m1_3_profiles.update(m2_profiles)
        legacy_rows = [row for row in functions if row["proname"] in legacy_functions]
        assert all(
            row["prosecdef"] and row["rolname"] == "asm_migrator" and not row["public_execute"]
            for row in legacy_rows
        )
        for row in (row for row in functions if row["proname"] in m1_3_profiles):
            security_definer, runtime_execute = m1_3_profiles[row["proname"]]
            assert row["prosecdef"] is security_definer
            assert row["runtime_execute"] is runtime_execute
            assert row["rolname"] == "asm_migrator"
            assert not row["public_execute"]
            assert row["proconfig"] == ["search_path=pg_catalog, pg_temp"]
        assert all(row["proconfig"] == ["search_path=pg_catalog, pg_temp"] for row in functions)


async def test_real_schema_matches_contract_and_constraints(db):
    _, migrator = db
    contract = json.loads(Path("contracts/tenancy.v1.json").read_text())
    async with migrator.connect() as connection:

        def verify(sync):
            inspector = inspect(sync)
            actual_fks = []
            for qualified, expected in contract["columns"].items():
                schema, table = qualified.split(".")
                columns = inspector.get_columns(table, schema=schema)
                assert [column["name"] for column in columns] == expected
                assert (
                    inspector.get_pk_constraint(table, schema=schema)["constrained_columns"]
                    == contract["primary_keys"][qualified]
                )
                assert [column["name"] for column in columns if column["nullable"]] == contract[
                    "nullable_columns"
                ].get(qualified, [])
                by_name = {column["name"]: column for column in columns}
                assert by_name["created_at"]["type"].timezone
                assert str(by_name["version"]["type"]) == "BIGINT"
                if "id" in by_name:
                    assert "uuidv7()" in by_name["id"]["default"]
                checks = inspector.get_check_constraints(table, schema=schema)
                assert any("version > 0" in check["sqltext"] for check in checks)
                if "role" in by_name:
                    for role in contract["permissions_by_role"]:
                        assert any(role in check["sqltext"] for check in checks)
                for status in contract["statuses"][qualified]:
                    assert any(status in check["sqltext"] for check in checks)
                for fk in inspector.get_foreign_keys(
                    table, schema=schema, postgresql_ignore_search_path=True
                ):
                    assert fk["options"].get("ondelete") == "RESTRICT"
                    actual_fks.append(
                        [
                            qualified,
                            fk["constrained_columns"],
                            fk["referred_schema"] + "." + fk["referred_table"],
                            fk["referred_columns"],
                        ]
                    )
            assert sorted(actual_fks, key=str) == sorted(contract["foreign_keys"], key=str)

        await connection.run_sync(verify)


async def test_concurrent_cas_has_exactly_one_winner(seeded):
    runtime, _ = seeded
    barrier = asyncio.Barrier(2)

    async def rename(name):
        try:
            async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
                await asyncio.wait_for(barrier.wait(), 3)
                await unit.rename_business(BA, name, 1)
                return "updated"
        except TenancyError as error:
            return error.code.value

    results = await asyncio.gather(rename("first"), rename("second"))
    assert sorted(results) == ["STALE_STATE", "updated"]
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert (await unit.get_business(BA))["version"] == 2


async def test_membership_revocation_is_serialized_with_active_transaction(seeded):
    runtime, migrator = seeded
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert (await unit.get_business(BA))["id"] == BA
        with pytest.raises(DBAPIError) as caught:
            async with migrator.begin() as connection:
                await connection.execute(text("SET LOCAL lock_timeout='100ms'"))
                await connection.execute(
                    text(
                        "UPDATE platform.workspace_memberships SET status='REVOKED' "
                        "WHERE workspace_id=:ws AND user_account_id=:actor"
                    ),
                    {"ws": A, "actor": UA},
                )
        assert caught.value.orig.sqlstate == "55P03"
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET status='REVOKED' "
                "WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            {"ws": A, "actor": UA},
        )
    with pytest.raises(TenancyError, match="ACCESS_DENIED"):
        async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()):
            pytest.fail("revoked membership")


async def test_suppressed_database_error_still_rolls_back_whole_unit(seeded):
    runtime, _ = seeded
    with pytest.raises(TenancyError, match="TRANSACTION_STATE"):
        async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            await unit.rename_business(BA, "must roll back", 1)
            with pytest.raises(TenancyError, match="INVALID_STATE"):
                # Deliberately probe the internal boundary: consumers never execute arbitrary SQL.
                await unit._execute("UPDATE app.businesses SET status='invalid'", {})
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        row = await unit.get_business(BA)
        assert row["version"] == 1 and row["name"] == "A"


async def test_duplicate_id_other_workspace_is_not_unique_constraint_oracle(seeded):
    runtime, migrator = seeded
    async with runtime.engine.begin() as connection:
        await raw_context(connection, B, UB)
        await connection.execute(
            text("INSERT INTO app.businesses(workspace_id,id,name) VALUES (:ws,:id,'B copy')"),
            {"ws": B, "id": BA},
        )
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert (await unit.get_business(BA))["name"] == "A"
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) "
                "VALUES (:ws,:actor,'PROVIDER')"
            ),
            {"ws": B, "actor": UA},
        )
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), B, uuid4()) as unit:
        assert (await unit.get_business(BA))["name"] == "B copy"
        assert unit.context.permissions == {Permission.READ}


async def test_row_security_off_does_not_bypass_rls(seeded):
    runtime, _ = seeded
    with pytest.raises(DBAPIError) as caught:
        async with runtime.engine.begin() as connection:
            await raw_context(connection)
            await connection.execute(text("SET LOCAL row_security=off"))
            await connection.execute(text("SELECT * FROM app.businesses"))
    assert caught.value.orig.sqlstate == "42501"
