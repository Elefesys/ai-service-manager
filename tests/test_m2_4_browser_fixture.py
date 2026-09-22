"""M2-A10/A12: finite TEST harness guards; real journeys run in test_browser.sh."""

import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
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
        harness.fixture.bot(p) for p in harness.fixture.PRESETS
    }
    page = [e for e in values if e.bot_identity == harness.fixture.bot("pagination")]
    assert len({e.external_connection_id for e in page}) == 27
    assert len({e.chat_id for e in page}) == 28
    assert sum(e.chat_id == "m24-pagination-main" for e in page) > 25
    assert values[-1].image_file_id == "m24-image-pending"
    assert sum(e.image_file_id == "m24-image-pending" for e in values) == 1
    assert all(e.text is None or "e\u0301 🎨" in e.text for e in values)


@pytest.mark.parametrize("module", ["fixture", "worker"])
def test_unknown_cli_arguments_never_echo_payloads(harness, monkeypatch, capsys, module):
    monkeypatch.setattr(sys, "argv", ["fixture", "--arbitrary", "canary-secret-url-payload"])
    assert getattr(harness, module).main() == 1
    output = capsys.readouterr()
    assert output.out == "" and "canary" not in output.err
    assert output.err in {"M2_4_BROWSER_FIXTURE_FAILED\n", "M2_4_BROWSER_WORKER_FAILED\n"}
