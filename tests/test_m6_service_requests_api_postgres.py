"""Owner HTTP admission and scope on the installed service request schema."""

import pytest
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m5_intake_postgres import application, summary
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
    signed_in = await login(auth)
    assert signed_in.status_code == 200
    mutation = headers(auth.client, signed_in.json()["csrf_token"])

    async def create(body, key="request-one"):
        return await auth.client.post(
            url, json=body, headers=mutation | {"Idempotency-Key": key}
        )

    assert (await auth.client.get(url)).json() is None
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
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert await request_count(h, conversation) == 1
    by_id = {"request_id": receipt["request_id"]}
    card = await auth.client.get(url, params=by_id)
    assert card.status_code == 200 and card.headers["Cache-Control"] == "no-store"
    assert (await auth.client.get(url)).json() == card.json()
    assert card.json()["facts"][0]["source"] == (
        (await summary(h, conversation))["facts"][0]["source"] | {"quote": ""}
    )
    assert (await auth.client.get(route(other_conversation), params=by_id)).status_code == 404
    assert (await auth.client.get(route(conversation, business=BA2), params=by_id)).status_code == 404
    assert (await auth.client.get(url, params=list(by_id.items()) * 2)).status_code == 422

    async with h.migrator.begin() as connection:
        await connection.execute(
            text("UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:a"),
            {"w": A, "a": UA},
        )
    try:
        assert (await auth.client.get(url, params=by_id)).status_code == 403
        assert (await create(proposal)).status_code == 403
        assert await request_count(h, conversation) == 1
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text("UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:a"),
                {"w": A, "a": UA},
            )
