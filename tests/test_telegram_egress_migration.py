"""Migration regressions and the explicit disposable harness extension.

Default pytest collects only unit tests here. run_disposable is invoked solely by
the separate migration shell lane, never by an owner command or the old 6+6 lane.
"""

import argparse
import copy
import hashlib
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from scripts import prepare_telegram_egress as e


def run_disposable(f):
    """Real old helper/images -> completed recovery -> migration, on one held DB."""
    old, run = f["e"], f["run"]
    directory, project = f["directory"], f["project"]
    source, fault = f["migration"]["source"], f["migration"]["fault"]
    assert source == e.command(["git", "-C", str(e.ROOT), "rev-parse", "HEAD"]).decode().strip()
    assert f["source"] == e.MIGRATION_FROM
    phase = f["phase_start"]
    fresh, fresh_dir = f["state"], f["state_dir"]
    phase("migration_exact_predecessor_recovery")
    run([*f["prelive"], "up", "-d", "--no-deps", "--force-recreate", "--wait", "api", "worker"])
    f["compose"]("up", "-d", "--no-deps", "--wait", "egress-https")
    f["compose"]("rm", "-f", "-s", "telegram-egress")
    run(["docker", "network", "rm", f["values"]["ASM_TELEGRAM_EGRESS_NETWORK6"]])
    original_before = old.encoded(old.snapshot(fresh, fresh_dir))
    legacy = {k: v for k, v in fresh.items() if k != "subnet6"}
    legacy.update(version=1, source_sha=old.LEGACY_SHA)
    state_dir = directory / "completed-predecessor"
    state_dir.mkdir(mode=0o700)
    legacy_config = old.encoded(old.minimal_config(f["profile"], f["relay_ip"]))
    legacy["config_sha256"] = old.sha(legacy_config)
    for name, raw in {
        "config.json": legacy_config,
        "runtime.json": (fresh_dir / "runtime.json").read_bytes(),
        "route.env": old.route_env(old.route_values(legacy, state_dir)),
        "state.json": old.encoded(legacy),
        "deployment-before.json": original_before,
    }.items():
        old.write_private(state_dir / name, raw)
    old.write_private(directory / "legacy-compose.yaml", old.LEGACY_OVERLAY)
    legacy_prefix = [
        *old.compose_prefix(legacy, state_dir, overlay=False),
        "-f",
        str(directory / "legacy-compose.yaml"),
        "--profile",
        "telegram-egress",
    ]
    for services in (("telegram-egress",), ("api", "worker")):
        run(
            [
                *legacy_prefix,
                "up",
                "-d",
                "--no-deps",
                "--pull",
                "never",
                "--force-recreate",
                "--wait",
                *services,
            ]
        )
    f["state_dir"] = state_dir
    f["operator"]("recover")
    recovered = old.verify(state_dir)
    f.update(
        state=recovered,
        values=old.route_values(recovered, state_dir),
        live=old.compose_prefix(recovered, state_dir),
        base=old.compose_prefix(recovered, state_dir, overlay=False),
        lifecycle="migration",
    )
    f["prefix"] = [
        *f["live"],
        "-f",
        str(f["root"] / "infra/telegram-egress/compose.test.yaml"),
        "--profile",
        "test",
    ]
    f["operator"]("preflight")
    recovered_bytes = (state_dir / "state.json").read_bytes()
    old_receipt = (state_dir / "recovery.json").read_bytes()
    target = old.snapshot(recovered, state_dir)
    identity = target["api"]["database_identity"]
    assert identity == target["worker"]["database_identity"]
    e.write_private(
        directory / "durable-target.json",
        e.encoded(
            {
                "project": project,
                "postgres_id": f["postgres_id"],
                "database_identity": identity,
                "callers": {n: target[n]["database_identity"] for n in ("api", "worker")},
            }
        ),
    )
    # Keep its exact recovered network endpoints while the synthetic fixture
    # seeds UNKNOWN; a stop would release dynamic addresses to the held one-off.
    run(["docker", "pause", target["worker"]["id"]])
    durable = f["start_checks"](
        ["python", "tests/test_telegram_egress_postgres.py", "--durable-receipt", "before"],
        local=True,
    )
    f["await_process"](durable, marker=directory / "durable-before.json", timeout=90)
    held_started = time.monotonic()
    run(["docker", "unpause", target["worker"]["id"]])
    before = json.loads((directory / "durable-before.json").read_bytes())
    assert len(before["database"]["tables"]) == 31 and before["wire_counter"] == 1
    held_ids = (
        run(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + project,
                "--filter",
                "label=com.docker.compose.service=egress-checks",
            ]
        )
        .decode()
        .split()
    )
    assert len(held_ids) == 1
    held = json.loads(run(["docker", "inspect", held_ids[0]]))[0]
    assert held["Config"]["Labels"]["com.docker.compose.oneoff"] == "True"
    assert (
        held["Image"]
        == json.loads(run(["docker", "image", "inspect", "asm-connect5-development:" + source]))[0][
            "Id"
        ]
    )
    observed = old.snapshot(recovered, state_dir)
    if "egress-checks" in observed:
        assert observed["egress-checks"]["id"] == held["Id"]
        del observed["egress-checks"]
    # UNKNOWN seed itself executes the existing real relay-loss/restart scenario.
    # Admit only its recorded relay ID delta; every other recovered byte/field stays exact.
    assert [row["action"] for row in f["controls"]] == ["recreate", "stop", "recreate"]
    assert observed["telegram-egress"]["id"] == f["controls"][-1]["relay_id"]
    assert observed["telegram-egress"]["id"] != target["telegram-egress"]["id"]
    for name in target:
        before_record, after_record = target[name], observed[name]
        if name == "telegram-egress":
            before_record = {k: v for k, v in before_record.items() if k != "id"}
            after_record = {k: v for k, v in after_record.items() if k != "id"}
        assert after_record == before_record, (
            "MIGRATION_RECOVERED_BASELINE_CHANGED_DURING_FIXTURE_SEED"
        )
    assert observed.keys() == target.keys()
    operator_image = json.loads(
        run(["docker", "image", "inspect", project + "-telegram-operator"])
    )[0]["Id"]
    common = {
        "source_sha": e.MIGRATION_FROM,
        "source_tree": e.MIGRATION_FROM_TREE,
        "original_before_sha256": e.sha(original_before),
    }
    discovery = directory / "asm-telegram-discovery-0b7e24ee.json"
    e.write_private(
        discovery,
        e.encoded(dict(common, status="STARTED", staged_sha256=e.sha(f["staged_inputs"]))),
    )
    corrected = f["staged_inputs"].replace(b"OWNER_ID='101'", b"OWNER_ID='202'")
    journal = directory / "asm-telegram-owner-id-correction-0b7e24ee.json"
    e.write_private(
        journal,
        e.encoded(
            dict(
                common,
                version=1,
                previous_owner_id="101",
                approved_owner_id="202",
                prior_attempt_sha256=e.sha(discovery.read_bytes()),
                staged_before_sha256=e.sha(f["staged_inputs"]),
                staged_after_sha256=e.sha(corrected),
            )
        ),
    )
    e.write_private(directory / "telegram.env", corrected)
    f["staged_inputs"] = corrected
    binding = directory / "asm-telegram-binding-fixture.json"
    e.write_private(
        binding,
        e.encoded(
            dict(
                common,
                status="BINDING_COMMITTED",
                preservation_pass=True,
                staged_sha256=e.sha(corrected),
                operator_image_id=operator_image,
                canonical_database_sha256=before["database"]["sha256"],
                prior_receipts_sha256={p.name: e.sha(p.read_bytes()) for p in (discovery, journal)},
            )
        ),
    )
    receipt = directory / "asm-telegram-diagnostic-fixture.json"
    e.write_private(
        receipt,
        e.encoded(
            dict(
                common,
                status="DIAGNOSTIC_COMPLETE",
                preservation_pass=True,
                staged_sha256=e.sha(corrected),
                operator_image_id=operator_image,
                prior_receipts_sha256={binding.name: e.sha(binding.read_bytes())},
            )
        ),
    )
    arguments = [
        "--state-dir",
        str(state_dir),
        "--accepted-sha",
        source,
        "--from-sha",
        e.MIGRATION_FROM,
        "--predecessor-checkout",
        str(f["root"]),
    ]
    helper = str(e.ROOT / "scripts/prepare_telegram_egress.py")
    timings, interruptions, negatives = {}, [], []
    original_inspects = {
        name: json.loads(run(["docker", "inspect", target[name]["id"]]))[0]
        for name in e.MIGRATION_SERVICES
    }

    def config_diagnostic():
        # Synthetic disposable fixture only: print field names, never values.
        current = e.migration_runtime(recovered, state_dir)
        for name, previous in original_inspects.items():
            if name not in current:
                continue
            observed = json.loads(run(["docker", "inspect", current[name]["id"]]))[0]
            for section in ("Config", "HostConfig"):
                keys = sorted(set(previous[section]) | set(observed[section]))
                changed = [k for k in keys if previous[section].get(k) != observed[section].get(k)]
                print(
                    "MIGRATION_CONFIG_FIELDS=" + name + ":" + section + ":" + ",".join(changed),
                    flush=True,
                )
            before_env = dict(x.split("=", 1) for x in previous["Config"]["Env"])
            after_env = dict(x.split("=", 1) for x in observed["Config"]["Env"])
            print(
                "MIGRATION_ENV_MAPPING_EQUAL=" + name + ":" + str(before_env == after_env),
                flush=True,
            )
            print(
                "MIGRATION_MOUNTS_EQUAL="
                + name
                + ":"
                + str(previous["Mounts"] == observed["Mounts"]),
                flush=True,
            )

    def invoke(action, *, pin=False):
        started = time.monotonic()
        output = run(
            [
                "python3",
                helper,
                action,
                *arguments,
                *(
                    [
                        "--operator-receipt",
                        str(receipt),
                        "--operator-receipt-sha256",
                        e.sha(receipt.read_bytes()),
                    ]
                    if pin
                    else []
                ),
            ],
            180,
        )
        assert output.strip() == ("TELEGRAM_EGRESS_" + action.upper() + "_PASS").encode()
        timings.setdefault(action, []).append(round(time.monotonic() - started, 3))
        assert timings[action][-1] <= 180
        print(output.decode().strip(), flush=True)

    invoke("migration-prepare", pin=True)
    bundle = state_dir / "migration-v3"
    plan = json.loads((bundle / "preparation.json").read_bytes())
    ready = json.loads((bundle / "prepared.json").read_bytes())
    saved = {p: Path(p).read_bytes() for p in plan["files"]}
    assert all(
        plan["image_proofs"][v]["source_sha"] == e.MIGRATION_FROM
        for v in ready["before_images"].values()
    )

    def interrupted(action, reverse=False):
        marker = directory / ("migration-interruption-" + action + ".json")
        # Only wrap actual fsync/real Docker-command boundaries. This executes the
        # candidate helper main(), without stubbing any source/image/DB check.
        injector = r"""
import importlib.util,os,signal,sys
from pathlib import Path
path,fault,marker,reverse=sys.argv[1:5]
spec=importlib.util.spec_from_file_location('migration_candidate',path)
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
sys.argv=[path,*sys.argv[5:]]
save,execute=e.write_private,e.command
def crash():
    save(Path(marker),e.encoded({'boundary':fault,'direction':reverse,'sigkill':True}))
    os.kill(os.getpid(),signal.SIGKILL)
def write(path,raw,**kwargs):
    save(path,raw,**kwargs)
    intent='rollback-intent.json' if reverse=='rollback' else 'intent.json'
    if fault=='intent' and path.name==intent or fault=='state' and path.name=='state.json': crash()
def command(argv,**kwargs):
    value=execute(argv,**kwargs)
    if fault=='image' and 'up' in argv and argv[-1]=='api': crash()
    return value
e.write_private,e.command=write,command
e.main()
"""
        started = time.monotonic()
        result = subprocess.run(
            [
                "python3",
                "-c",
                injector,
                helper,
                fault,
                str(marker),
                "rollback" if reverse else "forward",
                action,
                *arguments,
            ],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=180,
            env=f["environment"],
        )
        if result.returncode != -signal.SIGKILL:
            code = result.stdout.decode().strip()
            if code.startswith("EGRESS_") and len(code) < 150:
                print(code, flush=True)
            config_diagnostic()
        assert result.returncode == -signal.SIGKILL, "MIGRATION_EXPECTED_REAL_SIGKILL"
        evidence = json.loads(marker.read_bytes())
        assert evidence == {
            "boundary": fault,
            "direction": "rollback" if reverse else "forward",
            "sigkill": True,
        }
        evidence["seconds"] = round(time.monotonic() - started, 3)
        interruptions.append(evidence)
        print("MIGRATION_REAL_INTERRUPTION_" + fault.upper(), flush=True)

    interrupted("migrate")
    actual_before_negative = e.migration_runtime(recovered, state_dir)
    if fault == "intent":
        path = state_dir / "deployment-before.json"
        original = path.read_bytes()
        e.write_private(path, original + b"\n")

        def restore():
            e.write_private(path, original)
    elif fault == "image":
        tag = ready["tags"]["development"]
        run(["docker", "tag", operator_image, tag])

        def restore():
            run(["docker", "tag", ready["after_images"]["telegram-operator"], tag])
    else:
        path = state_dir / "state.json"
        original = path.read_bytes()
        changed = json.loads(original)
        changed["source_sha"] = "f" * 40
        e.write_private(path, e.encoded(changed))

        def restore():
            e.write_private(path, original)

    try:
        rejected = subprocess.run(
            ["python3", helper, "migration-resume", *arguments],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=180,
            env=f["environment"],
        )
        assert rejected.returncode == 1 and rejected.stdout.startswith(b"EGRESS_MIGRATION_")
        negatives.append(rejected.stdout.decode().strip())
        assert e.migration_runtime(recovered, state_dir) == actual_before_negative
        assert not (bundle / "forward-complete.json").exists()
    finally:
        restore()
    invoke("migration-resume")
    forward = e.migration_runtime(recovered, state_dir)
    invoke("migration-preflight")
    invoke("migrate")
    assert e.migration_runtime(recovered, state_dir) == forward
    completed = (bundle / "forward-complete.json").read_bytes()
    forward_audit = {p.name: e.sha(p.read_bytes()) for p in bundle.glob("forward-*")}
    assert all(forward[n]["image"] == ready["after_images"][n] for n in e.MIGRATION_SERVICES)
    assert e.verify(state_dir)["version"] == 3
    interrupted("migration-rollback", reverse=True)
    rollback_intent = (bundle / "rollback-intent.json").read_bytes()
    rollback_binding = json.loads(rollback_intent)
    assert rollback_binding["version"] == 2
    assert rollback_binding["forward_audit_sha256"] == forward_audit
    assert rollback_binding["forward_runtime"] == forward
    invoke("migration-rollback")
    rolled_back = e.migration_runtime(recovered, state_dir)
    invoke("migration-rollback")
    assert e.migration_runtime(recovered, state_dir) == rolled_back
    assert (state_dir / "state.json").read_bytes() == recovered_bytes
    assert (bundle / "forward-complete.json").read_bytes() == completed
    assert (bundle / "rollback-intent.json").read_bytes() == rollback_intent
    assert {p.name: e.sha(p.read_bytes()) for p in bundle.glob("forward-*")} == forward_audit
    assert all(rolled_back[n]["image"] == ready["before_images"][n] for n in e.MIGRATION_SERVICES)
    assert all(Path(p).read_bytes() == raw for p, raw in saved.items())
    assert (state_dir / "recovery.json").read_bytes() == old_receipt
    # Return to the preserved exact predecessor checkout, not a manufactured v2.
    f["operator"]("preflight")
    f["compose"](
        "run",
        "--rm",
        "--no-deps",
        "-T",
        *f["local_database_args"](),
        "egress-checks",
        "python",
        "tests/test_telegram_egress_postgres.py",
        "--durable-receipt",
        "after",
    )
    f["await_process"](durable, timeout=30)
    held_seconds = time.monotonic() - held_started
    assert held_seconds < 180, "MIGRATION_HELD_FIXTURE_DEADLINE"
    after = json.loads((directory / "durable-after.json").read_bytes())
    assert before == after and after["wire_counter"] == 1
    assertions = [
        json.loads(row) for row in (directory / "assertions.jsonl").read_text().splitlines()
    ]
    assert len(assertions) == 1 and assertions[0]["result"] == "PASS"
    report = {
        "rollback_audit_binding": {
            "version": 2,
            "forward_audit_sha256": forward_audit,
            "rollback_intent_sha256": e.sha(rollback_intent),
            "unchanged_after_resume_and_completed_retry": True,
        },
        "source_sha": source,
        "source_tree": plan["to_tree"],
        "from_sha": e.MIGRATION_FROM,
        "from_tree": e.MIGRATION_FROM_TREE,
        "fault": fault,
        "timings": timings,
        "held_seconds": round(held_seconds, 3),
        "interruptions": interruptions,
        "negatives": negatives,
        "assertions": assertions,
        "before_images": ready["before_images"],
        "after_images": ready["after_images"],
        "image_proofs": plan["image_proofs"],
        "seed_relay_controls": f["controls"],
        "database_before": before,
        "database_after": after,
        "runtime_before": plan["before"],
        "runtime_forward": forward,
        "runtime_rollback": rolled_back,
        "completed_retry_without_recreate": True,
        "old_source_preflight_after_rollback": True,
        "preserved_files_sha256": {
            Path(p).name + "-" + str(i): e.sha(raw)
            for i, (p, raw) in enumerate(sorted(saved.items()))
        },
        "receipts_sha256": {p.name: e.sha(p.read_bytes()) for p in bundle.glob("*.json")},
        "docker": json.loads(run(["docker", "version", "--format", "{{json .}}"])),
        "compose": run(["docker", "compose", "version", "--short"]).decode().strip(),
    }
    reports = e.ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / ("migration-" + fault + ".json")).write_text(json.dumps(report, indent=2) + "\n")
    print("TELEGRAM_EGRESS_MIGRATION_" + fault.upper() + "_PASS", flush=True)


if __name__ == "__migration_harness__":
    run_disposable(globals()["fixture"])
    raise SystemExit(0)

import pytest  # noqa: E402 -- host harness uses only stdlib; default collection remains ordinary.


@pytest.mark.parametrize("fail", [False, True])
def test_parallel_image_proofs_wait_for_all_and_propagate_failure(monkeypatch, fail):
    barrier = threading.Barrier(4, timeout=5)
    finished = set()
    requests = [(str(i), "source", "runtime") for i in range(4)]

    def probe(image, source, kind):
        barrier.wait()
        finished.add(image)
        if fail and image == "0":
            raise e.EgressError("EGRESS_MIGRATION_TEST_IMAGE_REJECTED")
        return {"id": image, "source_sha": source, "kind": kind}

    monkeypatch.setattr(e, "migration_image", probe)
    if fail:
        with pytest.raises(e.EgressError, match="TEST_IMAGE_REJECTED"):
            e.migration_image_proofs(requests + requests)
    else:
        proofs = e.migration_image_proofs(requests + requests)
        assert set(proofs) == set(requests)
        assert all(proofs[key]["id"] == key[0] for key in requests)
    assert finished == {"0", "1", "2", "3"}


def test_migration_environment_order_is_not_identity():
    rows = ["ASM_TELEGRAM_ENABLED=false", "TG_BOT_TOKEN=", "VALUE=a=b"]
    digest = e.sha(e.encoded(e.migration_environment(rows)))
    assert e.sha(e.encoded(e.migration_environment(list(reversed(rows))))) == digest
    for changed in (rows[:-1], rows + ["EXTRA="], rows[:-1] + ["VALUE=changed"]):
        assert e.sha(e.encoded(e.migration_environment(changed))) != digest


@pytest.mark.parametrize("rows", [["A=1", "A=1"], ["A=1", "A=2"], ["A"], ["=value"]])
def test_migration_environment_rejects_ambiguous_entries(rows):
    with pytest.raises(e.EgressError, match="EGRESS_MIGRATION_ENVIRONMENT_"):
        e.migration_environment(rows)


@pytest.mark.parametrize("kind", ["runtime", "development"])
@pytest.mark.parametrize("drift", [None, "bytes", "extra", "missing"])
def test_image_probe_executes_git_blob_byte_checks(tmp_path, monkeypatch, kind, drift):
    real_command = e.command
    source = "a" * 40
    # The unit image has no Git executable/metadata. Independently form Git-format
    # blobs and an archive from its copied source, and execute the actual probe.
    # The separate disposable lane supplies real Git and Docker, including UID10001.
    paths = [
        "backend",
        "migrations",
        "pyproject.toml",
        "uv.lock",
        "alembic.ini",
        "tests",
        "scripts",
        "contracts",
        "infra/postgres/ensure_m1_3_prerequisites.sh",
    ]
    files = {
        str(p.relative_to(e.ROOT)): p.read_bytes()
        for name in paths
        for p in ([e.ROOT / name] if (e.ROOT / name).is_file() else (e.ROOT / name).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        directories = {str(p) for name in files for p in Path(name).parents if str(p) != "."}
        for name in sorted(directories):
            entry = tarfile.TarInfo(name)
            entry.type, entry.mode = tarfile.DIRTYPE, 0o775
            tar.addfile(entry)
        for name, data in files.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(data), 0o664
            tar.addfile(entry, io.BytesIO(data))
    blobs = {
        name: hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest()
        for name, data in files.items()
    }
    image = "sha256:" + "1" * 64
    probes = []

    def command(argv, **kwargs):
        if argv[0] == "git":
            if "archive" in argv:
                return archive.getvalue()
            assert "ls-tree" in argv
            selected = argv[argv.index("--") + 1 :]
            return b"".join(
                ("100644 blob " + value + "\t" + name).encode() + bytes([0])
                for name, value in blobs.items()
                if any(name == p or name.startswith(p + "/") for p in selected)
            )
        if argv[:3] == ["docker", "image", "inspect"]:
            return e.encoded([{"Id": image, "Os": "linux", "Architecture": "amd64"}])
        assert argv[:6] == ["docker", "run", "--rm", "--network", "none", "--read-only"]
        assert "--cap-drop=ALL" in argv and "--security-opt=no-new-privileges" in argv
        assert argv[-3:-1] == ["-B", "-c"]
        probe = argv[-1].replace(
            "pathlib.Path('/app')", "pathlib.Path(" + repr(str(tmp_path)) + ")"
        )
        probes.append(probe)
        return real_command([sys.executable, "-B", "-c", probe])

    monkeypatch.setattr(e, "command", command)
    mask = os.umask(0o077)
    try:
        e.migration_build_context(source, tmp_path)
    finally:
        os.umask(mask)
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o755 for p in tmp_path.rglob("*") if p.is_dir())
    assert stat.S_IMODE((tmp_path / "backend/src/asm/telegram/client.py").stat().st_mode) == 0o644
    assert not (tmp_path / ".env").exists()
    target = tmp_path / "backend/src/asm/telegram/client.py"
    if drift == "bytes":
        target.write_bytes(target.read_bytes() + b"\n")
    elif drift == "extra":
        (target.parent / "foreign.py").write_bytes(b"# foreign\n")
    elif drift == "missing":
        target.unlink()
    if drift:
        with pytest.raises(e.EgressError, match="EGRESS_COMMAND_FAILED"):
            e.migration_image(image, source, kind)
    else:
        assert e.migration_image(image, source, kind)["source_sha"] == source
    assert len(probes) == 1


@pytest.fixture
def migration_machine(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    bundle = directory / "migration-v3"
    bundle.mkdir(mode=0o700)
    old = {"version": 2, "source_sha": e.MIGRATION_FROM, "generation": "recovery-v2"}
    before_images = {n: "sha256:" + "1" * 64 for n in (*e.MIGRATION_SERVICES, "telegram-operator")}
    after_images = {n: "sha256:" + "2" * 64 for n in before_images}
    database = {"identity": {"database": "asm_local"}, "tables": {"sealed": "original"}}
    runtime = {
        n: {
            "id": n + "-original",
            "image": before_images.get(n, "unchanged"),
            "running": True,
            "config_sha256": "config",
            "host_sha256": "host",
            "mounts": [],
            "networks": {"default": {"Gateway": "g", "IPv6Gateway": "g6", "IPAMConfig": None}},
            **({"database_identity": database["identity"]} if n in e.MIGRATION_SERVICES else {}),
        }
        for n in (*e.MIGRATION_SERVICES, "scheduler", "postgres", "storage", "telegram-egress")
    }
    plan = {
        "version": 1,
        "from_sha": e.MIGRATION_FROM,
        "from_tree": e.MIGRATION_FROM_TREE,
        "to_sha": "f" * 40,
        "to_tree": "e" * 40,
        "before": copy.deepcopy(runtime),
        "before_images": before_images,
        "database": copy.deepcopy(database),
    }
    ready = {"before_images": before_images, "after_images": after_images}
    for name, value in {
        "state-before.json": old,
        "preparation.json": plan,
        "prepared.json": ready,
    }.items():
        e.write_private(bundle / name, e.encoded(value))
    e.write_private(directory / "state.json", e.encoded(old))
    args = argparse.Namespace(accepted_sha=plan["to_sha"], from_sha=e.MIGRATION_FROM)
    effects = []
    monkeypatch.setattr(e, "migration_prepared", lambda _: (bundle, plan, old, ready))
    monkeypatch.setattr(e, "migration_saved", lambda _: (bundle, plan, old))
    monkeypatch.setattr(e, "migration_runtime", lambda *_: copy.deepcopy(runtime))
    monkeypatch.setattr(e, "migration_database", lambda *_: copy.deepcopy(database))
    monkeypatch.setattr(e, "compose_prefix", lambda *_: ["docker", "compose"])
    monkeypatch.setattr(e, "caller_probe", lambda *_: None)

    def command(argv, **kwargs):
        assert "up" in argv and argv[-1] in e.MIGRATION_SERVICES
        side = "before" if "images-before.json" in argv[3] else "after"
        name = argv[-1]
        effects.append((side, name))
        runtime[name] = copy.deepcopy(plan["before"][name])
        runtime[name].update(id=name + str(len(effects)), image=ready[side + "_images"][name])
        return b""

    monkeypatch.setattr(e, "command", command)
    return SimpleNamespace(
        directory=directory,
        bundle=bundle,
        old=old,
        args=args,
        effects=effects,
        runtime=runtime,
        database=database,
        plan=plan,
        ready=ready,
    )


def test_migration_complete_retry_and_explicit_rollback(migration_machine):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    assert len(m.effects) == 2
    completed = (m.bundle / "forward-complete.json").read_bytes()
    final = copy.deepcopy(m.runtime)
    for readonly in (True, False, True):
        e.migration_switch(m.args, m.directory, readonly=readonly)
        assert m.runtime == final and len(m.effects) == 2
        assert (m.bundle / "forward-complete.json").read_bytes() == completed
    e.migration_switch(m.args, m.directory, reverse=True)
    assert len(m.effects) == 4
    assert (m.directory / "state.json").read_bytes() == e.encoded(m.old)
    assert (m.bundle / "forward-complete.json").read_bytes() == completed
    assert m.runtime["scheduler"] == m.plan["before"]["scheduler"]
    e.migration_switch(m.args, m.directory, reverse=True)
    assert len(m.effects) == 4
    with pytest.raises(e.EgressError, match="ROLLBACK_ALREADY_STARTED"):
        e.migration_switch(m.args, m.directory)


def test_forward_complete_tamper_requires_stop(migration_machine):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    path = m.bundle / "forward-complete.json"
    receipt = json.loads(path.read_bytes())
    receipt["database_sha256"] = "0" * 64
    e.write_private(path, e.encoded(receipt))
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects
    assert not (m.bundle / "rollback-intent.json").exists()
    assert not (m.bundle / "rollback-complete.json").exists()


@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize("corrupt", [False, True])
def test_completed_rollback_keeps_forward_result(migration_machine, service, corrupt):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    e.migration_switch(m.args, m.directory, reverse=True)
    path = m.bundle / ("forward-" + service + "-result.json")
    if corrupt:
        e.write_private(path, b"not-json\n")
    else:
        path.unlink()
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects


def interrupt_migration(m, monkeypatch, boundary, *, reverse=False):
    """Actual helper and private I/O; only external runtime is the machine fixture."""
    write, command = e.write_private, e.command
    direction = "rollback" if reverse else "forward"
    stop = {
        "intent": "rollback-intent.json" if reverse else "intent.json",
        "state": "state.json",
        "complete-before": direction + "-complete.json",
        "complete": direction + "-complete.json",
    }.get(boundary, direction + "-" + boundary + ".json")

    def interrupted_write(path, raw, **kwargs):
        if path.name == stop and boundary == "complete-before":
            raise InterruptedError("before publication")
        write(path, raw, **kwargs)
        if path.name == stop:
            raise InterruptedError("after publication")

    def interrupted_command(argv, **kwargs):
        value = command(argv, **kwargs)
        if boundary == argv[-1] + "-image":
            raise InterruptedError("after recreate")
        return value

    with monkeypatch.context() as patch:
        patch.setattr(e, "write_private", interrupted_write)
        patch.setattr(e, "command", interrupted_command)
        with pytest.raises(InterruptedError):
            e.migration_switch(m.args, m.directory, reverse=reverse)


@pytest.mark.parametrize(
    "boundary",
    [
        "intent",
        "api-intent",
        "api-image",
        "api-result",
        "api-done",
        "worker-intent",
        "worker-image",
        "worker-result",
        "worker-done",
        "state",
        "complete-before",
        "complete",
    ],
)
def test_valid_partial_forward_rollback_preserves_pinned_audit(
    migration_machine, monkeypatch, boundary
):
    m = migration_machine
    interrupt_migration(m, monkeypatch, boundary)
    forward = {p.name: p.read_bytes() for p in m.bundle.glob("forward-*")}
    effects = list(m.effects)
    interrupt_migration(m, monkeypatch, "api-done", reverse=True)
    rollback_intent = (m.bundle / "rollback-intent.json").read_bytes()
    record = json.loads(rollback_intent)
    assert record["version"] == 2
    assert record["forward_audit_sha256"] == {name: e.sha(raw) for name, raw in forward.items()}
    for _ in range(3):
        e.migration_switch(m.args, m.directory, reverse=True)
        assert (m.bundle / "rollback-intent.json").read_bytes() == rollback_intent
        assert {p.name: p.read_bytes() for p in m.bundle.glob("forward-*")} == forward
    assert m.effects == effects + [("before", name) for _, name in effects]
    assert (m.directory / "state.json").read_bytes() == e.encoded(m.old)
    with pytest.raises(e.EgressError, match="ROLLBACK_ALREADY_STARTED"):
        e.migration_switch(m.args, m.directory)


@pytest.mark.parametrize(
    "boundary",
    [
        "api-result",
        "api-done",
        "worker-image",
        "worker-result",
        "worker-done",
        "complete-before",
        "complete",
    ],
)
def test_interrupted_rollback_results_keep_both_directions(
    migration_machine, monkeypatch, boundary
):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    forward = {p.name: p.read_bytes() for p in m.bundle.glob("forward-*")}
    interrupt_migration(m, monkeypatch, boundary, reverse=True)
    e.migration_switch(m.args, m.directory, reverse=True)
    e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == [
        ("after", "api"),
        ("after", "worker"),
        ("before", "api"),
        ("before", "worker"),
    ]
    assert {p.name: p.read_bytes() for p in m.bundle.glob("forward-*")} == forward


@pytest.mark.parametrize("phase", ["before", "interrupted", "completed"])
@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize("drift", ["missing", "corrupt", "intent", "shape", "database"])
def test_forward_result_drift_stops_rollback_at_every_phase(
    migration_machine, monkeypatch, phase, service, drift
):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    if phase == "interrupted":
        interrupt_migration(m, monkeypatch, "api-image", reverse=True)
    elif phase == "completed":
        e.migration_switch(m.args, m.directory, reverse=True)
    path = m.bundle / ("forward-" + service + "-result.json")
    record = json.loads(path.read_bytes())
    if drift == "missing":
        path.unlink()
    elif drift == "corrupt":
        e.write_private(path, b"not-json\n")
    else:
        if drift == "intent":
            record["intent_sha256"] = "0" * 64
        elif drift == "shape":
            record["runtime"]["foreign"] = True
        else:
            record["runtime"]["database_identity"] = {"database": "wrong"}
        e.write_private(path, e.encoded(record))
    effects, state = list(m.effects), (m.directory / "state.json").read_bytes()
    files = {p.name: p.read_bytes() for p in m.bundle.iterdir()}
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects and (m.directory / "state.json").read_bytes() == state
    assert {p.name: p.read_bytes() for p in m.bundle.iterdir()} == files


@pytest.mark.parametrize("direction", ["forward", "rollback"])
@pytest.mark.parametrize(
    "field", ["database_sha256", "state_sha256", "intent_sha256", "source_sha", "after", "foreign"]
)
def test_completion_requires_exact_database_state_and_intent(migration_machine, direction, field):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    if direction == "rollback":
        e.migration_switch(m.args, m.directory, reverse=True)
    path = m.bundle / (direction + "-complete.json")
    value = json.loads(path.read_bytes())
    value[field] = "0" * 64
    e.write_private(path, e.encoded(value))
    effects = list(m.effects)
    with pytest.raises(e.EgressError, match="COMPLETED_DRIFT"):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects
    if direction == "forward":
        assert not (m.bundle / "rollback-intent.json").exists()


@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize("direction", ["forward", "rollback"])
def test_done_requires_result_in_both_directions(migration_machine, service, direction):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    if direction == "rollback":
        e.migration_switch(m.args, m.directory, reverse=True)
    (m.bundle / (direction + "-" + service + "-result.json")).unlink()
    effects = list(m.effects)
    with pytest.raises(e.EgressError, match="SERVICE_RESULT_REQUIRED"):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects


@pytest.mark.parametrize("phase", ["interrupted", "completed"])
@pytest.mark.parametrize("drift", ["bytes", "remove", "unexpected", "add-completion"])
def test_rollback_intent_pins_exact_forward_inventory(migration_machine, monkeypatch, phase, drift):
    m = migration_machine
    interrupt_migration(m, monkeypatch, "complete-before")
    forward_runtime = copy.deepcopy(m.runtime)
    new = (m.directory / "state.json").read_bytes()
    if phase == "interrupted":
        interrupt_migration(m, monkeypatch, "intent", reverse=True)
    else:
        e.migration_switch(m.args, m.directory, reverse=True)
    pin = (m.bundle / "rollback-intent.json").read_bytes()
    intent_hash = json.loads(pin)["intent_sha256"]
    if drift == "bytes":
        path = m.bundle / "forward-api-result.json"
        e.write_private(path, path.read_bytes() + b"\n")  # same parsed value, different bytes
    elif drift == "remove":
        # Semantically valid shorter partial history must still violate the frozen inventory.
        for suffix in ("done", "result", "intent"):
            (m.bundle / ("forward-worker-" + suffix + ".json")).unlink()
    elif drift == "unexpected":
        e.write_private(m.bundle / "forward-foreign.json", e.encoded({}))
    else:
        e.write_private(
            m.bundle / "forward-complete.json",
            e.encoded(
                {
                    "intent_sha256": intent_hash,
                    "source_sha": m.plan["to_sha"],
                    "state_sha256": e.sha(new),
                    "after": forward_runtime,
                    "database_sha256": e.sha(e.encoded(m.database)),
                    "preservation": "PASS",
                }
            ),
        )
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects and (m.bundle / "rollback-intent.json").read_bytes() == pin


@pytest.mark.parametrize("service", ["api", "worker"])
def test_rollback_checks_forward_audit_after_each_effect(migration_machine, monkeypatch, service):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    command = e.command

    def tamper(argv, **kwargs):
        result = command(argv, **kwargs)
        if argv[-1] == service:
            path = m.bundle / "forward-api-result.json"
            e.write_private(path, path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(e, "command", tamper)
    with pytest.raises(e.EgressError, match="ROLLBACK_AUDIT_CHANGED"):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert len(m.effects) == (3 if service == "api" else 4)
    assert not (m.bundle / "rollback-complete.json").exists()


@pytest.mark.parametrize("completed", [False, True])
def test_rollback_rechecks_forward_audit_before_success(migration_machine, monkeypatch, completed):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    if completed:
        e.migration_switch(m.args, m.directory, reverse=True)

    def tamper(*_):
        path = m.bundle / "forward-worker-result.json"
        e.write_private(path, path.read_bytes() + b"\n")

    monkeypatch.setattr(e, "caller_probe", tamper)
    with pytest.raises(e.EgressError, match="ROLLBACK_AUDIT_CHANGED"):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert len(m.effects) == 4
    assert (m.bundle / "rollback-complete.json").exists() == completed


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize(
    "field", ["version", "from_tree", "to_tree", "before", "prepared_sha256", "preparation_sha256"]
)
def test_rollback_requires_exact_original_intent(migration_machine, completed, field):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    if completed:
        e.migration_switch(m.args, m.directory, reverse=True)
    path = m.bundle / "intent.json"
    value = json.loads(path.read_bytes())
    value[field] = "foreign"
    e.write_private(path, e.encoded(value))
    effects = list(m.effects)
    with pytest.raises(e.EgressError, match="INTENT_CHANGED"):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects


@pytest.mark.parametrize(
    "drift", ["legacy", "intent", "inventory", "snapshot-shape", "snapshot-id"]
)
def test_rollback_intent_schema_and_historical_binding(migration_machine, monkeypatch, drift):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    interrupt_migration(m, monkeypatch, "api-image", reverse=True)
    path = m.bundle / "rollback-intent.json"
    value = json.loads(path.read_bytes())
    if drift == "legacy":
        value = {k: value[k] for k in ("stage", "intent_sha256")}
    elif drift == "intent":
        value["intent_sha256"] = "0" * 64
    elif drift == "inventory":
        value["forward_audit_sha256"] = {}
    elif drift == "snapshot-shape":
        del value["forward_runtime"]["api"]["image"]
    else:
        value["forward_runtime"]["api"]["id"] = "foreign"
    e.write_private(path, e.encoded(value))
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects


@pytest.mark.parametrize("missing", [False, True])
def test_pending_forward_caller_can_be_rolled_back(migration_machine, monkeypatch, missing):
    m = migration_machine
    interrupt_migration(m, monkeypatch, "api-intent")
    if missing:
        del m.runtime["api"]
    else:
        m.runtime["api"]["running"] = False
        del m.runtime["api"]["database_identity"]
    e.migration_switch(m.args, m.directory, reverse=True)
    e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == [("before", "api")]


@pytest.mark.parametrize("direction", ["forward", "rollback"])
@pytest.mark.parametrize("damage", ["stage-binding", "stage-order", "result-without-intent"])
def test_audit_stage_binding_and_order_before_effects(
    migration_machine, monkeypatch, direction, damage
):
    m = migration_machine
    if direction == "rollback":
        e.migration_switch(m.args, m.directory)
        interrupt_migration(m, monkeypatch, "api-result", reverse=True)
    else:
        interrupt_migration(m, monkeypatch, "api-result")
    if damage == "stage-binding":
        path = m.bundle / (direction + "-api-intent.json")
        e.write_private(
            path, e.encoded({"stage": direction + "-api-intent", "intent_sha256": "0" * 64})
        )
    elif damage == "stage-order":
        intent = json.loads((m.bundle / "intent.json").read_bytes())
        e.migration_stage(m.bundle, direction + "-worker-intent", intent, publish=True)
    else:
        (m.bundle / (direction + "-api-intent.json")).unlink()
    effects = list(m.effects)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == effects


@pytest.mark.parametrize("service", ["api", "worker"])
def test_migration_rechecks_full_runtime_after_each_recreate(
    migration_machine, monkeypatch, service
):
    m = migration_machine
    command = e.command

    def recreate(argv, **kwargs):
        result = command(argv, **kwargs)
        if argv[-1] == service:
            m.runtime["storage"]["id"] = "foreign-recreate"
        return result

    monkeypatch.setattr(e, "command", recreate)
    with pytest.raises(e.EgressError, match="EGRESS_MIGRATION_UNRELATED_DRIFT"):
        e.migration_switch(m.args, m.directory)
    assert len(m.effects) == (1 if service == "api" else 2)
    assert not (m.bundle / "forward-complete.json").exists()


@pytest.mark.parametrize("boundary", ["intent", "api-intent", "api-image", "state", "receipt"])
@pytest.mark.parametrize("reverse", [False, True])
def test_migration_interruption_resume_never_repeats_completed_effects(
    migration_machine, monkeypatch, boundary, reverse
):
    m = migration_machine
    if reverse:
        e.migration_switch(m.args, m.directory)
    saved_write, saved_command = e.write_private, e.command
    direction = "rollback" if reverse else "forward"
    stop = {
        "intent": "rollback-intent.json" if reverse else "intent.json",
        "api-intent": direction + "-api-intent.json",
        "state": "state.json",
        "receipt": direction + "-complete.json",
    }.get(boundary)

    def write(path, raw, **kwargs):
        if path.name == stop and boundary == "receipt":
            raise InterruptedError("interrupted")
        saved_write(path, raw, **kwargs)
        if path.name == stop:
            raise InterruptedError("interrupted")

    def command(argv, **kwargs):
        result = saved_command(argv, **kwargs)
        if boundary == "api-image" and argv[-1] == "api":
            raise InterruptedError("interrupted")
        return result

    monkeypatch.setattr(e, "write_private", write)
    monkeypatch.setattr(e, "command", command)
    with pytest.raises(InterruptedError):
        e.migration_switch(m.args, m.directory, reverse=reverse)
    monkeypatch.setattr(e, "write_private", saved_write)
    monkeypatch.setattr(e, "command", saved_command)
    e.migration_switch(m.args, m.directory, reverse=reverse)
    e.migration_switch(m.args, m.directory, reverse=reverse)
    assert m.effects == (
        [("after", "api"), ("after", "worker")]
        + ([("before", "api"), ("before", "worker")] if reverse else [])
    )


@pytest.mark.parametrize(
    "drift",
    [
        "database",
        "image",
        "config",
        "mount",
        "network",
        "unrelated",
        "missing",
        "stopped",
        "state",
        "target",
    ],
)
def test_migration_drift_stops_before_any_effect(migration_machine, drift):
    m = migration_machine
    if drift == "database":
        m.database["tables"]["sealed"] = "changed"
    elif drift == "target":
        m.args.accepted_sha = "a" * 40
    elif drift == "state":
        e.write_private(m.directory / "state.json", e.encoded(dict(m.old, version=1)))
    elif drift == "image":
        m.runtime["api"]["image"] = "foreign"
    elif drift == "config":
        m.runtime["api"]["host_sha256"] = "changed"
    elif drift == "mount":
        m.runtime["api"]["mounts"] = ["foreign"]
    elif drift == "network":
        m.runtime["api"]["networks"]["default"]["Gateway"] = "foreign"
    elif drift == "unrelated":
        m.runtime["storage"]["id"] = "foreign"
    elif drift == "missing":
        del m.runtime["api"]
    else:
        m.runtime["api"]["running"] = False
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory)
    assert not m.effects and not (m.bundle / "forward-complete.json").exists()


@pytest.mark.parametrize(
    "path", ["intent.json", "images-after.json", "forward-api-done.json", "forward-complete.json"]
)
def test_completed_migration_rejects_changed_evidence(migration_machine, path):
    m = migration_machine
    e.migration_switch(m.args, m.directory)
    raw = json.loads((m.bundle / path).read_bytes())
    raw["foreign"] = True
    e.write_private(m.bundle / path, e.encoded(raw))
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory)
    assert len(m.effects) == 2


@pytest.mark.parametrize("delta", [{"version": 1}, {"source_sha": "f" * 40}, {"generation": "."}])
def test_only_exact_completed_recovery_is_a_migration_predecessor(tmp_path, monkeypatch, delta):
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    state = {
        "version": 2,
        "source_sha": e.MIGRATION_FROM,
        "generation": "recovery-v2",
        "uid": os.getuid(),
        "gid": os.getgid(),
        **delta,
    }
    e.write_private(directory / "state.json", e.encoded(state))
    monkeypatch.setattr(e, "migration_source", lambda _: "e" * 40)
    with pytest.raises(e.EgressError, match="MIGRATION_PREDECESSOR"):
        e.migration_attest(
            argparse.Namespace(from_sha=e.MIGRATION_FROM, accepted_sha="f" * 40), directory
        )


def test_owner_id_change_requires_exact_pinned_delta(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    (directory / "recovery-v1").mkdir(mode=0o700)
    original = b"ASM_TELEGRAM_EXPECTED_OWNER_ID='101' # preserve comment\r\nOTHER=unchanged\r\n"
    corrected = original.replace(b"101", b"202")
    staged = tmp_path / "telegram.env"
    e.write_private(staged, corrected)
    before = {"runtime_env": "a", "profile": "b", "staged_env": e.sha(original)}
    e.write_private(directory / "recovery-v1/inputs.json", e.encoded(before))
    monkeypatch.setattr(
        e, "input_hashes", lambda _: dict(before, staged_env=e.sha(staged.read_bytes()))
    )
    journal = {
        "previous_owner_id": "101",
        "approved_owner_id": "202",
        "staged_before_sha256": e.sha(original),
        "staged_after_sha256": e.sha(corrected),
    }
    receipts = {"asm-telegram-owner-id-correction-0b7e24ee.json": e.encoded(journal)}
    assert e.migration_inputs({"telegram_env": str(staged)}, directory, receipts)[
        "staged_env"
    ] == e.sha(corrected)
    for changed in (corrected + b"\n", corrected.replace(b"OTHER=unchanged", b"OTHER=changed")):
        e.write_private(staged, changed)
        with pytest.raises(e.EgressError, match="OWNER_DELTA"):
            e.migration_inputs({"telegram_env": str(staged)}, directory, receipts)


def test_migration_deadline_clamps_every_subprocess(monkeypatch):
    calls = []
    monkeypatch.setattr(
        e.subprocess,
        "run",
        lambda *a, **kw: calls.append(kw["timeout"]) or SimpleNamespace(returncode=0, stdout=b""),
    )
    with e.migration_budget(0.5):
        e.command(["git", "status"], timeout=40)
    assert len(calls) == 1 and 0 < calls[0] <= 0.5
