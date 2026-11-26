"""S8 over the normal Inbox, Turn, AI worker, scheduling and Outbox capabilities."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from asm.ai.contracts import SchedulingIntentGatewayConfig
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_settings import IntakeRuntimeSettings
from asm.foundation import create_worker
from asm.messaging.adapter import (
    ControlledAdapter,
    OutcomeKind,
)
from asm.messaging.database import worker_active
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AISendPermit
from asm.messaging.worker import Worker
from asm.scheduling.commands import AppointmentResult
from m5_portfolio_fixtures import call
from m7_scheduling_fixtures import (
    POLICY,
    ZONE,
    accept_pair_with_modes,
    accept_work,
    booking_contract,
)
from m7_scheduling_fixtures import scheduling_pg as scheduling_pg
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_models import event
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, reconcile, scalar
from test_m3_1_provenance_postgres import shared_controlled_apply
from test_m4_agent import config
from test_m4_delivery_postgres import run_turn, source_turn
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_knowledge_postgres import publish_configuration
from test_m5_portfolio_runtime_postgres import PrivateBytes, bridge
from test_m6_owner_decisions_postgres import approval_pg as approval_pg
from test_m6_owner_decisions_postgres import assessment_pg as assessment_pg
from test_m6_owner_decisions_postgres import auth as auth
from test_m6_owner_decisions_postgres import db as db
from test_m6_owner_decisions_postgres import intake_pg as intake_pg
from test_m6_owner_decisions_postgres import owner_get, owner_post
from test_m6_owner_decisions_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_owner_decisions_postgres import pricing_pg as pricing_pg
from test_m6_owner_decisions_postgres import search_pg as search_pg
from test_m6_owner_decisions_postgres import seeded as seeded
from test_m6_owner_decisions_postgres import service_request_pg as service_request_pg
from test_m7_scheduling_holds_postgres import command_http
from test_m7_scheduling_owner_day_postgres import day_route
from test_m7_scheduling_reschedule_postgres import option_at, reschedule_offer, wall
from test_tenancy_postgres import BA, BA2, BB, UA, UB, A, B

pytestmark = pytest.mark.integration
PROFILE = "SYNTHETIC_SERVICE_INTENTS_V1"


class SchedulingFake(FakeAdapter):
    def __init__(self, route):
        super().__init__(route)
        self.barrier = None

    async def complete(self, request):
        self.requests.append(request)
        context = next(
            value
            for message in request.request.messages
            if message.role == "context"
            if (value := json.loads(message.text)).get("revision") == "conversation_intake_v1"
        )
        available = context["sources"][-1]
        line = available["text"].casefold()
        if line.startswith("выбираю") or line == "первый":
            intent = {"name": "select_availability"}
        else:
            intent = {
                "name": "list_availability",
                "period": "AFTERNOON" if "после обеда" in line else "ANY",
            }
        intent["source"] = {key: available[key] for key in ("message_id", "source_version")}
        if self.barrier is not None:
            await self.barrier()
        from asm.ai.contracts import AdapterResponse

        return AdapterResponse(
            kind="OUTPUT",
            output_json=json.dumps(
                {"kind": "no_reply", "text": None, "reason": "SCHEDULING", "scheduling": intent},
                ensure_ascii=False,
            ),
        )


class SchedulingWire(ControlledAdapter):
    def __init__(self):
        super().__init__(environment="TEST")
        self.texts = []

    async def send(self, permit):
        assert isinstance(permit, AISendPermit) and permit.provider == "CONTROLLED"
        assert not worker_active()
        self.texts.append(permit.text)
        return await super().send(permit)


def report(case, **evidence):
    print(
        "M7S8", json.dumps({"case": case, **evidence}, ensure_ascii=False, default=str), flush=True
    )


async def scope_for(h, conversation):
    return (
        await query(
            h,
            """SELECT c.provider_chat_id AS chat_id, ci.external_user_id AS sender_id,
               cc.bot_identity,cc.external_connection_id FROM app.conversations c
               JOIN app.client_identities ci ON (ci.workspace_id,ci.id,ci.client_id)
                 =(c.workspace_id,c.identity_id,c.client_id)
               JOIN app.channel_connections cc ON (cc.workspace_id,cc.id)=(c.workspace_id,c.connection_id)
               WHERE c.id=:conversation""",
            conversation=conversation,
        )
    )[0]


class SchedulingChat:
    def __init__(self, h, conversation, scope, *, workspace=A, business=BA, actor=UA):
        self.h, self.conversation, self.scope = h, conversation, dict(scope)
        self.workspace, self.business, self.actor = workspace, business, actor
        self.wire = SchedulingWire()
        self.model = SchedulingFake(config().route)
        self.worker = None
        self.generated = 0

    async def start(self):
        cfg = SchedulingIntentGatewayConfig.model_validate(
            config().model_dump()
            | {
                "prompt_revision": "conversation_v9",
                "schema_revision": "conversation_result_v5",
            }
        )
        admission = await call(
            bridge(self.h),
            "portfolio_session_admit",
            [
                self.business,
                self.conversation,
                {
                    "profile_id": PROFILE,
                    "execution": "CONTROLLED",
                    "eligibility": "EVAL_ONLY",
                    "max_calls": 4,
                    "max_cost": "10",
                    "duration_seconds": 900,
                },
            ],
            ws=self.workspace,
            actor=self.actor,
        )
        settings = IntakeRuntimeSettings(
            session_id=UUID(admission["session_id"]),
            workspace_id=self.workspace,
            business_id=self.business,
            client_id=UUID(admission["client_id"]),
            conversation_id=self.conversation,
            data_profile=PROFILE,
            expires_at=datetime.fromisoformat(admission["expires_at"]),
            max_calls=4,
            max_cost=Decimal(10),
            config=cfg,
        )
        self.worker = create_worker(
            self.h.kernel,
            self.wire,
            environment="TEST",
            intake_settings=settings,
            model=lambda: self.model,
            portfolio_storage=PrivateBytes(),
        )
        self.h.intake_workers.append(self.worker)
        self.generated = 0

    async def begin(self, value, *, occurred_at=None):
        if self.worker is None or self.generated == 4:
            await self.start()
        number = f"s8-{next(COUNTER)}"
        message = event(
            event_id=number,
            message_id=number,
            occurred_at=occurred_at or datetime.now(UTC),
            **(self.scope | {"text": value}),
        )
        receipt = await self.h.kernel.ingest_event(
            self.wire.source(message.bot_identity), message, uuid4()
        )
        await self.worker.execute(await claim_job(self.h, receipt.job_id))
        (row,) = await query(
            self.h,
            """SELECT i.message_id, tm.turn_id FROM platform.inbox_events i
               JOIN app.conversation_turn_messages tm ON (tm.workspace_id,tm.message_id)=(i.workspace_id,i.message_id)
               WHERE i.id=:inbox AND i.status='PROCESSED'""",
            inbox=receipt.inbox_id,
        )

        async def step(name):
            return await scalar(
                self.h,
                """SELECT j.id FROM platform.messaging_jobs j JOIN app.conversation_turns t
                   ON (t.workspace_id,t.id,t.revision)=(j.workspace_id,j.turn_id,j.turn_revision)
                   WHERE t.id=:turn AND j.step=:step""",
                turn=row["turn_id"],
                step=name,
            )

        await self.worker.execute(await claim_job(self.h, await step("GROUP")))
        return message, row["message_id"], await claim_job(self.h, await step("TEST_CONSUME"))

    async def say(self, value, *, send=True, occurred_at=None):
        message, source, turn = await self.begin(value, occurred_at=occurred_at)
        self.generated += 1
        claim, delivery = await run_turn(self.h, self.worker, turn)
        if send and delivery["send_job_id"] is not None:
            await self.worker.execute(await claim_job(self.h, delivery["send_job_id"]))
        rows = await query(
            self.h,
            """SELECT a.result,a.selection,a.source_message_id,a.option_id,a.outbox_id,d.send_job_id,
                 b.status AS delivery_status,m.text
               FROM platform.scheduling_turn_actions a
               JOIN platform.ai_deliveries d ON (d.workspace_id,d.run_id)=(a.workspace_id,a.run_id)
               LEFT JOIN app.outbox_events b ON (b.workspace_id,b.id)=(a.workspace_id,a.outbox_id)
               LEFT JOIN app.messages m ON (m.workspace_id,m.id)=(b.workspace_id,b.message_id)
               WHERE d.job_id=:job""",
            job=claim.job_id,
        )
        if rows:
            assert len(rows) == 1 and rows[0]["source_message_id"] == source
            return message, claim, rows[0]
        return message, claim, None

    async def repeat_input(self, message):
        repeated = await self.h.kernel.ingest_event(
            self.wire.source(message.bot_identity), message, uuid4()
        )
        assert repeated.code == "DUPLICATE"
        return repeated

    async def calendar(self, auth, day):
        return await owner_get(auth, day_route(day))


async def configure_wide(h, auth, token, work, *, hold_ttl=POLICY["hold_ttl_minutes"]):
    preview = await owner_get(auth, work.preview_url())
    schedule = await owner_post(
        auth,
        work.preview_url(),
        token,
        {
            "action": "schedule",
            "timezone": ZONE,
            "expected_version": preview["schedule_version"],
            "week": [{"weekday": n, "start_minute": 540, "end_minute": 1200} for n in range(7)],
        },
    )
    await owner_post(
        auth,
        work.preview_url(),
        token,
        POLICY | {"expected_version": schedule["schedule_version"], "hold_ttl_minutes": hold_ttl},
    )


async def sample(h, auth, *, hold_ttl=POLICY["hold_ttl_minutes"]):
    token, rose, swallow = await accept_pair_with_modes(
        h, auth, "NONE", "FIXED_DEPOSIT", titles=("роза", "ласточка")
    )
    scope = h.intake_scope.copy()
    await configure_wide(h, auth, token, rose, hold_ttl=hold_ttl)
    await configure_wide(h, auth, token, swallow, hold_ttl=hold_ttl)
    return token, rose, swallow, scope


async def calendar_facts(h):
    return (
        await query(
            h,
            """SELECT
            (SELECT count(*) FROM app.reservation_holds) AS holds,
            (SELECT count(*) FROM app.appointments) AS appointments,
            (SELECT count(*) FROM app.resource_allocations) AS allocations""",
        )
    )[0]


def offered(row):
    assert row["delivery_status"] == "SENT"
    offer = row["result"]["offer"]
    assert offer["options"] and ZONE in row["text"]
    assert set(re.findall(r"S-[A-Z0-9]{6}", row["text"])) == {
        option["code"] for option in offer["options"]
    }
    return offer


def match_calendar(day, work, id_name, identifier):
    (entry,) = [e for e in day["entries"] if e.get("booking", {}).get(id_name) == identifier]
    for key, actual in work.proof().items():
        if key in entry["selection"]:
            assert entry["selection"][key] == actual
    return entry["booking"]


def appointment_route(work, appointment_id):
    return work.booking_url().split("?", 1)[0] + "/" + str(appointment_id)


async def outgoing_status(h, outgoing):
    return (
        await query(
            h,
            """SELECT b.status,b.error_code,b.attempt_id,j.status AS job
               FROM app.outbox_events b JOIN platform.messaging_jobs j
                 ON (j.workspace_id,j.outbox_id)=(b.workspace_id,b.id)
               WHERE b.id=:id""",
            id=outgoing["outbox_id"],
        )
    )[0]


@pytest.mark.parametrize("stale", ["CANCELLED", "EXPIRED"])
async def test_r1_stale_commitment_is_terminal_before_wire(scheduling_pg, auth, stale):
    h = scheduling_pg
    token, rose, swallow, scope = await sample(h, auth, hold_ttl=1)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    work = rose if stale == "CANCELLED" else swallow
    narrow_id = "appointment_id" if stale == "CANCELLED" else "hold_id"
    title = "розу" if stale == "CANCELLED" else "ласточку"
    _, _, listed = await chat.say(f"Когда можно на {title} завтра после обеда?")
    offer = offered(listed)
    option = offer["options"][0]
    assert wall(option["visit_start"]) == "12:00"
    choice, generation, outgoing = await chat.say(f"Выбираю {option['code']}", send=False)
    assert outgoing["delivery_status"] == "PENDING"
    outcome = outgoing["result"]
    before = await chat.calendar(auth, offer["date"])
    current = match_calendar(before, work, narrow_id, outcome[narrow_id])
    assert current["outcome"] == ("CONFIRMED" if stale == "CANCELLED" else "HELD")
    counts = (chat.wire.calls, chat.wire.effects)
    assert counts == (1, 1)
    staged = await outgoing_status(h, outgoing)
    assert staged == dict(status="PENDING", error_code=None, attempt_id=None, job="READY")

    if stale == "CANCELLED":
        refs = work.selection.model_dump(include={"client_id", "quote_id", "order_id"})
        response = await command_http(
            auth,
            token,
            appointment_route(work, outcome[narrow_id]) + "/cancel",
            "r1-cancel-before-send",
            refs | {"reason": "Клиент отменил визит"},
        )
        assert response.status_code == 200 and response.json()["outcome"] == stale
    else:
        deadline = datetime.fromisoformat(current["expires_at"])
        await scalar(
            h,
            "SELECT pg_sleep(greatest(extract(epoch FROM :deadline - clock_timestamp()),0)+0.02)",
            deadline=deadline,
        )

    after = await chat.calendar(auth, offer["date"])
    assert after["entries"] == []
    (history,) = after["history"]
    assert history["selection"]["session_id"] == work.selection.session_id
    assert history["booking"][narrow_id] == current[narrow_id]
    assert history["booking"]["outcome"] == stale
    send = await claim_job(h, outgoing["send_job_id"])
    await chat.worker.execute(send)
    terminal = await outgoing_status(h, outgoing)
    assert terminal == dict(status="FAILED", error_code="NOT_ALLOWED", attempt_id=None, job="DEAD")
    assert (chat.wire.calls, chat.wire.effects) == counts
    assert chat.wire.texts == [listed["text"]]

    fresh_wire = SchedulingWire()
    restarted = Worker(h.kernel, fresh_wire, ai=chat.worker.ai)
    await h.kernel.recover_expired()
    await restarted.execute(generation)
    with pytest.raises(MessagingError) as error:
        await restarted.execute(send)
    assert error.value.code == Code.STALE_CLAIM
    await chat.repeat_input(choice)
    assert await outgoing_status(h, outgoing) == terminal
    assert (fresh_wire.calls, fresh_wire.effects, fresh_wire.texts) == (0, 0, [])
    assert (await chat.calendar(auth, offer["date"]))["history"] == after["history"]
    report(
        "R1-stale-" + stale,
        session=work.selection.session_id,
        option=outgoing["option_id"],
        outbox=outgoing["outbox_id"],
        delivered=chat.wire.texts,
        suppressed=outgoing["text"],
        calendar_before=current,
        calendar_after=history["booking"],
        outbox_before=staged,
        outbox_after=terminal,
        counts_before=counts,
        counts_after=(chat.wire.calls, chat.wire.effects),
        counts_restart=(fresh_wire.calls, fresh_wire.effects),
    )


async def test_r1_queries_report_existing_commitments_and_replacement(scheduling_pg, auth):
    h = scheduling_pg
    token, rose, swallow, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    rose_question = "Когда можно на розу завтра после обеда?"
    swallow_question = "Когда можно на ласточку завтра после обеда?"
    _, _, listed = await chat.say(rose_question)
    offer = offered(listed)
    option = offer["options"][0]
    _, _, booked = await chat.say(f"Выбираю {option['code']}")
    appointment = AppointmentResult.model_validate(booked["result"])
    before_move = await chat.calendar(auth, offer["date"])
    original = match_calendar(before_move, rose, "appointment_id", appointment.appointment_id)
    assert wall(original["visit_start"]) == "12:00"

    async def counts():
        return dict(
            await calendar_facts(h),
            offers=await scalar(h, "SELECT count(*) FROM app.availability_offers"),
        )

    rose_counts = await counts()
    _, _, existing = await chat.say(rose_question)
    assert existing["delivery_status"] == "SENT" and existing["result"] == booked["result"]
    assert existing["text"] == booked["text"] and await counts() == rose_counts

    options = await reschedule_offer(h, rose, appointment, date.fromisoformat(offer["date"]))
    later = option_at(options, "10:00")
    refs = rose.selection.model_dump(include={"client_id", "quote_id", "order_id"})
    moved = await command_http(
        auth,
        token,
        appointment_route(rose, appointment.appointment_id) + "/reschedule",
        "r1-reschedule-existing",
        refs | {"option_id": later.option_id, "reason": "Время изменено"},
    )
    assert moved.status_code == 200
    actual = moved.json()["booking"]
    moved_counts = await counts()
    _, _, after_move = await chat.say(rose_question)
    assert after_move["delivery_status"] == "SENT"
    assert after_move["result"]["appointment_id"] == actual["appointment_id"]
    assert "10:00 +0700" in after_move["text"] and "12:00 +0700" not in after_move["text"]
    assert await counts() == moved_counts

    _, _, swallow_list = await chat.say(swallow_question)
    swallow_option = offered(swallow_list)["options"][0]
    _, _, held = await chat.say(f"Выбираю {swallow_option['code']}")
    held_counts = await counts()
    _, _, active_hold = await chat.say(swallow_question)
    assert active_hold["delivery_status"] == "SENT" and active_hold["result"] == held["result"]
    assert active_hold["text"] == held["text"] and "Время удержано до" in active_hold["text"]
    assert await counts() == held_counts
    day = await chat.calendar(auth, offer["date"])
    assert match_calendar(day, rose, "appointment_id", actual["appointment_id"]) == actual
    hold = match_calendar(day, swallow, "hold_id", held["result"]["hold_id"])
    assert wall(hold["visit_start"]) == "12:00"
    assert datetime.fromisoformat(hold["expires_at"]) == datetime.fromisoformat(
        held["result"]["expires_at"]
    )
    assert chat.wire.texts == [
        row["text"]
        for row in (listed, booked, existing, after_move, swallow_list, held, active_hold)
    ]
    assert "Выбор кода подтверждает визит" in listed["text"]
    assert "Выбор кода только удерживает время" in swallow_list["text"]
    assert (chat.wire.calls, chat.wire.effects) == (7, 7)
    report(
        "R1-current-session",
        rose_session=rose.selection.session_id,
        swallow_session=swallow.selection.session_id,
        original=original,
        current=actual,
        active_hold=hold,
        outgoing=[
            {"outbox": row["outbox_id"], "text": row["text"]}
            for row in (booked, existing, after_move, held, active_hold)
        ],
        counts=(chat.wire.calls, chat.wire.effects),
        extra_offers=0,
        extra_bookings=0,
    )


async def test_r1_both_clarification_orders_keep_source_date_at_midnight(scheduling_pg, auth):
    h = scheduling_pg
    _, rose, _, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    day = await scalar(h, "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Novosibirsk')::date")
    midnight = datetime.combine(day + timedelta(days=1), datetime.min.time(), ZoneInfo(ZONE))
    original_at, answer_at = midnight - timedelta(seconds=1), midnight + timedelta(seconds=1)
    conversations = (
        ("Когда можно завтра после обеда?", "Для какой согласованной работы", "На розу"),
        ("Когда можно на розу завтра или послезавтра после обеда?", "На какую дату", "Завтра"),
    )
    receipts = []
    for question, expected, answer in conversations:
        _, _, prompt = await chat.say(question, occurred_at=original_at)
        assert prompt["text"].startswith(expected) and prompt["text"].count("?") == 1
        _, _, result = await chat.say(answer, occurred_at=answer_at)
        offer = offered(result)
        assert result["selection"]["session_id"] == rose.selection.session_id
        assert offer["date"] == midnight.date().isoformat()
        assert wall(offer["options"][0]["visit_start"]) == "12:00"
        assert (await chat.calendar(auth, offer["date"]))["entries"] == []
        receipts.append(
            dict(
                question=question,
                prompt=prompt["text"],
                answer=answer,
                delivered=result["text"],
                origin=prompt["source_message_id"],
                response=result["source_message_id"],
                outbox=result["outbox_id"],
                offer=offer,
            )
        )
    async with shared_controlled_apply(h, receipts[-1]["origin"]) as mutate:
        await mutate()
    code = receipts[-1]["offer"]["options"][0]["code"]
    _, _, rejected = await chat.say(f"Выбираю {code}")
    assert rejected["option_id"] is None and "Этот вариант недоступен" in rejected["text"]
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    report(
        "R1-clarifications",
        session=rose.selection.session_id,
        dialogues=receipts,
        original_local_time=original_at,
        answer_local_time=answer_at,
        stale_origin=rejected["text"],
        counts=(chat.wire.calls, chat.wire.effects),
        occupancy=0,
    )


async def test_r1_deposit_alternatives_respect_earliest_local_start(scheduling_pg, auth):
    h = scheduling_pg
    token, rose, swallow, scope = await sample(h, auth)
    other = await accept_work(h, auth, token, "23 mm")
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    _, _, prompt = await chat.say("Когда можно на ласточку завтра после обеда, в 16:00?")
    assert "Какое самое раннее время" in prompt["text"] and "S-" not in prompt["text"]
    _, _, listed = await chat.say("Не раньше 16:00")
    original = offered(listed)
    assert [wall(slot["visit_start"]) for slot in original["options"]] == [
        "16:00",
        "16:15",
        "16:30",
        "16:45",
    ]
    assert "Выбор кода только удерживает время" in listed["text"]
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)

    rival = SchedulingChat(
        h,
        UUID(other.selection.conversation_id),
        await scope_for(h, UUID(other.selection.conversation_id)),
    )
    _, _, rival_list = await rival.say("Когда можно завтра после обеда, но не раньше 16:00?")
    competing = offered(rival_list)["options"][0]
    assert competing["visit_start"] == original["options"][0]["visit_start"]
    _, _, occupied = await rival.say(f"Выбираю {competing['code']}")
    counts = await calendar_facts(h)
    _, _, conflict = await chat.say(f"Выбираю {original['options'][0]['code']}")
    alternatives = offered(conflict)
    assert (
        "Выбор кода только удерживает время" in conflict["text"]
        and "нужна предоплата" in conflict["text"]
    )
    assert all(wall(slot["visit_start"]) >= "16:00" for slot in alternatives["options"])
    assert await calendar_facts(h) == counts
    _, _, chosen = await chat.say(f"Выбираю {alternatives['options'][0]['code']}")
    calendar = await chat.calendar(auth, original["date"])
    assert match_calendar(calendar, other, "hold_id", occupied["result"]["hold_id"])
    current = match_calendar(calendar, swallow, "hold_id", chosen["result"]["hold_id"])
    assert (chat.wire.calls, chat.wire.effects) == (4, 4)
    report(
        "R1-cutoff-deposit",
        session=swallow.selection.session_id,
        clarification=prompt["text"],
        initial=listed["text"],
        alternatives=conflict["text"],
        alternative_outbox=conflict["outbox_id"],
        selected=chosen["text"],
        selected_outbox=chosen["outbox_id"],
        calendar=current,
        competitor=occupied["result"]["hold_id"],
        counts=(chat.wire.calls, chat.wire.effects),
    )


async def test_s8_rose_none_swallow_deposit_worker_and_calendar(scheduling_pg, auth):
    h = scheduling_pg
    _, rose, swallow, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    first = "Когда можно на розу завтра после обеда?"
    _, _, listing = await chat.say(first)
    roses = offered(listing)
    assert "«роза»" in listing["text"] and "«ласточка»" not in listing["text"]
    assert listing["selection"]["session_id"] == rose.selection.session_id
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    assert not (await chat.calendar(auth, roses["date"]))["entries"]
    assert all(
        12 <= datetime.fromisoformat(o["visit_start"]).astimezone(ZoneInfo(ZONE)).hour < 18
        for o in roses["options"]
    )
    rose_option = roses["options"][0]
    rose_choice = f"Выбираю {rose_option['code']}"
    original, claim, booked = await chat.say(rose_choice)
    assert booked["option_id"] == UUID(rose_option["option_id"])
    assert booked["result"]["outcome"] == "CONFIRMED"
    assert booked["delivery_status"] == "SENT" and "Визит подтверждён" in booked["text"]
    assert await calendar_facts(h) == dict(holds=1, appointments=1, allocations=1)
    await chat.repeat_input(original)
    calls = len(chat.model.requests)
    await chat.worker.execute(claim)
    assert len(chat.model.requests) == calls
    assert (chat.wire.calls, chat.wire.effects) == (2, 2)
    second = "Когда можно на ласточку завтра после обеда?"
    _, _, listing_b = await chat.say(second)
    swallows = offered(listing_b)
    assert "«ласточка»" in listing_b["text"]
    swallow_option = swallows["options"][-1]
    swallow_choice = f"Выбираю {swallow_option['code']}"
    _, held_claim, held = await chat.say(swallow_choice)
    assert held["option_id"] == UUID(swallow_option["option_id"])
    assert held["result"]["outcome"] == "HELD" and held["delivery_status"] == "SENT"
    assert "Время удержано до" in held["text"] and "нужна предоплата" in held["text"]
    assert "Визит подтверждён" not in held["text"]
    assert await calendar_facts(h) == dict(holds=2, appointments=1, allocations=2)
    day = await chat.calendar(auth, roses["date"])
    appointment = match_calendar(day, rose, "appointment_id", booked["result"]["appointment_id"])
    hold = match_calendar(day, swallow, "hold_id", held["result"]["hold_id"])
    assert datetime.fromisoformat(appointment["visit_start"]) == datetime.fromisoformat(
        booked["result"]["visit_start"]
    )
    assert datetime.fromisoformat(hold["expires_at"]) == datetime.fromisoformat(
        held["result"]["expires_at"]
    )
    assert [listing["text"], booked["text"], listing_b["text"], held["text"]] == chat.wire.texts
    _, repeated_claim, repeat = await chat.say(swallow_choice)
    assert repeated_claim.job_id != held_claim.job_id and repeat["outbox_id"] is None
    assert repeat["result"]["original"]["hold_id"] == held["result"]["hold_id"]
    assert repeat["result"]["original"]["expires_at"] == held["result"]["expires_at"]
    assert await calendar_facts(h) == dict(holds=2, appointments=1, allocations=2)
    assert (chat.wire.calls, chat.wire.effects) == (4, 4)
    report(
        "two-works",
        rose=rose.proof(),
        swallow=swallow.proof(),
        appointment=appointment,
        hold=hold,
        dialogue=[
            [first, listing["text"]],
            [rose_choice, booked["text"]],
            [second, listing_b["text"]],
            [swallow_choice, held["text"]],
        ],
        choices=[rose_option, swallow_option],
        outbox=[
            listing["outbox_id"],
            booked["outbox_id"],
            listing_b["outbox_id"],
            held["outbox_id"],
        ],
        list_occupancy=0,
        calls=chat.wire.calls,
        effects=chat.wire.effects,
        repeat_new_run_effects=0,
        duplicate_inbox_effects=0,
    )


async def test_s8_returns_clickable_new_options_after_competition(scheduling_pg, auth):
    h = scheduling_pg
    token, rose, _, scope = await sample(h, auth)
    other = await accept_work(h, auth, token, "23 mm")
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    _, _, listed = await chat.say("Когда можно на розу завтра после обеда, но не раньше 16:00?")
    initial = offered(listed)
    slot = initial["options"][0]
    competitor = SchedulingChat(
        h,
        UUID(other.selection.conversation_id),
        await scope_for(h, UUID(other.selection.conversation_id)),
    )
    _, _, foreign = await competitor.say(f"Выбираю {slot['code']}")
    assert "Этот вариант недоступен" in foreign["text"]
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    _, _, competitor_list = await competitor.say(
        "Когда можно завтра после обеда, но не раньше 16:00?"
    )
    rival = next(
        option
        for option in offered(competitor_list)["options"]
        if option["visit_start"] == slot["visit_start"]
    )
    _, _, rival_result = await competitor.say(f"Выбираю {rival['code']}")
    winner = rival_result["result"]
    assert winner["outcome"] == "HELD"
    _, _, rejected = await chat.say(f"Выбираю {slot['code']}")
    alternatives = offered(rejected)
    assert rejected["result"]["outcome"] == "OPTION_UNAVAILABLE"
    assert "уже занято" in rejected["text"] and other.selection.client_id not in rejected["text"]
    assert "Выбор кода подтверждает визит" in rejected["text"]
    assert wall(initial["options"][0]["visit_start"]) == "16:00"
    assert all(wall(slot["visit_start"]) >= "16:00" for slot in alternatives["options"])
    assert rejected["selection"]["session_id"] == rose.selection.session_id
    times = {o["visit_start"] for o in initial["options"]}
    later = next(o for o in alternatives["options"] if o["visit_start"] not in times)
    _, _, booked = await chat.say(f"Выбираю {later['code']}")
    assert (
        booked["option_id"] == UUID(later["option_id"])
        and booked["result"]["outcome"] == "CONFIRMED"
    )
    day = await chat.calendar(auth, initial["date"])
    assert match_calendar(day, other, "hold_id", winner["hold_id"])
    assert match_calendar(day, rose, "appointment_id", booked["result"]["appointment_id"])
    assert (chat.wire.calls, chat.wire.effects) == (3, 3)
    report(
        "competition",
        winner_hold=winner["hold_id"],
        initial=initial["options"],
        declined_text=rejected["text"],
        new_choice=later,
        booked=booked["result"],
        calls=chat.wire.calls,
        effects=chat.wire.effects,
    )


async def test_s8_clarification_empty_list_and_unconfirmed_code(scheduling_pg, auth):
    h = scheduling_pg
    _, rose, _, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    _, _, work = await chat.say("Когда можно завтра после обеда?")
    _, _, day = await chat.say("Когда можно на розу завтра или послезавтра?")
    _, _, roses = await chat.say("Когда можно на розу завтра после обеда?")
    _, _, swallows = await chat.say("Когда можно на ласточку завтра после обеда?")
    assert offered(roses)["offer_id"] != offered(swallows)["offer_id"]
    _, _, number = await chat.say("первый")
    assert [row["text"].count("?") for row in (work, day, number)] == [1, 1, 1]
    assert "какой согласованной работы" in work["text"]
    assert "какую дату" in day["text"] and "код" in number["text"]
    _, _, pending = await chat.say("Когда можно на розу завтра после обеда?", send=False)
    assert pending["delivery_status"] == "PENDING"
    code = pending["result"]["offer"]["options"][0]["code"]
    _, _, bad = await chat.say(f"Выбираю {code}")
    assert "Этот вариант недоступен" in bad["text"]
    _, _, empty = await chat.say("Когда можно на розу 2099-01-01 после обеда?")
    assert empty["result"]["offer"]["options"] == [] and empty["text"].count("?") == 1
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    report(
        "clarification",
        work=work["text"],
        day=day["text"],
        number=number["text"],
        pending_status=pending["delivery_status"],
        invalid_code_response=bad["text"],
        empty=empty["text"],
        calendar_effects=0,
        calls=chat.wire.calls,
        effects=chat.wire.effects,
    )


async def test_s8_lost_commit_and_unknown_does_not_repeat_wire(scheduling_pg, auth, monkeypatch):
    h = scheduling_pg
    _, rose, _, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    chat.wire.outcome = OutcomeKind.UNKNOWN
    _, _, uncertain = await chat.say("Когда можно на розу завтра после обеда?")
    assert uncertain["delivery_status"] == "UNKNOWN"
    unknown_code = uncertain["result"]["offer"]["options"][0]["code"]
    first_restart = Worker(h.kernel, SchedulingWire(), ai=chat.worker.ai)
    await h.kernel.recover_expired()
    assert (first_restart.adapter.calls, first_restart.adapter.effects) == (0, 0)
    chat.wire.outcome = OutcomeKind.SUCCESS
    _, _, bad = await chat.say(f"Выбираю {unknown_code}")
    assert "Этот вариант недоступен" in bad["text"]
    _, _, sent = await chat.say("Когда можно на розу завтра после обеда?")
    usable = offered(sent)
    checkpoint = h.kernel.checkpoint
    lost = []

    async def after_commit(name):
        await checkpoint(name)
        if name == "scheduling_intent_after_commit":
            lost.append(name)
            raise SQLAlchemyError("synthetic loss of committed result")

    chat.wire.outcome = OutcomeKind.UNKNOWN
    choice = f"Выбираю {usable['options'][0]['code']}"
    with monkeypatch.context() as patch:
        patch.setattr(h.kernel, "checkpoint", after_commit)
        _, winner_claim, committed = await chat.say(choice)
    assert lost == ["scheduling_intent_after_commit"]
    assert (
        committed["delivery_status"] == "UNKNOWN" and committed["result"]["outcome"] == "CONFIRMED"
    )
    restarted = SchedulingWire()
    worker = Worker(h.kernel, restarted, ai=chat.worker.ai)
    await h.kernel.recover_expired()
    await worker.execute(winner_claim)
    assert (restarted.calls, restarted.effects) == (0, 0)
    assert await calendar_facts(h) == dict(holds=1, appointments=1, allocations=1)
    day = await chat.calendar(auth, usable["date"])
    assert match_calendar(day, rose, "appointment_id", committed["result"]["appointment_id"])
    assert (chat.wire.calls, chat.wire.effects) == (4, 4)
    report(
        "unknown-restart",
        list_outbox=uncertain["outbox_id"],
        result_outbox=committed["outbox_id"],
        appointment=committed["result"],
        calls_before=chat.wire.calls,
        effects_before=chat.wire.effects,
        calls_after=restarted.calls,
        effects_after=restarted.effects,
        lost_commit_replays=len(lost),
    )


@pytest.mark.parametrize("fence", ["HUMAN", "CHANNEL"])
async def test_s8_revocation_before_and_after_commit(scheduling_pg, auth, fence):
    h = scheduling_pg
    _, rose, _, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    _, _, listed = await chat.say("Когда можно на розу завтра после обеда?")
    offer_view = offered(listed)
    first = offer_view["options"][0]
    connection = await scalar(
        h, "SELECT connection_id FROM app.conversations WHERE id=:id", id=chat.conversation
    )

    async def revoke():
        if fence == "HUMAN":
            await owner(h, chat.conversation, "TAKEOVER")
        else:
            async with h.migrator.begin() as db:
                await db.execute(
                    text("UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id"),
                    {"id": connection},
                )

    async def restore():
        if fence == "HUMAN":
            await reconcile(h, chat.conversation)
            await owner(h, chat.conversation)
        else:
            async with h.migrator.begin() as db:
                await db.execute(
                    text("UPDATE app.channel_connections SET status='ACTIVE' WHERE id=:id"),
                    {"id": connection},
                )

    chat.model.barrier = revoke
    _, _, rejected = await chat.say(f"Выбираю {first['code']}")
    assert rejected is None
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    assert (chat.wire.calls, chat.wire.effects) == (1, 1)
    await restore()
    chat.model.barrier = None
    _, _, pending = await chat.say(f"Выбираю {first['code']}", send=False)
    assert pending["result"]["outcome"] == "CONFIRMED" and pending["delivery_status"] == "PENDING"
    await revoke()
    try:
        job_status = await scalar(
            h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=pending["send_job_id"]
        )
        if job_status == "READY":
            await chat.worker.execute(await claim_job(h, pending["send_job_id"]))
        box = await scalar(
            h, "SELECT status FROM app.outbox_events WHERE id=:id", id=pending["outbox_id"]
        )
        assert box in {"FAILED", "CANCELLED"}
        day = await chat.calendar(auth, offer_view["date"])
        assert match_calendar(day, rose, "appointment_id", pending["result"]["appointment_id"])
        assert (chat.wire.calls, chat.wire.effects) == (1, 1)
    finally:
        await restore()
    report(
        "fence-" + fence,
        before_commit_allocations=0,
        after_commit=pending["result"],
        delivery_status=box,
        post_revocation_calls=0,
        post_revocation_effects=0,
    )


async def test_s8_business_and_workspace_cannot_choose_a_foreign_code(scheduling_pg, auth):
    h = scheduling_pg
    _, rose, _, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    _, _, listed = await chat.say("Когда можно на розу завтра после обеда?")
    option = offered(listed)["options"][0]
    checked = []
    for workspace, business, actor in ((A, BA2, UA), (B, BB, UB)):
        await publish_configuration(
            h, booking_contract("NONE"), ws=workspace, business=business, actor=actor
        )
        cid, seed, foreign_scope = await source_turn(h, workspace=workspace)
        await Worker(h.kernel, SchedulingWire()).execute(seed)
        foreign = SchedulingChat(
            h, cid, foreign_scope, workspace=workspace, business=business, actor=actor
        )
        _, _, unknown = await foreign.say(f"Выбираю {option['code']}")
        assert unknown["delivery_status"] == "SENT" and "Этот вариант недоступен" in unknown["text"]
        assert unknown["option_id"] is None and unknown["selection"] is None
        assert (foreign.wire.calls, foreign.wire.effects) == (1, 1)
        assert str(chat.conversation) not in unknown["text"]
        checked.append(
            dict(
                workspace=workspace,
                business=business,
                delivery=unknown["delivery_status"],
                allocation=0,
            )
        )
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    _, _, valid = await chat.say(f"Выбираю {option['code']}")
    assert valid["result"]["outcome"] == "CONFIRMED"
    report(
        "business-workspace-isolation",
        foreign=checked,
        own_appointment=valid["result"]["appointment_id"],
    )


async def test_s8_late_processing_uses_original_local_date_and_refuses_stale_source(
    scheduling_pg, auth
):
    h = scheduling_pg
    _, rose, _, scope = await sample(h, auth)
    today = await scalar(h, "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Novosibirsk')::date")
    midnight = datetime.combine(today, datetime.min.time(), ZoneInfo(ZONE))
    earlier = (midnight - timedelta(seconds=1)).astimezone(UTC)
    chat = SchedulingChat(h, UUID(rose.selection.conversation_id), scope)
    _, _, before_midnight = await chat.say("Когда можно на розу завтра?", occurred_at=earlier)
    assert before_midnight["result"]["offer"]["date"] == today.isoformat()
    _, _, listed = await chat.say("Когда можно на розу завтра после обеда?")
    option = offered(listed)["options"][0]
    async with shared_controlled_apply(h, listed["source_message_id"]) as mutate:
        await mutate()

    _, _, rejected = await chat.say(f"Выбираю {option['code']}")
    assert rejected["option_id"] is None and "Этот вариант недоступен" in rejected["text"]
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    _, _, fresh = await chat.say("Когда можно на розу завтра после обеда?")
    new_code = offered(fresh)["options"][0]["code"]

    async def invalidate_choice():
        source = await scalar(
            h,
            """SELECT id FROM app.messages
            WHERE conversation_id=:cid AND direction='INBOUND' ORDER BY id DESC LIMIT 1""",
            cid=chat.conversation,
        )
        async with shared_controlled_apply(h, source) as mutate:
            await mutate()

    chat.model.barrier = invalidate_choice
    calls, effects = chat.wire.calls, chat.wire.effects
    _, _, changed_choice = await chat.say(f"Выбираю {new_code}")
    assert changed_choice is None
    assert (chat.wire.calls, chat.wire.effects) == (calls, effects)
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    report(
        "source-version",
        original_local_day=today,
        delayed_offer_day=before_midnight["result"]["offer"]["date"],
        outcome=rejected["text"],
        appointments=0,
        holds=0,
    )


async def test_s8_expired_offer_and_hold_require_a_new_choice(scheduling_pg, auth):
    h = scheduling_pg
    _, _, swallow, scope = await sample(h, auth)
    chat = SchedulingChat(h, UUID(swallow.selection.conversation_id), scope)
    _, _, listed = await chat.say("Когда можно на ласточку завтра после обеда?")
    before = offered(listed)
    offer_id = UUID(before["offer_id"])
    async with h.migrator.begin() as db:
        await db.execute(
            text("ALTER TABLE app.availability_offers DISABLE TRIGGER scheduling_fact_immutable")
        )
        await db.execute(
            text(
                "UPDATE app.availability_offers SET expires_at=issued_at+interval '1 millisecond' WHERE id=:id"
            ),
            {"id": offer_id},
        )
        await db.execute(
            text("ALTER TABLE app.availability_offers ENABLE TRIGGER scheduling_fact_immutable")
        )
    _, _, stale = await chat.say(f"Выбираю {before['options'][0]['code']}")
    alternatives = offered(stale)
    assert alternatives["offer_id"] != before["offer_id"]
    assert await calendar_facts(h) == dict(holds=0, appointments=0, allocations=0)
    fresh = alternatives["options"][0]
    command = f"Выбираю {fresh['code']}"
    _, _, valid = await chat.say(command)
    assert valid["result"]["outcome"] == "HELD"
    hold_id = valid["result"]["hold_id"]
    async with h.migrator.begin() as db:
        await db.execute(
            text("ALTER TABLE app.reservation_holds DISABLE TRIGGER scheduling_fact_immutable")
        )
        await db.execute(
            text(
                "UPDATE app.reservation_holds SET expires_at=created_at+interval '1 millisecond' WHERE id=:id"
            ),
            {"id": UUID(hold_id)},
        )
        await db.execute(
            text("ALTER TABLE app.reservation_holds ENABLE TRIGGER scheduling_fact_immutable")
        )
    _, _, expired = await chat.say(command)
    assert expired["result"]["hold_id"] == hold_id and expired["result"]["outcome"] == "EXPIRED"
    assert "подобрать окна" in expired["text"]
    assert await calendar_facts(h) == dict(holds=1, appointments=0, allocations=1)
    day = await chat.calendar(auth, alternatives["date"])
    assert not day["entries"] and any(
        row["booking"]["hold_id"] == hold_id for row in day["history"]
    )
    report(
        "expired",
        offer_id=offer_id,
        new_offer_id=alternatives["offer_id"],
        hold_id=hold_id,
        expired_outcome=expired["result"]["outcome"],
        fresh_required=True,
        calls=chat.wire.calls,
        effects=chat.wire.effects,
    )
