"""Destructive M1.3 prerequisite/migration lifecycle evidence on disposable asm_test."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

TABLES = (
    "platform.saas_plans",
    "platform.saas_plan_revisions",
    "platform.plan_entitlements",
    "platform.workspace_billing_accounts",
    "platform.workspace_subscriptions",
    "platform.workspace_service_modes",
    "app.audit_events",
    "platform.billing_contact_command_receipts",
)


async def migrate(*arguments, succeeds=True):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), 30)
    assert (process.returncode == 0) is succeeds, output.decode()


def prerequisite_sql():
    source = Path("infra/postgres/ensure_m1_3_prerequisites.sh").read_text()
    return source.split("<<'SQL'\n", 1)[1].rsplit("\nSQL", 1)[0]


async def domain_tables(connection):
    return {
        name
        for name in TABLES
        if (await connection.execute(text("SELECT to_regclass(:name)"), {"name": name})).scalar()
    }


async def test_existing_0003_admin_prerequisite_repeat_downgrade_and_reupgrade():
    admin_url = os.environ["ASM_ADMIN_DATABASE_URL"]
    assert make_url(admin_url).database == "asm_test"
    admin = create_async_engine(admin_url, hide_parameters=True)
    try:
        await migrate("downgrade", "0003")
        async with admin.begin() as connection:
            await connection.execute(text("DROP EXTENSION btree_gist"))
            await connection.exec_driver_sql(prerequisite_sql())
            await connection.exec_driver_sql(prerequisite_sql())
        await migrate("upgrade", "0004")
        async with admin.connect() as connection:
            assert await domain_tables(connection) == set(TABLES)
        await migrate("downgrade", "0003")
        async with admin.connect() as connection:
            assert await domain_tables(connection) == set()
            assert (
                await connection.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname='btree_gist'")
                )
            ).scalar_one() == "1.8"
        await migrate("upgrade", "0004")
        async with admin.connect() as connection:
            assert await domain_tables(connection) == set(TABLES)
    finally:
        await migrate("upgrade", "head")
        await admin.dispose()


@pytest.mark.parametrize("damage", ["missing", "namespace", "version", "opclass"])
async def test_prerequisite_damage_fails_before_domain_ddl(damage):
    admin = create_async_engine(os.environ["ASM_ADMIN_DATABASE_URL"], hide_parameters=True)
    try:
        await migrate("downgrade", "0003")
        async with admin.begin() as connection:
            if damage == "missing":
                await connection.execute(text("DROP EXTENSION btree_gist"))
            elif damage == "namespace":
                await connection.execute(text("ALTER EXTENSION btree_gist SET SCHEMA public"))
            elif damage == "version":
                await connection.execute(
                    text(
                        "UPDATE pg_extension SET extversion='0.invalid' WHERE extname='btree_gist'"
                    )
                )
            else:
                await connection.execute(
                    text(
                        "ALTER OPERATOR CLASS extensions.gist_uuid_ops USING gist RENAME TO damaged_uuid_ops"
                    )
                )
        await migrate("upgrade", "0004", succeeds=False)
        async with admin.connect() as connection:
            assert await domain_tables(connection) == set()
    finally:
        async with admin.begin() as connection:
            await connection.execute(text("DROP EXTENSION IF EXISTS btree_gist CASCADE"))
            await connection.exec_driver_sql(prerequisite_sql())
        await migrate("upgrade", "head")
        await admin.dispose()
