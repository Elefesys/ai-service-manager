"""M6.3B through the owner commands and ordinary leased delivery worker."""

import asyncio
import json
from uuid import UUID

import httpx
import pytest
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase, worker_active
from asm.messaging.results import QuoteSendJobClaim, QuoteSendPermit
from asm.messaging.worker import Worker
from asm.telegram.client import TelegramClient
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, control, scalar
from test_m4_reply_rights_postgres import connection, telegram
from test_m5_intake_postgres import next_turn, summary
from test_m6_owner_decisions_postgres import (
    AB,
    FIXED_DURATION,
    contract,
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
from test_m6_pricing_postgres import draft_for_size, formula_price, price, publish, sign_in
from test_m6_service_assessments_api_postgres import create_draft, request_assessment
from test_m6_service_requests_api_postgres import route
from test_tenancy_postgres import A

pytestmark = pytest.mark.integration


class DeliveryWire(ControlledAdapter):
    def __init__(self, h, *, lose_reply=False, barrier=None):
        self.h = h
        self.permits = []
        self.lose_reply = lose_reply
        super().__init__(environment="TEST", barrier=barrier)

    async def send(self, permit):
        assert isinstance(permit, QuoteSendPermit) and permit.provider == "CONTROLLED"
        assert not worker_active()
        assert (
            await scalar(
                self.h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        self.permits.append(permit)
        outcome = await super().send(permit)
        if self.lose_reply:
            raise TimeoutError("synthetic response lost after effect")
        return outcome


async def delivery(h, q):
    return (
        await query(
            h,
            "SELECT i.message_id,i.outbox_id,i.send_job_id,i.hold_reason,"
            "o.status,o.attempt_id,j.status AS job_status,m.text "
            "FROM platform.quote_delivery_intents i "
            "LEFT JOIN app.outbox_events o ON (o.workspace_id,o.id)=(i.workspace_id,i.outbox_id) "
            "LEFT JOIN platform.messaging_jobs j ON (j.workspace_id,j.id)=(i.workspace_id,i.send_job_id) "
            "LEFT JOIN app.messages m ON (m.workspace_id,m.id)=(i.workspace_id,i.message_id) "
            "WHERE (i.workspace_id,i.quote_id)=(:ws,:qid)",
            ws=A,
            qid=UUID(q["quote_id"]),
        )
    )[0]


async def run_quote(h, worker, q):
    record = await delivery(h, q)
    claim = await claim_job(h, record["send_job_id"])
    assert isinstance(claim, QuoteSendJobClaim)
    assert claim.quote_id == UUID(q["quote_id"]) and claim.outbox_id == record["outbox_id"]
    await worker.execute(claim)
    return record


async def input_count(h, conversation):
    return await scalar(
        h,
        "SELECT count(*) FROM app.messages WHERE conversation_id=:c AND direction='INBOUND'",
        c=conversation,
    )


async def exact_ready(h, auth, *, use_telegram=False):
    await publish(h, contract(formula_price(), FIXED_DURATION))
    token = await sign_in(auth)
    cid, _, _, _, request = await draft_for_size(h, auth, token, "20 mm", telegram=use_telegram)
    url = f"{route(cid)}/{request}"
    await price(auth, url + "/pricing", token)
    await request_assessment(auth, url + "/assessment", token)
    view = await owner_get(auth, url + "/quote")
    assert view["status"] == "QUEUED" and view["reason"] is None
    return cid, token, request, url, view["quote"]


def report(label, **data):
    print("M63B", json.dumps({"check": label, **data}, ensure_ascii=False), flush=True)


async def test_two_quotes_same_conversation_owner_continuation_without_inbound(approval_pg, auth):
    h = approval_pg
    await publish(h, contract(formula_price(), FIXED_DURATION))
    token = await sign_in(auth)
    cid, intake, extract, initial, a = await draft_for_size(h, auth, token, "20 mm")
    a_url = f"{route(cid)}/{a}"
    a_assessment, a_price = await asyncio.gather(
        request_assessment(auth, a_url + "/assessment", token),
        price(auth, a_url + "/pricing", token),
    )
    a_view = await owner_get(auth, a_url + "/quote")
    qa = a_view["quote"]
    assert a_view["status"] == "QUEUED"
    assert qa["material"]["price_reference_id"] == a_price["calculation_id"]
    assert qa["material"]["duration_reference_id"] == a_assessment["assessment_id"]
    assert qa["material"]["amount_minor"] == 350_000 and qa["material"]["occupied_minutes"] == 65
    await intake.execute(await claim_job(h, initial["send_job_id"]))
    transport = DeliveryWire(h)
    worker = Worker(h.kernel, transport)
    first = await run_quote(h, worker, qa)
    assert (transport.calls, transport.effects) == (1, 1)
    assert transport.permits[0].text == qa["text"] == first["text"]

    extract.values = dict(
        idea="bird", placement="shoulder", approximate_size="101 mm", style="linework"
    )
    extract.switch = True
    await next_turn(h, intake, "Separate bird shoulder 101 mm linework")
    b = await create_draft(auth, cid, token, await summary(h, cid))
    b_url = f"{route(cid)}/{b}"
    before = await input_count(h, cid)
    await request_assessment(auth, b_url + "/assessment", token)
    assert (await price(auth, b_url + "/pricing", token))["reason"] == "SIZE_OUTSIDE_RULE"
    assert (await owner_get(auth, b_url + "/quote"))["quote"] is None
    approval = await owner_open(auth, b_url + "/approvals", token)
    decision_url = b_url + "/approvals/" + approval["approval_id"]
    body = AB | {"operation": "APPROVE", "amount_minor": 460_000}
    decision, duplicate = await asyncio.gather(
        owner_post(auth, decision_url, token, body), owner_post(auth, decision_url, token, body)
    )
    assert decision == duplicate
    b_view = await owner_get(auth, b_url + "/quote")
    qb = b_view["quote"]
    assert b_view["status"] == "QUEUED"
    assert qb["material"]["price_reference_id"] == decision["decision"]["decision_id"]
    assert qb["material"]["duration_reference_id"] == approval["basis"]["assessment_id"]
    assert qb["material"]["amount_minor"] == 460_000 and qb["material"]["occupied_minutes"] == 65
    assert qa["material"]["request_id"] == a and qb["material"]["request_id"] == b
    assert qa["material"]["intent_source"] != qb["material"]["intent_source"]
    assert qa["quote_id"] != qb["quote_id"] and qa["code"] != qb["code"]
    await run_quote(h, worker, qb)
    assert (transport.calls, transport.effects) == (2, 2)
    assert [p.text for p in transport.permits] == [qa["text"], qb["text"]]
    assert [p.chat_id for p in transport.permits] == [h.intake_scope["chat_id"]] * 2
    await asyncio.gather(
        price(auth, a_url + "/pricing", token), owner_post(auth, decision_url, token, body)
    )
    assert await input_count(h, cid) == before
    for url, q in ((a_url, qa), (b_url, qb)):
        assert await owner_get(auth, url + "/quote") == {
            "quote": q,
            "status": "SENT",
            "reason": None,
        }
        assert q["text"].endswith("\nПринимаю " + q["code"])
        linked = await delivery(h, q)
        assert linked["job_status"] == "SUCCEEDED" and linked["attempt_id"] is not None
    assert await scalar(h, "SELECT count(*) FROM app.quotes WHERE conversation_id=:c", c=cid) == 2
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='SEND_QUOTE_TEXT' AND status IN ('READY','RUNNING')",
            ws=A,
        )
        == 0
    )
    assert (transport.calls, transport.effects) == (2, 2)
    report(
        "two_works",
        conversation=str(cid),
        inbound_after_decision=0,
        works=[
            {
                "request_id": rid,
                "quote_id": q["quote_id"],
                "version": q["version"],
                "code": q["code"],
                "text": q["text"],
                "status": "SENT",
                "calls": 1,
                "effects": 1,
                "replay_calls": 0,
                "replay_effects": 0,
            }
            for rid, q in ((a, qa), (b, qb))
        ],
    )


@pytest.mark.parametrize("deposit", ["NONE", "FIXED_DEPOSIT", "PERCENT_DEPOSIT", "FULL_PREPAYMENT"])
async def test_preliminary_range_respects_published_prepayment(approval_pg, auth, deposit):
    h = approval_pg
    bundle = contract(formula_price(range_add_minor=50_000), FIXED_DURATION, deposit)
    bundle["services"][0]["deposit"].update(
        amount_minor=100_000 if deposit == "FIXED_DEPOSIT" else None,
        percent=25 if deposit == "PERCENT_DEPOSIT" else None,
    )
    await publish(h, bundle)
    token = await sign_in(auth)
    cid, _, _, _, request = await draft_for_size(h, auth, token, "21 mm")
    url = f"{route(cid)}/{request}"
    await price(auth, url + "/pricing", token)
    await request_assessment(auth, url + "/assessment", token)
    view = await owner_get(auth, url + "/quote")
    transport = DeliveryWire(h)
    if deposit in {"PERCENT_DEPOSIT", "FULL_PREPAYMENT"}:
        assert view == {
            "quote": None,
            "status": "NEEDS_CLARIFICATION",
            "reason": "EXACT_PRICE_REQUIRED",
        }
        assert (
            await scalar(h, "SELECT count(*) FROM app.quotes WHERE conversation_id=:c", c=cid) == 0
        )
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='SEND_QUOTE_TEXT'",
                ws=A,
            )
            == 0
        )
        report(
            "range_requires_exact",
            deposit=deposit,
            calls=transport.calls,
            effects=transport.effects,
            status=view["status"],
            reason=view["reason"],
        )
        return
    q = view["quote"]
    assert view["status"] == "QUEUED"
    assert q["material"]["amount_minor"] is None
    assert q["material"]["price_range"] == {
        "authority": "PROVISIONAL",
        "lower_minor": 400_000,
        "upper_minor": 450_000,
    }
    assert "Предварительный диапазон цены — 4\u202f000–4\u202f500 ₽." in q["text"]
    await run_quote(h, Worker(h.kernel, transport), q)
    assert (transport.calls, transport.effects) == (1, 1)
    assert (await owner_get(auth, url + "/quote"))["status"] == "SENT"
    report(
        "range_delivered",
        deposit=deposit,
        quote_id=q["quote_id"],
        text=q["text"],
        calls=1,
        effects=1,
    )


@pytest.mark.parametrize(
    "reason", ["HUMAN_CONTROL", "CHANNEL_WINDOW_CLOSED", "CHANNEL_RIGHTS_UNAVAILABLE"]
)
async def test_local_quote_block_prevents_even_telegram_probe(approval_pg, auth, reason):
    h = approval_pg
    cid, _, _, url, q = await exact_ready(h, auth, use_telegram=True)
    if reason == "HUMAN_CONTROL":
        await control(h, cid, "TAKEOVER")
    elif reason == "CHANNEL_WINDOW_CLOSED":
        # Fault only on the owned disposable conversation. Preserve the quote and
        # its sources and expire the existing transport window after enqueue.
        await scalar(
            h,
            "UPDATE app.conversations SET last_client_inbound_at=clock_timestamp()-interval '25 hours' WHERE id=:c RETURNING id",
            c=cid,
        )
    else:
        await scalar(
            h,
            "UPDATE platform.telegram_connection_state SET can_reply=false WHERE connection_id=:id RETURNING connection_id",
            id=h.telegram_connection,
        )
    version_before_worker = await scalar(
        h, "SELECT version FROM app.conversations WHERE id=:c", c=cid
    )
    seen = []

    async def wire(req):
        seen.append(req.url.path.rsplit("/", 1)[-1])
        return connection()

    controlled = DeliveryWire(h)
    client = telegram(wire)
    try:
        record = await run_quote(h, Worker(h.kernel, controlled, telegram=client), q)
    finally:
        await client.aclose()
    assert not seen and (controlled.calls, controlled.effects) == (0, 0)
    saved = await delivery(h, q)
    assert saved["attempt_id"] is None and saved["outbox_id"] == record["outbox_id"]
    assert (
        await scalar(h, "SELECT version FROM app.conversations WHERE id=:c", c=cid)
        == version_before_worker
    )
    assert await owner_get(auth, url + "/quote") == {"quote": q, "status": "HELD", "reason": reason}
    report("local_block", quote_id=q["quote_id"], reason=reason, probes=0, calls=0, effects=0)


async def test_telegram_quote_newly_denied_rights_do_not_start_dispatch(approval_pg, auth):
    h = approval_pg
    _, _, _, url, q = await exact_ready(h, auth, use_telegram=True)
    requests = []

    async def wire(req):
        requests.append(req.url.path.rsplit("/", 1)[-1])
        assert not worker_active()
        assert requests == ["getBusinessConnection"]
        return connection(reply=False)

    client = telegram(wire)
    transport = DeliveryWire(h)
    try:
        await run_quote(h, Worker(h.kernel, transport, telegram=client), q)
    finally:
        await client.aclose()
    assert requests == ["getBusinessConnection"] and (transport.calls, transport.effects) == (0, 0)
    assert (await delivery(h, q))["attempt_id"] is None
    view = await owner_get(auth, url + "/quote")
    assert view["status"] in {"HELD", "FAILED"} and view["reason"] == "CHANNEL_RIGHTS_UNAVAILABLE"


async def test_telegram_quote_requires_the_exact_test_transport(approval_pg, auth):
    class OtherTransport(httpx.MockTransport):
        pass

    h = approval_pg
    _, _, _, url, q = await exact_ready(h, auth, use_telegram=True)
    requests = []

    async def wire(req):
        requests.append(req.url.path)
        return connection()

    synthetic = telegram(wire)
    client = TelegramClient(synthetic.settings, transport=OtherTransport(wire))
    controlled = DeliveryWire(h)
    try:
        assert synthetic.synthetic_ai and not client.synthetic_ai
        await run_quote(h, Worker(h.kernel, controlled, telegram=client), q)
    finally:
        await client.aclose()
        await synthetic.aclose()
    assert not requests and (controlled.calls, controlled.effects) == (0, 0)
    assert (await delivery(h, q))["attempt_id"] is None
    view = await owner_get(auth, url + "/quote")
    assert (view["status"], view["reason"]) == ("HELD", "CHANNEL_RIGHTS_UNAVAILABLE")


async def test_quote_uses_existing_telegram_text_wire_for_exact_recipient(approval_pg, auth):
    h = approval_pg
    _, token, _, url, q = await exact_ready(h, auth, use_telegram=True)
    requests = []
    effects = 0
    target = h.intake_scope["chat"]

    async def wire(req):
        nonlocal effects
        assert not worker_active()
        method = req.url.path.rsplit("/", 1)[-1]
        requests.append(method)
        if method == "getBusinessConnection":
            return connection()
        assert method == "sendMessage" and req.method == "POST"
        body = json.loads(req.content)
        external = connection().json()["result"]["id"]
        assert body == {"business_connection_id": external, "chat_id": target, "text": q["text"]}
        effects += 1
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 91231,
                    "chat": {"id": int(target), "type": "private"},
                    "business_connection_id": external,
                },
            },
        )

    client = telegram(wire)
    controlled = DeliveryWire(h)
    try:
        await run_quote(h, Worker(h.kernel, controlled, telegram=client), q)
        await price(auth, url + "/pricing", token)
    finally:
        await client.aclose()
    assert requests == ["getBusinessConnection", "sendMessage"]
    assert effects == 1 and (controlled.calls, controlled.effects) == (0, 0)
    assert await owner_get(auth, url + "/quote") == {"quote": q, "status": "SENT", "reason": None}
    report("telegram_mock_wire", quote_id=q["quote_id"], probes=1, calls=1, effects=1)


@pytest.mark.parametrize("fault", ["lost_response", "restart_before_finalize"])
async def test_quote_unknown_survives_restart_without_second_effect(approval_pg, auth, fault):
    h = approval_pg
    _, token, _, url, q = await exact_ready(h, auth)

    async def interrupt(stage):
        if stage == "before_finalize" and fault == "restart_before_finalize":
            raise ConnectionError("synthetic worker exits after the effect, before finalization")

    transport = DeliveryWire(h, lose_reply=fault == "lost_response", barrier=interrupt)
    worker = Worker(h.kernel, transport)
    if fault == "restart_before_finalize":
        with pytest.raises(ConnectionError, match="synthetic worker exits"):
            await run_quote(h, worker, q)
        open_attempt = await delivery(h, q)
        assert open_attempt["status"] == "DISPATCHING" and open_attempt["attempt_id"] is not None
        await scalar(
            h,
            "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
            id=open_attempt["send_job_id"],
        )
    else:
        await run_quote(h, worker, q)
        assert (await owner_get(auth, url + "/quote"))["status"] == "UNKNOWN"
    assert (transport.calls, transport.effects) == (1, 1)
    restarted_transport = DeliveryWire(h)
    restarted = Worker(MessagingDatabase(h.runtime.engine, environment="TEST"), restarted_transport)
    await restarted.database.recover_expired()
    assert await owner_get(auth, url + "/quote") == {
        "quote": q,
        "status": "UNKNOWN",
        "reason": "UNKNOWN_EXTERNAL_RESULT",
    }
    await price(auth, url + "/pricing", token)
    record = await delivery(h, q)
    assert record["status"] == "UNKNOWN" and record["job_status"] == "DEAD"
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='SEND_QUOTE_TEXT' AND status IN ('READY','RUNNING')",
            ws=A,
        )
        == 0
    )
    assert (restarted_transport.calls, restarted_transport.effects) == (0, 0)
    report(
        "unknown_after_restart",
        fault=fault,
        quote_id=q["quote_id"],
        status="UNKNOWN",
        calls=1,
        effects=1,
        restart_calls=0,
        restart_effects=0,
    )
