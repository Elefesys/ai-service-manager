"""Applied migration integrity and exact legacy contract restoration."""

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from scripts.native_context_db_catalog import source_catalog

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
    "migrations/versions/0018_business_configuration.py": "c265e524fe224b189a43a5dfd5786c62f084d009c0a3374b2335843b824393b4",
    "migrations/versions/0019_published_knowledge.py": "95891e616f7b5601886d298c1d155089c4500ad293f66d5f64d4ab88d282fcff",
    "migrations/versions/0020_knowledge_search.py": "2834b9ffe1fd66507f436e8c89a5e1082f312819214fd57c9819307b918992c2",
}


def source():
    spec = importlib.util.spec_from_file_location(
        "m5_portfolio_0021", "migrations/versions/0021_vision_portfolio.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.upgrade()
    return module, commands


def test_applied0001_through0020_remain_byte_identical_and_slot_has_exact_predecessor():
    module, _ = source()
    assert (module.revision, module.down_revision) == ("0021", "0020")
    assert len(APPLIED) == 20
    for name, digest in APPLIED.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest


def test_exact0020_contracts_are_restored_without_reinterpreting_saved_rows():
    module, _ = source()
    old = source_catalog(Path.cwd(), "0020")["functions"]
    assert set(module.ORIGINAL) == set(module.REPLACEMENTS)
    for signature, definition in module.ORIGINAL.items():
        assert definition == old[signature]["definition"]
    statements = []
    module.op = SimpleNamespace(execute=statements.append)
    module.downgrade()
    first_drop = next(i for i, s in enumerate(statements) if s.startswith("DROP "))
    assert all("PORTFOLIO_DURABLE_DATA" in s for s in statements[1 : 1 + len(module.TABLES)])
    assert all(
        s in statements[:first_drop]
        for s in [
            v.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
            for v in module.ORIGINAL.values()
        ]
    )
    assert not any(s.startswith("UPDATE platform.ai_runs") for s in statements)


def test_new_current_profile_is_independent_and_historical_profiles_stay_closed():
    from scripts.native_context_db_catalog import compare_embedded_profile

    current = source_catalog(Path.cwd(), "0021")
    old = source_catalog(Path.cwd(), "0020")
    assert (len(current["functions"]), len(current["columns"])) == (289, 68)
    assert compare_embedded_profile(current) == {
        "other_functions": 288,
        "tables": 68,
        "result": "PASS",
    }
    for name in old["functions"]:
        if name.endswith("schema_profile()"):
            assert current["functions"][name] == old["functions"][name]
    assert current["functions"]["platform.portfolio_schema_profile()"]["runtime_execute"] is False


def test_migration_literal_strings_do_not_become_sqlalchemy_parameter_bindings():
    _, statements = source()
    for statement in statements:
        assert not text(statement).compile(dialect=postgresql.dialect()).params
