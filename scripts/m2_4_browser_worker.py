"""Finite CONTROLLED browser runner using real asm_runtime/PostgreSQL/private S3.

No migrator capability, HTTP test endpoint, arbitrary payload, host, or Workspace
argument. CALL/EFFECT files are private instrumentation, never a replacement queue.
"""

import asyncio
import json
import os
import stat
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from asm.files.config import StorageSettings
from asm.files.database import FileDatabase
from asm.files.provider import ControlledImageProvider
from asm.files.storage import S3ObjectStorage
from asm.files.transfer import FetchTransfer
from asm.foundation import DATABASE_SCHEMA_REVISION
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.models import EventKind, NormalizedEventV1, OutcomeKind
from asm.messaging.worker import Worker
from m2_4_browser_fixture import PRESETS, bot, route
from PIL import Image
from provision_local_auth import PrivateArgumentParser, ProvisioningError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ACTIONS = ("seed", "success", "unknown", "permanent", "recover", "stats")
COUNTER_DIRECTORY = Path("/run/m2-browser-counters")


def validate_operation(preset, operation):
    if operation not in ACTIONS or (
        preset is not None if operation == "seed" else preset not in PRESETS
    ):
        raise ProvisioningError("Invalid finite messaging runner action")


def target():
    url = make_url(os.environ.get("ASM_DATABASE_URL", ""))
    if (
        os.environ.get("ASM_ENVIRONMENT") != "TEST"
        or url.drivername != "postgresql+psycopg"
        or url.username != "asm_runtime"
        or url.database != "asm_test"
        or url.host != "postgres"
        or url.port != 5432
        or url.query
        or any(
            name in os.environ
            for name in (
                "ASM_MIGRATION_DATABASE_URL",
                "ASM_ADMIN_DATABASE_URL",
                "PG_ADMIN_PASSWORD",
                "PG_MIGRATION_PASSWORD",
            )
        )
    ):
        raise ProvisioningError("Disposable runtime-only browser TEST target required")
    storage = StorageSettings()
    if (
        storage.environment != "TEST"
        or storage.endpoint != "http://storage:9000"
        or storage.bucket != "asm-private-test"
    ):
        raise ProvisioningError("Disposable private browser TEST storage required")
    return url, storage


def ledger_path(preset):
    if preset not in PRESETS:
        raise ProvisioningError("Invalid finite counter preset")
    directory = os.open(COUNTER_DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ProvisioningError("Private current-owner TEST counter directory required")
        path = COUNTER_DIRECTORY / (preset + ".jsonl")
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or info.st_size > 65536
            ):
                raise ProvisioningError("Private bounded TEST counter file required")
        finally:
            os.close(descriptor)
        return path
    finally:
        os.close(directory)


def counters(preset):
    path = ledger_path(preset)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(65537)
    finally:
        os.close(descriptor)
    if len(content) > 65536:
        raise ProvisioningError("Bounded TEST counter file required")
    result = {"calls": 0, "effects": 0}
    for line in content.splitlines():
        value = json.loads(line)
        if value == {"event": "CALL"}:
            result["calls"] += 1
        elif value == {"event": "EFFECT"}:
            result["effects"] += 1
        else:
            raise ProvisioningError("Finite TEST instrumentation required")
    return result


async def guard(engine):
    async with engine.connect() as connection:
        identity = (await connection.execute(text("SELECT current_user,current_database()"))).one()
        if tuple(identity) != ("asm_runtime", "asm_test"):
            raise ProvisioningError("Unexpected runtime browser TEST identity")
        safe = (
            await connection.execute(
                text(
                    "SELECT NOT rolsuper AND NOT rolbypassrls "
                    "AND NOT has_schema_privilege(current_user,'app','CREATE') "
                    "AND NOT has_schema_privilege(current_user,'platform','CREATE') "
                    "FROM pg_roles WHERE rolname=current_user"
                )
            )
        ).scalar_one()
        revision = (
            await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
        ).scalar_one()
        if safe is not True or revision != DATABASE_SCHEMA_REVISION:
            raise ProvisioningError("Unsafe or unprepared runtime browser TEST target")


class FixtureAdapter(ControlledAdapter):
    """No extra retry/dedupe: reject a misrouted test before its adapter effect."""

    def __init__(self, preset, outcome, barrier):
        super().__init__(
            environment="TEST", ledger=ledger_path(preset), outcome=outcome, barrier=barrier
        )
        self.preset = preset
        self.mismatched = False

    async def send(self, permit):
        if permit.bot_identity != bot(self.preset):
            self.mismatched = True
            raise ProvisioningError("Concurrent browser outbound fixture not allowed")
        return await super().send(permit)


def event(preset, suffix, *, conversation="main", connection=0, image=None):
    return NormalizedEventV1(
        provider="CONTROLLED",
        bot_identity=bot(preset),
        event_id=f"m24-{preset}-{suffix}",
        kind=EventKind.CLIENT_MESSAGE,
        external_connection_id=route(preset, connection),
        chat_id=f"m24-{preset}-{conversation}",
        message_id=f"m24-{preset}-{suffix}",
        sender_id=f"m24-{preset}-{conversation}-client",
        occurred_at=datetime(2026, 1, 2, 3, 4, 5, 6, UTC),
        text=f"Incoming {preset} {suffix} — e\u0301 🎨" if image is None else None,
        image_file_id=f"m24-image-{image}" if image else None,
    )


def seed_events():
    # Deterministic finite fixtures; accepted Message/File rows still originate
    # exclusively from canonical runtime ingest/process/fetch capabilities.
    for preset in PRESETS:
        yield event(preset, "main")
        yield event(preset, "alternate", conversation="alternate")
        if preset == "pagination":
            for index in range(1, 27):
                yield event(
                    preset, f"conversation-{index}", conversation=f"page-{index}", connection=index
                )
            for index in range(1, 27):
                yield event(preset, f"history-{index}")
        yield event(preset, "ready-image", image="ready")
        if preset == "happy":
            yield event(preset, "failed-image", image="failed")
    # Leave one genuinely scheduled FETCH pending for the initial UI. A later
    # explicit Worker run can complete it without fixture-side state updates.
    yield event("happy", "pending-image", image="pending")


def controlled_images(provider):
    stream = BytesIO()
    Image.new("RGB", (23, 17), (21, 90, 153)).save(stream, format="PNG")
    for preset in PRESETS:
        for label in ("ready", "pending"):
            provider.register(bot(preset), f"m24-image-{label}", stream.getvalue())
    # No registered bytes for "failed": the actual FetchTransfer finalizes the
    # missing CONTROLLED reference as FAILED/INVALID_INPUT.


async def drain(worker):
    count = 0
    for _ in range(256):
        if not await worker.run_once():
            return count
        count += 1
    raise ProvisioningError("Bounded browser TEST jobs exceeded")


async def seed(kernel, worker, adapter):
    processed = 0
    for value in seed_events():
        receipt = await kernel.ingest_event(adapter.source(value.bot_identity), value, uuid4())
        if receipt.code != "ACCEPTED":
            raise ProvisioningError("Fresh browser TEST Inbox required")
        claim = await kernel.claim_job("m24-browser-seed")
        if claim is None or claim.kind != "PROCESS_INBOX" or claim.job_id != receipt.job_id:
            raise ProvisioningError("Exclusive browser seed queue required")
        await worker.execute(claim)
        processed += 1
        if value.image_file_id and value.image_file_id != "m24-image-pending":
            fetch = await kernel.claim_job("m24-browser-image")
            if fetch is None or fetch.kind != "FETCH_IMAGE":
                raise ProvisioningError("Canonical browser FETCH required")
            await worker.execute(fetch)
    return {"processed": processed}


async def action(preset, operation):
    validate_operation(preset, operation)
    url, settings = target()
    engine = create_async_engine(
        url, hide_parameters=True, pool_size=2, max_overflow=0, connect_args={"connect_timeout": 3}
    )
    storage = None
    transfer = None
    try:
        async with asyncio.timeout(120):
            await guard(engine)
            if operation == "stats":
                return counters(preset)

            async def no_transaction(_):
                if engine.pool.checkedout() != 0:
                    raise ProvisioningError("External browser TEST I/O holds a DB connection")

            kernel = MessagingDatabase(engine)
            outcome = {
                "unknown": OutcomeKind.UNKNOWN,
                "permanent": OutcomeKind.NOT_SENT_PERMANENT,
            }.get(operation, OutcomeKind.SUCCESS)
            adapter = (
                ControlledAdapter(environment="TEST", barrier=no_transaction)
                if operation == "seed"
                else FixtureAdapter(preset, outcome, no_transaction)
            )
            provider = ControlledImageProvider(environment="TEST", barrier=no_transaction)
            controlled_images(provider)
            storage = S3ObjectStorage(settings)
            original_io = storage._io

            async def storage_io(operation):
                await no_transaction("storage")
                return await original_io(operation)

            storage._io = storage_io
            transfer = FetchTransfer(FileDatabase(kernel), kernel, provider, storage)
            worker = Worker(kernel, adapter, files=transfer)
            if operation == "seed":
                for selected in PRESETS:
                    if counters(selected) != {"calls": 0, "effects": 0}:
                        raise ProvisioningError("Fresh browser TEST counters required")
                return await seed(kernel, worker, adapter)
            recovered = await kernel.recover_expired() if operation == "recover" else 0
            worked = await drain(worker)
            if adapter.mismatched:
                raise ProvisioningError("Concurrent browser outbound fixture not allowed")
            return {"worked": worked, "recovered": recovered, **counters(preset)}
    finally:
        if transfer is not None:
            await transfer.close()
        if storage is not None:
            await storage.close()
        await engine.dispose()


def main():
    try:
        parser = PrivateArgumentParser()
        parser.add_argument("--preset", choices=PRESETS)
        parser.add_argument("--action", required=True, choices=ACTIONS)
        args = parser.parse_args()
        print(json.dumps(asyncio.run(action(args.preset, args.action)), sort_keys=True))
        return 0
    except Exception:
        print("M2_4_BROWSER_WORKER_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
