"""Owner HTTP admission and scope on the installed service request schema."""

import pytest
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m3_1_native_context_postgres import claim_job
from test_m5_intake_postgres import application, next_turn, summary
from test_m6_service_requests_postgres import create_body, request_count
from test_m6_service_requests_postgres import db as db
from test_m6_service_requests_postgres import intake_pg as intake_pg
from test_m6_service_requests_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_service_requests_postgres import search_pg as search_pg
from test_m6_service_requests_postgres import seeded as seeded
from test_m6_service_requests_postgres import service_request_pg as service_request_pg
from test_tenancy_postgres import BA, BA2, UA, A

pytestmark = pytest.mark.integration


def route(conversation, *, business=BA):
    return (
        f"/api/v1/workspaces/{A}/businesses/{business}/intake"
        f"/conversations/{conversation}/service-requests"
    )


async def test_q1_http_validates_inputs_and_reauthorizes_read_and_receipt_replay(
    service_request_pg, auth
):
    h = service_request_pg
    conversation, _, _, _, _ = await application(h, {"idea": "flower"})
    other_conversation, _, _, _, _ = await application(h, {"idea": "flower"})
    url = route(conversation)
    proposal = create_body(await summary(h, conversation))
    assert (await auth.client.get(url)).status_code == 401
    assert (await auth.client.get(url + "/cards")).status_code == 401
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])

    async def create(body, key="request-one"):
        return await auth.client.post(url, json=body, headers=mutation | {"Idempotency-Key": key})

    assert (await auth.client.get(url)).json() is None
    assert (await auth.client.get(url + "/cards")).json() == {"items": []}
    missing_csrf = await auth.client.post(
        url,
        json=proposal,
        headers={"Origin": mutation["Origin"], "Idempotency-Key": "missing-csrf"},
    )
    assert missing_csrf.status_code == 403
    assert (await create(proposal | {"facts": []})).status_code == 422
    unclear = await create(proposal | {"selection": "UNCLEAR"})
    assert unclear.status_code == 409 and unclear.json()["error"]["code"] == "NEEDS_CLARIFICATION"
    assert await request_count(h, conversation) == 0

    accepted = await create(proposal)
    assert accepted.status_code == 200, accepted.text
    receipt = accepted.json()
    assert set(receipt) == {"request_id"}
    assert (await create(proposal)).json() == receipt
    assert (await create(proposal, key="another-tab")).json() == receipt
    conflict = await create(proposal | {"fields": []})
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    )
    assert await request_count(h, conversation) == 1
    by_id = {"request_id": receipt["request_id"]}
    card = await auth.client.get(url, params=by_id)
    assert card.status_code == 200 and card.headers["Cache-Control"] == "no-store"
    listed = await auth.client.get(url + "/cards")
    assert listed.status_code == 200 and listed.headers["Cache-Control"] == "no-store"
    assert listed.json() == {
        "items": [
            {
                **{
                    name: card.json()[name]
                    for name in ("request_id", "revision", "service_name", "intent_source")
                },
                "idea": "flower",
            }
        ]
    }
    assert await request_count(h, conversation) == 1
    assert (await create(proposal | {"fields": []}, key="existing-empty")).json() == receipt
    assert (await auth.client.get(url, params=by_id)).json() == card.json()
    assert (await auth.client.get(url)).json() == card.json()
    assert card.json()["facts"][0]["source"] == (
        (await summary(h, conversation))["facts"][0]["source"] | {"quote": ""}
    )
    assert (await auth.client.get(route(other_conversation), params=by_id)).status_code == 404
    assert (await auth.client.get(route(other_conversation) + "/cards")).json() == {"items": []}
    assert (
        await auth.client.get(route(conversation, business=BA2), params=by_id)
    ).status_code == 404
    assert (await auth.client.get(url, params=list(by_id.items()) * 2)).status_code == 422

    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:a"
            ),
            {"w": A, "a": UA},
        )
    try:
        assert (await auth.client.get(url, params=by_id)).status_code == 403
        assert (await auth.client.get(url + "/cards")).status_code == 403
        assert (await create(proposal)).status_code == 403
        assert await request_count(h, conversation) == 1
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:a"
                ),
                {"w": A, "a": UA},
            )


async def test_r1_http_explicit_revision_uses_source_and_preserves_other_fields(
    service_request_pg, auth
):
    h = service_request_pg
    conversation, worker, model, _, delivery = await application(
        h, {"idea": "flower", "approximate_size": "8 cm"}
    )
    url = route(conversation)
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])
    proposal = create_body(await summary(h, conversation))
    created = await auth.client.post(
        url, json=proposal, headers=mutation | {"Idempotency-Key": "revision-create"}
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["request_id"]
    selected = {"request_id": request_id}
    original = (await auth.client.get(url, params=selected)).json()

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"approximate_size": "12 cm"}
    model.correction = True
    await next_turn(h, worker, "For the flower, the size is now 12 cm")
    projection = await summary(h, conversation)
    fact = next(item for item in projection["facts"] if item["field"] == "approximate_size")
    body = {
        "expected_revision": original["revision"],
        "expected_version": projection["version"],
        "expected_fingerprint": projection["fingerprint"],
        "field": "approximate_size",
        "source": {name: fact["source"][name] for name in ("message_id", "source_version")},
        "selection": "ONE_WORK",
    }
    revision_url = f"{url}/{request_id}"

    async def revise(body, key="explicit-revision", *, path=revision_url):
        return await auth.client.patch(path, json=body, headers=mutation | {"Idempotency-Key": key})

    missing_csrf = await auth.client.patch(
        revision_url,
        json=body,
        headers={"Origin": mutation["Origin"], "Idempotency-Key": "no-csrf"},
    )
    assert missing_csrf.status_code == 403
    assert (await revise(body | {"value": "99 cm"})).status_code == 422
    assert (await auth.client.get(url, params=selected)).json() == original

    saved = await revise(body)
    assert saved.status_code == 200, saved.text
    assert saved.json() == selected and saved.headers["Cache-Control"] == "no-store"
    assert (await revise(body)).json() == selected
    stale = await revise(body, key="stale-tab")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_STATE"
    card = (await auth.client.get(url, params=selected)).json()
    assert card["revision"] == "2"
    assert card["intent_source"] == original["intent_source"]
    assert {item["field"]: item for item in card["facts"]} == {
        **{item["field"]: item for item in original["facts"]},
        "approximate_size": fact | {"source": fact["source"] | {"quote": ""}},
    }
    other_conversation, _, _, _, _ = await application(h, {"idea": "bird"})
    other_url = f"{route(other_conversation)}/{request_id}"
    assert (await revise(body, "foreign-target", path=other_url)).status_code == 404
    assert (await auth.client.get(url, params=selected)).json() == card
    assert await request_count(h, conversation) == 1
