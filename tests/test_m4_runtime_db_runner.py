"""Finite R11 admission and evidence checks; no PostgreSQL substitute."""

import itertools
import json
import os
import re
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
def driver_inputs(tmp_path, monkeypatch):
    """Private synthetic inputs, also when /app has neither image pins nor .git."""
    root = tmp_path / "driver-inputs"
    (root / "infra").mkdir(parents=True)
    inputs = {
        "infra/images.lock.env": f"DB_IMAGE={carrier.DB_IMAGE}\n",
        "uv.lock": "# Synthetic unit input; never resolved.\nversion = 1\n",
    }
    for name, value in inputs.items():
        path = root / name
        path.write_text(value)
        path.chmod(0o444)
    # The real wrapper exports an archive; its synthetic Git source is private too.
    for args in (("init", "-q"), ("add", "."), ("commit", "-qm", "synthetic driver inputs")):
        subprocess.run(
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
            check=True,
            capture_output=True,
        )
    monkeypatch.chdir(root)
    yield root
    assert {name: (root / name).read_text() for name in inputs} == inputs


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
def test_real_wrapper_driver_smoke_inventory_cleanup_and_export(
    tmp_path, monkeypatch, driver_inputs, mode, fault
):
    """Synthetic Docker/PG child boundaries; real phase/write/cleanup/finalization."""
    root = tmp_path / "real-wrapper-run"
    (root / "evidence").mkdir(parents=True)
    (root / "private").mkdir()
    assert Path.cwd() == driver_inputs
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
        for m, count in zip(carrier.MODULES, (35, 22, 9, 1, 1, 1, 1), strict=True)
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
    runner.write(evidence/'readiness.json',{'runtime_check':'PASS','revision':'0021'})
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
    count = (72 if mode == "targeted" else 66) + (0 if fault in {"build", "collection"} else 4)
    assert summary["expected_cases"] == count == sum(summary["planned_cases_by_module"].values())
    assert (
        summary["missing_count"]
        == summary["not_reached_count"]
        == (0 if fault == "none" else count)
    )
    assert summary["inventory_complete"] is (fault not in {"build", "collection", "m4-duplicate"})
    assert summary["unknown_inventory_cases"] == (
        66 if fault in {"build", "collection"} else 70 if fault == "m4-duplicate" else 0
    )
    assert summary["collected_cases"] == (
        count if fault == "none" else 0 if fault in {"build", "collection", "m4-duplicate"} else 70
    )
    assert summary["collection_complete"] is (fault == "none")
    group = root / (root.name + "-group-0")
    primary = json.loads((group / "evidence/primary.json").read_text())
    if fault == "none":
        assert summary["complete"] and not summary["missing"]
        assert len(summary["groups"]) == (9 if mode == "targeted" else 8)
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
    if destination := os.environ.get("ASM_R9_OFFLINE_EVIDENCE"):
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
    "constraint", ["messaging_jobs_telegram_probe_check", "PRIVATE_SENTINEL", None]
)
async def test_sql_failure_keeps_known_constraint_and_real_application_frame(constraint):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    from asm.messaging.database import MessagingDatabase
    from sqlalchemy.exc import IntegrityError

    class DriverError(Exception):
        sqlstate = "23514"
        diag = SimpleNamespace(constraint_name=constraint)

    def driver_depth(n):
        if n:
            return driver_depth(n - 1)
        raise IntegrityError(
            "PRIVATE_SENTINEL", {"PRIVATE_SENTINEL": "claim"}, DriverError("PRIVATE_SENTINEL")
        )

    async def execute(statement):
        driver_depth(20)

    @asynccontextmanager
    async def admit(*args):
        yield SimpleNamespace(_execute=execute)

    with pytest.raises(IntegrityError) as caught:
        await MessagingDatabase.telegram_probe(
            SimpleNamespace(admit_job=admit),
            SimpleNamespace(job_id=uuid4(), claim_token=uuid4()),
        )
    details = carrier.case_failure_details(caught)
    assert details["exception_type"] == "IntegrityError" and details["sqlstate"] == "23514"
    assert details.get("constraint_name") == (
        constraint if constraint != "PRIVATE_SENTINEL" else None
    )
    assert len(details["frames"]) == 12
    assert all(f["function"] == "driver_depth" for f in details["frames"])
    assert any(
        f["file"] == "backend/src/asm/messaging/database.py" and f["function"] == "telegram_probe"
        for f in details["application_frames"]
    )
    assert 0 < len(details["application_frames"]) <= 8
    assert "PRIVATE_SENTINEL" not in json.dumps(details)
    assert all(not f["file"].startswith("/") for f in details["application_frames"])


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
    carrier.preparation("SEND_ATTEMPT", observe_count=1, send_count=0, send_completed=False)
    assert case["events"][-1] == {
        "stage": "SEND_ATTEMPT",
        "observe_count": 1,
        "send_count": 0,
        "send_completed": False,
    }
    for fields in (
        {"observe_count": True},
        {"send_count": 3},
        {"send_completed": "PRIVATE_SENTINEL"},
    ):
        carrier.preparation("SEND_ATTEMPT", **fields)
    assert case["invalid_fields"] == 11 and len(case["events"]) == 2
    assert "PRIVATE_SENTINEL" not in (tmp_path / "cases.json").read_text()
    carrier.preparation(
        "OLD_CHECK_REJECTION",
        sqlstate="23514",
        constraint_name="messaging_jobs_telegram_probe_check",
    )
    assert case["events"][-1]["constraint_name"] == "messaging_jobs_telegram_probe_check"
    for fields in ({"constraint_name": "PRIVATE_SENTINEL"}, {"sqlstate": "PRIVATE_SENTINEL"}):
        carrier.preparation("OLD_CHECK_REJECTION", **fields)
    assert case["invalid_fields"] == 13 and len(case["events"]) == 3
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
    tmp_path, monkeypatch, driver_inputs, mode, fault
):
    """Exercise orchestration with explicit fake boundaries; no PG/Docker claim."""
    root = tmp_path / "constructed-run"
    (root / "evidence").mkdir(parents=True)
    (root / "private").mkdir()
    assert Path.cwd() == driver_inputs
    for key, value in {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "push",
    }.items():
        monkeypatch.setenv(key, value)
    nodes = [
        module + "::test_constructed_" + str(i)
        for module, count in zip(carrier.MODULES, (35, 22, 9, 1, 1, 1, 1), strict=True)
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
        if label == "catalog-0021" and fault == "catalog":
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
    expected_count = 76 if mode == "targeted" else 70
    assert summary["expected_cases"] == expected_count
    assert summary["sql_test_seconds"] <= 600
    assert summary["result"] == ("PASS" if fault == "none" else "FAIL")
    assert len(cleaned) == summary["groups_visited"]
    assert len(set(cleaned)) == len(cleaned)
    if fault in {"catalog", "budget"}:
        assert summary["groups_visited"] == 1 and len(summary["not_reached"]) == expected_count
        assert not any(label == carrier.COMMAND_REPORT for _, label, _ in calls)
    elif fault == "retained":
        assert summary["groups_visited"] == 9 and len(summary["missing"]) == 34
        assert summary["groups"][-1]["outcome"] == "PASS"
    else:
        assert summary["complete"] and not summary["missing"]
        assert summary["groups_visited"] == (9 if mode == "targeted" else 8)


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
@pytest.mark.parametrize(
    "revision,name",
    [
        ("0018", "business_configuration_schema_profile"),
        ("0019", "published_knowledge_schema_profile"),
        ("0020", "knowledge_search_schema_profile"),
        ("0021", "portfolio_schema_profile"),
        ("0022", "portfolio_delivery_schema_profile"),
        ("0023", "intake_schema_profile"),
        ("0024", "intake_v7_schema_profile"),
        ("0025", "service_request_schema_profile"),
        ("0026", "service_assessment_schema_profile"),
        ("0027", "price_schema_profile"),
        ("0028", "owner_decision_schema_profile"),
        ("0029", "quote_schema_profile"),
        ("0030", "quote_acceptance_schema_profile"),
        ("0031", "service_intent_schema_profile"),
        ("0032", "scheduling_availability_schema_profile"),
        ("0033", "scheduling_hold_schema_profile"),
        ("0034", "scheduling_appointment_schema_profile"),
    ],
)
def test_current_verifier_embedded_table_is_independent_and_closed(damage, reason, revision, name):
    expected = catalog.source_catalog(catalog.ROOT, revision)
    profile = expected["functions"]["platform." + name + "()"]
    row = "('platform.human_context_schema_profile()','527fce5681d5345369cd88b555a302df6d305ef8566cf12a666198eb64a6f4ac','sql',true,'s',false)"
    assert profile["body"].count(row) == 1
    replacement = {
        "self": row.replace("human_context_schema_profile", name),
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
    "revision,name,functions,others",
    [
        ("0018", "business_configuration_schema_profile", 202, 201),
        ("0019", "published_knowledge_schema_profile", 207, 206),
        ("0020", "knowledge_search_schema_profile", 233, 232),
        ("0021", "portfolio_schema_profile", 289, 288),
        ("0022", "portfolio_delivery_schema_profile", 303, 302),
        ("0023", "intake_schema_profile", 318, 317),
        ("0024", "intake_v7_schema_profile", 321, 320),
        ("0025", "service_request_schema_profile", 331, 330),
        ("0026", "service_assessment_schema_profile", 340, 339),
        ("0027", "price_schema_profile", 348, 347),
        ("0028", "owner_decision_schema_profile", 359, 358),
        ("0029", "quote_schema_profile", 377, 376),
        ("0030", "quote_acceptance_schema_profile", 390, 389),
        ("0031", "service_intent_schema_profile", 409, 408),
        ("0032", "scheduling_availability_schema_profile", 416, 415),
        ("0033", "scheduling_hold_schema_profile", 430, 429),
        ("0034", "scheduling_appointment_schema_profile", 434, 433),
    ],
)
@pytest.mark.parametrize("field", ["functions", "others", "tables"])
def test_current_verifier_rejects_stale_count_predicates(revision, name, functions, others, field):
    expected = catalog.source_catalog(catalog.ROOT, revision)
    profile = expected["functions"]["platform." + name + "()"]
    predicate = {
        "functions": f"(SELECT count(*) FROM functions)={functions}",
        "others": f"(SELECT count(DISTINCT to_regprocedure(signature)) FROM expected)={others}",
        "tables": f"(SELECT count(*) FROM tables)={len(expected['columns'])}",
    }[field]
    assert profile["body"].count(predicate) == 1
    profile["body"] = profile["body"].replace(predicate, predicate.rsplit("=", 1)[0] + "=0")
    with pytest.raises(catalog.Refusal, match="^EMBEDDED_COUNT_PREDICATE$"):
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
    from asm.foundation import DATABASE_SCHEMA_REVISION, NATIVE_CONTEXT_PROFILE_SHA256

    expected = catalog.source_catalog(catalog.ROOT, DATABASE_SCHEMA_REVISION)
    profile_name = "platform.scheduling_appointment_schema_profile()"
    if not body_matches:
        expected["functions"][profile_name]["body_sha256"] = "0" * 64
    digest = NATIVE_CONTEXT_PROFILE_SHA256 if hash_matches else "f" * 64
    declared = {
        "schema_revision": DATABASE_SCHEMA_REVISION,
        "valid": valid,
        "profile_sha256": digest,
    }
    result = carrier.catalog_comparison(expected, digest, "{}", declared)
    assert result["failed_predicate"] == reason
    assert result["application_pin_matches"] is hash_matches
    assert result["application_body_pin_matches"] is body_matches


@pytest.fixture
def r11_event(foundation_git, tmp_path, monkeypatch):
    """Constructed real Git history; actual admission code, no Docker/DB."""
    f = foundation_git
    # Checks images omit host pins/lock files. These private inputs are only
    # hashed by source export; no image is built and no dependency is resolved.
    for name, content in {
        "infra/images.lock.env": f"DB_IMAGE={carrier.DB_IMAGE}\n",
        "uv.lock": "# Synthetic unit input; never resolved.\nversion = 1\n",
    }.items():
        path = f.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    f.git("add", ".")
    f.git("commit", "-qm", "locked source identity inputs")
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

    def admitted(root, event, manifest, mode, *, sql_test_budget_seconds=600):
        boundary.append(
            {
                "root": root,
                "event": event,
                "manifest": manifest,
                "mode": mode,
                "sql_test_budget_seconds": sql_test_budget_seconds,
            }
        )

    def forbidden(*args, **kwargs):
        pytest.fail("resource or credential boundary was entered")

    original_capture = carrier.capture

    def only_git(args):
        assert args[0] == "git", "Docker/credentials before source admission"
        return original_capture(args)

    monkeypatch.setattr(carrier, "capture", only_git)
    real_run_admitted = carrier.run_admitted
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
        real_run_admitted=real_run_admitted,
    )


def prepare_m5_planning_event(r, monkeypatch, route, *, extra=None, branch=None):
    """Actual Git merge and event admission, with the resource boundary forbidden."""
    f = r["f"]
    # Planning starts after the legacy runtime base, as PR45 does in the real repo.
    monkeypatch.setattr(carrier, "M5_PLAN_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_PLAN_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    for relative in sorted(carrier.M5_PLAN_PATHS | ({extra} if extra else set())):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((path.read_text() if path.exists() else "") + "\n# constructed M5 delta\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed M5 planning")
    source, tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    merged = f.git("commit-tree", tree, "-p", r["source"], "-p", source, "-m", "test merge")
    f.git("reset", "--hard", merged)
    env, payload = ci_event(Path(r["env"]["GITHUB_EVENT_PATH"]).parent, route)
    env.update(GITHUB_SHA=merged, GITHUB_RUN_ATTEMPT="1")
    if route == "same-repository-pr-merge":
        env["GITHUB_HEAD_REF"] = branch or carrier.M5_PLAN_BRANCH
        payload["pull_request"]["base"]["sha"] = r["source"]
        payload["pull_request"]["head"].update(sha=source, ref=env["GITHUB_HEAD_REF"])
    else:
        payload.update(after=merged, head_commit={"id": merged})
    r["payload"].clear()
    r["payload"].update(payload)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return merged


def prepare_m5_configuration_event(
    r, monkeypatch, route, *, extra=None, branch=None, wrong_base=False
):
    """Real constructed Git merge for the exact implementation scope; no resources."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_CONFIGURATION_BASE", r["source"])
    monkeypatch.setattr(
        carrier, "M5_CONFIGURATION_TREE", f.git("rev-parse", r["source"] + "^{tree}")
    )
    for relative in sorted(carrier.M5_CONFIGURATION_PATHS | ({extra} if extra else set())):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (path.read_text() if path.exists() else "") + "\n# constructed configuration delta\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed bounded configuration")
    source, tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    base = r["base"] if wrong_base else r["source"]
    merged = f.git("commit-tree", tree, "-p", base, "-p", source, "-m", "test merge")
    f.git("reset", "--hard", merged)
    env, payload = ci_event(Path(r["env"]["GITHUB_EVENT_PATH"]).parent, route)
    env.update(GITHUB_SHA=merged, GITHUB_RUN_ATTEMPT="1")
    if route == "same-repository-pr-merge":
        env["GITHUB_HEAD_REF"] = branch or carrier.M5_CONFIGURATION_BRANCH
        payload["pull_request"]["base"]["sha"] = base
        payload["pull_request"]["head"].update(sha=source, ref=env["GITHUB_HEAD_REF"])
    else:
        payload.update(after=merged, head_commit={"id": merged})
    r["payload"].clear()
    r["payload"].update(payload)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return merged


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("damage", [None, "base", "base_tree", "branch", "paths", "tree"])
def test_m5_configuration_outer_export_and_inner_source_binding(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    merged = prepare_m5_configuration_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1 and r["boundary"][0]["mode"] == "runtime"
    receipt = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert (receipt["base"], receipt["base_tree"]) == (
        carrier.M5_CONFIGURATION_BASE,
        carrier.M5_CONFIGURATION_TREE,
    )
    assert set(receipt["paths"]) == carrier.M5_CONFIGURATION_PATHS
    assert r["boundary"][0]["sql_test_budget_seconds"] == 600
    assert not list((r["root"] / "private").iterdir())

    class BeforeResources(Exception):
        pass

    actual_run = subprocess.run

    def stop_at_archive(args, *positional, **keywords):
        assert args[0] == "git", "resource before source export"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", stop_at_archive)
    bound = r["boundary"][0]
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](bound["root"], bound["event"], bound["manifest"], bound["mode"])
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_CONFIGURATION_BRANCH and proof["source"] == merged
    assert proof["paths"] == receipt["paths"]
    for key, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": receipt["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, value)
    if damage:
        proof[damage] = {
            "base": "f" * 40,
            "base_tree": "f" * 40,
            "branch": "c1/unapproved",
            "paths": ["backend/src/asm/ai/runtime.py"],
            "tree": "f" * 40,
        }[damage]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == receipt["tree"]


@pytest.mark.parametrize("damage", ["branch", "base", "base_tree", "path"])
def test_m5_configuration_outer_refuses_unapproved_source_before_resources(
    r11_event, monkeypatch, damage
):
    r = r11_event
    prepare_m5_configuration_event(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        extra="backend/src/asm/ai/runtime.py" if damage == "path" else None,
        branch="c1/unapproved" if damage == "branch" else None,
        wrong_base=damage == "base",
    )
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_CONFIGURATION_TREE", "f" * 40)
    with pytest.raises((carrier.Refusal, catalog.Refusal)) as caught:
        r["run"]()
    assert (
        str(caught.value)
        == {
            "branch": "POLZA_RUNTIME_EVENT_BRANCH",
            "base": "CONFIGURATION_EVENT_BASE",
            "base_tree": "BASE_TREE",
            "path": "POLZA_RUNTIME_WRITE_SET",
        }[damage]
    )
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "route,damage",
    [
        (route, damage)
        for route in ("same-repository-pr-merge", "main-push")
        for damage in (None, "base", "base_tree", "source", "branch", "event")
    ]
    + [("same-repository-pr-merge", "paths")],
)
def test_m5_planning_and_post_merge_admit_exact_files_to_full_runtime(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    merged = prepare_m5_planning_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1
    assert r["boundary"][0]["mode"] == "runtime"
    assert r["boundary"][0]["event"]["head"] == merged
    receipt = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    expected_base = r["source"] if route == "same-repository-pr-merge" else r["base"]
    assert receipt["base"] == expected_base and receipt["source"] == merged
    assert set(receipt["paths"]) == carrier.M5_PLAN_PATHS
    assert not list((r["root"] / "private").iterdir())

    # Exercise the real producer and the DB-image consumer, not just outer admission.
    # Stop at archive export, before the first Docker/resource operation.
    class BeforeResources(Exception):
        pass

    actual_run = subprocess.run

    def stop_after_source_export(args, *positional, **keywords):
        assert args[0] == "git"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", stop_after_source_export)
    b = r["boundary"][0]
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](b["root"], b["event"], b["manifest"], b["mode"])
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert (proof["base"], proof["base_tree"], proof["paths"]) == (
        receipt["base"],
        receipt["base_tree"],
        receipt["paths"],
    )
    for key, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": receipt["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, value)
    if damage:
        proof[damage] = {
            "base": "f" * 40,
            "base_tree": "f" * 40,
            "source": "f" * 40,
            "branch": "c0/unapproved",
            "event": "workflow_dispatch",
            "paths": ["backend/src/asm/configuration/service.py"],
        }[damage]
        carrier.write(path, proof)
    if damage:
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == receipt["tree"]


@pytest.mark.parametrize(
    "route,damage,reason",
    [
        ("same-repository-pr-merge", "application", "POLZA_RUNTIME_WRITE_SET"),
        ("same-repository-pr-merge", "migration", "POLZA_RUNTIME_WRITE_SET"),
        ("same-repository-pr-merge", "foreign_doc", "POLZA_RUNTIME_WRITE_SET"),
        ("same-repository-pr-merge", "workflow", "CI gate input drift: .github/workflows/ci.yml"),
        ("same-repository-pr-merge", "branch", "POLZA_RUNTIME_EVENT_BRANCH"),
        ("same-repository-pr-merge", "legacy_branch", "POLZA_RUNTIME_WRITE_SET"),
        ("same-repository-pr-merge", "base_tree", "BASE_TREE"),
        ("main-push", "future_application", "POLZA_RUNTIME_WRITE_SET"),
        ("main-push", "foreign_doc", "POLZA_RUNTIME_WRITE_SET"),
    ],
)
def test_m5_planning_does_not_admit_other_work_or_weaken_legacy_scope(
    r11_event, monkeypatch, route, damage, reason
):
    r = r11_event
    paths = {
        "application": "backend/src/asm/ai/runtime.py",
        "migration": "migrations/versions/0017_ai_reply_rights.py",
        "foreign_doc": "docs/tasks/M6_HANDOFF.md",
        "workflow": ".github/workflows/ci.yml",
        "future_application": "backend/src/asm/configuration/service.py",
    }
    branch = (
        "c0/unapproved"
        if damage == "branch"
        else carrier.BRANCH
        if damage == "legacy_branch"
        else None
    )
    prepare_m5_planning_event(r, monkeypatch, route, extra=paths.get(damage), branch=branch)
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_PLAN_TREE", "f" * 40)
    with pytest.raises((catalog.Refusal, carrier.Refusal)) as caught:
        r["run"]()
    assert str(caught.value) == reason
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "metadata", [None, "refs/heads/main", "refs/heads/c3/task-name", "refs/tags/v1.2"]
)
def test_constructed_full_admission_reaches_targeted_without_resources(r11_event, metadata):
    r = r11_event
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
        "scripts/test_telegram_egress.sh",
        "tests/test_m1_3_c0_acceptance.py",
        "tests/test_postgres.py",
        "tests/test_m1_3_api_postgres.py",
        "tests/test_auth_postgres.py",
        "tests/test_foundation.py",
    ],
)
def test_polza_repair_admits_egress_evidence_producer_without_resources(
    r11_event, monkeypatch, path
):
    r = r11_event
    f = r["f"]
    target = f.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# constructed current-schema evidence producer change\n")
    f.git("add", path)
    f.git("commit", "--amend", "--no-edit")
    source = f.git("rev-parse", "HEAD")
    r["payload"]["after"] = r["payload"]["head_commit"]["id"] = source
    monkeypatch.setenv("GITHUB_SHA", source)

    r["run"]()

    assert len(r["boundary"]) == 1
    assert r["boundary"][0]["event"]["head"] == source
    admitted = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert admitted["result"] == "PASS"
    assert admitted["paths"] == ["scripts/m4_runtime_db.py", path]
    assert not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "path",
    [
        "migrations/versions/0014_ai_runtime.py",
        "migrations/versions/0015_ai_delivery.py",
        "backend/src/asm/auth/service.py",
        "backend/src/asm/ai/probe.py",
        "backend/src/asm/ai/prompts/conversation_v2.txt",
        "frontend/package.json",
        "backend/src/asm/ai/agent.py",
        "tests/test_m4_gateway.py",
        "tests/test_m1_3_api_postgres_extra.py",
        "tests/test_auth_postgres_extra.py",
        "infra/Dockerfile.backend",
        ".github/workflows/ci.yml",
        "scripts/test_browser.sh",
    ],
)
def test_r11_admission_rejects_other_product_and_ci_write_paths(r11_event, monkeypatch, path):
    r = r11_event
    f = r["f"]
    target = f.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        target.read_text() + "\n# forbidden R11 change\n"
        if target.exists()
        else "# forbidden R11 file\n"
    )
    f.git("add", path)
    f.git("commit", "--amend", "--no-edit")
    source = f.git("rev-parse", "HEAD")
    r["payload"]["after"] = r["payload"]["head_commit"]["id"] = source
    monkeypatch.setenv("GITHUB_SHA", source)
    with pytest.raises((catalog.Refusal, carrier.Refusal)) as caught:
        r["run"]()
    assert str(caught.value) == (
        "CI gate input drift: .github/workflows/ci.yml"
        if path == ".github/workflows/ci.yml"
        else "POLZA_RUNTIME_WRITE_SET"
    )
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
        ("write_set", "POLZA_RUNTIME_WRITE_SET"),
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
def test_constructed_full_admission_refuses_before_resources(
    r11_event, monkeypatch, damage, reason
):
    r = r11_event
    f, p = r["f"], r["payload"]
    p["base_ref"] = "refs/heads/main"
    if damage == "repo":
        monkeypatch.setenv("GITHUB_REPOSITORY", "other/repo")
    elif damage == "payload_repo":
        p["repository"]["id"] += 1
    elif damage in {"ref", "capture_not_open"}:
        ref = "refs/heads/" + (
            "c3/m4-3-runtime-catalog-run-r10" if damage == "capture_not_open" else "other"
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
    if reason not in {"BASE_TREE", "POLZA_RUNTIME_WRITE_SET"}:
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
def test_constructed_full_admission_rejects_malformed_metadata_without_echo(r11_event, metadata):
    r = r11_event
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


def prepare_m5_knowledge_event(r, monkeypatch, route, *, extra=None, branch=None, wrong_base=False):
    """Actual Git docs assignment, implementation and merge; no resource substitutes."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_KNOWLEDGE_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_KNOWLEDGE_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    handoff = f.root / "docs/tasks/M5_HANDOFF.md"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text("# constructed C0 assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed C0 knowledge assignment")
    assignment = f.git("rev-parse", "HEAD")
    monkeypatch.setattr(carrier, "M5_KNOWLEDGE_ASSIGNMENT", assignment)
    monkeypatch.setattr(carrier, "M5_KNOWLEDGE_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    for relative in sorted(carrier.M5_KNOWLEDGE_PATHS | ({extra} if extra else set())):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (path.read_text() if path.exists() else "") + "\n# constructed knowledge delta\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed bounded published knowledge")
    source, tree = f.git("rev-parse", "HEAD"), f.git("rev-parse", "HEAD^{tree}")
    base = r["base"] if wrong_base else r["source"]
    merged = f.git("commit-tree", tree, "-p", base, "-p", source, "-m", "test merge")
    f.git("reset", "--hard", merged)
    env, payload = ci_event(Path(r["env"]["GITHUB_EVENT_PATH"]).parent, route)
    env.update(GITHUB_SHA=merged, GITHUB_RUN_ATTEMPT="1")
    if route == "same-repository-pr-merge":
        env["GITHUB_HEAD_REF"] = branch or carrier.M5_KNOWLEDGE_BRANCH
        payload["pull_request"]["base"]["sha"] = base
        payload["pull_request"]["head"].update(sha=source, ref=env["GITHUB_HEAD_REF"])
    else:
        payload.update(after=merged, head_commit={"id": merged})
    r["payload"].clear()
    r["payload"].update(payload)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return merged


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("damage", [None, "base", "base_tree", "branch", "paths", "tree"])
def test_m5_knowledge_outer_export_and_inner_source_binding(r11_event, monkeypatch, route, damage):
    r = r11_event
    merged = prepare_m5_knowledge_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1 and r["boundary"][0]["mode"] == "runtime"
    receipt = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert (receipt["base"], receipt["base_tree"]) == (
        carrier.M5_KNOWLEDGE_BASE,
        carrier.M5_KNOWLEDGE_TREE,
    )
    assert set(receipt["paths"]) == carrier.M5_KNOWLEDGE_PATHS
    assert r["boundary"][0]["sql_test_budget_seconds"] == 900
    assert not list((r["root"] / "private").iterdir())

    class BeforeResources(Exception):
        pass

    actual_run = subprocess.run

    def stop_at_archive(args, *positional, **keywords):
        assert args[0] == "git", "resource before source export"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", stop_at_archive)
    bound = r["boundary"][0]
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](bound["root"], bound["event"], bound["manifest"], bound["mode"])
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_KNOWLEDGE_BRANCH and proof["source"] == merged
    assert proof["paths"] == receipt["paths"]
    for key, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": receipt["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, value)
    if damage:
        proof[damage] = {
            "base": "f" * 40,
            "base_tree": "f" * 40,
            "branch": "c4/unapproved",
            "paths": ["migrations/versions/0018_business_configuration.py"],
            "tree": "f" * 40,
        }[damage]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == receipt["tree"]


@pytest.mark.parametrize(
    "damage", ["branch", "base", "base_tree", "path", "assignment_tree", "assignment_ancestry"]
)
def test_m5_knowledge_outer_refuses_foreign_source_before_resources(r11_event, monkeypatch, damage):
    r = r11_event
    prepare_m5_knowledge_event(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        extra="migrations/versions/0018_business_configuration.py" if damage == "path" else None,
        branch="c4/unapproved" if damage == "branch" else None,
        wrong_base=damage == "base",
    )
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_KNOWLEDGE_TREE", "f" * 40)
    elif damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_KNOWLEDGE_ASSIGNMENT_TREE", "f" * 40)
    elif damage == "assignment_ancestry":
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "unrelated assignment")
        monkeypatch.setattr(carrier, "M5_KNOWLEDGE_ASSIGNMENT", unrelated)
        monkeypatch.setattr(carrier, "M5_KNOWLEDGE_ASSIGNMENT_TREE", tree)
    with pytest.raises((carrier.Refusal, catalog.Refusal)) as caught:
        r["run"]()
    assert (
        str(caught.value)
        == {
            "branch": "POLZA_RUNTIME_EVENT_BRANCH",
            "base": "KNOWLEDGE_EVENT_BASE",
            "base_tree": "BASE_TREE",
            "path": "POLZA_RUNTIME_WRITE_SET",
            "assignment_tree": "KNOWLEDGE_ASSIGNMENT_TREE",
            "assignment_ancestry": "INSPECTION_FAILED",
        }[damage]
    )
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.fixture
def aggregate_driver(r11_event, monkeypatch):
    """Real Git admission and aggregate orchestration; finite fake command/PG boundaries.

    A controlled clock advances only inside the simulated phase, so 700 seconds
    of work need no sleep. This proves execution budgeting, never PostgreSQL/LLM.
    """
    r = r11_event
    module_cases = (35, 22, 9, 41, 25, 17, 11)
    assert len(carrier.MODULES) == len(module_cases)
    nodes = [
        module + "::test_aggregate_" + str(i)
        for module, count in zip(carrier.MODULES, module_cases, strict=True)
        for i in range(count)
    ]
    assert len(nodes) == 160
    clock, calls, cleaned = {"now": 0.0}, [], []
    fault = {"kind": None}
    capture_git = carrier.capture

    def capture(args):
        if args[0] == "git":
            return capture_git(args)
        if "ps" in args:
            return "synthetic-owned-container"
        if "exec" in args:
            return "Uid:\t999\t999\t999\t999"
        if "inspect" in args:
            return "sha256:" + "c" * 64
        raise AssertionError(args)

    def phase(group, label, args, budget):
        assert 0 < budget <= 600
        calls.append((group, label, budget))
        reports = group / "evidence/phases"
        reports.mkdir(exist_ok=True)
        carrier.write(reports / "active.json", {"phase": label})
        elapsed = 0.0
        if label == "inventory":
            carrier.write(
                group / "evidence/all-m4.json",
                {"nodeids": nodes, "collection_exit": 0, "deselected": []},
            )
        elif label == "current-native-inventory":
            carrier.write(
                group / "evidence/current-native-inventory.json",
                {"nodeids": carrier.CURRENT_NATIVE_NODES, "collection_exit": 0, "deselected": []},
            )
        elif label in {
            "schema-0021",
            "catalog-0021",
            "readiness",
            "schema",
            "versions",
            "native-owner",
        }:
            elapsed = 2.0
        elif label == carrier.COMMAND_REPORT:
            elapsed = 95.0
            expected = json.loads((group / "evidence/inventory.json").read_text())["nodeids"]
            if fault["kind"] == "budget" and expected[-1].startswith(carrier.MODULES[-1] + "::"):
                # Match process timeout/termination overhead: the phase reports
                # exit124, and elapsed accounting still includes the overrun.
                elapsed = budget + 0.017
            if elapsed <= budget:
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
                if expected[-1].startswith(carrier.MODULES[-1] + "::"):
                    if fault["kind"] == "missing":
                        cases.pop()
                    elif fault["kind"] == "missing_call":
                        cases[-1]["phases"] = [
                            p for p in cases[-1]["phases"] if p["phase"] != "call"
                        ]
                carrier.write(group / "evidence/cases.json", cases)
                carrier.write(
                    group / "evidence" / carrier.SUMMARY_REPORT,
                    carrier.summarize(cases, expected, 0),
                )
                if expected == carrier.CURRENT_NATIVE_NODES:
                    carrier.write(
                        group / "evidence/before-reset-proofs.json", [{} for _ in expected]
                    )
                    carrier.write(
                        group / "evidence/native-identity-proofs.json", [{} for _ in expected]
                    )
        clock["now"] += elapsed
        code = 124 if elapsed > budget else 0
        carrier.write(
            reports / (label + ".json"),
            {"budget_seconds": budget, "seconds": elapsed, "exit_code": code},
        )
        if code:
            raise carrier.Refusal(label.upper().replace("-", "_") + "_FAILED")

    def cleanup(group):
        cleaned.append(group)
        if fault["kind"] == "cleanup" and group.name.endswith("-group-7"):
            raise carrier.Refusal("CLEANUP_COMMAND_1_FAILED")
        carrier.write(group / "evidence/cleanup.json", {"outcome": "PASS"})

    # The real admission fixture forbids all resources. Only this explicitly
    # synthetic executor supplies disposable non-secret credential placeholders.
    monkeypatch.setattr(carrier.secrets, "token_hex", lambda n: "a" * (2 * n))
    monkeypatch.setattr(carrier, "capture", capture)
    monkeypatch.setattr(carrier, "phase", phase)
    monkeypatch.setattr(carrier, "cleanup", cleanup)
    monkeypatch.setattr(
        carrier, "inventory", lambda group: {"containers": [], "networks": [], "volumes": []}
    )
    monkeypatch.setattr(carrier, "compose", lambda group: ["synthetic-compose"])
    monkeypatch.setattr(
        carrier, "checks", lambda group, *args, **kwargs: ["synthetic-checks", *args]
    )
    monkeypatch.setattr(
        carrier, "current_native_checks", lambda group, label, *args: ["synthetic-native", *args]
    )
    monkeypatch.setattr(carrier.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(carrier, "run_admitted", r["real_run_admitted"])
    return dict(r=r, nodes=nodes, calls=calls, cleaned=cleaned, fault=fault, clock=clock)


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("fault", [None, "budget", "cleanup", "missing", "missing_call"])
def test_m5_admitted_aggregate_budget_keeps_full_inventory_and_fails_closed(
    aggregate_driver, monkeypatch, route, fault
):
    h = aggregate_driver
    r = h["r"]
    prepare_m5_knowledge_event(r, monkeypatch, route)
    h["fault"]["kind"] = fault
    if fault is None:
        r["run"]()
    else:
        with pytest.raises(carrier.Refusal, match="^PRIMARY_FAILED$"):
            r["run"]()
    summary = json.loads((r["root"] / "evidence/summary.json").read_text())
    assert summary["sql_test_budget_seconds"] == 900
    assert summary["expected_cases"] == summary["collected_cases"] == 160
    assert summary["groups_visited"] == len(carrier.MODULES) + 1
    assert len(h["cleaned"]) == len(set(h["cleaned"])) == summary["groups_visited"]
    assert summary["result"] == ("PASS" if fault is None else "FAIL")
    assert summary["inventory_complete"] and summary["collection_complete"]
    assert set(summary["planned_cases_by_module"]) == set(carrier.MODULES)
    commands = [(g, budget) for g, label, budget in h["calls"] if label == carrier.COMMAND_REPORT]
    assert len(commands) == len(carrier.MODULES)
    assert all(0 < budget <= 600 for _, budget in commands)
    assert all(budget == 420 for _, label, budget in h["calls"] if label == "build")
    if fault == "budget":
        assert 900 < summary["sql_test_seconds"] < 901
        assert 0 < commands[-1][1] < 600
        phase = json.loads(
            (commands[-1][0] / "evidence/phases" / (carrier.COMMAND_REPORT + ".json")).read_text()
        )
        assert phase["exit_code"] == 124 and phase["budget_seconds"] == commands[-1][1]
        assert summary["missing_count"] == 11 and summary["not_reached_modules"] == []
    else:
        assert 600 < summary["sql_test_seconds"] < 900
        assert summary["missing_count"] == int(fault == "missing")
        assert summary["missing_call_phase_count"] == int(fault in {"missing", "missing_call"})
        if fault in {"missing", "missing_call"}:
            assert summary["missing_call_phases"] == [h["nodes"][-1]]
        if fault == "cleanup":
            assert summary["groups"][-1]["cleanup"]["code"] == "CLEANUP_COMMAND_1_FAILED"
        if fault is None:
            assert summary["complete"] and summary["missing"] == []
            assert summary["not_reached_modules"] == []


@pytest.mark.parametrize("route", ["configuration", "planning", "targeted"])
def test_historical_routes_retain_600_aggregate_budget(aggregate_driver, monkeypatch, route):
    h = aggregate_driver
    r = h["r"]
    if route == "configuration":
        prepare_m5_configuration_event(r, monkeypatch, "same-repository-pr-merge")
    elif route == "planning":
        prepare_m5_planning_event(r, monkeypatch, "same-repository-pr-merge")
    with pytest.raises(carrier.Refusal, match="^PRIMARY_FAILED$"):
        r["run"]()
    summary = json.loads((r["root"] / "evidence/summary.json").read_text())
    assert summary["sql_test_budget_seconds"] == 600
    assert summary["sql_test_seconds"] <= 600
    assert summary["result"] == "FAIL" and summary["missing_count"] > 0
    assert len(h["cleaned"]) == summary["groups_visited"]
    assert summary["not_reached_modules"]


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_admission_cannot_extend_targeted_budget(aggregate_driver, monkeypatch, route):
    h = aggregate_driver
    r = h["r"]
    prepare_m5_knowledge_event(r, monkeypatch, route)
    (r["root"] / "evidence").mkdir(parents=True)
    (r["root"] / "private").mkdir()
    Path(r["env"]["GITHUB_EVENT_PATH"]).write_text(json.dumps(r["payload"]))
    event, manifest = carrier.admit_source(r["root"] / "evidence")
    with pytest.raises(carrier.Refusal, match="^SQL_TEST_BUDGET_ADMISSION$"):
        carrier.run_admitted(r["root"], event, manifest, "targeted", sql_test_budget_seconds=900)
    assert not h["calls"] and not h["cleaned"]


@pytest.mark.parametrize("route", ["configuration", "planning", "targeted"])
def test_historical_admission_cannot_request_900(aggregate_driver, monkeypatch, route):
    h = aggregate_driver
    r = h["r"]
    if route == "configuration":
        prepare_m5_configuration_event(r, monkeypatch, "same-repository-pr-merge")
    elif route == "planning":
        prepare_m5_planning_event(r, monkeypatch, "same-repository-pr-merge")
    (r["root"] / "evidence").mkdir(parents=True)
    (r["root"] / "private").mkdir()
    Path(r["env"]["GITHUB_EVENT_PATH"]).write_text(json.dumps(r["payload"]))
    event, manifest = carrier.admit_source(r["root"] / "evidence")
    with pytest.raises(carrier.Refusal, match="^SQL_TEST_BUDGET_ADMISSION$"):
        carrier.run_admitted(r["root"], event, manifest, "runtime", sql_test_budget_seconds=900)
    assert not h["calls"] and not h["cleaned"]


def capability_checkout(r, monkeypatch, route, source, *, branch=None, wrong_base=False):
    """Bind the actual Git source and two-parent merge to the CI event."""
    f = r["f"]
    tree = f.git("rev-parse", source + "^{tree}")
    base = r["base"] if wrong_base else r["source"]
    merged = f.git("commit-tree", tree, "-p", base, "-p", source, "-m", "test merge")
    f.git("reset", "--hard", merged)
    env, payload = ci_event(Path(r["env"]["GITHUB_EVENT_PATH"]).parent, route)
    env.update(GITHUB_SHA=merged, GITHUB_RUN_ATTEMPT="1")
    if route == "same-repository-pr-merge":
        env["GITHUB_HEAD_REF"] = branch or carrier.M5_CAPABILITY_BRANCH
        payload["pull_request"]["base"]["sha"] = base
        payload["pull_request"]["head"].update(sha=source, ref=env["GITHUB_HEAD_REF"])
    else:
        payload.update(after=merged, head_commit={"id": merged})
    r["payload"].clear()
    r["payload"].update(payload)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return merged


def prepare_m5_capability_event(
    r, monkeypatch, route, *, extra=None, branch=None, wrong_base=False
):
    """Real Git assignment, changed approved C0 CURRENT, implementation and merge."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_CAPABILITY_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_CAPABILITY_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    for relative in sorted(carrier.M5_CAPABILITY_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# constructed C0 capability assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed immutable C0 capability assignment")
    monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    (f.root / "docs/TASK_REGISTER.md").write_text("# constructed approved C0 CURRENT revision\n")
    f.git("add", "docs/TASK_REGISTER.md")
    f.git("commit", "-qm", "constructed approved C0 docs revision")
    monkeypatch.setattr(
        carrier, "M5_CAPABILITY_C0_DOCS_REVISION", f.git("rev-parse", "HEAD"), raising=False
    )
    monkeypatch.setattr(
        carrier,
        "M5_CAPABILITY_C0_DOCS_TREE",
        f.git("rev-parse", "HEAD^{tree}"),
        raising=False,
    )
    for relative in sorted(
        (carrier.M5_CAPABILITY_PATHS - carrier.M5_CAPABILITY_C0_DOCS)
        | ({extra} if extra else set())
    ):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (path.read_text() if path.exists() else "") + "\n# constructed probe delta\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed bounded capability probe")
    return capability_checkout(
        r, monkeypatch, route, f.git("rev-parse", "HEAD"), branch=branch, wrong_base=wrong_base
    )


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_capability_accepts_approved_docs_revision(r11_event, monkeypatch, route):
    r = r11_event
    merged = prepare_m5_capability_event(r, monkeypatch, route)
    f = r["f"]
    assignment, revision = carrier.M5_CAPABILITY_ASSIGNMENT, carrier.M5_CAPABILITY_C0_DOCS_REVISION
    assert assignment != revision
    assert f.git("merge-base", assignment, "HEAD") == assignment
    assert f.git("merge-base", revision, "HEAD") == revision
    assert f.git("rev-parse", revision + "^{tree}") == carrier.M5_CAPABILITY_C0_DOCS_TREE
    protected = sorted(carrier.M5_CAPABILITY_C0_DOCS)
    assert f.git("diff", "--name-only", assignment, revision, "--", *protected) == (
        "docs/TASK_REGISTER.md"
    )
    assert not f.git("diff", "--name-only", revision, "HEAD", "--", *protected)
    r["run"]()
    assert len(r["boundary"]) == 1 and not list((r["root"] / "private").iterdir())
    bound = r["boundary"][0]
    assert bound["event"]["head"] == merged
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("damage", ["tree", "ancestry", "unrelated_same_tree"])
def test_m5_capability_refuses_unapproved_docs_revision(r11_event, monkeypatch, route, damage):
    r = r11_event
    prepare_m5_capability_event(r, monkeypatch, route)
    f = r["f"]
    assignment, revision = carrier.M5_CAPABILITY_ASSIGNMENT, carrier.M5_CAPABILITY_C0_DOCS_REVISION
    if damage == "tree":
        monkeypatch.setattr(carrier, "M5_CAPABILITY_C0_DOCS_TREE", "f" * 40)
        reason = "CAPABILITY_C0_DOCS_TREE"
    elif damage == "ancestry":
        # Keep the original assignment and exact accepted bytes, but omit the
        # approved docs commit from history. Content equality is not approval.
        tree = f.git("rev-parse", "HEAD^{tree}")
        source = f.git("commit-tree", tree, "-p", assignment, "-m", "omit docs ancestor")
        capability_checkout(r, monkeypatch, route, source)
        assert f.git("merge-base", revision, "HEAD") == assignment
        assert not f.git(
            "diff", "--name-only", revision, "HEAD", "--", *sorted(carrier.M5_CAPABILITY_C0_DOCS)
        )
        reason = "CAPABILITY_C0_DOCS_ANCESTRY"
    else:
        tree = f.git("rev-parse", revision + "^{tree}")
        unrelated = f.git("commit-tree", tree, "-m", "unrelated same-tree docs commit")
        assert unrelated != revision and f.git("rev-parse", unrelated + "^{tree}") == tree
        monkeypatch.setattr(carrier, "M5_CAPABILITY_C0_DOCS_REVISION", unrelated)
        # Actual Git refuses merge-base for unrelated histories, before the
        # ancestry equality predicate can succeed.
        reason = "INSPECTION_FAILED"
    assert f.git("merge-base", assignment, "HEAD") == assignment
    with pytest.raises(carrier.Refusal, match="^" + reason + "$"):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("document", sorted(carrier.M5_CAPABILITY_C0_DOCS))
@pytest.mark.parametrize("drift", ["content", "mode", "type"])
def test_m5_capability_refuses_each_protected_doc_drift_before_resources(
    r11_event, monkeypatch, route, document, drift
):
    r = r11_event
    prepare_m5_capability_event(r, monkeypatch, route)
    f = r["f"]
    revision = carrier.M5_CAPABILITY_C0_DOCS_REVISION
    path = f.root / document
    assert f.git("ls-tree", revision, "--", document).split()[0] == "100644"
    if drift == "content":
        path.write_text(path.read_text() + "# unapproved later change\n")
    elif drift == "mode":
        path.chmod(0o755)
    else:
        path.unlink()
        path.symlink_to("untrusted-doc-target")
    f.git("add", document)
    f.git("commit", "-qm", "unapproved protected doc " + drift)
    capability_checkout(r, monkeypatch, route, f.git("rev-parse", "HEAD"))
    assert f.git("merge-base", revision, "HEAD") == revision
    assert f.git("diff", "--name-only", revision, "HEAD", "--", document) == document
    if drift in {"mode", "type"}:
        assert f.git("ls-tree", "HEAD", "--", document).split()[0] == (
            "100755" if drift == "mode" else "120000"
        )
    with pytest.raises((carrier.Refusal, catalog.Refusal)) as rejected:
        r["run"]()
    if drift != "type":
        assert str(rejected.value) == "CAPABILITY_C0_DOCS_IMMUTABLE"
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("damage", [None, "base", "base_tree", "branch", "paths", "tree", "source"])
def test_m5_capability_outer_export_and_inner_binding(r11_event, monkeypatch, route, damage):
    r = r11_event
    merged = prepare_m5_capability_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1 and not list((r["root"] / "private").iterdir())
    bound = r["boundary"][0]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert admission["base"] == carrier.M5_CAPABILITY_BASE
    assert admission["base_tree"] == carrier.M5_CAPABILITY_TREE
    assert set(admission["paths"]) == carrier.M5_CAPABILITY_PATHS
    assert "tests/test_telegram_egress_migration.py" in admission["paths"]

    class BeforeResources(Exception):
        pass

    actual_run = subprocess.run

    def archive_boundary(args, *a, **kw):
        assert args[0] == "git", "resource or credential access before source export"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", archive_boundary)
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_CAPABILITY_BRANCH and proof["source"] == merged
    for name, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": proof["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    if damage:
        proof[damage] = {
            "base": "f" * 40,
            "base_tree": "f" * 40,
            "branch": "c4/other",
            "paths": [".github/workflows/ci.yml"],
            "tree": "f" * 40,
            "source": "f" * 40,
        }[damage]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == admission["tree"]


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "extra",
    [
        "tests/test_telegram_egress.py",
        "tests/test_telegram_egress_migration_extra.py",
        "scripts/test_telegram_egress_migration.sh",
    ],
)
def test_m5_capability_migration_repair_refuses_adjacent_paths(
    r11_event, monkeypatch, route, extra
):
    r = r11_event
    prepare_m5_capability_event(r, monkeypatch, route, extra=extra)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "damage",
    [
        "branch",
        "base",
        "base_tree",
        "assignment_tree",
        "assignment_ancestry",
        "workflow",
        "migration",
        "ui",
        "c0_docs",
    ],
)
def test_m5_capability_refuses_before_resources_and_preserves_c0_docs(
    r11_event, monkeypatch, damage
):
    r = r11_event
    prepare_m5_capability_event(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        extra={
            "workflow": ".github/workflows/ci.yml",
            "migration": "migrations/new.py",
            "ui": "frontend/new.ts",
            "c0_docs": "docs/TASK_REGISTER.md",
        }.get(damage),
        branch="c4/other" if damage == "branch" else None,
        wrong_base=damage == "base",
    )
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_CAPABILITY_TREE", "f" * 40)
    if damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT_TREE", "f" * 40)
    if damage == "assignment_ancestry":
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "lost assignment ancestor")
        monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT", unrelated)
        monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT_TREE", tree)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("fault", [None, "budget", "cleanup", "missing_call"])
def test_m5_capability_inherits_all_160_cases_and_eight_cleanups(
    aggregate_driver, monkeypatch, route, fault
):
    h = aggregate_driver
    r = h["r"]
    prepare_m5_capability_event(r, monkeypatch, route)
    h["fault"]["kind"] = fault
    if fault is None:
        r["run"]()
    else:
        with pytest.raises(carrier.Refusal, match="^PRIMARY_FAILED$"):
            r["run"]()
    summary = json.loads((r["root"] / "evidence/summary.json").read_text())
    assert summary["sql_test_budget_seconds"] == 900
    assert summary["expected_cases"] == summary["collected_cases"] == 160
    assert summary["groups_visited"] == len(h["cleaned"]) == len(set(h["cleaned"])) == 8
    assert summary["result"] == ("PASS" if fault is None else "FAIL")
    assert all(
        0 < seconds <= 600 for _, label, seconds in h["calls"] if label == carrier.COMMAND_REPORT
    )


@pytest.mark.parametrize("damage", ["assignment_ancestry", "c0_docs", "path"])
def test_m5_capability_main_push_refuses_damaged_assignment_without_resources(
    r11_event, monkeypatch, damage
):
    r = r11_event
    prepare_m5_capability_event(
        r,
        monkeypatch,
        "main-push",
        extra={
            "c0_docs": "docs/TASK_REGISTER.md",
            "path": "backend/src/asm/foundation.py",
        }.get(damage),
    )
    if damage == "assignment_ancestry":
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "lost main assignment")
        monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT", unrelated)
        monkeypatch.setattr(carrier, "M5_CAPABILITY_ASSIGNMENT_TREE", tree)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


def prepare_m5_search_event(r, monkeypatch, route, *, extra=None, branch=None, wrong_base=False):
    """Actual Git C0 assignment + bounded implementation, before all resources."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_SEARCH_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_SEARCH_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    for relative in sorted(carrier.M5_SEARCH_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# constructed C0 search assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed immutable C0 search assignment")
    monkeypatch.setattr(carrier, "M5_SEARCH_ASSIGNMENT", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(carrier, "M5_SEARCH_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    for relative in sorted(
        (carrier.M5_SEARCH_PATHS - carrier.M5_SEARCH_C0_DOCS) | ({extra} if extra else set())
    ):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (path.read_text() if path.exists() else "") + "\n# constructed search delta\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed bounded knowledge search")
    return capability_checkout(
        r,
        monkeypatch,
        route,
        f.git("rev-parse", "HEAD"),
        branch=branch or carrier.M5_SEARCH_BRANCH,
        wrong_base=wrong_base,
    )


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_search_admission_export_and_inner_binding(r11_event, monkeypatch, route):
    r = r11_event
    merged = prepare_m5_search_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1 and not list((r["root"] / "private").iterdir())
    bound = r["boundary"][0]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert admission["source"] == merged and admission["base"] == carrier.M5_SEARCH_BASE
    actual_run = subprocess.run

    class BeforeResources(Exception):
        pass

    def archive_boundary(args, *a, **kw):
        assert args[0] == "git", "resource or credential access before source export"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", archive_boundary)
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_SEARCH_BRANCH and proof["source"] == merged
    for name, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": proof["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    assert carrier.source_tree_from_evidence(path) == admission["tree"]
    proof["paths"] = [".github/workflows/ci.yml"]
    carrier.write(path, proof)
    with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_WRITE_SET"):
        carrier.source_tree_from_evidence(path)


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("document", sorted(carrier.M5_SEARCH_C0_DOCS))
@pytest.mark.parametrize("drift", ["content", "mode", "type"])
def test_m5_search_refuses_each_protected_doc_before_resources(
    r11_event, monkeypatch, route, document, drift
):
    r = r11_event
    prepare_m5_search_event(r, monkeypatch, route)
    f = r["f"]
    path = f.root / document
    if drift == "content":
        path.write_text(path.read_text() + "# unapproved\n")
    elif drift == "mode":
        path.chmod(0o755)
    else:
        path.unlink()
        path.symlink_to("untrusted-target")
    f.git("add", document)
    f.git("commit", "-qm", "unapproved protected C0 document")
    capability_checkout(
        r, monkeypatch, route, f.git("rev-parse", "HEAD"), branch=carrier.M5_SEARCH_BRANCH
    )
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("damage", ["assignment_tree", "assignment_ancestry", "base_tree", "path"])
def test_m5_search_refuses_unapproved_source_before_resources(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    prepare_m5_search_event(r, monkeypatch, route, extra="uv.lock" if damage == "path" else None)
    if damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_SEARCH_ASSIGNMENT_TREE", "f" * 40)
    elif damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_SEARCH_TREE", "f" * 40)
    elif damage == "assignment_ancestry":
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "unrelated same-tree assignment")
        monkeypatch.setattr(carrier, "M5_SEARCH_ASSIGNMENT", unrelated)
        monkeypatch.setattr(carrier, "M5_SEARCH_ASSIGNMENT_TREE", tree)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "damage",
    ["base", "branch", "old_migration", "probe", "workflow", "m1_api", "configuration_permissions"],
)
def test_m5_search_refuses_adjacent_scope_on_pr(r11_event, monkeypatch, damage):
    r = r11_event
    prepare_m5_search_event(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        wrong_base=damage == "base",
        branch="c4/unrelated" if damage == "branch" else None,
        extra={
            "old_migration": "migrations/versions/0019_published_knowledge.py",
            "probe": "backend/src/asm/ai/capability_probe.py",
            "workflow": ".github/workflows/ci.yml",
            "m1_api": "tests/test_m1_3_api_postgres.py",
            "configuration_permissions": "backend/src/asm/configuration/permissions.py",
        }.get(damage),
    )
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_search_inherits_runtime_inventory_cleanup_and_budget(
    aggregate_driver, monkeypatch, route
):
    h = aggregate_driver
    prepare_m5_search_event(h["r"], monkeypatch, route)
    h["r"]["run"]()
    summary = json.loads((h["r"]["root"] / "evidence/summary.json").read_text())
    assert summary["result"] == "PASS"
    assert summary["expected_cases"] == summary["collected_cases"] == 160
    assert summary["groups_visited"] == len(h["cleaned"]) == 8
    assert summary["sql_test_budget_seconds"] == 900


def prepare_m5_portfolio_event(
    r,
    monkeypatch,
    route,
    *,
    extra=None,
    branch=None,
    wrong_base=False,
    wrong_parent=False,
    wrong_checkpoint_parent=False,
    wrong_finish_parent=False,
    wrong_ci_fix_parent=False,
    wrong_unit_fix_parent=False,
    wrong_core_fix_parent=False,
):
    """Construct real Git assignment, contract, C0 upload continuation and candidate."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_PORTFOLIO_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_PORTFOLIO_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    for relative in sorted(carrier.M5_PORTFOLIO_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# constructed C0 portfolio assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed immutable C0 portfolio assignment")
    for label in (
        "ASSIGNMENT",
        "CONTRACT",
        "CONTINUATION",
        "CHECKPOINT",
        "FINISH_ASSIGNMENT",
        "REVIEW_BASE",
        "CI_FIX_ASSIGNMENT",
        "UNIT_REVIEW_BASE",
        "UNIT_FIX_ASSIGNMENT",
        "CORE_REVIEW_BASE",
        "CORE_FIX_ASSIGNMENT",
    ):
        if label != "ASSIGNMENT":
            handoff = f.root / "docs/tasks/M5_HANDOFF.md"
            handoff.write_text(handoff.read_text() + "# approved " + label + "\n")
            f.git("add", ".")
            f.git("commit", "-qm", "constructed " + label)
        monkeypatch.setattr(carrier, "M5_PORTFOLIO_" + label, f.git("rev-parse", "HEAD"))
        monkeypatch.setattr(
            carrier, "M5_PORTFOLIO_" + label + "_TREE", f.git("rev-parse", "HEAD^{tree}")
        )
        if (
            wrong_parent
            and label == "CONTRACT"
            or wrong_checkpoint_parent
            and label == "CONTINUATION"
            or wrong_finish_parent
            and label == "CHECKPOINT"
            or wrong_ci_fix_parent
            and label == "REVIEW_BASE"
            or wrong_unit_fix_parent
            and label == "UNIT_REVIEW_BASE"
            or wrong_core_fix_parent
            and label == "CORE_REVIEW_BASE"
        ):
            f.git("commit", "--allow-empty", "-qm", "unapproved intermediate parent")
    for relative in sorted(
        (carrier.M5_PORTFOLIO_PATHS - carrier.M5_PORTFOLIO_C0_DOCS) | ({extra} if extra else set())
    ):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (path.read_text() if path.exists() else "") + "\n# constructed portfolio delta\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed bounded vision and portfolio")
    return capability_checkout(
        r,
        monkeypatch,
        route,
        f.git("rev-parse", "HEAD"),
        branch=branch or carrier.M5_PORTFOLIO_BRANCH,
        wrong_base=wrong_base,
    )


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_portfolio_admission_export_and_inner_binding(r11_event, monkeypatch, route):
    r = r11_event
    merged = prepare_m5_portfolio_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1 and not list((r["root"] / "private").iterdir())
    bound = r["boundary"][0]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert (admission["source"], admission["base"], admission["base_tree"]) == (
        merged,
        carrier.M5_PORTFOLIO_BASE,
        carrier.M5_PORTFOLIO_TREE,
    )
    assert set(admission["paths"]) == carrier.M5_PORTFOLIO_PATHS
    actual_run = subprocess.run

    class BeforeResources(Exception):
        pass

    def archive_boundary(args, *a, **kw):
        assert args[0] == "git", "resource or credential access before source export"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", archive_boundary)
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_PORTFOLIO_BRANCH
    for name, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": proof["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    assert carrier.source_tree_from_evidence(path) == admission["tree"]
    for forbidden in (
        "backend/src/asm/auth/store.py",
        "frontend/src/HumanContextPanel.tsx",
        "uv.lock",
    ):
        proof["paths"] = [forbidden]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_WRITE_SET"):
            carrier.source_tree_from_evidence(path)


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("document", sorted(carrier.M5_PORTFOLIO_C0_DOCS))
@pytest.mark.parametrize("drift", ["content", "mode", "type"])
def test_m5_portfolio_protected_assignment_files_refused_before_resources(
    r11_event, monkeypatch, route, document, drift
):
    r = r11_event
    prepare_m5_portfolio_event(r, monkeypatch, route)
    f, path = r["f"], r["f"].root / document
    if drift == "content":
        path.write_text(path.read_text() + "# unapproved\n")
    elif drift == "mode":
        path.chmod(0o755)
    else:
        path.unlink()
        path.symlink_to("untrusted-target")
    f.git("add", document)
    f.git("commit", "-qm", "unapproved protected document")
    capability_checkout(
        r, monkeypatch, route, f.git("rev-parse", "HEAD"), branch=carrier.M5_PORTFOLIO_BRANCH
    )
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        "base_tree",
        "assignment_tree",
        "contract_tree",
        "continuation_tree",
        "assignment_ancestry",
        "contract_ancestry",
        "continuation_ancestry",
        "continuation_parent",
        "checkpoint_tree",
        "finish_assignment_tree",
        "checkpoint_ancestry",
        "finish_assignment_ancestry",
        "checkpoint_parent",
        "finish_assignment_parent",
        "review_base_tree",
        "ci_fix_assignment_tree",
        "review_base_ancestry",
        "ci_fix_assignment_ancestry",
        "ci_fix_assignment_parent",
        "unit_review_base_tree",
        "unit_fix_assignment_tree",
        "unit_review_base_ancestry",
        "unit_fix_assignment_ancestry",
        "unit_fix_assignment_parent",
        "core_review_base_tree",
        "core_fix_assignment_tree",
        "core_review_base_ancestry",
        "core_fix_assignment_ancestry",
        "core_fix_assignment_parent",
    ],
)
def test_m5_portfolio_pin_and_ancestry_failures_refuse_before_resources(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    prepare_m5_portfolio_event(
        r,
        monkeypatch,
        route,
        wrong_parent=damage == "continuation_parent",
        wrong_checkpoint_parent=damage == "checkpoint_parent",
        wrong_finish_parent=damage == "finish_assignment_parent",
        wrong_ci_fix_parent=damage == "ci_fix_assignment_parent",
        wrong_unit_fix_parent=damage == "unit_fix_assignment_parent",
        wrong_core_fix_parent=damage == "core_fix_assignment_parent",
    )
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_PORTFOLIO_TREE", "f" * 40)
    elif damage.endswith("_tree"):
        monkeypatch.setattr(carrier, "M5_PORTFOLIO_" + damage.upper(), "f" * 40)
    elif damage.endswith("_ancestry"):
        label = damage.removesuffix("_ancestry").upper()
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "unrelated same-tree assignment")
        monkeypatch.setattr(carrier, "M5_PORTFOLIO_" + label, unrelated)
        monkeypatch.setattr(carrier, "M5_PORTFOLIO_" + label + "_TREE", tree)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize(
    "damage",
    [
        "base",
        "branch",
        "old_migration",
        "probe",
        "workflow",
        "auth_store",
        "human_context_panel",
        "future_migration",
        "adjacent_telegram",
        "production_probe",
        "adjacent_configuration",
        "playwright_config",
    ],
)
def test_m5_portfolio_refuses_adjacent_scope_on_pr(r11_event, monkeypatch, damage):
    r = r11_event
    prepare_m5_portfolio_event(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        wrong_base=damage == "base",
        branch="c4/unrelated" if damage == "branch" else None,
        extra={
            "old_migration": "migrations/versions/0020_knowledge_search.py",
            "probe": "backend/src/asm/ai/capability_probe.py",
            "workflow": ".github/workflows/ci.yml",
            "auth_store": "backend/src/asm/auth/store.py",
            "human_context_panel": "frontend/src/HumanContextPanel.tsx",
            "future_migration": "migrations/versions/0022_future.py",
            "adjacent_telegram": "tests/test_m2_3_wire_postgres.py",
            "production_probe": "backend/src/asm/ai/probe.py",
            "adjacent_configuration": "tests/test_m5_configuration_api_postgres.py",
            "playwright_config": "frontend/playwright.config.ts",
        }.get(damage),
    )
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_portfolio_preserves_runtime_inventory_cleanup_and_budget(
    aggregate_driver, monkeypatch, route
):
    h = aggregate_driver
    prepare_m5_portfolio_event(h["r"], monkeypatch, route)
    h["r"]["run"]()
    summary = json.loads((h["r"]["root"] / "evidence/summary.json").read_text())
    assert summary["result"] == "PASS"
    assert summary["expected_cases"] == summary["collected_cases"] == 160
    assert summary["groups_visited"] == len(h["cleaned"]) == 8
    assert summary["sql_test_budget_seconds"] == 900


def prepare_m5_foundation_budget_event(
    r, monkeypatch, route, *, extra=None, branch=None, wrong_base=False, wrong_parent=False
):
    """Real Git 45-minute base, C0 assignment, exact CI fix and merge event."""
    f = r["f"]
    workflow = f.root / ".github/workflows/ci.yml"
    # Reconstruct the reviewed M5 workflow even when the current job budgets change.
    historical_workflow = re.sub(
        r"(?m)(^  (browser|foundation):\n(?:    needs: \[foundation-durable\]\n)?"
        r"    runs-on: ubuntu-24\.04\n    timeout-minutes: )\d+$",
        lambda m: m[1] + {"browser": "30", "foundation": "60"}[m[2]],
        workflow.read_text(),
    )
    historical_pin = "f5b67834ace38286e28b3ad8299f3a66078090e895fd22c5ad31c9b4e9e98f0b"
    assert catalog.sha256(historical_workflow.encode()) == historical_pin
    monkeypatch.setitem(catalog.CI_INPUT_SHA256, ".github/workflows/ci.yml", historical_pin)
    current = "  foundation:\n    needs: [foundation-durable]\n    runs-on: ubuntu-24.04\n    timeout-minutes: 60"
    assert historical_workflow.count(current) == 1
    workflow.write_text(historical_workflow.replace(current, current.replace(": 60", ": 45")))
    f.git("add", ".")
    f.git("commit", "-qm", "constructed reviewed application with foundation45")
    r["source"] = f.git("rev-parse", "HEAD")
    monkeypatch.setattr(carrier, "M5_FOUNDATION_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_FOUNDATION_TREE", f.git("rev-parse", "HEAD^{tree}"))
    if wrong_parent:
        f.git("commit", "--allow-empty", "-qm", "unapproved assignment parent")
    for relative in sorted(carrier.M5_FOUNDATION_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# constructed C0 foundation budget assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed foundation budget assignment")
    monkeypatch.setattr(carrier, "M5_FOUNDATION_ASSIGNMENT", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(carrier, "M5_FOUNDATION_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    for relative in sorted(
        (carrier.M5_FOUNDATION_PATHS - carrier.M5_FOUNDATION_C0_DOCS)
        | ({extra} if extra else set())
    ):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path == workflow:
            path.write_text(historical_workflow)
        else:
            path.write_text((path.read_text() if path.exists() else "") + "\n# bounded CI fix\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed foundation60 and narrow admission")
    return capability_checkout(
        r,
        monkeypatch,
        route,
        f.git("rev-parse", "HEAD"),
        branch=branch or carrier.M5_FOUNDATION_BRANCH,
        wrong_base=wrong_base,
    )


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage", [None, "base", "base_tree", "branch", "paths", "tree", "attempt"]
)
def test_m5_foundation_budget_admission_export_and_persisted_binding(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    merged = prepare_m5_foundation_budget_event(r, monkeypatch, route)
    r["run"]()
    assert len(r["boundary"]) == 1 and not list((r["root"] / "private").iterdir())
    bound = r["boundary"][0]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert (admission["source"], admission["base"], admission["base_tree"]) == (
        merged,
        carrier.M5_FOUNDATION_BASE,
        carrier.M5_FOUNDATION_TREE,
    )
    assert set(admission["paths"]) == carrier.M5_FOUNDATION_PATHS
    actual_run = subprocess.run

    class BeforeResources(Exception):
        pass

    def archive_boundary(args, *positional, **keywords):
        assert args[0] == "git", "resource or credential access before source export"
        if args[1] == "archive":
            raise BeforeResources
        return actual_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", archive_boundary)
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_FOUNDATION_BRANCH
    assert proof["paths"] == admission["paths"]
    for name, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": proof["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    if damage:
        proof[damage] = {
            "base": "f" * 40,
            "base_tree": "f" * 40,
            "branch": carrier.M5_PORTFOLIO_BRANCH,
            "paths": ["backend/src/asm/foundation.py"],
            "tree": "f" * 40,
            "attempt": 2,
        }[damage]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == admission["tree"]


@pytest.mark.parametrize("damage", ["branch", "base"])
def test_m5_foundation_budget_wrong_pr_identity_refused(r11_event, monkeypatch, damage):
    r = r11_event
    prepare_m5_foundation_budget_event(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        wrong_base=damage == "base",
        branch="c4/unapproved" if damage == "branch" else None,
    )
    with pytest.raises(
        carrier.Refusal,
        match="^"
        + {
            "branch": "POLZA_RUNTIME_EVENT_BRANCH",
            "base": "FOUNDATION_BUDGET_EVENT_BASE",
        }[damage]
        + "$",
    ):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        "base_tree",
        "base_ancestry",
        "assignment_tree",
        "assignment_ancestry",
        "assignment_parent",
        "application",
        "workflow",
    ],
)
def test_m5_foundation_budget_pin_and_adjacent_path_refusals(r11_event, monkeypatch, route, damage):
    r = r11_event
    prepare_m5_foundation_budget_event(
        r,
        monkeypatch,
        route,
        wrong_parent=damage == "assignment_parent",
        extra={
            "application": "backend/src/asm/foundation.py",
            "workflow": ".github/workflows/m4-runtime-db.yml",
        }.get(damage),
    )
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_FOUNDATION_TREE", "f" * 40)
    elif damage == "base_ancestry":
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "unrelated same-tree base")
        monkeypatch.setattr(carrier, "M5_FOUNDATION_BASE", unrelated)
        monkeypatch.setattr(carrier, "M5_FOUNDATION_TREE", tree)
    elif damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_FOUNDATION_ASSIGNMENT_TREE", "f" * 40)
    elif damage == "assignment_ancestry":
        tree = r["f"].git("rev-parse", "HEAD^{tree}")
        unrelated = r["f"].git("commit-tree", tree, "-m", "unrelated same-tree assignment")
        monkeypatch.setattr(carrier, "M5_FOUNDATION_ASSIGNMENT", unrelated)
        monkeypatch.setattr(carrier, "M5_FOUNDATION_ASSIGNMENT_TREE", tree)
    reason = {
        "base_tree": "BASE_TREE",
        "base_ancestry": (
            "FOUNDATION_BUDGET_EVENT_BASE"
            if route == "same-repository-pr-merge"
            else "FOUNDATION_BUDGET_ASSIGNMENT_PARENT"
        ),
        "assignment_tree": "FOUNDATION_BUDGET_ASSIGNMENT_TREE",
        "assignment_ancestry": "INSPECTION_FAILED",
        "assignment_parent": "FOUNDATION_BUDGET_ASSIGNMENT_PARENT",
        "application": "POLZA_RUNTIME_WRITE_SET",
        "workflow": "POLZA_RUNTIME_WRITE_SET",
    }[damage]
    with pytest.raises(carrier.Refusal, match="^" + reason + "$"):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize("document", sorted(carrier.M5_FOUNDATION_C0_DOCS))
@pytest.mark.parametrize("drift", ["content", "mode", "type"])
def test_m5_foundation_budget_assignment_docs_remain_immutable(
    r11_event, monkeypatch, route, document, drift
):
    r = r11_event
    prepare_m5_foundation_budget_event(r, monkeypatch, route)
    f, path = r["f"], r["f"].root / document
    if drift == "content":
        path.write_text(path.read_text() + "# unapproved\n")
    elif drift == "mode":
        path.chmod(0o755)
    else:
        path.unlink()
        path.symlink_to("untrusted-target")
    f.git("add", document)
    f.git("commit", "-qm", "unapproved C0 document drift")
    capability_checkout(
        r, monkeypatch, route, f.git("rev-parse", "HEAD"), branch=carrier.M5_FOUNDATION_BRANCH
    )
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m5_foundation_budget_keeps_existing_runtime_inventory_and_sql_cap(
    aggregate_driver, monkeypatch, route
):
    h = aggregate_driver
    prepare_m5_foundation_budget_event(h["r"], monkeypatch, route)
    h["r"]["run"]()
    summary = json.loads((h["r"]["root"] / "evidence/summary.json").read_text())
    assert summary["result"] == "PASS"
    assert summary["expected_cases"] == summary["collected_cases"] == 160
    assert summary["groups_visited"] == len(h["cleaned"]) == 8
    assert summary["sql_test_budget_seconds"] == 900


def prepare_m5_delivery_event(
    r,
    monkeypatch,
    route,
    *,
    extra=None,
    wrong_parent=False,
    wrong_amendment_parent=False,
    missing_amendment=False,
    application_amendment=False,
    wrong_second_parent=False,
    merged_second_parent=False,
    missing_second_amendment=False,
    application_second_amendment=False,
):
    """Constructed local Git/event metadata, never an Actions execution claim."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_DELIVERY_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_DELIVERY_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    if wrong_parent:
        f.git("commit", "--allow-empty", "-qm", "constructed unapproved assignment parent")
    for relative in sorted(carrier.M5_DELIVERY_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# constructed immutable C0 photo assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed photo assignment")
    monkeypatch.setattr(carrier, "M5_DELIVERY_ASSIGNMENT", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(carrier, "M5_DELIVERY_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    if wrong_amendment_parent:
        f.git("commit", "--allow-empty", "-qm", "constructed unapproved amendment parent")
    handoff = f.root / "docs/tasks/M5_HANDOFF.md"
    handoff.write_text(handoff.read_text() + "\n# C0 exact inventory scope amendment\n")
    if application_amendment:
        application = f.root / "backend/src/asm/ai/fake.py"
        application.parent.mkdir(parents=True, exist_ok=True)
        application.write_text(
            (application.read_text() if application.exists() else "")
            + "\n# unapproved amendment code\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed C0 scope amendment")
    monkeypatch.setattr(carrier, "M5_DELIVERY_SCOPE_AMENDMENT", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(
        carrier, "M5_DELIVERY_SCOPE_AMENDMENT_TREE", f.git("rev-parse", "HEAD^{tree}")
    )
    if missing_amendment:
        f.git("checkout", "--detach", carrier.M5_DELIVERY_ASSIGNMENT)
    for relative in sorted(
        (carrier.M5_DELIVERY_PATHS - carrier.M5_DELIVERY_C0_DOCS) | ({extra} if extra else set())
    ):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            (path.read_text() if path.exists() else "") + "\n# constructed exact photo delta\n"
        )
    f.git("add", ".")
    f.git("commit", "-qm", "constructed bounded photo repair")
    monkeypatch.setattr(
        carrier, "M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT", f.git("rev-parse", "HEAD")
    )
    if wrong_second_parent:
        f.git("commit", "--allow-empty", "-qm", "constructed unapproved scope02 parent")
    handoff.write_text(handoff.read_text() + "\n# C0 exact initializer scope02 receipt\n")
    if application_second_amendment:
        application = f.root / "backend/src/asm/ai/fake.py"
        application.write_text(application.read_text() + "\n# unapproved scope02 code\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed C0 scope02 receipt")
    if merged_second_parent:
        merged = f.git(
            "commit-tree",
            f.git("rev-parse", "HEAD^{tree}"),
            "-p",
            carrier.M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT,
            "-p",
            carrier.M5_DELIVERY_ASSIGNMENT,
            "-m",
            "constructed two-parent scope02 receipt",
        )
        f.git("checkout", "--detach", merged)
    monkeypatch.setattr(carrier, "M5_DELIVERY_SCOPE_AMENDMENT_02", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(
        carrier, "M5_DELIVERY_SCOPE_AMENDMENT_02_TREE", f.git("rev-parse", "HEAD^{tree}")
    )
    if missing_second_amendment:
        f.git("checkout", "--detach", carrier.M5_DELIVERY_SCOPE_AMENDMENT_02_PARENT)
    handoff.write_text(handoff.read_text() + "\n# constructed final photo candidate\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed final photo candidate")
    return capability_checkout(
        r, monkeypatch, route, f.git("rev-parse", "HEAD"), branch=carrier.M5_DELIVERY_BRANCH
    )


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "base",
        "branch",
        "paths",
        "tree",
        "attempt",
        "scope_sha",
        "scope_tree",
        "scope_parent",
        "scope_missing",
        "scope_extra",
        "scope_type",
        "scope02_sha",
        "scope02_tree",
        "scope02_parent",
        "scope02_missing",
        "scope02_extra",
        "scope02_type",
        "scope_receipts_swapped",
    ],
)
def test_delivery_exact_source_producer_consumer_and_main_selector_priority(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    merged = prepare_m5_delivery_event(r, monkeypatch, route)
    # An earlier main selector must never mask the newly assigned closed route.
    monkeypatch.setattr(carrier, "foundation_budget_event", lambda event: True)
    r["run"]()
    assert len(r["boundary"]) == 1
    bound = r["boundary"][0]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert admission["base"] == carrier.M5_DELIVERY_BASE
    assert set(admission["paths"]) == carrier.M5_DELIVERY_PATHS
    assert admission["scope_amendment"] == carrier.delivery_scope_amendment()
    assert admission["scope_amendment_02"] == carrier.delivery_scope_amendment_02()
    real_run = subprocess.run

    class BeforeResources(Exception):
        pass

    def before_archive(args, *positional, **keywords):
        assert args[0] == "git", "resource/credential access before exact source export"
        if args[1] == "archive":
            raise BeforeResources
        return real_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", before_archive)
    with pytest.raises(BeforeResources):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["branch"] == carrier.M5_DELIVERY_BRANCH
    assert proof["scope_amendment"] == carrier.delivery_scope_amendment()
    assert proof["scope_amendment_02"] == carrier.delivery_scope_amendment_02()
    for name, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": proof["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    if damage:
        if damage in {"scope_sha", "scope_tree", "scope_parent"}:
            proof["scope_amendment"][damage.removeprefix("scope_")] = "f" * 40
        elif damage == "scope_missing":
            del proof["scope_amendment"]
        elif damage == "scope_extra":
            proof["scope_amendment"]["unapproved"] = True
        elif damage == "scope_type":
            proof["scope_amendment"] = "unapproved"
        elif damage in {"scope02_sha", "scope02_tree", "scope02_parent"}:
            proof["scope_amendment_02"][damage.removeprefix("scope02_")] = "f" * 40
        elif damage == "scope02_missing":
            del proof["scope_amendment_02"]
        elif damage == "scope02_extra":
            proof["scope_amendment_02"]["unapproved"] = True
        elif damage == "scope02_type":
            proof["scope_amendment_02"] = "unapproved"
        elif damage == "scope_receipts_swapped":
            proof["scope_amendment"], proof["scope_amendment_02"] = (
                proof["scope_amendment_02"],
                proof["scope_amendment"],
            )
        else:
            proof[damage] = {
                "base": "f" * 40,
                "branch": carrier.M5_FOUNDATION_BRANCH,
                "paths": ["backend/src/asm/ai/polza.py"],
                "tree": "f" * 40,
                "attempt": 2,
            }[damage]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == proof["tree"]
    assert not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        "base_tree",
        "assignment_tree",
        "parent",
        "adjacent",
        "amendment_tree",
        "amendment_parent",
        "amendment_ancestry",
        "amendment_application",
        "scope02_tree",
        "scope02_parent",
        "scope02_merged_parent",
        "scope02_ancestry",
        "scope02_application",
    ],
)
def test_delivery_source_damage_refuses_before_resources(r11_event, monkeypatch, route, damage):
    r = r11_event
    prepare_m5_delivery_event(
        r,
        monkeypatch,
        route,
        extra="backend/src/asm/ai/polza.py" if damage == "adjacent" else None,
        wrong_parent=damage == "parent",
        wrong_amendment_parent=damage == "amendment_parent",
        missing_amendment=damage == "amendment_ancestry",
        application_amendment=damage == "amendment_application",
        wrong_second_parent=damage == "scope02_parent",
        merged_second_parent=damage == "scope02_merged_parent",
        missing_second_amendment=damage == "scope02_ancestry",
        application_second_amendment=damage == "scope02_application",
    )
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_DELIVERY_TREE", "f" * 40)
    elif damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_DELIVERY_ASSIGNMENT_TREE", "f" * 40)
    elif damage == "amendment_tree":
        monkeypatch.setattr(carrier, "M5_DELIVERY_SCOPE_AMENDMENT_TREE", "f" * 40)
    elif damage == "scope02_tree":
        monkeypatch.setattr(carrier, "M5_DELIVERY_SCOPE_AMENDMENT_02_TREE", "f" * 40)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("relative", sorted(carrier.M5_DELIVERY_C0_DOCS))
def test_delivery_assignment_docs_are_immutable_after_assignment(r11_event, monkeypatch, relative):
    r = r11_event
    prepare_m5_delivery_event(r, monkeypatch, "same-repository-pr-merge")
    f = r["f"]
    (f.root / relative).write_text("# unauthorized assignment rewrite\n")
    f.git("add", relative)
    f.git("commit", "-qm", "constructed forbidden assignment rewrite")
    capability_checkout(
        r,
        monkeypatch,
        "same-repository-pr-merge",
        f.git("rev-parse", "HEAD"),
        branch=carrier.M5_DELIVERY_BRANCH,
    )
    with pytest.raises(carrier.Refusal, match="DELIVERY_C0_DOCS_IMMUTABLE"):
        r["run"]()
    assert not r["boundary"]


def prepare_m5_intake_event(r, monkeypatch, route, *, damage=None):
    """Local constructed Git metadata exercises both sides of the source proof."""
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_INTAKE_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_INTAKE_TREE", f.git("rev-parse", r["source"] + "^{tree}"))
    if damage == "parent":
        f.git("commit", "--allow-empty", "-qm", "unexpected pre-assignment commit")
    for relative in sorted(carrier.M5_INTAKE_C0_DOCS | {"docs/tasks/M5_HANDOFF.md"}):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# exact C0 intake assignment\n")
    if damage == "assignment_application":
        path = f.root / "backend/src/asm/ai/fake.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# forbidden assignment application change\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed intake assignment")
    assignment = f.git("rev-parse", "HEAD")
    monkeypatch.setattr(carrier, "M5_INTAKE_ASSIGNMENT", assignment)
    monkeypatch.setattr(carrier, "M5_INTAKE_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    if damage == "missing_assignment":
        f.git("checkout", "--detach", r["source"])
    for relative in sorted(carrier.M5_INTAKE_PATHS - carrier.M5_INTAKE_C0_DOCS):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((path.read_text() if path.exists() else "") + "\n# finite intake delta\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed reviewed intake implementation")
    review = f.git("rev-parse", "HEAD")
    monkeypatch.setattr(carrier, "M5_INTAKE_SCOPE_AMENDMENT_PARENT", review)
    if damage == "scope_parent":
        f.git("commit", "--allow-empty", "-qm", "unapproved receipt parent")
    handoff = f.root / "docs/tasks/M5_HANDOFF.md"
    handoff.write_text(handoff.read_text() + "\n# exact C0 scope receipt\n")
    if damage == "scope_application":
        path = f.root / "tests/test_auth_contract.py"
        path.write_text(path.read_text() + "# receipt must remain docs-only\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed C0 intake scope receipt")
    if damage == "scope_merged_parent":
        merged = f.git(
            "commit-tree",
            f.git("rev-parse", "HEAD^{tree}"),
            "-p",
            review,
            "-p",
            assignment,
            "-m",
            "unexpected two-parent scope receipt",
        )
        f.git("checkout", "--detach", merged)
    monkeypatch.setattr(carrier, "M5_INTAKE_SCOPE_AMENDMENT", f.git("rev-parse", "HEAD"))
    monkeypatch.setattr(
        carrier, "M5_INTAKE_SCOPE_AMENDMENT_TREE", f.git("rev-parse", "HEAD^{tree}")
    )
    if damage == "missing_scope":
        f.git("checkout", "--detach", review)
    if damage == "adjacent":
        path = f.root / "backend/src/asm/ai/polza.py"
        path.write_text("# provider transport stays outside intake scope\n")
    if damage == "protected":
        (f.root / "AGENTS.md").write_text("# forbidden rewrite\n")
    handoff.write_text(handoff.read_text() + "\n# final candidate after scope receipt\n")
    f.git("add", ".")
    f.git("commit", "-qm", "constructed intake candidate")
    return capability_checkout(
        r, monkeypatch, route, f.git("rev-parse", "HEAD"), branch=carrier.M5_INTAKE_BRANCH
    )


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        None,
        "proof_sha",
        "proof_tree",
        "proof_parent",
        "proof_paths",
        "proof_extra",
        "proof_type",
        "proof_missing",
        "scope_sha",
        "scope_tree",
        "scope_parent",
        "scope_paths",
        "scope_extra",
        "scope_type",
        "scope_missing",
        "base",
        "branch",
        "paths",
        "tree",
        "attempt",
    ],
)
def test_intake_producer_consumer_proof_and_route_priority(r11_event, monkeypatch, route, damage):
    r = r11_event
    merged = prepare_m5_intake_event(r, monkeypatch, route)
    monkeypatch.setattr(carrier, "foundation_budget_event", lambda _: True)
    r["run"]()
    assert len(r["boundary"]) == 1
    bound = r["boundary"][0]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert admission["base"] == carrier.M5_INTAKE_BASE
    assert set(admission["paths"]) == carrier.M5_INTAKE_PATHS
    assert admission["intake_assignment"] == carrier.intake_assignment_proof()
    assert admission["intake_scope_amendment"] == carrier.intake_scope_amendment_proof()
    real_run = subprocess.run

    class BeforeArchive(Exception):
        pass

    def before_archive(args, *positional, **keywords):
        assert args[0] == "git", "credentials/resources accessed before source export"
        if args[1] == "archive":
            raise BeforeArchive
        return real_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", before_archive)
    with pytest.raises(BeforeArchive):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["intake_scope_amendment"] == carrier.intake_scope_amendment_proof()
    for name, value in {
        "SOURCE_SHA": merged,
        "SOURCE_TREE": proof["tree"],
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    if damage:
        if damage.startswith("proof_"):
            key = damage.removeprefix("proof_")
            if key == "missing":
                del proof["intake_assignment"]
            elif key == "type":
                proof["intake_assignment"] = "not-a-proof"
            else:
                proof["intake_assignment"][key] = (
                    [] if key == "paths" else True if key == "extra" else "f" * 40
                )
        elif damage.startswith("scope_"):
            key = damage.removeprefix("scope_")
            if key == "missing":
                del proof["intake_scope_amendment"]
            elif key == "type":
                proof["intake_scope_amendment"] = "not-a-proof"
            else:
                proof["intake_scope_amendment"][key] = (
                    [] if key == "paths" else True if key == "extra" else "f" * 40
                )
        else:
            proof[damage] = {
                "base": "f" * 40,
                "branch": carrier.M5_DELIVERY_BRANCH,
                "paths": ["backend/src/asm/ai/polza.py"],
                "tree": "f" * 40,
                "attempt": 2,
            }[damage]
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    else:
        assert carrier.source_tree_from_evidence(path) == proof["tree"]
    assert not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        "base_tree",
        "assignment_tree",
        "parent",
        "assignment_application",
        "missing_assignment",
        "scope_tree",
        "scope_sha",
        "scope_parent",
        "scope_merged_parent",
        "scope_application",
        "missing_scope",
        "adjacent",
        "protected",
        "dirty",
    ],
)
def test_intake_source_damage_refused_before_resources(r11_event, monkeypatch, route, damage):
    r = r11_event
    prepare_m5_intake_event(r, monkeypatch, route, damage=damage)
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_INTAKE_TREE", "f" * 40)
    elif damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_INTAKE_ASSIGNMENT_TREE", "f" * 40)
    elif damage == "scope_tree":
        monkeypatch.setattr(carrier, "M5_INTAKE_SCOPE_AMENDMENT_TREE", "f" * 40)
    elif damage == "scope_sha":
        monkeypatch.setattr(carrier, "M5_INTAKE_SCOPE_AMENDMENT", "f" * 40)
    elif damage == "dirty":
        (r["f"].root / "untracked.py").write_text("# dirty source\n")
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


def prepare_v7_fix_event(r, monkeypatch, route, *, damage=None):
    f = r["f"]
    monkeypatch.setattr(carrier, "M5_V7_FIX_BASE", r["source"])
    monkeypatch.setattr(carrier, "M5_V7_FIX_TREE", f.git("rev-parse", "HEAD^{tree}"))
    if damage == "assignment_parent":
        f.git("commit", "--allow-empty", "-qm", "unexpected prior commit")
    for name in sorted(carrier.M5_V7_FIX_DOCS):
        path = f.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# exact assignment draft\n")
    if damage == "assignment_paths":
        (f.root / "outside.md").write_text("# adjacent assignment rewrite\n")
    f.git("add", ".")
    f.git("commit", "-qm", "v7 assignment")
    assignment = f.git("rev-parse", "HEAD")
    monkeypatch.setattr(carrier, "M5_V7_FIX_ASSIGNMENT", assignment)
    monkeypatch.setattr(carrier, "M5_V7_FIX_ASSIGNMENT_TREE", f.git("rev-parse", "HEAD^{tree}"))
    if damage == "assignment_ancestry":
        f.git("checkout", "--detach", r["source"])
    path = f.root / "migrations/versions/0024_intake_v7_repair.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# approved repair\n")
    if damage == "write_set":
        (f.root / "outside.md").write_text("# outside scope\n")
    if damage in carrier.M5_INTAKE_C0_DOCS:
        (f.root / damage).write_text("# unauthorized rewrite\n")
    f.git("add", ".")
    f.git("commit", "-qm", "v7 candidate")
    head = f.git("rev-parse", "HEAD")
    tree = f.git("rev-parse", "HEAD^{tree}")
    merge = capability_checkout(
        r,
        monkeypatch,
        route,
        head,
        branch="c1/other-v7-branch" if damage == "branch" else carrier.M5_V7_FIX_BRANCH,
        wrong_base=damage == "merge_parents",
    )
    if damage in {"merge_tree", "single_parent"}:
        (f.root / "m4-carrier-receipt.md").write_text("# unexpected merge-specific bytes\n")
        f.git("add", ".")
        replacement = f.git(
            "commit-tree",
            f.git("write-tree"),
            "-p",
            r["source"],
            *(["-p", head] if damage == "merge_tree" else []),
            "-m",
            "damaged merge",
        )
        f.git("reset", "--hard", replacement)
        monkeypatch.setenv("GITHUB_SHA", replacement)
        if route == "main-push":
            r["payload"].update(after=replacement, head_commit={"id": replacement})
    if damage == "dirty":
        (f.root / "untracked.txt").write_text("# working tree drift\n")
    return head, tree, merge


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage", [None, "assignment", "candidate_parents", "candidate_tree", "paths"]
)
def test_v7_fix_actual_git_two_parent_source_and_child_receipt(
    r11_event, monkeypatch, route, damage
):
    r = r11_event
    head, tree, merge = prepare_v7_fix_event(r, monkeypatch, route)
    r["run"]()
    (bound,) = r["boundary"]
    assert bound["mode"] == "runtime" and bound["sql_test_budget_seconds"] == 900
    expected = {"sha": head, "tree": tree, "merge_parents": [r["source"], head]}
    admission = json.loads((r["root"] / "evidence/source-admission.json").read_text())
    assert admission["base"] == carrier.M5_V7_FIX_BASE and admission["tree"] == tree
    assert admission["v7_fix_assignment"] == carrier.v7_fix_assignment_proof()
    assert admission["v7_fix_candidate"] == expected

    real_run = subprocess.run

    class Archived(Exception):
        pass

    def before_archive(args, *positional, **keywords):
        assert args[0] == "git"
        if args[1] == "archive":
            raise Archived
        return real_run(args, *positional, **keywords)

    monkeypatch.setattr(subprocess, "run", before_archive)
    with pytest.raises(Archived):
        r["real_run_admitted"](
            bound["root"],
            bound["event"],
            bound["manifest"],
            bound["mode"],
            sql_test_budget_seconds=900,
        )
    path = r["root"] / "evidence/source.json"
    proof = json.loads(path.read_text())
    assert proof["source"] == merge and proof["branch"] == carrier.M5_V7_FIX_BRANCH
    assert proof["v7_fix_candidate"] == expected
    for key, value in {
        "SOURCE_SHA": merge,
        "SOURCE_TREE": tree,
        "RUN_ID": proof["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, value)
    assert carrier.source_tree_from_evidence(path) == tree
    if damage:
        if damage == "assignment":
            del proof["v7_fix_assignment"]
        elif damage == "candidate_parents":
            proof["v7_fix_candidate"]["merge_parents"].reverse()
        elif damage == "candidate_tree":
            proof["v7_fix_candidate"]["tree"] = "f" * 40
        else:
            proof["paths"] = sorted([*proof["paths"], "outside.md"])
        carrier.write(path, proof)
        with pytest.raises(carrier.Refusal, match="SOURCE_IDENTITY_"):
            carrier.source_tree_from_evidence(path)
    assert not list((r["root"] / "private").iterdir())


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
@pytest.mark.parametrize(
    "damage",
    [
        "base_tree",
        "assignment_tree",
        "assignment_parent",
        "assignment_paths",
        "assignment_ancestry",
        "merge_parents",
        "merge_tree",
        "single_parent",
        "write_set",
        "dirty",
        *sorted(carrier.M5_INTAKE_C0_DOCS),
    ],
)
def test_v7_fix_rejects_damage_before_resources(r11_event, monkeypatch, route, damage):
    r = r11_event
    prepare_v7_fix_event(r, monkeypatch, route, damage=damage)
    if damage == "base_tree":
        monkeypatch.setattr(carrier, "M5_V7_FIX_TREE", "f" * 40)
    elif damage == "assignment_tree":
        monkeypatch.setattr(carrier, "M5_V7_FIX_ASSIGNMENT_TREE", "a" * 40)
    with pytest.raises((carrier.Refusal, catalog.Refusal)):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())


def test_v7_fix_refuses_other_pr_branch(r11_event, monkeypatch):
    r = r11_event
    prepare_v7_fix_event(r, monkeypatch, "same-repository-pr-merge", damage="branch")
    with pytest.raises(carrier.Refusal, match="POLZA_RUNTIME_EVENT_BRANCH"):
        r["run"]()
    assert not r["boundary"]


def prepare_plan_event(r, monkeypatch, route, milestone, *, damage=None):
    f = r["f"]
    name = milestone + "_PLAN"
    plan = getattr(carrier, name)
    base_tree = f.git("rev-parse", "HEAD^{tree}")
    # The generic M5 route also recognizes this ancestry on a main push.
    monkeypatch.setattr(carrier, "M5_V7_FIX_BASE", r["base"])
    handoff = f"docs/tasks/{milestone}_HANDOFF.md"
    document = f.root / handoff
    document.parent.mkdir(parents=True)
    document.write_text("initial plan\n")
    f.git("add", ".")
    f.git("commit", "-qm", "initial plan")
    initial = f.git("rev-parse", "HEAD")
    plan = plan._replace(
        base=r["source"],
        base_tree="f" * 40 if damage == "base_tree" else base_tree,
        initial=initial,
    )
    monkeypatch.setattr(carrier, name, plan)
    if damage == "lineage":
        f.git("checkout", "--detach", r["source"])
    changed = {
        "application": "backend/src/asm/ai/runtime.py",
        "migration": "migrations/versions/future.py",
        "history": "docs/tasks/M6_HANDOFF.md" if milestone == "M7" else "docs/tasks/M5_HANDOFF.md",
        "other_workflow": ".github/workflows/other.yml",
    }.get(damage, "scripts/m4_runtime_db.py")
    path = f.root / changed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("review delta\n")
    f.git("add", ".")
    f.git("commit", "-qm", "reviewed plan")
    head = f.git("rev-parse", "HEAD")
    branch = "c0/other-plan" if damage == "branch" else plan.branch
    merge = capability_checkout(
        r, monkeypatch, route, head, branch=branch, wrong_base=damage == "base"
    )
    if route == "same-repository-pr-merge":
        number = 42 if damage == "pr_number" else plan.pr
        r["payload"]["number"] = r["payload"]["pull_request"]["number"] = number
        monkeypatch.setenv("GITHUB_REF", f"refs/pull/{number}/merge")
        if damage == "head":
            r["payload"]["pull_request"]["head"]["sha"] = initial
    if damage in {"merge_tree", "single_parent"}:
        tree = base_tree if damage == "merge_tree" else f.git("rev-parse", head + "^{tree}")
        parents = ["-p", plan.base] if damage == "single_parent" else ["-p", plan.base, "-p", head]
        merge = f.git("commit-tree", tree, *parents, "-m", "damaged merge")
        f.git("reset", "--hard", merge)
        monkeypatch.setenv("GITHUB_SHA", merge)
        if route == "main-push":
            r["payload"].update(after=merge, head_commit={"id": merge})
    return plan, head, merge


@pytest.mark.parametrize("milestone,revision", [("M6", "0024"), ("M7", "0031")])
@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_planning_source_runs_accepted_schema(
    aggregate_driver, monkeypatch, route, milestone, revision
):
    r = aggregate_driver["r"]
    plan, head, merge = prepare_plan_event(r, monkeypatch, route, milestone)
    r["run"]()
    evidence = r["root"] / "evidence"
    admitted = json.loads((evidence / "source-admission.json").read_text())
    source = json.loads((evidence / "source.json").read_text())
    tree = r["f"].git("rev-parse", head + "^{tree}")
    candidate = {"sha": head, "tree": tree, "merge_parents": [r["source"], head]}
    assert admitted[plan.candidate_key] == source[plan.candidate_key] == candidate
    assert (
        admitted["paths"]
        == source["paths"]
        == [f"docs/tasks/{milestone}_HANDOFF.md", "scripts/m4_runtime_db.py"]
    )
    assert admitted["base"] == source["base"] == r["source"]
    assert (
        admitted["base_tree"]
        == source["base_tree"]
        == r["f"].git("rev-parse", plan.base + "^{tree}")
    )
    assert source["branch"] == plan.branch and admitted["source"] == source["source"] == merge
    assert source["event"] == ("pull_request" if route == "same-repository-pr-merge" else "push")
    for key, val in {
        "SOURCE_SHA": merge,
        "SOURCE_TREE": tree,
        "RUN_ID": "123",
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, val)
    assert carrier.source_tree_from_evidence(evidence / "source.json") == tree
    source[plan.candidate_key]["merge_parents"].reverse()
    carrier.write(evidence / "source.json", source)
    with pytest.raises(carrier.Refusal, match=f"^SOURCE_IDENTITY_{plan.prefix}_CANDIDATE$"):
        carrier.source_tree_from_evidence(evidence / "source.json")
    phases = {label for _, label, _ in aggregate_driver["calls"]}
    assert {"schema-" + revision, "catalog-" + revision, "readiness"} <= phases
    summary = json.loads((evidence / "summary.json").read_text())
    assert summary["result"] == "PASS" and summary["sql_test_budget_seconds"] == 900


@pytest.mark.parametrize("milestone", ["M6", "M7"])
@pytest.mark.parametrize(
    "route,damage,reason",
    [
        ("same-repository-pr-merge", "branch", "POLZA_RUNTIME_EVENT_BRANCH"),
        ("same-repository-pr-merge", "pr_number", "{prefix}_PR_NUMBER"),
        ("same-repository-pr-merge", "base", "{prefix}_EVENT"),
        ("same-repository-pr-merge", "base_tree", "BASE_TREE"),
        ("same-repository-pr-merge", "head", "EVENT_PR_HEAD_PARENT"),
        ("same-repository-pr-merge", "merge_tree", "{prefix}_MERGE_TREE"),
        ("same-repository-pr-merge", "application", "{prefix}_REVIEW_WRITE_SET"),
        ("main-push", "migration", "{prefix}_REVIEW_WRITE_SET"),
        ("main-push", "history", "{prefix}_REVIEW_WRITE_SET"),
        ("main-push", "other_workflow", "{prefix}_REVIEW_WRITE_SET"),
        ("main-push", "lineage", "{prefix}_ASSIGNMENT_ANCESTRY"),
        ("main-push", "single_parent", "{prefix}_MERGE_PARENTS"),
        ("main-push", "merge_tree", "{prefix}_MERGE_TREE"),
    ],
)
def test_planning_source_refuses_before_resources(
    r11_event, monkeypatch, route, damage, reason, milestone
):
    r = r11_event
    plan, _, _ = prepare_plan_event(r, monkeypatch, route, milestone, damage=damage)
    with pytest.raises(
        (carrier.Refusal, catalog.Refusal), match=f"^{reason.format(prefix=plan.prefix)}$"
    ):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())
    assert not (r["root"] / "evidence/source-admission.json").exists()


SCHEDULING_FEATURES = {"scheduling", "holds", "appointments"}
HOLD_PROOF_PATHS = {
    "backend/src/asm/scheduling/offer_store.py",
    "tests/test_m7_scheduling_holds.py",
}
APPOINTMENT_PROOF_PATHS = HOLD_PROOF_PATHS | {
    "frontend/src/SessionBooking.tsx",
    "frontend/e2e/scheduling-booking.spec.ts",
    "tests/test_m7_scheduling_appointments_postgres.py",
}


def prepare_slice_event(r, monkeypatch, route, feature, revision, *, protected=False, damage=None):
    f = r["f"]
    prefix = ("M7_" if feature in SCHEDULING_FEATURES else "M6_") + feature.upper()
    branch = getattr(carrier, prefix + "_BRANCH")
    monkeypatch.setattr(carrier, prefix + "_BASE", r["source"])
    base_tree = f.git("rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(carrier, prefix + "_TREE", "f" * 40 if damage == "base_tree" else base_tree)
    monkeypatch.setattr(carrier, "M5_V7_FIX_BASE", r["base"])
    for document in sorted(getattr(carrier, prefix + "_DOCS")):
        path = f.root / document
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("C0 assignment\n")
    f.git("add", ".")
    f.git("commit", "-qm", "assign slice")
    monkeypatch.setattr(carrier, prefix + "_ASSIGNMENT", f.git("rev-parse", "HEAD"))
    assignment_tree = f.git("rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(
        carrier,
        prefix + "_ASSIGNMENT_TREE",
        "f" * 40 if damage == "assignment_tree" else assignment_tree,
    )
    migration = f.root / getattr(carrier, prefix + "_MIGRATION")
    migration.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text(f"revision = '{revision}'\n")
    if protected:
        handoff = "M7" if feature in SCHEDULING_FEATURES else "M6"
        (f.root / f"docs/tasks/{handoff}_HANDOFF.md").write_text("changed assignment\n")
    outside = {
        "extra_file": "outside-scope.md",
        "historical_migration": "migrations/versions/0032_scheduling_availability.py",
        "other_migration": "migrations/versions/0034_scheduling_future.py",
        "frontend": "frontend/e2e/scheduling-holds.spec.ts",
        "unassigned_tests": "tests/test_m7_appointments.py",
    }.get(damage)
    if outside:
        path = f.root / outside
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not part of the assignment\n")
    if damage is None:
        extra = {"holds": HOLD_PROOF_PATHS, "appointments": APPOINTMENT_PROOF_PATHS}
        for relative in sorted(extra.get(feature, ())):
            path = f.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# permitted scheduling implementation\n")
    f.git("add", ".")
    f.git("commit", "-qm", "implement slice")
    head = f.git("rev-parse", "HEAD")
    merged = capability_checkout(
        r,
        monkeypatch,
        route,
        head,
        branch="c1/m7-unrelated" if damage == "branch" else branch,
        wrong_base=damage == "base",
    )
    if damage in {"merge_tree", "single_parent"}:
        tree = assignment_tree if damage == "merge_tree" else f.git("rev-parse", head + "^{tree}")
        parents = ["-p", r["source"]]
        if damage == "merge_tree":
            parents.extend(["-p", head])
        merged = f.git("commit-tree", tree, *parents, "-m", "damaged slice merge")
        f.git("reset", "--hard", merged)
        monkeypatch.setenv("GITHUB_SHA", merged)
        if route == "main-push":
            r["payload"].update(after=merged, head_commit={"id": merged})
    return head, merged


@pytest.mark.parametrize(
    ("feature", "revision"),
    [
        ("request", "0025"),
        ("assessment", "0026"),
        ("pricing", "0027"),
        ("decision", "0028"),
        ("quote", "0029"),
        ("acceptance", "0030"),
        ("intents", "0031"),
        ("scheduling", "0032"),
        ("holds", "0033"),
        ("appointments", "0034"),
    ],
)
@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_milestone_slice_admits_exact_assignment_and_selects_runtime(
    aggregate_driver, monkeypatch, route, feature, revision
):
    r = aggregate_driver["r"]
    head, merge = prepare_slice_event(r, monkeypatch, route, feature, revision)
    r["run"]()
    evidence = r["root"] / "evidence"
    admitted = json.loads((evidence / "source-admission.json").read_text())
    source = json.loads((evidence / "source.json").read_text())
    tree = r["f"].git("rev-parse", head + "^{tree}")
    prefix = ("M7_" if feature in SCHEDULING_FEATURES else "M6_") + feature.upper()
    assignment = prefix.lower() + "_assignment"
    candidate = prefix.lower() + "_candidate"
    assert admitted[assignment] == source[assignment]
    assert (
        admitted[candidate]
        == source[candidate]
        == {"tree": tree, "sha": head, "merge_parents": [r["source"], head]}
    )
    extra = {"holds": HOLD_PROOF_PATHS, "appointments": APPOINTMENT_PROOF_PATHS}
    assert set(source["paths"]) == getattr(carrier, prefix + "_DOCS") | {
        getattr(carrier, prefix + "_MIGRATION")
    } | extra.get(feature, set())
    for key, val in {
        "SOURCE_SHA": merge,
        "SOURCE_TREE": tree,
        "RUN_ID": "123",
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, val)
    assert carrier.source_tree_from_evidence(evidence / "source.json") == tree
    phases = {label for _, label, _ in aggregate_driver["calls"]}
    assert {"schema-" + revision, "catalog-" + revision, "readiness"} <= phases
    if feature in {"holds", "appointments"}:
        assert source["branch"] == getattr(carrier, prefix + "_BRANCH")
        source["paths"].append("tests/test_unassigned.py")
        carrier.write(evidence / "source.json", source)
        with pytest.raises(carrier.Refusal, match="^SOURCE_IDENTITY_WRITE_SET$"):
            carrier.source_tree_from_evidence(evidence / "source.json")
        source["paths"].pop()
    source[candidate]["merge_parents"].reverse()
    carrier.write(evidence / "source.json", source)
    with pytest.raises(carrier.Refusal, match=f"SOURCE_IDENTITY_{prefix}_CANDIDATE"):
        carrier.source_tree_from_evidence(evidence / "source.json")


@pytest.mark.parametrize(
    ("feature", "revision"),
    [
        ("request", "0025"),
        ("assessment", "0026"),
        ("pricing", "0027"),
        ("decision", "0028"),
        ("quote", "0029"),
        ("acceptance", "0030"),
        ("intents", "0031"),
    ],
)
def test_m6_slice_cannot_change_its_protected_assignment(r11_event, monkeypatch, feature, revision):
    r = r11_event
    prepare_slice_event(
        r, monkeypatch, "same-repository-pr-merge", feature, revision, protected=True
    )
    with pytest.raises(carrier.Refusal, match=f"M6_{feature.upper()}_WRITE_SET"):
        r["run"]()
    assert not r["boundary"]


@pytest.mark.parametrize(
    "route,damage,reason",
    [
        ("same-repository-pr-merge", "branch", "POLZA_RUNTIME_EVENT_BRANCH"),
        ("same-repository-pr-merge", "base", "M7_SCHEDULING_EVENT"),
        ("same-repository-pr-merge", "base_tree", "BASE_TREE"),
        ("same-repository-pr-merge", "protected", "M7_SCHEDULING_WRITE_SET"),
        ("main-push", "assignment_tree", "M7_SCHEDULING_ASSIGNMENT_IDENTITY"),
        ("main-push", "extra_file", "M7_SCHEDULING_WRITE_SET"),
    ],
)
def test_m7_scheduling_refuses_ineligible_source(r11_event, monkeypatch, route, damage, reason):
    r = r11_event
    prepare_slice_event(
        r, monkeypatch, route, "scheduling", "0032", protected=damage == "protected", damage=damage
    )
    with pytest.raises((carrier.Refusal, catalog.Refusal), match=f"^{reason}$"):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())
    assert not (r["root"] / "evidence/source-admission.json").exists()


@pytest.mark.parametrize(
    "route,damage,reason",
    [
        ("same-repository-pr-merge", "branch", "POLZA_RUNTIME_EVENT_BRANCH"),
        ("same-repository-pr-merge", "base", "{prefix}_EVENT"),
        ("same-repository-pr-merge", "base_tree", "BASE_TREE"),
        ("same-repository-pr-merge", "protected", "{prefix}_WRITE_SET"),
        ("same-repository-pr-merge", "frontend", "{prefix}_WRITE_SET"),
        ("same-repository-pr-merge", "merge_tree", "{prefix}_MERGE_TREE"),
        ("main-push", "merge_tree", "{prefix}_MERGE_TREE"),
        ("main-push", "single_parent", "{prefix}_MERGE_PARENTS"),
        ("main-push", "assignment_tree", "{prefix}_ASSIGNMENT_IDENTITY"),
        ("main-push", "historical_migration", "{prefix}_WRITE_SET"),
        ("main-push", "other_migration", "{prefix}_WRITE_SET"),
        ("main-push", "unassigned_tests", "{prefix}_WRITE_SET"),
    ],
)
@pytest.mark.parametrize(("feature", "revision"), [("holds", "0033"), ("appointments", "0034")])
def test_m7_booking_refuses_ineligible_source(
    r11_event, monkeypatch, route, damage, reason, feature, revision
):
    r = r11_event
    prepare_slice_event(
        r, monkeypatch, route, feature, revision, protected=damage == "protected", damage=damage
    )
    with pytest.raises(
        (carrier.Refusal, catalog.Refusal),
        match=f"^{reason.format(prefix='M7_' + feature.upper())}$",
    ):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())
    assert not (r["root"] / "evidence/source-admission.json").exists()


def prepare_m6_4b_event(r, monkeypatch, route, *, damage=None):
    f = r["f"]
    migration = f.root / "migrations/versions/0031_service_intents.py"
    migration.parent.mkdir(parents=True)
    migration.write_text("revision = '0031'\n")
    f.git("add", str(migration))
    f.git("commit", "-qm", "accepted 0031 base")
    r["source"] = f.git("rev-parse", "HEAD")
    monkeypatch.setattr(carrier, "M6_4B_BASE", r["source"])
    base_tree = f.git("rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(carrier, "M6_4B_TREE", "f" * 40 if damage == "base_tree" else base_tree)
    monkeypatch.setattr(carrier, "M5_V7_FIX_BASE", r["base"])

    if damage == "assignment_parent":
        f.git("commit", "--allow-empty", "-qm", "unexpected assignment parent")
    documents = {"docs/TASK_REGISTER.md", "docs/tasks/M6_HANDOFF.md"}
    for relative in sorted(documents):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("C0 assignment\n")
    if damage == "assignment_paths":
        (f.root / "unexpected-assignment.md").write_text("outside assignment scope\n")
    f.git("add", ".")
    f.git("commit", "-qm", "original M6.4B assignment")
    monkeypatch.setattr(carrier, "M6_4B_ASSIGNMENT", f.git("rev-parse", "HEAD"))
    assignment_tree = f.git("rev-parse", "HEAD^{tree}")
    monkeypatch.setattr(
        carrier,
        "M6_4B_ASSIGNMENT_TREE",
        "f" * 40 if damage == "assignment_tree" else assignment_tree,
    )
    if damage == "assignment_ancestry":
        f.git("checkout", "--detach", r["source"])

    implementation = {
        "docs/tasks/M6_4B_ACCEPTANCE.md",
        "frontend/e2e/intake-duration.spec.ts",
        "scripts/m4_runtime_db.py",
        "scripts/m5_intake_fixture.py",
        "tests/test_m4_runtime_db_runner.py",
        "tests/test_m6_quote_delivery_postgres.py",
    }
    if damage in documents | {"backend/src/asm/foundation.py"}:
        implementation.add(damage)
    for relative in sorted(implementation):
        path = f.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("M6.4B candidate delta\n")
    f.git("add", ".")
    f.git("commit", "-qm", "M6.4B candidate")
    head = f.git("rev-parse", "HEAD")
    branch = "c8/m6-other" if damage == "branch" else carrier.M6_4B_BRANCH
    merge = capability_checkout(
        r, monkeypatch, route, head, branch=branch, wrong_base=damage == "base"
    )
    if route == "same-repository-pr-merge":
        number = 64 if damage == "pr_number" else 63
        r["payload"]["number"] = r["payload"]["pull_request"]["number"] = number
        monkeypatch.setenv("GITHUB_REF", f"refs/pull/{number}/merge")
        if damage == "second_parent":
            r["payload"]["pull_request"]["head"]["sha"] = r["source"]
    if damage in {"merge_tree", "single_parent"}:
        tree = assignment_tree if damage == "merge_tree" else f.git("rev-parse", head + "^{tree}")
        parents = ["-p", r["source"]]
        if damage == "merge_tree":
            parents.extend(["-p", head])
        merge = f.git("commit-tree", tree, *parents, "-m", "damaged M6.4B merge")
        f.git("reset", "--hard", merge)
        monkeypatch.setenv("GITHUB_SHA", merge)
        if route == "main-push":
            r["payload"].update(after=merge, head_commit={"id": merge})
    return head, merge, documents | implementation


@pytest.mark.parametrize("route", ["same-repository-pr-merge", "main-push"])
def test_m6_4b_admits_0031_and_reads_bound_source(aggregate_driver, monkeypatch, route):
    r = aggregate_driver["r"]
    head, merge, paths = prepare_m6_4b_event(r, monkeypatch, route)
    r["run"]()
    evidence = r["root"] / "evidence"
    admitted = json.loads((evidence / "source-admission.json").read_text())
    source_path = evidence / "source.json"
    source = json.loads(source_path.read_text())
    tree = r["f"].git("rev-parse", head + "^{tree}")
    assignment = carrier.m6_4b_assignment_proof()
    candidate = {"sha": head, "tree": tree, "merge_parents": [r["source"], head]}
    assert admitted["result"] == "PASS"
    assert admitted["m6_4b_assignment"] == source["m6_4b_assignment"] == assignment
    assert admitted["m6_4b_candidate"] == source["m6_4b_candidate"] == candidate
    assert admitted["paths"] == source["paths"] == sorted(paths)
    assert admitted["source"] == source["source"] == merge
    assert source["branch"] == carrier.M6_4B_BRANCH
    assert source["event"] == ("pull_request" if route == "same-repository-pr-merge" else "push")
    for key, value in {
        "SOURCE_SHA": merge,
        "SOURCE_TREE": tree,
        "RUN_ID": "123",
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + key, value)
    assert carrier.source_tree_from_evidence(source_path) == tree
    source["m6_4b_candidate"]["merge_parents"].reverse()
    carrier.write(source_path, source)
    with pytest.raises(carrier.Refusal, match="^SOURCE_IDENTITY_M6_4B_CANDIDATE$"):
        carrier.source_tree_from_evidence(source_path)
    phases = {label for _, label, _ in aggregate_driver["calls"]}
    assert {"schema-0031", "catalog-0031", "readiness"} <= phases


@pytest.mark.parametrize(
    "route,damage,reason",
    [
        ("same-repository-pr-merge", "branch", "POLZA_RUNTIME_EVENT_BRANCH"),
        ("same-repository-pr-merge", "pr_number", "M6_4B_PR_NUMBER"),
        ("same-repository-pr-merge", "base", "M6_4B_EVENT"),
        ("same-repository-pr-merge", "base_tree", "BASE_TREE"),
        ("same-repository-pr-merge", "second_parent", "EVENT_PR_HEAD_PARENT"),
        ("same-repository-pr-merge", "merge_tree", "M6_4B_MERGE_TREE"),
        ("same-repository-pr-merge", "assignment_tree", "M6_4B_ASSIGNMENT_IDENTITY"),
        ("main-push", "single_parent", "M6_4B_MERGE_PARENTS"),
        ("main-push", "merge_tree", "M6_4B_MERGE_TREE"),
        ("main-push", "assignment_parent", "M6_4B_ASSIGNMENT_IDENTITY"),
        ("main-push", "assignment_ancestry", "M6_4B_ASSIGNMENT_ANCESTRY"),
        ("main-push", "assignment_paths", "M6_4B_ASSIGNMENT_WRITE_SET"),
        ("main-push", "backend/src/asm/foundation.py", "M6_4B_WRITE_SET"),
        ("main-push", "docs/TASK_REGISTER.md", "M6_4B_WRITE_SET"),
        ("same-repository-pr-merge", "docs/tasks/M6_HANDOFF.md", "M6_4B_WRITE_SET"),
    ],
)
def test_m6_4b_refuses_invalid_source_before_resources(
    r11_event, monkeypatch, route, damage, reason
):
    r = r11_event
    prepare_m6_4b_event(r, monkeypatch, route, damage=damage)
    with pytest.raises((carrier.Refusal, catalog.Refusal), match=f"^{reason}$"):
        r["run"]()
    assert not r["boundary"] and not list((r["root"] / "private").iterdir())
    assert not (r["root"] / "evidence/source-admission.json").exists()
