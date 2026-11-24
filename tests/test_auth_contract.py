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
    # CONTROL is additive; the frozen auth.v1 and five M2 routes stay exact.
    control_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/control",
        "POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/takeover",
        "POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/resume",
    ]
    # Accepted M3.2 adds exactly four owner routes; the frozen auth list stays exact.
    escalation_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/escalations",
        "GET /api/v1/workspaces/{workspace_id}/escalations/{escalation_id}",
        "POST /api/v1/workspaces/{workspace_id}/escalations/{escalation_id}/resolve",
        "POST /api/v1/workspaces/{workspace_id}/escalations/{escalation_id}/cancel",
    ]
    # Accepted native context adds exactly three owner routes; auth.v1 stays frozen.
    native_context_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/human-context",
        "GET /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/human-context/observations",
        "POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/human-context/reconcile",
    ]
    configuration_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration/draft",
        "PUT /api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration/draft",
        "GET /api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration/preview",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration/publish",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration/rollback",
        "GET /api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration/active",
    ]
    knowledge_endpoints = [
        "GET /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/sources",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/sources/{source_id}/confirm",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/sources/{source_id}/revoke",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/sources/{source_id}/delete",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/builds",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/publish",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge/rollback",
    ]
    portfolio_prefix = "/api/v1/workspaces/{workspace_id}/businesses/{business_id}/portfolio"
    portfolio_upload = "/assets/{asset_id}/versions/{version_id}/uploads/{upload_id}"
    portfolio_endpoints = [
        f"GET {portfolio_prefix}",
        f"POST {portfolio_prefix}/assets/uploads",
        f"PUT {portfolio_prefix}{portfolio_upload}/content",
        f"POST {portfolio_prefix}{portfolio_upload}/finalize",
        f"POST {portfolio_prefix}{portfolio_upload}/abandon",
        f"POST {portfolio_prefix}{portfolio_upload}/recover",
        f"GET {portfolio_prefix}/assets/{{asset_id}}/versions/{{version_id}}/preview",
        f"POST {portfolio_prefix}/assets/{{asset_id}}/versions/{{version_id}}/purge",
        f"POST {portfolio_prefix}/assets/{{asset_id}}/versions/{{version_id}}/analysis",
        f"POST {portfolio_prefix}/items",
        f"POST {portfolio_prefix}/items/{{item_id}}/confirm",
        f"POST {portfolio_prefix}/items/{{item_id}}/revoke",
        f"POST {portfolio_prefix}/assets/{{asset_id}}/delete",
        f"POST {portfolio_prefix}/builds",
        f"POST {portfolio_prefix}/publish",
        f"POST {portfolio_prefix}/rollback",
        f"GET {portfolio_prefix}/conversations/{{conversation_id}}",
        f"POST {portfolio_prefix}/conversations/{{conversation_id}}/analysis",
        f"POST {portfolio_prefix}/conversations/{{conversation_id}}/matches",
    ]
    intake_prefix = "/api/v1/workspaces/{workspace_id}/businesses/{business_id}/intake"
    intake_endpoints = [
        f"GET {intake_prefix}/conversations/{{conversation_id}}",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/confirm",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/correct",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/cards",
        f"PATCH {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/assessment",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/assessment",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/pricing",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/pricing",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/quote",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/sessions/{{session_id}}/availability",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/sessions/{{session_id}}/availability",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/sessions/{{session_id}}/availability-offers",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/scheduling/blocks",
        "POST /api/v1/workspaces/{workspace_id}/businesses/{business_id}/scheduling/blocks/{block_id}/release",
        "GET /api/v1/workspaces/{workspace_id}/service-approvals",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/approvals",
        f"POST {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/approvals/{{approval_id}}",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/approvals/{{approval_id}}",
        f"GET {intake_prefix}/conversations/{{conversation_id}}/service-requests/{{request_id}}/approvals/{{approval_id}}/sources/{{message_id}}",
        f"GET {intake_prefix}/duration-cases",
        f"GET {intake_prefix}/duration-cases/search",
        f"POST {intake_prefix}/duration-cases/{{operation}}",
    ]
    assert len(contract["endpoints"]) == 7
    assert actual_endpoints == sorted(
        contract["endpoints"]
        + billing_endpoints
        + messaging_endpoints
        + control_endpoints
        + escalation_endpoints
        + native_context_endpoints
        + configuration_endpoints
        + knowledge_endpoints
        + portfolio_endpoints
        + intake_endpoints
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
