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
from test_m6_service_requests_postgres import create_body, revise_body, source_pin
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


@pytest.mark.parametrize(
    ("category", "separate"),
    [("COVER_UP", False), ("OTHER_COMPLEX", False), ("COVER_UP", True)],
    ids=["late-cover-up", "late-other-complex", "separate-cover-up"],
)
async def test_assessment_complex_work_is_bound_to_owner_selected_request(
    assessment_pg, auth, category, separate
):
    h = assessment_pg
    await publish(h, {"mode": "FIXED", "minutes": 65, "rule_note": None})
    cid, worker, model, _, delivery = await application(
        h,
        {"idea": "flower", "placement": "forearm", "approximate_size": "8 cm", "style": "linework"},
    )
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])
    collection = route(cid)
    first_id = await create_draft(auth, cid, mutation, await summary(h, cid))
    first_url = f"{collection}/{first_id}"
    first_assessment = first_url + "/assessment"
    original = await request_assessment(auth, first_assessment, mutation)
    assert (original["current"], original["outcome"], original["occupied_minutes"]) == (
        True,
        "FEASIBLE",
        65,
    )

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.category = category
    model.correction = not separate
    model.switch = separate
    if separate:
        model.values = {"idea": "bird", "placement": "shoulder", "approximate_size": "12 cm"}
        message = "Separate bird on the shoulder, 12 cm, to cover an old tattoo"
    else:
        model.values = {"approximate_size": "12 cm"}
        detail = "to cover an old tattoo" if category == "COVER_UP" else "around an old scar"
        message = f"For the first flower, actually 12 cm, {detail}"
    await next_turn(h, worker, message)
    projection = await summary(h, cid)
    assert (projection["status"], projection["category"]) == ("OWNER_HANDOFF", category)
    first = (await auth.client.get(collection, params={"request_id": first_id})).json()
    command = revise_body(projection, first, "approximate_size")
    source = command["source"]
    assert projection["sources"][-1]["message_id"] == source["message_id"]
    assert (await auth.client.get(first_assessment)).json() == original

    if separate:
        second_id = await create_draft(auth, cid, mutation, projection)
        assert first_id != second_id
        blocked = await auth.client.patch(
            first_url, json=command, headers=mutation | {"Idempotency-Key": str(uuid4())}
        )
        assert (
            blocked.status_code == 409 and blocked.json()["error"]["code"] == "NEEDS_CLARIFICATION"
        )
        assert await request_assessment(auth, first_assessment, mutation) == original
        result = await request_assessment(auth, f"{collection}/{second_id}/assessment", mutation)
        assert (result["request_revision"], result["current"], result["occupied_minutes"]) == (
            "1",
            True,
            None,
        )
        assert (result["outcome"], result["reason"]) == ("NEEDS_OWNER", "OWNER_HANDOFF")
        assert result["complex_work"] == {
            "category": category,
            "source": source,
            "source_current": True,
        }
        return

    unclear = await auth.client.patch(
        first_url,
        json=command | {"selection": "UNCLEAR"},
        headers=mutation | {"Idempotency-Key": str(uuid4())},
    )
    assert unclear.status_code == 409 and unclear.json()["error"]["code"] == "NEEDS_CLARIFICATION"
    key = mutation | {"Idempotency-Key": str(uuid4())}
    for _ in range(2):
        revised = await auth.client.patch(first_url, json=command, headers=key)
        assert revised.status_code == 200, revised.text
        assert revised.json()["request_id"] == first_id
    assert (await auth.client.get(first_assessment)).json() == original | {"current": False}
    current = await request_assessment(auth, first_assessment, mutation, revision="2")
    assert (current["request_revision"], current["current"], current["occupied_minutes"]) == (
        "2",
        True,
        None,
    )
    assert (current["outcome"], current["reason"]) == ("NEEDS_OWNER", "OWNER_HANDOFF")
    assert current["assessment_id"] != original["assessment_id"]
    assert current["duration_policy"] is None
    assert current["complex_work"] == {
        "category": category,
        "source": source,
        "source_current": True,
    }
    assert current["archived_duration"] == {
        field: original[field]
        for field in (
            "assessment_id",
            "request_revision",
            "release_id",
            "activation_version",
            "occupied_minutes",
        )
    }
    assert await request_assessment(auth, first_assessment, mutation, revision="2") == current
    assert (await auth.client.get(first_assessment)).json() == current
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.service_assessments WHERE request_id=:id",
            id=UUID(first_id),
        )
        == 2
    )


@pytest.mark.parametrize(
    ("category", "separate"),
    [("COVER_UP", False), ("OTHER_COMPLEX", False), ("COVER_UP", True)],
    ids=["cover-up-only", "other-complex-only", "separate-work"],
)
async def test_assessment_accepts_complexity_message_without_a_field(
    assessment_pg, auth, category, separate
):
    h = assessment_pg
    await publish(h, {"mode": "FIXED", "minutes": 65, "rule_note": None})
    cid, worker, model, _, delivery = await application(
        h,
        {"idea": "flower", "placement": "forearm", "approximate_size": "8 cm", "style": "linework"},
    )
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])
    collection = route(cid)
    first_id = await create_draft(auth, cid, mutation, await summary(h, cid))
    first_url = f"{collection}/{first_id}/assessment"
    first = await request_assessment(auth, first_url, mutation)
    assert (first["current"], first["outcome"], first["occupied_minutes"]) == (True, "FEASIBLE", 65)

    target_id, original = first_id, first
    if separate:
        await worker.execute(await claim_job(h, delivery["send_job_id"]))
        model.switch = True
        model.values = {
            "idea": "bird",
            "placement": "shoulder",
            "approximate_size": "5 cm",
            "style": "linework",
        }
        _, delivery = await next_turn(h, worker, "Separate bird, shoulder, 5 cm, linework")
        target_id = await create_draft(auth, cid, mutation, await summary(h, cid))
        assert target_id != first_id
        original = await request_assessment(auth, f"{collection}/{target_id}/assessment", mutation)
        assert original["occupied_minutes"] == 65
    target_url = f"{collection}/{target_id}/assessment"
    draft = (await auth.client.get(collection, params={"request_id": target_id})).json()
    before = await summary(h, cid)

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {}
    model.switch = False
    model.category = category
    work = "bird" if separate else "flower"
    detail = "will cover an old tattoo" if category == "COVER_UP" else "must go around a scar"
    message = f"I forgot to say, the {work} {detail}"
    await next_turn(h, worker, message)
    projection = await summary(h, cid)
    assert (projection["status"], projection["category"]) == ("OWNER_HANDOFF", category)
    assert projection["facts"] == before["facts"]
    latest = projection["sources"][-1]
    assert latest["text"] == message
    source = source_pin(latest)
    assert all(fact["source"]["message_id"] != source["message_id"] for fact in projection["facts"])
    assert (await auth.client.get(target_url)).json() == original
    command = {
        "expected_revision": draft["revision"],
        "expected_version": projection["version"],
        "expected_fingerprint": projection["fingerprint"],
        "selection": "ONE_WORK",
        "source": source,
    }

    async def bind(body, *, request_id=target_id, key=None):
        return await auth.client.patch(
            f"{collection}/{request_id}",
            json=body,
            headers=mutation | {"Idempotency-Key": key or str(uuid4())},
        )

    for changes, code in (
        ({"source": source | {"source_version": "0" * 64}}, "STALE_STATE"),
        ({"source": draft["intent_source"]}, "NEEDS_CLARIFICATION"),
        ({"selection": "UNCLEAR"}, "NEEDS_CLARIFICATION"),
    ):
        rejected = await bind(command | changes)
        assert (rejected.status_code, rejected.json()) == (409, {"error": {"code": code}})
    assert (await auth.client.get(target_url)).json() == original

    key = str(uuid4())
    for _ in range(2):
        accepted = await bind(command, key=key)
        assert accepted.status_code == 200, accepted.text
        assert accepted.json() == {"request_id": target_id}
    original_revision = command["expected_revision"]
    assert original_revision == "1"
    stale = await bind(command)
    assert (stale.status_code, stale.json()) == (409, {"error": {"code": "STALE_STATE"}})
    same_source = await bind(command | {"expected_revision": "2"})
    assert same_source.status_code == 200, same_source.text
    revised = (await auth.client.get(collection, params={"request_id": target_id})).json()
    assert revised["revision"] == "2"
    assert revised["facts"] == draft["facts"]
    assert (await auth.client.get(target_url)).json() == original | {"current": False}

    current = await request_assessment(auth, target_url, mutation, revision="2")
    assert (current["current"], current["outcome"], current["reason"]) == (
        True,
        "NEEDS_OWNER",
        "OWNER_HANDOFF",
    )
    assert (
        current["request_revision"],
        current["occupied_minutes"],
        current["duration_policy"],
    ) == (
        "2",
        None,
        None,
    )
    assert current["complex_work"] == {
        "category": category,
        "source": source,
        "source_current": True,
    }
    assert current["assessment_id"] != original["assessment_id"]
    assert current["archived_duration"]["assessment_id"] == original["assessment_id"]
    assert current["archived_duration"]["occupied_minutes"] == 65
    assert await request_assessment(auth, target_url, mutation, revision="2") == current
    assert (await auth.client.get(target_url)).json() == current
    if separate:
        refused = await bind(command, request_id=first_id)
        assert (refused.status_code, refused.json()) == (
            409,
            {"error": {"code": "NEEDS_CLARIFICATION"}},
        )
        assert await request_assessment(auth, first_url, mutation) == first


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
