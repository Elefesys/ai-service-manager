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


# PG-R2 additions. The complete R1 prefix above is intentionally immutable.
async def runtime_effects(h, claim):
    """Read-only migrator inspection; application calls still use asm_runtime."""
    tables = {
        "app.messages": "id",
        "app.conversation_turns": "id",
        "app.escalations": "id",
        "app.audit_events": "audit_event_id",
        "app.file_objects": "id",
        "platform.file_object_uploads": "id",
        "platform.turn_guard_receipts": "job_id",
        "platform.turn_consumer_receipts": "job_id",
        "platform.human_context_reconciliations": "id",
    }
    result = {
        table: [dict(row) for row in await query(h, f"SELECT * FROM {table} ORDER BY {order}")]
        for table, order in tables.items()
    }
    result["other_jobs"] = [
        dict(row)
        for row in await query(
            h, "SELECT * FROM platform.messaging_jobs WHERE id<>:id ORDER BY id", id=claim.job_id
        )
    ]
    return result


def runtime_sql_trace(h, statements):
    """Observe outer runtime SQL without replacing admission or any capability."""
    from contextlib import contextmanager

    from sqlalchemy import event

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    @contextmanager
    def attached():
        engine = h.runtime.engine.sync_engine
        event.listen(engine, "before_cursor_execute", record)
        try:
            yield
        finally:
            event.remove(engine, "before_cursor_execute", record)

    return attached()


@pytest.mark.parametrize(
    "boundary", ["accept", "send", "escalation", "test_prepare", "test_finalize"]
)
@pytest.mark.parametrize("kind", ["hold", "exhausted"])
async def test_python_remaining_boundaries_terminal_work_replay_and_takeover(
    native_runtime, monkeypatch, boundary, kind
):
    """Actual Worker/wrapper/SQL terminal matrix; only exhaustion is a fault seam."""
    from asm.messaging.errors import Code

    h = native_runtime
    cid, turn, claim, saved, accepted, marker = await setup_boundary(h, boundary)
    # No successful receipt may preempt the boundary under test. The send case
    # alone needs its real prior ACCEPTED guarded intent, on a different Job.
    if boundary == "accept":
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            await h.kernel.replay_guarded_text(
                claim.job_id, claim.claim_token, saved.snapshot_digest, consume_guarded(saved).text
            )
    elif boundary.startswith("test_"):
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            await h.kernel.replay_turn(claim.job_id, claim.claim_token)
    elif boundary == "escalation":
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            await h.kernel.replay_escalation(claim.job_id, claim.claim_token)
    else:
        assert accepted.code == "ACCEPTED" and accepted.send_job_id == claim.job_id
    if kind == "hold":
        await policy(h, CA, "PAUSE")
    else:
        await duplicate_pending(h, value=marker)
        # Retained explicit negative budget injection, never authority/receipt DML.
        changed = await query(
            h,
            "UPDATE platform.messaging_jobs SET attempt_count=5 WHERE id=:id AND status='RUNNING' AND claim_token=:token RETURNING id",
            id=claim.job_id,
            token=claim.claim_token,
        )
        assert [row["id"] for row in changed] == [claim.job_id]
    before = await job(h, claim)
    effects = await runtime_effects(h, claim)
    before_context = await read(h, cid)
    boxes = await query(h, "SELECT * FROM app.outbox_events ORDER BY id")
    assert len(boxes) == (1 if accepted else 0)
    assert len(effects["platform.turn_guard_receipts"]) == (1 if accepted else 0)
    assert not effects["platform.turn_consumer_receipts"] and not effects["app.escalations"]
    assert before["status"] == "RUNNING" and before["claim_token"] == claim.claim_token
    assert before["context_wait_result"] is None and before["context_wait_claim_token"] is None
    method = {
        "accept": "accept_guarded_text",
        "send": "begin_guarded_send",
        "escalation": "request_escalation",
        "test_prepare": "process_turn",
        "test_finalize": "finish_turn",
    }[boundary]
    sql_function = {
        "accept": "guard_turn_accept",
        "send": "guard_send_begin",
        "escalation": "escalation_request_for_turn",
        "test_prepare": "turn_execute",
        "test_finalize": "turn_consumer_finalize",
    }[boundary]
    original = getattr(h.kernel, method)
    returned = []

    async def observe(*args, **kwargs):
        result = await original(*args, **kwargs)
        returned.append(result)
        return result

    monkeypatch.setattr(h.kernel, method, observe)
    statements = []
    with runtime_sql_trace(h, statements):
        await execute_boundary(h, boundary, claim, saved)
    assert any("platform." + sql_function + "(" in statement for statement in statements)
    assert len(returned) == 1
    result = returned[0]
    assert type(result) is (ContextHold if kind == "hold" else ContextWaitExhausted)
    reason = "CONTEXT_POLICY_PAUSED" if kind == "hold" else "CONTEXT_WAIT_EXHAUSTED"
    error = "NOT_ALLOWED" if kind == "hold" else "RETRY_EXHAUSTED"
    assert (result.job_id, result.turn_id, result.turn_revision, result.outbox_id) == (
        claim.job_id,
        turn["id"],
        turn["revision"],
        accepted.outbox_id if accepted else None,
    )
    assert result.status == "DEAD" and result.reason == reason and result.available_at is None
    terminal = await job(h, claim)
    assert terminal["status"] == "DEAD" and terminal["error_code"] == error
    assert terminal["version"] == before["version"] + 1
    assert terminal["context_wait_claim_token"] == claim.claim_token
    assert terminal["context_wait_result"] == result.model_dump(mode="json")
    assert terminal["context_block_reason"] == reason and terminal["completed_at"] is not None
    assert all(terminal[key] is None for key in ("claim_token", "lease_until", "worker_id"))
    for key in ("attempt_count", "first_started_at", "available_at", "turn_input", "turn_revision"):
        assert terminal[key] == before[key], key
    assert terminal["turn_outcome"] == (None if accepted else "FAILED")
    assert terminal["guard_rejection"] == ("NOT_ALLOWED" if accepted and kind == "hold" else None)
    assert await runtime_effects(h, claim) == effects
    after_context = await read(h, cid)
    assert after_context["automation_work"]["state"] == "OPERATOR_REQUIRED"
    assert after_context["automation_work"]["reason"] == reason
    assert after_context["automation_work"]["job_id"] == str(claim.job_id)
    assert after_context["automation_work"]["turn_id"] == str(turn["id"])
    for key in (
        "control_mode",
        "control_generation",
        "policy_epoch",
        "observation_epoch",
        "current_revision",
    ):
        assert after_context[key] == before_context[key], key
    assert int(after_context["context_version"]) == int(before_context["context_version"]) + bool(
        accepted
    )
    if accepted:
        box = (
            await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id)
        )[0]
        assert box["status"] == "FAILED" and box["error_code"] == error
        assert box["version"] == boxes[0]["version"] + 1 and box["completed_at"] is not None
        assert box["attempt_id"] is None and box["provider_message_id"] is None
        for key in ("id", "workspace_id", "connection_id", "message_id", "kind", "created_at"):
            assert box[key] == boxes[0][key], key
    else:
        assert await query(h, "SELECT * FROM app.outbox_events ORDER BY id") == boxes
    statements.clear()
    with runtime_sql_trace(h, statements):
        assert await h.kernel.replay_context_work(claim.job_id, claim.claim_token) == result
        assert await invoke(h, boundary, claim, saved) == result
        await execute_boundary(h, boundary, claim, saved)
    # Historical replay works after the lease was cleared: no new physical
    # admission, boundary invocation, claim or mutation is allowed here.
    assert any(
        s.lstrip().startswith("SELECT platform.human_context_work_replay(") for s in statements
    )
    assert all("platform.messaging_admit(" not in s for s in statements)
    assert all("platform." + sql_function + "(" not in s for s in statements)
    assert all("platform.messaging_claim(" not in s for s in statements)
    assert await job(h, claim) == terminal and await runtime_effects(h, claim) == effects
    assert h.adapter.calls == h.adapter.effects == 0 and not h.adapter.ledger.exists()
    with pytest.raises(MessagingError) as wrong_token:
        from uuid import uuid4

        await h.kernel.replay_context_work(claim.job_id, uuid4())
    assert wrong_token.value.code == Code.STALE_CLAIM
    await control(h, cid, "TAKEOVER")
    assert (await read(h, cid))["automation_work"]["state"] == "IDLE"
    assert await invoke(h, boundary, claim, saved) == result
    assert await job(h, claim) == terminal
    assert await h.kernel.recover_expired() == 0
    assert await job(h, claim) == terminal
    assert (
        await query(
            h, "SELECT * FROM platform.messaging_jobs WHERE id<>:id ORDER BY id", id=claim.job_id
        )
        == effects["other_jobs"]
    )
    assert h.adapter.calls == h.adapter.effects == 0


async def test_python_committed_send_begin_ack_loss_replay_miss_recovers_unknown(
    native_runtime, monkeypatch
):
    """Post-commit transport loss + bounded lease expiry; no forged permit/outcome."""
    from asm.messaging.errors import Code
    from asm.messaging.http_models import DeliveryResponse

    h = native_runtime
    cid, turn, claim, saved, accepted, _ = await setup_boundary(h, "send")
    assert accepted.code == "ACCEPTED"
    before_job = await job(h, claim)
    before = await runtime_effects(h, claim)
    before_box = (
        await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id)
    )[0]
    assert before_box["status"] == "PENDING" and before_box["attempt_id"] is None
    original_begin = h.kernel.begin_guarded_send
    original_replay = h.kernel.replay_context_work
    begin_calls = 0
    returned_permits = []
    replay_misses = []
    dispatch = []
    loss = SQLAlchemyError("guarded send-begin post-commit ACK loss seam")

    async def observe_begin(value):
        nonlocal begin_calls
        begin_calls += 1
        result = await original_begin(value)
        returned_permits.append(result)
        return result

    async def observe_replay(job_id, token):
        try:
            return await original_replay(job_id, token)
        except MessagingError as miss:
            assert miss.code == Code.STALE_CLAIM
            replay_misses.append((job_id, token))
            raise

    async def lost_ack(name):
        if name == "start_after_commit":
            assert not dispatch  # Exactly one durable begin; caller has no permit.
            row = (
                await query(
                    h, "SELECT * FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id
                )
            )[0]
            assert row["status"] == "DISPATCHING" and row["attempt_id"] is not None
            assert row["version"] == before_box["version"] + 1
            dispatch.append(dict(row))
            raise loss

    monkeypatch.setattr(h.kernel, "begin_guarded_send", observe_begin)
    monkeypatch.setattr(h.kernel, "replay_context_work", observe_replay)
    statements = []
    h.kernel._barrier = lost_ack
    try:
        with runtime_sql_trace(h, statements), pytest.raises(SQLAlchemyError) as caught:
            await Worker(h.kernel, h.adapter).execute(claim)
        assert caught.value is loss
    finally:
        h.kernel._barrier = None
    assert begin_calls == 1 and returned_permits == [] and len(dispatch) == 1
    # One miss before begin, a second from the real Worker exception branch.
    assert replay_misses == [(claim.job_id, claim.claim_token)] * 2
    assert sum("platform.guard_send_begin(" in s for s in statements) == 1
    assert sum("platform.messaging_admit(" in s for s in statements) == 1
    assert (
        sum(s.lstrip().startswith("SELECT platform.human_context_work_replay(") for s in statements)
        == 2
    )
    durable = await job(h, claim)
    assert durable["status"] == "RUNNING" and durable["claim_token"] == claim.claim_token
    for key in ("attempt_count", "first_started_at", "lease_until", "version"):
        assert durable[key] == before_job[key], key
    assert durable["context_wait_result"] is None and durable["context_wait_claim_token"] is None
    assert await runtime_effects(h, claim) == before
    assert (await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id))[
        0
    ] == dispatch[0]
    assert h.adapter.calls == h.adapter.effects == 0 and not h.adapter.ledger.exists()
    # Explicit single-row clock/expiry fault, identical to retained crash tests.
    # No Outbox/permit/receipt/outcome DML and no wall-clock sleep is used.
    expired = await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id AND status='RUNNING' AND claim_token=:token RETURNING id",
        id=claim.job_id,
        token=claim.claim_token,
    )
    assert [row["id"] for row in expired] == [claim.job_id]
    assert await h.kernel.recover_expired() == 1
    terminal = await job(h, claim)
    unknown = (
        await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id)
    )[0]
    assert unknown["status"] == "UNKNOWN" and unknown["error_code"] == "UNKNOWN_EXTERNAL_RESULT"
    assert unknown["attempt_id"] == dispatch[0]["attempt_id"]
    assert (
        unknown["version"] == dispatch[0]["version"] + 1 and unknown["provider_message_id"] is None
    )
    assert unknown["completed_at"] is not None
    assert terminal["status"] == "DEAD" and terminal["error_code"] == "UNKNOWN_EXTERNAL_RESULT"
    assert terminal["version"] == durable["version"] + 1
    assert terminal["attempt_count"] == before_job["attempt_count"]
    assert terminal["first_started_at"] == before_job["first_started_at"]
    assert all(
        terminal[key] is None
        for key in (
            "claim_token",
            "lease_until",
            "worker_id",
            "context_wait_result",
            "context_wait_claim_token",
        )
    )
    assert await runtime_effects(h, claim) == before
    assert await h.kernel.recover_expired() == 0
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.replay_context_work(claim.job_id, claim.claim_token)
    assert begin_calls == 1 and returned_permits == []
    assert await job(h, claim) == terminal
    await control(h, cid, "TAKEOVER")
    await reconcile(h, cid)
    await control(h, cid)
    await incoming(h, 3, text="Future context read after UNKNOWN")
    future = await current_turn(h, cid)
    assert future["id"] != turn["id"]
    await seal(h, future["id"])
    future = await current_turn(h, cid)
    view = await h.kernel.process_turn(await work_for(h, future, "TEST_CONSUME"))
    assert type(view) is TurnSnapshotV3
    history = [
        message
        for message in view.recent_messages
        if message.message_id == str(accepted.message_id)
    ]
    assert len(history) == 1 and history[0].origin == "CONTROLLED_AUTOMATION"
    delivery = history[0].delivery
    assert type(delivery) is DeliveryResponse and delivery.status == "UNKNOWN"
    assert delivery.error_code == "UNKNOWN_EXTERNAL_RESULT" and delivery.completed_at is not None
    assert (await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=accepted.outbox_id))[
        0
    ] == unknown
    assert await job(h, claim) == terminal
    assert (
        await scalar(
            h, "SELECT count(*) FROM platform.turn_guard_receipts WHERE turn_id=:id", id=turn["id"]
        )
        == 1
    )
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.messaging_jobs WHERE outbox_id=:id",
            id=accepted.outbox_id,
        )
        == 1
    )
    assert begin_calls == 1 and returned_permits == []
    assert h.adapter.calls == h.adapter.effects == 0 and not h.adapter.ledger.exists()


async def test_postgres_jsonb_utf8_bytes_and_hash_independent_closed_vectors(native_runtime):
    """Vector-only SELECTs on asm_runtime; no stored snapshot/receipt evidence."""
    import hashlib
    import json

    from asm.conversations.turns import native_jsonb

    h = native_runtime
    # Independent wire literals: PostgreSQL, not native_jsonb, supplies expected
    # canonical bytes/hash. No float/Decimal, NUL, surrogate or domain widening.
    vectors = (
        ("utf8-key-length-and-ties", '{"яя":1,"aa":2,"é":3,"b":4,"a":5,"💠":6,"zz":7}'),
        ("cyrillic", '{"текст":"Согласовали ёжика, прежний эскиз отменён."}'),
        ("combining-and-astral", '{"é":"e\\u0301","🧭":"𐐀😀","e\\u0301":"é"}'),
        ("unicode-line-separators", '{"lines":"до\\u2028между\\u2029после"}'),
        ("quote-backslash-controls", r'{"s":"\"\\\b\f\n\r\t\u0001\u001f/"}'),
        ("signed-bigint-endpoints", "[-9223372036854775808,9223372036854775807,0,-1,1]"),
        ("nested-closed-domain", '{"outer":[null,true,false,{"b":[],"a":[1,{"я":"е\\u0301"}]}]}'),
        ("empty-values", '{"":{},"a":[],"b":"","c":null,"d":false}'),
        ("unicode-and-control-keys", '{"\\u001f":1,"\\n":2,"é":3,"aa":4,"😀":5,"яя":6}'),
        ("array-order-and-types", '[{"x":true},false,null,"true",1,"1",[[],{},null]]'),
    )
    before = await scalar(h, "SELECT count(*) FROM platform.messaging_jobs")
    async with h.runtime.engine.begin() as connection:
        assert (await connection.execute(text("SELECT session_user"))).scalar_one() == "asm_runtime"
        for label, wire in vectors:
            value = json.loads(wire)
            result = (
                (
                    await connection.execute(
                        text(
                            "SELECT convert_to(CAST(:wire AS jsonb)::text,'UTF8') AS body,encode(sha256(convert_to(CAST(:wire AS jsonb)::text,'UTF8')),'hex') AS digest"
                        ),
                        {"wire": wire},
                    )
                )
                .mappings()
                .one()
            )
            actual = native_jsonb(value)
            assert actual == bytes(result["body"]), label
            assert hashlib.sha256(actual).hexdigest() == result["digest"], label
    assert await scalar(h, "SELECT count(*) FROM platform.messaging_jobs") == before == 0
    assert await scalar(h, "SELECT count(*) FROM app.messages") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 0
    assert h.adapter.calls == 0


def runtime_unicode_text():
    """Full scalar field, not an HTTP-body-cap claim or normalized replacement."""
    unit = 'Полный контекст е\u0301 🧭 \u2028\u2029 "\\\n'
    value = (unit * (4096 // len(unit) + 1))[:4096]
    assert len(value) == 4096 and len(value.encode("utf-8")) <= 16384 and value.strip()
    return value


async def runtime_photo(h, number, status, *, provider="CONTROLLED", value=None):
    """Reuse retained private File primitives; MANIFEST is a DB-only TEST seam."""
    from asm.files.database import FileDatabase
    from asm.messaging.errors import Code
    from test_m2_2_db_postgres import MANIFEST

    changes = {"photo": "runtime-photo-" + str(number), "value": value}
    if provider == "CONTROLLED":
        changes = {"image_file_id": "runtime-photo-" + str(number), "text": value}
    _, message, cid = await incoming(h, number, provider=provider, **changes)
    file = (
        await query(h, "SELECT * FROM app.file_objects WHERE message_id=:id", id=message.message_id)
    )[0]
    if status != "PENDING":
        fetch = await claim_job(
            h,
            await scalar(
                h,
                "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE' AND file_id=:id",
                id=file["id"],
            ),
        )
        if status == "READY":
            files = FileDatabase(h.kernel)
            upload = await files.prepare_upload(fetch, MANIFEST)
            assert (
                await files.finish_fetch(fetch.job_id, fetch.claim_token, upload.intent_id)
            ).status == "READY"
            assert (
                await scalar(
                    h,
                    "SELECT status FROM platform.file_object_uploads WHERE id=:id",
                    id=upload.intent_id,
                )
                == "WINNER"
            )
        else:
            assert status == "FAILED"
            # Explicit permanent fetch failure through the actual retry capability.
            await h.kernel.retry(fetch, Code.INVALID_INPUT, retryable=False)
    file = (await query(h, "SELECT * FROM app.file_objects WHERE id=:id", id=file["id"]))[0]
    assert file["status"] == status
    return cid, message.message_id, file


async def runtime_saved_v3_bytes(h, claim, snapshot, shape):
    """Server reads persisted input bytes/hash; strict parser receives it unchanged."""
    import copy
    import hashlib

    from asm.conversations.guards import parse_guarded_snapshot
    from asm.conversations.turns import native_jsonb, parse_snapshot

    row = (
        await query(
            h,
            "SELECT turn_input AS body,convert_to(turn_input::text,'UTF8') AS signed_bytes,convert_to((turn_input-'snapshot_digest')::text,'UTF8') AS unsigned_bytes,encode(sha256(convert_to((turn_input-'snapshot_digest')::text,'UTF8')),'hex') AS digest,platform.human_context_snapshot_valid(turn_input,:shape) AS valid FROM platform.messaging_jobs WHERE id=:id",
            id=claim.job_id,
            shape=shape,
        )
    )[0]
    body = row["body"]
    assert row["valid"] is True and body["schema_version"] == 3
    assert native_jsonb(body) == bytes(row["signed_bytes"])
    unsigned = {key: value for key, value in body.items() if key != "snapshot_digest"}
    encoded = native_jsonb(unsigned)
    assert encoded == bytes(row["unsigned_bytes"]) and len(encoded) <= 2097152
    assert (
        hashlib.sha256(encoded).hexdigest()
        == row["digest"]
        == body["snapshot_digest"]
        == snapshot.snapshot_digest
    )
    raw = body | {"code": "SNAPSHOT", "job_id": str(claim.job_id)}
    original = copy.deepcopy(raw)
    parsed = (parse_guarded_snapshot if shape == "GUARDED" else parse_snapshot)(raw)
    assert parsed == snapshot and raw == original
    assert (
        await scalar(
            h, "SELECT turn_input FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
        )
        == body
    )
    return body


async def test_python_capability_saved_base_guarded_and_unsigned_escalation_unicode_files(
    native_runtime,
):
    """CONTROLLED-only guarded/E path; DB File seams perform no S3/provider I/O."""
    import copy
    import hashlib

    from asm.conversations.escalations import MARKER
    from asm.conversations.native_context_http_models import HumanContextRevision
    from asm.conversations.turns import RecentMessage, TurnMemberV2, native_jsonb

    h = native_runtime
    _, _, cid = await incoming(h)
    await policy(h)
    owner_text = runtime_unicode_text()
    expected = {}
    for number, status in ((10, "READY"), (11, "FAILED"), (12, "PENDING")):
        same, message, file = await runtime_photo(h, number, status, value="История е\u0301 🧭")
        assert same == cid
        expected[str(message)] = (file, "История е\u0301 🧭")
    revision = await reconcile(h, cid, value=owner_text, media="UNAVAILABLE")
    await control(h, cid)
    same, message, file = await runtime_photo(
        h, 13, "READY", value='Текущий "эскиз" \\ е\u0301 🧭\u2028\u2029'
    )
    assert same == cid
    expected[str(message)] = (file, 'Текущий "эскиз" \\ е\u0301 🧭\u2028\u2029')
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    files_before = await query(h, "SELECT * FROM app.file_objects ORDER BY id")
    uploads_before = await query(h, "SELECT * FROM platform.file_object_uploads ORDER BY id")
    for shape, step, method, model in (
        ("BASE", "TEST_CONSUME", h.kernel.process_turn, TurnSnapshotV3),
        ("GUARDED", "GUARDED_TEXT", h.kernel.prepare_guarded_turn, GuardedTurnSnapshotV3),
    ):
        claim = await work_for(h, turn, step)
        snapshot = await method(claim)
        assert type(snapshot) is model
        body = await runtime_saved_v3_bytes(h, claim, snapshot, shape)
        assert snapshot.human_context.text == owner_text and snapshot.human_context.text.encode(
            "utf-8"
        ) == owner_text.encode("utf-8")
        assert snapshot.human_context.revision_id == revision["result"]["revision_id"]
        assert snapshot.readiness == "PARTIAL" and snapshot.context_limitations == (
            "PROVIDER_HISTORY_UNVERIFIED",
            "NATIVE_MEDIA_UNAVAILABLE",
        )
        assert (
            snapshot.members[0].file.status == "READY" and consume(snapshot).ready_file_count == 1
        )
        recent = {item["message_id"]: item for item in body["recent_messages"]}
        for mid, (saved_file, caption) in expected.items():
            assert recent[mid]["current"]["text"] == caption
            assert (
                recent[mid]["current"]["image_availability"] == "ORIGINAL_" + saved_file["status"]
            )
            assert recent[mid]["file"] == {
                "file_id": str(saved_file["id"]),
                "version": str(saved_file["version"]),
                "status": saved_file["status"],
            }
            assert recent[mid]["delivery"] is None
    # A new real Turn selects the marker route. It cannot preempt the preceding
    # guarded preparation, and no guarded acceptance is fabricated to reach E.
    await incoming(h, 14, text=MARKER)
    escalation_turn = await current_turn(h, cid)
    assert escalation_turn["id"] != turn["id"]
    await seal(h, escalation_turn["id"])
    escalation_turn = await current_turn(h, cid)
    claim = await work_for(h, escalation_turn, "ESCALATE_OWNER")
    result = await h.kernel.request_escalation(claim)
    assert result.code == "ESCALATED"
    row = (
        await query(
            h,
            "SELECT request_snapshot AS body,convert_to(request_snapshot::text,'UTF8') AS body_bytes,encode(sha256(convert_to(request_snapshot::text,'UTF8')),'hex') AS hash,encode(context_fingerprint,'hex') AS fingerprint,platform.human_context_snapshot_valid(request_snapshot,'ESCALATION') AS valid FROM app.escalations WHERE id=:id",
            id=result.escalation_id,
        )
    )[0]
    body = row["body"]
    original = copy.deepcopy(body)
    assert row["valid"] is True and body["schema_version"] == 3
    assert "snapshot_digest" not in body and "consumer" not in body
    assert set(body) == {
        "schema_version",
        "workspace_id",
        "connection_id",
        "turn_id",
        "turn_revision",
        "context_version",
        "control_generation",
        "readiness",
        "members",
        "human_context",
        "context_policy_epoch",
        "human_observation_epoch",
        "resume_receipt_id",
        "recent_messages",
        "history_truncated",
        "coverage_status",
        "context_coverage",
        "context_limitations",
        "conversation_id",
        "client_id",
        "business_id",
        "activation_fence_seq",
        "source_job_id",
        "source_job_kind",
        "source_job_step",
        "source_claim_token",
    }
    encoded = native_jsonb(body)
    assert encoded == bytes(row["body_bytes"])
    # Existing context_fingerprint hashes the unsigned closed E body; no digest
    # field is added to it and no BASE/GUARDED parser fallback is used.
    assert (
        hashlib.sha256(encoded).hexdigest()
        == row["hash"]
        == row["fingerprint"]
        == result.context_fingerprint
    )
    assert HumanContextRevision.model_validate(body["human_context"]).text == owner_text
    assert body["source_job_id"] == str(claim.job_id) and body["source_claim_token"] == str(
        claim.claim_token
    )
    for member in body["members"]:
        TurnMemberV2.model_validate(member)
    recent = {
        item["message_id"]: RecentMessage.model_validate(item) for item in body["recent_messages"]
    }
    for mid, (saved_file, caption) in expected.items():
        assert (
            recent[mid].current.text == caption and recent[mid].file.status == saved_file["status"]
        )
        assert recent[mid].file.file_id == str(saved_file["id"])
    assert (
        body == original
        and await scalar(
            h, "SELECT request_snapshot FROM app.escalations WHERE id=:id", id=result.escalation_id
        )
        == body
    )
    assert await query(h, "SELECT * FROM app.file_objects ORDER BY id") == files_before
    assert (
        await query(h, "SELECT * FROM platform.file_object_uploads ORDER BY id") == uploads_before
    )
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 0
    assert h.adapter.calls == h.adapter.effects == 0 and not h.adapter.ledger.exists()


async def test_python_capability_saved_base_unicode_current_material_and_private_winners(
    native_runtime,
):
    """Actual Telegram MATERIAL + BASE; guarded automation remains CONTROLLED-only."""
    from test_m3_1_provenance_postgres import process as process_material
    from test_m3_1_provenance_postgres import raw

    h = native_runtime
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    originals = {}
    for number in (10, 11):
        _, message, same = await incoming(h, number, provider="TELEGRAM", value="Старый текст")
        assert same == cid
        originals[number] = message.message_id
    for number in (12, 13, 14):
        same, message, _ = await runtime_photo(
            h, number, "READY", provider="TELEGRAM", value="Старая подпись"
        )
        assert same == cid
        originals[number] = message
    originals_before = await query(
        h, "SELECT id,text,image_file_id,projection_fingerprint FROM app.messages ORDER BY id"
    )
    files_before = await query(h, "SELECT * FROM app.file_objects ORDER BY id")
    uploads_before = await query(h, "SELECT * FROM platform.file_object_uploads ORDER BY id")
    unicode_value = 'Новый эскиз е\u0301 🧭\u2028\u2029 "точно" \\ конец'
    changes = (
        raw(200010, 510, kind="EDIT", value=unicode_value),
        raw(200011, 511, kind="DELETE"),
        raw(200012, 512, kind="EDIT", value=unicode_value, photo="runtime-photo-12"),
        raw(200013, 513, kind="EDIT", value=unicode_value, photo="replacement-photo"),
        raw(200014, 514, kind="EDIT", value=unicode_value),
    )
    for change in changes:
        receipt, _, result = await process_material(h, change)
        assert result.code == "MATERIAL_PROCESSED"
        applied = await scalar(
            h, "SELECT material_result FROM platform.inbox_events WHERE id=:id", id=receipt.inbox_id
        )
        assert len(applied) == 1 and applied[0]["code"] == "APPLIED"
    assert (
        await query(
            h, "SELECT id,text,image_file_id,projection_fingerprint FROM app.messages ORDER BY id"
        )
        == originals_before
    )
    assert await query(h, "SELECT * FROM app.file_objects ORDER BY id") == files_before
    assert (
        await query(h, "SELECT * FROM platform.file_object_uploads ORDER BY id") == uploads_before
    )
    owner_text = runtime_unicode_text()
    await reconcile(h, cid, value=owner_text, media="UNAVAILABLE")
    await control(h, cid)
    same, current_id, _ = await runtime_photo(
        h, 15, "READY", provider="TELEGRAM", value=unicode_value
    )
    assert same == cid
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    assert not turn["material_invalidated"]
    claim = await work_for(h, turn, "TEST_CONSUME")
    snapshot = await h.kernel.process_turn(claim)
    assert type(snapshot) is TurnSnapshotV3 and snapshot.human_context.text == owner_text
    body = await runtime_saved_v3_bytes(h, claim, snapshot, "BASE")
    recent = {item["message_id"]: item for item in body["recent_messages"]}
    for number, state, kind, availability in (
        (10, "VISIBLE", "TEXT", "NOT_APPLICABLE"),
        (11, "DELETED", None, "HIDDEN"),
        (12, "VISIBLE", "PHOTO", "ORIGINAL_READY"),
        (13, "VISIBLE", "PHOTO", "MEDIA_REPLACED_UNAVAILABLE"),
        (14, "VISIBLE", "TEXT", "NOT_APPLICABLE"),
    ):
        message = recent[str(originals[number])]
        assert message["current"] == {
            "schema_version": 1,
            "state": state,
            "content_type": kind,
            "text": None if number == 11 else unicode_value,
            "image_availability": availability,
            "changed": True,
        }
        assert message["version"] == "2"
        if number >= 12:
            old_file = next(
                file for file in files_before if file["message_id"] == originals[number]
            )
            # Historical private File/WINNER persists even when the effective
            # PHOTO was replaced or became TEXT. It is never made usable again.
            assert message["file"] == {
                "file_id": str(old_file["id"]),
                "version": str(old_file["version"]),
                "status": "READY",
            }
        else:
            assert message["file"] is None
    assert recent[str(current_id)]["current"]["image_availability"] == "ORIGINAL_READY"
    assert (
        snapshot.members[0].current.text == unicode_value
        and snapshot.members[0].file.status == "READY"
    )
    assert consume(snapshot).ready_file_count == 1
    assert await scalar(h, "SELECT count(*) FROM app.file_objects") == 4
    assert (
        await scalar(h, "SELECT count(*) FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")
        == 4
    )
    assert (
        await scalar(h, "SELECT count(*) FROM platform.file_object_uploads WHERE status='WINNER'")
        == 4
    )
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 0
    assert h.adapter.calls == h.adapter.effects == 0 and not h.adapter.ledger.exists()
