"""0014 source guardrails; real upgrade/roles/constraints are proved in PostgreSQL."""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_mock_engine
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.sql.elements import TextClause

from scripts import m4_pg_observation as observation

APPLIED = {
    "migrations/versions/0001_foundation.py": "427ece53f3cff5608643bd0bcf0b07d10de53100dbd48d7728d8f5ee8991c403",
    "migrations/versions/0002_tenant_foundation.py": "f3d021582d8c1a0cd7b3a7d8588b920cc278cf45d3b945f0bec41443b74b7c33",
    "migrations/versions/0003_auth_sessions.py": "78b5f22ab776936a6c33af2ace15e602897e7c36411eb6935a62a4a6facfc79a",
    "migrations/versions/0004_billing_entitlements_audit.py": "ec872f20e3044b673b1919ea124c5ae81d6ce4c93daef503a60a63e5718b4157",
    "migrations/versions/0005_messaging_kernel.py": "bea55b9cd2262ba9967ca5e2e2a2cb9ea95e147b1bd8fe928cac76fda31ab255",
    "migrations/versions/0006_private_images.py": "6fe7a7d772ad2bf2fcf337daa3ccc139f53e2afbfee7350b90916cffbe48840d",
    "migrations/versions/0007_telegram_api.py": "97e24d5e54be934cde9cecd89dbe16fb77b49685d8f58efd031c43fee1111eac",
    "migrations/versions/0008_conversation_turns.py": "74928cdb323fb9d66054cc24a57f12cc0fedf8373eb316cea2ac7ca9ed7affdf",
    "migrations/versions/0009_conversation_control.py": "a36a1d75f1fe70eef347c44f7420bd12b273ca2999bf537ab9de79dc7a8c5339",
    "migrations/versions/0010_conversation_guards.py": "0224b5cb2105e2942b164f6abfac9a7e725cce24314a1653874e69ae18866c6b",
    "migrations/versions/0011_escalations.py": "0985edb566dc91f2d152071a7aa8b3745fc34e843f8e7897070db33e6fe7fce9",
    "migrations/versions/0012_message_provenance.py": "5e6f448b3ef20d7f45499c0a008713a406f5c79b900f1ab06864a6b205c5350a",
    "migrations/versions/0013_native_context.py": "bbc4aa5d10e970dd4eed3ef8c635a8d723c0b18784e60ac1b7aeaa8087e1fe53",
}


def source_statements():
    spec = importlib.util.spec_from_file_location(
        "ai_0014", "migrations/versions/0014_ai_runtime.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements = []
    module.op = SimpleNamespace(execute=statements.append)
    module.upgrade()
    return module, statements


def test_predecessors_immutable_and_successor_assigned():
    module, _ = source_statements()
    assert (module.revision, module.down_revision) == ("0014", "0013")
    assert len(APPLIED) == 13
    for path, expected in APPLIED.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected


def test_closed_capabilities_private_rls_and_durable_intent_keys():
    module, statements = source_statements()
    sql = "\n".join(statements)
    assert len(module.PUBLIC) == 2
    for signature in module.FUNCTIONS:
        assert f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC,asm_runtime" in statements
    assert sql.count("GRANT EXECUTE") == 2
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "UNIQUE(workspace_id,turn_id,turn_revision)" in sql
    assert (
        "REFERENCES platform.messaging_jobs(workspace_id,id,connection_id,kind,turn_id,turn_revision,step)"
        in sql
    )
    assert "REFERENCES app.conversations(workspace_id,id,client_id)" in sql
    assert (
        "REFERENCES platform.conversation_control_receipts(workspace_id,id,conversation_id,client_id,accepted_generation)"
        in sql
    )
    assert "CONTROLLED_GUARDS_V1" not in sql
    assert "human_context_schema_profile" not in sql
    assert "messaging_manual_send" not in sql.replace("messaging_manual_send_allowed", "")


def test_unused_downgrade_refuses_before_ddl_and_restores_narrow_delta():
    module, _ = source_statements()
    statements = []
    module.op = SimpleNamespace(execute=statements.append)
    module.downgrade()
    assert "AI_RUNTIME_DURABLE_DATA" in statements[0]
    assert "step='AI_GENERATE'" in statements[0]
    assert all("DROP " not in s for s in statements[:1])
    assert "AI_GENERATE" not in next(
        s for s in statements if "ADD CONSTRAINT messaging_jobs_turn_check" in s
    )
    assert "AI_RUNTIME_RESCHEDULE_SOURCE_MISMATCH" in statements[-1]


def test_application_revision_not_advanced():
    from asm.foundation import DATABASE_SCHEMA_REVISION

    assert DATABASE_SCHEMA_REVISION == "0013"


def compile_statements(statements):
    """Use Alembic's string-to-text execution path and the actual psycopg compiler."""
    compiled_statements = []

    def executor(construct, *args, **kwargs):
        assert isinstance(construct, TextClause)
        compiled = construct.compile(dialect=engine.dialect)
        assert compiled.construct_params() == {}
        assert not compiled.bind_names
        compiled_statements.append(str(compiled))

    engine = create_mock_engine("postgresql+psycopg://", executor)
    operations = Operations(MigrationContext.configure(connection=engine))
    for statement in statements:
        operations.execute(statement)
    return compiled_statements


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_every_0014_statement_compiles_without_bind_values(direction):
    module, statements = source_statements()
    if direction == "downgrade":
        statements = []
        module.op = SimpleNamespace(execute=statements.append)
        module.downgrade()
    compiled = compile_statements(statements)
    assert statements and len(compiled) == len(statements)


def test_old_default_bind_fails_and_repaired_default_preserves_unknown_json():
    _, statements = source_statements()
    statement = next(s for s in statements if "CREATE TABLE platform.ai_provider_calls" in s)
    literal = re.search(r"completion jsonb NOT NULL DEFAULT '([^']+)'", statement).group(1)
    original = literal.replace(": null", ":null")
    assert original.count(":null") == 5
    with pytest.raises(InvalidRequestError, match="bind parameter 'null'"):
        compile_statements([statement.replace(literal, original)])
    assert len(compile_statements([statement])) == 1
    assert (
        json.loads(literal)
        == json.loads(original)
        == {
            "kind": "UNKNOWN",
            "usage": {"input_tokens": None, "output_tokens": None},
            "cost": {"status": "UNKNOWN", "amount": None, "currency": None},
            "error": None,
        }
    )


@pytest.fixture
def source_evidence(tmp_path, monkeypatch):
    values = {
        "base": observation.BASE,
        "base_tree": observation.BASE_TREE,
        "source": "1" * 40,
        "tree": "2" * 40,
        "paths": sorted(observation.WRITE_SET),
        "run_id": "123456",
        "attempt": 1,
        "event": "push",
        "branch": observation.BRANCH,
        "pins": {"DB_IMAGE": observation.DB_IMAGE},
        "uv_lock_sha256": "3" * 64,
    }
    for name, value in {
        "SOURCE_SHA": values["source"],
        "SOURCE_TREE": values["tree"],
        "RUN_ID": values["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("ASM_M4_" + name, value)
    # This is a real directory without Git metadata, as in the checks image.
    assert not (tmp_path / ".git").exists()
    path = tmp_path / "source.json"
    path.write_text(json.dumps(values))
    return path, values


def test_source_evidence_valid_without_git(source_evidence):
    path, values = source_evidence
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CEILING_DIRECTORIES"] = str(path.parent.parent)
    previous_fixture = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=path.parent, env=env, capture_output=True
    )
    assert previous_fixture.returncode == 128
    assert observation.source_tree_from_evidence(path) == values["tree"]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("missing", "MISSING"),
        ("malformed", "MALFORMED"),
        ("duplicate", "DUPLICATE_KEY"),
        ("non_object", "SHAPE"),
        ("missing_key", "SHAPE"),
        ("short_source", "MISMATCH"),
        ("invalid_tree", "MISMATCH"),
        ("stale_source", "MISMATCH"),
        ("stale_tree", "MISMATCH"),
        ("stale_base", "MISMATCH"),
        ("stale_base_tree", "MISMATCH"),
        ("stale_branch", "MISMATCH"),
        ("stale_run", "MISMATCH"),
        ("wrong_event", "MISMATCH"),
        ("retry", "MISMATCH"),
        ("bool_attempt", "MISMATCH"),
        ("foreign_path", "SHAPE"),
        ("missing_environment", "ENVIRONMENT"),
        ("short_environment_tree", "ENVIRONMENT"),
    ],
)
def test_source_evidence_rejects_missing_malformed_stale_without_git(
    source_evidence, monkeypatch, case, expected
):
    path, values = source_evidence
    mutations = {
        "short_source": ("source", "1" * 8),
        "invalid_tree": ("tree", "z" * 40),
        "stale_source": ("source", "4" * 40),
        "stale_tree": ("tree", "4" * 40),
        "stale_base": ("base", "4" * 40),
        "stale_base_tree": ("base_tree", "4" * 40),
        "stale_branch": ("branch", "c2/m4-3-pg-runtime-run-r1"),
        "stale_run": ("run_id", "123455"),
        "wrong_event": ("event", "workflow_dispatch"),
        "retry": ("attempt", 2),
        "bool_attempt": ("attempt", True),
        "foreign_path": ("paths", ["backend/src/asm/foundation.py"]),
    }
    if case in mutations:
        key, value = mutations[case]
        values[key] = value
        path.write_text(json.dumps(values))
    elif case == "missing":
        path.unlink()
    elif case == "malformed":
        path.write_text("{")
    elif case == "duplicate":
        path.write_text('{"tree":"duplicate",' + json.dumps(values)[1:])
    elif case == "non_object":
        path.write_text("[]")
    elif case == "missing_key":
        del values["source"]
        path.write_text(json.dumps(values))
    elif case == "missing_environment":
        monkeypatch.delenv("ASM_M4_SOURCE_SHA")
    elif case == "short_environment_tree":
        monkeypatch.setenv("ASM_M4_SOURCE_TREE", "2" * 8)
    else:
        pytest.fail("unhandled source evidence case")
    with pytest.raises(RuntimeError, match="^SOURCE_IDENTITY_" + expected + "$"):
        observation.source_tree_from_evidence(path)


def test_checks_passes_independent_host_source_identity(source_evidence, monkeypatch):
    path, values = source_evidence
    for name, value in {
        "SHA": values["source"],
        "RUN_ID": values["run_id"],
        "RUN_ATTEMPT": "1",
    }.items():
        monkeypatch.setenv("GITHUB_" + name, value)
    host_tree = values["tree"]
    values["tree"] = "4" * 40
    path.write_text(json.dumps(values))

    def capture(command):
        assert command == ["git", "rev-parse", "HEAD^{tree}"]
        return host_tree

    monkeypatch.setattr(observation, "capture", capture)
    command = observation.checks(path.parent, "pytest", plugin=True)
    environment = [command[i + 1] for i, item in enumerate(command) if item == "-e"]
    assert environment == [
        "ASM_M4_PG_PLUGIN=1",
        "ASM_M4_SOURCE_SHA=" + values["source"],
        "ASM_M4_SOURCE_TREE=" + host_tree,
        "ASM_M4_RUN_ID=" + values["run_id"],
        "ASM_M4_RUN_ATTEMPT=1",
    ]
    assert command[-2:] == ["checks", "pytest"]
