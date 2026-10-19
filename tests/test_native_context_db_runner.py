"""Runner refusal and real Settings regressions; never PostgreSQL runtime evidence."""

import asyncio
import copy
import importlib
import inspect
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from scripts import native_context_db_catalog as lane

REQUIRED_MODULES = (
    "tests/test_m3_1_native_context_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_m3_1_native_context_api_postgres.py",
    "tests/test_m3_1_native_context_runtime_postgres.py",
)


def complete_reports(nodes):
    return [
        dict(nodeid=node, when=phase, outcome="passed", xfail=False)
        for node in nodes
        for phase in ("setup", "call", "teardown")
    ]


def owned_fixture():
    labels = {"asm.c6.nonce": "a" * 32, "asm.c6.source": "b" * 40}
    lease = {
        "container_id": "c" * 64,
        "image_id": "sha256:" + "d" * 64,
        "volume": "asm-native-" + "a" * 32 + "-data",
        "labels": labels,
        "volume_mountpoint": "/var/lib/docker/volumes/owned/_data",
        "volume_created": "2026-10-18T01:00:00Z",
        "bootstrap": "/checkout/infra/postgres/bootstrap.sh",
        "pid": 23456,
        "started_at": "2026-10-18T01:00:01Z",
        "port": 34567,
    }
    container = {
        "Id": lease["container_id"],
        "Image": lease["image_id"],
        "RestartCount": 0,
        "Config": {"Image": lane.DB_IMAGE, "Labels": labels.copy()},
        "HostConfig": {
            "Privileged": False,
            "NetworkMode": "bridge",
            "RestartPolicy": {"Name": "no"},
            "PortBindings": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]},
        },
        "State": {"Running": True, "Pid": 23456, "StartedAt": lease["started_at"]},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "34567"}]}},
        "Mounts": [
            {
                "Type": "volume",
                "Name": lease["volume"],
                "Source": lease["volume_mountpoint"],
                "Destination": "/var/lib/postgresql",
                "RW": True,
            },
            {
                "Type": "bind",
                "Source": lease["bootstrap"],
                "Destination": "/docker-entrypoint-initdb.d/010-bootstrap.sh",
                "RW": False,
            },
        ],
    }
    volume = {
        "Name": lease["volume"],
        "Labels": labels.copy(),
        "Driver": "local",
        "Scope": "local",
        "Options": None,
        "Mountpoint": lease["volume_mountpoint"],
        "CreatedAt": lease["volume_created"],
    }
    return lease, container, volume


def role_fixture():
    return [
        dict(
            name="asm_" + name,
            login=True,
            superuser=False,
            bypassrls=False,
            inherit=name == "migrator",
            createrole=False,
            createdb=False,
            replication=False,
        )
        for name in ("runtime", "migrator")
    ]


def catalog_fixture():
    functions = {}
    for signature, body in (
        ("platform.example(p_id uuid)", " SELECT true "),
        (lane.PROFILE, " SELECT '{}'::jsonb "),
    ):
        result = "boolean" if "example" in signature else "jsonb"
        row = lane.parse_function(
            "CREATE FUNCTION "
            + signature
            + " RETURNS "
            + result
            + " LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$"
            + body
            + "$$"
        )
        row.update(runtime_execute=False, acl=[["asm_migrator", "asm_migrator", "EXECUTE", False]])
        functions[row["signature"]] = row
    rows, resolved = [], {}
    for oid, (sig, source) in enumerate(functions.items(), 100):
        row = copy.deepcopy(source)
        row.update(oid=oid, kind="f", leakproof=False, parallel="u")
        rows.append(row)
        resolved[sig] = oid
    columns = {"platform.alembic_version": ["version_num"]}
    snapshot = {
        "functions": [[s, v["definition"]] for s, v in functions.items()],
        "columns": [
            ["platform.alembic_version", "version_num", "character varying(32)", True, "", None]
        ],
        "constraints": [
            ["platform.alembic_version", "alembic_version_pkc", "PRIMARY KEY (version_num)", True]
        ],
    }
    nonfunction = {k: v for k, v in snapshot.items() if k != "functions"}
    return (
        {"functions": functions, "columns": columns},
        rows,
        resolved,
        json.dumps(snapshot),
        json.dumps(nonfunction),
    )


class SourceGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        (self.root / "source.py").write_text("SOURCE = 1\n")
        self.git("add", "source.py")
        self.git(
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@example.invalid",
            "commit",
            "-qm",
            "unit fixture",
        )
        self.sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE
        )

    def refused_before_reset(self, expected_sha):
        owner, destructive = Mock(), Mock()
        with self.assertRaises(lane.Refusal):
            lane.guarded_reset(
                lambda: lane.require_source(self.root, expected_sha), owner, destructive
            )
        owner.assert_not_called()
        destructive.assert_not_called()

    def test_event_head_mismatch_refuses_before_reset(self):
        self.refused_before_reset("0" * 40)

    def test_tracked_byte_drift_refuses_before_reset(self):
        (self.root / "source.py").write_text("SOURCE = 2\n")
        self.refused_before_reset(self.sha)

    def test_untracked_file_refuses_before_reset(self):
        (self.root / "unexpected").write_text("foreign")
        self.refused_before_reset(self.sha)

    def test_assume_unchanged_cannot_hide_source_mutation(self):
        self.git("update-index", "--assume-unchanged", "source.py")
        (self.root / "source.py").write_text("SOURCE = 2\n")
        self.refused_before_reset(self.sha)

    def test_valid_source_records_real_tree_and_exact_bytes(self):
        tree, manifest = lane.require_source(self.root, self.sha)
        self.assertEqual(tree, self.git("rev-parse", "HEAD^{tree}").strip())
        self.assertEqual(manifest[0]["sha256"], lane.sha256(b"SOURCE = 1\n"))

    def test_wrong_source_prevents_cleanup_calls(self):
        inspect, destructive = Mock(), Mock()
        lease, _, _ = owned_fixture()
        with self.assertRaises(lane.Refusal):
            lane.guarded_reset(
                lambda: lane.require_source(self.root, "0" * 40),
                lambda: None,
                lambda: lane.cleanup_owned(lease, inspect, inspect, destructive, destructive),
            )
        inspect.assert_not_called()
        destructive.assert_not_called()


class OwnershipGuards(unittest.TestCase):
    def test_valid_owned_cleanup_removes_only_recorded_ids(self):
        lease, container, volume = owned_fixture()
        removals = []
        lane.cleanup_owned(
            lease,
            lambda _: container,
            lambda _: volume,
            lambda identity: removals.append(("container", identity)),
            lambda identity: removals.append(("volume", identity)),
        )
        self.assertEqual(
            removals, [("container", lease["container_id"]), ("volume", lease["volume"])]
        )

    def assert_refuses_all_destructive_calls(self, lease, container, volume):
        reset, remove_container, remove_volume = Mock(), Mock(), Mock()
        with self.assertRaises(lane.Refusal):
            lane.guarded_reset(
                lambda: None,
                lambda: (
                    lane.validate_volume(lease, volume),
                    lane.validate_container(lease, container),
                ),
                reset,
            )
        reset.assert_not_called()
        with self.assertRaises(lane.Refusal):
            lane.cleanup_owned(
                lease, lambda _: container, lambda _: volume, remove_container, remove_volume
            )
        remove_container.assert_not_called()
        remove_volume.assert_not_called()

    def test_foreign_container_identity_refuses_reset_and_cleanup(self):
        changes = (
            ("Id", "f" * 64),
            ("Image", "sha256:" + "f" * 64),
            ("RestartCount", 1),
        )
        for key, value in changes:
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                container[key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_labels_or_source_image_refuse_reset_and_cleanup(self):
        for key, value in (("Labels", {"asm.c6.nonce": "foreign"}), ("Image", "postgres:18")):
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                container["Config"][key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_mounts_refuse_reset_and_cleanup(self):
        for index, key, value in (
            (0, "Source", "/shared/data"),
            (0, "Name", "foreign"),
            (0, "Destination", "/shared"),
            (0, "RW", False),
            (1, "Source", "/foreign/bootstrap.sh"),
            (1, "RW", True),
        ):
            with self.subTest(mount=index, field=key):
                lease, container, volume = owned_fixture()
                container["Mounts"][index][key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_host_or_port_refuses_reset_and_cleanup(self):
        for section in ("HostConfig", "NetworkSettings"):
            for key, value in (
                ("HostIp", "0.0.0.0"),
                ("HostIp", "192.0.2.1"),
                ("HostPort", "5432"),
            ):
                with self.subTest(section=section, field=key, value=value):
                    lease, container, volume = owned_fixture()
                    field = "PortBindings" if section == "HostConfig" else "Ports"
                    container[section][field]["5432/tcp"][0][key] = value
                    self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_pid_or_start_refuses_reset_and_cleanup(self):
        for key, value in (("Pid", 99999), ("StartedAt", "foreign-start")):
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                container["State"][key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_stopped_container_with_foreign_retained_port_refuses_cleanup(self):
        lease, container, volume = owned_fixture()
        container["State"].update(Running=False, Pid=0)
        container["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "5432"
        self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_foreign_volume_refuses_all_removals(self):
        for key, value in (
            ("Name", "foreign"),
            ("Labels", {}),
            ("Mountpoint", "/shared/data"),
            ("Driver", "nfs"),
            ("Scope", "global"),
            ("Options", {"device": "/shared"}),
            ("CreatedAt", "foreign"),
        ):
            with self.subTest(field=key):
                lease, container, volume = owned_fixture()
                volume[key] = value
                self.assert_refuses_all_destructive_calls(lease, container, volume)

    def test_missing_container_never_causes_removal_by_name(self):
        lease, _, volume = owned_fixture()
        remove_container, remove_volume = Mock(), Mock()
        lane.cleanup_owned(lease, lambda _: None, lambda _: volume, remove_container, remove_volume)
        remove_container.assert_not_called()
        remove_volume.assert_called_once_with(lease["volume"])

    def test_wrong_server_identity_refuses_before_database_reset(self):
        identity = [
            "postgres",
            "asm_admin",
            "asm_admin",
            5432,
            "180003",
            "1234567890",
            "2026-10-18 01:00:00+00",
        ]
        lease = {"server_identity": identity}
        lane.compare_server_identity(lease, identity, identity[5])
        for index, value in (
            (0, "shared"),
            (1, "postgres"),
            (2, "asm_migrator"),
            (3, 5433),
            (4, "170003"),
            (5, "9999999999"),
            (6, "foreign-start"),
        ):
            with self.subTest(field=index):
                mutant, destructive = list(identity), Mock()
                mutant[index] = value
                with self.assertRaises(lane.Refusal):
                    lane.guarded_reset(
                        lambda: None,
                        lambda: lane.compare_server_identity(lease, mutant, identity[5]),
                        destructive,
                    )
                destructive.assert_not_called()
        with self.assertRaises(lane.Refusal):
            lane.compare_server_identity(lease, identity, "9876543210", initial=True)


class CatalogGuards(unittest.TestCase):
    def test_all_actual_migrations_expand_and_profile_body_is_source_derived(self):
        expected = lane.source_catalog(lane.ROOT)
        self.assertEqual(len(expected["functions"]), 167)
        self.assertEqual(len(expected["columns"]), 45)
        self.assertEqual((len(expected["additions"]), len(expected["replacements"])), (35, 18))
        verifier = expected["functions"][lane.PROFILE]
        self.assertEqual(verifier["body_sha256"], lane.sha256(verifier["body"].encode()))
        self.assertIn("WITH expected(signature,body_hash", verifier["body"])
        for row in expected["functions"].values():
            self.assertIn(["asm_migrator", "asm_migrator", "EXECUTE", False], row["acl"])
            self.assertTrue(all(grant[3] is False for grant in row["acl"]))

    def test_typed_overloads_defaults_and_table_outputs_are_distinct(self):
        sql = "CREATE FUNCTION platform.example(p_id uuid, p_flag boolean DEFAULT false) RETURNS TABLE(item_id uuid, seen_at timestamptz) LANGUAGE sql STABLE STRICT SET search_path=pg_catalog,pg_temp AS $$ SELECT p_id,now() $$"
        row = lane.parse_function(sql)
        self.assertEqual(row["signature"], "platform.example(uuid,boolean)")
        self.assertEqual(row["argmodes"], ["i", "i", "t", "t"])
        self.assertEqual(row["all_types"], ["uuid", "boolean", "uuid", "timestamptz"])
        self.assertEqual(row["defaults"], "false")
        self.assertNotEqual(
            row["signature"],
            lane.parse_function(sql.replace("p_id uuid", "p_id text"))["signature"],
        )

    def test_unknown_sql_headers_and_unclosed_quotes_fail_closed(self):
        sql = "CREATE FUNCTION platform.example() RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,pg_temp AS $$ SELECT true $$"
        for mutant in (
            sql.replace("IMMUTABLE", "PARALLEL SAFE"),
            sql.replace("RETURNS boolean", "RETURNS SETOF boolean"),
            sql.replace("pg_catalog,pg_temp", "public"),
            sql.replace("AS $$", "AS '"),
        ):
            with self.subTest(mutant=mutant), self.assertRaises(lane.Refusal):
                lane.parse_function(mutant)
        for malformed in ("SELECT 'oops", "/* oops", "SELECT ($$oops", "SELECT )"):
            with self.subTest(sql=malformed), self.assertRaises(lane.Refusal):
                list(lane.split_sql(malformed))

    def test_unknown_nonfunction_statement_fails_before_catalog_comparison(self):
        command = {
            "revision": "0013",
            "index": 0,
            "sql": "CREATE VIEW platform.unreviewed AS SELECT 1",
        }
        with patch.object(lane, "capture_source", return_value=({}, [command])):
            with self.assertRaisesRegex(lane.Refusal, "Unsupported source SQL"):
                lane.source_catalog(lane.ROOT)

    def test_sql_lexer_preserves_executable_body_bytes_and_internal_comments(self):
        sql = "-- leading\nCREATE FUNCTION platform.example() RETURNS text LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$\n -- body ; ,\n SELECT 'a;''b'\n$$; SELECT 2;"
        statements = list(lane.split_sql(sql))
        row = lane.parse_function(lane.leading_comments(statements[0]))
        self.assertEqual(row["body"], "\n -- body ; ,\n SELECT 'a;''b'\n")
        self.assertEqual(statements[1], "SELECT 2")

    def test_missing_extra_duplicate_oid_and_typed_resolution_refuse(self):
        expected, rows, resolved, _, _ = catalog_fixture()
        for case in ("missing", "extra", "duplicate_oid", "wrong_signature_resolution"):
            with self.subTest(case=case):
                actual, ids = copy.deepcopy(rows), dict(resolved)
                if case == "missing":
                    actual.pop()
                elif case == "extra":
                    row = copy.deepcopy(actual[0])
                    row.update(signature="platform.foreign(uuid)", oid=999)
                    actual.append(row)
                elif case == "duplicate_oid":
                    actual[1]["oid"] = actual[0]["oid"]
                else:
                    ids[actual[0]["signature"]] = 999
                with self.assertRaises(lane.Refusal):
                    lane.compare_functions(expected["functions"], actual, ids)

    def test_body_own_verifier_acl_argument_and_return_drift_refuse(self):
        expected, rows, resolved, _, _ = catalog_fixture()
        changes = {
            "body": " SELECT '{\"valid\":true}'::jsonb ",
            "acl": [["asm_migrator", "PUBLIC", "EXECUTE", False]],
            "owner": "asm_runtime",
            "proconfig": ["search_path=public"],
            "argnames": ["foreign"],
            "input_types": ["text"],
            "return_type": "text",
            "security_definer": False,
            "volatility": "v",
            "runtime_execute": True,
            "strict": True,
        }
        for key, value in changes.items():
            with self.subTest(field=key):
                actual = copy.deepcopy(rows)
                actual[1][key] = value
                with self.assertRaises(lane.Refusal):
                    lane.compare_functions(expected["functions"], actual, resolved)

    def test_verifier_self_report_is_never_consulted_after_body_drift(self):
        expected, rows, resolved, full_text, nonfunction = catalog_fixture()
        rows[1]["body"] = " SELECT '{\"valid\":true}'::jsonb "
        self_report = Mock()
        with self.assertRaises(lane.Refusal):
            lane.compare_catalog(expected, rows, resolved, full_text, nonfunction, self_report)
        self_report.assert_not_called()

    def test_nonfunction_drift_and_column_order_refuse(self):
        expected, _, _, full_text, nonfunction = catalog_fixture()
        with patch.object(lane, "NONFUNCTION_SHA256", lane.sha256(nonfunction.encode())):
            self.assertEqual(
                lane.compare_snapshot(expected["columns"], full_text, nonfunction),
                lane.sha256(b"asm:m3:native_schema:v1\n" + full_text.encode()),
            )
            for case in ("constraint_validation", "column_type", "extra_column"):
                with self.subTest(case=case):
                    full = json.loads(full_text)
                    if case == "constraint_validation":
                        full["constraints"][0][3] = False
                    elif case == "column_type":
                        full["columns"][0][2] = "text"
                    else:
                        full["columns"].append(
                            ["platform.alembic_version", "foreign", "text", False, "", None]
                        )
                    non = {k: v for k, v in full.items() if k != "functions"}
                    with self.assertRaises(lane.Refusal):
                        lane.compare_snapshot(
                            expected["columns"], json.dumps(full), json.dumps(non)
                        )

    def test_independent_full_hash_is_compared_after_body_and_nonfunction_checks(self):
        expected, rows, resolved, full_text, nonfunction = catalog_fixture()
        full_hash = lane.sha256(b"asm:m3:native_schema:v1\n" + full_text.encode())
        declared = {"schema_revision": "0013", "valid": True, "profile_sha256": full_hash}
        with patch.object(lane, "NONFUNCTION_SHA256", lane.sha256(nonfunction.encode())):
            self.assertEqual(
                lane.compare_catalog(
                    expected, rows, resolved, full_text, nonfunction, lambda: declared
                ),
                (full_hash, declared),
            )
            for wrong in (dict(declared, valid=False), dict(declared, profile_sha256="0" * 64)):
                with self.assertRaises(lane.Refusal):
                    lane.compare_catalog(
                        expected, rows, resolved, full_text, nonfunction, lambda value=wrong: value
                    )

    def test_runtime_membership_ownership_and_role_flags_refuse(self):
        roles = role_fixture()
        lane.compare_roles(roles, [], 0)
        for key in ("inherit", "superuser", "bypassrls", "createrole", "createdb", "replication"):
            with self.subTest(field=key):
                mutated = copy.deepcopy(roles)
                mutated[0][key] = True
                with self.assertRaises(lane.Refusal):
                    lane.compare_roles(mutated, [], 0)
        for memberships, owned in (
            ([{"role": "asm_migrator", "member": "asm_runtime"}], 0),
            ([], 1),
        ):
            with self.assertRaises(lane.Refusal):
                lane.compare_roles(roles, memberships, owned)


class ChildSettingsConfiguration(unittest.TestCase):
    def assert_test_settings(self, parent):
        from asm import foundation
        from pydantic import ValidationError

        with patch.dict(os.environ, parent, clear=True):
            child = lane.child_environment(Path("/synthetic/native/private"))
            self.assertEqual(dict(os.environ), parent)
        self.assertTrue(all(key not in child for key in (*lane.SECRET_ENV, "GITHUB_TOKEN")))
        synthetic_url = "postgresql+psycopg://asm_runtime:synthetic-only@settings-regression.invalid:65432/asm_test"
        # The fixture adds only a synthetic URL, never an engine or an owned DB.
        child["ASM_DATABASE_URL"] = synthetic_url
        with (
            patch.dict(os.environ, child, clear=True),
            patch.object(
                foundation,
                "create_async_engine",
                side_effect=AssertionError("No engine in Settings regression"),
            ) as engine,
            patch(
                "socket.getaddrinfo", side_effect=AssertionError("No DNS in Settings regression")
            ),
            patch(
                "socket.socket.connect",
                side_effect=AssertionError("No network in Settings regression"),
            ),
        ):
            settings = foundation.Settings()
            self.assertEqual(settings.environment, "TEST")
            self.assertEqual(settings.database_url.get_secret_value(), synthetic_url)
            # The unchanged foundation must still reject a missing environment.
            del os.environ["ASM_ENVIRONMENT"]
            with self.assertRaises(ValidationError) as missing:
                foundation.Settings()
            self.assertEqual(
                [
                    (row["loc"], row["type"])
                    for row in missing.exception.errors(include_input=False)
                ],
                [(("environment",), "missing")],
            )
        engine.assert_not_called()

    def test_real_settings_validates_test_without_parent_environment(self):
        self.assert_test_settings({})

    def test_real_settings_remains_test_with_non_test_parent_environment(self):
        for environment in ("LOCAL", "PRODUCTION"):
            with self.subTest(parent_environment=environment):
                self.assert_test_settings(
                    {
                        "ASM_ENVIRONMENT": environment,
                        "ASM_DATABASE_URL": "foreign-invalid-url",
                        "ASM_MIGRATION_DATABASE_URL": "foreign-migrator",
                        "ASM_NATIVE_TEST_ADMIN_URL": "foreign-admin",
                        "ASM_NATIVE_TEST_ALLOW_RESET": "1",
                        "ASM_AUTH_ORIGINS": "hostile-invalid-json",
                        "GITHUB_TOKEN": "synthetic-parent-token",
                    }
                )


class ExecutionEvidence(unittest.TestCase):
    def test_payload_failure_and_cleanup_failure_cannot_be_masked(self):
        # Complete orchestration with mocked commands/resources. No Docker or DB
        # is contacted, and these toy receipts are deleted with the fixture.
        for carrier_exit, cleanup_failure in ((7, False), (0, True)):
            with self.subTest(carrier_exit=carrier_exit, cleanup_failure=cleanup_failure):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    private, evidence = root / "private", root / "evidence"
                    private.mkdir()
                    evidence.mkdir()
                    (root / "job-start").write_text(str(int(time.time())))
                    commands = Mock(passwords=())

                    def command(argv, **kwargs):
                        if argv == ["uv", "--version"]:
                            return 0, b"uv 0.10.0\n"
                        if argv[:2] == ["git", "--version"]:
                            return 0, b"git version unit-fixture\n"
                        if argv[:2] == ["docker", "version"]:
                            return 0, b'"unit-fixture"'
                        if "pytest" in argv:
                            (private / "runner-unit.xml").write_text(
                                '<testsuites><testsuite><testcase name="guard"/></testsuite></testsuites>'
                            )
                        if argv[-1] == "carrier":
                            return carrier_exit, b"mock carrier"
                        return 0, b"mock unit/static/catalog"

                    commands.run.side_effect = command
                    env = {
                        "GITHUB_SHA": "b" * 40,
                        "GITHUB_EVENT_NAME": "push",
                        "GITHUB_REF": lane.EXECUTION_REF,
                        "GITHUB_REPOSITORY": "Elefesys/ai-service-manager",
                        "GITHUB_RUN_ID": "123",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "UV_PROJECT_ENVIRONMENT": str(Path(lane.sys.prefix).resolve()),
                        "UV_CACHE_DIR": str(root / "uv-cache"),
                        "RUFF_CACHE_DIR": str(root / "ruff-cache"),
                    }
                    cleanup_error = (
                        lane.Refusal("mock foreign cleanup identity") if cleanup_failure else None
                    )
                    with (
                        patch.dict(os.environ, env),
                        patch.object(lane.sys, "version_info", (3, 13, 0)),
                        patch.object(lane, "Commands", return_value=commands),
                        patch.object(lane, "require_source", return_value=("e" * 40, [])),
                        patch.object(lane, "git_bytes", return_value=b"mock source archive"),
                        patch.object(
                            lane,
                            "admit_event",
                            return_value=({"head": "b" * 40, "tree": "e" * 40}, []),
                        ),
                        patch.object(lane, "prove_partition", return_value=({}, [])),
                        patch.object(
                            lane, "source_catalog", return_value={"functions": {}, "columns": {}}
                        ),
                        patch.object(lane.importlib.metadata, "distributions", return_value=[]),
                        patch.object(lane, "create_database", return_value={}),
                        patch.object(lane, "cleanup", side_effect=cleanup_error) as cleanup,
                    ):
                        result = lane.run_lane(private, evidence)
                    self.assertNotEqual(result, 0)
                    receipt = json.loads((evidence / "receipt.json").read_text())
                    self.assertEqual(receipt["result"], "FAIL")
                    self.assertEqual(receipt["carrier_exit"], carrier_exit)
                    self.assertEqual(receipt["catalog_exit"], 0)
                    cleanup.assert_called_once()

    def test_sqlstate_survives_wrapped_exceptions_without_exposing_parameters(self):
        original = RuntimeError("private SQL parameters")
        original.sqlstate = "23514"
        wrapped = RuntimeError("wrapper")
        wrapped.orig = original
        wrapped.__cause__ = original
        original.__context__ = wrapped
        self.assertEqual(lane.exception_sqlstates(wrapped), ["23514"])
        self.assertEqual(lane.exception_sqlstates(None), [])

    def test_future_regressions_are_collected_without_a_fixed_total(self):
        nodes = [module + "::test_new_regression" for module in REQUIRED_MODULES]
        reports = complete_reports(nodes)
        lane.validate_collection(nodes, [], reports, 0)
        nodes.append(lane.MODULES[1] + "::test_another_regression")
        reports.extend(complete_reports(nodes[-1:]))
        lane.validate_collection(nodes, [], reports, 0)

    def test_skip_xfail_no_tests_deselection_and_incomplete_execution_cannot_pass(self):
        nodes = [module + "::test_case" for module in REQUIRED_MODULES]
        good = complete_reports(nodes)
        cases = [([], [], [], 5), (nodes, ["deselected"], good, 0), (nodes, [], good[:-1], 0)]
        for key, value in (("outcome", "skipped"), ("xfail", True)):
            reports = copy.deepcopy(good)
            reports[-1][key] = value
            cases.append((nodes, [], reports, 0))
        for case in cases:
            with self.subTest(case=case), self.assertRaises(lane.Refusal):
                lane.validate_collection(*case)
        # Failure status is retained, not retried or transformed into success.
        lane.validate_collection(nodes, [], good[:-1], 1)

    def test_urls_passwords_and_junit_traces_are_redacted(self):
        secret = "sensitive" + "0123456789" * 4
        raw = (
            "<failure>postgresql+psycopg://asm_runtime:"
            + secret
            + "@127.0.0.1:34567/asm_test password="
            + secret
            + "</failure>"
        )
        clean = lane.redact(raw, (secret,))
        self.assertNotIn(secret, clean)
        self.assertNotIn("postgresql", clean)
        self.assertIn("[DB_URL]", clean)

    def test_empty_or_skipped_unit_junit_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unit.xml"
            for xml in (
                "<testsuites/>",
                '<testsuites><testsuite><testcase name="guard"><skipped/></testcase></testsuite></testsuites>',
            ):
                path.write_text(xml)
                with self.assertRaises(lane.Refusal):
                    lane.require_unit_junit(path)
            path.write_text(
                '<testsuites><testsuite><testcase name="guard"/></testsuite></testsuites>'
            )
            lane.require_unit_junit(path)

    def test_reset_optin_and_urls_are_absent_from_child_environment_until_guarded(self):
        with patch.dict(
            os.environ,
            {
                "ASM_DATABASE_URL": "foreign",
                "ASM_NATIVE_TEST_ALLOW_RESET": "1",
                "GITHUB_TOKEN": "private",
                "PYTEST_ADDOPTS": "-k subset",
            },
        ):
            env = lane.child_environment(Path("/outside/private"))
        self.assertTrue(
            all(key not in env for key in (*lane.SECRET_ENV, "GITHUB_TOKEN", "PYTEST_ADDOPTS"))
        )

    def test_changed_reset_url_or_optin_refuses_before_destructive_call(self):
        lease = {
            "port": 34567,
            "passwords": {key: key + "123" for key in ("admin", "runtime", "migrator")},
        }
        for key in lane.SECRET_ENV:
            with self.subTest(key=key), patch.dict(os.environ, lane.urls(lease)):
                lane.require_child_urls(lease)
                os.environ[key] = "foreign"
                destructive = Mock()
                with self.assertRaises(lane.Refusal):
                    lane.guarded_reset(
                        lambda: None, lambda: lane.require_child_urls(lease), destructive
                    )
                destructive.assert_not_called()

    def test_artifacts_and_cache_must_be_outside_checkout(self):
        with self.assertRaises(lane.Refusal):
            lane.external_directory(lane.ROOT / "artifacts")

    def test_workflow_has_one_exact_push_branch_one_job_and_whole_job_cap(self):
        text = (lane.ROOT / ".github/workflows/native-context-db.yml").read_text()
        self.assertIn("branches: [c0/m3-1-native-context-db-stock-r1]", text)
        self.assertIn("timeout-minutes: 20", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertEqual(text.count("runs-on:"), 1)
        self.assertNotIn("secrets.", text)
        for forbidden in ("workflow_dispatch:", "pull_request:", "schedule:"):
            self.assertNotIn(forbidden, text)
        for line in text.splitlines():
            if "uses:" in line:
                self.assertRegex(line, r"uses: (?:actions|astral-sh)/[a-z-]+@[0-9a-f]{40}")

    def test_job_env_does_not_use_runner_context_before_a_runner_exists(self):
        text = (lane.ROOT / ".github/workflows/native-context-db.yml").read_text()
        job_env = text.split("    env:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertNotIn("${{", job_env)
        self.assertIn('TASK_ROOT="$RUNNER_TEMP/native-context-db"', text)
        self.assertIn('>> "$GITHUB_ENV"', text)


class FourModuleCollection(unittest.TestCase):
    def setUp(self):
        self.nodes = [module + "::test_case" for module in REQUIRED_MODULES]
        self.reports = complete_reports(self.nodes)

    def test_omitting_api_or_runtime_fails_even_with_all_remaining_reports_passed(self):
        for omitted in REQUIRED_MODULES[2:]:
            with self.subTest(omitted=omitted), self.assertRaises(lane.Refusal):
                nodes = [node for node in self.nodes if not node.startswith(omitted + "::")]
                lane.validate_collection(nodes, [], complete_reports(nodes), 0)

    def test_missing_setup_call_or_teardown_report_cannot_pass(self):
        for index, row in enumerate(self.reports):
            with self.subTest(node=row["nodeid"], phase=row["when"]):
                with self.assertRaises(lane.Refusal):
                    lane.validate_collection(
                        self.nodes, [], self.reports[:index] + self.reports[index + 1 :], 0
                    )

    def test_failed_setup_call_or_teardown_cannot_pass(self):
        for phase in ("setup", "call", "teardown"):
            with self.subTest(phase=phase):
                reports = copy.deepcopy(self.reports)
                next(row for row in reports if row["when"] == phase)["outcome"] = "failed"
                with self.assertRaises(lane.Refusal):
                    lane.validate_collection(self.nodes, [], reports, 0)
                # A real nonzero pytest result remains a whole-run failure.
                lane.validate_collection(self.nodes, [], reports, 1)

    def test_duplicate_nodes_reports_foreign_nodes_and_unknown_phases_refuse(self):
        for case in ("duplicate_node", "duplicate_report", "foreign_node", "phase", "outcome"):
            with self.subTest(case=case), self.assertRaises(lane.Refusal):
                nodes, reports = list(self.nodes), copy.deepcopy(self.reports)
                if case == "duplicate_node":
                    nodes.append(nodes[-1])
                elif case == "duplicate_report":
                    reports.append(dict(reports[-1]))
                elif case == "foreign_node":
                    reports.append(dict(reports[-1], nodeid=nodes[-1] + "_uncollected"))
                elif case == "phase":
                    reports.append(dict(reports[-1], when="unknown"))
                else:
                    reports[-1]["outcome"] = "unknown"
                lane.validate_collection(nodes, [], reports, 0)

    def test_skip_or_xfail_in_any_phase_cannot_pass(self):
        for phase in ("setup", "call", "teardown"):
            for key, value in (("outcome", "skipped"), ("xfail", True)):
                with self.subTest(phase=phase, field=key), self.assertRaises(lane.Refusal):
                    reports = copy.deepcopy(self.reports)
                    next(row for row in reports if row["when"] == phase)[key] = value
                    lane.validate_collection(self.nodes, [], reports, 0)


class CarrierFixtureGuards(unittest.TestCase):
    """Real imported fixture bodies, mocked pytest/resources; no service or SQL."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.private, self.evidence = self.root / "private", self.root / "evidence"
        self.private.mkdir()
        self.evidence.mkdir()
        self.modules = {path: importlib.import_module(Path(path).stem) for path in REQUIRED_MODULES}
        self.db = self.modules[REQUIRED_MODULES[1]]
        self.original_reset = self.db.reset_disposable
        self.nodes = [path + "::test_case" for path in REQUIRED_MODULES]
        self.lease = {
            "source_sha": "b" * 40,
            "port": 34567,
            "passwords": {key: "synthetic-" + key for key in ("admin", "runtime", "migrator")},
        }
        self.commands = Mock(passwords=())

    def items(self):
        items = []
        for node in self.nodes:
            path = node.split("::", 1)[0]
            module = self.modules[path]
            definitions = (
                {"native": (SimpleNamespace(func=inspect.unwrap(module.native)),)}
                if path in REQUIRED_MODULES[1:]
                else {}
            )
            items.append(
                SimpleNamespace(
                    nodeid=node,
                    module=module,
                    _fixtureinfo=SimpleNamespace(name2fixturedefs=definitions),
                )
            )
        return items

    def run_carrier(self, *, action=None, exit_code=0, items=None, reports=None):
        def pytest_main(argv, *, plugins):
            self.argv = argv
            audit = plugins[0]
            audit.pytest_collection_finish(
                SimpleNamespace(items=self.items() if items is None else items)
            )
            if action:
                action(audit)
            for row in complete_reports(self.nodes) if reports is None else reports:
                report = SimpleNamespace(
                    **{key: value for key, value in row.items() if key != "xfail"},
                    duration=0.001,
                    failed=row["outcome"] == "failed",
                    longrepr="synthetic runner failure",
                )
                if row["xfail"]:
                    report.wasxfail = "synthetic xfail"
                audit.pytest_runtest_logreport(report)
            return exit_code

        try:
            with patch("pytest.main", side_effect=pytest_main):
                return lane.carrier(self.private, self.evidence, self.lease, self.commands)
        finally:
            self.assertIs(self.db.reset_disposable, self.original_reset)

    def enter_native(self, path):
        # The actual async fixture executes to_thread(reset_disposable). Its
        # first psycopg.connect is blocked below, before any SQL or migration.
        generator = inspect.unwrap(self.modules[path].native)(SimpleNamespace(), self.root)
        return asyncio.run(generator.__anext__())

    def test_four_complete_paths_and_future_api_runtime_cases_are_used(self):
        for path in REQUIRED_MODULES[2:]:
            self.nodes.append(path + "::test_future_c3_case[appended]")
        self.assertEqual(self.run_carrier(), 0)
        self.assertEqual(tuple(self.argv[:4]), REQUIRED_MODULES)
        self.assertFalse(any(arg in self.argv for arg in ("-k", "-m", "--deselect")))
        collection = json.loads((self.evidence / "collection.json").read_text())
        self.assertEqual(collection["nodeids"], self.nodes)
        self.assertEqual(
            collection["per_module"],
            {
                path: [node for node in self.nodes if node.startswith(path + "::")]
                for path in REQUIRED_MODULES
            },
        )
        self.assertEqual(collection["count"], 6)
        self.assertFalse(collection["fixed_total_required"])
        guards = json.loads((self.evidence / "fixture-guards.json").read_text())
        self.assertEqual(guards["reset_entry_point"], REQUIRED_MODULES[1] + "::reset_disposable")
        self.assertEqual(
            guards["per_module"], {p: collection["per_module"][p] for p in REQUIRED_MODULES[1:]}
        )
        results = json.loads((self.evidence / "test-results.json").read_text())
        self.assertEqual(len(results["reports"]), 18)

    def test_collection_hook_rejects_missing_api_or_runtime_before_any_fixture(self):
        for omitted in REQUIRED_MODULES[2:]:
            with self.subTest(omitted=omitted):
                self.nodes = [path + "::test_case" for path in REQUIRED_MODULES if path != omitted]
                with (
                    patch(
                        "psycopg.connect", side_effect=AssertionError("No connection")
                    ) as connect,
                    self.assertRaises(lane.Refusal),
                ):
                    self.run_carrier()
                connect.assert_not_called()
                collection = json.loads((self.evidence / "collection.json").read_text())
                self.assertEqual(collection["per_module"][omitted], [])
                self.assertEqual(collection["count"], 3)

    def test_all_pg_consumers_call_same_guard_before_real_reset_entry_point(self):
        events = []

        def source(*args):
            events.append("source")

        def owner(*args):
            events.append("owner")
            lease, container, volume = owned_fixture()
            lane.validate_container(lease, container)
            lane.validate_volume(lease, volume)
            return {"unit_mock": True}

        def blocked_connect(*args, **kwargs):
            events.append("reset_entry")
            raise RuntimeError("blocked first connection; no SQL")

        def exercise(audit):
            for path in REQUIRED_MODULES[1:]:
                with self.subTest(module=path):
                    self.assertIs(self.modules[path].native, self.db.native)
                    self.assertIs(self.db.reset_disposable.__wrapped__, self.original_reset)
                    with self.assertRaisesRegex(RuntimeError, "blocked first connection"):
                        self.enter_native(path)

        with (
            patch.dict(os.environ, lane.urls(self.lease)),
            patch.object(lane, "require_source", side_effect=source),
            patch.object(lane, "verify_server", side_effect=owner),
            patch("psycopg.connect", side_effect=blocked_connect) as connect,
            patch("asyncio.create_subprocess_exec", side_effect=AssertionError("No migration")),
        ):
            self.assertEqual(self.run_carrier(action=exercise), 0)
        self.assertEqual(events, ["source", "owner", "reset_entry"] * 3)
        self.assertEqual(connect.call_count, 3)
        proofs = json.loads((self.evidence / "before-reset-proofs.json").read_text())
        self.assertEqual([row["reset"] for row in proofs], [1, 2, 3])

    def test_each_pg_consumer_refuses_source_url_and_owner_drift_before_reset(self):
        for path in REQUIRED_MODULES[1:]:
            for guard in ("source", "url", "owner"):
                with self.subTest(module=path, guard=guard):
                    env = lane.urls(self.lease)
                    if guard == "url":
                        env["ASM_NATIVE_TEST_ALLOW_RESET"] = "foreign"
                    with (
                        patch.dict(os.environ, env),
                        patch.object(
                            lane,
                            "require_source",
                            side_effect=lane.Refusal("source drift") if guard == "source" else None,
                        ) as source,
                        patch.object(
                            lane,
                            "verify_server",
                            side_effect=lane.Refusal("owner drift") if guard == "owner" else None,
                        ) as owner,
                        patch(
                            "psycopg.connect", side_effect=AssertionError("No connection")
                        ) as connect,
                        patch(
                            "asyncio.create_subprocess_exec",
                            side_effect=AssertionError("No migration"),
                        ),
                    ):

                        def exercise(audit):
                            self.enter_native(path)

                        with self.assertRaises(lane.Refusal):
                            self.run_carrier(action=exercise)
                    source.assert_called_once_with(lane.ROOT, self.lease["source_sha"])
                    if guard in ("source", "url"):
                        owner.assert_not_called()
                    else:
                        owner.assert_called_once_with(self.lease, self.commands)
                    connect.assert_not_called()

    def test_import_alias_or_resolved_fixture_drift_refuses_before_reset(self):
        for path in REQUIRED_MODULES[2:]:
            with self.subTest(module=path, drift="imported alias"):
                items = self.items()
                with patch.object(self.modules[path], "native", object()):
                    with self.assertRaises(lane.Refusal):
                        self.run_carrier(items=items)
        for path in REQUIRED_MODULES[1:]:
            for drift in ("override", "absent"):
                with self.subTest(module=path, drift=drift):
                    items = self.items()
                    item = next(item for item in items if item.nodeid.startswith(path + "::"))
                    definitions = item._fixtureinfo.name2fixturedefs
                    if drift == "absent":
                        definitions.clear()
                    else:
                        definitions["native"] = (SimpleNamespace(func=lambda: None),)
                    with self.assertRaises(lane.Refusal):
                        self.run_carrier(items=items)

    def test_reset_restored_and_failure_evidence_retained_on_exception_or_nonzero(self):
        for failure in ("exception", "nonzero"):
            with self.subTest(failure=failure):

                def action(audit):
                    self.assertIsNot(self.db.reset_disposable, self.original_reset)
                    if failure == "exception":
                        raise RuntimeError("synthetic pytest exception")

                reports = complete_reports(self.nodes)
                reports[-1]["outcome"] = "failed"
                if failure == "exception":
                    with self.assertRaisesRegex(RuntimeError, "synthetic pytest exception"):
                        self.run_carrier(action=action)
                else:
                    self.assertEqual(
                        self.run_carrier(action=action, exit_code=7, reports=reports), 7
                    )
                result = json.loads((self.evidence / "test-results.json").read_text())
                self.assertEqual(result["pytest_exit"], 1 if failure == "exception" else 7)
                collection = json.loads((self.evidence / "collection.json").read_text())
                self.assertEqual(collection["nodeids"], self.nodes)


def ci_event(tmp_path, route):
    repository = {"full_name": lane.REPOSITORY, "id": lane.REPOSITORY_ID, "fork": False}
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": lane.REPOSITORY,
        "GITHUB_REPOSITORY_ID": str(lane.REPOSITORY_ID),
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": lane.EXECUTION_REF if route == "stock-push" else "refs/heads/main",
        "GITHUB_SHA": "b" * 40,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_EVENT_PATH": str(tmp_path / "event.json"),
        "UV_PROJECT_ENVIRONMENT": str(Path(lane.sys.prefix).resolve()),
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
        "RUFF_CACHE_DIR": str(tmp_path / "ruff-cache"),
    }
    payload = {
        "repository": repository,
        "ref": env["GITHUB_REF"],
        "after": env["GITHUB_SHA"],
        "head_commit": {"id": env["GITHUB_SHA"]},
        "deleted": False,
        "base_ref": None,
    }
    if route == "same-repository-pr-merge":
        env.update(
            GITHUB_EVENT_NAME="pull_request",
            GITHUB_REF="refs/pull/42/merge",
            GITHUB_BASE_REF="main",
            GITHUB_HEAD_REF="candidate",
        )
        payload = {
            "repository": repository,
            "action": "synchronize",
            "number": 42,
            "pull_request": {
                "number": 42,
                "state": "open",
                "merged": False,
                "merge_commit_sha": env["GITHUB_SHA"],
                "base": {"ref": "main", "sha": "c" * 40, "repo": copy.deepcopy(repository)},
                "head": {"ref": "candidate", "sha": "d" * 40, "repo": copy.deepcopy(repository)},
            },
        }
    return env, payload


def exercise_ci_lane(
    tmp_path,
    env,
    payload,
    *,
    parents=None,
    raw=None,
    carrier_exit=0,
    catalog_exit=0,
    cleanup_failure=False,
    partition_failure=False,
    retained_state=False,
):
    """Real JSON/admission/source-input checks; every command/resource is mocked."""
    private, evidence = tmp_path / "private", tmp_path / "evidence"
    private.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    if retained_state:
        (private / "state.json").write_text("Unadopted private state")
    (tmp_path / "job-start").write_text(str(int(time.time())))
    Path(env["GITHUB_EVENT_PATH"]).write_text(json.dumps(payload) if raw is None else raw)
    commands = Mock(passwords=())

    def command(argv, **kwargs):
        if argv == ["uv", "--version"]:
            return 0, b"uv 0.10.0\n"
        if argv[:2] == ["docker", "version"]:
            return 0, b'"unit-only"'
        if "pytest" in argv:
            (private / "runner-unit.xml").write_text(
                '<testsuites><testsuite><testcase name="guard"/></testsuite></testsuites>'
            )
        if argv[-1] == "carrier":
            return carrier_exit, b"unit-only carrier"
        if argv[-1] == "catalog":
            return catalog_exit, b"unit-only catalog"
        return 0, b"unit-only command"

    commands.run.side_effect = command
    parent_lines = ["c" * 40, "d" * 40] if parents is None else parents
    headers = (
        "tree "
        + "e" * 40
        + "\n"
        + "".join("parent " + p + "\n" for p in parent_lines)
        + "\nunit-only commit"
    ).encode()
    with (
        patch.dict(os.environ, env, clear=True),
        patch.object(lane, "require_source", return_value=("e" * 40, [])),
        patch.object(
            lane,
            "git_bytes",
            side_effect=lambda root, *args: (
                headers if args == ("cat-file", "-p", "HEAD") else b"unit-only archive"
            ),
        ) as git,
        patch.object(lane, "Commands", return_value=commands),
        patch.object(lane, "source_catalog", return_value={"functions": {}, "columns": {}}),
        patch.object(lane.importlib.metadata, "distributions", return_value=[]),
        patch.object(
            lane,
            "prove_partition",
            side_effect=lane.Refusal("partition failure") if partition_failure else None,
        ) as partition,
        patch.object(lane, "create_database") as create,
        patch.object(lane, "collect_owned_logs") as logs,
        patch.object(
            lane,
            "cleanup",
            side_effect=lane.Refusal("cleanup failure") if cleanup_failure else None,
        ) as cleanup,
    ):
        result = lane.run_lane(private, evidence)
    return SimpleNamespace(
        result=result,
        receipt=json.loads((evidence / "receipt.json").read_text()),
        evidence=evidence,
        commands=commands,
        create=create,
        logs=logs,
        cleanup=cleanup,
        partition=partition,
        git=git,
    )


@pytest.mark.parametrize("route", ("stock-push", "main-push", "same-repository-pr-merge"))
def test_ci_actual_event_identity_and_archive_are_never_relabelled(tmp_path, route):
    env, payload = ci_event(tmp_path, route)
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result == 0
    identity = json.loads((probe.evidence / "source-identity.json").read_text())
    assert identity["route"] == route
    assert identity["event"] == env["GITHUB_EVENT_NAME"]
    assert identity["ref"] == env["GITHUB_REF"]
    assert (identity["head"], identity["tree"], identity["run_id"], identity["attempt"]) == (
        env["GITHUB_SHA"],
        "e" * 40,
        "123",
        "2",
    )
    assert identity["source_archive_sha256"] == lane.sha256(
        (probe.evidence / "source.tar").read_bytes()
    )
    assert identity["event_payload_sha256"] == lane.sha256(
        Path(env["GITHUB_EVENT_PATH"]).read_bytes()
    )
    assert identity["event_identity_is_c0_approval"] is False
    assert probe.receipt["source_identity"]["event"] == identity["event"]
    probe.git.assert_any_call(lane.ROOT, "cat-file", "-p", "HEAD")
    probe.create.assert_called_once()
    probe.cleanup.assert_called_once()
    if route == "same-repository-pr-merge":
        assert identity["merge_parents"] == [
            payload["pull_request"][key]["sha"] for key in ("base", "head")
        ]


@pytest.mark.parametrize(
    "key,value",
    (
        ("GITHUB_ACTIONS", "false"),
        ("GITHUB_REPOSITORY", "foreign/repo"),
        ("GITHUB_REPOSITORY_ID", "1"),
        ("GITHUB_EVENT_NAME", "workflow_call"),
        ("GITHUB_EVENT_NAME", "workflow_dispatch"),
        ("GITHUB_EVENT_NAME", "pull_request_target"),
        ("GITHUB_REF", "refs/heads/other"),
        ("GITHUB_REF", "refs/tags/main"),
        ("GITHUB_RUN_ID", "0"),
        ("GITHUB_RUN_ATTEMPT", "01"),
        ("GITHUB_RUN_ATTEMPT", "١"),
        ("GITHUB_SHA", "a" * 40),
        ("GITHUB_BASE_REF", "main"),
        ("GITHUB_HEAD_REF", "candidate"),
    ),
)
def test_ci_bad_event_context_refuses_all_commands_and_resource_recovery(tmp_path, key, value):
    env, payload = ci_event(tmp_path, "stock-push")
    env[key] = value
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    assert probe.receipt["owned_cleanup"] == "NOT_ATTEMPTED_EVENT_REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup, probe.partition):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "change",
    (
        "repository",
        "repository-id",
        "fork",
        "push-ref",
        "push-after",
        "push-head",
        "deleted",
        "pr-base",
        "pr-env-base",
        "pr-head",
        "pr-head-repository",
        "pr-base-repository",
        "pr-ref",
        "pr-number",
        "pr-state",
        "pr-action",
        "pr-merge",
        "pr-head-sha",
        "pr-base-sha",
    ),
)
def test_ci_payload_target_and_merge_mismatch_refuses_before_docker(tmp_path, change):
    env, payload = ci_event(
        tmp_path, "same-repository-pr-merge" if change.startswith("pr-") else "main-push"
    )
    pr = payload.get("pull_request", {})
    if change == "repository":
        payload["repository"]["full_name"] = "foreign/repo"
    elif change == "repository-id":
        payload["repository"]["id"] = True
    elif change == "fork":
        payload["repository"]["fork"] = True
    elif change == "push-ref":
        payload["ref"] = lane.EXECUTION_REF
    elif change == "push-after":
        payload["after"] = "a" * 40
    elif change == "push-head":
        payload["head_commit"]["id"] = "a" * 40
    elif change == "deleted":
        payload["deleted"] = True
    elif change == "pr-base":
        pr["base"]["ref"] = "other"
    elif change == "pr-env-base":
        env["GITHUB_BASE_REF"] = "other"
    elif change == "pr-head":
        env["GITHUB_HEAD_REF"] = "other"
    elif change == "pr-head-repository":
        pr["head"]["repo"]["full_name"] = "fork/repo"
    elif change == "pr-base-repository":
        pr["base"]["repo"]["id"] = 1
    elif change == "pr-ref":
        env["GITHUB_REF"] = "refs/pull/42/head"
    elif change == "pr-number":
        payload["number"] = "42"
    elif change == "pr-state":
        pr["state"] = "closed"
    elif change == "pr-action":
        payload["action"] = "closed"
    elif change == "pr-merge":
        pr["merge_commit_sha"] = "a" * 40
    elif change == "pr-head-sha":
        pr["head"]["sha"] = "a" * 40
    elif change == "pr-base-sha":
        pr["base"]["sha"] = "a" * 40
    probe = exercise_ci_lane(tmp_path, env, payload)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "parents",
    ([], ["d" * 40], ["d" * 40, "c" * 40], ["c" * 40, "a" * 40], ["c" * 40, "d" * 40, "a" * 40]),
)
def test_ci_real_commit_headers_must_bind_both_ordered_merge_parents(tmp_path, parents):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    probe = exercise_ci_lane(tmp_path, env, payload, parents=parents)
    assert probe.result != 0
    probe.commands.run.assert_not_called()
    probe.cleanup.assert_not_called()


@pytest.mark.parametrize("raw", ("{}", "[]", "{", '{"repository":{},"repository":{}}', "null"))
def test_ci_malformed_actual_event_payload_refuses_without_resources(tmp_path, raw):
    env, payload = ci_event(tmp_path, "main-push")
    probe = exercise_ci_lane(tmp_path, env, payload, raw=raw)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize("carrier,catalog,cleanup", ((7, 0, False), (0, 9, False), (0, 0, True)))
def test_ci_admitted_routes_keep_payload_and_cleanup_failures(tmp_path, carrier, catalog, cleanup):
    env, payload = ci_event(tmp_path, "same-repository-pr-merge")
    probe = exercise_ci_lane(
        tmp_path, env, payload, carrier_exit=carrier, catalog_exit=catalog, cleanup_failure=cleanup
    )
    assert probe.result != 0 and probe.receipt["result"] == "FAIL"
    assert probe.receipt["carrier_exit"] == carrier and probe.receipt["catalog_exit"] == catalog
    probe.cleanup.assert_called_once()


def test_ci_partition_failure_stops_before_first_docker_command(tmp_path):
    env, payload = ci_event(tmp_path, "main-push")
    probe = exercise_ci_lane(tmp_path, env, payload, partition_failure=True)
    assert probe.result != 0
    assert all(call.args[0][0] != "docker" for call in probe.commands.run.call_args_list)
    probe.create.assert_not_called()
    probe.cleanup.assert_called_once()


def test_ci_run_never_adopts_retained_state_even_with_the_same_event(tmp_path):
    env, payload = ci_event(tmp_path, "main-push")
    probe = exercise_ci_lane(tmp_path, env, payload, retained_state=True)
    assert probe.result != 0 and probe.receipt["admission"] == "REFUSED"
    for mock in (probe.commands.run, probe.create, probe.logs, probe.cleanup):
        mock.assert_not_called()


@pytest.mark.parametrize(
    "field", (None, "source_sha", "tree", "asm.c6.source", "asm.c6.tree", "asm.c6.run")
)
def test_ci_child_and_recovery_lease_bind_source_tree_run_and_attempt(tmp_path, field):
    identity = {"head": "b" * 40, "tree": "e" * 40, "run_id": "123", "attempt": "2"}
    lease = {
        "name": "asm-native-" + "a" * 32,
        "bootstrap": str(lane.ROOT / "infra/postgres/bootstrap.sh"),
        "source_sha": identity["head"],
        "tree": identity["tree"],
        "labels": {
            "asm.c6.source": identity["head"],
            "asm.c6.tree": identity["tree"],
            "asm.c6.run": "123:2",
        },
    }
    if field:
        (lease["labels"] if field.startswith("asm.") else lease)[field] = "foreign"
    lane.private_json(tmp_path / "state.json", lease)
    with patch.object(lane, "Commands") as commands:
        if field:
            with pytest.raises(lane.Refusal):
                lane.require_event_lease(tmp_path, identity)
        else:
            lane.require_event_lease(tmp_path, identity)
    commands.assert_not_called()


@pytest.mark.parametrize("mode", ("cleanup", "carrier", "catalog"))
def test_ci_secondary_entrypoints_cannot_adopt_resources_for_bad_event(tmp_path, mode):
    with (
        patch.dict(os.environ, {"NATIVE_ROOT": str(tmp_path)}, clear=True),
        patch.object(lane.sys, "argv", ["runner", mode]),
        patch.object(lane.signal, "signal"),
        patch.object(lane, "admit_event", side_effect=lane.Refusal("bad actual event")),
        patch.object(lane, "cleanup") as cleanup,
        patch.object(lane, "load_lease") as lease,
        patch.object(lane, "verify_server") as server,
    ):
        with pytest.raises(lane.Refusal):
            if mode == "cleanup":
                lane.main()
            else:
                lane.child(mode, tmp_path, tmp_path)
    for mock in (cleanup, lease, server):
        mock.assert_not_called()


def partition_fixture():
    native = [path + "::test_case" for path in REQUIRED_MODULES]
    generic = ["tests/test_tenancy_postgres.py::test_old", "tests/test_other_postgres.py::test_new"]

    def inventory(nodes, pg, fixtures, deselected):
        return {
            "collection_exit": 0,
            "nodeids": nodes,
            "integration_nodeids": pg,
            "native_fixture_nodes": fixtures,
            "deselected": deselected,
        }

    return (
        inventory(generic + native[1:], generic + native[1:], native[1:], native[:1]),
        inventory(native, native[1:], native[1:], []),
        inventory(generic, generic[:], [], native[:1]),
    )


def test_ci_partition_uses_exact_modules_dynamic_ids_and_separate_source_tests():
    assert lane.PG_MODULES == REQUIRED_MODULES[1:]
    a, n, g = partition_fixture()
    assert lane.validate_partition(a, n, g)["native_source"] == 1
    for inventory in (a, n):
        for key in ("nodeids", "integration_nodeids", "native_fixture_nodes"):
            inventory[key].append(REQUIRED_MODULES[3] + "::test_future_case[new]")
    proof = lane.validate_partition(a, n, g)
    assert (proof["all_pg"], proof["generic_pg"], proof["native_pg"], proof["native_total"]) == (
        6,
        2,
        4,
        5,
    )
    assert proof["disjoint_pg_sets_and_complete_union"] and proof["fixed_total_required"] is False


@pytest.mark.parametrize(
    "change",
    (
        "lost-generic",
        "lost-native",
        "module",
        "duplicate",
        "exit",
        "foreign",
        "marker",
        "skip-selection",
        "fixture-escape",
        "fixture-loss",
        "generic-order",
        "source-marker",
    ),
)
def test_ci_partition_refuses_lost_cases_modules_markers_and_fixture_escape(change):
    a, n, g = partition_fixture()
    if change == "lost-generic":
        g["nodeids"].pop()
    elif change == "lost-native":
        n["nodeids"].pop()
    elif change == "duplicate":
        g["nodeids"].append(g["nodeids"][0])
    elif change == "exit":
        a["collection_exit"] = 2
    elif change == "foreign":
        g["nodeids"].append("tests/test_foreign.py::test_x")
    elif change == "marker":
        n["integration_nodeids"].pop()
    elif change == "skip-selection":
        n["deselected"].append("test_hidden")
    elif change == "fixture-escape":
        g["native_fixture_nodes"].append(g["nodeids"][0])
    elif change == "fixture-loss":
        a["native_fixture_nodes"].pop()
    elif change == "generic-order":
        g["nodeids"].reverse()
    elif change == "source-marker":
        n["integration_nodeids"].append(n["nodeids"][0])
    with patch.object(
        lane, "MODULES", REQUIRED_MODULES[:-1] if change == "module" else REQUIRED_MODULES
    ):
        with pytest.raises(lane.Refusal):
            lane.validate_partition(a, n, g)


def test_ci_collection_is_collect_only_and_hook_blocks_fixture_execution(tmp_path):
    def collect(argv, *, plugins):
        assert "--collect-only" in argv
        with pytest.raises(lane.Refusal, match="never execute fixtures"):
            plugins[0].pytest_runtest_setup(object())
        return 2

    path = tmp_path / "inventory.json"
    with patch.dict(os.environ, {}, clear=True), patch("pytest.main", side_effect=collect):
        assert lane.collect_partition("collect-all-pg", path) == 2
    assert json.loads(path.read_text())["collection_exit"] == 2


def test_ci_failed_partition_collection_cannot_proceed(tmp_path):
    commands = Mock()
    commands.run.return_value = (2, b"collection error")
    with pytest.raises(lane.Refusal):
        lane.prove_partition(tmp_path, tmp_path, commands, {})
    assert commands.run.call_count == 1


@pytest.mark.parametrize("bad_selection", (False, True))
def test_ci_actual_generic_execution_must_match_proven_inventory(tmp_path, bad_selection):
    expected = partition_fixture()[2]["nodeids"]

    def execute(argv, *, plugins):
        assert argv[:4] == ["-v", "--durations=20", "-m", "integration"]
        assert (
            tuple(arg.removeprefix("--ignore=") for arg in argv if arg.startswith("--ignore="))
            == REQUIRED_MODULES[1:]
        )
        items = [
            SimpleNamespace(nodeid=node) for node in (expected[:-1] if bad_selection else expected)
        ]
        plugins[0].pytest_collection_finish(SimpleNamespace(items=items))
        return 7

    with (
        patch.dict(
            os.environ,
            {
                "ASM_DATABASE_URL": "ordinary-runtime",
                "ASM_MIGRATION_DATABASE_URL": "ordinary-migrator",
            },
            clear=True,
        ),
        patch.object(lane, "prove_partition", return_value=({}, expected)),
        patch("pytest.main", side_effect=execute),
    ):
        if bad_selection:
            with pytest.raises(lane.Refusal):
                lane.generic_integration()
        else:
            assert lane.generic_integration() == 7


@pytest.mark.parametrize("key", (*lane.SECRET_ENV[:2], "PYTEST_ADDOPTS"))
def test_ci_generic_selection_never_receives_reset_admin_or_subset_flags(key):
    with (
        patch.dict(os.environ, {key: "forbidden"}, clear=True),
        patch.object(lane, "prove_partition") as collect,
    ):
        with pytest.raises(lane.Refusal):
            lane.generic_integration()
    collect.assert_not_called()


@pytest.mark.parametrize("path", tuple(lane.CI_INPUT_SHA256))
def test_ci_guard_reads_actual_inputs_and_refuses_absent_or_changed_gate(tmp_path, path):
    lane.require_ci_inputs()
    for relative in lane.CI_INPUT_SHA256:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((lane.ROOT / relative).read_bytes())
    changed = tmp_path / path
    original = changed.read_bytes()
    changed.write_bytes(
        original.replace(b"native-context-db", b"missing-native-gate", 1)
        if "workflows" in path
        else original.replace(b" generic-integration", b" generic-integration -k subset")
    )
    assert changed.read_bytes() != original
    with patch.object(lane, "ROOT", tmp_path):
        with pytest.raises(lane.Refusal):
            lane.require_ci_inputs()
        changed.unlink()
        with pytest.raises(FileNotFoundError):
            lane.require_ci_inputs()


if __name__ == "__main__":
    unittest.main()
