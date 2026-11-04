"""C3-M4.3-RUNTIME-INTEGRATION-R8: separate owned PG18 application carrier."""

import asyncio
import contextlib
import functools
import hashlib
import inspect
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
import traceback
from pathlib import Path
from uuid import UUID

BASE = "c7ee300ae4182152eb9c8636d2f958da087113f2"
BASE_TREE = "a978f014177b2e6c66cee3a9221435449e01adc0"
BRANCH = "c3/m4-3-runtime-integration-pr-r8"
TARGETED_BRANCH = "c3/m4-3-runtime-targeted-run-r8"
DB_IMAGE = (
    "pgvector/pgvector@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
)
MODULES = [
    "tests/test_m4_runtime_postgres.py",
    "tests/test_m4_delivery_postgres.py",
    "tests/test_m4_schema_postgres.py",
]
CURRENT_NATIVE_MODULE = "tests/test_m3_1_native_context_runtime_postgres.py"
# Exactly the six R1 cases blocked by the current0015 schema prerequisite.
# In full CI they remain in the complete native lane, outside the M4 partition.
CURRENT_NATIVE_NODES = [
    CURRENT_NATIVE_MODULE + "::test_native_host_" + name
    for name in (
        "policy_enable_noop_pause_old_replay_and_current",
        "policy_wrong_cas_and_key_conflict_roll_back[stale]",
        "policy_wrong_cas_and_key_conflict_roll_back[key]",
        "policy_catalog_drift_refuses_without_new_authority",
        "committed_receipt_survives_current_failure_then_read_only_retry",
        "unreadable_result_rolls_back_real_capability",
    )
]
COMMAND_REPORT = "runtime-command"
SUMMARY_REPORT = "runtime-summary.json"
COLLECTED = []
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
CASE = None
CASES = []
EVENT_LIMIT = 8192
PROBE_CONSTRAINTS = {
    "messaging_jobs_telegram_probe_check",
    "messaging_jobs_telegram_probe_generation_check",
    "messaging_jobs_telegram_probe_version_check",
}


class Refusal(RuntimeError):
    """A known carrier predicate, safe to preserve without exception values."""


def require(condition, code):
    if not condition:
        raise Refusal(code)


def failure_details(error):
    return {
        "error_type": type(error).__name__[:80],
        "code": str(error)
        if isinstance(error, Refusal) and re.fullmatch(r"[A-Z0-9_]{1,80}", str(error))
        else "OPERATION_FAILED",
        "frames": [
            {
                "file": Path(frame.filename).name[:120],
                "function": frame.name[:120],
                "line": frame.lineno,
            }
            for frame in traceback.extract_tb(error.__traceback__, limit=-8)
        ],
    }


def case_failure_details(excinfo):
    """Keep only bounded locations and known SQL diagnostics, never exception values."""
    from asm.messaging.errors import MessagingError
    from sqlalchemy.exc import DBAPIError

    data = {"exception_type": excinfo.typename[:80]}
    error = excinfo.value
    if isinstance(error, MessagingError):
        data["error_code"] = error.code.value
    if isinstance(error, DBAPIError):
        sqlstate = getattr(error.orig, "sqlstate", None)
        if type(sqlstate) is str and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
            data["sqlstate"] = sqlstate
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if type(constraint) is str and constraint in PROBE_CONSTRAINTS:
            data["constraint_name"] = constraint
    frames = traceback.extract_tb(error.__traceback__)
    data["frames"] = [
        {"file": Path(f.filename).name[:120], "function": f.name[:120], "line": f.lineno}
        for f in frames[-12:]
    ]
    application = []
    root = Path(__file__).resolve().parents[1]
    for frame in frames:
        try:
            path = Path(frame.filename).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if (
            (path.startswith("backend/src/asm/") or path.startswith("tests/"))
            and path.endswith(".py")
            and len(path) <= 180
            and re.fullmatch(r"[A-Za-z0-9_<>]{1,120}", frame.name)
        ):
            location = {"file": path, "function": frame.name, "line": frame.lineno}
            if location not in application:
                application.append(location)
    data["application_frames"] = application[-8:]
    return data


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
            or value["branch"] == TARGETED_BRANCH
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
        "SELECTION",
        "MODEL_ENTER",
        "TIMEOUT",
        "REPLAY",
        "SEND",
        "STALE_OBSERVATION",
        "SEND_ATTEMPT",
        "SEND_REPLAY",
        "OLD_CHECK_REJECTION",
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
        elif (
            name == "state"
            and type(value) is str
            and value in {"COLLECTING", "WAITING_MEDIA", "READY", "FAILED"}
        ):
            event[name] = value
        elif name == "selected_kind" and (
            value is None or type(value) is str and value in {"reply", "handoff", "no_reply"}
        ):
            event[name] = value
        elif (
            name in {"call_count", "reservation_count", "observe_count", "send_count"}
            and type(value) is int
            and 0 <= value <= 2
        ):
            event[name] = value
        elif (
            name
            in {
                "adapter_entered",
                "adapter_cancelled",
                "has_result",
                "has_outbox",
                "reserve_held",
                "completion_unknown_metering",
                "send_completed",
            }
            and type(value) is bool
        ):
            event[name] = value
        elif (
            name == "job_state"
            and type(value) is str
            and value in {"READY", "RUNNING", "SUCCEEDED", "DEAD"}
        ):
            event[name] = value
        elif name == "error_code" and (
            value is None
            or type(value) is str
            and value
            in {
                "DEPENDENCY_UNAVAILABLE",
                "UNKNOWN_EXTERNAL_RESULT",
                "NOT_ALLOWED",
                "STALE_CLAIM",
                "AI_STALE",
                "AI_BUDGET",
                "AI_INCOMPLETE",
                "TIMEOUT",
                "CANCELLED",
            }
        ):
            event[name] = value
        elif name == "constraint_name" and type(value) is str and value in PROBE_CONSTRAINTS:
            event[name] = value
        elif name == "sqlstate" and type(value) is str and value == "23514":
            event[name] = value
        else:
            CASE["invalid_fields"] += 1
            return
    CASE["events"].append(event)
    flush_cases()


if os.environ.get("ASM_M4_PG_PLUGIN") == "1":
    import pytest

    def pytest_collection_modifyitems(session, config, items):
        global COLLECTED
        COLLECTED = [item.nodeid for item in items]
        write(evidence_path() / "collected.json", COLLECTED)
        validate_collection(COLLECTED)
        if os.environ.get("ASM_M4_CURRENT_NATIVE") == "1":
            guard_current_native(items)

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
            data.update(case_failure_details(call.excinfo))
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


def native_identity():
    """The native reset runs only in the namespace of our fresh owned server."""
    import psycopg
    from sqlalchemy.engine import make_url

    admin = make_url(os.environ["ASM_NATIVE_TEST_ADMIN_URL"])
    require(
        os.environ.get("ASM_NATIVE_TEST_ALLOW_RESET") == "1"
        and admin.host == "127.0.0.1"
        and admin.port == 5432
        and admin.database == "postgres"
        and admin.username == "asm_admin",
        "CURRENT_NATIVE_ADMIN_TARGET",
    )
    for key, user in (
        ("ASM_DATABASE_URL", "asm_runtime"),
        ("ASM_MIGRATION_DATABASE_URL", "asm_migrator"),
    ):
        url = make_url(os.environ[key])
        require(
            (url.host, url.port, url.database, url.username)
            == (admin.host, admin.port, "asm_test", user),
            "CURRENT_NATIVE_TARGET",
        )
    with psycopg.connect(admin.render_as_string(hide_password=False), connect_timeout=5) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        row = c.execute(
            "SELECT system_identifier::text,pg_postmaster_start_time()::text,current_setting('server_version_num'),session_user,current_database() FROM pg_control_system()"
        ).fetchone()
    require(row[2:] == ("180006", "asm_admin", "postgres"), "CURRENT_NATIVE_SERVER")
    return {"system_identifier": row[0], "postmaster_start": row[1], "server_version_num": row[2]}


def guard_current_native(items):
    from scripts import native_context_db_catalog as catalog

    require([item.nodeid for item in items] == CURRENT_NATIVE_NODES, "CURRENT_NATIVE_SELECTION")
    module = sys.modules["test_m3_1_native_context_postgres"]
    native = inspect.unwrap(module.native)
    original = module.reset_disposable
    original_identity = module.source_tree_identity
    require(
        Path(original.__code__.co_filename).resolve() == catalog.ROOT / catalog.MODULES[1]
        and native.__globals__ is vars(module)
        and inspect.isfunction(original_identity)
        and original_identity.__name__ == "source_tree_identity"
        and Path(original_identity.__code__.co_filename).resolve()
        == catalog.ROOT / catalog.MODULES[1]
        and original_identity.__globals__ is vars(module)
        and native.__globals__["source_tree_identity"] is original_identity
        and all(
            inspect.unwrap(item._fixtureinfo.name2fixturedefs["native"][-1].func) is native
            for item in items
        ),
        "CURRENT_NATIVE_RESET_IMPLEMENTATION",
    )
    baseline = json.loads((evidence_path() / "native-owner.json").read_text())
    proofs = []
    identities = []

    def checked_source_tree():
        tree, _ = catalog.require_source(catalog.ROOT, os.environ["ASM_M4_SOURCE_SHA"])
        require(tree == source_tree_from_evidence(), "CURRENT_NATIVE_SOURCE")
        return tree

    @functools.wraps(original_identity)
    def checked_identity():
        # The historical fixture writes a temporary Git index. This carrier has
        # a read-only checkout; prove all actual bytes/modes again at point of use.
        tree = checked_source_tree()
        identities.append({"identity": len(identities) + 1, "source_tree": tree})
        write(evidence_path() / "native-identity-proofs.json", identities)
        return tree

    @functools.wraps(original)
    def checked_reset():
        tree = checked_source_tree()
        actual = native_identity()
        require(actual == baseline, "CURRENT_NATIVE_SERVER_CHANGED")
        proofs.append({"reset": len(proofs) + 1, "source_tree": tree, **actual})
        write(evidence_path() / "before-reset-proofs.json", proofs)
        return original()

    module.reset_disposable = checked_reset
    module.source_tree_identity = checked_identity
    write(
        evidence_path() / "fixture-guards.json",
        {
            "nodeids": CURRENT_NATIVE_NODES,
            "reset": catalog.MODULES[1] + "::reset_disposable",
            "source_and_server_before_each_reset": True,
            "identity": catalog.MODULES[1] + "::source_tree_identity",
            "full_source_check_at_identity_use": True,
        },
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
    called = [c["nodeid"] for c in cases if any(p["phase"] == "call" for p in c["phases"])]
    return {
        "completed": completed,
        "active": [n for n in started if n not in completed],
        "missing": [n for n in expected if n not in completed],
        "not_reached": [n for n in expected if n not in started],
        "call_reached": called,
        "missing_call_phases": [n for n in expected if n not in called],
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
        event["ref"] in {"refs/heads/" + TARGETED_BRANCH, "refs/heads/main"}
        or event.get("head_ref") == BRANCH,
        "R8_EVENT_BRANCH",
    )
    require(capture(["git", "rev-parse", BASE + "^{tree}"]) == BASE_TREE, "BASE_TREE")
    require(capture(["git", "merge-base", BASE, "HEAD"]) == BASE, "BASE_ANCESTRY")
    allowed = {
        "scripts/native_context_db_catalog.py",
        "scripts/m4_runtime_db.py",
        ".github/workflows/m4-runtime-db.yml",
        "tests/test_m4_runtime_db_runner.py",
        "tests/test_m4_schema_postgres.py",
        "docs/tasks/M4_HANDOFF.md",
        "docs/TASK_REGISTER.md",
    }
    paths = capture(["git", "diff", "--name-only", BASE, "HEAD"]).splitlines()
    require(bool(paths) and set(paths) <= allowed, "R8_WRITE_SET")
    write(
        evidence / "source-admission.json",
        {
            "base": BASE,
            "base_tree": BASE_TREE,
            "source": event["head"],
            "tree": event["tree"],
            "paths": paths,
            "result": "PASS",
        },
    )
    return event, manifest


def catalog_comparison(expected, digest, nonfunction, declared):
    from asm.foundation import NATIVE_CONTEXT_PROFILE_SHA256, NATIVE_PROFILE_BODY_SHA256

    revision = expected["revision"]
    profile = (
        "platform.ai_delivery_schema_profile()"
        if revision == "0015"
        else "platform.human_context_schema_profile()"
    )
    body_hash = expected["functions"][profile]["body_sha256"]
    declared_matches = (
        declared == {"schema_revision": revision, "valid": True, "profile_sha256": digest}
        and type(declared.get("valid")) is bool
    )
    pin_matches = revision == "0013" or digest == NATIVE_CONTEXT_PROFILE_SHA256
    body_matches = revision == "0013" or body_hash == NATIVE_PROFILE_BODY_SHA256
    return {
        "revision": revision,
        "independent_profile_sha256": digest,
        "nonfunction_sha256": hashlib.sha256(nonfunction.encode()).hexdigest(),
        "functions_checked": len(expected["functions"]),
        "tables_checked": len(expected["columns"]),
        "verifier_body_sha256": body_hash,
        "application_body_pin_matches": body_matches,
        "application_profile_pin": NATIVE_CONTEXT_PROFILE_SHA256,
        "application_body_pin": NATIVE_PROFILE_BODY_SHA256,
        "all_source_bodies_security_roles_nonfunction": "PASS",
        "declared_equals_independent": declared_matches,
        "application_pin_matches": pin_matches,
        "failed_predicate": "CATALOG_DECLARED_PROFILE"
        if not declared_matches
        else "APPLICATION_VERIFIER_BODY_PIN"
        if not body_matches
        else "APPLICATION_FULL_CATALOG_PIN"
        if not pin_matches
        else None,
    }


def stock_catalog():
    """Independent stock facts before consulting the installed verifier/pin."""
    import psycopg
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
        if revision == "0015":
            write(
                destination / "embedded-invariant.json", catalog.compare_embedded_profile(expected)
            )
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
        comparison = catalog_comparison(expected, digest, nonfunction, declared)
        write(destination / "comparison.json", comparison)
        require(comparison["failed_predicate"] is None, comparison["failed_predicate"])


async def readiness():
    from asm.foundation import RuntimeDatabase, Settings

    runtime = RuntimeDatabase(Settings())
    try:
        await runtime.check()
        write(evidence_path() / "readiness.json", {"revision": "0015", "runtime_check": "PASS"})
    finally:
        await runtime.close()


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


def phase(root, label, args, budget, *, separate_stdout=False):
    reports = root / "evidence/phases"
    reports.mkdir(exist_ok=True, mode=0o700)
    start = time.monotonic()
    entry = {"phase": label, "command": args, "budget_seconds": budget, "started_utc": time.time()}
    write(reports / "active.json", entry)
    private = root / ("private/" + label + ".log")
    with (
        private.open("wb") as output,
        (
            (root / ("private/" + label + ".stdout")).open("wb")
            if separate_stdout
            else contextlib.nullcontext(output)
        ) as stdout,
    ):
        process = subprocess.Popen(args, stdout=stdout, stderr=output, start_new_session=True)
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
    write(reports / (label + ".json"), entry)
    with private.open("rb") as stream:
        raw = stream.read(8388609)
    if len(raw) > 8388608:
        raw = raw[:8388608]
        entry["log_incomplete"] = True
        write(reports / (label + ".json"), entry)
    (reports / (label + ".log")).write_text(sanitize(raw, root))
    print("M4_PG_PHASE=" + label + " EXIT=" + str(code), flush=True)
    require(code == 0, label.upper().replace("-", "_") + "_FAILED")


def stack_diagnostics(root, prefix):
    """Bounded startup evidence: states and known schema-refusal fields only."""
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True, mode=0o700)
    result = {"services": [], "schema_refusals": [], "probe_errors": []}
    for kind, tail in (
        ("states", ["ps", "--all", "--format", "json"]),
        ("logs", ["logs", "--no-color", "--tail", "80", "api", "worker", "migrate"]),
    ):
        try:
            proc = subprocess.run([*prefix, *tail], capture_output=True, timeout=10)
            if proc.returncode or len(proc.stdout) > 262144:
                result["probe_errors"].append(
                    {"probe": kind, "exit": proc.returncode, "bounded": len(proc.stdout) <= 262144}
                )
                continue
            raw = proc.stdout.decode(errors="replace")
            if kind == "states":
                rows = (
                    json.loads(raw)
                    if raw.lstrip().startswith("[")
                    else [json.loads(line) for line in raw.splitlines() if line.strip()]
                )
                for row in rows[:32]:
                    service = row.get("Service", "")
                    if re.fullmatch(r"[a-z][a-z0-9-]{0,48}", service):
                        result["services"].append(
                            {
                                "service": service,
                                "state": row.get("State")
                                if row.get("State")
                                in {
                                    "running",
                                    "exited",
                                    "created",
                                    "restarting",
                                    "dead",
                                    "removing",
                                    "paused",
                                }
                                else "UNKNOWN",
                                "health": row.get("Health")
                                if row.get("Health") in {"", "healthy", "unhealthy", "starting"}
                                else "UNKNOWN",
                                "exit_code": row.get("ExitCode")
                                if type(row.get("ExitCode")) is int
                                else None,
                            }
                        )
            else:
                for line in raw.splitlines():
                    if "{" not in line:
                        continue
                    try:
                        row = json.loads(line[line.index("{") :])
                    except ValueError:
                        continue
                    if (
                        type(row) is dict
                        and row.get("component") == "schema-admission"
                        and row.get("event") == "refused"
                        and row.get("stage")
                        in {"VERIFIER_BODY_OR_SECURITY", "DECLARED_PROFILE_OR_FULL_PIN"}
                    ):
                        error = row.get("error_type", "")
                        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,60}", error):
                            result["schema_refusals"].append(
                                {"stage": row["stage"], "error_type": error}
                            )
        except Exception as error:
            result["probe_errors"].append({"probe": kind, "error_type": type(error).__name__})
    write(evidence / "stack-diagnostics.json", result)


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


def current_native_checks(root, label, *args):
    """Use the built locked image, actual read-only Git checkout and owned DB namespace."""
    values = dict(
        line.split("=", 1) for line in (root / "private/test.env").read_text().splitlines()
    )
    env = {
        "ASM_ENVIRONMENT": "TEST",
        "ASM_NATIVE_TEST_ALLOW_RESET": "1",
        "ASM_M4_CURRENT_NATIVE": "1",
        "ASM_M4_PG_PLUGIN": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ASM_M4_SOURCE_SHA": os.environ["GITHUB_SHA"],
        "ASM_M4_SOURCE_TREE": capture(["git", "rev-parse", "HEAD^{tree}"]),
        "ASM_M4_RUN_ID": os.environ["GITHUB_RUN_ID"],
        "ASM_M4_RUN_ATTEMPT": "1",
    }
    for name, user, key, database, driver in (
        (
            "ASM_DATABASE_URL",
            "asm_runtime",
            "PG_RUNTIME_PASSWORD",
            "asm_test",
            "postgresql+psycopg",
        ),
        (
            "ASM_MIGRATION_DATABASE_URL",
            "asm_migrator",
            "PG_MIGRATION_PASSWORD",
            "asm_test",
            "postgresql+psycopg",
        ),
        ("ASM_NATIVE_TEST_ADMIN_URL", "asm_admin", "PG_ADMIN_PASSWORD", "postgres", "postgresql"),
    ):
        env[name] = f"{driver}://{user}:{values[key]}@127.0.0.1:5432/{database}"
    env_path = root / "private/native.env"
    env_path.write_text("".join(k + "=" + v + "\n" for k, v in env.items()))
    identity = capture(compose(root) + ["ps", "-q", "postgres-test"])
    image = capture(
        DOCKER + ["image", "inspect", "--format", "{{.Id}}", "asm-" + root.name + "-checks"]
    )
    return DOCKER + [
        "run",
        "--rm",
        "--cidfile",
        str(root / ("private/" + label + ".cid")),
        "--label",
        "com.docker.compose.project=asm-" + root.name,
        "--label",
        "asm.m4.run=" + os.environ["GITHUB_RUN_ID"],
        "--label",
        "asm.m4.attempt=1",
        "--network",
        "container:" + identity,
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env-file",
        str(env_path),
        "--volume",
        str(Path.cwd()) + ":/app:ro",
        "--volume",
        str(root / "evidence") + ":/evidence",
        image,
        *args,
    ]


def collect_current_native():
    import pytest

    require(not os.environ.get("PYTEST_ADDOPTS"), "CURRENT_NATIVE_EXTERNAL_SELECTION")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    data = {"nodeids": [], "deselected": []}

    class Inventory:
        def pytest_collection_finish(self, session):
            data["nodeids"] = [item.nodeid for item in session.items]
            require(data["nodeids"] == CURRENT_NATIVE_NODES, "CURRENT_NATIVE_SELECTION")
            require(
                all(
                    not item.get_closest_marker(m)
                    for item in session.items
                    for m in ("skip", "skipif", "xfail")
                ),
                "CURRENT_NATIVE_SKIP",
            )

        def pytest_deselected(self, items):
            data["deselected"].extend(item.nodeid for item in items)

        def pytest_runtest_setup(self, item):
            raise RuntimeError("INVENTORY_MUST_NOT_EXECUTE")

    code = 1
    try:
        code = int(
            pytest.main(
                [
                    *CURRENT_NATIVE_NODES,
                    "--collect-only",
                    "-q",
                    "-p",
                    "pytest_asyncio.plugin",
                    "-p",
                    "no:cacheprovider",
                ],
                plugins=[Inventory()],
            )
        )
    finally:
        write(evidence_path() / "current-native-inventory.json", {**data, "collection_exit": code})
    require(code == 0 and not data["deselected"], "CURRENT_NATIVE_COLLECTION")


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
        # A cancelled docker-run client need not have stopped its container.
        # Its cidfile and exact run/project labels bind this cleanup authority.
        for cidfile in sorted((root / "private").glob("*.cid")):
            cid = cidfile.read_text().strip()
            require(re.fullmatch(r"[0-9a-f]{64}", cid), "NATIVE_CLEANUP_ID")
            if capture(DOCKER + ["ps", "-aq", "--filter", "id=" + cid]):
                labels = json.loads(
                    capture(DOCKER + ["inspect", "--format", "{{json .Config.Labels}}", cid])
                )
                require(
                    all(
                        labels.get(k) == v
                        for k, v in {
                            "com.docker.compose.project": "asm-" + root.name,
                            "asm.m4.run": os.environ["GITHUB_RUN_ID"],
                            "asm.m4.attempt": "1",
                        }.items()
                    ),
                    "NATIVE_CLEANUP_OWNERSHIP",
                )
                phase(root, "native-cleanup-" + cidfile.stem, DOCKER + ["rm", "-f", cid], 30)
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
        attempts.append({"outcome": "FAIL", **failure_details(error)})
        write(evidence / "cleanup.json", {"outcome": "FAIL", "attempts": attempts})
        raise


def run(root):
    # Each complete module owns a fresh cluster. In particular, used 0014/0015
    # downgrade guards are observed before destruction, never bypassed by row reset.
    require(not root.exists(), "RUN_ALREADY_STARTED")
    (root / "evidence").mkdir(parents=True, mode=0o700)
    (root / "private").mkdir(mode=0o700)
    event, manifest = admit_source(root / "evidence")
    mode = "targeted" if event["ref"] == "refs/heads/" + TARGETED_BRANCH else "runtime"
    write(root / "evidence/mode.json", {"mode": mode})
    run_admitted(root, event, manifest, mode)


def run_admitted(root, event, manifest, mode):
    # No resource access or credentials before the complete source admission.
    require(mode in {"targeted", "runtime"}, "R5_MODE")
    modules = ["preflight", *MODULES]
    planned = dict(zip(MODULES, (35, 22, 9), strict=True))
    native_nodes = CURRENT_NATIVE_NODES if mode == "targeted" else []
    if mode == "targeted":
        modules.append(CURRENT_NATIVE_MODULE)
        planned[CURRENT_NATIVE_MODULE] = len(native_nodes)
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
    outcomes, all_nodes, collected_nodes = [], list(native_nodes), []
    test_seconds = sql_test_seconds = 0.0

    def inventory_record():
        return {
            "mode": mode,
            "planned_cases_by_module": planned,
            "expected_cases": sum(planned.values()),
            "nodeids": all_nodes,
            "inventory_complete": len(all_nodes) == sum(planned.values()),
            "unknown_inventory_cases": sum(planned.values()) - len(all_nodes),
            "collected_nodeids": collected_nodes,
            "collected_cases": len(collected_nodes),
            "collection_complete": len(collected_nodes) == sum(planned.values()),
        }

    write(root / "evidence/inventory.json", inventory_record())

    def sql_phase(group, name, command, cap):
        nonlocal sql_test_seconds, test_seconds
        require(sql_test_seconds < 600, "TOTAL_SQL_TEST_BUDGET_EXHAUSTED")
        start = time.monotonic()
        try:
            phase(group, name, command, min(cap, 600 - sql_test_seconds))
        finally:
            elapsed = time.monotonic() - start
            sql_test_seconds += elapsed
            if name == COMMAND_REPORT:
                test_seconds += elapsed
        require(sql_test_seconds <= 600, "TOTAL_SQL_TEST_BUDGET_EXHAUSTED")

    for index, module in enumerate(modules):
        group = root / (root.name + "-group-" + str(index))
        (group / "evidence").mkdir(parents=True, mode=0o700)
        (group / "private").mkdir(mode=0o700)
        write(group / "evidence/source.json", source)
        nodes = (
            [] if module == "preflight" else [n for n in all_nodes if n.startswith(module + "::")]
        )
        write(group / "evidence/inventory.json", {"nodeids": nodes})
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
            if module == "preflight":
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
                m4_nodes = expected["nodeids"]
                require(
                    {n.split("::", 1)[0] for n in m4_nodes} == set(MODULES), "INVENTORY_MODULES"
                )
                require(
                    all(
                        sum(n.startswith(m + "::") for n in m4_nodes) == planned[m] for m in MODULES
                    ),
                    "RETAINED_CASES_LOST",
                )
                planned_nodes = [*m4_nodes, *native_nodes]
                require(len(planned_nodes) == len(set(planned_nodes)), "INVENTORY_DUPLICATE")
                all_nodes = planned_nodes
                collected_nodes = list(m4_nodes)
                write(root / "evidence/inventory.json", inventory_record())
                if mode == "targeted":
                    phase(
                        group,
                        "current-native-inventory",
                        checks(
                            group, "python", "scripts/m4_runtime_db.py", "collect-current-native"
                        ),
                        60,
                    )
                    native = json.loads(
                        (group / "evidence/current-native-inventory.json").read_text()
                    )
                    require(
                        native["collection_exit"] == 0
                        and not native["deselected"]
                        and native["nodeids"] == CURRENT_NATIVE_NODES,
                        "CURRENT_NATIVE_SELECTION",
                    )
                    collected_nodes.extend(native["nodeids"])
                write(root / "evidence/inventory.json", inventory_record())
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
                {"uid": uid, "image_id": image_id, "pin": DB_IMAGE, "container_id": identity},
            )
            if module == "preflight":
                sql_phase(group, "schema-0015", checks(group, "alembic", "upgrade", "0015"), 120)
                sql_phase(
                    group,
                    "catalog-0015",
                    checks(group, "python", "scripts/m4_runtime_db.py", "catalog-snapshot"),
                    60,
                )
                sql_phase(
                    group,
                    "readiness",
                    checks(group, "python", "scripts/m4_runtime_db.py", "readiness"),
                    30,
                )
            else:
                require(bool(nodes), "EMPTY_MODULE_INVENTORY")
                if module == CURRENT_NATIVE_MODULE:
                    sql_phase(
                        group,
                        "native-owner",
                        current_native_checks(
                            group,
                            "native-owner",
                            "python",
                            "scripts/m4_runtime_db.py",
                            "native-owner",
                        ),
                        30,
                    )
                else:
                    sql_phase(group, "schema", checks(group, "alembic", "upgrade", "0014"), 120)
                    sql_phase(
                        group,
                        "versions",
                        checks(group, "python", "scripts/m4_runtime_db.py", "versions"),
                        30,
                    )
                arguments = [
                    "pytest",
                    "-p",
                    "scripts.m4_runtime_db",
                    "-q",
                    "--tb=short",
                    "--show-capture=no",
                    "-p",
                    "no:cacheprovider",
                    "--junitxml=/evidence/junit.xml",
                ]
                command = (
                    current_native_checks(group, "native-tests", *arguments, *nodes)
                    if module == CURRENT_NATIVE_MODULE
                    else checks(group, *arguments, module, plugin=True)
                )
                sql_phase(group, COMMAND_REPORT, command, 600)
                summary = json.loads((group / "evidence" / SUMMARY_REPORT).read_text())
                require(
                    summary["result"] == "PASS" and summary["complete"],
                    "RUNTIME_EVIDENCE_INCOMPLETE",
                )
                if module == CURRENT_NATIVE_MODULE:
                    proofs = json.loads((group / "evidence/before-reset-proofs.json").read_text())
                    require(
                        len(proofs) == len(CURRENT_NATIVE_NODES),
                        "CURRENT_NATIVE_RESET_COMPLETENESS",
                    )
                    identities = json.loads(
                        (group / "evidence/native-identity-proofs.json").read_text()
                    )
                    require(
                        len(identities) == len(CURRENT_NATIVE_NODES),
                        "CURRENT_NATIVE_IDENTITY_COMPLETENESS",
                    )
            result["outcome"] = "PASS"
        except Exception as error:
            result.update(outcome="FAIL", **failure_details(error))
            active_phase = group / "evidence/phases/active.json"
            if active_phase.exists():
                result["last_phase"] = json.loads(active_phase.read_text())["phase"]
        finally:
            if module != "preflight":
                cases_path = group / "evidence/cases.json"
                summary_path = group / "evidence" / SUMMARY_REPORT
                if not summary_path.exists():
                    cases = json.loads(cases_path.read_text()) if cases_path.exists() else []
                    write(summary_path, summarize(cases, nodes, None))
                result["tests"] = json.loads(summary_path.read_text())
            write(group / "evidence/primary.json", result)
            try:
                cleanup(group)
            except Exception as error:
                result.update(outcome="FAIL", cleanup=failure_details(error))
            outcomes.append(result)
            completed = {n for v in outcomes for n in v.get("tests", {}).get("completed", [])}
            started = {
                n
                for v in outcomes
                for n in v.get("tests", {}).get("completed", [])
                + v.get("tests", {}).get("active", [])
            }
            called = {n for v in outcomes for n in v.get("tests", {}).get("call_reached", [])}
            write(root / "evidence/inventory.json", inventory_record())
            write(
                root / "evidence/summary.json",
                {
                    "groups": outcomes,
                    "test_seconds": test_seconds,
                    "sql_test_seconds": sql_test_seconds,
                    "sql_test_budget_seconds": 600,
                    "groups_visited": len(outcomes),
                    "groups_expected": modules,
                    "not_reached_modules": modules[len(outcomes) :],
                    "planned_cases_by_module": planned,
                    "expected_cases": sum(planned.values()),
                    "inventory_complete": len(all_nodes) == sum(planned.values()),
                    "unknown_inventory_cases": sum(planned.values()) - len(all_nodes),
                    "collected_cases": len(collected_nodes),
                    "collection_complete": len(collected_nodes) == sum(planned.values()),
                    "missing_count": sum(planned.values()) - len(completed),
                    "not_reached_count": sum(planned.values()) - len(started),
                    "missing_call_phase_count": sum(planned.values()) - len(called),
                    "missing_call_phases": [n for n in all_nodes if n not in called],
                    "missing": [n for n in all_nodes if n not in completed],
                    "not_reached": [n for n in all_nodes if n not in started],
                    "complete": len(outcomes) == len(modules)
                    and all(
                        v.get("tests", {}).get(
                            "complete", v["module"] == "preflight" and v["outcome"] == "PASS"
                        )
                        for v in outcomes
                    ),
                    "result": "PASS"
                    if len(outcomes) == len(modules)
                    and all(v["outcome"] == "PASS" for v in outcomes)
                    and sql_test_seconds <= 600
                    else "FAIL",
                },
            )
            shutil.copytree(group / "evidence", root / "evidence" / group.name, dirs_exist_ok=True)
        # A failed prerequisite cannot authorize destructive runtime fixtures.
        # Other test modules still report their independent outcomes within budget.
        if module == "preflight" and result["outcome"] != "PASS" or sql_test_seconds >= 600:
            break
    clean = not capture(["git", "status", "--porcelain", "--untracked-files=all"])
    write(root / "evidence/source-preservation.json", {"clean": clean})
    require(clean, "SOURCE_CHANGED")
    require(
        len(outcomes) == len(modules) and all(v["outcome"] == "PASS" for v in outcomes),
        "PRIMARY_FAILED",
    )


def main():
    os.umask(0o077)
    if sys.argv[1:] == ["collect-current-native"]:
        collect_current_native()
        return
    if sys.argv[1:] == ["native-owner"]:
        write(evidence_path() / "native-owner.json", native_identity())
        return
    if sys.argv[1:] == ["readiness"]:
        asyncio.run(readiness())
        return
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
