"""Finite CONTROLLED browser runner using real asm_runtime/PostgreSQL/private S3.

No migrator capability, HTTP test endpoint, arbitrary payload, host, or Workspace
argument. CALL/EFFECT files are private instrumentation, never a replacement queue.
"""

import asyncio
import json
import os
import stat
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from asm.ai.contracts import DTO, KnowledgeGatewayConfig, Limits, Route, strict_json
from asm.ai.database import AIDatabase
from asm.ai.fake import FakeAdapter
from asm.ai.knowledge import KnowledgeView, project_knowledge
from asm.ai.runtime import SyntheticRuntime
from asm.ai.runtime_contracts import KnowledgeRuntimeReceipt, PreparedKnowledgeRun
from asm.conversations.escalations import MARKER
from asm.conversations.guards import parse_guarded_snapshot
from asm.conversations.turns import parse_snapshot
from asm.files.config import StorageSettings
from asm.files.database import FileDatabase
from asm.files.models import FetchPermit
from asm.files.provider import ChannelImageProvider, ControlledImageProvider
from asm.files.storage import S3ObjectStorage
from asm.files.transfer import FetchTransfer
from asm.foundation import DATABASE_SCHEMA_REVISION
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import MessagingError
from asm.messaging.models import EventKind, NormalizedEventV1, OutcomeKind
from asm.messaging.results import AIJobClaim, FinalizeResult, ScanStep
from asm.messaging.worker import Worker
from asm.telegram.database import TelegramIngress
from m2_4_browser_fixture import (
    ESCALATION_PRESETS,
    MATERIAL_PHOTOS,
    NATIVE_PRESETS,
    PRESETS,
    bot,
    route,
)
from PIL import Image
from provision_local_auth import PrivateArgumentParser, ProvisioningError
from pydantic import Field
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

MATERIAL_ACTIONS = ("material-edit", "material-delete") + tuple(
    f"material-{label}-{step}" for label in MATERIAL_PHOTOS for step in ("caption", "change")
)
ACTIONS = (
    "seed",
    *MATERIAL_ACTIONS,
    "success",
    "unknown",
    "permanent",
    "recover",
    "stats",
    "escalate-main",
    "escalate-alternate",
    "knowledge-answer",
)
COUNTER_DIRECTORY = Path("/run/m2-browser-counters")


@dataclass
class BrowserDiagnostic:
    stage: str = "ARGS"
    ready: bool = False
    model_calls: int = 0
    mismatched: bool = False
    primary: tuple[str, str, str] | None = None
    cleanup: str = "NONE"


_diagnostic = BrowserDiagnostic()
DIAGNOSTIC_STAGES = frozenset(
    {
        "ARGS",
        "TARGET",
        "GUARD",
        "SEED",
        "INGEST",
        "CLAIM_AI",
        "CLAIM_WORK",
        "EXECUTE_INBOX",
        "EXECUTE_TURN",
        "EXECUTE_AI",
        "EXECUTE_SEND",
        "MODEL",
        "REPLAY",
        "JOURNAL",
        "DRAIN",
        "CLEANUP",
    }
)


def diagnostic_failure(error, stage):
    kind = (
        "MESSAGING"
        if isinstance(error, MessagingError)
        else "DATABASE"
        if isinstance(error, SQLAlchemyError)
        else "TIMEOUT"
        if isinstance(error, TimeoutError)
        else "INPUT"
        if isinstance(error, ValueError)
        else "IO"
        if isinstance(error, OSError)
        else "OTHER"
    )
    code = "NONE"
    if isinstance(error, MessagingError):
        code = error.code.value
        if code not in {
            "NOT_ALLOWED",
            "STALE_CLAIM",
            "AI_STALE",
            "ACCESS_DENIED",
            "INVALID_INPUT",
            "IDEMPOTENCY_KEY_CONFLICT",
        }:
            code = "OTHER"
    return stage if stage in DIAGNOSTIC_STAGES else "ARGS", kind, code


def diagnostic_line(error, preset):
    """One closed record; never stringify exceptions, payloads, IDs or child output."""
    stage, kind, code = _diagnostic.primary or diagnostic_failure(error, _diagnostic.stage)
    counted = {"calls": "UNKNOWN", "effects": "UNKNOWN"}
    if _diagnostic.ready and preset in PRESETS:
        try:
            values = counters(preset)
            for name in counted:
                if type(values[name]) is int and 0 <= values[name] <= 4096:
                    counted[name] = str(values[name])
        except Exception:
            pass  # Diagnostics never grant file/DB/effect authority or replace a failure.
    model_calls = (
        str(_diagnostic.model_calls)
        if type(_diagnostic.model_calls) is int and 0 <= _diagnostic.model_calls <= 2
        else "UNKNOWN"
    )
    return (
        f"M2_4_BROWSER_DIAGNOSTIC:stage={stage};class={kind};code={code};"
        f"cleanup={_diagnostic.cleanup};calls={counted['calls']};effects={counted['effects']};"
        f"model_calls={model_calls};mismatch={int(_diagnostic.mismatched)}"
    )


def validate_operation(preset, operation):
    if operation not in ACTIONS or (
        preset is not None if operation == "seed" else preset not in PRESETS
    ):
        raise ProvisioningError("Invalid finite messaging runner action")
    if (operation.startswith("material-") and preset != "material") or (
        preset == "material" and operation not in {*MATERIAL_ACTIONS, "stats"}
    ):
        raise ProvisioningError("Finite material browser action required")
    if operation.startswith("escalate-") and (
        preset not in ESCALATION_PRESETS
        or operation == "escalate-alternate"
        and preset not in ("esc_happy", "esc_narrow")
    ):
        raise ProvisioningError("Invalid finite Escalation runner action")
    if (operation == "knowledge-answer" and preset != "knowledge") or (
        preset == "knowledge" and operation not in {"knowledge-answer", "stats"}
    ):
        raise ProvisioningError("Finite knowledge browser action required")


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
        _diagnostic.stage = "EXECUTE_SEND"
        if permit.bot_identity != bot(self.preset):
            self.mismatched = True
            _diagnostic.mismatched = True
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
        if preset == "material":
            continue
        yield event(preset, "main")
        yield event(preset, "alternate", conversation="alternate")
        if preset == "pagination":
            for index in range(1, 27):
                yield event(
                    preset, f"conversation-{index}", conversation=f"page-{index}", connection=index
                )
            # main +24 history +ready image still crosses the real limit25;
            # leave room for two text-only knowledge fixtures under the old cap.
            for index in range(1, 25):
                yield event(preset, f"history-{index}")
        if preset not in ESCALATION_PRESETS + NATIVE_PRESETS + ("knowledge",):
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
        if preset == "knowledge":
            continue
        for label in ("ready", "pending"):
            provider.register(bot(preset), f"m24-image-{label}", stream.getvalue())
    # No registered bytes for "failed": the actual FetchTransfer finalizes the
    # missing CONTROLLED reference as FAILED/INVALID_INPUT.
    return stream.getvalue()


class MaterialFixtureImageProvider:
    """Finite TEST bytes for genuine TELEGRAM permits; no provider substitution.

    FetchTransfer still validates bytes, uploads to disposable private S3 and
    commits the real File/WINNER. No Telegram network client is constructed.
    """

    def __init__(self, content, barrier):
        self.content, self.barrier = content, barrier

    async def open_image(self, permit):
        if (
            type(permit) is not FetchPermit
            or permit.provider != "TELEGRAM"
            or permit.bot_identity != bot("material")
            or permit.external_connection_id != route("material")
            or permit.image_file_id
            not in {f"m24-material-{label}-original" for label in MATERIAL_PHOTOS}
        ):
            raise ProvisioningError("Finite material original image permit required")
        await self.barrier("material-image")
        yield self.content


async def drain(worker):
    count = 0
    for _ in range(256):
        if not await worker.run_once():
            return count
        count += 1
    raise ProvisioningError("Bounded browser TEST jobs exceeded")


async def seed_knowledge(kernel, worker, adapter, values):
    """Finish the two HUMAN histories before any Resume or unrelated queue work.

    A later available_at cursor cannot exclude an old HUMAN job whose next step
    becomes due after Resume. Its existing generation must never enter the AI
    runtime. Ordinary effect-free consumption here needs no extra capability.
    """
    if (
        len(values) != 2
        or {value.chat_id for value in values} != {"m24-knowledge-main", "m24-knowledge-alternate"}
        or any(value.image_file_id is not None for value in values)
        or getattr(worker, "ai", None) is not None
    ):
        raise ProvisioningError("Two HUMAN knowledge seed histories required")
    expected = {}
    workspace = connection_id = None
    for value in values:
        receipt = await kernel.ingest_event(adapter.source(value.bot_identity), value, uuid4())
        if receipt.code != "ACCEPTED" or (
            workspace is not None and workspace != receipt.workspace_id
        ):
            raise ProvisioningError("Fresh exclusive knowledge seed required")
        workspace = receipt.workspace_id
        expected[receipt.job_id] = receipt.inbox_id
    observed, turns = set(), 0
    async with asyncio.timeout(15):
        for _ in range(256):
            claim = await kernel.claim_job("knowledge-browser-seed")
            if claim is None:
                await asyncio.sleep(0.05)
                continue
            if claim.workspace_id != workspace or (
                connection_id is not None and claim.connection_id != connection_id
            ):
                raise ProvisioningError("Exclusive knowledge seed scope required")
            connection_id = claim.connection_id
            if claim.kind == "PROCESS_INBOX":
                if expected.get(claim.job_id) != claim.inbox_id:
                    raise ProvisioningError("Original knowledge seed Inbox required")
                await worker.execute(claim)
                del expected[claim.job_id]
            elif claim.kind == "PROCESS_TURN" and claim.step in {"GROUP", "TEST_CONSUME"}:
                await worker.execute(claim)
                turns += 1
                if claim.step == "TEST_CONSUME":
                    receipt = await kernel.replay_turn(claim.job_id, claim.claim_token)
                    if (
                        receipt.code != "OBSERVED"
                        or receipt.job_id != claim.job_id
                        or receipt.workspace_id != workspace
                        or receipt.connection_id != connection_id
                        or receipt.turn_id != claim.turn_id
                        or receipt.turn_revision != claim.turn_revision
                        or receipt.consumer != "TURN_TEST_V1"
                        or receipt.result.member_count != 1
                        or receipt.result.ready_file_count != 0
                        or receipt.turn_id in observed
                    ):
                        raise ProvisioningError("Canonical HUMAN seed observation required")
                    observed.add(receipt.turn_id)
            else:
                raise ProvisioningError("Effect-free knowledge seed work required")
            if not expected and len(observed) == 2:
                if (
                    adapter.calls != 0
                    or adapter.effects != 0
                    or counters("knowledge") != {"calls": 0, "effects": 0}
                ):
                    raise ProvisioningError("Knowledge seed must have zero external effects")
                return turns
    raise ProvisioningError("Bounded HUMAN knowledge seed did not complete")


async def seed(kernel, worker, adapter):
    processed = 0
    seed_turns = 0
    values = tuple(seed_events())
    knowledge = tuple(value for value in values if value.bot_identity == bot("knowledge"))
    if knowledge:
        seed_turns += await seed_knowledge(kernel, worker, adapter, knowledge)
        processed += len(knowledge)

    async def next_seed_claim(name):
        nonlocal seed_turns
        for _ in range(256):
            claim = await kernel.claim_job(name)
            # Earlier HUMAN seed Turns may become due while later fixtures are
            # ingested. Execute only their ordinary effect-free Turn work, then
            # retain the exact Inbox/FETCH assertions below. No send/guard/timer
            # or extra FETCH is drained; the last PENDING image still stays so.
            if (
                claim is None
                or claim.kind != "PROCESS_TURN"
                or claim.step not in {"GROUP", "MEDIA", "TEST_CONSUME"}
            ):
                return claim
            await worker.execute(claim)
            seed_turns += 1
        raise ProvisioningError("Bounded browser seed Turn jobs exceeded")

    processed += await seed_material(kernel, worker, next_seed_claim)
    for value in values:
        if value.bot_identity == bot("knowledge"):
            continue  # Already observed through the ordinary HUMAN worker above.
        receipt = await kernel.ingest_event(adapter.source(value.bot_identity), value, uuid4())
        if receipt.code != "ACCEPTED":
            raise ProvisioningError("Fresh browser TEST Inbox required")
        claim = await next_seed_claim("m24-browser-seed")
        if claim is None or claim.kind != "PROCESS_INBOX" or claim.job_id != receipt.job_id:
            raise ProvisioningError("Exclusive browser seed queue required")
        await worker.execute(claim)
        processed += 1
        if value.image_file_id and value.image_file_id != "m24-image-pending":
            fetch = await next_seed_claim("m24-browser-image")
            if fetch is None or fetch.kind != "FETCH_IMAGE":
                raise ProvisioningError("Canonical browser FETCH required")
            await worker.execute(fetch)
    return {"processed": processed, "seed_turns": seed_turns}


async def seed_material(kernel, worker, next_seed_claim):
    processed = 0
    for alternate in (False, True):
        receipt = await TelegramIngress(kernel, bot("material")).ingest_update(
            material_event("original", alternate=alternate), uuid4()
        )
        claim = await next_seed_claim("material-browser-seed")
        if receipt.code != "ACCEPTED" or claim is None or claim.job_id != receipt.job_id:
            raise ProvisioningError("Fresh material browser Inbox required")
        await worker.execute(claim)
        processed += 1
    for label in MATERIAL_PHOTOS:
        receipt = await TelegramIngress(kernel, bot("material")).ingest_update(
            material_photo_event(label, "original"), uuid4()
        )
        claim = await next_seed_claim("material-photo-seed")
        if receipt.code != "ACCEPTED" or claim is None or claim.job_id != receipt.job_id:
            raise ProvisioningError("Fresh material PHOTO Inbox required")
        await worker.execute(claim)
        fetch = await next_seed_claim("material-photo-fetch")
        if (
            fetch is None
            or fetch.kind != "FETCH_IMAGE"
            or fetch.workspace_id != receipt.workspace_id
        ):
            raise ProvisioningError("Canonical material PHOTO FETCH required")
        await worker.execute(fetch)
        processed += 1
    return processed


def material_photo_event(label, step):
    if label not in MATERIAL_PHOTOS or step not in {"original", "caption", "change"}:
        raise ProvisioningError("Finite material PHOTO event required")
    index = MATERIAL_PHOTOS.index(label)
    chat = 7000014 + index
    update = 120010 + index * 3 + ("original", "caption", "change").index(step)
    if label == "delete" and step == "change":
        return {
            "update_id": update,
            "deleted_business_messages": {
                "business_connection_id": route("material"),
                "chat": {"id": chat},
                "message_ids": [501],
            },
        }
    body = {
        "business_connection_id": route("material"),
        "chat": {"id": chat, "type": "private"},
        "from": {"id": chat, "is_bot": False},
        "message_id": 501,
        "date": 1767323045,
    }
    if label == "text" and step == "change":
        body["text"] = "Material current text"
    else:
        ref = f"m24-material-{label}-" + ("replacement" if step == "change" else "original")
        body.update(
            photo=[{"file_id": ref, "width": 23, "height": 17}], caption=f"Material {label} {step}"
        )
    if step != "original":
        body["edit_date"] = 1767323065 + int(step == "change")
    return {
        "update_id": update,
        "business_message" if step == "original" else "edited_business_message": body,
    }


def material_event(operation, *, alternate=False):
    if operation in MATERIAL_ACTIONS[2:] and not alternate:
        _, label, step = operation.split("-")
        return material_photo_event(label, step)
    if operation not in {"original", "material-edit", "material-delete"} or (
        alternate and operation != "original"
    ):
        raise ProvisioningError("Finite material event required")
    chat = 7000013 if alternate else 7000012
    update = {
        "original": 120001 + int(alternate),
        "material-edit": 120003,
        "material-delete": 120004,
    }[operation]
    if operation == "material-delete":
        return {
            "update_id": update,
            "deleted_business_messages": {
                "business_connection_id": route("material"),
                "chat": {"id": chat},
                "message_ids": [501],
            },
        }
    body = {
        "business_connection_id": route("material"),
        "chat": {"id": chat, "type": "private"},
        "from": {"id": chat, "is_bot": False},
        "message_id": 501,
        "date": 1767323045,
        "text": "Material original alternate" if alternate else "Material original A",
    }
    if operation == "material-edit":
        body.update(edit_date=1767323065, text="Material edited B")
    return {
        "update_id": update,
        "edited_business_message" if operation == "material-edit" else "business_message": body,
    }


async def material_action(kernel, worker, operation):
    receipt = await TelegramIngress(kernel, bot("material")).ingest_update(
        material_event(operation), uuid4()
    )
    if receipt.code == "DUPLICATE":
        return {"processed": 0, "replayed": 1}
    for _ in range(256):
        claim = await kernel.claim_job("material-browser-worker")
        if claim is None:
            raise ProvisioningError("Due material Inbox required")
        if claim.job_id == receipt.job_id:
            await worker.execute(claim)
            # This is a narrow terminal read AFTER ordinary Worker dispatch.
            # A retry/pending result cannot masquerade as browser acceptance.
            async with kernel._transaction() as connection:
                result = (
                    await connection.execute(
                        text("SELECT platform.material_processing_replay(:job,:token)"),
                        {"job": claim.job_id, "token": claim.claim_token},
                    )
                ).scalar_one()
            if (
                result is None
                or result.get("code") != "MATERIAL_PROCESSED"
                or result.get("inbox_id") != str(receipt.inbox_id)
            ):
                raise ProvisioningError("Material completion required")
            return {"processed": 1, "replayed": 0}
        if claim.kind != "PROCESS_TURN" or claim.step not in {"GROUP", "MEDIA", "TEST_CONSUME"}:
            raise ProvisioningError("Exclusive material browser worker required")
        await worker.execute(claim)
    raise ProvisioningError("Bounded material browser work exceeded")


async def escalate(kernel, worker, adapter, preset, operation):
    # Browser performs the accepted owner Resume first. This ordinary controlled
    # ingress cannot create a request if Resume/billing/marker/authority fails.
    conversation = "alternate" if operation == "escalate-alternate" else "main"
    value = replace(event(preset, f"escalation-{uuid4()}", conversation=conversation), text=MARKER)
    incoming = await kernel.ingest_event(adapter.source(value.bot_identity), value, uuid4())
    if incoming.code != "ACCEPTED":
        raise ProvisioningError("Fresh controlled Escalation ingress required")
    processed = 0
    async with asyncio.timeout(15):
        for _ in range(512):
            claim = await kernel.claim_job("m3-browser-escalation")
            if claim is None:
                # Bounded ordinary worker scheduling; no clock/Job-row rewrite.
                await asyncio.sleep(0.025)
                continue
            await worker.execute(claim)
            processed += 1
            if claim.kind == "PROCESS_TURN" and claim.step == "ESCALATE_OWNER":
                saved = await kernel.replay_escalation(claim.job_id, claim.claim_token)
                if saved.workspace_id != incoming.workspace_id:
                    raise ProvisioningError("Concurrent Escalation fixture not allowed")
                processed += await drain(worker)
                if adapter.mismatched:
                    raise ProvisioningError("Concurrent browser outbound fixture not allowed")
                return {"created": 1, "worked": processed, **counters(preset)}
    raise ProvisioningError("Bounded Escalation creation not observed")


def knowledge_config():
    """One finite synthetic v3 composition; no provider/key/enable configuration."""
    return KnowledgeGatewayConfig(
        revision="browser_published_knowledge_v1",
        route=Route(
            branch="RU_AGGREGATOR",
            adapter="fake",
            execution="FAKE",
            endpoint="https://fake.invalid/v1",
            model="openai/gpt-6-luna",
            upstream="synthetic-official",
            eligibility="EVAL_ONLY",
        ),
        prompt_revision="conversation_v3",
        schema_revision="conversation_result_v1",
        limits=Limits(
            model_calls=2,
            read_executions=1,
            input_bytes=65536,
            output_bytes=8192,
            input_tokens=32768,
            output_tokens=1024,
            total_tokens=100000,
            duration_seconds=30.0,
            currency="RUB",
            cost_budget=Decimal("0.30"),
            call_cost_reservation=Decimal("0.10"),
        ),
    )


class KnowledgeBrowserDatabase(AIDatabase):
    prepared = None

    async def prepare(self, *args, **kwargs):
        run = await super().prepare(*args, **kwargs)
        if not isinstance(run, PreparedKnowledgeRun):
            raise ProvisioningError("Knowledge-aware browser PREPARE required")
        question = self.messaging.question_message_id
        snapshot = (
            parse_guarded_snapshot(run.snapshot)
            if "consumer" in run.snapshot
            else parse_snapshot(run.snapshot)
        )
        if question is None or question not in {member.message_id for member in snapshot.members}:
            raise ProvisioningError("Canonical browser question must be in the prepared Turn")
        self.prepared = run
        return run


class KnowledgeBrowserKernel(MessagingDatabase):
    finalized = None
    question_inbox_id = None
    question_message_id = None

    async def process_inbox(self, claim):
        result = await super().process_inbox(claim)
        if claim.inbox_id == self.question_inbox_id:
            if (
                result.inbox_id != self.question_inbox_id
                or result.code != "PROCESSED"
                or result.message_id is None
            ):
                raise ProvisioningError("Canonical browser question processing required")
            self.question_message_id = result.message_id
        return result

    async def finish_send(self, *args, **kwargs):
        result = await super().finish_send(*args, **kwargs)
        self.finalized = result
        return result

    async def claim_knowledge(self, cutoff, *, ai=False):
        # This is an available_at paging boundary, not a scope/creation filter.
        # HUMAN seed work is completed before Resume. Unexpected claims still
        # fail the caller's scope checks; every accepted job is admitted normally.
        name = "m5-knowledge-ai" if ai else "m5-knowledge-work"
        self._claim_scan[name] = ScanStep(
            step="BUSY", scan_until=cutoff + timedelta(seconds=30), at=cutoff, id=UUID(int=0)
        )
        return await self.claim_job(name, ai=ai)


class KnowledgeBrowserModel(FakeAdapter):
    """Echo a FAQ present in the actual Gateway input; no hardcoded business answer."""

    def __init__(self, database, barrier):
        super().__init__(knowledge_config().route)
        self.database, self.barrier = database, barrier
        self.view = None

    async def complete(self, request):
        _diagnostic.stage = "MODEL"
        await self.barrier("model")
        run = self.database.prepared
        if run is None or request.config != run.config or self.requests:
            raise ProvisioningError("One pinned browser model request required")
        values = [strict_json(m.text) for m in request.request.messages if m.role == "context"]
        candidates = [v for v in values if v.get("revision") == "business_knowledge_v1"]
        if len(candidates) != 1:
            raise ProvisioningError("Published model projection required")
        view = KnowledgeView.model_validate_json(json.dumps(candidates[0], allow_nan=False))
        current = [
            item
            for message in request.request.messages
            if message.role == "user"
            for item in strict_json(message.text)["current"]
        ]
        query = "\n".join(item["text"] for item in current if item["text"] is not None)
        if view != project_knowledge(run.active_projection, run.knowledge_pin, query):
            raise ProvisioningError("Model facts differ from the pinned publication")
        if view.status != "PUBLISHED" or not view.faqs:
            raise ProvisioningError("Owner-published browser FAQ required")
        for private in (
            run.binding.workspace_id,
            run.binding.client_id,
            run.binding.business_id,
            run.knowledge_pin.release_id,
        ):
            if str(private) in request.input_json():
                raise ProvisioningError("Private binding in model input")
        self.view = view
        response = await super().complete(request)
        _diagnostic.model_calls = len(self.requests)
        return response.model_copy(
            update={
                "output_json": json.dumps(
                    {
                        "kind": "reply",
                        "text": view.faqs[0].fact.answer,
                        "reason": None,
                    },
                    ensure_ascii=False,
                )
            }
        )


class KnowledgeBrowserTransport(FixtureAdapter):
    model = None

    async def send(self, permit):
        if (
            self.model is None
            or self.model.view is None
            or permit.provider != "CONTROLLED"
            or permit.text != self.model.view.faqs[0].fact.answer
        ):
            raise ProvisioningError("Canonical published text required at browser send")
        return await super().send(permit)


class KnowledgeBrowserJournal(DTO):
    revision: Literal["browser_knowledge_receipt_v1"]
    question_inbox_id: UUID
    claim: AIJobClaim = Field(repr=False)
    receipt: KnowledgeRuntimeReceipt = Field(repr=False)
    finalized: FinalizeResult = Field(repr=False)
    model_calls: Literal[1]
    source: str = Field(min_length=1, max_length=120)


def knowledge_journal(value=None):
    """Private bounded ACK evidence; it never authorizes a model call or resend."""
    ledger = ledger_path("knowledge")  # Validate the private current-owner directory.
    path = ledger.with_name("knowledge-receipt.json")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if value is None:
            return None
        data = value.model_dump_json().encode("utf-8")
        if len(data) > 8192:
            raise ProvisioningError("Bounded knowledge browser journal required")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            if os.write(descriptor, data) != len(data):
                raise ProvisioningError("Complete browser ACK journal required")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return value
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or not 0 < info.st_size <= 8192
        ):
            raise ProvisioningError("Private bounded knowledge browser journal required")
        data = os.read(descriptor, 8193)
    finally:
        os.close(descriptor)
    saved = KnowledgeBrowserJournal.model_validate_json(
        json.dumps(strict_json(data.decode("utf-8")))
    )
    if value is not None and saved != value:
        raise ProvisioningError("Knowledge browser journal already belongs to another result")
    return saved


def knowledge_report(journal, *, replayed):
    result = journal.receipt.result
    counted = counters("knowledge")
    if (
        result.kind != "reply"
        or journal.finalized.status != "SENT"
        or counted != {"calls": 1, "effects": 1}
    ):
        raise ProvisioningError("One canonical browser reply/effect required")
    pin = journal.receipt.knowledge_pin
    return {
        "model_calls": journal.model_calls,
        **counted,
        "activation_version": pin.activation_version,
        "release_id": str(pin.release_id),
        "answer": result.text,
        "source": journal.source,
        "replayed": replayed,
    }


async def knowledge_answer(engine, barrier):
    kernel = KnowledgeBrowserKernel(engine, environment="TEST")
    transport = KnowledgeBrowserTransport("knowledge", OutcomeKind.SUCCESS, barrier)
    runtime = SyntheticRuntime(kernel, knowledge_config(), lambda: model, environment="TEST")
    runtime.database = KnowledgeBrowserDatabase(kernel, environment="TEST", delivery=True)
    model = KnowledgeBrowserModel(runtime.database, barrier)
    transport.model = model
    worker = Worker(kernel, transport, ai=runtime)
    observer = Worker(kernel, transport)
    async with kernel._transaction() as connection:
        cutoff = (await connection.execute(text("SELECT clock_timestamp()"))).scalar_one()
    value = replace(
        event("knowledge", "published-question"),
        text="Как подготовиться к консультации? Synthetic preparation.",
    )
    _diagnostic.stage = "INGEST"
    incoming = await kernel.ingest_event(transport.source(value.bot_identity), value, uuid4())
    kernel.question_inbox_id = incoming.inbox_id
    _diagnostic.stage = "JOURNAL"
    journal = knowledge_journal()
    if journal is not None:
        if (
            incoming.code != "DUPLICATE"
            or journal.question_inbox_id != incoming.inbox_id
            or journal.claim.workspace_id != incoming.workspace_id
        ):
            raise ProvisioningError("Journal requires its original canonical question")
        _diagnostic.stage = "REPLAY"
        saved = await runtime.database.replay(journal.claim, knowledge_config())
        if saved != journal.receipt:
            raise ProvisioningError("Canonical knowledge receipt changed")
        return knowledge_report(journal, replayed=True)
    if incoming.code != "ACCEPTED" or counters("knowledge") != {"calls": 0, "effects": 0}:
        raise ProvisioningError("Fresh knowledge question or saved canonical journal required")
    ai_claim = None
    connection_id = None
    async with asyncio.timeout(25):
        for _ in range(512):
            _diagnostic.stage = "CLAIM_AI" if ai_claim is None else "CLAIM_WORK"
            claim = await kernel.claim_knowledge(cutoff, ai=ai_claim is None)
            if claim is None:
                _diagnostic.stage = "CLAIM_WORK"
                claim = await kernel.claim_knowledge(cutoff)
            if claim is None:
                await asyncio.sleep(0.025)
                continue
            if claim.workspace_id != incoming.workspace_id:
                raise ProvisioningError("Exclusive knowledge browser job required")
            if connection_id is None:
                if claim.kind != "PROCESS_INBOX" or claim.job_id != incoming.job_id:
                    raise ProvisioningError("Original knowledge question Inbox required")
                connection_id = claim.connection_id
            elif claim.connection_id != connection_id:
                raise ProvisioningError("Original knowledge connection required")
            if claim.kind not in {"PROCESS_INBOX", "PROCESS_TURN", "SEND_AI_TEXT"}:
                raise ProvisioningError("Text-only knowledge browser job required")
            if isinstance(claim, AIJobClaim):
                if ai_claim is not None:
                    raise ProvisioningError("One browser model job required")
                ai_claim = claim
            _diagnostic.stage = (
                "EXECUTE_AI"
                if isinstance(claim, AIJobClaim)
                else "EXECUTE_INBOX"
                if claim.kind == "PROCESS_INBOX"
                else "EXECUTE_SEND"
                if claim.kind == "SEND_AI_TEXT"
                else "EXECUTE_TURN"
            )
            # TEST_CONSUME is the ordinary effect-free observer, independent of
            # the GUARDED_TEXT source enrolled below. Sending it to the AI
            # worker would try to enroll the same current Turn a second time.
            selected = (
                observer
                if claim.kind == "PROCESS_TURN" and getattr(claim, "step", None) == "TEST_CONSUME"
                else worker
            )
            await selected.execute(claim)
            if kernel.finalized is None:
                continue
            if ai_claim is None or model.view is None or len(model.requests) != 1:
                raise ProvisioningError("Completed bounded knowledge browser model required")
            _diagnostic.stage = "REPLAY"
            receipt = await runtime.database.replay(ai_claim, knowledge_config())
            if (
                not isinstance(receipt, KnowledgeRuntimeReceipt)
                or receipt.knowledge_pin != runtime.database.prepared.knowledge_pin
            ):
                raise ProvisioningError("Canonical published browser pin required")
            journal = KnowledgeBrowserJournal(
                revision="browser_knowledge_receipt_v1",
                question_inbox_id=incoming.inbox_id,
                claim=ai_claim,
                receipt=receipt,
                finalized=kernel.finalized,
                model_calls=1,
                source=model.view.faqs[0].fact.source,
            )
            _diagnostic.stage = "JOURNAL"
            knowledge_journal(journal)
            return knowledge_report(journal, replayed=False)
    raise ProvisioningError("Bounded knowledge browser result not observed")


async def action(preset, operation):
    global _diagnostic
    _diagnostic = BrowserDiagnostic(stage="TARGET")
    validate_operation(preset, operation)
    url, settings = target()
    engine = create_async_engine(
        url, hide_parameters=True, pool_size=2, max_overflow=0, connect_args={"connect_timeout": 3}
    )
    storage = None
    transfer = None
    try:
        async with asyncio.timeout(120):
            _diagnostic.stage = "GUARD"
            await guard(engine)
            _diagnostic.ready = True
            if operation == "stats":
                return counters(preset)

            async def no_transaction(_):
                if engine.pool.checkedout() != 0:
                    raise ProvisioningError("External browser TEST I/O holds a DB connection")

            if operation == "knowledge-answer":
                return await knowledge_answer(engine, no_transaction)

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
            image_bytes = controlled_images(provider)
            images = ChannelImageProvider(
                provider, MaterialFixtureImageProvider(image_bytes, no_transaction)
            )
            storage = S3ObjectStorage(settings)
            original_io = storage._io

            async def storage_io(operation):
                await no_transaction("storage")
                return await original_io(operation)

            storage._io = storage_io
            transfer = FetchTransfer(FileDatabase(kernel), kernel, images, storage)
            worker = Worker(kernel, adapter, files=transfer)
            if operation == "seed":
                _diagnostic.stage = "SEED"
                for selected in PRESETS:
                    if counters(selected) != {"calls": 0, "effects": 0}:
                        raise ProvisioningError("Fresh browser TEST counters required")
                return await seed(kernel, worker, adapter)
            if operation.startswith("material-"):
                return await material_action(kernel, worker, operation)
            if operation.startswith("escalate-"):
                return await escalate(kernel, worker, adapter, preset, operation)
            recovered = await kernel.recover_expired() if operation == "recover" else 0
            _diagnostic.stage = "DRAIN"
            worked = await drain(worker)
            if adapter.mismatched:
                raise ProvisioningError("Concurrent browser outbound fixture not allowed")
            return {"worked": worked, "recovered": recovered, **counters(preset)}
    except Exception as error:
        _diagnostic.primary = diagnostic_failure(error, _diagnostic.stage)
        raise
    finally:
        try:
            if transfer is not None:
                await transfer.close()
            if storage is not None:
                await storage.close()
            await engine.dispose()
        except Exception as error:
            if _diagnostic.primary is None:
                _diagnostic.primary = diagnostic_failure(error, "CLEANUP")
            else:
                _diagnostic.cleanup = diagnostic_failure(error, "CLEANUP")[1]
            raise


def main():
    global _diagnostic
    _diagnostic = BrowserDiagnostic()
    preset = None
    try:
        parser = PrivateArgumentParser()
        parser.add_argument("--preset", choices=PRESETS)
        parser.add_argument("--action", required=True, choices=ACTIONS)
        args = parser.parse_args()
        preset = args.preset
        print(json.dumps(asyncio.run(action(args.preset, args.action)), sort_keys=True))
        return 0
    except Exception as error:
        if _diagnostic.stage != "ARGS":
            print(diagnostic_line(error, preset), file=sys.stderr)
        print("M2_4_BROWSER_WORKER_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
