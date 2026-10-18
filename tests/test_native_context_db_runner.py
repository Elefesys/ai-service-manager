"""Stdlib unit refusal proofs; these are never PostgreSQL runtime evidence."""

import copy
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import native_context_db_catalog as lane


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
        row.update(runtime_execute=False, acl=[["asm_migrator", "asm_migrator", "EXECUTE", True]])
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
        nodes = [lane.MODULES[0] + "::test_source", lane.MODULES[1] + "::test_new_regression"]
        reports = [dict(nodeid=n, when="call", outcome="passed", xfail=False) for n in nodes]
        lane.validate_collection(nodes, [], reports, 0)
        nodes.append(lane.MODULES[1] + "::test_another_regression")
        reports.append(dict(nodeid=nodes[-1], when="call", outcome="passed", xfail=False))
        lane.validate_collection(nodes, [], reports, 0)

    def test_skip_xfail_no_tests_deselection_and_incomplete_execution_cannot_pass(self):
        nodes = [lane.MODULES[0] + "::test_source", lane.MODULES[1] + "::test_db"]
        good = [dict(nodeid=n, when="call", outcome="passed", xfail=False) for n in nodes]
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


if __name__ == "__main__":
    unittest.main()
