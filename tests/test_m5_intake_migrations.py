"""Frozen 0022 predecessor, narrow 0023 catalog, and real reversible DDL."""

import copy
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from test_m5_portfolio_migrations import APPLIED
from test_tenancy_postgres import db as db

from scripts.native_context_db_catalog import Refusal, compare_embedded_profile, source_catalog


def migration():
    spec = importlib.util.spec_from_file_location(
        "intake0023", "migrations/versions/0023_intake_duration.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_predecessors_frozen_and_exact_0023_slot():
    module = migration()
    assert (module.revision, module.down_revision) == ("0023", "0022")
    frozen = APPLIED | {
        "migrations/versions/0021_vision_portfolio.py": "3a161cf82eba873bd6edb11f11c4f63fecb6bd7aef03027449943339bdd6e8f7",
        "migrations/versions/0022_portfolio_delivery.py": "054a734a85ca3ec301dd770c5d86a41597fc138ba57e307b380bfaa84136dcc2",
    }
    assert len(frozen) == 22
    for path, digest in frozen.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    previous = source_catalog(Path.cwd(), "0022")
    assert set(module.ORIGINAL) == set(module.REPLACEMENTS)
    for signature, definition in module.ORIGINAL.items():
        assert definition == previous["functions"][signature]["definition"]


def test_independently_expanded_catalog_and_only_new_owner_capability():
    before, after = (source_catalog(Path.cwd(), rev) for rev in ("0022", "0023"))
    assert (len(after["functions"]), len(after["columns"])) == (318, 73)
    assert compare_embedded_profile(after) == {
        "other_functions": 317,
        "tables": 73,
        "result": "PASS",
    }
    for name, row in before["functions"].items():
        if name.endswith("schema_profile()"):
            assert after["functions"][name] == row
    new = set(after["functions"]) - set(before["functions"])
    assert {s for s in new if after["functions"][s]["runtime_execute"]} == {
        "platform.intake_owner(uuid,uuid,text,text,jsonb)"
    }
    assert set(after["columns"]) - set(before["columns"]) == {
        "platform.intake_state",
        "platform.duration_cases",
        "platform.intake_receipts",
        "platform.intake_escalation_links",
    }


@pytest.mark.parametrize("damage", ["body_sha256", "language", "runtime_execute"])
def test_profile_detects_drift_in_new_private_helper(damage):
    catalog = copy.deepcopy(source_catalog(Path.cwd(), "0023"))
    row = catalog["functions"]["platform.intake_apply(platform.ai_runs,jsonb)"]
    row[damage] = {"body_sha256": "f" * 64, "language": "sql", "runtime_execute": True}[damage]
    with pytest.raises(Refusal, match="EMBEDDED_FUNCTION_MISMATCH"):
        compare_embedded_profile(catalog)


def test_all_sql_compiles_and_used_guard_precedes_mutation():
    module, statements = migration(), []
    module.op = SimpleNamespace(execute=statements.append)
    module.upgrade()
    for statement in statements:
        assert text(statement).compile(dialect=postgresql.dialect()).params == {}
    statements.clear()
    module.downgrade()
    assert statements[0].startswith("LOCK TABLE")
    assert "INTAKE_DURABLE_DATA" in statements[1]
    assert all(
        name in statements[1]
        for name in (
            "intake_state",
            "duration_cases",
            "intake_receipts",
            "intake_escalation_links",
            "conversation_v7",
            "intake_pin",
            "SYNTHETIC_INTAKE_V1",
        )
    )
    assert not any(s.startswith(("DELETE ", "UPDATE ")) for s in statements)
    first_drop = next(i for i, s in enumerate(statements) if s.startswith("DROP "))
    assert all(
        sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1) in statements[:first_drop]
        for sql in module.ORIGINAL.values()
    )


def execute_migration(connection, direction):
    module = migration()
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, direction)()
    # Alembic normally updates its version row after the revision operation.
    # This rollback-only carrier executes the same step on the same connection.
    connection.execute(
        text("UPDATE platform.alembic_version SET version_num=:revision"),
        {"revision": "0022" if direction == "downgrade" else "0023"},
    )


def downgrade_to_intake_schema(connection):
    from test_m5_intake_v7_repair_migrations import execute_repair

    scripts = ScriptDirectory("migrations")
    for revision, predecessor in (("0027", "0026"), ("0026", "0025"), ("0025", "0024")):
        script = scripts.get_revision(revision)
        with Operations.context(MigrationContext.configure(connection)):
            script.module.downgrade()
        connection.execute(
            text("UPDATE platform.alembic_version SET version_num=:revision"),
            {"revision": predecessor},
        )
    execute_repair(connection, "downgrade")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_actual_unused_downgrade_reupgrade_keeps_exact_catalog_and_legacy_nulls(db):
    _, migrator = db
    async with migrator.connect() as c:
        transaction = await c.begin()
        try:
            await c.run_sync(downgrade_to_intake_schema)
            before = (await c.execute(text("SELECT platform.intake_schema_profile()"))).scalar_one()
            assert before["valid"] is True
            await c.run_sync(execute_migration, "downgrade")
            assert (
                await c.execute(
                    text("SELECT to_regprocedure('platform.intake_schema_profile()') IS NULL")
                )
            ).scalar_one()
            assert (
                await c.execute(text("SELECT platform.portfolio_delivery_schema_profile()"))
            ).scalar_one()["valid"] is True
            await c.run_sync(execute_migration, "upgrade")
            assert (
                await c.execute(text("SELECT platform.intake_schema_profile()"))
            ).scalar_one() == before
            assert (
                await c.execute(
                    text(
                        "SELECT count(*) FROM platform.ai_runs WHERE config->>'prompt_revision'<>'conversation_v7' AND intake_pin IS NOT NULL"
                    )
                )
            ).scalar_one() == 0
        finally:
            await transaction.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_used_downgrade_refuses_before_any_schema_change(db):
    _, migrator = db
    # A real durable synthetic session is enough to make downgrade unsafe. All
    # fixture rows are transactional and cannot affect another test's database.
    async with migrator.connect() as c:
        outer = await c.begin()
        try:
            await c.run_sync(downgrade_to_intake_schema)
            # Existing constraints are deliberately exercised through the owner
            # DurationCase capability in API tests; here inspect the DDL guard by
            # inserting a minimal complete typed owner receipt in a savepoint.
            await c.execute(
                text(
                    "INSERT INTO platform.user_accounts(id) VALUES ('00000000-0000-0000-0000-000000000901')"
                )
            )
            await c.execute(
                text(
                    "INSERT INTO platform.workspaces(id) VALUES ('00000000-0000-0000-0000-000000000902')"
                )
            )
            await c.execute(
                text(
                    "INSERT INTO app.businesses(workspace_id,id,name) VALUES ('00000000-0000-0000-0000-000000000902','00000000-0000-0000-0000-000000000903','Synthetic migration guard')"
                )
            )
            await c.execute(
                text(
                    "INSERT INTO platform.intake_receipts(workspace_id,business_id,actor_id,command_key,request_hash,result,payload) VALUES ('00000000-0000-0000-0000-000000000902','00000000-0000-0000-0000-000000000903','00000000-0000-0000-0000-000000000901','guard',repeat('a',64),'{}','{}')"
                )
            )
            before = (await c.execute(text("SELECT platform.intake_schema_profile()"))).scalar_one()
            with pytest.raises(DBAPIError, match="INTAKE_DURABLE_DATA"):
                async with c.begin_nested():
                    await c.run_sync(execute_migration, "downgrade")
            assert (
                await c.execute(text("SELECT platform.intake_schema_profile()"))
            ).scalar_one() == before
            assert (
                await c.execute(text("SELECT count(*) FROM platform.intake_receipts"))
            ).scalar_one() == 1
        finally:
            await outer.rollback()


def test_existing_text_session_admission_only_advances_current_readiness_verifier():
    module = migration()
    signature = "platform.ai_provider_session(jsonb,boolean)"
    old = source_catalog(Path.cwd(), "0022")["functions"][signature]["definition"]
    assert module.ORIGINAL[signature] == old
    assert module.REPLACEMENTS[signature] == old.replace(
        "platform.portfolio_delivery_schema_profile()", "platform.intake_schema_profile()"
    )
    assert "conversation_v7" not in module.REPLACEMENTS[signature]
    assert (
        "(('SYNTHETIC_TEXT_V1','conversation_v2'),('SYNTHETIC_PUBLISHED_KNOWLEDGE_V1','conversation_v3'))"
        in old
    )
