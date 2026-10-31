"""Finite R3 admission and evidence checks; no PostgreSQL substitute."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_native_context_db_runner import ci_event
from test_native_context_db_runner import foundation_git as foundation_git

from scripts import m4_runtime_db as carrier
from scripts import native_context_db_catalog as catalog


@pytest.fixture
def r3_event(foundation_git, tmp_path, monkeypatch):
    """Constructed real Git history; actual admission code, no Docker/DB."""
    f = foundation_git
    base, base_tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    changed = f.root / "scripts/m4_runtime_db.py"
    changed.write_text("# constructed allowed source delta\n")
    f.git("add", str(changed))
    f.git("commit", "-qm", "constructed capture source")
    source, tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    monkeypatch.chdir(f.root)
    monkeypatch.setattr(carrier, "BASE", base)
    monkeypatch.setattr(carrier, "BASE_TREE", base_tree)
    monkeypatch.setattr(
        catalog, "M4_R3_TRANSITIONS", {"refs/heads/" + carrier.CAPTURE_BRANCH: base}
    )
    env, payload = ci_event(tmp_path, "stock-push")
    env.update(
        GITHUB_SHA=source, GITHUB_REF="refs/heads/" + carrier.CAPTURE_BRANCH, GITHUB_RUN_ATTEMPT="1"
    )
    payload.update(
        ref=env["GITHUB_REF"],
        before=base,
        after=source,
        head_commit={"id": source},
        created=False,
        deleted=False,
        forced=False,
    )
    boundary = []

    def admitted(root, event, manifest, mode):
        boundary.append({"root": root, "event": event, "manifest": manifest, "mode": mode})

    def forbidden(*args, **kwargs):
        pytest.fail("resource or credential boundary was entered")

    original_capture = carrier.capture

    def only_git(args):
        assert args[0] == "git", "Docker/credentials before source admission"
        return original_capture(args)

    monkeypatch.setattr(carrier, "capture", only_git)
    monkeypatch.setattr(carrier, "run_admitted", admitted)
    monkeypatch.setattr(carrier, "inventory", forbidden)
    monkeypatch.setattr(carrier.secrets, "token_hex", forbidden)
    monkeypatch.setattr(carrier, "compose", forbidden)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    root = tmp_path / "constructed-run"

    def run():
        Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload))
        carrier.run(root)

    return dict(
        f=f,
        env=env,
        payload=payload,
        source=source,
        tree=tree,
        base=base,
        root=root,
        run=run,
        boundary=boundary,
    )


@pytest.mark.parametrize(
    "metadata", [None, "refs/heads/main", "refs/heads/c3/task-name", "refs/tags/v1.2"]
)
def test_constructed_full_admission_reaches_capture_without_resources(r3_event, metadata):
    r = r3_event
    r["payload"]["base_ref"] = metadata
    r["run"]()
    assert len(r["boundary"]) == 1
    b = r["boundary"][0]
    assert b["mode"] == "catalog" and b["manifest"]
    assert (b["event"]["head"], b["event"]["tree"], b["event"]["before"]) == (
        r["source"],
        r["tree"],
        r["base"],
    )
    diag = json.loads((r["root"] / "evidence/event-admission-run.json").read_text())
    assert diag["result"] == "PASS"
    assert diag["operands"]["push_base_ref"]["value"] == metadata
    assert diag["operands"]["push_base_ref"]["valid"] is True
    assert diag["operands"]["actual_parents"] == [r["base"]]
    assert diag["operands"]["push_created"] is False
    assert diag["operands"]["push_forced"] is False


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("repo", "EVENT_ENV_REPOSITORY"),
        ("payload_repo", "EVENT_REPOSITORY_ID"),
        ("ref", "EVENT_PUSH_ENV_REF"),
        ("targeted_not_open", "EVENT_PUSH_ENV_REF"),
        ("before", "EVENT_M4_BEFORE"),
        ("missing_before", "EVENT_M4_BEFORE"),
        ("parent", "EVENT_M4_PARENT"),
        ("merge", "EVENT_M4_PARENT"),
        ("base_tree", "BASE_TREE"),
        ("dirty", "EVENT_SOURCE_VERIFY"),
        ("write_set", "R3_WRITE_SET"),
        ("head", "EVENT_SHA_HEAD_MISMATCH"),
        ("after", "EVENT_PUSH_AFTER"),
        ("head_commit", "EVENT_PUSH_HEAD"),
        ("created", "EVENT_M4_CREATED"),
        ("missing_created", "EVENT_M4_CREATED"),
        ("deleted", "EVENT_PUSH_DELETED"),
        ("missing_deleted", "EVENT_PUSH_DELETED"),
        ("forced", "EVENT_M4_FORCED"),
        ("missing_forced", "EVENT_M4_FORCED"),
        ("attempt", "EVENT_M4_ATTEMPT"),
        ("missing_base_ref", "EVENT_M4_BASE_REF_MISSING"),
    ],
)
def test_constructed_full_admission_refuses_before_resources(r3_event, monkeypatch, damage, reason):
    r = r3_event
    f, p = r["f"], r["payload"]
    p["base_ref"] = "refs/heads/main"
    if damage == "repo":
        monkeypatch.setenv("GITHUB_REPOSITORY", "other/repo")
    elif damage == "payload_repo":
        p["repository"]["id"] += 1
    elif damage in {"ref", "targeted_not_open"}:
        ref = "refs/heads/" + (
            carrier.TARGETED_BRANCH if damage == "targeted_not_open" else "other"
        )
        monkeypatch.setenv("GITHUB_REF", ref)
        p["ref"] = ref
    elif damage == "before":
        p["before"] = "f" * 40
    elif damage == "base_tree":
        monkeypatch.setattr(carrier, "BASE_TREE", "f" * 40)
    elif damage == "head":
        monkeypatch.setenv("GITHUB_SHA", "f" * 40)
    elif damage == "after":
        p["after"] = "f" * 40
    elif damage == "head_commit":
        p["head_commit"]["id"] = "f" * 40
    elif damage in {"created", "deleted", "forced"}:
        p[damage] = True
    elif damage == "attempt":
        monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    elif damage.startswith("missing_"):
        del p[damage.removeprefix("missing_")]
    elif damage == "dirty":
        (f.root / "scripts/m4_runtime_db.py").write_text("# uncommitted\n")
    elif damage == "write_set":
        (f.root / "foreign.py").write_text("# forbidden delta\n")
        f.git("add", "foreign.py")
        f.git("commit", "--amend", "--no-edit")
    elif damage == "parent":
        f.git("commit", "--allow-empty", "-qm", "wrong immediate parent")
    elif damage == "merge":
        new = f.git(
            "commit-tree", r["tree"], "-p", r["base"], "-p", r["source"], "-m", "constructed merge"
        )
        f.git("reset", "--soft", new)
    else:
        raise AssertionError(damage)
    if damage in {"write_set", "parent", "merge"}:
        source = f.git("rev-parse", "HEAD")
        p["after"] = p["head_commit"]["id"] = source
        monkeypatch.setenv("GITHUB_SHA", source)
    message = (
        "Tracked/untracked source is dirty; destructive operations refused"
        if damage == "dirty"
        else reason
    )
    with pytest.raises((catalog.Refusal, RuntimeError), match="^" + message + "$"):
        r["run"]()
    assert r["boundary"] == []
    assert list((r["root"] / "private").iterdir()) == []
    diag = json.loads((r["root"] / "evidence/event-admission-run.json").read_text())
    if reason not in {"BASE_TREE", "R3_WRITE_SET"}:
        assert diag["failure_reason"] == reason


@pytest.mark.parametrize(
    "metadata",
    [
        1,
        True,
        [],
        {},
        "",
        "refs/heads/" + "a" * 170,
        "refs/heads/../secret",
        "refs/heads/a.lock",
        "refs/heads/a//b",
        "refs/heads/.secret",
        "refs/heads/a@{b",
        "https://secret.invalid/password",
        "refs/heads/a\nPRIVATE_SENTINEL",
    ],
)
def test_constructed_full_admission_rejects_malformed_metadata_without_echo(r3_event, metadata):
    r = r3_event
    r["payload"]["base_ref"] = metadata
    with pytest.raises(catalog.Refusal, match="^EVENT_M4_BASE_REF_METADATA$"):
        r["run"]()
    assert not r["boundary"]
    text = (r["root"] / "evidence/event-admission-run.json").read_text()
    assert "PRIVATE_SENTINEL" not in text and "password" not in text
    diag = json.loads(text)
    assert diag["operands"]["push_base_ref"]["value"] is None
    assert diag["operands"]["push_base_ref"]["valid"] is False


@pytest.mark.parametrize("route", ["main-push", "stock-push"])
def test_legacy_push_base_ref_rule_is_unchanged(tmp_path, route):
    env, payload = ci_event(tmp_path, route)
    for metadata in (None, "refs/heads/main"):
        payload["base_ref"] = metadata
        if metadata is None:
            assert (
                catalog.event_identity(env, payload, env["GITHUB_SHA"], "a" * 40, ["c" * 40])[
                    "route"
                ]
                == route
            )
        else:
            with pytest.raises(catalog.Refusal, match="EVENT_PUSH_BASE_REF"):
                catalog.event_identity(env, payload, env["GITHUB_SHA"], "a" * 40, ["c" * 40])


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_interrupted_phase_is_saved_before_return_and_missing_is_not_complete(tmp_path, phase):
    root = Path.cwd()
    fixture = tmp_path / "test_fixture.py"
    fixture.write_text(
        "import pytest,time\n"
        "@pytest.fixture\ndef resource():\n"
        + ("    time.sleep(30)\n" if phase == "setup" else "")
        + "    yield\n"
        + ("    time.sleep(30)\n" if phase == "teardown" else "")
        + "def test_active(resource):\n"
        + ("    time.sleep(30)\n" if phase == "call" else "    pass\n")
        + "def test_not_reached():\n    pass\n"
    )
    expected = ["test_fixture.py::test_active", "test_fixture.py::test_not_reached"]
    (tmp_path / "inventory.json").write_text(json.dumps({"nodeids": expected}))
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(root), str(root / "backend/src")]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        ASM_M4_PG_PLUGIN="1",
        ASM_M4_EVIDENCE=str(tmp_path),
    )
    with (tmp_path / "process.log").open("wb") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "scripts.m4_runtime_db",
                "-p",
                "no:cacheprovider",
                "-q",
                str(fixture),
            ],
            cwd=tmp_path,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                path = tmp_path / "active-case.json"
                if path.exists() and json.loads(path.read_text())["phase"] == phase:
                    break
                assert process.poll() is None, (tmp_path / "process.log").read_text()
                time.sleep(0.02)
            else:
                pytest.fail("phase checkpoint missing")
            cases = json.loads((tmp_path / "cases.json").read_text())
            summary = carrier.summarize(cases, expected, None)
            assert summary["complete"] is False and summary["result"] == "FAIL"
            assert summary["active"] == expected[:1]
            assert summary["missing"] == expected
            assert summary["not_reached"] == expected[1:]
            assert summary["completed"] == []
        finally:
            process.terminate()
            process.wait(timeout=3)
