"""CONTROL wire contract/codec tests; PostgreSQL evidence is in separate suites."""

import hashlib
import json
from uuid import UUID

import pytest
from asm.billing.models import AuditPage
from asm.billing.queries import POST_LOCK_PRODUCT_SNAPSHOT, SNAPSHOT
from asm.conversations.control import control_fingerprint
from asm.conversations.http_models import (
    ControlAcceptedResult,
    ControlCommandRequest,
    ControlCommandResponse,
    ControlStateResponse,
)
from asm.foundation import Settings, create_app
from pydantic import SecretStr, ValidationError
from test_auth_contract import OfflineDatabase

WS, ACTOR, CONVERSATION, CLIENT = (UUID(int=n) for n in range(1, 5))
STAMP = "2026-10-11T12:00:00.123456Z"
REQUEST = {
    "expected_client_id": str(CLIENT),
    "expected_control_generation": "1",
    "expected_context_version": "7",
}


def accepted(**updates):
    return dict(
        workspace_id=str(WS),
        conversation_id=str(CONVERSATION),
        client_id=str(CLIENT),
        receipt_id=str(UUID(int=5)),
        audit_event_id=str(UUID(int=6)),
        operation="RESUME",
        previous_mode="HUMAN",
        accepted_mode="AI",
        previous_generation="1",
        accepted_generation="2",
        context_version="7",
        accepted_at=STAMP,
        **updates,
    )


@pytest.mark.parametrize("field", ["expected_control_generation", "expected_context_version"])
@pytest.mark.parametrize(
    "value", [None, True, 1, 1.0, "0", "01", "+1", "1e0", " 1", "1\n", "9223372036854775808"]
)
def test_decimal_versions_reject_coercion_and_overflow(field, value):
    with pytest.raises(ValidationError):
        ControlCommandRequest.model_validate({**REQUEST, field: value})


def test_exact_body_frozen_and_maximum_bigint():
    maximum = ControlCommandRequest.model_validate(
        {**REQUEST, "expected_context_version": "9223372036854775807"}
    )
    assert maximum.expected_context_version == "9223372036854775807"
    with pytest.raises(ValidationError):
        maximum.expected_context_version = "2"
    for key in REQUEST:
        with pytest.raises(ValidationError):
            ControlCommandRequest.model_validate({k: v for k, v in REQUEST.items() if k != key})
    for key in ("actor", "workspace_id", "activation_fence_seq", "control_mode", "reason"):
        with pytest.raises(ValidationError):
            ControlCommandRequest.model_validate({**REQUEST, key: None})


def test_control_codec_vector_exact_lf_namespaces_and_fields():
    body = ControlCommandRequest.model_validate(REQUEST)
    vector = (
        b"asm:m3:conversation_control:v1\n00000000-0000-0000-0000-000000000001\n"
        b"00000000-0000-0000-0000-000000000002\n00000000-0000-0000-0000-000000000003\n"
        b"00000000-0000-0000-0000-000000000004\nRESUME\n1\n7"
    )
    expected = hashlib.sha256(vector).hexdigest()
    assert control_fingerprint(WS, ACTOR, CONVERSATION, body, "RESUME") == expected
    assert hashlib.sha256(vector + b"\n").hexdigest() != expected
    assert control_fingerprint(WS, ACTOR, CONVERSATION, body, "TAKEOVER") != expected
    for field in REQUEST:
        changed = {**REQUEST, field: str(UUID(int=50)) if field == "expected_client_id" else "9"}
        assert (
            control_fingerprint(
                WS, ACTOR, CONVERSATION, ControlCommandRequest.model_validate(changed), "RESUME"
            )
            != expected
        )
    assert control_fingerprint(WS, UUID(int=50), CONVERSATION, body, "RESUME") != expected


def test_saved_acceptance_is_not_current_state_and_has_no_private_fields():
    saved = ControlAcceptedResult.model_validate(accepted())
    replay = ControlCommandResponse(outcome="REPLAY", result=saved)
    state = ControlStateResponse.model_validate(
        dict(
            workspace_id=str(WS),
            conversation_id=str(CONVERSATION),
            client_id=str(CLIENT),
            control_mode="HUMAN",
            control_generation="3",
            context_version="7",
            observed_at=STAMP,
            manual_delivery={"has_dispatching": False, "has_unknown": True},
        )
    )
    assert replay.result.accepted_mode == "AI" and state.control_mode == "HUMAN"
    for mutation in (
        {"accepted_generation": "1"},
        {"accepted_mode": "HUMAN"},
        {"previous_mode": "AUTO"},
        {"accepted_at": "2026-10-11T12:00:00Z"},
        {"activation_fence_seq": "1"},
    ):
        with pytest.raises(ValidationError):
            ControlAcceptedResult.model_validate({**accepted(), **mutation})
    for flags in (
        {"has_unknown": True},
        {"has_dispatching": 0, "has_unknown": False},
        {"has_dispatching": False, "has_unknown": False, "job_id": None},
    ):
        with pytest.raises(ValidationError):
            ControlStateResponse.model_validate({**state.model_dump(), "manual_delivery": flags})


def test_control_audit_discriminator_and_exact_generations():
    base = dict(
        audit_event_id=str(UUID(int=6)),
        occurred_at=STAMP,
        correlation_id=str(UUID(int=8)),
        object_type="CONVERSATION",
        object_id=str(CONVERSATION),
        object_version="7",
        actor_kind="USER_ACCOUNT",
        actor_user_account_id=str(ACTOR),
    )
    items = [
        dict(
            **base,
            event_type=event,
            payload={
                "previous_mode": "HUMAN",
                "control_mode": mode,
                "previous_generation": "9007199254740992",
                "control_generation": "9007199254740993",
            },
        )
        for event, mode in (("CONVERSATION_TAKEN_OVER", "HUMAN"), ("CONVERSATION_RESUMED", "AI"))
    ]
    assert (
        AuditPage.model_validate({"items": items, "next_cursor": None}).model_dump()["items"]
        == items
    )
    for patch in (
        {"control_mode": "HUMAN"},
        {"previous_generation": True},
        {"control_generation": "9007199254740994"},
        {"fence": "8"},
    ):
        with pytest.raises(ValidationError):
            AuditPage.model_validate(
                {
                    "items": [{**items[1], "payload": {**items[1]["payload"], **patch}}],
                    "next_cursor": None,
                }
            )


def test_post_lock_projection_preserves_full_r4_shape_but_captures_one_db_clock():
    assert (
        POST_LOCK_PRODUCT_SNAPSHOT.split("SELECT evaluated_at,", 1)[1]
        == SNAPSHOT.split("SELECT evaluated_at,", 1)[1]
    )
    assert "WITH evaluation AS MATERIALIZED" in POST_LOCK_PRODUCT_SNAPSHOT
    assert POST_LOCK_PRODUCT_SNAPSHOT.count("clock_timestamp()") == 1
    assert "CURRENT_TIMESTAMP" in SNAPSHOT and "clock_timestamp" not in SNAPSHOT


def test_control_generated_api_has_three_exact_routes_and_strict_models():
    api = create_app(
        Settings(
            environment="TEST",
            database_url=SecretStr("postgresql+psycopg://asm_runtime:unused@localhost/asm_test"),
        ),
        OfflineDatabase(),
    ).openapi()
    assert api == json.loads(open("contracts/openapi.json").read())
    prefix = "/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
    for suffix, method in (("control", "get"), ("takeover", "post"), ("resume", "post")):
        assert set(api["paths"][f"{prefix}/{suffix}"]) == {method}
    for name in (
        "ControlStateResponse",
        "ManualDeliveryState",
        "ControlAcceptedResult",
        "ControlCommandResponse",
        "ControlErrorDetail",
        "ControlErrorResponse",
        "ConversationTakenOverAudit",
        "ConversationResumedAudit",
        "TakeoverPayload",
        "ResumePayload",
    ):
        schema = api["components"]["schemas"][name]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    for operation in ("takeover", "resume"):
        body = api["paths"][f"{prefix}/{operation}"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert body["additionalProperties"] is False and set(body["required"]) == set(REQUEST)
