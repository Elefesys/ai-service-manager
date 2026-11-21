"""Owner decision Q3 through the production routes on TEST PostgreSQL."""

import asyncio
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job, control, scalar
from test_m3_1_provenance_postgres import process, raw
from test_m4_runtime_postgres import COUNTER
from test_m5_intake_postgres import application, next_turn, summary
from test_m6_pricing_postgres import (
    FIXED,
    MANUAL,
    draft_for_size,
    formula_price,
    price,
    pricing_bundle,
    publish,
    sign_in,
)
from test_m6_pricing_postgres import assessment_pg as assessment_pg
from test_m6_pricing_postgres import auth as auth
from test_m6_pricing_postgres import db as db
from test_m6_pricing_postgres import intake_pg as intake_pg
from test_m6_pricing_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_pricing_postgres import pricing_pg as pricing_pg
from test_m6_pricing_postgres import search_pg as search_pg
from test_m6_pricing_postgres import seeded as seeded
from test_m6_pricing_postgres import service_request_pg as service_request_pg
from test_m6_service_assessments_api_postgres import create_draft
from test_m6_service_requests_api_postgres import route
from test_m6_service_requests_postgres import revise_body, source_pin
from test_tenancy_postgres import BB, UA, A, B

pytestmark = pytest.mark.integration
AB = {"expected_version": "1", "action": "PREPARE_QUOTE"}
CONFIRM = AB | {"operation": "APPROVE", "amount_minor": 395_001, "occupied_minutes": 75}
OWNER_DURATION = {"mode": "OWNER_DEFINED", "minutes": None, "rule_note": None}
FIXED_DURATION = {"mode": "FIXED", "minutes": 65, "rule_note": None}


@pytest_asyncio.fixture
async def approval_pg(pricing_pg):
    try:
        yield pricing_pg
    finally:
        async with pricing_pg.migrator.begin() as c:
            await c.execute(text("TRUNCATE app.approval_requests,app.owner_decisions"))


def contract(price=MANUAL, duration=OWNER_DURATION, deposit="NONE"):
    bundle = pricing_bundle(price)
    bundle["services"][0]["duration"] = duration
    bundle["services"][0]["deposit"] = {"mode": deposit, "amount_minor": None, "percent": None}
    return bundle


def endpoint(cid, request):
    return f"{route(cid)}/{request}/approvals"


def source_url(detail, source):
    return f"{detail}/sources/{source['message_id']}?source_version={source['source_version']}"


async def owner_post(auth, url, token, body):
    result = await auth.client.post(url, json=body, headers=token)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


async def owner_open(auth, url, token, revision="1"):
    result = await owner_post(auth, url, token, {"expected_revision": revision})
    if result:
        assert result["request_revision"] == revision
        assert result["assignee_user_account_id"] == str(UA)
    return result


async def owner_get(auth, url):
    result = await auth.client.get(url)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()


async def assert_denial(auth, url, token, body, status, code=None):
    result = await auth.client.post(url, headers=token, json=body)
    assert result.status_code == status, result.text
    if code:
        assert result.json()["error"]["code"] == code


async def test_two_approvals_same_dialog_replay_exact_edition_in_human(approval_pg, auth):
    h = approval_pg
    published = await publish(h, contract())
    token = await sign_in(auth)
    cid, worker, model, delivery, a = await draft_for_size(h, auth, token, "20 mm")
    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {
        "idea": "bird",
        "placement": "shoulder",
        "approximate_size": "21 mm",
        "style": "linework",
    }
    model.switch = True
    await next_turn(h, worker, "Separate bird shoulder, 21 mm, linework")
    b = await create_draft(auth, cid, token, await summary(h, cid))
    await control(h, cid, "TAKEOVER")
    before = await query(
        h, "SELECT to_jsonb(c) AS row FROM app.conversations c WHERE id=:cid", cid=cid
    )
    outbox = await scalar(h, "SELECT count(*) FROM app.outbox_events WHERE workspace_id=:w", w=A)
    assert before[0]["row"]["control_mode"] == "HUMAN"
    a_url, b_url = endpoint(cid, a), endpoint(cid, b)
    first, duplicate, second = await asyncio.gather(
        owner_open(auth, a_url, token),
        owner_open(auth, a_url, token),
        owner_open(auth, b_url, token),
    )
    assert first == duplicate
    assert first["approval_id"] != second["approval_id"]
    for approval, request, size in ((first, a, "20 mm"), (second, b, "21 mm")):
        assert approval["request_id"] == request and approval["status"] == "PENDING"
        assert approval["basis"]["release_id"] == published["release_id"]
        assert approval["basis"]["deposit"]["mode"] == "NONE"
        assert (
            approval["basis"]["amount_minor"] is None
            and approval["basis"]["occupied_minutes"] is None
        )
        fact = next(f for f in approval["basis"]["facts"] if f["field"] == "approximate_size")
        assert (fact["value"], fact["source"]["message_id"]) == (
            size,
            approval["basis"]["intent_source"]["message_id"],
        )
    assert first["basis"]["intent_source"] != second["basis"]["intent_source"]
    page_url = f"/api/v1/workspaces/{A}/service-approvals"
    assert {c["approval_id"] for c in (await owner_get(auth, page_url))["items"]} == {
        first["approval_id"],
        second["approval_id"],
    }
    first_url = a_url + "/" + first["approval_id"]
    pinned = first["basis"]["intent_source"]
    source = await owner_get(auth, source_url(first_url, pinned))
    assert source == pinned | {
        "workspace_id": str(A),
        "business_id": first["business_id"],
        "client_id": first["client_id"],
        "conversation_id": str(cid),
        "request_id": a,
        "approval_id": first["approval_id"],
        "content_type": "TEXT",
        "text": "flower forearm linework 20 mm",
    }
    foreign_source = second["basis"]["intent_source"]
    assert (await auth.client.get(source_url(first_url, foreign_source))).status_code == 404
    wrong_version = pinned | {"source_version": "0" * 64}
    assert (await auth.client.get(source_url(first_url, wrong_version))).status_code == 404
    result, replay = await asyncio.gather(
        owner_post(auth, first_url, token, CONFIRM | {"note": "  Test exact note  "}),
        owner_post(auth, first_url, token, CONFIRM | {"note": "  Test exact note  "}),
    )
    assert (
        result == replay == await owner_open(auth, a_url, token) == await owner_get(auth, first_url)
    )
    decision = result["decision"]
    assert result["authorization_current"] is True and result["version"] == "2"
    assert (
        decision["actor_user_account_id"] == str(UA)
        and decision["authorized_action"] == "PREPARE_QUOTE"
    )
    assert decision["submitted"] == CONFIRM | {"note": "  Test exact note  "}
    assert decision["terms"] == {
        "currency": "RUB",
        "amount_minor": 395_001,
        "price_range": None,
        "occupied_minutes": 75,
        "price_reference_id": decision["decision_id"],
        "duration_reference_id": decision["decision_id"],
    }
    assert await owner_get(auth, b_url + "/" + second["approval_id"]) == second
    await assert_denial(
        auth, first_url, token, CONFIRM | {"occupied_minutes": 76}, 409, "IDEMPOTENCY_KEY_CONFLICT"
    )
    await assert_denial(auth, b_url + "/" + first["approval_id"], token, CONFIRM, 404, "NOT_FOUND")
    assert (
        await query(h, "SELECT to_jsonb(c) AS row FROM app.conversations c WHERE id=:cid", cid=cid)
        == before
    )
    assert (
        await scalar(h, "SELECT count(*) FROM app.outbox_events WHERE workspace_id=:w", w=A)
        == outbox
    )
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.owner_decisions WHERE approval_id=:id",
            id=UUID(first["approval_id"]),
        )
        == 1
    )
    with pytest.raises(IntegrityError, match="OWNER_DECISION_IMMUTABLE"):
        async with h.migrator.begin() as c:
            await c.execute(
                text("UPDATE app.owner_decisions SET occupied_minutes=76 WHERE id=:id"),
                {"id": UUID(decision["decision_id"])},
            )
    print(
        "Q3 A",
        a,
        first["approval_id"],
        decision["decision_id"],
        "395001 kopeks / 75 min; B",
        b,
        second["approval_id"],
        "PENDING",
        flush=True,
    )


@pytest.mark.parametrize("known", ["price", "price-prepaid", "duration", "both"])
async def test_one_missing_dimension_keeps_original_basis(approval_pg, auth, known):
    h = approval_pg
    published = await publish(
        h,
        contract(
            MANUAL if known == "duration" else FIXED,
            OWNER_DURATION if known.startswith("price") else FIXED_DURATION,
            "FULL_PREPAYMENT" if known in {"duration", "price-prepaid"} else "NONE",
        ),
    )
    token = await sign_in(auth)
    cid, _, _, _, request = await draft_for_size(h, auth, token, "20 mm")
    url = endpoint(cid, request)
    card = await owner_open(auth, url, token)
    if known == "both":
        assert card is None
        assert (await owner_get(auth, f"/api/v1/workspaces/{A}/service-approvals"))["items"] == []
        return
    assert card["basis"]["release_id"] == published["release_id"]
    detail = url + "/" + card["approval_id"]
    await assert_denial(auth, detail, token, CONFIRM, 422, "INVALID_INPUT")
    body = (
        AB
        | {"operation": "APPROVE"}
        | ({"occupied_minutes": 80} if known.startswith("price") else {"amount_minor": 460_000})
    )
    result = await owner_post(auth, detail, token, body)
    decision = result["decision"]
    assert await owner_post(auth, detail, token, body) == await owner_get(auth, detail) == result
    if known.startswith("price"):
        assert result["basis"]["deposit"]["mode"] == (
            "FULL_PREPAYMENT" if known == "price-prepaid" else "NONE"
        )
        assert decision["terms"]["price_range"] is None
        assert (decision["terms"]["amount_minor"], decision["terms"]["occupied_minutes"]) == (
            120_001,
            80,
        )
        assert decision["terms"]["price_reference_id"] == card["basis"]["price_calculation_id"]
        assert decision["terms"]["duration_reference_id"] == decision["decision_id"]
        assert decision["submitted"]["amount_minor"] is None
    else:
        assert result["basis"]["deposit"]["mode"] == "FULL_PREPAYMENT"
        assert (decision["terms"]["amount_minor"], decision["terms"]["occupied_minutes"]) == (
            460_000,
            65,
        )
        assert decision["terms"]["price_reference_id"] == decision["decision_id"]
        assert decision["terms"]["duration_reference_id"] == card["basis"]["assessment_id"]
        assert decision["submitted"]["occupied_minutes"] is None
    print(
        "Q3 partial",
        known,
        decision["decision_id"],
        decision["terms"],
        result["basis"]["deposit"]["mode"],
        flush=True,
    )


@pytest.mark.parametrize(
    ("operation", "status"), [("CLARIFY", "CLARIFICATION"), ("DECLINE", "DECLINED")]
)
async def test_clarify_and_decline_are_recorded_without_values(
    approval_pg, auth, operation, status
):
    h = approval_pg
    await publish(h, contract())
    token = await sign_in(auth)
    cid, _, _, _, request = await draft_for_size(h, auth, token, "20 mm")
    url = endpoint(cid, request)
    card = await owner_open(auth, url, token)
    target = url + "/" + card["approval_id"]
    body = AB | {"operation": operation, "note": "Check the synthetic fact 5000 and 65"}
    await assert_denial(auth, target, token, body | {"amount_minor": 500_000}, 422, "INVALID_INPUT")
    result = await owner_post(auth, target, token, body)
    assert result["status"] == status
    assert result["decision"]["terms"] is result["decision"]["authorized_action"] is None
    assert result["decision"]["submitted"] == body | {
        "amount_minor": None,
        "occupied_minutes": None,
    }
    assert not result["authorization_current"]
    assert await owner_post(auth, target, token, body) == await owner_get(auth, target)


@pytest.mark.parametrize("change", ["EDIT", "DELETE", "RULE", "REVISION", "EXPIRE", "WITHDRAW"])
async def test_old_edition_cannot_be_used_after_material_change(approval_pg, auth, change):
    h = approval_pg
    await publish(h, contract())
    token = await sign_in(auth)
    cid, worker, model, delivery, request = await draft_for_size(
        h, auth, token, "20 mm", telegram=change in {"EDIT", "DELETE"}
    )
    url = endpoint(cid, request)
    card = await owner_open(auth, url, token)
    target = url + "/" + card["approval_id"]
    original = await owner_post(auth, target, token, CONFIRM)
    expected, error = "STALE", "STALE_STATE"
    if change in {"EDIT", "DELETE"}:
        pinned_url = source_url(target, card["basis"]["intent_source"])
        assert "20 mm" in (await owner_get(auth, pinned_url))["text"]
        source = (
            await query(
                h,
                "SELECT provider_message_id,provider_chat_id FROM app.messages WHERE id=:id",
                id=UUID(card["basis"]["intent_source"]["message_id"]),
            )
        )[0]
        _, _, material = await process(
            h,
            raw(
                next(COUNTER) + 900_000,
                int(source["provider_message_id"]),
                kind=change,
                value="Synthetic correction 35 mm",
                chat=source["provider_chat_id"],
                sender=source["provider_chat_id"],
                date=40,
            ),
        )
        assert material.code == "MATERIAL_PROCESSED"
        preview = await auth.client.get(pinned_url)
        assert (preview.status_code, preview.json()) == (
            (409, {"error": {"code": "STALE_STATE"}})
            if change == "EDIT"
            else (404, {"error": {"code": "NOT_FOUND"}})
        )
    elif change == "RULE":
        await publish(h, contract(FIXED))
    elif change == "REVISION":
        await worker.execute(await claim_job(h, delivery["send_job_id"]))
        model.values = {"approximate_size": "28 mm"}
        model.correction = True
        await next_turn(h, worker, "Corrected size 28 mm")
        projection = await summary(h, cid)
        draft = (await auth.client.get(route(cid), params={"request_id": request})).json()
        revised = await auth.client.patch(
            f"{route(cid)}/{request}",
            headers=token | {"Idempotency-Key": str(uuid4())},
            json=revise_body(projection, draft, "approximate_size"),
        )
        assert (revised.status_code, revised.json()) == (200, {"request_id": request})
    elif change == "WITHDRAW":
        expected, error = "REVOKED", "APPROVAL_REVOKED"
        await owner_post(
            auth, target, token, AB | {"expected_version": "2", "operation": "WITHDRAW"}
        )
    else:
        expected, error = "EXPIRED", "APPROVAL_EXPIRED"
        async with h.migrator.begin() as c:
            await c.execute(
                text("ALTER TABLE app.approval_requests DISABLE TRIGGER owner_decision_immutable")
            )
            await c.execute(
                text(
                    "UPDATE app.approval_requests SET created_at=now()-interval '25 hours', expires_at=now()-interval '1 hour' WHERE id=:id"
                ),
                {"id": UUID(card["approval_id"])},
            )
            await c.execute(
                text("ALTER TABLE app.approval_requests ENABLE TRIGGER owner_decision_immutable")
            )
    check = await owner_get(auth, target)
    assert (
        check["status"] == expected
        and check["decision"] == original["decision"]
        and not check["authorization_current"]
    )
    await assert_denial(auth, target, token, CONFIRM, 409, error)
    fresh = await owner_open(auth, url, token, "2" if change == "REVISION" else "1")
    assert fresh["approval_id"] != card["approval_id"] and fresh["status"] == "PENDING"
    assert await owner_get(auth, target) == check
    print("Q3 invalidation", change, expected, error, flush=True)


async def test_cross_scope_rights_revocation_and_durable_downgrade_refusal(approval_pg, auth):
    h = approval_pg
    await publish(h, contract())
    token = await sign_in(auth)
    cid, _, _, _, request = await draft_for_size(h, auth, token, "20 mm")
    url = endpoint(cid, request)
    card = await owner_open(auth, url, token)
    target = url + "/" + card["approval_id"]
    await owner_post(auth, target, token, CONFIRM)
    other, *_ = await application(h, {"idea": "separate client"})
    for foreign, status in (
        (endpoint(other, request), 404),
        (
            f"/api/v1/workspaces/{B}/businesses/{BB}/intake/conversations/{cid}/service-requests/{request}/approvals",
            403,
        ),
    ):
        foreign_approval = foreign + "/" + card["approval_id"]
        assert (await auth.client.get(foreign_approval)).status_code == status
        assert (
            await auth.client.get(source_url(foreign_approval, card["basis"]["intent_source"]))
        ).status_code == status
        await assert_denial(auth, foreign + "/" + card["approval_id"], token, CONFIRM, status)
    with pytest.raises(AssertionError, match="OWNER_DECISION_DURABLE_DATA"):
        await _migrate("downgrade", "0027")
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN',version=version+1 WHERE (workspace_id,user_account_id)=(:w,:a)"
            ),
            {"w": A, "a": UA},
        )
    try:
        assert (await auth.client.get(target)).status_code == 403
        assert (
            await auth.client.get(source_url(target, card["basis"]["intent_source"]))
        ).status_code == 403
        assert (
            await auth.client.get(f"/api/v1/workspaces/{A}/service-approvals")
        ).status_code == 403
        await assert_denial(auth, target, token, CONFIRM, 403)
    finally:
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER',version=version+1 WHERE (workspace_id,user_account_id)=(:w,:a)"
                ),
                {"w": A, "a": UA},
            )
    assert (await owner_get(auth, target))["status"] == "REVOKED"
    await assert_denial(auth, target, token, CONFIRM, 409, "APPROVAL_REVOKED")
    print(
        "Q3 scope denied 404/403; rights revoked then restored without restoring the old approval",
        flush=True,
    )


async def test_m3_pending_covers_only_the_work_with_the_same_question(approval_pg, auth):
    h = approval_pg
    await publish(h, contract())
    token = await sign_in(auth)
    cid, worker, model, delivery, a = await draft_for_size(h, auth, token, "20 mm")
    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {
        "idea": "bird",
        "placement": "shoulder",
        "approximate_size": "21 mm",
        "style": "linework",
    }
    model.switch = True
    _, delivery = await next_turn(h, worker, "Separate bird shoulder, 21 mm, linework")
    b = await create_draft(auth, cid, token, await summary(h, cid))
    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {}
    model.category = "COVER_UP"
    model.switch = False
    await next_turn(h, worker, "The flower covers an old tattoo")
    projection = await summary(h, cid)
    assert projection["status"] == "OWNER_HANDOFF"
    legacy = await query(
        h, "SELECT id,status FROM app.escalations WHERE conversation_id=:cid", cid=cid
    )
    assert len(legacy) == 1 and legacy[0]["status"] == "PENDING"
    source = source_pin(projection["sources"][-1])
    revised = await auth.client.patch(
        f"{route(cid)}/{a}",
        headers=token | {"Idempotency-Key": str(uuid4())},
        json={
            "expected_revision": "1",
            "expected_version": projection["version"],
            "expected_fingerprint": projection["fingerprint"],
            "selection": "ONE_WORK",
            "source": source,
        },
    )
    assert (revised.status_code, revised.json()) == (200, {"request_id": a})
    first = await owner_open(auth, endpoint(cid, a), token, "2")
    second = await owner_open(auth, endpoint(cid, b), token)
    assert first["related_escalation_id"] == str(legacy[0]["id"])
    assert first["basis"]["complex_work"]["source"] == source
    assert second["related_escalation_id"] is None
    assert first["status"] == second["status"] == "PENDING"
    accepted = await owner_post(auth, endpoint(cid, a) + "/" + first["approval_id"], token, CONFIRM)
    assert accepted["status"] == "APPROVED"
    assert (await owner_get(auth, endpoint(cid, b) + "/" + second["approval_id"]))[
        "status"
    ] == "PENDING"
    assert (
        await query(h, "SELECT id,status FROM app.escalations WHERE conversation_id=:cid", cid=cid)
        == legacy
    )
    print(
        "Q3 M3 linkage",
        legacy[0]["id"],
        "A",
        first["approval_id"],
        "B",
        second["approval_id"],
        flush=True,
    )


@pytest.mark.parametrize(
    ("deposit", "fixed", "percent", "retain_range"),
    [
        pytest.param("NONE", None, None, True, id="none"),
        pytest.param("FIXED_DEPOSIT", 400_000, None, True, id="fixed-at-lower-bound"),
        pytest.param("FIXED_DEPOSIT", 410_000, None, False, id="fixed-above-lower-bound"),
        pytest.param("PERCENT_DEPOSIT", None, 25, False, id="percent-needs-exact-price"),
        pytest.param("FULL_PREPAYMENT", None, None, False, id="full-prepayment-needs-exact-price"),
    ],
)
async def test_r1_provisional_range_depends_on_deposit_and_survives_duration_only_decision(
    approval_pg, auth, deposit, fixed, percent, retain_range
):
    h = approval_pg
    bundle = contract(formula_price(range_add_minor=50_000), deposit=deposit)
    bundle["services"][0]["deposit"].update(amount_minor=fixed, percent=percent)
    await publish(h, bundle)
    token = await sign_in(auth)
    conversation, _, _, _, request = await draft_for_size(h, auth, token, "21 mm")
    url = endpoint(conversation, request)
    calculation = await price(auth, f"{route(conversation)}/{request}/pricing", token)
    price_range = {"lower_minor": 400_000, "upper_minor": 450_000, "authority": "PROVISIONAL"}
    assert (calculation["outcome"], calculation["amount_minor"]) == ("RANGE", None)
    assert price_range == {key: calculation[key] for key in price_range}
    card = await owner_open(auth, url, token)
    detail = url + "/" + card["approval_id"]
    basis = card["basis"]
    assert basis["price_calculation_id"] == calculation["calculation_id"]
    assert basis["amount_minor"] is None and basis["occupied_minutes"] is None
    assert basis["price_range"] == (price_range if retain_range else None)
    minutes_only = AB | {"operation": "APPROVE", "occupied_minutes": 75}
    if not retain_range:
        await assert_denial(auth, detail, token, minutes_only, 422, "INVALID_INPUT")
        assert (await owner_get(auth, detail))["decision"] is None
        if fixed:
            await assert_denial(auth, detail, token, CONFIRM, 409, "NEEDS_CLARIFICATION")
        exact = await owner_post(auth, detail, token, minutes_only | {"amount_minor": 440_000})
        exact_terms = exact["decision"]["terms"]
        assert exact_terms["amount_minor"] == 440_000 and exact_terms["price_range"] is None
        assert exact_terms["price_reference_id"] == exact["decision"]["decision_id"]
        print("R1 range requires exact price", deposit, fixed, flush=True)
        return

    await assert_denial(auth, detail, token, CONFIRM, 422, "INVALID_INPUT")
    approved = await owner_post(auth, detail, token, minutes_only)
    assert approved == await owner_post(auth, detail, token, minutes_only)
    assert approved == await owner_get(auth, detail) == await owner_open(auth, url, token)
    assert approved["status"] == "APPROVED"
    decision = approved["decision"]
    assert decision["submitted"]["amount_minor"] is None
    assert decision["terms"] == {
        "currency": "RUB",
        "amount_minor": None,
        "price_range": price_range,
        "occupied_minutes": 75,
        "price_reference_id": calculation["calculation_id"],
        "duration_reference_id": decision["decision_id"],
    }
    persisted = await query(
        h,
        "SELECT amount_minor,lower_minor,upper_minor,price_reference_id,occupied_minutes "
        "FROM app.owner_decisions WHERE id=:id",
        id=UUID(decision["decision_id"]),
    )
    assert persisted == [
        {
            "amount_minor": None,
            "lower_minor": 400_000,
            "upper_minor": 450_000,
            "price_reference_id": UUID(calculation["calculation_id"]),
            "occupied_minutes": 75,
        }
    ]
    print(
        "R1 RANGE",
        deposit,
        card["approval_id"],
        decision["decision_id"],
        calculation["calculation_id"],
        "400000–450000 PROVISIONAL / 75",
        flush=True,
    )
