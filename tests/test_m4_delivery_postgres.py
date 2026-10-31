"""Actual application composition/worker + PG; fake model, no network egress."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from asm.ai.fake import FakeAdapter
from asm.foundation import create_worker
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.models import OutcomeKind
from asm.messaging.results import AIJobClaim
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import query
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER
from test_m3_1_native_context_postgres import claim_job, incoming, migrate, reconcile, scalar
from test_m3_1_turns_postgres import seal
from test_m4_agent import config
from test_m4_runtime_postgres import COUNTER, owner
from test_m4_runtime_postgres import pg as pg
from test_tenancy_postgres import UA, UB, A, B

from scripts.m4_runtime_db import preparation

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def delivery(pg):
    await migrate("upgrade", "0015")
    pg.schema_revision = "0015"
    return pg


async def source_turn(h, *, native=False, workspace=A, telegram=False):
    number = next(COUNTER)
    chat = f"ai-{number}"
    scope = dict(chat_id=chat, sender_id=f"user-{number}")
    if telegram:
        native = True
        scope = dict(provider="TELEGRAM", chat=str(number), sender=str(number))
    elif workspace == B:
        scope.update(bot_identity="bot-b", external_connection_id="conn-b")
    elif not native:
        scope["external_connection_id"] = "conn-a2"
    preparation("INGRESS", workspace_id=workspace)
    _, _, cid = await incoming(h, number, **scope)
    if native:
        preparation("RECONCILE", workspace_id=workspace, conversation_id=cid)
        await reconcile(h, cid)
    preparation("RESUME", workspace_id=workspace, conversation_id=cid)
    await owner(h, cid, workspace=workspace, actor=UA if workspace == A else UB)
    preparation("AI_INGRESS", workspace_id=workspace, conversation_id=cid)
    await incoming(h, next(COUNTER), **scope)
    turn = (
        await query(
            h,
            "SELECT id,workspace_id,connection_id,revision,state FROM app.conversation_turns WHERE workspace_id=:ws AND conversation_id=:id AND ingress_control_mode='AI' ORDER BY first_ingress_at DESC,id DESC LIMIT 1",
            ws=workspace,
            id=cid,
        )
    )[0]
    identity = dict(workspace_id=workspace, connection_id=turn["connection_id"], turn_id=turn["id"])
    preparation("PRE_SEAL", **identity, turn_revision=turn["revision"], state=turn["state"])
    assert turn["workspace_id"] == workspace and turn["state"] == "COLLECTING"
    sealed = await seal(h, turn["id"])
    current = (
        await query(
            h,
            "SELECT id,workspace_id,connection_id,revision,state FROM app.conversation_turns WHERE workspace_id=:ws AND id=:id",
            ws=workspace,
            id=turn["id"],
        )
    )[0]
    preparation(
        "POST_SEAL",
        **identity,
        before_revision=turn["revision"],
        turn_revision=current["revision"],
        state=current["state"],
    )
    assert sealed.code == "GROUPED" and sealed.turn_id == turn["id"] == current["id"]
    assert (
        current["workspace_id"] == workspace and current["connection_id"] == turn["connection_id"]
    )
    assert current["state"] == "READY" and current["revision"] == sealed.turn_revision
    assert current["revision"] != turn["revision"]
    # Keep the revision predicate: the pre-seal revision must not select a consumer.
    lookup = "SELECT id FROM platform.messaging_jobs WHERE workspace_id=:ws AND connection_id=:connection AND turn_id=:id AND turn_revision=:r AND kind='PROCESS_TURN' AND step='TEST_CONSUME'"
    parameters = dict(ws=workspace, connection=turn["connection_id"], id=turn["id"])
    assert await query(h, lookup, **parameters, r=turn["revision"]) == []
    jobs = await query(h, lookup, **parameters, r=current["revision"])
    assert len(jobs) == 1
    source_id = jobs[0]["id"]
    preparation(
        "SOURCE_CLAIM", **identity, source_job_id=source_id, turn_revision=current["revision"]
    )
    source = await claim_job(h, source_id)
    assert (
        source.job_id,
        source.workspace_id,
        source.connection_id,
        source.turn_id,
        source.turn_revision,
        source.step,
    ) == (
        source_id,
        workspace,
        turn["connection_id"],
        turn["id"],
        current["revision"],
        "TEST_CONSUME",
    )
    return cid, source, scope


def application(h, script=("reply",), *, adapter=None, telegram=None, fake=None):
    cfg = config()
    fake = fake or FakeAdapter(cfg.route, script)
    worker = create_worker(
        h.kernel,
        adapter or h.adapter,
        environment="TEST",
        ai_config=cfg,
        model=lambda: fake,
        ai_telegram=telegram,
    )
    return worker, fake


async def enrollment(h, source):
    return (
        await query(
            h, "SELECT * FROM platform.ai_deliveries WHERE source_job_id=:id", id=source.job_id
        )
    )[0]


async def run_turn(h, worker, source):
    await worker.execute(source)
    d = await enrollment(h, source)
    claim = await h.kernel.claim_job("synthetic-ai", ai=True)
    assert isinstance(claim, AIJobClaim) and claim.job_id == d["job_id"]
    await worker.execute(claim)
    return claim, await enrollment(h, source)


@pytest.mark.parametrize(
    "script,kind,calls,reads",
    [
        (("reply",), "reply", 1, 0),
        (("tools", "reply"), "reply", 2, 1),
        (("handoff",), "handoff", 1, 0),
        (("no_reply",), "no_reply", 1, 0),
    ],
)
async def test_application_turn_agent_durable_result_action_and_replay(
    delivery, script, kind, calls, reads
):
    h = delivery
    cid, source, _ = await source_turn(h, native=True)
    worker, fake = application(h, script)
    before = h.adapter.calls
    claim, d = await run_turn(h, worker, source)
    assert d["selected_kind"] == kind and d["run_id"] is not None
    run = (await query(h, "SELECT * FROM platform.ai_runs WHERE id=:id", id=d["run_id"]))[0]
    assert run["result"]["kind"] == kind and (run["calls_used"], run["reads_used"]) == (
        calls,
        reads,
    )
    assert len(fake.requests) == calls
    # New composition/process state recognizes the original immutable result.
    fresh, unused = application(h)
    await fresh.execute(claim)
    await fresh.execute(source)
    assert unused.requests == [] and await enrollment(h, source) == d
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.turn_consumer_receipts WHERE job_id=:id",
            id=source.job_id,
        )
        == 0
    )
    if kind == "reply":
        send = await claim_job(h, d["send_job_id"])
        assert send.kind == "SEND_AI_TEXT"
        await worker.execute(send)
        assert h.adapter.calls == before + 1
        assert (
            await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
            == "SENT"
        )
    elif kind == "handoff":
        e = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=d["escalation_id"]))[0]
        assert (
            e["conversation_id"] == cid
            and e["status"] == "PENDING"
            and e["source_job_step"] == "AI_GENERATE"
        )
        assert d["outbox_id"] is None and h.adapter.calls == before
    else:
        assert d["outbox_id"] is None and d["escalation_id"] is None and h.adapter.calls == before
    assert (
        await scalar(
            h, "SELECT count(*) FROM platform.ai_deliveries WHERE job_id=:id", id=claim.job_id
        )
        == 1
    )


async def test_default_disabled_preserves_original_consumer(delivery):
    h = delivery
    _, source, _ = await source_turn(h)
    worker = create_worker(h.kernel, h.adapter, environment="TEST")
    assert worker.ai is None
    await worker.execute(source)
    assert (
        await query(
            h, "SELECT * FROM platform.ai_deliveries WHERE source_job_id=:id", id=source.job_id
        )
        == []
    )
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.turn_consumer_receipts WHERE job_id=:id",
            id=source.job_id,
        )
        == 1
    )


@pytest.mark.parametrize("change", ["HUMAN", "input", "native"])
async def test_saved_reply_fresh_fences_before_send(delivery, change):
    h = delivery
    cid, source, scope = await source_turn(h, native=True)
    worker, fake = application(h)
    _, d = await run_turn(h, worker, source)
    assert d["selected_kind"] == "reply"
    before = h.adapter.calls
    if change == "input":
        await incoming(h, next(COUNTER), **scope)
    else:
        await owner(h, cid, "TAKEOVER")
        if change == "native":
            await reconcile(h, cid, value="Changed owner context")
            await owner(h, cid)
    send = await claim_job(h, d["send_job_id"])
    await worker.execute(send)
    assert len(fake.requests) == 1 and h.adapter.calls == before
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
        == "FAILED"
    )


async def test_unknown_delivery_never_resends_or_regenerates(delivery):
    h = delivery
    _, source, _ = await source_turn(h)
    transport = ControlledAdapter(environment="TEST", outcome=OutcomeKind.UNKNOWN)
    worker, fake = application(h, adapter=transport)
    claim, d = await run_turn(h, worker, source)
    send = await claim_job(h, d["send_job_id"])
    await worker.execute(send)
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
        == "UNKNOWN"
    )
    await worker.execute(claim)
    assert len(fake.requests) == 1 and transport.calls == 1
    assert (
        await scalar(h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=send.job_id)
        == "DEAD"
    )


async def test_enqueue_concurrency_lost_ack_single_enrollment(delivery):
    h = delivery
    _, source, _ = await source_turn(h)
    worker, _ = application(h)
    count = 0

    async def lost(name):
        nonlocal count
        if name == "ai_enqueue_after_commit" and count == 0:
            count += 1
            raise SQLAlchemyError("synthetic lost ACK")

    h.kernel._barrier = lost
    try:
        await asyncio.gather(worker.execute(source), worker.execute(source))
    finally:
        h.kernel._barrier = None
    d = await enrollment(h, source)
    claims = await asyncio.gather(
        h.kernel.claim_job("ai-one", ai=True), h.kernel.claim_job("ai-two", ai=True)
    )
    winner = [c for c in claims if c is not None]
    assert len(winner) == 1 and winner[0].job_id == d["job_id"] and count == 1
    await worker.execute(winner[0])
    assert (await enrollment(h, source))["selected_kind"] == "reply"


async def test_waiting_ai_allows_inbound_and_manual_progress_and_cancel_is_terminal(delivery):
    from asm.messaging.worker import run
    from test_m2_1_postgres import command

    h = delivery
    cid, source, _ = await source_turn(h)
    entered, stop = asyncio.Event(), asyncio.Event()

    class Waiting(FakeAdapter):
        async def complete(self, request):
            self.requests.append(request)
            entered.set()
            await asyncio.Event().wait()

    fake = Waiting(config().route)
    worker, _ = application(h, fake=fake)
    await worker.execute(source)
    task = asyncio.create_task(run("worker", h.kernel, h.adapter, stop, ai=worker.ai))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        d = await enrollment(h, source)
        lease = (
            await query(
                h,
                "SELECT extract(epoch FROM lease_until-first_started_at) AS seconds FROM platform.messaging_jobs WHERE id=:id",
                id=d["job_id"],
            )
        )[0]
        assert 30 < lease["seconds"] <= 125
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        # Actual ingress and manual command execute while model is suspended.
        _, _, another = await incoming(
            h, next(COUNTER), chat_id="parallel-manual", external_connection_id="conn-a2"
        )
        result = await command(h, another, key=str(uuid4()))
        for _ in range(100):
            if (
                await scalar(
                    h, "SELECT status FROM app.outbox_events WHERE id=:id", id=result.outbox_id
                )
                == "SENT"
            ):
                break
            await asyncio.sleep(0.02)
        assert (
            await scalar(
                h, "SELECT status FROM app.outbox_events WHERE id=:id", id=result.outbox_id
            )
            == "SENT"
        )
    finally:
        task.cancel()
        done, pending = await asyncio.wait({task}, timeout=4)
        assert done == {task} and not pending and task.cancelled()
        assert not stop.is_set()
    assert len(fake.requests) == 1
    assert (
        await scalar(h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=d["job_id"])
        == "DEAD"
    )
    assert await h.kernel.claim_job("restart-ai", ai=True) is None
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE m.conversation_id=:id",
            id=cid,
        )
        == 0
    )


@pytest.mark.parametrize("rights", [True, False])
async def test_synthetic_telegram_real_admission_and_rights_race(delivery, rights):
    h = delivery
    cid, source, scope = await source_turn(h, telegram=True)
    requests = []

    async def handler(request):
        requests.append(request.url.path.rsplit("/", 1)[-1])
        body = json.loads(request.content)
        if requests[-1] == "getBusinessConnection":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "id": EXTERNAL,
                        "user": {"id": int(OWNER), "is_bot": False},
                        "user_chat_id": int(OWNER),
                        "date": 1789990000,
                        "is_enabled": True,
                        "rights": {"can_reply": rights},
                    },
                },
            )
        assert requests[-1] == "sendMessage"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 8899,
                    "chat": {"id": int(body["chat_id"]), "type": "private"},
                    "date": int(datetime.now(UTC).timestamp()),
                    "text": body["text"],
                    "business_connection_id": EXTERNAL,
                },
            },
        )

    settings = TelegramSettings(
        ASM_ENVIRONMENT="TEST",
        ASM_TELEGRAM_ENABLED=True,
        TG_BOT_TOKEN=BOT + ":synthetic_token_123456789",
        TG_WEBHOOK_SECRET="synthetic_webhook_secret_123",
        ASM_TELEGRAM_EXPECTED_BOT_ID=BOT,
        ASM_TELEGRAM_WEBHOOK_URL="https://test.invalid/webhooks/telegram",
    )
    telegram = TelegramClient(settings, transport=httpx.MockTransport(handler))
    try:
        worker, fake = application(h, telegram=telegram)
        _, d = await run_turn(h, worker, source)
        assert d["selected_kind"] == "reply"
        await worker.execute(await claim_job(h, d["send_job_id"]))
        assert requests == (
            ["getBusinessConnection", "sendMessage"] if rights else ["getBusinessConnection"]
        )
        assert len(fake.requests) == 1
        assert await scalar(
            h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"]
        ) == ("SENT" if rights else "FAILED")
    finally:
        await telegram.aclose()


async def test_selected_commit_lost_ack_replays_without_second_call(delivery):
    h = delivery
    _, source, _ = await source_turn(h)
    worker, fake = application(h)
    original = worker.ai.database._command
    losses = 0

    async def lost(claim, operation, **payload):
        nonlocal losses
        value = await original(claim, operation, **payload)
        if operation == "COMMIT":
            losses += 1
            raise SQLAlchemyError("synthetic committed result ACK loss")
        return value

    worker.ai.database._command = lost
    claim, d = await run_turn(h, worker, source)
    assert d["selected_kind"] == "reply" and losses == len(fake.requests) == 1
    fresh, unused = application(h)
    await fresh.execute(claim)
    assert unused.requests == [] and await enrollment(h, source) == d


async def test_dispatching_lost_ack_recovers_unknown_without_transport(delivery):
    h = delivery
    _, source, _ = await source_turn(h)
    worker, fake = application(h)
    _, d = await run_turn(h, worker, source)
    send = await claim_job(h, d["send_job_id"])
    before = h.adapter.calls

    async def lost(name):
        if name == "start_after_commit":
            raise SQLAlchemyError("synthetic DISPATCHING ACK loss")

    h.kernel._barrier = lost
    try:
        with pytest.raises(SQLAlchemyError):
            await worker.execute(send)
    finally:
        h.kernel._barrier = None
    assert h.adapter.calls == before
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
        == "DISPATCHING"
    )
    await scalar(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=send.job_id,
    )
    await h.kernel.recover_expired()
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
        == "UNKNOWN"
    )
    assert h.adapter.calls == before and len(fake.requests) == 1


@pytest.mark.parametrize("cause", ["unknown_cost", "timeout"])
async def test_unknown_charge_or_timeout_terminalizes_without_regeneration(delivery, cause):
    h = delivery
    _, source, _ = await source_turn(h)
    cfg = config(duration_seconds=0.2 if cause == "timeout" else 30)
    fake = FakeAdapter(cfg.route, (cause,))
    worker = create_worker(
        h.kernel, h.adapter, environment="TEST", ai_config=cfg, model=lambda: fake
    )
    claim, d = await run_turn(h, worker, source)
    assert d["selected_kind"] is None and len(fake.requests) == 1
    assert (
        await scalar(h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id)
        == "DEAD"
    )
    fresh, unused = application(h)
    await fresh.execute(claim)
    assert unused.requests == []
    assert await h.kernel.claim_job("restart-after-incomplete", ai=True) is None


@pytest.mark.parametrize("change", ["HUMAN", "input", "native", "observation"])
async def test_authority_changes_during_model_wait_prevent_action(delivery, change):
    h = delivery
    cid, source, scope = await source_turn(h, native=True, telegram=change == "observation")
    entered, release = asyncio.Event(), asyncio.Event()

    class Waiting(FakeAdapter):
        async def complete(self, request):
            entered.set()
            await release.wait()
            return await super().complete(request)

    fake = Waiting(config().route)
    worker, _ = application(h, fake=fake)
    await worker.execute(source)
    d = await enrollment(h, source)
    claim = await h.kernel.claim_job("authority-ai", ai=True)
    assert claim.job_id == d["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if change == "input":
            await incoming(h, next(COUNTER), **scope)
        elif change == "observation":
            await incoming(
                h,
                next(COUNTER),
                **(scope | dict(sender=OWNER)),
                process=False,
                value="New native owner agreement",
            )
        else:
            await owner(h, cid, "TAKEOVER")
            if change == "native":
                await reconcile(h, cid, value="Revised context")
                await owner(h, cid)
        release.set()
        await asyncio.wait_for(task, 5)
        assert len(fake.requests) == 1
        assert (await enrollment(h, source))["selected_kind"] is None
        assert (
            await scalar(
                h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
            )
            == "DEAD"
        )
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
