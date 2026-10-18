"""Real Python wrapper/worker native0013 carrier on the owned native fixture.

No startup/readiness bypass. Instrumented adapters are observable LOCAL/TEST
seams; these assertions are not live provider or whole-application evidence.
"""

import os
from uuid import UUID

import pytest
import pytest_asyncio
from asm.conversations.guards import GuardedTurnSnapshotV3, consume_guarded
from asm.conversations.turns import TurnSnapshotV3, consume
from asm.foundation import RuntimeDatabase, Settings
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import MessagingError
from asm.messaging.results import ContextHold, ContextWait, ContextWaitExhausted
from asm.messaging.worker import Worker
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import CA, query
from test_m3_1_native_context_postgres import (
    activate,
    claim_job,
    control,
    current_turn,
    duplicate_pending,
    incoming,
    policy,
    read,
    reconcile,
    scalar,
    work_for,
)
from test_m3_1_native_context_postgres import native as native
from test_m3_1_turns_postgres import seal
from test_tenancy_postgres import UA, A

pytestmark = pytest.mark.integration
BOUNDARIES = ("prepare", "accept", "send", "escalation", "test_prepare", "test_finalize")


@pytest_asyncio.fixture
async def native_runtime(native):
    native.kernel = MessagingDatabase(native.runtime.engine, environment="TEST")
    return native


async def setup_boundary(h, boundary):
    cid, _, _ = await activate(h)
    marker = "CONTROLLED ESCALATION TEST" if boundary == "escalation" else None
    await incoming(h, 2, **({"text": marker} if marker else {}))
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    step = (
        "ESCALATE_OWNER"
        if boundary == "escalation"
        else "TEST_CONSUME"
        if boundary.startswith("test_")
        else "GUARDED_TEXT"
    )
    claim = await work_for(h, turn, step)
    saved = None
    accepted = None
    if boundary in ("accept", "send"):
        saved = await h.kernel.prepare_guarded_turn(claim)
        assert type(saved) is GuardedTurnSnapshotV3
    elif boundary == "test_finalize":
        saved = await h.kernel.process_turn(claim)
        assert type(saved) is TurnSnapshotV3
    if boundary == "send":
        accepted = await h.kernel.accept_guarded_text(
            claim, saved.snapshot_digest, consume_guarded(saved).text
        )
        assert accepted.code == "ACCEPTED"
        claim = await claim_job(h, accepted.send_job_id)
    return cid, turn, claim, saved, accepted, marker


async def invoke(h, boundary, claim, saved):
    if boundary == "prepare":
        return await h.kernel.prepare_guarded_turn(claim)
    if boundary == "accept":
        return await h.kernel.accept_guarded_text(
            claim, saved.snapshot_digest, consume_guarded(saved).text
        )
    if boundary == "send":
        return await h.kernel.begin_guarded_send(claim)
    if boundary == "escalation":
        return await h.kernel.request_escalation(claim)
    if boundary == "test_prepare":
        return await h.kernel.process_turn(claim)
    return await h.kernel.finish_turn(claim, consume(saved))


async def execute_boundary(h, boundary, claim, saved):
    worker = Worker(h.kernel, h.adapter)
    if boundary == "accept":
        await worker._finish_guarded(claim, consume_guarded(saved))
    elif boundary == "test_finalize":
        await worker._finish_turn(claim, consume(saved))
    else:
        await worker.execute(claim)


async def job(h, claim):
    return (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id))[
        0
    ]


@pytest.mark.parametrize("boundary", BOUNDARIES)
async def test_python_six_boundaries_wait_commit_lost_ack_replay_single_continuation(
    native_runtime, boundary
):
    h = native_runtime
    cid, turn, claim, saved, accepted, marker = await setup_boundary(h, boundary)
    before_job = await job(h, claim)
    before_context = await read(h, cid)
    duplicate = await duplicate_pending(h, value=marker)
    phase = {
        "prepare": "guard_prepare_after_commit",
        "accept": "guard_accept_after_commit",
        "send": "start_after_commit",
        "escalation": "escalation_create_after_commit",
        "test_prepare": "turn_after_commit",
        "test_finalize": "turn_finalize_after_commit",
    }[boundary]
    losses = 0

    async def lost_ack(name):
        nonlocal losses
        if name == phase:
            losses += 1
            assert losses == 1
            raise SQLAlchemyError("post-commit ACK loss test seam")

    h.kernel._barrier = lost_ack
    try:
        await execute_boundary(h, boundary, claim, saved)
    finally:
        h.kernel._barrier = None
    waited = await h.kernel.replay_context_work(claim.job_id, claim.claim_token)
    assert type(waited) is ContextWait and losses == 1
    after = await job(h, claim)
    assert after["status"] == "READY" and after["version"] == before_job["version"] + 1
    assert (
        after["attempt_count"] == before_job["attempt_count"]
        and after["first_started_at"] == before_job["first_started_at"]
    )
    assert after["context_wait_claim_token"] == claim.claim_token and after[
        "context_wait_result"
    ] == waited.model_dump(mode="json")
    for key in (
        "control_generation",
        "context_version",
        "observation_epoch",
        "policy_epoch",
        "current_revision",
    ):
        assert (await read(h, cid))[key] == before_context[key]
    assert (await read(h, cid))["automation_work"]["state"] == "WAITING_CONTEXT"
    assert h.adapter.calls == 0
    # Historical work lookup must succeed even though scheduling cleared lease.
    assert await invoke(h, boundary, claim, saved) == waited
    assert (await job(h, claim))["version"] == after["version"]
    if accepted:
        assert (
            await scalar(
                h, "SELECT status FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id
            )
            == "PENDING"
        )
    duplicate_claim = await claim_job(h, duplicate.job_id)
    assert (await h.kernel.process_inbox(duplicate_claim)).code == "DUPLICATE"
    next_claim = await claim_job(h, claim.job_id)
    assert (
        next_claim.job_id == claim.job_id
        and next_claim.claim_token != claim.claim_token
        and next_claim.attempt_count == 2
    )
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.replay_context_work(claim.job_id, claim.claim_token)
    await Worker(h.kernel, h.adapter).execute(next_claim)
    if boundary in ("prepare", "accept", "send"):
        rows = await query(
            h,
            "SELECT * FROM platform.turn_guard_receipts WHERE turn_id=:id AND outcome='ACCEPTED'",
            id=turn["id"],
        )
        assert len(rows) == 1
        if boundary != "send":
            send_claim = await claim_job(h, rows[0]["send_job_id"])
            await Worker(h.kernel, h.adapter).execute(send_claim)
        assert h.adapter.calls == 1
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM app.outbox_events WHERE id=:id AND status='SENT'",
                id=rows[0]["outbox_id"],
            )
            == 1
        )
    elif boundary == "escalation":
        assert (
            await scalar(h, "SELECT count(*) FROM app.escalations WHERE turn_id=:id", id=turn["id"])
            == 1
            and h.adapter.calls == 0
        )
    else:
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.turn_consumer_receipts WHERE turn_id=:id",
                id=turn["id"],
            )
            == 1
            and h.adapter.calls == 0
        )
    assert (await job(h, next_claim))["first_started_at"] == before_job["first_started_at"]


@pytest.mark.parametrize("boundary", BOUNDARIES)
async def test_python_six_boundaries_real_deferred_commit_failure_no_optimistic_schedule(
    native_runtime, boundary
):
    h = native_runtime
    cid, _, claim, saved, _, marker = await setup_boundary(h, boundary)
    await duplicate_pending(h, value=marker)
    before = await job(h, claim)
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform.test_runtime_wait_commit_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.context_wait_result IS NOT NULL THEN RAISE EXCEPTION 'native wait test commit failure' USING ERRCODE='23514'; END IF; RETURN NULL; END $$"
            )
        )
        await c.execute(
            text(
                "CREATE CONSTRAINT TRIGGER test_runtime_wait_commit_failure AFTER UPDATE ON platform.messaging_jobs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.test_runtime_wait_commit_failure()"
            )
        )
    try:
        with pytest.raises(SQLAlchemyError):
            await invoke(h, boundary, claim, saved)
        assert await job(h, claim) == before
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            await h.kernel.replay_context_work(claim.job_id, claim.claim_token)
        assert h.adapter.calls == 0
    finally:
        async with h.migrator.begin() as c:
            await c.execute(
                text("DROP TRIGGER test_runtime_wait_commit_failure ON platform.messaging_jobs")
            )
            await c.execute(text("DROP FUNCTION platform.test_runtime_wait_commit_failure()"))
    assert type(await invoke(h, boundary, claim, saved)) is ContextWait
    assert (await read(h, cid))["automation_work"]["state"] == "WAITING_CONTEXT"


@pytest.mark.parametrize("kind", ["hold", "exhausted"])
async def test_python_terminal_context_variants_operator_visibility_no_adapter_or_revival(
    native_runtime, kind
):
    h = native_runtime
    cid, _, claim, saved, _, marker = await setup_boundary(h, "prepare")
    if kind == "hold":
        await policy(h, CA, "PAUSE")
    else:
        await duplicate_pending(h, value=marker)
        # Explicit negative budget injection, not a fabricated policy/receipt.
        await query(
            h,
            "UPDATE platform.messaging_jobs SET attempt_count=5 WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
    result = await h.kernel.prepare_guarded_turn(claim)
    assert type(result) is (ContextHold if kind == "hold" else ContextWaitExhausted)
    assert (await read(h, cid))["automation_work"]["state"] == "OPERATOR_REQUIRED"
    terminal = await job(h, claim)
    await Worker(h.kernel, h.adapter).execute(claim)
    assert await job(h, claim) == terminal and terminal["status"] == "DEAD" and h.adapter.calls == 0
    await control(h, cid, "TAKEOVER")
    assert (await read(h, cid))["automation_work"]["state"] == "IDLE"
    assert (await job(h, claim))["status"] == "DEAD"


async def test_python_native_v3_completed_delivery_history_is_contract_utc6(native_runtime):
    """Executable blocker: frozen0013 recent.completed_at uses raw timestamptz.

    This must pass after C0 assigns the minimal SQL timestamp correction. Keep
    the contract expectation strict; no skip/xfail or Python digest rewrite.
    """
    from uuid import uuid4

    from asm.tenancy import AuthenticatedAccount

    h = native_runtime
    cid, _, _ = await activate(h)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        manual = await unit.messaging_request_text(
            cid, "Completed manual handoff", "native-history"
        )
    sent = await claim_job(
        h,
        await scalar(
            h,
            "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id",
            id=UUID(manual["outbox_id"]),
        ),
    )
    await Worker(h.kernel, h.adapter).execute(sent)
    await reconcile(h, cid)
    await control(h, cid)
    await incoming(h, 2)
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    claim = await work_for(h, turn, "GUARDED_TEXT")
    # Use actual wrapper: a protocol mismatch must fail closed before consume.
    value = await h.kernel.prepare_guarded_turn(claim)
    assert type(value) is GuardedTurnSnapshotV3
    completed = [
        m.delivery.completed_at
        for m in value.recent_messages
        if m.delivery and m.delivery.completed_at
    ]
    assert completed and all(t.endswith("Z") and "." in t for t in completed)


async def test_python_foundation0012_still_refuses_actual_native0013(native_runtime):
    settings = Settings(environment="TEST", database_url=SecretStr(os.environ["ASM_DATABASE_URL"]))
    db = RuntimeDatabase(settings)
    try:
        with pytest.raises(RuntimeError, match="Database capability/schema mismatch"):
            await db.check()
    finally:
        await db.close()
