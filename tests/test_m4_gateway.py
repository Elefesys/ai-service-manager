"""Synthetic contract evidence only; no real model, tenant or Telegram claims."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.resources import files

import pytest
from asm.ai.contracts import (
    CONVERSATION_RESULT,
    DTO,
    AdapterResponse,
    GatewayConfig,
    GatewayRequest,
    Limits,
    Message,
    ReadTool,
    Route,
    ToolCall,
    ToolResult,
)
from asm.ai.fake import FakeAdapter, synthetic_read_tool
from asm.ai.gateway import ModelGateway
from pydantic import Field, ValidationError


def config(**limit_changes):
    limits = dict(
        model_calls=3,
        read_executions=4,
        input_bytes=65536,
        output_bytes=8192,
        input_tokens=32768,
        output_tokens=1024,
        total_tokens=100000,
        duration_seconds=30.0,
        currency="RUB",
        cost_budget=Decimal("0.30"),
        call_cost_reservation=Decimal("0.10"),
    )
    return GatewayConfig(
        revision="synthetic_config_v1",
        route=Route(
            branch="RU_AGGREGATOR",
            adapter="fake",
            execution="FAKE",
            endpoint="https://fake.invalid/v1",
            model="openai/gpt-6-luna",
            upstream="synthetic-official",
            eligibility="EVAL_ONLY",
        ),
        prompt_revision="conversation_v1",
        schema_revision="conversation_result_v1",
        limits=Limits(**(limits | limit_changes)),
    )


def request(**changes):
    return GatewayRequest(
        **(
            dict(
                run_id="synthetic-run-1",
                deadline=datetime.now(UTC) + timedelta(seconds=30),
                messages=(Message(role="user", text="Здравствуйте! Сколько стоит услуга?"),),
                tools=(synthetic_read_tool(),),
            )
            | changes
        )
    )


def tools_response(*ids):
    return AdapterResponse(
        kind="TOOLS",
        tool_calls=tuple(
            ToolCall(call_id=i, name="read_context", arguments_json='{"query":"current"}')
            for i in ids
        ),
    )


def tool_results(outcome):
    return tuple(
        ToolResult(call_id=c.call_id, name=c.name, result_json='{"fact":"Цена пока неизвестна."}')
        for c in outcome.tool_calls
    )


@pytest.mark.parametrize(
    "scenario,kind", [("reply", "reply"), ("handoff", "handoff"), ("no_reply", "no_reply")]
)
async def test_final_result_is_typed_and_terminal(scenario, kind):
    cfg = config()
    adapter = FakeAdapter(cfg.route, (scenario,))
    gateway = ModelGateway(cfg, request(), adapter)
    result = await gateway.call()
    assert result.kind == "FINAL" and result.result.kind == kind
    assert result.cost.status == "CONFIRMED" and result.cost.currency == "RUB"
    assert result.budget.calls_used == 1 and result.budget.cost_reserved == Decimal("0.1")
    assert (await gateway.call()).error == "CLOSED"
    assert len(adapter.requests) == 1


async def test_round_trip_pins_config_deadline_and_consumes_one_total_budget():
    cfg, req = config(), request()
    adapter = FakeAdapter(cfg.route, ("tools", "reply"))
    gateway = ModelGateway(cfg, req, adapter)
    first = await gateway.call()
    assert first.kind == "TOOLS" and first.result is None
    assert first.budget.reads_reserved == 1
    final = await gateway.call(tool_results(first))
    assert final.kind == "FINAL" and final.budget.calls_used == 2
    assert final.budget.cost_reserved == Decimal("0.20")
    assert final.budget.tokens_reserved > first.budget.tokens_reserved
    one, two = adapter.requests
    assert one.config == two.config == cfg
    assert one.request.run_id == two.request.run_id == req.run_id
    assert one.request.deadline == two.request.deadline == req.deadline
    assert two.remaining_seconds <= one.remaining_seconds
    assert two.exchanges[0].calls == first.tool_calls
    assert two.exchanges[0].results == tool_results(first)
    assert two.budget.calls_used == 2 and two.budget.reads_reserved == 1


async def test_declared_json_arrays_validate_as_immutable_tool_tuples():
    class Arguments(DTO):
        positions: tuple[int, ...] = Field(min_length=1, max_length=2)

    class Result(DTO):
        values: tuple[int, ...] = Field(min_length=1, max_length=2)

    tool = ReadTool(
        name="read_positions",
        revision="v1",
        description="Synthetic positions",
        arguments=Arguments,
        result=Result,
    )
    response = AdapterResponse(
        kind="TOOLS",
        tool_calls=(
            ToolCall(
                call_id="a",
                name=tool.name,
                arguments_json='{"positions":[1,2]}',
            ),
        ),
    )
    cfg = config()
    gateway = ModelGateway(cfg, request(tools=(tool,)), FakeAdapter(cfg.route, (response, "reply")))
    assert (await gateway.call()).kind == "TOOLS"
    result = await gateway.call(
        (ToolResult(call_id="a", name=tool.name, result_json='{"values":[3,4]}'),)
    )
    assert result.kind == "FINAL"


async def test_exact_three_calls_and_four_reads_succeed():
    cfg = config()
    adapter = FakeAdapter(cfg.route, (tools_response("a", "b"), tools_response("c", "d"), "reply"))
    gateway = ModelGateway(cfg, request(), adapter)
    first = await gateway.call()
    second = await gateway.call(tool_results(first))
    assert second.kind == "TOOLS" and second.budget.reads_reserved == 4
    final = await gateway.call(tool_results(second))
    assert final.kind == "FINAL" and final.budget.calls_used == 3
    assert len(adapter.requests) == 3


@pytest.mark.parametrize(
    "branch,model,endpoint",
    [
        ("RU_AGGREGATOR", "openai/gpt-6-luna", "https://one.invalid/v1"),
        ("DIRECT_PROVIDER", "google/gemini-3.8-flash", "https://two.invalid/v2"),
    ],
)
async def test_config_only_route_variants_are_still_fake_eval_only(branch, model, endpoint):
    cfg = config()
    route = Route(**(cfg.route.model_dump() | dict(branch=branch, model=model, endpoint=endpoint)))
    cfg = GatewayConfig(**(cfg.model_dump() | {"route": route}))
    adapter = FakeAdapter(route)
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.kind == "FINAL"
    assert adapter.requests[0].config.route == route
    assert route.execution == "FAKE" and route.eligibility == "EVAL_ONLY"


async def test_unknown_usage_cost_is_not_zero_or_a_budget_refund():
    cfg = config()
    adapter = FakeAdapter(cfg.route, (tools_response("one"), "unknown_cost"))
    gateway = ModelGateway(cfg, request(), adapter)
    first = await gateway.call()
    assert first.cost.status == "UNKNOWN" and first.cost.amount is None
    final = await gateway.call(tool_results(first))
    assert final.kind == "FINAL" and final.usage.input_tokens is None
    assert final.cost.amount is None and final.cost.status == "UNKNOWN"
    assert final.budget.calls_used == 2 and final.budget.cost_reserved == Decimal("0.20")
    assert final.budget.tokens_reserved > first.budget.tokens_reserved


def test_schema_exactly_matches_runtime_and_assets_are_importable():
    schema = json.loads(files("asm.ai").joinpath("schemas/conversation_result_v1.json").read_text())
    assert schema == CONVERSATION_RESULT.json_schema()
    prompt = files("asm.ai").joinpath("prompts/conversation_v1.txt").read_text()
    assert "untrusted" in prompt and "unknown" in prompt and "Handoff is a proposal" in prompt


def test_immutable_strict_dtos_hide_content_in_repr_and_validation_errors():
    secret = "synthetic-private-sentinel"
    req = request(messages=(Message(role="user", text=secret),))
    assert secret not in repr(req) and secret not in repr(req.messages[0])
    with pytest.raises(ValidationError) as error:
        Message(role="system", text=secret)
    assert secret not in str(error.value)
    with pytest.raises(ValidationError):
        req.run_id = "changed"
    with pytest.raises(ValidationError):
        config(model_calls=True)
    with pytest.raises(ValidationError):
        config(total_tokens="10")
    with pytest.raises(ValidationError):
        config(duration_seconds=float("inf"))


async def test_concurrent_call_does_not_start_a_second_attempt():
    cfg = config(duration_seconds=0.03)
    adapter = FakeAdapter(cfg.route, ("timeout",))
    gateway = ModelGateway(cfg, request(), adapter)
    task = asyncio.create_task(gateway.call())
    await asyncio.sleep(0)  # Only yield to the pending call; no wall-clock sleep.
    assert (await gateway.call()).error == "BUSY"
    assert (await task).error == "TIMEOUT"
    assert len(adapter.requests) == 1 and gateway.budget.calls_used == 1


async def test_cancellation_keeps_reservation_and_closes_request():
    cfg = config()
    adapter = FakeAdapter(cfg.route, ("timeout",))
    gateway = ModelGateway(cfg, request(), adapter)
    task = asyncio.create_task(gateway.call())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gateway.budget.calls_used == 1
    assert (await gateway.call()).error == "CLOSED" and len(adapter.requests) == 1
