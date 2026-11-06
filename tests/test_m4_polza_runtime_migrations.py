"""Immutable predecessors and current provider admission source audit.

Actual DDL/rollback/privileges are executed separately on owned PostgreSQL.
"""

import hashlib
from pathlib import Path

from scripts.native_context_db_catalog import compare_embedded_profile, source_catalog

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
}


def test_all_applied_migrations_remain_byte_identical():
    assert len(APPLIED) == 15
    for file, digest in APPLIED.items():
        assert hashlib.sha256(Path(file).read_bytes()).hexdigest() == digest


def test_provider_inventory_keeps_historical_verifiers_and_narrow_grants():
    root = Path(".")
    old = source_catalog(root, "0015")
    current = source_catalog(root, "0016")
    for signature in (
        "platform.human_context_schema_profile()",
        "platform.ai_delivery_schema_profile()",
    ):
        assert current["functions"][signature] == old["functions"][signature]
    assert compare_embedded_profile(current)["result"] == "PASS"
    grants = {s for s, f in current["functions"].items() if f["runtime_execute"]} - {
        s for s, f in old["functions"].items() if f["runtime_execute"]
    }
    assert grants == {
        "platform.ai_provider_enqueue(uuid,uuid,uuid)",
        "platform.ai_provider_command(uuid,uuid,uuid,text,jsonb)",
    }
    assert not current["functions"]["platform.ai_provider_session(jsonb,boolean)"][
        "runtime_execute"
    ]
    assert set(current["columns"]) - set(old["columns"]) == {"platform.ai_provider_sessions"}
