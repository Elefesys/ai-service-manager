"""Finite R6 admission and evidence checks; no PostgreSQL substitute."""

import itertools
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


@pytest.mark.parametrize(
    "label,key",
    [
        ("current-native-inventory", "collection_exit"),
        ("native-owner", "system_identifier"),
        ("readiness", "runtime_check"),
    ],
)
@pytest.mark.parametrize("outcome", ["success", "failure", "timeout"])
def test_real_phase_preserves_producer_payload_and_consumer(tmp_path, label, key, outcome):
    """The R4 wrapper overwrites these files and breaks the same consumer lookup."""
    (tmp_path / "private").mkdir()
    (tmp_path / "evidence").mkdir()
    child = tmp_path / "producer.py"
    child.write_text(
        "import json,sys,time\nfrom pathlib import Path\n"
        "p=Path(sys.argv[1]);p.write_text(json.dumps({sys.argv[2]: 'payload'}))\n"
        "print('producer completed',flush=True)\n"
        "if sys.argv[3]=='timeout': time.sleep(30)\n"
        "sys.exit(7 if sys.argv[3]=='failure' else 0)\n"
    )
    payload = tmp_path / "evidence" / (label + ".json")
    args = [sys.executable, str(child), str(payload), key, outcome]
    if outcome == "success":
        carrier.phase(tmp_path, label, args, 5)
    else:
        with pytest.raises(RuntimeError, match=label.upper().replace("-", "_") + "_FAILED"):
            carrier.phase(tmp_path, label, args, 1 if outcome == "timeout" else 5)
    # Actual filesystem roundtrip: the command report must not replace the payload.
    assert json.loads(payload.read_text())[key] == "payload"
    report = json.loads((tmp_path / "evidence/phases" / (label + ".json")).read_text())
    assert report["exit_code"] == {"success": 0, "failure": 7, "timeout": 124}[outcome]
    assert report["seconds"] < 10
    assert (tmp_path / "evidence/phases" / (label + ".log")).read_text() == "producer completed\n"
    assert json.loads((tmp_path / "evidence/phases/active.json").read_text())["phase"] == label


@pytest.mark.parametrize(
    "mode,fault",
    [
        ("targeted", "none"),
        ("runtime", "none"),
        ("targeted", "build"),
        ("runtime", "build"),
        ("targeted", "collection"),
        ("targeted", "m4-duplicate"),
        ("targeted", "native"),
        ("targeted", "native-malformed"),
        ("targeted", "native-cleanup"),
    ],
)
def test_real_wrapper_driver_smoke_inventory_cleanup_and_export(tmp_path, monkeypatch, mode, fault):
    """Synthetic Docker/PG child boundaries; real phase/write/cleanup/finalization."""
    root = tmp_path / "real-wrapper-run"
    (root / "evidence").mkdir(parents=True)
    (root / "private").mkdir()
    monkeypatch.chdir(catalog.ROOT)
    for key, value in {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "push",
        "PYTHONPATH": str(catalog.ROOT) + os.pathsep + str(catalog.ROOT / "backend/src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }.items():
        monkeypatch.setenv(key, value)
    nodes = [
        m + "::test_synthetic_" + str(i)
        for m, count in zip(carrier.MODULES, (35, 21, 8), strict=True)
        for i in range(count)
    ]
    configuration = tmp_path / "synthetic.json"
    configuration.write_text(
        json.dumps({"m4": nodes, "native": carrier.CURRENT_NATIVE_NODES, "fault": fault})
    )
    child = tmp_path / "synthetic_boundary.py"
    child.write_text("""import json,sys
from pathlib import Path
from scripts import m4_runtime_db as runner
config=json.loads(Path(sys.argv[1]).read_text())
root=Path(sys.argv[2]); args=sys.argv[3:]; evidence=root/'evidence'; fault=config['fault']
if args[0]=='compose':
    if 'build' in args and fault=='build': raise SystemExit(7)
    if 'down' in args and fault=='native-cleanup':
        marker=root/'cleanup-failed-once'
        if not marker.exists(): marker.touch(); raise SystemExit(9)
elif 'collect-m4' in args:
    if fault=='collection': raise SystemExit(7)
    if fault=='m4-duplicate': config['m4'][1]=config['m4'][0]
    runner.write(evidence/'all-m4.json',{'nodeids':config['m4'],'collection_exit':0,'deselected':[]})
elif 'collect-current-native' in args:
    if fault in {'native','native-cleanup'}: raise SystemExit(7)
    runner.write(evidence/'current-native-inventory.json', {'malformed':True} if fault=='native-malformed' else {'nodeids':config['native'],'collection_exit':0,'deselected':[]})
elif 'native-owner' in args:
    runner.write(evidence/'native-owner.json',{'system_identifier':'synthetic-owned-server'})
elif 'readiness' in args:
    runner.write(evidence/'readiness.json',{'runtime_check':'PASS','revision':'0015'})
elif 'pytest' in args:
    nodes=json.loads((evidence/'inventory.json').read_text())['nodeids']
    if nodes==config['native']:
        assert json.loads((evidence/'native-owner.json').read_text())['system_identifier']=='synthetic-owned-server'
        runner.write(evidence/'before-reset-proofs.json',[{'synthetic':True} for _ in nodes])
        runner.write(evidence/'native-identity-proofs.json',[{'synthetic':True} for _ in nodes])
    cases=[{'nodeid':n,'overflow':0,'invalid_fields':0,'phases':[{'phase':p,'outcome':'passed','xfail':False} for p in ('setup','call','teardown')]} for n in nodes]
    runner.write(evidence/'cases.json',cases)
    runner.write(evidence/runner.SUMMARY_REPORT,runner.summarize(cases,nodes,0))
""")

    def command(group, *args, **kwargs):
        return [sys.executable, str(child), str(configuration), str(group), *args]

    def capture(args):
        if args[:2] == ["git", "rev-parse"]:
            return carrier.BASE_TREE if args[-1].startswith(carrier.BASE) else "b" * 40
        if args[:2] == ["git", "diff"]:
            return "scripts/m4_runtime_db.py"
        if args[:2] == ["git", "status"]:
            return ""
        if "ps" in args:
            return "synthetic-owned-container"
        if "exec" in args:
            return "Uid:\t999\t999\t999\t999"
        if "inspect" in args:
            return "sha256:" + "c" * 64
        raise AssertionError(args)

    monkeypatch.setattr(carrier, "compose", lambda group: command(group, "compose"))
    monkeypatch.setattr(carrier, "checks", command)
    monkeypatch.setattr(
        carrier, "current_native_checks", lambda group, label, *args: command(group, *args)
    )
    monkeypatch.setattr(carrier, "capture", capture)
    monkeypatch.setattr(
        carrier, "inventory", lambda group: {"containers": [], "networks": [], "volumes": []}
    )
    # No phase/write/Popen/run/cleanup/finalization replacement.
    event = {"ref": "refs/heads/" + carrier.TARGETED_BRANCH}
    if fault == "none":
        carrier.run_admitted(root, event, [], mode)
    else:
        with pytest.raises(RuntimeError, match="PRIMARY_FAILED"):
            carrier.run_admitted(root, event, [], mode)
    summary = json.loads((root / "evidence/summary.json").read_text())
    inventory = json.loads((root / "evidence/inventory.json").read_text())
    count = 70 if mode == "targeted" else 64
    assert summary["expected_cases"] == count == sum(summary["planned_cases_by_module"].values())
    assert (
        summary["missing_count"]
        == summary["not_reached_count"]
        == (0 if fault == "none" else count)
    )
    assert summary["inventory_complete"] is (fault not in {"build", "collection", "m4-duplicate"})
    assert summary["unknown_inventory_cases"] == (
        64 if fault in {"build", "collection", "m4-duplicate"} else 0
    )
    assert summary["collected_cases"] == (
        count if fault == "none" else 0 if fault in {"build", "collection", "m4-duplicate"} else 64
    )
    assert summary["collection_complete"] is (fault == "none")
    group = root / (root.name + "-group-0")
    primary = json.loads((group / "evidence/primary.json").read_text())
    if fault == "none":
        assert summary["complete"] and not summary["missing"]
        assert len(summary["groups"]) == (5 if mode == "targeted" else 4)
        assert (
            json.loads((group / "evidence/readiness.json").read_text())["runtime_check"] == "PASS"
        )
    else:
        assert not summary["complete"]
        assert summary["missing"] == summary["not_reached"] == inventory["nodeids"]
        if fault.startswith("native"):
            assert summary["missing"] == nodes + carrier.CURRENT_NATIVE_NODES
        assert 0 < len(primary["frames"]) <= 8
        assert set(primary["frames"][-1]) == {"file", "function", "line"}
        if fault == "native-malformed":
            assert primary["error_type"] == "KeyError" and primary["code"] == "OPERATION_FAILED"
            assert primary["frames"][-1]["function"] == "run_admitted"
        if fault == "native-cleanup":
            assert primary["code"] == "CURRENT_NATIVE_INVENTORY_FAILED"
            assert summary["groups"][0]["cleanup"]["code"] == "CLEANUP_COMMAND_1_FAILED"
    # Actual always-finalization copies the nested reports and creates its manifest.
    primary_bytes = (group / "evidence/primary.json").read_bytes()
    monkeypatch.setattr(carrier, "root_path", lambda: root)
    monkeypatch.setattr(sys, "argv", ["m4_runtime_db.py", "cleanup"])
    carrier.main()
    saved = root / "evidence" / group.name
    assert (saved / "primary.json").read_bytes() == primary_bytes
    assert json.loads((saved / "cleanup.json").read_text())["outcome"] == "PASS"
    manifest = json.loads((root / "evidence/manifest.json").read_text())
    assert group.name + "/phases/build.json" in manifest
    assert group.name + "/inventory.json" in manifest
    for name, proof in manifest.items():
        data = (root / "evidence" / name).read_bytes()
        assert (
            len(data) == proof["bytes"]
            and carrier.hashlib.sha256(data).hexdigest() == proof["sha256"]
        )
    if destination := os.environ.get("ASM_R6_OFFLINE_EVIDENCE"):
        carrier.shutil.copytree(root / "evidence", Path(destination) / (mode + "-" + fault))


def test_failure_location_excludes_exception_values_locals_and_absolute_paths():
    private = "PRIVATE_SENTINEL_POSTGRES_DSN"
    try:
        raise ValueError(private)
    except ValueError as error:
        result = carrier.failure_details(error)
    assert result["code"] == "OPERATION_FAILED"
    assert private not in json.dumps(result)
    assert all("/" not in row["file"] for row in result["frames"])
    assert (
        result["frames"][-1]["function"]
        == "test_failure_location_excludes_exception_values_locals_and_absolute_paths"
    )


@pytest.mark.parametrize(
    "damage",
    ["none", "tracked", "untracked", "mode", "head", "env", "evidence", "fixture", "identity"],
)
async def test_native_fixture_identity_uses_real_git_and_rechecks_drift_at_use(
    foundation_git, tmp_path, monkeypatch, damage
):
    """Actual fixture/function and real Git/file checks; only DB/engine boundaries mocked."""
    import importlib.util
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    f = foundation_git
    source_file = f.root / catalog.MODULES[1]
    source_file.write_bytes((f.actual / catalog.MODULES[1]).read_bytes())
    f.git("add", ".")
    f.git("commit", "-qm", "real immutable native fixture")
    source, tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for key, value in {
        "SOURCE_SHA": source,
        "SOURCE_TREE": tree,
        "RUN_ID": "123",
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, value)
    monkeypatch.setenv("ASM_M4_EVIDENCE", str(evidence))
    proof = {
        "base": carrier.BASE,
        "base_tree": carrier.BASE_TREE,
        "source": source,
        "tree": tree,
        "paths": [catalog.MODULES[1]],
        "run_id": "123",
        "attempt": 1,
        "event": "push",
        "branch": carrier.TARGETED_BRANCH,
        "pins": {"DB_IMAGE": carrier.DB_IMAGE},
        "uv_lock_sha256": "a" * 64,
    }
    carrier.write(evidence / "source.json", proof)
    carrier.write(evidence / "native-owner.json", {"constructed": "owned SQL boundary"})
    spec = importlib.util.spec_from_file_location("test_m3_1_native_context_postgres", source_file)
    fixture = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, fixture)
    spec.loader.exec_module(fixture)
    items = [
        SimpleNamespace(
            nodeid=n,
            _fixtureinfo=SimpleNamespace(
                name2fixturedefs={"native": [SimpleNamespace(func=fixture.native)]}
            ),
        )
        for n in carrier.CURRENT_NATIVE_NODES
    ]
    if damage == "fixture":
        items[0]._fixtureinfo.name2fixturedefs["native"][0].func = lambda: None
    elif damage == "identity":
        fixture.source_tree_identity = lambda: tree
    if damage in {"fixture", "identity"}:
        with pytest.raises(RuntimeError, match="CURRENT_NATIVE_RESET_IMPLEMENTATION"):
            carrier.guard_current_native(items)
        return
    index = (f.root / ".git/index").read_bytes()
    git_commands = []
    actual_git = catalog.git_bytes

    def read_only_git(root, *args):
        assert args[0] in {"rev-parse", "status", "ls-tree"}
        git_commands.append(args[0])
        return actual_git(root, *args)

    monkeypatch.setattr(catalog, "git_bytes", read_only_git)
    carrier.guard_current_native(items)
    assert fixture.source_tree_identity() == tree
    assert git_commands.count("ls-tree") == 1
    if damage == "tracked":
        source_file.write_text(source_file.read_text() + "\n# dirty\n")
    elif damage == "untracked":
        (f.root / "untracked.txt").write_text("dirty")
    elif damage == "mode":
        source_file.chmod(0o755)
    elif damage == "head":
        f.git("commit", "--allow-empty", "-qm", "different head")
    elif damage == "env":
        monkeypatch.setenv("ASM_M4_SOURCE_SHA", "a" * 40)
    elif damage == "evidence":
        carrier.write(evidence / "source.json", proof | {"tree": "c" * 40})

    # Drive the real fixture until its h construction consumes identity. The SQL
    # reset/migration/engine are deliberately offline boundaries, not PG evidence.
    class IdentityConsumed(Exception):
        pass

    consumed = []

    def namespace(**fields):
        if "source_tree" in fields:
            consumed.append(fields["source_tree"])
            raise IdentityConsumed
        return SimpleNamespace(**fields)

    monkeypatch.setattr(fixture.asyncio, "to_thread", AsyncMock())
    monkeypatch.setattr(fixture, "migrate", AsyncMock())
    monkeypatch.setattr(fixture, "create_async_engine", lambda *a, **kw: None)
    monkeypatch.setattr(fixture, "TenantDatabase", lambda *a: None)
    monkeypatch.setattr(fixture, "MessagingDatabase", lambda *a: None)
    monkeypatch.setattr(fixture, "SimpleNamespace", namespace)
    monkeypatch.setenv("ASM_DATABASE_URL", "unused-offline-boundary")
    monkeypatch.setenv("ASM_MIGRATION_DATABASE_URL", "unused-offline-boundary")
    generator = carrier.inspect.unwrap(fixture.native)(SimpleNamespace(), tmp_path)
    with pytest.raises(IdentityConsumed if damage == "none" else (RuntimeError, catalog.Refusal)):
        await anext(generator)
    identities = json.loads((evidence / "native-identity-proofs.json").read_text())
    assert len(identities) == (2 if damage == "none" else 1)
    assert consumed == ([tree] if damage == "none" else [])
    if damage == "none":
        assert (f.root / ".git/index").read_bytes() == index
        assert not list((f.root / ".git").rglob("*.lock"))
        assert git_commands.count("ls-tree") == 2


def test_bounded_delivery_operands_and_missing_call_phases(tmp_path, monkeypatch):
    case = {
        "nodeid": "synthetic",
        "events": [],
        "overflow": 0,
        "invalid_fields": 0,
        "phases": [
            {"phase": "setup", "outcome": "failed", "xfail": False},
            {"phase": "teardown", "outcome": "passed", "xfail": False},
        ],
    }
    monkeypatch.setenv("ASM_M4_EVIDENCE", str(tmp_path))
    monkeypatch.setattr(carrier, "CASE", case)
    monkeypatch.setattr(carrier, "CASES", [case])
    carrier.preparation(
        "SELECTION",
        selected_kind=None,
        call_count=1,
        job_state="DEAD",
        adapter_entered=True,
        error_code="DEPENDENCY_UNAVAILABLE",
    )
    assert case["events"] == [
        {
            "stage": "SELECTION",
            "selected_kind": None,
            "call_count": 1,
            "job_state": "DEAD",
            "adapter_entered": True,
            "error_code": "DEPENDENCY_UNAVAILABLE",
        }
    ]
    for fields in (
        {"selected_kind": "PRIVATE_SENTINEL"},
        {"call_count": True},
        {"call_count": 3},
        {"adapter_entered": 1},
        {"job_state": "PRIVATE_SENTINEL"},
        {"error_code": "PRIVATE_SENTINEL"},
        {"claim": "PRIVATE_SENTINEL"},
        {"selected_kind": []},
    ):
        carrier.preparation("SELECTION", **fields)
    assert case["invalid_fields"] == 8 and len(case["events"]) == 1
    assert "PRIVATE_SENTINEL" not in (tmp_path / "cases.json").read_text()
    summary = carrier.summarize([case], ["synthetic"], 1)
    assert summary["completed"] == ["synthetic"] and summary["missing"] == []
    assert summary["call_reached"] == [] and summary["missing_call_phases"] == ["synthetic"]
    assert summary["result"] == "FAIL" and not summary["complete"]


@pytest.mark.parametrize(
    "mode,fault",
    [
        ("targeted", "none"),
        ("runtime", "none"),
        ("targeted", "catalog"),
        ("targeted", "retained"),
        ("targeted", "budget"),
    ],
)
def test_constructed_driver_preflight_isolation_budget_and_missing_evidence(
    tmp_path, monkeypatch, mode, fault
):
    """Exercise orchestration with explicit fake boundaries; no PG/Docker claim."""
    root = tmp_path / "constructed-run"
    (root / "evidence").mkdir(parents=True)
    (root / "private").mkdir()
    monkeypatch.chdir(catalog.ROOT)
    for key, value in {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "push",
    }.items():
        monkeypatch.setenv(key, value)
    nodes = [
        module + "::test_constructed_" + str(i)
        for module, count in zip(carrier.MODULES, (35, 21, 8), strict=True)
        for i in range(count)
    ]
    calls, cleaned = [], []

    def capture(args):
        if args[:2] == ["git", "rev-parse"]:
            return carrier.BASE_TREE if args[-1].startswith(carrier.BASE) else "b" * 40
        if args[:2] == ["git", "diff"]:
            return "scripts/m4_runtime_db.py"
        if args[:2] == ["git", "status"]:
            return ""
        if "ps" in args:
            return "constructed-container"
        if "exec" in args:
            return "Uid:\t999\t999\t999\t999"
        if "inspect" in args:
            return "sha256:" + "c" * 64
        raise AssertionError(args)

    def phase(group, label, args, budget):
        calls.append((group.name, label, budget))
        assert 0 < budget <= 600
        if label == "inventory":
            carrier.write(
                group / "evidence/all-m4.json",
                {"nodeids": nodes, "collection_exit": 0, "deselected": []},
            )
        if label == "current-native-inventory":
            carrier.write(
                group / "evidence/current-native-inventory.json",
                {"nodeids": carrier.CURRENT_NATIVE_NODES, "collection_exit": 0, "deselected": []},
            )
        if label == "catalog-0015" and fault == "catalog":
            raise RuntimeError("CATALOG_DECLARED_PROFILE")
        if label == carrier.COMMAND_REPORT:
            expected = json.loads((group / "evidence/inventory.json").read_text())["nodeids"]
            cases = [
                {
                    "nodeid": n,
                    "overflow": 0,
                    "invalid_fields": 0,
                    "phases": [
                        {"phase": p, "outcome": "passed", "xfail": False}
                        for p in ("setup", "call", "teardown")
                    ],
                }
                for n in expected
            ]
            if fault == "retained" and group.name.endswith("-group-1"):
                cases = cases[:1]
                cases[0]["phases"][1]["outcome"] = "failed"
            carrier.write(group / "evidence/cases.json", cases)
            summary = carrier.summarize(cases, expected, 0 if len(cases) == len(expected) else 1)
            carrier.write(group / "evidence" / carrier.SUMMARY_REPORT, summary)
            if expected == carrier.CURRENT_NATIVE_NODES:
                carrier.write(group / "evidence/before-reset-proofs.json", [{}] * 6)
                carrier.write(group / "evidence/native-identity-proofs.json", [{}] * 6)
            if summary["result"] == "FAIL":
                raise RuntimeError("RUNTIME_COMMAND_FAILED")

    def cleanup(group):
        cleaned.append(group.name)
        carrier.write(group / "evidence/cleanup.json", {"outcome": "PASS"})

    def archive(args, **kwargs):
        assert args[:3] == ["git", "archive", "--format=tar.gz"]
        Path(args[4]).write_bytes(b"constructed unit-test archive boundary")

    monkeypatch.setattr(carrier, "capture", capture)
    monkeypatch.setattr(carrier, "phase", phase)
    monkeypatch.setattr(carrier, "cleanup", cleanup)
    monkeypatch.setattr(
        carrier, "inventory", lambda group: {"containers": [], "networks": [], "volumes": []}
    )
    monkeypatch.setattr(carrier, "checks", lambda group, *args, **kwargs: ["checks", *args])
    monkeypatch.setattr(
        carrier, "current_native_checks", lambda group, label, *args: ["native", *args]
    )
    monkeypatch.setattr(carrier.subprocess, "run", archive)
    clock = itertools.count(step=200 if fault == "budget" else 0.01)
    monkeypatch.setattr(carrier.time, "monotonic", lambda: next(clock))
    event = {"ref": "refs/heads/" + carrier.TARGETED_BRANCH}
    if fault == "none":
        carrier.run_admitted(root, event, [], mode)
    else:
        with pytest.raises(RuntimeError, match="PRIMARY_FAILED"):
            carrier.run_admitted(root, event, [], mode)
    summary = json.loads((root / "evidence/summary.json").read_text())
    expected_count = 70 if mode == "targeted" else 64
    assert summary["expected_cases"] == expected_count
    assert summary["sql_test_seconds"] <= 600
    assert summary["result"] == ("PASS" if fault == "none" else "FAIL")
    assert len(cleaned) == summary["groups_visited"]
    assert len(set(cleaned)) == len(cleaned)
    if fault in {"catalog", "budget"}:
        assert summary["groups_visited"] == 1 and len(summary["not_reached"]) == expected_count
        assert not any(label == carrier.COMMAND_REPORT for _, label, _ in calls)
    elif fault == "retained":
        assert summary["groups_visited"] == 5 and len(summary["missing"]) == 34
        assert summary["groups"][-1]["outcome"] == "PASS"
    else:
        assert summary["complete"] and not summary["missing"]
        assert summary["groups_visited"] == (5 if mode == "targeted" else 4)


def test_phase_keeps_private_json_stdout_separate_and_redacts_stderr(tmp_path):
    (tmp_path / "private").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "private/test.env").write_text("ASM_TEST_PASSWORD=PRIVATE_SENTINEL\n")
    carrier.phase(
        tmp_path,
        "provision",
        [
            sys.executable,
            "-c",
            "import sys;print('{\"ok\": true}');print('Creating container PRIVATE_SENTINEL',file=sys.stderr)",
        ],
        5,
        separate_stdout=True,
    )
    assert json.loads((tmp_path / "private/provision.stdout").read_text()) == {"ok": True}
    assert "PRIVATE_SENTINEL" not in (tmp_path / "evidence/phases/provision.log").read_text()
    assert (
        "Creating container [REDACTED]" in (tmp_path / "evidence/phases/provision.log").read_text()
    )


def test_stack_diagnostics_keeps_states_and_schema_stage_without_raw_values(tmp_path, monkeypatch):
    from types import SimpleNamespace

    outputs = [
        json.dumps(
            [
                {
                    "Service": "api",
                    "State": "exited",
                    "Health": "unhealthy",
                    "ExitCode": 1,
                    "Command": "PRIVATE_SENTINEL",
                }
            ]
        ),
        'api | {"component":"schema-admission","event":"refused","stage":"DECLARED_PROFILE_OR_FULL_PIN","error_type":"RuntimeError","dsn":"PRIVATE_SENTINEL"}\nPRIVATE_SENTINEL raw log',
    ]
    monkeypatch.setattr(
        carrier.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=outputs.pop(0).encode()),
    )
    carrier.stack_diagnostics(tmp_path, ["constructed-compose"])
    raw = (tmp_path / "evidence/stack-diagnostics.json").read_text()
    assert "PRIVATE_SENTINEL" not in raw
    data = json.loads(raw)
    assert data["services"] == [
        {"service": "api", "state": "exited", "health": "unhealthy", "exit_code": 1}
    ]
    assert data["schema_refusals"] == [
        {"stage": "DECLARED_PROFILE_OR_FULL_PIN", "error_type": "RuntimeError"}
    ]


@pytest.mark.parametrize("damage", ["source", "tree", "server"])
def test_current_native_reset_refuses_changed_source_or_server_before_destructive_sql(
    tmp_path, monkeypatch, damage
):
    from types import SimpleNamespace

    import test_m3_1_native_context_postgres as fixture

    original = fixture.reset_disposable
    original_identity = fixture.source_tree_identity
    monkeypatch.setenv("ASM_M4_SOURCE_SHA", "a" * 40)
    monkeypatch.setenv("ASM_M4_EVIDENCE", str(tmp_path))
    baseline = {
        "system_identifier": "123",
        "postmaster_start": "constructed",
        "server_version_num": "180006",
    }
    carrier.write(tmp_path / "native-owner.json", baseline)
    calls = []

    def source(*args):
        calls.append("source")
        if damage == "source":
            raise catalog.Refusal("CONSTRUCTED_DIRTY_SOURCE")
        return ("b" * 40 if damage != "tree" else "c" * 40), []

    def identity():
        calls.append("identity")
        return dict(baseline, system_identifier="different-server")

    monkeypatch.setattr(catalog, "require_source", source)
    monkeypatch.setattr(carrier, "source_tree_from_evidence", lambda: "b" * 40)
    monkeypatch.setattr(carrier, "native_identity", identity)
    items = [
        SimpleNamespace(
            nodeid=node,
            _fixtureinfo=SimpleNamespace(
                name2fixturedefs={"native": [SimpleNamespace(func=fixture.native)]}
            ),
        )
        for node in carrier.CURRENT_NATIVE_NODES
    ]
    try:
        carrier.guard_current_native(items)
        with pytest.raises(
            (RuntimeError, catalog.Refusal),
            match={
                "source": "CONSTRUCTED_DIRTY_SOURCE",
                "tree": "CURRENT_NATIVE_SOURCE",
                "server": "CURRENT_NATIVE_SERVER_CHANGED",
            }[damage],
        ):
            fixture.reset_disposable()
        assert calls == (["source", "identity"] if damage == "server" else ["source"])
        assert not (tmp_path / "before-reset-proofs.json").exists()
    finally:
        fixture.reset_disposable = original
        fixture.source_tree_identity = original_identity


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("self", "EMBEDDED_SELF_ROW"),
        ("missing", "EMBEDDED_FUNCTION_SET"),
        ("duplicate", "EMBEDDED_DUPLICATE_FUNCTION"),
        *[
            (name, "EMBEDDED_FUNCTION_MISMATCH")
            for name in ("hash", "language", "security", "volatility", "runtime")
        ],
        ("columns", "EMBEDDED_COLUMN_SET"),
    ],
)
def test_current_verifier_embedded_table_is_independent_and_closed(damage, reason):
    expected = catalog.source_catalog(catalog.ROOT, "0015")
    profile = expected["functions"]["platform.ai_delivery_schema_profile()"]
    row = "('platform.human_context_schema_profile()','527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac','sql',true,'s',false)"
    assert profile["body"].count(row) == 1
    replacement = {
        "self": row.replace("human_context_schema_profile", "ai_delivery_schema_profile"),
        "missing": "",
        "duplicate": row + "," + row,
        "hash": row.replace(
            "527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac", "0" * 64
        ),
        "language": row.replace("'sql'", "'plpgsql'"),
        "security": row.replace(",true,", ",false,"),
        "volatility": row.replace("'s'", "'v'"),
        "runtime": row.replace(",false)", ",true)"),
    }
    if damage == "columns":
        profile["body"] = profile["body"].replace(
            "'app.audit_events',ARRAY['workspace_id',", "'app.audit_events',ARRAY[", 1
        )
    elif damage == "missing":
        profile["body"] = profile["body"].replace(row + ",", "", 1)
    else:
        profile["body"] = profile["body"].replace(row, replacement[damage])
    with pytest.raises(catalog.Refusal, match="^" + reason + "$"):
        catalog.compare_embedded_profile(expected)


@pytest.mark.parametrize(
    "valid,hash_matches,body_matches,reason",
    [
        (False, False, False, "CATALOG_DECLARED_PROFILE"),
        (False, True, True, "CATALOG_DECLARED_PROFILE"),
        (1, True, True, "CATALOG_DECLARED_PROFILE"),
        (True, False, False, "APPLICATION_VERIFIER_BODY_PIN"),
        (True, False, True, "APPLICATION_FULL_CATALOG_PIN"),
        (True, True, True, None),
    ],
)
def test_catalog_primary_refusal_preserves_both_pin_facts(
    valid, hash_matches, body_matches, reason
):
    from asm.foundation import NATIVE_CONTEXT_PROFILE_SHA256

    expected = catalog.source_catalog(catalog.ROOT, "0015")
    if not body_matches:
        expected["functions"]["platform.ai_delivery_schema_profile()"]["body_sha256"] = "0" * 64
    digest = NATIVE_CONTEXT_PROFILE_SHA256 if hash_matches else "f" * 64
    declared = {"schema_revision": "0015", "valid": valid, "profile_sha256": digest}
    result = carrier.catalog_comparison(expected, digest, "{}", declared)
    assert result["failed_predicate"] == reason
    assert result["application_pin_matches"] is hash_matches
    assert result["application_body_pin_matches"] is body_matches


@pytest.fixture
def r6_event(foundation_git, tmp_path, monkeypatch):
    """Constructed real Git history; actual admission code, no Docker/DB."""
    f = foundation_git
    base, base_tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    changed = f.root / "scripts/m4_runtime_db.py"
    changed.write_text("# constructed allowed source delta\n")
    f.git("add", str(changed))
    f.git("commit", "-qm", "constructed targeted source")
    source, tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    monkeypatch.chdir(f.root)
    monkeypatch.setattr(carrier, "BASE", base)
    monkeypatch.setattr(carrier, "BASE_TREE", base_tree)
    monkeypatch.setattr(
        catalog, "M4_R3_TRANSITIONS", {"refs/heads/" + carrier.TARGETED_BRANCH: base}
    )
    env, payload = ci_event(tmp_path, "stock-push")
    env.update(
        GITHUB_SHA=source,
        GITHUB_REF="refs/heads/" + carrier.TARGETED_BRANCH,
        GITHUB_RUN_ATTEMPT="1",
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
def test_constructed_full_admission_reaches_targeted_without_resources(r6_event, metadata):
    r = r6_event
    r["payload"]["base_ref"] = metadata
    r["run"]()
    assert len(r["boundary"]) == 1
    b = r["boundary"][0]
    assert b["mode"] == "targeted" and b["manifest"]
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
    "path",
    [
        "migrations/versions/0015_ai_delivery.py",
        "backend/src/asm/foundation.py",
        ".github/workflows/ci.yml",
        "scripts/test_telegram_egress.sh",
    ],
)
def test_r6_admission_rejects_r4_product_and_ci_write_paths(r6_event, monkeypatch, path):
    r = r6_event
    f = r["f"]
    target = f.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        target.read_text() + "\n# forbidden R6 change\n"
        if target.exists()
        else "# forbidden R6 file\n"
    )
    f.git("add", path)
    f.git("commit", "--amend", "--no-edit")
    source = f.git("rev-parse", "HEAD")
    r["payload"]["after"] = r["payload"]["head_commit"]["id"] = source
    monkeypatch.setenv("GITHUB_SHA", source)
    with pytest.raises((catalog.Refusal, RuntimeError)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "damage,reason",
    [
        ("repo", "EVENT_ENV_REPOSITORY"),
        ("payload_repo", "EVENT_REPOSITORY_ID"),
        ("ref", "EVENT_PUSH_ENV_REF"),
        ("capture_not_open", "EVENT_PUSH_ENV_REF"),
        ("before", "EVENT_M4_BEFORE"),
        ("missing_before", "EVENT_M4_BEFORE"),
        ("parent", "EVENT_M4_PARENT"),
        ("merge", "EVENT_M4_PARENT"),
        ("base_tree", "BASE_TREE"),
        ("dirty", "EVENT_SOURCE_VERIFY"),
        ("write_set", "R6_WRITE_SET"),
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
def test_constructed_full_admission_refuses_before_resources(r6_event, monkeypatch, damage, reason):
    r = r6_event
    f, p = r["f"], r["payload"]
    p["base_ref"] = "refs/heads/main"
    if damage == "repo":
        monkeypatch.setenv("GITHUB_REPOSITORY", "other/repo")
    elif damage == "payload_repo":
        p["repository"]["id"] += 1
    elif damage in {"ref", "capture_not_open"}:
        ref = "refs/heads/" + (
            "c3/m4-3-runtime-catalog-run-r6" if damage == "capture_not_open" else "other"
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
    if reason not in {"BASE_TREE", "R6_WRITE_SET"}:
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
def test_constructed_full_admission_rejects_malformed_metadata_without_echo(r6_event, metadata):
    r = r6_event
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
