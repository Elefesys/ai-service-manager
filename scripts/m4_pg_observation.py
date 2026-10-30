"""C2-M4-CI-OBSERVATION-R3: one disposable observer lifecycle validation."""

import asyncio
import functools
import hashlib
import itertools
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE = "3123fab2d9ac99e66161c0358e8b572783581d5e"
BASE_TREE = "925cd198f7247f2a327202b0a6d174766f38916e"
BRANCH = "c2/m4-pg-observation-run-r3"
DB_IMAGE = (
    "pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
)
TARGET = "tests/test_m3_1_control_api_postgres.py::test_post_lock_product_boundaries_with_actual_conversation_wait"
NODEIDS = [
    TARGET + "[" + "-".join(case) + "]"
    for case in itertools.product(
        ("resume", "controlled", "telegram"), ("expiry", "activation"), ("subscription", "mode")
    )
]
MODULES = [
    "tests/test_m3_1_control_postgres.py",
    "tests/test_m3_1_control_api_postgres.py",
    "tests/test_m3_1_guards_postgres.py",
    "tests/test_m3_1_provenance_postgres.py",
]
EXISTING_COLLECTION_SHA256 = "9d176494741dc88fe945c2f820d6d36f3f38b7e941593292236cde94f94772f0"
NEW_NODEIDS = [
    MODULES[0] + "::" + name + "[" + case + "]"
    for name, cases in (
        (
            "test_wait_blocked_controlled_target_contract",
            (
                "matching",
                "foreign",
                "unknown",
                "completed_before",
                "failed_before",
                "cancelled_before",
                "completed_during",
                "failed_during",
                "cancelled_during",
                "query_finished",
                "query_replaced",
                "observer_error",
                "observer_cancelled",
            ),
        ),
        (
            "test_wait_blocked_pg_target_controls",
            (
                "matching",
                "foreign",
                "absent",
                "two_targets",
                "completed",
                "failed",
                "cancelled",
            ),
        ),
        (
            "test_wait_blocked_pg_observer_failure_preserves_blocker",
            ("error", "cancelled"),
        ),
        (
            "test_m4_observation_summary_rejects_incomplete",
            (
                "valid",
                "missing_case",
                "extra_case",
                "reordered",
                "missing_phase",
                "duplicate_phase",
                "skip",
                "xfail",
                "overflow",
                "invalid",
                "failed",
                "exit",
                "unknown_outcome",
            ),
        ),
    )
    for case in cases
] + [MODULES[0] + "::test_m4_observation_command_preserves_summary"]
COMMAND_REPORT = "matrix-command"
SUMMARY_REPORT = "matrix-summary.json"
COLLECTED = []


WRITE_SET = {
    ".github/workflows/m4-pg-observation.yml",
    "scripts/m4_pg_observation.py",
    "tests/test_m3_1_control_postgres.py",
    "docs/tasks/M4_HANDOFF.md",
    "docs/TASK_REGISTER.md",
}
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
CASE = None
CASES = []
EVENT_LIMIT = 8192


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def record(kind, **fields):
    """Only bounded scalars in memory; no I/O, awaits, or database reads."""
    if CASE is None or CASE["nodeid"] not in NODEIDS:
        return
    if kind == "request_scheduled":
        CASE["pending"] = fields.pop("pending")
        CASE["engine"] = fields.pop("engine")
    elif kind in {"before_cleanup", "after_cleanup"}:
        pending = fields.pop("pending")
        fields.update(done=pending.done(), cancelled=pending.cancelled())
    if len(CASE["events"]) >= EVENT_LIMIT:
        CASE["overflow"] += 1
        return
    values = {}
    for name, value in fields.items():
        if name in {"edge", "blocked_at", "released_at"}:
            value = value.timestamp()
        if type(value) not in (int, float, bool, str, type(None)):
            CASE["invalid_fields"] += 1
            continue
        if isinstance(value, str) and len(value) > 120:
            CASE["invalid_fields"] += 1
            continue
        values[name] = value
    CASE["events"].append({"kind": kind, "monotonic_ns": time.monotonic_ns(), **values})


def request_wrapper(original):
    @functools.wraps(original)
    async def observed(*args, **kwargs):
        if CASE is None or asyncio.current_task() is not CASE.get("pending"):
            return await original(*args, **kwargs)
        record("request_start")
        try:
            response = await original(*args, **kwargs)
        except BaseException as error:
            record("request_completion", exception_type=type(error).__name__)
            raise
        record("request_completion", http_status=response.status_code)
        return response

    return observed


def cursor_event(connection, _cursor, statement, _parameters, _context, _many, *, end=False):
    if CASE is None or asyncio.current_task() is not CASE.get("pending"):
        return
    # SQLAlchemy's already-open psycopg connection exposes the PID without SQL.
    try:
        pid = connection.connection.driver_connection.info.backend_pid
    except Exception:
        record("operation_pid_unavailable")
        return
    workspace = connection.engine is CASE.get("engine")
    category = "OTHER"
    for name in (
        "conversation_manual_prelock",
        "conversation_control_prepare",
        "conversation_control_execute",
        "conversation_manual",
        "post_lock_product",
        "auth_",
        "billing_",
    ):
        if name in statement:
            category = name.upper()
            break
    record(
        "request_cursor_end" if end else "request_cursor_start",
        backend_pid=pid,
        workspace_connection=workspace,
        sql_category=category,
    )


if os.environ.get("ASM_M4_PG_PLUGIN") == "1":
    import pytest
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def pytest_collection_modifyitems(session, config, items):
        global COLLECTED
        COLLECTED = [item.nodeid for item in items]
        write(Path("/evidence/collected.json"), COLLECTED)
        validate_collection(COLLECTED)
        module = next(item.module for item in items if item.nodeid in NODEIDS)
        module.post = request_wrapper(module.post)
        module.manual = request_wrapper(module.manual)
        event.listen(Engine, "before_cursor_execute", cursor_event)
        event.listen(Engine, "after_cursor_execute", functools.partial(cursor_event, end=True))

    def pytest_runtest_setup(item):
        global CASE
        CASE = {
            "nodeid": item.nodeid,
            "events": [],
            "overflow": 0,
            "invalid_fields": 0,
            "phases": [],
        }
        CASES.append(CASE)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_makereport(item, call):
        result = yield
        report = result.get_result()
        data = {
            "phase": report.when,
            "outcome": report.outcome,
            "duration_seconds": report.duration,
            "xfail": hasattr(report, "wasxfail"),
        }
        if call.excinfo is not None:
            data["exception_type"] = call.excinfo.typename
            data["frames"] = [
                {"file": Path(entry.path).name, "line": entry.lineno + 1, "function": entry.name}
                for entry in call.excinfo.traceback[-12:]
            ]
            # Preserve failure and stack locations, never exception values,
            # cookies, query parameters, fixture reprs, captured logs or DSNs.
            report.longrepr = json.dumps(data, sort_keys=True)
        report.sections = []
        report.user_properties = []
        CASE["phases"].append(data)
        if report.when == "teardown":
            flush_cases()

    def pytest_collectreport(report):
        if report.failed:
            report.longrepr = "M4_OBSERVATION_COLLECTION_FAILED"
        report.sections = []

    def pytest_sessionfinish(session, exitstatus):
        flush_cases()
        summary = summarize(CASES, COLLECTED, int(exitstatus))
        write(Path("/evidence") / SUMMARY_REPORT, summary)
        if summary["result"] != "PASS" and session.exitstatus == 0:
            session.exitstatus = 1


def validate_collection(actual):
    existing = [node for node in actual if node not in NEW_NODEIDS]
    require(
        len(actual) == 222 + len(NEW_NODEIDS)
        and len(set(actual)) == len(actual)
        and [node for node in actual if node in NEW_NODEIDS] == NEW_NODEIDS
        and hashlib.sha256(("\n".join(existing) + "\n").encode()).hexdigest()
        == EXISTING_COLLECTION_SHA256,
        "SOURCE_COLLECTION_MISMATCH",
    )


def summarize(cases, expected, exitstatus):
    complete = (
        bool(expected)
        and [case["nodeid"] for case in cases] == expected
        and all(
            [p["phase"] for p in case["phases"]] == ["setup", "call", "teardown"]
            and all(p["outcome"] in {"passed", "failed"} and not p["xfail"] for p in case["phases"])
            and not case["overflow"]
            and not case["invalid_fields"]
            for case in cases
        )
    )
    passed = (
        complete
        and exitstatus == 0
        and all(p["outcome"] == "passed" for case in cases for p in case["phases"])
    )
    return {
        "pytest_exit": exitstatus,
        "cases": len(cases),
        "expected": len(expected),
        "complete": complete,
        "result": "PASS" if passed else "FAIL",
        "server_wait_vs_event_loop_delay": "UNKNOWN",
        "timings": "client monotonic spans for original matrix12; not server query durations",
    }


def flush_cases():
    write(
        Path("/evidence/cases.json"),
        [{k: v for k, v in case.items() if k not in {"pending", "engine"}} for case in CASES],
    )


def versions():
    import psycopg
    import sqlalchemy
    from sqlalchemy.engine import make_url

    value = {
        "python": platform.python_version(),
        "psycopg": psycopg.__version__,
        "sqlalchemy": sqlalchemy.__version__,
        "libpq": psycopg.pq.version(),
    }
    for kind, env in (("migrator", "ASM_MIGRATION_DATABASE_URL"), ("runtime", "ASM_DATABASE_URL")):
        url = make_url(os.environ[env])
        require(url.database == "asm_test", "VERSION_PROBE_TARGET")
        with psycopg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False)
        ) as c:
            identity = c.execute(
                "SELECT session_user,current_user,current_database(),current_setting('server_version'),current_setting('server_version_num')"
            ).fetchone()
            require(identity[:3] == ("asm_" + kind, "asm_" + kind, "asm_test"), "VERSION_IDENTITY")
            require(int(identity[4]) // 10000 == 18, "PG_MAJOR_MISMATCH")
            value[kind] = dict(
                zip(
                    (
                        "session_user",
                        "current_user",
                        "database",
                        "server_version",
                        "server_version_num",
                    ),
                    identity,
                    strict=True,
                )
            )
            if kind == "migrator":
                value["schema"] = c.execute(
                    "SELECT version_num FROM platform.alembic_version"
                ).fetchall()
                require(value["schema"] == [("0013",)], "SCHEMA_MISMATCH")
                value["roles"] = c.execute(
                    "SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolcanlogin FROM pg_roles WHERE rolname IN ('asm_runtime','asm_migrator') ORDER BY rolname"
                ).fetchall()
                require(
                    [row[0] for row in value["roles"]] == ["asm_migrator", "asm_runtime"]
                    and all(
                        row[1:5] == (False, False, False, False) and row[5]
                        for row in value["roles"]
                    ),
                    "ROLE_MISMATCH",
                )
                value["extensions"] = c.execute(
                    "SELECT extname,extversion FROM pg_extension WHERE extname IN ('vector','btree_gist') ORDER BY extname"
                ).fetchall()
    write(Path("/evidence/database-versions.json"), value)


def root_path():
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    require(re.fullmatch(r"[1-9][0-9]{0,19}", run) and attempt == "1", "RUN_IDENTITY")
    return Path(os.environ["RUNNER_TEMP"]) / ("m4-pg-" + run + "-" + attempt)


def compose(root):
    return DOCKER + [
        "compose",
        "--project-name",
        "asm-" + root.name,
        "--env-file",
        str(root / "private/test.env"),
        "--env-file",
        "infra/images.lock.env",
        "-f",
        "compose.yaml",
        "--profile",
        "test",
    ]


def capture(args):
    result = subprocess.run(args, capture_output=True, timeout=30)
    require(result.returncode == 0 and len(result.stdout) < 1048576, "INSPECTION_FAILED")
    return result.stdout.decode().strip()


def sanitize(raw, root):
    value = raw.decode(errors="replace")
    env = root / "private/test.env"
    if env.exists():
        for line in env.read_text().splitlines():
            secret = line.partition("=")[2]
            if secret:
                value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"postgres(?:ql)?(?:\+[a-z]+)?://[^\s\"']+", "[REDACTED_DSN]", value)
    return value


def phase(root, label, args, budget):
    start = time.monotonic()
    entry = {"phase": label, "command": args, "budget_seconds": budget, "started_utc": time.time()}
    write(root / "evidence/active-phase.json", entry)
    private = root / ("private/" + label + ".log")
    with private.open("wb") as output:
        process = subprocess.Popen(
            args, stdout=output, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            code = process.wait(timeout=budget)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            code = 124
    entry.update(exit_code=code, seconds=time.monotonic() - start)
    write(root / ("evidence/" + label + ".json"), entry)
    with private.open("rb") as stream:
        raw = stream.read(8388609)
    if len(raw) > 8388608:
        raw = raw[:8388608]
        entry["log_incomplete"] = True
        write(root / ("evidence/" + label + ".json"), entry)
    (root / ("evidence/" + label + ".log")).write_text(sanitize(raw, root))
    print("M4_PG_PHASE=" + label + " EXIT=" + str(code), flush=True)
    require(code == 0, label.upper().replace("-", "_") + "_FAILED")


def checks(root, *args, plugin=False):
    command = compose(root) + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        str(root / "evidence") + ":/evidence",
    ]
    if plugin:
        command += ["-e", "ASM_M4_PG_PLUGIN=1"]
    return command + ["checks", *args]


def inventory(root):
    project = "asm-" + root.name
    return {
        "containers": capture(
            DOCKER + ["ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]
        ).split(),
        "networks": capture(
            DOCKER + ["network", "ls", "-q", "--filter", "name=^" + project + "_default$"]
        ).split(),
        "volumes": capture(DOCKER + ["volume", "ls", "-q", "--filter", "name=" + project]).split(),
    }


def cleanup(root):
    evidence = root / "evidence"
    if not (root / "owned.json").exists():
        if evidence.exists():
            write(evidence / "cleanup.json", {"outcome": "NOT_OWNED_NOT_TOUCHED"})
        return
    attempts = []
    if (evidence / "cleanup.json").exists():
        old = json.loads((evidence / "cleanup.json").read_text())
        attempts = old.get("attempts", [])
        if old.get("outcome") == "PASS":
            require(not any(inventory(root).values()), "RESOURCES_REAPPEARED")
            return
    owner = json.loads((root / "owned.json").read_text())
    require(
        owner
        == {"project": "asm-" + root.name, "run_id": os.environ["GITHUB_RUN_ID"], "attempt": 1},
        "CLEANUP_OWNERSHIP",
    )
    try:
        phase(
            root,
            "cleanup-command-" + str(len(attempts) + 1),
            compose(root)
            + ["down", "--volumes", "--remove-orphans", "--rmi", "local", "--timeout", "10"],
            60,
        )
        remaining = inventory(root)
        require(not any(remaining.values()), "CLEANUP_INCOMPLETE")
        attempts.append({"outcome": "PASS", "remaining": remaining})
        write(evidence / "cleanup.json", {"outcome": "PASS", "attempts": attempts})
        shutil.rmtree(root / "private")
    except Exception as error:
        attempts.append({"outcome": "FAIL", "error": type(error).__name__})
        write(evidence / "cleanup.json", {"outcome": "FAIL", "attempts": attempts})
        raise


def run(root):
    require(not root.exists(), "RUN_ALREADY_STARTED")
    (root / "evidence").mkdir(parents=True, mode=0o700)
    (root / "private").mkdir(mode=0o700)
    primary = {"outcome": "NOT_RUN"}
    try:
        require(
            os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == "Elefesys/ai-service-manager"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH,
            "EXECUTION_CONTEXT",
        )
        require(capture(["git", "rev-parse", "HEAD"]) == os.environ["GITHUB_SHA"], "EVENT_SHA")
        require(capture(["git", "show", "-s", "--format=%P", "HEAD"]) == BASE, "SOURCE_PARENT")
        require(capture(["git", "rev-parse", BASE + "^{tree}"]) == BASE_TREE, "BASE_TREE")
        require(
            not capture(["git", "status", "--porcelain", "--untracked-files=all"]), "SOURCE_DIRTY"
        )
        paths = capture(["git", "diff", "--name-only", BASE, "HEAD"]).splitlines()
        require(set(paths) <= WRITE_SET, "SOURCE_WRITE_SET")
        require(not Path(".env").exists(), "UNEXPECTED_ENV_FILE")
        require(not any(inventory(root).values()), "RESOURCE_NAME_CONFLICT")
        pins = dict(
            line.split("=", 1) for line in Path("infra/images.lock.env").read_text().splitlines()
        )
        require(pins["DB_IMAGE"] == DB_IMAGE, "DB_IMAGE_PIN")
        write(
            root / "evidence/source.json",
            {
                "base": BASE,
                "base_tree": BASE_TREE,
                "source": os.environ["GITHUB_SHA"],
                "tree": capture(["git", "rev-parse", "HEAD^{tree}"]),
                "paths": paths,
                "run_id": os.environ["GITHUB_RUN_ID"],
                "attempt": 1,
                "event": "push",
                "branch": BRANCH,
                "pins": pins,
                "uv_lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
            },
        )
        write(
            root / "evidence/runner.json",
            {
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
                "uid": os.getuid(),
                "docker": json.loads(capture(DOCKER + ["version", "--format", "{{json .}}"])),
                "compose": capture(DOCKER + ["compose", "version", "--short"]),
            },
        )
        credentials = {
            name: secrets.token_hex(24)
            for name in (
                "PG_ADMIN_PASSWORD",
                "PG_MIGRATION_PASSWORD",
                "PG_RUNTIME_PASSWORD",
                "STORAGE_ROOT_USER",
                "STORAGE_ROOT_PASSWORD",
                "STORAGE_ACCESS_KEY",
                "STORAGE_SECRET_KEY",
            )
        }
        (root / "private/test.env").write_text(
            "".join(k + "=" + v + "\n" for k, v in credentials.items())
        )
        write(
            root / "owned.json",
            {"project": "asm-" + root.name, "run_id": os.environ["GITHUB_RUN_ID"], "attempt": 1},
        )
        phase(root, "build", compose(root) + ["build", "checks"], 420)
        phase(
            root,
            "database-start",
            compose(root) + ["up", "-d", "--wait", "--wait-timeout", "80", "postgres-test"],
            120,
        )
        identity = capture(compose(root) + ["ps", "-q", "postgres-test"])
        status = capture(DOCKER + ["exec", identity, "cat", "/proc/1/status"])
        uid = int(next(line.split()[1] for line in status.splitlines() if line.startswith("Uid:")))
        require(uid != 0, "POSTGRES_SERVER_ROOT")
        image_id = capture(DOCKER + ["inspect", "--format", "{{.Image}}", identity])
        pinned_id = capture(DOCKER + ["image", "inspect", "--format", "{{.Id}}", DB_IMAGE])
        require(image_id == pinned_id, "RUNNING_DB_IMAGE_MISMATCH")
        write(
            root / "evidence/server-process.json",
            {
                "uid": uid,
                "image_id": image_id,
                "pin": DB_IMAGE,
                "repo_digests": json.loads(
                    capture(
                        DOCKER + ["image", "inspect", "--format", "{{json .RepoDigests}}", DB_IMAGE]
                    )
                ),
            },
        )
        phase(root, "schema", checks(root, "alembic", "upgrade", "head"), 120)
        phase(
            root, "versions", checks(root, "python", "scripts/m4_pg_observation.py", "versions"), 30
        )
        phase(
            root,
            COMMAND_REPORT,
            checks(
                root,
                "pytest",
                "-p",
                "scripts.m4_pg_observation",
                "-q",
                "--tb=short",
                "--show-capture=no",
                "-o",
                "cache_dir=/tmp/asm-pytest-cache",
                "--junitxml=/evidence/junit.xml",
                *MODULES,
                plugin=True,
            ),
            600,
        )
        summary = json.loads((root / "evidence" / SUMMARY_REPORT).read_text())
        require(summary["result"] == "PASS" and summary["complete"], "MATRIX_EVIDENCE_INCOMPLETE")
        primary = {
            "outcome": "PASS",
            "scope": "222 retained cases plus exact-target and reporter controls; historical timeout cause UNKNOWN",
        }
    except Exception as error:
        code = str(error)
        primary = {
            "outcome": "FAIL",
            "error_type": type(error).__name__,
            "code": code if re.fullmatch(r"[A-Z0-9_]{1,80}", code) else "OPERATION_FAILED",
            "last_phase": json.loads((root / "evidence/active-phase.json").read_text())["phase"]
            if (root / "evidence/active-phase.json").exists()
            else "preflight",
        }
    finally:
        write(root / "evidence/primary.json", primary)
        cleanup(root)
        clean = not capture(["git", "status", "--porcelain", "--untracked-files=all"])
        write(root / "evidence/source-preservation.json", {"clean": clean})
        require(clean, "SOURCE_CHANGED")
    require(primary["outcome"] == "PASS", "PRIMARY_FAILED")


def main():
    os.umask(0o077)
    if sys.argv[1:] == ["versions"]:
        versions()
        return
    require(sys.argv[1:] in (["run"], ["cleanup"]), "USAGE")
    root = root_path()
    if sys.argv[1] == "run":
        run(root)
    else:
        try:
            cleanup(root)
        finally:
            if (root / "evidence").exists():
                files = {
                    p.name: {
                        "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in (root / "evidence").iterdir()
                    if p.is_file() and p.name != "manifest.json"
                }
                write(root / "evidence/manifest.json", files)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        print(
            "M4_PG_STOP="
            + (code if re.fullmatch(r"[A-Z0-9_]{1,80}", code) else type(error).__name__)
        )
        raise SystemExit(1) from None
