"""Install the intent capability over populated 0030 without widening v7 results."""

import pytest
from generic_pg_schema import assert_schema
from sqlalchemy import text
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m5_intake_postgres import application, summary
from test_m5_intake_postgres import db as db
from test_m5_intake_postgres import intake_pg as intake_pg
from test_m5_intake_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m5_intake_postgres import search_pg as search_pg
from test_m5_intake_postgres import seeded as seeded

pytestmark = pytest.mark.integration


async def test_0031_preserves_populated_0030_v7_run(intake_pg):
    h = intake_pg
    await h.runtime.engine.dispose()
    try:
        await _migrate("downgrade", "0030")
        h.schema_revision = "0030"
        async with h.migrator.begin() as connection:
            profile = await connection.execute(
                text("SELECT platform.quote_acceptance_schema_profile()")
            )
            assert profile.scalar_one()["valid"] is True
        cid, _, _, _, _ = await application(h, {"idea": "flower"})
        rows = """SELECT to_jsonb(r)-'service_request_pin' AS run FROM platform.ai_runs r
                  WHERE conversation_id=:cid ORDER BY id"""
        before = await query(h, rows, cid=cid)
        assert (
            len(before) == 1 and before[0]["run"]["config"]["prompt_revision"] == "conversation_v7"
        )
        projection = await summary(h, cid)
        assert projection["facts"][0]["value"] == "flower"
        await _migrate("upgrade", "0031")
        h.schema_revision = "0031"
        await _migrate("upgrade", "0031")
        async with h.migrator.begin() as connection:
            await assert_schema(connection, "0031", "service_intent_schema_profile")
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM platform.service_request_agent_intents")
                )
            ).scalar_one() == 0
            assert (
                await connection.execute(
                    text(
                        "SELECT service_request_pin FROM platform.ai_runs WHERE conversation_id=:cid"
                    ),
                    {"cid": cid},
                )
            ).scalar_one() is None
        assert await query(h, rows, cid=cid) == before
        assert await summary(h, cid) == projection
    finally:
        await _migrate("upgrade", "0036")
        h.schema_revision = "0036"
        await h.runtime.check()
