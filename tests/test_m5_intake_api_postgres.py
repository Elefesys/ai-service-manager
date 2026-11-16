"""Actual cookie/CSRF/owner capabilities and durable DurationCase acceptance."""

import copy

import pytest
import pytest_asyncio
from m5_intake_fixtures import case_input
from sqlalchemy import text
from test_auth_postgres import headers
from test_m5_configuration_api_postgres import auth as auth
from test_m5_configuration_api_postgres import configured as configured
from test_m5_configuration_api_postgres import db as db
from test_m5_configuration_api_postgres import seeded as seeded
from test_tenancy_postgres import BA, BA2, BB, A, B

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def intake_api(configured):
    h = configured
    try:
        yield h
    finally:
        async with h.migrator.begin() as c:
            for name in (
                "intake_escalation_links",
                "intake_receipts",
                "duration_cases",
                "intake_state",
            ):
                await c.execute(
                    text(f"DELETE FROM platform.{name} WHERE workspace_id IN (:a,:b)"),
                    {"a": A, "b": B},
                )


def route(suffix, business=BA, workspace=A):
    return f"/api/v1/workspaces/{workspace}/businesses/{business}/intake/{suffix}"


async def send(h, operation, body, key, business=BA, workspace=A):
    return await h.client.post(
        route("duration-cases/" + operation, business, workspace),
        json=body,
        headers={**headers(h.client, h.csrf), "Idempotency-Key": key},
    )


async def test_owner_description_case_create_confirm_correct_revoke_and_replay(intake_api):
    h = intake_api
    body = {"expected_version": "0", "case_id": None, "data": case_input().model_dump(mode="json")}
    result = await send(h, "create", body, "case-create-one")
    assert result.status_code == 200, result.text
    repeat = await send(h, "create", body, "case-create-one")
    assert repeat.status_code == 200 and repeat.json()["outcome"] == "REPLAY"
    page = (await h.client.get(route("duration-cases"))).json()
    assert len(page["items"]) == 1
    case = page["items"][0]
    assert case["data"]["occupied_minutes"] is None and case["data"]["asset"] is None
    confirm = {"expected_version": case["version"], "case_id": case["case_id"], "data": None}
    result = await send(h, "confirm", confirm, "case-confirm-one")
    assert result.status_code == 200, result.text
    search = (await h.client.get(route("duration-cases/search?placement=forearm"))).json()
    assert len(search["items"]) == 1 and search["items"][0]["case"]["confirmed_by"]
    stale = await send(h, "revoke", confirm, "case-stale-one")
    assert stale.status_code == 409
    edit = {
        "expected_version": "2",
        "case_id": case["case_id"],
        "data": case_input(working_minutes=35, occupied_minutes=60).model_dump(mode="json"),
    }
    result = await send(h, "edit", edit, "case-edit-one")
    assert result.status_code == 200
    assert (await h.client.get(route("duration-cases/search"))).json()["items"] == []
    revoke = {"expected_version": "3", "case_id": case["case_id"], "data": None}
    assert (await send(h, "revoke", revoke, "case-revoke-one")).status_code == 200
    assert (await h.client.get(route("duration-cases"))).json()["items"][0]["state"] == "REVOKED"


async def test_two_businesses_same_code_and_cross_workspace_denial(intake_api):
    h = intake_api
    for index, business in enumerate((BA, BA2)):
        body = {
            "expected_version": "0",
            "case_id": None,
            "data": case_input(description=f"Business example {index}").model_dump(mode="json"),
        }
        result = await send(h, "create", body, f"case-business-{index}", business=business)
        assert result.status_code == 200, result.text
        items = (await h.client.get(route("duration-cases", business))).json()["items"]
        assert len(items) == 1 and items[0]["data"]["description"] == f"Business example {index}"
    assert (await h.client.get(route("duration-cases", BB, B))).status_code == 403
    assert (await h.client.get(route("duration-cases", BB, A))).status_code == 404


async def test_case_commands_reject_bad_csrf_conflicts_contradictions_and_unconfirmed_search(
    intake_api,
):
    h = intake_api
    body = {"expected_version": "0", "case_id": None, "data": case_input().model_dump(mode="json")}
    response = await h.client.post(
        route("duration-cases/create"),
        json=body,
        headers={"Origin": "http://localhost:8080", "Idempotency-Key": "no-csrf"},
    )
    assert response.status_code == 403
    assert (await send(h, "create", body, "idempotent-case")).status_code == 200
    bad = copy.deepcopy(body)
    bad["data"]["description"] = "Different intent"
    assert (await send(h, "create", bad, "idempotent-case")).status_code == 409
    bad["data"]["working_minutes"] = 60
    bad["data"]["occupied_minutes"] = 30
    assert (await send(h, "create", bad, "contradictory-case")).status_code == 422
    assert (await h.client.get(route("duration-cases/search"))).json()["items"] == []
