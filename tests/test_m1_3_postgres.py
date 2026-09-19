"""Real PostgreSQL evidence for the M1.3 DB-only contract."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def migrator():
    url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert make_url(url).database == "asm_test"
    engine = create_async_engine(url, hide_parameters=True)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_m1_3_inventory_extension_rls_and_privileges(migrator):
    async with migrator.connect() as connection:
        extension = (
            await connection.execute(
                text(
                    "SELECT e.extversion,n.nspname FROM pg_extension e "
                    "JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='btree_gist'"
                )
            )
        ).one()
        assert extension == ("1.8", "extensions")
        tables = (
            (
                await connection.execute(
                    text(
                        "SELECT schemaname||'.'||tablename FROM pg_tables WHERE "
                        "(schemaname,tablename) IN (( 'platform','saas_plans'),"
                        "('platform','saas_plan_revisions'),('platform','plan_entitlements'),"
                        "('platform','workspace_billing_accounts'),"
                        "('platform','workspace_subscriptions'),"
                        "('platform','workspace_service_modes'),('app','audit_events'),"
                        "('platform','billing_contact_command_receipts')) ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) == 8
        rls = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE c.relname IN ('workspace_billing_accounts','workspace_subscriptions',"
                    "'workspace_service_modes','audit_events','billing_contact_command_receipts') "
                    "AND c.relrowsecurity AND c.relforcerowsecurity"
                )
            )
        ).scalar_one()
        assert rls == 5
        assert not (
            await connection.execute(
                text(
                    "SELECT has_database_privilege('asm_migrator',current_database(),'CREATE') "
                    "OR has_schema_privilege('asm_migrator','extensions','CREATE')"
                )
            )
        ).scalar_one()


async def test_initializer_manifest_overlap_adjacency_and_replay(migrator):
    first, second = uuid4(), uuid4()
    async with migrator.begin() as connection:
        await connection.execute(
            text("INSERT INTO platform.workspaces(id) VALUES (:a),(:b)"),
            {"a": first, "b": second},
        )
        call = text(
            "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name',"
            "'ACTIVE','COMPED','2026-09-01T00:00:00Z','2026-10-01T00:00:00Z','NORMAL')"
        )
        assert (await connection.execute(call, {"ws": first})).scalar_one() == "INITIALIZED"
        assert (await connection.execute(call, {"ws": first})).scalar_one() == "NOOP"
        assert (await connection.execute(call, {"ws": second})).scalar_one() == "INITIALIZED"
        assert (
            await connection.execute(text("SELECT count(*) FROM platform.saas_plans"))
        ).scalar_one() == 1
        assert (
            await connection.execute(text("SELECT count(*) FROM platform.plan_entitlements"))
        ).scalar_one() == 5
        revision = (
            await connection.execute(
                text(
                    "SELECT plan_revision_id FROM platform.saas_plan_revisions "
                    "WHERE publication_state='SEALED'"
                )
            )
        ).scalar_one()
        # Half-open adjacency is legal.
        await connection.execute(
            text(
                "INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,"
                "required_publication_state,status,funding_mode,effective_from,effective_until) "
                "VALUES(:ws,:revision,'SEALED','ACTIVE','COMPED',"
                "'2026-10-01T00:00:00Z','2026-11-01T00:00:00Z')"
            ),
            {"ws": first, "revision": revision},
        )
    with pytest.raises(DBAPIError) as caught:
        async with migrator.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_subscriptions(workspace_id,plan_revision_id,"
                    "required_publication_state,status,funding_mode,effective_from,effective_until) "
                    "VALUES(:ws,:revision,'SEALED','ACTIVE','COMPED',"
                    "'2026-09-15T00:00:00Z','2026-09-20T00:00:00Z')"
                ),
                {"ws": first, "revision": revision},
            )
    assert caught.value.orig.sqlstate == "23P01"
