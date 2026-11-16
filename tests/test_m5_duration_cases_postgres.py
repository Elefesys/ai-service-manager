"""Exact asset/version revocation, runtime table isolation and owner-only data."""

import pytest
from asm.intake.duration_cases import compare_cases
from asm.intake.models import DurationCase
from m5_intake_fixtures import case_input
from m5_knowledge_search_fixtures import owner_unit
from m5_portfolio_fixtures import asset, call, command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m5_intake_postgres import application, bridge
from test_m5_intake_postgres import db as db
from test_m5_intake_postgres import intake_pg as intake_pg
from test_m5_intake_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m5_intake_postgres import search_pg as search_pg
from test_m5_intake_postgres import seeded as seeded
from test_tenancy_postgres import BA

pytestmark = pytest.mark.integration


async def test_case_asset_version_is_owner_scoped_and_delete_invalidates_comparison(intake_pg):
    h = intake_pg
    a, _ = await asset(bridge(h))
    data = case_input(
        description="Private owner explanation forbidden in client context",
        working_minutes=12345,
        asset={"asset_id": str(a["asset_id"]), "asset_version_id": str(a["version_id"])},
    )
    async with owner_unit(h) as u:
        await u.intake_owner(
            BA,
            None,
            "CASE_CREATE",
            "case-with-asset",
            dict(expected_version="0", case_id=None, data=data.model_dump(mode="json")),
        )
        page = await u.intake_owner(BA, None, "CASES", "", {})
        case = page["items"][0]
        await u.intake_owner(
            BA,
            None,
            "CASE_CONFIRM",
            "confirm-asset-case",
            dict(expected_version=case["version"], case_id=case["case_id"], data=None),
        )
    cid, _, model, _, _ = await application(h, {"idea": "flower"})
    assert cid
    for request in model.requests:
        wire = request.input_json()
        assert "working_minutes" not in wire and data.description not in wire
    async with owner_unit(h) as u:
        case = DurationCase.model_validate(
            (await u.intake_owner(BA, None, "CASES", "", {}))["items"][0]
        )
    assert case.source_current and compare_cases([case], {})
    portfolio = await call(bridge(h), "portfolio_owner_read", [BA])
    await command(
        bridge(h),
        "PORTFOLIO_DELETE",
        {
            "asset_id": str(a["asset_id"]),
            "expected_asset_version": portfolio["assets"][0]["version"],
            "expected_activation_version": portfolio["activation_version"],
        },
    )
    async with owner_unit(h) as u:
        current = DurationCase.model_validate(
            (await u.intake_owner(BA, None, "CASES", "", {}))["items"][0]
        )
    assert not current.source_current and compare_cases([current], {}) == []


@pytest.mark.parametrize(
    "table", ["intake_state", "duration_cases", "intake_receipts", "intake_escalation_links"]
)
async def test_runtime_cannot_read_or_mutate_new_private_tables(intake_pg, table):
    h = intake_pg
    for sql in (f"SELECT * FROM platform.{table}", f"DELETE FROM platform.{table}"):
        with pytest.raises(DBAPIError) as error:
            async with h.runtime.engine.begin() as c:
                await c.execute(text(sql))
        assert error.value.orig.sqlstate == "42501"
    async with h.migrator.connect() as c:
        assert (
            await c.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:name)"
                ),
                dict(name="platform." + table),
            )
        ).scalar_one()
