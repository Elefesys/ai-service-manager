"""C3-M4.3-RUNTIME-INTEGRATION-R2: separate owned PG18 application carrier."""

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

BASE = "4f989a09c38c112111819878319df0c9b09db00d"
BASE_TREE = "8a5e6f1f6fa0a6b8a36eff4c561794db001b42f7"
BRANCH = "c3/m4-3-runtime-integration-pr-r2"
CAPTURE_BRANCH = "c3/m4-3-runtime-catalog-run-r2"
TARGETED_BRANCH = "c3/m4-3-runtime-targeted-run-r2"
DB_IMAGE = (
    "pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
)
MODULES = [
    "tests/test_m4_runtime_postgres.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_schema_postgres.py",
]
COMMAND_REPORT = "runtime-command"
SUMMARY_REPORT = "runtime-summary.json"
COLLECTED = []
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
CASE = None
CASES = []
EVENT_LIMIT = 8192


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def evidence_path():
    return Path(os.environ.get("ASM_M4_EVIDENCE", "/evidence"))


def source_tree_from_evidence(path=None):
    """Bind the DB-only fixture to this executor's checked source, without Git in the image."""

    path = path or evidence_path() / "source.json"

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
        and (
            value["branch"] == BRANCH
            and value["event"] in {"pull_request", "push"}
            or value["branch"] in {CAPTURE_BRANCH, TARGETED_BRANCH}
            and value["event"] == "push"
        )
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
    flush_cases()


if os.environ.get("ASM_M4_PG_PLUGIN") == "1":
    import pytest
    from asm.messaging.errors import MessagingError
    from sqlalchemy.exc import DBAPIError

    def pytest_collection_modifyitems(session, config, items):
        global COLLECTED
        COLLECTED = [item.nodeid for item in items]
        write(evidence_path() / "collected.json", COLLECTED)
        validate_collection(COLLECTED)

    @pytest.hookimpl(tryfirst=True)
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
        active_case("setup")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_call(item):
        active_case("call")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_teardown(item):
        active_case("teardown")

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
        flush_cases()
        if report.when == "teardown":
            write(
                evidence_path() / "active-case.json", {"nodeid": item.nodeid, "phase": "completed"}
            )

    def pytest_collectreport(report):
        if report.failed:
            report.longrepr = "M4_OBSERVATION_COLLECTION_FAILED"
        report.sections = []

    def pytest_sessionfinish(session, exitstatus):
        flush_cases()
        summary = summarize(CASES, COLLECTED, int(exitstatus))
        write(evidence_path() / SUMMARY_REPORT, summary)
        if summary["result"] != "PASS" and session.exitstatus == 0:
            session.exitstatus = 1


def validate_collection(actual):
    expected = json.loads((evidence_path() / "inventory.json").read_text())["nodeids"]
    require(
        bool(actual) and actual == expected and len(set(actual)) == len(actual),
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
    completed = [c["nodeid"] for c in cases if any(p["phase"] == "teardown" for p in c["phases"])]
    started = [c["nodeid"] for c in cases]
    return {
        "completed": completed,
        "active": [n for n in started if n not in completed],
        "missing": [n for n in expected if n not in completed],
        "not_reached": [n for n in expected if n not in started],
        "pytest_exit": exitstatus,
        "cases": len(cases),
        "expected": len(expected),
        "complete": complete,
        "result": "PASS" if passed else "FAIL",
        "scope": "retained0014 and current0015 synthetic application; no live/paid transport",
        "paid_http": 0,
    }


def active_case(phase):
    write(
        evidence_path() / "active-case.json",
        {"nodeid": CASE["nodeid"], "phase": phase, "utc": time.time()},
    )
    flush_cases()


def flush_cases():
    write(
        evidence_path() / "cases.json",
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
    write(evidence_path() / "database-versions.json", value)


def root_path():
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    require(re.fullmatch(r"[1-9][0-9]{0,19}", run) and attempt == "1", "RUN_IDENTITY")
    return Path(os.environ["RUNNER_TEMP"]) / ("m4-runtime-" + run + "-" + attempt)


def admit_source(evidence):
    from scripts import native_context_db_catalog as catalog

    event, manifest = catalog.admit_event(evidence, entrypoint="run")
    require(event["attempt"] == "1", "RUN_ATTEMPT")
    require(
        event["ref"]
        in {"refs/heads/" + CAPTURE_BRANCH, "refs/heads/" + TARGETED_BRANCH, "refs/heads/main"}
        or event.get("head_ref") == BRANCH,
        "R2_EVENT_BRANCH",
    )
    require(capture(["git", "rev-parse", BASE + "^{tree}"]) == BASE_TREE, "BASE_TREE")
    require(capture(["git", "merge-base", BASE, "HEAD"]) == BASE, "BASE_ANCESTRY")
    allowed = {
        "backend/src/asm/ai/runtime.py",
        "backend/src/asm/ai/database.py",
        "backend/src/asm/ai/runtime_contracts.py",
        "backend/src/asm/messaging/worker.py",
        "backend/src/asm/foundation.py",
        "backend/src/asm/telegram/provisioning.py",
        "migrations/versions/0015_ai_delivery.py",
        "scripts/native_context_db_catalog.py",
        "scripts/m4_runtime_db.py",
        "scripts/test_browser.sh",
        "scripts/test_telegram_egress.sh",
        ".github/workflows/m4-runtime-db.yml",
        ".github/workflows/ci.yml",
        "tests/test_m4_delivery.py",
        "tests/test_m4_delivery_postgres.py",
        "tests/test_m4_schema_postgres.py",
        "tests/test_m4_runtime_database.py",
        "tests/test_m4_runtime_migrations.py",
        "tests/test_foundation.py",
        "tests/test_native_context_db_runner.py",
        "tests/test_m3_1_native_context_runtime_postgres.py",
        "tests/test_telegram_egress.py",
        "tests/test_m4_runtime_db_runner.py",
        "docs/tasks/M4_HANDOFF.md",
        "docs/TASK_REGISTER.md",
    }
    paths = capture(["git", "diff", "--name-only", BASE, "HEAD"]).splitlines()
    require(bool(paths) and set(paths) <= allowed, "R2_WRITE_SET")
    return event, manifest


def stock_catalog():
    """Independent stock facts before consulting the installed verifier/pin."""
    import psycopg
    from asm.foundation import NATIVE_CONTEXT_PROFILE_SHA256
    from psycopg.rows import dict_row
    from sqlalchemy.engine import make_url

    from scripts import native_context_db_catalog as catalog

    url = make_url(os.environ["ASM_MIGRATION_DATABASE_URL"])
    require(url.database == "asm_test" and url.username == "asm_migrator", "CATALOG_TARGET")
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    ) as c:
        c.execute("SET TRANSACTION READ ONLY")
        for sql in (
            "SET LOCAL search_path=pg_catalog,pg_temp",
            "SET LOCAL timezone='UTC'",
            "SET LOCAL extra_float_digits=3",
            "SET LOCAL statement_timeout='10s'",
        ):
            c.execute(sql)
        revision = c.execute("SELECT version_num FROM platform.alembic_version").fetchone()[0]
        require(revision in {"0013", "0015"}, "CATALOG_REVISION")
        destination = evidence_path() / ("catalog-" + revision)
        destination.mkdir(mode=0o700)
        expected = catalog.source_catalog(catalog.ROOT, revision)
        write(destination / "expected-source-catalog.json", expected)
        (destination / "independent-catalog.sql").write_text(
            catalog.CATALOG_SQL + ";\n" + catalog.FUNCTION_SQL + ";\n" + catalog.ROLE_SQL
        )
        full, nonfunction = c.execute(catalog.CATALOG_SQL).fetchone()
        (destination / "installed-catalog.pg-json.txt").write_text(full)
        (destination / "installed-nonfunction.pg-json.txt").write_text(nonfunction)
        locale = c.execute(
            "SELECT jsonb_build_object('server_version',current_setting('server_version'),'server_version_num',current_setting('server_version_num'),'lc_collate',datcollate,'lc_ctype',datctype,'provider',datlocprovider,'locale',to_jsonb(d)->'datlocale','collation_version',datcollversion,'encoding',pg_encoding_to_char(encoding)) FROM pg_database d WHERE datname=current_database()"
        ).fetchone()[0]
        locale["function_order"] = [row[0] for row in json.loads(full)["functions"]]
        locale["function_order_C"] = c.execute(
            "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app','platform') AND p.prokind='f' ORDER BY p.oid::regprocedure::text COLLATE \"C\""
        ).fetchall()
        write(destination / "locale-and-order.json", locale)
        require(locale["server_version_num"] == "180006", "CATALOG_SERVER_VERSION")
        c.row_factory = dict_row
        functions = c.execute(catalog.FUNCTION_SQL).fetchall()
        resolved = {
            r["signature"]: r["oid"]
            for r in c.execute(
                "SELECT signature,to_regprocedure(signature)::oid::bigint AS oid FROM unnest(%s::text[]) AS source(signature) ORDER BY signature",
                (sorted(expected["functions"]),),
            ).fetchall()
        }
        write(
            destination / "installed-function-oids.json",
            {"functions": functions, "resolved": resolved},
        )
        roles = c.execute(catalog.ROLE_SQL).fetchall()
        memberships = c.execute(
            "SELECT roleid,member FROM pg_auth_members WHERE roleid IN ('asm_runtime'::regrole,'asm_migrator'::regrole) OR member IN ('asm_runtime'::regrole,'asm_migrator'::regrole)"
        ).fetchall()
        owned = c.execute(
            "SELECT (SELECT count(*) FROM pg_database WHERE datdba='asm_runtime'::regrole) + (SELECT count(*) FROM pg_namespace WHERE nspowner='asm_runtime'::regrole) + (SELECT count(*) FROM pg_class WHERE relowner='asm_runtime'::regrole) + (SELECT count(*) FROM pg_proc WHERE proowner='asm_runtime'::regrole) AS count"
        ).fetchone()["count"]
        write(
            destination / "roles.json",
            {"roles": roles, "memberships": memberships, "owned_by_runtime": owned},
        )
        catalog.compare_roles(roles, memberships, owned)
        catalog.compare_functions(expected["functions"], functions, resolved)
        digest = catalog.compare_snapshot(expected["columns"], full, nonfunction, revision=revision)
        profile = "platform.ai_delivery_schema_profile()" if revision == "0015" else catalog.PROFILE
        declared = c.execute("SELECT " + profile + " AS profile").fetchone()["profile"]
        write(destination / "declared-profile.json", declared)
        comparison = {
            "revision": revision,
            "independent_profile_sha256": digest,
            "nonfunction_sha256": catalog.sha256(nonfunction.encode()),
            "functions_checked": len(functions),
            "tables_checked": len(expected["columns"]),
            "verifier_body_sha256": expected["functions"][profile]["body_sha256"],
            "all_source_bodies_security_roles_nonfunction": "PASS",
            "declared_equals_independent": declared
            == {"schema_revision": revision, "valid": True, "profile_sha256": digest},
            "application_pin_matches": revision == "0013"
            or digest == NATIVE_CONTEXT_PROFILE_SHA256,
            "failed_predicate": "APPLICATION_FULL_CATALOG_PIN"
            if revision == "0015" and digest != NATIVE_CONTEXT_PROFILE_SHA256
            else None,
        }
        write(destination / "comparison.json", comparison)
        require(comparison["declared_equals_independent"], "CATALOG_DECLARED_PROFILE")
        # Only this diagnostic mode permits the known application pin mismatch;
        # source bodies, security, full catalog coherence and cleanup still gate.


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
    # Each complete module owns a fresh cluster. In particular, used 0014/0015
    # downgrade guards are observed before destruction, never bypassed by row reset.
    require(not root.exists(), "RUN_ALREADY_STARTED")
    (root / "evidence").mkdir(parents=True, mode=0o700)
    (root / "private").mkdir(mode=0o700)
    event, manifest = admit_source(root / "evidence")
    diagnostic = event["ref"] == "refs/heads/" + CAPTURE_BRANCH
    modules = ["catalog"] if diagnostic else MODULES
    pins = dict(
        line.split("=", 1) for line in Path("infra/images.lock.env").read_text().splitlines()
    )
    require(pins["DB_IMAGE"] == DB_IMAGE, "DB_IMAGE_PIN")
    require(capture(["git", "rev-parse", BASE + "^{tree}"]) == BASE_TREE, "BASE_TREE")
    require(not Path(".env").exists(), "UNEXPECTED_ENV_FILE")
    source = {
        "base": BASE,
        "base_tree": BASE_TREE,
        "source": os.environ["GITHUB_SHA"],
        "tree": capture(["git", "rev-parse", "HEAD^{tree}"]),
        "paths": capture(["git", "diff", "--name-only", BASE, "HEAD"]).splitlines(),
        "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": 1,
        "event": os.environ["GITHUB_EVENT_NAME"],
        "branch": event.get("head_ref")
        or (event["ref"][11:] if event["ref"] != "refs/heads/main" else BRANCH),
        "pins": pins,
        "uv_lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
    }
    write(root / "evidence/source.json", source)
    write(root / "evidence/event.json", event)
    write(root / "evidence/source-manifest.json", manifest)
    subprocess.run(
        ["git", "archive", "--format=tar.gz", "-o", str(root / "evidence/source.tar.gz"), "HEAD"],
        check=True,
    )
    outcomes = []
    test_seconds = 0.0
    expected = None
    for index, module in enumerate(modules):
        group = root / (root.name + "-group-" + str(index))
        (group / "evidence").mkdir(parents=True, mode=0o700)
        (group / "private").mkdir(mode=0o700)
        write(group / "evidence/source.json", source)
        result = {"module": module, "outcome": "NOT_REACHED"}
        try:
            require(not any(inventory(group).values()), "RESOURCE_NAME_CONFLICT")
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
            (group / "private/test.env").write_text(
                "".join(k + "=" + v + "\n" for k, v in credentials.items())
            )
            write(
                group / "owned.json",
                {
                    "project": "asm-" + group.name,
                    "run_id": os.environ["GITHUB_RUN_ID"],
                    "attempt": 1,
                },
            )
            phase(group, "build", compose(group) + ["build", "checks"], 420)
            if expected is None and not diagnostic:
                phase(
                    group,
                    "inventory",
                    checks(
                        group,
                        "python",
                        "scripts/native_context_db_catalog.py",
                        "collect-m4",
                        "--inventory",
                        "/evidence/all-m4.json",
                    ),
                    90,
                )
                expected = json.loads((group / "evidence/all-m4.json").read_text())
                require(
                    expected["collection_exit"] == 0 and not expected["deselected"],
                    "INVENTORY_FAILED",
                )
                write(root / "evidence/inventory.json", expected)
                require(
                    {n.split("::", 1)[0] for n in expected["nodeids"]} == set(MODULES),
                    "INVENTORY_MODULES",
                )
                require(
                    sum(n.startswith(MODULES[0] + "::") for n in expected["nodeids"]) == 35,
                    "RETAINED_CASES_LOST",
                )
            nodes = (
                []
                if diagnostic
                else [n for n in expected["nodeids"] if n.startswith(module + "::")]
            )
            write(group / "evidence/inventory.json", {"nodeids": nodes})
            phase(
                group,
                "database-start",
                compose(group) + ["up", "-d", "--wait", "--wait-timeout", "80", "postgres-test"],
                120,
            )
            identity = capture(compose(group) + ["ps", "-q", "postgres-test"])
            status = capture(DOCKER + ["exec", identity, "cat", "/proc/1/status"])
            uid = int(
                next(line.split()[1] for line in status.splitlines() if line.startswith("Uid:"))
            )
            image_id = capture(DOCKER + ["inspect", "--format", "{{.Image}}", identity])
            require(
                uid != 0
                and image_id
                == capture(DOCKER + ["image", "inspect", "--format", "{{.Id}}", DB_IMAGE]),
                "SERVER_IDENTITY",
            )
            write(
                group / "evidence/server-process.json",
                {"uid": uid, "image_id": image_id, "pin": DB_IMAGE},
            )
            if diagnostic:
                for revision in ("0013", "0015"):
                    phase(
                        group,
                        "schema-" + revision,
                        checks(group, "alembic", "upgrade", revision),
                        120,
                    )
                    phase(
                        group,
                        "catalog-" + revision,
                        checks(group, "python", "scripts/m4_runtime_db.py", "catalog-snapshot"),
                        60,
                    )
                result["outcome"] = "PASS"
                continue
            phase(group, "schema", checks(group, "alembic", "upgrade", "0014"), 120)
            phase(
                group,
                "versions",
                checks(group, "python", "scripts/m4_runtime_db.py", "versions"),
                30,
            )
            require(test_seconds < 600, "TOTAL_TEST_BUDGET_EXHAUSTED")
            started = time.monotonic()
            try:
                phase(
                    group,
                    COMMAND_REPORT,
                    checks(
                        group,
                        "pytest",
                        "-p",
                        "scripts.m4_runtime_db",
                        "-q",
                        "--tb=short",
                        "--show-capture=no",
                        "-p",
                        "no:cacheprovider",
                        "--junitxml=/evidence/junit.xml",
                        module,
                        plugin=True,
                    ),
                    600 - test_seconds,
                )
            finally:
                test_seconds += time.monotonic() - started
            summary = json.loads((group / "evidence" / SUMMARY_REPORT).read_text())
            require(
                summary["result"] == "PASS" and summary["complete"], "RUNTIME_EVIDENCE_INCOMPLETE"
            )
            result["outcome"] = "PASS"
        except Exception as error:
            result.update(
                outcome="FAIL",
                error_type=type(error).__name__,
                code=str(error)
                if re.fullmatch(r"[A-Z0-9_]{1,80}", str(error))
                else "OPERATION_FAILED",
            )
        finally:
            if not diagnostic:
                cases_path = group / "evidence/cases.json"
                summary_path = group / "evidence" / SUMMARY_REPORT
                if not summary_path.exists():
                    cases = json.loads(cases_path.read_text()) if cases_path.exists() else []
                    nodes_path = group / "evidence/inventory.json"
                    nodes = (
                        json.loads(nodes_path.read_text())["nodeids"] if nodes_path.exists() else []
                    )
                    write(summary_path, summarize(cases, nodes, None))
                result["tests"] = json.loads(summary_path.read_text())
            write(group / "evidence/primary.json", result)
            try:
                cleanup(group)
            except Exception as error:
                result.update(outcome="FAIL", cleanup=type(error).__name__)
            outcomes.append(result)
            write(
                root / "evidence/summary.json",
                {
                    "groups": outcomes,
                    "test_seconds": test_seconds,
                    "groups_visited": len(outcomes),
                    "complete": len(outcomes) == len(modules)
                    and all(
                        v.get("tests", {}).get("complete", diagnostic and v["outcome"] == "PASS")
                        for v in outcomes
                    ),
                    "result": "PASS"
                    if len(outcomes) == len(modules)
                    and all(v["outcome"] == "PASS" for v in outcomes)
                    else "FAIL",
                },
            )
            shutil.copytree(group / "evidence", root / "evidence" / group.name, dirs_exist_ok=True)
    clean = not capture(["git", "status", "--porcelain", "--untracked-files=all"])
    write(root / "evidence/source-preservation.json", {"clean": clean})
    require(clean, "SOURCE_CHANGED")
    require(all(v["outcome"] == "PASS" for v in outcomes), "PRIMARY_FAILED")


def main():
    os.umask(0o077)
    if sys.argv[1:] == ["catalog-snapshot"]:
        stock_catalog()
        return
    if sys.argv[1:] == ["versions"]:
        versions()
        return
    require(sys.argv[1:] in (["run"], ["cleanup"]), "USAGE")
    root = root_path()
    if sys.argv[1] == "run":
        run(root)
    else:
        try:
            for group in sorted(root.glob("*-group-*")):
                cleanup(group)
                shutil.copytree(
                    group / "evidence", root / "evidence" / group.name, dirs_exist_ok=True
                )
        finally:
            if (root / "evidence").exists():
                files = {
                    str(p.relative_to(root / "evidence")): {
                        "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in (root / "evidence").rglob("*")
                    if p.is_file() and p.name != "manifest.json"
                }
                write(root / "evidence/manifest.json", files)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        main()
    except Exception as error:
        code = str(error)
        print(
            "M4_PG_STOP="
            + (code if re.fullmatch(r"[A-Z0-9_]{1,80}", code) else type(error).__name__)
        )
        raise SystemExit(1) from None
