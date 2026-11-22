"""A held quote needs fresh owner authority before its existing intent can send."""

from uuid import UUID

import pytest
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, control, reconcile
from test_m6_owner_decisions_postgres import (
    AB,
    CONFIRM,
    contract,
    endpoint,
    owner_get,
    owner_open,
    owner_post,
)
from test_m6_owner_decisions_postgres import approval_pg as approval_pg
from test_m6_owner_decisions_postgres import assessment_pg as assessment_pg
from test_m6_owner_decisions_postgres import auth as auth
from test_m6_owner_decisions_postgres import db as db
from test_m6_owner_decisions_postgres import intake_pg as intake_pg
from test_m6_owner_decisions_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_owner_decisions_postgres import pricing_pg as pricing_pg
from test_m6_owner_decisions_postgres import search_pg as search_pg
from test_m6_owner_decisions_postgres import seeded as seeded
from test_m6_owner_decisions_postgres import service_request_pg as service_request_pg
from test_m6_pricing_postgres import draft_for_size, publish, sign_in
from test_m6_service_requests_api_postgres import route

pytestmark = pytest.mark.integration


async def pending_terms(h, auth):
    await publish(h, contract())
    token = await sign_in(auth)
    conversation, worker, _, _, request = await draft_for_size(h, auth, token, "20 mm")
    root = endpoint(conversation, request)
    approval = await owner_open(auth, root, token)
    approval_url = f"{root}/{approval['approval_id']}"
    return conversation, worker, token, approval_url, f"{route(conversation)}/{request}/quote"


async def delivery(h, version):
    rows = await query(
        h,
        """SELECT i.send_job_id, i.outbox_id, i.message_id, j.status AS job_status,
             b.attempt_id, b.status AS outbox_status
           FROM platform.quote_delivery_intents i
           LEFT JOIN platform.messaging_jobs j ON (j.workspace_id,j.id)=(i.workspace_id,i.send_job_id)
           LEFT JOIN app.outbox_events b ON (b.workspace_id,b.id)=(i.workspace_id,i.outbox_id)
           WHERE i.quote_id=:version""",
        version=UUID(version),
    )
    (row,) = rows
    return row


@pytest.mark.parametrize("queued_before_takeover", [False, True], ids=["held", "queued"])
async def test_explicit_resume_preserves_one_never_dispatched_intent(
    approval_pg, auth, queued_before_takeover
):
    h = approval_pg
    conversation, worker, token, approval_url, quote_url = await pending_terms(h, auth)
    if not queued_before_takeover:
        await control(h, conversation, "TAKEOVER")
    await owner_post(auth, approval_url, token, CONFIRM)
    quote = await owner_get(auth, quote_url)
    version = quote["quote"]["quote_id"]
    before = await delivery(h, version)
    calls, effects = h.adapter.calls, h.adapter.effects

    if queued_before_takeover:
        assert quote["status"] == "QUEUED" and before["send_job_id"]
        await control(h, conversation, "TAKEOVER")
        await worker.execute(await claim_job(h, before["send_job_id"]))
        assert (await delivery(h, version))["outbox_status"] == "FAILED"
    else:
        assert all(value is None for value in before.values())
    assert await owner_get(auth, quote_url) == {
        "quote": quote["quote"],
        "status": "HELD",
        "reason": "HUMAN_CONTROL",
    }
    assert (h.adapter.calls, h.adapter.effects) == (calls, effects)

    await reconcile(h, conversation)
    await control(h, conversation, "RESUME")
    queued = await delivery(h, version)
    assert queued["attempt_id"] is None and queued["job_status"] == "READY"
    if queued_before_takeover:
        for key in ("send_job_id", "outbox_id", "message_id"):
            assert queued[key] == before[key]
    await worker.execute(await claim_job(h, queued["send_job_id"]))
    assert (h.adapter.calls, h.adapter.effects) == (calls + 1, effects + 1)
    assert await owner_get(auth, quote_url) == {
        "quote": quote["quote"],
        "status": "SENT",
        "reason": None,
    }


async def test_withdrawn_decision_blocks_queued_quote_before_call(approval_pg, auth):
    h = approval_pg
    _, worker, token, approval_url, quote_url = await pending_terms(h, auth)
    await owner_post(auth, approval_url, token, CONFIRM)
    quote = await owner_get(auth, quote_url)
    assert quote["status"] == "QUEUED"
    version = quote["quote"]["quote_id"]
    queued = await delivery(h, version)
    await owner_post(
        auth, approval_url, token, AB | {"expected_version": "2", "operation": "WITHDRAW"}
    )
    calls, effects = h.adapter.calls, h.adapter.effects
    await worker.execute(await claim_job(h, queued["send_job_id"]))
    assert (h.adapter.calls, h.adapter.effects) == (calls, effects)
    stopped = await delivery(h, version)
    assert stopped["outbox_status"] == "FAILED" and stopped["attempt_id"] is None
    assert await owner_get(auth, quote_url) == {
        "quote": quote["quote"],
        "status": "HELD",
        "reason": "REVOKED",
    }
