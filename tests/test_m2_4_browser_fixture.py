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
    profile = dict(schema_revision="0013", valid=True, profile_sha256="b" * 64)
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
        "schema_revision": "0013",
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
                        dict(schema_revision="0013", valid=True, profile_sha256="b" * 64) | patch
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
