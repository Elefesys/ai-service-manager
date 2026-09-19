"""Destructive migration lifecycle checks, restricted to the disposable TEST database."""

import asyncio
import os
import sys
from uuid import uuid4

import pytest
from asm.foundation import RuntimeDatabase, Settings, create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def migrate(*arguments):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 0, output.decode()


async def test_fresh_m0_idempotent_downgrade_reupgrade_and_readiness():
    settings = Settings()
    migration_url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert settings.environment == "TEST"
    assert make_url(settings.database_url.get_secret_value()).database == "asm_test"
    assert make_url(migration_url).database == "asm_test"
    assert make_url(migration_url).username == "asm_migrator"
    runtime = RuntimeDatabase(settings)
    migrator = create_async_engine(migration_url, hide_parameters=True)
    identifier = uuid4()
    try:
        await migrate("downgrade", "base")
        await migrate("upgrade", "head")
        await runtime.check()
        await migrate("downgrade", "base")
        await migrate("upgrade", "0001")
        async with migrator.connect() as connection:
            assert (
                await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one() == "0001"
            assert (
                await connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname IN ('app','platform')")
                )
            ).scalars().all() == ["alembic_version"]
        with pytest.raises(RuntimeError, match="capability/schema mismatch"):
            await runtime.check()
        await migrate("upgrade", "head")
        async with migrator.begin() as connection:
            await connection.execute(
                text("INSERT INTO platform.workspaces(id) VALUES (:id)"), {"id": identifier}
            )
        await migrate("upgrade", "head")
        async with migrator.connect() as connection:
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM platform.workspaces WHERE id=:id"),
                    {"id": identifier},
                )
            ).scalar_one() == 1
        await migrate("downgrade", "0001")
        await migrate("upgrade", "head")
        await runtime.check()
        application = create_app(settings)
        async with application.router.lifespan_context(application):
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://test"
            ) as client:
                response = await client.get("/health/ready")
                assert response.status_code == 200
        async with migrator.connect() as connection:
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM platform.workspaces WHERE id=:id"),
                    {"id": identifier},
                )
            ).scalar_one() == 0
            assert (
                await connection.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname='vector'")
                )
            ).scalar_one() == "0.8.6"
            assert (
                await connection.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname='btree_gist'")
                )
            ).scalar_one() == "1.8"
    finally:
        # A failed assertion must not leave later M0 regression tests on an old head.
        await migrate("upgrade", "head")
        await runtime.close()
        await migrator.dispose()
