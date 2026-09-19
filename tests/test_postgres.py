import asyncio
import json
import os
import sys
from uuid import UUID

import pytest
import pytest_asyncio
from asm.foundation import RuntimeDatabase, Settings
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
A = "018f0000-0000-7000-8000-00000000000a"
B = "018f0000-0000-7000-8000-00000000000b"


@pytest_asyncio.fixture
async def database():
    settings = Settings()
    assert settings.environment == "TEST", "Tests must never target LOCAL/production data"
    assert make_url(settings.database_url.get_secret_value()).database == "asm_test"
    migration_url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert make_url(migration_url).database == "asm_test"
    runtime = RuntimeDatabase(settings, pool_size=1)
    migrator = create_async_engine(migration_url, hide_parameters=True)
    await runtime.check()
    try:
        yield runtime, migrator
    finally:
        await runtime.close()
        await migrator.dispose()


@pytest_asyncio.fixture
async def probe(database):
    runtime, migrator = database
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE app._m0_probe (id integer PRIMARY KEY, workspace_id uuid NOT NULL, label text NOT NULL)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO app._m0_probe VALUES (1, CAST(:a AS uuid), 'A'), (2, CAST(:b AS uuid), 'B')"
            ),
            {"a": A, "b": B},
        )
        await connection.execute(text("ALTER TABLE app._m0_probe ENABLE ROW LEVEL SECURITY"))
        await connection.execute(text("ALTER TABLE app._m0_probe FORCE ROW LEVEL SECURITY"))
        await connection.execute(
            text(
                "CREATE POLICY isolated ON app._m0_probe USING (workspace_id = NULLIF(current_setting('asm.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('asm.workspace_id', true), '')::uuid)"
            )
        )
        await connection.execute(
            text("GRANT SELECT, INSERT, UPDATE, DELETE ON app._m0_probe TO asm_runtime")
        )
    try:
        yield runtime.engine
    finally:
        async with migrator.begin() as connection:
            await connection.execute(text("DROP TABLE app._m0_probe"))


async def context(connection, workspace):
    await connection.execute(
        text("SELECT set_config('asm.workspace_id', :workspace, true)"), {"workspace": workspace}
    )


async def test_real_postgres_capabilities_and_roles(database):
    runtime, migrator = database
    async with runtime.engine.begin() as connection:
        assert (await connection.execute(text("SELECT current_user"))).scalar_one() == "asm_runtime"
        assert (
            UUID(str((await connection.execute(text("SELECT uuidv7()"))).scalar_one())).version == 7
        )
        distance = (
            await connection.execute(
                text("SELECT '[1,0,0]'::extensions.vector <-> '[0,1,0]'::extensions.vector")
            )
        ).scalar_one()
        assert distance == pytest.approx(2**0.5)
        assert not (
            await connection.execute(
                text("SELECT has_database_privilege(current_user, current_database(), 'TEMP')")
            )
        ).scalar_one()
    async with migrator.begin() as connection:
        assert (
            await connection.execute(text("SELECT current_user"))
        ).scalar_one() == "asm_migrator"
        tables = (
            (
                await connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname IN ('app','platform') ORDER BY tablename"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert tables == [
            "alembic_version",
            "audit_events",
            "auth_credentials",
            "auth_sessions",
            "billing_contact_command_receipts",
            "business_members",
            "businesses",
            "locations",
            "plan_entitlements",
            "saas_plan_revisions",
            "saas_plans",
            "user_accounts",
            "workspace_billing_accounts",
            "workspace_memberships",
            "workspace_service_modes",
            "workspace_subscriptions",
            "workspaces",
        ], "Only the accepted M0 through M1.3 tables are allowed"


async def test_rls_no_context_and_cross_workspace_reads(probe):
    async with probe.begin() as connection:
        assert (await connection.execute(text("SELECT * FROM app._m0_probe"))).all() == []
        await context(connection, A)
        assert (
            await connection.execute(text("SELECT label FROM app._m0_probe"))
        ).scalars().all() == ["A"]
        result = await connection.execute(
            text("UPDATE app._m0_probe SET label='forbidden' WHERE id=2")
        )
        assert result.rowcount == 0
    async with probe.begin() as connection:
        await context(connection, B)
        assert (
            await connection.execute(text("SELECT label FROM app._m0_probe"))
        ).scalars().all() == ["B"]


async def test_rls_rejects_cross_workspace_insert(probe):
    with pytest.raises(DBAPIError) as caught:
        async with probe.begin() as connection:
            await context(connection, A)
            await connection.execute(
                text("INSERT INTO app._m0_probe VALUES (3, CAST(:workspace AS uuid), 'forbidden')"),
                {"workspace": B},
            )
    assert caught.value.orig.sqlstate == "42501"


async def test_transaction_rollback_and_pool_context_cleanup(probe):
    with pytest.raises(RuntimeError, match="rollback-probe"):
        async with probe.begin() as connection:
            pid = (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await context(connection, A)
            await connection.execute(text("UPDATE app._m0_probe SET label='changed' WHERE id=1"))
            raise RuntimeError("rollback-probe")
    async with probe.begin() as connection:
        assert (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one() == pid
        assert (
            await connection.execute(
                text("SELECT NULLIF(current_setting('asm.workspace_id',true),'') IS NULL")
            )
        ).scalar_one()
        assert (await connection.execute(text("SELECT * FROM app._m0_probe"))).all() == []
        await context(connection, A)
        assert (
            await connection.execute(text("SELECT label FROM app._m0_probe"))
        ).scalar_one() == "A"
    async with probe.begin() as connection:
        assert (await connection.execute(text("SELECT * FROM app._m0_probe"))).all() == []


async def test_runtime_cannot_create_tables_or_assume_migration_role(database):
    runtime, _ = database
    for statement in ("CREATE TABLE app.forbidden (id integer)", "SET ROLE asm_migrator"):
        with pytest.raises(DBAPIError) as caught:
            async with runtime.engine.begin() as connection:
                await connection.execute(text(statement))
        assert caught.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("role", ["worker", "scheduler"])
async def test_process_graceful_shutdown_with_real_database(database, role):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "asm.foundation",
        role,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        line = await asyncio.wait_for(process.stdout.readline(), 10)
        event = json.loads(line)
        assert event["event"] == "started"
        assert event["jobs_enabled"] is False
        process.terminate()
        out, err = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode == 0, err.decode()
        assert json.loads(out)["event"] == "stopped"
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
