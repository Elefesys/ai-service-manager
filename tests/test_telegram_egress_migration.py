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
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from scripts import prepare_telegram_egress as e

OWNER_ACK_INTENT = "asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.intent.json"


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
    operator_image = json.loads(
        run(["docker", "image", "inspect", project + "-telegram-operator"])
    )[0]["Id"]
    operator_source = f["migration"]["operator_source"]
    operator_proof = e.migration_image(operator_image, operator_source, "development")
    if fault == "image":
        assert operator_image == f["migration"]["operator_image"]
        assert operator_source == e.HISTORICAL_OPERATOR
        assert operator_proof["source_tree"] == e.HISTORICAL_OPERATOR_TREE
        assert operator_proof["blobs_sha256"] == e.HISTORICAL_OPERATOR_MANIFEST
        try:
            e.migration_image(operator_image, e.MIGRATION_FROM, "development")
        except e.EgressError as error:
            assert str(error) == "EGRESS_COMMAND_FAILED"
        else:
            raise AssertionError("HISTORICAL_OPERATOR_MUST_FAIL_DEFAULT_INVENTORY")
    else:
        assert operator_source == e.MIGRATION_FROM
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
    # Add the historical intent and a new pinned root without rewriting any of
    # the original 28 private files (including the previous diagnostic receipt).
    ack_intent = directory / OWNER_ACK_INTENT
    e.write_private(
        ack_intent,
        e.encoded(
            dict(
                common,
                status="OWNER_APPROVED_PREFIX_INTENT",
                prior_receipts_sha256={binding.name: e.sha(binding.read_bytes())},
            )
        ),
    )
    previous_receipt = receipt
    receipt = directory / "asm-telegram-tls-budget-fixed-owner2-0b7e24ee.json"
    e.write_private(
        receipt,
        e.encoded(
            dict(
                common,
                status="DIAGNOSTIC_COMPLETE",
                preservation_pass=True,
                staged_sha256=e.sha(corrected),
                operator_image_id=operator_image,
                prior_receipts_sha256={
                    p.name: e.sha(p.read_bytes()) for p in (previous_receipt, ack_intent)
                },
            )
        ),
    )
    receipt_pin = e.sha(receipt.read_bytes())
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
                        receipt_pin,
                        *(
                            ["--predecessor-operator-sha", operator_source]
                            if fault == "image"
                            else []
                        ),
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
    added_files = {str(p): p.read_bytes() for p in (ack_intent, receipt)}
    assert added_files.items() <= saved.items()
    assert len(saved.keys() - added_files.keys()) == 28 and len(saved) == 30
    assert all(
        (bundle / plan["files"][p]["archive"]).read_bytes() == raw
        and plan["files"][p]["sha256"] == e.sha(raw)
        for p, raw in added_files.items()
    )
    receipt_dag, receipt_image = e.migration_receipts(receipt, receipt_pin, recovered, state_dir)
    assert receipt_image == operator_image and len(receipt_dag) == 6
    assert receipt_dag.items() <= saved.items()
    assert plan["predecessor_operator_sha"] == operator_source
    assert plan["image_proofs"]["telegram-operator"] == operator_proof
    assert all(
        plan["image_proofs"][n]["source_sha"] == e.MIGRATION_FROM for n in e.MIGRATION_SERVICES
    )
    assert all(
        plan["image_proofs"][n]["id"] == image for n, image in ready["before_images"].items()
    )
    assert all(
        p["source_sha"] == source and p["source_tree"] == plan["to_tree"]
        for p in ready["image_proofs"].values()
    )
    preparation_bytes = (bundle / "preparation.json").read_bytes()
    prepared_bytes = (bundle / "prepared.json").read_bytes()

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
    assert e.migration_receipts(receipt, receipt_pin, recovered, state_dir) == (
        receipt_dag,
        operator_image,
    )
    assert (state_dir / "recovery.json").read_bytes() == old_receipt
    assert (bundle / "preparation.json").read_bytes() == preparation_bytes
    assert (bundle / "prepared.json").read_bytes() == prepared_bytes
    assert e.migration_image(operator_image, operator_source, "development") == operator_proof
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
        "predecessor_operator": {
            "explicit_historical_choice": fault == "image",
            "default_inventory_rejected_historical_image": fault == "image",
            "source_sha": operator_source,
            "source_tree": operator_proof["source_tree"],
            "image_id": operator_image,
            "copied_blob_map_sha256": operator_proof["blobs_sha256"],
            "saved_proof": plan["image_proofs"]["telegram-operator"],
            "preparation_sha256": e.sha(preparation_bytes),
            "prepared_sha256": e.sha(prepared_bytes),
            "unchanged_through_resume_preflight_and_rollback_retry": True,
        },
        "owner_receipt_compat": {
            "intent_name": ack_intent.name,
            "intent_sha256": e.sha(saved[str(ack_intent)]),
            "root_name": receipt.name,
            "root_sha256": receipt_pin,
            "dag_sha256": {Path(p).name: e.sha(raw) for p, raw in receipt_dag.items()},
            "original_files_count": 28,
            "added_files": sorted(Path(p).name for p in added_files),
            "archived_and_unchanged": True,
        },
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


def schema_recovery_source(result, observe, report, candidate):
    """An expected post-commit failure is not a successful migration result."""
    detail = {
        "injection": "after_commit_before_success_exit",
        "exit_code": result.returncode,
        "marker": "M3_UPGRADE_COMMITTED_RESULT_LOST"
        if result.stdout.strip() == b"M3_UPGRADE_COMMITTED_RESULT_LOST"
        else "UNEXPECTED",
        "observed": "NOT_READ",
    }
    report["upgrade_ack_loss"] = detail
    if result.returncode != 86 or result.stdout.strip() != b"M3_UPGRADE_COMMITTED_RESULT_LOST":
        detail["result"] = "UNEXPECTED_MIGRATOR_RESULT"
        raise AssertionError("M3_EXPECTED_POST_COMMIT_FAILURE")
    detail["result"] = "CONTROLLED_FAILURE_OBSERVED"
    try:
        observation = observe()
    except Exception:
        detail["observed"] = "UNREADABLE"
        raise
    detail["observed"] = observation
    if observation.get("revision") != "0008":
        raise AssertionError("M3_RECOVERY_REVISION_UNCONFIRMED")
    detail["recovery_source"] = candidate
    return candidate


def run_schema_phase(request):
    """New disposable LOCAL volume, exact H/I images, drained schema cutover."""
    import tempfile

    historical = "754f1c883e5a94a7fc9e729af2605424f949ba33"
    candidate = e.command(["git", "rev-parse", "HEAD"]).decode().strip()
    assert request == {"historical": historical, "candidate": candidate}
    assert os.getuid() != 0 and os.environ.get("GITHUB_ACTIONS") == "true"
    e.source_check(candidate)
    assert not e.command(["docker", "ps", "-aq"]).strip()
    assert not e.command(["docker", "volume", "ls", "-q"]).strip()
    project = "asm-m3-schema-phase"
    report = {"coordinator": candidate, "historical": historical, "images": {}, "checks": []}
    pins = dict(
        line.split("=", 1)
        for line in (e.ROOT / "infra/images.lock.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    with tempfile.TemporaryDirectory(prefix="asm-m3-schema-") as temporary:
        directory = Path(temporary)
        sources, images = {}, {}
        # Only exact tracked archives enter build contexts. The historical-only
        # production migration_build_images helper is deliberately not called for I.
        with e.migration_budget(600):
            for source in (historical, candidate):
                archive = directory / source
                archive.mkdir()
                e.migration_build_context(source, archive)
                sources[source] = archive
                images[source] = {}
                for kind in ("runtime", "development"):
                    tag = "asm-m3-schema-" + kind + ":" + source
                    reuse = "asm-connect5-" + kind + ":" + source
                    existing = (
                        e.command(["docker", "image", "ls", "-q", "--no-trunc", reuse])
                        .decode()
                        .strip()
                    )
                    if existing:
                        e.migration_image(existing, source, kind)
                        e.command(["docker", "tag", existing, tag])
                    else:
                        e.command(
                            [
                                "docker",
                                "build",
                                "--pull",
                                "--network=default",
                                "--target",
                                kind,
                                "--build-arg",
                                "PYTHON_IMAGE=" + pins["PYTHON_IMAGE"],
                                "--build-arg",
                                "UV_IMAGE=" + pins["UV_IMAGE"],
                                "-f",
                                str(archive / "infra/Dockerfile.backend"),
                                "-t",
                                tag,
                                str(archive),
                            ],
                            timeout=480,
                        )
                    image_id = json.loads(e.command(["docker", "image", "inspect", tag]))[0]["Id"]
                    images[source][kind] = image_id
                    report["images"][source + ":" + kind] = e.migration_image(
                        image_id, source, kind
                    )
        # init_local emits only a fixed diagnostic, never credentials. All private
        # runtime files are outside both source archives and the repository.
        subprocess.run(
            [sys.executable, str(e.ROOT / "scripts/init_local.py")],
            cwd=directory,
            check=True,
            timeout=30,
        )
        compose = [
            "docker",
            "compose",
            "--project-directory",
            str(sources[candidate]),
            "--project-name",
            project,
            "--env-file",
            str(e.ROOT / "infra/images.lock.env"),
            "--env-file",
            str(directory / ".env"),
            "-f",
            str(sources[candidate] / "compose.yaml"),
            "--profile",
            "telegram-operator",
        ]
        model = json.loads(e.command([*compose, "config", "--format", "json"]))
        variables = dict(model["services"]["api"]["environment"])
        variables.update(model["services"]["migrate"]["environment"])
        assert variables["ASM_TELEGRAM_ENABLED"] == "false" and variables["TG_BOT_TOKEN"] == ""
        envfile = directory / "controller.env"
        e.write_private(
            envfile, "".join(k + "=" + str(v) + "\n" for k, v in sorted(variables.items())).encode()
        )
        state = directory / "state"
        state.mkdir(mode=0o700)
        prefix = [
            "docker",
            "run",
            "--rm",
            "--network",
            project + "_default",
            "--env-file",
            str(envfile),
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,source={state},target=/state",
        ]

        def controller(action):
            output = e.command(
                [
                    *prefix,
                    images[candidate]["development"],
                    "python",
                    "tests/test_m3_1_migrations.py",
                    "--schema-phase",
                    action,
                    "/state/receipt.json",
                ],
                timeout=120,
            )
            assert output.decode().strip() == "M3_SCHEMA_" + action.upper() + "_PASS"
            report["checks"].append(action)

        def migrate(source, direction, revision):
            e.command(
                [*prefix, images[source]["development"], "alembic", direction, revision], timeout=30
            )

        def probe(source, expected):
            code = """import asyncio
from asm.foundation import RuntimeDatabase,Settings
async def main():
 d=RuntimeDatabase(Settings())
 try:
  try: await d.check()
  except Exception:
   assert not EXPECTED
  else: assert EXPECTED
 finally: await d.close()
asyncio.run(main())
""".replace("EXPECTED", repr(expected))
            e.command([*prefix, images[source]["runtime"], "python", "-c", code], timeout=30)

        def callers(source):
            e.command(["docker", "tag", images[source]["runtime"], "asm-backend:local"])
            e.command(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-deps",
                    "--pull",
                    "never",
                    "--force-recreate",
                    "--wait",
                    "api",
                    "worker",
                    "scheduler",
                ],
                timeout=120,
            )
            result = {}
            for service in ("api", "worker", "scheduler"):
                ident = e.command([*compose, "ps", "-q", service]).decode().strip()
                info = json.loads(e.command(["docker", "inspect", ident]))[0]
                assert info["Image"] == images[source]["runtime"] and info["State"]["Running"]
                result[service] = {"id": ident, "image": info["Image"], "source": source}
            return result

        def drain():
            e.command(
                [*compose, "stop", "--timeout", "10", "api", "worker", "scheduler"], timeout=60
            )
            for service in ("api", "worker", "scheduler"):
                ident = e.command([*compose, "ps", "-aq", service]).decode().strip()
                assert not json.loads(e.command(["docker", "inspect", ident]))[0]["State"][
                    "Running"
                ]

        try:
            e.command([*compose, "up", "-d", "--wait", "postgres", "storage"], timeout=120)
            e.command([*compose, "run", "--rm", "--no-deps", "-T", "storage-init"], timeout=120)
            migrate(historical, "upgrade", "0007")
            report["baseline_callers"] = callers(historical)
            probe(historical, True)
            probe(candidate, False)
            drain()
            controller("seed")  # migration identity only, all historical pools terminate here
            # Reject the actual changed helper's direct migration commands before
            # any source/image switch or migration journal on this candidate.
            guard = directory / "guard"
            guard.mkdir(mode=0o700)
            e.write_private(guard / "operation.lock", b"")
            before = {p.name: p.read_bytes() for p in guard.iterdir()}
            for action in ("migration-attest", "migration-prepare"):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(e.ROOT / "scripts/prepare_telegram_egress.py"),
                        action,
                        "--state-dir",
                        str(guard),
                        "--accepted-sha",
                        candidate,
                        "--from-sha",
                        e.MIGRATION_FROM,
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=30,
                )
                assert (
                    result.returncode == 1
                    and b"EGRESS_MIGRATION_HISTORICAL_SCHEMA_ONLY" in result.stdout
                )
                assert {p.name: p.read_bytes() for p in guard.iterdir()} == before
            report["checks"].append("candidate_direct_cli_pairing_refusal")
            migrate(candidate, "upgrade", "0008")
            controller("check8")  # independent committed revision read after migrator exits
            probe(candidate, True)
            probe(historical, False)
            # Separate empty-M3 case: preserve all seeded M2 rows, restore exact H.
            migrate(candidate, "downgrade", "0007")
            controller("check7")
            probe(historical, True)
            # A separate migrator really commits 0008, then exits unsuccessfully.
            # Observe its failure; NEVER infer the revision from that exit alone.
            lost = subprocess.run(
                [
                    *prefix,
                    images[candidate]["development"],
                    "python",
                    "tests/test_m3_1_migrations.py",
                    "--schema-phase",
                    "upgrade-lost-result",
                    "/state/receipt.json",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
            )

            def observe_revision():
                return json.loads(
                    e.command(
                        [
                            *prefix,
                            images[candidate]["development"],
                            "python",
                            "tests/test_m3_1_migrations.py",
                            "--schema-phase",
                            "observe",
                            "/state/receipt.json",
                        ],
                        timeout=30,
                    )
                )

            recovery_source = schema_recovery_source(lost, observe_revision, report, candidate)
            controller("check8")  # projection/private S3/pending/UNKNOWN still exact
            probe(historical, False)  # committed0008 explicitly rejects H
            probe(recovery_source, True)
            report["upgrade_ack_loss"]["historical_readiness"] = "REJECTED"
            report["upgrade_ack_loss"]["candidate_readiness"] = "PASS"
            # Exercise I runtime/worker on the correctly paired schema before
            # permanent callers start, so duplicate-first admission is deterministic.
            controller("fresh")
            report["cutover_callers"] = callers(recovery_source)
            report["upgrade_ack_loss"]["forward_callers"] = report["cutover_callers"]
            drain()
            controller("refuse")
            report["restarted_callers"] = callers(recovery_source)
            report["upgrade_ack_loss"]["restarted_callers"] = report["restarted_callers"]
            probe(recovery_source, True)
            drain()
            controller("refuse")
            report["database"] = json.loads((state / "receipt.json").read_text())
            assert report["database"]["populated_refusal"] == "PASS"
            # No raw signed URL or fixture content is published.
            report["database"]["object"].pop("key")
        except BaseException as error:
            report["failure"] = type(error).__name__
            raise
        finally:
            # Record the observed failure/revision/recovery before destroying
            # disposable evidence, including a refusal/unreadable revision.
            reports = e.ROOT / "reports"
            reports.mkdir(exist_ok=True)
            (reports / "m3-schema-phase.json").write_text(json.dumps(report, indent=2) + "\n")
            e.command(
                [*compose, "down", "--volumes", "--remove-orphans", "--timeout", "2"], timeout=90
            )
    e.source_check(candidate)
    print("TELEGRAM_EGRESS_SCHEMA_PHASE_PASS", flush=True)


CONTROL_T = "ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad"
CONTROL_PHASE = "CONTROL_SCHEMA_0008_0009"
GUARDS_C = "c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5"
GUARDS_PHASE = "GUARDS_SCHEMA_0009_0010"
SCHEMA_OWNER_LABEL = "io.asm.schema-owner"
RETAINED_MODULE_BLOB = "571bc4e48fc8c7de8e89f0cfe01c06949d7e84c1"
RETAINED_HELPER_BLOB = "f6cda8841f50eab0347a365079af6ed76632d988"


def retained_exception_observer(config):
    """Observe the exact frozen frame; never replace its code/helper/globals.

    This stdlib-only function is also embedded verbatim in the private python3
    launcher. It runs in the frozen process, before its finally can mask an
    exception. No traceback/argv/payload is serialized.
    """
    import hashlib
    import json
    import os
    import re
    import stat
    import tempfile
    import time
    from pathlib import Path

    root = Path(config["owner_directory"])
    module = config["module"]
    active = False
    finished = False
    journal_ok = False
    records = []
    errors = []
    overflow = False
    binding = {
        key: config[key] for key in ("source", "phase", "token", "module_blob", "helper_blob")
    }
    binding["version"] = 1
    entered = None

    def encoded(value):
        return (json.dumps(value, sort_keys=True) + "\n").encode()

    def diagnostic(name, step):
        nonlocal overflow
        if len(errors) < 16:
            errors.append({"file": name, "step": step, "reason": "CONTROL_RETAINED_JOURNAL_IO"})
        else:
            overflow = True

    def save(name, raw):
        temporary = None
        step = "deadline"
        try:
            end = config["deadline"]
            budget = root / "cleanup-budget.json"
            if budget.exists():
                end = min(end, json.loads(budget.read_text())["deadline"])
            if time.monotonic() >= end:
                raise OSError("deadline")
            step = "write"
            fd, temporary = tempfile.mkstemp(dir=root, prefix=".observer-")
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                step = "fsync_file"
                os.fsync(stream.fileno())
            step = "publish"
            os.replace(temporary, root / name)
            step = "fsync_directory"
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return True
        except (OSError, ValueError, KeyError, TypeError):
            diagnostic(name, step)
            return False
        finally:
            if temporary is not None:
                try:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                except OSError:
                    diagnostic(name, "unlink")

    def slot(name, value):
        raw = encoded(value)
        return {
            "name": name,
            "raw": raw,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "attempts": 0,
            "durable": False,
        }

    def flush(final=False):
        # Retry only these immutable bytes, never the latest exception. Every
        # slot has at most three attempts, under the original600/cleanup90.
        for item in ([entered] if entered is not None else []) + records:
            while not item["durable"] and item["attempts"] < 3:
                item["attempts"] += 1
                item["durable"] = save(item["name"], item["raw"])
                if not final:
                    break
        ready = (
            entered is not None
            and entered["durable"]
            and all(item["durable"] for item in records)
            and not overflow
        )
        for _ in range(3 if final else 1):
            health = {
                "binding": binding,
                "completed": final,
                "entered_sha256": entered["sha256"] if entered else None,
                "event_hashes": [item["sha256"] for item in records],
                "published": [item["durable"] for item in records],
                "attempts": [item["attempts"] for item in records],
                "errors": list(errors),
                "overflow": overflow,
                "state": "CONFIRMED"
                if ready and records
                else "NO_FAILURE"
                if ready
                else "UNCONFIRMED",
            }
            if save("trace-health.json", encoded(health)):
                return ready and final
        return False

    def finish():
        nonlocal finished, journal_ok
        if not finished:
            finished = True
            journal_ok = flush(final=True) if active else False
        return journal_ok

    def observe(frame, event, arg):
        nonlocal active, entered, overflow
        if frame.f_code.co_filename != module or frame.f_code.co_name != "run_schema_phase":
            return None
        if event == "call":
            raw = Path(module).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            assert blob == config["module_blob"], "CONTROL_RETAINED_FUNCTION_SOURCE"
            info = root.stat()
            assert info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
            assert not active, "CONTROL_RETAINED_FUNCTION_REENTRY"
            active = True
            entered = slot(
                "trace-entered.json",
                {
                    "source": config["source"],
                    "module_blob": blob,
                    "binding": binding,
                    "at": time.monotonic(),
                    "pid": os.getpid(),
                },
            )
            flush()
        if event == "exception" and active:
            # This sequence/first-event identity is process memory, independent
            # of publication. No exists() or later collect can choose first.
            sequence = len(records) + 1
            if sequence > 32:
                overflow = True
                return observe
            error = arg[1]
            kind = re.sub(r"[^A-Za-z0-9_]", "_", type(error).__name__)[:80]
            reason = str(error)
            if not re.fullmatch(r"(?:CONTROL|EGRESS|FROZEN|SCHEMA)_[A-Z0-9_]{1,100}", reason):
                reason = (
                    "CONTROL_COMMAND_TIMEOUT"
                    if kind == "TimeoutExpired"
                    else "CONTROL_" + kind.upper()[:80]
                )
            operation = {}
            try:
                if (root / "retained-operation.json").exists():
                    operation = json.loads((root / "retained-operation.json").read_text())
                    assert (
                        operation["source"] == binding["source"]
                        and operation["token"] == binding["token"]
                    )
            except (OSError, ValueError, KeyError, TypeError, AssertionError):
                # A damaged operation journal does not replace the original
                # exception; its unproved stage must fail the closing gate.
                operation = {"stage": "retained_operation_unreadable"}
                diagnostic("retained-operation.json", "read")
                overflow = True
            stage = operation.get("stage", "retained_function")
            # In this pinned function, reports is assigned only in finally,
            # before mkdir/write_text and before the wrapped down command.
            # Attribute a report failure to that phase, not its last CLI call.
            if "reports" in frame.f_locals and stage != "retained_down":
                stage = "retained_report"
            detail = {
                "type": kind,
                "reason": reason,
                "stage": stage,
                "source": config["source"],
                "at": time.monotonic(),
            }
            if (
                operation.get("result", {}).get("reason") == "CONTROL_COMMAND_EXIT"
                and kind == "EgressError"
            ):
                detail.update(operation["result"], observed_type=kind)
            records.append(
                slot(
                    "trace-primary.json"
                    if sequence == 1
                    else f"trace-secondary-{sequence:04d}.json",
                    {"binding": binding, "sequence": sequence, "detail": detail},
                )
            )
            flush()
        if event == "return" and active:
            finish()
        return observe

    observe.finish = finish
    return observe


def write_retained_launcher(directory):
    """One launcher for actual frozen shells and the separate-process unit seam."""
    import inspect

    launcher = (
        "#!"
        + sys.executable
        + "\nimport json,sys,os\n"
        + inspect.getsource(retained_exception_observer)
        + "\nfrom pathlib import Path\n"
        + "config=json.loads(Path("
        + repr(str(directory / "retained.json"))
        + ").read_text())\n"
        + "assert sys.argv[1:3]==['-','--schema-upgrade'], 'CONTROL_RETAINED_LAUNCHER'\n"
        + "sys.argv=sys.argv[1:]\nsys.path[0]=os.getcwd()\n"
        + "observer=retained_exception_observer(config)\nsys.settrace(observer)\n"
        + "try: exec(compile(sys.stdin.buffer.read(),'<stdin>','exec'),{'__name__':'__main__'})\n"
        + "finally:\n sys.settrace(None)\n"
        # Independent process outcome closes the last-fsync ACK gap: a visible
        # health file alone never proves its final directory fsync succeeded.
        + " if not observer.finish(): raise SystemExit(78) from None\n"
    )
    path = directory / "python3"
    path.write_text(launcher)
    path.chmod(0o700)
    return path


def enable_retained_checkpoint(owner, checkout, deadline, fault=None):
    """Private C launcher and bind backing; frozen shell/function/images unchanged."""
    assert owner.admitted and owner.source == CONTROL_T, "CONTROL_RETAINED_OWNER"
    assert fault in (None, "timeout", "export"), "CONTROL_RETAINED_FAULT"
    checkout = Path(checkout)
    for name, blob in (
        ("tests/test_telegram_egress_migration.py", RETAINED_MODULE_BLOB),
        ("scripts/prepare_telegram_egress.py", RETAINED_HELPER_BLOB),
    ):
        raw = (checkout / name).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob, (
            "CONTROL_RETAINED_SOURCE"
        )
    config = {
        "token": owner.token,
        "source": CONTROL_T,
        "phase": owner.phase,
        "owner_directory": str(owner.directory),
        "module": str(checkout / "tests/test_telegram_egress_migration.py"),
        "module_blob": RETAINED_MODULE_BLOB,
        "helper_blob": RETAINED_HELPER_BLOB,
        "deadline": deadline,
        "fault": fault,
    }
    e.write_private(owner.directory / "retained.json", e.encoded(config))
    write_retained_launcher(owner.directory)


class RetainedCheckpoint:
    """An owned, durable bind source outside frozen TemporaryDirectory teardown."""

    def __init__(self, directory):
        self.directory = e.checked_path(directory, directory=True)
        self.config = e.strict_json(e.private_bytes(self.directory / "retained.json"))
        self.owner = e.strict_json(e.private_bytes(self.directory / "ownership.json"))
        assert (
            self.config["token"] == self.owner["token"]
            and self.config["source"] == self.owner["source"] == CONTROL_T
            and self.config["phase"] == self.owner["phase"]
            and self.config["owner_directory"] == str(self.directory)
        ), "CONTROL_RETAINED_BINDING"
        self.root = self.directory / "checkpoint"
        self.state = self.root / "state"

    @staticmethod
    def identity(path):
        path = e.checked_path(path, directory=True)
        info = path.stat()
        return {
            "device": info.st_dev,
            "inode": info.st_ino,
            "uid": info.st_uid,
            "mode": stat.S_IMODE(info.st_mode),
            "path_sha256": e.sha(str(path).encode()),
        }

    def bound(self):
        assert time.monotonic() < self.config["deadline"], "CONTROL_RETAINED_PREPARE_DEADLINE"
        budget = self.directory / "cleanup-budget.json"
        if budget.exists():
            assert time.monotonic() < e.strict_json(e.private_bytes(budget))["deadline"], (
                "CONTROL_CLEANUP_DEADLINE"
            )

    def event(self, name, **details):
        self.bound()
        events = self.directory / "retained-events"
        events.mkdir(mode=0o700, exist_ok=True)
        value = {
            "event": name,
            "at": time.monotonic(),
            "source": CONTROL_T,
            "token": self.owner["token"],
            **details,
        }
        e.write_private(events / (uuid4().hex + ".json"), e.encoded(value))
        return value

    def files(self):
        self.bound()
        result = {}
        if not self.state.exists():
            return result
        assert len(list(self.state.iterdir())) <= 16, "CONTROL_RETAINED_STATE_LIMIT"
        for path in sorted(self.state.iterdir()):
            assert re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", path.name), "CONTROL_RETAINED_FILE_NAME"
            before = path.stat()
            raw = e.private_bytes(path)
            after = path.stat()
            assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ), "CONTROL_RETAINED_FILE_CHANGED"
            result[path.name] = {
                "bytes": len(raw),
                "sha256": e.sha(raw),
                "mode": stat.S_IMODE(after.st_mode),
            }
        return result

    def bind(self, args):
        mounts = [
            i + 1
            for i, arg in enumerate(args[:-1])
            if arg == "--mount" and "target=/state" in args[i + 1].split(",")
        ]
        if not mounts:
            return args, None
        assert len(mounts) == 1 and "--env-file" in args and "--network" in args, (
            "CONTROL_RETAINED_MOUNT"
        )
        assert args[args.index("--network") + 1] == self.owner["project"] + "_default", (
            "CONTROL_RETAINED_NETWORK"
        )
        index = mounts[0]
        pairs = args[index].split(",")
        mount = dict(part.split("=", 1) for part in pairs)
        assert (
            len(pairs) == len(mount) == 3
            and mount["type"] == "bind"
            and mount["target"] == "/state"
        ), "CONTROL_RETAINED_MOUNT"
        original = e.checked_path(mount["source"], directory=True)
        envfile = e.checked_path(args[args.index("--env-file") + 1])
        assert original.name == "state" and envfile == original.parent / "controller.env", (
            "CONTROL_RETAINED_STATE_RELATION"
        )
        e.checked_path(original.parent, directory=True)
        binding_path = self.directory / "retained-binding.json"
        if not binding_path.exists():
            self.root.mkdir(mode=0o700)
            self.state.mkdir(mode=0o700)
            assert not list(original.iterdir()), "CONTROL_RETAINED_INITIAL_STATE"
            for name in ("controller.env", ".env"):
                e.write_private(self.root / name, e.private_bytes(original.parent / name))
            binding = {
                "token": self.owner["token"],
                "source": CONTROL_T,
                "original": str(original),
                "original_identity": self.identity(original),
                "state_identity": self.identity(self.state),
                "controller_env_sha256": e.sha(e.private_bytes(envfile)),
            }
            e.write_private(binding_path, e.encoded(binding))
            self.event(
                "BOUND_BEFORE_CREATE",
                original_identity=binding["original_identity"],
                state_identity=binding["state_identity"],
            )
        binding = e.strict_json(e.private_bytes(binding_path))
        assert binding["original_identity"] == self.identity(original) and binding[
            "state_identity"
        ] == self.identity(self.state), "CONTROL_RETAINED_STATE_IDENTITY"
        assert binding["controller_env_sha256"] == e.sha(e.private_bytes(envfile)), (
            "CONTROL_RETAINED_ENV_CHANGED"
        )
        args = list(args)
        args[index] = f"type=bind,source={self.state},target=/state"
        stage = (
            "controller_" + args[args.index("--schema-phase") + 1]
            if "--schema-phase" in args
            else "migrate"
            if "alembic" in args
            else "probe"
        )
        assert re.fullmatch(r"(?:controller_[a-z0-9-]{1,40}|migrate|probe)", stage), (
            "CONTROL_RETAINED_STAGE"
        )
        operation = {
            "source": CONTROL_T,
            "token": self.owner["token"],
            "stage": stage,
            "at": time.monotonic(),
        }
        e.write_private(self.directory / "retained-operation.json", e.encoded(operation))
        return args, binding["state_identity"]

    def mirror(self):
        binding = e.strict_json(e.private_bytes(self.directory / "retained-binding.json"))
        original = Path(binding["original"])
        assert self.identity(original) == binding["original_identity"], (
            "CONTROL_RETAINED_MIRROR_IDENTITY"
        )
        for name, proof in self.files().items():
            raw = e.private_bytes(self.state / name)
            assert e.sha(raw) == proof["sha256"], "CONTROL_RETAINED_FILE_CHANGED"
            e.write_private(original / name, raw)
            assert e.sha(e.private_bytes(original / name)) == proof["sha256"], (
                "CONTROL_RETAINED_MIRROR_CHANGED"
            )

    def capture(self):
        if not (self.directory / "retained-binding.json").exists():
            return None
        self.bound()
        files = self.files()
        snapshot = self.root / ("snapshot-" + uuid4().hex)
        snapshot.mkdir(mode=0o700)
        for name, proof in files.items():
            raw = e.private_bytes(self.state / name)
            assert e.sha(raw) == proof["sha256"], "CONTROL_RETAINED_FILE_CHANGED"
            e.write_private(snapshot / name, raw)
            assert e.sha(e.private_bytes(snapshot / name)) == proof["sha256"], (
                "CONTROL_RETAINED_CAPTURE_CHANGED"
            )
        assert self.files() == files, "CONTROL_RETAINED_CAPTURE_CHANGED"
        # write_private fsyncs each snapshot file and its immediate directory.
        # Persist the snapshot directory entry too, before publishing its name.
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        capture = {
            "state": "CAPTURED",
            "source": CONTROL_T,
            "token": self.owner["token"],
            "snapshot": snapshot.name,
            "state_identity": self.identity(self.state),
            "files": files,
            "at": time.monotonic(),
        }
        e.write_private(self.directory / "retained-capture.json", e.encoded(capture))
        self.event("CHECKPOINT_CAPTURED", files=files, snapshot=snapshot.name)
        if (
            self.config["fault"] == "export"
            and not (self.directory / "export-fault-used.json").exists()
        ):
            e.write_private(
                self.directory / "export-fault-used.json", e.encoded({"at": time.monotonic()})
            )
            raise e.EgressError("CONTROL_RETAINED_EXPORT_FAILED")
        e.write_private(self.directory / "retained-export.json", e.encoded(capture))
        self.event("SAFE_EXPORT_SAVED", snapshot=snapshot.name)
        return capture

    def daemon(self, args, timeout=40):
        self.bound()
        limit = self.config["deadline"]
        budget = self.directory / "cleanup-budget.json"
        if budget.exists():
            limit = min(limit, e.strict_json(e.private_bytes(budget))["deadline"])
        return e.command(
            [self.owner["docker"], *args], timeout=min(timeout, limit - time.monotonic())
        )

    def connections(self, db, timeout=5):
        return int(
            self.daemon(
                [
                    "exec",
                    db,
                    "psql",
                    "-U",
                    "asm_admin",
                    "-d",
                    "asm_local",
                    "-Atqc",
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name='retained_"
                    + self.owner["token"]
                    + "'",
                ],
                timeout,
            )
        )

    def foreign(self, image):
        ids = {}
        path = self.directory / "foreign.json"
        # Save each exact identity before the next create; partial setup also
        # remains recoverable without daemon-wide adoption or prune.
        for kind in ("volume", "network", "container"):
            if kind == "container":
                args = [
                    "create",
                    "--network",
                    ids["network"],
                    "--mount",
                    "type=volume,source=" + ids["volume"] + ",target=/sentinel",
                    "--label",
                    "io.asm.foreign-sentinel=" + self.owner["token"],
                    image,
                    "python",
                    "-c",
                    "pass",
                ]
            else:
                args = [kind, "create", "asm-foreign-" + self.owner["token"]]
            ids[kind] = self.daemon(args).decode().strip()
            e.write_private(path, e.encoded(ids))
        proof = self.foreign_proof()
        e.write_private(self.directory / "foreign-before.json", e.encoded(proof))

    def foreign_proof(self):
        ids = e.strict_json(e.private_bytes(self.directory / "foreign.json"))
        return {
            kind: e.sha(self.daemon([*command, ids[kind]]))
            for kind, command in {
                "container": ["inspect"],
                "volume": ["volume", "inspect"],
                "network": ["network", "inspect"],
            }.items()
        }

    def remove_foreign_fixture(self):
        ids = e.strict_json(e.private_bytes(self.directory / "foreign.json"))
        assert self.foreign_proof() == e.strict_json(
            e.private_bytes(self.directory / "foreign-before.json")
        ), "CONTROL_FOREIGN_CHANGED"
        for kind, command in (
            ("container", ["rm", "-v"]),
            ("volume", ["volume", "rm"]),
            ("network", ["network", "rm"]),
        ):
            self.daemon([*command, ids[kind]])

    def observe_live(self):
        """Before killing the controller, prove its real bind/image/PG identity."""
        ids = (
            self.daemon(
                [
                    "ps",
                    "-aq",
                    "--no-trunc",
                    "--filter",
                    "label=" + SCHEMA_OWNER_LABEL + "=" + self.owner["token"],
                ]
            )
            .decode()
            .split()
        )
        infos = json.loads(self.daemon(["inspect", *ids]))
        db = [
            i
            for i in infos
            if (i["Config"].get("Labels") or {}).get("com.docker.compose.service") == "postgres"
        ]
        controllers = [
            i
            for i in infos
            if i["State"]["Running"]
            and any(
                m["Type"] == "bind"
                and m["Destination"] == "/state"
                and m["Source"] == str(self.state)
                for m in i.get("Mounts", [])
            )
        ]
        assert len(db) == len(controllers) == 1, "CONTROL_RETAINED_DAEMON_REQUIRED"
        info = controllers[0]
        intent = e.strict_json(
            e.private_bytes(self.directory / ("run-" + info["Name"].lstrip("/") + ".json"))
        )
        cid = (self.directory / ("run-" + intent["name"] + ".cid")).read_text().strip()
        assert cid == info["Id"] and intent["retained_bind"] == self.identity(self.state), (
            "CONTROL_RETAINED_DAEMON_IDENTITY"
        )
        count = self.connections(db[0]["Id"])
        assert count == 1, "CONTROL_RETAINED_CONNECTION_REQUIRED"
        marker = e.strict_json(e.private_bytes(self.state / "connected.json"))
        proof = {
            "controller_cid": cid,
            "database_cid": db[0]["Id"],
            "image": info["Image"],
            "phase": self.owner["phase"],
            "source": CONTROL_T,
            "helper_blob": RETAINED_HELPER_BLOB,
            "module_blob": RETAINED_MODULE_BLOB,
            "state_identity": self.identity(self.state),
            "backend_pid": marker["backend_pid"],
            "connections_before_cleanup": count,
            "controller_running": True,
            "at": time.monotonic(),
        }
        e.write_private(self.directory / "retained-live.json", e.encoded(proof))
        self.event("LIVE_CONTROLLER_PROVED", **proof)
        return proof

    def disconnected(self, deadline):
        proof = e.strict_json(e.private_bytes(self.directory / "retained-live.json"))
        previous = self.directory / "down-cleanup.json"
        if previous.exists():
            down = e.strict_json(e.private_bytes(previous))
            if (
                down.get("connections_after_controller_stop") == 0
                and down.get("owned_remaining") == []
            ):
                assert (
                    proof["database_cid"]
                    not in self.daemon(["ps", "-aq", "--no-trunc"]).decode().split()
                ), "CONTROL_DATABASE_REAPPEARED"
                return 0
        end = min(deadline, time.monotonic() + 3)
        while True:
            assert time.monotonic() < end, "CONTROL_CONNECTION_REMAINS"
            count = self.connections(proof["database_cid"], min(5, end - time.monotonic()))
            if count == 0:
                self.event(
                    "PG_ZERO_BEFORE_DB_STOP", database_cid=proof["database_cid"], connections=0
                )
                return 0
            time.sleep(0.02)

    def host_children(self):
        results = []
        for path in self.directory.glob("host-child-*.json"):
            detail = e.strict_json(e.private_bytes(path))
            try:
                fields = Path(f"/proc/{detail['pid']}/stat").read_text().rpartition(")")[2].split()
                live = fields[0] != "Z" and int(fields[19]) == detail["start_ticks"]
            except FileNotFoundError:
                live = False
            assert not live, "CONTROL_HOST_CLI_REMAINS"
            results.append({**detail, "live": live})
        assert results, "CONTROL_HOST_CHILD_PROOF_REQUIRED"
        return results

    def seed_fault(self, args):
        assert args[-5:] == [
            "python",
            "tests/test_m3_1_migrations.py",
            "--schema-phase",
            "seed",
            "/state/receipt.json",
        ], "CONTROL_RETAINED_SEED_COMMAND"
        # Execute the exact T controller first. Only after its real seed/receipt
        # completes does this disposable test process hold a PostgreSQL session.
        code = (
            "import os,sys,runpy,signal,time,json,hashlib,psycopg\nfrom pathlib import Path\n"
            "p=Path('tests/test_m3_1_migrations.py');raw=p.read_bytes()\n"
            "assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\\0'+raw).hexdigest()=='21592a4dc2ad737f4d7a1f201125ebe1f18bcbe5'\n"
            "sys.argv=[str(p),'--schema-phase','seed','/state/receipt.json']\n"
            "sys.path[0]=str(p.parent.resolve())\n"
            "try: runpy.run_path(str(p),run_name='__main__')\n"
            "except SystemExit as done: assert done.code in (None,0)\n"
            "receipt=Path('/state/receipt.json');assert receipt.is_file()\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            "c=psycopg.connect(os.environ['ASM_MIGRATION_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1),connect_timeout=3,application_name='retained_"
            + self.owner["token"]
            + "')\n"
            "pid=c.execute('select pg_backend_pid()').fetchone()[0]\n"
            "p=Path('/state/connected.json');p.write_text(json.dumps({'backend_pid':pid}));p.chmod(0o600)\n"
            "while True: time.sleep(1)\n"
        )
        return [*args[:-5], "python", "-c", code]

    def run_bound(self, args):
        fault = (
            self.config["fault"]
            and "--schema-phase" in args
            and args[args.index("--schema-phase") + 1] == "seed"
        )
        if fault:
            self.foreign(args[-6])
            args = self.seed_fault(args)

        def die_with_wrapper():
            # subprocess.run(timeout) in unchanged T kills this wrapper. A
            # direct Docker CLI must not keep its stdout pipe/host PID alive.
            import ctypes

            parent = os.getppid()
            assert ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) == 0
            if os.getppid() != parent:
                os.kill(os.getpid(), signal.SIGKILL)

        child = subprocess.Popen(
            [self.owner["docker"], *args], stdin=subprocess.DEVNULL, preexec_fn=die_with_wrapper
        )
        fields = Path(f"/proc/{child.pid}/stat").read_text().rpartition(")")[2].split()
        e.write_private(
            self.directory / ("host-child-" + uuid4().hex + ".json"),
            e.encoded({"pid": child.pid, "start_ticks": int(fields[19])}),
        )
        try:
            if fault and self.config["fault"] == "export":
                end = min(self.config["deadline"], time.monotonic() + 120)
                while not (self.state / "connected.json").exists():
                    assert child.poll() is None, "CONTROL_RETAINED_SEED_FAILED"
                    assert time.monotonic() < end, "CONTROL_RETAINED_SEED_DEADLINE"
                    time.sleep(0.02)
                self.observe_live()
                child.kill()
                child.wait(timeout=5)
                result = 7  # Exact controlled host failure, not the controller exit.
            else:
                result = child.wait(timeout=max(0.001, self.config["deadline"] - time.monotonic()))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
        operation = e.strict_json(e.private_bytes(self.directory / "retained-operation.json"))
        operation["result"] = (
            {"type": "CalledProcessError", "reason": "CONTROL_COMMAND_EXIT", "exit_code": result}
            if result
            else {"reason": "PASS"}
        )
        e.write_private(self.directory / "retained-operation.json", e.encoded(operation))
        if result == 0:
            self.mirror()
        return result

    def collect_journal(self, report):
        """Prove sequence1 across IPC or STOP; later events cannot repair it."""
        binding = {
            key: self.config[key]
            for key in ("source", "phase", "token", "module_blob", "helper_blob")
        }
        binding["version"] = 1
        diagnostics = []
        details = []
        health = {}
        journal_errors = []
        primary = None
        stop = self.directory / "trace-collection-stop.json"

        def secondary(detail):
            if detail not in report.setdefault("secondary_failures", []):
                report["secondary_failures"].append(detail)

        def problem(error):
            diagnostics.append({"stage": "retained_journal", **schema_failure(error)})

        try:
            if (
                report.get("retained_journal", {}).get("state") == "STOP"
                or stop.exists()
                or stop.is_symlink()
            ):
                problem(e.EgressError("CONTROL_RETAINED_JOURNAL_STOP_LATCHED"))
            health = e.strict_json(e.private_bytes(self.directory / "trace-health.json"))
            assert set(health) == {
                "binding",
                "completed",
                "entered_sha256",
                "event_hashes",
                "published",
                "attempts",
                "errors",
                "overflow",
                "state",
            }
            assert health["binding"] == binding, "CONTROL_RETAINED_JOURNAL_BINDING"
            assert health["completed"] is True and health["overflow"] is False, (
                "CONTROL_RETAINED_JOURNAL_INCOMPLETE"
            )
            hashes = health["event_hashes"]
            assert isinstance(hashes, list) and len(hashes) <= 32
            assert all(isinstance(h, str) and re.fullmatch("[0-9a-f]{64}", h) for h in hashes)
            assert len(health["published"]) == len(hashes) and all(
                type(value) is bool for value in health["published"]
            )
            assert len(health["attempts"]) == len(hashes) and all(
                type(n) is int and 1 <= n <= 3 for n in health["attempts"]
            )
            assert health["state"] in {"CONFIRMED", "NO_FAILURE", "UNCONFIRMED"}
            assert isinstance(health["errors"], list) and len(health["errors"]) <= 16
            for item in health["errors"]:
                assert set(item) == {"file", "step", "reason"}
                assert re.fullmatch(
                    r"trace-(?:entered|primary|health|secondary-[0-9]{4})\.json|retained-operation\.json",
                    item["file"],
                )
                assert item["step"] in {
                    "deadline",
                    "write",
                    "fsync_file",
                    "publish",
                    "fsync_directory",
                    "unlink",
                    "read",
                }
                assert item["reason"] == "CONTROL_RETAINED_JOURNAL_IO"
            journal_errors = health["errors"]
            entered_raw = e.private_bytes(self.directory / "trace-entered.json")
            assert e.sha(entered_raw) == health["entered_sha256"]
            entered = e.strict_json(entered_raw)
            assert entered["binding"] == binding and entered["source"] == CONTROL_T
            assert entered["module_blob"] == self.config["module_blob"]
            assert type(entered["pid"]) is int and entered["pid"] > 0
            last = entered["at"]
            assert type(last) in (float, int) and 0 < last < self.config["deadline"]
            for number, digest in enumerate(hashes, 1):
                name = "trace-primary.json" if number == 1 else f"trace-secondary-{number:04d}.json"
                try:
                    raw = e.private_bytes(self.directory / name)
                    assert e.sha(raw) == digest, "CONTROL_RETAINED_JOURNAL_HASH"
                    record = e.strict_json(raw)
                    assert set(record) == {"binding", "sequence", "detail"}
                    assert record["binding"] == binding and type(record["sequence"]) is int
                    assert record["sequence"] == number, "CONTROL_RETAINED_JOURNAL_ORDER"
                    detail = record["detail"]
                    assert {"type", "reason", "stage", "source", "at"} <= set(detail)
                    assert set(detail) <= {
                        "type",
                        "reason",
                        "stage",
                        "source",
                        "at",
                        "exit_code",
                        "observed_type",
                    }
                    assert detail["source"] == CONTROL_T
                    assert re.fullmatch(r"[A-Za-z0-9_]{1,80}", detail["type"])
                    assert re.fullmatch(
                        r"(?:CONTROL|EGRESS|FROZEN|SCHEMA)_[A-Z0-9_]{1,100}", detail["reason"]
                    )
                    assert re.fullmatch(r"[a-z0-9_]{1,80}", detail["stage"])
                    assert (
                        type(detail["at"]) in (float, int)
                        and last <= detail["at"] < self.config["deadline"]
                    )
                    assert "exit_code" not in detail or type(detail["exit_code"]) is int
                    assert "observed_type" not in detail or detail["observed_type"] == "EgressError"
                    last = detail["at"]
                    if number == 1:
                        primary = detail
                    else:
                        details.append(detail)
                except Exception as error:
                    problem(error)
            assert all(health["published"]) and health["state"] == (
                "CONFIRMED" if hashes else "NO_FAILURE"
            ), "CONTROL_RETAINED_JOURNAL_UNPUBLISHED"
            # The real launcher reserves78 for failed durability/publication,
            # including an apparently complete health file visible after failed
            # final fsync. Missing/killed/other shell exits cannot acknowledge it.
            exit_code = report.get("retained_shell_exit", report.get("shell_exit"))
            assert type(exit_code) is int and exit_code in (0, 1), (
                "CONTROL_RETAINED_JOURNAL_CHILD_UNCONFIRMED"
            )
            assert hashes or exit_code == 0, "CONTROL_RETAINED_JOURNAL_FAILURE_MISSING"
        except Exception as error:
            problem(error)
        for detail in details:
            secondary(detail)
        if diagnostics:
            # Persist STOP for a fresh collector/re-entry too. Failure to write
            # the latch remains an explicit diagnostic, never authorizes PASS.
            report["private_state_retained"] = True
            report["result"] = "STOP"
            unconfirmed = {
                "type": "UNCONFIRMED",
                "reason": "CONTROL_RETAINED_JOURNAL_UNCONFIRMED",
                "stage": "retained_journal",
                "source": CONTROL_T,
            }
            if "primary_failure" in report and report["primary_failure"] != unconfirmed:
                secondary(report["primary_failure"])
            report["primary_failure"] = unconfirmed
            report["failure"] = "UNCONFIRMED"
            report["retained_journal"] = {
                "state": "STOP",
                "primary": "UNCONFIRMED",
                "binding": binding,
                "diagnostics": journal_errors,
            }
            try:
                if not stop.exists():
                    e.write_private(stop, e.encoded({"binding": binding, "state": "STOP"}))
            except Exception as error:
                problem(error)
            for detail in diagnostics:
                secondary(detail)
            raise e.EgressError("CONTROL_RETAINED_JOURNAL_UNCONFIRMED")
        report["retained_journal"] = {
            "state": "RECOVERED" if health["errors"] else "HEALTHY",
            "primary": "CONFIRMED" if primary else "NONE",
            "binding": binding,
            "event_hashes": health["event_hashes"],
            "attempts": health["attempts"],
            "diagnostics": health["errors"],
            "observer_pid": entered["pid"],
        }
        if primary is not None:
            if report.get("primary_failure") != primary and "primary_failure" in report:
                secondary(report["primary_failure"])
            report["primary_failure"] = primary
            report["failure"] = primary["type"]
            report["private_state_retained"] = True

    def collect(self, report):
        # Retention evidence is independent of journal health: even STOP must
        # leave checkpoint/cleanup proof visible to the coordinator.
        evidence = {
            "source": CONTROL_T,
            "phase": self.owner["phase"],
            "token": self.owner["token"],
            "state": "NOT_BOUND",
            "events": [],
        }
        binding = self.directory / "retained-binding.json"
        if binding.exists():
            value = e.strict_json(e.private_bytes(binding))
            evidence.update(
                state="PRIVATE_STATE_RETAINED",
                original_identity=value["original_identity"],
                state_identity=self.identity(self.state),
                files=self.files(),
                original_exists=Path(value["original"]).exists(),
            )
            for key in ("capture", "export"):
                path = self.directory / ("retained-" + key + ".json")
                if path.exists():
                    evidence[key] = e.strict_json(e.private_bytes(path))
            evidence["events"] = sorted(
                (
                    e.strict_json(e.private_bytes(p))
                    for p in (self.directory / "retained-events").glob("*.json")
                ),
                key=lambda row: row["at"],
            )
        report["retained_checkpoint"] = evidence
        for key in ("live",):
            path = self.directory / ("retained-" + key + ".json")
            if path.exists():
                evidence[key] = e.strict_json(e.private_bytes(path))
        for event in evidence["events"]:
            if event.get("diagnostic"):
                detail = {"stage": "retained_down", **event["diagnostic"]}
                if detail not in report.setdefault("secondary_failures", []):
                    report["secondary_failures"].append(detail)
        self.collect_journal(report)


def schema_failure(error):
    """Reports never retain exception text containing argv, paths or credentials."""
    reason = str(error)
    if not re.fullmatch(r"(?:CONTROL|EGRESS|FROZEN|SCHEMA)_[A-Z0-9_]{1,100}", reason):
        reason = (
            "CONTROL_COMMAND_TIMEOUT"
            if isinstance(error, subprocess.TimeoutExpired)
            else "CONTROL_COMMAND_EXIT"
            if isinstance(error, subprocess.CalledProcessError)
            else "CONTROL_CANCELLED"
            if isinstance(error, (KeyboardInterrupt, SystemExit))
            else "CONTROL_" + type(error).__name__.upper()
        )
    result = {"type": type(error).__name__, "reason": reason}
    if isinstance(error, subprocess.CalledProcessError):
        result["exit_code"] = error.returncode
    return result


def schema_envelope(request, phase):
    def source(key):
        value = request.get(key)
        return (
            value if isinstance(value, str) and re.fullmatch("[0-9a-f]{40}", value) else "INVALID"
        )

    return {
        "phase": phase,
        "stage": "admission",
        "requested_source": source("candidate"),
        "requested_historical": source("historical"),
        "observed_source": "NOT_OBSERVED",
        "started_at": time.monotonic(),
        "budget_state": "NOT_VALIDATED",
        "cleanup": {"state": "NOT_ADMITTED"},
    }


def schema_record_failure(report, error):
    report.setdefault("failure", type(error).__name__)
    report.setdefault("primary_failure", {**schema_failure(error), "stage": report["stage"]})


def schema_publish(report, path, primary=None):
    report["elapsed_seconds"] = time.monotonic() - report["started_at"]
    budget = report.get("prepare_budget")
    if budget:
        # Preserve validated bindings even if source/archive/build/probe never succeeds.
        report["budget_at_report"] = {
            "deadline": budget["deadline"],
            "charged_seconds": time.monotonic() - budget["started_at"],
            "remaining_seconds": budget["deadline"] - time.monotonic(),
        }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")
    except BaseException as error:
        report.setdefault("secondary_failures", []).append(
            {"stage": "report", **schema_failure(error)}
        )
        if primary is None:
            raise
        primary.add_note("CONTROL_REPORT_WRITE_FAILED")
        print("CONTROL_REPORT_WRITE_FAILED", flush=True)


class SchemaOwnership:
    """Private per-phase Docker CLI wrapper, never a daemon-wide adoption rule.

    A nonce is placed on every run/create and Compose resource. Before the CLI
    can contact Docker, run/create has a durable name/CID-file intent. Thus a
    killed CLI need not return a CID for the phase to find its own container.
    Frozen T executes unchanged bytes through this scoped executable.
    """

    def __init__(self, directory, project, phase, source):
        self.directory = Path(directory)
        self.project, self.phase, self.source = project, phase, source
        self.token = uuid4().hex
        self.docker = shutil.which("docker")
        self.admitted = False

    def admit(self):
        assert self.docker and Path(self.docker).is_absolute(), "CONTROL_DOCKER_REQUIRED"
        assert not e.command([self.docker, "ps", "-aq"]).strip(), "CONTROL_INITIAL_CONTAINERS"
        assert not e.command([self.docker, "volume", "ls", "-q"]).strip(), "CONTROL_INITIAL_VOLUMES"
        self.directory.mkdir(mode=0o700)
        self.admitted = True
        value = {
            "project": self.project,
            "phase": self.phase,
            "source": self.source,
            "token": self.token,
            "docker": self.docker,
            "uid": os.getuid(),
        }
        e.write_private(self.directory / "ownership.json", e.encoded(value))
        wrapper = (
            "#!"
            + sys.executable
            + "\nimport runpy,sys\n"
            + "sys.path.insert(0,"
            + repr(str(e.ROOT))
            + ")\n"
            + "runpy.run_path("
            + repr(str(e.ROOT / "tests/test_telegram_egress_migration.py"))
            + ",run_name='__schema_docker__',init_globals={'ownership_file':"
            + repr(str(self.directory / "ownership.json"))
            + ",'docker_args':sys.argv[1:]})\n"
        )
        path = self.directory / "docker"
        path.write_text(wrapper)
        path.chmod(0o700)

    def environment(self):
        assert self.admitted, "CONTROL_OWNERSHIP_NOT_ADMITTED"
        return {**os.environ, "PATH": str(self.directory) + os.pathsep + os.environ["PATH"]}

    @classmethod
    def inherited(cls, project, source):
        executable = shutil.which("docker")
        assert executable, "CONTROL_OWNERSHIP_REQUIRED"
        directory = Path(executable).parent
        value = e.strict_json(e.private_bytes(directory / "ownership.json"))
        assert value["project"] == project and value["source"] == source, (
            "CONTROL_OWNERSHIP_BINDING"
        )
        assert value["uid"] == os.getuid(), "CONTROL_OWNERSHIP_UID"
        owner = cls(directory, project, value["phase"], source)
        owner.token, owner.docker, owner.admitted = value["token"], value["docker"], True
        return owner

    def cleanup_budget(self):
        assert self.admitted, "CONTROL_CLEANUP_NOT_ADMITTED"
        began = time.monotonic()
        budget_path = self.directory / "cleanup-budget.json"
        if budget_path.exists():
            budget = e.strict_json(e.private_bytes(budget_path))
            assert (
                budget["token"] == self.token and budget["deadline"] == budget["started_at"] + 90
            ), "CONTROL_CLEANUP_BUDGET"
        else:
            budget = {"token": self.token, "started_at": began, "deadline": began + 90}
            e.write_private(budget_path, e.encoded(budget))
        return budget

    def cleanup(self, report, observe_disconnected=None):
        began = time.monotonic()
        budget = self.cleanup_budget()
        deadline = budget["deadline"]
        report.update(
            state="RUNNING",
            token=self.token,
            project=self.project,
            phase=self.phase,
            source=self.source,
            containers=[],
            volumes=[],
            networks=[],
            intents=[],
            deadline=deadline,
            cleanup_started_at=budget["started_at"],
        )
        previous = self.directory / "down-cleanup.json"
        if previous.exists():
            report["before_frozen_teardown"] = e.strict_json(e.private_bytes(previous))

        def run(args, timeout=40):
            remaining = deadline - time.monotonic()
            assert remaining > 0, "CONTROL_CLEANUP_DEADLINE"
            return e.command([self.docker, *args], timeout=min(timeout, remaining))

        def inventory(kind):
            return (
                run([*kind, "--filter", "label=" + SCHEMA_OWNER_LABEL + "=" + self.token])
                .decode()
                .split()
            )

        try:
            intents = {}
            for path in self.directory.glob("run-*.json"):
                intent = e.strict_json(e.private_bytes(path))
                assert intent["token"] == self.token, "CONTROL_INTENT_OWNER"
                intents[intent["name"]] = intent
                cidfile = path.with_suffix(".cid")
                if cidfile.exists():
                    cid = cidfile.read_text().strip()
                    assert re.fullmatch("[0-9a-f]{64}", cid), "CONTROL_CID_FORMAT"
                    intent["cid"] = cid
                report["intents"].append(intent)
            ids = inventory(["ps", "-aq", "--no-trunc"])
            infos = json.loads(run(["inspect", *ids])) if ids else []
            volumes = set(inventory(["volume", "ls", "-q"]))
            networks = set(inventory(["network", "ls", "-q", "--no-trunc"]))
            controllers, services = [], []
            for info in infos:
                labels = info["Config"].get("Labels") or {}
                assert labels.get(SCHEMA_OWNER_LABEL) == self.token, "CONTROL_CONTAINER_OWNER"
                name = info["Name"].lstrip("/")
                if name in intents:
                    intent = intents[name]
                    assert intent.get("cid", info["Id"]) == info["Id"], "CONTROL_CID_CHANGED"
                    if "retained_bind" in intent:
                        checkpoint = RetainedCheckpoint(self.directory)
                        assert checkpoint.identity(checkpoint.state) == intent["retained_bind"], (
                            "CONTROL_RETAINED_BIND_IDENTITY"
                        )
                        assert any(
                            m["Type"] == "bind"
                            and m["Destination"] == "/state"
                            and m["Source"] == str(checkpoint.state)
                            for m in info.get("Mounts", [])
                        ), "CONTROL_RETAINED_DAEMON_BIND"
                    intent["cid"] = info["Id"]
                    controllers.append(info["Id"])
                else:
                    assert labels.get("com.docker.compose.project") == self.project, (
                        "CONTROL_COMPOSE_OWNER"
                    )
                    services.append(info["Id"])
                report["containers"].append(
                    {
                        "id": info["Id"],
                        "name": name,
                        "running": info["State"]["Running"],
                        "token": self.token,
                    }
                )
                for mount in info.get("Mounts", []):
                    if mount["Type"] == "volume":
                        # Anonymous image VOLUMEs are owned by this exact CID,
                        # never merely because the initial daemon was empty.
                        meta = json.loads(run(["volume", "inspect", mount["Name"]]))[0]
                        if (meta.get("Labels") or {}).get(SCHEMA_OWNER_LABEL) == self.token or (
                            not meta.get("Labels")
                            and meta.get("Driver") == "local"
                            and not meta.get("Options")
                            and re.fullmatch("[0-9a-f]{64}", mount["Name"])
                            and mount["Destination"] in (info["Config"].get("Volumes") or {})
                        ):
                            volumes.add(mount["Name"])
            report["volumes"], report["networks"] = sorted(volumes), sorted(networks)
            unconfirmed = [intent["name"] for intent in intents.values() if "cid" not in intent]
            report["unconfirmed_creations"] = unconfirmed

            def remove(containers):
                if not containers:
                    return
                # stop sends TERM, Docker kills a TERM-ignoring process after2s.
                # If its CLI fails, exact-ID force removal still runs in this90s bound.
                try:
                    run(["stop", "--time", "2", *containers], timeout=15)
                except Exception as error:
                    report.setdefault("stop_diagnostics", []).append(schema_failure(error))
                still_present = set(run(["ps", "-aq", "--no-trunc"]).decode().split())
                retained = [ident for ident in containers if ident in still_present]
                if retained:
                    try:
                        run(["rm", "-f", "-v", *retained], timeout=40)
                    except e.EgressError as error:
                        # Docker --rm can finish between list and remove. Read
                        # canonical absence; never repeat the destructive call.
                        current = set(run(["ps", "-aq", "--no-trunc"]).decode().split())
                        if set(retained) & current:
                            raise
                        report.setdefault("remove_ack_readback", []).append(schema_failure(error))
                assert not set(containers) & set(
                    run(["ps", "-aq", "--no-trunc"]).decode().split()
                ), "CONTROL_CONTAINER_NOT_REMOVED"

            remove(controllers)
            if observe_disconnected is not None:
                report["connections_after_controller_stop"] = observe_disconnected(deadline)
                assert report["connections_after_controller_stop"] == 0, (
                    "CONTROL_CONNECTION_REMAINS"
                )
            remove(services)
            # --rm may already have removed anonymous volumes; inspect current
            # names but intersect only the identities proved above.
            existing_volumes = set(run(["volume", "ls", "-q"]).decode().split())
            for name in sorted(volumes & existing_volumes):
                run(["volume", "rm", name])
            existing_networks = set(run(["network", "ls", "-q", "--no-trunc"]).decode().split())
            for ident in sorted(networks & existing_networks):
                run(["network", "rm", ident])
            assert not inventory(["ps", "-aq", "--no-trunc"]), "CONTROL_OWNED_CONTAINER_REMAINS"
            assert not inventory(["volume", "ls", "-q"]), "CONTROL_OWNED_VOLUME_REMAINS"
            assert not inventory(["network", "ls", "-q", "--no-trunc"]), (
                "CONTROL_OWNED_NETWORK_REMAINS"
            )
            remaining_containers = run(["ps", "-aq", "--no-trunc"]).decode().split()
            remaining_volumes = run(["volume", "ls", "-q"]).decode().split()
            report.update(
                owned_remaining=[],
                foreign_containers=remaining_containers,
                foreign_volumes=remaining_volumes,
                state="OWNED_REMOVED",
            )
            # A CLI lost before both CID-file and label observation is not proof
            # of non-creation. Keep the private intents, report STOP, never PASS.
            if unconfirmed:
                report["state"] = "CREATION_UNCONFIRMED"
                raise AssertionError("CONTROL_CREATION_UNCONFIRMED")
            # A foreign sentinel is preserved AND still makes the phase fail.
            assert not remaining_containers and not remaining_volumes, (
                "CONTROL_FOREIGN_RESOURCE_REMAINS"
            )
            report["state"] = "PASS"
        except BaseException as error:
            report["diagnostic"] = schema_failure(error)
            raise
        finally:
            report["seconds"] = time.monotonic() - began
            report["whole_cleanup_seconds"] = time.monotonic() - budget["started_at"]


def schema_docker_cli(path, args):
    """Only the disposable phase inherits this wrapper; no frozen file changes."""
    path = Path(path)
    value = e.strict_json(e.private_bytes(path))
    assert value["uid"] == os.getuid(), "CONTROL_OWNERSHIP_UID"
    docker, token, project = value["docker"], value["token"], value["project"]
    label = SCHEMA_OWNER_LABEL + "=" + token
    checkpoint = (
        RetainedCheckpoint(path.parent) if (path.parent / "retained.json").exists() else None
    )
    binding = None
    if args[:1] in (["run"], ["create"]):
        assert not any(
            a == "--name" or a.startswith("--name=") or a.startswith("--cidfile") for a in args
        ), "CONTROL_CONTAINER_ID_OVERRIDE"
        name = "asm-schema-" + token + "-" + uuid4().hex[:12]
        intent = path.parent / ("run-" + name + ".json")
        birth = Path("/proc/self/stat").read_text().rpartition(")")[2].split()[19]
        if checkpoint is not None:
            args, binding = checkpoint.bind(args)
        e.write_private(
            intent,
            e.encoded(
                {
                    "name": name,
                    "token": token,
                    "phase": value["phase"],
                    "cli_pid": os.getpid(),
                    "cli_pgid": os.getpgrp(),
                    "cli_start_ticks": int(birth),
                    **({"retained_bind": binding} if binding else {}),
                }
            ),
        )
        args = [
            args[0],
            "--label",
            label,
            "--name",
            name,
            "--cidfile",
            str(intent.with_suffix(".cid")),
            *args[1:],
        ]
    elif args[:2] in (["volume", "create"], ["network", "create"]):
        args = [*args[:2], "--label", label, *args[2:]]
    elif args[:1] == ["compose"]:
        commands = {"config", "up", "run", "ps", "stop", "down"}
        index = next((i for i, a in enumerate(args) if a in commands), None)
        assert index is not None, "CONTROL_COMPOSE_COMMAND"
        prefix = args[:index]
        assert (
            "--project-name" in prefix and prefix[prefix.index("--project-name") + 1] == project
        ), "CONTROL_COMPOSE_PROJECT"
        overlay = path.parent / "compose-ownership.json"
        if not overlay.exists():
            result = subprocess.run(
                [docker, *prefix, "config", "--format", "json"],
                capture_output=True,
                check=True,
                timeout=40,
            )
            model = json.loads(result.stdout)
            labels = {SCHEMA_OWNER_LABEL: token}
            document = {}
            for group in ("services", "volumes", "networks"):
                document[group] = {}
                for name, item in model.get(group, {}).items():
                    assert not item.get("external"), "CONTROL_EXTERNAL_COMPOSE_RESOURCE"
                    document[group][name] = {"labels": labels}
            e.write_private(overlay, e.encoded(document))
        if args[index] == "down":
            # Frozen T destroys its private state immediately after this call.
            # Complete exact owned cleanup here too, before that unchanged
            # finally can run; never let compose --remove-orphans touch foreign.
            owner = SchemaOwnership.inherited(project, value["source"])
            detail = {}
            try:
                if checkpoint is not None:
                    owner.cleanup_budget()
                    e.write_private(
                        path.parent / "retained-operation.json",
                        e.encoded({"stage": "retained_down", "source": CONTROL_T, "token": token}),
                    )
                    if (
                        checkpoint.config["fault"]
                        and (checkpoint.state / "connected.json").exists()
                    ):
                        checkpoint.observe_live()
                    checkpoint.capture()
                    checkpoint.event("OWNED_CLEANUP_BEGIN")
                if (
                    checkpoint is not None
                    and (checkpoint.directory / "retained-live.json").exists()
                ):
                    owner.cleanup(detail, checkpoint.disconnected)
                else:
                    owner.cleanup(detail)
            finally:
                primary = sys.exception()
                try:
                    e.write_private(path.parent / "down-cleanup.json", e.encoded(detail))
                except BaseException:
                    if primary is None:
                        raise
                    primary.add_note("CONTROL_DOWN_REPORT_FAILED")
                if checkpoint is not None:
                    try:
                        checkpoint.event(
                            "OWNED_CLEANUP_RESULT",
                            state=detail.get("state", "NOT_STARTED"),
                            diagnostic=schema_failure(primary) if primary else None,
                        )
                    except BaseException:
                        if primary is None:
                            raise
                        primary.add_note("CONTROL_RETAINED_EVENT_FAILED")
        args = [*prefix, "-f", str(overlay), *args[index:]]
    if checkpoint is not None and binding is not None:
        raise SystemExit(checkpoint.run_bound(args))
    os.execv(docker, [docker, *args])


@contextmanager
def schema_private_workspace(report, prefix):
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield directory
    finally:
        primary = sys.exception()
        if report["cleanup"]["state"] not in {"NOT_ADMITTED", "PASS", "OWNED_REMOVED"}:
            report["private_state_retained"] = True
        else:
            try:
                shutil.rmtree(directory)
            except BaseException as error:
                report["private_state_retained"] = True
                report.setdefault("secondary_failures", []).append(
                    {"stage": "private_state_cleanup", **schema_failure(error)}
                )
                if primary is None:
                    raise
                primary.add_note("CONTROL_PRIVATE_STATE_CLEANUP_FAILED")


@contextmanager
def schema_cleanup_scope(owner, report, path, observe_disconnected=None):
    primary = None
    try:
        yield
    except BaseException as error:
        primary = error
        schema_record_failure(report, error)
        raise
    finally:
        secondary = None
        directory = getattr(owner, "directory", None)
        checkpoint = (
            RetainedCheckpoint(directory)
            if directory and (directory / "retained.json").exists()
            else None
        )
        if checkpoint is not None:
            try:
                owner.cleanup_budget()
                checkpoint.capture()
                checkpoint.collect(report)
            except BaseException as error:
                report["private_state_retained"] = True
                report.setdefault("secondary_failures", []).append(
                    {"stage": "retained_checkpoint", **schema_failure(error)}
                )
                if primary is None:
                    secondary = error
                    schema_record_failure(report, error)
        try:
            schema_publish(report, path, primary)
        except BaseException as error:
            secondary = error
            schema_record_failure(report, error)
        try:
            if observe_disconnected is None:
                owner.cleanup(report["cleanup"])
            else:
                owner.cleanup(report["cleanup"], observe_disconnected)
        except BaseException as error:
            if primary is None and secondary is None:
                secondary = error
                schema_record_failure(report, error)
            report.setdefault("secondary_failures", []).append(
                {"stage": "cleanup", **schema_failure(error)}
            )
            if primary is not None:
                primary.add_note("CONTROL_OWNED_CLEANUP_FAILED")
        finally:
            if checkpoint is not None:
                try:
                    checkpoint.collect(report)
                except BaseException as error:
                    report["private_state_retained"] = True
                    report.setdefault("secondary_failures", []).append(
                        {"stage": "retained_evidence", **schema_failure(error)}
                    )
                    if primary is None and secondary is None:
                        secondary = error
            schema_publish(report, path, primary or secondary)
        if primary is None and secondary is not None:
            raise secondary


def consume_control_budget(path, historical, candidate):
    """One private handoff, absolute monotonic deadline, no inherited/global reset."""
    raw = e.private_bytes(path)
    info = path.stat()
    assert info.st_nlink == 1, "CONTROL_BUDGET_SINGLE_LINK"
    value = e.strict_json(raw)
    assert set(value) == {
        "version",
        "phase",
        "historical",
        "candidate",
        "uid",
        "started_at",
        "issued_at",
        "charged_seconds",
        "deadline",
    }, "CONTROL_BUDGET_FORMAT"
    assert value["version"] == 1 and type(value["version"]) is int, "CONTROL_BUDGET_VERSION"
    assert value["phase"] == CONTROL_PHASE and value["historical"] == historical == CONTROL_T, (
        "CONTROL_BUDGET_PHASE_SOURCE"
    )
    assert (
        value["candidate"] == candidate
        and type(value["uid"]) is int
        and value["uid"] == os.getuid()
    ), "CONTROL_BUDGET_CANDIDATE_OWNER"
    for key in ("started_at", "issued_at", "charged_seconds", "deadline"):
        assert type(value[key]) in (int, float) and 0 < value[key] < float("inf"), (
            "CONTROL_BUDGET_CLOCK"
        )
    assert abs(value["deadline"] - value["started_at"] - 600) < 0.001, "CONTROL_BUDGET_TOTAL"
    assert abs(value["issued_at"] - value["started_at"] - value["charged_seconds"]) < 0.001, (
        "CONTROL_BUDGET_CHARGED"
    )
    now = time.monotonic()
    assert value["issued_at"] <= now < value["deadline"], "CONTROL_BUDGET_EXHAUSTED"
    # Preserve the absolute bound across process startup and handoff delay.
    assert (path.stat().st_dev, path.stat().st_ino) == (info.st_dev, info.st_ino), (
        "CONTROL_BUDGET_FILE_CHANGED"
    )
    path.unlink()
    return {
        **value,
        "handoff_seconds": now - value["issued_at"],
        "remaining_seconds": value["deadline"] - now,
    }


def supervised_schema_child(args, *, cwd, timeout, environment=None):
    """No detached runner; timeout kills the owned process group and waits."""
    assert timeout > 0, "CONTROL_PREPARE_BUDGET_EXHAUSTED"
    process = subprocess.Popen(
        args, cwd=cwd, stdin=subprocess.DEVNULL, start_new_session=True, env=environment
    )

    def stop_group():
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if sig == signal.SIGKILL:
                    raise
        # The shell may exit on TERM while a descendant ignores it. KILL the
        # group even after its leader exits, then observe all members stopped.
        deadline = time.monotonic() + 5
        while True:
            live = []
            for path in Path("/proc").glob("[0-9]*/stat"):
                try:
                    fields = path.read_text().rpartition(")")[2].split()
                except FileNotFoundError:
                    continue
                if int(fields[2]) == process.pid and fields[0] != "Z":
                    live.append(path.parent.name)
            if not live:
                return
            assert time.monotonic() < deadline, "CONTROL_CHILD_GROUP_NOT_STOPPED"
            time.sleep(0.02)

    try:
        result = process.wait(timeout=timeout)
    except BaseException as error:
        try:
            stop_group()
        except BaseException as cleanup:
            error.add_note("CONTROL_CHILD_CLEANUP_FAILED: " + type(cleanup).__name__)
        raise
    if result:
        try:
            stop_group()
        except BaseException as cleanup:
            error = subprocess.CalledProcessError(result, args)
            error.add_note("CONTROL_CHILD_CLEANUP_FAILED: " + type(cleanup).__name__)
            raise error from cleanup
    return result


@contextmanager
def schema_coordinator_workspace(ledger):
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix="asm-frozen-t-"))
    try:
        yield directory
    finally:
        primary = sys.exception()
        # Keep a private checkpoint if evidence export or daemon cleanup failed.
        # Never destroy a bind-mounted state under a still-running owned process.
        if (
            ledger.get("private_state_retained")
            or ledger.get("retained_reports_failed")
            or ledger["cleanup"]["state"]
            not in {
                "NOT_ADMITTED",
                "PASS",
                "OWNED_REMOVED",
            }
        ):
            ledger["private_state_retained"] = True
        else:
            try:
                checkout = directory / "turns"
                if (checkout / ".git").exists():
                    e.command(["git", "worktree", "remove", str(checkout)])
                shutil.rmtree(directory)
            except BaseException as error:
                ledger["private_state_retained"] = True
                ledger.setdefault("secondary_failures", []).append(
                    {"stage": "workspace_cleanup", **schema_failure(error)}
                )
                if primary is None:
                    raise
                primary.add_note("CONTROL_WORKSPACE_CLEANUP_FAILED")


def run_retained_full_negatives(directory, checkout, request, ledger):
    """Entire immutable T function/finally, charged to the original600 clock."""
    deadline = ledger["deadline"]
    positive = json.loads((checkout / "reports/m3-schema-phase.json").read_text())
    historical = request["historical"]
    candidate = request["candidate"]
    results = []
    for source in (historical, CONTROL_T):
        for kind in ("runtime", "development"):
            image = positive["images"][source + ":" + kind]["id"]
            # The unchanged T image probes will independently recheck all bytes.
            # These aliases ensure neither negative can fall back to rebuilding.
            e.command(
                ["docker", "tag", image, "asm-connect5-" + kind + ":" + source],
                timeout=min(40, deadline - time.monotonic()),
            )
    for fault in ("timeout", "export"):
        ledger["stage"] = "full_retained_" + fault
        report = schema_envelope(request, "FULL_RETAINED_T_" + fault.upper())
        report.update(
            evidence="ACTUAL_FULL_T_DOCKER_POSTGRES",
            whole_prepare_started_at=ledger["started_at"],
            deadline=deadline,
            budget_seconds=600,
            executor_source=CONTROL_T,
        )
        path = e.ROOT / "reports" / ("control-full-retained-" + fault + ".json")
        owner = SchemaOwnership(
            directory / ("owner-T-" + fault), "asm-m3-schema-phase", report["phase"], CONTROL_T
        )
        checkpoint = None
        failure = None
        schema_publish(report, path)
        try:
            owner.admit()
            report["cleanup"] = {"state": "ADMITTED"}
            enable_retained_checkpoint(owner, checkout, deadline, fault)
            checkpoint = RetainedCheckpoint(owner.directory)
            # A failed case must retain its private backing even if an assertion
            # prevents the positive coordinator handoff from being reached.
            ledger["private_state_retained"] = True
            with schema_cleanup_scope(owner, report, path, checkpoint.disconnected):
                report["stage"] = "full_retained_shell"
                result = supervised_schema_child(
                    [
                        "sh",
                        "scripts/test_telegram_egress.sh",
                        "--schema-upgrade",
                        historical,
                        CONTROL_T,
                    ],
                    cwd=checkout,
                    timeout=deadline - time.monotonic(),
                    environment=owner.environment(),
                )
                report["shell_exit"] = result
                checkpoint.collect(report)
                report["partial_T_report"] = json.loads(
                    (checkout / "reports/m3-schema-phase.json").read_text()
                )
                report["trace_entered"] = e.strict_json(
                    e.private_bytes(owner.directory / "trace-entered.json")
                )
                proof = report["retained_checkpoint"]
                assert result != 0 and not proof["original_exists"], (
                    "CONTROL_FULL_T_FAILURE_REQUIRED"
                )
                assert "database" not in report["partial_T_report"], (
                    "CONTROL_FULL_T_FAILURE_AFTER_FINAL_READ"
                )
                assert proof["files"]["receipt.json"]["bytes"] > 0, (
                    "CONTROL_FULL_T_RECEIPT_REQUIRED"
                )
                detail = report["primary_failure"]
                expected = (
                    "CONTROL_COMMAND_TIMEOUT" if fault == "timeout" else "CONTROL_COMMAND_EXIT"
                )
                assert (
                    detail["reason"] == expected
                    and detail["stage"] == "controller_seed"
                    and detail["source"] == CONTROL_T
                ), "CONTROL_PRIMARY_FAILURE_CHANGED"
                assert (
                    proof["live"]["image"] == positive["images"][CONTROL_T + ":development"]["id"]
                ), "CONTROL_RETAINED_IMAGE_CHANGED"
                checkpoint.event(
                    "FROZEN_TEMP_REMOVED_STATE_RETAINED",
                    files=proof["files"],
                    state_identity=proof["state_identity"],
                )
                if fault == "export":
                    assert detail["exit_code"] == 7
                    assert not (owner.directory / "retained-export.json").exists(), (
                        "CONTROL_EXPORT_FAILURE_REQUIRED"
                    )
                    report["live_after_T_teardown"] = checkpoint.observe_live()
                    assert report["live_after_T_teardown"]["connections_before_cleanup"] == 1
                    assert (
                        checkpoint.root / proof["capture"]["snapshot"] / "receipt.json"
                    ).read_bytes() == e.private_bytes(checkpoint.state / "receipt.json"), (
                        "CONTROL_RETAINED_BYTES_CHANGED"
                    )
                report["host_children"] = checkpoint.host_children()
                raise e.EgressError(expected)
        except e.EgressError as error:
            failure = error
            expected = "CONTROL_COMMAND_TIMEOUT" if fault == "timeout" else "CONTROL_COMMAND_EXIT"
            assert str(error) == expected, "CONTROL_UNEXPECTED_FULL_T_FAILURE"
            assert report["cleanup"]["state"] == "OWNED_REMOVED", (
                "CONTROL_RETAINED_CLEANUP_REQUIRED"
            )
            assert report["cleanup"]["diagnostic"]["reason"] == "CONTROL_FOREIGN_RESOURCE_REMAINS"
            before = report["cleanup"].get("before_frozen_teardown", {})
            # In timeout, down already removed the owned DB. Re-entry records
            # absence rather than opening a new connection to a deleted service.
            cleanup = before if fault == "timeout" else report["cleanup"]
            assert cleanup["connections_after_controller_stop"] == 0
            assert report["cleanup"]["owned_remaining"] == []
            assert report["cleanup"]["deadline"] == cleanup["deadline"]
            assert report["cleanup"]["whole_cleanup_seconds"] < 90
            proof = report["retained_checkpoint"]
            assert proof["capture"]["files"] == proof["export"]["files"] == proof["files"]
            events = proof["events"]
            captures = [v["at"] for v in events if v["event"] == "CHECKPOINT_CAPTURED"]
            zero = [v["at"] for v in events if v["event"] == "PG_ZERO_BEFORE_DB_STOP"]
            removed = [
                v["at"] for v in events if v["event"] == "FROZEN_TEMP_REMOVED_STATE_RETAINED"
            ]
            assert report["primary_failure"]["at"] < min(captures) < min(removed), (
                "CONTROL_RETAINED_EVENT_ORDER"
            )
            assert len(zero) == 1
            assert (zero[0] < removed[0]) if fault == "timeout" else (removed[0] < zero[0])
            report["foreign_before"] = e.strict_json(
                e.private_bytes(owner.directory / "foreign-before.json")
            )
            report["foreign_after"] = checkpoint.foreign_proof()
            assert report["foreign_before"] == report["foreign_after"], "CONTROL_FOREIGN_CHANGED"
            report["host_children"] = checkpoint.host_children()
            report["source_clean"] = not bool(
                e.command(
                    ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"]
                ).strip()
            )
            assert report["source_clean"], "FROZEN_TURNS_SOURCE_CHANGED"
            report["result"] = "PASS"
            report["charged_seconds"] = time.monotonic() - ledger["started_at"]
            assert time.monotonic() < deadline, "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            results.append(fault)
            print("CONTROL_FULL_RETAINED_NEGATIVE_PASS " + fault, flush=True)
        except BaseException as error:
            failure = error
            schema_record_failure(report, error)
            raise
        finally:
            schema_publish(report, path, failure or sys.exception())
            if checkpoint is not None and report.get("result") == "PASS":
                # Only the fixture's exact foreign identities, after unchanged
                # evidence is saved. The owned cleanup deliberately refused them.
                checkpoint.remove_foreign_fixture()
    assert results == ["timeout", "export"]
    assert not e.command(["docker", "ps", "-aq"]).strip()
    assert not e.command(["docker", "volume", "ls", "-q"]).strip()
    summary = {
        "candidate": candidate,
        "source": CONTROL_T,
        "result": "PASS",
        "count": 2,
        "results": results,
        "deadline": deadline,
        "started_at": ledger["started_at"],
        "charged_seconds": time.monotonic() - ledger["started_at"],
    }
    (e.ROOT / "reports/control-full-retained-negatives.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    ledger["full_retained_negatives"] = summary


def run_control_coordinator(request):
    """Retained frozen T shell is charged once, including runtime and cleanup."""
    ledger = schema_envelope(request, "CONTROL_COORDINATOR")
    started = ledger["started_at"]
    deadline = started + 600
    ledger.update(budget_seconds=600, deadline=deadline, retained=CONTROL_T)
    reports = e.ROOT / "reports"
    path = reports / "control-schema-ledger.json"
    retained = reports / "retained-turns"
    primary = None
    schema_publish(ledger, path)
    try:
        historical, candidate = request["historical"], request["candidate"]
        assert historical == "754f1c883e5a94a7fc9e729af2605424f949ba33", "CONTROL_HISTORICAL_SOURCE"
        assert (
            Path.cwd() == e.ROOT and os.getuid() != 0 and os.environ.get("GITHUB_ACTIONS") == "true"
        ), "CONTROL_DISPOSABLE_RUNNER"
        ledger["observed_source"] = e.command(["git", "rev-parse", "HEAD"]).decode().strip()
        ledger["stage"] = "source_check"
        e.source_check(candidate)
        ledger.update(
            historical=historical, candidate=candidate, budget_state="COORDINATOR_VALIDATED"
        )
        retained.mkdir(parents=True, exist_ok=True)
        with schema_coordinator_workspace(ledger) as temp:
            directory = Path(temp)
            checkout = directory / "turns"
            added = False
            owner = SchemaOwnership(
                directory / "owner-T", "asm-m3-schema-phase", "RETAINED_T", CONTROL_T
            )
            ledger["stage"] = "retained_admission"
            owner.admit()
            ledger["cleanup"] = {"state": "ADMITTED"}
            # Includes report-copy and worktree-removal failures in the same
            # primary/secondary discipline as command failures.
            with schema_cleanup_scope(owner, ledger, path):
                try:
                    ledger["stage"] = "retained_archive"
                    with e.migration_budget(deadline - time.monotonic()):
                        e.command(["git", "merge-base", "--is-ancestor", CONTROL_T, candidate])
                        (retained / "source-T.tar.gz").write_bytes(
                            e.command(["git", "archive", "--format=tar.gz", CONTROL_T])
                        )
                        e.command(["git", "worktree", "add", "--detach", str(checkout), CONTROL_T])
                        added = True
                    enable_retained_checkpoint(owner, checkout, deadline)
                    ledger["stage"] = "retained_shell"
                    ledger["retained_shell_started_at"] = time.monotonic()
                    result = supervised_schema_child(
                        [
                            "sh",
                            "scripts/test_telegram_egress.sh",
                            "--schema-upgrade",
                            historical,
                            CONTROL_T,
                        ],
                        cwd=checkout,
                        timeout=deadline - time.monotonic(),
                        environment=owner.environment(),
                    )
                    ledger["retained_shell_exit"] = result
                    assert result == 0, "FROZEN_TURNS_SCHEMA_FAILED"
                finally:
                    failure = sys.exception()
                    if (owner.directory / "retained.json").exists():
                        try:
                            RetainedCheckpoint(owner.directory).collect(ledger)
                        except BaseException as error:
                            ledger["private_state_retained"] = True
                            ledger.setdefault("secondary_failures", []).append(
                                {"stage": "retained_evidence", **schema_failure(error)}
                            )
                            if failure is None:
                                raise
                            failure.add_note("CONTROL_RETAINED_EVIDENCE_FAILED")
                    ledger["retained_shell_seconds"] = time.monotonic() - ledger.get(
                        "retained_shell_started_at", started
                    )
                    try:
                        if (checkout / "reports").exists():
                            shutil.copytree(checkout / "reports", retained, dirs_exist_ok=True)
                        if added:
                            ledger["retained_clean"] = not bool(
                                e.command(
                                    [
                                        "git",
                                        "-C",
                                        str(checkout),
                                        "status",
                                        "--porcelain",
                                        "--untracked-files=all",
                                    ]
                                ).strip()
                            )
                        schema_publish(ledger, retained / "source-pairing.json", failure)
                    except BaseException as error:
                        ledger["retained_reports_failed"] = True
                        if failure is None:
                            raise
                        ledger.setdefault("secondary_failures", []).append(
                            {"stage": "retained_reports", **schema_failure(error)}
                        )
                        failure.add_note("CONTROL_RETAINED_REPORT_FAILED")
            # Owned cleanup and copied reports precede checkout removal. If any
            # preceding stage failed, retain the checkout instead of hiding it.
            ledger["retained_cleanup"] = ledger["cleanup"]
            run_retained_full_negatives(directory, checkout, request, ledger)
            if added:
                e.command(["git", "worktree", "remove", str(checkout)])
            assert ledger["retained_clean"], "FROZEN_TURNS_SOURCE_CHANGED"
            # C is a frozen executor in its own checkout. It receives the
            # same original deadline, not a nested coordinator/fresh600.
            control = directory / "control"
            retained_c = reports / "retained-control"
            retained_c.mkdir(parents=True, exist_ok=True)
            with e.migration_budget(deadline - time.monotonic()):
                e.command(["git", "merge-base", "--is-ancestor", GUARDS_C, candidate])
                (retained_c / "source-C.tar.gz").write_bytes(
                    e.command(["git", "archive", "--format=tar.gz", GUARDS_C])
                )
                e.command(["git", "worktree", "add", "--detach", str(control), GUARDS_C])
            ledger["retained_control_source"] = GUARDS_C
            issued = time.monotonic()
            assert issued < deadline, "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            value = {
                "version": 1,
                "phase": CONTROL_PHASE,
                "historical": CONTROL_T,
                "candidate": GUARDS_C,
                "uid": os.getuid(),
                "started_at": started,
                "issued_at": issued,
                "charged_seconds": issued - started,
                "deadline": deadline,
            }
            handoff = directory / "control-budget.json"
            e.write_private(handoff, e.encoded(value))
            ledger["handoff"] = value
            ledger["stage"] = "retained_control_admission"
            owner = SchemaOwnership(
                directory / "owner-C", "asm-control-schema-phase", CONTROL_PHASE, GUARDS_C
            )
            owner.admit()
            ledger["cleanup"] = {"state": "ADMITTED"}
            with schema_cleanup_scope(owner, ledger, path):
                ledger["stage"] = "retained_control_shell"
                began = time.monotonic()
                try:
                    result = supervised_schema_child(
                        [
                            "sh",
                            "scripts/test_telegram_egress.sh",
                            "--control-schema-upgrade",
                            CONTROL_T,
                            GUARDS_C,
                            str(handoff),
                        ],
                        cwd=control,
                        timeout=deadline - time.monotonic(),
                        environment=owner.environment(),
                    )
                    ledger["control_exit"] = result
                    assert result == 0 and not handoff.exists(), "CONTROL_SCHEMA_PHASE_FAILED"
                finally:
                    ledger["whole_control_seconds"] = time.monotonic() - began
                    if (control / "reports").exists():
                        shutil.copytree(control / "reports", retained_c, dirs_exist_ok=True)
            ledger["control_cleanup"] = ledger["cleanup"]
            ledger["whole_retained_charge"] = time.monotonic() - started
            assert time.monotonic() < deadline, "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            control_report = json.loads((retained_c / "control-schema-phase.json").read_text())
            assert (
                control_report["coordinator"] == GUARDS_C
                and control_report["historical"] == CONTROL_T
            )
            assert control_report["cleanup"]["state"] == "PASS"
            ledger["retained_control_report"] = "retained-control/control-schema-phase.json"

            issued = time.monotonic()
            value = {
                "version": 1,
                "phase": GUARDS_PHASE,
                "historical": GUARDS_C,
                "candidate": candidate,
                "uid": os.getuid(),
                "started_at": started,
                "issued_at": issued,
                "charged_seconds": issued - started,
                "deadline": deadline,
            }
            handoff_g = directory / "guards-budget.json"
            e.write_private(handoff_g, e.encoded(value))
            ledger["guards_handoff"] = value
            ledger["stage"] = "guards_admission"
            owner_g = SchemaOwnership(
                directory / "owner-G", "asm-guards-schema-phase", GUARDS_PHASE, candidate
            )
            owner_g.admit()
            ledger["cleanup"] = {"state": "ADMITTED"}
            with schema_cleanup_scope(owner_g, ledger, path):
                ledger["stage"] = "guards_shell"
                result = supervised_schema_child(
                    [
                        "sh",
                        "scripts/test_telegram_egress.sh",
                        "--guards-schema-upgrade",
                        GUARDS_C,
                        candidate,
                        str(handoff_g),
                    ],
                    cwd=e.ROOT,
                    timeout=(deadline - time.monotonic()) + 480,
                    environment=owner_g.environment(),
                )
                ledger["guards_exit"] = result
                assert result == 0 and not handoff_g.exists(), "GUARDS_SCHEMA_PHASE_FAILED"
                e.source_check(candidate)
            ledger["guards_cleanup"] = ledger["cleanup"]
            # Retain all six existing daemon assertions in the unchanged C
            # executor. Its report is kept as C evidence, never relabelled G.
            ledger["stage"] = "retained_control_cleanup_negatives"
            result = supervised_schema_child(
                [
                    sys.executable,
                    "-c",
                    "import runpy; runpy.run_path('tests/test_telegram_egress_migration.py', init_globals={'control_cleanup_request': {'historical': '754f1c883e5a94a7fc9e729af2605424f949ba33', 'candidate': 'c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5'}}, run_name='__control_cleanup_negatives__')",
                ],
                cwd=control,
                timeout=480,
            )
            try:
                assert result == 0, "CONTROL_CLEANUP_NEGATIVE_EXIT"
                negative = json.loads(
                    (control / "reports/control-cleanup-negatives.json").read_text()
                )
                assert (
                    negative["candidate"] == GUARDS_C
                    and negative["result"] == "PASS"
                    and negative["count"] == 3
                )
                ledger["retained_control_negatives"] = negative
            finally:
                shutil.copytree(control / "reports", retained_c, dirs_exist_ok=True)
            assert not e.command(
                ["git", "-C", str(control), "status", "--porcelain", "--untracked-files=all"]
            ).strip(), "FROZEN_CONTROL_SOURCE_CHANGED"
            e.command(["git", "worktree", "remove", str(control)])
            schema_publish(ledger, path)
            print("GUARDS_SCHEMA_COORDINATOR_PASS", flush=True)
    except BaseException as error:
        primary = error
        schema_record_failure(ledger, error)
        raise
    finally:
        ledger["total_schema_seconds"] = time.monotonic() - started
        ledger["charged_pre_handoff_seconds"] = ledger.get("handoff", {}).get(
            "charged_seconds", ledger["total_schema_seconds"]
        )
        schema_publish(ledger, path, primary)


def control_schema_recovery_source(result, observe, report, historical, candidate):
    detail = {
        "injection": "after_commit_before_success_exit",
        "exit_code": result.returncode,
        "observed": "NOT_READ",
    }
    report["upgrade_ack_loss"] = detail
    assert historical == CONTROL_T
    if result.returncode != 86 or result.stdout.strip() != b"CONTROL_UPGRADE_COMMITTED_RESULT_LOST":
        detail["result"] = "UNEXPECTED_MIGRATOR_RESULT"
        raise AssertionError("CONTROL_EXPECTED_POST_COMMIT_FAILURE")
    detail.update(
        result="CONTROLLED_FAILURE_OBSERVED", marker="CONTROL_UPGRADE_COMMITTED_RESULT_LOST"
    )
    try:
        observation = observe()
    except Exception:
        detail["observed"] = "UNREADABLE"
        raise
    detail["observed"] = observation
    assert observation["revision"] == "0009" and observation["role"] == "asm_migrator"
    assert observation["database"] == "asm_local"
    assert type(observation["reader_pid"]) is int and observation["reader_pid"] > 0
    assert type(observation["backend_pid"]) is int and observation["backend_pid"] > 0
    lost = report.get("lost_result_process")
    assert isinstance(lost, dict) and set(lost) == {
        "namespace",
        "pid",
        "start_ticks",
        "boot_id",
    }, "CONTROL_PROCESS_IDENTITY_REQUIRED"
    assert type(lost["pid"]) is int and lost["pid"] > 0
    assert type(lost["start_ticks"]) is int and lost["start_ticks"] > 0
    assert type(observation["reader_start_ticks"]) is int
    assert observation["reader_boot_id"] == lost["boot_id"] and lost["boot_id"], (
        "CONTROL_RECOVERY_HOST_BOOT"
    )
    # Docker can reuse a released PID namespace inode; PID1 alone is not a
    # process identity. Kernel start ticks prove this reader was created later
    # on the same boot, including that reuse case, and reject the prior process.
    assert observation["reader_start_ticks"] > lost["start_ticks"], "CONTROL_FRESH_PROCESS_REQUIRED"
    for key, value in report["seed_identity"].items():
        assert observation[key] == value, "CONTROL_RECOVERY_DATABASE_IDENTITY"
    detail["recovery_source"] = candidate
    return candidate


def run_control_schema_phase(request):
    """New disposable LOCAL volume, exact T/C images, drained CONTROL cutover."""
    report = schema_envelope(request, CONTROL_PHASE)
    report.update(images={}, checks=[], stage_timings=[])
    primary = None

    def run(args, **kwargs):
        began = time.monotonic()
        outcome = "FAILED"
        try:
            result = e.command(args, **kwargs)
            outcome = "PASS"
            return result
        finally:
            report["stage_timings"].append(
                {"stage": report["stage"], "seconds": time.monotonic() - began, "outcome": outcome}
            )

    started = report["started_at"]
    report_path = e.ROOT / "reports/control-schema-phase.json"
    schema_publish(report, report_path)
    try:
        historical = "ea1ae98ce9e5e26d5d0d14f3e6d278ecb9efbbad"
        report["stage"] = "observe_source"
        candidate = run(["git", "rev-parse", "HEAD"]).decode().strip()
        report["observed_source"] = candidate
        assert set(request) == {"historical", "candidate", "budget_file"}, "CONTROL_REQUEST_FORMAT"
        assert request["historical"] == historical and request["candidate"] == candidate, (
            "CONTROL_REQUEST_SOURCE"
        )
        report["stage"] = "consume_budget"
        budget = consume_control_budget(Path(request["budget_file"]), historical, candidate)
        report.update(
            coordinator=candidate,
            historical=historical,
            budget_state="VALIDATED_CONSUMED",
            prepare_budget=dict(budget),
        )
        schema_publish(report, report_path)
        assert (
            Path.cwd() == e.ROOT and os.getuid() != 0 and os.environ.get("GITHUB_ACTIONS") == "true"
        ), "CONTROL_DISPOSABLE_RUNNER"
        report["stage"] = "source_check"
        e.source_check(candidate)
        report["stage"] = "daemon_admission"
        assert not run(["docker", "ps", "-aq"]).strip()
        assert not run(["docker", "volume", "ls", "-q"]).strip()
        project = "asm-control-schema-phase"
        owner = SchemaOwnership.inherited(project, candidate)
        report["cleanup"] = {"state": "ADMITTED"}
        pins = dict(
            line.split("=", 1)
            for line in (e.ROOT / "infra/images.lock.env").read_text().splitlines()
            if line and not line.startswith("#")
        )
        with (
            schema_private_workspace(report, "asm-control-schema-") as temporary,
            schema_cleanup_scope(owner, report, report_path),
        ):
            directory = Path(temporary)
            sources, images = {}, {}
            # Only exact tracked archives enter build contexts. The historical-only
            # production migration_build_images helper is deliberately not called for I.
            report["stage"] = "prepare_images"
            prepare_started = time.monotonic()
            remaining = budget["deadline"] - prepare_started
            assert remaining > 0, "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            with e.migration_budget(remaining):
                for source in (historical, candidate):
                    archive = directory / source
                    archive.mkdir()
                    report["stage"] = "archive_" + source[:8]
                    e.migration_build_context(source, archive)
                    sources[source] = archive
                    images[source] = {}
                    for kind in ("runtime", "development"):
                        tag = "asm-control-schema-" + kind + ":" + source
                        reuse = "asm-m3-schema-" + kind + ":" + source
                        existing = (
                            run(["docker", "image", "ls", "-q", "--no-trunc", reuse])
                            .decode()
                            .strip()
                        )
                        if existing:
                            report["stage"] = "reuse_" + source[:8] + "_" + kind
                            e.migration_image(existing, source, kind)
                            run(["docker", "tag", existing, tag])
                        else:
                            report["stage"] = "build_" + source[:8] + "_" + kind
                            run(
                                [
                                    "docker",
                                    "build",
                                    "--pull",
                                    "--network=default",
                                    "--target",
                                    kind,
                                    "--build-arg",
                                    "PYTHON_IMAGE=" + pins["PYTHON_IMAGE"],
                                    "--build-arg",
                                    "UV_IMAGE=" + pins["UV_IMAGE"],
                                    "-f",
                                    str(archive / "infra/Dockerfile.backend"),
                                    "-t",
                                    tag,
                                    str(archive),
                                ],
                                timeout=480,
                            )
                        image_id = json.loads(run(["docker", "image", "inspect", tag]))[0]["Id"]
                        images[source][kind] = image_id
                        report["stage"] = "image_probe_" + source[:8] + "_" + kind
                        report["images"][source + ":" + kind] = e.migration_image(
                            image_id, source, kind
                        )
            prepared_at = time.monotonic()
            report["prepare_budget"] = {
                **budget,
                "candidate_prepare_seconds": prepared_at - prepare_started,
                "charged_total_seconds": 600 - (budget["deadline"] - prepared_at),
                "remaining_seconds": budget["deadline"] - prepared_at,
            }
            assert prepared_at < budget["deadline"], "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            # init_local emits only a fixed diagnostic, never credentials. All private
            # runtime files are outside both source archives and the repository.
            report["stage"] = "runtime_configuration"
            subprocess.run(
                [sys.executable, str(e.ROOT / "scripts/init_local.py")],
                cwd=directory,
                check=True,
                timeout=30,
            )
            compose = [
                "docker",
                "compose",
                "--project-directory",
                str(sources[candidate]),
                "--project-name",
                project,
                "--env-file",
                str(e.ROOT / "infra/images.lock.env"),
                "--env-file",
                str(directory / ".env"),
                "-f",
                str(sources[candidate] / "compose.yaml"),
                "--profile",
                "telegram-operator",
            ]
            model = json.loads(run([*compose, "config", "--format", "json"]))
            variables = dict(model["services"]["api"]["environment"])
            variables.update(model["services"]["migrate"]["environment"])
            assert variables["ASM_TELEGRAM_ENABLED"] == "false" and variables["TG_BOT_TOKEN"] == ""
            envfile = directory / "controller.env"
            e.write_private(
                envfile,
                "".join(k + "=" + str(v) + "\n" for k, v in sorted(variables.items())).encode(),
            )
            state = directory / "state"
            state.mkdir(mode=0o700)
            prefix = [
                "docker",
                "run",
                "--rm",
                "--network",
                project + "_default",
                "--env-file",
                str(envfile),
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--mount",
                f"type=bind,source={state},target=/state",
            ]

            def controller(action):
                report["stage"] = "controller_" + action
                try:
                    output = run(
                        [
                            *prefix,
                            images[candidate]["development"],
                            "python",
                            "tests/test_m3_1_control_migrations.py",
                            "--control-schema-phase",
                            action,
                            "/state/receipt.json",
                        ],
                        timeout=120,
                    )
                except BaseException:
                    failure = state / "controller-failure.json"
                    if failure.exists():
                        report["controller_failure"] = json.loads(e.private_bytes(failure))
                    raise
                assert output.decode().strip() == "CONTROL_SCHEMA_" + action.upper() + "_PASS"
                report["checks"].append(action)

            def migrate(source, direction, revision):
                report["stage"] = direction + "_" + revision
                run(
                    [*prefix, images[source]["development"], "alembic", direction, revision],
                    timeout=30,
                )

            def probe(source, expected):
                report["stage"] = "probe_" + source[:8] + "_" + str(expected)
                code = "import asyncio\nfrom asm.foundation import RuntimeDatabase,Settings\nasync def main():\n d=RuntimeDatabase(Settings())\n try:\n  try: await d.check()\n  except Exception:\n   assert not EXPECTED\n  else: assert EXPECTED\n finally: await d.close()\nasyncio.run(main())\n".replace(
                    "EXPECTED", repr(expected)
                )
                run([*prefix, images[source]["runtime"], "python", "-c", code], timeout=30)

            def callers(source):
                report["stage"] = "callers_" + source[:8]
                run(["docker", "tag", images[source]["runtime"], "asm-backend:local"])
                run(
                    [
                        *compose,
                        "up",
                        "-d",
                        "--no-deps",
                        "--pull",
                        "never",
                        "--force-recreate",
                        "--wait",
                        "api",
                        "worker",
                        "scheduler",
                    ],
                    timeout=120,
                )
                result = {}
                for service in ("api", "worker", "scheduler"):
                    ident = run([*compose, "ps", "-q", service]).decode().strip()
                    info = json.loads(run(["docker", "inspect", ident]))[0]
                    assert info["Image"] == images[source]["runtime"] and info["State"]["Running"]
                    result[service] = {"id": ident, "image": info["Image"], "source": source}
                return result

            def drain():
                report["stage"] = "drain"
                run([*compose, "stop", "--timeout", "10", "api", "worker", "scheduler"], timeout=60)
                for service in ("api", "worker", "scheduler"):
                    ident = run([*compose, "ps", "-aq", service]).decode().strip()
                    assert not json.loads(run(["docker", "inspect", ident]))[0]["State"]["Running"]

            try:
                report["stage"] = "infrastructure"
                run([*compose, "up", "-d", "--wait", "postgres", "storage"], timeout=120)
                run([*compose, "run", "--rm", "--no-deps", "-T", "storage-init"], timeout=120)
                migrate(historical, "upgrade", "0008")
                report["baseline_callers"] = callers(historical)
                probe(historical, True)
                probe(candidate, False)
                drain()
                controller("seed8")  # migration identity only; T runtime is drained.
                report["seed_identity"] = json.loads((state / "receipt.json").read_text())[
                    "identity"
                ]
                # Reject the actual changed helper's direct migration commands before
                # any source/image switch or migration journal on this candidate.
                guard = directory / "guard"
                guard.mkdir(mode=0o700)
                e.write_private(guard / "operation.lock", b"")
                before = {p.name: p.read_bytes() for p in guard.iterdir()}
                for action in ("migration-attest", "migration-prepare"):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(e.ROOT / "scripts/prepare_telegram_egress.py"),
                            action,
                            "--state-dir",
                            str(guard),
                            "--accepted-sha",
                            candidate,
                            "--from-sha",
                            e.MIGRATION_FROM,
                        ],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        timeout=30,
                    )
                    assert (
                        result.returncode == 1
                        and b"EGRESS_MIGRATION_HISTORICAL_SCHEMA_ONLY" in result.stdout
                    )
                    assert {p.name: p.read_bytes() for p in guard.iterdir()} == before
                report["checks"].append("candidate_direct_cli_pairing_refusal")
                migrate(candidate, "upgrade", "0009")
                controller("check9")  # independent committed revision read after migrator exits
                probe(candidate, True)
                probe(historical, False)
                # CONTROL-clean populated-T case: preserve all 34 tables and exact T definitions.
                migrate(candidate, "downgrade", "0008")
                controller("check8")
                probe(historical, True)
                # A separate migrator really commits 0009, then exits unsuccessfully.
                # Observe its failure; NEVER infer the revision from that exit alone.
                report["stage"] = "committed_upgrade_ack_loss"
                lost = subprocess.run(
                    [
                        *prefix,
                        images[candidate]["development"],
                        "python",
                        "tests/test_m3_1_control_migrations.py",
                        "--control-schema-phase",
                        "upgrade-lost-result",
                        "/state/receipt.json",
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=30,
                )

                def observe_revision():
                    return json.loads(
                        run(
                            [
                                *prefix,
                                images[candidate]["development"],
                                "python",
                                "tests/test_m3_1_control_migrations.py",
                                "--control-schema-phase",
                                "observe",
                                "/state/receipt.json",
                            ],
                            timeout=30,
                        )
                    )

                saved_loss = json.loads((state / "receipt.json").read_text())["lost_result_process"]
                report["lost_result_process"] = saved_loss
                recovery_source = control_schema_recovery_source(
                    lost, observe_revision, report, historical, candidate
                )
                controller("check9")  # projection/private S3/pending/UNKNOWN still exact
                probe(historical, False)  # committed0009 explicitly rejects T
                probe(recovery_source, True)
                report["upgrade_ack_loss"]["historical_readiness"] = "REJECTED"
                report["upgrade_ack_loss"]["candidate_readiness"] = "PASS"
                # Exercise C runtime/worker on the correctly paired schema before
                # permanent callers start, so duplicate-first admission is deterministic.
                controller("fresh")
                report["cutover_callers"] = callers(recovery_source)
                report["upgrade_ack_loss"]["forward_callers"] = report["cutover_callers"]
                drain()
                controller("refuse")
                report["restarted_callers"] = callers(recovery_source)
                report["upgrade_ack_loss"]["restarted_callers"] = report["restarted_callers"]
                probe(recovery_source, True)
                drain()
                controller("refuse")
                report["database"] = json.loads((state / "receipt.json").read_text())
                assert report["database"]["populated_refusal"] == "PASS"
                # No raw signed URL or fixture content is published.
                report["database"]["object"].pop("key")
            except BaseException as error:
                schema_record_failure(report, error)
                raise
            finally:
                schema_publish(report, report_path, sys.exception())
        e.source_check(candidate)
        print("TELEGRAM_EGRESS_CONTROL_SCHEMA_PHASE_PASS", flush=True)
    except BaseException as error:
        primary = error
        schema_record_failure(report, error)
        raise
    finally:
        report["total_seconds"] = time.monotonic() - started
        schema_publish(report, report_path, primary)


def consume_guards_budget(path, historical, candidate):
    """One private handoff, absolute monotonic deadline, no inherited/global reset."""
    raw = e.private_bytes(path)
    info = path.stat()
    assert info.st_nlink == 1, "GUARDS_BUDGET_SINGLE_LINK"
    value = e.strict_json(raw)
    assert set(value) == {
        "version",
        "phase",
        "historical",
        "candidate",
        "uid",
        "started_at",
        "issued_at",
        "charged_seconds",
        "deadline",
    }, "GUARDS_BUDGET_FORMAT"
    assert value["version"] == 1 and type(value["version"]) is int, "GUARDS_BUDGET_VERSION"
    assert value["phase"] == GUARDS_PHASE and value["historical"] == historical == GUARDS_C, (
        "GUARDS_BUDGET_PHASE_SOURCE"
    )
    assert (
        value["candidate"] == candidate
        and type(value["uid"]) is int
        and value["uid"] == os.getuid()
    ), "GUARDS_BUDGET_CANDIDATE_OWNER"
    for key in ("started_at", "issued_at", "charged_seconds", "deadline"):
        assert type(value[key]) in (int, float) and 0 < value[key] < float("inf"), (
            "GUARDS_BUDGET_CLOCK"
        )
    assert abs(value["deadline"] - value["started_at"] - 600) < 0.001, "GUARDS_BUDGET_TOTAL"
    assert abs(value["issued_at"] - value["started_at"] - value["charged_seconds"]) < 0.001, (
        "GUARDS_BUDGET_CHARGED"
    )
    now = time.monotonic()
    assert value["issued_at"] <= now < value["deadline"], "GUARDS_BUDGET_EXHAUSTED"
    # Preserve the absolute bound across process startup and handoff delay.
    assert (path.stat().st_dev, path.stat().st_ino) == (info.st_dev, info.st_ino), (
        "GUARDS_BUDGET_FILE_CHANGED"
    )
    path.unlink()
    return {
        **value,
        "handoff_seconds": now - value["issued_at"],
        "remaining_seconds": value["deadline"] - now,
    }


def guards_schema_recovery_source(result, observe, report, historical, candidate):
    detail = {
        "injection": "after_commit_before_success_exit",
        "exit_code": result.returncode,
        "observed": "NOT_READ",
    }
    report["upgrade_ack_loss"] = detail
    assert historical == GUARDS_C
    if result.returncode != 86 or result.stdout.strip() != b"GUARDS_UPGRADE_COMMITTED_RESULT_LOST":
        detail["result"] = "UNEXPECTED_MIGRATOR_RESULT"
        raise AssertionError("GUARDS_EXPECTED_POST_COMMIT_FAILURE")
    detail.update(
        result="CONTROLLED_FAILURE_OBSERVED", marker="GUARDS_UPGRADE_COMMITTED_RESULT_LOST"
    )
    try:
        observation = observe()
    except Exception:
        detail["observed"] = "UNREADABLE"
        raise
    detail["observed"] = observation
    assert observation["revision"] in {"0009", "0010"} and observation["role"] == "asm_migrator"
    assert observation["database"] == "asm_local"
    assert type(observation["reader_pid"]) is int and observation["reader_pid"] > 0
    assert type(observation["backend_pid"]) is int and observation["backend_pid"] > 0
    lost = report.get("lost_result_process")
    assert isinstance(lost, dict) and set(lost) == {
        "namespace",
        "pid",
        "start_ticks",
        "boot_id",
    }, "GUARDS_PROCESS_IDENTITY_REQUIRED"
    assert type(lost["pid"]) is int and lost["pid"] > 0
    assert type(lost["start_ticks"]) is int and lost["start_ticks"] > 0
    assert type(observation["reader_start_ticks"]) is int
    assert observation["reader_boot_id"] == lost["boot_id"] and lost["boot_id"], (
        "GUARDS_RECOVERY_HOST_BOOT"
    )
    # Docker can reuse a released PID namespace inode; PID1 alone is not a
    # process identity. Kernel start ticks prove this reader was created later
    # on the same boot, including that reuse case, and reject the prior process.
    assert observation["reader_start_ticks"] > lost["start_ticks"], "GUARDS_FRESH_PROCESS_REQUIRED"
    for key, value in report["seed_identity"].items():
        assert observation[key] == value, "GUARDS_RECOVERY_DATABASE_IDENTITY"
    source = historical if observation["revision"] == "0009" else candidate
    detail["recovery_source"] = source
    return source


def run_guards_schema_phase(request):
    """New disposable LOCAL volume, exact C/G images, drained GUARDS cutover."""
    report = schema_envelope(request, GUARDS_PHASE)
    report.update(images={}, checks=[], stage_timings=[])
    primary = None

    def run(args, **kwargs):
        began = time.monotonic()
        outcome = "FAILED"
        try:
            result = e.command(args, **kwargs)
            outcome = "PASS"
            return result
        finally:
            report["stage_timings"].append(
                {"stage": report["stage"], "seconds": time.monotonic() - began, "outcome": outcome}
            )

    started = report["started_at"]
    report_path = e.ROOT / "reports/guards-schema-phase.json"
    schema_publish(report, report_path)
    try:
        historical = "c6a55b6b17d1c1ab286ce97dfa4bd27197141fe5"
        report["stage"] = "observe_source"
        candidate = run(["git", "rev-parse", "HEAD"]).decode().strip()
        report["observed_source"] = candidate
        assert set(request) == {"historical", "candidate", "budget_file"}, "CONTROL_REQUEST_FORMAT"
        assert request["historical"] == historical and request["candidate"] == candidate, (
            "CONTROL_REQUEST_SOURCE"
        )
        report["stage"] = "consume_budget"
        budget = consume_guards_budget(Path(request["budget_file"]), historical, candidate)
        report.update(
            coordinator=candidate,
            historical=historical,
            budget_state="VALIDATED_CONSUMED",
            prepare_budget=dict(budget),
        )
        schema_publish(report, report_path)
        assert (
            Path.cwd() == e.ROOT and os.getuid() != 0 and os.environ.get("GITHUB_ACTIONS") == "true"
        ), "CONTROL_DISPOSABLE_RUNNER"
        report["stage"] = "source_check"
        e.source_check(candidate)
        report["stage"] = "daemon_admission"
        assert not run(["docker", "ps", "-aq"]).strip()
        assert not run(["docker", "volume", "ls", "-q"]).strip()
        project = "asm-guards-schema-phase"
        owner = SchemaOwnership.inherited(project, candidate)
        report["cleanup"] = {"state": "ADMITTED"}
        pins = dict(
            line.split("=", 1)
            for line in (e.ROOT / "infra/images.lock.env").read_text().splitlines()
            if line and not line.startswith("#")
        )
        with (
            schema_private_workspace(report, "asm-guards-schema-") as temporary,
            schema_cleanup_scope(owner, report, report_path),
        ):
            directory = Path(temporary)
            sources, images = {}, {}
            # Only exact tracked archives enter build contexts. The historical-only
            # production migration_build_images helper is deliberately not called for I.
            report["stage"] = "prepare_images"
            prepare_started = time.monotonic()
            remaining = budget["deadline"] - prepare_started
            assert remaining > 0, "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            with e.migration_budget(remaining):
                for source in (historical, candidate):
                    archive = directory / source
                    archive.mkdir()
                    report["stage"] = "archive_" + source[:8]
                    e.migration_build_context(source, archive)
                    sources[source] = archive
                    images[source] = {}
                    for kind in ("runtime", "development"):
                        tag = "asm-guards-schema-" + kind + ":" + source
                        reuse = "asm-control-schema-" + kind + ":" + source
                        existing = (
                            run(["docker", "image", "ls", "-q", "--no-trunc", reuse])
                            .decode()
                            .strip()
                        )
                        if existing:
                            report["stage"] = "reuse_" + source[:8] + "_" + kind
                            e.migration_image(existing, source, kind)
                            run(["docker", "tag", existing, tag])
                        else:
                            report["stage"] = "build_" + source[:8] + "_" + kind
                            run(
                                [
                                    "docker",
                                    "build",
                                    "--pull",
                                    "--network=default",
                                    "--target",
                                    kind,
                                    "--build-arg",
                                    "PYTHON_IMAGE=" + pins["PYTHON_IMAGE"],
                                    "--build-arg",
                                    "UV_IMAGE=" + pins["UV_IMAGE"],
                                    "-f",
                                    str(archive / "infra/Dockerfile.backend"),
                                    "-t",
                                    tag,
                                    str(archive),
                                ],
                                timeout=480,
                            )
                        image_id = json.loads(run(["docker", "image", "inspect", tag]))[0]["Id"]
                        images[source][kind] = image_id
                        report["stage"] = "image_probe_" + source[:8] + "_" + kind
                        report["images"][source + ":" + kind] = e.migration_image(
                            image_id, source, kind
                        )
            prepared_at = time.monotonic()
            report["prepare_budget"] = {
                **budget,
                "candidate_prepare_seconds": prepared_at - prepare_started,
                "charged_total_seconds": 600 - (budget["deadline"] - prepared_at),
                "remaining_seconds": budget["deadline"] - prepared_at,
            }
            assert prepared_at < budget["deadline"], "CONTROL_PREPARE_BUDGET_EXHAUSTED"
            # init_local emits only a fixed diagnostic, never credentials. All private
            # runtime files are outside both source archives and the repository.
            report["stage"] = "runtime_configuration"
            subprocess.run(
                [sys.executable, str(e.ROOT / "scripts/init_local.py")],
                cwd=directory,
                check=True,
                timeout=30,
            )
            compose = [
                "docker",
                "compose",
                "--project-directory",
                str(sources[candidate]),
                "--project-name",
                project,
                "--env-file",
                str(e.ROOT / "infra/images.lock.env"),
                "--env-file",
                str(directory / ".env"),
                "-f",
                str(sources[candidate] / "compose.yaml"),
                "--profile",
                "telegram-operator",
            ]
            model = json.loads(run([*compose, "config", "--format", "json"]))
            variables = dict(model["services"]["api"]["environment"])
            variables.update(model["services"]["migrate"]["environment"])
            assert variables["ASM_TELEGRAM_ENABLED"] == "false" and variables["TG_BOT_TOKEN"] == ""
            envfile = directory / "controller.env"
            e.write_private(
                envfile,
                "".join(k + "=" + str(v) + "\n" for k, v in sorted(variables.items())).encode(),
            )
            state = directory / "state"
            state.mkdir(mode=0o700)
            prefix = [
                "docker",
                "run",
                "--rm",
                "--network",
                project + "_default",
                "--env-file",
                str(envfile),
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--mount",
                f"type=bind,source={state},target=/state",
            ]

            def controller(action):
                report["stage"] = "controller_" + action
                try:
                    output = run(
                        [
                            *prefix,
                            images[candidate]["development"],
                            "python",
                            "tests/test_m3_1_guards_migrations.py",
                            "--guards-schema-phase",
                            action,
                            "/state/receipt.json",
                        ],
                        timeout=120,
                    )
                except BaseException:
                    failure = state / "controller-failure.json"
                    if failure.exists():
                        report["controller_failure"] = json.loads(e.private_bytes(failure))
                    raise
                assert output.decode().strip() == "GUARDS_SCHEMA_" + action.upper() + "_PASS"
                report["checks"].append(action)

            def migrate(source, direction, revision):
                report["stage"] = direction + "_" + revision
                run(
                    [*prefix, images[source]["development"], "alembic", direction, revision],
                    timeout=30,
                )

            def probe(source, expected):
                report["stage"] = "probe_" + source[:8] + "_" + str(expected)
                code = "import asyncio\nfrom asm.foundation import RuntimeDatabase,Settings\nasync def main():\n d=RuntimeDatabase(Settings())\n try:\n  try: await d.check()\n  except Exception:\n   assert not EXPECTED\n  else: assert EXPECTED\n finally: await d.close()\nasyncio.run(main())\n".replace(
                    "EXPECTED", repr(expected)
                )
                run([*prefix, images[source]["runtime"], "python", "-c", code], timeout=30)

            def callers(source):
                report["stage"] = "callers_" + source[:8]
                run(["docker", "tag", images[source]["runtime"], "asm-backend:local"])
                run(
                    [
                        *compose,
                        "up",
                        "-d",
                        "--no-deps",
                        "--pull",
                        "never",
                        "--force-recreate",
                        "--wait",
                        "api",
                        "worker",
                        "scheduler",
                    ],
                    timeout=120,
                )
                result = {}
                for service in ("api", "worker", "scheduler"):
                    ident = run([*compose, "ps", "-q", service]).decode().strip()
                    info = json.loads(run(["docker", "inspect", ident]))[0]
                    assert info["Image"] == images[source]["runtime"] and info["State"]["Running"]
                    result[service] = {"id": ident, "image": info["Image"], "source": source}
                return result

            def drain():
                report["stage"] = "drain"
                run([*compose, "stop", "--timeout", "10", "api", "worker", "scheduler"], timeout=60)
                for service in ("api", "worker", "scheduler"):
                    ident = run([*compose, "ps", "-aq", service]).decode().strip()
                    assert not json.loads(run(["docker", "inspect", ident]))[0]["State"]["Running"]

            try:
                report["stage"] = "infrastructure"
                run([*compose, "up", "-d", "--wait", "postgres", "storage"], timeout=120)
                run([*compose, "run", "--rm", "--no-deps", "-T", "storage-init"], timeout=120)
                migrate(historical, "upgrade", "0009")
                report["baseline_callers"] = callers(historical)
                probe(historical, True)
                probe(candidate, False)
                drain()
                controller("seed9")  # migration identity only; T runtime is drained.
                report["seed_identity"] = json.loads((state / "receipt.json").read_text())[
                    "identity"
                ]
                # Reject the actual changed helper's direct migration commands before
                # any source/image switch or migration journal on this candidate.
                guard = directory / "guard"
                guard.mkdir(mode=0o700)
                e.write_private(guard / "operation.lock", b"")
                before = {p.name: p.read_bytes() for p in guard.iterdir()}
                for action in ("migration-attest", "migration-prepare"):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(e.ROOT / "scripts/prepare_telegram_egress.py"),
                            action,
                            "--state-dir",
                            str(guard),
                            "--accepted-sha",
                            candidate,
                            "--from-sha",
                            e.MIGRATION_FROM,
                        ],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        timeout=30,
                    )
                    assert (
                        result.returncode == 1
                        and b"EGRESS_MIGRATION_HISTORICAL_SCHEMA_ONLY" in result.stdout
                    )
                    assert {p.name: p.read_bytes() for p in guard.iterdir()} == before
                report["checks"].append("candidate_direct_cli_pairing_refusal")
                migrate(candidate, "upgrade", "0010")
                migrate(candidate, "upgrade", "0010")  # repeat upgrade is a no-op
                controller("check10")  # independent committed revision read after migrator exits
                probe(candidate, True)
                probe(historical, False)
                # GUARDS-clean populated-C case: preserve all 35 tables and exact C definitions.
                migrate(candidate, "downgrade", "0009")
                controller("check9")
                probe(historical, True)
                # A separate migrator really commits 0010, then exits unsuccessfully.
                # Observe its failure; NEVER infer the revision from that exit alone.
                report["stage"] = "committed_upgrade_ack_loss"
                lost = subprocess.run(
                    [
                        *prefix,
                        images[candidate]["development"],
                        "python",
                        "tests/test_m3_1_guards_migrations.py",
                        "--guards-schema-phase",
                        "upgrade-lost-result",
                        "/state/receipt.json",
                    ],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=30,
                )

                def observe_revision():
                    return json.loads(
                        run(
                            [
                                *prefix,
                                images[candidate]["development"],
                                "python",
                                "tests/test_m3_1_guards_migrations.py",
                                "--guards-schema-phase",
                                "observe",
                                "/state/receipt.json",
                            ],
                            timeout=30,
                        )
                    )

                saved_loss = json.loads((state / "receipt.json").read_text())["lost_result_process"]
                report["lost_result_process"] = saved_loss
                recovery_source = guards_schema_recovery_source(
                    lost, observe_revision, report, historical, candidate
                )
                controller("check10")  # projection/private S3/pending/UNKNOWN still exact
                probe(historical, False)  # committed0010 explicitly rejects T
                probe(recovery_source, True)
                report["upgrade_ack_loss"]["historical_readiness"] = "REJECTED"
                report["upgrade_ack_loss"]["candidate_readiness"] = "PASS"
                # Exercise C runtime/worker on the correctly paired schema before
                # permanent callers start, so duplicate-first admission is deterministic.
                controller("fresh")
                report["cutover_callers"] = callers(recovery_source)
                report["upgrade_ack_loss"]["forward_callers"] = report["cutover_callers"]
                drain()
                controller("refuse")
                report["restarted_callers"] = callers(recovery_source)
                report["upgrade_ack_loss"]["restarted_callers"] = report["restarted_callers"]
                probe(recovery_source, True)
                drain()
                controller("refuse")
                report["database"] = json.loads((state / "receipt.json").read_text())
                assert report["database"]["populated_refusal"] == "PASS"
                # No raw signed URL or fixture content is published.
                report["database"]["object"].pop("key")
            except BaseException as error:
                schema_record_failure(report, error)
                raise
            finally:
                schema_publish(report, report_path, sys.exception())
        e.source_check(candidate)
        print("TELEGRAM_EGRESS_GUARDS_SCHEMA_PHASE_PASS", flush=True)
    except BaseException as error:
        primary = error
        schema_record_failure(report, error)
        raise
    finally:
        report["total_seconds"] = time.monotonic() - started
        schema_publish(report, report_path, primary)


def run_schema_cleanup_negatives(request):
    """Actual daemon/PG negatives; mandatory only in the two existing state lanes."""
    import tempfile

    candidate = request["candidate"]
    assert os.getuid() != 0 and os.environ.get("GITHUB_ACTIONS") == "true"
    e.source_check(candidate)
    positive = json.loads((e.ROOT / "reports/control-schema-phase.json").read_text())
    assert positive["coordinator"] == candidate and positive["historical"] == CONTROL_T
    assert positive["cleanup"]["state"] == "PASS"
    pins = dict(
        line.split("=", 1)
        for line in (e.ROOT / "infra/images.lock.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    results = []
    for fault in ("retained-t-watchdog", "new-c-command-timeout", "new-c-cli-exit"):
        report = schema_envelope(request, "NEGATIVE_" + fault.upper().replace("-", "_"))
        path = e.ROOT / "reports" / ("control-cleanup-" + fault + ".json")
        report["evidence"] = "ACTUAL_DOCKER_POSTGRES"
        schema_publish(report, path)
        with tempfile.TemporaryDirectory(prefix="asm-schema-negative-") as temporary:
            directory = Path(temporary)
            project = "asm-control-negative-" + uuid4().hex[:12]
            source = CONTROL_T if fault.startswith("retained") else candidate
            owner = SchemaOwnership(directory / "owner", project, report["phase"], source)
            owner.admit()
            report["cleanup"] = {"state": "ADMITTED"}
            environment = owner.environment()
            foreign = {}
            checkout = e.ROOT
            added = False
            db = None
            application = "cleanup_" + owner.token

            def run(args, timeout=40):
                return e.command(args, timeout=timeout, environment=environment)

            def real(args, timeout=40):
                return e.command([owner.docker, *args], timeout=timeout)

            def connections(timeout=5):
                return int(
                    real(
                        [
                            "exec",
                            db,
                            "psql",
                            "-U",
                            "postgres",
                            "-d",
                            "asm_cleanup",
                            "-Atqc",
                            "SELECT count(*) FROM pg_stat_activity WHERE application_name='"
                            + application
                            + "'",
                        ],
                        timeout=timeout,
                    )
                )

            def disconnected(cleanup_deadline):
                end = min(time.monotonic() + 3, cleanup_deadline)
                while True:
                    remaining = end - time.monotonic()
                    assert remaining > 0, "CONTROL_CONNECTION_REMAINS"
                    count = connections(timeout=min(5, remaining))
                    if count == 0:
                        return count
                    assert time.monotonic() < end, "CONTROL_CONNECTION_REMAINS"
                    time.sleep(0.02)

            def foreign_proof():
                return {
                    kind: e.sha(real([*command, foreign[kind]]))
                    for kind, command in {
                        "container": ["inspect"],
                        "volume": ["volume", "inspect"],
                        "network": ["network", "inspect"],
                    }.items()
                }

            try:
                try:
                    with schema_cleanup_scope(owner, report, path, disconnected):
                        report["stage"] = "negative_infrastructure"
                        compose_file = directory / "compose.json"
                        compose_file.write_text(
                            json.dumps(
                                {
                                    "services": {
                                        "postgres": {
                                            "image": pins["DB_IMAGE"],
                                            "environment": {
                                                "POSTGRES_HOST_AUTH_METHOD": "trust",
                                                "POSTGRES_DB": "asm_cleanup",
                                            },
                                            "volumes": ["pgdata:/var/lib/postgresql"],
                                            "healthcheck": {
                                                "test": [
                                                    "CMD",
                                                    "pg_isready",
                                                    "-h",
                                                    "127.0.0.1",
                                                    "-U",
                                                    "postgres",
                                                    "-d",
                                                    "asm_cleanup",
                                                ],
                                                "interval": "1s",
                                                "timeout": "2s",
                                                "retries": 20,
                                            },
                                        }
                                    },
                                    "volumes": {"pgdata": {}},
                                }
                            )
                        )
                        compose = [
                            "docker",
                            "compose",
                            "--project-directory",
                            str(directory),
                            "--project-name",
                            project,
                            "-f",
                            str(compose_file),
                        ]
                        run([*compose, "up", "-d", "--pull", "never", "--wait"], timeout=30)
                        db = run([*compose, "ps", "-q", "postgres"]).decode().strip()
                        report["database_container"] = db
                        report["observed_source"] = candidate
                        image = positive["images"][source + ":runtime"]["id"]
                        report.update(executor_source=source, runtime_image=image)
                        # Explicit test-fixture creation after initial-empty admission.
                        # It bypasses the owner wrapper, so cleanup must preserve it.
                        foreign["volume"] = (
                            real(["volume", "create", "asm-foreign-" + owner.token])
                            .decode()
                            .strip()
                        )
                        foreign["network"] = (
                            real(["network", "create", "asm-foreign-" + owner.token])
                            .decode()
                            .strip()
                        )
                        foreign["container"] = (
                            real(
                                [
                                    "create",
                                    "--network",
                                    foreign["network"],
                                    "--mount",
                                    "type=volume,source=" + foreign["volume"] + ",target=/sentinel",
                                    "--label",
                                    "io.asm.foreign-sentinel=" + owner.token,
                                    image,
                                    "python",
                                    "-c",
                                    "pass",
                                ]
                            )
                            .decode()
                            .strip()
                        )
                        report["foreign_ids"] = dict(foreign)
                        report["foreign_before"] = foreign_proof()
                        if source == CONTROL_T:
                            checkout = directory / "frozen-T"
                            e.command(
                                ["git", "worktree", "add", "--detach", str(checkout), CONTROL_T]
                            )
                            added = True
                        report["helper_blob"] = (
                            e.command(
                                ["git", "rev-parse", source + ":scripts/prepare_telegram_egress.py"]
                            )
                            .decode()
                            .strip()
                        )
                        state = directory / "state"
                        state.mkdir(mode=0o700)
                        # A real connection/idle transaction survives the killed host
                        # Docker CLI. PID1 ignores TERM until bounded Docker cleanup.
                        code = (
                            "import os,signal,time,psycopg\nfrom pathlib import Path\n"
                            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                            "c=psycopg.connect('host=postgres dbname=asm_cleanup user=postgres application_name="
                            + application
                            + "',connect_timeout=3)\n"
                            "pid=c.execute('select pg_backend_pid()').fetchone()[0]\n"
                            "Path('/state/connected').write_text(str(pid))\n"
                            "while True: time.sleep(1)\n"
                        )
                        command = [
                            "docker",
                            "run",
                            "--rm",
                            "--network",
                            project + "_default",
                            "--user",
                            f"{os.getuid()}:{os.getgid()}",
                            "--mount",
                            f"type=bind,source={state},target=/state",
                            image,
                            "python",
                            "-c",
                            code,
                        ]
                        report["stage"] = fault
                        failure = None
                        try:
                            if fault == "new-c-command-timeout":
                                # Exact helper.command cancellation boundary: its
                                # subprocess.run kills the CLI, not the daemon PID1.
                                run(command, timeout=3)
                                raise AssertionError("CONTROL_EXPECTED_COMMAND_TIMEOUT")
                            else:
                                if fault == "new-c-cli-exit":
                                    command.insert(3, "-d")
                                child = (
                                    "import sys,time\nfrom pathlib import Path\n"
                                    "from scripts import prepare_telegram_egress as e\n"
                                    "e.command(" + repr(command) + ",timeout=40)\n"
                                )
                                if fault == "new-c-cli-exit":
                                    child += (
                                        "end=time.monotonic()+3\n"
                                        "while not Path("
                                        + repr(str(state / "connected"))
                                        + ").exists():\n"
                                        " assert time.monotonic()<end;time.sleep(.02)\n"
                                        "sys.exit(7)\n"
                                    )
                                result = supervised_schema_child(
                                    [sys.executable, "-c", child],
                                    cwd=checkout,
                                    timeout=5,
                                    environment=environment,
                                )
                                assert result == 7 and fault == "new-c-cli-exit", (
                                    "CONTROL_EXPECTED_CLI_EXIT"
                                )
                                raise subprocess.CalledProcessError(result, ["owned-controller"])
                        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                            failure = error
                            report["expected_failure"] = schema_failure(error)
                            assert (state / "connected").exists(), (
                                "CONTROL_NEGATIVE_NEVER_CONNECTED"
                            )
                            report["backend_pid"] = int((state / "connected").read_text())
                            report["connections_before_cleanup"] = connections()
                            assert report["connections_before_cleanup"] == 1, (
                                "CONTROL_NEGATIVE_CONNECTION_REQUIRED"
                            )
                            infos = json.loads(
                                real(
                                    [
                                        "inspect",
                                        *real(
                                            [
                                                "ps",
                                                "-q",
                                                "--filter",
                                                "label=" + SCHEMA_OWNER_LABEL + "=" + owner.token,
                                            ]
                                        )
                                        .decode()
                                        .split(),
                                    ]
                                )
                            )
                            controllers = [i for i in infos if i["Id"] != db]
                            assert len(controllers) == 1 and controllers[0]["State"]["Running"], (
                                "CONTROL_NEGATIVE_DAEMON_SURVIVOR_REQUIRED"
                            )
                            report["controller_cid"] = controllers[0]["Id"]
                            report["controller_running_after_host_failure"] = True
                            ignored = int(
                                real(
                                    [
                                        "exec",
                                        report["controller_cid"],
                                        "python",
                                        "-c",
                                        "from pathlib import Path;print(next(s.split()[1] for s in Path('/proc/1/status').read_text().splitlines() if s.startswith('SigIgn:')))",
                                    ]
                                ).strip(),
                                16,
                            )
                            assert ignored & (1 << (signal.SIGTERM - 1)), (
                                "CONTROL_TERM_MUST_BE_IGNORED"
                            )
                            report["term_ignored"] = True
                            report["host_cli_processes"] = []
                            for intent_path in owner.directory.glob("run-*.json"):
                                intent = json.loads(intent_path.read_text())
                                proc = Path(f"/proc/{intent['cli_pid']}/stat")
                                try:
                                    stat_fields = proc.read_text().rpartition(")")[2].split()
                                    live = (
                                        stat_fields[0] != "Z"
                                        and int(stat_fields[19]) == intent["cli_start_ticks"]
                                    )
                                except FileNotFoundError:
                                    live = False
                                assert not live, "CONTROL_HOST_CLI_REMAINS"
                                report["host_cli_processes"].append(
                                    {
                                        "pid": intent["cli_pid"],
                                        "start_ticks": intent["cli_start_ticks"],
                                        "live": live,
                                    }
                                )
                            raise
                        finally:
                            if failure is not None:
                                schema_publish(report, path, failure)
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                    assert schema_failure(error) == report["expected_failure"], (
                        "CONTROL_PRIMARY_FAILURE_CHANGED"
                    )
                    assert report["cleanup"]["state"] == "OWNED_REMOVED"
                    assert (
                        report["cleanup"]["diagnostic"]["reason"]
                        == "CONTROL_FOREIGN_RESOURCE_REMAINS"
                    )
                    assert report["cleanup"]["connections_after_controller_stop"] == 0
                    assert report["cleanup"]["owned_remaining"] == []
                    report["foreign_after"] = foreign_proof()
                    assert report["foreign_before"] == report["foreign_after"]
                    assert report["cleanup"]["seconds"] < 90
                    report["result"] = "PASS"
                    results.append(fault)
                    print("CONTROL_CLEANUP_NEGATIVE_PASS " + fault, flush=True)
                finally:
                    # Publish proof before removing these explicitly-created
                    # foreign fixture identities, never via phase ownership.
                    schema_publish(report, path, sys.exception())
                    if foreign.get("container"):
                        real(["rm", "-v", foreign["container"]])
                    if foreign.get("volume"):
                        real(["volume", "rm", foreign["volume"]])
                    if foreign.get("network"):
                        real(["network", "rm", foreign["network"]])
                    if added:
                        assert not e.command(
                            [
                                "git",
                                "-C",
                                str(checkout),
                                "status",
                                "--porcelain",
                                "--untracked-files=all",
                            ]
                        ).strip()
                        e.command(["git", "worktree", "remove", str(checkout)])
            finally:
                schema_publish(report, path, sys.exception())
    assert results == ["retained-t-watchdog", "new-c-command-timeout", "new-c-cli-exit"]
    assert not e.command(["docker", "ps", "-aq"]).strip()
    assert not e.command(["docker", "volume", "ls", "-q"]).strip()
    e.source_check(candidate)
    (e.ROOT / "reports/control-cleanup-negatives.json").write_text(
        json.dumps(
            {
                "candidate": candidate,
                "evidence": "ACTUAL_DOCKER_POSTGRES",
                "results": results,
                "result": "PASS",
                "count": len(results),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__schema_docker__":
    schema_docker_cli(globals()["ownership_file"], globals()["docker_args"])
    raise SystemExit(0)


if __name__ == "__control_cleanup_negatives__":
    run_schema_cleanup_negatives(globals()["control_cleanup_request"])
    raise SystemExit(0)


if __name__ == "__control_coordinator__":
    run_control_coordinator(globals()["control_coordinator_request"])
    raise SystemExit(0)


if __name__ == "__schema_harness__":
    if "guards_schema_request" in globals():
        run_guards_schema_phase(globals()["guards_schema_request"])
    elif "control_schema_request" in globals():
        run_control_schema_phase(globals()["control_schema_request"])
    else:
        run_schema_phase(globals()["schema_request"])
    raise SystemExit(0)


if __name__ == "__migration_harness__":
    run_disposable(globals()["fixture"])
    raise SystemExit(0)

import pytest  # noqa: E402 -- host harness uses only stdlib; default collection remains ordinary.

OWNER_RECEIPT_NAMES = (
    "asm-telegram-discovery-0b7e24ee.json",
    "asm-telegram-owner-id-correction-0b7e24ee.json",
    "asm-telegram-discovery-owner2-0b7e24ee.json",
    "asm-telegram-queue-diagnostic-owner2-0b7e24ee.json",
    "asm-telegram-discovery-fresh-owner2-0b7e24ee.json",
    "asm-telegram-binding-owner2-0b7e24ee.json",
    "asm-telegram-connection-diagnostic-owner2-0b7e24ee.json",
    "asm-telegram-binding-after-diagnostic-owner2-0b7e24ee.json",
    "asm-telegram-queue-routes-owner2-0b7e24ee.json",
    OWNER_ACK_INTENT,
    "asm-telegram-ack-old-lifecycle-owner2-0b7e24ee.json",
    "asm-telegram-ack-dependency-diagnostic-owner2-0b7e24ee.json",
    "asm-telegram-egress-segments-owner2-0b7e24ee.json",
    "asm-telegram-tls-budget-owner2-0b7e24ee.json",
    "asm-telegram-tls-budget-fixed-owner2-0b7e24ee.json",
)


@pytest.fixture
def owner_receipt_dag(tmp_path):
    """Issued names/topology, anonymous bytes; no owner files or runtime access."""
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    e.write_private(directory / "deployment-before.json", b'{"synthetic":"baseline"}\n')
    staged = tmp_path / "telegram.env"
    e.write_private(staged, b"synthetic staged input\r\n")
    common = {
        "source_sha": e.MIGRATION_FROM,
        "source_tree": e.MIGRATION_FROM_TREE,
        "original_before_sha256": e.sha((directory / "deployment-before.json").read_bytes()),
    }
    paths = [tmp_path / name for name in OWNER_RECEIPT_NAMES]
    values = {}
    for i, path in enumerate(paths):
        value = dict(common, status="DIAGNOSTIC_COMPLETE")
        if i == 1:
            value["prior_attempt_sha256"] = e.sha(paths[0].read_bytes())
        elif i == 2:
            value["owner_correction_sha256"] = e.sha(paths[1].read_bytes())
        elif i > 2:
            value["prior_receipts_sha256"] = {p.name: e.sha(p.read_bytes()) for p in paths[:i]}
        if i in (5, 7):
            value.update(status="BINDING_COMMITTED", preservation_pass=True)
        if path.name == OWNER_ACK_INTENT:
            value["status"] = "OWNER_APPROVED_PREFIX_INTENT"
        if i == 10:
            value["status"] = "NOT_ATTEMPTED"
        if i == 14:
            value.update(
                preservation_pass=True,
                staged_sha256=e.sha(staged.read_bytes()),
                operator_image_id="sha256:" + "1" * 64,
            )
        values[path.name] = value
        e.write_private(path, e.encoded(value))
    return SimpleNamespace(
        directory=directory,
        paths=paths,
        values=values,
        last=paths[-1],
        pin=e.sha(paths[-1].read_bytes()),
        state={"telegram_env": str(staged)},
    )


def receipt_inventory(directory):
    return {
        str(p.relative_to(directory)): (
            p.lstat().st_mode,
            p.lstat().st_uid,
            os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None,
        )
        for p in directory.rglob("*")
    }


@pytest.mark.parametrize("as_root", [False, True])
def test_historical_owner_intent_preserves_complete_receipt_dag(
    owner_receipt_dag, monkeypatch, as_root
):
    m = owner_receipt_dag
    if as_root:
        # Exercise the current/root basename check independently of parent keys.
        root = m.last.with_name("asm-telegram-tls-budget-fixed-owner2-0b7e24ee.intent.json")
        m.last.rename(root)
        m.paths[-1] = m.last = root
    original = {str(p): p.read_bytes() for p in m.paths}
    before = receipt_inventory(m.directory.parent)

    def forbidden(*_args, **_kwargs):
        pytest.fail("receipt reader attempted a write or external command")

    monkeypatch.setattr(e, "write_private", forbidden)
    monkeypatch.setattr(e, "command", forbidden)
    files, image = e.migration_receipts(m.last, m.pin, m.state, m.directory)
    assert files == original and len(files) == 15
    assert str(m.directory.parent / OWNER_ACK_INTENT) in files
    assert image == "sha256:" + "1" * 64
    assert receipt_inventory(m.directory.parent) == before


@pytest.mark.parametrize("damage", ["tamper", "missing"])
@pytest.mark.parametrize("name", OWNER_RECEIPT_NAMES)
def test_owner_receipt_dag_requires_every_original_byte(
    owner_receipt_dag, monkeypatch, name, damage
):
    m = owner_receipt_dag
    path = m.directory.parent / name
    if damage == "tamper":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path.unlink()
    assert_receipt_stop(m, monkeypatch, (e.EgressError, FileNotFoundError))


def assert_receipt_stop(m, monkeypatch, error=e.EgressError, match=None):
    before = receipt_inventory(m.directory.parent)

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid receipt caused a write or external command")

    monkeypatch.setattr(e, "write_private", forbidden)
    monkeypatch.setattr(e, "command", forbidden)
    with pytest.raises(error, match=match):
        e.migration_receipts(m.last, m.pin, m.state, m.directory)
    assert receipt_inventory(m.directory.parent) == before
    assert not (m.directory / "migration-v3").exists()


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../intent.json",
        "/intent.json",
        "sub/intent.json",
        r"sub\intent.json",
        "intent..json",
        "intent.intent.intent.json",
        "intent.other.json",
        ".intent.json",
        "intent.json.bak",
        "intent.INTENT.json",
        "intent_.json",
        "intent.json\n",
    ],
)
def test_owner_receipt_rejects_unsafe_parent_names(owner_receipt_dag, monkeypatch, name):
    m = owner_receipt_dag
    last = m.values[m.last.name]
    last["prior_receipts_sha256"][name] = last["prior_receipts_sha256"].pop(OWNER_ACK_INTENT)
    e.write_private(m.last, e.encoded(last))
    m.pin = e.sha(m.last.read_bytes())
    assert_receipt_stop(m, monkeypatch, match="EGRESS_MIGRATION_RECEIPT_PATH")


@pytest.mark.parametrize(
    "name",
    [
        "intent..json",
        "intent.other.json",
        "intent.intent.intent.json",
        ".intent.json",
        "intent.json.bak",
    ],
)
def test_owner_receipt_rejects_unsafe_current_names(owner_receipt_dag, monkeypatch, name):
    m = owner_receipt_dag
    path = m.last.with_name(name)
    m.last.rename(path)
    m.last = path
    assert_receipt_stop(m, monkeypatch, match="EGRESS_MIGRATION_RECEIPT_PATH")


@pytest.mark.parametrize(
    "field",
    ["source_sha", "source_tree", "original_before_sha256", "staged_sha256", "preservation_pass"],
)
def test_owner_receipt_retains_source_baseline_and_staged_bindings(
    owner_receipt_dag, monkeypatch, field
):
    m = owner_receipt_dag
    last = m.values[m.last.name]
    last[field] = "changed"
    e.write_private(m.last, e.encoded(last))
    m.pin = e.sha(m.last.read_bytes())
    assert_receipt_stop(m, monkeypatch, match="EGRESS_MIGRATION_(RECEIPT_SOURCE|LAST_RECEIPT)")


@pytest.mark.parametrize(
    "damage", ["pin", "hash", "legacy-attempt", "legacy-correction", "mode", "symlink", "size"]
)
def test_owner_receipt_retains_hash_and_private_guards(owner_receipt_dag, monkeypatch, damage):
    m = owner_receipt_dag
    intent = m.directory.parent / OWNER_ACK_INTENT
    last = m.values[m.last.name]
    if damage == "pin":
        m.pin = "0" * 64
    elif damage == "mode":
        intent.chmod(0o644)
    elif damage == "symlink":
        other = intent.with_name("same-bytes.json")
        intent.rename(other)
        intent.symlink_to(other)
    elif damage == "size":
        intent.write_bytes(b" " * 65537)
    else:
        if damage == "hash":
            last["prior_receipts_sha256"][OWNER_ACK_INTENT] = "0" * 64
        else:
            key = (
                "prior_attempt_sha256" if damage == "legacy-attempt" else "owner_correction_sha256"
            )
            last[key] = "0" * 64
        e.write_private(m.last, e.encoded(last))
        m.pin = e.sha(m.last.read_bytes())
    assert_receipt_stop(m, monkeypatch)


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
            if "rev-parse" in argv:
                return b"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\n"
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
    originals = {name: getattr(e, name) for name in ("migration_saved", "migration_prepared")}
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    bundle = directory / "migration-v3"
    bundle.mkdir(mode=0o700)
    old = {"version": 2, "source_sha": e.MIGRATION_FROM, "generation": "recovery-v2"}
    before_images = {n: "sha256:" + "1" * 64 for n in (*e.MIGRATION_SERVICES, "telegram-operator")}
    after_images = {n: "sha256:" + "2" * 64 for n in before_images}
    before_images["telegram-operator"] = "sha256:" + "3" * 64
    after_images["telegram-operator"] = "sha256:" + "4" * 64
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
        originals=originals,
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


@pytest.fixture(params=[e.MIGRATION_FROM, e.HISTORICAL_OPERATOR])
def provenance_machine(migration_machine, tmp_path, monkeypatch, request):
    """Real preparation/archive/receipts/probes; Git and Docker are external fixtures.

    The synthetic 128-file historical image has an independently fixed fixture
    digest. CI separately asserts the production constant against the real archive.
    No production validator is stubbed for source/proof/receipt/image inventory.
    """
    m = migration_machine
    real_command, machine_command = subprocess.run, e.command
    m.operator_source = request.param
    target = m.args.accepted_sha
    roots = [tmp_path / "candidate", tmp_path / "predecessor"]
    for root in roots:
        root.mkdir(mode=0o700)
        e.write_private(root / ".env", b"SYNTHETIC=private\n")
    monkeypatch.setattr(e, "ROOT", roots[0])
    m.trees = {
        e.MIGRATION_FROM: e.MIGRATION_FROM_TREE,
        e.HISTORICAL_OPERATOR: e.HISTORICAL_OPERATOR_TREE,
        target: m.plan["to_tree"],
    }
    historical = {f"backend/file{i}.py": f"value={i}\n".encode() for i in range(60)}
    historical.update({f"tests/file{i}.py": b"# synthetic\n" for i in range(61)})
    historical.update(
        {
            p: b"# original\n"
            for p in (
                "migrations/revision.py",
                "pyproject.toml",
                "uv.lock",
                "alembic.ini",
                "scripts/ci.sh",
                "scripts/provision_telegram_test.py",
                "infra/postgres/ensure_m1_3_prerequisites.sh",
            )
        }
    )
    assert len(historical) == 128

    def blob(data):
        return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

    monkeypatch.setattr(
        e,
        "HISTORICAL_OPERATOR_MANIFEST",
        e.sha(e.encoded({p: blob(v) for p, v in historical.items()})),
    )
    historical.update(
        {
            p: b"# frozen build input\n"
            for p in ("infra/Dockerfile.backend", "infra/images.lock.env", "compose.yaml")
        }
    )
    operational = dict(historical)
    operational.update(
        {
            p: b"# operational addition\n"
            for p in (
                "scripts/prepare_telegram_egress.py",
                "scripts/test_telegram_egress.sh",
                "tests/test_telegram_egress.py",
                "tests/test_telegram_egress_postgres.py",
            )
        }
    )
    operational["scripts/ci.sh"] = b"# operational CI\n"
    candidate = dict(operational, **{"backend/file0.py": b"# target client\n"})
    m.sources = {
        e.HISTORICAL_OPERATOR: historical,
        e.MIGRATION_FROM: operational,
        target: candidate,
    }
    m.image_roots, m.tags, m.probes, m.builds = {}, {}, [], []
    m.inspect_drift = {}

    def command(argv, **kwargs):
        if argv[0] == "git":
            if "rev-parse" in argv:
                return m.trees[argv[-1].removesuffix("^{tree}")].encode()
            if "ls-files" in argv:
                return b""
            assert "ls-tree" in argv
            source = argv[argv.index("--") - 1]
            selected = argv[argv.index("--") + 1 :]
            return b"".join(
                ("100644 blob " + blob(data) + "\t" + path + "\0").encode()
                for path, data in sorted(m.sources[source].items())
                if any(path == p or path.startswith(p + "/") for p in selected)
            )
        if argv[:3] == ["docker", "image", "inspect"]:
            identity = m.tags.get(argv[3], argv[3])
            assert identity in m.image_roots
            return e.encoded(
                [{"Id": identity, "Os": "linux", "Architecture": "amd64", **m.inspect_drift}]
            )
        if argv[:3] == ["docker", "image", "ls"]:
            return m.tags.get(argv[-1], "").encode()
        if argv[:2] == ["docker", "tag"]:
            m.tags[argv[3]] = argv[2]
            return b""
        if argv[:2] == ["docker", "run"]:
            assert argv[2:6] == ["--rm", "--network", "none", "--read-only"]
            image = argv[-4]
            assert image in m.image_roots and argv[-3:-1] == ["-B", "-c"]
            probe = argv[-1].replace(
                "pathlib.Path('/app')", "pathlib.Path(" + repr(str(m.image_roots[image])) + ")"
            )
            m.probes.append(image)
            result = real_command(
                [sys.executable, "-B", "-c", probe], capture_output=True, timeout=10
            )
            e.require(result.returncode == 0, "EGRESS_COMMAND_FAILED")
            return result.stdout
        return machine_command(argv, **kwargs)

    monkeypatch.setattr(e, "command", command)
    for side, source in (("before", e.MIGRATION_FROM), ("after", target)):
        for name, identity in m.ready[side + "_images"].items():
            if identity in m.image_roots:
                continue
            origin = (
                m.operator_source if side == "before" and name == "telegram-operator" else source
            )
            kind = "development" if name == "telegram-operator" else "runtime"
            _, inventory = e.migration_inventory(origin, kind)
            folder = tmp_path / ("image-" + identity[-1])
            folder.mkdir()
            for path in inventory:
                dest = folder / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(m.sources[origin][path])
            m.image_roots[identity] = folder
            m.tags[side + "-" + kind] = identity
    for name, function in m.originals.items():
        monkeypatch.setattr(e, name, function)
    monkeypatch.setattr(e, "migration_source", lambda value: m.trees[value])
    monkeypatch.setattr(e, "migration_predecessor_checkout", lambda _: roots[1])
    monkeypatch.setattr(e, "verify_state_contents", lambda *_: None)
    monkeypatch.setattr(e, "transition_relay", lambda *_: {"status": "running"})
    monkeypatch.setattr(
        e,
        "checked_model",
        lambda *_: {
            "services": {
                n: {"image": "before-" + ("development" if n == "telegram-operator" else "runtime")}
                for n in e.CALLERS
            }
        },
    )
    monkeypatch.setattr(e, "runtime_snapshot", lambda *_: copy.deepcopy(m.runtime))
    monkeypatch.setattr(
        e,
        "compare_deployment",
        lambda before, after, _: e.require(before == after, "FIXTURE_RUNTIME"),
    )

    def build(source, tree):
        assert (source, tree) == (target, m.trees[target])
        m.builds.append(source)
        images = {kind: m.tags["after-" + kind] for kind in ("runtime", "development")}
        for kind, image in images.items():
            e.migration_image(image, source, kind)
        return {k: "after-" + k for k in images}, images

    monkeypatch.setattr(e, "migration_build_images", build)
    for path in m.bundle.iterdir():
        path.unlink()
    m.bundle.rmdir()
    staged, profile = tmp_path / "telegram.env", tmp_path / "profile.json"
    e.write_private(staged, b"# staged private fixture\n")
    e.write_private(profile, b"{}\n")
    legacy = {"version": 1, "source_sha": e.LEGACY_SHA}
    before = e.encoded(m.runtime)
    m.old.update(
        uid=os.getuid(),
        gid=os.getgid(),
        project="synthetic",
        telegram_env=str(staged),
        profile=str(profile),
        legacy_state_sha256=e.sha(e.encoded(legacy)),
        recovery_before_sha256=e.sha(before),
    )
    for name in ("recovery-v1", "recovery-v2"):
        (m.directory / name).mkdir(mode=0o700)
    originals = {
        "state.json": e.encoded(m.old),
        "deployment-before.json": before,
        "deployment-after.json": before,
        "recovery-v1/state.json": e.encoded(legacy),
        "recovery-v2/state.json": e.encoded(m.old),
        "recovery-v1/deployment-before.json": before,
        "recovery-v1/inputs.json": e.encoded(e.input_hashes(m.old)),
        "recovery-v1/transition.json": e.encoded(
            {"from_sha": e.LEGACY_SHA, "accepted_sha": e.MIGRATION_FROM}
        ),
        "recovery.json": e.encoded(
            {
                "from_sha": e.LEGACY_SHA,
                "source_sha": e.MIGRATION_FROM,
                "original_before_sha256": e.sha(before),
                "after_sha256": e.sha(before),
                "legacy_state_sha256": m.old["legacy_state_sha256"],
                "mapping_readiness_preservation": "PASS",
            }
        ),
    }
    for name in ("config.json", "runtime.json", "route.env"):
        originals[name] = originals["recovery-v1/" + name] = b"{}\n"
    for name, data in originals.items():
        e.write_private(m.directory / name, data)
    common = {
        "source_sha": e.MIGRATION_FROM,
        "source_tree": e.MIGRATION_FROM_TREE,
        "original_before_sha256": e.sha(before),
    }
    intent = tmp_path / OWNER_ACK_INTENT
    receipt = tmp_path / "asm-telegram-binding-fixture.json"
    e.write_private(intent, e.encoded(dict(common, status="NOT_ATTEMPTED")))
    e.write_private(
        receipt,
        e.encoded(
            dict(
                common,
                status="BINDING_COMMITTED",
                preservation_pass=True,
                staged_sha256=e.sha(staged.read_bytes()),
                operator_image_id=m.ready["before_images"]["telegram-operator"],
                prior_receipts_sha256={intent.name: e.sha(intent.read_bytes())},
            )
        ),
    )
    m.args.predecessor_checkout = str(roots[1])
    m.args.operator_receipt = str(receipt)
    m.args.operator_receipt_sha256 = e.sha(receipt.read_bytes())
    m.args.predecessor_operator_sha = (
        m.operator_source if m.operator_source == e.HISTORICAL_OPERATOR else None
    )
    m.receipt = receipt
    e.migration_prepare(m.args, m.directory)
    m.plan.clear()
    m.plan.update(json.loads((m.bundle / "preparation.json").read_bytes()))
    m.ready.clear()
    m.ready.update(json.loads((m.bundle / "prepared.json").read_bytes()))
    m.args.predecessor_operator_sha = None  # Every repeat must recover the saved choice.
    m.saved = {p: Path(p).read_bytes() for p in m.plan["files"]}
    return m


def test_operator_provenance_prepare_default_and_explicit_choice(provenance_machine):
    m = provenance_machine
    assert m.plan["version"] == 2 and len(m.builds) == 1
    assert m.plan["predecessor_operator_sha"] == m.operator_source
    proof = m.plan["image_proofs"]["telegram-operator"]
    assert (
        proof["source_sha"] == m.operator_source
        and proof["source_tree"] == m.trees[m.operator_source]
    )
    assert all(
        m.plan["image_proofs"][n]["source_sha"] == e.MIGRATION_FROM for n in e.MIGRATION_SERVICES
    )
    if m.operator_source == e.HISTORICAL_OPERATOR:
        with pytest.raises(e.EgressError, match="EGRESS_COMMAND_FAILED"):
            e.migration_image(proof["id"], e.MIGRATION_FROM, "development")
        assert proof["blobs_sha256"] == e.HISTORICAL_OPERATOR_MANIFEST
    e.migration_attest(m.args, m.directory)
    e.migration_prepare(m.args, m.directory)
    assert len(m.builds) == 1 and not m.effects
    assert all(Path(p).read_bytes() == raw for p, raw in m.saved.items())


@pytest.mark.parametrize("boundary", ["api-image", "state"])
def test_saved_provenance_survives_interrupted_both_directions(
    provenance_machine, monkeypatch, boundary
):
    m = provenance_machine
    preparation = (m.bundle / "preparation.json").read_bytes()
    for reverse in (False, True):
        interrupt_migration(m, monkeypatch, boundary, reverse=reverse)
        e.migration_switch(m.args, m.directory, reverse=reverse)
        e.migration_switch(m.args, m.directory, reverse=reverse)
        if not reverse:
            e.migration_switch(m.args, m.directory, readonly=True)
    assert len(m.effects) == 4 and (m.bundle / "preparation.json").read_bytes() == preparation
    assert all(Path(p).read_bytes() == raw for p, raw in m.saved.items())


def test_saved_provenance_allows_partial_rollback(provenance_machine, monkeypatch):
    m = provenance_machine
    interrupt_migration(m, monkeypatch, "api-image")
    e.migration_switch(m.args, m.directory, reverse=True)
    e.migration_switch(m.args, m.directory, reverse=True)
    assert m.effects == [("after", "api"), ("before", "api")]
    assert m.runtime["worker"] == m.plan["before"]["worker"]
    assert all(Path(p).read_bytes() == raw for p, raw in m.saved.items())


@pytest.mark.parametrize(
    "drift",
    [
        "source",
        "tree",
        "kind",
        "id",
        "manifest",
        "role",
        "request",
        "missing",
        "extra",
        "changed",
        "inspect",
        "coherent-choice",
        "coherent-id",
        "target-proof",
        "legacy-choice",
    ],
)
def test_provenance_drift_stops_before_effects(provenance_machine, drift):
    m = provenance_machine
    proof = m.plan["image_proofs"]["telegram-operator"]
    if drift in {"source", "tree", "kind", "id", "manifest"}:
        field = {"source": "source_sha", "tree": "source_tree", "manifest": "blobs_sha256"}.get(
            drift, drift
        )
        proof[field] = "foreign"
    elif drift == "role":
        m.plan["image_proofs"]["api"] = dict(proof)
    elif drift == "request":
        m.args.predecessor_operator_sha = "b" * 40
    elif drift in {"missing", "extra", "changed"}:
        folder = m.image_roots[proof["id"]]
        path = folder / "tests/file0.py"
        if drift == "missing":
            path.unlink()
        elif drift == "extra":
            (folder / "tests/extra.py").write_bytes(b"extra")
        else:
            path.write_bytes(path.read_bytes() + b"\n")
    elif drift == "inspect":
        m.inspect_drift["Id"] = "sha256:" + "9" * 64
    elif drift == "coherent-choice":
        other = (
            e.MIGRATION_FROM
            if m.operator_source == e.HISTORICAL_OPERATOR
            else e.HISTORICAL_OPERATOR
        )
        m.plan["predecessor_operator_sha"] = other
        m.plan["image_proofs"]["telegram-operator"] = e.migration_image_expected(
            proof["id"], other, "development"
        )
    elif drift == "coherent-id":
        other = m.ready["after_images"]["telegram-operator"]
        m.plan["before_images"]["telegram-operator"] = other
        proof["id"] = other
        m.ready["before_images"]["telegram-operator"] = other
    elif drift == "target-proof":
        m.ready["image_proofs"]["telegram-operator"]["source_sha"] = e.MIGRATION_FROM
    else:
        del m.plan["predecessor_operator_sha"]
    # An attacker can recompute local hashes; they still cannot change the
    # independently pinned root image or the image's actual copied Git bytes.
    m.ready["preparation_sha256"] = e.sha(e.encoded(m.plan))
    e.write_private(m.bundle / "preparation.json", e.encoded(m.plan))
    e.write_private(m.bundle / "prepared.json", e.encoded(m.ready))
    inventory = receipt_inventory(m.directory)
    with pytest.raises(e.EgressError):
        e.migration_switch(m.args, m.directory)
    assert not m.effects and receipt_inventory(m.directory) == inventory


def test_legacy_preparation_is_only_exact_operational_source(provenance_machine):
    m = provenance_machine
    m.plan["version"] = 1
    m.plan.pop("predecessor_operator_sha")
    m.plan["image_proofs"] = {
        p["id"]: {k: v for k, v in p.items() if k != "source_tree"}
        for p in m.plan["image_proofs"].values()
    }
    m.ready.pop("image_proofs")
    m.ready["preparation_sha256"] = e.sha(e.encoded(m.plan))
    e.write_private(m.bundle / "preparation.json", e.encoded(m.plan))
    e.write_private(m.bundle / "prepared.json", e.encoded(m.ready))
    if m.operator_source == e.HISTORICAL_OPERATOR:
        with pytest.raises(e.EgressError, match="IMAGE_PROOF_CHANGED"):
            e.migration_prepared(m.directory)
    else:
        e.migration_switch(m.args, m.directory)
        e.migration_switch(m.args, m.directory, reverse=True)
        assert len(m.effects) == 4


def test_initial_attest_never_infers_historical_choice(provenance_machine):
    m = provenance_machine
    archive = m.directory.parent / "saved-preparation"
    m.bundle.rename(archive)
    before = receipt_inventory(m.directory)
    try:
        if m.operator_source == e.HISTORICAL_OPERATOR:
            with pytest.raises(e.EgressError, match="EGRESS_COMMAND_FAILED"):
                e.migration_attest(m.args, m.directory)
            m.args.predecessor_operator_sha = e.HISTORICAL_OPERATOR
        result = e.migration_attest(m.args, m.directory)
        assert result[5]["telegram-operator"]["source_sha"] == m.operator_source
        for invalid_source in ("", "b" * 40):
            m.args.predecessor_operator_sha = invalid_source
            with pytest.raises(e.EgressError, match="EGRESS_MIGRATION_OPERATOR_SOURCE"):
                e.migration_attest(m.args, m.directory)
        assert not m.effects and receipt_inventory(m.directory) == before
    finally:
        archive.rename(m.bundle)


@pytest.mark.parametrize("phase", ["partial-forward", "forward", "partial-rollback", "rollback"])
@pytest.mark.parametrize("drift", ["request", "coherent-choice"])
def test_repeat_provenance_drift_never_adds_effects(provenance_machine, monkeypatch, phase, drift):
    m = provenance_machine
    if phase == "partial-forward":
        interrupt_migration(m, monkeypatch, "api-image")
    else:
        e.migration_switch(m.args, m.directory)
    if phase == "partial-rollback":
        interrupt_migration(m, monkeypatch, "api-image", reverse=True)
    elif phase == "rollback":
        e.migration_switch(m.args, m.directory, reverse=True)
    other = (
        e.MIGRATION_FROM if m.operator_source == e.HISTORICAL_OPERATOR else e.HISTORICAL_OPERATOR
    )
    if drift == "request":
        m.args.predecessor_operator_sha = other
    else:
        plan = json.loads((m.bundle / "preparation.json").read_bytes())
        plan["predecessor_operator_sha"] = other
        image = plan["before_images"]["telegram-operator"]
        plan["image_proofs"]["telegram-operator"] = e.migration_image_expected(
            image, other, "development"
        )
        ready = json.loads((m.bundle / "prepared.json").read_bytes())
        ready["preparation_sha256"] = e.sha(e.encoded(plan))
        intent = json.loads((m.bundle / "intent.json").read_bytes())
        intent.update(
            preparation_sha256=ready["preparation_sha256"], prepared_sha256=e.sha(e.encoded(ready))
        )
        for name, value in (
            ("preparation.json", plan),
            ("prepared.json", ready),
            ("intent.json", intent),
        ):
            e.write_private(m.bundle / name, e.encoded(value))
    effects, before = list(m.effects), receipt_inventory(m.directory)
    with pytest.raises(e.EgressError, match="EGRESS_(COMMAND_FAILED|MIGRATION_REQUEST_CHANGED)"):
        e.migration_switch(
            m.args, m.directory, reverse=phase.endswith("rollback"), readonly=phase == "forward"
        )
    assert m.effects == effects and receipt_inventory(m.directory) == before


@pytest.mark.parametrize("drift", ["source", "tree", "manifest", "count", "delta", "frozen"])
def test_historical_source_pins_are_independent_of_saved_proofs(
    provenance_machine, monkeypatch, drift
):
    m = provenance_machine
    source = e.HISTORICAL_OPERATOR
    if drift == "source":
        source = "a" * 40
    elif drift == "tree":
        m.trees[source] = "a" * 40
    elif drift == "manifest":
        m.sources[source]["tests/file0.py"] = b"foreign\n"
    elif drift == "count":
        del m.sources[source]["tests/file0.py"]
        _, inventory = e.migration_inventory(source, "development")
        monkeypatch.setattr(e, "HISTORICAL_OPERATOR_MANIFEST", e.sha(e.encoded(inventory)))
    elif drift == "delta":
        m.sources[e.MIGRATION_FROM]["scripts/foreign.sh"] = b"foreign\n"
    else:
        m.sources[source]["infra/Dockerfile.backend"] = b"foreign\n"
    with pytest.raises(e.EgressError, match="EGRESS_MIGRATION_OPERATOR_"):
        e.migration_operator_source(source)
    assert not m.effects


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


@pytest.mark.parametrize(
    "revision,versions",
    [
        ("0008", 8),
        ("9999", 7),
        ("0007", 8),
        ("0007", 6),
    ],
)
@pytest.mark.parametrize("saved", [False, True])
def test_candidate_historical_guard_rejects_mixed_schema_before_effects(
    tmp_path, monkeypatch, revision, versions, saved
):
    source = "e" * 40
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    bundle = directory / "migration-v3"
    bundle.mkdir(mode=0o700)
    e.write_private(
        bundle / "preparation.json",
        e.encoded(
            {
                "version": 2,
                "from_sha": e.MIGRATION_FROM,
                "from_tree": e.MIGRATION_FROM_TREE,
                "to_sha": source,
                "to_tree": "a" * 40,
            }
        ),
    )
    before = receipt_inventory(directory)
    reads = []

    def command(args, **kwargs):
        reads.append(args)
        assert args[0] == "git", "schema refusal must precede Docker/build/recreate"
        if "show" in args:
            return f'DATABASE_SCHEMA_REVISION = "{revision}"\n'.encode()
        if "ls-tree" in args:
            return "\n".join(
                f"migrations/versions/{i:04d}_revision.py" for i in range(1, versions + 1)
            ).encode()
        pytest.fail("schema refusal must precede other migration work")

    monkeypatch.setattr(e, "source_check", lambda value: value == source)
    monkeypatch.setattr(e, "command", command)
    with pytest.raises(e.EgressError, match="EGRESS_MIGRATION_HISTORICAL_SCHEMA_ONLY"):
        e.migration_saved(directory) if saved else e.migration_source(source)
    assert reads and receipt_inventory(directory) == before
    assert not (bundle / "intent.json").exists()


@pytest.mark.parametrize("revision", ["0007", "0008"])
@pytest.mark.parametrize("damage", ["missing", "extra", "same-count", "wrong-revision"])
def test_revision_qualified_inventory_rejects_names_not_only_counts(revision, damage):
    names = set(e.SCHEMA_TABLES[revision])
    e.schema_inventory(revision, names)
    if damage == "wrong-revision":
        revision = "0008" if revision == "0007" else "0007"
    else:
        if damage in {"missing", "same-count"}:
            names.remove("platform.inbox_events")
        if damage in {"extra", "same-count"}:
            names.add("platform.substituted_inbox_events")
    with pytest.raises(e.EgressError, match="EGRESS_MIGRATION_DATABASE_TABLES"):
        e.schema_inventory(revision, names)


def test_schema_entrypoint_is_mandatory_only_in_both_state_shards():
    coordinator = (e.ROOT / "scripts/test_telegram_egress_migration.sh").read_text()
    shell = (e.ROOT / "scripts/test_telegram_egress.sh").read_text()
    assert "if fault == 'state':" in coordinator
    # T and C execute frozen sources; G is the single new terminal phase.
    assert "run_name='__control_coordinator__'" in coordinator
    assert "reports/retained-control/control-cleanup-negatives.json" in coordinator
    assert "negative['count'] == 3" in coordinator
    import ast
    import inspect

    dispatcher = ast.parse(inspect.getsource(run_control_coordinator))
    calls = [
        node
        for node in ast.walk(dispatcher)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "supervised_schema_child"
    ]
    argv = [
        [
            item.value if isinstance(item, ast.Constant) else ast.unparse(item)
            for item in call.args[0].elts
        ]
        for call in sorted(calls, key=lambda call: call.lineno)
    ]
    assert argv[:3] == [
        ["sh", "scripts/test_telegram_egress.sh", "--schema-upgrade", "historical", "CONTROL_T"],
        [
            "sh",
            "scripts/test_telegram_egress.sh",
            "--control-schema-upgrade",
            "CONTROL_T",
            "GUARDS_C",
            "str(handoff)",
        ],
        [
            "sh",
            "scripts/test_telegram_egress.sh",
            "--guards-schema-upgrade",
            "GUARDS_C",
            "candidate",
            "str(handoff_g)",
        ],
    ]
    assert len(argv) == 4
    assert argv[3][:2] == ["sys.executable", "-c"]
    assert "run_name='__control_cleanup_negatives__'" in argv[3][2]
    assert GUARDS_C in argv[3][2]
    ordered = sorted(calls, key=lambda call: call.lineno)
    assert ast.unparse(next(k.value for k in ordered[1].keywords if k.arg == "cwd")) == "control"
    assert (
        ast.unparse(next(k.value for k in ordered[1].keywords if k.arg == "timeout"))
        == "deadline - time.monotonic()"
    )
    assert ast.unparse(next(k.value for k in ordered[3].keywords if k.arg == "cwd")) == "control"
    assert "--guards-schema-upgrade" in shell
    assert '"budget_file": sys.argv[4]' in shell or "'budget_file': sys.argv[4]" in shell
    assert "run_name='__schema_harness__'" in shell
    assert "754f1c883e5a94a7fc9e729af2605424f949ba33" in coordinator


@pytest.mark.parametrize("revision", [None, "0007", "0009", "unknown"])
def test_ack_loss_unknown_revision_never_selects_runtime(revision):
    from types import SimpleNamespace

    report = {}
    lost = SimpleNamespace(returncode=86, stdout=b"M3_UPGRADE_COMMITTED_RESULT_LOST\n")
    with pytest.raises(AssertionError, match="REVISION_UNCONFIRMED"):
        schema_recovery_source(lost, lambda: {"revision": revision}, report, "candidate")
    assert "recovery_source" not in report["upgrade_ack_loss"]


def test_ack_loss_unreadable_revision_never_selects_runtime():
    from types import SimpleNamespace

    def unreadable():
        raise OSError("disposable database unavailable")

    report = {}
    with pytest.raises(OSError):
        schema_recovery_source(
            SimpleNamespace(returncode=86, stdout=b"M3_UPGRADE_COMMITTED_RESULT_LOST"),
            unreadable,
            report,
            "candidate",
        )
    assert report["upgrade_ack_loss"]["observed"] == "UNREADABLE"
    assert "recovery_source" not in report["upgrade_ack_loss"]


@pytest.mark.parametrize(
    "status,marker", [(0, b"M3_UPGRADE_COMMITTED_RESULT_LOST"), (1, b""), (86, b"unexpected")]
)
def test_ack_loss_does_not_accept_unexpected_migrator_result(status, marker):
    from types import SimpleNamespace

    def must_not_observe():
        pytest.fail("unexpected failure must not enter forward recovery")

    report = {}
    with pytest.raises(AssertionError, match="EXPECTED_POST_COMMIT_FAILURE"):
        schema_recovery_source(
            SimpleNamespace(returncode=status, stdout=marker), must_not_observe, report, "candidate"
        )
    assert report["upgrade_ack_loss"]["observed"] == "NOT_READ"
    assert "recovery_source" not in report["upgrade_ack_loss"]


def control_budget_file(tmp_path, **changes):
    now = time.monotonic()
    value = dict(
        version=1,
        phase=CONTROL_PHASE,
        historical=CONTROL_T,
        candidate="c" * 40,
        uid=os.getuid(),
        started_at=now - 30,
        issued_at=now,
        charged_seconds=30,
        deadline=now + 570,
    )
    value.update(changes)
    path = tmp_path / "control-budget.json"
    tmp_path.chmod(0o700)
    e.write_private(path, e.encoded(value))
    return path


def test_control_remaining_budget_is_absolute_private_and_consumed_once(tmp_path):
    path = control_budget_file(tmp_path)
    budget = consume_control_budget(path, CONTROL_T, "c" * 40)
    assert 0 < budget["remaining_seconds"] <= 570
    assert budget["charged_seconds"] == 30 and not path.exists()
    with pytest.raises(FileNotFoundError):
        consume_control_budget(path, CONTROL_T, "c" * 40)


@pytest.mark.parametrize(
    "change",
    [
        {"phase": "TURNS"},
        {"historical": "a" * 40},
        {"candidate": "b" * 40},
        {"uid": -1},
        {"version": True},
        {"charged_seconds": 1},
        {"deadline": 0},
        {"started_at": 1},
        {"unexpected": 1},
    ],
)
def test_control_budget_wrong_phase_source_clock_or_owner_refuses(tmp_path, change):
    path = control_budget_file(tmp_path, **change)
    with pytest.raises(AssertionError):
        consume_control_budget(path, CONTROL_T, "c" * 40)


def test_control_budget_exhaustion_and_file_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    now = time.monotonic()
    path = control_budget_file(
        tmp_path, started_at=now - 601, issued_at=now - 2, charged_seconds=599, deadline=now - 1
    )
    with pytest.raises(AssertionError, match="EXHAUSTED"):
        consume_control_budget(path, CONTROL_T, "c" * 40)
    path.unlink()
    path = control_budget_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(e.EgressError, match="PRIVATE_MODE"):
        consume_control_budget(path, CONTROL_T, "c" * 40)
    path.chmod(0o600)
    os.link(path, tmp_path / "duplicate")
    with pytest.raises(AssertionError, match="SINGLE_LINK"):
        consume_control_budget(path, CONTROL_T, "c" * 40)


@pytest.mark.parametrize("revision", ["0007", "0008", "0010", None])
def test_control_recovery_never_selects_candidate_for_unconfirmed_schema(revision):
    result = SimpleNamespace(returncode=86, stdout=b"CONTROL_UPGRADE_COMMITTED_RESULT_LOST\n")
    report = {"seed_identity": {"database": "asm_local", "database_oid": 10}}
    with pytest.raises(AssertionError):
        control_schema_recovery_source(
            result, lambda: {"revision": revision}, report, CONTROL_T, "c" * 40
        )
    assert "recovery_source" not in report["upgrade_ack_loss"]


def test_control_recovery_requires_exact_database_and_controlled_failure():
    observed = dict(
        revision="0009",
        role="asm_migrator",
        database="asm_local",
        database_oid=10,
        reader_pid=2,
        backend_pid=3,
        reader_namespace="pid:[123]",
        reader_start_ticks=200,
        reader_boot_id="test-boot",
    )
    result = SimpleNamespace(returncode=86, stdout=b"CONTROL_UPGRADE_COMMITTED_RESULT_LOST\n")
    report = {
        "seed_identity": {"database": "asm_local", "database_oid": 10},
        "lost_result_process": {
            "pid": 1,
            "namespace": "pid:[122]",
            "start_ticks": 100,
            "boot_id": "test-boot",
        },
    }
    assert (
        control_schema_recovery_source(result, lambda: observed, report, CONTROL_T, "c" * 40)
        == "c" * 40
    )
    # A successful exit or unrelated failure is not this post-commit cut.
    for code in (0, 1, 87):
        with pytest.raises(AssertionError, match="POST_COMMIT"):
            control_schema_recovery_source(
                SimpleNamespace(returncode=code, stdout=result.stdout),
                lambda: observed,
                report,
                CONTROL_T,
                "c" * 40,
            )
    with pytest.raises(AssertionError, match="DATABASE_IDENTITY"):
        control_schema_recovery_source(
            result, lambda: observed | {"database_oid": 11}, report, CONTROL_T, "c" * 40
        )
    # A recycled namespace/PID pair is still a new process only with a later
    # kernel birth time; no missing metadata or same-process fallback is allowed.
    recycled = observed | {"reader_namespace": "pid:[122]", "reader_pid": 1}
    assert (
        control_schema_recovery_source(result, lambda: recycled, report, CONTROL_T, "c" * 40)
        == "c" * 40
    )
    for birth in (100, 99):
        with pytest.raises(AssertionError, match="FRESH_PROCESS"):
            control_schema_recovery_source(
                result,
                lambda: recycled | {"reader_start_ticks": birth},
                report,
                CONTROL_T,
                "c" * 40,
            )
    with pytest.raises(AssertionError, match="HOST_BOOT"):
        control_schema_recovery_source(
            result,
            lambda: recycled | {"reader_boot_id": "different-boot"},
            report,
            CONTROL_T,
            "c" * 40,
        )
    del report["lost_result_process"]
    with pytest.raises(AssertionError, match="IDENTITY_REQUIRED"):
        control_schema_recovery_source(result, lambda: recycled, report, CONTROL_T, "c" * 40)


def test_schema_supervisor_reaps_child_on_timeout(tmp_path):
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        supervised_schema_child(
            [sys.executable, "-c", "import time; time.sleep(60)"], cwd=tmp_path, timeout=0.1
        )
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("failure", ["timeout", "exit"])
def test_schema_supervisor_stops_term_ignoring_descendant_after_leader_exit(tmp_path, failure):
    script = """
import os,signal,sys,time
from pathlib import Path
if os.fork()==0:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 Path('descendant').write_text(str(os.getpid()))
 time.sleep(60)
else:
 while not Path('descendant').exists(): time.sleep(.01)
 if sys.argv[1]=='exit': sys.exit(7)
 time.sleep(60)
"""
    started = time.monotonic()
    args = [sys.executable, "-c", script, failure]
    if failure == "timeout":
        with pytest.raises(subprocess.TimeoutExpired):
            supervised_schema_child(args, cwd=tmp_path, timeout=1)
    else:
        assert supervised_schema_child(args, cwd=tmp_path, timeout=1) == 7
    pid = int((tmp_path / "descendant").read_text())
    path = Path(f"/proc/{pid}/stat")
    # A zombie has already terminated and retains no descriptors or execution;
    # its orphan reaping belongs to the runner init, not this unrelated parent.
    assert not path.exists() or path.read_text().rpartition(")")[2].split()[0] == "Z"
    assert time.monotonic() - started < 7


def test_schema_probe_programs_are_executable_python_without_hidden_indentation():
    import ast
    import inspect

    for phase in (run_schema_phase, run_control_schema_phase):
        tree = ast.parse(inspect.getsource(phase))
        assignment = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "code" for t in n.targets)
        )
        value = ast.literal_eval(assignment.value.func.value).replace("EXPECTED", "True")
        compile(value, "<isolated schema readiness probe>", "exec")


@pytest.mark.parametrize("entry", ["coordinator", "child"])
@pytest.mark.parametrize("fault", ["mismatch", "dirty", "git", "command"])
def test_control_initial_failure_retains_source_budget_and_primary(
    tmp_path, monkeypatch, entry, fault
):
    # Reproduce the runner's fractional clock edge: subtracting the two stored
    # floats yields 600.0000000000001, although deadline is exactly start+600.
    # This early-refusal unit seam does no waiting or external command work.
    monkeypatch.setattr(time, "monotonic", lambda: 905.198142485)
    root = tmp_path / "checkout"
    root.mkdir()
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"untouched foreign state")
    calls = []
    candidate = "c" * 40
    monkeypatch.setattr(e, "ROOT", root)
    monkeypatch.chdir(root)
    monkeypatch.setattr(os, "getuid", lambda: 1001)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    request = {"historical": CONTROL_T, "candidate": candidate}
    if entry == "child":
        directory = tmp_path / "handoff"
        directory.mkdir(mode=0o700)
        # File guards are tested separately with the actual uid. This seam only
        # substitutes uid lookup, keeping real one-use consume/accounting.
        monkeypatch.setattr(os, "getuid", lambda: directory.stat().st_uid)
        path = control_budget_file(directory)
        request["budget_file"] = str(path)
        monkeypatch.setattr(e, "checked_path", lambda p, **kw: Path(p))
        monkeypatch.setattr(os, "getuid", lambda: directory.stat().st_uid or 1001)
        value = json.loads(path.read_text())
        value["uid"] = os.getuid()
        path.write_text(json.dumps(value))
        monkeypatch.setattr(e, "private_bytes", lambda p: Path(p).read_bytes())
    else:
        request["historical"] = "754f1c883e5a94a7fc9e729af2605424f949ba33"

    def command(args, **kwargs):
        calls.append(args)
        assert args[0] == "git", "early refusal must never reach Docker"
        if fault == "git":
            raise subprocess.CalledProcessError(7, ["git", "credential-looking-secret"])
        return (candidate + "\n").encode()

    codes = {
        "mismatch": "EGRESS_CHECKOUT_MISMATCH",
        "dirty": "EGRESS_DIRTY_SOURCE",
        "command": "EGRESS_COMMAND_FAILED",
    }
    monkeypatch.setattr(e, "command", command)

    def reject(_):
        raise e.EgressError(codes[fault])

    monkeypatch.setattr(e, "source_check", reject)
    with pytest.raises((e.EgressError, subprocess.CalledProcessError)):
        (run_control_coordinator if entry == "coordinator" else run_control_schema_phase)(request)
    filename = (
        "control-schema-ledger.json" if entry == "coordinator" else "control-schema-phase.json"
    )
    report = json.loads((root / "reports" / filename).read_text())
    assert report["requested_source"] == candidate
    assert report["observed_source"] == ("NOT_OBSERVED" if fault == "git" else candidate)
    assert report["primary_failure"]["reason"] == (
        "CONTROL_COMMAND_EXIT" if fault == "git" else codes[fault]
    )
    assert report["elapsed_seconds"] >= 0 and report["cleanup"]["state"] == "NOT_ADMITTED"
    assert foreign.read_bytes() == b"untouched foreign state"
    assert "credential-looking-secret" not in json.dumps(report)
    if entry == "child" and fault != "git":
        assert report["historical"] == CONTROL_T and report["coordinator"] == candidate
        assert report["prepare_budget"]["charged_seconds"] == 30
        assert report["prepare_budget"]["deadline"] == report["prepare_budget"]["started_at"] + 600
        assert report["budget_at_report"]["charged_seconds"] >= 30
        assert report["budget_state"] == "VALIDATED_CONSUMED" and not path.exists()
    else:
        assert "prepare_budget" not in report


@pytest.mark.parametrize("fault", ["malformed", "invalid", "expired", "unreadable", "consumed"])
def test_control_rejected_handoff_report_never_claims_unvalidated_budget(
    tmp_path, monkeypatch, fault
):
    candidate = "c" * 40
    root = tmp_path / "checkout"
    root.mkdir()
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o700)
    path = control_budget_file(handoff)
    if fault == "malformed":
        path.write_text("{not json")
    elif fault == "invalid":
        value = json.loads(path.read_text())
        value["candidate"] = "b" * 40
        path.write_text(json.dumps(value))
    elif fault == "expired":
        value = json.loads(path.read_text())
        now = time.monotonic()
        value.update(started_at=now - 601, issued_at=now - 2, charged_seconds=599, deadline=now - 1)
        path.write_text(json.dumps(value))
    elif fault == "unreadable":
        path.chmod(0o644)
    else:
        consume_control_budget(path, CONTROL_T, candidate)
    calls = []
    monkeypatch.setattr(e, "ROOT", root)
    monkeypatch.chdir(root)

    def command(args, **kwargs):
        calls.append(args)
        assert args == ["git", "rev-parse", "HEAD"]
        return candidate.encode()

    monkeypatch.setattr(e, "command", command)
    monkeypatch.setattr(
        e, "source_check", lambda _: pytest.fail("budget refusal must precede source admission")
    )
    with pytest.raises((e.EgressError, AssertionError, FileNotFoundError)):
        run_control_schema_phase(
            {"historical": CONTROL_T, "candidate": candidate, "budget_file": str(path)}
        )
    report = json.loads((root / "reports/control-schema-phase.json").read_text())
    assert len(calls) == 1 and report["primary_failure"]["stage"] == "consume_budget"
    assert report["budget_state"] == "NOT_VALIDATED" and "prepare_budget" not in report
    assert report["requested_source"] == report["observed_source"] == candidate
    assert report["elapsed_seconds"] >= 0 and report["cleanup"]["state"] == "NOT_ADMITTED"
    assert "coordinator" not in report and "historical" not in report


@pytest.mark.parametrize("fault", ["archive", "build", "reuse", "probe"])
def test_control_prepare_failure_keeps_consumed_budget_before_any_runtime(
    tmp_path, monkeypatch, fault
):
    root = tmp_path / "checkout"
    (root / "infra").mkdir(parents=True)
    (root / "infra/images.lock.env").write_text("PYTHON_IMAGE=synthetic\nUV_IMAGE=synthetic\n")
    handoff = tmp_path / "handoff"
    handoff.mkdir(mode=0o700)
    path = control_budget_file(handoff)
    budget = consume_control_budget(path, CONTROL_T, "c" * 40)
    monkeypatch.setattr(sys.modules[__name__], "consume_control_budget", lambda *a: budget)
    monkeypatch.setattr(e, "ROOT", root)
    monkeypatch.chdir(root)
    monkeypatch.setattr(os, "getuid", lambda: 1001)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(e, "source_check", lambda _: None)
    calls, cleanup = [], []

    def close(report):
        cleanup.append(True)
        report["state"] = "PASS"

    monkeypatch.setattr(SchemaOwnership, "inherited", lambda *a: SimpleNamespace(cleanup=close))

    def command(args, **kwargs):
        calls.append(args)
        if args == ["git", "rev-parse", "HEAD"]:
            return b"c" * 40
        if args[:2] in (["docker", "ps"], ["docker", "volume"]):
            return b""
        if args[:3] == ["docker", "image", "ls"]:
            return b"sha256:synthetic" if fault == "reuse" else b""
        if args[:2] == ["docker", "build"]:
            if fault == "build":
                raise e.EgressError("EGRESS_COMMAND_FAILED")
            return b""
        if args[:3] == ["docker", "image", "inspect"]:
            return b'[{"Id":"sha256:synthetic"}]'
        pytest.fail("no runtime/compose/controller after prepare fault: " + args[0])

    monkeypatch.setattr(e, "command", command)

    def archive(*args):
        if fault == "archive":
            raise e.EgressError("EGRESS_COMMAND_FAILED")

    monkeypatch.setattr(e, "migration_build_context", archive)

    def probe(*args):
        assert fault in {"reuse", "probe"}
        raise e.EgressError("EGRESS_MIGRATION_IMAGE_IDENTITY")

    monkeypatch.setattr(e, "migration_image", probe)
    with pytest.raises(e.EgressError):
        run_control_schema_phase(
            {"historical": CONTROL_T, "candidate": "c" * 40, "budget_file": str(path)}
        )
    report = json.loads((root / "reports/control-schema-phase.json").read_text())
    expected = "image_probe" if fault == "probe" else fault
    assert report["primary_failure"]["stage"].startswith(expected + "_")
    assert report["budget_state"] == "VALIDATED_CONSUMED" and report["prepare_budget"] == budget
    assert report["budget_at_report"]["charged_seconds"] >= 30
    assert report["budget_at_report"]["remaining_seconds"] <= budget["remaining_seconds"]
    assert cleanup == [True] and report["cleanup"]["state"] == "PASS"
    assert not report["checks"] and all("compose" not in c for c in calls)


@pytest.mark.parametrize("primary_present", [False, True])
@pytest.mark.parametrize("report_failure", [False, True])
def test_control_secondary_cleanup_and_report_errors_preserve_primary(
    tmp_path, monkeypatch, capsys, primary_present, report_failure
):
    report = schema_envelope({"candidate": "c" * 40}, CONTROL_PHASE)
    primary = e.EgressError("EGRESS_CHECKOUT_MISMATCH")
    calls = []

    def cleanup(detail):
        calls.append("cleanup")
        raise e.EgressError("CONTROL_FOREIGN_RESOURCE_REMAINS")

    owner = SimpleNamespace(cleanup=cleanup)
    if report_failure:
        monkeypatch.setattr(
            Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("secret report path"))
        )
    with pytest.raises((e.EgressError, OSError)) as caught:
        with schema_cleanup_scope(owner, report, tmp_path / "report.json"):
            if primary_present:
                raise primary
    assert calls == ["cleanup"]
    if primary_present:
        assert (
            caught.value is primary
            and report["primary_failure"]["reason"] == "EGRESS_CHECKOUT_MISMATCH"
        )
    else:
        assert report["failure"] in {"OSError", "EgressError"}
    assert any(d["stage"] == "cleanup" for d in report["secondary_failures"])
    assert "secret report path" not in json.dumps(report) + capsys.readouterr().out


def test_control_ownership_refuses_nonempty_daemon_without_cleanup(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")

    def command(args, **kwargs):
        calls.append(args)
        return b"foreign-sentinel\n"

    monkeypatch.setattr(e, "command", command)
    owner = SchemaOwnership(tmp_path / "private", "project", CONTROL_PHASE, "c" * 40)
    with pytest.raises(AssertionError, match="INITIAL_CONTAINERS"):
        owner.admit()
    with pytest.raises(AssertionError, match="NOT_ADMITTED"):
        owner.cleanup({})
    assert not owner.admitted and not owner.directory.exists()
    assert calls == [["/usr/bin/docker", "ps", "-aq"]]


def test_control_cli_records_precreation_name_and_cid_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(e, "command", lambda *a, **k: b"")
    owner = SchemaOwnership(tmp_path / "owner", "project", CONTROL_PHASE, "c" * 40)
    owner.admit()
    observed = []

    def execute(binary, args):
        intent = next(owner.directory.glob("run-*.json"))
        value = json.loads(intent.read_text())
        assert value["token"] == owner.token
        assert args[args.index("--name") + 1] == value["name"]
        assert args[args.index("--cidfile") + 1] == str(intent.with_suffix(".cid"))
        assert not intent.with_suffix(".cid").exists()
        assert SCHEMA_OWNER_LABEL + "=" + owner.token in args
        observed.append(binary)

    monkeypatch.setattr(os, "execv", execute)
    schema_docker_cli(owner.directory / "ownership.json", ["run", "--rm", "image", "python"])
    assert observed == ["/usr/bin/docker"]


@pytest.mark.parametrize("missing_cid", [False, True])
@pytest.mark.parametrize("foreign", [False, True])
def test_control_cleanup_owns_created_container_even_if_cli_lost_cid(
    tmp_path, monkeypatch, missing_cid, foreign
):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    owner = SchemaOwnership(tmp_path / "owner", "project", CONTROL_PHASE, "c" * 40)
    owner.directory.mkdir(mode=0o700)
    owner.admitted = True
    own, database, sentinel = "a" * 64, "b" * 64, "f" * 64
    name = "plain-controller"
    intent = owner.directory / "run-controller.json"
    e.write_private(intent, e.encoded({"name": name, "token": owner.token, "phase": CONTROL_PHASE}))
    if not missing_cid:
        intent.with_suffix(".cid").write_text(own)
    label = {SCHEMA_OWNER_LABEL: owner.token}
    rows = {
        own: {
            "Id": own,
            "Name": "/" + name,
            "Config": {"Labels": label, "Volumes": {}},
            "State": {"Running": True},
            "Mounts": [],
        },
        database: {
            "Id": database,
            "Name": "/project-postgres-1",
            "Config": {"Labels": {**label, "com.docker.compose.project": "project"}},
            "State": {"Running": True},
            "Mounts": [{"Type": "volume", "Name": "owned-volume", "Destination": "/data"}],
        },
    }
    volumes, networks = {"owned-volume"}, {"owned-network"}
    operations = []

    def command(argv, **kwargs):
        args = argv[1:]
        operations.append(args)
        assert 0 < kwargs["timeout"] <= 90
        if args[:2] == ["ps", "-aq"]:
            ids = list(rows)
            if "--filter" not in args and foreign:
                ids.append(sentinel)
            return "\n".join(ids).encode()
        if args[0] == "inspect":
            return json.dumps([rows[i] for i in args[1:]]).encode()
        if args[:2] == ["volume", "inspect"]:
            return json.dumps([{"Labels": label}]).encode()
        if args[:2] == ["volume", "ls"]:
            return "\n".join(
                volumes | ({"foreign-volume"} if foreign and "--filter" not in args else set())
            ).encode()
        if args[:2] == ["network", "ls"]:
            return "\n".join(networks).encode()
        if args[0] == "stop":
            for ident in args[3:]:
                rows[ident]["State"]["Running"] = False
            return b""
        if args[:3] == ["rm", "-f", "-v"]:
            for ident in args[3:]:
                assert ident != sentinel
                del rows[ident]
            return b""
        if args[:2] == ["volume", "rm"]:
            volumes.remove(args[2])
            return b""
        if args[:2] == ["network", "rm"]:
            networks.remove(args[2])
            return b""
        pytest.fail("unexpected cleanup command")

    monkeypatch.setattr(e, "command", command)

    def disconnected(deadline):
        assert deadline > time.monotonic()
        assert own not in rows and database in rows
        return 0

    report = {}
    if foreign:
        with pytest.raises(AssertionError, match="FOREIGN_RESOURCE_REMAINS"):
            owner.cleanup(report, disconnected)
        assert report["foreign_containers"] == [sentinel] and report["foreign_volumes"] == [
            "foreign-volume"
        ]
    else:
        owner.cleanup(report, disconnected)
        assert report["state"] == "PASS"
    assert not rows and not volumes and not networks
    assert report["intents"][0]["cid"] == own
    assert not report["unconfirmed_creations"] and report["owned_remaining"] == []
    assert report["connections_after_controller_stop"] == 0
    assert not any(sentinel in a or "foreign-volume" in a for a in operations)


def test_control_unconfirmed_creation_is_stop_even_on_empty_daemon(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    owner = SchemaOwnership(tmp_path / "owner", "project", CONTROL_PHASE, "c" * 40)
    owner.directory.mkdir(mode=0o700)
    owner.admitted = True
    e.write_private(
        owner.directory / "run-before-ack.json",
        e.encoded({"name": "pending-name", "token": owner.token, "phase": CONTROL_PHASE}),
    )
    monkeypatch.setattr(e, "command", lambda *a, **k: b"")
    report = {}
    with pytest.raises(AssertionError, match="CREATION_UNCONFIRMED"):
        owner.cleanup(report)
    assert report["state"] == "CREATION_UNCONFIRMED"
    assert report["unconfirmed_creations"] == ["pending-name"]


def test_control_coordinator_archive_failure_retains_ledger_and_cleans_only_admitted_owner(
    tmp_path, monkeypatch
):
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setattr(e, "ROOT", root)
    monkeypatch.chdir(root)
    monkeypatch.setattr(os, "getuid", lambda: 1001)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(e, "source_check", lambda _: None)
    admitted, cleaned, commands = [], [], []
    monkeypatch.setattr(SchemaOwnership, "admit", lambda self: admitted.append(self.token))

    def cleanup(self, report):
        assert self.token in admitted
        cleaned.append(self.token)
        report["state"] = "PASS"

    monkeypatch.setattr(SchemaOwnership, "cleanup", cleanup)

    def command(args, **kwargs):
        commands.append(args)
        assert args[0] == "git"
        if args[1:3] == ["rev-parse", "HEAD"]:
            return b"c" * 40
        if args[1] == "merge-base":
            return b""
        assert args[1] == "archive"
        raise e.EgressError("EGRESS_COMMAND_FAILED")

    monkeypatch.setattr(e, "command", command)
    with pytest.raises(e.EgressError, match="COMMAND_FAILED"):
        run_control_coordinator(
            {"historical": "754f1c883e5a94a7fc9e729af2605424f949ba33", "candidate": "c" * 40}
        )
    report = json.loads((root / "reports/control-schema-ledger.json").read_text())
    assert report["primary_failure"]["stage"] == "retained_archive"
    assert report["primary_failure"]["reason"] == "EGRESS_COMMAND_FAILED"
    assert report["deadline"] == report["started_at"] + 600 and report["elapsed_seconds"] >= 0
    assert len(admitted) == 1 and cleaned == admitted
    assert report["requested_source"] == report["observed_source"] == "c" * 40
    assert (root / "reports/retained-turns/source-pairing.json").exists()
    assert not any("worktree" in c or "docker" in c for c in commands)


def test_control_cleanup_reuses_one_absolute_90s_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    owner = SchemaOwnership(tmp_path / "owner", "project", CONTROL_PHASE, "c" * 40)
    owner.directory.mkdir(mode=0o700)
    owner.admitted = True
    # Crossing a binary exponent boundary makes (start +90) -start differ
    # from90 by one ULP, while JSON preserves both original float values.
    clock, calls = [450.432197629], []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(e, "command", lambda *a, **k: calls.append(a[0]) or b"")
    first = {}
    owner.cleanup(first)
    assert first["state"] == "PASS"
    saved = (owner.directory / "cleanup-budget.json").read_bytes()
    assert first["deadline"] - first["cleanup_started_at"] != 90
    clock[0] += 1
    resumed = {}
    owner.cleanup(resumed)
    assert resumed["state"] == "PASS" and resumed["deadline"] == first["deadline"]
    clock[0] += 90
    before = len(calls)
    second = {}
    with pytest.raises(AssertionError, match="CLEANUP_DEADLINE"):
        owner.cleanup(second)
    assert len(calls) == before and second["deadline"] == first["deadline"]
    assert (owner.directory / "cleanup-budget.json").read_bytes() == saved


def test_control_compose_overlay_owns_resources_without_changing_source(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(e, "command", lambda *a, **k: b"")
    owner = SchemaOwnership(tmp_path / "owner", "project", CONTROL_PHASE, "c" * 40)
    owner.admit()
    compose = tmp_path / "frozen-compose.json"
    original = b'{"services":{"postgres":{"image":"pinned"}},"volumes":{"data":{}},"networks":{"default":{}}}'
    compose.write_bytes(original)

    def model(args, **kwargs):
        assert args == [
            "/usr/bin/docker",
            "compose",
            "--project-name",
            "project",
            "-f",
            str(compose),
            "config",
            "--format",
            "json",
        ]
        assert kwargs["timeout"] == 40
        return SimpleNamespace(stdout=original)

    monkeypatch.setattr(subprocess, "run", model)
    executed = []
    monkeypatch.setattr(os, "execv", lambda binary, args: executed.append(args))
    schema_docker_cli(
        owner.directory / "ownership.json",
        ["compose", "--project-name", "project", "-f", str(compose), "up", "-d"],
    )
    overlay = json.loads((owner.directory / "compose-ownership.json").read_text())
    for group, name in (("services", "postgres"), ("volumes", "data"), ("networks", "default")):
        assert overlay[group][name]["labels"] == {SCHEMA_OWNER_LABEL: owner.token}
    assert compose.read_bytes() == original
    assert executed[0][-4:] == ["-f", str(owner.directory / "compose-ownership.json"), "up", "-d"]


def retained_full_function_fixture(tmp_path, monkeypatch, fault):
    import ast
    import inspect
    from contextlib import nullcontext

    checkout = tmp_path / "frozen-T"
    # Development images have no Git/history. This entire retained function is
    # still byte-identical to T lines626--927; pin those original bytes, then
    # compile its full AST without modifying a node. Only surrounding source/
    # image/daemon admission is a unit seam. Actual lanes pin the full T blob.
    raw = inspect.getsource(run_schema_phase).encode()
    assert e.sha(raw) == "8227f4dceafb76e946cd51731d47e9ea000670bf7011e0b57b6acfe3d27d97f5"
    module = checkout / "tests/test_telegram_egress_migration.py"
    module.parent.mkdir(parents=True)
    module.write_bytes(raw)
    pins = checkout / "infra/images.lock.env"
    pins.parent.mkdir()
    pins.write_text("PYTHON_IMAGE=unit\nUV_IMAGE=unit\n")
    node = next(
        n
        for n in ast.parse(module.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "run_schema_phase"
    )
    original_ast = ast.dump(node, include_attributes=True)
    executable = compile(ast.Module(body=[node], type_ignores=[]), str(module), "exec")
    assert ast.dump(node, include_attributes=True) == original_ast
    monkeypatch.setattr(shutil, "which", lambda _: str(tmp_path / "owner/docker"))
    owner = SchemaOwnership(tmp_path / "owner", "asm-m3-schema-phase", "RETAINED_T", CONTROL_T)
    owner.directory.mkdir(mode=0o700)
    owner.docker, owner.admitted = "/unit/docker", True
    e.write_private(
        owner.directory / "ownership.json",
        e.encoded(
            {
                "project": owner.project,
                "phase": owner.phase,
                "source": owner.source,
                "token": owner.token,
                "docker": owner.docker,
                "uid": os.getuid(),
            }
        ),
    )
    e.write_private(
        owner.directory / "retained.json",
        e.encoded(
            {
                "token": owner.token,
                "source": CONTROL_T,
                "phase": owner.phase,
                "owner_directory": str(owner.directory),
                "module": str(module),
                "module_blob": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest(),
                "helper_blob": RETAINED_HELPER_BLOB,
                "deadline": time.monotonic() + 600,
                "fault": "export" if fault == "export" else None,
            }
        ),
    )
    checkpoint = RetainedCheckpoint(owner.directory)
    e.write_private(owner.directory / "compose-ownership.json", b"{}\n")
    monkeypatch.setattr(os, "execv", lambda *args: None)
    receipt = e.encoded(
        {
            "unique_private_receipt": uuid4().hex,
            "private_payload": "private-fixture-not-for-reports",
        }
    )
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"foreign unchanged")
    live = {"controller": False, "callers": True, "cleanup_calls": 0}
    temporary_paths = []

    def cleanup(self, report, observe_disconnected=None):
        live["cleanup_calls"] += 1
        budget = self.cleanup_budget()
        if fault == "cleanup-still-live" or (fault == "cleanup" and live["cleanup_calls"] == 1):
            report["state"] = "INJECTED_FAILURE"
            raise e.EgressError("CONTROL_INJECTED_OWNED_CLEANUP")
        live["controller"] = False
        report.update(state="PASS", owned_remaining=[], deadline=budget["deadline"])

    monkeypatch.setattr(SchemaOwnership, "cleanup", cleanup)
    if fault == "capture":
        original_capture = RetainedCheckpoint.capture
        capture_calls = []

        def fail_capture(self):
            capture_calls.append(True)
            if len(capture_calls) == 1:
                raise OSError("private-capture-error-never-serialized")
            return original_capture(self)

        monkeypatch.setattr(RetainedCheckpoint, "capture", fail_capture)

    def init(args, *, cwd, **kwargs):
        assert Path(args[1]).name == "init_local.py"
        temporary_paths.append(Path(cwd))
        e.write_private(Path(cwd) / ".env", b"PRIVATE=fixture-secret\n")
        return SimpleNamespace(returncode=0)

    def command(args, **kwargs):
        if args == ["git", "rev-parse", "HEAD"]:
            return CONTROL_T.encode()
        assert args[0] == "docker"
        if args[1:3] in (["ps", "-aq"], ["volume", "ls"]):
            return b""
        if args[1:3] == ["image", "ls"]:
            return b"sha256:" + b"1" * 64
        if args[1:3] == ["image", "inspect"]:
            return json.dumps([{"Id": "sha256:" + "1" * 64}]).encode()
        if args[1] == "tag":
            return b""
        if args[1] == "inspect":
            return json.dumps(
                [{"Image": "sha256:" + "1" * 64, "State": {"Running": live["callers"]}}]
            ).encode()
        if args[1] == "compose":
            if "config" in args:
                return json.dumps(
                    {
                        "services": {
                            "api": {
                                "environment": {"ASM_TELEGRAM_ENABLED": "false", "TG_BOT_TOKEN": ""}
                            },
                            "migrate": {"environment": {}},
                        }
                    }
                ).encode()
            if "ps" in args:
                return b"fake-caller"
            if "stop" in args:
                live["callers"] = False
            if "down" in args:
                assert (checkpoint.state / "receipt.json").read_bytes() == receipt
                schema_docker_cli(owner.directory / "ownership.json", args[1:])
                if fault == "down":
                    raise e.EgressError("EGRESS_COMMAND_FAILED")
            return b""
        assert args[1] == "run"
        remapped, identity = checkpoint.bind(args[1:])
        assert identity == checkpoint.identity(checkpoint.state)
        assert "source=" + str(checkpoint.state) in remapped[remapped.index("--mount") + 1]
        if "--schema-phase" in args and args[args.index("--schema-phase") + 1] == "seed":
            e.write_private(checkpoint.state / "receipt.json", receipt)
            live["controller"] = True
            raise subprocess.TimeoutExpired(["private-command-never-serialized"], 120)
        checkpoint.mirror()
        return b""

    frozen = SimpleNamespace(
        ROOT=checkout,
        command=command,
        source_check=lambda _: None,
        migration_budget=lambda _: nullcontext(),
        migration_build_context=lambda *args: None,
        migration_image=lambda image, source, kind: {
            "image_id": image,
            "source": source,
            "kind": kind,
        },
        write_private=e.write_private,
    )
    namespace = {
        "e": frozen,
        "os": SimpleNamespace(
            getuid=lambda: 1001, getgid=os.getgid, environ={"GITHUB_ACTIONS": "true"}
        ),
        "subprocess": SimpleNamespace(run=init),
        "Path": Path,
        "json": json,
        "sys": sys,
    }
    exec(executable, namespace)
    if fault == "report":
        original_write = Path.write_text

        def report_failure(path, *args, **kwargs):
            if path.name == "m3-schema-phase.json":
                raise OSError("private-report-error-never-serialized")
            return original_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", report_failure)
    return owner, checkpoint, namespace, live, receipt, foreign, temporary_paths


@pytest.mark.parametrize(
    "fault",
    ["down-success", "down", "cleanup", "cleanup-still-live", "capture", "export", "report"],
)
def test_retained_full_function_keeps_checkpoint_and_primary(tmp_path, monkeypatch, fault):
    owner, checkpoint, namespace, live, receipt, foreign, temporary_paths = (
        retained_full_function_fixture(tmp_path, monkeypatch, fault)
    )
    outer = schema_envelope(
        {"historical": CONTROL_T, "candidate": CONTROL_T}, "UNIT_FULL_RETAINED_T"
    )
    outer["cleanup"] = {"state": "ADMITTED"}
    ledger = tmp_path / "outer-ledger.json"
    previous_trace = sys.gettrace()
    observer = retained_exception_observer(checkpoint.config)
    with pytest.raises((subprocess.TimeoutExpired, e.EgressError, OSError)):
        with schema_cleanup_scope(owner, outer, ledger):
            try:
                sys.settrace(observer)
                namespace["run_schema_phase"](
                    {
                        "historical": "754f1c883e5a94a7fc9e729af2605424f949ba33",
                        "candidate": CONTROL_T,
                    }
                )
            finally:
                sys.settrace(previous_trace)
                # Same-process daemon seam supplies the launcher's exit ACK.
                # Separate-child tests below exercise that boundary without it.
                outer["retained_shell_exit"] = 1 if observer.finish() else 78
                assert temporary_paths and not temporary_paths[0].exists()
                assert (checkpoint.state / "receipt.json").read_bytes() == receipt
                if live["controller"]:
                    assert fault in {"cleanup", "cleanup-still-live", "capture", "export", "report"}
                    assert checkpoint.state.is_relative_to(owner.directory)
    saved = json.loads(ledger.read_text())
    assert saved["primary_failure"]["type"] == "TimeoutExpired"
    assert saved["primary_failure"]["reason"] == "CONTROL_COMMAND_TIMEOUT"
    assert saved["primary_failure"]["stage"] == "controller_seed"
    assert saved["private_state_retained"]
    assert live["controller"] == (fault == "cleanup-still-live")
    assert saved["cleanup"]["state"] == (
        "INJECTED_FAILURE" if fault == "cleanup-still-live" else "PASS"
    )
    proof = saved["retained_checkpoint"]
    assert proof["files"]["receipt.json"]["sha256"] == e.sha(receipt)
    assert not proof["original_exists"]
    assert (checkpoint.root / proof["capture"]["snapshot"] / "receipt.json").read_bytes() == receipt
    assert foreign.read_bytes() == b"foreign unchanged"
    for private in (
        "private-fixture-not-for-reports",
        "private-command-never-serialized",
        "private-report-error-never-serialized",
        "private-capture-error-never-serialized",
        "fixture-secret",
    ):
        assert private not in ledger.read_text()
    if fault != "down-success":
        assert saved["secondary_failures"]
    if fault == "report":
        assert any(
            detail["stage"] == "retained_report" and detail["type"] == "OSError"
            for detail in saved["secondary_failures"]
        )


def inject_retained_journal_io(monkeypatch, fault):
    """Scoped filesystem faults only; no replacement observer/collector logic."""
    original_replace, original_sync, original_open = os.replace, os.fsync, os.fdopen
    attempts, failed = [], []
    pending = {"name": None}

    def replace(source, target):
        name = Path(target).name
        pending["name"] = None
        if name == "trace-primary.json" and Path(source).name.startswith(".observer-"):
            attempts.append(Path(source).read_bytes())
            if fault == "permanent" or (fault == "transient" and not failed):
                failed.append(True)
                raise OSError("private-journal-error-never-serialized")
        result = original_replace(source, target)
        pending["name"] = name
        return result

    def sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            name, pending["name"] = pending["name"], None
            if (fault == "directory-once" and name == "trace-primary.json" and not failed) or (
                fault == "health-durability" and name == "trace-health.json"
            ):
                failed.append(True)
                raise OSError("private-journal-error-never-serialized")
        elif fault == "file-once" and not failed:
            path = Path(os.readlink(f"/proc/self/fd/{fd}"))
            if path.name.startswith(".observer-") and b'"sequence": 1' in path.read_bytes():
                failed.append(True)
                raise OSError("private-journal-error-never-serialized")
        return original_sync(fd)

    @contextmanager
    def opened(fd, mode="r", *args, **kwargs):
        with original_open(fd, mode, *args, **kwargs) as stream:
            if fault != "write-once" or mode != "wb":
                yield stream
                return

            def write(raw):
                target = Path(os.readlink(f"/proc/self/fd/{fd}"))
                if target.name.startswith(".observer-") and b'"sequence": 1' in raw and not failed:
                    failed.append(True)
                    raise OSError("private-journal-error-never-serialized")
                return stream.write(raw)

            yield SimpleNamespace(write=write, flush=stream.flush, fileno=stream.fileno)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "fdopen", opened)
    return attempts, failed


@pytest.mark.parametrize("fault", ["down", "report"])
@pytest.mark.parametrize(
    "journal_fault", ["transient", "write-once", "file-once", "directory-once"]
)
def test_retained_full_function_first_event_retry(tmp_path, monkeypatch, fault, journal_fault):
    attempts, failed = inject_retained_journal_io(monkeypatch, journal_fault)
    # All original assertions still execute: full unchanged T, real receipt/
    # tempdir, checkpoint byte identity, cleanup, primary and secondary.
    test_retained_full_function_keeps_checkpoint_and_primary(tmp_path, monkeypatch, fault)
    assert failed and 1 <= len(attempts) <= 3 and len(set(attempts)) == 1
    record = json.loads(attempts[0])
    assert record["sequence"] == 1 and record["detail"]["type"] == "TimeoutExpired"
    saved = json.loads((tmp_path / "outer-ledger.json").read_text())
    health = saved["retained_journal"]
    assert health["state"] == "RECOVERED" and health["primary"] == "CONFIRMED"
    assert health["event_hashes"][0] == e.sha(attempts[0])
    assert health["attempts"][0] == 2 and health["diagnostics"]
    assert any(d["stage"] == "retained_" + fault for d in saved["secondary_failures"])
    primary = copy.deepcopy(saved["primary_failure"])
    RetainedCheckpoint(tmp_path / "owner").collect(saved)
    assert saved["primary_failure"] == primary
    assert "private-journal-error-never-serialized" not in json.dumps(saved)


def damage_retained_journal(directory, fault, monkeypatch):
    name = "trace-health.json" if fault.startswith("health-") else "trace-primary.json"
    path = directory / name
    original = path.read_bytes() if path.exists() else None
    if fault.endswith("missing"):
        path.unlink()
    elif fault.endswith("unreadable"):
        read = e.private_bytes

        def unreadable(target):
            if Path(target) == path:
                raise PermissionError("private-journal-read-error-never-serialized")
            return read(target)

        monkeypatch.setattr(e, "private_bytes", unreadable)
    elif fault.endswith("corrupt"):
        e.write_private(path, b"not-json\n")
    elif fault in {"wrong-sequence", "wrong-owner", "wrong-source", "wrong-phase"}:
        record = json.loads(original)
        if fault == "wrong-sequence":
            record["sequence"] = 2
        else:
            key = {"wrong-owner": "token", "wrong-source": "source", "wrong-phase": "phase"}[fault]
            record["binding"][key] = "f" * 40
        e.write_private(path, e.encoded(record))
        health = e.strict_json(e.private_bytes(directory / "trace-health.json"))
        health["event_hashes"][0] = e.sha(e.private_bytes(path))
        e.write_private(directory / "trace-health.json", e.encoded(health))
    return path, original


@pytest.mark.parametrize("fault", ["down", "report"])
@pytest.mark.parametrize("journal_fault", ["permanent", "missing", "unreadable", "corrupt"])
def test_retained_full_function_journal_stop_keeps_cleanup(
    tmp_path, monkeypatch, fault, journal_fault
):
    owner, checkpoint, namespace, live, receipt, foreign, temporary_paths = (
        retained_full_function_fixture(tmp_path, monkeypatch, fault)
    )
    attempts, _ = inject_retained_journal_io(monkeypatch, journal_fault)
    report = schema_envelope({"candidate": CONTROL_T}, "UNIT_FULL_RETAINED_JOURNAL")
    report["cleanup"] = {"state": "ADMITTED"}
    path = tmp_path / "outer-ledger.json"
    observer = retained_exception_observer(checkpoint.config)
    previous_trace = sys.gettrace()
    with pytest.raises((subprocess.TimeoutExpired, e.EgressError, OSError)):
        with schema_cleanup_scope(owner, report, path):
            try:
                sys.settrace(observer)
                namespace["run_schema_phase"](
                    {
                        "historical": "754f1c883e5a94a7fc9e729af2605424f949ba33",
                        "candidate": CONTROL_T,
                    }
                )
            finally:
                sys.settrace(previous_trace)
                report["retained_shell_exit"] = 1 if observer.finish() else 78
                if journal_fault != "permanent":
                    damage_retained_journal(owner.directory, journal_fault, monkeypatch)
    assert attempts and len(attempts) <= 3 and len(set(attempts)) == 1
    if journal_fault == "permanent":
        assert len(attempts) == 3 and report["retained_shell_exit"] == 78
    assert not live["controller"] and report["cleanup"]["state"] == "PASS"
    assert temporary_paths and not temporary_paths[0].exists()
    assert (checkpoint.state / "receipt.json").read_bytes() == receipt
    proof = report["retained_checkpoint"]
    assert (checkpoint.root / proof["capture"]["snapshot"] / "receipt.json").read_bytes() == receipt
    assert proof["files"]["receipt.json"]["sha256"] == e.sha(receipt)
    assert report["result"] == "STOP" and report["retained_journal"]["primary"] == "UNCONFIRMED"
    assert report["primary_failure"]["type"] == "UNCONFIRMED"
    assert any(d["stage"] == "retained_" + fault for d in report["secondary_failures"])
    assert foreign.read_bytes() == b"foreign unchanged"
    assert "private-journal" not in path.read_text()
    for target in (report, {"retained_shell_exit": 1}):
        with pytest.raises(e.EgressError, match="CONTROL_RETAINED_JOURNAL_UNCONFIRMED"):
            RetainedCheckpoint(owner.directory).collect(target)
        assert target["primary_failure"]["type"] == "UNCONFIRMED"
        assert target["retained_journal"]["state"] == "STOP"


@pytest.mark.parametrize(
    "journal_fault",
    [
        "transient",
        "permanent",
        "health-durability",
        "missing",
        "unreadable",
        "corrupt",
        "health-missing",
        "health-unreadable",
        "health-corrupt",
        "wrong-sequence",
        "wrong-owner",
        "wrong-source",
        "wrong-phase",
    ],
)
def test_retained_journal_separate_child_then_parent_collection(
    tmp_path, monkeypatch, journal_fault
):
    # Only fixture/source/image/daemon seams live in the child. It runs the
    # production C launcher/observer and the entire unchanged T function. The
    # parent never receives its exception/object memory and collects only IPC.
    bootstrap = """
import importlib.util,runpy,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('retained_child_candidate',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
patch=pytest.MonkeyPatch()
fixture=m.retained_full_function_fixture(Path(sys.argv[2]),patch,'down')
owner,checkpoint,namespace,*_=fixture
launcher=m.write_retained_launcher(owner.directory)
m.inject_retained_journal_io(patch,sys.argv[3])
sys.modules['unit_frozen_case']=SimpleNamespace(run=namespace['run_schema_phase'])
sys.argv=[str(launcher),'-','--schema-upgrade']
runpy.run_path(str(launcher),run_name='__main__')
"""
    program = (
        "from unit_frozen_case import run\n"
        "run({'historical':'754f1c883e5a94a7fc9e729af2605424f949ba33',"
        "'candidate':'" + CONTROL_T + "'})\n"
    )
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            bootstrap,
            str(Path(__file__).resolve()),
            str(tmp_path),
            journal_fault,
        ],
        input=program.encode(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == (78 if journal_fault in {"permanent", "health-durability"} else 1)
    directory = tmp_path / "owner"
    checkpoint = RetainedCheckpoint(directory)
    entered = e.strict_json(e.private_bytes(directory / "trace-entered.json"))
    assert entered["pid"] != os.getpid()
    cleanup = e.strict_json(e.private_bytes(directory / "down-cleanup.json"))
    assert cleanup["state"] == "PASS"  # unit daemon seam, not actual PG evidence
    raw = e.private_bytes(checkpoint.state / "receipt.json")
    capture = e.strict_json(e.private_bytes(directory / "retained-capture.json"))
    assert e.private_bytes(checkpoint.root / capture["snapshot"] / "receipt.json") == raw
    report = {"retained_shell_exit": child.returncode, "cleanup": cleanup}
    healthy = {"transient", "permanent", "health-durability"}
    originals = {p.name: p.read_bytes() for p in directory.glob("trace-*.json")}
    with monkeypatch.context() as read_fault:
        if journal_fault not in healthy:
            damage_retained_journal(directory, journal_fault, read_fault)
        if journal_fault == "transient":
            checkpoint.collect(report)
            assert report["primary_failure"]["type"] == "TimeoutExpired"
            assert report["primary_failure"]["stage"] == "controller_seed"
            assert report["retained_journal"]["state"] == "RECOVERED"
            assert report["retained_journal"]["observer_pid"] == entered["pid"]
            assert any(d["stage"] == "retained_down" for d in report["secondary_failures"])
        else:
            with pytest.raises(e.EgressError, match="CONTROL_RETAINED_JOURNAL_UNCONFIRMED"):
                checkpoint.collect(report)
            assert report["primary_failure"]["type"] == "UNCONFIRMED"
            assert report["retained_journal"]["state"] == report["result"] == "STOP"
    assert not report["retained_checkpoint"]["original_exists"]
    assert report["retained_checkpoint"]["files"]["receipt.json"]["sha256"] == e.sha(raw)
    assert (tmp_path / "foreign").read_bytes() == b"foreign unchanged"
    assert "private-journal" not in json.dumps(report)
    if journal_fault != "transient":
        # Restoration or later publications cannot erase a recorded STOP, even
        # for a fresh collector/ledger. No first event is inferred from slot2.
        for name, data in originals.items():
            e.write_private(directory / name, data)
        for target in (report, {"retained_shell_exit": 1, "cleanup": cleanup}):
            with pytest.raises(e.EgressError, match="CONTROL_RETAINED_JOURNAL_UNCONFIRMED"):
                RetainedCheckpoint(directory).collect(target)
            assert target["primary_failure"]["type"] == "UNCONFIRMED"
            assert target["cleanup"]["state"] == "PASS"
            assert e.private_bytes(checkpoint.state / "receipt.json") == raw


@pytest.mark.parametrize("outcome", ["success", "failed-shell", "missing-health"])
def test_retained_journal_no_failure_requires_success_ack(tmp_path, monkeypatch, outcome):
    _, checkpoint, _, _, _, _, _ = retained_full_function_fixture(tmp_path, monkeypatch, "down")
    # Protocol-only unit frame: no claim to execute a successful full T here.
    # Both actual state lanes retain the complete positive frozen T execution.
    frame = SimpleNamespace(
        f_code=SimpleNamespace(co_filename=checkpoint.config["module"], co_name="run_schema_phase"),
        f_locals={},
    )
    observer = retained_exception_observer(checkpoint.config)
    observer(frame, "call", None)
    observer(frame, "return", None)
    assert observer.finish()
    assert not (checkpoint.directory / "trace-primary.json").exists()
    report = {"retained_shell_exit": 1 if outcome == "failed-shell" else 0}
    if outcome == "missing-health":
        (checkpoint.directory / "trace-health.json").unlink()
    if outcome == "success":
        checkpoint.collect(report)
        assert report["retained_journal"]["primary"] == "NONE"
        assert report["retained_journal"]["state"] == "HEALTHY"
        assert "primary_failure" not in report and "failure" not in report
    else:
        with pytest.raises(e.EgressError, match="CONTROL_RETAINED_JOURNAL_UNCONFIRMED"):
            checkpoint.collect(report)
        assert report["primary_failure"]["type"] == "UNCONFIRMED"


@pytest.mark.parametrize("revision,selected", [("0009", GUARDS_C), ("0010", "g" * 40)])
def test_guards_recovery_uses_actual_revision_and_fresh_process_identity(revision, selected):
    report = {
        "seed_identity": {
            "database": "asm_local",
            "database_oid": 45,
            "server_address": "172.20.0.2",
            "postmaster_started": "canonical-start",
        },
        "lost_result_process": {
            "namespace": "pid:[10]",
            "pid": 1,
            "start_ticks": 100,
            "boot_id": "boot",
        },
    }
    observation = {
        **report["seed_identity"],
        "revision": revision,
        "role": "asm_migrator",
        "reader_pid": 1,
        "backend_pid": 20,
        "reader_start_ticks": 101,
        "reader_boot_id": "boot",
    }
    lost = SimpleNamespace(returncode=86, stdout=b"GUARDS_UPGRADE_COMMITTED_RESULT_LOST\n")
    assert (
        guards_schema_recovery_source(lost, lambda: observation, report, GUARDS_C, "g" * 40)
        == selected
    )
    for changed in (
        {"revision": "0008"},
        {"revision": "unknown"},
        {"reader_start_ticks": 100},
        {"database_oid": 46},
        {"reader_boot_id": "other"},
    ):
        with pytest.raises(AssertionError):
            guards_schema_recovery_source(
                lost, lambda: {**observation, **changed}, report, GUARDS_C, "g" * 40
            )
        assert "recovery_source" not in report["upgrade_ack_loss"]

    def unreadable():
        raise OSError("unreadable")

    with pytest.raises(OSError):
        guards_schema_recovery_source(lost, unreadable, report, GUARDS_C, "g" * 40)
    assert report["upgrade_ack_loss"]["observed"] == "UNREADABLE"


@pytest.mark.parametrize(
    "damage", [None, "phase", "historical", "candidate", "deadline", "charged_seconds"]
)
def test_guards_budget_is_known_c_g_pair_and_same_absolute600(tmp_path, damage, monkeypatch):
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    path = tmp_path / "budget.json"
    issued = time.monotonic()
    value = dict(
        version=1,
        phase=GUARDS_PHASE,
        historical=GUARDS_C,
        candidate="a" * 40,
        uid=os.getuid(),
        started_at=issued - 430,
        issued_at=issued,
        charged_seconds=430,
        deadline=issued + 170,
    )
    if damage:
        value[damage] = value[damage] + 1 if damage in {"deadline", "charged_seconds"} else "wrong"
    e.write_private(path, e.encoded(value))
    if damage:
        with pytest.raises(AssertionError):
            consume_guards_budget(path, GUARDS_C, "a" * 40)
        assert path.exists()
    else:
        consumed = consume_guards_budget(path, GUARDS_C, "a" * 40)
        assert (
            consumed["deadline"] == value["deadline"] and 0 < consumed["remaining_seconds"] <= 170
        )
        assert not path.exists()
