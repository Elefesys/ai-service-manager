"""Actual application composition/worker + PG; fake model, no network egress."""

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from asm.ai.fake import FakeAdapter
from asm.foundation import create_worker
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind
from asm.messaging.results import AIJobClaim
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_m2_1_postgres import query
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER, observe_owner, observed, worker_sql
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
    await migrate("upgrade", "0017")
    pg.schema_revision = "0017"
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


async def delivery_facts(h, d, fake, stage, **facts):
    job = (
        await query(
            h, "SELECT status,error_code FROM platform.messaging_jobs WHERE id=:id", id=d["job_id"]
        )
    )[0]
    facts.setdefault("adapter_entered", bool(fake.requests))
    preparation(
        stage,
        selected_kind=d["selected_kind"],
        call_count=len(fake.requests),
        job_state=job["status"],
        error_code=job["error_code"],
        has_outbox=d["outbox_id"] is not None,
        **facts,
    )
    return job["status"]


async def refresh_synthetic_observation(h, conversation):
    # Trusted owner capability only: no manual message, no positive timestamp UPDATE.
    probe = (
        await query(
            h,
            "SELECT generation,observation_version FROM platform.telegram_connection_state WHERE workspace_id=:ws AND connection_id=:id",
            ws=A,
            id=h.telegram_connection,
        )
    )[0]
    assert (await observe_owner(h, conversation, probe))["code"] == "OBSERVED"


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

    from scripts.m4_runtime_db import evidence_path, write

    h = delivery
    cid, source, _ = await source_turn(h)
    entered, cancelled, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
    loop = asyncio.get_running_loop()
    started = loop.time()
    facts = {
        "boundary": "waiting_ai",
        "stages": [],
        "error": {"type": "NONE_OBSERVED", "code": "NONE_OBSERVED"},
    }

    def stage(name, **values):
        assert len(facts["stages"]) < 12
        facts.update(values)
        facts["stages"].append({"stage": name, "seconds": round(loop.time() - started, 6)})
        # The carrier strips pytest properties; retain only this bounded, payload-free record.
        if evidence_path().is_dir():
            write(evidence_path() / "waiting-ai-control.json", facts)

    class Waiting(FakeAdapter):
        async def complete(self, request):
            self.requests.append(request)
            entered.set()
            stage(
                "model_entered",
                entry_count=len(self.requests),
                call_count=len(self.requests),
                read_count=request.budget.reads_reserved,
            )
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                stage(
                    "model_cancelled",
                    cancellation_observed=True,
                    cancellation_type="CancelledError",
                    cancellation_code="CANCELLED",
                )
                raise

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
        reservation_count = await scalar(
            h,
            "SELECT count(*) FROM platform.ai_provider_calls p JOIN platform.ai_runs r ON (r.workspace_id,r.id)=(p.workspace_id,p.run_id) WHERE r.job_id=:id",
            id=d["job_id"],
        )
        stage(
            "model_blocked",
            reservation_count=reservation_count,
            lease_valid=True,
            idle_transactions=0,
        )
        assert reservation_count == 1 and not cancelled.is_set() and not task.done()
        assert fake.requests[0].budget.reads_reserved == 0
        # The running worker is the sole consumer. Never claim/process this ingress in the helper.
        number = next(COUNTER)
        receipt = await incoming(
            h, number, process=False, chat_id="parallel-manual", external_connection_id="conn-a2"
        )
        stage("ingress_accepted")
        row = None
        async with asyncio.timeout(5):
            while True:
                rows = await query(
                    h,
                    """SELECT j.step,j.status AS job_status,i.status AS inbox_status,i.result_code,
                      m.conversation_id,
                      j.correlation_id=i.correlation_id AS receipt_correlated,
                      i.connection_id=:connection AND j.connection_id=i.connection_id
                        AND m.connection_id=i.connection_id AND c.connection_id=i.connection_id AS connection_correlated,
                      i.event_id=:event AND m.provider_message_id=:message
                        AND m.provider_chat_id=:chat AND c.provider_chat_id=:chat
                        AND m.direction='INBOUND' AND c.id<>:ai AS message_correlated
                    FROM platform.inbox_events i
                    JOIN platform.messaging_jobs j ON (j.workspace_id,j.inbox_id)=(i.workspace_id,i.id)
                    LEFT JOIN app.messages m ON (m.workspace_id,m.id)=(i.workspace_id,i.message_id)
                    LEFT JOIN app.conversations c ON (c.workspace_id,c.id)=(m.workspace_id,m.conversation_id)
                    WHERE i.workspace_id=:ws AND i.id=:inbox AND j.id=:job""",
                    ws=receipt.workspace_id,
                    inbox=receipt.inbox_id,
                    job=receipt.job_id,
                    connection=source.connection_id,
                    event=f"native-{number}",
                    message=f"native-message-{number}",
                    chat="parallel-manual",
                    ai=cid,
                )
                assert len(rows) == 1
                row = rows[0]
                facts.update(
                    persisted_step=row["step"],
                    job_status=row["job_status"],
                    inbox_status=row["inbox_status"],
                    result_code=row["result_code"],
                    receipt_correlated=row["receipt_correlated"] is True,
                    connection_correlated=row["connection_correlated"] is True,
                    message_correlated=row["message_correlated"] is True,
                )
                assert not task.done() and not cancelled.is_set() and len(fake.requests) == 1
                assert row["job_status"] != "DEAD" and row["inbox_status"] not in {
                    "FAILED",
                    "IGNORED",
                }
                if row["job_status"] == "SUCCEEDED" and row["inbox_status"] == "PROCESSED":
                    break
                await asyncio.sleep(0.02)
        assert receipt.workspace_id == source.workspace_id and row["step"] is None
        assert row["result_code"] == "PROCESSED"
        assert all(
            facts[k] for k in ("receipt_correlated", "connection_correlated", "message_correlated")
        )
        another = row["conversation_id"]
        assert another is not None and another != cid
        stage("ingress_persisted")
        result = await command(h, another, key=str(uuid4()))
        assert not task.done() and not cancelled.is_set() and len(fake.requests) == 1
        stage("manual_command")
        async with asyncio.timeout(5):
            while True:
                sent = (
                    await query(
                        h,
                        """SELECT o.status,m.conversation_id=:conversation AND m.direction='OUTBOUND'
                      AND o.message_id=:message AND o.connection_id=:connection AS correlated
                    FROM app.outbox_events o JOIN app.messages m
                      ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id)
                    WHERE o.workspace_id=:ws AND o.id=:id""",
                        ws=receipt.workspace_id,
                        id=result.outbox_id,
                        conversation=another,
                        message=result.message_id,
                        connection=source.connection_id,
                    )
                )[0]
                facts.update(send_status=sent["status"], send_correlated=sent["correlated"] is True)
                assert not task.done() and not cancelled.is_set() and len(fake.requests) == 1
                assert sent["correlated"] is True and sent["status"] not in {"FAILED", "UNKNOWN"}
                if sent["status"] == "SENT":
                    break
                await asyncio.sleep(0.02)
        stage("manual_sent", model_still_blocked=True)
    except BaseException as exc:
        facts["error"] = {
            "type": type(exc).__name__[:80],
            "code": exc.code.value
            if isinstance(exc, MessagingError)
            else "TIMEOUT"
            if isinstance(exc, TimeoutError)
            else "OPERATION_FAILED",
        }
        raise
    finally:
        task.cancel()
        done, pending = await asyncio.wait({task}, timeout=4)
        stage(
            "worker_joined",
            task_done=task.done(),
            task_cancelled=task.cancelled(),
            stop_unset=not stop.is_set(),
        )
        assert done == {task} and not pending and task.cancelled()
        assert not stop.is_set()
    try:
        assert len(fake.requests) == 1 and cancelled.is_set()
        ai_state = await scalar(
            h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=d["job_id"]
        )
        stage("terminal", ai_job_status=ai_state)
        assert ai_state == "DEAD"
        restart = await h.kernel.claim_job("restart-ai", ai=True)
        facts["restart_none"] = restart is None
        assert restart is None
        outboxes = await scalar(
            h,
            "SELECT count(*) FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE m.conversation_id=:id",
            id=cid,
        )
        facts["ai_outbox_count"] = outboxes
        assert outboxes == 0
        stage("verified")
    except BaseException as exc:
        facts["error"] = {
            "type": type(exc).__name__[:80],
            "code": exc.code.value if isinstance(exc, MessagingError) else "OPERATION_FAILED",
        }
        raise
    finally:
        stage("finished")


@pytest.mark.parametrize("rights", [True, False])
async def test_synthetic_telegram_real_admission_and_rights_race(delivery, rights):
    h = delivery
    if rights:
        # Negative control: expired observation cannot select a send intent.
        _, expired_source, _ = await source_turn(h, telegram=True)
        await scalar(
            h,
            "UPDATE platform.telegram_connection_state SET observed_at=clock_timestamp()-interval '31 seconds' WHERE workspace_id=:ws AND connection_id=:id RETURNING connection_id",
            ws=A,
            id=h.telegram_connection,
        )
        expired_worker, expired_fake = application(h)
        _, expired = await run_turn(h, expired_worker, expired_source)
        await delivery_facts(h, expired, expired_fake, "STALE_OBSERVATION")
        assert expired["selected_kind"] is None
        assert expired["outbox_id"] is None
    cid, source, scope = await source_turn(h, telegram=True)
    await refresh_synthetic_observation(h, cid)
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
                        "rights": {
                            "can_reply": True
                            if requests.count("getBusinessConnection") == 1
                            else rights
                        },
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
        ai_claim, d = await run_turn(h, worker, source)
        await delivery_facts(h, d, fake, "SELECTION")
        assert d["selected_kind"] == "reply"
        assert len(fake.requests) == 1
        completed = False
        try:
            send = await claim_job(h, d["send_job_id"])
            await worker.execute(send)
            completed = True
        finally:
            # No DB query here: preserve counters even when claim/probe/send raises.
            preparation(
                "SEND_ATTEMPT",
                observe_count=requests.count("getBusinessConnection"),
                send_count=requests.count("sendMessage"),
                send_completed=completed,
            )
        await delivery_facts(h, d, fake, "SEND")
        assert requests == (
            ["getBusinessConnection", "getBusinessConnection", "sendMessage"]
            if rights
            else ["getBusinessConnection", "getBusinessConnection"]
        )
        assert len(fake.requests) == 1
        assert await scalar(
            h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"]
        ) == ("SENT" if rights else "FAILED")
        fresh, unused = application(h, telegram=telegram)
        try:
            await fresh.execute(ai_claim)
            await fresh.execute(source)
            with pytest.raises(MessagingError) as caught:
                await fresh.execute(send)
            assert caught.value.code == Code.STALE_CLAIM
            assert unused.requests == [] and await enrollment(h, source) == d
            assert len(fake.requests) == 1
            assert requests == (
                ["getBusinessConnection", "getBusinessConnection", "sendMessage"]
                if rights
                else ["getBusinessConnection", "getBusinessConnection"]
            )
            assert (
                await scalar(
                    h,
                    "SELECT count(*) FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE m.conversation_id=:id",
                    id=cid,
                )
                == 1
            )
        finally:
            preparation(
                "SEND_REPLAY",
                observe_count=requests.count("getBusinessConnection"),
                send_count=requests.count("sendMessage"),
                call_count=len(unused.requests),
            )
    finally:
        await telegram.aclose()


@pytest_asyncio.fixture(loop_scope="module")
async def positive_reply_rights_client():
    from test_m4_reply_rights_postgres import connection, telegram

    client = telegram(lambda request: connection())
    try:
        yield client
    finally:
        await client.aclose()


async def test_ai_probe_claim_version_tenant_and_foreign_observation_guards(
    delivery, positive_reply_rights_client
):
    h = delivery
    cid, source, _ = await source_turn(h, telegram=True)
    await refresh_synthetic_observation(h, cid)
    worker, fake = application(h, telegram=positive_reply_rights_client)
    _, d = await run_turn(h, worker, source)
    assert d["selected_kind"] == "reply" and len(fake.requests) == 1
    send = await claim_job(h, d["send_job_id"])
    probe = await h.kernel.telegram_probe(send)
    assert probe is not None
    before = await scalar(
        h, "SELECT to_jsonb(o) FROM app.outbox_events o WHERE id=:id", id=d["outbox_id"]
    )
    for bad_claim, bad_probe in (
        (send.model_copy(update={"claim_token": uuid4()}), probe),
        (send, None),
        (send, probe.model_copy(update={"generation": probe.generation + 1})),
        (send, probe.model_copy(update={"observation_version": probe.observation_version + 1})),
    ):
        with pytest.raises(MessagingError) as caught:
            await h.kernel.begin_ai_send(bad_claim, bad_probe, observed())
        assert caught.value.code == Code.STALE_CLAIM
        assert (
            await scalar(
                h, "SELECT to_jsonb(o) FROM app.outbox_events o WHERE id=:id", id=d["outbox_id"]
            )
            == before
        )
    _, foreign, _ = await source_turn(h, workspace=B)
    with pytest.raises(DBAPIError) as caught:
        await worker_sql(
            h,
            send,
            "SELECT platform.telegram_worker_probe(:other_job,:other_claim)",
            other_job=foreign.job_id,
            other_claim=foreign.claim_token,
        )
    assert caught.value.orig.sqlstate == "P2001"
    assert caught.value.orig.diag.message_primary == "STALE_CLAIM"
    assert (
        await scalar(
            h,
            "SELECT telegram_probe_claim FROM platform.messaging_jobs WHERE id=:id",
            id=foreign.job_id,
        )
        is None
    )
    rejected = await h.kernel.begin_ai_send(
        send, probe, observed(external_connection_id="synthetic-foreign-connection")
    )
    assert (rejected.code, rejected.status) == ("NOT_ALLOWED", "FAILED")
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
        == "FAILED"
    )
    assert len(fake.requests) == 1


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


async def test_valid_output_unknown_metering_keeps_reserve_and_replays_without_regeneration(
    delivery,
):
    h = delivery
    _, source, _ = await source_turn(h)
    cfg = config()
    fake = FakeAdapter(cfg.route, ("unknown_cost",))
    worker = create_worker(
        h.kernel, h.adapter, environment="TEST", ai_config=cfg, model=lambda: fake
    )
    claim, d = await run_turn(h, worker, source)
    state = await delivery_facts(h, d, fake, "SELECTION")
    assert d["selected_kind"] == "reply"
    assert len(fake.requests) == 1
    assert state == "SUCCEEDED"
    run = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id))[0]
    calls = await query(
        h, "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"]
    )
    preparation(
        "SELECTION",
        has_result=run["result"] is not None,
        reservation_count=len(calls),
        reserve_held=run["cost_reserved"] == cfg.limits.call_cost_reservation > 0,
        completion_unknown_metering=len(calls) == 1
        and calls[0]["completion"]["cost"]
        == {"status": "UNKNOWN", "amount": None, "currency": None},
    )
    assert len(calls) == 1 and run["calls_used"] == 1
    assert run["result"]["kind"] == "reply" and d["run_id"] == run["id"]
    assert run["cost_reserved"] == cfg.limits.call_cost_reservation > 0
    assert Decimal(calls[0]["budget"]["cost_reserved"]) == run["cost_reserved"]
    assert calls[0]["completion"] == {
        "kind": "OUTPUT",
        "usage": {"input_tokens": None, "output_tokens": None},
        "cost": {"status": "UNKNOWN", "amount": None, "currency": None},
        "error": None,
    }
    assert calls[0]["completed_at"] is not None
    assert d["outbox_id"] is not None and d["send_job_id"] is not None
    fresh, unused = application(h)
    await fresh.execute(claim)
    await fresh.execute(source)
    await delivery_facts(h, await enrollment(h, source), unused, "REPLAY")
    assert unused.requests == []
    assert await enrollment(h, source) == d
    assert (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id)) == [
        run
    ]
    assert (
        await query(h, "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"])
    ) == calls
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.ai_deliveries WHERE source_job_id=:id",
            id=source.job_id,
        )
        == 1
    )
    assert (
        await scalar(h, "SELECT count(*) FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
        == 1
    )


async def test_in_call_timeout_terminalizes_without_result_or_regeneration(delivery):
    h = delivery
    cid, source, _ = await source_turn(h)
    cfg = config(duration_seconds=10)
    entered = asyncio.Event()

    class Waiting(FakeAdapter):
        cancelled = False

        async def complete(self, request):
            entered.set()
            try:
                return await super().complete(request)
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    fake = Waiting(cfg.route, ("timeout",))
    worker = create_worker(
        h.kernel, h.adapter, environment="TEST", ai_config=cfg, model=lambda: fake
    )
    await worker.execute(source)
    d = await enrollment(h, source)
    claim = await h.kernel.claim_job("synthetic-timeout", ai=True)
    assert isinstance(claim, AIJobClaim) and claim.job_id == d["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    signal = asyncio.create_task(entered.wait())
    try:
        await asyncio.wait(
            {task, signal},
            timeout=cfg.limits.duration_seconds + 2,
            return_when=asyncio.FIRST_COMPLETED,
        )
        await delivery_facts(
            h, await enrollment(h, source), fake, "MODEL_ENTER", adapter_entered=entered.is_set()
        )
        assert entered.is_set(), "one-call scenario must actually enter the adapter"
        assert len(fake.requests) == 1
        reservations = await scalar(
            h,
            "SELECT count(*) FROM platform.ai_provider_calls p JOIN platform.ai_runs r ON (r.workspace_id,r.id)=(p.workspace_id,p.run_id) WHERE r.job_id=:id",
            id=claim.job_id,
        )
        preparation("MODEL_ENTER", reservation_count=reservations)
        assert reservations == 1
        # Only the real runtime deadline expires; never inject a timeout or cancel
        # the successful path to turn a pre-model expiration into one model call.
        await asyncio.wait_for(asyncio.shield(task), cfg.limits.duration_seconds + 3)
    finally:
        for pending in (signal, task):
            if not pending.done():
                pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
    d = await enrollment(h, source)
    state = await delivery_facts(
        h, d, fake, "TIMEOUT", adapter_entered=entered.is_set(), adapter_cancelled=fake.cancelled
    )
    assert fake.cancelled
    assert len(fake.requests) == 1
    assert d["selected_kind"] is None
    assert d["outbox_id"] is None
    assert state == "DEAD"
    run = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id))[0]
    assert run["result"] is None and run["calls_used"] == 1
    calls = await query(
        h, "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"]
    )
    preparation(
        "TIMEOUT",
        has_result=run["result"] is not None,
        reservation_count=len(calls),
        reserve_held=run["cost_reserved"] == cfg.limits.call_cost_reservation > 0,
    )
    assert len(calls) == 1 and calls[0]["completion"]["kind"] == "UNKNOWN"
    assert run["cost_reserved"] == cfg.limits.call_cost_reservation > 0
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE m.conversation_id=:id",
            id=cid,
        )
        == 0
    )
    fresh, unused = application(h)
    await fresh.execute(claim)
    await delivery_facts(h, await enrollment(h, source), unused, "REPLAY")
    assert unused.requests == []
    assert await enrollment(h, source) == d
    assert (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id)) == [
        run
    ]
    assert (
        await query(h, "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"])
    ) == calls
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
