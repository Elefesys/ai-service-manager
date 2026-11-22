"""M6.4A through persisted Inbox, the standard worker and a controlled transport."""

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from asm.ai.contracts import IntakeGatewayConfig, ServiceIntentGatewayConfig
from asm.ai.runtime_contracts import ServiceIntentRuntimeReceipt
from asm.ai.runtime_settings import IntakeRuntimeSettings
from asm.foundation import create_worker
from asm.intake.projection import AMBIGUOUS_QUESTION
from asm.messaging.worker import Worker
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, control, incoming, reconcile, scalar
from test_m4_agent import config
from test_m4_delivery_postgres import run_turn
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_intake_postgres import Extractor, summary
from test_m5_intake_v7_integration_postgres import session
from test_m5_portfolio_runtime_postgres import PrivateBytes
from test_m6_owner_decisions_postgres import AB, FIXED_DURATION, contract, owner_get, owner_post
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
from test_m6_pricing_postgres import formula_price, publish, sign_in
from test_m6_quote_delivery_postgres import DeliveryWire, delivery, input_count, run_quote
from test_m6_service_requests_api_postgres import route
from test_tenancy_postgres import BA, A

pytestmark = pytest.mark.integration

FLOWER = dict(idea="flower", placement="forearm", approximate_size="20 mm", style="linework")
SWALLOW = dict(idea="swallow", placement="shoulder", approximate_size="101 mm", style="linework")
PREPARE = "prepare_service_request"
OWNER_DECISION = "request_owner_decision"


class IntentModel(Extractor):
    def __init__(self, route):
        super().__init__(route, FLOWER)
        self.intents = (PREPARE,)
        self.source_override = None
        self.amount = None

    async def complete(self, request):
        response = await super().complete(request)
        if request.config.prompt_revision == "conversation_v7":
            return response
        result = json.loads(response.output_json)
        context = next(
            value
            for message in request.request.messages
            if message.role == "context"
            if (value := json.loads(message.text)).get("revision") == "conversation_intake_v1"
        )
        source = context["sources"][-1]
        source = {name: source[name] for name in ("message_id", "source_version")}
        source.update(self.source_override or {})
        result.update(
            kind="no_reply",
            text=None,
            reason="REQUEST_PREPARATION",
            intents=[{"name": name, "source": source} for name in self.intents],
        )
        if self.amount is not None:
            result["intents"][0]["amount_minor"] = self.amount
        return response.model_copy(update={"output_json": json.dumps(result)})


async def receive(h, worker, scope, value):
    receipt = await incoming(h, next(COUNTER), process=False, **scope, text=value)
    claim = await claim_job(h, receipt.job_id)
    assert claim.kind == "PROCESS_INBOX"
    await worker.execute(claim)
    return (
        await query(
            h,
            """SELECT m.id,m.conversation_id,tm.turn_id FROM platform.inbox_events i
            JOIN app.messages m ON (m.workspace_id,m.id)=(i.workspace_id,i.message_id)
            LEFT JOIN app.conversation_turn_messages tm
              ON (tm.workspace_id,tm.message_id)=(m.workspace_id,m.id)
            WHERE i.id=:inbox AND i.status='PROCESSED'""",
            inbox=receipt.inbox_id,
        )
    )[0]


async def source_turn(h, worker, scope, value):
    message = await receive(h, worker, scope, value)

    async def claim_step(step):
        job = await scalar(
            h,
            """SELECT j.id FROM platform.messaging_jobs j JOIN app.conversation_turns t
            ON (t.workspace_id,t.id,t.revision)=(j.workspace_id,j.turn_id,j.turn_revision)
            WHERE t.id=:turn AND j.step=:step""",
            turn=message["turn_id"],
            step=step,
        )
        return await claim_job(h, job)

    await worker.execute(await claim_step("GROUP"))
    return message["id"], await claim_step("TEST_CONSUME")


async def application(h, *, legacy=False):
    number = next(COUNTER)
    scope = dict(chat_id=f"m64a-{number}", sender_id=f"m64a-client-{number}")
    wire = DeliveryWire(h)
    seed = await receive(h, Worker(h.kernel, wire), scope, "Synthetic conversation seed")
    conversation = seed["conversation_id"]
    await reconcile(h, conversation)
    await owner(h, conversation)
    profile = "SYNTHETIC_INTAKE_V1" if legacy else "SYNTHETIC_SERVICE_INTENTS_V1"
    admission = await session(h, conversation, profile=profile)
    config_type = IntakeGatewayConfig if legacy else ServiceIntentGatewayConfig
    cfg = config_type.model_validate(
        config().model_dump()
        | dict(
            prompt_revision="conversation_v7" if legacy else "conversation_v8",
            schema_revision="conversation_result_v3" if legacy else "conversation_result_v4",
        )
    )
    model = IntentModel(cfg.route)
    settings = IntakeRuntimeSettings(
        session_id=UUID(admission["session_id"]),
        workspace_id=A,
        business_id=BA,
        client_id=UUID(admission["client_id"]),
        conversation_id=conversation,
        data_profile=profile,
        expires_at=datetime.fromisoformat(admission["expires_at"]),
        max_calls=4,
        max_cost=Decimal(10),
        config=cfg,
    )
    worker = create_worker(
        h.kernel,
        wire,
        environment="TEST",
        intake_settings=settings,
        model=lambda: model,
        portfolio_storage=PrivateBytes(),
    )
    h.intake_workers.append(worker)
    return conversation, scope, worker, model, wire


async def effects(h, cid):
    return (
        await query(
            h,
            """SELECT
              (SELECT count(*) FROM app.service_requests r WHERE r.conversation_id=:c) AS requests,
              (SELECT count(*) FROM app.approval_requests a WHERE a.conversation_id=:c) AS approvals,
              (SELECT count(*) FROM app.owner_decisions d JOIN app.approval_requests a
                ON (a.workspace_id,a.id)=(d.workspace_id,d.approval_id)
                WHERE a.conversation_id=:c) AS decisions,
              (SELECT count(*) FROM app.quotes q WHERE q.conversation_id=:c) AS quotes,
              (SELECT count(*) FROM platform.quote_delivery_intents i JOIN app.quotes q
                ON (q.workspace_id,q.id)=(i.workspace_id,i.quote_id)
                WHERE q.conversation_id=:c) AS deliveries,
              (SELECT count(*) FROM app.service_orders o JOIN app.service_requests r
                ON (r.workspace_id,r.id)=(o.workspace_id,o.request_id)
                WHERE r.conversation_id=:c) AS orders""",
            c=cid,
        )
    )[0]


def report(check, **facts):
    print(
        "M64A", json.dumps({"check": check, **facts}, ensure_ascii=False, default=str), flush=True
    )


async def result(worker, claim):
    receipt = await worker.ai.database.replay(claim, worker.ai.config)
    assert isinstance(receipt, ServiceIntentRuntimeReceipt) and receipt.service_intents is not None
    return receipt


async def test_agent_two_works_one_quote_each_and_owner_continuation(
    approval_pg, auth, monkeypatch
):
    h = approval_pg
    await publish(h, contract(formula_price(), FIXED_DURATION))
    token = await sign_in(auth)
    cid, scope, worker, model, wire = await application(h)
    endpoint = route(cid)
    assert (await owner_get(auth, endpoint + "/cards"))["items"] == []

    first_message, first_turn = await source_turn(h, worker, scope, "flower forearm 20 mm linework")
    first_claim, _ = await run_turn(h, worker, first_turn)
    first = await result(worker, first_claim)
    a = first.service_intents
    assert a.approval_id is None and a.quote_id is not None
    a_url = f"{endpoint}/{a.request_id}"
    quote_a = (await owner_get(auth, a_url + "/quote"))["quote"]
    assert quote_a["quote_id"] == str(a.quote_id)
    assert (quote_a["material"]["amount_minor"], quote_a["material"]["occupied_minutes"]) == (
        350_000,
        65,
    )
    await run_quote(h, worker, quote_a)
    assert (wire.calls, wire.effects) == (1, 1)

    model.values, model.switch = SWALLOW, True
    model.intents = (PREPARE, OWNER_DECISION)
    second_message, second_turn = await source_turn(
        h, worker, scope, "Отдельная татуировка: swallow shoulder 101 mm linework"
    )
    checkpoint = h.kernel.checkpoint
    lost = []

    async def lose_committed_result(name):
        await checkpoint(name)
        if name == "service_intents_after_commit":
            lost.append(name)
            raise SQLAlchemyError("synthetic loss after the commercial transaction committed")

    with monkeypatch.context() as patch:
        patch.setattr(h.kernel, "checkpoint", lose_committed_result)
        second_claim, _ = await run_turn(h, worker, second_turn)
    second = await result(worker, second_claim)
    assert lost == ["service_intents_after_commit"]
    b = second.service_intents
    assert b.request_id != a.request_id and b.approval_id is not None and b.quote_id is None
    assert len(model.requests) == 2
    await worker.execute(second_claim)
    assert len(model.requests) == 2 and await result(worker, second_claim) == second

    # A fresh Turn has a different technical replay key. It confirms the same
    # selected work, which therefore retains its decision Request and draft.
    model.values, model.switch = {}, False
    model.intents = (PREPARE, OWNER_DECISION)
    _, duplicate_turn = await source_turn(h, worker, scope, 'Для татуировки "swallow" всё верно')
    duplicate_claim, _ = await run_turn(h, worker, duplicate_turn)
    duplicate = await result(worker, duplicate_claim)
    assert second.run_id != duplicate.run_id
    assert (duplicate.service_intents.request_id, duplicate.service_intents.approval_id) == (
        b.request_id,
        b.approval_id,
    )
    committed = await query(
        h,
        """SELECT run_id,actor_kind,request_id,approval_id,phase
        FROM platform.service_request_agent_intents WHERE workspace_id=:ws""",
        ws=A,
    )
    assert {
        row["run_id"]: (row["actor_kind"], row["request_id"], row["approval_id"], row["phase"])
        for row in committed
    } == {
        first.run_id: ("AI_AGENT", a.request_id, None, "DONE"),
        second.run_id: ("AI_AGENT", b.request_id, b.approval_id, "DONE"),
        duplicate.run_id: ("AI_AGENT", b.request_id, b.approval_id, "DONE"),
    }

    cards = (await owner_get(auth, endpoint + "/cards"))["items"]
    assert {card["request_id"]: card["intent_source"]["message_id"] for card in cards} == {
        str(a.request_id): str(first_message),
        str(b.request_id): str(second_message),
    }
    for work, source, expected in ((a, first_message, FLOWER), (b, second_message, SWALLOW)):
        card = await owner_get(auth, f"{endpoint}?request_id={work.request_id}")
        assert {fact["field"]: fact["value"] for fact in card["facts"]} == expected
        assert {fact["source"]["message_id"] for fact in card["facts"]} == {str(source)}
    queue = (await owner_get(auth, f"/api/v1/workspaces/{A}/service-approvals"))["items"]
    assert len(queue) == 1
    approval = queue[0]
    assert (approval["approval_id"], approval["request_id"], approval["status"]) == (
        str(b.approval_id),
        str(b.request_id),
        "PENDING",
    )
    assert (approval["basis"]["price_reason"], approval["basis"]["occupied_minutes"]) == (
        "SIZE_OUTSIDE_RULE",
        65,
    )
    assert (wire.calls, wire.effects) == (1, 1)
    before = await input_count(h, cid)

    b_url = f"{endpoint}/{b.request_id}"
    decision_url = f"{b_url}/approvals/{b.approval_id}"
    body = AB | {"operation": "APPROVE", "amount_minor": 460_000}
    decision = (await owner_post(auth, decision_url, token, body))["decision"]
    quote_b = (await owner_get(auth, b_url + "/quote"))["quote"]
    assert quote_b["quote_id"] != quote_a["quote_id"]
    assert quote_b["material"]["price_reference_id"] == decision["decision_id"]
    assert quote_b["material"]["amount_minor"] == 460_000
    assert quote_b["material"]["occupied_minutes"] == 65
    await run_quote(h, worker, quote_b)
    assert (await owner_post(auth, decision_url, token, body))["decision"] == decision

    assert await input_count(h, cid) == before
    assert [permit.text for permit in wire.permits] == [quote_a["text"], quote_b["text"]]
    assert (wire.calls, wire.effects) == (2, 2)
    assert await effects(h, cid) == dict(
        requests=2, approvals=1, decisions=1, quotes=2, deliveries=2, orders=0
    )
    works = []
    for work_url, quote in ((a_url, quote_a), (b_url, quote_b)):
        assert (await owner_get(auth, work_url + "/quote"))["status"] == "SENT"
        sent = await delivery(h, quote)
        assert sent["status"] == "SENT" and sent["job_status"] == "SUCCEEDED"
        assert quote["text"].endswith("\nПринимаю " + quote["code"])
        works.append(
            dict(
                request_id=quote["material"]["request_id"],
                source_message_id=quote["material"]["intent_source"]["message_id"],
                quote_id=quote["quote_id"],
                message_id=sent["message_id"],
                outbox_id=sent["outbox_id"],
                code=quote["code"],
                calls=1,
                effects=1,
            )
        )
    report(
        "agent_two_works",
        conversation=cid,
        works=works,
        approval_id=b.approval_id,
        decision_id=decision["decision_id"],
        initial_run_id=second.run_id,
        replay_run_id=duplicate.run_id,
        actor="AI_AGENT",
        replay_calls=0,
        replay_effects=0,
        inbound_after_decision=0,
        orders=0,
    )


async def test_agent_updates_selected_work_and_clarifies_an_ambiguous_reference(approval_pg, auth):
    h = approval_pg
    await publish(h, contract(formula_price(), FIXED_DURATION))
    await sign_in(auth)
    cid, scope, worker, model, wire = await application(h)
    first_source, first_turn = await source_turn(h, worker, scope, "flower forearm 20 mm linework")
    first_claim, _ = await run_turn(h, worker, first_turn)
    first = (await result(worker, first_claim)).service_intents
    endpoint = route(cid)
    initial = await owner_get(auth, f"{endpoint}?request_id={first.request_id}")
    quote_url = f"{endpoint}/{first.request_id}/quote"
    old_quote = (await owner_get(auth, quote_url))["quote"]
    await run_quote(h, worker, old_quote)

    model.values, model.correction = {"approximate_size": "21 mm"}, True
    fresh_source, correction = await source_turn(
        h, worker, scope, 'For the tattoo "flower", the correct size is 21 mm.'
    )
    correction_claim, _ = await run_turn(h, worker, correction)
    updated = (await result(worker, correction_claim)).service_intents
    assert updated.request_id == first.request_id and updated.quote_id != first.quote_id
    amended = await owner_get(auth, f"{endpoint}?request_id={updated.request_id}")
    assert (initial["revision"], amended["revision"]) == ("1", "2")
    assert amended["intent_source"] == initial["intent_source"]
    assert amended["intent_source"]["message_id"] == str(first_source)
    facts = {fact["field"]: fact for fact in amended["facts"]}
    assert facts["approximate_size"]["value"] == "21 mm"
    assert facts["approximate_size"]["source"]["message_id"] == str(fresh_source)
    assert {
        fact["source"]["message_id"] for field, fact in facts.items() if field != "approximate_size"
    } == {str(first_source)}
    quote = (await owner_get(auth, quote_url))["quote"]
    assert quote["quote_id"] == str(updated.quote_id)
    assert (quote["material"]["amount_minor"], quote["material"]["occupied_minutes"]) == (
        400_000,
        65,
    )
    await run_quote(h, worker, quote)
    assert (wire.calls, wire.effects) == (2, 2)
    before = await effects(h, cid)
    assert before == dict(requests=1, approvals=0, decisions=0, quotes=2, deliveries=2, orders=0)

    model.values, model.correction = {}, False
    ambiguous_source, ambiguous_turn = await source_turn(
        h, worker, scope, "Can we proceed with that idea?"
    )
    ambiguous_claim, selected = await run_turn(h, worker, ambiguous_turn)
    receipt = await worker.ai.database.replay(ambiguous_claim, worker.ai.config)
    assert isinstance(receipt, ServiceIntentRuntimeReceipt)
    assert receipt.service_intents is None
    assert (receipt.result.kind, receipt.result.text) == ("reply", AMBIGUOUS_QUESTION)
    assert selected["send_job_id"] is not None
    assert await effects(h, cid) == before
    assert await owner_get(auth, f"{endpoint}?request_id={updated.request_id}") == amended
    assert len(model.requests) == 3
    report(
        "agent_update_and_clarification",
        conversation=cid,
        request_id=updated.request_id,
        original_source=first_source,
        updated_source=fresh_source,
        old_quote_id=first.quote_id,
        new_quote_id=updated.quote_id,
        amount_minor=quote["material"]["amount_minor"],
        revision=amended["revision"],
        ambiguous_source=ambiguous_source,
        ambiguous_question=receipt.result.text,
        ambiguous_commercial_effects=0,
    )


@pytest.mark.parametrize(
    "fence", ["HUMAN", "REVOKED", "STALE_TURN", "FOREIGN", "STALE_SOURCE", "AMOUNT", "V7"]
)
async def test_intent_guard_creates_no_commercial_effect(approval_pg, auth, fence):
    h = approval_pg
    await publish(h, contract(formula_price(), FIXED_DURATION))
    await sign_in(auth)
    cid, scope, worker, model, wire = await application(h, legacy=fence == "V7")
    if fence == "FOREIGN":
        other = await receive(
            h,
            Worker(h.kernel, wire),
            dict(chat_id="foreign-chat", sender_id="foreign-client"),
            "Other client's exact work",
        )
        other_projection = await summary(h, other["conversation_id"])
        model.source_override = {
            name: other_projection["sources"][-1][name] for name in ("message_id", "source_version")
        }
    elif fence == "STALE_SOURCE":
        model.source_override = {"source_version": "0" * 64}
    elif fence == "AMOUNT":
        model.amount = 1

    source_message, turn = await source_turn(h, worker, scope, "flower forearm 20 mm linework")
    database = worker.ai.database
    commit = database.commit
    changed = []

    async def change_after_candidate(*args, **kwargs):
        if fence == "HUMAN":
            await control(h, cid, "TAKEOVER")
        elif fence == "REVOKED":
            await scalar(
                h,
                """UPDATE platform.portfolio_ai_sessions SET revoked_at=clock_timestamp()
                WHERE id=:session RETURNING id""",
                session=worker.ai.settings.session_id,
            )
        else:
            await receive(h, worker, scope, "A newly arrived inbound supersedes the Turn")
        changed.append(fence)
        return await commit(*args, **kwargs)

    if fence in {"HUMAN", "REVOKED", "STALE_TURN"}:
        database.commit = change_after_candidate
    try:
        claim, selected = await run_turn(h, worker, turn)
    finally:
        database.commit = commit
    assert len(model.requests) == 1
    if fence in {"HUMAN", "REVOKED", "STALE_TURN"}:
        assert changed == [fence]
    if fence == "V7":
        assert selected["selected_kind"] == "reply"
    else:
        assert selected["selected_kind"] is None and selected["send_job_id"] is None
    stats = await effects(h, cid)
    assert stats == dict(requests=0, approvals=0, decisions=0, quotes=0, deliveries=0, orders=0)
    assert (wire.calls, wire.effects) == (0, 0)
    assert (await owner_get(auth, route(cid) + "/cards"))["items"] == []
    history = await owner_get(auth, f"/api/v1/workspaces/{A}/conversations/{cid}/messages")
    assert any(row["message_id"] == str(source_message) for row in history["items"])
    if fence == "HUMAN":
        human_message = await receive(h, worker, scope, "A new inbound while the owner controls")
        history = await owner_get(auth, f"/api/v1/workspaces/{A}/conversations/{cid}/messages")
        assert any(row["message_id"] == str(human_message["id"]) for row in history["items"])
        assert [row["direction"] for row in history["items"]] == ["INBOUND"] * len(history["items"])
    job = (
        await query(
            h, "SELECT status,error_code FROM platform.messaging_jobs WHERE id=:j", j=claim.job_id
        )
    )[0]
    assert job["status"] == ("SUCCEEDED" if fence == "V7" else "DEAD")
    report(fence, conversation=cid, inbox_message=source_message, **job, **stats, effects=0)
