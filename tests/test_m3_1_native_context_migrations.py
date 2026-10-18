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
    """Retain the R1/Resume freeze; R3's exact R2 delta is constrained below."""
    module, commands = source_statements()
    historical_r1_bodies = {
        "platform.human_context_projection(uuid,uuid,timestamptz)": "5a8c60036a0b8541a7b20b912485a2c0a00fc76ddd2d3e3476a4edfdd7b15830",
        "platform.human_context_reason(jsonb,boolean)": "6cc0081a0955a6a8398ae1b75aa7c45df2078e5392bef79b3b1884ca36286ed1",
        # R3 also changes this body. The R2 comparison below excludes only the
        # two assigned UTC6 bodies and verifier; Resume reason stays byte-exact.
        "platform.human_context_snapshot_valid(jsonb,text)": "56ae7479219928bdc1e2bc091efc29a6a6b4011e91509395cb973f5a4dc0f006",
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
        == "a942cfa261338faccf73fe0abaee876a82c05c6630e88edebb5a90e49fe2ef30"
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


def test_r3_preserves_r2_sql_except_utc6_bodies_and_generated_profile():
    """Freeze accepted DB-R2, including both Resume corrections and all other SQL."""
    module, commands = source_statements()
    historical_r2_bodies = {
        "platform.human_context_projection(uuid,uuid,timestamptz)": "2ad43cb844a4676fe4d9bc0e5fe8d0d30736e5f306aa7ce5bbab12a32528e4c1",
        "platform.human_context_snapshot_valid(jsonb,text)": "56ae7479219928bdc1e2bc091efc29a6a6b4011e91509395cb973f5a4dc0f006",
        "platform.human_context_schema_profile()": "d485135ecccf986a2b16e71dd451f95508847bb455f8fbf987cf5092ec5de8a6",
    }
    normalized = list(commands)
    bodies = {}
    for signature, old_digest in historical_r2_bodies.items():
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
        == "d077fd534f42eaf3ff5990630ad830d81d7d3727ae91042ff9cfefa6e764a6b4"
    )
    profile_signature = "platform.human_context_schema_profile()"
    profile_body = bodies[profile_signature]
    for signature, body in bodies.items():
        if signature != profile_signature:
            digest = hashlib.sha256(body.encode()).hexdigest()
            assert profile_body.count(digest) == 1
            profile_body = profile_body.replace(digest, historical_r2_bodies[signature])
    assert (
        hashlib.sha256(profile_body.encode()).hexdigest() == historical_r2_bodies[profile_signature]
    )


UTC6_VALID_TIMESTAMPS = (
    "2030-01-01T00:00:00.000000Z",
    "2032-02-29T23:59:59.123400Z",
    "2000-02-29T12:34:56.999999Z",
    "0001-01-01T00:00:00.000000Z",
    "9999-12-31T23:59:59.999999Z",
)
UTC6_INVALID_TIMESTAMPS = (
    "2030-01-01T00:00:00+00:00",
    "2030-01-01T00:00:00.000000+00:00",
    "2030-01-01T07:00:00.000000+07:00",
    "2030-01-01T00:00:00Z",
    "2030-01-01T00:00:00.0Z",
    "2030-01-01T00:00:00.12345Z",
    "2030-01-01T00:00:00.1234567Z",
    "2030-01-01T00:00:00,123456Z",
    "2030-01-01 00:00:00.000000Z",
    "2030-01-01t00:00:00.000000z",
    "2030-1-01T00:00:00.000000Z",
    "2030-01-1T00:00:00.000000Z",
    "2030-01-01T0:00:00.000000Z",
    " 2030-01-01T00:00:00.000000Z",
    "2030-01-01T00:00:00.000000Z\n",
    "2030-02-29T00:00:00.000000Z",
    "2032-02-30T00:00:00.000000Z",
    "2030-04-31T00:00:00.000000Z",
    "2030-00-01T00:00:00.000000Z",
    "2030-13-01T00:00:00.000000Z",
    "2030-01-00T00:00:00.000000Z",
    "2030-01-01T24:00:00.000000Z",
    "2030-01-01T00:60:00.000000Z",
    "2030-01-01T00:00:60.000000Z",
    "0000-01-01T00:00:00.000000Z",
    "10000-01-01T00:00:00.000000Z",
    "infinity",
    "-infinity",
    "now",
    "",
    False,
    1,
    [],
    {},
)


def test_utc6_delivery_vectors_preserve_strict_python_dto_and_resigned_v3():
    """Codec-only evidence; the same vectors run against SQL in the paired PG module."""
    import copy

    import pytest
    from asm.conversations.guards import parse_guarded_snapshot
    from asm.conversations.turns import parse_snapshot
    from asm.messaging.http_models import DeliveryResponse
    from pydantic import ValidationError
    from test_m3_1_native_context import sign, snapshot

    for guarded in (False, True):
        value = snapshot(guarded=guarded)
        value["recent_messages"] = [
            dict(
                message_id="00000000-0000-0000-0000-000000000033",
                version="1",
                direction="OUTBOUND",
                origin="OWNER_MANUAL",
                created_at=UTC6_VALID_TIMESTAMPS[0],
                current=copy.deepcopy(value["members"][0]["current"]),
                delivery=dict(status="SENT", error_code=None, completed_at=None, version="2"),
                file=None,
            )
        ]
        parse = parse_guarded_snapshot if guarded else parse_snapshot
        for moment in UTC6_VALID_TIMESTAMPS:
            candidate = copy.deepcopy(value)
            delivery = candidate["recent_messages"][0]["delivery"]
            delivery["completed_at"] = moment
            assert DeliveryResponse.model_validate(delivery).model_dump(mode="json") == delivery
            before = json.dumps(sign(candidate), sort_keys=True)
            assert parse(candidate).recent_messages[0].delivery.completed_at == moment
            assert json.dumps(candidate, sort_keys=True) == before
        for moment in UTC6_INVALID_TIMESTAMPS:
            candidate = copy.deepcopy(value)
            delivery = candidate["recent_messages"][0]["delivery"]
            delivery["completed_at"] = moment
            with pytest.raises(ValidationError):
                DeliveryResponse.model_validate(delivery)
            with pytest.raises(ValidationError, match="completed_at"):
                parse(sign(candidate))
