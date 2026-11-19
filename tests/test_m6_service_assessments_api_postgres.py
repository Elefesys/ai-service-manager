"""Assessment through the normal owner routes and PostgreSQL."""

import asyncio
from uuid import UUID, uuid4

import pytest
from m5_intake_fixtures import intake_bundle
from m5_knowledge_search_fixtures import ControlledEmbeddings, owner_unit
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m3_1_native_context_postgres import claim_job, scalar
from test_m4_delivery_postgres import run_turn
from test_m5_intake_postgres import application, next_turn, summary
from test_m5_intake_v7_integration_postgres import compose
from test_m5_portfolio_runtime_postgres import analyse, source_image
from test_m6_service_assessment import SIZE_RULE
from test_m6_service_assessments_postgres import assessment_pg as assessment_pg
from test_m6_service_requests_api_postgres import route
from test_m6_service_requests_postgres import create_body, revise_body
from test_m6_service_requests_postgres import db as db
from test_m6_service_requests_postgres import intake_pg as intake_pg
from test_m6_service_requests_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_service_requests_postgres import search_pg as search_pg
from test_m6_service_requests_postgres import seeded as seeded
from test_m6_service_requests_postgres import service_request_pg as service_request_pg
from test_tenancy_postgres import BA, BA2

pytestmark = pytest.mark.integration


async def publish(h, duration):
    bundle = intake_bundle()
    bundle["rules"] = []
    bundle["faqs"] = []
    service = bundle["services"][0]
    service["price"] = {"mode": "OWNER_QUOTE", "amount_minor": None, "formula_note": None}
    service["duration"] = duration
    async with owner_unit(h) as unit:
        state = await unit.configuration_owner_read(BA)
        edited = await unit.configuration_command(
            BA,
            "EDIT",
            str(uuid4()),
            {"expected_draft_version": state["draft_version"], "bundle": bundle},
        )
        published = await unit.configuration_command(
            BA,
            "PUBLISH",
            str(uuid4()),
            {
                "expected_draft_version": edited["result"]["draft_version"],
                "expected_activation_version": state["activation_version"],
            },
        )
    return published["result"]


async def create_draft(auth, conversation, mutation, projection):
    response = await auth.client.post(
        route(conversation),
        json=create_body(projection),
        headers=mutation | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()["request_id"]


async def request_assessment(auth, url, mutation, revision="1"):
    response = await auth.client.post(url, json={"expected_revision": revision}, headers=mutation)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


async def test_assessment_owner_api_isolates_work_and_refreshes_revision_and_release(
    assessment_pg, auth
):
    h = assessment_pg
    fixed = await publish(h, {"mode": "FIXED", "minutes": 65, "rule_note": None})
    cid, worker, model, _, delivery = await application(
        h,
        {"idea": "flower", "placement": "forearm", "approximate_size": "8 cm", "style": "linework"},
    )
    projection = await summary(h, cid)
    assert (await auth.client.get(route(cid) + f"/{uuid4()}/assessment")).status_code == 401
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])
    first_id = await create_draft(auth, cid, mutation, projection)
    endpoint = f"{route(cid)}/{first_id}/assessment"
    assert (await auth.client.get(endpoint)).json() is None
    assert (await auth.client.post(endpoint, json={"expected_revision": "1"})).status_code == 403
    assert (
        await auth.client.post(
            endpoint, json={"expected_revision": "1", "occupied_minutes": 10}, headers=mutation
        )
    ).status_code == 422

    left, right = await asyncio.gather(
        request_assessment(auth, endpoint, mutation), request_assessment(auth, endpoint, mutation)
    )
    assert left == right
    assert (left["outcome"], left["occupied_minutes"], left["release_id"]) == (
        "FEASIBLE",
        65,
        fixed["release_id"],
    )
    assert left["duration_policy"] == {"mode": "FIXED", "minutes": 65, "rule_note": None}
    assert (await auth.client.get(endpoint)).json() == left
    assert (
        await auth.client.get(f"{route(cid, business=BA2)}/{first_id}/assessment")
    ).status_code == 404

    configured = await publish(
        h, {"mode": "CONFIGURED_RULE", "minutes": None, "rule_note": None, "size_rule": SIZE_RULE}
    )
    old = (await auth.client.get(endpoint)).json()
    assert old == left | {"current": False}
    at_boundary = await request_assessment(auth, endpoint, mutation)
    assert (at_boundary["size_mm"], at_boundary["occupied_minutes"], at_boundary["release_id"]) == (
        80,
        90,
        configured["release_id"],
    )
    assert at_boundary["duration_policy"]["size_rule"] == SIZE_RULE
    size_source = next(
        f["source"] for f in at_boundary["evidence"] if f["field"] == "approximate_size"
    )

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"idea": "bird", "placement": "shoulder", "style": "linework"}
    model.switch = True
    _, delivery = await next_turn(h, worker, "Separate work: bird on the shoulder, linework")
    second_id = await create_draft(auth, cid, mutation, await summary(h, cid))
    second = await request_assessment(auth, f"{route(cid)}/{second_id}/assessment", mutation)
    assert second_id != first_id and second["outcome"] == "NEEDS_DATA"
    assert (second["field"], second["occupied_minutes"]) == ("approximate_size", None)
    assert {fact["value"] for fact in second["evidence"]} == {"bird", "shoulder", "linework"}
    assert all(
        fact["source"]["message_id"] != size_source["message_id"] for fact in second["evidence"]
    )

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"approximate_size": "81 mm"}
    model.switch = False
    model.correction = True
    await next_turn(h, worker, "The first flower is 81 mm")
    updated = await summary(h, cid)
    draft = (await auth.client.get(route(cid), params={"request_id": first_id})).json()
    saved = await auth.client.patch(
        f"{route(cid)}/{first_id}",
        json=revise_body(updated, draft, "approximate_size"),
        headers=mutation | {"Idempotency-Key": str(uuid4())},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["request_id"] == first_id
    assert (await auth.client.get(endpoint)).json() == at_boundary | {"current": False}
    stale = await auth.client.post(endpoint, json={"expected_revision": "1"}, headers=mutation)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_STATE"
    above_boundary = await request_assessment(auth, endpoint, mutation, revision="2")
    assert (above_boundary["size_mm"], above_boundary["occupied_minutes"]) == (81, 120)
    assert (
        above_boundary["request_revision"] == "2"
        and above_boundary["assessment_id"] != at_boundary["assessment_id"]
    )
    assert (await auth.client.get(f"{route(cid)}/{second_id}/assessment")).json() == second
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.service_assessments WHERE request_id=:id",
            id=UUID(first_id),
        )
        == 3
    )


async def test_unscaled_image_is_evidence_but_cannot_establish_duration(assessment_pg, auth):
    h = assessment_pg
    await publish(
        h, {"mode": "CONFIGURED_RULE", "minutes": None, "rule_note": None, "size_rule": SIZE_RULE}
    )
    cid, source_job, _, image = await source_image(h, caption="flower forearm linework")
    reserved, completed, _ = await analyse(h, cid)
    assert completed["state"] == "SUCCESS"
    digest = await scalar(
        h,
        "SELECT encode(sha256(convert_to((completion->'result')::text,'UTF8')),'hex') "
        "FROM platform.vision_analyses WHERE id=:id",
        id=UUID(reserved["analysis_id"]),
    )
    h.photo_embeddings = ControlledEmbeddings()
    h.photo_store = h.store
    h.photo_workers = h.intake_workers

    def observed_reference(result):
        fact = next(f for f in result["intake"]["facts"] if f["field"] == "references")
        fact["status"] = "observed"
        fact["source"].update(quote="", analysis_id=reserved["analysis_id"], analysis_sha256=digest)

    worker, _, _ = await compose(
        h,
        cid,
        [],
        photo=False,
        mutate=observed_reference,
        values={
            "idea": "flower",
            "placement": "forearm",
            "style": "linework",
            "references": "outline",
        },
    )
    await run_turn(h, worker, source_job)
    projection = await summary(h, cid)
    assert {f["field"] for f in projection["facts"]} == {"idea", "placement", "style", "references"}
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])
    request_id = await create_draft(auth, cid, mutation, projection)
    result = await request_assessment(auth, f"{route(cid)}/{request_id}/assessment", mutation)
    assert (result["outcome"], result["reason"], result["field"]) == (
        "NEEDS_DATA",
        "MISSING_FACT",
        "approximate_size",
    )
    assert result["size_mm"] is None and result["occupied_minutes"] is None
    reference = next(f for f in result["evidence"] if f["field"] == "references")
    assert reference["status"] == "observed"
    assert reference["source"]["message_id"] == str(image["message_id"])
    assert reference["source"]["analysis_id"] == reserved["analysis_id"]
    assert reference["source"]["analysis_sha256"] == digest
