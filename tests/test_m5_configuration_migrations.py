"""0018 source pairing and exact preservation of accepted migration history."""

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from scripts import native_context_db_catalog as catalog

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
    "migrations/versions/0014_ai_runtime.py": "74db20d70ded7ec9bd3fc7baa78af9cbe81136e84651f6525f610615a3907c39",
    "migrations/versions/0015_ai_delivery.py": "9b0492e432d963e380b626a4ae44aae1a299fee94479cab316e0abc896934ece",
    "migrations/versions/0016_polza_runtime.py": "90aec95a85f42fd3c5c6a2dc065a5e7adf9cc231993938bce414f305518043a0",
    "migrations/versions/0017_ai_reply_rights.py": "70f386554d147353675c1ae467cdc3d13c042d6004faadf236b0d2462a139730",
}


def source():
    spec = importlib.util.spec_from_file_location(
        "m5_0018", "migrations/versions/0018_business_configuration.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.upgrade()
    return module, commands


def test_reserved_revision_and_all_accepted_predecessor_bytes():
    module, _ = source()
    assert (module.revision, module.down_revision) == ("0018", "0017")
    assert len(APPLIED) == 17
    for name, expected in APPLIED.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected


def test_full_source_pairing_and_only_two_current_dispatcher_replacements():
    module, _ = source()
    previous = catalog.source_catalog(Path.cwd(), "0017")
    current = catalog.source_catalog(Path.cwd(), "0018")
    assert (
        len(current["functions"]),
        len(current["columns"]),
        sum(map(len, current["columns"].values())),
    ) == (202, 52, 732)
    assert catalog.compare_embedded_profile(current) == {
        "other_functions": 201,
        "tables": 52,
        "result": "PASS",
    }
    replaced = {
        name
        for name in previous["functions"]
        if previous["functions"][name] != current["functions"][name]
    }
    assert replaced == set(module.ORIGINAL) == set(module.CURRENT_FUNCTIONS)
    assert replaced == {
        "platform.ai_provider_session(jsonb,boolean)",
        "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)",
    }
    for name in replaced:
        before = previous["functions"][name]["definition"].replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        )
        assert module.ORIGINAL[name] == before
        assert module.CURRENT_FUNCTIONS[name] == before.replace("'0017'", "'0018'").replace(
            "platform.ai_reply_rights_schema_profile()",
            "platform.business_configuration_schema_profile()",
        )


def test_private_capabilities_and_actual_alembic_text_has_no_accidental_bind():
    module, commands = source()
    assert len(module.RUNTIME_FUNCTIONS) == 3
    sql = "\n".join(commands)
    assert sql.count("GRANT EXECUTE") == 3
    for command in (
        *module.FUNCTIONS.values(),
        *module.RUNTIME_FUNCTIONS.values(),
        *module.TABLES.values(),
        module.IMMUTABLE_SQL,
    ):
        assert not text(command)._bindparams
    for name in module.TABLES:
        table = "platform.business_configuration_" + name
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in commands
        assert f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime" in commands
    assert "FOR SHARE" in module.RUNTIME_FUNCTIONS["configuration_command(uuid,text,text,jsonb)"]
    assert "platform.messaging_lock_owner(ws,actor) IS NOT TRUE" in sql


def test_unused_reverse_refuses_before_ddl_and_restores_original_definitions():
    module, _ = source()
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.downgrade()
    assert commands[0].startswith("LOCK TABLE ")
    assert "CONFIGURATION_DURABLE_DATA" in commands[1] and "55000" in commands[1]
    assert all(sql in commands[2:4] for sql in module.ORIGINAL.values())
    assert not any(sql.startswith("DROP ") for sql in commands[:4])
