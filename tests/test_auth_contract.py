"""Consumer/schema drift checks; generated OpenAPI contains no credentials or runtime state."""

import difflib
import json
from pathlib import Path

from asm.auth.config import AuthSettings
from asm.auth.crypto import PASSWORD_HASHER
from asm.auth.models import AuthCode
from asm.foundation import Settings, create_app
from pydantic import SecretStr


class OfflineDatabase:
    async def check(self):
        raise RuntimeError("Schema export must not connect to a database")

    async def close(self):
        pass


def test_auth_machine_contract_and_generated_c5_api_have_no_drift():
    contract = json.loads(Path("contracts/auth.v1.json").read_text())
    settings = Settings(
        environment="TEST",
        database_url=SecretStr("postgresql+psycopg://asm_runtime:unused@localhost/asm_test"),
    )
    api = create_app(settings, OfflineDatabase()).openapi()
    actual_endpoints = sorted(
        f"{method.upper()} {path}"
        for path, methods in api["paths"].items()
        if path.startswith(("/api/v1/auth/", "/api/v1/workspaces/"))
        for method in methods
    )
    billing_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/billing",
        "PATCH /api/v1/workspaces/{workspace_id}/billing-account",
        "GET /api/v1/workspaces/{workspace_id}/audit-events",
    ]
    # M2.3 adds exactly five owner routes; frozen auth.v1 stays seven endpoints.
    messaging_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/channel-connections",
        "GET /api/v1/workspaces/{workspace_id}/conversations",
        "GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        "POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        "POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages/{message_id}/files/{file_id}/read-grant",
    ]
    assert len(contract["endpoints"]) == 7
    assert actual_endpoints == sorted(
        contract["endpoints"] + billing_endpoints + messaging_endpoints
    )
    assert contract["schema_revision"] == "0003" and contract["down_revision"] == "0002"
    assert contract["environments"] == ["LOCAL", "TEST"]
    assert contract["error_codes"] == [code.value for code in AuthCode]
    defaults = AuthSettings()
    assert contract["session"]["absolute_ttl_default_seconds"] == defaults.auth_session_ttl_seconds
    assert contract["session"]["prelogin_ttl_default_seconds"] == defaults.auth_prelogin_ttl_seconds
    assert contract["password"]["memory_kib"] == PASSWORD_HASHER.memory_cost
    assert contract["password"]["time_cost"] == PASSWORD_HASHER.time_cost
    assert contract["password"]["parallelism"] == PASSWORD_HASHER.parallelism
    assert contract["password"]["algorithm"] == "argon2id"
    assert contract["production_enabled"] is False and contract["platform_ops_authorized"] is False
    expected = Path("contracts/openapi.json").read_text()
    actual = json.dumps(api, sort_keys=True, indent=2) + "\n"
    if expected != actual:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(True),
                actual.splitlines(True),
                fromfile="a/contracts/openapi.json",
                tofile="b/contracts/openapi.json",
            )
        )
        raise AssertionError("OpenAPI drift; generate/review/commit the snapshot:\n" + diff)
