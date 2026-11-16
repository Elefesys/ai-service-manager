"""Frozen predecessors, closed version gates and exact source-derived catalog."""

import copy
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from test_m5_portfolio_migrations import APPLIED

from scripts.native_context_db_catalog import (
    Refusal,
    compare_embedded_profile,
    source_catalog,
)


def migration():
    spec = importlib.util.spec_from_file_location(
        "portfolio_delivery_0022", "migrations/versions/0022_portfolio_delivery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.upgrade()
    return module, commands


def test_predecessors_are_frozen_and0022_uses_exact_assigned_slot():
    module, _ = migration()
    assert (module.revision, module.down_revision) == ("0022", "0021")
    applied = APPLIED | {
        "migrations/versions/0021_vision_portfolio.py": "3a161cf82eba873bd6edb11f11c4f63fecb6bd7aef03027449943339bdd6e8f7"
    }
    assert len(applied) == 21
    for path, digest in applied.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_frozen_original_functions_are_exact_source_not_reconstructed_or_installed():
    module, _ = migration()
    previous = source_catalog(Path.cwd(), "0021")
    assert set(module.ORIGINAL) == set(module.REPLACEMENTS)
    assert len(module.ORIGINAL) == 30
    for signature, sql in module.ORIGINAL.items():
        assert sql == previous["functions"][signature]["definition"]


def test_current_verifier_and_inventory_are_closed_and_old_profiles_unchanged():
    previous, current = (source_catalog(Path.cwd(), revision) for revision in ("0021", "0022"))
    assert (len(current["functions"]), len(current["columns"])) == (303, 69)
    assert compare_embedded_profile(current) == {
        "other_functions": 302,
        "tables": 69,
        "result": "PASS",
    }
    for name, row in previous["functions"].items():
        if name.endswith("schema_profile()"):
            assert current["functions"][name] == row
    assert (
        current["functions"]["platform.portfolio_delivery_schema_profile()"]["runtime_execute"]
        is False
    )
    exposed = {
        s
        for s in set(current["functions"]) - set(previous["functions"])
        if current["functions"][s]["runtime_execute"]
    }
    assert exposed == {
        "platform.portfolio_delivery_read(uuid,uuid)",
        "platform.portfolio_delivery_begin(uuid,uuid,uuid,bigint,bigint,jsonb,text)",
    }


@pytest.mark.parametrize("damage", ["body", "type", "privilege"])
def test_independent_source_detects_embedded_profile_drift(damage):
    current = copy.deepcopy(source_catalog(Path.cwd(), "0022"))
    row = current["functions"][
        "platform.portfolio_delivery_begin(uuid,uuid,uuid,bigint,bigint,jsonb,text)"
    ]
    if damage == "body":
        row["body_sha256"] = "f" * 64
    elif damage == "type":
        row["language"] = "sql"
    else:
        row["runtime_execute"] = False
    with pytest.raises(Refusal, match="EMBEDDED_FUNCTION_MISMATCH"):
        compare_embedded_profile(current)


def test_downgrade_refuses_used_state_before_drop_and_restores_exact_predecessor():
    module, _ = migration()
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.downgrade()
    assert commands[0].startswith("LOCK TABLE")
    guard = commands[1]
    assert "PORTFOLIO_DELIVERY_DURABLE_DATA" in guard
    for durable in (
        "portfolio_delivery_intents",
        "conversation_v6",
        "SEND_AI_PHOTO",
        "PORTFOLIO_PHOTO",
        "SYNTHETIC_PORTFOLIO_PHOTO_V1",
    ):
        assert durable in guard
    first_drop = next(i for i, value in enumerate(commands) if value.startswith("DROP "))
    for sql in module.ORIGINAL.values():
        assert (
            sql.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1) in commands[:first_drop]
        )
    type_drop = commands.index("DROP TABLE platform.portfolio_delivery_intents")
    assert any(
        value.startswith("DROP FUNCTION platform.portfolio_delivery_intent_current(")
        for value in commands[:type_drop]
    )
    assert not any(value.startswith(("UPDATE ", "DELETE ")) for value in commands)


def test_migration_strings_have_no_accidental_sqlalchemy_bind_parameters():
    _, commands = migration()
    for sql in commands:
        compiled = text(sql).compile(dialect=postgresql.dialect())
        assert compiled.params == {}


def test_current_native_policy_replaces_only_revision_and_verifier_without_weakening_guards():
    module, _ = migration()
    signature = "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)"
    before = module.ORIGINAL[signature]
    expected = before.replace(
        "p_profile->>'schema_revision'<>'0021'", "p_profile->>'schema_revision'<>'0022'"
    ).replace("platform.portfolio_schema_profile()", "platform.portfolio_delivery_schema_profile()")
    assert module.REPLACEMENTS[signature] == expected
    assert expected.count("SELECT platform.portfolio_delivery_schema_profile() INTO profile;") == 2
    for guard in (
        "session_user<>'asm_migrator'",
        "profile->'valid' IS DISTINCT FROM 'true'::jsonb",
        "p_profile->>'profile_sha256' IS DISTINCT FROM profile->>'profile_sha256'",
        "p_profile->'drain_confirmed' IS DISTINCT FROM 'true'::jsonb",
    ):
        assert guard in expected


def test_existing_text_provider_sessions_only_change_the_current_verifier():
    module, _ = migration()
    signature = "platform.ai_provider_session(jsonb,boolean)"
    before = module.ORIGINAL[signature]
    assert module.REPLACEMENTS[signature] == before.replace(
        "platform.portfolio_schema_profile()", "platform.portfolio_delivery_schema_profile()"
    )
    assert (
        "(('SYNTHETIC_TEXT_V1','conversation_v2'),('SYNTHETIC_PUBLISHED_KNOWLEDGE_V1','conversation_v3'))"
        in before
    )


def test_no_current_runtime_gate_reads_a_closed_historical_verifier():
    current = source_catalog(Path.cwd(), "0022")
    for signature, row in current["functions"].items():
        if not signature.endswith("schema_profile()"):
            assert "portfolio_schema_profile()" not in row["body"], signature


def test_photo_session_lock_preserves_every_guard_and_old_vision_authority():
    module, _ = migration()
    previous = source_catalog(Path.cwd(), "0021")
    current = source_catalog(Path.cwd(), "0022")
    signature = "platform.portfolio_session_lock(uuid,uuid,uuid,numeric)"
    photo = "platform.portfolio_delivery_session_lock(uuid,uuid,uuid,numeric)"
    expected = (
        previous["functions"][signature]["definition"]
        .replace("platform.portfolio_session_lock(", "platform.portfolio_delivery_session_lock(", 1)
        .replace("'SYNTHETIC_VISION_PORTFOLIO_V1'", "'SYNTHETIC_PORTFOLIO_PHOTO_V1'")
    )
    assert module.FUNCTIONS[photo] == expected
    assert current["functions"][signature] == previous["functions"][signature]
    assert current["functions"][photo]["runtime_execute"] is False
    for old_only in (
        "platform.vision_private_reserve(uuid,uuid,text,uuid,uuid,uuid)",
        "platform.portfolio_build_reserve(uuid,uuid,uuid)",
        "platform.portfolio_owner_lookup_reserve(uuid,uuid,uuid)",
    ):
        assert current["functions"][old_only] == previous["functions"][old_only]


def test_photo_runtime_selects_its_session_lock_at_all_three_cost_boundaries():
    current = source_catalog(Path.cwd(), "0022")
    command = current["functions"]["platform.ai_runtime_command(uuid,uuid,text,jsonb)"]["body"]
    query = current["functions"]["platform.portfolio_query_reserve(uuid,uuid,uuid,jsonb)"]["body"]
    assert (
        command.count(
            "IF cfg->>'prompt_revision'='conversation_v6' THEN PERFORM platform.portfolio_delivery_session_lock("
        )
        == 1
    )
    assert (
        command.count(
            "IF r.config->>'prompt_revision'='conversation_v6' THEN PERFORM platform.portfolio_delivery_session_lock("
        )
        == 1
    )
    assert (
        query.count(
            "IF r.config->>'prompt_revision'='conversation_v6' THEN s:=platform.portfolio_delivery_session_lock("
        )
        == 1
    )
    assert command.count("ELSE PERFORM platform.portfolio_session_lock(") == 2
    assert query.count("ELSE s:=platform.portfolio_session_lock(") == 1


def test_current_source_and_generated_verifier_share_the_verified_nonfunction_binding():
    from scripts.native_context_db_catalog import PORTFOLIO_DELIVERY_NONFUNCTION_SHA256

    expected = "6890bd1d959ef3e6c05c0ca8f7e203586035e3a2f46c4e343e4e64dbf38bf210"
    assert PORTFOLIO_DELIVERY_NONFUNCTION_SHA256 == expected
    current = source_catalog(Path.cwd(), "0022")
    body = current["functions"]["platform.portfolio_delivery_schema_profile()"]["body"]
    assert body.count("='" + expected + "'") == 1


def test_photo_intent_current_only_converts_exact_authority_staleness_to_false():
    module, _ = migration()
    signature = "platform.portfolio_delivery_intent_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs,platform.portfolio_delivery_intents)"
    body = module.FUNCTIONS[signature]
    assert body.endswith(
        "EXCEPTION WHEN SQLSTATE 'P2001' THEN\n"
        " IF SQLERRM='AI_STALE' THEN RETURN false; END IF;\n"
        " RAISE;\n"
        "END $$"
    )
    assert body.count("EXCEPTION WHEN") == 1
    previous = source_catalog(Path.cwd(), "0021")
    current = source_catalog(Path.cwd(), "0022")
    old = "platform.ai_delivery_current(platform.messaging_jobs,platform.ai_deliveries,platform.ai_runs)"
    assert current["functions"][old] == previous["functions"][old]
