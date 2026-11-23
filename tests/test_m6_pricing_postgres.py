"""M6.2 owner routes on the real TEST database."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.configuration.validation import validate_bundle
from m5_intake_fixtures import intake_bundle
from m5_knowledge_search_fixtures import owner_unit
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_auth_postgres import headers, login
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job, scalar
from test_m3_1_provenance_postgres import process, raw
from test_m4_runtime_postgres import COUNTER
from test_m5_intake_postgres import application, next_turn, summary
from test_m6_service_assessments_api_postgres import assessment_pg as assessment_pg
from test_m6_service_assessments_api_postgres import auth as auth
from test_m6_service_assessments_api_postgres import create_draft, request_assessment
from test_m6_service_assessments_api_postgres import db as db
from test_m6_service_assessments_api_postgres import intake_pg as intake_pg
from test_m6_service_assessments_api_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_service_assessments_api_postgres import search_pg as search_pg
from test_m6_service_assessments_api_postgres import seeded as seeded
from test_m6_service_assessments_api_postgres import service_request_pg as service_request_pg
from test_m6_service_requests_api_postgres import route
from test_tenancy_postgres import BA, BB, A, B

pytestmark = pytest.mark.integration
FORMULA = {
    "kind": "SIZE_STEPS_V1",
    "currency": "RUB",
    "input_unit": "MM",
    "rounding": "CEILING",
    "base_minor": 250_000,
    "step_minor": 50_000,
    "step_mm": 10,
    "max_size_mm": 100,
    "range_add_minor": None,
}
FLOWER = {"idea": "flower", "placement": "forearm", "style": "linework"}
FIXED = {"mode": "FIXED", "amount_minor": 120_001, "formula_note": None}
MANUAL = {"mode": "OWNER_QUOTE", "amount_minor": None, "formula_note": None}


@pytest_asyncio.fixture
async def pricing_pg(assessment_pg):
    try:
        yield assessment_pg
    finally:
        async with assessment_pg.migrator.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE app.price_calculations DISABLE TRIGGER price_calculation_immutable"
                )
            )
            await connection.execute(
                text("DELETE FROM app.price_calculations WHERE workspace_id IN (:a,:b)"),
                {"a": A, "b": B},
            )
            await connection.execute(
                text(
                    "ALTER TABLE app.price_calculations ENABLE TRIGGER price_calculation_immutable"
                )
            )


def formula_price(**changes):
    return {
        "mode": "CONFIGURED_FORMULA",
        "amount_minor": None,
        "formula_note": None,
        "size_formula": FORMULA | changes,
    }


def pricing_bundle(price):
    bundle = intake_bundle()
    bundle["rules"] = []
    bundle["faqs"] = []
    bundle["services"][0]["price"] = price
    return bundle


async def publish(h, bundle):
    async with owner_unit(h) as unit:
        state = await unit.configuration_owner_read(BA)
        edit = await unit.configuration_command(
            BA,
            "EDIT",
            str(uuid4()),
            {"expected_draft_version": state["draft_version"], "bundle": bundle},
        )
        return (
            await unit.configuration_command(
                BA,
                "PUBLISH",
                str(uuid4()),
                {
                    "expected_draft_version": edit["result"]["draft_version"],
                    "expected_activation_version": state["activation_version"],
                },
            )
        )["result"]


async def sign_in(auth):
    response = await login(auth)
    assert response.status_code == 200
    return headers(auth.client, response.json()["csrf_token"])


async def price(auth, endpoint, mutation, revision="1"):
    response = await auth.client.post(
        endpoint, headers=mutation, json={"expected_revision": revision}
    )
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


async def history(auth, endpoint):
    response = await auth.client.get(endpoint)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["next_before_id"] is None
    return response.json()["items"]


async def draft_for_size(h, auth, mutation, value, *, telegram=False):
    facts = FLOWER | ({"approximate_size": value} if value is not None else {})
    cid, worker, model, _, delivery = await application(
        h, facts, telegram=telegram, message_text=" ".join(facts.values())
    )
    projection = await summary(h, cid)
    request_id = await create_draft(auth, cid, mutation, projection)
    return cid, worker, model, delivery, request_id


async def test_pricing_two_work_sources_boundary_replay_and_access(pricing_pg, auth):
    h = pricing_pg
    published = await publish(h, pricing_bundle(formula_price()))
    mutation = await sign_in(auth)
    cid, worker, model, delivery, first_id = await draft_for_size(h, auth, mutation, "20 mm")
    url = f"{route(cid)}/{first_id}/pricing"
    assert not await history(auth, url)
    first, duplicate = await asyncio.gather(price(auth, url, mutation), price(auth, url, mutation))
    assert first == duplicate
    assert (
        first["outcome"],
        first["authority"],
        first["currency"],
        first["size_mm"],
        first["steps"],
        first["amount_minor"],
    ) == ("EXACT", "CONFIRMED", "RUB", 20, 2, 350_000)
    assert first["policy"]["size_formula"] == FORMULA
    assert (first["release_id"], first["activation_version"]) == (
        published["release_id"],
        published["activation_version"],
    )

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {
        "idea": "bird",
        "placement": "shoulder",
        "approximate_size": "2.1 cm",
        "style": "linework",
    }
    model.switch = True
    await next_turn(h, worker, "Separate bird shoulder, 2.1 cm, linework")
    second_id = await create_draft(auth, cid, mutation, await summary(h, cid))
    other = f"{route(cid)}/{second_id}/pricing"
    second = await price(auth, other, mutation)
    assert (second["size_mm"], second["steps"], second["amount_minor"]) == (21, 3, 400_000)
    assert second["release_id"] == first["release_id"]
    assert second["size_fact"]["value"] == "2.1 cm"
    assert second["size_fact"]["source"]["message_id"] != first["size_fact"]["source"]["message_id"]
    assert (
        second["size_fact"]["source"]["source_version"]
        != first["size_fact"]["source"]["source_version"]
    )
    assert await price(auth, other, mutation) == second
    assert await history(auth, other) == [second] and await history(auth, url) == [first]
    assert (
        await auth.client.get(other, params={"before_id": first["calculation_id"]})
    ).status_code == 404

    foreign_cid, _, _, _, _ = await application(h, {"idea": "flower"})
    foreign_client = f"{route(foreign_cid)}/{first_id}/pricing"
    foreign_workspace = f"/api/v1/workspaces/{B}/businesses/{BB}/intake/conversations/{cid}/service-requests/{first_id}/pricing"
    for endpoint, code in ((foreign_client, 404), (foreign_workspace, 403)):
        assert (await auth.client.get(endpoint)).status_code == code
        assert (
            await auth.client.post(endpoint, headers=mutation, json={"expected_revision": "1"})
        ).status_code == code
    assert (
        await auth.client.post(
            url, headers=mutation, json={"expected_revision": "1", "amount_minor": 1}
        )
    ).status_code == 422
    assert (await auth.client.post(url, json={"expected_revision": "1"})).status_code == 403
    assert (
        await scalar(
            h, "SELECT count(*) FROM app.price_calculations WHERE request_id=:id", id=UUID(first_id)
        )
        == 1
    )
    assert (
        await scalar(
            h,
            "SELECT has_table_privilege('asm_runtime','app.price_calculations','SELECT,INSERT,UPDATE,DELETE')",
        )
        is False
    )
    with pytest.raises(IntegrityError, match="PRICE_CALCULATION_IMMUTABLE"):
        async with h.migrator.begin() as connection:
            await connection.execute(
                text("UPDATE app.price_calculations SET amount_minor=1 WHERE id=:id"),
                {"id": UUID(first["calculation_id"])},
            )


@pytest.mark.parametrize("material_change", ["EDIT", "DELETE"])
async def test_pricing_material_source_change_retains_old_result(pricing_pg, auth, material_change):
    h = pricing_pg
    await publish(h, pricing_bundle(formula_price()))
    mutation = await sign_in(auth)
    cid, _, _, _, request_id = await draft_for_size(h, auth, mutation, "20 mm", telegram=True)
    endpoint = f"{route(cid)}/{request_id}/pricing"
    approved = await price(auth, endpoint, mutation)
    assert approved["amount_minor"] == 350_000
    source = (
        await query(
            h,
            "SELECT provider_message_id,provider_chat_id FROM app.messages WHERE id=:id",
            id=UUID(approved["size_fact"]["source"]["message_id"]),
        )
    )[0]
    _, _, change = await process(
        h,
        raw(
            900000 + next(COUNTER),
            int(source["provider_message_id"]),
            kind=material_change,
            value="Corrected size 22 mm",
            chat=source["provider_chat_id"],
            sender=source["provider_chat_id"],
            date=40,
        ),
    )
    assert change.code == "MATERIAL_PROCESSED"
    archived = approved | {"current": False}
    assert await history(auth, endpoint) == [archived]
    missing = await price(auth, endpoint, mutation)
    assert (
        missing["outcome"],
        missing["reason"],
        missing["amount_minor"],
        missing["size_fact"],
    ) == ("NEEDS_INPUT", "SIZE_REQUIRED", None, None)
    assert missing["calculation_id"] != approved["calculation_id"]
    assert await price(auth, endpoint, mutation) == missing
    assert await history(auth, endpoint) == [missing, archived]


async def test_pricing_publication_range_and_rollback_preserve_history(pricing_pg, auth):
    h = pricing_pg
    initial = await publish(h, pricing_bundle(formula_price()))
    mutation = await sign_in(auth)
    cid, _, _, _, request_id = await draft_for_size(h, auth, mutation, "20 mm")
    endpoint = f"{route(cid)}/{request_id}/pricing"
    first = await price(auth, endpoint, mutation)
    changed_bundle = pricing_bundle(formula_price(base_minor=300_000, range_add_minor=50_000))
    new_release = await publish(h, changed_bundle)
    assert await history(auth, endpoint) == [first | {"current": False}]
    interval = await price(auth, endpoint, mutation)
    assert (
        interval["outcome"],
        interval["authority"],
        interval["amount_minor"],
        interval["lower_minor"],
        interval["upper_minor"],
    ) == ("RANGE", "PROVISIONAL", None, 400_000, 450_000)
    assert interval["release_id"] == new_release["release_id"]
    assert await price(auth, endpoint, mutation) == interval
    changed_bundle["services"][0]["deposit"] = {
        "mode": "PERCENT_DEPOSIT",
        "amount_minor": None,
        "percent": 20,
    }
    deposit_only = await publish(h, changed_bundle)
    same_range = await price(auth, endpoint, mutation)
    assert same_range["release_id"] == deposit_only["release_id"]
    assert (same_range["lower_minor"], same_range["upper_minor"], same_range["authority"]) == (
        400_000,
        450_000,
        "PROVISIONAL",
    )
    async with owner_unit(h) as unit:
        rollback = (
            await unit.configuration_command(
                BA,
                "ROLLBACK",
                str(uuid4()),
                {
                    "expected_activation_version": deposit_only["activation_version"],
                    "release_id": initial["release_id"],
                },
            )
        )["result"]
    assert all(not row["current"] for row in await history(auth, endpoint))
    latest = await price(auth, endpoint, mutation)
    assert latest["amount_minor"] == first["amount_minor"] == 350_000
    assert latest["release_id"] == first["release_id"]
    assert (
        latest["activation_version"]
        == rollback["activation_version"]
        != first["activation_version"]
    )
    assert latest["calculation_id"] != first["calculation_id"]
    assert await history(auth, endpoint) == [
        latest,
        same_range | {"current": False},
        interval | {"current": False},
        first | {"current": False},
    ]


async def test_pricing_per_service_independent_of_approved_duration(pricing_pg, auth):
    h = pricing_pg
    bundle = pricing_bundle(FIXED)
    fixed_service = bundle["services"][0]
    fixed_service["duration"] = {"mode": "OWNER_DEFINED", "minutes": None, "rule_note": None}
    bundle["services"].append(
        fixed_service
        | {
            "id": "owner-quote",
            "name": "Synthetic owner quote",
            "price": MANUAL,
            "duration": {"mode": "FIXED", "minutes": 65, "rule_note": None},
        }
    )
    published = await publish(h, bundle)
    mutation = await sign_in(auth)
    cid, worker, model, delivery, first_id = await draft_for_size(h, auth, mutation, "20 mm")
    fixed_url = f"{route(cid)}/{first_id}"
    duration = await request_assessment(auth, fixed_url + "/assessment", mutation)
    fixed_price = await price(auth, fixed_url + "/pricing", mutation)
    assert duration["outcome"] == "NEEDS_OWNER" and duration["occupied_minutes"] is None
    assert fixed_price["amount_minor"] == 120_001 and fixed_price["reason"] == "FIXED_PRICE"
    assert fixed_price["release_id"] == published["release_id"]

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.service_id = "owner-quote"
    model.switch = True
    model.values = {
        "idea": "bird",
        "placement": "shoulder",
        "approximate_size": "21 mm",
        "style": "linework",
    }
    await next_turn(h, worker, "Separate bird, shoulder, 21 mm, linework")
    current = await summary(h, cid)
    assert current["service_id"] == "owner-quote"
    second_id = await create_draft(auth, cid, mutation, current)
    second_url = f"{route(cid)}/{second_id}"
    approved_duration = await request_assessment(auth, second_url + "/assessment", mutation)
    manual = await price(auth, second_url + "/pricing", mutation)
    assert approved_duration["occupied_minutes"] == 65
    assert (manual["outcome"], manual["reason"], manual["amount_minor"]) == (
        "NEEDS_HUMAN",
        "OWNER_QUOTE",
        None,
    )
    assert manual["release_id"] == fixed_price["release_id"]
    assert (await auth.client.get(second_url + "/assessment")).json() == approved_duration
    assert await history(auth, fixed_url + "/pricing") == [fixed_price]


@pytest.mark.parametrize(
    ("limit", "measurement", "millimetres", "reason", "amount"),
    [
        (1000, None, None, "SIZE_REQUIRED", None),
        (100, "-20 mm", None, "SIZE_REQUIRED", None),
        (100, "20 m", None, "SIZE_REQUIRED", None),
        (100, "101 mm", 101, "SIZE_OUTSIDE_RULE", None),
        (1000, "1000 mm", 1000, "SIZE_FORMULA", 5_250_000),
        (1000, "1001 mm", 1001, "SIZE_OUTSIDE_RULE", None),
        (1000, "100,1 cm", 1001, "SIZE_OUTSIDE_RULE", None),
    ],
)
async def test_pricing_distinguishes_missing_size_from_exceeding_the_limit(
    pricing_pg, auth, limit, measurement, millimetres, reason, amount
):
    h = pricing_pg
    await publish(h, pricing_bundle(formula_price(max_size_mm=limit)))
    mutation = await sign_in(auth)
    cid, _, _, _, request_id = await draft_for_size(h, auth, mutation, measurement)
    endpoint = f"{route(cid)}/{request_id}/pricing"
    calculated = await price(auth, endpoint, mutation)
    assert (
        calculated["size_mm"],
        calculated["reason"],
        calculated["amount_minor"],
        calculated["lower_minor"],
        calculated["upper_minor"],
    ) == (millimetres, reason, amount, None, None)
    assert (
        calculated["outcome"]
        == {
            "SIZE_REQUIRED": "NEEDS_INPUT",
            "SIZE_OUTSIDE_RULE": "NEEDS_HUMAN",
            "SIZE_FORMULA": "EXACT",
        }[reason]
    )
    assert calculated["authority"] == ("CONFIRMED" if amount is not None else None)
    assert calculated["steps"] == (100 if amount is not None else None)
    if millimetres is None:
        assert calculated["size_fact"] is None
    else:
        fact = calculated["size_fact"]
        assert fact["value"] == measurement
        original = next(
            fact for fact in (await summary(h, cid))["facts"] if fact["field"] == "approximate_size"
        )
        assert (fact["source"]["message_id"], fact["source"]["source_version"]) == (
            original["source"]["message_id"],
            original["source"]["source_version"],
        )
    assert await price(auth, endpoint, mutation) == calculated
    assert await history(auth, endpoint) == [calculated]


async def test_pricing_legacy_note_and_invalid_publication_parameters(pricing_pg, auth):
    h = pricing_pg
    for changes in (
        {"input_unit": "CM"},
        {"step_mm": 0},
        {"rounding": "FLOOR"},
        {"step_minor": -50000},
        {"step_minor": 100_000_000_000},
    ):
        bundle = pricing_bundle(formula_price(**changes))
        assert validate_bundle(bundle).valid is False
        async with h.migrator.connect() as connection:
            valid = await connection.scalar(
                text("SELECT platform.configuration_bundle_shape(CAST(:b AS jsonb))"),
                {"b": json.dumps(bundle)},
            )
        assert valid is False
    legacy = {"mode": "CONFIGURED_FORMULA", "amount_minor": None, "formula_note": "Example: 12345"}
    await publish(h, pricing_bundle(legacy))
    mutation = await sign_in(auth)
    cid, _, _, _, request_id = await draft_for_size(h, auth, mutation, "20 mm")
    result = await price(auth, f"{route(cid)}/{request_id}/pricing", mutation)
    assert result["outcome"] == "NEEDS_HUMAN" and result["reason"] == "PRICE_UNPUBLISHED"
    assert result["policy"] == legacy and result["amount_minor"] is None


async def test_0027_preserves_0026_data_and_refuses_downgrade_after_calculation(pricing_pg, auth):
    h = pricing_pg
    await publish(h, pricing_bundle(FIXED))
    mutation = await sign_in(auth)
    cid, _, _, _, request_id = await draft_for_size(h, auth, mutation, None)
    before = (await auth.client.get(route(cid), params={"request_id": request_id})).json()
    try:
        await _migrate("downgrade", "0026")
        assert await scalar(h, "SELECT to_regclass('app.price_calculations') IS NULL")
        assert (await scalar(h, "SELECT platform.service_assessment_schema_profile()"))[
            "valid"
        ] is True
    finally:
        await _migrate("upgrade", "0031")
    assert (await auth.client.get(route(cid), params={"request_id": request_id})).json() == before
    endpoint = f"{route(cid)}/{request_id}/pricing"
    first = await price(auth, endpoint, mutation)
    try:
        with pytest.raises(AssertionError, match="PRICE_CALCULATION_DURABLE_DATA"):
            await _migrate("downgrade", "0026")
    finally:
        await _migrate("upgrade", "0031")
    assert await history(auth, endpoint) == [first]
