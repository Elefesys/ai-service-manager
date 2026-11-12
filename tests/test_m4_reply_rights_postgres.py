"""Real PostgreSQL/worker path; every Telegram request uses MockTransport."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from asm.ai.agent import ConversationAgent
from asm.ai.database import DurableAdapter
from asm.ai.fake import FakeAdapter
from asm.foundation import create_worker
from asm.messaging.errors import Code, MessagingError
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import query
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER
from test_m3_1_native_context_postgres import claim_job, incoming, migrate, scalar
from test_m4_agent import config
from test_m4_delivery_postgres import application, enrollment, run_turn, source_turn
from test_m4_delivery_postgres import delivery as delivery
from test_m4_runtime_postgres import COUNTER, intent, owner
from test_m4_runtime_postgres import pg as pg
from test_tenancy_postgres import A, B

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


def telegram(handler):
    return TelegramClient(
        TelegramSettings(
            ASM_ENVIRONMENT="TEST",
            ASM_TELEGRAM_ENABLED=True,
            TG_BOT_TOKEN=BOT + ":synthetic_token_123456789",
            TG_WEBHOOK_SECRET="synthetic_webhook_secret_123",
            ASM_TELEGRAM_EXPECTED_BOT_ID=BOT,
            ASM_TELEGRAM_WEBHOOK_URL="https://test.invalid/webhooks/telegram",
        ),
        transport=httpx.MockTransport(handler),
    )


def connection(*, enabled=True, reply=True):
    return httpx.Response(
        200,
        json={
            "ok": True,
            "result": {
                "id": EXTERNAL,
                "user": {"id": int(OWNER), "is_bot": False},
                "user_chat_id": int(OWNER),
                "date": 1789990000,
                "is_enabled": enabled,
                "rights": {"can_reply": reply},
            },
        },
    )


async def test_expired_rights_are_observed_before_reply_commit_and_again_before_send(delivery):
    h = delivery
    _, source, _ = await source_turn(h, telegram=True)
    # Expiry fault only; the runtime must obtain a real mocked observation.
    await scalar(
        h,
        "UPDATE platform.telegram_connection_state SET observed_at=clock_timestamp()-interval '31 seconds' WHERE workspace_id=:ws AND connection_id=:id RETURNING connection_id",
        ws=A,
        id=h.telegram_connection,
    )
    requests = []

    async def handler(request):
        method = request.url.path.rsplit("/", 1)[-1]
        requests.append(method)
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        if method == "getBusinessConnection":
            return connection()
        assert method == "sendMessage"
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 8801,
                    "chat": {"id": int(body["chat_id"]), "type": "private"},
                    "date": int(datetime.now(UTC).timestamp()),
                    "text": body["text"],
                    "business_connection_id": EXTERNAL,
                },
            },
        )

    client = telegram(handler)
    try:
        worker, fake = application(h, telegram=client)
        claim, d = await run_turn(h, worker, source)
        assert len(fake.requests) == 1
        assert d["selected_kind"] == "reply" and d["outbox_id"] is not None
        assert requests == ["getBusinessConnection"]
        send = await claim_job(h, d["send_job_id"])
        await worker.execute(send)
        assert requests == ["getBusinessConnection", "getBusinessConnection", "sendMessage"]
        assert (
            await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
            == "SENT"
        )
        await worker.execute(claim)
        assert len(fake.requests) == 1 and len(requests) == 3
    finally:
        await client.aclose()


async def no_selection(h, d, fake):
    saved = (
        await query(h, "SELECT * FROM platform.ai_deliveries WHERE job_id=:id", id=d["job_id"])
    )[0]
    assert saved["selected_kind"] is saved["outbox_id"] is None
    run = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=d["job_id"]))[0]
    assert run["result"] is None and run["calls_used"] == len(fake.requests) == 1
    completion = await scalar(
        h, "SELECT completion FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"]
    )
    assert completion["kind"] == "OUTPUT"
    assert run["cost_reserved"] > 0


@pytest.mark.parametrize(
    "failure", ["revoked", "disabled", "unknown", "timeout", "owner", "connection"]
)
async def test_negative_observation_is_saved_without_reply_or_outbox(delivery, failure):
    h = delivery
    _, source, _ = await source_turn(h, telegram=True)
    version = await scalar(
        h,
        "SELECT observation_version FROM platform.telegram_connection_state WHERE connection_id=:id",
        id=h.telegram_connection,
    )
    requests = []

    async def handler(request):
        requests.append(request.url.path.rsplit("/", 1)[-1])
        assert requests == ["getBusinessConnection"]
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic observation timeout")
        if failure == "unknown":
            return httpx.Response(503)
        result = connection(enabled=failure != "disabled", reply=failure != "revoked").json()
        if failure == "owner":
            result["result"]["user"]["id"] = 987654321
        if failure == "connection":
            result["result"]["id"] = "synthetic-foreign"
        return httpx.Response(200, json=result)

    client = telegram(handler)
    try:
        worker, fake = application(h, telegram=client)
        claim, d = await run_turn(h, worker, source)
        await no_selection(h, d, fake)
        state = (
            await query(
                h,
                "SELECT * FROM platform.telegram_connection_state WHERE connection_id=:id",
                id=h.telegram_connection,
            )
        )[0]
        assert state["observation_version"] == version + 1
        if failure in {"revoked", "disabled"}:
            assert state["error_code"] is None
            assert state["can_reply"] is False or state["is_enabled"] is False
        else:
            assert state["error_code"] is not None and state["can_reply"] is None
        await worker.execute(claim)
        assert len(fake.requests) == len(requests) == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("change", ["generation", "version", "context", "human", "lease"])
async def test_state_changed_during_http_cannot_select_a_reply(delivery, change):
    h = delivery
    cid, source, scope = await source_turn(h, telegram=True)
    requests = []

    async def handler(request):
        requests.append(request.url.path.rsplit("/", 1)[-1])
        assert requests == ["getBusinessConnection"]
        if change in {"generation", "version"}:
            assignment = (
                "generation=generation+1,observation_version=observation_version+1"
                if change == "generation"
                else "observation_version=observation_version+1"
            )
            await scalar(
                h,
                f"UPDATE platform.telegram_connection_state SET {assignment} WHERE connection_id=:id RETURNING connection_id",
                id=h.telegram_connection,
            )
        elif change == "context":
            await incoming(h, next(COUNTER), **scope)
        elif change == "human":
            await owner(h, cid, "TAKEOVER")
        else:
            await scalar(
                h,
                "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE kind='PROCESS_TURN' AND step='AI_GENERATE' AND status='RUNNING' RETURNING id",
            )
        return connection()

    client = telegram(handler)
    try:
        worker, fake = application(h, telegram=client)
        _, d = await run_turn(h, worker, source)
        await no_selection(h, d, fake)
        assert requests == ["getBusinessConnection"]
    finally:
        await client.aclose()


@pytest.mark.parametrize("kind", ["no_reply", "handoff", "controlled", "db_only"])
async def test_paths_without_telegram_reply_do_not_probe_or_observe(delivery, kind, monkeypatch):
    h = delivery

    async def forbidden(*args, **kwargs):
        raise AssertionError("No reply-rights probe permitted on this path")

    client = telegram(forbidden)
    try:
        if kind in {"no_reply", "handoff", "db_only"}:
            monkeypatch.setattr(h.kernel, "ai_reply_probe", forbidden)
        if kind == "db_only":
            _, claim, _ = await intent(h, telegram=True)
            cfg = config()
            fake = FakeAdapter(cfg.route, ("reply",))
            receipt = await h.ai.execute(
                claim,
                cfg,
                fake,
                deadline=datetime.now(UTC) + timedelta(seconds=30),
                telegram=client,
            )
            assert receipt.result.kind == "reply"
        else:
            _, source, _ = await source_turn(h, telegram=kind != "controlled")
            worker, fake = application(
                h, ("reply" if kind == "controlled" else kind,), telegram=client
            )
            _, d = await run_turn(h, worker, source)
            assert d["selected_kind"] == ("reply" if kind == "controlled" else kind)
        assert len(fake.requests) == 1
    finally:
        await client.aclose()


async def prepared_reply(h, source):
    worker, fake = application(h)
    await worker.execute(source)
    d = await enrollment(h, source)
    claim = await h.kernel.claim_job("rights-boundary", ai=True)
    assert claim.job_id == d["job_id"]
    db, cfg = worker.ai.database, worker.ai.config
    run = await db.prepare(claim, cfg, deadline=datetime.now(UTC) + timedelta(seconds=30))
    outcome = await ConversationAgent(
        cfg, DurableAdapter(db, claim, run, fake), db.authority(claim, run)
    ).run(run.binding, run.snapshot, run_id=str(run.run_id), deadline=run.deadline)
    assert outcome.candidate.kind == "reply"
    return worker, fake, claim, run, outcome.candidate


@pytest.mark.parametrize("fault", ["claim", "foreign_run", "unprobed", "generation", "version"])
async def test_reply_capability_is_bound_to_claim_run_and_original_probe(delivery, fault):
    h = delivery
    _, source, _ = await source_turn(h, telegram=True)
    worker, fake, claim, run, candidate = await prepared_reply(h, source)
    before = await scalar(
        h,
        "SELECT observation_version FROM platform.telegram_connection_state WHERE connection_id=:id",
        id=h.telegram_connection,
    )
    if fault in {"claim", "foreign_run"}:
        wrong = claim.model_copy(update={"claim_token": uuid4()}) if fault == "claim" else claim
        target_run = run.run_id
        if fault == "foreign_run":
            _, foreign_source, _ = await source_turn(h, workspace=B)
            foreign_worker, _ = application(h)
            await foreign_worker.execute(foreign_source)
            foreign = await enrollment(h, foreign_source)
            foreign_claim = await h.kernel.claim_job("rights-foreign", ai=True)
            assert foreign_claim.job_id == foreign["job_id"]
            foreign_run = await foreign_worker.ai.database.prepare(
                foreign_claim,
                foreign_worker.ai.config,
                deadline=datetime.now(UTC) + timedelta(seconds=30),
            )
            target_run = foreign_run.run_id
        with pytest.raises(MessagingError):
            await h.kernel.ai_reply_probe(wrong, target_run)
        if fault == "foreign_run":
            await foreign_worker.ai.stop(foreign_claim)
    else:
        probe = await h.kernel.ai_reply_probe(claim, run.run_id)
        if fault == "unprobed":
            await scalar(
                h,
                "UPDATE platform.messaging_jobs SET telegram_probe_claim=NULL,telegram_probe_generation=NULL,telegram_probe_version=NULL WHERE id=:id RETURNING id",
                id=claim.job_id,
            )
        else:
            probe = probe.model_copy(
                update={
                    "generation" if fault == "generation" else "observation_version": (
                        probe.generation if fault == "generation" else probe.observation_version
                    )
                    + 1
                }
            )
        from test_m2_3_db_postgres import observed

        with pytest.raises(MessagingError) as caught:
            await h.kernel.commit_ai_reply(
                claim, run.run_id, probe, observed(), candidate.model_dump(mode="json")
            )
        assert caught.value.code == Code.STALE_CLAIM
    assert (
        await scalar(
            h,
            "SELECT observation_version FROM platform.telegram_connection_state WHERE connection_id=:id",
            id=h.telegram_connection,
        )
        == before
    )
    await worker.ai.stop(claim)
    await no_selection(h, await enrollment(h, source), fake)


@pytest.mark.parametrize("mode", ["deadline", "cancel"])
async def test_observation_is_inside_original_deadline_and_cancellation(delivery, mode):
    h = delivery
    _, source, _ = await source_turn(h, telegram=True)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def handler(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client = telegram(handler)
    cfg = config(duration_seconds=0.8 if mode == "deadline" else 30)
    fake = FakeAdapter(cfg.route, ("reply",))
    worker = create_worker(
        h.kernel,
        h.adapter,
        environment="TEST",
        ai_config=cfg,
        model=lambda: fake,
        ai_telegram=client,
    )
    try:
        await worker.execute(source)
        d = await enrollment(h, source)
        claim = await h.kernel.claim_job("rights-deadline", ai=True)
        assert claim.job_id == d["job_id"]
        task = asyncio.create_task(worker.execute(claim))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            if mode == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await asyncio.wait_for(task, 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert cancelled.is_set()
        await no_selection(h, d, fake)
        await worker.execute(claim)
        assert len(fake.requests) == 1
    finally:
        await client.aclose()


async def test_selected_reply_lost_ack_replays_without_second_observation(delivery):
    h = delivery
    _, source, _ = await source_turn(h, telegram=True)
    requests = []

    async def handler(request):
        requests.append(request.url.path.rsplit("/", 1)[-1])
        assert requests == ["getBusinessConnection"]
        return connection()

    client = telegram(handler)
    lost = 0

    async def checkpoint(name):
        nonlocal lost
        if name == "ai_reply_after_commit" and lost == 0:
            lost += 1
            raise SQLAlchemyError("synthetic lost commit ACK")

    h.kernel._barrier = checkpoint
    try:
        worker, fake = application(h, telegram=client)
        claim, d = await run_turn(h, worker, source)
        assert d["selected_kind"] == "reply" and d["outbox_id"] is not None and lost == 1
        await worker.execute(claim)
        assert len(fake.requests) == 1 and requests == ["getBusinessConnection"]
        assert (
            await scalar(
                h, "SELECT count(*) FROM app.outbox_events WHERE id=:id", id=d["outbox_id"]
            )
            == 1
        )
    finally:
        h.kernel._barrier = None
        await client.aclose()


async def test_downgrade_restores_previous_catalog_without_losing_results_or_cost(delivery):
    h = delivery
    before = {}
    for table in ("ai_runs", "ai_provider_calls", "ai_deliveries"):
        before[table] = await scalar(
            h, f"SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM platform.{table} t"
        )
    outbox = await scalar(
        h, "SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM app.outbox_events t"
    )
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.messaging_jobs WHERE kind='PROCESS_TURN' AND step='AI_GENERATE' AND telegram_probe_claim IS NOT NULL",
        )
        > 0
    )
    await migrate("downgrade", "0016")
    try:
        profile = await scalar(h, "SELECT platform.ai_provider_schema_profile()")
        assert profile["valid"] and profile["schema_revision"] == "0016"
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.messaging_jobs WHERE kind='PROCESS_TURN' AND telegram_probe_claim IS NOT NULL",
            )
            == 0
        )
        for table, saved in before.items():
            assert (
                await scalar(
                    h,
                    f"SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM platform.{table} t",
                )
                == saved
            )
        assert (
            await scalar(
                h,
                "SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM app.outbox_events t",
            )
            == outbox
        )
    finally:
        try:
            await migrate("upgrade", "0017")
            historical = await scalar(h, "SELECT platform.ai_reply_rights_schema_profile()")
            assert historical["valid"] and historical["schema_revision"] == "0017"
        finally:
            await migrate("upgrade", "0018")
    profile = await scalar(h, "SELECT platform.business_configuration_schema_profile()")
    assert profile["valid"] and profile["schema_revision"] == "0018"
