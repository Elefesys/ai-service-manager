"""0014 source guardrails; real upgrade/roles/constraints are proved in PostgreSQL."""

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

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
