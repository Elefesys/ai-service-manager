"""GUARDS through real owner/Inbox/queue/worker/PG, including counted process death."""

import asyncio
import os
import sys
from uuid import uuid4

import pytest
from asm.conversations.guards import GUARD_TEXT, GuardedTurnSnapshot, GuardProgress, GuardReceipt
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase, worker_active
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind
from asm.messaging.worker import Worker
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_auth_postgres import auth as auth
from test_m2_1_models import event
from test_m2_1_postgres import CHILD, command, expire, ingest, ledger, query
from test_m2_1_postgres import messaging as messaging
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_api_postgres import api as api
from test_m3_1_control_api_postgres import post
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import execute, incoming, process_receipt, state, wait_blocked
from test_tenancy_postgres import UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


async def next_kind(h, kind, step=None):
    async with asyncio.timeout(10):
        while True:
            claim = await h.kernel.claim_job("guards-test")
            if claim is None:
                await asyncio.sleep(0.02)
                continue
            if claim.kind == kind and (step is None or claim.step == step):
                return claim
            await h.worker.execute(claim)


async def fresh(h, *, api_resume=False):
    cid, _, _ = await incoming(h)
    if api_resume:
        response = await post(h, cid, "resume", "guards-resume")
        assert response.status_code == 200
    else:
        await execute(h, cid, "RESUME", "guards-resume")
    rec = await ingest(h, event(event_id="guard-fresh", message_id="guard-fresh"))
    await process_receipt(h, rec)
    claim = await next_kind(h, "PROCESS_TURN", "GUARDED_TEXT")
    return cid, claim


async def prepared(h):
    cid, claim = await fresh(h)
    snapshot = await h.kernel.prepare_guarded_turn(claim)
    assert isinstance(snapshot, GuardedTurnSnapshot)
    return cid, claim, snapshot


async def accepted(h):
    cid, claim, snapshot = await prepared(h)
    receipt = await h.kernel.accept_guarded_text(claim, snapshot.snapshot_digest, GUARD_TEXT)
    assert isinstance(receipt, GuardReceipt) and receipt.code == "ACCEPTED"
    send = await next_kind(h, "SEND_GUARDED_TEXT")
    assert send.job_id == receipt.send_job_id
    return cid, claim, snapshot, receipt, send


async def ddl(h, statement):
    async with h.migrator.begin() as c:
        await c.execute(text(statement))


async def facts(h):
    tables = (
        "app.conversations",
        "app.conversation_turns",
        "platform.messaging_jobs",
        "platform.turn_guard_receipts",
        "app.messages",
        "app.outbox_events",
        "app.audit_events",
    )
    return {
        t: await query(h, f"SELECT to_jsonb(t) AS row FROM {t} t ORDER BY to_jsonb(t)::text")
        for t in tables
    }


async def test_fresh_owner_resume_normal_ingress_worker_atomic_intent_and_final_send(api):
    h = api
    cid, claim = await fresh(h, api_resume=True)
    initial = await state(h, cid)
    audits = await query(h, "SELECT * FROM app.audit_events ORDER BY audit_event_id")
    assert (
        await query(
            h,
            "SELECT guard_profile FROM platform.conversation_control_receipts WHERE operation='RESUME'",
        )
    )[0]["guard_profile"] == "CONTROLLED_GUARDS_V1"
    await h.worker.execute(claim)
    r = (await query(h, "SELECT * FROM platform.turn_guard_receipts"))[0]
    assert r["outcome"] == "ACCEPTED" and r["result_text"] == GUARD_TEXT
    assert r["input_context_version"] == initial["version"]
    assert r["intent_context_version"] == initial["version"] + 1
    current = await state(h, cid)
    assert (
        current["control_mode"] == "AI"
        and current["control_generation"] == initial["control_generation"]
    )
    assert h.adapter.calls == 0
    assert await query(h, "SELECT * FROM app.audit_events ORDER BY audit_event_id") == audits
    assert (await query(h, "SELECT count(*) n FROM platform.messaging_command_receipts"))[0][
        "n"
    ] == 0

    async def outside(name):
        assert not worker_active() and h.runtime.engine.pool.checkedout() == 0

    h.adapter.barrier = outside
    send = await next_kind(h, "SEND_GUARDED_TEXT")
    await h.worker.execute(send)
    assert h.adapter.calls == h.adapter.effects == 1
    assert (await query(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=r["outbox_id"]))[
        0
    ]["status"] == "SENT"
    assert (await state(h, cid))["version"] == initial["version"] + 2
    assert (await query(h, "SELECT count(*) n FROM platform.turn_guard_receipts"))[0]["n"] == 1


@pytest.mark.parametrize("takeover", [False, True])
async def test_legacy_capability_rejects_genuine_guarded_claim_before_any_mutation(
    control, takeover
):
    h = control
    cid, claim = await fresh(h)
    if takeover:
        await execute(h, cid, "TAKEOVER", "stop")
    before = await facts(h)
    with pytest.raises(MessagingError) as rejected:
        await h.kernel.process_turn(claim)
    assert rejected.value.code == Code.INVALID_INPUT
    assert await facts(h) == before
    await h.worker.execute(claim)
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id))[0]
    assert job["turn_outcome"] == ("STALE" if takeover else "ACCEPTED")
    assert job["status"] == "SUCCEEDED"
    assert h.adapter.calls == 0


@pytest.mark.parametrize("boundary", ["accept", "begin"])
async def test_takeover_wins_observed_conversation_wait(control, boundary):
    h = control
    if boundary == "accept":
        cid, claim, snap = await prepared(h)

        async def action():
            return await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, GUARD_TEXT)
    else:
        cid, _, _, receipt, claim = await accepted(h)

        async def action():
            return await h.kernel.begin_guarded_send(claim)

    from test_tenancy_postgres import raw_context

    row = await state(h, cid)
    args = {
        "id": cid,
        "client": row["client_id"],
        "gen": row["control_generation"],
        "version": row["version"],
    }
    async with h.runtime.engine.connect() as blocker:
        tx = await blocker.begin()
        await raw_context(blocker, A, UA)
        # The genuine owner capability owns the serialization lock. Runtime
        # never needs direct UPDATE privilege or a migrator impersonation.
        prepared_control = (
            await blocker.execute(
                text(
                    "SELECT platform.conversation_control_prepare(:id,:client,'TAKEOVER','wait-stop',:gen,:version)"
                ),
                args,
            )
        ).scalar_one()
        assert prepared_control["code"] == "NEW"
        pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        pending = asyncio.create_task(action())
        try:
            await wait_blocked(blocker, pid, pending=pending)
            # Execute the real owner command on this already-held serialization row.
            await blocker.execute(
                text(
                    "SELECT platform.conversation_control_execute(:id,:client,'TAKEOVER','wait-stop',:gen,:version)"
                ),
                args,
            )
            await tx.commit()
            result = await pending
        finally:
            if tx.is_active:
                await tx.rollback()
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    assert h.adapter.calls == 0
    if boundary == "accept":
        assert result.code == "STALE"
        assert (await query(h, "SELECT count(*) n FROM app.outbox_events"))[0]["n"] == 0
    else:
        assert result.code == "NOT_ALLOWED"
        row = (
            await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id)
        )[0]
        assert row["status"] == "FAILED" and row["attempt_id"] is None
        assert (
            await query(
                h,
                "SELECT guard_rejection FROM platform.messaging_jobs WHERE id=:id",
                id=claim.job_id,
            )
        )[0]["guard_rejection"] == "STALE"


@pytest.mark.parametrize("material", ["inbound", "manual", "resume", "file_revision"])
async def test_new_material_or_generation_rejects_old_snapshot(control, material):
    h = control
    cid, claim, snap = await prepared(h)
    if material == "inbound":
        rec = await ingest(h, event(event_id="new-context", message_id="new-context"))
        await process_receipt(h, rec)
    elif material == "manual":
        await command(h, cid, "owner text", "manual")
    elif material == "resume":
        await execute(h, cid, "TAKEOVER", "stop")
        await execute(h, cid, "RESUME", "again")
    else:
        # Existing material file caller and revision hook, not a raw version bump.
        from asm.files.database import FileDatabase
        from test_m2_2_db_postgres import MANIFEST

        rec = await ingest(
            h,
            event(event_id="material-photo", message_id="material-photo", image_file_id="image"),
        )
        await process_receipt(h, rec)
        fetch = await next_kind(h, "FETCH_IMAGE")
        before_file = await state(h, cid)
        files = FileDatabase(h.kernel)
        permit = await files.prepare_upload(fetch, MANIFEST)
        assert (
            await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
        ).status == "READY"
        assert (await state(h, cid))["version"] > before_file["version"]
    r = await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, GUARD_TEXT)
    assert r.code in {"STALE", "SUPERSEDED"}
    assert r.message_id is None and h.adapter.calls == 0


@pytest.mark.parametrize("boundary", ["accept", "begin"])
@pytest.mark.parametrize("denial", ["owner", "product_expiry", "product_activation", "channel"])
async def test_post_wait_live_authority_and_db_clock(control, boundary, denial):
    h = control
    if boundary == "accept":
        cid, claim, snap = await prepared(h)

        async def action():
            return await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, GUARD_TEXT)
    else:
        cid, _, _, _, claim = await accepted(h)

        async def action():
            return await h.kernel.begin_guarded_send(claim)

    lock = {
        "owner": "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor",
        "product_expiry": "UPDATE platform.workspace_subscriptions SET effective_until=clock_timestamp()+interval '0.25 seconds' WHERE workspace_id=:ws",
        "product_activation": "UPDATE platform.workspace_subscriptions SET effective_from=clock_timestamp()+interval '0.25 seconds' WHERE workspace_id=:ws",
        "channel": "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws AND id=:connection",
    }[denial]
    async with h.migrator.connect() as blocker:
        tx = await blocker.begin()
        await blocker.execute(text(lock), {"ws": A, "actor": UA, "connection": claim.connection_id})
        pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        task = asyncio.create_task(action())
        try:
            await wait_blocked(blocker, pid, pending=task)
            if denial in {"product_expiry", "product_activation"}:
                # Observe equality/expiry on the DB clock; do not override time.
                column = "effective_until" if denial == "product_expiry" else "effective_from"
                while not (
                    await blocker.execute(
                        text(
                            f"SELECT {column}<=clock_timestamp() FROM platform.workspace_subscriptions WHERE workspace_id=:ws"
                        ),
                        {"ws": A},
                    )
                ).scalar_one():
                    await asyncio.sleep(0.01)
            await tx.commit()
            result = await task
        finally:
            if tx.is_active:
                await tx.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    expected = (
        ("ACCEPTED" if boundary == "accept" else "PERMITTED")
        if denial == "product_activation"
        else "NOT_ALLOWED"
    )
    assert result.code == expected and h.adapter.calls == 0


async def test_canonical_refs_bad_digest_token_and_concurrent_exact_replay(control):
    h = control
    cid, claim, snap = await prepared(h)
    before = await facts(h)
    for bad, digest in (
        (claim.model_copy(update={"claim_token": uuid4()}), snap.snapshot_digest),
        (claim, "f" * 64),
    ):
        with pytest.raises(MessagingError) as caught:
            await h.kernel.accept_guarded_text(bad, digest, GUARD_TEXT)
        assert caught.value.code in {Code.STALE_CLAIM, Code.INVALID_INPUT}
        assert await facts(h) == before
    forged = claim.model_copy(
        update={"workspace_id": B, "connection_id": uuid4(), "turn_id": uuid4()}
    )
    a, b = await asyncio.gather(
        h.kernel.accept_guarded_text(forged, snap.snapshot_digest, " exact e\u0301\n🙂 "),
        h.kernel.accept_guarded_text(claim, snap.snapshot_digest, " exact e\u0301\n🙂 "),
    )
    assert (
        a == b and a.workspace_id == A and a.conversation_id == cid and a.turn_id == claim.turn_id
    )
    saved = await facts(h)
    await execute(h, cid, "TAKEOVER", "after-accept")
    assert (
        await h.kernel.replay_guarded_text(
            claim.job_id, claim.claim_token, snap.snapshot_digest, " exact e\u0301\n🙂 "
        )
        == a
    )
    with pytest.raises(MessagingError) as conflict:
        await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, "exact é\n🙂")
    assert conflict.value.code == Code.IDEMPOTENCY_KEY_CONFLICT
    assert len(saved["platform.turn_guard_receipts"]) == len(saved["app.outbox_events"]) == 1
    expected = (
        await query(
            h,
            "SELECT encode(platform.guard_text_fingerprint(turn_input,:body),'hex') fingerprint FROM platform.messaging_jobs WHERE id=:id",
            body=" exact e\u0301\n🙂 ",
            id=claim.job_id,
        )
    )[0]["fingerprint"]
    assert a.request_fingerprint == expected


@pytest.mark.parametrize(
    "target", ["message", "outbox", "send_job", "receipt", "consumer_terminal", "commit"]
)
async def test_acceptance_rolls_back_every_write_and_final_update(control, target):
    h = control
    _, claim, snap = await prepared(h)
    before = await facts(h)
    table, check = {
        "message": ("app.messages", "direction<>'OUTBOUND'"),
        "outbox": ("app.outbox_events", "kind<>'SEND_GUARDED_TEXT'"),
        "send_job": ("platform.messaging_jobs", "kind<>'SEND_GUARDED_TEXT'"),
        "receipt": ("platform.turn_guard_receipts", "outcome<>'ACCEPTED'"),
        "consumer_terminal": (
            "platform.messaging_jobs",
            "step IS DISTINCT FROM 'GUARDED_TEXT' OR status<>'SUCCEEDED'",
        ),
        "commit": (None, None),
    }[target]

    async def fail(name):
        if name == "guard_accept_before_commit":
            raise SQLAlchemyError("controlled commit boundary")

    if table:
        await ddl(h, f"ALTER TABLE {table} ADD CONSTRAINT guards_rollback CHECK({check}) NOT VALID")
    else:
        h.kernel._barrier = fail
    try:
        with pytest.raises(SQLAlchemyError):
            await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, GUARD_TEXT)
        assert await facts(h) == before
    finally:
        h.kernel._barrier = None
        if table:
            await ddl(h, f"ALTER TABLE {table} DROP CONSTRAINT guards_rollback")
    assert (
        await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, GUARD_TEXT)
    ).code == "ACCEPTED"


async def test_acceptance_and_finalize_ack_loss_read_canonical_success(control):
    h = control
    _, claim = await fresh(h)
    failures = set()

    async def lose(name):
        if name in {"guard_accept_after_commit", "finalize_after_commit"} and name not in failures:
            failures.add(name)
            raise SQLAlchemyError("controlled lost ACK")

    h.kernel._barrier = lose
    await h.worker.execute(claim)
    send = await next_kind(h, "SEND_GUARDED_TEXT")
    await h.worker.execute(send)
    assert failures == {"guard_accept_after_commit", "finalize_after_commit"}
    assert h.adapter.calls == h.adapter.effects == 1
    assert (await query(h, "SELECT status FROM app.outbox_events"))[0]["status"] == "SENT"
    assert (await query(h, "SELECT count(*) n FROM platform.turn_guard_receipts"))[0]["n"] == 1


@pytest.mark.parametrize("when", ["before", "after"])
async def test_dispatch_linearizes_before_effect_and_takeover_does_not_veto_finalize(control, when):
    h = control
    cid, _, _, _, claim = await accepted(h)
    entered, release = asyncio.Event(), asyncio.Event()

    async def barrier(name):
        if name == ("before_call" if when == "before" else "after_effect"):
            assert not worker_active() and h.runtime.engine.pool.checkedout() == 0
            entered.set()
            await release.wait()

    h.adapter.barrier = barrier
    pending = asyncio.create_task(h.worker.execute(claim))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        await execute(h, cid, "TAKEOVER", "inflight")
        release.set()
        await pending
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
    assert h.adapter.calls == h.adapter.effects == 1
    assert (await query(h, "SELECT status FROM app.outbox_events"))[0]["status"] == "SENT"


@pytest.mark.parametrize("stop", [False, True])
async def test_proven_not_sent_rechecks_guard_and_exhausts_without_turn_failure(control, stop):
    h = control
    cid, _, _, receipt, claim = await accepted(h)
    h.adapter.outcome = OutcomeKind.NOT_SENT_RETRYABLE
    await h.worker.execute(claim)
    box = (await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id))[0]
    assert box["status"] == "PENDING" and box["attempt_id"] is not None
    if stop:
        await execute(h, cid, "TAKEOVER", "before-retry")
    while True:
        await query(
            h,
            "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
        new = await next_kind(h, "SEND_GUARDED_TEXT")
        await h.worker.execute(new)
        job = (
            await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id)
        )[0]
        if job["status"] == "DEAD":
            break
    assert h.adapter.calls == (1 if stop else 5) and h.adapter.effects == 0
    assert job["error_code"] == ("NOT_ALLOWED" if stop else "RETRY_EXHAUSTED")
    assert (
        await query(h, "SELECT state FROM app.conversation_turns WHERE id=:id", id=receipt.turn_id)
    )[0]["state"] == "READY"
    if stop:
        assert job["guard_rejection"] == "STALE"
        assert (
            await query(
                h, "SELECT attempt_id FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id
            )
        )[0]["attempt_id"] == box["attempt_id"]


async def test_claim_expiry_reclaim_and_guarded_exhaustion_leave_ready_turn(control):
    h = control
    _, claim, snapshot = await prepared(h)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    before = await facts(h)
    with pytest.raises(MessagingError) as expired:
        await h.kernel.accept_guarded_text(claim, snapshot.snapshot_digest, GUARD_TEXT)
    assert expired.value.code == Code.STALE_CLAIM and await facts(h) == before
    assert await h.kernel.recover_expired() >= 1
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    new = await next_kind(h, "PROCESS_TURN", "GUARDED_TEXT")
    assert new.job_id == claim.job_id and new.claim_token != claim.claim_token
    with pytest.raises(MessagingError):
        await h.kernel.prepare_guarded_turn(claim)
    snap = await h.kernel.prepare_guarded_turn(new)
    assert isinstance(snap, GuardedTurnSnapshot)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET attempt_count=5 WHERE id=:id RETURNING id",
        id=new.job_id,
    )
    await h.kernel.retry(new, Code.DEPENDENCY_UNAVAILABLE)
    assert (
        await query(
            h, "SELECT status,turn_outcome FROM platform.messaging_jobs WHERE id=:id", id=new.job_id
        )
    )[0] == {"status": "DEAD", "turn_outcome": "FAILED"}
    assert (
        await query(h, "SELECT state FROM app.conversation_turns WHERE id=:id", id=new.turn_id)
    )[0]["state"] == "READY"


@pytest.mark.parametrize("stage,calls", [("start_after_commit", 0), ("after_effect", 1)])
async def test_guarded_process_death_unknown_no_resend_after_restart_and_resume(
    control, stage, calls
):
    h = control
    cid, claim = await fresh(h)
    await h.worker.execute(claim)
    r = (await query(h, "SELECT * FROM platform.turn_guard_receipts"))[0]
    # Reuse the existing crash family/barriers while allowing the normal queue
    # to drain retained effects-free work before it reaches the guarded send.
    once = "await Worker(kernel, adapter).run_once()"
    assert CHILD.count(once) == 1
    child_program = CHILD.replace(
        once,
        "worker = Worker(kernel, adapter)\n        while await worker.run_once():\n            pass",
    )
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        child_program,
        env={**os.environ, "M2_CRASH_STAGE": stage, "M2_LEDGER": str(h.ledger)},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(child.communicate(), 15)
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
    assert child.returncode == 42, (out, err)
    assert ledger(h).count("CALL") == ledger(h).count("EFFECT") == calls
    await execute(h, cid, "TAKEOVER", "after-crash")
    await execute(h, cid, "RESUME", "after-crash-resume")
    await expire(h)
    replacement = Worker(
        MessagingDatabase(h.runtime.engine), ControlledAdapter(environment="TEST", ledger=h.ledger)
    )
    for _ in range(2):
        assert not await replacement.run_once()
    assert (await query(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=r["outbox_id"]))[
        0
    ]["status"] == "UNKNOWN"
    assert ledger(h).count("CALL") == ledger(h).count("EFFECT") == calls


async def test_late_same_turn_file_revision_cannot_replace_accepted_intent(control):
    from asm.files.database import FileDatabase
    from test_m2_2_db_postgres import MANIFEST

    h = control
    cid, _, _ = await incoming(h)
    await execute(h, cid, "RESUME", "media-resume")
    rec = await ingest(
        h, event(event_id="guard-photo", message_id="guard-photo", image_file_id="image")
    )
    await process_receipt(h, rec)
    fetch = await next_kind(h, "FETCH_IMAGE")  # Keep the real file claim open, no raw Turn fixture.
    # Await the accepted existing 15-second media deadline through the normal queue.
    async with asyncio.timeout(25):
        while True:
            claim = await h.kernel.claim_job("guards-media")
            if claim is None:
                await asyncio.sleep(0.03)
                continue
            if claim.kind == "PROCESS_TURN" and claim.step == "GUARDED_TEXT":
                break
            await h.worker.execute(claim)
    snapshot = await h.kernel.prepare_guarded_turn(claim)
    assert snapshot.readiness == "PARTIAL"
    r = await h.kernel.accept_guarded_text(claim, snapshot.snapshot_digest, GUARD_TEXT)
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(fetch, MANIFEST)
    assert (
        await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    ).status == "READY"
    # The pending intent is suppressed by revised material; next guarded step
    # acknowledges the original identity without computing/replacing it.
    new = await next_kind(h, "PROCESS_TURN", "GUARDED_TEXT")
    progress = await h.kernel.prepare_guarded_turn(new)
    assert isinstance(progress, GuardProgress) and progress.code == "ALREADY_ACCEPTED"
    assert progress.accepted_job_id == r.job_id and progress.message_id == r.message_id
    assert new.turn_revision > r.turn_revision
    assert (
        await query(
            h, "SELECT count(*) n FROM platform.turn_guard_receipts WHERE outcome='ACCEPTED'"
        )
    )[0]["n"] == 1
    assert (await query(h, "SELECT count(*) n FROM app.outbox_events"))[0]["n"] == 1
    assert h.adapter.calls == 0


async def test_private_receipts_and_same_workspace_relation_forgery_are_rejected(control):
    h = control
    cid, _, _, r, _ = await accepted(h)
    async with h.runtime.engine.begin() as c:
        for sql in (
            "SELECT * FROM platform.turn_guard_receipts",
            "DELETE FROM platform.turn_guard_receipts",
        ):
            with pytest.raises(DBAPIError) as denied:
                async with c.begin_nested():
                    await c.execute(text(sql))
            assert denied.value.orig.sqlstate == "42501"
    before = await facts(h)
    async with h.migrator.begin() as c:
        with pytest.raises(DBAPIError) as immutable:
            async with c.begin_nested():
                await c.execute(
                    text(
                        "UPDATE platform.turn_guard_receipts SET result_text='changed' WHERE job_id=:id"
                    ),
                    {"id": r.job_id},
                )
        assert immutable.value.orig.sqlstate == "23514"
        # A typed send Job cannot point at an Outbox of a different origin kind.
        with pytest.raises(DBAPIError) as kind:
            async with c.begin_nested():
                await c.execute(
                    text(
                        """WITH msg AS (
                          INSERT INTO app.messages(workspace_id,conversation_id,connection_id,provider_chat_id,direction,content_type,text,occurred_at)
                          SELECT workspace_id,conversation_id,connection_id,provider_chat_id,'OUTBOUND','TEXT','forged kind',clock_timestamp()
                          FROM app.messages WHERE id=:message RETURNING *
                        ), box AS (
                          INSERT INTO app.outbox_events(workspace_id,connection_id,message_id,kind)
                          SELECT workspace_id,connection_id,id,'SEND_GUARDED_TEXT' FROM msg RETURNING *
                        ) INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,outbox_id,correlation_id)
                          SELECT workspace_id,connection_id,'SEND_MANUAL_TEXT',id,:corr FROM box"""
                    ),
                    {"message": r.message_id, "corr": uuid4()},
                )
        assert kind.value.orig.sqlstate == "23503"
        assert kind.value.orig.diag.constraint_name == "messaging_send_kind_fkey"
    assert await facts(h) == before


async def test_telegram_resume_and_fresh_ingress_never_plan_or_probe_automated_send(control):
    h = control
    cid, _, _ = await incoming(h, "TELEGRAM")
    await execute(h, cid, "RESUME", "telegram-ai")
    await incoming(h, "TELEGRAM", 2)
    async with asyncio.timeout(10):
        while (
            await query(h, "SELECT count(*) n FROM platform.messaging_jobs WHERE status='READY'")
        )[0]["n"]:
            if not await h.worker.run_once():
                await asyncio.sleep(0.02)
    assert (await query(h, "SELECT guard_profile FROM platform.conversation_control_receipts"))[0][
        "guard_profile"
    ] is None
    assert (
        await query(
            h,
            "SELECT count(*) n FROM platform.messaging_jobs WHERE step='GUARDED_TEXT' OR kind='SEND_GUARDED_TEXT'",
        )
    )[0]["n"] == 0
    assert h.adapter.calls == 0 and not await query(h, "SELECT * FROM platform.turn_guard_receipts")
