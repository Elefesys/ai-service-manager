"""M2-A10/A12: finite TEST harness guards; real journeys run in test_browser.sh."""

import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from asm.messaging.models import OutcomeKind
from asm.messaging.results import SendPermit


@pytest.fixture
def harness(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    fixture = importlib.import_module("m2_4_browser_fixture")
    worker = importlib.import_module("m2_4_browser_worker")
    monkeypatch.setenv("ASM_ENVIRONMENT", "TEST")
    monkeypatch.setenv(
        "ASM_MIGRATION_DATABASE_URL",
        "postgresql+psycopg://asm_migrator:synthetic@postgres:5432/asm_test",
    )
    monkeypatch.setenv(
        "ASM_DATABASE_URL", "postgresql+psycopg://asm_runtime:synthetic@postgres:5432/asm_test"
    )
    monkeypatch.setenv("ASM_STORAGE_ENVIRONMENT", "TEST")
    monkeypatch.setenv("ASM_STORAGE_ENDPOINT", "http://storage:9000")
    monkeypatch.setenv("ASM_STORAGE_BUCKET", "asm-private-test")
    monkeypatch.setenv("ASM_STORAGE_ACCESS_KEY", "synthetic-access-key")
    monkeypatch.setenv("ASM_STORAGE_SECRET_KEY", "synthetic-secret-key")
    for key in ("ASM_ADMIN_DATABASE_URL", "PG_ADMIN_PASSWORD", "PG_MIGRATION_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    directory = tmp_path / "counters"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(worker, "COUNTER_DIRECTORY", directory)
    return SimpleNamespace(fixture=fixture, worker=worker, directory=directory)


def runtime_environment(monkeypatch):
    monkeypatch.delenv("ASM_MIGRATION_DATABASE_URL", raising=False)


@pytest.mark.parametrize(
    "key,value",
    [
        ("ASM_ENVIRONMENT", "LOCAL"),
        ("ASM_MIGRATION_DATABASE_URL", "postgresql+psycopg://asm_runtime:x@postgres:5432/asm_test"),
        (
            "ASM_MIGRATION_DATABASE_URL",
            "postgresql+psycopg://asm_migrator:x@postgres:5432/asm_local",
        ),
        (
            "ASM_MIGRATION_DATABASE_URL",
            "postgresql+psycopg://asm_migrator:x@external:5432/asm_test",
        ),
        (
            "ASM_MIGRATION_DATABASE_URL",
            "postgresql+psycopg://asm_migrator:x@postgres:5432/asm_test?host=external",
        ),
    ],
)
async def test_provision_rejects_target_before_engine_or_identity_write(
    harness, monkeypatch, key, value
):
    monkeypatch.setenv(key, value)
    called = False

    async def no_provision(*args):
        nonlocal called
        called = True

    monkeypatch.setattr(harness.fixture, "provision", no_provision)
    with pytest.raises(Exception):
        await harness.fixture.setup_messaging("synthetic-password")
    assert called is False


@pytest.mark.parametrize(
    "preset,operation",
    [
        ("foreign", "downgrade"),
        ("happy", "disable"),
        ("recovery", "restrict"),
        (None, "stats"),
        ("happy", "inventory"),
        ("../../arbitrary", "stats"),
        ("happy", "sql"),
        (None, "control-stats"),
        ("../../arbitrary", "control-stats"),
        ("ctrl_stale", "downgrade"),
        ("ctrl_recovery", "disable"),
        ("ctrl_stale", "restrict"),
        ("happy", "escalation-stats"),
        ("esc_stale", "downgrade"),
        ("esc_read", "disable"),
        ("esc_recovery", "restrict"),
    ],
)
async def test_finite_negative_actions_are_checked_before_database(
    harness, monkeypatch, preset, operation
):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected database construction")

    monkeypatch.setattr(harness.fixture, "create_async_engine", forbidden)
    with pytest.raises(harness.fixture.ProvisioningError):
        await harness.fixture.action(preset, operation)


@pytest.mark.parametrize(
    "key,value",
    [
        ("ASM_ENVIRONMENT", "LOCAL"),
        ("ASM_DATABASE_URL", "postgresql+psycopg://asm_migrator:x@postgres:5432/asm_test"),
        ("ASM_DATABASE_URL", "postgresql+psycopg://asm_runtime:x@postgres:5432/asm_local"),
        ("ASM_DATABASE_URL", "postgresql+psycopg://asm_runtime:x@external:5432/asm_test"),
        (
            "ASM_DATABASE_URL",
            "postgresql+psycopg://asm_runtime:x@postgres:5432/asm_test?host=external",
        ),
        ("ASM_STORAGE_ENVIRONMENT", "LOCAL"),
        ("ASM_STORAGE_ENDPOINT", "http://external:9000"),
        ("ASM_STORAGE_BUCKET", "asm-private-local"),
        ("ASM_MIGRATION_DATABASE_URL", ""),
        ("ASM_ADMIN_DATABASE_URL", ""),
        ("PG_ADMIN_PASSWORD", ""),
        ("PG_MIGRATION_PASSWORD", ""),
    ],
)
async def test_runtime_cannot_inherit_privileged_or_external_targets(
    harness, monkeypatch, key, value
):
    runtime_environment(monkeypatch)
    monkeypatch.setenv(key, value)

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected database or storage construction")

    monkeypatch.setattr(harness.worker, "create_async_engine", forbidden)
    with pytest.raises(harness.worker.ProvisioningError):
        await harness.worker.action("happy", "success")


def test_exact_test_targets_and_initial_private_counter_are_accepted(harness, monkeypatch):
    assert harness.fixture.target().database == "asm_test"
    runtime_environment(monkeypatch)
    url, storage = harness.worker.target()
    assert url.username == "asm_runtime" and storage.bucket == "asm-private-test"
    assert harness.worker.counters("happy") == {"calls": 0, "effects": 0}
    assert (harness.directory / "happy.jsonl").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "unsafe",
    [
        "directory_mode",
        "symlink_directory",
        "file_mode",
        "symlink_file",
        "hardlink_file",
        "large_file",
        "payload_file",
    ],
)
def test_private_durable_instrumentation_rejects_unsafe_files(
    harness, tmp_path, monkeypatch, unsafe
):
    path = harness.worker.ledger_path("happy")
    if unsafe == "directory_mode":
        harness.directory.chmod(0o755)
    elif unsafe == "symlink_directory":
        linked = tmp_path / "linked"
        linked.symlink_to(harness.directory)
        monkeypatch.setattr(harness.worker, "COUNTER_DIRECTORY", linked)
    elif unsafe == "file_mode":
        path.chmod(0o644)
    elif unsafe == "symlink_file":
        path.unlink()
        path.symlink_to(tmp_path / "elsewhere")
    elif unsafe == "hardlink_file":
        os.link(path, tmp_path / "other-link")
    elif unsafe == "large_file":
        path.write_bytes(b"x" * 65537)
    else:
        path.write_text('{"text":"unexpected payload"}\n')
    with pytest.raises((harness.worker.ProvisioningError, OSError)):
        harness.worker.counters("happy")


async def test_controlled_effect_counter_survives_adapter_replacement_without_hidden_dedupe(
    harness,
):
    async def no_transaction(_):
        pass

    permit = SendPermit(
        code="PERMITTED",
        job_id=uuid4(),
        claim_token=uuid4(),
        attempt_id=uuid4(),
        workspace_id=uuid4(),
        connection_id=uuid4(),
        provider="CONTROLLED",
        bot_identity=harness.fixture.bot("unknown"),
        external_connection_id="finite",
        chat_id="finite",
        text="Exact e\u0301 🎨\n",
    )
    adapter = harness.worker.FixtureAdapter("unknown", OutcomeKind.UNKNOWN, no_transaction)
    assert (await adapter.send(permit)).kind == OutcomeKind.UNKNOWN
    replacement = harness.worker.FixtureAdapter("unknown", OutcomeKind.SUCCESS, no_transaction)
    assert replacement.calls == 0 and replacement.effects == 0
    assert harness.worker.counters("unknown") == {"calls": 1, "effects": 1}
    # Instrumentation deliberately does not dedupe; canonical Jobs/Worker must
    # prevent a second call. The real no-resend assertion is the browser journey.
    assert (await replacement.send(permit)).kind == OutcomeKind.SUCCESS
    assert harness.worker.counters("unknown") == {"calls": 2, "effects": 2}
    assert harness.worker.counters("happy") == {"calls": 0, "effects": 0}
    assert set(
        json.loads(line).get("event") for line in adapter.ledger.read_text().splitlines()
    ) == {"CALL", "EFFECT"}


def test_seed_is_finite_multipage_and_uses_valid_exact_normalized_events(harness):
    values = list(harness.worker.seed_events())
    assert len(values) < 128
    assert len({(e.bot_identity, e.event_id) for e in values}) == len(values)
    assert {e.provider for e in values} == {"CONTROLLED"}
    assert {e.bot_identity for e in values} == {
        harness.fixture.bot(p) for p in harness.fixture.PRESETS if p != "material"
    }
    page = [e for e in values if e.bot_identity == harness.fixture.bot("pagination")]
    assert len({e.external_connection_id for e in page}) == 27
    assert len({e.chat_id for e in page}) == 28
    assert sum(e.chat_id == "m24-pagination-main" for e in page) > 25
    assert values[-1].image_file_id == "m24-image-pending"
    assert sum(e.image_file_id == "m24-image-pending" for e in values) == 1
    assert all(e.text is None or "e\u0301 🎨" in e.text for e in values)


def test_control_presets_use_existing_canonical_seed_and_finite_mutation_scope(harness):
    presets = {p for p in harness.fixture.PRESETS if p.startswith("ctrl_")}
    assert presets == {
        "ctrl_stale",
        "ctrl_recovery",
        "ctrl_read",
        "ctrl_revoked",
        "ctrl_inactive",
        "ctrl_restricted",
    }
    for preset in presets:
        harness.fixture.validate_operation(preset, "control-stats")
        events = [
            e for e in harness.worker.seed_events() if e.bot_identity == harness.fixture.bot(preset)
        ]
        assert len(events) == 3
        assert {e.chat_id for e in events} == {f"m24-{preset}-main", f"m24-{preset}-alternate"}


def test_escalation_presets_retain_pending_image_boundary_and_need_runtime_creation(harness):
    assert set(harness.fixture.ESCALATION_PRESETS) == {
        "esc_happy",
        "esc_narrow",
        "esc_recovery",
        "esc_read",
        "esc_stale",
        "esc_revoked",
    }
    events = list(harness.worker.seed_events())
    assert events[-1].image_file_id == "m24-image-pending"
    for preset in harness.fixture.ESCALATION_PRESETS:
        own = [e for e in events if e.bot_identity == harness.fixture.bot(preset)]
        assert len(own) == 2 and all(e.image_file_id is None for e in own)
        assert all(e.text != harness.worker.MARKER for e in own)
        harness.fixture.validate_operation(preset, "escalation-stats")
        harness.worker.validate_operation(preset, "escalate-main")
    for preset in ("esc_happy", "esc_narrow"):
        harness.fixture.validate_operation(preset, "disable")
        harness.fixture.validate_operation(preset, "restrict")
        harness.worker.validate_operation(preset, "escalate-alternate")


@pytest.mark.parametrize(
    "preset,operation",
    [
        ("happy", "escalate-main"),
        ("esc_read", "escalate-alternate"),
        (None, "escalate-main"),
        ("esc_happy", "escalate-arbitrary"),
    ],
)
async def test_escalation_runner_rejects_unassigned_actions_before_database(
    harness, monkeypatch, preset, operation
):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected database construction")

    monkeypatch.setattr(harness.worker, "create_async_engine", forbidden)
    with pytest.raises(harness.worker.ProvisioningError):
        await harness.worker.action(preset, operation)


async def test_escalation_runtime_keeps_privileged_environment_denial(harness, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected database construction")

    monkeypatch.setattr(harness.worker, "create_async_engine", forbidden)
    # The fixture intentionally still has a migration credential in its env.
    with pytest.raises(harness.worker.ProvisioningError):
        await harness.worker.action("esc_recovery", "escalate-main")


@pytest.mark.parametrize("conversation", ["main", "alternate"])
async def test_escalation_action_ingests_validated_event_then_uses_worker(harness, conversation):
    """Exercise the real immutable event type, before any runtime I/O is needed."""
    from asm.messaging.models import NormalizedEventV1

    workspace, job, token = uuid4(), uuid4(), uuid4()
    claim = SimpleNamespace(
        kind="PROCESS_TURN", step="ESCALATE_OWNER", job_id=job, claim_token=token
    )
    observed = []

    class Kernel:
        async def ingest_event(self, source, value, correlation):
            assert isinstance(value, NormalizedEventV1)
            assert source == value.bot_identity == harness.fixture.bot("esc_happy")
            assert value.text == harness.worker.MARKER and value.image_file_id is None
            assert value.chat_id == f"m24-esc_happy-{conversation}"
            assert value.sender_id == f"m24-esc_happy-{conversation}-client"
            observed.append("ingest")
            return SimpleNamespace(code="ACCEPTED", workspace_id=workspace)

        async def claim_job(self, name):
            observed.append("claim")
            return claim

        async def replay_escalation(self, job_id, claim_token):
            assert (job_id, claim_token) == (job, token)
            observed.append("replay")
            return SimpleNamespace(workspace_id=workspace)

    class Worker:
        async def execute(self, received):
            assert received is claim
            observed.append("execute")

        async def run_once(self):
            observed.append("drain")
            return False

    result = await harness.worker.escalate(
        Kernel(),
        Worker(),
        SimpleNamespace(source=lambda value: value, mismatched=False),
        "esc_happy",
        f"escalate-{conversation}",
    )
    assert observed == ["ingest", "claim", "execute", "replay", "drain"]
    assert result == {"created": 1, "worked": 1, "calls": 0, "effects": 0}


async def test_seed_handles_due_turn_between_inbox_claims_but_leaves_last_fetch_pending(
    harness, monkeypatch
):
    """More finite fixtures must not assume that a real durable queue is FIFO."""
    first, last, turn = uuid4(), uuid4(), uuid4()
    events = [
        harness.worker.event("esc_happy", "first"),
        harness.worker.event("happy", "pending-image", image="pending"),
    ]
    monkeypatch.setattr(harness.worker, "seed_material", AsyncMock(return_value=0))
    monkeypatch.setattr(harness.worker, "seed_events", lambda: iter(events))
    waiting = [
        SimpleNamespace(kind="PROCESS_INBOX", job_id=first),
        SimpleNamespace(kind="PROCESS_TURN", step="TEST_CONSUME", job_id=turn),
        SimpleNamespace(kind="PROCESS_INBOX", job_id=last),
        SimpleNamespace(kind="FETCH_IMAGE", job_id=uuid4()),
    ]
    accepted, executed = [], []

    class Kernel:
        async def ingest_event(self, source, value, correlation):
            accepted.append(value)
            return SimpleNamespace(code="ACCEPTED", job_id=first if len(accepted) == 1 else last)

        async def claim_job(self, name):
            return waiting.pop(0)

    class Worker:
        async def execute(self, claim):
            executed.append(claim.job_id)

    result = await harness.worker.seed(Kernel(), Worker(), SimpleNamespace(source=lambda v: v))
    assert result["processed"] == 2
    assert result["seed_turns"] == 1
    assert executed == [first, turn, last]
    assert len(waiting) == 1 and waiting[0].kind == "FETCH_IMAGE"


@pytest.mark.parametrize(
    "kind,step",
    [
        ("FETCH_IMAGE", None),
        ("SEND_MANUAL_TEXT", None),
        ("PROCESS_TURN", "GUARDED_TEXT"),
        ("PROCESS_TURN", "ESCALATE_OWNER"),
        ("ESCALATION_TIMER", "EXPIRE"),
        ("PROCESS_INBOX", None),
    ],
)
async def test_seed_still_rejects_unrelated_jobs_without_executing_them(
    harness, monkeypatch, kind, step
):
    monkeypatch.setattr(harness.worker, "seed_material", AsyncMock(return_value=0))
    monkeypatch.setattr(
        harness.worker, "seed_events", lambda: iter([harness.worker.event("esc_happy", "first")])
    )

    class Kernel:
        async def ingest_event(self, source, value, correlation):
            return SimpleNamespace(code="ACCEPTED", job_id=uuid4())

        async def claim_job(self, name):
            return SimpleNamespace(kind=kind, step=step, job_id=uuid4())

    class Worker:
        async def execute(self, claim):
            pytest.fail("Unrelated seed work must not execute")

    with pytest.raises(harness.worker.ProvisioningError, match="Exclusive browser seed"):
        await harness.worker.seed(Kernel(), Worker(), SimpleNamespace(source=lambda v: v))


async def test_control_counters_are_read_only_bound_to_finite_owner_workspace(harness, monkeypatch):
    from contextlib import asynccontextmanager

    workspace, actor = uuid4(), uuid4()
    queries = []

    class Connection:
        async def execute(self, sql, params):
            queries.append((str(sql), params))
            return SimpleNamespace(scalar_one=lambda: 7)

    class Engine:
        @asynccontextmanager
        async def begin(self):
            yield Connection()

        async def dispose(self):
            pass

    async def guard(_):
        pass

    async def identity(_, preset):
        assert preset == "ctrl_recovery"
        return SimpleNamespace(workspace_id=workspace, user_account_id=actor)

    monkeypatch.setattr(harness.fixture, "create_async_engine", lambda *args, **kwargs: Engine())
    monkeypatch.setattr(harness.fixture, "guard", guard)
    monkeypatch.setattr(harness.fixture, "identity", identity)
    result = await harness.fixture.action("ctrl_recovery", "control-stats")
    assert set(result) == {
        "messages",
        "receipts",
        "audit_events",
        "outbox_events",
        "jobs",
        "control_receipts",
        "control_audit_events",
    }
    assert len(queries) == 7 and set(result.values()) == {7}
    for sql, params in queries:
        assert sql.startswith("SELECT count(*) FROM ") and "workspace_id=:ws" in sql
        assert params == {"ws": workspace, "actor": actor}


async def test_escalation_counters_are_read_only_and_do_not_return_answers(harness, monkeypatch):
    from contextlib import asynccontextmanager

    workspace, actor = uuid4(), uuid4()
    queries = []

    class Connection:
        async def execute(self, sql, params):
            queries.append((str(sql), params))
            return SimpleNamespace(scalar_one=lambda: 0)

    class Engine:
        @asynccontextmanager
        async def begin(self):
            yield Connection()

        async def dispose(self):
            pass

    async def guard(_):
        pass

    async def identity(_, preset):
        assert preset == "esc_recovery"
        return SimpleNamespace(workspace_id=workspace, user_account_id=actor)

    monkeypatch.setattr(harness.fixture, "create_async_engine", lambda *a, **kw: Engine())
    monkeypatch.setattr(harness.fixture, "guard", guard)
    monkeypatch.setattr(harness.fixture, "identity", identity)
    result = await harness.fixture.action("esc_recovery", "escalation-stats")
    assert set(result) == {
        "messages",
        "receipts",
        "audit_events",
        "outbox_events",
        "jobs",
        "control_receipts",
        "control_audit_events",
        "escalations",
        "escalation_receipts",
        "escalation_audit",
        "escalation_timers",
    }
    for sql, params in queries:
        assert sql.startswith("SELECT count(*) FROM ") and "workspace_id=:ws" in sql
        assert "answer" not in sql and params == {"ws": workspace, "actor": actor}


@pytest.mark.parametrize("module", ["fixture", "worker"])
def test_unknown_cli_arguments_never_echo_payloads(harness, monkeypatch, capsys, module):
    monkeypatch.setattr(sys, "argv", ["fixture", "--arbitrary", "canary-secret-url-payload"])
    assert getattr(harness, module).main() == 1
    output = capsys.readouterr()
    assert output.out == "" and "canary" not in output.err
    assert output.err in {"M2_4_BROWSER_FIXTURE_FAILED\n", "M2_4_BROWSER_WORKER_FAILED\n"}


def test_material_harness_is_finite_and_uses_distinct_numeric_telegram_binding(harness):
    from asm.telegram.normalization import normalize_update_v2

    worker, fixture = harness.worker, harness.fixture
    assert fixture.bot("material") == "9000012"
    for operation, kind in (
        ("original", "NEW"),
        ("material-edit", "EDIT"),
        ("material-delete", "DELETE"),
    ):
        value = normalize_update_v2(fixture.bot("material"), worker.material_event(operation))
        assert value.discriminator == kind and value.connection == fixture.route("material")
    for preset, operation in (
        ("happy", "material-edit"),
        ("material", "success"),
        ("material", "escalate-main"),
    ):
        with pytest.raises(fixture.ProvisioningError):
            worker.validate_operation(preset, operation)
    assert all(v.bot_identity != fixture.bot("material") for v in worker.seed_events())


def test_material_photo_actions_keep_original_reference_only_for_caption(harness):
    from asm.telegram.normalization import normalize_update_v2

    worker, fixture = harness.worker, harness.fixture
    updates, chats = set(), set()
    for label in fixture.MATERIAL_PHOTOS:
        original = normalize_update_v2(
            fixture.bot("material"), worker.material_photo_event(label, "original")
        )
        assert original.discriminator == "NEW" and original.content.kind == "PHOTO"
        assert original.content.selected_file_id == f"m24-material-{label}-original"
        chats.add(original.chat_id)
        for step in ("caption", "change"):
            action = f"material-{label}-{step}"
            worker.validate_operation("material", action)
            value = normalize_update_v2(fixture.bot("material"), worker.material_event(action))
            assert value.chat_id == original.chat_id and value.update_id not in updates
            updates.add(value.update_id)
            if step == "caption":
                assert value.content.selected_file_id == original.content.selected_file_id
            elif label == "delete":
                assert value.discriminator == "DELETE" and value.content is None
            elif label == "text":
                assert value.content.kind == "TEXT"
            else:
                assert (
                    value.content.kind == "PHOTO"
                    and value.content.selected_file_id != original.content.selected_file_id
                )
            with pytest.raises(worker.ProvisioningError):
                worker.validate_operation("happy", action)
    assert len(chats) == 4 and len(updates) == 8
    fixture.validate_operation("material", "material-stats")
    for label, step in (("arbitrary", "change"), ("replacement", "restore")):
        with pytest.raises(worker.ProvisioningError):
            worker.material_photo_event(label, step)
    with pytest.raises(fixture.ProvisioningError):
        fixture.validate_operation("happy", "material-stats")


async def test_material_fixture_bytes_require_exact_telegram_original_permit(harness):
    from io import BytesIO

    from asm.files.models import FetchPermit
    from asm.files.provider import ControlledImageProvider
    from PIL import Image

    worker = harness.worker
    content = worker.controlled_images(ControlledImageProvider(environment="TEST"))
    barrier = AsyncMock()
    provider = worker.MaterialFixtureImageProvider(content, barrier)
    values = {
        name: uuid4()
        for name in (
            "job_id",
            "claim_token",
            "workspace_id",
            "connection_id",
            "file_id",
            "message_id",
            "conversation_id",
        )
    }
    permit = FetchPermit(
        **values,
        provider="TELEGRAM",
        bot_identity=worker.bot("material"),
        external_connection_id=worker.route("material"),
        image_file_id="m24-material-replacement-original",
    )
    chunks = [chunk async for chunk in provider.open_image(permit)]
    assert Image.open(BytesIO(b"".join(chunks))).size == (23, 17)
    barrier.assert_awaited_once()
    for changes in (
        {"provider": "CONTROLLED"},
        {"bot_identity": "1"},
        {"external_connection_id": "other"},
        {"image_file_id": "m24-material-replacement-replacement"},
    ):
        with pytest.raises(worker.ProvisioningError):
            _ = [chunk async for chunk in provider.open_image(permit.model_copy(update=changes))]
    assert barrier.await_count == 1


@pytest.mark.parametrize("terminal", [True, False])
async def test_material_action_dispatches_worker_and_only_reads_terminal_afterwards(
    harness, monkeypatch, terminal
):
    from contextlib import asynccontextmanager

    worker = harness.worker
    receipt = SimpleNamespace(code="ACCEPTED", job_id=uuid4(), inbox_id=uuid4())
    claim = SimpleNamespace(job_id=receipt.job_id, claim_token=uuid4(), kind="PROCESS_INBOX")
    ingress = AsyncMock(return_value=receipt)
    monkeypatch.setattr(
        worker, "TelegramIngress", lambda *args: SimpleNamespace(ingest_update=ingress)
    )
    dispatch = AsyncMock()

    class Kernel:
        claim_job = AsyncMock(return_value=claim)

        @asynccontextmanager
        async def _transaction(self):
            async def execute(sql, params):
                dispatch.assert_awaited_once_with(claim)
                assert "material_processing_replay" in str(sql)
                assert params == {"job": claim.job_id, "token": claim.claim_token}
                return SimpleNamespace(
                    scalar_one=lambda: (
                        {"code": "MATERIAL_PROCESSED", "inbox_id": str(receipt.inbox_id)}
                        if terminal
                        else None
                    )
                )

            yield SimpleNamespace(execute=execute)

        async def process_inbox(self, *args):
            pytest.fail("Mutation must dispatch ordinary Worker; readback must not reprocess")

    if terminal:
        assert await worker.material_action(
            Kernel(), SimpleNamespace(execute=dispatch), "material-replacement-change"
        ) == {"processed": 1, "replayed": 0}
    else:
        with pytest.raises(worker.ProvisioningError, match="Material completion required"):
            await worker.material_action(
                Kernel(), SimpleNamespace(execute=dispatch), "material-replacement-change"
            )


def test_native_presets_keep_old_seed_cap_and_never_provision_reconciliation(harness):
    fixture, worker = harness.fixture, harness.worker
    assert fixture.NATIVE_PRESETS == ("native_happy", "native_narrow")
    events = list(worker.seed_events())
    assert len(events) < 128 and events[-1].image_file_id == "m24-image-pending"
    for preset in fixture.NATIVE_PRESETS:
        own = [e for e in events if e.bot_identity == fixture.bot(preset)]
        assert len(own) == 2 and all(e.image_file_id is None for e in own)
        assert {e.chat_id for e in own} == {f"m24-{preset}-main", f"m24-{preset}-alternate"}
        for action in ("native-stats", "native-enable", "native-pause", "downgrade"):
            fixture.validate_operation(preset, action)
    for action in ("native-stats", "native-enable", "native-pause"):
        with pytest.raises(fixture.ProvisioningError):
            fixture.validate_operation("happy", action)


@pytest.mark.parametrize("source", [None, "", "a" * 39, "a" * 41, "A" * 40, True, "a" * 40 + "\n"])
async def test_native_policy_requires_exact_source_before_database(harness, monkeypatch, source):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected database construction")

    monkeypatch.setattr(harness.fixture, "create_async_engine", forbidden)
    with pytest.raises(harness.fixture.ProvisioningError):
        await harness.fixture.action("native_happy", "native-enable", source)
    with pytest.raises(harness.fixture.ProvisioningError):
        await harness.fixture.action("native_happy", "native-stats", "a" * 40)


@pytest.mark.parametrize("operation", ["native-enable", "native-pause"])
async def test_native_policy_carrier_uses_catalog_binding_and_actual_capability_only(
    harness, operation
):
    fixture = harness.fixture
    ws, business, connection = uuid4(), uuid4(), uuid4()
    row = dict(
        id=connection,
        business_id=business,
        provider="CONTROLLED",
        bot_identity=fixture.bot("native_happy"),
        external_connection_id=fixture.route("native_happy"),
        human_context_policy="ON",
        human_context_policy_epoch=1,
    )
    profile = dict(schema_revision="0019", valid=True, profile_sha256="b" * 64)
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: row)),
                SimpleNamespace(scalar_one=lambda: profile),
                None,
            ]
        )
    )
    result = await fixture.native_policy(db, {"ws": ws}, "native_happy", operation, "a" * 40)
    assert result == {"command_completed": True}
    calls = db.execute.await_args_list
    assert len(calls) == 3 and all(str(c.args[0]).startswith("SELECT ") for c in calls)
    assert str(calls[2].args[0]).startswith("SELECT platform.human_context_policy_command(")
    params = calls[2].args[1]
    assert params["ws"] == ws and params["id"] == connection
    assert params["op"] == operation.removeprefix("native-").upper()
    assert params["policy"] == "ON" and params["epoch"] == 1
    assert json.loads(params["binding"]) == {
        "business_id": str(business),
        "provider": "CONTROLLED",
        "bot_identity": row["bot_identity"],
        "external_connection_id": row["external_connection_id"],
        "owner_user_id": None,
    }
    assert json.loads(params["profile"]) == {
        "source_tree": "a" * 40,
        "schema_revision": "0019",
        "profile_sha256": "b" * 64,
        "drain_confirmed": True,
    }
    assert "reconcile" not in str(calls[2].args[0])


@pytest.mark.parametrize(
    "patch",
    [
        {"valid": False},
        {"valid": 1},
        {"schema_revision": "0012"},
        {"profile_sha256": "A" * 64},
        {"extra": True},
    ],
)
async def test_native_policy_rejects_bad_catalog_before_capability(harness, patch):
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: {})),
                SimpleNamespace(
                    scalar_one=lambda: (
                        dict(schema_revision="0019", valid=True, profile_sha256="b" * 64) | patch
                    )
                ),
            ]
        )
    )
    with pytest.raises(harness.fixture.ProvisioningError):
        await harness.fixture.native_policy(
            db, {"ws": uuid4()}, "native_happy", "native-enable", "a" * 40
        )
    assert db.execute.await_count == 2


def test_knowledge_preset_has_only_two_text_seeds_and_closed_actions(harness):
    fixture, worker = harness.fixture, harness.worker
    events = list(worker.seed_events())
    own = [value for value in events if value.bot_identity == fixture.bot("knowledge")]
    assert len(events) < 128 and len(own) == 2
    assert {value.chat_id for value in own} == {"m24-knowledge-main", "m24-knowledge-alternate"}
    assert all(value.image_file_id is None for value in own)
    worker.validate_operation("knowledge", "knowledge-answer")
    worker.validate_operation("knowledge", "stats")
    for preset, operation in (
        ("happy", "knowledge-answer"),
        (None, "knowledge-answer"),
        ("knowledge", "success"),
        ("knowledge", "recover"),
    ):
        with pytest.raises(worker.ProvisioningError):
            worker.validate_operation(preset, operation)
    for operation in ("downgrade", "native-enable", "material-stats"):
        with pytest.raises(fixture.ProvisioningError):
            fixture.validate_operation("knowledge", operation)
    config = worker.knowledge_config()
    assert config.prompt_revision == "conversation_v3"
    assert config.route.execution == "FAKE" and config.route.eligibility == "EVAL_ONLY"
    assert config.limits.model_calls == 2 and config.limits.read_executions == 1


def knowledge_browser_journal(worker):
    from datetime import UTC, datetime

    from asm.ai.contracts import Reply
    from asm.ai.runtime_contracts import KnowledgeRuntimeReceipt
    from asm.messaging.results import AIJobClaim, FinalizeResult
    from m5_knowledge_fixtures import knowledge_run

    run = knowledge_run()
    claim = AIJobClaim(
        job_id=run.binding.job_id,
        kind="PROCESS_TURN",
        step="AI_GENERATE",
        workspace_id=run.binding.workspace_id,
        connection_id=run.binding.connection_id,
        turn_id=run.binding.turn_id,
        turn_revision=run.binding.turn_revision,
        claim_token=uuid4(),
        lease_until=run.deadline,
        correlation_id=uuid4(),
        attempt_count=1,
        inbox_id=None,
        outbox_id=None,
    )
    receipt = KnowledgeRuntimeReceipt(
        run_id=run.run_id,
        job_id=claim.job_id,
        turn_id=claim.turn_id,
        turn_revision=claim.turn_revision,
        selected_at=datetime.now(UTC),
        result=Reply(kind="reply", text="From the published FAQ", reason=None),
        knowledge_pin=run.knowledge_pin,
    )
    return worker.KnowledgeBrowserJournal(
        revision="browser_knowledge_receipt_v1",
        question_inbox_id=uuid4(),
        claim=claim,
        receipt=receipt,
        finalized=FinalizeResult(
            code="FINALIZED", status="SENT", job_id=uuid4(), outbox_id=uuid4(), attempt_id=uuid4()
        ),
        model_calls=1,
        source="Synthetic owner handbook",
    )


@pytest.mark.parametrize("fault", [None, "mode", "size", "duplicate_key"])
def test_knowledge_ack_journal_is_private_bounded_and_not_authority(harness, fault):
    worker = harness.worker
    assert worker.knowledge_journal() is None
    journal = knowledge_browser_journal(worker)
    worker.knowledge_journal(journal)
    path = harness.directory / "knowledge-receipt.json"
    assert path.stat().st_mode & 0o777 == 0o600
    if fault == "mode":
        path.chmod(0o644)
    elif fault == "size":
        path.write_bytes(b"x" * 8193)
    elif fault == "duplicate_key":
        path.write_text('{"revision":"browser_knowledge_receipt_v1","revision":"other"}')
    if fault:
        with pytest.raises((worker.ProvisioningError, ValueError)):
            worker.knowledge_journal()
    else:
        assert worker.knowledge_journal() == journal
        with pytest.raises(worker.ProvisioningError):
            worker.knowledge_report(journal, replayed=True)  # No physical effect evidence.


async def test_knowledge_model_echoes_actual_projected_source_and_never_a_canned_answer(harness):
    from asm.ai.context import KnowledgeContextBuilder
    from asm.ai.contracts import AdapterRequest, Budget, GatewayRequest
    from m5_knowledge_fixtures import knowledge_run

    worker = harness.worker
    run = knowledge_run().model_copy(update={"config": worker.knowledge_config()})
    view = (
        KnowledgeContextBuilder()
        .build(run.snapshot, run.binding, run.knowledge_pin, run.active_projection)
        .view
    )
    model = worker.KnowledgeBrowserModel(SimpleNamespace(prepared=run), AsyncMock())
    request = AdapterRequest(
        config=run.config,
        request=GatewayRequest(
            run_id=str(run.run_id), deadline=run.deadline, messages=view.messages(), tools=()
        ),
        prompt="synthetic",
        output_schema_json="{}",
        exchanges=(),
        budget=Budget(
            calls_used=1,
            reads_reserved=0,
            tokens_reserved=1000,
            cost_reserved=worker.Decimal("0.10"),
            currency="RUB",
        ),
        remaining_seconds=5.0,
    )
    response = await model.complete(request)
    assert json.loads(response.output_json)["text"] == run.active_projection.bundle.faqs[0].answer
    assert model.view.faqs[0].fact.source == run.active_projection.bundle.faqs[0].source
    assert len(model.requests) == 1
    with pytest.raises(worker.ProvisioningError):
        await model.complete(request)
    assert len(model.requests) == 1


@pytest.mark.parametrize("fault", [None, "missing_journal", "different_receipt"])
async def test_knowledge_repeat_reads_canonical_receipt_without_claim_model_or_send(
    harness, monkeypatch, fault
):
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime

    worker = harness.worker
    journal = knowledge_browser_journal(worker)
    if fault != "missing_journal":
        worker.knowledge_journal(journal)
        worker.ledger_path("knowledge").write_text('{"event":"CALL"}\n{"event":"EFFECT"}\n')
    raw = journal.receipt.model_dump(mode="json")
    if fault == "different_receipt":
        raw["result"]["text"] = "Different saved result"

    class Kernel:
        ingest_event = AsyncMock(
            return_value=SimpleNamespace(
                code="DUPLICATE",
                inbox_id=journal.question_inbox_id,
                workspace_id=journal.claim.workspace_id,
            )
        )
        replay_ai = AsyncMock(return_value=raw)
        claim_knowledge = AsyncMock(side_effect=AssertionError("Replay claimed a job"))

        @asynccontextmanager
        async def _transaction(self):
            yield SimpleNamespace(
                execute=AsyncMock(
                    return_value=SimpleNamespace(scalar_one=lambda: datetime.now(UTC))
                )
            )

    kernel = Kernel()
    monkeypatch.setattr(worker, "KnowledgeBrowserKernel", lambda *args, **kwargs: kernel)
    if fault:
        with pytest.raises(worker.ProvisioningError):
            await worker.knowledge_answer(None, AsyncMock())
    else:
        result = await worker.knowledge_answer(None, AsyncMock())
        assert result == {
            "model_calls": 1,
            "calls": 1,
            "effects": 1,
            "activation_version": journal.receipt.knowledge_pin.activation_version,
            "release_id": str(journal.receipt.knowledge_pin.release_id),
            "answer": "From the published FAQ",
            "source": "Synthetic owner handbook",
            "replayed": True,
        }
        kernel.replay_ai.assert_awaited_once()
    kernel.claim_knowledge.assert_not_awaited()


def human_knowledge_seed(harness):
    """Controlled queue/proofs, not a PostgreSQL or live OWNER substitute."""
    worker = harness.worker
    values = tuple(v for v in worker.seed_events() if v.bot_identity == worker.bot("knowledge"))
    ws, connection = uuid4(), uuid4()
    inboxes = [
        SimpleNamespace(code="ACCEPTED", workspace_id=ws, inbox_id=uuid4(), job_id=uuid4())
        for _ in values
    ]
    inbox_claims = [
        SimpleNamespace(
            kind="PROCESS_INBOX",
            workspace_id=ws,
            connection_id=connection,
            job_id=r.job_id,
            inbox_id=r.inbox_id,
        )
        for r in inboxes
    ]
    groups, consumers, proofs = [], [], []
    for _ in values:
        turn = uuid4()
        groups.append(
            SimpleNamespace(
                kind="PROCESS_TURN",
                step="GROUP",
                workspace_id=ws,
                connection_id=connection,
                job_id=uuid4(),
                claim_token=uuid4(),
                turn_id=turn,
                turn_revision=1,
            )
        )
        consumer = SimpleNamespace(
            kind="PROCESS_TURN",
            step="TEST_CONSUME",
            workspace_id=ws,
            connection_id=connection,
            job_id=uuid4(),
            claim_token=uuid4(),
            turn_id=turn,
            turn_revision=2,
        )
        consumers.append(consumer)
        proofs.append(
            SimpleNamespace(
                code="OBSERVED",
                job_id=consumer.job_id,
                workspace_id=ws,
                connection_id=connection,
                turn_id=turn,
                turn_revision=2,
                consumer="TURN_TEST_V1",
                result=SimpleNamespace(member_count=1, ready_file_count=0),
            )
        )
    queue = list(inbox_claims + groups + consumers)
    executed, observed = [], []
    events = []

    async def ingest(source, value, correlation):
        events.append(("ingest", value.bot_identity))
        return inboxes[values.index(value)]

    async def claim(name):
        assert name == "knowledge-browser-seed"
        return queue.pop(0) if queue else None

    async def dispatch(value):
        events.append(("execute", value.kind))
        executed.append(value)

    async def replay(job, token):
        consumer = next(c for c in consumers if c.job_id == job)
        assert token == consumer.claim_token and consumer in executed
        observed.append(job)
        events.append(("observe", job))
        return proofs[consumers.index(consumer)]

    return SimpleNamespace(
        values=values,
        inboxes=inboxes,
        inbox_claims=inbox_claims,
        groups=groups,
        consumers=consumers,
        proofs=proofs,
        queue=queue,
        events=events,
        executed=executed,
        observed=observed,
        kernel=SimpleNamespace(
            ingest_event=AsyncMock(side_effect=ingest),
            claim_job=AsyncMock(side_effect=claim),
            replay_turn=AsyncMock(side_effect=replay),
        ),
        ordinary=SimpleNamespace(ai=None, execute=AsyncMock(side_effect=dispatch)),
        adapter=SimpleNamespace(calls=0, effects=0, source=lambda bot: bot),
    )


async def test_human_knowledge_seed_finishes_two_canonical_histories_before_material(
    harness, monkeypatch
):
    worker, data = harness.worker, human_knowledge_seed(harness)
    other = worker.event("happy", "main")
    monkeypatch.setattr(worker, "seed_events", lambda: iter((*data.values, other)))

    async def material(*args):
        assert len(set(data.observed)) == 2
        assert {proof.turn_id for proof in data.proofs} == {c.turn_id for c in data.consumers}
        assert worker.counters("knowledge") == {"calls": 0, "effects": 0}
        data.events.append(("material", None))
        return 0

    monkeypatch.setattr(worker, "seed_material", material)
    original_ingest = data.kernel.ingest_event.side_effect
    original_claim = data.kernel.claim_job.side_effect
    happy = SimpleNamespace(code="ACCEPTED", job_id=uuid4(), inbox_id=uuid4())
    happy_claim = SimpleNamespace(kind="PROCESS_INBOX", job_id=happy.job_id)

    async def ingest(source, value, correlation):
        if value is other:
            assert data.events[-1][0] == "material"
            data.events.append(("happy", None))
            return happy
        return await original_ingest(source, value, correlation)

    async def claim(name):
        return happy_claim if name == "m24-browser-seed" else await original_claim(name)

    data.kernel.ingest_event.side_effect = ingest
    data.kernel.claim_job.side_effect = claim
    result = await worker.seed(data.kernel, data.ordinary, data.adapter)
    assert result == {"processed": 3, "seed_turns": 4}
    assert data.kernel.ingest_event.await_count == 3
    assert len(data.observed) == len(set(data.observed)) == 2
    assert data.events.index(("material", None)) > max(
        i for i, e in enumerate(data.events) if e[0] == "observe"
    )
    assert data.ordinary.execute.await_args_list[-1].args == (happy_claim,)
    assert data.adapter.calls == data.adapter.effects == 0


@pytest.mark.parametrize(
    "fault",
    ["ai_worker", "foreign_workspace", "foreign_connection", "wrong_inbox", "send", "guarded_turn"],
)
async def test_human_knowledge_seed_refuses_unexpected_work_before_dispatch(harness, fault):
    data, worker = human_knowledge_seed(harness), harness.worker
    rejected = data.inbox_claims[0]
    if fault == "ai_worker":
        data.ordinary.ai = object()
    elif fault == "foreign_workspace":
        rejected.workspace_id = uuid4()
    elif fault == "foreign_connection":
        rejected = data.inbox_claims[1]
        rejected.connection_id = uuid4()
    elif fault == "wrong_inbox":
        rejected.inbox_id = uuid4()
    elif fault == "send":
        rejected.kind = "SEND_AI_TEXT"
    else:
        rejected.kind, rejected.step = "PROCESS_TURN", "GUARDED_TEXT"
    with pytest.raises(worker.ProvisioningError):
        await worker.seed_knowledge(data.kernel, data.ordinary, data.adapter, data.values)
    if fault == "ai_worker":
        data.kernel.ingest_event.assert_not_awaited()
        data.kernel.claim_job.assert_not_awaited()
    assert rejected not in data.executed
    assert data.observed == []
    assert worker.counters("knowledge") == {"calls": 0, "effects": 0}


@pytest.mark.parametrize(
    "field",
    [
        "code",
        "job_id",
        "workspace_id",
        "connection_id",
        "turn_id",
        "turn_revision",
        "consumer",
        "member_count",
        "ready_file_count",
        "duplicate_turn",
    ],
)
async def test_human_knowledge_seed_requires_two_separate_exact_observation_proofs(harness, field):
    data, worker = human_knowledge_seed(harness), harness.worker
    target = data.proofs[1]
    if field == "duplicate_turn":
        data.consumers[1].turn_id = target.turn_id = data.proofs[0].turn_id
    elif field in {"member_count", "ready_file_count"}:
        setattr(target.result, field, 2)
    elif field == "code":
        target.code = "STALE"
    elif field == "turn_revision":
        target.turn_revision += 1
    elif field == "consumer":
        target.consumer = "OTHER_CONSUMER"
    else:
        setattr(target, field, uuid4())
    with pytest.raises(worker.ProvisioningError, match="Canonical HUMAN seed observation required"):
        await worker.seed_knowledge(data.kernel, data.ordinary, data.adapter, data.values)
    assert data.kernel.replay_turn.await_count == 2
    assert worker.counters("knowledge") == {"calls": 0, "effects": 0}


@pytest.mark.parametrize(
    "effect", ["adapter_calls", "adapter_effects", "ledger_call", "ledger_effect"]
)
async def test_human_knowledge_seed_rejects_effect_evidence_even_after_valid_proofs(
    harness, effect
):
    data, worker = human_knowledge_seed(harness), harness.worker
    if effect.startswith("adapter_"):
        setattr(data.adapter, effect.removeprefix("adapter_"), 1)
    else:
        event = "CALL" if effect == "ledger_call" else "EFFECT"
        worker.ledger_path("knowledge").write_text(json.dumps({"event": event}) + "\n")
    with pytest.raises(worker.ProvisioningError, match="zero external effects"):
        await worker.seed_knowledge(data.kernel, data.ordinary, data.adapter, data.values)
    assert data.kernel.replay_turn.await_count == 2


async def test_human_knowledge_seed_never_catches_not_allowed_or_falls_back(harness):
    from asm.messaging.errors import Code, MessagingError

    data, worker = human_knowledge_seed(harness), harness.worker
    original = data.ordinary.execute.side_effect

    async def execute(claim):
        if claim is data.consumers[0]:
            raise MessagingError(Code.NOT_ALLOWED)
        await original(claim)

    data.ordinary.execute.side_effect = execute
    with pytest.raises(MessagingError, match="NOT_ALLOWED"):
        await worker.seed_knowledge(data.kernel, data.ordinary, data.adapter, data.values)
    data.kernel.replay_turn.assert_not_awaited()
    assert data.consumers[1] not in data.executed
    assert data.ordinary.ai is None


async def test_human_knowledge_seed_exhaustion_never_reports_one_proof_as_complete(
    harness, monkeypatch
):
    data, worker = human_knowledge_seed(harness), harness.worker
    data.queue.pop()  # One HUMAN history never reaches its canonical consumer.
    sleep = AsyncMock()
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(worker.ProvisioningError, match="did not complete"):
        await worker.seed_knowledge(data.kernel, data.ordinary, data.adapter, data.values)
    assert data.kernel.claim_job.await_count == 256
    assert data.kernel.replay_turn.await_count == 1
    assert sleep.await_count == 251
    assert worker.counters("knowledge") == {"calls": 0, "effects": 0}


@pytest.mark.parametrize("case", ["v3_owner", "v3_guarded_image"])
@pytest.mark.parametrize("pin", ["canonical", "foreign", "missing"])
async def test_knowledge_prepare_requires_canonical_question_membership_before_model(
    harness, monkeypatch, case, pin
):
    from asm.ai.fake import FakeAdapter
    from asm.ai.runtime_contracts import PreparedKnowledgeRun
    from asm.messaging.errors import Code, MessagingError
    from m5_knowledge_fixtures import knowledge_run
    from test_m4_context import fixture

    worker = harness.worker
    snapshot, binding = fixture(case)
    value = knowledge_run().model_dump(mode="json")
    value.update(snapshot=snapshot, binding=binding.model_dump(mode="json"))
    value["knowledge_pin"]["business_id"] = str(binding.business_id)
    value["active_projection"].update(
        workspace_id=str(binding.workspace_id), business_id=str(binding.business_id)
    )
    run = PreparedKnowledgeRun.model_validate_json(json.dumps(value))
    from uuid import UUID

    question = UUID(snapshot["members"][0]["message_id"])
    supplied = question if pin == "canonical" else uuid4() if pin == "foreign" else None
    prepare = AsyncMock(return_value=run)
    monkeypatch.setattr(worker.AIDatabase, "prepare", prepare)

    class Database(worker.KnowledgeBrowserDatabase):
        async def replay(self, *args, **kwargs):
            raise MessagingError(Code.STALE_CLAIM)

    database = Database(
        SimpleNamespace(question_message_id=supplied), environment="TEST", delivery=True
    )
    adapter = FakeAdapter(run.config.route)
    if pin == "canonical":
        result = await database.prepare(None, run.config, deadline=run.deadline)
        assert result is database.prepared is run
        assert result.snapshot is snapshot or result.snapshot == snapshot
    else:
        with pytest.raises(worker.ProvisioningError, match="Canonical browser question"):
            await database.execute(None, run.config, adapter, deadline=run.deadline)
        assert database.prepared is None
    assert adapter.requests == []


@pytest.mark.parametrize("shape", ["one_history", "other_chat", "image"])
async def test_human_knowledge_seed_shape_refuses_before_ingress(harness, shape):
    from dataclasses import replace

    data, worker = human_knowledge_seed(harness), harness.worker
    values = data.values
    if shape == "one_history":
        values = values[:1]
    elif shape == "other_chat":
        values = (replace(values[0], chat_id="another-client"), values[1])
    else:
        values = (replace(values[0], image_file_id="private-image", text=None), values[1])
    with pytest.raises(worker.ProvisioningError):
        await worker.seed_knowledge(data.kernel, data.ordinary, data.adapter, values)
    data.kernel.ingest_event.assert_not_awaited()
    data.kernel.claim_job.assert_not_awaited()
    data.ordinary.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "result", ["canonical", "foreign_inbox", "unprocessed", "missing_message", "other_claim"]
)
async def test_knowledge_question_pin_comes_only_from_its_canonical_inbox_processing(
    harness, monkeypatch, result
):
    worker = harness.worker
    kernel = object.__new__(worker.KnowledgeBrowserKernel)
    inbox, message = uuid4(), uuid4()
    kernel.question_inbox_id = inbox
    kernel.question_message_id = None
    claim = SimpleNamespace(inbox_id=uuid4() if result == "other_claim" else inbox)
    processed = SimpleNamespace(
        inbox_id=uuid4() if result == "foreign_inbox" else inbox,
        code="IGNORED" if result == "unprocessed" else "PROCESSED",
        message_id=None if result == "missing_message" else message,
    )
    base = AsyncMock(return_value=processed)
    monkeypatch.setattr(worker.MessagingDatabase, "process_inbox", base)
    if result in {"foreign_inbox", "unprocessed", "missing_message"}:
        with pytest.raises(worker.ProvisioningError, match="Canonical browser question processing"):
            await kernel.process_inbox(claim)
    else:
        assert await kernel.process_inbox(claim) is processed
    assert kernel.question_message_id == (message if result == "canonical" else None)
    base.assert_awaited_once_with(claim)


def test_worker_diagnostic_never_stringifies_sql_or_other_private_error_text(harness, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    class PrivateDatabaseError(SQLAlchemyError):
        def __str__(self):
            pytest.fail("Diagnostic tried to stringify private SQL/credentials")

    class PrivateInputError(ValueError):
        def __str__(self):
            pytest.fail("Diagnostic tried to stringify private payload")

    worker = harness.worker
    monkeypatch.setattr(worker, "_diagnostic", worker.BrowserDiagnostic(stage="MODEL"))
    for error, label in (
        (PrivateDatabaseError("SELECT PRIVATE_SENTINEL credential=synthetic"), "DATABASE"),
        (PrivateInputError("PAYLOAD_PRIVATE_SENTINEL"), "INPUT"),
    ):
        line = worker.diagnostic_line(error, "knowledge")
        assert f"stage=MODEL;class={label};code=NONE;" in line
        assert "SENTINEL" not in line and "SELECT" not in line and "credential" not in line
        assert "calls=UNKNOWN;effects=UNKNOWN;" in line
    assert worker.diagnostic_failure(PrivateInputError("PRIVATE"), "PRIVATE_STAGE") == (
        "ARGS",
        "INPUT",
        "NONE",
    )


async def test_worker_diagnostic_keeps_primary_not_allowed_when_cleanup_also_fails(
    harness, monkeypatch
):
    from asm.messaging.errors import Code, MessagingError
    from sqlalchemy.exc import SQLAlchemyError

    worker = harness.worker
    monkeypatch.setattr(worker, "_diagnostic", worker.BrowserDiagnostic())
    monkeypatch.setattr(worker, "target", lambda: ("unused-test-url", object()))
    cleanup = SQLAlchemyError("PRIVATE_SQL_CLEANUP_SENTINEL")
    engine = SimpleNamespace(dispose=AsyncMock(side_effect=cleanup))
    monkeypatch.setattr(worker, "create_async_engine", lambda *args, **kwargs: engine)
    guard = AsyncMock(side_effect=MessagingError(Code.NOT_ALLOWED))
    monkeypatch.setattr(worker, "guard", guard)
    with pytest.raises(SQLAlchemyError):
        await worker.action("happy", "success")
    line = worker.diagnostic_line(cleanup, "happy")
    assert "stage=GUARD;class=MESSAGING;code=NOT_ALLOWED;cleanup=DATABASE;" in line
    assert "SENTINEL" not in line and "PRIVATE_SQL" not in line
    engine.dispose.assert_awaited_once()
    assert not worker._diagnostic.ready


def test_worker_diagnostic_cannot_read_or_create_counters_before_validated_guard(
    harness, monkeypatch
):
    worker = harness.worker

    def forbidden(*args):
        pytest.fail("Unvalidated diagnostics touched counter files")

    monkeypatch.setattr(worker, "counters", forbidden)
    diagnostic = worker.BrowserDiagnostic(stage="GUARD", ready=False)
    monkeypatch.setattr(worker, "_diagnostic", diagnostic)
    assert list(harness.directory.iterdir()) == []
    line = worker.diagnostic_line(ValueError("PRIVATE_SENTINEL"), "knowledge")
    assert "calls=UNKNOWN;effects=UNKNOWN;" in line
    diagnostic.ready = True
    line = worker.diagnostic_line(ValueError("PRIVATE_SENTINEL"), "../../invalid-preset")
    assert "calls=UNKNOWN;effects=UNKNOWN;" in line
    assert list(harness.directory.iterdir()) == []


def test_worker_diagnostic_reports_only_bounded_counter_numbers_after_guard(harness, monkeypatch):
    worker = harness.worker
    diagnostic = worker.BrowserDiagnostic(stage="DRAIN", ready=True, model_calls=1)
    monkeypatch.setattr(worker, "_diagnostic", diagnostic)
    assert "calls=0;effects=0;model_calls=1;" in worker.diagnostic_line(
        ValueError("PRIVATE"), "happy"
    )
    assert (harness.directory / "happy.jsonl").exists()
    monkeypatch.setattr(
        worker, "counters", lambda preset: {"calls": True, "effects": "PRIVATE_SENTINEL"}
    )
    diagnostic.model_calls = 3
    line = worker.diagnostic_line(ValueError("PRIVATE"), "happy")
    assert "calls=UNKNOWN;effects=UNKNOWN;model_calls=UNKNOWN;" in line
    assert "SENTINEL" not in line


async def knowledge_observer_journey(harness, monkeypatch, *, before_guarded):
    """Real Worker/Gateway/fake/transport dispatch; controlled stores are not PG proof."""
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime
    from uuid import UUID

    from asm.ai.agent import KnowledgeConversationAgent
    from asm.ai.runtime_contracts import KnowledgeRuntimeReceipt
    from asm.conversations.turns import parse_snapshot
    from asm.messaging.errors import Code, MessagingError
    from asm.messaging.results import (
        AIJobClaim,
        AISendPermit,
        FinalizeResult,
        JobClaim,
        TurnJobClaim,
    )
    from m5_knowledge_fixtures import ControlledKnowledgeAuthority, knowledge_run

    worker = harness.worker
    run = knowledge_run().model_copy(update={"config": worker.knowledge_config()})
    question = uuid4()
    common = dict(
        workspace_id=run.binding.workspace_id,
        connection_id=run.binding.connection_id,
        claim_token=uuid4(),
        lease_until=run.deadline,
        correlation_id=uuid4(),
        attempt_count=1,
        inbox_id=None,
        outbox_id=None,
    )
    inbox = JobClaim(
        **(common | {"job_id": uuid4(), "kind": "PROCESS_INBOX", "inbox_id": question})
    )
    turn = common | {
        "kind": "PROCESS_TURN",
        "turn_id": run.binding.turn_id,
        "turn_revision": run.binding.turn_revision,
    }
    observer = TurnJobClaim(**(turn | {"job_id": uuid4(), "step": "TEST_CONSUME"}))
    source = TurnJobClaim(**(turn | {"job_id": uuid4(), "step": "GUARDED_TEXT"}))
    ai_claim = AIJobClaim(**(turn | {"job_id": run.binding.job_id, "step": "AI_GENERATE"}))
    send = JobClaim(**(common | {"job_id": uuid4(), "kind": "SEND_AI_TEXT", "outbox_id": uuid4()}))
    order = [inbox, observer, source, send] if before_guarded else [inbox, source, observer, send]
    actions, enrollments = [], []
    runtimes = []

    class Kernel:
        finalized = None
        question_message_id = None
        process_turn = AsyncMock(return_value=parse_snapshot(run.snapshot))
        finish_turn = AsyncMock()
        checkpoint = AsyncMock()
        telegram_probe = AsyncMock(return_value=None)

        @asynccontextmanager
        async def _transaction(self):
            yield SimpleNamespace(
                execute=AsyncMock(
                    return_value=SimpleNamespace(scalar_one=lambda: datetime.now(UTC))
                )
            )

        async def ingest_event(self, *args):
            return SimpleNamespace(
                code="ACCEPTED",
                inbox_id=question,
                workspace_id=inbox.workspace_id,
                job_id=inbox.job_id,
            )

        async def claim_knowledge(self, cutoff, *, ai=False):
            if ai:
                return ai_claim if enrollments and not runtimes[0].model_jobs else None
            return order.pop(0) if order else None

        async def process_inbox(self, claim):
            assert claim == inbox
            self.question_message_id = UUID(run.snapshot["members"][0]["message_id"])
            actions.append("inbox")

        async def enqueue_ai(self, claim):
            # An observer routed to the AI worker reproduces the old failure:
            # it must never become a second source for this admitted Turn.
            if claim != source or enrollments:
                raise MessagingError(Code.IDEMPOTENCY_KEY_CONFLICT)
            enrollments.append(claim)
            actions.append("enroll")

        async def begin_ai_send(self, claim, probe, observation):
            assert claim == send and probe is observation is None
            actions.append("send")
            return AISendPermit(
                code="PERMITTED",
                job_id=send.job_id,
                claim_token=send.claim_token,
                attempt_id=uuid4(),
                workspace_id=send.workspace_id,
                connection_id=send.connection_id,
                provider="CONTROLLED",
                bot_identity=worker.bot("knowledge"),
                external_connection_id=worker.route("knowledge"),
                chat_id="m24-knowledge-main",
                text=runtimes[0].database.receipt.result.text,
                ai_delivery=True,
            )

        async def finish_send(self, job, token, attempt, outcome):
            assert job == send.job_id and token == send.claim_token
            assert outcome.kind == OutcomeKind.SUCCESS
            self.finalized = FinalizeResult(
                code="FINALIZED",
                status="SENT",
                job_id=job,
                outbox_id=send.outbox_id,
                attempt_id=attempt,
            )
            return self.finalized

    kernel = Kernel()

    async def observe(claim):
        assert claim == observer
        actions.append("observe")
        return parse_snapshot(run.snapshot)

    kernel.process_turn.side_effect = observe

    class Database:
        def __init__(self, messaging, **kwargs):
            self.messaging, self.prepared, self.receipt = messaging, run, None

        async def replay(self, claim, config):
            assert claim == ai_claim and config == run.config and self.receipt is not None
            return self.receipt

    class Runtime:
        def __init__(self, messaging, config, factory, **kwargs):
            self.database = SimpleNamespace(messaging=messaging)
            self.config, self.factory = config, factory
            self.telegram = None
            self.model_jobs = []
            runtimes.append(self)

        async def enqueue(self, claim):
            await self.database.messaging.enqueue_ai(claim)

        async def execute(self, claim):
            assert claim == ai_claim and len(enrollments) == 1
            self.model_jobs.append(claim)
            actions.append("model")
            authority = ControlledKnowledgeAuthority(run, allowed=True)
            agent = KnowledgeConversationAgent(
                run.config,
                self.factory(),
                authority,
                knowledge_pin=run.knowledge_pin,
                active_projection=run.active_projection,
            )
            outcome = await agent.run(
                run.binding, run.snapshot, run_id=str(run.run_id), deadline=run.deadline
            )
            assert outcome.candidate is not None and outcome.candidate.kind == "reply"
            self.database.receipt = KnowledgeRuntimeReceipt(
                run_id=run.run_id,
                job_id=claim.job_id,
                turn_id=claim.turn_id,
                turn_revision=claim.turn_revision,
                selected_at=datetime.now(UTC),
                result=outcome.candidate,
                knowledge_pin=run.knowledge_pin,
            )

    monkeypatch.setattr(worker, "KnowledgeBrowserKernel", lambda *args, **kwargs: kernel)
    monkeypatch.setattr(worker, "KnowledgeBrowserDatabase", Database)
    monkeypatch.setattr(worker, "SyntheticRuntime", Runtime)
    monkeypatch.setattr(worker, "_diagnostic", worker.BrowserDiagnostic())
    result = await worker.knowledge_answer(None, AsyncMock())
    assert actions == (
        ["inbox", "observe", "enroll", "model", "send"]
        if before_guarded
        else ["inbox", "enroll", "model", "observe", "send"]
    )
    assert enrollments == [source] and runtimes[0].model_jobs == [ai_claim]
    kernel.process_turn.assert_awaited_once_with(observer)
    kernel.finish_turn.assert_awaited_once()
    assert kernel.finish_turn.await_args.args[0] == observer
    assert len(runtimes[0].factory().requests) == 1
    assert result["model_calls"] == result["calls"] == result["effects"] == 1
    assert result["answer"] == run.active_projection.bundle.faqs[0].answer
    assert worker.knowledge_journal().receipt == runtimes[0].database.receipt


async def test_knowledge_current_observer_before_guarded_source_never_enrolls(harness, monkeypatch):
    await knowledge_observer_journey(harness, monkeypatch, before_guarded=True)


async def test_knowledge_current_observer_after_ai_cannot_enroll_or_regenerate(
    harness, monkeypatch
):
    await knowledge_observer_journey(harness, monkeypatch, before_guarded=False)
