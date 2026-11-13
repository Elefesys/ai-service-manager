"""Additive0017 source/privilege contract; PostgreSQL proofs are separate."""

import hashlib
from pathlib import Path

from test_m4_polza_runtime_migrations import APPLIED

from scripts.native_context_db_catalog import compare_embedded_profile, source_catalog


def test_applied_0001_through_0016_remain_immutable():
    expected = APPLIED | {
        "migrations/versions/0016_polza_runtime.py": "90aec95a85f42fd3c5c6a2dc065a5e7adf9cc231993938bce414f305518043a0"
    }
    assert len(expected) == 16
    for file, digest in expected.items():
        assert hashlib.sha256(Path(file).read_bytes()).hexdigest() == digest


def test_reply_rights_add_only_two_claim_bound_runtime_capabilities():
    old, current = (source_catalog(Path("."), r) for r in ("0016", "0017"))
    added = set(current["functions"]) - set(old["functions"])
    assert added == {
        "platform.ai_reply_rights_current(uuid,uuid,uuid)",
        "platform.ai_reply_rights_probe(uuid,uuid,uuid)",
        "platform.ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)",
        "platform.ai_reply_rights_schema_profile()",
    }
    replacements = {
        "platform.ai_provider_session(jsonb,boolean)",
        "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)",
    }
    for signature, previous in old["functions"].items():
        actual = current["functions"][signature]
        if signature not in replacements:
            assert actual == previous
        else:
            assert actual["body"] == previous["body"].replace(
                "platform.ai_provider_schema_profile()", "platform.ai_reply_rights_schema_profile()"
            ).replace("'0016'", "'0017'")
            assert actual["runtime_execute"] == previous["runtime_execute"]
    assert current["columns"] == old["columns"]
    granted = {s for s in added if current["functions"][s]["runtime_execute"]}
    assert granted == {
        "platform.ai_reply_rights_probe(uuid,uuid,uuid)",
        "platform.ai_reply_rights_commit(uuid,uuid,uuid,bigint,bigint,jsonb,jsonb)",
    }
    assert compare_embedded_profile(current) == {
        "other_functions": 193,
        "tables": 49,
        "result": "PASS",
    }


def test_current_profile_pin_includes_the_additive_rights_boundary():
    from asm.foundation import DATABASE_SCHEMA_REVISION, NATIVE_PROFILE_BODY_SHA256

    current = source_catalog(Path("."), "0019")
    assert DATABASE_SCHEMA_REVISION == "0019"
    assert (
        current["functions"]["platform.published_knowledge_schema_profile()"]["body_sha256"]
        == NATIVE_PROFILE_BODY_SHA256
    )
