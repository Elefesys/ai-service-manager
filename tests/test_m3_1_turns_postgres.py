"""M3.1 behavior and lock/receipt invariants through real PostgreSQL capabilities."""

import asyncio
import json
from uuid import uuid4

import pytest
from asm.conversations.turns import TurnSnapshot, consume
from asm.files.database import FileDatabase
from asm.messaging.database import MessagingDatabase, call, worker_active
from asm.messaging.errors import Code, MessagingError
from asm.messaging.worker import Worker
from asm.telegram.database import TelegramReceipt
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_m2_1_models import event
from test_m2_1_postgres import CA, CA2, command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_2_db_postgres import MANIFEST
from test_m2_3_db_postgres import BOT, ingress, projection
from test_m2_3_db_postgres import telegram as telegram
from test_tenancy_postgres import A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


async def rows(h, table):
    return await query(h, f"SELECT * FROM {table} ORDER BY 1,2")


async def claim_exact(h, job):
    # A test fixture may place unrelated jobs later, but never changes the
    # canonical Turn deadlines. All admission/execution uses production paths.
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE status='READY' AND id<>:id RETURNING id",
        id=job,
    )
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE status='READY' AND id=:id RETURNING id",
        id=job,
    )
    result = await h.kernel.claim_job("m3-exact")
    assert result is not None and result.job_id == job
    return result


async def receive(h, **changes):
    key = str(uuid4())
    receipt = await ingest(h, event(**{"event_id": key, "message_id": key, **changes}))
    claim = await claim_exact(h, receipt.job_id)
    return receipt, await h.kernel.process_inbox(claim)


async def turns(h):
    return await query(h, "SELECT * FROM app.conversation_turns ORDER BY first_ingress_at,id")


async def context(h, conv):
    return (
        await query(
            h,
            "SELECT version,control_mode,control_generation FROM app.conversations WHERE id=:id",
            id=conv,
        )
    )[0]


async def wait_due(h, turn, step="GROUP"):
    column = "quiet_at" if step == "GROUP" else "media_deadline_at"
    left = (
        await query(
            h,
            f"SELECT extract(epoch FROM {column}-clock_timestamp()) AS left FROM app.conversation_turns WHERE id=:id",
            id=turn,
        )
    )[0]["left"]
    if left > 0:
        # Waiting for the real persisted deadline is the behavior under test,
        # never a race workaround or a production clock override.
        await asyncio.sleep(float(left))


async def turn_claim(h, turn, step):
    values = await query(
        h,
        "SELECT j.id FROM platform.messaging_jobs j JOIN app.conversation_turns t ON (t.workspace_id,t.id,t.revision)=(j.workspace_id,j.turn_id,j.turn_revision) WHERE t.id=:id AND j.step=:step",
        id=turn,
        step=step,
    )
    assert len(values) == 1
    return await claim_exact(h, values[0]["id"])


async def seal(h, turn):
    await wait_due(h, turn)
    claim = await turn_claim(h, turn, "GROUP")
    result = await h.kernel.process_turn(claim)
    assert result.code in {"GROUPED", "WAITING_MEDIA"}
    return result


async def snapshot(h, turn):
    claim = await turn_claim(h, turn, "TEST_CONSUME")
    result = await h.kernel.process_turn(claim)
    assert isinstance(result, TurnSnapshot)
    return claim, result


async def test_text_dedupe_conflict_grouping_snapshot_and_effect_free_receipt(messaging):
    h = messaging
    first, message = await receive(h, event_id="first", message_id="one", text=" exact é\n ")
    initial = (await turns(h))[0]
    second, _ = await receive(h, event_id="second", message_id="two")
    grouped = (await turns(h))[0]
    assert grouped["id"] == initial["id"] and grouped["member_count"] == 2
    assert grouped["revision"] == 2 and grouped["hard_at"] == initial["hard_at"]
    assert (grouped["hard_at"] - grouped["first_ingress_at"]).total_seconds() == 10
    assert (grouped["quiet_at"] - grouped["last_ingress_at"]).total_seconds() == 2
    assert (grouped["media_deadline_at"] - grouped["first_ingress_at"]).total_seconds() == 25
    replay = await ingest(h, event(event_id="first", message_id="one", text=" exact é\n "))
    assert replay.inbox_id == first.inbox_id
    _, duplicate = await receive(h, event_id="duplicate", message_id="one", text=" exact é\n ")
    assert duplicate.code == "DUPLICATE"
    _, conflict = await receive(h, event_id="conflict", message_id="one", text="different")
    assert conflict.code == "MESSAGE_ID_CONFLICT"
    assert (await turns(h))[0] == grouped
    conv = grouped["conversation_id"]
    assert await context(h, conv) == {
        "version": 3,
        "control_mode": "HUMAN",
        "control_generation": 1,
    }
    await seal(h, grouped["id"])
    claim, value = await snapshot(h, grouped["id"])
    assert value.readiness == "COMPLETE" and value.context_version == 3
    assert len(value.members) == 2 and value.members[0].message_id == message.message_id
    assert [m.ingress_seq for m in value.members] == sorted(m.ingress_seq for m in value.members)
    assert all(m.file is None and m.message_version == 1 for m in value.members)
    assert not worker_active()
    saved = await h.kernel.finish_turn(claim, consume(value))
    assert saved.code == "OBSERVED"
    assert await h.kernel.replay_turn(claim.job_id, claim.claim_token) == saved
    assert await context(h, conv) == {
        "version": 3,
        "control_mode": "HUMAN",
        "control_generation": 1,
    }
    assert len(await rows(h, "platform.turn_consumer_receipts")) == 1
    assert not await rows(h, "app.outbox_events") and not await rows(h, "app.audit_events")
    assert not h.ledger.exists()
    origins = await rows(h, "app.conversation_turn_messages")
    assert {m["origin_inbox_id"] for m in origins} == {first.inbox_id, second.inbox_id}


async def test_equal_quiet_boundary_and_out_of_order_singleton_do_not_reopen(messaging):
    h = messaging
    older = await ingest(h, event(event_id="older", message_id="older"))
    _, recent = await receive(h, event_id="recent", message_id="recent")
    active = (await turns(h))[0]
    await h.kernel.process_inbox(await claim_exact(h, older.job_id))
    all_turns = await turns(h)
    singleton = next(t for t in all_turns if t["id"] != active["id"])
    assert singleton["state"] == "READY" and singleton["member_count"] == 1
    assert next(t for t in all_turns if t["id"] == active["id"]) == active
    boundary = await ingest(h, event(event_id="boundary", message_id="boundary"))
    mark = (
        await query(
            h,
            "SELECT turn_ingress_at FROM platform.inbox_events WHERE id=:id",
            id=boundary.inbox_id,
        )
    )[0]["turn_ingress_at"]
    # A migrator test sets a COLLECTING deadline to the exact already trusted
    # incoming mark. No ingress mutation, trigger bypass or runtime backdating API.
    await query(
        h,
        "UPDATE app.conversation_turns SET quiet_at=:mark WHERE id=:id RETURNING id",
        mark=mark,
        id=active["id"],
    )
    await h.kernel.process_inbox(await claim_exact(h, boundary.job_id))
    closed = next(t for t in await turns(h) if t["id"] == active["id"])
    assert (
        closed["state"] == "READY" and closed["seal_time"] == mark and closed["member_count"] == 1
    )
    assert len(await turns(h)) == 3
    for change in ("member_count=2", "quiet_at=quiet_at+interval '1 second'", "state='COLLECTING'"):
        with pytest.raises(DBAPIError):
            await query(
                h,
                f"UPDATE app.conversation_turns SET {change} WHERE id=:id RETURNING id",
                id=closed["id"],
            )
    assert recent.message_id is not None


async def test_max_32_and_album_boundaries_are_durable(messaging):
    h = messaging
    # Commit all trusted ingress marks first; processing can cross wall D without
    # extending the saved window or inventing worker-time ingress.
    receipts = [await ingest(h, event(event_id=f"n{i}", message_id=f"n{i}")) for i in range(33)]
    marks = await query(
        h, "SELECT min(turn_ingress_at) AS lo,max(turn_ingress_at) AS hi FROM platform.inbox_events"
    )
    assert (marks[0]["hi"] - marks[0]["lo"]).total_seconds() < 2
    # Process all in one admitted DB transaction per Inbox, as the real worker.
    for rec in receipts:
        await h.kernel.process_inbox(await claim_exact(h, rec.job_id))
    values = await turns(h)
    # If processing itself crossed quiet, the first 32 still remain subject to
    # ingress policy: the contract seals delayed singleton work immediately.
    # This test requires the actual 32-member path, not an alternate assertion.
    assert values[0]["member_count"] == 32 and values[0]["state"] == "READY"
    assert len(values) == 2 and values[1]["member_count"] == 1
    for suffix, group in (("a", "album-a"), ("b", "album-a"), ("c", "album-b")):
        await receive(
            h,
            event_id=suffix,
            message_id=suffix,
            chat_id="photo-chat",
            image_file_id=f"opaque-{suffix}",
            media_group_id=group,
            text="caption",
        )
    albums = [t for t in await turns(h) if t["provider_chat_id"] == "photo-chat"]
    assert [(t["media_group_id"], t["member_count"]) for t in albums] == [
        ("album-a", 2),
        ("album-b", 1),
    ]
    assert albums[0]["state"] == "WAITING_MEDIA"


async def test_media_wait_expired_late_success_and_failure_do_not_change_message_version(messaging):
    h = messaging
    _, msg = await receive(h, image_file_id="private-photo", text="caption", media_group_id="album")
    turn = (await turns(h))[0]
    file = (await rows(h, "app.file_objects"))[0]
    result = await seal(h, turn["id"])
    assert result.code == "WAITING_MEDIA"
    sealed = (await turns(h))[0]
    assert (sealed["media_deadline_at"] - sealed["seal_time"]).total_seconds() == 15
    await wait_due(h, turn["id"], "MEDIA")
    media = await turn_claim(h, turn["id"], "MEDIA")
    await h.kernel.process_turn(media)
    consumer, value = await snapshot(h, turn["id"])
    assert value.readiness == "PARTIAL" and value.members[0].file.wait_expired
    assert (await rows(h, "app.file_objects"))[0]["status"] == "PENDING"
    saved = await h.kernel.finish_turn(consumer, consume(value))
    assert saved.result.wait_expired_count == 1
    fetch_job = (
        await query(h, "SELECT id FROM platform.messaging_jobs WHERE file_id=:id", id=file["id"])
    )[0]["id"]
    fetch = await claim_exact(h, fetch_job)
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(fetch, MANIFEST)
    before = await context(h, turn["conversation_id"])
    await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    ready = (await turns(h))[0]
    assert (
        ready["revision"] == value.turn_revision + 1
        and ready["state"] == "READY"
        and ready["readiness"] == "COMPLETE"
    )
    for field in (
        "member_count",
        "quiet_at",
        "hard_at",
        "seal_time",
        "media_deadline_at",
        "closed_at",
    ):
        assert ready[field] == sealed[field]
    assert (await context(h, turn["conversation_id"]))["version"] == before["version"] + 1
    assert (await query(h, "SELECT version FROM app.messages WHERE id=:id", id=msg.message_id))[0][
        "version"
    ] == 1
    again = await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    assert again.code == "ALREADY_FINALIZED"
    assert (await context(h, turn["conversation_id"]))["version"] == before["version"] + 1
    current, new_value = await snapshot(h, turn["id"])
    assert not new_value.members[0].file.wait_expired
    assert (await h.kernel.finish_turn(current, consume(new_value))).code == "OBSERVED"
    assert len(await rows(h, "platform.turn_consumer_receipts")) == 2


@pytest.mark.parametrize("change", ["context", "generation"])
async def test_context_or_generation_change_is_stale_without_action_authority(messaging, change):
    h = messaging
    await receive(h)
    turn = (await turns(h))[0]
    await seal(h, turn["id"])
    claim, value = await snapshot(h, turn["id"])
    if change == "context":
        send = await command(h, turn["conversation_id"], "exact manual", "stale")
        replay = await command(h, turn["conversation_id"], "exact manual", "stale")
        assert replay.message_id == send.message_id
    else:
        # Future control behavior is not exposed: only the migrator test can
        # exercise the generation fence while all modes remain HUMAN.
        await query(
            h,
            "UPDATE app.conversations SET control_generation=control_generation+1 WHERE id=:id RETURNING id",
            id=turn["conversation_id"],
        )
    before = await context(h, turn["conversation_id"])
    result = await h.kernel.finish_turn(claim, consume(value))
    assert result.code == "STALE" and await context(h, turn["conversation_id"]) == before
    assert result.input_context_version == value.context_version
    assert result.input_control_generation == value.control_generation


@pytest.mark.parametrize(
    "point",
    [
        "process_before_commit",
        "process_after_commit",
        "turn_finalize_before_commit",
        "turn_finalize_after_commit",
    ],
)
async def test_restart_atomic_membership_and_consumer_commit_ack(messaging, point):
    h = messaging
    fired = False

    async def crash(name):
        nonlocal fired
        if name == point and not fired:
            fired = True
            raise SQLAlchemyError("simulated process boundary")

    h.kernel = MessagingDatabase(h.runtime.engine, barrier=crash)
    rec = await ingest(h)
    first = await claim_exact(h, rec.job_id)
    if point.startswith("process"):
        with pytest.raises(SQLAlchemyError):
            await h.kernel.process_inbox(first)
        assert len(await turns(h)) == (point == "process_after_commit")
        h.kernel = MessagingDatabase(h.runtime.engine)
        if point == "process_before_commit":
            await h.kernel.process_inbox(first)
        assert len(await turns(h)) == 1
    else:
        await h.kernel.process_inbox(first)
        turn = (await turns(h))[0]
        await seal(h, turn["id"])
        claim, value = await snapshot(h, turn["id"])
        with pytest.raises(SQLAlchemyError):
            await h.kernel.finish_turn(claim, consume(value))
        h.kernel = MessagingDatabase(h.runtime.engine)
        if point == "turn_finalize_before_commit":
            with pytest.raises(MessagingError) as miss:
                await h.kernel.replay_turn(claim.job_id, claim.claim_token)
            assert miss.value.code == Code.STALE_CLAIM
            result = await h.kernel.finish_turn(claim, consume(value))
        else:
            result = await h.kernel.replay_turn(claim.job_id, claim.claim_token)
        assert (
            result.code == "OBSERVED" and len(await rows(h, "platform.turn_consumer_receipts")) == 1
        )


async def test_receipt_live_fencing_reclaim_wrong_tokens_and_direct_access(messaging):
    h = messaging
    await receive(h)
    turn = (await turns(h))[0]
    await seal(h, turn["id"])
    old, value = await snapshot(h, turn["id"])
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=old.job_id,
    )
    assert await h.kernel.recover_expired() == 1
    new = await claim_exact(h, old.job_id)
    fresh = await h.kernel.process_turn(new)
    result = await h.kernel.finish_turn(new, consume(fresh))
    assert result.code == "OBSERVED"
    for job, token in (
        (old.job_id, old.claim_token),
        (uuid4(), new.claim_token),
        (new.job_id, uuid4()),
    ):
        with pytest.raises(MessagingError) as caught:
            await h.kernel.replay_turn(job, token)
        assert caught.value.code == Code.STALE_CLAIM
    with pytest.raises(MessagingError) as late:
        await h.kernel.finish_turn(old, consume(value))
    assert late.value.code == Code.STALE_CLAIM
    assert await h.kernel.replay_turn(new.job_id, new.claim_token) == result
    async with h.runtime.engine.begin() as c:
        for sql in (
            "SELECT * FROM platform.turn_consumer_receipts",
            "UPDATE platform.turn_consumer_receipts SET result='{}'",
            "DELETE FROM platform.turn_consumer_receipts",
        ):
            with pytest.raises(DBAPIError) as denied:
                async with c.begin_nested():
                    await c.execute(text(sql))
            assert denied.value.orig.sqlstate == "42501"
        for token in (None, uuid4()):
            with pytest.raises(DBAPIError) as denied:
                async with c.begin_nested():
                    await c.execute(
                        text("SELECT platform.turn_consumer_replay(:job,:claim)"),
                        {"job": new.job_id, "claim": token},
                    )
            assert denied.value.orig.sqlstate == "P2001"
    assert len(await rows(h, "platform.turn_consumer_receipts")) == 1


@pytest.mark.parametrize("path", ["claim", "retry", "recover", "execute", "finalize"])
async def test_superseded_precedes_exhaustion_and_does_not_fail_current_turn(messaging, path):
    h = messaging
    await receive(h)
    turn = (await turns(h))[0]
    await seal(h, turn["id"])
    claim, value = await snapshot(h, turn["id"])
    await query(
        h,
        "UPDATE app.conversation_turns SET revision=revision+1 WHERE id=:id RETURNING id",
        id=turn["id"],
    )
    if path == "claim":
        await query(
            h,
            "UPDATE platform.messaging_jobs SET status='READY',claim_token=NULL,lease_until=NULL,worker_id=NULL,attempt_count=5,available_at=clock_timestamp() WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
        assert await h.kernel.claim_job("superseded") is None
    elif path == "retry":
        result = await h.kernel.retry(claim, Code.RETRY_EXHAUSTED, False)
        assert result["code"] == "SUPERSEDED"
    elif path == "recover":
        await query(
            h,
            "UPDATE platform.messaging_jobs SET attempt_count=5,lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
            id=claim.job_id,
        )
        assert await h.kernel.recover_expired() == 1
    elif path == "execute":
        assert (await h.kernel.process_turn(claim)).code == "SUPERSEDED"
    else:
        assert (await h.kernel.finish_turn(claim, consume(value))).code == "SUPERSEDED"
    state = (
        await query(
            h,
            "SELECT status,turn_outcome,error_code FROM platform.messaging_jobs WHERE id=:id",
            id=claim.job_id,
        )
    )[0]
    assert state == {"status": "SUCCEEDED", "turn_outcome": "SUPERSEDED", "error_code": None}
    assert (await turns(h))[0]["state"] == "READY" and not await rows(
        h, "platform.turn_consumer_receipts"
    )


@pytest.mark.parametrize("provider", ["CONTROLLED", "TELEGRAM"])
@pytest.mark.parametrize("commit_first", [True, False])
async def test_ingress_share_barrier_earliest_committed_origin(provider, commit_first, telegram):
    h = telegram
    # Telegram fixture retains the independent CONTROLLED connection as well.
    first_event = event(event_id="barrier-1", message_id="same")
    second_event = event(event_id="barrier-2", message_id="same")
    async with h.runtime.engine.connect() as first:
        tx = await first.begin()
        if provider == "CONTROLLED":
            sql = "SELECT platform.messaging_ingest('CONTROLLED','bot-a',CAST(:event AS jsonb),:correlation)"
            saved = (
                await first.execute(
                    text(sql), {"event": first_event.encoded(), "correlation": uuid4()}
                )
            ).scalar_one()
            second = await ingest(h, second_event)
        else:
            first_projection = projection(update="9101", message="5101")
            saved = (
                await first.execute(
                    text(
                        "SELECT platform.telegram_ingest(:bot,CAST(:projection AS jsonb),:correlation)"
                    ),
                    {
                        "bot": BOT,
                        "projection": json.dumps(first_projection),
                        "correlation": uuid4(),
                    },
                )
            ).scalar_one()
            second = TelegramReceipt.model_validate(
                await ingress(h, projection(update="9102", message="5101"))
            )
        claim = await claim_exact(h, second.job_id)
        task = asyncio.create_task(h.kernel.process_inbox(claim))
        blocker = (await first.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        try:
            async with asyncio.timeout(1.5):
                while True:
                    waiting = await query(
                        h,
                        "SELECT count(*) AS n FROM pg_stat_activity WHERE :pid=ANY(pg_blocking_pids(pid))",
                        pid=blocker,
                    )
                    if waiting[0]["n"]:
                        break
                    await asyncio.sleep(0)
            assert not task.done()
            if commit_first:
                await tx.commit()
            else:
                await tx.rollback()
            processed = await task
        finally:
            if tx.is_active:
                await tx.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    member = (
        await query(
            h,
            "SELECT * FROM app.conversation_turn_messages WHERE message_id=:id",
            id=processed.message_id,
        )
    )[0]
    assert str(member["origin_inbox_id"]) == (
        saved["inbox_id"] if commit_first else str(second.inbox_id)
    )
    assert (await context(h, member["conversation_id"]))["version"] == 2


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_non_read_committed_rejected_by_python_and_direct_capability(messaging, isolation):
    h = messaging
    async with h.runtime.engine.connect() as c:
        c = await c.execution_options(isolation_level=isolation)
        with pytest.raises(DBAPIError) as caught:
            await c.execute(text("SELECT platform.messaging_claim('bad-isolation',NULL,NULL,NULL)"))
        assert caught.value.orig.sqlstate == "P2001"
    engine = h.runtime.engine.execution_options(isolation_level=isolation)
    with pytest.raises(MessagingError) as caught:
        await MessagingDatabase(engine).claim_job("bad-python-isolation")
    assert caught.value.code == Code.TRANSACTION_STATE


@pytest.mark.parametrize("kind", ["FETCH_IMAGE", "SEND_MANUAL_TEXT"])
@pytest.mark.parametrize("same_connection", [True, False])
async def test_exhausted_blocked_conversation_releases_all_locks_and_allows_b(
    messaging, kind, same_connection
):
    h = messaging
    _, first = await receive(
        h, chat_id="blocked", image_file_id="private-a" if kind == "FETCH_IMAGE" else None
    )
    a = (await turns(h))[0]
    if kind == "SEND_MANUAL_TEXT":
        sent = await command(h, a["conversation_id"], "pending", "blocked-a")
        job_a = (
            await query(
                h,
                "SELECT j.id FROM platform.messaging_jobs j JOIN app.outbox_events b ON (b.workspace_id,b.id)=(j.workspace_id,j.outbox_id) WHERE b.message_id=:id",
                id=sent.message_id,
            )
        )[0]["id"]
    else:
        job_a = (
            await query(
                h,
                "SELECT j.id FROM platform.messaging_jobs j JOIN app.file_objects f ON (f.workspace_id,f.id)=(j.workspace_id,j.file_id) WHERE f.message_id=:id",
                id=first.message_id,
            )
        )[0]["id"]
    await receive(
        h, chat_id="healthy", external_connection_id="conn-a" if same_connection else "conn-a2"
    )
    b = next(t for t in await turns(h) if t["id"] != a["id"])
    await seal(h, b["id"])
    job_b = (
        await query(
            h,
            "SELECT id FROM platform.messaging_jobs WHERE turn_id=:id AND step='TEST_CONSUME'",
            id=b["id"],
        )
    )[0]["id"]
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE status='READY' RETURNING id",
    )
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()-interval '1 second',attempt_count=5,first_started_at=clock_timestamp()-interval '1 minute' WHERE id=:id RETURNING id",
        id=job_a,
    )
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE id=:id RETURNING id",
        id=job_b,
    )
    before = (
        await query(
            h, "SELECT to_jsonb(j) AS row FROM platform.messaging_jobs j WHERE id=:id", id=job_a
        )
    )[0]
    version = await context(h, a["conversation_id"])
    async with h.migrator.begin() as blocker:
        await blocker.execute(
            text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
            {"id": a["conversation_id"]},
        )
        selected = await h.kernel.claim_job("healthy-b")
        assert selected.job_id == job_b
        assert (
            await query(
                h, "SELECT to_jsonb(j) AS row FROM platform.messaging_jobs j WHERE id=:id", id=job_a
            )
        )[0] == before
        assert await context(h, a["conversation_id"]) == version
        async with h.migrator.begin() as verify:
            # The BUSY savepoint must release job and file/outbox, not just the
            # final blocked conversation. This transaction would fail NOWAIT.
            await verify.execute(
                text("SELECT id FROM platform.messaging_jobs WHERE id=:id FOR UPDATE NOWAIT"),
                {"id": job_a},
            )
            table, foreign = (
                ("app.file_objects", "file_id")
                if kind == "FETCH_IMAGE"
                else ("app.outbox_events", "outbox_id")
            )
            await verify.execute(
                text(
                    f"SELECT id FROM {table} WHERE id=(SELECT {foreign} FROM platform.messaging_jobs WHERE id=:id) FOR UPDATE NOWAIT"
                ),
                {"id": job_a},
            )
        await Worker(h.kernel, h.adapter).execute(selected)
    assert await h.kernel.claim_job("finish-a") is None
    assert (
        await query(
            h, "SELECT status,error_code FROM platform.messaging_jobs WHERE id=:id", id=job_a
        )
    )[0] == {"status": "DEAD", "error_code": "RETRY_EXHAUSTED"}
    assert (await context(h, a["conversation_id"]))["version"] == version["version"] + 1
    assert await h.kernel.claim_job("finish-a") is None
    assert (await context(h, a["conversation_id"]))["version"] == version["version"] + 1


async def test_more_than_100_blocked_prefix_continues_unlock_and_restart(messaging):
    h = messaging
    await receive(h, chat_id="prefix")
    a = (await turns(h))[0]
    messages = [
        (await command(h, a["conversation_id"], "pending", f"prefix-{i}")).message_id
        for i in range(101)
    ]
    assert len(set(messages)) == 101
    await receive(h, chat_id="healthy")
    b = next(t for t in await turns(h) if t["id"] != a["id"])
    await seal(h, b["id"])
    job_b = (
        await query(
            h,
            "SELECT id FROM platform.messaging_jobs WHERE turn_id=:id AND step='TEST_CONSUME'",
            id=b["id"],
        )
    )[0]["id"]
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()+interval '1 hour' WHERE status='READY' RETURNING id",
    )
    await query(
        h,
        "UPDATE platform.messaging_jobs SET attempt_count=5,first_started_at=clock_timestamp()-interval '1 minute',available_at=clock_timestamp()-interval '1 second' WHERE kind='SEND_MANUAL_TEXT' RETURNING id",
    )
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp() WHERE id=:id RETURNING id",
        id=job_b,
    )
    before = await query(
        h,
        "SELECT id,version,available_at,attempt_count FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT' ORDER BY id",
    )
    async with h.migrator.begin() as c:
        await c.execute(
            text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
            {"id": a["conversation_id"]},
        )
        assert await h.kernel.claim_job("prefix") is None
        cursor = h.kernel._claim_scan["prefix"]
        selected = await h.kernel.claim_job("prefix")
        assert selected is not None and selected.job_id == job_b and cursor.id is not None
        assert (
            await query(
                h,
                "SELECT id,version,available_at,attempt_count FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT' ORDER BY id",
            )
            == before
        )
        await Worker(h.kernel, h.adapter).execute(selected)
    restarted = MessagingDatabase(h.runtime.engine)
    assert not restarted._claim_scan
    # First bounded call terminalizes 100; the second reaches the remaining row.
    assert await restarted.claim_job("restart") is None
    assert await restarted.claim_job("restart") is None
    state = await query(
        h,
        "SELECT status,count(*) AS n FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT' GROUP BY status",
    )
    assert state == [{"status": "DEAD", "n": 101}]


async def test_concurrent_recovery_skips_busy_and_unknown_is_single_context_fact(messaging):
    h = messaging
    await receive(h, chat_id="a")
    a = (await turns(h))[0]
    sa = await command(h, a["conversation_id"], "a", "unknown-a")
    ja = (
        await query(
            h,
            "SELECT j.id FROM platform.messaging_jobs j JOIN app.outbox_events b ON (b.workspace_id,b.id)=(j.workspace_id,j.outbox_id) WHERE b.message_id=:id",
            id=sa.message_id,
        )
    )[0]["id"]
    ca = await claim_exact(h, ja)
    await h.kernel.begin_send(ca)
    await receive(h, chat_id="b")
    b = next(t for t in await turns(h) if t["id"] != a["id"])
    sb = await command(h, b["conversation_id"], "b", "unknown-b")
    jb = (
        await query(
            h,
            "SELECT j.id FROM platform.messaging_jobs j JOIN app.outbox_events x ON (x.workspace_id,x.id)=(j.workspace_id,x.outbox_id) WHERE x.message_id=:id",
            id=sb.message_id,
        )
    )[0]["id"]
    cb = await claim_exact(h, jb)
    await h.kernel.begin_send(cb)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE status='RUNNING' RETURNING id",
    )
    va, vb = await context(h, a["conversation_id"]), await context(h, b["conversation_id"])
    other = MessagingDatabase(h.runtime.engine)
    async with h.migrator.begin() as lock:
        await lock.execute(
            text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
            {"id": a["conversation_id"]},
        )
        results = await asyncio.gather(h.kernel.recover_expired(1), other.recover_expired(1))
        assert sum(results) == 1
        assert await context(h, a["conversation_id"]) == va
        assert (await context(h, b["conversation_id"]))["version"] == vb["version"] + 1
    # A new process loses only the cursor hint; it recovers A exactly once.
    restarted = MessagingDatabase(h.runtime.engine)
    assert await restarted.recover_expired() == 1
    assert await restarted.recover_expired() == 0
    assert (await context(h, a["conversation_id"]))["version"] == va["version"] + 1
    assert {r["status"] for r in await rows(h, "app.outbox_events")} == {"UNKNOWN"}
    assert not h.ledger.exists()


async def test_raw_typed_refs_rls_and_membership_origin_immutability(messaging):
    h = messaging
    await receive(h)
    turn = (await turns(h))[0]
    member = (await rows(h, "app.conversation_turn_messages"))[0]
    async with h.migrator.begin() as c:
        for table in (
            "app.conversation_turns",
            "app.conversation_turn_messages",
            "platform.turn_consumer_receipts",
        ):
            actual = (
                await c.execute(
                    text(
                        "SELECT c.relrowsecurity,c.relforcerowsecurity,r.rolname,has_table_privilege('asm_runtime',c.oid,'SELECT,INSERT,UPDATE,DELETE') FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE c.oid=CAST(:table AS regclass)"
                    ),
                    {"table": table},
                )
            ).one()
            assert actual == (True, True, "asm_migrator", False)
        mutations = [
            (
                "UPDATE app.conversation_turn_messages SET origin_inbox_id=:wrong WHERE message_id=:id",
                member["message_id"],
            ),
            (
                "UPDATE app.conversation_turn_messages SET turn_id=:wrong WHERE message_id=:id",
                member["message_id"],
            ),
            (
                "UPDATE platform.inbox_events SET turn_ingress_seq=turn_ingress_seq+1 WHERE id=:id",
                member["origin_inbox_id"],
            ),
            ("UPDATE app.conversation_turns SET conversation_id=:wrong WHERE id=:id", turn["id"]),
        ]
        for sql, target in mutations:
            with pytest.raises(DBAPIError) as caught:
                async with c.begin_nested():
                    await c.execute(text(sql), {"wrong": uuid4(), "id": target})
            assert caught.value.orig.sqlstate == "23514"
        for ws, conn, target in ((B, CA, turn["id"]), (A, CA2, turn["id"]), (A, CA, uuid4())):
            with pytest.raises(DBAPIError) as caught:
                async with c.begin_nested():
                    await c.execute(
                        text(
                            "INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,turn_id,turn_revision,step,correlation_id) VALUES(:ws,:conn,'PROCESS_TURN',:turn,999,'GROUP',:corr)"
                        ),
                        {"ws": ws, "conn": conn, "turn": target, "corr": uuid4()},
                    )
            assert caught.value.orig.sqlstate == "23503"
    async with h.runtime.engine.begin() as c:
        for table in ("app.conversation_turns", "app.conversation_turn_messages"):
            with pytest.raises(DBAPIError) as caught:
                async with c.begin_nested():
                    await c.execute(text(f"SELECT * FROM {table}"))
            assert caught.value.orig.sqlstate == "42501"


async def test_uncommitted_receipt_never_replays_and_concurrent_finalize_is_one_result(messaging):
    h = messaging
    await receive(h)
    turn = (await turns(h))[0]
    await seal(h, turn["id"])
    claim, value = await snapshot(h, turn["id"])
    result = consume(value)
    async with h.runtime.engine.connect() as pending:
        transaction = await pending.begin()
        saved = await call(
            pending,
            "SELECT platform.turn_consumer_finalize(:job,:claim,CAST(:result AS jsonb))",
            {"job": claim.job_id, "claim": claim.claim_token, "result": result.model_dump_json()},
        )
        with pytest.raises(MessagingError) as miss:
            await h.kernel.replay_turn(claim.job_id, claim.claim_token)
        assert miss.value.code == Code.STALE_CLAIM
        await transaction.rollback()
    assert not await rows(h, "platform.turn_consumer_receipts")
    first, second = await asyncio.gather(
        h.kernel.finish_turn(claim, result),
        MessagingDatabase(h.runtime.engine).finish_turn(claim, result),
    )
    assert (
        first == second
        and first.model_dump(mode="json")["snapshot_digest"] == saved["snapshot_digest"]
    )
    assert len(await rows(h, "platform.turn_consumer_receipts")) == 1


async def test_turn_exhaustion_is_terminal_and_file_failure_adds_only_context(messaging):
    h = messaging
    await receive(h, image_file_id="late-failed")
    turn = (await turns(h))[0]
    await wait_due(h, turn["id"])
    group = await turn_claim(h, turn["id"], "GROUP")
    await h.kernel.retry(group, Code.RETRY_EXHAUSTED, False)
    failed = (await turns(h))[0]
    assert failed["state"] == "FAILED" and failed["error_code"] == "RETRY_EXHAUSTED"
    job = (await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"))[0][
        "id"
    ]
    fetch = await claim_exact(h, job)
    version = await context(h, turn["conversation_id"])
    await h.kernel.retry(fetch, Code.INVALID_INPUT, False)
    assert (await turns(h))[0] == failed
    assert (await context(h, turn["conversation_id"]))["version"] == version["version"] + 1
    assert (await rows(h, "app.file_objects"))[0]["status"] == "FAILED"


async def test_continuous_ingress_reaches_real_hard_cap_without_extending_it(messaging):
    from datetime import UTC, datetime

    h = messaging
    await receive(h, event_id="hard-0", message_id="hard-0")
    initial = (await turns(h))[0]
    # Real elapsed policy time, with arrivals less than D apart. No synthetic
    # deadline or mark is changed for this G/cap evidence.
    for index, seconds in enumerate((1.5, 3, 4.5, 6, 7.5, 9), 1):
        delay = seconds - (datetime.now(UTC) - initial["first_ingress_at"]).total_seconds()
        assert delay > 0
        await asyncio.sleep(delay)
        await receive(h, event_id=f"hard-{index}", message_id=f"hard-{index}")
    collecting = (await turns(h))[0]
    assert collecting["id"] == initial["id"] and collecting["member_count"] == 7
    assert collecting["quiet_at"] == collecting["hard_at"] == initial["hard_at"]
    await seal(h, initial["id"])
    closed = (await turns(h))[0]
    assert closed["seal_time"] == initial["hard_at"] and closed["state"] == "READY"
    assert (closed["media_deadline_at"] - closed["first_ingress_at"]).total_seconds() == 25
    await receive(h, event_id="after-hard", message_id="after-hard")
    assert len(await turns(h)) == 2
    assert next(t for t in await turns(h) if t["id"] == initial["id"]) == closed


async def test_file_commit_rollback_has_no_partial_context_revision_or_new_jobs(messaging):
    h = messaging
    await receive(h, image_file_id="rollback-photo")
    turn = (await turns(h))[0]
    fetch_id = (await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"))[
        0
    ]["id"]
    fetch = await claim_exact(h, fetch_id)
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(fetch, MANIFEST)
    before_turn, before_context = (await turns(h))[0], await context(h, turn["conversation_id"])
    jobs_before = await rows(h, "platform.messaging_jobs")

    async def crash(name):
        if name == "fetch_finalize_before_commit":
            raise SQLAlchemyError("file commit boundary")

    failing = FileDatabase(MessagingDatabase(h.runtime.engine, barrier=crash))
    with pytest.raises(SQLAlchemyError, match="file commit boundary"):
        await failing.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    assert (await turns(h))[0] == before_turn
    assert await context(h, turn["conversation_id"]) == before_context
    assert await rows(h, "platform.messaging_jobs") == jobs_before
    assert (await rows(h, "app.file_objects"))[0]["status"] == "PENDING"
    await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    assert (await context(h, turn["conversation_id"]))["version"] == before_context["version"] + 1
    assert (await turns(h))[0]["revision"] == before_turn["revision"] + 1


async def test_failed_media_is_partial_without_wait_expired_or_reopen(messaging):
    h = messaging
    await receive(h, image_file_id="failed-photo")
    turn = (await turns(h))[0]
    fetch_id = (await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"))[
        0
    ]["id"]
    fetch = await claim_exact(h, fetch_id)
    initial = await context(h, turn["conversation_id"])
    await h.kernel.retry(fetch, Code.DEPENDENCY_UNAVAILABLE, True)
    assert await context(h, turn["conversation_id"]) == initial
    assert (await turns(h))[0] == turn
    fetched_again = await claim_exact(h, fetch_id)
    await h.kernel.retry(fetched_again, Code.INVALID_INPUT, False)
    assert (await context(h, turn["conversation_id"]))["version"] == initial["version"] + 1
    await seal(h, turn["id"])
    claim, value = await snapshot(h, turn["id"])
    assert value.readiness == "PARTIAL" and value.members[0].file.status == "FAILED"
    assert not value.members[0].file.wait_expired
    assert (await h.kernel.finish_turn(claim, consume(value))).result.wait_expired_count == 0


@pytest.mark.parametrize("ending", ["SENT", "UNKNOWN", "FAILED", "REVOKED", "RETRY"])
async def test_each_manual_acceptance_and_terminal_fact_increments_once(messaging, ending):
    from asm.messaging.models import OutcomeKind, SendOutcome
    from test_tenancy_postgres import UA

    h = messaging
    await receive(h)
    turn = (await turns(h))[0]
    conv = turn["conversation_id"]
    before = (await context(h, conv))["version"]
    accepted = await command(h, conv, "one material fact", "material")
    replay = await command(h, conv, "one material fact", "material")
    assert (
        accepted.message_id == replay.message_id
        and (await context(h, conv))["version"] == before + 1
    )
    job = (
        await query(
            h,
            "SELECT j.id FROM platform.messaging_jobs j JOIN app.outbox_events b ON (b.workspace_id,b.id)=(j.workspace_id,j.outbox_id) WHERE b.message_id=:id",
            id=accepted.message_id,
        )
    )[0]["id"]
    claim = await claim_exact(h, job)
    if ending == "REVOKED":
        await query(
            h,
            "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:owner RETURNING workspace_id",
            ws=A,
            owner=UA,
        )
        rejected = await h.kernel.begin_send(claim)
        assert rejected.code == "NOT_ALLOWED"
    else:
        permit = await h.kernel.begin_send(claim)
        assert (await context(h, conv))["version"] == before + 1
        if ending == "SENT":
            outcome = SendOutcome(OutcomeKind.SUCCESS, provider_message_id="delivered")
        elif ending == "UNKNOWN":
            outcome = SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT)
        elif ending == "FAILED":
            outcome = SendOutcome(OutcomeKind.NOT_SENT_PERMANENT, error_code=Code.INVALID_INPUT)
        else:
            outcome = SendOutcome(
                OutcomeKind.NOT_SENT_RETRYABLE, error_code=Code.DEPENDENCY_UNAVAILABLE
            )
        saved = await h.kernel.finish_send(
            claim.job_id, claim.claim_token, permit.attempt_id, outcome
        )
        repeated = await h.kernel.finish_send(
            claim.job_id, claim.claim_token, permit.attempt_id, outcome
        )
        assert repeated.code == "ALREADY_FINALIZED" and repeated.status == saved.status
        assert repeated.job_id == saved.job_id and repeated.attempt_id == saved.attempt_id
        if ending == "RETRY":
            assert (await context(h, conv))["version"] == before + 1
            await query(
                h,
                "UPDATE platform.messaging_jobs SET attempt_count=5,available_at=clock_timestamp() WHERE id=:id RETURNING id",
                id=job,
            )
            assert await h.kernel.claim_job("manual-exhaustion") is None
    assert (await context(h, conv))["version"] == before + 2
    assert (
        await query(h, "SELECT version FROM app.messages WHERE id=:id", id=accepted.message_id)
    )[0]["version"] == 1
