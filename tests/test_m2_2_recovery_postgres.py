"""Real PostgreSQL/S3 fetch recovery, process death, and late-PUT cleanup."""

import asyncio
import os
import sys
import threading
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from asm.files.config import StorageSettings
from asm.files.database import FileDatabase
from asm.files.provider import ControlledImageProvider
from asm.files.storage import S3ObjectStorage
from asm.files.transfer import CleanupSweep, FetchTransfer
from asm.files.validation import decode_image
from asm.messaging.errors import Code, MessagingError
from asm.messaging.worker import Worker
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_models import event
from test_m2_1_postgres import due, expire, query, receive
from test_m2_1_postgres import messaging as messaging
from test_m2_2_media import image_bytes, webp_dimension_header
from test_tenancy_postgres import A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def files(messaging):
    h = messaging
    settings = StorageSettings()
    assert settings.environment == "TEST"
    h.original = image_bytes()
    h.storage = S3ObjectStorage(settings)
    h.provider = ControlledImageProvider(environment="TEST")
    h.provider.register("bot-a", "provider-ref", h.original)
    h.files = FileDatabase(h.kernel)
    h.fetch = FetchTransfer(h.files, h.kernel, h.provider, h.storage)
    h.sweep = CleanupSweep(h.files, h.storage)
    h.worker = Worker(h.kernel, h.adapter, files=h.fetch)
    try:
        yield h
    finally:
        # Test infrastructure owns precisely these persisted test intents. Never
        # list/delete a whole bucket or ask SQL migrations to perform object I/O.
        rows = await query(
            h,
            "SELECT storage_key FROM platform.file_object_uploads WHERE workspace_id IN (:a,:b)",
            a=A,
            b=B,
        )
        for row in rows:
            await h.storage._io(
                lambda key=row["storage_key"]: h.storage._client.delete_object(
                    Bucket=settings.bucket, Key=key
                )
            )
        await h.fetch.close()
        await h.storage.close()


async def plan_image(h):
    _, message = await receive(h, event(image_file_id="provider-ref"))
    return message


async def claim_image(h):
    claim = await h.kernel.claim_job("file-test")
    assert claim is not None and claim.kind == "FETCH_IMAGE"
    return claim


async def file_state(h):
    rows = await query(h, "SELECT * FROM app.file_objects")
    assert len(rows) == 1
    return rows[0]


async def uploads(h):
    return await query(h, "SELECT * FROM platform.file_object_uploads ORDER BY created_at,id")


async def make_cleanup_due(h):
    await query(
        h,
        "UPDATE platform.file_object_uploads SET next_check_at=clock_timestamp()-interval '1 second' WHERE status='ABANDONED' RETURNING id",
    )


async def test_fetch_roundtrip_no_provider_or_s3_io_with_held_transaction(files, monkeypatch):
    h = files
    await plan_image(h)
    stages = []

    async def checkpoint(stage):
        stages.append(stage)
        assert h.runtime.engine.pool.checkedout() == 0

    h.provider.barrier = checkpoint
    original_io = h.storage._io

    async def checked_io(operation):
        assert h.runtime.engine.pool.checkedout() == 0
        return await original_io(operation)

    monkeypatch.setattr(h.storage, "_io", checked_io)
    assert await h.worker.run_once()
    row = await file_state(h)
    assert row["status"] == "READY"
    assert await h.storage.get(row["storage_key"]) == h.original
    assert row["sha256"] == decode_image(h.original).sha256
    assert stages == ["image_before_open", "image_before_read", "image_after_read"]
    assert h.adapter.calls == 0


async def test_lost_finalize_ack_reads_winner_without_repeat_provider_or_put(files, monkeypatch):
    h = files
    await plan_image(h)
    failures = []
    put_calls = []
    real_put = h.storage.put

    async def counted_put(permit, content):
        put_calls.append(permit.intent_id)
        await real_put(permit, content)

    async def lost_ack(stage):
        if stage == "fetch_finalize_after_commit" and not failures:
            failures.append(True)
            raise SQLAlchemyError("controlled lost acknowledgement")

    monkeypatch.setattr(h.storage, "put", counted_put)
    h.kernel._barrier = lost_ack
    claim = await claim_image(h)
    await h.fetch.execute(claim)
    stored = (await uploads(h))[0]
    assert stored["status"] == "WINNER"
    assert h.provider.calls == 1 and put_calls == [stored["id"]]
    replay = await h.files.finish_fetch(claim.job_id, claim.claim_token, stored["id"])
    assert replay.code == "ALREADY_FINALIZED"
    assert await h.storage.get(stored["storage_key"]) == h.original
    assert not await h.worker.run_once()
    assert not await h.sweep.run_once()


async def test_lost_prepare_ack_never_authorizes_put_and_retries_new_key(files):
    h = files
    await plan_image(h)
    failed = False

    async def lost_ack(stage):
        nonlocal failed
        if stage == "prepare_after_commit" and not failed:
            failed = True
            raise SQLAlchemyError("controlled lost acknowledgement")

    h.kernel._barrier = lost_ack
    assert await h.worker.run_once()
    original = (await uploads(h))[0]
    assert original["status"] == "ABANDONED"
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await h.storage.head(original["storage_key"])
    await due(h)
    assert await h.worker.run_once()
    row = await file_state(h)
    assert row["status"] == "READY" and row["storage_key"] != original["storage_key"]
    assert len(await uploads(h)) == 2
    assert await h.storage.get(row["storage_key"]) == h.original


async def test_retry_exhaustion_keeps_message_and_sets_failed_file(files):
    h = files
    message = await plan_image(h)

    async def unavailable(stage):
        raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)

    h.provider.barrier = unavailable
    for attempt in range(1, 6):
        assert await h.worker.run_once()
        assert (await file_state(h))["status"] == ("PENDING" if attempt < 5 else "FAILED")
        job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"))[0]
        assert job["attempt_count"] == attempt
        if attempt < 5:
            delay = (job["available_at"] - datetime.now(UTC)).total_seconds()
            assert -1 <= delay <= min(60, 2 ** (attempt - 1))
        else:
            assert job["status"] == "DEAD" and job["error_code"] == "RETRY_EXHAUSTED"
        await due(h)
    assert h.provider.calls == 5
    assert not await h.worker.run_once()
    assert await uploads(h) == []
    assert (await query(h, "SELECT id,image_file_id FROM app.messages"))[0] == {
        "id": message.message_id,
        "image_file_id": "provider-ref",
    }


@pytest.mark.parametrize(
    "input_kind",
    ["missing", "malformed", "truncated", "animated", "oversized", "webp_pixels", "webp_canvas"],
)
async def test_invalid_input_is_terminal_before_storage(files, input_kind, monkeypatch):
    h = files
    await plan_image(h)

    async def forbidden_put(*args, **kwargs):
        raise AssertionError("Invalid input reached storage PUT")

    monkeypatch.setattr(h.storage, "put", forbidden_put)
    if input_kind == "missing":
        h.provider._images.clear()
    else:
        invalid = {
            "malformed": b"not an image",
            "truncated": h.original[:-8],
            "animated": image_bytes("WEBP", animated=True),
            "oversized": b"x" * (10 * 1024 * 1024 + 1),
            "webp_pixels": webp_dimension_header(5000, 4001),
            "webp_canvas": webp_dimension_header(1, 1, canvas=(8192, 8192)),
        }[input_kind]
        h.provider.register("bot-a", "provider-ref", invalid, content_length=1)
    assert await h.worker.run_once()
    row = await file_state(h)
    assert row["status"] == "FAILED" and row["error_code"] == "INVALID_INPUT"
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"))[0]
    assert job["status"] == "DEAD" and job["error_code"] == "INVALID_INPUT"
    assert job["attempt_count"] == 1 and h.adapter.calls == 0
    assert await uploads(h) == []
    assert not await h.worker.run_once()
    assert len(await query(h, "SELECT id FROM app.messages")) == 1


CHILD = r"""
import asyncio, os
from asm.foundation import Settings, RuntimeDatabase
from asm.messaging.database import MessagingDatabase
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.worker import Worker
from asm.files.config import StorageSettings
from asm.files.database import FileDatabase
from asm.files.provider import ControlledImageProvider
from asm.files.storage import S3ObjectStorage
from asm.files.transfer import FetchTransfer
async def main():
    async def barrier(stage):
        if stage == os.environ['M2_FILE_CRASH_STAGE']:
            os._exit(42)
    runtime = RuntimeDatabase(Settings())
    kernel = MessagingDatabase(runtime.engine, barrier=barrier)
    storage = S3ObjectStorage(StorageSettings())
    provider = ControlledImageProvider(environment='TEST')
    provider.register('bot-a', 'provider-ref', bytes.fromhex(os.environ['M2_TEST_IMAGE_HEX']))
    transfer = FetchTransfer(FileDatabase(kernel), kernel, provider, storage, barrier=barrier)
    try:
        await Worker(kernel, ControlledAdapter(environment='TEST'), files=transfer).run_once()
    finally:
        await transfer.close()
        await storage.close()
        await runtime.close()
asyncio.run(main())
"""


@pytest.mark.parametrize(
    "stage", ["prepare_after_commit", "fetch_after_put", "fetch_finalize_after_commit"]
)
async def test_actual_process_death_intent_put_ready_and_restart(files, stage):
    h = files
    await plan_image(h)
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        CHILD,
        env={**os.environ, "M2_FILE_CRASH_STAGE": stage, "M2_TEST_IMAGE_HEX": h.original.hex()},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(child.communicate(), timeout=20)
    assert child.returncode == 42, (out.decode(), err.decode())
    before = (await uploads(h))[0]
    if stage == "prepare_after_commit":
        with pytest.raises(MessagingError, match="NOT_FOUND"):
            await h.storage.head(before["storage_key"])
    else:
        assert await h.storage.get(before["storage_key"]) == h.original
    await expire(h)
    worked = await h.worker.run_once()
    assert worked == (stage != "fetch_finalize_after_commit")
    row = await file_state(h)
    assert row["status"] == "READY"
    assert await h.storage.get(row["storage_key"]) == h.original
    stored = await uploads(h)
    assert len(stored) == (1 if stage == "fetch_finalize_after_commit" else 2)
    assert h.provider.calls == (0 if stage == "fetch_finalize_after_commit" else 1)
    if stage != "fetch_finalize_after_commit":
        assert row["storage_key"] != before["storage_key"]
        assert await h.sweep.run_once()
        with pytest.raises(MessagingError, match="NOT_FOUND"):
            await h.storage.head(before["storage_key"])
    assert await h.storage.get(row["storage_key"]) == h.original


@pytest.mark.parametrize("after_new_ready", [False, True])
async def test_late_put_after_first_delete_remains_durably_cleanable(files, after_new_ready):
    h = files
    await plan_image(h)
    old = await claim_image(h)
    permit = await h.files.prepare_upload(old, decode_image(h.original))
    await expire(h)
    assert await h.sweep.run_once()  # DELETE before the old in-flight PUT arrives.
    tombstone = (await uploads(h))[0]
    assert tombstone["status"] == "ABANDONED" and tombstone["cleanup_outcome"] == "DELETED"
    assert 3595 < (tombstone["next_check_at"] - datetime.now(UTC)).total_seconds() <= 3600
    if after_new_ready:
        assert await h.worker.run_once()
    # A real late S3 PUT, representing a timed-out sync SDK request. The obsolete
    # permit cannot finalize but its durable, distinct object key still exists.
    await h.storage.put(permit, h.original)
    assert await h.storage.get(permit.storage_key) == h.original
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.files.finish_fetch(old.job_id, old.claim_token, permit.intent_id)
    if not after_new_ready:
        assert await h.worker.run_once()
    winner = await file_state(h)
    assert winner["storage_key"] != permit.storage_key
    assert not await h.sweep.run_once()  # Tombstone deliberately waits one hour.
    await make_cleanup_due(h)
    assert await h.sweep.run_once()
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await h.storage.head(permit.storage_key)
    assert await h.storage.get(winner["storage_key"]) == h.original
    assert len(await uploads(h)) == 2  # Success retains ABANDONED intent.
    assert not await h.files.claim_cleanup()


async def test_cancelled_worker_sync_put_arrives_after_cleanup_and_new_ready(files, monkeypatch):
    h = files
    await plan_image(h)
    started, release, completed = threading.Event(), threading.Event(), threading.Event()
    real_put = h.storage._client.put_object
    intercepted = False

    def delayed_put(**kwargs):
        nonlocal intercepted
        if not intercepted:
            intercepted = True
            started.set()
            assert release.wait(timeout=10)
            try:
                return real_put(**kwargs)
            finally:
                completed.set()
        return real_put(**kwargs)

    monkeypatch.setattr(h.storage._client, "put_object", delayed_put)
    worker = asyncio.create_task(h.worker.run_once())
    try:
        assert await asyncio.to_thread(started.wait, 5)
        worker.cancel()  # Await cancellation does not stop the synchronous PUT.
        with pytest.raises(asyncio.CancelledError):
            await worker
        old = (await uploads(h))[0]
        assert old["status"] == "ABANDONED"
        assert await h.sweep.run_once()
        assert not completed.is_set()
        replacement = image_bytes(size=(9, 3))
        h.provider.register("bot-a", "provider-ref", replacement)
        await due(h)
        assert await h.worker.run_once()
        winner = await file_state(h)
        assert winner["storage_key"] != old["storage_key"]
        assert winner["sha256"] == decode_image(replacement).sha256
        release.set()
        assert await asyncio.to_thread(completed.wait, 5)
        assert await h.storage.get(old["storage_key"]) == h.original
        assert await h.storage.get(winner["storage_key"]) == replacement
        await make_cleanup_due(h)
        assert await h.sweep.run_once()
        with pytest.raises(MessagingError, match="NOT_FOUND"):
            await h.storage.head(old["storage_key"])
        assert await h.storage.get(winner["storage_key"]) == replacement
        assert (await file_state(h))["winner_intent_id"] == winner["winner_intent_id"]
    finally:
        release.set()
        await asyncio.gather(worker, return_exceptions=True)


async def test_cleanup_outage_reclaim_stale_token_and_winner_safety(files, monkeypatch):
    h = files
    await plan_image(h)
    old = await claim_image(h)
    permit = await h.files.prepare_upload(old, decode_image(h.original))
    await h.storage.put(permit, h.original)
    await expire(h)
    assert await h.worker.run_once()
    winner = await file_state(h)
    real_delete = h.storage._client.delete_object

    def service_outage(**kwargs):
        # Keep the real private S3 endpoint/transport but address a nonexistent
        # bucket; the S3 error must not be recorded as confirmed removal.
        return real_delete(**{**kwargs, "Bucket": "m2-nonexistent-bucket"})

    with monkeypatch.context() as fault:
        fault.setattr(h.storage._client, "delete_object", service_outage)
        assert await h.sweep.run_once()
    abandoned = [u for u in await uploads(h) if u["status"] == "ABANDONED"][0]
    assert abandoned["cleanup_outcome"] == "DEPENDENCY_UNAVAILABLE"
    assert 0 < (abandoned["next_check_at"] - datetime.now(UTC)).total_seconds() <= 3600
    assert await h.storage.get(permit.storage_key) == h.original
    await make_cleanup_due(h)
    first = (await h.files.claim_cleanup())[0]
    assert not await h.files.claim_cleanup()
    await query(
        h,
        "UPDATE platform.file_object_uploads SET cleanup_lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=first.intent_id,
    )
    second = (await h.files.claim_cleanup())[0]
    assert second.intent_id == first.intent_id and second.claim_token != first.claim_token
    with pytest.raises(MessagingError, match="STALE_CLAIM"):
        await h.files.finish_cleanup(first.intent_id, first.claim_token)
    await h.storage.delete(second)
    await h.files.finish_cleanup(second.intent_id, second.claim_token)
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await h.storage.head(permit.storage_key)
    assert await h.storage.get(winner["storage_key"]) == h.original
    await make_cleanup_due(h)
    claimed = await h.files.claim_cleanup()
    assert len(claimed) == 1 and claimed[0].intent_id == permit.intent_id
    assert claimed[0].intent_id != winner["winner_intent_id"]
