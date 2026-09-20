"""HTTP preflight and exact generated schemas; no PostgreSQL evidence claimed here."""

import json
from pathlib import Path

import pytest
from asm.auth.models import AuthCode
from asm.foundation import Settings, create_app
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_auth_contract import OfflineDatabase


def app():
    return create_app(
        Settings(
            environment="TEST",
            database_url=SecretStr("postgresql+psycopg://asm_runtime:unused@localhost/asm_test"),
            auth_origins=("http://localhost:8000",),
        ),
        OfflineDatabase(),
    )


@pytest.mark.parametrize(
    ("origin", "method", "headers", "status"),
    [
        ("http://localhost:8000", "PATCH", "content-type,x-csrf-token,idempotency-key", 200),
        ("http://localhost:8000", "POST", "content-type,x-csrf-bootstrap", 200),
        ("http://localhost:8000", "GET", "x-csrf-token", 200),
        ("http://outside.example", "PATCH", "content-type,x-csrf-token,idempotency-key", 400),
        ("http://localhost:8000", "PUT", "content-type", 400),
        ("http://localhost:8000", "DELETE", "content-type", 400),
        ("http://localhost:8000", "PATCH", "if-match", 400),
        ("http://localhost:8000", "PATCH", "x-forged-actor", 400),
    ],
)
def test_additive_cors_preserves_configured_origin_credentials_and_old_headers(
    origin, method, headers, status
):
    with TestClient(app(), base_url="http://localhost:8000") as client:
        response = client.options(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000001/billing-account",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": headers,
            },
        )
    assert response.status_code == status
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers.get("access-control-allow-origin") != "*"
    if status == 200:
        assert response.headers["access-control-allow-origin"] == origin
        assert set(response.headers["access-control-allow-methods"].split(", ")) == {
            "GET",
            "POST",
            "PATCH",
        }
        allowed = response.headers["access-control-allow-headers"].lower()
        assert all(
            header in allowed
            for header in ("content-type", "x-csrf-token", "x-csrf-bootstrap", "idempotency-key")
        )
    elif origin == "http://outside.example":
        assert "access-control-allow-origin" not in response.headers


def test_generated_billing_schemas_are_strict_disjoint_complete_and_keep_auth_error():
    api = app().openapi()
    assert api == json.loads(Path("contracts/openapi.json").read_text())
    schemas = api["components"]["schemas"]
    assert schemas["ErrorDetail"]["properties"] == {
        "code": {"$ref": "#/components/schemas/AuthCode"}
    }
    assert schemas["AuthCode"]["enum"] == [code.value for code in AuthCode]
    assert set(schemas["CommonErrorDetail"]["properties"]) == {"code"}
    assert set(schemas["BillingStateDetail"]["required"]) == {"code", "state_reason"}
    assert (
        schemas["BillingStateDetail"]["properties"]["code"]["const"] == "BILLING_STATE_UNAVAILABLE"
    )
    assert (
        "BILLING_STATE_UNAVAILABLE"
        not in schemas["CommonErrorDetail"]["properties"]["code"]["enum"]
    )
    for name in (
        "CommonError",
        "CommonErrorDetail",
        "BillingStateError",
        "BillingStateDetail",
        "BillingResponse",
        "BillingAccount",
        "Subscription",
        "Plan",
        "ContactResult",
        "EnabledDecision",
        "DisabledDecision",
        "LimitDecision",
        "AuditPage",
        "ProvisionAudit",
        "ContactAudit",
        "ProvisionPayload",
        "ContactPayload",
    ):
        schema = schemas[name]
        assert schema["additionalProperties"] is False, name
        assert set(schema.get("required", [])) == set(schema["properties"]), name
    assert schemas["BillingResponse"]["properties"]["decisions"]["maxItems"] == 100
    assert schemas["LimitDecision"]["properties"]["limit"]["type"] == "string"
    assert schemas["ContactResult"]["properties"]["result_version"]["type"] == "string"
    assert "\\.[0-9]{6}Z" in schemas["ContactResult"]["properties"]["completed_at"]["pattern"]
    paths = api["paths"]
    billing = paths["/api/v1/workspaces/{workspace_id}/billing"]["get"]
    assert billing["responses"]["503"]["content"]["application/json"]["schema"]["anyOf"] == [
        {"$ref": "#/components/schemas/CommonError"},
        {"$ref": "#/components/schemas/BillingStateError"},
    ]
    patch = paths["/api/v1/workspaces/{workspace_id}/billing-account"]["patch"]
    body = patch["requestBody"]["content"]["application/json"]["schema"]
    assert body["additionalProperties"] is False
    assert set(body["required"]) == {"expected_version", "contact_display_name"}
    assert patch["requestBody"]["required"]
    assert {"404", "409", "422", "503"} <= set(patch["responses"])
    assert set(schemas["ContactResult"]["properties"]) == {
        "workspace_id",
        "billing_account_id",
        "receipt_id",
        "result_version",
        "outcome",
        "completed_at",
    }
