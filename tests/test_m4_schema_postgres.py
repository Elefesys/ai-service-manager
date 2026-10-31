"""Current exact0015 catalog, retained0014 data and guarded migration lifecycle."""

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from asm.ai.fake import FakeAdapter
from asm.foundation import RuntimeDatabase, Settings
from generic_pg_schema import assert_current_schema, current_snapshot, historical_native_check
from sqlalchemy import text
from test_m3_1_native_context_postgres import migrate, scalar
from test_m4_agent import config
from test_m4_delivery_postgres import application, enrollment, source_turn
from test_m4_runtime_postgres import intent
from test_m4_runtime_postgres import pg as pg

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def schema15(pg):
    # Retain a real0014 AIRun/result, not merely an empty predecessor table.
    _, claim, _ = await intent(pg)
    cfg = config()
    receipt = await pg.ai.execute(
        claim, cfg, FakeAdapter(cfg.route), deadline=datetime.now(UTC) + timedelta(seconds=30)
    )
    before = await scalar(
        pg, "SELECT to_jsonb(r) FROM platform.ai_runs r WHERE id=:id", id=receipt.run_id
    )
    await migrate("upgrade", "0015")
    await migrate("upgrade", "0015")
    assert (
        await scalar(
            pg, "SELECT to_jsonb(r) FROM platform.ai_runs r WHERE id=:id", id=receipt.run_id
        )
        == before
    )
    assert await scalar(pg, "SELECT count(*) FROM platform.ai_deliveries") == 0
    assert (
        await scalar(pg, "SELECT to_jsonb(c) FROM app.conversations c WHERE id=:id", id=pg.retained)
        == pg.retained_before
    )
    pg.schema_revision = "0015"
    return pg


async def test_unused_successor_downgrade_restore_and_exact_readiness(schema15):
    h = schema15
    runtime = RuntimeDatabase(Settings())
    try:
        async with h.migrator.begin() as c:
            before = await current_snapshot(c)
        await runtime.check()
        with pytest.raises(RuntimeError, match="schema"):
            await historical_native_check(runtime)
        await migrate("downgrade", "0014")
        with pytest.raises(RuntimeError, match="schema"):
            await runtime.check()
        assert await scalar(h, "SELECT to_regclass('platform.ai_deliveries')") is None
        await migrate("upgrade", "0015")
        await runtime.check()
        async with h.migrator.begin() as c:
            assert await current_snapshot(c) == before
    finally:
        await runtime.close()


@pytest.mark.parametrize(
    "damage",
    [
        "ALTER TABLE platform.ai_deliveries NO FORCE ROW LEVEL SECURITY",
        "GRANT SELECT ON platform.ai_deliveries TO asm_runtime",
        "GRANT EXECUTE ON FUNCTION platform.ai_delivery_schema_profile() TO PUBLIC",
        "ALTER FUNCTION platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs) RESET search_path",
        "ALTER TABLE platform.ai_deliveries DROP CONSTRAINT ai_deliveries_selected_kind_check",
        "CREATE FUNCTION platform.unapproved_ai() RETURNS int LANGUAGE sql AS 'SELECT 1'",
    ],
)
async def test_current_catalog_refuses_body_acl_rls_constraint_and_extra_capability(
    schema15, damage
):
    h = schema15
    async with h.migrator.connect() as c:
        transaction = await c.begin()
        try:
            await c.execute(text(damage))
            with pytest.raises(Exception) as caught:
                await assert_current_schema(c)
            assert type(caught.value).__name__ in {"AssertionError", "Refusal"}
        finally:
            await transaction.rollback()
    async with h.migrator.begin() as c:
        await assert_current_schema(c)


async def test_durable_enrollment_blocks_downgrade_before_any_mutation(schema15):
    h = schema15
    _, source, _ = await source_turn(h)
    worker, _ = application(h)
    await worker.execute(source)
    assert (await enrollment(h, source))["selected_kind"] is None
    async with h.migrator.begin() as c:
        before = await current_snapshot(c)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "downgrade",
        "0014",
        env=dict(os.environ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode != 0 and b"AI_DELIVERY_DURABLE_DATA" in stderr
    async with h.migrator.begin() as c:
        assert await current_snapshot(c) == before
