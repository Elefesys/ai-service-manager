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
from asm.intake.projection import AMBIGUOUS_QUESTION, QUESTIONS
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.results import AISendPermit
from asm.messaging.worker import Worker
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, control, incoming, reconcile, scalar
from test_m4_agent import config
from test_m4_delivery_postgres import run_turn
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_intake_postgres import Extractor, summary
from test_m5_intake_v7_integration_postgres import session
from test_m5_portfolio_runtime_postgres import PrivateBytes
from test_m6_owner_decisions_postgres import (
    AB,
    FIXED_DURATION,
    assert_denial,
    contract,
    owner_get,
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
        if request.config.prompt_revision == "conversation_v7" or self.intents is None:
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


ROSE = dict(idea="роза", placement="предплечье", approximate_size="20 мм", style="лайнворк")
SECOND_ROSE = ROSE | {"placement": "плечо", "approximate_size": "21 мм"}
SECOND_SWALLOW = dict(
    idea="ласточка", placement="плечо", approximate_size="101 мм", style="лайнворк"
)
ROSE_TEXT = "Хочу татуировку: роза, место — предплечье, 20 мм, стиль лайнворк"
SWALLOW_TEXT = "Отдельная татуировка: ласточка, место — плечо, 101 мм, стиль лайнворк"
APPROVAL_TEXT = "Для тату «роза» прошу мастера подтвердить цену и длительность"


class FollowupWire(ControlledAdapter):
    def __init__(self):
        super().__init__(environment="TEST")
        self.texts = []

    async def send(self, permit):
        assert isinstance(permit, AISendPermit) and permit.provider == "CONTROLLED"
        self.texts.append(permit.text)
        return await super().send(permit)


class R1Conversation:
    @classmethod
    async def open(cls, h, auth, *, manual=False):
        await publish(h, contract() if manual else contract(formula_price(), FIXED_DURATION))
        case = cls()
        case.h, case.auth = h, auth
        case.token = await sign_in(auth)
        case.cid, case.scope, case.worker, case.model, case.wire = await application(h)
        case.endpoint = route(case.cid)
        case.followups = FollowupWire()
        case.reply_worker = Worker(h.kernel, case.followups, ai=case.worker.ai)
        return case

    async def turn(self, message, facts, *, switch=False, correction=False, intents=(PREPARE,)):
        self.model.values, self.model.switch, self.model.correction, self.model.intents = (
            facts,
            switch,
            correction,
            intents,
        )
        source, turn = await source_turn(self.h, self.worker, self.scope, message)
        claim, selected = await run_turn(self.h, self.worker, turn)
        receipt = await self.worker.ai.database.replay(claim, self.worker.ai.config)
        assert isinstance(receipt, ServiceIntentRuntimeReceipt)
        if selected["send_job_id"] is not None:
            await self.reply_worker.execute(await claim_job(self.h, selected["send_job_id"]))
        return source, receipt

    async def commercial(self, *args, **kwargs):
        source, receipt = await self.turn(*args, **kwargs)
        assert receipt.result.kind == "no_reply"
        result = receipt.service_intents
        assert result is not None and result.request_id is not None
        return source, result

    async def cards(self):
        return (await owner_get(self.auth, self.endpoint + "/cards"))["items"]

    async def card(self, request_id):
        return await owner_get(self.auth, f"{self.endpoint}?request_id={request_id}")

    async def approvals(self):
        rows = (await owner_get(self.auth, f"/api/v1/workspaces/{A}/service-approvals"))["items"]
        return [row for row in rows if row["conversation_id"] == str(self.cid)]

    def decision_url(self, request_id, approval_id):
        return f"{self.endpoint}/{request_id}/approvals/{approval_id}"

    async def quote_view(self, request_id):
        return await owner_get(self.auth, f"{self.endpoint}/{request_id}/quote")

    async def send_quote(self, request_id, amount, minutes):
        view = await self.quote_view(request_id)
        assert view["status"] == "QUEUED"
        quote = view["quote"]
        assert (quote["material"]["amount_minor"], quote["material"]["occupied_minutes"]) == (
            amount,
            minutes,
        )
        calls, effects_before = self.wire.calls, self.wire.effects
        await run_quote(self.h, self.worker, quote)
        assert (self.wire.calls, self.wire.effects) == (calls + 1, effects_before + 1)
        assert self.wire.permits[-1].text == quote["text"]
        delivered = await delivery(self.h, quote)
        assert (delivered["status"], delivered["job_status"]) == ("SENT", "SUCCEEDED")
        assert delivered["text"] == quote["text"]
        assert (await self.quote_view(request_id))["status"] == "SENT"
        assert quote["text"].endswith("\nПринимаю " + quote["code"])
        return dict(
            quote_id=quote["quote_id"],
            outbox_id=delivered["outbox_id"],
            message_id=delivered["message_id"],
            amount_minor=amount,
            occupied_minutes=minutes,
            text=quote["text"],
        )

    async def first_rose(self):
        source, result = await self.commercial(ROSE_TEXT, ROSE)
        card = await self.card(result.request_id)
        assert_source_map(card, ROSE, source)
        assert card["revision"] == "1" and result.approval_id is None
        quote = await self.send_quote(result.request_id, 350_000, 65)
        assert quote["quote_id"] == str(result.quote_id)
        return card, quote

    async def approve_and_send(self, request_id, approval_id):
        before = await input_count(self.h, self.cid)
        decision = await owner_post(
            self.auth,
            self.decision_url(request_id, approval_id),
            self.token,
            AB | {"operation": "APPROVE", "amount_minor": 460_000, "occupied_minutes": 75},
        )
        assert decision["status"] == "APPROVED" and decision["authorization_current"]
        quote = await self.send_quote(request_id, 460_000, 75)
        material = (await self.quote_view(request_id))["quote"]["material"]
        decision_id = decision["decision"]["decision_id"]
        assert (
            material["approval_id"],
            material["price_reference_id"],
            material["duration_reference_id"],
        ) == (str(approval_id), decision_id, decision_id)
        assert await input_count(self.h, self.cid) == before
        return decision_id, quote

    async def check_counts(self, *, requests, approvals, quotes, decisions=0, followups=()):
        counts = await effects(self.h, self.cid)
        assert counts == dict(
            requests=requests,
            approvals=approvals,
            decisions=decisions,
            quotes=quotes,
            deliveries=quotes,
            orders=0,
        )
        assert self.wire.calls == self.wire.effects == quotes
        assert self.followups.calls == self.followups.effects == len(followups)
        assert self.followups.texts == list(followups)
        outbox = await query(
            self.h,
            """SELECT o.status FROM app.outbox_events o JOIN app.messages m
            ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id)
            WHERE m.conversation_id=:c""",
            c=self.cid,
        )
        assert [row["status"] for row in outbox] == ["SENT"] * (quotes + len(followups))
        return dict(
            counts=dict(counts),
            calls=self.wire.calls,
            effects=self.wire.effects,
            followup_calls=self.followups.calls,
            followup_effects=self.followups.effects,
            followup_texts=self.followups.texts,
        )


def work_evidence(card):
    return dict(
        request_id=card["request_id"],
        revision=card["revision"],
        source=card["intent_source"]["message_id"],
        facts=fact_evidence(card),
    )


def fact_evidence(card):
    return {fact["field"]: (fact["value"], fact["source"]["message_id"]) for fact in card["facts"]}


def assert_source_map(card, facts, source, **changed_sources):
    assert card["intent_source"]["message_id"] == str(source)
    assert fact_evidence(card) == {
        field: (value, str(changed_sources.get(field, source))) for field, value in facts.items()
    }


async def quote_counts_by_request(case):
    rows = await query(
        case.h,
        """SELECT r.id AS request_id, count(q.id) AS quotes, count(i.quote_id) AS deliveries,
                  count(o.id) FILTER (WHERE o.status='SENT') AS sent
             FROM app.service_requests r
             LEFT JOIN app.quotes q ON (q.workspace_id,q.request_id)=(r.workspace_id,r.id)
             LEFT JOIN platform.quote_delivery_intents i ON (i.workspace_id,i.quote_id)=(q.workspace_id,q.id)
             LEFT JOIN app.outbox_events o ON (o.workspace_id,o.id)=(i.workspace_id,i.outbox_id)
            WHERE r.conversation_id=:c GROUP BY r.id""",
        c=case.cid,
    )
    return {
        str(row["request_id"]): {key: row[key] for key in ("quotes", "deliveries", "sent")}
        for row in rows
    }


async def test_r1_explicit_second_work_with_same_idea_keeps_original(approval_pg, auth):
    case = await R1Conversation.open(approval_pg, auth)
    original, quote_a = await case.first_rose()
    source, b = await case.commercial(
        "На другом месте хочу отдельную татуировку: роза, место — плечо, 21 мм, стиль лайнворк",
        SECOND_ROSE,
        switch=True,
    )
    second = await case.card(b.request_id)
    assert second["revision"] == "1" and second["request_id"] != original["request_id"]
    assert_source_map(second, SECOND_ROSE, source)
    quote_b = await case.send_quote(b.request_id, 400_000, 65)
    assert quote_b["quote_id"] == str(b.quote_id)
    assert (await case.quote_view(original["request_id"]))["quote"]["quote_id"] == quote_a[
        "quote_id"
    ]

    ambiguous_source, ambiguous = await case.turn(
        "Для тату „роза“ уточняю размер: 23 мм", {"approximate_size": "23 мм"}, correction=True
    )
    assert ambiguous.service_intents is None and ambiguous.result.text == AMBIGUOUS_QUESTION
    assert await case.card(original["request_id"]) == original
    assert await case.card(b.request_id) == second
    assert {row["request_id"] for row in await case.cards()} == {
        original["request_id"],
        second["request_id"],
    }
    assert not await case.approvals()
    stats = await case.check_counts(
        requests=2, approvals=0, quotes=2, followups=(AMBIGUOUS_QUESTION,)
    )
    report(
        "R1_01_same_idea",
        conversation=case.cid,
        a=work_evidence(original),
        b=work_evidence(second),
        quotes=[quote_a, quote_b],
        ambiguous_source=ambiguous_source,
        **stats,
    )


async def test_r1_separate_work_keeps_anchor_across_clarification(approval_pg, auth):
    case = await R1Conversation.open(approval_pg, auth)
    original, quote_a = await case.first_rose()
    source, incomplete = await case.turn(
        "Отдельная татуировка: ласточка", {"idea": "ласточка"}, switch=True, intents=None
    )
    assert incomplete.service_intents is None and incomplete.result.text == QUESTIONS["placement"]
    assert [row["request_id"] for row in await case.cards()] == [original["request_id"]]
    await case.check_counts(requests=1, approvals=0, quotes=1, followups=(QUESTIONS["placement"],))

    answer, b = await case.commercial(
        "Для тату «ласточка»: место — плечо, 101 мм, стиль лайнворк",
        SECOND_SWALLOW,
        intents=(PREPARE, OWNER_DECISION),
    )
    second = await case.card(b.request_id)
    assert second["revision"] == "1" and second["request_id"] != original["request_id"]
    assert_source_map(
        second,
        SECOND_SWALLOW,
        source,
        placement=answer,
        approximate_size=answer,
        style=answer,
    )
    assert await case.card(original["request_id"]) == original
    assert (await case.quote_view(original["request_id"]))["quote"]["quote_id"] == quote_a[
        "quote_id"
    ]
    (approval,) = await case.approvals()
    assert (approval["approval_id"], approval["request_id"], approval["status"]) == (
        str(b.approval_id),
        str(b.request_id),
        "PENDING",
    )
    assert_source_map(
        approval["basis"],
        SECOND_SWALLOW,
        source,
        placement=answer,
        approximate_size=answer,
        style=answer,
    )
    assert b.quote_id is None
    stats = await case.check_counts(
        requests=2, approvals=1, quotes=1, followups=(QUESTIONS["placement"],)
    )
    report(
        "R1_01_two_turns",
        conversation=case.cid,
        a=work_evidence(original),
        b=work_evidence(second),
        quotes=[quote_a],
        approval_id=b.approval_id,
        approval_status=approval["status"],
        **stats,
    )


async def test_r1_updates_earlier_work_without_changing_later_approval(approval_pg, auth):
    case = await R1Conversation.open(approval_pg, auth)
    original, first_quote = await case.first_rose()
    source_b, b = await case.commercial(
        SWALLOW_TEXT, SECOND_SWALLOW, switch=True, intents=(PREPARE, OWNER_DECISION)
    )
    case_b = await case.card(b.request_id)
    assert_source_map(case_b, SECOND_SWALLOW, source_b)
    approval_url = case.decision_url(b.request_id, b.approval_id)
    before = await owner_get(auth, approval_url)
    assert before["status"] == "PENDING" and b.quote_id is None

    source, updated = await case.commercial(
        "Для тату „роза“ уточняю размер: 21 мм", {"approximate_size": "21 мм"}, correction=True
    )
    card = await case.card(updated.request_id)
    assert original["request_id"] == card["request_id"] == str(updated.request_id)
    assert card["revision"] == "2"
    assert_source_map(
        card,
        ROSE | {"approximate_size": "21 мм"},
        original["intent_source"]["message_id"],
        approximate_size=source,
    )
    assert await case.card(b.request_id) == case_b
    after = await owner_get(auth, approval_url)
    for field in ("approval_id", "request_revision", "status", "basis"):
        assert after[field] == before[field]
    quote = await case.send_quote(updated.request_id, 400_000, 65)
    assert quote["quote_id"] == str(updated.quote_id) != first_quote["quote_id"]
    stats = await case.check_counts(requests=2, approvals=1, quotes=2)
    report(
        "R1_02_update_earlier",
        conversation=case.cid,
        a=work_evidence(card),
        b=work_evidence(case_b),
        quotes=[first_quote, quote],
        approval_id=b.approval_id,
        approval_status=after["status"],
        **stats,
    )


async def test_r1_prepare_alone_opens_owner_request_when_both_values_missing(approval_pg, auth):
    case = await R1Conversation.open(approval_pg, auth, manual=True)
    source, prepared = await case.commercial(ROSE_TEXT, ROSE)
    assert prepared.approval_id is not None and prepared.quote_id is None
    card = await case.card(prepared.request_id)
    assert_source_map(card, ROSE, source)
    (approval,) = await case.approvals()
    assert (approval["approval_id"], approval["request_id"], approval["status"]) == (
        str(prepared.approval_id),
        str(prepared.request_id),
        "PENDING",
    )
    assert (
        approval["basis"]["amount_minor"] is None and approval["basis"]["occupied_minutes"] is None
    )
    await case.check_counts(requests=1, approvals=1, quotes=0)
    _, repeated = await case.commercial(APPROVAL_TEXT, {}, intents=(OWNER_DECISION,))
    assert repeated == prepared
    assert await case.card(prepared.request_id) == card
    await case.check_counts(requests=1, approvals=1, quotes=0)

    decision, quote = await case.approve_and_send(prepared.request_id, prepared.approval_id)
    stats = await case.check_counts(requests=1, approvals=1, quotes=1, decisions=1)
    report(
        "R1_03_prepare_only",
        conversation=case.cid,
        work=work_evidence(card),
        approval_id=prepared.approval_id,
        approval_status="PENDING",
        replay_approval_id=repeated.approval_id,
        decision_id=decision,
        inbound_after_approval=0,
        quotes=[quote],
        **stats,
    )


async def test_r1_expired_approval_is_replaced_and_remains_in_history(approval_pg, auth):
    h = approval_pg
    case = await R1Conversation.open(h, auth, manual=True)
    source, initial = await case.commercial(ROSE_TEXT, ROSE, intents=(PREPARE, OWNER_DECISION))
    card = await case.card(initial.request_id)
    assert_source_map(card, ROSE, source)
    assert initial.approval_id is not None and initial.quote_id is None
    old_url = case.decision_url(initial.request_id, initial.approval_id)
    _, repeated = await case.commercial(APPROVAL_TEXT, {}, intents=(OWNER_DECISION,))
    assert repeated == initial and (await owner_get(auth, old_url))["status"] == "PENDING"
    await case.check_counts(requests=1, approvals=1, quotes=0)

    # Advance only this request's 24-hour window in the disposable test database.
    async with h.migrator.begin() as connection:
        await connection.execute(
            text("ALTER TABLE app.approval_requests DISABLE TRIGGER owner_decision_immutable")
        )
        expired_id = (
            await connection.execute(
                text("""UPDATE app.approval_requests
                    SET created_at=now()-interval '25 hours', expires_at=now()-interval '1 hour'
                    WHERE workspace_id=:ws AND id=:id RETURNING id"""),
                {"ws": A, "id": initial.approval_id},
            )
        ).scalar_one()
        assert expired_id == initial.approval_id
        await connection.execute(
            text("ALTER TABLE app.approval_requests ENABLE TRIGGER owner_decision_immutable")
        )
    expired = await owner_get(auth, old_url)
    assert expired["status"] == "EXPIRED" and not expired["authorization_current"]

    renewal_source, renewed = await case.commercial(APPROVAL_TEXT, {}, intents=(OWNER_DECISION,))
    assert renewed.request_id == initial.request_id and renewed.quote_id is None
    assert renewed.approval_id is not None and renewed.approval_id != initial.approval_id
    assert await case.card(initial.request_id) == card
    approvals = await case.approvals()
    assert [row["approval_id"] for row in approvals if row["status"] == "PENDING"] == [
        str(renewed.approval_id)
    ]
    retained = await owner_get(auth, old_url)
    assert (retained["status"], retained["basis"]) == ("EXPIRED", expired["basis"])
    await assert_denial(
        auth,
        old_url,
        case.token,
        AB | {"operation": "APPROVE", "amount_minor": 460_000, "occupied_minutes": 75},
        409,
        "APPROVAL_EXPIRED",
    )
    _, repeat_renewal = await case.commercial(APPROVAL_TEXT, {}, intents=(OWNER_DECISION,))
    assert repeat_renewal == renewed
    await case.check_counts(requests=1, approvals=2, quotes=0)
    decision, quote = await case.approve_and_send(initial.request_id, renewed.approval_id)
    stats = await case.check_counts(requests=1, approvals=2, quotes=1, decisions=1)
    assert (await owner_get(auth, old_url))["status"] == "EXPIRED"
    report(
        "R1_03_expired",
        conversation=case.cid,
        work=work_evidence(card),
        expired_approval_id=expired_id,
        expired_status="EXPIRED",
        source_of_renewal=renewal_source,
        new_approval_id=renewed.approval_id,
        new_approval_status="PENDING",
        replay_approval_id=repeat_renewal.approval_id,
        decision_id=decision,
        inbound_after_approval=0,
        quotes=[quote],
        **stats,
    )


async def test_r2_excluded_work_requires_clarification_without_new_commercial_effect(
    approval_pg, auth
):
    case = await R1Conversation.open(approval_pg, auth)
    a, quote = await case.first_rose()
    _, b = await case.commercial(
        SWALLOW_TEXT, SECOND_SWALLOW, switch=True, intents=(PREPARE, OWNER_DECISION)
    )
    assert b.approval_id is not None and b.quote_id is None
    b_id = str(b.request_id)
    b_before = await case.card(b_id)
    a_quote_before = await case.quote_view(a["request_id"])
    b_quote_before = await case.quote_view(b_id)
    (approval,) = await case.approvals()
    assert (approval["approval_id"], approval["request_id"], approval["status"]) == (
        str(b.approval_id),
        b_id,
        "PENDING",
    )
    before = await quote_counts_by_request(case)
    assert before == {
        a["request_id"]: dict(quotes=1, deliveries=1, sent=1),
        b_id: dict(quotes=0, deliveries=0, sent=0),
    }

    source, receipt = await case.turn(
        "Это не для тату „роза“. У второй работы уточняю размер: 21 мм.",
        {"approximate_size": "21 мм"},
        correction=True,
    )
    assert receipt.service_intents is None
    assert (receipt.result.kind, receipt.result.text) == ("reply", AMBIGUOUS_QUESTION)
    assert await case.card(a["request_id"]) == a
    assert await case.card(b_id) == b_before
    assert await case.quote_view(a["request_id"]) == a_quote_before
    assert await case.quote_view(b_id) == b_quote_before
    assert await case.approvals() == [approval]
    after = await quote_counts_by_request(case)
    assert after == before
    stats = await case.check_counts(
        requests=2, approvals=1, quotes=1, followups=(AMBIGUOUS_QUESTION,)
    )
    report(
        "R2_excluded_work",
        conversation=case.cid,
        source=source,
        a=work_evidence(a),
        b=work_evidence(b_before),
        quote_a=quote,
        approval_id=b.approval_id,
        approval_status=approval["status"],
        before_per_work=before,
        after_per_work=after,
        **stats,
    )


async def test_r2_ordinal_answer_finishes_the_single_pending_second_work(approval_pg, auth):
    case = await R1Conversation.open(approval_pg, auth)
    a, quote = await case.first_rose()
    a_quote_before = await case.quote_view(a["request_id"])
    anchor, incomplete = await case.turn(
        "Отдельная татуировка: ласточка", {"idea": "ласточка"}, switch=True, intents=None
    )
    assert incomplete.service_intents is None and incomplete.result.text == QUESTIONS["placement"]
    await case.check_counts(requests=1, approvals=0, quotes=1, followups=(QUESTIONS["placement"],))
    before = await quote_counts_by_request(case)
    assert before == {a["request_id"]: dict(quotes=1, deliveries=1, sent=1)}

    answer, b = await case.commercial(
        "Для второй татуировки: место — плечо, 101 мм, стиль лайнворк.",
        {field: value for field, value in SECOND_SWALLOW.items() if field != "idea"},
        intents=(PREPARE, OWNER_DECISION),
    )
    b_id = str(b.request_id)
    second = await case.card(b_id)
    assert b_id != a["request_id"] and second["revision"] == "1"
    answer_sources = dict(placement=answer, approximate_size=answer, style=answer)
    assert_source_map(second, SECOND_SWALLOW, anchor, **answer_sources)
    assert await case.card(a["request_id"]) == a
    assert await case.quote_view(a["request_id"]) == a_quote_before
    assert b.approval_id is not None and b.quote_id is None
    (approval,) = await case.approvals()
    assert (approval["approval_id"], approval["request_id"], approval["status"]) == (
        str(b.approval_id),
        b_id,
        "PENDING",
    )
    assert_source_map(approval["basis"], SECOND_SWALLOW, anchor, **answer_sources)
    after = await quote_counts_by_request(case)
    assert after == before | {b_id: dict(quotes=0, deliveries=0, sent=0)}
    stats = await case.check_counts(
        requests=2, approvals=1, quotes=1, followups=(QUESTIONS["placement"],)
    )
    report(
        "R2_ordinal_answer",
        conversation=case.cid,
        source=answer,
        a=work_evidence(a),
        b=work_evidence(second),
        quote_a=quote,
        approval_id=b.approval_id,
        approval_status=approval["status"],
        before_per_work=before,
        after_per_work=after,
        **stats,
    )


async def test_r3_two_named_works_require_clarification_before_correcting_swallow(
    approval_pg, auth
):
    case = await R1Conversation.open(approval_pg, auth)
    a, quote_a = await case.first_rose()
    _, prepared = await case.commercial(
        SWALLOW_TEXT, SECOND_SWALLOW, switch=True, intents=(PREPARE, OWNER_DECISION)
    )
    assert prepared.approval_id is not None and prepared.quote_id is None
    a_id, b_id = a["request_id"], str(prepared.request_id)
    b = await case.card(b_id)

    def size(card):
        return next(fact for fact in card["facts"] if fact["field"] == "approximate_size")

    a_quote_view, b_quote_view = await case.quote_view(a_id), await case.quote_view(b_id)
    (pending,) = await case.approvals()
    approval_url = case.decision_url(b_id, prepared.approval_id)
    assert pending == await owner_get(auth, approval_url)
    assert (pending["approval_id"], pending["request_id"], pending["status"]) == (
        str(prepared.approval_id),
        b_id,
        "PENDING",
    )
    assert pending["can_resolve"]
    before = await quote_counts_by_request(case)
    assert before == {
        a_id: dict(quotes=1, deliveries=1, sent=1),
        b_id: dict(quotes=0, deliveries=0, sent=0),
    }
    mixed, receipt = await case.turn(
        "У тату «роза» размер не меняем. Для тату «ласточка» уточняю размер: 21 мм.",
        {"approximate_size": "21 мм"},
        correction=True,
    )
    assert receipt.service_intents is None
    assert (receipt.result.kind, receipt.result.text) == ("reply", AMBIGUOUS_QUESTION)
    assert await case.card(a_id) == a and await case.card(b_id) == b
    assert await case.quote_view(a_id) == a_quote_view
    assert await case.quote_view(b_id) == b_quote_view
    assert await case.approvals() == [pending] and await owner_get(auth, approval_url) == pending
    after_mixed = await quote_counts_by_request(case)
    assert after_mixed == before
    stats = await case.check_counts(
        requests=2, approvals=1, quotes=1, followups=(AMBIGUOUS_QUESTION,)
    )
    report(
        "R3_mixed_clarification",
        conversation=case.cid,
        incoming_id=mixed,
        a=work_evidence(a),
        b=work_evidence(b),
        a_size=size(a),
        b_size=size(b),
        quote_a=quote_a,
        approval_id=pending["approval_id"],
        approval_status=pending["status"],
        before_per_work=before,
        after_per_work=after_mixed,
        **stats,
    )

    explicit, updated = await case.commercial(
        "Для тату «ласточка» уточняю размер: 21 мм.",
        {"approximate_size": "21 мм"},
        correction=True,
    )
    assert str(updated.request_id) == b_id and updated.approval_id is None
    b_after = await case.card(b_id)
    assert b["revision"] == "1" and b_after["revision"] == "2"
    assert b_after["intent_source"] == b["intent_source"]
    assert [fact for fact in b_after["facts"] if fact["field"] != "approximate_size"] == [
        fact for fact in b["facts"] if fact["field"] != "approximate_size"
    ]
    assert size(b_after)["value"] == "21 мм"
    projection = await summary(approval_pg, case.cid)
    source = next(item for item in projection["sources"] if item["message_id"] == str(explicit))
    assert (size(b_after)["source"]["message_id"], size(b_after)["source"]["source_version"]) == (
        str(explicit),
        source["source_version"],
    )
    quote_b = await case.send_quote(b_id, 400_000, 65)
    assert quote_b["quote_id"] == str(updated.quote_id)
    assert await case.card(a_id) == a and await case.quote_view(a_id) == a_quote_view
    history = await owner_get(auth, approval_url)
    assert (history["approval_id"], history["request_revision"], history["status"]) == (
        pending["approval_id"],
        "1",
        "STALE",
    )
    assert history["basis"] == pending["basis"]
    assert not history["can_resolve"] and not history["authorization_current"]
    assert not [row for row in await case.approvals() if row["status"] == "PENDING"]
    after = await quote_counts_by_request(case)
    assert after == before | {b_id: dict(quotes=1, deliveries=1, sent=1)}
    stats = await case.check_counts(
        requests=2, approvals=1, quotes=2, followups=(AMBIGUOUS_QUESTION,)
    )
    report(
        "R3_explicit_swallow",
        conversation=case.cid,
        incoming_id=explicit,
        a=work_evidence(a),
        b=work_evidence(b_after),
        a_size=size(a),
        b_size_before=size(b),
        b_size_after=size(b_after),
        quote_a=quote_a,
        quote_b=quote_b,
        historical_approval_id=history["approval_id"],
        historical_approval_status=history["status"],
        pending_approvals=0,
        before_per_work=after_mixed,
        after_per_work=after,
        **stats,
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
