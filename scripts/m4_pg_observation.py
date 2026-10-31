"""C2-M4.3-PG-RUNTIME-R3: one bounded disposable DB-only runtime validation."""

import hashlib
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
from uuid import UUID

BASE = "3b5252a58b7730da6e0ff99f49a5e46b05dc2c5c"
BASE_TREE = "5141f997073cdd74ce813011971c08101da12697"
BRANCH = "c2/m4-3-pg-runtime-run-r3"
DB_IMAGE = (
    "pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
)
MODULES = [
    "tests/test_m4_runtime_migrations.py",
    "tests/test_m4_runtime_database.py",
    "tests/test_m4_runtime_postgres.py",
]
COLLECTION_COUNT = 82
COLLECTION_SHA256 = "ec64c4acebaee16f21de49b7e407fb7a2b2f7fd34032df46892be66ad36dd4ef"
COMMAND_REPORT = "runtime-command"
SUMMARY_REPORT = "runtime-summary.json"
COLLECTED = []
WRITE_SET = {
    "tests/test_m4_runtime_postgres.py",
    "scripts/m4_pg_observation.py",
    ".github/workflows/m4-pg-observation.yml",
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


def source_tree_from_evidence(path=Path("/evidence/source.json")):
    """Bind the DB-only fixture to this executor's checked source, without Git in the image."""

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "SOURCE_IDENTITY_DUPLICATE_KEY")
            value[key] = item
        return value

    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
        require(len(raw) <= 65536, "SOURCE_IDENTITY_TOO_LARGE")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except OSError:
        raise RuntimeError("SOURCE_IDENTITY_MISSING") from None
    except (UnicodeDecodeError, ValueError):
        raise RuntimeError("SOURCE_IDENTITY_MALFORMED") from None
    keys = {
        "base",
        "base_tree",
        "source",
        "tree",
        "paths",
        "run_id",
        "attempt",
        "event",
        "branch",
        "pins",
        "uv_lock_sha256",
    }
    require(type(value) is dict and set(value) == keys, "SOURCE_IDENTITY_SHAPE")
    expected = {
        name: os.environ.get("ASM_M4_" + name)
        for name in ("SOURCE_SHA", "SOURCE_TREE", "RUN_ID", "RUN_ATTEMPT")
    }
    require(
        all(
            type(expected[k]) is str and re.fullmatch(r"[0-9a-f]{40}", expected[k])
            for k in ("SOURCE_SHA", "SOURCE_TREE")
        )
        and type(expected["RUN_ID"]) is str
        and re.fullmatch(r"[1-9][0-9]{0,19}", expected["RUN_ID"])
        and expected["RUN_ATTEMPT"] == "1",
        "SOURCE_IDENTITY_ENVIRONMENT",
    )
    require(
        all(
            type(value[k]) is str and re.fullmatch(r"[0-9a-f]{40}", value[k])
            for k in ("base", "base_tree", "source", "tree")
        )
        and value["base"] == BASE
        and value["base_tree"] == BASE_TREE
        and value["source"] == expected["SOURCE_SHA"]
        and value["source"] != BASE
        and value["tree"] == expected["SOURCE_TREE"]
        and value["branch"] == BRANCH
        and value["event"] == "push"
        and type(value["attempt"]) is int
        and value["attempt"] == 1
        and value["run_id"] == expected["RUN_ID"],
        "SOURCE_IDENTITY_MISMATCH",
    )
    paths = value["paths"]
    require(
        type(paths) is list
        and bool(paths)
        and all(type(p) is str for p in paths)
        and paths == sorted(set(paths))
        and set(paths) <= WRITE_SET
        and type(value["pins"]) is dict
        and value["pins"].get("DB_IMAGE") == DB_IMAGE
        and all(type(k) is str and type(v) is str for k, v in value["pins"].items())
        and type(value["uv_lock_sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", value["uv_lock_sha256"]),
        "SOURCE_IDENTITY_SHAPE",
    )
    return value["tree"]


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def preparation(stage, **facts):
    """Record only bounded synthetic preparation identities, never claims or snapshots."""
    if CASE is None:
        return
    if len(CASE["events"]) >= EVENT_LIMIT:
        CASE["overflow"] += 1
        return
    if stage not in {
        "INGRESS",
        "RECONCILE",
        "RESUME",
        "AI_INGRESS",
        "PRE_SEAL",
        "POST_SEAL",
        "SOURCE_CLAIM",
        "ENQUEUE",
        "AI_CLAIM",
        "PREPARE",
        "PREPARED",
        "STALE_REVISION_REJECTED",
        "DOWNGRADE_READY",
    }:
        CASE["invalid_fields"] += 1
        return
    event = {"stage": stage}
    for name, value in facts.items():
        if (
            name
            in {
                "workspace_id",
                "connection_id",
                "conversation_id",
                "turn_id",
                "source_job_id",
                "job_id",
                "run_id",
            }
            and type(value) is UUID
        ):
            event[name] = str(value)
        elif (
            name in {"before_revision", "turn_revision"}
            and type(value) is int
            and 0 < value <= 9223372036854775807
        ):
            event[name] = value
        elif name == "state" and value in {"COLLECTING", "WAITING_MEDIA", "READY", "FAILED"}:
            event[name] = value
        else:
            CASE["invalid_fields"] += 1
            return
    CASE["events"].append(event)


if os.environ.get("ASM_M4_PG_PLUGIN") == "1":
    import pytest
    from asm.messaging.errors import MessagingError
    from sqlalchemy.exc import DBAPIError

    def pytest_collection_modifyitems(session, config, items):
        global COLLECTED
        COLLECTED = [item.nodeid for item in items]
        write(Path("/evidence/collected.json"), COLLECTED)
        validate_collection(COLLECTED)

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
            if isinstance(call.excinfo.value, MessagingError):
                data["error_code"] = call.excinfo.value.code.value
            if isinstance(call.excinfo.value, DBAPIError):
                sqlstate = getattr(call.excinfo.value.orig, "sqlstate", None)
                if type(sqlstate) is str and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
                    data["sqlstate"] = sqlstate
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
    require(
        len(actual) == COLLECTION_COUNT
        and len(set(actual)) == len(actual)
        and {node.split("::", 1)[0] for node in actual} == set(MODULES)
        and hashlib.sha256(("\n".join(actual) + "\n").encode()).hexdigest() == COLLECTION_SHA256,
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
        "scope": "DB-only 0014 runtime; application readiness remains 0013",
        "paid_http": 0,
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
                require(value["schema"] == [("0014",)], "SCHEMA_MISMATCH")
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
                value["ai_tables"] = c.execute(
                    "SELECT relname,relowner::regrole::text,relrowsecurity,relforcerowsecurity,has_table_privilege('asm_runtime',c.oid,'SELECT,INSERT,UPDATE,DELETE') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='platform' AND relname IN ('ai_runs','ai_provider_calls') ORDER BY relname"
                ).fetchall()
                require(
                    len(value["ai_tables"]) == 2
                    and all(
                        row[1:] == ("asm_migrator", True, True, False) for row in value["ai_tables"]
                    ),
                    "AI_DDL_SECURITY",
                )
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
        expected = {
            "SOURCE_SHA": os.environ["GITHUB_SHA"],
            "SOURCE_TREE": capture(["git", "rev-parse", "HEAD^{tree}"]),
            "RUN_ID": os.environ["GITHUB_RUN_ID"],
            "RUN_ATTEMPT": os.environ["GITHUB_RUN_ATTEMPT"],
        }
        for name, value in expected.items():
            command += ["-e", "ASM_M4_" + name + "=" + value]
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
        require(summary["result"] == "PASS" and summary["complete"], "RUNTIME_EVIDENCE_INCOMPLETE")
        primary = {
            "outcome": "PASS",
            "scope": "DB-only 0014 authority/run/call/result; no application compatibility or live provider claim",
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
