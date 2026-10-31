"""Finite R2 admission and evidence checks; no PostgreSQL substitute."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_native_context_db_runner import ci_event

from scripts import m4_runtime_db as carrier
from scripts import native_context_db_catalog as catalog


@pytest.mark.parametrize("branch", [carrier.CAPTURE_BRANCH, carrier.TARGETED_BRANCH])
@pytest.mark.parametrize("attempt", ["1", "2"])
def test_two_exact_push_routes_refuse_reruns(tmp_path, branch, attempt):
    env, payload = ci_event(tmp_path, "stock-push")
    head, tree, parents = env["GITHUB_SHA"], "a" * 40, []
    env.update(GITHUB_REF="refs/heads/" + branch, GITHUB_RUN_ATTEMPT=attempt)
    payload["ref"] = env["GITHUB_REF"]
    if attempt == "1":
        assert catalog.event_identity(env, payload, head, tree, parents)["route"] == "m4-r2-push"
    else:
        with pytest.raises(catalog.Refusal, match="EVENT_M4_ATTEMPT"):
            catalog.event_identity(env, payload, head, tree, parents)


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
