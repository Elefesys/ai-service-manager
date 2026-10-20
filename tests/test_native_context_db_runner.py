"""Runner refusal and real Settings regressions; never PostgreSQL runtime evidence."""

import asyncio
import copy
import importlib
import inspect
import json
import os
import re
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from scripts import native_context_db_catalog as lane

REQUIRED_MODULES = (
    "tests/test_m3_1_native_context_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_api_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
)


@pytest.fixture
def foundation_git(tmp_path, monkeypatch):
    """Constructed clean Git source and journals; no product fixtures or resources."""
    actual = lane.ROOT
    producer = lane.source_catalog
    root = tmp_path / "source"
    root.mkdir()
    for relative in (
        *lane.CI_INPUT_SHA256,
        "scripts/ci.sh",
        "scripts/native_context_db_catalog.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((actual / relative).read_bytes())
    (root / ".gitignore").write_text("reports/\n.env\n.pytest_cache/\n__pycache__/\n*.pyc\n")
    (root / "tests").mkdir()
    (root / "tests/test_constructed.py").write_text(
        "import pytest\n"
        "@pytest.fixture\ndef setup_bad():\n    raise ValueError('PRIVATE_SENTINEL_DSN_SQL')\n"
        "@pytest.fixture\ndef teardown_bad():\n    yield\n    raise RuntimeError('PRIVATE_SENTINEL_DSN_SQL')\n"
        "@pytest.mark.integration\ndef test_pass():\n    assert True\n"
        "@pytest.mark.integration\ndef test_call():\n    raise AssertionError('PRIVATE_SENTINEL_DSN_SQL')\n"
        "@pytest.mark.integration\ndef test_setup(setup_bad):\n    raise AssertionError('must not run')\n"
        "@pytest.mark.integration\ndef test_teardown(teardown_bad):\n    assert True\n"
    )

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Constructed",
                "-c",
                "user.email=unit@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=root,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "constructed source")
    for key in list(os.environ):
        if key.startswith(("GITHUB_", "ASM_FOUNDATION_")):
            monkeypatch.delenv(key)
    monkeypatch.setattr(lane, "ROOT", root)
    catalog = {
        "columns": {"app.messages": ["id"]},
        "functions": {"platform.safe_function()": {}},
        "nonfunction_ddl": [
            {
                "index": 0,
                "revision": "0001",
                "sql": "CREATE TABLE app.messages (id integer CONSTRAINT approved_check CHECK (id>0))",
            }
        ],
    }
    monkeypatch.setattr(lane, "source_catalog", lambda _: catalog)
    return SimpleNamespace(root=root, actual=actual, git=git, catalog=catalog, producer=producer)


@pytest.fixture
def foundation_sink(foundation_git, monkeypatch):
    path = lane.foundation_prepare("foundation-core")
    monkeypatch.setenv("ASM_FOUNDATION_EVIDENCE", str(path))
    monkeypatch.setenv("ASM_FOUNDATION_OWNER_UID", str(os.getuid()))
    monkeypatch.setenv(
        "ASM_FOUNDATION_BINDING_SHA256", lane.sha256((path / "binding.json").read_bytes())
    )
    return lane.foundation_store()


def foundation_rows(store, name="cases.jsonl"):
    return [json.loads(line) for line in store.read(name).splitlines()]


def constructed_report(phase, outcome="passed", duration=0.01):
    return SimpleNamespace(when=phase, outcome=outcome, duration=duration)


@pytest.fixture
def foundation_real_catalog_sink(foundation_git, monkeypatch, request):
    """Real migration expansion in an owned synthetic Git checkout; no database."""
    fixture = foundation_git
    paths = sorted((fixture.actual / "migrations/versions").glob("*.py"))
    assert len(paths) == 13
    for source in paths:
        target = fixture.root / source.relative_to(fixture.actual)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        assert target.read_bytes() == source.read_bytes()
    fixture.git("add", "migrations")
    fixture.git("commit", "-qm", "actual migration source for local formatter checks")
    monkeypatch.setattr(lane, "source_catalog", fixture.producer)
    assert lane.source_catalog is fixture.producer
    return request.getfixturevalue("foundation_sink")


@pytest.mark.parametrize(
    "constraint",
    ("conversations_control_mode_check", "conversation_control_receipts_audit_fk", "private_guess"),
)
def test_foundation_real_catalog_constraint_whitelist(constraint):
    from psycopg.errors import CheckViolation
    from psycopg.pq import DiagnosticField as D

    catalog = lane.source_catalog(lane.ROOT)
    assert len(catalog["nonfunction_ddl"]) == 717
    assert all(set(row) == {"index", "revision", "sql"} for row in catalog["nonfunction_ddl"])
    before = copy.deepcopy(catalog)
    error = CheckViolation(
        "PRIVATE_SENTINEL_DSN_SQL",
        info={
            D.SQLSTATE: b"23514",
            D.SCHEMA_NAME: b"app",
            D.TABLE_NAME: b"conversations",
            D.CONSTRAINT_NAME: constraint.encode(),
            D.CONTEXT: b"PL/pgSQL function platform.human_context_schema_profile() line 7 at PRIVATE_SENTINEL_DSN_SQL",
        },
    )
    value = lane.foundation_failure(error, {}, catalog)
    row = value["chain"][0]
    assert row["exception"] == "CheckViolation" and row["sqlstate"] == "23514"
    assert row["schema"] == "app" and row["table"] == "conversations"
    assert row["constraint"] == ("UNKNOWN" if constraint == "private_guess" else constraint)
    assert row["plpgsql_frames"] == [
        {"function": "platform.human_context_schema_profile", "line": 7}
    ]
    raw = json.dumps(value, ensure_ascii=True).encode()
    assert raw.isascii() and len(raw) <= 3400 and b"PRIVATE_SENTINEL" not in raw
    assert b"private_guess" not in raw and catalog == before


@pytest.mark.parametrize("phase", ("setup", "call", "teardown"))
@pytest.mark.parametrize("fault", (None, "write", "fsync"))
def test_foundation_real_catalog_failed_phase_journal(foundation_real_catalog_sink, phase, fault):
    store = foundation_real_catalog_sink
    node = "tests/test_constructed.py::test_call"
    journal = lane.GenericJournal(store, [node])
    assert len(journal.catalog["nonfunction_ddl"]) == 717
    journal.start(node)
    append = store.append

    def append_failure(name, value):
        if name == "failures.jsonl" and fault:
            with patch.object(lane.os, fault, side_effect=OSError("PRIVATE_SENTINEL_DSN_SQL")):
                return append(name, value)
        return append(name, value)

    phases = [p for p in ("setup", "call", "teardown") if not (phase == "setup" and p == "call")]
    with patch.object(store, "append", side_effect=append_failure):
        for current in phases:
            journal.report(
                node,
                constructed_report(current, "failed" if current == phase else "passed"),
                AssertionError("PRIVATE_SENTINEL_DSN_SQL") if current == phase else None,
            )
            if current == phase:
                # Failure bytes are persisted immediately, before finish/terminal summary.
                assert not store.read("generic-result.json")
                assert len(foundation_rows(store, "failures.jsonl")) == (
                    0 if fault == "write" else 1
                )
    journal.finish(7)
    assert json.loads(store.read("generic-result.json")) == {
        "pytest_exit": 7,
        "complete": True,
        "evidence_failed": fault is not None,
        "expected": 1,
        "completed": 1,
    }
    rows = foundation_rows(store)
    assert [(r["event"], r.get("phase")) for r in rows] == [
        ("start", None),
        *(("phase", p) for p in phases),
        ("case-end", None),
    ]
    assert rows[-1]["outcome"] == "FAILED"
    assert [r["sequence"] for r in rows] == list(range(1, len(rows) + 1))
    failures = foundation_rows(store, "failures.jsonl")
    assert [r["sequence"] for r in failures] == list(range(1, len(failures) + 1))
    assert all(
        r["index"] == 0 and r["nodeid_sha256"] == lane.sha256(node.encode())
        for r in rows + failures
    )
    if failures:
        assert failures[0]["phase"] == phase
        assert failures[0]["failure"]["chain"][0]["exception"] == "AssertionError"
    for name in ("cases.jsonl", "failures.jsonl", "issues.jsonl"):
        raw = store.read(name)
        assert not raw or (raw.isascii() and raw.endswith(b"\n"))
        assert all(len(line) + 1 <= 4096 for line in raw.splitlines())
        assert b"PRIVATE_SENTINEL" not in raw
    assert bool(store.read("issues.jsonl")) == (fault is not None)
    if fault:
        with pytest.raises(lane.Refusal, match="Foundation evidence sink failed"):
            lane.foundation_check(store)
    else:
        # A successfully recorded failed test still cannot pass the strict gate.
        for p in (*lane.FOUNDATION_HOST, *lane.FOUNDATION_CORE, "cleanup"):
            store.append("host.jsonl", {"phase": p, "edge": "start"})
            store.append("host.jsonl", {"phase": p, "edge": "end", "status": 0})
        store.publish("execution.json", {"primary_exit": 7, "cleanup_exit": 0})
        with pytest.raises(lane.Refusal, match="Foundation execution/cleanup failed"):
            lane.foundation_check(store)


@pytest.mark.parametrize(
    "fault",
    (
        "missing",
        "strings",
        "empty",
        "tuple",
        "missing-sql",
        "sql-type",
        "empty-sql",
        "index",
        "revision",
        "extra",
    ),
)
def test_foundation_real_catalog_malformed_records_refuse(fault):
    catalog = lane.source_catalog(lane.ROOT)
    if fault == "missing":
        del catalog["nonfunction_ddl"]
    elif fault == "strings":
        catalog["nonfunction_ddl"] = [row["sql"] for row in catalog["nonfunction_ddl"]]
    elif fault == "empty":
        catalog["nonfunction_ddl"] = []
    elif fault == "tuple":
        catalog["nonfunction_ddl"] = tuple(catalog["nonfunction_ddl"])
    else:
        row = catalog["nonfunction_ddl"][0]
        if fault == "missing-sql":
            del row["sql"]
        else:
            key, value = {
                "sql-type": ("sql", None),
                "empty-sql": ("sql", " "),
                "index": ("index", True),
                "revision": ("revision", "PRIVATE_SENTINEL"),
                "extra": ("extra", "PRIVATE_SENTINEL"),
            }[fault]
            row[key] = value
    expected = KeyError if fault == "missing" else lane.Refusal
    with pytest.raises(expected) as caught:
        lane.foundation_failure(AssertionError("PRIVATE_SENTINEL"), {}, catalog)
    assert caught.value.args == (
        "nonfunction_ddl" if fault == "missing" else "Foundation source DDL records",
    )


def test_foundation_real_catalog_pytest_reports(foundation_real_catalog_sink, monkeypatch):
    store = foundation_real_catalog_sink
    # Each nested pytest run imports its own synthetic module under the same
    # name. Restore that one cache entry on teardown, including failed checks.
    monkeypatch.setitem(lane.sys.modules, "test_constructed", None)
    del lane.sys.modules["test_constructed"]
    nodes = [
        "tests/test_constructed.py::test_" + name for name in ("pass", "call", "setup", "teardown")
    ]

    def proof(private, evidence, commands, env):
        a, n, g = partition_fixture()
        a["nodeids"] = nodes + n["integration_nodeids"]
        a["integration_nodeids"] = a["nodeids"][:]
        g["nodeids"] = g["integration_nodeids"] = nodes[:]
        result = lane.validate_partition(a, n, g)
        for name, data in (
            ("partition-all-pg.json", a),
            ("partition-native.json", n),
            ("partition-generic-pg.json", g),
            ("integration-partition.json", result),
        ):
            lane.write_json(private / name, data)
        return result, nodes

    monkeypatch.setattr(lane, "prove_partition", proof)
    monkeypatch.chdir(lane.ROOT)
    assert lane.generic_integration() == 1
    assert json.loads(store.read("generic-result.json")) == {
        "pytest_exit": 1,
        "complete": True,
        "evidence_failed": False,
        "expected": 4,
        "completed": 4,
    }
    assert not store.read("issues.jsonl")
    rows, failures = foundation_rows(store), foundation_rows(store, "failures.jsonl")
    assert [r["sequence"] for r in rows] == list(range(1, 20))
    assert [(r["index"], r["phase"], r["sequence"]) for r in failures] == [
        (1, "call", 1),
        (2, "setup", 2),
        (3, "teardown", 3),
    ]
    assert [r["failure"]["chain"][0]["exception"] for r in failures] == [
        "AssertionError",
        "ValueError",
        "RuntimeError",
    ]
    assert [(r["index"], r["event"], r.get("phase")) for r in rows] == [
        (i, event, phase)
        for i in range(4)
        for event, phase in (
            ("start", None),
            ("phase", "setup"),
            ("phase", "call"),
            ("phase", "teardown"),
            ("case-end", None),
        )
        if not (i == 2 and phase == "call")
    ]
    assert [r["outcome"] for r in rows if r["event"] == "case-end"] == [
        "PASSED",
        "FAILED",
        "FAILED",
        "FAILED",
    ]
    assert all(
        r["nodeid_sha256"] == lane.sha256(nodes[r["index"]].encode()) for r in rows + failures
    )
    for name in ("cases.jsonl", "failures.jsonl"):
        raw = store.read(name)
        assert raw.isascii() and raw.endswith(b"\n") and b"PRIVATE_SENTINEL" not in raw
        assert all(len(line) + 1 <= 4096 for line in raw.splitlines())


def test_foundation_workflow_has_eleven_required_jobs_serial_source_and_always_gates():
    source = (lane.ROOT / ".github/workflows/ci.yml").read_text()
    parts = re.split(r"^  ([a-z0-9-]+):\n", source.split("jobs:\n", 1)[1], flags=re.M)
    jobs = dict(zip(parts[1::2], parts[2::2], strict=True))
    assert set(jobs) == {
        "browser",
        "foundation-durable",
        "foundation",
        "docker29-compatibility",
        "connect5-migration",
        "native-context-db",
    }
    assert len(jobs) - 1 + 6 == 11
    for job, digest in {
        "browser": "b3ab2a96b6f7f8eb3a3b726b9769d756a55bd50694b3f21be8779aabcc87c3db",
        "docker29-compatibility": "37ecbf897d53f318f3d0e2192b05574923e6e9ed7a6bbd421aa6eecddff055b1",
        "connect5-migration": "c624af64b59752a4889032d4bbbbb729fe5732f99733199a2b590e2b942df645",
        "native-context-db": "ab14f25d082e830a8be35422a7ae4f0fc7d8f7092ec992fcbde703751b2fe78b",
    }.items():
        assert lane.sha256(jobs[job].encode()) == digest
    assert "needs: [foundation-durable]" in jobs["foundation"]
    for job, cap, route in (
        ("foundation-durable", 25, "normal-durable"),
        ("foundation", 45, "foundation-core"),
    ):
        block = jobs[job]
        assert (
            f"timeout-minutes: {cap}" in block
            and f"sh scripts/ci.sh --{route} 2>&1 | tee reports/ci.log" in block
        )
        assert "ref:" not in block and "continue-on-error" not in block
        assert block.count("if: always()") == 4
        assert (
            "foundation-check" in block and "git status --porcelain --untracked-files=all" in block
        )
    lane.require_ci_inputs()


def test_foundation_preparation_binds_clean_source_private_inodes_and_no_adoption(foundation_sink):
    store = foundation_sink
    assert (
        store.binding["identity"]["head"]
        == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lane.ROOT, text=True).strip()
    )
    assert store.binding["identity"]["parents"] == []
    assert store.binding["source_identity_is_runtime_approval"] is False
    assert store.binding["project"].startswith("asm-foundation-foundation-core-")
    for name in lane.FOUNDATION_FILES:
        info = (store.path / name).stat()
        assert info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o600 and info.st_nlink == 1
    assert store.path.stat().st_mode & 0o777 == 0o700
    with pytest.raises(lane.Refusal, match="adopted"):
        lane.foundation_prepare("foundation-core")


@pytest.mark.parametrize(
    "fault",
    (
        "uid",
        "digest",
        "directory-mode",
        "file-mode",
        "file-inode",
        "symlink",
        "hardlink",
        "outside",
    ),
)
def test_foundation_refuses_foreign_or_replaced_evidence_before_any_command(
    foundation_sink, monkeypatch, tmp_path, fault
):
    store = foundation_sink
    sentinel = tmp_path / "unrelated"
    sentinel.write_text("private sentinel must remain unchanged")
    if fault == "uid":
        monkeypatch.setenv("ASM_FOUNDATION_OWNER_UID", str(os.getuid() + 1))
    elif fault == "digest":
        monkeypatch.setenv("ASM_FOUNDATION_BINDING_SHA256", "0" * 64)
    elif fault == "directory-mode":
        store.path.chmod(0o755)
    elif fault == "file-mode":
        (store.path / "cases.jsonl").chmod(0o644)
    elif fault == "file-inode":
        p = store.path / "cases.jsonl"
        p.rename(store.path / "old-cases")
        p.touch(mode=0o600)
    elif fault == "symlink":
        p = store.path / "cases.jsonl"
        p.unlink()
        p.symlink_to(sentinel)
    elif fault == "hardlink":
        os.link(store.path / "cases.jsonl", store.path / "alias")
    elif fault == "outside":
        monkeypatch.setenv("ASM_FOUNDATION_EVIDENCE", str(tmp_path))
    with patch.object(lane.subprocess, "Popen") as commands:
        with pytest.raises((lane.Refusal, OSError)):
            lane.foundation_step("host", "init", ["must-never-start"])
    commands.assert_not_called()
    assert sentinel.read_text() == "private sentinel must remain unchanged"


def test_foundation_parent_symlink_and_dirty_source_refuse_before_prepare(foundation_git, tmp_path):
    frozen = lane.require_source(foundation_git.root, foundation_git.git("rev-parse", "HEAD"))
    reports = foundation_git.root / "reports"
    reports.symlink_to(tmp_path, target_is_directory=True)
    with (
        patch.object(lane, "require_source", return_value=frozen),
        pytest.raises(lane.Refusal, match="Symlinked reports"),
    ):
        lane.foundation_prepare("all")
    reports.unlink()
    (foundation_git.root / "untracked.py").write_text("private = 1\n")
    with pytest.raises(lane.Refusal, match="dirty"):
        lane.foundation_prepare("all")


def test_foundation_changed_copied_input_refuses_even_if_host_binding_is_retained(foundation_sink):
    (lane.ROOT / "scripts/check_backend.sh").write_text("exit 0\n")
    with pytest.raises(lane.Refusal, match="CI gate input drift"):
        lane.foundation_store()


def test_foundation_live_start_phases_durations_and_completion_are_persisted_before_summary(
    foundation_sink,
):
    node = "tests/test_constructed.py::test_pass"
    journal = lane.GenericJournal(foundation_sink, [node])
    with patch.object(lane.os, "fsync", wraps=os.fsync) as synced:
        journal.start(node)
        assert foundation_rows(foundation_sink)[0]["event"] == "start"
        assert not foundation_sink.read("generic-result.json")
        for i, phase in enumerate(("setup", "call", "teardown")):
            journal.report(node, constructed_report(phase), None)
            rows = foundation_rows(foundation_sink)
            assert len([r for r in rows if r["event"] == "phase"]) == i + 1
            assert len([r for r in rows if r["event"] == "case-end"]) == int(phase == "teardown")
        assert synced.call_count == 5
    rows = foundation_rows(foundation_sink)
    assert rows[-1]["outcome"] == "PASSED"
    assert all(
        row["index"] == 0 and row["nodeid_sha256"] == lane.sha256(node.encode()) for row in rows
    )
    assert [r["sequence"] for r in rows] == list(range(1, 6))
    assert all(r["duration"] == 0.01 for r in rows if r["event"] == "phase")
    journal.finish(0)
    assert json.loads(foundation_sink.read("generic-result.json"))["complete"] is True


@pytest.mark.parametrize("phase", ("setup", "call", "teardown"))
def test_foundation_failed_phase_uses_same_exception_and_preserves_status(foundation_sink, phase):
    node = "tests/test_constructed.py::test_call"
    journal = lane.GenericJournal(foundation_sink, [node])
    journal.start(node)
    error = ValueError("PRIVATE_SENTINEL_DSN_SQL")
    for current in ("setup", "call", "teardown"):
        if phase == "setup" and current == "call":
            continue
        journal.report(
            node,
            constructed_report(current, "failed" if current == phase else "passed"),
            error if current == phase else None,
        )
    journal.finish(7)
    result = json.loads(foundation_sink.read("generic-result.json"))
    assert result["pytest_exit"] == 7 and result["complete"] is True
    assert foundation_rows(foundation_sink)[-1]["outcome"] == "FAILED"
    failures = foundation_rows(foundation_sink, "failures.jsonl")
    assert len(failures) == 1 and failures[0]["phase"] == phase
    assert failures[0]["failure"]["chain"][0]["exception"] == "ValueError"
    assert "PRIVATE_SENTINEL" not in foundation_sink.read("failures.jsonl").decode()


@pytest.mark.parametrize("until", ("start", "setup", "call"))
def test_foundation_interruption_never_fabricates_teardown_or_case_completion(
    foundation_sink, until
):
    node = "tests/test_constructed.py::test_pass"
    journal = lane.GenericJournal(foundation_sink, [node])
    journal.start(node)
    for phase in ("setup", "call")[: (0 if until == "start" else 1 if until == "setup" else 2)]:
        journal.report(node, constructed_report(phase), None)
    assert not any(row["event"] == "case-end" for row in foundation_rows(foundation_sink))
    assert not foundation_sink.read("generic-result.json")
    # If pytest itself returns after interruption, only its incomplete receipt is added.
    journal.finish(2)
    assert json.loads(foundation_sink.read("generic-result.json"))["complete"] is False


@pytest.mark.parametrize("fault", ("nan", "negative", "duplicate", "unknown", "skip", "xfail"))
def test_foundation_invalid_or_nonpassing_phase_cannot_create_complete_green_evidence(
    foundation_sink, fault
):
    node = "tests/test_constructed.py::test_pass"
    journal = lane.GenericJournal(foundation_sink, [node])
    journal.start(node)
    for phase in ("setup", "call", "teardown"):
        report = constructed_report(phase)
        if phase == "call":
            if fault == "nan":
                report.duration = float("nan")
            elif fault == "negative":
                report.duration = -1
            elif fault == "unknown":
                report.when = "untrusted"
            elif fault == "skip":
                report.outcome = "skipped"
            elif fault == "xfail":
                report.wasxfail = "PRIVATE_SENTINEL"
        journal.report(node, report, None)
        if phase == "setup" and fault == "duplicate":
            journal.report(node, report, None)
    journal.finish(0)
    result = json.loads(foundation_sink.read("generic-result.json"))
    assert result["evidence_failed"] or not result["complete"]


def test_foundation_torn_record_and_io_limit_are_explicit_never_repaired(
    foundation_sink, monkeypatch
):
    path = foundation_sink.path / "cases.jsonl"
    path.write_bytes(b'{"incomplete":')
    node = "tests/test_constructed.py::test_pass"
    journal = lane.GenericJournal(foundation_sink, [node])
    journal.start(node)
    assert path.read_bytes() == b'{"incomplete":'
    assert journal.failed and foundation_sink.read("issues.jsonl")
    monkeypatch.setattr(lane, "FOUNDATION_LIMIT", 1)
    with pytest.raises(lane.Refusal, match="limit"):
        foundation_sink.append("backend.jsonl", {"event": "test"})


def test_foundation_partial_write_and_fsync_failure_cannot_be_hidden(foundation_sink):
    original_write = os.write
    with patch.object(lane.os, "write", side_effect=lambda fd, raw: original_write(fd, raw[:5])):
        with pytest.raises(lane.Refusal, match="Partial"):
            foundation_sink.append("cases.jsonl", {"event": "start"})
    assert not foundation_sink.read("cases.jsonl").endswith(b"\n")
    with patch.object(lane.os, "fsync", side_effect=OSError("PRIVATE_SENTINEL")):
        with pytest.raises(OSError):
            foundation_sink.append("backend.jsonl", {"event": "start"})


def test_foundation_bounded_failure_metadata_never_formats_hostile_values(foundation_git):
    class Forbidden:
        def __str__(self):
            raise AssertionError("must not stringify")

        def __repr__(self):
            raise AssertionError("must not repr")

    error = ValueError(Forbidden())
    error.sqlstate = "23514"
    error.diag = SimpleNamespace(
        schema_name="app",
        table_name="messages",
        constraint_name="approved_check",
        context="PL/pgSQL function platform.safe_function() line 7 at PRIVATE_SENTINEL_DSN_SQL",
    )
    error.orig = error
    value = lane.foundation_failure(error, {}, foundation_git.catalog)
    raw = json.dumps(value)
    assert "PRIVATE_SENTINEL" not in raw
    node = value["chain"][0]
    assert node["exception"] == "ValueError" and node["sqlstate"] == "23514"
    assert node["constraint"] == "approved_check" and node["table"] == "messages"
    assert node["plpgsql_frames"] == [{"function": "platform.safe_function", "line": 7}]
    for field in ("schema_name", "table_name", "constraint_name", "context"):
        setattr(error.diag, field, Forbidden())
    error.sqlstate = Forbidden()
    other = lane.foundation_failure(error, {}, foundation_git.catalog)
    assert other["chain"][0]["sqlstate"] == "UNKNOWN"
    assert other["chain"][0]["constraint"] == "UNKNOWN"


def test_foundation_failure_chain_frames_and_encoded_record_are_bounded(
    foundation_sink, foundation_git
):
    source = lane.ROOT / "tests/test_constructed.py"
    namespace = {"__name__": "constructed"}
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    try:
        namespace["test_call"]()
    except AssertionError as error:
        first = error
    cursor = first
    for _ in range(8):
        following = RuntimeError("PRIVATE_SENTINEL_DSN_SQL")
        cursor.orig = following
        cursor = following
    cursor.orig = first
    locations = lane.foundation_locations(foundation_sink.binding["source_manifest"])
    value = lane.foundation_failure(first, locations, foundation_git.catalog)
    assert len(value["chain"]) == 4 and value["chain_limited"]
    assert value["chain"][0]["python_frames"][-1] == {
        "path": "tests/test_constructed.py",
        "function": "test_call",
        "line": 14,
    }
    foundation_sink.append(
        "failures.jsonl", {"index": 0, "nodeid_sha256": "a" * 64, "phase": "call", "failure": value}
    )
    raw = foundation_sink.read("failures.jsonl")
    assert len(raw) <= 4096 and raw.isascii() and "PRIVATE_SENTINEL" not in raw.decode()


def test_foundation_formatter_and_reporter_do_not_swallow_baseexception(foundation_sink):
    node = "tests/test_constructed.py::test_pass"
    journal = lane.GenericJournal(foundation_sink, [node])
    with patch.object(foundation_sink, "append", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            journal.start(node)


def test_foundation_actual_constructed_pytest_reports_retained_before_terminal_summary(
    foundation_sink, foundation_git, monkeypatch
):
    nodes = [
        "tests/test_constructed.py::test_" + name for name in ("pass", "call", "setup", "teardown")
    ]

    def proof(private, evidence, commands, env):
        a, n, g = partition_fixture()
        a["nodeids"] = nodes + n["integration_nodeids"]
        a["integration_nodeids"] = a["nodeids"][:]
        g["nodeids"] = g["integration_nodeids"] = nodes[:]
        result = lane.validate_partition(a, n, g)
        for name, data in (
            ("partition-all-pg.json", a),
            ("partition-native.json", n),
            ("partition-generic-pg.json", g),
            ("integration-partition.json", result),
        ):
            lane.write_json(private / name, data)
        return result, nodes

    monkeypatch.setattr(lane, "prove_partition", proof)
    monkeypatch.chdir(lane.ROOT)
    with patch.object(lane.GenericJournal, "finish", autospec=True, wraps=None) as finish:
        assert lane.generic_integration() == 1
        assert not foundation_sink.read("generic-result.json")
        assert finish.call_args.args[1] == 1
    failures = foundation_rows(foundation_sink, "failures.jsonl")
    assert [row["phase"] for row in failures] == ["call", "setup", "teardown"]
    assert [row["failure"]["chain"][0]["exception"] for row in failures] == [
        "AssertionError",
        "ValueError",
        "RuntimeError",
    ]
    assert [
        row["outcome"] for row in foundation_rows(foundation_sink) if row["event"] == "case-end"
    ] == ["PASSED", "FAILED", "FAILED", "FAILED"]
    assert b"PRIVATE_SENTINEL" not in foundation_sink.read("failures.jsonl")


def foundation_complete_fixture(store):
    a, n, g = partition_fixture()
    proof = lane.validate_partition(a, n, g)
    route = store.binding["route"]
    host = (
        *lane.FOUNDATION_HOST,
        *(("normal-durable",) if route != "foundation-core" else ()),
        *(lane.FOUNDATION_CORE if route != "normal-durable" else ()),
        "cleanup",
    )
    for stream, phases in (
        ("host", host),
        ("backend", lane.FOUNDATION_BACKEND if route != "normal-durable" else ()),
    ):
        for phase in phases:
            store.append(stream + ".jsonl", {"phase": phase, "edge": "start"})
            store.append(stream + ".jsonl", {"phase": phase, "edge": "end", "status": 0})
    if route == "normal-durable":
        store.publish("execution.json", {"primary_exit": 0, "cleanup_exit": 0})
        return
    for name, data in (
        ("partition-all-pg.json", a),
        ("partition-native.json", n),
        ("partition-generic-pg.json", g),
        ("integration-partition.json", proof),
    ):
        store.publish(name, data)
    journal = lane.GenericJournal(store, g["nodeids"])
    for node in g["nodeids"]:
        journal.start(node)
        for phase in ("setup", "call", "teardown"):
            journal.report(node, constructed_report(phase), None)
    journal.finish(0)
    store.publish("execution.json", {"primary_exit": 0, "cleanup_exit": 0})


@pytest.mark.parametrize(
    "fault",
    (
        None,
        "missing-phase",
        "duplicate-phase",
        "missing-case",
        "torn",
        "exit",
        "cleanup",
        "issue",
        "clock",
        "identity",
        "fake-end",
    ),
)
def test_foundation_separate_completeness_gate_requires_full_actual_evidence(
    foundation_sink, fault
):
    store = foundation_sink
    foundation_complete_fixture(store)
    if fault is None:
        lane.foundation_check(store)
        return
    name = "cases.jsonl"
    rows = foundation_rows(store)
    if fault == "missing-phase":
        rows.pop(2)
    elif fault == "duplicate-phase":
        rows.insert(2, rows[1])
    elif fault == "missing-case":
        rows = rows[:5]
    elif fault == "clock":
        rows[-1]["elapsed"] = -1
    elif fault == "identity":
        rows[2]["nodeid_sha256"] = "f" * 64
    elif fault == "fake-end":
        rows[1]["event"] = "case-end"
    elif fault == "torn":
        with (store.path / name).open("ab") as output:
            output.write(b'{"partial":')
    elif fault in {"exit", "cleanup"}:
        (store.path / "execution.json").write_text(
            json.dumps(
                {
                    "primary_exit": 7 if fault == "exit" else 0,
                    "cleanup_exit": 23 if fault == "cleanup" else 0,
                }
            )
        )
    elif fault == "issue":
        store.issue()
    if fault not in {"exit", "cleanup", "issue", "torn"}:
        for i, row in enumerate(rows, 1):
            row["sequence"] = i
        (store.path / name).write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(lane.Refusal):
        lane.foundation_check(store)


@pytest.fixture
def foundation_commands(foundation_git, tmp_path, monkeypatch):
    """All Docker/shell/build/test invocations are inert local command stubs."""
    import sys

    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "commands.jsonl"
    program = (
        "#!"
        + sys.executable
        + "\n"
        + r"""
import json, os, pathlib, signal, sys
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as output:
    output.write(json.dumps({'name': name, 'args': args, 'epoch': os.environ.get('SOURCE_DATE_EPOCH'), 'project': os.environ.get('COMPOSE_PROJECT_NAME')}) + '\n')
if name in {'python', 'python3'} and args[:1] == ['scripts/native_context_db_catalog.py'] and len(args)>1 and args[1].startswith('foundation-'):
    if args[1] == 'foundation-check':
        # Routing probe only. Actual completeness is tested with real records separately.
        sys.exit(int(os.environ.get('FAKE_COMPLETENESS_STATUS', '0')))
    os.execv(sys.executable, [sys.executable, *args])
if name == 'sha256sum' and args and args[0].endswith('/binding.json'):
    import hashlib
    print(hashlib.sha256(pathlib.Path(args[0]).read_bytes()).hexdigest()+'  '+args[0])
    sys.exit(0)
stage = 'other'
if name == 'docker':
    stage = 'build' if 'build' in args else 'checks' if 'run' in args and args[-1]=='checks' else 'cleanup' if 'down' in args else 'other'
elif name == 'sh': stage = 'durable'
elif name in {'python', 'python3'} and args == ['-']:
    pathlib.Path(os.environ['FAKE_SMOKE_CAPTURE']).write_text(sys.stdin.read())
    stage = 'http'
elif name in {'python', 'python3'} and args[-1:] == ['generic-integration']: stage = 'generic'
if stage == os.environ.get('FAKE_BLOCK'):
    pathlib.Path(os.environ['FAKE_MARKER']).write_text(str(os.getpid()))
    while True: signal.pause()
if stage == 'cleanup' and os.environ.get('FAKE_CLEANUP_STATUS'):
    sys.exit(int(os.environ['FAKE_CLEANUP_STATUS']))
sys.exit(17 if stage == os.environ.get('FAKE_FAIL') else 0)
"""
    )
    for name in (
        "python",
        "python3",
        "docker",
        "sh",
        "ruff",
        "mypy",
        "pytest",
        "alembic",
        "cmp",
        "sha256sum",
    ):
        p = binary / name
        p.write_text(program)
        p.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_LOG", str(log))
    marker = tmp_path / "blocked"
    monkeypatch.setenv("FAKE_MARKER", str(marker))
    smoke = tmp_path / "http-body"
    monkeypatch.setenv("FAKE_SMOKE_CAPTURE", str(smoke))
    return SimpleNamespace(root=foundation_git.root, log=log, marker=marker, smoke=smoke)


@pytest.mark.parametrize(
    "args",
    (
        ("--unknown",),
        ("--normal-durable", "extra"),
        ("all",),
        ("--foundation-core", "--normal-durable"),
    ),
)
def test_foundation_invalid_routes_never_reach_init_or_commands(foundation_commands, args):
    fixture = foundation_commands
    result = subprocess.run(
        ["/bin/sh", "scripts/ci.sh", *args], cwd=fixture.root, capture_output=True, text=True
    )
    assert result.returncode == 2 and result.stderr.strip() == "INVALID_FOUNDATION_ROUTE"
    assert not fixture.log.exists() and not (fixture.root / "reports").exists()


@pytest.mark.parametrize("mode", (None, "--normal-durable", "--foundation-core"))
def test_foundation_closed_routes_preserve_complete_default_prelude_tail_and_private_bind(
    foundation_commands, mode
):
    fixture = foundation_commands
    args = ["/bin/sh", "scripts/ci.sh", *([mode] if mode else [])]
    result = subprocess.run(args, cwd=fixture.root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(x) for x in fixture.log.read_text().splitlines()]
    stages = [
        c["args"][2]
        for c in calls
        if c["args"][:2] == ["scripts/native_context_db_catalog.py", "foundation-step"]
    ]
    expected = ["host", "host", "host"]  # Stream is separate from the fixed label.
    assert stages[:3] == expected
    labels = [
        c["args"][3]
        for c in calls
        if c["args"][:2] == ["scripts/native_context_db_catalog.py", "foundation-step"]
    ]
    assert labels == [
        "init",
        "config",
        "build",
        *(["normal-durable"] if mode != "--foundation-core" else []),
        *([] if mode == "--normal-durable" else lane.FOUNDATION_CORE),
        "cleanup",
    ]
    docker = [c["args"] for c in calls if c["name"] == "docker"]
    assert any(c[-5:] == ["build", "--pull", "api", "checks", "frontend"] for c in docker)
    assert sum(
        c["name"] == "sh" and c["args"] == ["scripts/test_telegram_egress.sh"] for c in calls
    ) == int(mode != "--foundation-core")
    checks = [c for c in docker if "run" in c and c[-1] == "checks"]
    assert len(checks) == int(mode != "--normal-durable")
    if checks:
        assert "--rm" in checks[0] and "--volume" in checks[0]
        assert any(x.endswith(":/asm-evidence:rw") for x in checks[0])
        assert not any(
            "ASM_NATIVE_TEST_ADMIN" in x or "ASM_NATIVE_TEST_ALLOW_RESET" in x for x in checks[0]
        )
        assert "for port in (8000, 8080)" in fixture.smoke.read_text()
        assert "http://127.0.0.1:8080/ops/" in fixture.smoke.read_text()
    if mode:
        projects = {c["project"] for c in calls if c["name"] == "docker"}
        assert len(projects) == 1 and next(iter(projects)).startswith("asm-foundation-")


@pytest.mark.parametrize(
    "failure,cleanup,completion,expected",
    (
        ("build", 0, 0, 17),
        ("durable", 23, 0, 17),
        ("checks", 23, 0, 17),
        ("http", 23, 0, 17),
        (None, 23, 0, 23),
        (None, 0, 9, 9),
    ),
)
def test_foundation_primary_status_cleanup_and_separate_evidence_gate(
    foundation_commands, monkeypatch, failure, cleanup, completion, expected
):
    fixture = foundation_commands
    if failure:
        monkeypatch.setenv("FAKE_FAIL", failure)
    monkeypatch.setenv("FAKE_CLEANUP_STATUS", str(cleanup))
    monkeypatch.setenv("FAKE_COMPLETENESS_STATUS", str(completion))
    result = subprocess.run(
        ["/bin/sh", "scripts/ci.sh"], cwd=fixture.root, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == expected, result.stderr
    paths = list((fixture.root / "reports/foundation-local").glob("*/execution.json"))
    assert len(paths) == 1
    receipt = json.loads(paths[0].read_text())
    assert receipt["primary_exit"] == (17 if failure else 0) and receipt["cleanup_exit"] == cleanup


def test_foundation_signal_forwarding_preserves_cancellation_and_owned_cleanup(
    foundation_commands, monkeypatch
):
    fixture = foundation_commands
    monkeypatch.setenv("FAKE_BLOCK", "build")
    process = subprocess.Popen(
        ["/bin/sh", "scripts/ci.sh", "--normal-durable"],
        cwd=fixture.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 8
        while (
            not fixture.marker.exists() and process.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert fixture.marker.exists(), process.communicate(timeout=1)
        os.killpg(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, (stdout, stderr)
        receipt = next((fixture.root / "reports/foundation-local").glob("*/execution.json"))
        assert json.loads(receipt.read_text()) == {"primary_exit": 143, "cleanup_exit": 0}
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=2)


@pytest.fixture
def foundation_cleanup_fault(foundation_commands, monkeypatch):
    """Damage diagnostics in an external inert command after valid admission."""
    fixture = foundation_commands
    docker = Path(os.environ["PATH"].split(os.pathsep)[0]) / "docker"
    program = docker.read_text()
    before = "if stage == os.environ.get('FAKE_BLOCK'):"
    assert program.count(before) == 1
    docker.write_text(
        program.replace(
            before,
            r"""
if stage == os.environ.get('FAKE_FAULT_STAGE'):
    path = pathlib.Path(os.environ['ASM_FOUNDATION_EVIDENCE'])
    target = path / 'cases.jsonl'
    fault = os.environ['FAKE_EVIDENCE_FAULT']
    if fault == 'missing': target.unlink()
    elif fault == 'replacement':
        target.rename(path / 'cases.saved')
        target.write_text('PRIVATE_SENTINEL_FOREIGN_JOURNAL\n')
        target.chmod(0o600)
    elif fault == 'mode': target.chmod(0)
    elif fault == 'symlink':
        target.rename(path / 'cases.saved')
        target.symlink_to(path / 'cases.saved')
    elif fault == 'binding':
        binding = json.loads((path / 'binding.json').read_text())
        binding['project'] = 'PRIVATE_SENTINEL_FOREIGN_PROJECT'
        (path / 'binding.json').write_text(json.dumps(binding))
    elif fault == 'directory':
        path.rename(path.with_name(path.name + '.saved'))
        path.mkdir(mode=0o700)
        (path / 'binding.json').write_text('{"project":"PRIVATE_SENTINEL_FOREIGN_PROJECT"}')
"""
            + before,
        )
    )
    monkeypatch.setenv("FAKE_EVIDENCE_FAULT", "missing")
    monkeypatch.setenv("FAKE_FAULT_STAGE", "checks")
    return fixture


def foundation_actual_down(fixture):
    calls = [json.loads(line) for line in fixture.log.read_text().splitlines()]
    checks = [
        c
        for c in calls
        if c["name"] == "docker" and "run" in c["args"] and c["args"][-1] == "checks"
    ]
    down = [c for c in calls if c["name"] == "docker" and "down" in c["args"]]
    assert len(checks) == len(down) == 1  # Count the actual command, not its Python wrapper.
    assert down[0]["args"] == list(lane.FOUNDATION_CLEANUP[1:])
    assert down[0]["project"] == checks[0]["project"]
    assert down[0]["project"].startswith("asm-foundation-foundation-core-")
    return next(
        p
        for p in (fixture.root / "reports/foundation-local").iterdir()
        if not p.name.endswith(".saved")
    )


@pytest.mark.parametrize(
    "fault", ("control", "missing", "replacement", "mode", "symlink", "binding", "directory")
)
@pytest.mark.parametrize("primary", (0, 17))
def test_foundation_post_admission_loss_executes_same_owned_down_once_and_fails_evidence(
    foundation_cleanup_fault, monkeypatch, fault, primary
):
    fixture = foundation_cleanup_fault
    monkeypatch.setenv("FAKE_EVIDENCE_FAULT", fault)
    # For primary0, damage the last command so execution succeeds up to cleanup.
    monkeypatch.setenv("FAKE_FAULT_STAGE", "checks" if primary else "other-last")
    if primary:
        monkeypatch.setenv("FAKE_FAIL", "checks")
    else:
        docker = Path(os.environ["PATH"].split(os.pathsep)[0]) / "docker"
        docker.write_text(
            docker.read_text().replace(
                "if stage == os.environ.get('FAKE_FAULT_STAGE'):",
                "if stage == os.environ.get('FAKE_FAULT_STAGE') or args[-1:] == ['images']:",
            )
        )
    result = subprocess.run(
        ["/bin/sh", "scripts/ci.sh", "--foundation-core"],
        cwd=fixture.root,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == (primary or int(fault != "control")), result.stderr
    path = foundation_actual_down(fixture)
    assert "PRIVATE_SENTINEL" not in result.stdout + result.stderr
    if fault == "directory":
        assert not (path / "execution.json").exists()  # Never recreate a foreign sink.
        assert set(p.name for p in path.iterdir()) == {"binding.json"}
    else:
        receipt = json.loads((path / "execution.json").read_text())
        assert receipt == {
            "primary_exit": primary,
            "cleanup_exit": 0,
            **({"evidence_failed": True} if fault != "control" else {}),
        }
        if fault != "control":
            issues = (path / "issues.jsonl").read_text()
            assert "EVIDENCE_WRITE_FAILED" in issues
            rows = [json.loads(line) for line in (path / "host.jsonl").read_text().splitlines()]
            assert rows[-1]["phase"] == "cleanup" and rows[-1]["process_exit"] == 0
        if fault == "missing":
            assert not (path / "cases.jsonl").exists()
        elif fault == "replacement":
            assert (path / "cases.jsonl").read_text() == "PRIVATE_SENTINEL_FOREIGN_JOURNAL\n"
            assert not (path / "cases.saved").read_bytes()
        elif fault == "mode":
            assert (path / "cases.jsonl").stat().st_mode & 0o777 == 0
        elif fault == "symlink":
            assert (path / "cases.jsonl").is_symlink() and not (path / "cases.saved").read_bytes()


@pytest.mark.parametrize("fault", ("missing", "replacement"))
@pytest.mark.parametrize("signum", (signal.SIGTERM, signal.SIGINT))
def test_foundation_post_admission_loss_retains_cancellation_and_actual_owned_down(
    foundation_cleanup_fault, monkeypatch, fault, signum
):
    fixture = foundation_cleanup_fault
    monkeypatch.setenv("FAKE_EVIDENCE_FAULT", fault)
    monkeypatch.setenv("FAKE_BLOCK", "checks")
    process = subprocess.Popen(
        ["/bin/sh", "scripts/ci.sh", "--foundation-core"],
        cwd=fixture.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not fixture.marker.exists() and process.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert fixture.marker.exists(), process.communicate(timeout=1)
        process.send_signal(signum)  # Actual shell PID, including SIGINT handling.
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 128 + signum, (stdout, stderr)
        path = foundation_actual_down(fixture)
        assert json.loads((path / "execution.json").read_text()) == {
            "primary_exit": 128 + signum,
            "cleanup_exit": 0,
            "evidence_failed": True,
        }
        assert "PRIVATE_SENTINEL" not in stdout + stderr
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=2)


@pytest.mark.parametrize("fault", ("inode", "project"))
def test_foundation_no_cleanup_authority_is_granted_to_invalid_initial_admission(
    foundation_commands, monkeypatch, fault
):
    fixture = foundation_commands
    binary = Path(os.environ["PATH"].split(os.pathsep)[0]) / "python3"
    before = "    os.execv(sys.executable, [sys.executable, *args])"
    program = binary.read_text()
    assert program.count(before) == 1
    binary.write_text(
        program.replace(
            before,
            "    if args[1] == 'foundation-ownership':\n"
            + (
                "        path = pathlib.Path(os.environ['ASM_FOUNDATION_EVIDENCE']) / 'cases.jsonl'\n"
                "        path.rename(path.with_name('cases.saved'))\n"
                "        path.touch(mode=0o600)\n"
                if fault == "inode"
                else "        os.environ['COMPOSE_PROJECT_NAME'] = 'foreign-project'\n"
            )
            + before,
        )
    )
    result = subprocess.run(
        ["/bin/sh", "scripts/ci.sh", "--foundation-core"],
        cwd=fixture.root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1 and "FOUNDATION_EVIDENCE_REFUSED" in result.stderr
    calls = [json.loads(line) for line in fixture.log.read_text().splitlines()]
    assert not any(
        c["name"] == "docker" and any(x in c["args"] for x in ("build", "run", "up", "down"))
        for c in calls
    )


@pytest.mark.parametrize(
    "stream,phase,argv",
    (
        ("backend", "ruff", ("ruff",)),
        ("host", "build", ("docker",)),
        ("host", "cleanup", ("prune",)),
    ),
)
def test_foundation_owned_descriptor_cannot_authorize_other_commands(stream, phase, argv):
    with (
        patch.object(lane, "foundation_owned_cleanup") as admission,
        patch.object(lane.subprocess, "Popen") as command,
    ):
        with pytest.raises(lane.Refusal, match="owned cleanup command"):
            lane.foundation_step(stream, phase, list(argv), owned_cleanup=True)
    admission.assert_not_called()
    command.assert_not_called()


def test_foundation_owned_cleanup_requires_parent_descriptor_not_current_evidence(
    foundation_commands, foundation_sink
):
    fixture = foundation_commands
    result = subprocess.run(
        [
            lane.sys.executable,
            "scripts/native_context_db_catalog.py",
            "foundation-step",
            "host",
            "cleanup",
            "--owned-cleanup-fd=4",
            "--",
            *lane.FOUNDATION_CLEANUP,
        ],
        cwd=fixture.root,
        capture_output=True,
        text=True,
        close_fds=True,
        timeout=5,
    )
    assert result.returncode == 1 and result.stderr.strip() == "FOUNDATION_EVIDENCE_REFUSED"
    assert not fixture.log.exists()  # Valid current evidence alone grants no cleanup command.


def test_foundation_owned_cleanup_after_loss_pins_project_and_keeps_ninety_second_cap(
    foundation_sink, monkeypatch, tmp_path
):
    store = foundation_sink
    monkeypatch.chdir(lane.ROOT)
    project = store.binding["project"]
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    snapshot = lane.foundation_ownership()  # Genuine full admission, before diagnostic loss.
    authority = tmp_path / "parent-memory"
    authority.write_text(json.dumps(snapshot))
    (store.path / "cases.jsonl").unlink()
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "foreign-project-after-admission")
    original_dup = os.dup
    fd = os.open(authority, os.O_RDONLY)
    child = Mock(pid=12345)
    child.wait.side_effect = [subprocess.TimeoutExpired(["owned-cleanup"], 90), 0]
    try:
        with (
            patch.object(lane.os, "dup", side_effect=lambda n: original_dup(fd if n == 4 else n)),
            patch.object(lane.subprocess, "Popen", return_value=child) as command,
            patch.object(lane.os, "killpg") as terminate,
        ):
            assert (
                lane.foundation_step(
                    "host", "cleanup", list(lane.FOUNDATION_CLEANUP), owned_cleanup=True
                )
                == 124
            )
        assert command.call_args.kwargs["env"]["COMPOSE_PROJECT_NAME"] == project
        assert child.wait.call_args_list[0].kwargs == {"timeout": 90}
        terminate.assert_called_once_with(12345, signal.SIGKILL)
        assert not (store.path / "cases.jsonl").exists()
        assert foundation_rows(store, "host.jsonl")[-1]["process_exit"] == 124
        assert foundation_rows(store, "issues.jsonl")[-1]["issue"] == "EVIDENCE_WRITE_FAILED"
    finally:
        os.close(fd)


def test_foundation_backend_keeps_every_original_command_argument_and_epoch(
    foundation_commands, foundation_sink
):
    fixture = foundation_commands
    result = subprocess.run(
        ["/bin/sh", "scripts/check_backend.sh"],
        cwd=fixture.root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(x) for x in fixture.log.read_text().splitlines()]
    commands = [
        c["args"][5:]
        for c in calls
        if c["args"][:3] == ["scripts/native_context_db_catalog.py", "foundation-step", "backend"]
    ]
    assert commands == [
        ["ruff", "check", "backend", "tests", "scripts", "migrations"],
        ["ruff", "format", "--check", "--diff", "backend", "tests", "scripts", "migrations"],
        ["mypy", "backend/src"],
        ["pytest", "-q", "--durations=20", "-m", "not integration"],
        ["alembic", "upgrade", "head"],
        ["alembic", "upgrade", "head"],
        ["python", "scripts/native_context_db_catalog.py", "generic-integration"],
        ["alembic", "downgrade", "base"],
        ["alembic", "upgrade", "head"],
        ["python", "scripts/export_contracts.py", "--check"],
        ["python", "-m", "build", "--wheel", "--no-isolation", "--outdir", "/tmp/wheel-one"],
        ["python", "-m", "build", "--wheel", "--no-isolation", "--outdir", "/tmp/wheel-two"],
        ["cmp", "/tmp/wheel-one/*.whl", "/tmp/wheel-two/*.whl"],
        ["sha256sum", "/tmp/wheel-one/*.whl"],
    ]
    builds = [c for c in calls if c["name"] == "python" and c["args"][:2] == ["-m", "build"]]
    assert len(builds) == 2 and all(c["epoch"] == "315532800" for c in builds)
    assert [
        r["phase"] for r in foundation_rows(foundation_sink, "backend.jsonl") if r["edge"] == "end"
    ] == list(lane.FOUNDATION_BACKEND)


@pytest.mark.parametrize("fault", (None, "sha", "job", "workflow", "event"))
def test_foundation_main_source_event_admission_and_job_binding(
    foundation_git, tmp_path, monkeypatch, fault
):
    env, payload = ci_event(tmp_path, "main-push")
    head = foundation_git.git("rev-parse", "HEAD")
    env.update(
        GITHUB_SHA=head,
        GITHUB_JOB="foundation",
        GITHUB_WORKFLOW_REF=lane.REPOSITORY + "/.github/workflows/ci.yml@refs/heads/main",
        GITHUB_ENV=str(tmp_path / "actions-env"),
    )
    payload["after"], payload["head_commit"]["id"] = head, head
    Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload))
    if fault == "sha":
        env["GITHUB_SHA"] = "f" * 40
    elif fault == "job":
        env["GITHUB_JOB"] = "foundation-durable"
    elif fault == "workflow":
        env["GITHUB_WORKFLOW_REF"] = "foreign/workflow@main"
    elif fault == "event":
        env["GITHUB_EVENT_NAME"] = "workflow_dispatch"
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    if fault:
        with pytest.raises(lane.Refusal):
            lane.foundation_prepare("foundation-core")
        assert not (foundation_git.root / "reports").exists()
    else:
        directory = lane.foundation_prepare("foundation-core")
        binding = json.loads((directory / "binding.json").read_text())
        assert binding["identity"]["event_payload_sha256"] == lane.sha256(
            Path(env["GITHUB_EVENT_PATH"]).read_bytes()
        )
        assert (
            binding["identity"]["head"] == head
            and binding["run"] == "123"
            and binding["attempt"] == "2"
        )
        exported = Path(env["GITHUB_ENV"]).read_text()
        assert (
            str(directory) in exported
            and lane.sha256((directory / "binding.json").read_bytes()) in exported
        )


def test_foundation_full_storage_caller_is_preserved_without_broadening_native_events(
    foundation_git, tmp_path, monkeypatch
):
    head = foundation_git.git("rev-parse", "HEAD")
    event = tmp_path / "event.json"
    event.write_text('{"source":"constructed storage event"}')
    values = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": lane.REPOSITORY,
        "GITHUB_REPOSITORY_ID": str(lane.REPOSITORY_ID),
        "GITHUB_JOB": "verify",
        "GITHUB_SHA": head,
        "GITHUB_WORKFLOW_REF": lane.REPOSITORY
        + "/.github/workflows/storage-images.yml@refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_ENV": str(tmp_path / "actions-env"),
        "GITHUB_EVENT_PATH": str(event),
        "COMPOSE_PROJECT_NAME": "storage-image-verification",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    directory = lane.foundation_prepare("all")
    binding = json.loads((directory / "binding.json").read_text())
    assert binding["project"] == "storage-image-verification" and binding["route"] == "all"
    with pytest.raises(lane.Refusal):
        lane.admit_event()


def test_foundation_prior_durable_reports_are_not_adopted(foundation_git):
    reports = foundation_git.root / "reports"
    reports.mkdir()
    (reports / "telegram-egress.json").write_text('{"source_sha":"stale"}')
    with pytest.raises(lane.Refusal, match="previous durable"):
        lane.foundation_prepare("normal-durable")


@pytest.mark.parametrize("fault", (None, "missing-lifecycle", "source", "parents", "wire"))
def test_foundation_durable_completeness_requires_current_six_lane_receipts(
    foundation_git, monkeypatch, fault
):
    path = lane.foundation_prepare("normal-durable")
    monkeypatch.setenv("ASM_FOUNDATION_EVIDENCE", str(path))
    monkeypatch.setenv("ASM_FOUNDATION_OWNER_UID", str(os.getuid()))
    monkeypatch.setenv(
        "ASM_FOUNDATION_BINDING_SHA256", lane.sha256((path / "binding.json").read_bytes())
    )
    store = lane.foundation_store()
    foundation_complete_fixture(store)
    head = store.binding["identity"]["head"]
    report = {
        "source_sha": head,
        "lifecycles": {k: {"source_sha": head} for k in lane.FOUNDATION_LIFECYCLES},
        "assertions": [{"result": "PASS"}],
    }
    source = {
        "source_sha": head,
        "parents": [],
        "expected_revision": "0013",
        "images": {k: {} for k in ("api", "worker", "scheduler", "fixture")},
    }
    if fault == "missing-lifecycle":
        report["lifecycles"].pop("legacy-stop")
    elif fault == "source":
        report["source_sha"] = "f" * 40
    elif fault == "parents":
        source["parents"] = ["f" * 40]
    elif fault == "wire":
        report["assertions"][0]["result"] = "FAIL"
    for name, value in (("telegram-egress.json", report), ("candidate-egress-source.json", source)):
        target = lane.ROOT / "reports" / name
        target.write_text(json.dumps(value))
        target.chmod(0o600)
    if fault:
        with pytest.raises(lane.Refusal, match="durable evidence"):
            lane.foundation_check(store)
    else:
        lane.foundation_check(store)


def test_foundation_reporter_error_cannot_replace_primary_process_exit(foundation_sink):
    with (
        patch.object(lane, "foundation_store", return_value=foundation_sink),
        patch.object(foundation_sink, "append", side_effect=OSError("PRIVATE_SENTINEL_DSN_SQL")),
    ):
        assert (
            lane.foundation_step(
                "host", "build", [lane.sys.executable, "-c", "raise SystemExit(17)"]
            )
            == 17
        )
        assert lane.foundation_step("host", "build", [lane.sys.executable, "-c", "pass"]) != 0


def test_foundation_cleanup_remains_bounded_at_ninety_seconds(foundation_sink):
    child = Mock(pid=12345)
    child.wait.side_effect = [subprocess.TimeoutExpired(["constructed"], 90), 0]
    with (
        patch.object(lane, "foundation_store", return_value=foundation_sink),
        patch.object(lane.subprocess, "Popen", return_value=child),
        patch.object(lane.os, "killpg") as terminate,
    ):
        assert lane.foundation_step("host", "cleanup", ["constructed-owned-cleanup"]) == 124
    assert child.wait.call_args_list[0].kwargs == {"timeout": 90}
    terminate.assert_called_once_with(12345, signal.SIGKILL)
    assert foundation_rows(foundation_sink, "host.jsonl")[-1]["status"] == 124


def test_foundation_hostile_descriptors_stay_unknown_without_execution(foundation_git):
    class Hostile(RuntimeError):
        @property
        def diag(self):
            raise KeyboardInterrupt("must not evaluate")

        @property
        def sqlstate(self):
            raise AssertionError("must not evaluate")

        @property
        def orig(self):
            raise SystemExit("must not evaluate")

    value = lane.foundation_failure(Hostile("PRIVATE_SENTINEL_DSN_SQL"), {}, foundation_git.catalog)
    assert value["chain"][0]["exception"] == value["chain"][0]["sqlstate"] == "UNKNOWN"
    assert len(value["chain"]) == 1 and "PRIVATE_SENTINEL" not in json.dumps(value)


def test_foundation_genuine_psycopg_metadata_is_constructed_not_database_evidence(foundation_git):
    from psycopg.errors import CheckViolation
    from psycopg.pq import DiagnosticField as D

    error = CheckViolation(
        "PRIVATE_SENTINEL_DSN_SQL",
        info={
            D.SQLSTATE: b"23514",
            D.SCHEMA_NAME: b"app",
            D.TABLE_NAME: b"messages",
            D.CONSTRAINT_NAME: b"approved_check",
            D.CONTEXT: b"PL/pgSQL function platform.safe_function() line 8 at PRIVATE_SENTINEL_DSN_SQL",
        },
    )
    value = lane.foundation_failure(error, {}, foundation_git.catalog)
    row = value["chain"][0]
    assert row["exception"] == "CheckViolation" and row["sqlstate"] == "23514"
    assert (
        row["constraint"] == "approved_check"
        and row["schema"] == "app"
        and row["table"] == "messages"
    )
    assert row["plpgsql_frames"] == [{"function": "platform.safe_function", "line": 8}]
    assert "PRIVATE_SENTINEL" not in json.dumps(value)


@pytest.mark.parametrize("signum", (signal.SIGTERM, signal.SIGINT))
def test_foundation_backend_pid_one_signal_reaches_actual_child_without_a_group_signal(
    foundation_commands, foundation_sink, monkeypatch, signum
):
    fixture = foundation_commands
    monkeypatch.setenv("FAKE_BLOCK", "generic")
    process = subprocess.Popen(
        ["/bin/sh", "scripts/check_backend.sh"],
        cwd=fixture.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not fixture.marker.exists() and process.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert fixture.marker.exists(), process.communicate(timeout=1)
        process.send_signal(signum)  # Docker's PID1 delivery, not a synthetic killpg shortcut.
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 128 + signum, (stdout, stderr)
        rows = foundation_rows(foundation_sink, "backend.jsonl")
        assert rows[-1]["phase"] == "generic" and rows[-1]["status"] == 128 + signum
        assert not foundation_sink.read("generic-result.json")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=2)


def test_foundation_durable_term_enters_unchanged_python_finally_and_retains_incoming_status(
    foundation_sink, foundation_git, tmp_path
):
    marker, cleaned = tmp_path / "started", tmp_path / "cleaned"
    code = f"import pathlib,signal\ntry:\n pathlib.Path({str(marker)!r}).write_text('started')\n signal.pause()\nfinally:\n pathlib.Path({str(cleaned)!r}).write_text('owned cleanup')\n"
    process = subprocess.Popen(
        [
            lane.sys.executable,
            "scripts/native_context_db_catalog.py",
            "foundation-step",
            "host",
            "normal-durable",
            "--",
            lane.sys.executable,
            "-c",
            code,
        ],
        cwd=foundation_git.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), process.communicate(timeout=1)
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 143 and cleaned.read_text() == "owned cleanup", (
            stdout,
            stderr,
        )
        row = foundation_rows(foundation_sink, "host.jsonl")[-1]
        assert (
            row["status"] == 143 and row["process_exit"] == 130 and row["signal"] == signal.SIGTERM
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=2)


@pytest.mark.parametrize("original", (0, 7))
def test_foundation_generic_sink_failure_is_a_separate_gate_and_keeps_nonzero_exit(
    foundation_sink, monkeypatch, original
):
    expected = partition_fixture()[2]["nodeids"]

    def proof(private, evidence, commands, env):
        inventories = partition_fixture()
        value = lane.validate_partition(*inventories)
        for name, data in zip(("all-pg", "native", "generic-pg"), inventories, strict=True):
            lane.write_json(private / ("partition-" + name + ".json"), data)
        lane.write_json(private / "integration-partition.json", value)
        return value, expected

    def execute(argv, *, plugins):
        plugins[0].pytest_collection_finish(
            SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in expected])
        )
        return original

    publish = foundation_sink.publish

    def broken_result(name, value):
        if name == "generic-result.json":
            raise OSError("PRIVATE_SENTINEL_DSN_SQL")
        return publish(name, value)

    monkeypatch.setattr(lane, "prove_partition", proof)
    monkeypatch.setattr(foundation_sink, "publish", broken_result)
    monkeypatch.setattr(lane, "foundation_store", lambda: foundation_sink)
    with patch("pytest.main", side_effect=execute):
        if original:
            assert lane.generic_integration() == original
        else:
            with pytest.raises(lane.Refusal, match="after pytest exit zero"):
                lane.generic_integration()
    assert not foundation_sink.read("generic-result.json") and foundation_sink.read("issues.jsonl")


def test_foundation_python_frames_have_one_eight_frame_budget_across_the_chain(
    foundation_sink, foundation_git
):
    from types import TracebackType

    path = lane.ROOT / "tests/test_constructed.py"
    namespace = {"__name__": "constructed"}
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    try:
        namespace["test_call"]()
    except AssertionError as error:
        trace = error.__traceback__.tb_next
    repeated = None
    for _ in range(20):
        repeated = TracebackType(repeated, trace.tb_frame, trace.tb_lasti, trace.tb_lineno)
    first = RuntimeError("PRIVATE_SENTINEL").with_traceback(repeated)
    current = first
    for _ in range(3):
        current.orig = RuntimeError("PRIVATE_SENTINEL").with_traceback(repeated)
        current = current.orig
    value = lane.foundation_failure(
        first,
        lane.foundation_locations(foundation_sink.binding["source_manifest"]),
        foundation_git.catalog,
    )
    assert sum(len(row["python_frames"]) for row in value["chain"]) <= 8
    assert len(value["chain"]) == 4 and all(row["frames_limited"] for row in value["chain"])


def complete_reports(nodes):
    return [
        dict(nodeid=node, when=phase, outcome="passed", xfail=False)
        for node in nodes
        for phase in ("setup", "call", "teardown")
    ]


def owned_fixture():
    labels = {"asm.c6.nonce": "a" * 32, "asm.c6.source": "b" * 40}
    lease = {
        "container_id": "c" * 64,
        "image_id": "sha256:" + "d" * 64,
        "volume": "asm-native-" + "a" * 32 + "-data",
        "labels": labels,
        "volume_mountpoint": "/var/lib/docker/volumes/owned/_data",
        "volume_created": "2026-10-18T01:00:00Z",
        "bootstrap": "/checkout/infra/postgres/bootstrap.sh",
        "pid": 23456,
        "started_at": "2026-10-18T01:00:01Z",
        "port": 34567,
    }
    container = {
        "Id": lease["container_id"],
        "Image": lease["image_id"],
        "RestartCount": 0,
        "Config": {"Image": lane.DB_IMAGE, "Labels": labels.copy()},
        "HostConfig": {
            "Privileged": False,
            "NetworkMode": "bridge",
            "RestartPolicy": {"Name": "no"},
            "PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]},
        },
        "State": {"Running": True, "Pid": 23456, "StartedAt": lease["started_at"]},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}},
        "Mounts": [
            {
                "Type": "volume",
                "Name": lease["volume"],
                "Source": lease["volume_mountpoint"],
                "Destination": "/var/lib/postgresql",
                "RW": True,
            },
            {
                "Type": "bind",
                "Source": lease["bootstrap"],
                "Destination": "/docker-entrypoint-initdb.d/010-bootstrap.sh",
                "RW": False,
            },
        ],
    }
    volume = {
        "Name": lease["volume"],
        "Labels": labels.copy(),
        "Driver": "local",
        "Scope": "local",
        "Options": None,
        "Mountpoint": lease["volume_mountpoint"],
        "CreatedAt": lease["volume_created"],
    }
    return lease, container, volume


def role_fixture():
    return [
        dict(
            name="asm_" + name,
            login=True,
            superuser=False,
            bypassrls=False,
            inherit=name == "migrator",
            createrole=False,
            createdb=False,
            replication=False,
        )
        for name in ("runtime", "migrator")
    ]


def catalog_fixture():
    functions = {}
    for signature, body in (
        ("platform.example(p_id uuid)", " SELECT true "),
        (lane.PROFILE, " SELECT '{}'::jsonb "),
    ):
        result = "boolean" if "example" in signature else "jsonb"
        row = lane.parse_function(
            "CREATE FUNCTION "
            + signature
            + " RETURNS "
            + result
            + " LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$"
            + body
            + "$$"
        )
        row.update(runtime_execute=False, acl=[["asm_migrator", "asm_migrator", "EXECUTE", False]])
        functions[row["signature"]] = row
    rows, resolved = [], {}
    for oid, (sig, source) in enumerate(functions.items(), 100):
        row = copy.deepcopy(source)
        row.update(oid=oid, kind="f", leakproof=False, parallel="u")
        rows.append(row)
        resolved[sig] = oid
    columns = {"platform.alembic_version": ["version_num"]}
    snapshot = {
        "functions": [[s, v["definition"]] for s, v in functions.items()],
        "columns": [
            ["platform.alembic_version", "version_num", "character varying(32)", True, "", None]
        ],
        "constraints": [
            ["platform.alembic_version", "alembic_version_pkc", "PRIMARY KEY (version_num)", True]
        ],
    }
    nonfunction = {k: v for k, v in snapshot.items() if k != "functions"}
    return (
        {"functions": functions, "columns": columns},
        rows,
        resolved,
        json.dumps(snapshot),
        json.dumps(nonfunction),
    )


class SourceGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        (self.root / "source.py").write_text("SOURCE = 1\n")
        self.git("add", "source.py")
        self.git(
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@example.invalid",
            "commit",
            "-qm",
            "unit fixture",
        )
        self.sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE
        )

    def refused_before_reset(self, expected_sha):
        owner, destructive = Mock(), Mock()
        with self.assertRaises(lane.Refusal):
            lane.guarded_reset(
                lambda: lane.require_source(self.root, expected_sha), owner, destructive
            )
        owner.assert_not_called()
        destructive.assert_not_called()

    def test_event_head_mismatch_refuses_before_reset(self):
        self.refused_before_reset("0" * 40)

    def test_tracked_byte_drift_refuses_before_reset(self):
        (self.root / "source.py").write_text("SOURCE = 2\n")
        self.refused_before_reset(self.sha)

    def test_untracked_file_refuses_before_reset(self):
        (self.root / "unexpected").write_text("foreign")
        self.refused_before_reset(self.sha)

    def test_assume_unchanged_cannot_hide_source_mutation(self):
        self.git("update-index", "--assume-unchanged", "source.py")
        (self.root / "source.py").write_text("SOURCE = 2\n")
        self.refused_before_reset(self.sha)

    def test_valid_source_records_real_tree_and_exact_bytes(self):
        tree, manifest = lane.require_source(self.root, self.sha)
        self.assertEqual(tree, self.git("rev-parse", "HEAD^{tree}").strip())
        self.assertEqual(manifest[0]["sha256"], lane.sha256(b"SOURCE = 1\n"))

    def test_wrong_source_prevents_cleanup_calls(self):
        inspect, destructive = Mock(), Mock()
        lease, _, _ = owned_fixture()
        with self.assertRaises(lane.Refusal):
            lane.guarded_reset(
                lambda: lane.require_source(self.root, "0" * 40),
                lambda: None,
                lambda: lane.cleanup_owned(lease, inspect, inspect, destructive, destructive),
            )
        inspect.assert_not_called()
        destructive.assert_not_called()


class OwnershipGuards(unittest.TestCase):
    def test_valid_owned_cleanup_removes_only_recorded_ids(self):
        lease, container, volume = owned_fixture()
        removals = []
        lane.cleanup_owned(
            lease,
            lambda _: container,
            lambda _: volume,
            lambda identity: removals.append(("container", identity)),
            lambda identity: removals.append(("volume", identity)),
        )
        self.assertEqual(
            removals, [("container", lease["container_id"]), ("volume", lease["volume"])]
        )

    def assert_refuses_all_destructive_calls(self, lease, container, volume):
        reset, remove_container, remove_volume = Mock(), Mock(), Mock()
        with self.assertRaises(lane.Refusal):
            lane.guarded_reset(
                lambda: None,
                lambda: (
                    lane.validate_volume(lease, volume),
                    lane.validate_container(lease, container),
                ),
                reset,
            )
        reset.assert_not_called()
        with self.assertRaises(lane.Refusal):
            lane.cleanup_owned(
                lease, lambda _: container, lambda _: volume, remove_container, remove_volume
            )
        remove_container.assert_not_called()
        remove_volume.assert_not_called()

    def test_foreign_container_identity_refuses_reset_and_cleanup(self):
        changes = (
            ("Id", "f" * 64),
            ("Image", "sha256:" + "f" * 64),
            ("RestartCount", 1),
        )
        for key, value in changes:
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                container[key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_labels_or_source_image_refuse_reset_and_cleanup(self):
        for key, value in (("Labels", {"asm.c6.nonce": "foreign"}), ("Image", "postgres:18")):
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                container["Config"][key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_mounts_refuse_reset_and_cleanup(self):
        for index, key, value in (
            (0, "Source", "/shared/data"),
            (0, "Name", "foreign"),
            (0, "Destination", "/shared"),
            (0, "RW", False),
            (1, "Source", "/foreign/bootstrap.sh"),
            (1, "RW", True),
        ):
            with self.subTest(mount=index, field=key):
                lease, container, volume = owned_fixture()
                container["Mounts"][index][key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_host_or_port_refuses_reset_and_cleanup(self):
        for section in ("HostConfig", "NetworkSettings"):
            for key, value in (
                ("HostIp", "0.0.0.0"),
                ("HostIp", "192.0.2.1"),
                ("HostPort", "5432"),
            ):
                with self.subTest(section=section, field=key, value=value):
                    lease, container, volume = owned_fixture()
                    field = "PortBindings" if section == "HostConfig" else "Ports"
                    container[section][field]["5432/tcp"][0][key] = value
                    self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_pid_or_start_refuses_reset_and_cleanup(self):
        for key, value in (("Pid", 99999), ("StartedAt", "foreign-start")):
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                container["State"][key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_stopped_container_with_foreign_retained_port_refuses_cleanup(self):
        lease, container, volume = owned_fixture()
        container["State"].update(Running=False, Pid=0)
        container["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "5432"
        self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_volume_refuses_all_removals(self):
        for key, value in (
            ("Name", "foreign"),
            ("Labels", {}),
            ("Mountpoint", "/shared/data"),
            ("Driver", "nfs"),
            ("Scope", "global"),
            ("Options", {"device": "/shared"}),
            ("CreatedAt", "foreign"),
        ):
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                volume[key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_missing_container_never_causes_removal_by_name(self):
        lease, _, volume = owned_fixture()
        remove_container, remove_volume = Mock(), Mock()
        lane.cleanup_owned(lease, lambda _: None, lambda _: volume, remove_container, remove_volume)
        remove_container.assert_not_called()
        remove_volume.assert_called_once_with(lease["volume"])

    def test_wrong_server_identity_refuses_before_database_reset(self):
        identity = [
            "postgres",
            "asm_admin",
            "asm_admin",
            5432,
            "180003",
            "1234567890",
            "2026-10-18 01:00:00+00",
        ]
        lease = {"server_identity": identity}
        lane.compare_server_identity(lease, identity, identity[5])
        for index, value in (
            (0, "shared"),
            (1, "postgres"),
            (2, "asm_migrator"),
            (3, 5433),
            (4, "170003"),
            (5, "9999999999"),
            (6, "foreign-start"),
        ):
            with self.subTest(field=index):
                mutant, destructive = list(identity), Mock()
                mutant[index] = value
                with self.assertRaises(lane.Refusal):
                    lane.guarded_reset(
                        lambda: None,
                        lambda: lane.compare_server_identity(lease, mutant, identity[5]),
                        destructive,
                    )
                destructive.assert_not_called()
        with self.assertRaises(lane.Refusal):
            lane.compare_server_identity(lease, identity, "9876543210", initial=True)


class CatalogGuards(unittest.TestCase):
    def test_all_actual_migrations_expand_and_profile_body_is_source_derived(self):
        expected = lane.source_catalog(lane.ROOT)
        self.assertEqual(len(expected["functions"]), 167)
        self.assertEqual(len(expected["columns"]), 45)
        self.assertEqual((len(expected["additions"]), len(expected["replacements"])), (35, 18))
        verifier = expected["functions"][lane.PROFILE]
        self.assertEqual(verifier["body_sha256"], lane.sha256(verifier["body"].encode()))
        self.assertIn("WITH expected(signature,body_hash", verifier["body"])
        for row in expected["functions"].values():
            self.assertIn(["asm_migrator", "asm_migrator", "EXECUTE", False], row["acl"])
            self.assertTrue(all(grant[3] is False for grant in row["acl"]))

    def test_typed_overloads_defaults_and_table_outputs_are_distinct(self):
        sql = "CREATE FUNCTION platform.example(p_id uuid, p_flag boolean DEFAULT false) RETURNS TABLE(item_id uuid, seen_at timestamptz) LANGUAGE sql STABLE STRICT SET search_path=pg_catalog,pg_temp AS $$ SELECT p_id,now() $$"
        row = lane.parse_function(sql)
        self.assertEqual(row["signature"], "platform.example(uuid,boolean)")
        self.assertEqual(row["argmodes"], ["i", "i", "t", "t"])
        self.assertEqual(row["all_types"], ["uuid", "boolean", "uuid", "timestamptz"])
        self.assertEqual(row["defaults"], "false")
        self.assertNotEqual(
            row["signature"],
            lane.parse_function(sql.replace("p_id uuid", "p_id text"))["signature"],
        )

    def test_unknown_sql_headers_and_unclosed_quotes_fail_closed(self):
        sql = "CREATE FUNCTION platform.example() RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT true $$"
        for mutant in (
            sql.replace("IMMUTABLE", "PARALLEL SAFE"),
            sql.replace("RETURNS boolean", "RETURNS SETOF boolean"),
            sql.replace("pg_catalog,pg_temp", "public"),
            sql.replace("AS $$", "AS '"),
        ):
            with self.subTest(mutant=mutant), self.assertRaises(lane.Refusal):
                lane.parse_function(mutant)
        for malformed in ("SELECT 'oops", "/* oops", "SELECT ($$oops", "SELECT )"):
            with self.subTest(sql=malformed), self.assertRaises(lane.Refusal):
                list(lane.split_sql(malformed))

    def test_unknown_nonfunction_statement_fails_before_catalog_comparison(self):
        command = {
            "revision": "0013",
            "index": 0,
            "sql": "CREATE VIEW platform.unreviewed AS SELECT 1",
        }
        with patch.object(lane, "capture_source", return_value=({}, [command])):
            with self.assertRaisesRegex(lane.Refusal, "Unsupported source SQL"):
                lane.source_catalog(lane.ROOT)

    def test_sql_lexer_preserves_executable_body_bytes_and_internal_comments(self):
        sql = "-- leading\nCREATE FUNCTION platform.example() RETURNS text LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$\n -- body ; ,\n SELECT 'a;''b'\n$$; SELECT 2;"
        statements = list(lane.split_sql(sql))
        row = lane.parse_function(lane.leading_comments(statements[0]))
        self.assertEqual(row["body"], "\n -- body ; ,\n SELECT 'a;''b'\n")
        self.assertEqual(statements[1], "SELECT 2")

    def test_missing_extra_duplicate_oid_and_typed_resolution_refuse(self):
        expected, rows, resolved, _, _ = catalog_fixture()
        for case in ("missing", "extra", "duplicate_oid", "wrong_signature_resolution"):
            with self.subTest(case=case):
                actual, ids = copy.deepcopy(rows), dict(resolved)
                if case == "missing":
                    actual.pop()
                elif case == "extra":
                    row = copy.deepcopy(actual[0])
                    row.update(signature="platform.foreign(uuid)", oid=999)
                    actual.append(row)
                elif case == "duplicate_oid":
                    actual[1]["oid"] = actual[0]["oid"]
                else:
                    ids[actual[0]["signature"]] = 999
                with self.assertRaises(lane.Refusal):
                    lane.compare_functions(expected["functions"], actual, ids)

    def test_body_own_verifier_acl_argument_and_return_drift_refuse(self):
        expected, rows, resolved, _, _ = catalog_fixture()
        changes = {
            "body": " SELECT '{\"valid\":true}'::jsonb ",
            "acl": [["asm_migrator", "PUBLIC", "EXECUTE", False]],
            "owner": "asm_runtime",
            "proconfig": ["search_path=public"],
            "argnames": ["foreign"],
            "input_types": ["text"],
            "return_type": "text",
            "security_definer": False,
            "volatility": "v",
            "runtime_execute": True,
            "strict": True,
        }
        for key, value in changes.items():
            with self.subTest(field=key):
                actual = copy.deepcopy(rows)
                actual[1][key] = value
                with self.assertRaises(lane.Refusal):
                    lane.compare_functions(expected["functions"], actual, resolved)

    def test_verifier_self_report_is_never_consulted_after_body_drift(self):
        expected, rows, resolved, full_text, nonfunction = catalog_fixture()
        rows[1]["body"] = " SELECT '{\"valid\":true}'::jsonb "
        self_report = Mock()
        with self.assertRaises(lane.Refusal):
            lane.compare_catalog(expected, rows, resolved, full_text, nonfunction, self_report)
        self_report.assert_not_called()

    def test_nonfunction_drift_and_column_order_refuse(self):
        expected, _, _, full_text, nonfunction = catalog_fixture()
        with patch.object(lane, "NONFUNCTION_SHA256", lane.sha256(nonfunction.encode())):
            self.assertEqual(
                lane.compare_snapshot(expected["columns"], full_text, nonfunction),
                lane.sha256(b"asm:m3:native_schema:v1\n" + full_text.encode()),
            )
            for case in ("constraint_validation", "column_type", "extra_column"):
                with self.subTest(case=case):
                    full = json.loads(full_text)
                    if case == "constraint_validation":
                        full["constraints"][0][3] = False
                    elif case == "column_type":
                        full["columns"][0][2] = "text"
                    else:
                        full["columns"].append(
                            ["platform.alembic_version", "foreign", "text", False, "", None]
                        )
                    non = {k: v for k, v in full.items() if k != "functions"}
                    with self.assertRaises(lane.Refusal):
                        lane.compare_snapshot(
                            expected["columns"], json.dumps(full), json.dumps(non)
                        )

    def test_independent_full_hash_is_compared_after_body_and_nonfunction_checks(self):
        expected, rows, resolved, full_text, nonfunction = catalog_fixture()
        full_hash = lane.sha256(b"asm:m3:native_schema:v1\n" + full_text.encode())
        declared = {"schema_revision": "0013", "valid": True, "profile_sha256": full_hash}
        with patch.object(lane, "NONFUNCTION_SHA256", lane.sha256(nonfunction.encode())):
            self.assertEqual(
                lane.compare_catalog(
                    expected, rows, resolved, full_text, nonfunction, lambda: declared
                ),
                (full_hash, declared),
            )
            for wrong in (dict(declared, valid=False), dict(declared, profile_sha256="0" * 64)):
                with self.assertRaises(lane.Refusal):
                    lane.compare_catalog(
                        expected, rows, resolved, full_text, nonfunction, lambda value=wrong: value
                    )

    def test_runtime_membership_ownership_and_role_flags_refuse(self):
        roles = role_fixture()
        lane.compare_roles(roles, [], 0)
        for key in ("inherit", "superuser", "bypassrls", "createrole", "createdb", "replication"):
            with self.subTest(field=key):
                mutated = copy.deepcopy(roles)
                mutated[0][key] = True
                with self.assertRaises(lane.Refusal):
                    lane.compare_roles(mutated, [], 0)
        for memberships, owned in (
            ([{"role": "asm_migrator", "member": "asm_runtime"}], 0),
            ([], 1),
        ):
            with self.assertRaises(lane.Refusal):
                lane.compare_roles(roles, memberships, owned)


class ChildSettingsConfiguration(unittest.TestCase):
    def assert_test_settings(self, parent):
        from asm import foundation
        from pydantic import ValidationError

        with patch.dict(os.environ, parent, clear=True):
            child = lane.child_environment(Path("/synthetic/native/private"))
            self.assertEqual(dict(os.environ), parent)
        self.assertTrue(all(key not in child for key in (*lane.SECRET_ENV, "GITHUB_TOKEN")))
        synthetic_url = "postgresql+psycopg://asm_runtime:synthetic-only@settings-regression.invalid:65432/asm_test"
        # The fixture adds only a synthetic URL, never an engine or an owned DB.
        child["ASM_DATABASE_URL"] = synthetic_url
        with (
            patch.dict(os.environ, child, clear=True),
            patch.object(
                foundation,
                "create_async_engine",
                side_effect=AssertionError("No engine in Settings regression"),
            ) as engine,
            patch(
                "socket.getaddrinfo", side_effect=AssertionError("No DNS in Settings regression")
            ),
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("No network in Settings regression"),
            ),
        ):
            settings = foundation.Settings()
            self.assertEqual(settings.environment, "TEST")
            self.assertEqual(settings.database_url.get_secret_value(), synthetic_url)
            # The unchanged foundation must still reject a missing environment.
            del os.environ["ASM_ENVIRONMENT"]
            with self.assertRaises(ValidationError) as missing:
                foundation.Settings()
            self.assertEqual(
                [
                    (row["loc"], row["type"])
                    for row in missing.exception.errors(include_input=False)
                ],
                [(("environment",), "missing")],
            )
        engine.assert_not_called()

    def test_real_settings_validates_test_without_parent_environment(self):
        self.assert_test_settings({})

    def test_real_settings_remains_test_with_non_test_parent_environment(self):
        for environment in ("LOCAL", "PRODUCTION"):
            with self.subTest(parent_environment=environment):
                self.assert_test_settings(
                    {
                        "ASM_ENVIRONMENT": environment,
                        "ASM_DATABASE_URL": "foreign-invalid-url",
                        "ASM_MIGRATION_DATABASE_URL": "foreign-migrator",
                        "ASM_NATIVE_TEST_ADMIN_URL": "foreign-admin",
                        "ASM_NATIVE_TEST_ALLOW_RESET": "1",
                        "ASM_AUTH_ORIGINS": "hostile-invalid-json",
                        "GITHUB_TOKEN": "synthetic-parent-token",
                    }
                )


class ExecutionEvidence(unittest.TestCase):
    def test_payload_failure_and_cleanup_failure_cannot_be_masked(self):
        # Complete orchestration with mocked commands/resources. No Docker or DB
        # is contacted, and these toy receipts are deleted with the fixture.
        for carrier_exit, cleanup_failure in ((7, False), (0, True)):
            with self.subTest(carrier_exit=carrier_exit, cleanup_failure=cleanup_failure):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    private, evidence = root / "private", root / "evidence"
                    private.mkdir()
                    evidence.mkdir()
                    (root / "job-start").write_text(str(int(time.time())))
                    commands = Mock(passwords=())

                    def command(argv, **kwargs):
                        if argv == ["uv", "--version"]:
                            return 0, b"uv 0.10.0\n"
                        if argv[:2] == ["git", "--version"]:
                            return 0, b"git version unit-fixture\n"
                        if argv[:2] == ["docker", "version"]:
                            return 0, b'"unit-fixture"'
                        if "pytest" in argv:
                            (private / "runner-unit.xml").write_text(
                                '<testsuites><testsuite><testcase name="guard"/></testsuite></testsuites>'
                            )
                        if argv[-1] == "carrier":
                            return carrier_exit, b"mock carrier"
                        return 0, b"mock unit/static/catalog"

                    commands.run.side_effect = command
                    env = {
                        "GITHUB_SHA": "b" * 40,
                        "GITHUB_EVENT_NAME": "push",
                        "GITHUB_REF": lane.EXECUTION_REF,
                        "GITHUB_REPOSITORY": "Elefesys/ai-service-manager",
                        "GITHUB_RUN_ID": "123",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "UV_PROJECT_ENVIRONMENT": str(Path(lane.sys.prefix).resolve()),
                        "UV_CACHE_DIR": str(root / "uv-cache"),
                        "RUFF_CACHE_DIR": str(root / "ruff-cache"),
                    }
                    cleanup_error = (
                        lane.Refusal("mock foreign cleanup identity") if cleanup_failure else None
                    )
                    with (
                        patch.dict(os.environ, env),
                        patch.object(lane.sys, "version_info", (3, 13, 0)),
                        patch.object(lane, "Commands", return_value=commands),
                        patch.object(lane, "require_source", return_value=("e" * 40, [])),
                        patch.object(lane, "git_bytes", return_value=b"mock source archive"),
                        patch.object(
                            lane,
                            "admit_event",
                            return_value=({"head": "b" * 40, "tree": "e" * 40}, []),
                        ),
                        patch.object(lane, "prove_partition", return_value=({}, [])),
                        patch.object(
                            lane, "source_catalog", return_value={"functions": {}, "columns": {}}
                        ),
                        patch.object(lane.importlib.metadata, "distributions", return_value=[]),
                        patch.object(lane, "create_database", return_value={}),
                        patch.object(lane, "cleanup", side_effect=cleanup_error) as cleanup,
                    ):
                        result = lane.run_lane(private, evidence)
                    self.assertNotEqual(result, 0)
                    receipt = json.loads((evidence / "receipt.json").read_text())
                    self.assertEqual(receipt["result"], "FAIL")
                    self.assertEqual(receipt["carrier_exit"], carrier_exit)
                    self.assertEqual(receipt["catalog_exit"], 0)
                    cleanup.assert_called_once()

    def test_sqlstate_survives_wrapped_exceptions_without_exposing_parameters(self):
        original = RuntimeError("private SQL parameters")
        original.sqlstate = "23514"
        wrapped = RuntimeError("wrapper")
        wrapped.orig = original
        wrapped.__cause__ = original
        original.__context__ = wrapped
        self.assertEqual(lane.exception_sqlstates(wrapped), ["23514"])
        self.assertEqual(lane.exception_sqlstates(None), [])

    def test_future_regressions_are_collected_without_a_fixed_total(self):
        nodes = [module + "::test_new_regression" for module in REQUIRED_MODULES]
        reports = complete_reports(nodes)
        lane.validate_collection(nodes, [], reports, 0)
        nodes.append(lane.MODULES[1] + "::test_another_regression")
        reports.extend(complete_reports(nodes[-1:]))
        lane.validate_collection(nodes, [], reports, 0)

    def test_skip_xfail_no_tests_deselection_and_incomplete_execution_cannot_pass(self):
        nodes = [module + "::test_case" for module in REQUIRED_MODULES]
        good = complete_reports(nodes)
        cases = [([], [], [], 5), (nodes, ["deselected"], good, 0), (nodes, [], good[:-1], 0)]
        for key, value in (("outcome", "skipped"), ("xfail", True)):
            reports = copy.deepcopy(good)
            reports[-1][key] = value
            cases.append((nodes, [], reports, 0))
        for case in cases:
            with self.subTest(case=case), self.assertRaises(lane.Refusal):
                lane.validate_collection(*case)
        # Failure status is retained, not retried or transformed into success.
        lane.validate_collection(nodes, [], good[:-1], 1)

    def test_urls_passwords_and_junit_traces_are_redacted(self):
        secret = "sensitive" + "0123456789" * 4
        raw = (
            "<failure>postgresql+psycopg://asm_runtime:"
            + secret
            + "@127.0.0.1:34567/asm_test password="
            + secret
            + "</failure>"
        )
        clean = lane.redact(raw, (secret,))
        self.assertNotIn(secret, clean)
        self.assertNotIn("postgresql", clean)
        self.assertIn("[DB_URL]", clean)

    def test_empty_or_skipped_unit_junit_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unit.xml"
            for xml in (
                "<testsuites/>",
                '<testsuites><testsuite><testcase name="guard"><skipped/></testcase></testsuite></testsuites>',
            ):
                path.write_text(xml)
                with self.assertRaises(lane.Refusal):
                    lane.require_unit_junit(path)
            path.write_text(
                '<testsuites><testsuite><testcase name="guard"/></testsuite></testsuites>'
            )
            lane.require_unit_junit(path)

    def test_reset_optin_and_urls_are_absent_from_child_environment_until_guarded(self):
        with patch.dict(
            os.environ,
            {
                "ASM_DATABASE_URL": "foreign",
                "ASM_NATIVE_TEST_ALLOW_RESET": "1",
                "GITHUB_TOKEN": "private",
                "PYTEST_ADDOPTS": "-k subset",
            },
        ):
            env = lane.child_environment(Path("/outside/private"))
        self.assertTrue(
            all(key not in env for key in (*lane.SECRET_ENV, "GITHUB_TOKEN", "PYTEST_ADDOPTS"))
        )

    def test_changed_reset_url_or_optin_refuses_before_destructive_call(self):
        lease = {
            "port": 34567,
            "passwords": {key: key + "123" for key in ("admin", "runtime", "migrator")},
        }
        for key in lane.SECRET_ENV:
            with self.subTest(key=key), patch.dict(os.environ, lane.urls(lease)):
                lane.require_child_urls(lease)
                os.environ[key] = "foreign"
                destructive = Mock()
                with self.assertRaises(lane.Refusal):
                    lane.guarded_reset(
                        lambda: None, lambda: lane.require_child_urls(lease), destructive
                    )
                destructive.assert_not_called()

    def test_artifacts_and_cache_must_be_outside_checkout(self):
        with self.assertRaises(lane.Refusal):
            lane.external_directory(lane.ROOT / "artifacts")

    def test_workflow_has_one_exact_push_branch_one_job_and_whole_job_cap(self):
        text = (lane.ROOT / ".github/workflows/native-context-db.yml").read_text()
        self.assertIn("branches: [c0/m3-1-native-context-db-stock-r1]", text)
        self.assertIn("timeout-minutes: 20", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertEqual(text.count("runs-on:"), 1)
        self.assertNotIn("secrets.", text)
        for forbidden in ("workflow_dispatch:", "pull_request:", "schedule:"):
            self.assertNotIn(forbidden, text)
        for line in text.splitlines():
            if "uses:" in line:
                self.assertRegex(line, r"uses: (?:actions|astral-sh)/[a-z-]+@[0-9a-f]{40}")

    def test_job_env_does_not_use_runner_context_before_a_runner_exists(self):
        text = (lane.ROOT / ".github/workflows/native-context-db.yml").read_text()
        job_env = text.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("${{", job_env)
        self.assertIn('TASK_ROOT="$RUNNER_TEMP/native-context-db"', text)
        self.assertIn('>> "$GITHUB_ENV"', text)


class FourModuleCollection(unittest.TestCase):
    def setUp(self):
        self.nodes = [module + "::test_case" for module in REQUIRED_MODULES]
        self.reports = complete_reports(self.nodes)

    def test_omitting_api_or_runtime_fails_even_with_all_remaining_reports_passed(self):
        for omitted in REQUIRED_MODULES[2:]:
            with self.subTest(omitted=omitted), self.assertRaises(lane.Refusal):
                nodes = [node for node in self.nodes if not node.startswith(omitted + "::")]
                lane.validate_collection(nodes, [], complete_reports(nodes), 0)

    def test_missing_setup_call_or_teardown_report_cannot_pass(self):
        for index, row in enumerate(self.reports):
            with self.subTest(node=row["nodeid"], phase=row["when"]):
                with self.assertRaises(lane.Refusal):
                    lane.validate_collection(
                        self.nodes, [], self.reports[:index] + self.reports[index + 1 :], 0
                    )

    def test_failed_setup_call_or_teardown_cannot_pass(self):
        for phase in ("setup", "call", "teardown"):
            with self.subTest(phase=phase):
                reports = copy.deepcopy(self.reports)
                next(row for row in reports if row["when"] == phase)["outcome"] = "failed"
                with self.assertRaises(lane.Refusal):
                    lane.validate_collection(self.nodes, [], reports, 0)
                # A real nonzero pytest result remains a whole-run failure.
                lane.validate_collection(self.nodes, [], reports, 1)

    def test_duplicate_nodes_reports_foreign_nodes_and_unknown_phases_refuse(self):
        for case in ("duplicate_node", "duplicate_report", "foreign_node", "phase", "outcome"):
            with self.subTest(case=case), self.assertRaises(lane.Refusal):
                nodes, reports = list(self.nodes), copy.deepcopy(self.reports)
                if case == "duplicate_node":
                    nodes.append(nodes[-1])
                elif case == "duplicate_report":
                    reports.append(dict(reports[-1]))
                elif case == "foreign_node":
                    reports.append(dict(reports[-1], nodeid=nodes[-1] + "_uncollected"))
                elif case == "phase":
                    reports.append(dict(reports[-1], when="unknown"))
                else:
                    reports[-1]["outcome"] = "unknown"
                lane.validate_collection(nodes, [], reports, 0)

    def test_skip_or_xfail_in_any_phase_cannot_pass(self):
        for phase in ("setup", "call", "teardown"):
            for key, value in (("outcome", "skipped"), ("xfail", True)):
                with self.subTest(phase=phase, field=key), self.assertRaises(lane.Refusal):
                    reports = copy.deepcopy(self.reports)
                    next(row for row in reports if row["when"] == phase)[key] = value
                    lane.validate_collection(self.nodes, [], reports, 0)


class CarrierFixtureGuards(unittest.TestCase):
    """Real imported fixture bodies, mocked pytest/resources; no service or SQL."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.private, self.evidence = self.root / "private", self.root / "evidence"
        self.private.mkdir()
        self.evidence.mkdir()
        self.modules = {path: importlib.import_module(Path(path).stem) for path in REQUIRED_MODULES}
        self.db = self.modules[REQUIRED_MODULES[1]]
        self.original_reset = self.db.reset_disposable
        self.nodes = [path + "::test_case" for path in REQUIRED_MODULES]
        self.lease = {
            "source_sha": "b" * 40,
            "port": 34567,
            "passwords": {key: "synthetic-" + key for key in ("admin", "runtime", "migrator")},
        }
        self.commands = Mock(passwords=())

    def items(self):
        items = []
        for node in self.nodes:
            path = node.split("::", 1)[0]
            module = self.modules[path]
            definitions = (
                {"native": (SimpleNamespace(func=inspect.unwrap(module.native)),)}
                if path in REQUIRED_MODULES[1:]
                else {}
            )
            items.append(
                SimpleNamespace(
                    nodeid=node,
                    module=module,
                    _fixtureinfo=SimpleNamespace(name2fixturedefs=definitions),
                )
            )
        return items

    def run_carrier(self, *, action=None, exit_code=0, items=None, reports=None):
        def pytest_main(argv, *, plugins):
            self.argv = argv
            audit = plugins[0]
            audit.pytest_collection_finish(
                SimpleNamespace(items=self.items() if items is None else items)
            )
            if action:
                action(audit)
            for row in complete_reports(self.nodes) if reports is None else reports:
                report = SimpleNamespace(
                    **{key: value for key, value in row.items() if key != "xfail"},
                    duration=0.001,
                    failed=row["outcome"] == "failed",
                    longrepr="synthetic runner failure",
                )
                if row["xfail"]:
                    report.wasxfail = "synthetic xfail"
                audit.pytest_runtest_logreport(report)
            return exit_code

        try:
            with patch("pytest.main", side_effect=pytest_main):
                return lane.carrier(self.private, self.evidence, self.lease, self.commands)
        finally:
            self.assertIs(self.db.reset_disposable, self.original_reset)

    def enter_native(self, path):
        # The actual async fixture executes to_thread(reset_disposable). Its
        # first psycopg.connect is blocked below, before any SQL or migration.
        generator = inspect.unwrap(self.modules[path].native)(SimpleNamespace(), self.root)
        return asyncio.run(generator.__anext__())

    def test_four_complete_paths_and_future_api_runtime_cases_are_used(self):
        for path in REQUIRED_MODULES[2:]:
            self.nodes.append(path + "::test_future_c3_case[appended]")
        self.assertEqual(self.run_carrier(), 0)
        self.assertEqual(tuple(self.argv[:4]), REQUIRED_MODULES)
        self.assertFalse(any(arg in self.argv for arg in ("-k", "-m", "--deselect")))
        collection = json.loads((self.evidence / "collection.json").read_text())
        self.assertEqual(collection["nodeids"], self.nodes)
        self.assertEqual(
            collection["per_module"],
            {
                path: [node for node in self.nodes if node.startswith(path + "::")]
                for path in REQUIRED_MODULES
            },
        )
        self.assertEqual(collection["count"], 6)
        self.assertFalse(collection["fixed_total_required"])
        guards = json.loads((self.evidence / "fixture-guards.json").read_text())
        self.assertEqual(guards["reset_entry_point"], REQUIRED_MODULES[1] + "::reset_disposable")
        self.assertEqual(
            guards["per_module"], {p: collection["per_module"][p] for p in REQUIRED_MODULES[1:]}
        )
        results = json.loads((self.evidence / "test-results.json").read_text())
        self.assertEqual(len(results["reports"]), 18)

    def test_collection_hook_rejects_missing_api_or_runtime_before_any_fixture(self):
        for omitted in REQUIRED_MODULES[2:]:
            with self.subTest(omitted=omitted):
                self.nodes = [path + "::test_case" for path in REQUIRED_MODULES if path != omitted]
                with (
                    patch(
                        "psycopg.connect", side_effect=AssertionError("No connection")
                    ) as connect,
                    self.assertRaises(lane.Refusal),
                ):
                    self.run_carrier()
                connect.assert_not_called()
                collection = json.loads((self.evidence / "collection.json").read_text())
                self.assertEqual(collection["per_module"][omitted], [])
                self.assertEqual(collection["count"], 3)

    def test_all_pg_consumers_call_same_guard_before_real_reset_entry_point(self):
        events = []

        def source(*args):
            events.append("source")

        def owner(*args):
            events.append("owner")
            lease, container, volume = owned_fixture()
            lane.validate_container(lease, container)
            lane.validate_volume(lease, volume)
            return {"unit_mock": True}

        def blocked_connect(*args, **kwargs):
            events.append("reset_entry")
            raise RuntimeError("blocked first connection; no SQL")

        def exercise(audit):
            for path in REQUIRED_MODULES[1:]:
                with self.subTest(module=path):
                    self.assertIs(self.modules[path].native, self.db.native)
                    self.assertIs(self.db.reset_disposable.__wrapped__, self.original_reset)
                    with self.assertRaisesRegex(RuntimeError, "blocked first connection"):
                        self.enter_native(path)

        with (
            patch.dict(os.environ, lane.urls(self.lease)),
            patch.object(lane, "require_source", side_effect=source),
            patch.object(lane, "verify_server", side_effect=owner),
            patch("psycopg.connect", side_effect=blocked_connect) as connect,
            patch("asyncio.create_subprocess_exec", side_effect=AssertionError("No migration")),
        ):
            self.assertEqual(self.run_carrier(action=exercise), 0)
        self.assertEqual(events, ["source", "owner", "reset_entry"] * 3)
        self.assertEqual(connect.call_count, 3)
        proofs = json.loads((self.evidence / "before-reset-proofs.json").read_text())
        self.assertEqual([row["reset"] for row in proofs], [1, 2, 3])

    def test_each_pg_consumer_refuses_source_url_and_owner_drift_before_reset(self):
        for path in REQUIRED_MODULES[1:]:
            for guard in ("source", "url", "owner"):
                with self.subTest(module=path, guard=guard):
                    env = lane.urls(self.lease)
                    if guard == "url":
                        env["ASM_NATIVE_TEST_ALLOW_RESET"] = "foreign"
                    with (
                        patch.dict(os.environ, env),
                        patch.object(
                            lane,
                            "require_source",
                            side_effect=lane.Refusal("source drift") if guard == "source" else None,
                        ) as source,
                        patch.object(
                            lane,
                            "verify_server",
                            side_effect=lane.Refusal("owner drift") if guard == "owner" else None,
                        ) as owner,
                        patch(
                            "psycopg.connect", side_effect=AssertionError("No connection")
                        ) as connect,
                        patch(
                            "asyncio.create_subprocess_exec",
                            side_effect=AssertionError("No migration"),
                        ),
                    ):

                        def exercise(audit):
                            self.enter_native(path)

                        with self.assertRaises(lane.Refusal):
                            self.run_carrier(action=exercise)
                    source.assert_called_once_with(lane.ROOT, self.lease["source_sha"])
                    if guard in ("source", "url"):
                        owner.assert_not_called()
                    else:
                        owner.assert_called_once_with(self.lease, self.commands)
                    connect.assert_not_called()

    def test_import_alias_or_resolved_fixture_drift_refuses_before_reset(self):
        for path in REQUIRED_MODULES[2:]:
            with self.subTest(module=path, drift="imported alias"):
                items = self.items()
                with patch.object(self.modules[path], "native", object()):
                    with self.assertRaises(lane.Refusal):
                        self.run_carrier(items=items)
        for path in REQUIRED_MODULES[1:]:
            for drift in ("override", "absent"):
                with self.subTest(module=path, drift=drift):
                    items = self.items()
                    item = next(item for item in items if item.nodeid.startswith(path + "::"))
                    definitions = item._fixtureinfo.name2fixturedefs
                    if drift == "absent":
                        definitions.clear()
                    else:
                        definitions["native"] = (SimpleNamespace(func=lambda: None),)
                    with self.assertRaises(lane.Refusal):
                        self.run_carrier(items=items)

    def test_reset_restored_and_failure_evidence_retained_on_exception_or_nonzero(self):
        for failure in ("exception", "nonzero"):
            with self.subTest(failure=failure):

                def action(audit):
                    self.assertIsNot(self.db.reset_disposable, self.original_reset)
                    if failure == "exception":
                        raise RuntimeError("synthetic pytest exception")

                reports = complete_reports(self.nodes)
                reports[-1]["outcome"] = "failed"
                if failure == "exception":
                    with self.assertRaisesRegex(RuntimeError, "synthetic pytest exception"):
                        self.run_carrier(action=action)
                else:
                    self.assertEqual(
                        self.run_carrier(action=action, exit_code=7, reports=reports), 7
                    )
                result = json.loads((self.evidence / "test-results.json").read_text())
                self.assertEqual(result["pytest_exit"], 1 if failure == "exception" else 7)
                collection = json.loads((self.evidence / "collection.json").read_text())
                self.assertEqual(collection["nodeids"], self.nodes)


def ci_event(tmp_path, route):
    repository = {"full_name": lane.REPOSITORY, "id": lane.REPOSITORY_ID, "fork": False}
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": lane.REPOSITORY,
        "GITHUB_REPOSITORY_ID": str(lane.REPOSITORY_ID),
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": lane.EXECUTION_REF if route == "stock-push" else "refs/heads/main",
        "GITHUB_SHA": "b" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_EVENT_PATH": str(tmp_path / "event.json"),
        "UV_PROJECT_ENVIRONMENT": str(Path(lane.sys.prefix).resolve()),
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
        "RUFF_CACHE_DIR": str(tmp_path / "ruff-cache"),
    }
    payload = {
        "repository": repository,
        "ref": env["GITHUB_REF"],
        "after": env["GITHUB_SHA"],
        "head_commit": {"id": env["GITHUB_SHA"]},
        "deleted": False,
        "base_ref": None,
    }
    if route == "same-repository-pr-merge":
        env.update(
            GITHUB_EVENT_NAME="pull_request",
            GITHUB_REF="refs/pull/42/merge",
            GITHUB_BASE_REF="main",
            GITHUB_HEAD_REF="candidate",
        )
        payload = {
            "repository": repository,
            "action": "synchronize",
            "number": 42,
            "pull_request": {
                "number": 42,
                "state": "open",
                "merged": False,
                "merge_commit_sha": env["GITHUB_SHA"],
                "base": {"ref": "main", "sha": "c" * 40, "repo": copy.deepcopy(repository)},
                "head": {"ref": "candidate", "sha": "d" * 40, "repo": copy.deepcopy(repository)},
            },
        }
    return env, payload


def exercise_ci_lane(
    tmp_path,
    env,
    payload,
    *,
    parents=None,
    raw=None,
    carrier_exit=0,
    catalog_exit=0,
    cleanup_failure=False,
    partition_failure=False,
    retained_state=False,
    actual_head="b" * 40,
    header_tree="e" * 40,
    source_failure=None,
):
    """Real JSON/admission/source-input checks; every command/resource is mocked."""
    private, evidence = tmp_path / "private", tmp_path / "evidence"
    private.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    if retained_state:
        (private / "state.json").write_text("Unadopted private state")
    (tmp_path / "job-start").write_text(str(int(time.time())))
    Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload) if raw is None else raw)
    commands = Mock(passwords=())

    def command(argv, **kwargs):
        if argv == ["uv", "--version"]:
            return 0, b"uv 0.10.0\n"
        if argv[:2] == ["docker", "version"]:
            return 0, b'"unit-only"'
        if "pytest" in argv:
            (private / "runner-unit.xml").write_text(
                '<testsuites><testsuite><testcase name="guard"/></testsuite></testsuites>'
            )
        if argv[-1] == "carrier":
            return carrier_exit, b"unit-only carrier"
        if argv[-1] == "catalog":
            return catalog_exit, b"unit-only catalog"
        return 0, b"unit-only command"

    commands.run.side_effect = command
    parent_lines = ["c" * 40, "d" * 40] if parents is None else parents
    headers = (
        "tree "
        + header_tree
        + "\n"
        + "".join("parent " + p + "\n" for p in parent_lines)
        + "\nunit-only commit"
    ).encode()
    with (
        patch.dict(os.environ, env, clear=True),
        patch.object(
            lane, "require_source", return_value=("e" * 40, []), side_effect=source_failure
        ),
        patch.object(
            lane,
            "git_bytes",
            side_effect=lambda root, *args: (
                headers
                if args == ("cat-file", "-p", "HEAD")
                else actual_head.encode()
                if args == ("rev-parse", "HEAD")
                else b"unit-only archive"
            ),
        ) as git,
        patch.object(lane, "Commands", return_value=commands),
        patch.object(lane, "source_catalog", return_value={"functions": {}, "columns": {}}),
        patch.object(lane.importlib.metadata, "distributions", return_value=[]),
        patch.object(
            lane,
            "prove_partition",
            side_effect=lane.Refusal("partition failure") if partition_failure else None,
        ) as partition,
        patch.object(lane, "create_database") as create,
        patch.object(lane, "collect_owned_logs") as logs,
        patch.object(
            lane,
            "cleanup",
            side_effect=lane.Refusal("cleanup failure") if cleanup_failure else None,
        ) as cleanup,
    ):
        result = lane.run_lane(private, evidence)
    return SimpleNamespace(
        result=result,
        receipt=json.loads((evidence / "receipt.json").read_text()),
        evidence=evidence,
        commands=commands,
        create=create,
        logs=logs,
        cleanup=cleanup,
        partition=partition,
        git=git,
    )


@pytest.mark.parametrize("route", ("stock-push", "main-push", "same-repository-pr-merge"))
def test_ci_actual_event_identity_and_archive_are_never_relabelled(tmp_path, route):
    env, payload = ci_event(tmp_path, route)
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result == 0
    identity = json.loads((probe.evidence / "source-identity.json").read_text())
    assert identity["route"] == route
    assert identity["event"] == env["GITHUB_EVENT_NAME"]
    assert identity["ref"] == env["GITHUB_REF"]
    assert (identity["head"], identity["tree"], identity["run_id"], identity["attempt"]) == (
        env["GITHUB_SHA"],
        "e" * 40,
        "123",
        "2",
    )
    assert identity["source_archive_sha256"] == lane.sha256(
        (probe.evidence / "source.tar").read_bytes()
    )
    assert identity["event_payload_sha256"] == lane.sha256(
        Path(env["GITHUB_EVENT_PATH"]).read_bytes()
    )
    assert identity["event_identity_is_c0_approval"] is False
    assert probe.receipt["source_identity"]["event"] == identity["event"]
    probe.git.assert_any_call(lane.ROOT, "cat-file", "-p", "HEAD")
    probe.create.assert_called_once()
    probe.cleanup.assert_called_once()
    if route == "same-repository-pr-merge":
        assert identity["merge_parents"] == [
            payload["pull_request"][key]["sha"] for key in ("base", "head")
        ]


@pytest.mark.parametrize(
    "key,value",
    (
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_REPOSITORY", "foreign/repo"),
        ("GITHUB_REPOSITORY_ID", "1"),
        ("GITHUB_EVENT_NAME", "workflow_call"),
        ("GITHUB_EVENT_NAME", "workflow_dispatch"),
        ("GITHUB_EVENT_NAME", "pull_request_target"),
        ("GITHUB_REF", "refs/heads/other"),
        ("GITHUB_REF", "refs/tags/main"),
        ("GITHUB_RUN_ID", "0"),
        ("GITHUB_RUN_ATTEMPT", "01"),
        ("GITHUB_RUN_ATTEMPT", "١"),
        ("GITHUB_SHA", "a" * 40),
        ("GITHUB_BASE_REF", "main"),
        ("GITHUB_HEAD_REF", "candidate"),
    ),
)
def test_ci_bad_event_context_refuses_all_commands_and_resource_recovery(tmp_path, key, value):
    env, payload = ci_event(tmp_path, "stock-push")
    env[key] = value
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    assert probe.receipt["owned_cleanup"] == "NOT_ATTEMPTED_EVENT_REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup, probe.partition):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "change",
    (
        "repository",
        "repository-id",
        "fork",
        "push-ref",
        "push-after",
        "push-head",
        "deleted",
        "pr-base",
        "pr-env-base",
        "pr-head",
        "pr-head-repository",
        "pr-base-repository",
        "pr-ref",
        "pr-number",
        "pr-state",
        "pr-action",
        "pr-merge",
        "pr-head-sha",
        "pr-base-sha",
    ),
)
def test_ci_payload_target_and_merge_mismatch_refuses_before_docker(tmp_path, change):
    env, payload = ci_event(
        tmp_path, "same-repository-pr-merge" if change.startswith("pr-") else "main-push"
    )
    pr = payload.get("pull_request", {})
    if change == "repository":
        payload["repository"]["full_name"] = "foreign/repo"
    elif change == "repository-id":
        payload["repository"]["id"] = True
    elif change == "fork":
        payload["repository"]["fork"] = True
    elif change == "push-ref":
        payload["ref"] = lane.EXECUTION_REF
    elif change == "push-after":
        payload["after"] = "a" * 40
    elif change == "push-head":
        payload["head_commit"]["id"] = "a" * 40
    elif change == "deleted":
        payload["deleted"] = True
    elif change == "pr-base":
        pr["base"]["ref"] = "other"
    elif change == "pr-env-base":
        env["GITHUB_BASE_REF"] = "other"
    elif change == "pr-head":
        env["GITHUB_HEAD_REF"] = "other"
    elif change == "pr-head-repository":
        pr["head"]["repo"]["full_name"] = "fork/repo"
    elif change == "pr-base-repository":
        pr["base"]["repo"]["id"] = 1
    elif change == "pr-ref":
        env["GITHUB_REF"] = "refs/pull/42/head"
    elif change == "pr-number":
        payload["number"] = "42"
    elif change == "pr-state":
        pr["state"] = "closed"
    elif change == "pr-action":
        payload["action"] = "closed"
    elif change == "pr-merge":
        # A well-formed stale snapshot is advisory. Malformed values still refuse.
        pr["merge_commit_sha"] = "not-a-commit"
    elif change == "pr-head-sha":
        pr["head"]["sha"] = "a" * 40
    elif change == "pr-base-sha":
        pr["base"]["sha"] = "a" * 40
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "parents",
    ([], ["d" * 40], ["d" * 40, "c" * 40], ["c" * 40, "a" * 40], ["c" * 40, "d" * 40, "a" * 40]),
)
def test_ci_real_commit_headers_must_bind_both_ordered_merge_parents(tmp_path, parents):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    probe = exercise_ci_lane(tmp_path, env, payload, parents=parents)
    assert probe.result != 0
    probe.commands.run.assert_not_called()
    probe.cleanup.assert_not_called()


@pytest.mark.parametrize("raw", ("{}", "[]", "{", '{"repository":{},"repository":{}}', "null"))
def test_ci_malformed_actual_event_payload_refuses_without_resources(tmp_path, raw):
    env, payload = ci_event(tmp_path, "main-push")
    probe = exercise_ci_lane(tmp_path, env, payload, raw=raw)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("carrier,catalog,cleanup", ((7, 0, False), (0, 9, False), (0, 0, True)))
def test_ci_admitted_routes_keep_payload_and_cleanup_failures(tmp_path, carrier, catalog, cleanup):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    probe = exercise_ci_lane(
        tmp_path, env, payload, carrier_exit=carrier, catalog_exit=catalog, cleanup_failure=cleanup
    )
    assert probe.result != 0 and probe.receipt["result"] == "FAIL"
    assert probe.receipt["carrier_exit"] == carrier and probe.receipt["catalog_exit"] == catalog
    probe.cleanup.assert_called_once()


def test_ci_partition_failure_stops_before_first_docker_command(tmp_path):
    env, payload = ci_event(tmp_path, "main-push")
    probe = exercise_ci_lane(tmp_path, env, payload, partition_failure=True)
    assert probe.result != 0
    assert all(call.args[0][0] != "docker" for call in probe.commands.run.call_args_list)
    probe.create.assert_not_called()
    probe.cleanup.assert_called_once()


def test_ci_run_never_adopts_retained_state_even_with_the_same_event(tmp_path):
    env, payload = ci_event(tmp_path, "main-push")
    probe = exercise_ci_lane(tmp_path, env, payload, retained_state=True)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "field", (None, "source_sha", "tree", "asm.c6.source", "asm.c6.tree", "asm.c6.run")
)
def test_ci_child_and_recovery_lease_bind_source_tree_run_and_attempt(tmp_path, field):
    identity = {"head": "b" * 40, "tree": "e" * 40, "run_id": "123", "attempt": "2"}
    lease = {
        "name": "asm-native-" + "a" * 32,
        "bootstrap": str(lane.ROOT / "infra/postgres/bootstrap.sh"),
        "source_sha": identity["head"],
        "tree": identity["tree"],
        "labels": {
            "asm.c6.source": identity["head"],
            "asm.c6.tree": identity["tree"],
            "asm.c6.run": "123:2",
        },
    }
    if field:
        (lease["labels"] if field.startswith("asm.") else lease)[field] = "foreign"
    lane.private_json(tmp_path / "state.json", lease)
    with patch.object(lane, "Commands") as commands:
        if field:
            with pytest.raises(lane.Refusal):
                lane.require_event_lease(tmp_path, identity)
        else:
            lane.require_event_lease(tmp_path, identity)
    commands.assert_not_called()


@pytest.mark.parametrize("mode", ("cleanup", "carrier", "catalog"))
def test_ci_secondary_entrypoints_cannot_adopt_resources_for_bad_event(tmp_path, mode):
    with (
        patch.dict(os.environ, {"NATIVE_ROOT": str(tmp_path)}, clear=True),
        patch.object(lane.sys, "argv", ["runner", mode]),
        patch.object(lane.signal, "signal"),
        patch.object(lane, "admit_event", side_effect=lane.Refusal("bad actual event")),
        patch.object(lane, "cleanup") as cleanup,
        patch.object(lane, "load_lease") as lease,
        patch.object(lane, "verify_server") as server,
    ):
        with pytest.raises(lane.Refusal):
            if mode == "cleanup":
                lane.main()
            else:
                lane.child(mode, tmp_path, tmp_path)
    for mock in (cleanup, lease, server):
        mock.assert_not_called()


def partition_fixture():
    native = [path + "::test_case" for path in REQUIRED_MODULES]
    generic = ["tests/test_tenancy_postgres.py::test_old", "tests/test_other_postgres.py::test_new"]

    def inventory(nodes, pg, fixtures, deselected):
        return {
            "collection_exit": 0,
            "nodeids": nodes,
            "integration_nodeids": pg,
            "native_fixture_nodes": fixtures,
            "deselected": deselected,
        }

    return (
        inventory(generic + native[1:], generic + native[1:], native[1:], native[:1]),
        inventory(native, native[1:], native[1:], []),
        inventory(generic, generic[:], [], native[:1]),
    )


def test_ci_partition_uses_exact_modules_dynamic_ids_and_separate_source_tests():
    assert lane.PG_MODULES == REQUIRED_MODULES[1:]
    a, n, g = partition_fixture()
    assert lane.validate_partition(a, n, g)["native_source"] == 1
    for inventory in (a, n):
        for key in ("nodeids", "integration_nodeids", "native_fixture_nodes"):
            inventory[key].append(REQUIRED_MODULES[3] + "::test_future_case[new]")
    proof = lane.validate_partition(a, n, g)
    assert (proof["all_pg"], proof["generic_pg"], proof["native_pg"], proof["native_total"]) == (
        6,
        2,
        4,
        5,
    )
    assert proof["disjoint_pg_sets_and_complete_union"] and proof["fixed_total_required"] is False


@pytest.mark.parametrize(
    "change",
    (
        "lost-generic",
        "lost-native",
        "module",
        "duplicate",
        "exit",
        "foreign",
        "marker",
        "skip-selection",
        "fixture-escape",
        "fixture-loss",
        "generic-order",
        "source-marker",
    ),
)
def test_ci_partition_refuses_lost_cases_modules_markers_and_fixture_escape(change):
    a, n, g = partition_fixture()
    if change == "lost-generic":
        g["nodeids"].pop()
    elif change == "lost-native":
        n["nodeids"].pop()
    elif change == "duplicate":
        g["nodeids"].append(g["nodeids"][0])
    elif change == "exit":
        a["collection_exit"] = 2
    elif change == "foreign":
        g["nodeids"].append("tests/test_foreign.py::test_x")
    elif change == "marker":
        n["integration_nodeids"].pop()
    elif change == "skip-selection":
        n["deselected"].append("test_hidden")
    elif change == "fixture-escape":
        g["native_fixture_nodes"].append(g["nodeids"][0])
    elif change == "fixture-loss":
        a["native_fixture_nodes"].pop()
    elif change == "generic-order":
        g["nodeids"].reverse()
    elif change == "source-marker":
        n["integration_nodeids"].append(n["nodeids"][0])
    with patch.object(
        lane, "MODULES", REQUIRED_MODULES[:-1] if change == "module" else REQUIRED_MODULES
    ):
        with pytest.raises(lane.Refusal):
            lane.validate_partition(a, n, g)


def test_ci_collection_is_collect_only_and_hook_blocks_fixture_execution(tmp_path):
    def collect(argv, *, plugins):
        assert "--collect-only" in argv
        with pytest.raises(lane.Refusal, match="never execute fixtures"):
            plugins[0].pytest_runtest_setup(object())
        return 2

    path = tmp_path / "inventory.json"
    with patch.dict(os.environ, {}, clear=True), patch("pytest.main", side_effect=collect):
        assert lane.collect_partition("collect-all-pg", path) == 2
    assert json.loads(path.read_text())["collection_exit"] == 2


def test_ci_failed_partition_collection_cannot_proceed(tmp_path):
    commands = Mock()
    commands.run.return_value = (2, b"collection error")
    with pytest.raises(lane.Refusal):
        lane.prove_partition(tmp_path, tmp_path, commands, {})
    assert commands.run.call_count == 1


@pytest.mark.parametrize("bad_selection", (False, True))
def test_ci_actual_generic_execution_must_match_proven_inventory(tmp_path, bad_selection):
    expected = partition_fixture()[2]["nodeids"]

    def execute(argv, *, plugins):
        assert argv[:4] == ["-v", "--durations=20", "-m", "integration"]
        assert (
            tuple(arg.removeprefix("--ignore=") for arg in argv if arg.startswith("--ignore="))
            == REQUIRED_MODULES[1:]
        )
        items = [
            SimpleNamespace(nodeid=node) for node in (expected[:-1] if bad_selection else expected)
        ]
        plugins[0].pytest_collection_finish(SimpleNamespace(items=items))
        return 7

    with (
        patch.dict(
            os.environ,
            {
                "ASM_DATABASE_URL": "ordinary-runtime",
                "ASM_MIGRATION_DATABASE_URL": "ordinary-migrator",
            },
            clear=True,
        ),
        patch.object(lane, "prove_partition", return_value=({}, expected)),
        patch.object(lane, "foundation_store"),
        patch.object(lane, "GenericJournal"),
        patch("pytest.main", side_effect=execute),
    ):
        if bad_selection:
            with pytest.raises(lane.Refusal):
                lane.generic_integration()
        else:
            assert lane.generic_integration() == 7


@pytest.mark.parametrize("key", (*lane.SECRET_ENV[:2], "PYTEST_ADDOPTS"))
def test_ci_generic_selection_never_receives_reset_admin_or_subset_flags(key):
    with (
        patch.dict(os.environ, {key: "forbidden"}, clear=True),
        patch.object(lane, "prove_partition") as collect,
    ):
        with pytest.raises(lane.Refusal):
            lane.generic_integration()
    collect.assert_not_called()


@pytest.mark.parametrize("path", tuple(lane.CI_INPUT_SHA256))
def test_ci_guard_reads_actual_inputs_and_refuses_absent_or_changed_gate(tmp_path, path):
    lane.require_ci_inputs()
    for relative in lane.CI_INPUT_SHA256:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((lane.ROOT / relative).read_bytes())
    changed = tmp_path / path
    original = changed.read_bytes()
    changed.write_bytes(
        original.replace(b"native-context-db", b"missing-native-gate", 1)
        if "workflows" in path
        else original.replace(b" generic-integration", b" generic-integration -k subset")
    )
    assert changed.read_bytes() != original
    with patch.object(lane, "ROOT", tmp_path):
        with pytest.raises(lane.Refusal):
            lane.require_ci_inputs()
        changed.unlink()
        with pytest.raises(FileNotFoundError):
            lane.require_ci_inputs()


@pytest.mark.parametrize("action", ("opened", "reopened", "synchronize"))
@pytest.mark.parametrize("advisory", ("current", "null", "missing", "stale"))
def test_ci_pr_snapshot_is_advisory_after_exact_actual_merge_proof(tmp_path, action, advisory):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    payload["action"] = action
    pr = payload["pull_request"]
    if advisory == "missing":
        del pr["merge_commit_sha"]
    else:
        pr["merge_commit_sha"] = {"current": env["GITHUB_SHA"], "null": None, "stale": "a" * 40}[
            advisory
        ]
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result == 0
    identity = probe.receipt["source_identity"]
    assert identity["head"] == env["GITHUB_SHA"] != pr["head"]["sha"]
    assert identity["route"] == "same-repository-pr-merge" and identity["action"] == action
    assert identity["merge_parents"] == [pr["base"]["sha"], pr["head"]["sha"]]
    assert identity["advisory_merge_commit_sha"] == pr.get("merge_commit_sha")
    assert identity["advisory_merge_commit_sha_state"] == advisory
    diagnostic = json.loads((probe.evidence / "event-admission-run.json").read_text())
    assert diagnostic["result"] == "PASS" and diagnostic["failure_reason"] is None
    assert diagnostic["operands"]["actual_head"] == env["GITHUB_SHA"]
    assert diagnostic["operands"]["actual_parents"] == identity["merge_parents"]
    assert diagnostic["operands"]["advisory_merge_commit_sha_state"] == advisory
    assert diagnostic["event_payload_sha256"] == identity["event_payload_sha256"]


@pytest.mark.parametrize("action", ("opened", "reopened", "synchronize"))
@pytest.mark.parametrize(
    "fault,reason",
    (
        ("no-parents", "EVENT_PR_PARENT_COUNT"),
        ("one-parent", "EVENT_PR_PARENT_COUNT"),
        ("reversed", "EVENT_PR_BASE_PARENT"),
        ("base-parent", "EVENT_PR_BASE_PARENT"),
        ("head-parent", "EVENT_PR_HEAD_PARENT"),
        ("extra-parent", "EVENT_PR_PARENT_COUNT"),
        ("event-base", "EVENT_PR_BASE_PARENT"),
        ("event-head", "EVENT_PR_HEAD_PARENT"),
        ("merge-is-base", "EVENT_PR_MERGE_DISTINCT"),
        ("env-sha", "EVENT_SHA_HEAD_MISMATCH"),
        ("env-sha-format", "EVENT_SHA_FORMAT"),
        ("merge-ref", "EVENT_PR_MERGE_REF"),
        ("base-ref", "EVENT_PR_ENV_BASE_REF"),
        ("head-ref", "EVENT_PR_HEAD_REF"),
        ("fork", "EVENT_PR_HEAD_REPOSITORY_FORK"),
        ("base-sha-format", "EVENT_PR_BASE_SHA_FORMAT"),
    ),
)
def test_ci_stale_advisory_cannot_replace_any_actual_merge_operand(tmp_path, action, fault, reason):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    payload["action"] = action
    pr, parents = payload["pull_request"], ["c" * 40, "d" * 40]
    pr["merge_commit_sha"] = "a" * 40
    if fault == "no-parents":
        parents = []
    elif fault == "one-parent":
        parents = parents[:1]
    elif fault == "reversed":
        parents.reverse()
    elif fault == "base-parent":
        parents[0] = "a" * 40
    elif fault == "head-parent":
        parents[1] = "a" * 40
    elif fault == "extra-parent":
        parents.append("a" * 40)
    elif fault == "event-base":
        pr["base"]["sha"] = "a" * 40
    elif fault == "event-head":
        pr["head"]["sha"] = "a" * 40
    elif fault == "merge-is-base":
        pr["base"]["sha"] = parents[0] = env["GITHUB_SHA"]
    elif fault == "env-sha":
        env["GITHUB_SHA"] = "a" * 40
    elif fault == "env-sha-format":
        env["GITHUB_SHA"] = "not-a-sha"
    elif fault == "merge-ref":
        env["GITHUB_REF"] = "refs/pull/42/head"
    elif fault == "base-ref":
        env["GITHUB_BASE_REF"] = "other"
    elif fault == "head-ref":
        env["GITHUB_HEAD_REF"] = "other"
    elif fault == "fork":
        pr["head"]["repo"]["fork"] = True
    elif fault == "base-sha-format":
        pr["base"]["sha"] = "c" * 39
    probe = exercise_ci_lane(tmp_path, env, payload, parents=parents)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    assert probe.receipt["owned_cleanup"] == "NOT_ATTEMPTED_EVENT_REFUSED"
    diagnostic = json.loads((probe.evidence / "event-admission-run.json").read_text())
    assert diagnostic == probe.receipt["admission_diagnostic"]
    assert diagnostic["failure_reason"] == diagnostic["predicate"] == reason
    assert diagnostic["operands"]["actual_head"] == "b" * 40
    assert diagnostic["operands"]["actual_parents"] == parents
    assert diagnostic["event_payload_sha256"] == lane.sha256(
        Path(env["GITHUB_EVENT_PATH"]).read_bytes()
    )
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup, probe.partition):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "value",
    (
        True,
        7,
        [],
        {},
        "",
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "a" * 40 + "\n",
        "https://secret.invalid/credential",
    ),
)
def test_ci_invalid_advisory_type_or_format_is_explicit_and_never_echoed(tmp_path, value):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    payload["pull_request"]["merge_commit_sha"] = value
    probe = exercise_ci_lane(tmp_path, env, payload)
    diagnostic = probe.receipt["admission_diagnostic"]
    assert probe.result != 0 and diagnostic["failure_reason"] == "EVENT_PR_ADVISORY_FORMAT"
    assert diagnostic["operands"]["advisory_merge_commit_sha_state"] == "invalid"
    assert diagnostic["operands"]["advisory_merge_commit_sha"] == "INVALID"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("fault", ("head", "tree", "duplicate-tree", "bytes", "mode"))
def test_ci_real_source_proof_failures_keep_safe_operands_before_commands(tmp_path, fault):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    primary = lane.Refusal("existing source guard refused") if fault in {"bytes", "mode"} else None
    tree = "e" * 40 if fault not in {"tree", "duplicate-tree"} else "f" * 40
    if fault == "duplicate-tree":
        tree += "\ntree " + "e" * 40
    probe = exercise_ci_lane(
        tmp_path,
        env,
        payload,
        actual_head="a" * 40 if fault == "head" else "b" * 40,
        header_tree=tree,
        source_failure=primary,
    )
    reason = (
        "EVENT_SHA_HEAD_MISMATCH"
        if fault == "head"
        else "EVENT_SOURCE_VERIFY"
        if primary
        else "EVENT_HEAD_TREE"
    )
    assert probe.receipt["admission_diagnostic"]["failure_reason"] == reason
    assert probe.receipt["owned_cleanup"] == "NOT_ATTEMPTED_EVENT_REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("fault", ("advisory", "head-ref", "repository", "parent"))
def test_ci_diagnostics_are_bounded_allowlisted_and_omit_payload_env_and_urls(tmp_path, fault):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    secret = "https://credential.invalid/SECRET_PAYLOAD"
    env.update(GITHUB_TOKEN=secret, ARBITRARY_SECRET=secret)
    payload.update(body=secret * 2000, title=secret, html_url=secret, sender={"token": secret})
    pr = payload["pull_request"]
    pr.update(body=secret, title=secret, url=secret)
    parents = ["c" * 40, "d" * 40]
    if fault == "advisory":
        pr["merge_commit_sha"] = {"token": secret}
    elif fault == "head-ref":
        env["GITHUB_HEAD_REF"] = secret
    elif fault == "repository":
        payload["repository"]["full_name"] = secret
    elif fault == "parent":
        parents = [secret] * 7
    probe = exercise_ci_lane(tmp_path, env, payload, parents=parents)
    diagnostic = (probe.evidence / "event-admission-run.json").read_text()
    assert probe.result != 0 and len(diagnostic.encode()) < 8192
    assert secret not in diagnostic and "SECRET_PAYLOAD" not in diagnostic
    assert "GITHUB_TOKEN" not in diagnostic and "ARBITRARY_SECRET" not in diagnostic
    assert "https://" not in diagnostic and '"body"' not in diagnostic
    assert set(json.loads(diagnostic)) == {
        "version",
        "entrypoint",
        "result",
        "predicate",
        "failure_reason",
        "operands",
        "event_payload_sha256",
    }
    if fault == "parent":
        operands = json.loads(diagnostic)["operands"]
        assert operands["parent_count"] == 7 and operands["parents_truncated"]
        assert operands["actual_parents"] == ["INVALID"] * 3
    for path in probe.evidence.iterdir():
        assert "SECRET_PAYLOAD" not in path.read_text()
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("route", ("stock-push", "main-push", "same-repository-pr-merge"))
@pytest.mark.parametrize("primary_failure", (False, True))
def test_ci_diagnostic_write_failure_cannot_hide_refusal_or_authorize_resources(
    tmp_path, route, primary_failure
):
    env, payload = ci_event(tmp_path, route)
    primary = lane.Refusal("unit original source refusal") if primary_failure else None
    original_write = lane.write_json

    def write(path, value):
        if path.name.startswith("event-admission-"):
            raise OSError("unit diagnostic write failed")
        return original_write(path, value)

    with patch.object(lane, "write_json", side_effect=write):
        probe = exercise_ci_lane(tmp_path, env, payload, source_failure=primary)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    assert probe.receipt["owned_cleanup"] == "NOT_ATTEMPTED_EVENT_REFUSED"
    assert not (probe.evidence / "event-admission-run.json").exists()
    diagnostic = probe.receipt["admission_diagnostic"]
    assert diagnostic["result"] == "REFUSED"
    assert diagnostic["failure_reason"] == (
        "EVENT_SOURCE_VERIFY" if primary_failure else "EVENT_DIAGNOSTIC_WRITE_FAILED"
    )
    if primary_failure:
        assert primary.admission_diagnostic is not None
        assert primary.__notes__ == ["EVENT_DIAGNOSTIC_WRITE_FAILED"]
        assert "unit original source refusal" in (probe.evidence / "runner-error.log").read_text()
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("mode", ("cleanup", "carrier", "catalog"))
@pytest.mark.parametrize(
    "fault", ("parents", "malformed", "duplicate", "advisory", "write", "primary-write")
)
def test_ci_secondary_actual_admission_diagnostics_never_load_or_adopt_retained_state(
    tmp_path, mode, fault
):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    env["NATIVE_ROOT"] = str(tmp_path)
    private, evidence = tmp_path / "private", tmp_path / "evidence"
    private.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    (private / "state.json").write_text("unadopted state with private credentials")
    if fault == "advisory":
        payload["pull_request"]["merge_commit_sha"] = {"invalid": True}
    raw = (
        "{"
        if fault == "malformed"
        else '{"repository":{},"repository":{}}'
        if fault == "duplicate"
        else json.dumps(payload)
    )
    Path(env["GITHUB_EVENT_PATH"]).write_text(raw)
    parents = (
        ["d" * 40, "c" * 40] if fault in {"parents", "primary-write"} else ["c" * 40, "d" * 40]
    )
    header = (
        "tree "
        + "e" * 40
        + "\n"
        + "".join("parent " + p + "\n" for p in parents)
        + "\nunit fixture"
    ).encode()
    original_write = lane.write_json

    def write(path, value):
        if path.name.startswith("event-admission-") and fault in {"write", "primary-write"}:
            raise OSError("unit diagnostic write failed")
        return original_write(path, value)

    with (
        patch.dict(os.environ, env, clear=True),
        patch.object(lane.sys, "argv", ["runner", mode]),
        patch.object(lane.signal, "signal"),
        patch.object(lane, "require_source", return_value=("e" * 40, [])),
        patch.object(
            lane,
            "git_bytes",
            side_effect=lambda root, *args: b"b" * 40 if args == ("rev-parse", "HEAD") else header,
        ),
        patch.object(lane, "write_json", side_effect=write),
        patch.object(lane, "cleanup") as cleanup,
        patch.object(lane, "load_lease") as lease,
        patch.object(lane, "verify_server") as server,
        patch.object(lane, "collect_owned_logs") as logs,
        patch.object(lane, "Commands") as commands,
    ):
        with pytest.raises(lane.Refusal) as caught:
            lane.main()
    reason = {
        "parents": "EVENT_PR_BASE_PARENT",
        "malformed": "EVENT_PAYLOAD_JSON",
        "duplicate": "EVENT_PAYLOAD_DUPLICATE_KEYS",
        "advisory": "EVENT_PR_ADVISORY_FORMAT",
        "write": "EVENT_DIAGNOSTIC_WRITE_FAILED",
        "primary-write": "EVENT_PR_BASE_PARENT",
    }[fault]
    assert caught.value.admission_diagnostic["failure_reason"] == reason
    assert caught.value.admission_diagnostic["entrypoint"] == mode
    if fault in {"write", "primary-write"}:
        assert not (evidence / ("event-admission-" + mode + ".json")).exists()
        if fault == "primary-write":
            assert caught.value.__notes__ == ["EVENT_DIAGNOSTIC_WRITE_FAILED"]
    else:
        diagnostic = json.loads((evidence / ("event-admission-" + mode + ".json")).read_text())
        assert diagnostic["result"] == "REFUSED" and diagnostic["failure_reason"] == reason
        assert diagnostic["event_payload_sha256"] == lane.sha256(raw.encode())
    for mock in (cleanup, lease, server, logs, commands):
        mock.assert_not_called()
    assert (private / "state.json").read_text() == "unadopted state with private credentials"


def test_ci_admission_reads_real_shallow_merge_headers_and_never_advisory_parents(tmp_path):
    source, checkout, evidence = tmp_path / "source", tmp_path / "shallow", tmp_path / "evidence"
    source.mkdir()
    evidence.mkdir()

    def git(root, *args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Unit",
                "-c",
                "user.email=unit@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=root,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

    git(source, "init", "-q")
    for relative in lane.CI_INPUT_SHA256:
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((lane.ROOT / relative).read_bytes())
    (source / "source.py").write_text("value = 1\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "unit base")
    base = git(source, "rev-parse", "HEAD")
    (source / "source.py").write_text("value = 2\n")
    git(source, "commit", "-qam", "unit head")
    head = git(source, "rev-parse", "HEAD")
    tree = git(source, "rev-parse", "HEAD^{tree}")
    merge = git(source, "commit-tree", tree, "-p", base, "-p", head, "-m", "constructed unit merge")
    git(source, "update-ref", "HEAD", merge)
    git(tmp_path, "clone", "-q", "--depth=1", "--no-tags", source.as_uri(), str(checkout))
    assert git(checkout, "rev-list", "--parents", "-1", "HEAD") == merge
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    env["GITHUB_SHA"] = merge
    pr = payload["pull_request"]
    pr["base"]["sha"], pr["head"]["sha"] = base, head
    pr["merge_commit_sha"] = "a" * 40
    Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload))
    with patch.dict(os.environ, env, clear=True), patch.object(lane, "ROOT", checkout):
        identity, manifest = lane.admit_event(evidence, entrypoint="run")
    assert identity["head"] == merge and identity["tree"] == tree
    assert identity["merge_parents"] == [base, head]
    assert identity["advisory_merge_commit_sha"] == "a" * 40
    assert len(manifest) == len(lane.CI_INPUT_SHA256) + 1
    diagnostic = json.loads((evidence / "event-admission-run.json").read_text())
    assert diagnostic["result"] == "PASS"
    assert diagnostic["operands"]["actual_parents"] == [base, head]


@pytest.mark.parametrize("route", ("stock-push", "main-push"))
@pytest.mark.parametrize(
    "fault,reason",
    (
        ("env-ref", "EVENT_PUSH_ENV_REF"),
        ("payload-ref", "EVENT_PUSH_PAYLOAD_REF"),
        ("deleted", "EVENT_PUSH_DELETED"),
        ("base-ref", "EVENT_PUSH_BASE_REF"),
        ("env-base", "EVENT_PUSH_ENV_BASE_REF"),
        ("env-head", "EVENT_PUSH_ENV_HEAD_REF"),
        ("after", "EVENT_PUSH_AFTER"),
        ("head", "EVENT_PUSH_HEAD"),
    ),
)
def test_ci_push_refusal_identifies_the_actual_source_predicate(tmp_path, route, fault, reason):
    env, payload = ci_event(tmp_path, route)
    if fault == "env-ref":
        env["GITHUB_REF"] = "refs/heads/other"
    elif fault == "payload-ref":
        payload["ref"] = "refs/heads/other"
    elif fault == "deleted":
        payload["deleted"] = True
    elif fault == "base-ref":
        payload["base_ref"] = "refs/heads/main"
    elif fault == "env-base":
        env["GITHUB_BASE_REF"] = "main"
    elif fault == "env-head":
        env["GITHUB_HEAD_REF"] = "candidate"
    elif fault == "after":
        payload["after"] = "a" * 40
    elif fault == "head":
        payload["head_commit"]["id"] = "a" * 40
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result != 0 and probe.receipt["admission_diagnostic"]["failure_reason"] == reason
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_ci_non_json_constants_refuse_with_digest_without_echo_or_commands(tmp_path, constant):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    raw = '{"untrusted":' + constant + "}"
    probe = exercise_ci_lane(tmp_path, env, payload, raw=raw)
    diagnostic = probe.receipt["admission_diagnostic"]
    assert diagnostic["failure_reason"] == "EVENT_PAYLOAD_JSON"
    assert diagnostic["event_payload_sha256"] == lane.sha256(raw.encode())
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("stage", ("head", "headers"))
def test_ci_source_read_failure_keeps_already_observed_safe_operands(tmp_path, stage):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload))

    def git(root, *args):
        if args == ("rev-parse", "HEAD") and stage != "head":
            return b"b" * 40
        raise OSError("https://private.invalid/DO_NOT_PUBLISH")

    with (
        patch.dict(os.environ, env, clear=True),
        patch.object(lane, "git_bytes", side_effect=git),
        patch.object(lane, "Commands") as commands,
        patch.object(lane, "load_lease") as lease,
    ):
        with pytest.raises(lane.Refusal) as caught:
            lane.admit_event(tmp_path, entrypoint="cleanup")
    diagnostic = json.loads((tmp_path / "event-admission-cleanup.json").read_text())
    assert diagnostic["failure_reason"] == (
        "EVENT_HEAD_READ" if stage == "head" else "EVENT_COMMIT_HEADERS"
    )
    assert diagnostic["operands"]["actual_head"] == ("INVALID" if stage == "head" else "b" * 40)
    assert diagnostic["operands"]["event_sha"] == env["GITHUB_SHA"]
    assert "DO_NOT_PUBLISH" not in json.dumps(diagnostic) + str(caught.value)
    commands.assert_not_called()
    lease.assert_not_called()


if __name__ == "__main__":
    unittest.main()
