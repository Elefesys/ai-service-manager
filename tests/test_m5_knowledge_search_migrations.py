"""0020 source replay stays closed while historical releases and receipts stay exact."""

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from test_m5_configuration_migrations import APPLIED

from scripts import native_context_db_catalog as catalog

CAPABILITIES = {
    "knowledge_owner_read(uuid)",
    "knowledge_owner_command(uuid,text,text,jsonb)",
    "knowledge_build_reserve(uuid,uuid,integer)",
    "knowledge_embedding_complete(uuid,uuid,jsonb)",
    "knowledge_build_apply(uuid,uuid,uuid,jsonb)",
    "knowledge_query_reserve(uuid,uuid,uuid,jsonb)",
    "knowledge_query_apply(uuid,uuid,uuid,uuid,uuid,jsonb)",
    "knowledge_runtime_read(uuid,uuid,uuid,jsonb)",
}


def source():
    spec = importlib.util.spec_from_file_location(
        "m5_0020", "migrations/versions/0020_knowledge_search.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.upgrade()
    return module, commands


def test_reserved_successor_and_all_historical_migrations_remain_byte_exact():
    module, _ = source()
    assert (module.revision, module.down_revision) == ("0020", "0019")
    expected = APPLIED | {
        "migrations/versions/0018_business_configuration.py": "c265e524fe224b189a43a5dfd5786c62f084d009c0a3374b2335843b824393b4",
        "migrations/versions/0019_published_knowledge.py": "95891e616f7b5601886d298c1d155089c4500ad293f66d5f64d4ab88d282fcff",
    }
    assert len(expected) == 19
    for path, digest in expected.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_closed_source_inventory_and_exact_replacement_reverse_pairs():
    module, _ = source()
    previous = catalog.source_catalog(Path.cwd(), "0019")
    current = catalog.source_catalog(Path.cwd(), "0020")
    assert (
        len(current["functions"]),
        len(current["columns"]),
        sum(map(len, current["columns"].values())),
        len(current["nonfunction_ddl"]),
    ) == (233, 59, 832, 914)
    assert catalog.compare_embedded_profile(current) == {
        "other_functions": 232,
        "tables": 59,
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
    for name in previous["functions"]:
        if name.endswith("_schema_profile()"):
            assert previous["functions"][name] == current["functions"][name]


def test_direct_storage_private_force_rls_and_only_finite_capabilities_granted():
    module, commands = source()
    current = catalog.source_catalog(Path.cwd(), "0020")
    assert set(module.TABLES) == {
        "sources",
        "revisions",
        "chunks",
        "builds",
        "build_chunks",
        "release_builds",
        "embedding_calls",
    }
    for name in module.TABLES:
        table = "platform.knowledge_" + name
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in commands
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in commands
        assert f"REVOKE ALL ON {table} FROM PUBLIC,asm_runtime" in commands
    for signature in module.FUNCTIONS:
        assert current["functions"]["platform." + signature]["runtime_execute"] == (
            signature in CAPABILITIES
        )
        assert f"REVOKE ALL ON FUNCTION platform.{signature} FROM PUBLIC,asm_runtime" in commands
    assert {sql for sql in commands if sql.startswith("GRANT ")} == {
        f"GRANT EXECUTE ON FUNCTION platform.{signature} TO asm_runtime"
        for signature in CAPABILITIES
    }
    assert not any(sql.startswith("UPDATE ") for sql in commands)
    for sql in commands:
        assert not text(sql).compile(dialect=postgresql.dialect()).params


def test_pins_have_scoped_foreign_keys_and_storage_does_not_copy_fragments_or_queries():
    module, commands = source()
    sql = "\n".join(commands)
    assert (
        "REFERENCES platform.knowledge_release_builds(workspace_id,business_id,release_id,build_id)"
        in sql
    )
    assert "REFERENCES platform.ai_runs(workspace_id,id,search_pin)" in sql
    assert "UNIQUE(workspace_id,run_id)" in module.TABLES["embedding_calls"]
    assert "UNIQUE(workspace_id,business_id,build_id,batch_no)" in module.TABLES["embedding_calls"]
    assert "extensions.vector(1536)" in module.TABLES["build_chunks"]
    assert "to_tsvector('pg_catalog.simple'::regconfig,text)" in module.TABLES["chunks"]
    assert "hnsw" not in sql.lower() and "ivfflat" not in sql.lower()
    for name in ("query_text", "wire text", "fragments", "api_key"):
        assert name not in module.TABLES["embedding_calls"]
    assert "request_sha256" in module.TABLES["embedding_calls"]
    assert "ticket_hash" in module.TABLES["embedding_calls"]


def test_used_reverse_refuses_before_ddl_and_never_drops_durable_data():
    module, _ = source()
    commands = []
    module.op = SimpleNamespace(execute=commands.append)
    module.downgrade()
    assert commands[0].startswith("LOCK TABLE ")
    assert "KNOWLEDGE_SEARCH_DURABLE_DATA" in commands[1] and "55000" in commands[1]
    for carrier in (
        "knowledge_sources",
        "knowledge_builds",
        "knowledge_embedding_calls",
        "search_pin IS NOT NULL",
        "KNOWLEDGE_%",
    ):
        assert carrier in commands[1]
    assert commands[2 : 2 + len(module.ORIGINAL)] == list(module.ORIGINAL.values())
    assert not any(sql.startswith("DROP ") for sql in commands[:2])


def test_each_index_and_query_wire_uses_the_same_fixed_provider_contract():
    module, _ = source()
    routing = "'provider',jsonb_build_object('only',jsonb_build_array('openai'),'allow_fallbacks',false,'require_parameters',true,'max_price',jsonb_build_object('prompt',3,'completion',0,'image',0,'audio',0,'request',0))"
    for signature in (
        "knowledge_build_wire(uuid,uuid,uuid,integer)",
        "knowledge_build_create(uuid,uuid,uuid,jsonb)",
        "knowledge_query_reserve(uuid,uuid,uuid,jsonb)",
        "knowledge_query_apply(uuid,uuid,uuid,uuid,uuid,jsonb)",
    ):
        assert module.FUNCTIONS[signature].count(routing) == 1


def test_owner_build_deadlines_are_finite_read_projections_without_ledger_mutation():
    module, _ = source()
    sql = module.FUNCTIONS["knowledge_owner_read(uuid)"]
    assert "moment timestamptz:=clock_timestamp()" in sql
    assert sql.count("clock_timestamp()") == 1
    assert "b.state='PLANNED' AND b.deadline<=moment THEN 'ERROR'" in sql
    assert "b.state='BUILDING' AND (b.deadline<=moment OR EXISTS(" in sql
    assert "b.state IN ('PLANNED','BUILDING') AND b.deadline<=moment THEN 'DEADLINE'" in sql
    assert sql.count("ec.state='RESERVED' AND ec.deadline<=moment") == 2
    assert "THEN 'EMBEDDING_UNKNOWN'" in sql
    assert "ELSE b.state END" in sql
    for mutation in ("UPDATE platform.", "INSERT INTO", "DELETE FROM"):
        assert mutation not in sql
