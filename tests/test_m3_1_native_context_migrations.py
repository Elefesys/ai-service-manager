"""0013 source freeze. Real PG lifecycle assertions live in the paired PG module."""

import ast
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

MIGRATION = Path("migrations/versions/0013_native_context.py")


def migration():
    spec = importlib.util.spec_from_file_location("native_0013", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_statements():
    module = migration()
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.upgrade()
    return module, commands


def effective_predecessor():
    functions = {}
    for path in sorted(Path("migrations/versions").glob("*.py")):
        if path.name[:4] > "0012":
            continue
        commands = []
        nodes = [
            n
            for n in ast.parse(path.read_text()).body
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.FunctionDef))
        ]
        namespace = {"op": SimpleNamespace(execute=commands.append)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        namespace["upgrade"]()
        for sql in commands:
            for found in re.finditer(
                r"CREATE (?:OR REPLACE )?FUNCTION ([a-z0-9_.]+)\((.*?)\)\s+RETURNS.*?\$\$.*?\$\$",
                sql,
                re.S,
            ):
                args = found[2]
                key = (
                    found[1].split(".")[1]
                    + "("
                    + str(args.count(",") + 1 if args.strip() else 0)
                    + ")"
                )
                functions[key] = found[0].replace(
                    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
                )
    return functions


def test_assigned_successor_applied_source_freeze_and_exact_originals():
    module, _ = source_statements()
    assert (module.revision, module.down_revision) == ("0013", "0012")
    assert len(APPLIED_SHA256) == 12
    for path, digest in APPLIED_SHA256.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
    predecessor = effective_predecessor()
    assert all(sql == predecessor[key] for key, sql in module.ORIGINAL.items())
    assert len(module.BASELINE_FUNCTION_PROFILES) == 132
    assert len(module.NATIVE_COLUMNS) == 45
    assert len(module.TABLES) == 3
    assert (
        module.NATIVE_CATALOG_SHA256
        == "57e03fe369be4bd03116ce380e37a9b447a2bc1a72e3bbf2a70c7ac08d69e370"
    )


def test_closed_native_functions_and_private_projection_definitions():
    module, commands = source_statements()
    originals = {key.split("(")[0] for key in module.ORIGINAL}
    actual = {s for s in module.FUNCTIONS if s.split(".")[1].split("(")[0] not in originals}
    assert actual == set(module.NEW_FUNCTIONS)
    assert len(actual) == 35
    assert set(module.PUBLIC_FUNCTIONS) == {
        "platform.human_context_read(uuid)",
        "platform.human_context_observations(uuid,integer,jsonb)",
        "platform.human_context_reconcile(uuid,text,jsonb)",
        "platform.human_context_work_replay(uuid,uuid)",
    }
    for signature in actual:
        assert f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,asm_runtime" in commands
        assert f"ALTER FUNCTION {signature} OWNER TO asm_migrator" in commands
    for signature in (
        "platform.human_context_projection(uuid,uuid,timestamptz)",
        "platform.human_context_turn_projection(uuid,uuid,timestamptz)",
    ):
        sql = module.FUNCTIONS[signature]
        assert "LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp" in sql
        assert "FOR UPDATE" not in sql and "FOR SHARE" not in sql and "FOR NO KEY UPDATE" not in sql
        assert (
            "platform.message_effective(" not in sql and "platform.material_turn_usable(" not in sql
        )
        assert "clock_timestamp()" not in sql
    for signature in module.PUBLIC_FUNCTIONS:
        assert f"GRANT EXECUTE ON FUNCTION {signature} TO asm_runtime" in commands
    profile = module.FUNCTIONS["platform.human_context_schema_profile()"]
    assert module.NATIVE_CATALOG_SHA256 in profile
    assert "c.value-'functions'" in profile and "FROM pg_sequence" in profile
    assert (
        "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)"
        not in module.PUBLIC_FUNCTIONS
    )


def test_unused_reverse_checks_all_usage_before_any_ddl():
    module = migration()
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.downgrade()
    assert commands[0].startswith("LOCK TABLE")
    assert commands[1].startswith("DO $$") and "ERRCODE='55000'" in commands[1]
    check = commands[1]
    for marker in (
        "human_context_policy_epoch>0",
        "human_observation_epoch IS NOT NULL",
        "human_context_revision_id IS NOT NULL",
        "platform.human_context_observations",
        "platform.human_context_reconciliations",
        "platform.human_context_policy_receipts",
        "human_context_source_receipt_id IS NOT NULL",
        "context_block_reason IS NOT NULL",
        "context_wait_claim_token IS NOT NULL",
        "context_wait_result IS NOT NULL",
        "turn_input->>'schema_version'='3'",
        "request_snapshot->>'schema_version'='3'",
    ):
        assert marker in check
    assert "codec IS NOT NULL" not in check
    drops = {s.removeprefix("DROP FUNCTION ") for s in commands if s.startswith("DROP FUNCTION ")}
    assert drops == set(module.NEW_FUNCTIONS)
    assert all(sql in commands[2:] for sql in module.ORIGINAL.values())


def test_bounded_classifier_atomic_writes_and_completion_paths():
    module, _ = source_statements()
    sql = module.FUNCTIONS["platform.human_context_projection(uuid,uuid,timestamptz)"]
    assert sql.count("LIMIT 1025") == 3
    assert "UNION SELECT id FROM unsequenced_probe" in sql
    assert "LIMIT 17" in sql and "LIMIT 16" in sql
    assert "ORDER BY i.turn_ingress_seq DESC LIMIT 1" in sql
    command = module.FUNCTIONS["platform.human_context_reconcile(uuid,text,jsonb)"]
    assert command.count("UPDATE app.conversations") == 1
    assert (
        command.index("INSERT INTO app.audit_events")
        < command.index("INSERT INTO platform.human_context_reconciliations")
        < command.index("UPDATE app.conversations")
    )
    for name in (
        "platform.messaging_finish_send",
        "platform.files_finish_fetch",
        "platform.material_bind",
        "platform.material_apply",
        "platform.turn_material",
    ):
        assert not any(signature.startswith(name + "(") for signature in module.FUNCTIONS)
    claim = module.FUNCTIONS["platform.messaging_claim(text,timestamptz,timestamptz,uuid)"]
    assert "context_wait_claim_token=NULL,context_wait_result=NULL,status='RUNNING'" in claim
    supersede = module.FUNCTIONS["platform.turn_supersede(platform.messaging_jobs)"]
    assert (
        "turn_outcome='SUPERSEDED',error_code=NULL,context_block_reason=NULL,context_wait_claim_token=NULL,context_wait_result=NULL"
        in supersede
    )


APPLIED_SHA256 = {
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
}


def test_r2_preserves_r1_sql_except_two_bodies_and_generated_profile():
    """Freeze R1 SQL/metadata/DDL/grants; the paired PG carriers test semantics."""
    module, commands = source_statements()
    historical_r1_bodies = {
        "platform.human_context_projection(uuid,uuid,timestamptz)": "5a8c60036a0b8541a7b20b912485a2c0a00fc76ddd2d3e3476a4edfdd7b15830",
        "platform.human_context_reason(jsonb,boolean)": "6cc0081a0955a6a8398ae1b75aa7c45df2078e5392bef79b3b1884ca36286ed1",
        "platform.human_context_schema_profile()": "225049e113b6a9b146557491aea001a48b262d7b51aba8e2112e70c479305966",
    }
    normalized = list(commands)
    bodies = {}
    for signature, old_digest in historical_r1_bodies.items():
        sql = module.FUNCTIONS[signature]
        body = re.search(r"AS \$\$(.*)\$\$", sql, re.S)[1]
        bodies[signature] = body
        assert hashlib.sha256(body.encode()).hexdigest() != old_digest
        assert commands.count(sql) == 1
        normalized[commands.index(sql)] = sql.replace("AS $$" + body + "$$", "AS $$<R2 body>$$")
    assert len(commands) == 198 and len(module.FUNCTIONS) == 53
    assert (
        hashlib.sha256(
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        == "f7871bab01f97ef034b1615e251d385575efaaa31d89325dd0729407803a85a7"
    )
    profile_signature = "platform.human_context_schema_profile()"
    profile_body = bodies[profile_signature]
    for signature, body in bodies.items():
        if signature != profile_signature:
            digest = hashlib.sha256(body.encode()).hexdigest()
            assert profile_body.count(digest) == 1
            profile_body = profile_body.replace(digest, historical_r1_bodies[signature])
    assert (
        hashlib.sha256(profile_body.encode()).hexdigest() == historical_r1_bodies[profile_signature]
    )
