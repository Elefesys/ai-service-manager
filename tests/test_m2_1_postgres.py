"""M2 kernel invariants on real asm_runtime PostgreSQL, including worker crashes."""

import asyncio
import json
import os
import sys
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.messaging.adapter import ControlledAdapter, TrustedSource
from asm.messaging.commands import OwnerRepository, send_manual_text
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import EventKind, OutcomeKind, SendOutcome, text_fingerprint
from asm.messaging.worker import Worker, run
from asm.tenancy import AuthenticatedAccount, TenancyError, current_workspace_context
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_m2_1_models import event
from test_tenancy_postgres import BA, BA2, BB, PROVIDER, UA, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
CA, CB, CA2 = (UUID(int=n) for n in (3001, 3002, 3003))
TABLES = (
    "platform.messaging_command_receipts",
    "platform.messaging_jobs",
    "platform.inbox_events",
    "app.outbox_events",
    "app.audit_events",
    "app.messages",
    "app.conversations",
    "app.client_identities",
    "app.clients",
    "platform.channel_routes",
    "app.channel_connections",
)


async def provision(migrator):
    async with migrator.begin() as c:
        for ws, business, cid, bot, external in (
            (A, BA, CA, "bot-a", "conn-a"),
            (B, BB, CB, "bot-b", "conn-b"),
            (A, BA2, CA2, "bot-a", "conn-a2"),
        ):
            await c.execute(
                text(
                    "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) VALUES(:ws,:id,:business,'CONTROLLED',:bot,:external)"
                ),
                {"ws": ws, "id": cid, "business": business, "bot": bot, "external": external},
            )
            await c.execute(
                text(
                    "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:id,'CONTROLLED',:bot,:external)"
                ),
                {"ws": ws, "id": cid, "bot": bot, "external": external},
            )


async def cleanup(migrator):
    async with migrator.begin() as c:
        # M2.3 receipt/state references precede Inbox and connection deletion.
        # Also clear tenantless receipts for bots bound only to this fixture.
        await c.execute(
            text(
                "DELETE FROM platform.telegram_update_receipts WHERE workspace_id IN (:a,:b) OR "
                "(workspace_id IS NULL AND bot_identity IN (SELECT bot_identity FROM "
                "platform.telegram_connection_state WHERE workspace_id IN (:a,:b)))"
            ),
            {"a": A, "b": B},
        )
        await c.execute(
            text("DELETE FROM platform.telegram_connection_state WHERE workspace_id IN (:a,:b)"),
            {"a": A, "b": B},
        )
        # M2.2 adds a typed upload/job/file FK chain. Keep explicit scoped
        # deletion in one transaction; the READY winner FK is deferred.
        for table in ("platform.file_object_uploads", *TABLES[:2], "app.file_objects", *TABLES[2:]):
            suffix = (
                " AND event_type='MESSAGE_SEND_REQUESTED'" if table == "app.audit_events" else ""
            )
            await c.execute(
                text(f"DELETE FROM {table} WHERE workspace_id IN (:a,:b)" + suffix),
                {"a": A, "b": B},
            )


@pytest_asyncio.fixture
async def messaging(seeded, tmp_path):
    runtime, migrator = seeded
    await provision(migrator)
    adapter = ControlledAdapter(environment="TEST", ledger=tmp_path / "effects.jsonl")
    kernel = MessagingDatabase(runtime.engine)
    h = SimpleNamespace(
        runtime=runtime,
        migrator=migrator,
        kernel=kernel,
        adapter=adapter,
        worker=Worker(kernel, adapter),
        ledger=adapter.ledger,
    )
    try:
        yield h
    finally:
        await cleanup(migrator)


async def ingest(h, value=None):
    value = value or event()
    return await h.kernel.ingest_event(h.adapter.source(value.bot_identity), value, uuid4())


async def receive(h, value=None):
    receipt = await ingest(h, value)
    claim = await h.kernel.claim_job("test-receive")
    assert claim is not None and claim.kind == "PROCESS_INBOX"
    result = await h.kernel.process_inbox(claim)
    return receipt, result


async def conversation(h):
    await receive(h)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        rows = await OwnerRepository(unit).conversations()
        return UUID(rows[0]["conversation_id"])


async def command(h, cid, value="Reply", key="manual-1", actor=UA, workspace=A):
    return await send_manual_text(
        h.runtime.tenancy, AuthenticatedAccount(actor), workspace, uuid4(), cid, value, key
    )


async def delivery(h, message_id):
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        return await OwnerRepository(unit).delivery(message_id)


async def query(h, sql, **params):
    async with h.migrator.begin() as c:
        return (await c.execute(text(sql), params)).mappings().all()


async def counts(h):
    async with h.migrator.connect() as c:
        return {
            name: (
                await c.execute(
                    text(f"SELECT count(*) FROM {name} WHERE workspace_id=:ws"), {"ws": A}
                )
            ).scalar_one()
            for name in TABLES[:8]
        }


async def expire(h):
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE status='RUNNING' RETURNING id",
    )
    await h.kernel.recover_expired()
    await due(h)


async def due(h):
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE status='READY' RETURNING id",
    )


def ledger(h):
    return (
        [json.loads(line)["event"] for line in h.ledger.read_text().splitlines()]
        if h.ledger.exists()
        else []
    )


async def test_trusted_route_binding_and_concurrent_durable_event_dedupe(messaging):
    h = messaging
    receipts = await asyncio.gather(*(ingest(h) for _ in range(6)))
    assert len({r.inbox_id for r in receipts}) == len({r.job_id for r in receipts}) == 1
    assert {r.code for r in receipts} == {"ACCEPTED", "DUPLICATE"}
    assert len({r.accepted_at for r in receipts}) == 1
    stored = await query(
        h, "SELECT encode(event_fingerprint,'hex') AS fp,status FROM platform.inbox_events"
    )
    assert stored == [{"fp": event().fingerprint(), "status": "PENDING"}]
    for source, value in (
        (h.adapter.source("bot-b"), event()),
        (TrustedSource("CONTROLLED", "bot-a", object()), event()),
    ):
        with pytest.raises(MessagingError, match="ACCESS_DENIED"):
            await h.kernel.ingest_event(source, value, uuid4())
    with pytest.raises(MessagingError, match="EVENT_ID_CONFLICT"):
        await ingest(h, event(text="conflict"))
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await ingest(h, event(external_connection_id="unknown", event_id="unknown"))
    # Same event/message identifiers in a different provider/bot namespace are distinct.
    other = await ingest(h, event(bot_identity="bot-b", external_connection_id="conn-b"))
    assert other.workspace_id == B and other.inbox_id != receipts[0].inbox_id
    assert await h.worker.run_once() and await h.worker.run_once()
    assert not await h.worker.run_once()
    messages = await query(
        h, "SELECT workspace_id,provider_message_id FROM app.messages ORDER BY workspace_id"
    )
    assert messages == [
        {"workspace_id": A, "provider_message_id": "msg-1"},
        {"workspace_id": B, "provider_message_id": "msg-1"},
    ]


@pytest.mark.parametrize("kind", [k for k in EventKind if k != EventKind.CLIENT_MESSAGE])
async def test_ignored_kinds_have_durable_explicit_results(messaging, kind):
    h = messaging
    value = event(
        kind=kind, chat_id=None, message_id=None, sender_id=None, occurred_at=None, text=None
    )
    receipt, result = await receive(h, value)
    assert result.code == "IGNORED_" + kind.value and result.status == "IGNORED"
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        stored = await OwnerRepository(unit).inbox(receipt.inbox_id)
        assert stored["status"] == "IGNORED" and stored["result_code"] == result.code
        assert await OwnerRepository(unit).conversations() == ()
    assert h.adapter.calls == 0


async def test_image_reference_message_projection_dedupe_and_identity_conflicts(messaging):
    h = messaging
    value = event(text=" caption é\n ", image_file_id="provider-ref", media_group_id="album")
    _, original = await receive(h, value)
    # This M2.1 projection fixture deliberately has no provider bytes. Consume
    # its now-real FETCH job explicitly; all original dedupe assertions remain.
    fetch = await h.kernel.claim_job("legacy-image-fixture")
    assert fetch.kind == "FETCH_IMAGE"
    assert len(await query(h, "SELECT id FROM app.file_objects")) == 1
    await h.kernel.retry(fetch, Code.INVALID_INPUT, False)
    _, duplicate = await receive(h, replace(value, event_id="evt-2"))
    assert duplicate.code == "DUPLICATE" and duplicate.message_id == original.message_id
    _, conflict = await receive(h, replace(value, event_id="evt-3", text="changed"))
    assert conflict.code == "MESSAGE_ID_CONFLICT" and conflict.status == "FAILED"
    _, identity_conflict = await receive(
        h, replace(value, event_id="evt-4", message_id="msg-2", sender_id="other-client")
    )
    assert identity_conflict.code == "CONVERSATION_IDENTITY_CONFLICT"
    rows = await query(h, "SELECT content_type,text,image_file_id,media_group_id FROM app.messages")
    assert rows == [
        {
            "content_type": "IMAGE_REFERENCE",
            "text": value.text,
            "image_file_id": "provider-ref",
            "media_group_id": "album",
        }
    ]
    assert len(await query(h, "SELECT id FROM app.conversations")) == 1
    assert len(await query(h, "SELECT id FROM app.file_objects")) == 1
    assert (
        len(await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")) == 1
    )


@pytest.mark.parametrize(
    "value",
    [" é ", 'e\u0301\n"quote"\\', "🎨" * 4096, "a\t\n"],
    ids=["spaces", "combining-quotes", "max-utf8", "linebreaks"],
)
async def test_manual_fingerprints_replay_concurrent_atomic_intent(messaging, value):
    h = messaging
    cid = await conversation(h)
    receipts = await asyncio.gather(*(command(h, cid, value) for _ in range(4)))
    first = receipts[0]
    assert len({r.receipt_id for r in receipts}) == 1
    assert len({r.accepted_at for r in receipts}) == 1
    assert {r.code for r in receipts} == {"ACCEPTED", "REPLAY"}
    assert first.request_fingerprint == text_fingerprint(A, UA, cid, value)
    n = await counts(h)
    assert (
        n["platform.messaging_command_receipts"]
        == n["app.outbox_events"]
        == n["app.audit_events"]
        == 1
    )
    assert n["app.messages"] == n["platform.messaging_jobs"] == 2
    with pytest.raises(MessagingError, match="IDEMPOTENCY_KEY_CONFLICT"):
        await command(h, cid, "different")
    assert await counts(h) == n
    second = await command(h, cid, value, "manual-2")
    assert second.message_id != first.message_id
    assert (await command(h, cid, value)).accepted_at == first.accepted_at


@pytest.mark.parametrize(
    "table",
    [
        "app.messages",
        "app.outbox_events",
        "app.audit_events",
        "platform.messaging_jobs",
        "platform.messaging_command_receipts",
    ],
)
async def test_command_rollback_at_every_atomic_link(messaging, table):
    h = messaging
    cid = await conversation(h)
    before = await counts(h)
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform.test_m2_abort() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled abort'; END $$"
            )
        )
        await c.execute(
            text(
                f"CREATE TRIGGER test_m2_abort BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION platform.test_m2_abort()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            await command(h, cid)
        assert await counts(h) == before
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text(f"DROP TRIGGER test_m2_abort ON {table}"))
            await c.execute(text("DROP FUNCTION platform.test_m2_abort()"))
    assert (await command(h, cid)).code == "ACCEPTED"


async def test_owner_only_live_admission_replay_and_cross_workspace_reads(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    for actor, workspace in ((PROVIDER, A), (UB, B)):
        with pytest.raises(MessagingError, match="ACCESS_DENIED"):
            await command(h, cid, actor=actor, workspace=workspace)
        async with h.runtime.tenancy.transaction(
            AuthenticatedAccount(actor), workspace, uuid4()
        ) as unit:
            with pytest.raises(MessagingError, match="ACCESS_DENIED"):
                await OwnerRepository(unit).conversations()
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws RETURNING workspace_id",
        ws=B,
    )
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await command(h, cid, actor=UB, workspace=B)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UB), B, uuid4()) as unit:
        assert await OwnerRepository(unit).conversations() == ()
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        async with h.runtime.tenancy.transaction(AuthenticatedAccount(UB), B, uuid4()) as unit:
            await OwnerRepository(unit).delivery(receipt.message_id)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        ws=A,
        actor=UA,
    )
    with pytest.raises(MessagingError, match="ACCESS_DENIED"):
        await command(h, cid)  # authorization precedes even an existing receipt


@pytest.mark.parametrize("revoke", ["membership", "account", "workspace", "business", "connection"])
async def test_revocation_before_send_start_prevents_adapter_call(messaging, revoke):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    statements = {
        "membership": "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:id RETURNING workspace_id",
        "account": "UPDATE platform.user_accounts SET status='DISABLED' WHERE id=:id RETURNING id",
        "workspace": "UPDATE platform.workspaces SET status='ARCHIVED' WHERE id=:id RETURNING id",
        "business": "UPDATE app.businesses SET status='ARCHIVED' WHERE id=:id RETURNING id",
        "connection": "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id",
    }
    await query(
        h,
        statements[revoke],
        id={"membership": A, "account": UA, "workspace": A, "business": BA, "connection": CA}[
            revoke
        ],
    )
    assert await h.worker.run_once()
    row = (
        await query(
            h, "SELECT status,error_code FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id
        )
    )[0]
    assert row == {"status": "FAILED", "error_code": "NOT_ALLOWED"} and h.adapter.calls == 0


async def test_claims_task_xid_pool_and_human_worker_boundaries(messaging):
    h = messaging
    await ingest(h)
    claims = await asyncio.gather(h.kernel.claim_job("worker-1"), h.kernel.claim_job("worker-2"))
    claim = next(c for c in claims if c is not None)
    assert sum(c is not None for c in claims) == 1
    for job, token in ((uuid4(), claim.claim_token), (claim.job_id, uuid4())):
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            async with h.kernel.admit_job(job, token):
                pytest.fail("forged claim admitted")
    with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            with pytest.raises(TenancyError):
                current_workspace_context()
            with pytest.raises(TenancyError):
                async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()):
                    pytest.fail("nested owner")
            with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
                await asyncio.create_task(unit.process_inbox())
            # Failed cross-task invocation poisons the unit; whole transaction rolls back.
            with pytest.raises(MessagingError):
                await unit.process_inbox()


async def test_worker_physical_transaction_loss_and_no_general_table_access(messaging):
    h = messaging
    await ingest(h)
    claim = await h.kernel.claim_job("worker")
    with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            await unit._connection.exec_driver_sql("ROLLBACK")
            await unit.process_inbox()
    with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
        await unit.process_inbox()
    async with h.kernel.admit_job(claim.job_id, claim.claim_token) as active:
        assert (await active._connection.execute(text("SELECT * FROM app.businesses"))).all() == []
        assert (await active._connection.execute(text("SELECT * FROM app.messages"))).all() == []
        for table in (
            "platform.messaging_jobs",
            "platform.messaging_command_receipts",
            "platform.channel_routes",
            "app.outbox_events",
        ):
            with pytest.raises(DBAPIError) as caught:
                async with active._connection.begin_nested():
                    await active._connection.execute(text(f"SELECT * FROM {table}"))
            assert caught.value.orig.sqlstate == "42501"
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()):
        with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
            await h.kernel.claim_job("nested")
    async with h.runtime.engine.connect() as c:
        assert (await c.execute(text("SELECT app.current_workspace_id()"))).scalar_one() is None
        assert (
            await c.execute(text("SELECT nullif(current_setting('asm.actor_kind',true),'')"))
        ).scalar_one() is None


async def test_admission_ignores_forged_claim_entity_fields_and_preserves_disconnect_inbound(
    messaging,
):
    h = messaging
    receipt = await ingest(h)
    claim = await h.kernel.claim_job("worker")
    await query(
        h, "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id", id=CA
    )
    forged = claim.model_copy(
        update={
            "workspace_id": B,
            "connection_id": CB,
            "inbox_id": uuid4(),
            "kind": "SEND_MANUAL_TEXT",
        }
    )
    result = await h.kernel.process_inbox(forged)
    assert result.status == "PROCESSED" and result.inbox_id == receipt.inbox_id
    assert (await query(h, "SELECT workspace_id FROM app.messages"))[0]["workspace_id"] == A


async def test_lease_reclaim_new_token_stale_claim_and_retry_age(messaging):
    h = messaging
    await ingest(h)
    old = await h.kernel.claim_job("old")
    await expire(h)
    fresh = await h.kernel.claim_job("fresh")
    assert old.job_id == fresh.job_id and old.claim_token != fresh.claim_token
    assert fresh.attempt_count == 2
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.process_inbox(old)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET first_started_at=clock_timestamp()-interval '16 minutes' WHERE id=:id RETURNING id",
        id=fresh.job_id,
    )
    await expire(h)
    assert await h.kernel.claim_job("never") is None
    assert (await query(h, "SELECT status,result_code FROM platform.inbox_events"))[0] == {
        "status": "FAILED",
        "result_code": "RETRY_EXHAUSTED",
    }


async def test_safe_not_sent_jitter_and_exhaustion_count_every_call(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    h.adapter.outcome = OutcomeKind.NOT_SENT_RETRYABLE
    for attempt in range(1, 6):
        assert await h.worker.run_once()
        state = await delivery(h, receipt.message_id)
        assert state["status"] == ("PENDING" if attempt < 5 else "FAILED")
        job = (
            await query(
                h,
                "SELECT status,attempt_count,extract(epoch from available_at-clock_timestamp()) AS delay,error_code FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT'",
            )
        )[0]
        assert job["attempt_count"] == attempt
        if attempt < 5:
            assert -1 <= job["delay"] <= min(60, 2 ** (attempt - 1))
        else:
            assert job["status"] == "DEAD" and job["error_code"] == "RETRY_EXHAUSTED"
        await due(h)
    assert not await h.worker.run_once()
    assert ledger(h) == ["CALL"] * 5


@pytest.mark.parametrize("mode", ["success", "permanent", "unknown", "timeout", "exception"])
async def test_effect_result_and_pool_release_without_blind_resend(messaging, mode):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    h.adapter.outcome = {
        "success": OutcomeKind.SUCCESS,
        "permanent": OutcomeKind.NOT_SENT_PERMANENT,
    }.get(mode, OutcomeKind.UNKNOWN)

    async def barrier(stage):
        assert h.runtime.engine.pool.checkedout() == 0
        with pytest.raises(TenancyError):
            current_workspace_context()
        if stage == "after_effect" and mode == "timeout":
            await asyncio.Event().wait()
        if stage == "after_effect" and mode == "exception":
            raise OSError("provider body must not leak")

    h.adapter.barrier = barrier
    h.worker.deadline = 0.05
    assert await h.worker.run_once()
    state = await delivery(h, receipt.message_id)
    assert state["status"] == {"success": "SENT", "permanent": "FAILED"}.get(mode, "UNKNOWN")
    assert "claim_token" not in state and "attempt_id" not in state
    await expire(h)
    assert not await Worker(
        h.kernel, ControlledAdapter(environment="TEST", ledger=h.ledger)
    ).run_once()
    assert ledger(h).count("CALL") == 1


async def test_lost_finalize_ack_reads_canonical_success_and_replays_exact_outcome(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    lost = False

    async def barrier(stage):
        nonlocal lost
        if stage == "finalize_after_commit" and not lost:
            lost = True
            raise SQLAlchemyError("controlled lost commit acknowledgment")

    h.kernel._barrier = barrier
    assert await h.worker.run_once()
    assert (await delivery(h, receipt.message_id))["status"] == "SENT"
    assert ledger(h) == ["CALL", "EFFECT"]
    row = (
        await query(
            h,
            "SELECT id,last_claim_token,last_attempt_id,last_provider_message_id FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT'",
        )
    )[0]
    outcome = SendOutcome(OutcomeKind.SUCCESS, row["last_provider_message_id"])
    result = await h.kernel.finish_send(
        row["id"], row["last_claim_token"], row["last_attempt_id"], outcome
    )
    assert result.code == "ALREADY_FINALIZED" and result.status == "SENT"
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.finish_send(
            row["id"],
            row["last_claim_token"],
            row["last_attempt_id"],
            SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
        )


async def test_expired_dispatch_unknown_late_success_rejected_even_after_revocation(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    claim = await h.kernel.claim_job("old")
    permit = await h.kernel.begin_send(claim)
    outcome = await h.adapter.send(permit)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
    )
    await query(
        h, "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id", id=CA
    )
    await expire(h)
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.finish_send(claim.job_id, claim.claim_token, permit.attempt_id, outcome)
    assert (
        await query(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id)
    )[0]["status"] == "UNKNOWN"
    assert not await h.worker.run_once() and h.adapter.calls == 1


CHILD = r"""
import asyncio, os
from pathlib import Path
from asm.foundation import Settings, RuntimeDatabase
from asm.messaging.database import MessagingDatabase
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.worker import Worker
async def main():
    async def barrier(stage):
        if stage == os.environ['M2_CRASH_STAGE']:
            os._exit(42)
    runtime = RuntimeDatabase(Settings())
    kernel = MessagingDatabase(runtime.engine, barrier=barrier)
    adapter = ControlledAdapter(environment='TEST', ledger=Path(os.environ['M2_LEDGER']), barrier=barrier)
    try:
        await Worker(kernel, adapter).run_once()
    finally:
        await runtime.close()
asyncio.run(main())
"""


@pytest.mark.parametrize(
    "stage,expected,calls",
    [
        ("start_before_commit", "SENT", 1),
        ("start_after_commit", "UNKNOWN", 0),
        ("before_call", "UNKNOWN", 0),
        ("after_effect", "UNKNOWN", 1),
        ("before_finalize", "UNKNOWN", 1),
        ("finalize_before_commit", "UNKNOWN", 1),
        ("finalize_after_commit", "SENT", 1),
    ],
)
async def test_actual_process_crash_restart_durable_effect_ledger(
    messaging, stage, expected, calls
):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        CHILD,
        env={**os.environ, "M2_CRASH_STAGE": stage, "M2_LEDGER": str(h.ledger)},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(child.communicate(), timeout=15)
    assert child.returncode == 42, (stdout.decode(), stderr.decode())
    await expire(h)
    replacement = Worker(
        MessagingDatabase(h.runtime.engine), ControlledAdapter(environment="TEST", ledger=h.ledger)
    )
    await replacement.run_once()
    assert (await delivery(h, receipt.message_id))["status"] == expected
    assert ledger(h).count("CALL") == calls
    assert not await replacement.run_once()
    assert ledger(h).count("CALL") == calls


@pytest.mark.parametrize("stage", ["process_before_commit", "process_after_commit"])
async def test_inbound_process_crash_is_atomic_and_recoverable(messaging, stage):
    h = messaging
    await ingest(h)
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        CHILD,
        env={**os.environ, "M2_CRASH_STAGE": stage, "M2_LEDGER": str(h.ledger)},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(child.communicate(), 15)
    assert child.returncode == 42, (out.decode(), err.decode())
    before = await counts(h)
    assert before["app.messages"] == (0 if stage == "process_before_commit" else 1)
    await expire(h)
    await h.worker.run_once()
    assert (await counts(h))["app.messages"] == 1
    assert ledger(h) == []


async def test_scheduler_loop_recovers_and_sigterm_stop_prevents_claim(messaging):
    h = messaging
    await ingest(h)
    await h.kernel.claim_job("dead-worker")
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE status='RUNNING' RETURNING id",
    )
    stop = asyncio.Event()
    task = asyncio.create_task(run("scheduler", h.kernel, h.adapter, stop))
    for _ in range(40):
        if (await query(h, "SELECT status FROM platform.messaging_jobs"))[0]["status"] == "READY":
            break
        await asyncio.sleep(0.025)
    stop.set()
    await asyncio.wait_for(task, 2)
    assert (await query(h, "SELECT status FROM platform.messaging_jobs"))[0]["status"] == "READY"
    await due(h)
    assert not await h.worker.run_once(stop)
    assert (await query(h, "SELECT attempt_count FROM platform.messaging_jobs"))[0][
        "attempt_count"
    ] == 1


@pytest.mark.parametrize("mode", ["constructor", "execution_options", "driver"])
async def test_worker_autocommit_rejected_before_admission_and_pool_recovers(messaging, mode):
    from sqlalchemy.ext.asyncio import create_async_engine

    h = messaging
    await ingest(h)
    claim = await h.kernel.claim_job("worker")
    options = (
        {"isolation_level": "AUTOCOMMIT"}
        if mode == "constructor"
        else {"connect_args": {"autocommit": True}}
        if mode == "driver"
        else {}
    )
    engine = create_async_engine(
        h.runtime.engine.url, pool_size=1, max_overflow=0, hide_parameters=True, **options
    )
    target = (
        engine.execution_options(isolation_level="AUTOCOMMIT")
        if mode == "execution_options"
        else engine
    )
    try:
        with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
            async with MessagingDatabase(target).admit_job(claim.job_id, claim.claim_token):
                pytest.fail("AUTOCOMMIT must never publish a unit")
        assert (await query(h, "SELECT status FROM platform.inbox_events"))[0][
            "status"
        ] == "PENDING"
        assert (await h.kernel.process_inbox(claim)).status == "PROCESSED"
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "setting,value",
    [
        ("asm.context_xid", "0"),
        ("asm.connection_id", str(CB)),
        ("asm.workspace_id", str(B)),
        ("asm.claim_token", str(UUID(int=0))),
        ("asm.actor_id", str(UA)),
    ],
)
async def test_raw_worker_context_forgery_fails_closed(messaging, setting, value):
    h = messaging
    await ingest(h)
    claim = await h.kernel.claim_job("worker")
    with pytest.raises(MessagingError):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            await unit._connection.execute(
                text("SELECT set_config(:key,:value,true)"), {"key": setting, "value": value}
            )
            await unit.process_inbox()
    assert (await query(h, "SELECT status FROM platform.inbox_events"))[0]["status"] == "PENDING"
    assert (await h.kernel.process_inbox(claim)).status == "PROCESSED"


@pytest.mark.parametrize("stage", ["ingest_before_commit", "ingest_after_commit"])
async def test_ingestion_commit_boundary_never_false_ack_or_duplicate(messaging, stage):
    h = messaging

    async def barrier(current):
        if current == stage:
            raise SQLAlchemyError("controlled lost acknowledgement")

    h.kernel._barrier = barrier
    with pytest.raises(SQLAlchemyError):
        await ingest(h)
    n = await counts(h)
    assert (
        n["platform.inbox_events"]
        == n["platform.messaging_jobs"]
        == (0 if stage == "ingest_before_commit" else 1)
    )
    h.kernel._barrier = None
    receipt = await ingest(h)
    assert receipt.code == ("ACCEPTED" if stage == "ingest_before_commit" else "DUPLICATE")
    assert (await counts(h))["platform.inbox_events"] == 1


async def test_finalize_not_sent_ack_loss_and_changed_claim_exact_replay(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    h.adapter.outcome = OutcomeKind.NOT_SENT_RETRYABLE
    lost = False

    async def barrier(stage):
        nonlocal lost
        if stage == "finalize_after_commit" and not lost:
            lost = True
            raise SQLAlchemyError("controlled ack loss")

    h.kernel._barrier = barrier
    assert await h.worker.run_once()
    assert (await delivery(h, receipt.message_id))["status"] == "PENDING"
    row = (
        await query(
            h,
            "SELECT id,last_claim_token,last_attempt_id FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT'",
        )
    )[0]
    result = await h.kernel.finish_send(
        row["id"],
        row["last_claim_token"],
        row["last_attempt_id"],
        SendOutcome(OutcomeKind.NOT_SENT_RETRYABLE, error_code=Code.DEPENDENCY_UNAVAILABLE),
    )
    assert result.code == "ALREADY_FINALIZED"
    await due(h)
    fresh = await h.kernel.claim_job("replacement")
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.finish_send(
            row["id"],
            row["last_claim_token"],
            row["last_attempt_id"],
            SendOutcome(OutcomeKind.NOT_SENT_RETRYABLE, error_code=Code.DEPENDENCY_UNAVAILABLE),
        )
    h.adapter.outcome = OutcomeKind.SUCCESS
    await h.worker.execute(fresh)
    assert (await delivery(h, receipt.message_id))["status"] == "SENT"
    assert ledger(h) == ["CALL", "CALL", "EFFECT"]


async def test_send_completion_after_owner_revoke_records_real_evidence(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    claim = await h.kernel.claim_job("worker")
    permit = await h.kernel.begin_send(claim)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws RETURNING workspace_id",
        ws=A,
    )
    await query(
        h, "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id", id=CA
    )
    outcome = await h.adapter.send(permit)
    result = await h.kernel.finish_send(claim.job_id, claim.claim_token, permit.attempt_id, outcome)
    assert result.status == "SENT"
    assert (
        await query(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id)
    )[0]["status"] == "SENT"


async def test_cancellation_after_effect_is_unknown_and_never_ready(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    entered = asyncio.Event()

    async def barrier(stage):
        if stage == "after_effect":
            entered.set()
            await asyncio.Event().wait()

    h.adapter.barrier = barrier
    task = asyncio.create_task(h.worker.run_once())
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await delivery(h, receipt.message_id))["status"] == "UNKNOWN"
    await expire(h)
    assert not await h.worker.run_once() and ledger(h) == ["CALL", "EFFECT"]


async def test_backlog_age_starts_at_first_claim_and_failed_safe_start_is_reclaimable(messaging):
    h = messaging
    cid = await conversation(h)
    receipt = await command(h, cid)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET created_at=clock_timestamp()-interval '1 day' WHERE kind='SEND_MANUAL_TEXT' RETURNING id",
    )
    claim = await h.kernel.claim_job("worker")
    assert claim.attempt_count == 1

    async def barrier(stage):
        if stage == "start_before_commit":
            raise SQLAlchemyError("controlled precommit failure")

    h.kernel._barrier = barrier
    with pytest.raises(SQLAlchemyError):
        await h.kernel.begin_send(claim)
    assert (await delivery(h, receipt.message_id))["status"] == "PENDING"
    assert ledger(h) == []
    h.kernel._barrier = None
    await expire(h)
    assert await h.worker.run_once()
    assert (await delivery(h, receipt.message_id))["status"] == "SENT"
