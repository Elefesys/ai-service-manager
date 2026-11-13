"""0019 preserves history and binds the exact publication/current-schema surface."""

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from test_m5_configuration_migrations import APPLIED

from scripts import native_context_db_catalog as catalog


def source():
    spec = importlib.util.spec_from_file_location(
        "m5_0019", "migrations/versions/0019_published_knowledge.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.upgrade()
    return module, commands


def test_reserved_revision_preserves_all_applied_migrations():
    module, _ = source()
    assert (module.revision, module.down_revision) == ("0019", "0018")
    expected = APPLIED | {
        "migrations/versions/0018_business_configuration.py": "c265e524fe224b189a43a5dfd5786c62f084d009c0a3374b2335843b824393b4"
    }
    assert len(expected) == 18
    for name, digest in expected.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest


def test_exact_source_pairing_and_no_implicit_legacy_profile_changes():
    module, _ = source()
    previous = catalog.source_catalog(Path.cwd(), "0018")
    current = catalog.source_catalog(Path.cwd(), "0019")
    assert (
        len(current["functions"]),
        len(current["columns"]),
        sum(map(len, current["columns"].values())),
    ) == (207, 52, 736)
    assert catalog.compare_embedded_profile(current) == {
        "other_functions": 206,
        "tables": 52,
        "result": "PASS",
    }
    changed = {
        name
        for name in previous["functions"]
        if previous["functions"][name] != current["functions"][name]
    }
    assert changed == set(module.ORIGINAL) == set(module.REPLACEMENTS)
    for name in changed:
        assert module.ORIGINAL[name] == previous["functions"][name]["definition"].replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        )
    for revision, name in (
        ("0013", "human_context"),
        ("0015", "ai_delivery"),
        ("0016", "ai_provider"),
        ("0017", "ai_reply_rights"),
        ("0018", "business_configuration"),
    ):
        signature = f"platform.{name}_schema_profile()"
        assert (
            current["functions"][signature]
            == catalog.source_catalog(Path.cwd(), revision)["functions"][signature]
        )


def test_new_helpers_remain_private_and_release_binding_is_enforced_by_ddl():
    module, commands = source()
    assert set(module.FUNCTIONS) == {
        "ai_knowledge_valid(jsonb,jsonb,uuid,uuid)",
        "ai_knowledge_snapshot(uuid,uuid)",
        "ai_knowledge_current(platform.ai_runs)",
        "ai_knowledge_immutable()",
    }
    sql = "\n".join(commands)
    assert "CREATE TABLE" not in sql
    assert "GRANT " not in sql
    assert not any(command.startswith("UPDATE ") for command in commands)
    assert "REFERENCES platform.business_configuration_releases(workspace_id,business_id,id)" in sql
    assert "REFERENCES platform.ai_runs(workspace_id,id,knowledge_pin)" in sql
    for signature in module.FUNCTIONS:
        assert f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC,asm_runtime" in commands
    # Compile with the real dialect: TextClause's preliminary bind scanner has
    # false positives for accepted literal strings ending in a colon.
    for command in commands:
        assert not text(command).compile(dialect=postgresql.dialect()).params


def test_unused_reverse_refuses_pins_before_destructive_ddl_and_restores_exact_bodies():
    module, _ = source()
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.downgrade()
    assert commands[0].startswith("LOCK TABLE ")
    assert "PUBLISHED_KNOWLEDGE_DURABLE_DATA" in commands[1]
    assert "55000" in commands[1]
    assert "knowledge_pin IS NOT NULL" in commands[1]
    assert "SYNTHETIC_PUBLISHED_KNOWLEDGE_V1" in commands[1]
    assert commands[2 : 2 + len(module.ORIGINAL)] == list(module.ORIGINAL.values())
    assert not any(command.startswith("DROP ") for command in commands[:2])
