"""Real PostgreSQL evidence for atomic file planning and narrow file capabilities."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from asm.files.database import FileDatabase
from asm.files.models import ImageManifest
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.tenancy import AuthenticatedAccount, TenancyError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_models import event
from test_m2_1_postgres import CA, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_tenancy_postgres import PROVIDER, UA, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
MANIFEST = ImageManifest(mime_type="image/png", size_bytes=67, sha256="a" * 64, width=1, height=1)


async def image(h, **changes):
    receipt = await ingest(h, event(**{"image_file_id": "opaque-image", **changes}))
    # In tests creating multiple images, keep old FETCH jobs behind this event.
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()+interval '1 minute' WHERE kind='FETCH_IMAGE' AND status='READY' RETURNING id",
    )
    claim = await h.kernel.claim_job("file-process")
    assert claim is not None and claim.job_id == receipt.job_id
    result = await h.kernel.process_inbox(claim)
    row = (
        await query(
            h,
            "SELECT id,message_id,conversation_id FROM app.file_objects WHERE message_id=:message",
            message=result.message_id,
        )
    )[0]
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE file_id=:file RETURNING id",
        file=row["id"],
    )
    return row


async def file_claim(h):
    claim = await h.kernel.claim_job("file-test")
    assert claim is not None and claim.kind == "FETCH_IMAGE"
    return claim


async def ready(h, **changes):
    row = await image(h, **changes)
    claim = await file_claim(h)
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(claim, MANIFEST)
    result = await files.finish_fetch(claim.job_id, claim.claim_token, permit.intent_id)
    assert result.status == "READY"
    return row, claim, permit


async def read(h, row, actor=UA, workspace=A, **overrides):
    values = {
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "file_id": row["id"],
        **overrides,
    }
    async with h.runtime.tenancy.transaction(
        AuthenticatedAccount(actor), workspace, uuid4()
    ) as unit:
        return await unit.file_read_manifest(**values)


async def test_file_physical_rls_and_capability_privileges(messaging):
    h = messaging
    for relation in ("app.file_objects", "platform.file_object_uploads"):
        row = (
            await query(
                h,
                "SELECT r.rolname,c.relrowsecurity,c.relforcerowsecurity,"
                "has_table_privilege('asm_runtime',c.oid,'SELECT') AS readable,"
                "has_table_privilege('asm_runtime',c.oid,'INSERT') AS writable "
                "FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner WHERE c.oid=CAST(:relation AS regclass)",
                relation=relation,
            )
        )[0]
        assert row == {
            "rolname": "asm_migrator",
            "relrowsecurity": True,
            "relforcerowsecurity": True,
            "readable": relation == "app.file_objects",
            "writable": False,
        }
    async with h.runtime.engine.begin() as connection:
        assert (
            await connection.execute(text("SELECT count(*) FROM app.file_objects"))
        ).scalar() == 0
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(text("SELECT * FROM platform.file_object_uploads"))
        assert caught.value.orig.sqlstate == "42501"
        for signature in (
            "platform.files_plan(uuid,uuid,uuid)",
            "platform.files_upload_json(platform.file_object_uploads)",
        ):
            assert not (
                await connection.execute(
                    text("SELECT has_function_privilege(current_user,:signature,'EXECUTE')"),
                    {"signature": signature},
                )
            ).scalar_one()


async def test_image_planning_rollback_is_one_transaction(messaging):
    h = messaging
    receipt = await ingest(h, event(image_file_id="rollback-image"))
    claim = await h.kernel.claim_job("rollback-test")
    assert claim is not None

    async def stop(name):
        if name == "process_before_commit":
            raise RuntimeError("injected commit rollback")

    broken = MessagingDatabase(h.runtime.engine, barrier=stop)
    with pytest.raises(RuntimeError, match="injected commit rollback"):
        await broken.process_inbox(claim)
    assert not await query(h, "SELECT id FROM app.messages")
    assert not await query(h, "SELECT id FROM app.file_objects")
    assert not await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")
    assert (
        await query(h, "SELECT status FROM platform.inbox_events WHERE id=:id", id=receipt.inbox_id)
    ) == [{"status": "PENDING"}]
    await h.kernel.process_inbox(claim)
    assert len(await query(h, "SELECT id FROM app.messages")) == 1
    assert len(await query(h, "SELECT id FROM app.file_objects")) == 1
    assert (
        len(await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")) == 1
    )


async def test_concurrent_image_projection_dedupe_retains_bytes_and_fingerprint(messaging):
    h = messaging
    values = [
        event(event_id=f"img-{n}", text=" caption é\n ", image_file_id="original-ref")
        for n in range(6)
    ]
    receipts = await asyncio.gather(*(ingest(h, value) for value in values))
    claims = [await h.kernel.claim_job(f"plan-{n}") for n in range(6)]
    assert all(claim is not None and claim.kind == "PROCESS_INBOX" for claim in claims)
    results = await asyncio.gather(*(h.kernel.process_inbox(claim) for claim in claims))
    assert len({result.message_id for result in results}) == 1
    assert sum(result.code == "PROCESSED" for result in results) == 1
    assert len(await query(h, "SELECT id FROM app.file_objects")) == 1
    jobs = await query(
        h, "SELECT file_id,correlation_id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"
    )
    assert len(jobs) == 1
    original = await query(
        h,
        "SELECT id,text,image_file_id,encode(projection_fingerprint,'hex') AS fingerprint FROM app.messages",
    )
    assert original[0]["text"] == values[0].text
    assert original[0]["image_file_id"] == "original-ref"
    assert (
        original[0]["fingerprint"]
        == hashlib.sha256(values[0].fingerprint_bytes(projection=True)).hexdigest()
    )
    repeated = await asyncio.gather(*(ingest(h, values[0]) for _ in range(4)))
    assert all(value.inbox_id == receipts[0].inbox_id for value in repeated)
    assert (
        await query(
            h,
            "SELECT id,text,image_file_id,encode(projection_fingerprint,'hex') AS fingerprint FROM app.messages",
        )
        == original
    )


async def test_source_is_canonical_despite_forged_claim_fields_and_disconnect(messaging):
    h = messaging
    row = await image(h, image_file_id="https://never-fetch-this.invalid/token")
    claim = await file_claim(h)
    forged = claim.model_copy(
        update={
            "workspace_id": B,
            "connection_id": uuid4(),
            "file_id": uuid4(),
            "kind": "SEND_MANUAL_TEXT",
        }
    )
    await query(
        h, "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id", id=CA
    )
    permit = await FileDatabase(h.kernel).begin_fetch(forged)
    assert permit.workspace_id == A and permit.connection_id == CA and permit.file_id == row["id"]
    assert permit.image_file_id == "https://never-fetch-this.invalid/token"
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await FileDatabase(h.kernel).begin_fetch(claim.model_copy(update={"claim_token": uuid4()}))


async def test_prepare_intent_replay_manifest_binding_and_fenced_finalize_ack(messaging):
    h = messaging
    row = await image(h)
    claim = await file_claim(h)
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(claim, MANIFEST)
    assert await files.prepare_upload(claim, MANIFEST) == permit
    assert permit.storage_key == f"workspaces/{A}/files/{row['id']}/attempts/{permit.intent_id}"
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        await files.prepare_upload(claim, MANIFEST.model_copy(update={"sha256": "b" * 64}))
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await files.finish_fetch(claim.job_id, uuid4(), permit.intent_id)
    final = await files.finish_fetch(claim.job_id, claim.claim_token, permit.intent_id)
    replay = await files.finish_fetch(claim.job_id, claim.claim_token, permit.intent_id)
    assert final.code == "FINALIZED" and replay.code == "ALREADY_FINALIZED"
    assert final.model_copy(update={"code": "ALREADY_FINALIZED"}) == replay
    assert (await read(h, row)).manifest == MANIFEST
    assert await files.claim_cleanup() == ()
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.kernel.retry(claim, Code.DEPENDENCY_TIMEOUT)
    assert (await read(h, row)).storage_key == permit.storage_key


@pytest.mark.parametrize("mutation", ["null", "extra", "size", "pixels", "float", "hash", "mime"])
async def test_raw_manifest_validation_cannot_be_bypassed(messaging, mutation):
    h = messaging
    await image(h)
    claim = await file_claim(h)
    manifest = MANIFEST.model_dump()
    changes = {
        "null": {"sha256": None},
        "extra": {"url": "https://invalid"},
        "size": {"size_bytes": 10485761},
        "pixels": {"width": 8192, "height": 8192},
        "float": {"size_bytes": 1.5},
        "hash": {"sha256": "wrong"},
        "mime": {"mime_type": "image/gif"},
    }
    manifest.update(changes[mutation])
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            await unit._execute(
                "SELECT platform.files_prepare_upload(:job,:token,CAST(:manifest AS jsonb))",
                {"manifest": json.dumps(manifest)},
            )
    assert not await query(h, "SELECT id FROM platform.file_object_uploads")


async def test_retry_new_key_stale_finalize_and_durable_cleanup_reclaim(messaging):
    h = messaging
    row = await image(h)
    files = FileDatabase(h.kernel)
    old = await file_claim(h)
    abandoned = await files.prepare_upload(old, MANIFEST)
    await h.kernel.retry(old, Code.DEPENDENCY_TIMEOUT)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE kind='FETCH_IMAGE' AND status='READY' RETURNING id",
    )
    new = await file_claim(h)
    winner = await files.prepare_upload(new, MANIFEST)
    assert winner.storage_key != abandoned.storage_key
    await files.finish_fetch(new.job_id, new.claim_token, winner.intent_id)
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await files.finish_fetch(old.job_id, old.claim_token, abandoned.intent_id)
    cleanup = await files.claim_cleanup()
    assert len(cleanup) == 1 and cleanup[0].intent_id == abandoned.intent_id
    assert await files.claim_cleanup() == ()
    await query(
        h,
        "UPDATE platform.file_object_uploads SET cleanup_lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=abandoned.intent_id,
    )
    reclaim = (await files.claim_cleanup())[0]
    assert reclaim.claim_token != cleanup[0].claim_token
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await files.finish_cleanup(abandoned.intent_id, cleanup[0].claim_token)
    failure = await files.finish_cleanup(
        abandoned.intent_id, reclaim.claim_token, Code.DEPENDENCY_UNAVAILABLE
    )
    assert failure.code == "RETRY_SCHEDULED"
    assert datetime.now(UTC) < failure.next_check_at <= datetime.now(UTC) + timedelta(hours=1)
    await query(
        h,
        "UPDATE platform.file_object_uploads SET next_check_at=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=abandoned.intent_id,
    )
    again = (await files.claim_cleanup())[0]
    success = await files.finish_cleanup(again.intent_id, again.claim_token)
    assert timedelta(minutes=59) < success.next_check_at - datetime.now(UTC) <= timedelta(hours=1)
    assert (
        await query(
            h,
            "SELECT status,cleanup_outcome FROM platform.file_object_uploads WHERE id=:id",
            id=abandoned.intent_id,
        )
    ) == [{"status": "ABANDONED", "cleanup_outcome": "DELETED"}]
    assert (await read(h, row)).storage_key == winner.storage_key


@pytest.mark.parametrize("failed", [False, True])
async def test_pending_failed_never_get_manifest(messaging, failed):
    h = messaging
    row = await image(h)
    if failed:
        await h.kernel.retry(await file_claim(h), Code.INVALID_INPUT, retryable=False)
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await read(h, row)


async def test_exact_owner_relation_live_role_revoke_and_disconnect(messaging):
    h = messaging
    row, _, permit = await ready(h)
    other, _, _ = await ready(
        h, event_id="other", message_id="other", chat_id="other", sender_id="other"
    )
    assert (await read(h, row)).storage_key == permit.storage_key
    # Same Workspace OWNER can read both conversations, but cannot cross their refs.
    assert (await read(h, other)).file_id == other["id"]
    for overrides in (
        {"conversation_id": other["conversation_id"]},
        {"message_id": other["message_id"]},
        {"file_id": other["id"]},
    ):
        with pytest.raises(MessagingError, match="NOT_FOUND"):
            await read(h, row, **overrides)
    for actor, workspace in ((PROVIDER, A), (UB, B)):
        with pytest.raises((MessagingError, TenancyError), match="ACCESS_DENIED"):
            await read(h, row, actor=actor, workspace=workspace)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        ws=B,
        actor=UB,
    )
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await read(h, row, actor=UB, workspace=B)
    await query(
        h, "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING id", id=CA
    )
    assert (await read(h, row)).file_id == row["id"]
    downgrade_started = asyncio.get_running_loop().create_future()

    async def downgrade_owner():
        async with h.migrator.begin() as connection:
            await connection.execute(text("SET LOCAL lock_timeout='5s'"))
            downgrade_started.set_result(
                (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            )
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='ADMIN' "
                    "WHERE workspace_id=:ws AND user_account_id=:actor"
                ),
                {"ws": A, "actor": UA},
            )

    downgrade = None
    try:
        async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            owner_pid = (
                await unit._connection.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()
            downgrade = asyncio.create_task(downgrade_owner())
            downgrade_pid = await asyncio.wait_for(downgrade_started, 2)
            # Frozen tenant admission holds FOR SHARE. Observe the real blocker,
            # instead of awaiting an UPDATE that needs this same unit to commit.
            async with asyncio.timeout(2):
                while not (
                    await query(
                        h,
                        "SELECT :owner=ANY(pg_blocking_pids(:downgrade)) AS blocked",
                        owner=owner_pid,
                        downgrade=downgrade_pid,
                    )
                )[0]["blocked"]:
                    if downgrade.done():
                        await downgrade
                        raise AssertionError("Role change completed before admitted owner commit")
                    await asyncio.sleep(0.01)
            assert not downgrade.done()
            admitted = await unit.file_read_manifest(
                row["conversation_id"], row["message_id"], row["id"]
            )
            assert admitted.storage_key == permit.storage_key
        await asyncio.wait_for(downgrade, 5)
    finally:
        if downgrade is not None:
            if not downgrade.done():
                downgrade.cancel()
            await asyncio.gather(downgrade, return_exceptions=True)
    # The already admitted transaction is serialized before the role change.
    # Every fresh grant resolves the now-committed role and rejects ADMIN.
    with pytest.raises(MessagingError, match="ACCESS_DENIED"):
        await read(h, row)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='OWNER',status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        ws=A,
        actor=UA,
    )
    with pytest.raises(TenancyError, match="ACCESS_DENIED"):
        await read(h, row)


async def test_file_guards_reject_cross_task_and_owner_worker_nesting(messaging):
    h = messaging
    row = await image(h)
    claim = await file_claim(h)
    files = FileDatabase(h.kernel)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        with pytest.raises((MessagingError, TenancyError), match="TRANSACTION_STATE"):
            await asyncio.create_task(
                unit.file_read_manifest(row["conversation_id"], row["message_id"], row["id"])
            )
        with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
            await files.begin_fetch(claim)
    with pytest.raises((MessagingError, TenancyError), match="TRANSACTION_STATE"):
        await unit.file_read_manifest(row["conversation_id"], row["message_id"], row["id"])
    with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as worker:
            await asyncio.create_task(
                worker._execute("SELECT platform.files_begin_fetch(:job,:token)")
            )


async def test_terminal_key_manifest_and_abandoned_winner_are_immutable(messaging):
    h = messaging
    row, claim, permit = await ready(h)
    for sql in (
        "UPDATE app.file_objects SET storage_key='forged' WHERE id=:file",
        "UPDATE app.file_objects SET sha256=repeat('b',64) WHERE id=:file",
        "UPDATE platform.file_object_uploads SET status='ABANDONED' WHERE id=:intent",
        "UPDATE platform.file_object_uploads SET storage_key='forged' WHERE id=:intent",
        "UPDATE platform.file_object_uploads SET sha256=repeat('b',64) WHERE id=:intent",
    ):
        with pytest.raises(DBAPIError) as caught:
            await query(h, sql + " RETURNING id", file=row["id"], intent=permit.intent_id)
        assert caught.value.orig.sqlstate == "23514"
    assert (
        await FileDatabase(h.kernel).finish_fetch(claim.job_id, claim.claim_token, permit.intent_id)
    ).code == "ALREADY_FINALIZED"


async def test_typed_message_job_file_foreign_keys_reject_forged_relations(messaging):
    h = messaging
    first = await image(h)
    second = await image(h, event_id="other", message_id="other", chat_id="other")
    async with h.migrator.begin() as connection:
        values = {
            "ws": A,
            "other": B,
            "file": first["id"],
            "message": first["message_id"],
            "conv": first["conversation_id"],
            "other_message": second["message_id"],
            "other_conv": second["conversation_id"],
            "conn": CA,
        }
        # Individually existing IDs do not authorize a false relationship.
        for statement in (
            "INSERT INTO app.file_objects(workspace_id,message_id,connection_id,conversation_id) VALUES(:other,:message,:conn,:conv)",
            "INSERT INTO app.file_objects(workspace_id,message_id,connection_id,conversation_id) VALUES(:ws,:message,:conn,:other_conv)",
            "INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,file_id,correlation_id) VALUES(:other,:conn,'FETCH_IMAGE',:file,gen_random_uuid())",
        ):
            with pytest.raises(DBAPIError) as caught:
                async with connection.begin_nested():
                    await connection.execute(text(statement), values)
            # A duplicate Message may be rejected even earlier by its UNIQUE key.
            assert caught.value.orig.sqlstate in {"23503", "23505"}
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(
                    text(
                        "INSERT INTO platform.messaging_jobs(workspace_id,connection_id,kind,file_id,correlation_id) VALUES(:ws,:conn,'PROCESS_INBOX',:file,gen_random_uuid())"
                    ),
                    values,
                )
        assert caught.value.orig.sqlstate == "23514"


async def test_file_fetch_transaction_xid_and_claim_lease_guards(messaging):
    h = messaging
    await image(h)
    claim = await file_claim(h)
    with pytest.raises(MessagingError, match="TRANSACTION_STATE"):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            await unit._connection.execute(text("SELECT set_config('asm.context_xid','0',true)"))
            await unit._execute("SELECT platform.files_begin_fetch(:job,:token)")
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await FileDatabase(h.kernel).prepare_upload(claim, MANIFEST)
    assert not await query(h, "SELECT id FROM platform.file_object_uploads")


async def test_fetch_bounded_retry_exhaustion_marks_file_and_abandons_every_intent(messaging):
    h = messaging
    row = await image(h)
    files = FileDatabase(h.kernel)
    keys = set()
    for attempt in range(1, 6):
        claim = await file_claim(h)
        assert claim.attempt_count == attempt
        keys.add((await files.prepare_upload(claim, MANIFEST)).storage_key)
        result = await h.kernel.retry(claim, Code.DEPENDENCY_UNAVAILABLE)
        assert result["code"] == ("RETRY_SCHEDULED" if attempt < 5 else "RETRY_EXHAUSTED")
        await query(
            h,
            "UPDATE platform.messaging_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE kind='FETCH_IMAGE' AND status='READY' RETURNING id",
        )
    assert len(keys) == 5
    assert await h.kernel.claim_job("exhausted") is None
    assert (
        await query(h, "SELECT status,error_code FROM app.file_objects WHERE id=:id", id=row["id"])
    ) == [{"status": "FAILED", "error_code": "RETRY_EXHAUSTED"}]
    intents = await query(h, "SELECT status FROM platform.file_object_uploads")
    assert len(intents) == 5 and all(row["status"] == "ABANDONED" for row in intents)
