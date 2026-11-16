"""The actual gateway selects the v3 final parser, retaining its one-call budget."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from asm.ai.contracts import (
    AdapterResponse,
    GatewayRequest,
    IntakeGatewayConfig,
    IntakeGatewayResult,
    Message,
)
from asm.ai.fake import FakeAdapter
from asm.ai.gateway import ModelGateway
from m5_intake_fixtures import candidates
from test_m4_agent import config


@pytest.mark.asyncio
async def test_new_synthetic_gateway_returns_candidate_facts_in_one_final_call():
    cfg = IntakeGatewayConfig.model_validate(
        config().model_dump()
        | {"prompt_revision": "conversation_v7", "schema_revision": "conversation_result_v3"}
    )
    adapter = FakeAdapter(
        cfg.route,
        (
            AdapterResponse(
                kind="OUTPUT",
                output_json=json.dumps(
                    {
                        "kind": "reply",
                        "text": "Question",
                        "reason": None,
                        "intake": candidates().model_dump(mode="json"),
                    }
                ),
            ),
        ),
    )
    request = GatewayRequest(
        run_id="intake-unit",
        deadline=datetime.now(UTC) + timedelta(seconds=20),
        messages=(Message(role="user", text="flower"),),
        tools=(),
    )
    result = await ModelGateway(cfg, request, adapter).call()
    assert isinstance(result, IntakeGatewayResult) and result.kind == "FINAL"
    assert result.result.intake.facts[0].value == "цветок" and result.budget.calls_used == 1
