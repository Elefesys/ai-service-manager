"""Boundary negatives: reject without exposing raw model/tool/provider content."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from asm.ai.contracts import (
    AdapterResponse,
    Capabilities,
    Cost,
    GatewayConfig,
    Message,
    Route,
    ToolCall,
    ToolResult,
    Usage,
)
from asm.ai.fake import FakeAdapter
from asm.ai.gateway import ModelGateway
from pydantic import ValidationError
from test_m4_gateway import config, request, tool_results, tools_response


@pytest.mark.parametrize(
    "scenario,error",
    [
        ("invalid", "INVALID_OUTPUT"),
        ("truncated", "TRUNCATED"),
        ("oversize", "OUTPUT_SIZE"),
        ("429", "RATE_LIMIT"),
        ("5xx", "UNAVAILABLE"),
        ("timeout", "TIMEOUT"),
    ],
)
async def test_provider_failures_are_terminal_and_never_retried(scenario, error):
    cfg = config(duration_seconds=0.02)
    adapter = FakeAdapter(cfg.route, (scenario, "reply"))
    gateway = ModelGateway(cfg, request(), adapter)
    result = await gateway.call()
    assert result.kind == "ERROR" and result.error == error and result.result is None
    assert result.budget.calls_used == 1 and result.budget.cost_reserved > 0
    if scenario in ("timeout", "429", "5xx"):
        assert result.cost.status == "UNKNOWN" and result.cost.amount is None
        assert result.usage.output_tokens is None
    else:
        assert result.cost.status == "CONFIRMED" and result.cost.amount == Decimal("0.01")
    assert (await gateway.call()).error == "CLOSED" and len(adapter.requests) == 1


async def test_refusal_is_not_a_reply():
    cfg = config()
    adapter = FakeAdapter(cfg.route, ("refusal",))
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.kind == "REFUSAL" and result.result is None and result.error is None


@pytest.mark.parametrize(
    "limits",
    [
        {"model_calls": 0},
        {"read_executions": 0},
        {"total_tokens": 0},
        {"cost_budget": Decimal(0)},
        {"call_cost_reservation": Decimal(0)},
        {"total_tokens": 1},
    ],
)
async def test_exhausted_budgets_do_not_call_adapter(limits):
    cfg = config(**limits)
    adapter = FakeAdapter(cfg.route)
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.error == "BUDGET" and not adapter.requests
    assert result.budget.calls_used == 0


async def test_expired_deadline_never_calls_adapter():
    cfg = config()
    adapter = FakeAdapter(cfg.route)
    result = await ModelGateway(
        cfg, request(deadline=datetime.now(UTC) - timedelta(seconds=1)), adapter
    ).call()
    assert result.error == "DEADLINE" and not adapter.requests


@pytest.mark.parametrize(
    "field,value",
    [
        ("structured_output", None),
        ("structured_output", False),
        ("read_tools", None),
        ("read_tools", False),
        ("tools_with_structured_output", None),
        ("tools_with_structured_output", False),
        ("token_limits", None),
        ("deadline", False),
        ("bounded_output", None),
        ("schema_revisions", ()),
        ("max_input_tokens", None),
        ("max_input_tokens", 1),
        ("max_output_tokens", 1),
    ],
)
async def test_unconfirmed_or_incompatible_capability_never_calls_adapter(field, value):
    cfg = config()
    adapter = FakeAdapter(cfg.route)
    adapter.capabilities = Capabilities(**(adapter.capabilities.model_dump() | {field: value}))
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.error == "CAPABILITY" and not adapter.requests


@pytest.mark.parametrize(
    "field,value",
    [
        ("branch", "DIRECT_PROVIDER"),
        ("model", "other-model"),
        ("upstream", "other-upstream"),
        ("endpoint", "https://other.invalid/v1"),
    ],
)
async def test_route_mismatch_cannot_fall_back(field, value):
    cfg = config()
    other = Route(**(cfg.route.model_dump() | {field: value}))
    adapter = FakeAdapter(other)
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.error == "ROUTE" and not adapter.requests


async def test_route_change_mid_round_trip_is_rejected():
    cfg = config()
    adapter = FakeAdapter(cfg.route, ("tools", "reply"))
    gateway = ModelGateway(cfg, request(), adapter)
    first = await gateway.call()
    changed = Route(**(cfg.route.model_dump() | {"model": "other-model"}))
    adapter.capabilities = Capabilities(**(adapter.capabilities.model_dump() | {"route": changed}))
    assert (await gateway.call(tool_results(first))).error == "ROUTE"
    assert len(adapter.requests) == 1


async def test_continuation_rechecks_deadline_and_total_input_budget(monkeypatch):
    cfg, req = config(), request()
    adapter = FakeAdapter(cfg.route, ("tools", "reply"))
    gateway = ModelGateway(cfg, req, adapter)
    first = await gateway.call()
    monkeypatch.setattr(gateway, "_remaining_seconds", lambda: 0.0)
    result = await gateway.call(tool_results(first))
    assert result.error == "DEADLINE" and len(adapter.requests) == 1
    assert result.budget == first.budget

    # First call fits exactly; the tool continuation has no fresh token allowance.
    cfg = config(total_tokens=first.budget.tokens_reserved)
    adapter = FakeAdapter(cfg.route, ("tools", "reply"))
    gateway = ModelGateway(cfg, req, adapter)
    result = await gateway.call()
    assert result.error == "BUDGET" and len(adapter.requests) == 1
    assert not result.tool_calls

    # A second input includes tool exchanges, so it must be measured again.
    initial_bytes = len(adapter.requests[0].input_json().encode("utf-8"))
    cfg = config(input_bytes=initial_bytes)
    adapter = FakeAdapter(cfg.route, ("tools", "reply"))
    gateway = ModelGateway(cfg, req, adapter)
    first = await gateway.call()
    assert first.kind == "TOOLS"
    result = await gateway.call(tool_results(first))
    assert result.error == "INPUT_SIZE" and len(adapter.requests) == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"kind":"reply","text":"ok","reason":null,"price":10}',
        '{"kind":"reply","text":4,"reason":null}',
        '{"kind":"reply","text":"ok","reason":"unexpected"}',
        '{"kind":"reply","text":"","reason":null}',
        '{"kind":"reply","text":"   ","reason":null}',
        '{"kind":"reply","text":"ok"}',
        '{"kind":"handoff","text":"ok","reason":null}',
        '{"kind":"no_reply","text":"ok","reason":"none"}',
        '{"kind":"reply","kind":"no_reply","text":null,"reason":"x"}',
        '{"kind":"reply","text":"\\ud800","reason":null}',
        '{"kind":"reply","text":NaN,"reason":null}',
        '{"kind":"reply","text":"truncated',
        json.dumps({"kind": "reply", "text": "x" * 4001, "reason": None}),
        json.dumps({"kind": "handoff", "text": None, "reason": "x" * 501}),
    ],
)
async def test_strict_local_output_validation_even_with_structured_capability(raw):
    cfg = config()
    adapter = FakeAdapter(cfg.route, (AdapterResponse(kind="OUTPUT", output_json=raw),))
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.error == "INVALID_OUTPUT" and result.result is None
    assert raw not in repr(result)


@pytest.mark.parametrize(
    "name,arguments,error",
    [
        ("execute_sql", '{"query":"current"}', "TOOL_CONTRACT"),
        ("read_context", '{"query":"current","workspace_id":"other"}', "TOOL_CONTRACT"),
        ("read_context", '{"query":1}', "TOOL_CONTRACT"),
        ("read_context", '{"query":"other-client"}', "TOOL_CONTRACT"),
        ("read_context", '{"query":"current","query":"current"}', "TOOL_CONTRACT"),
    ],
)
async def test_tool_names_and_arguments_require_declared_contract(name, arguments, error):
    cfg = config()
    response = AdapterResponse(
        kind="TOOLS", tool_calls=(ToolCall(call_id="a", name=name, arguments_json=arguments),)
    )
    result = await ModelGateway(cfg, request(), FakeAdapter(cfg.route, (response,))).call()
    assert result.error == error and not result.tool_calls and result.budget.reads_reserved == 0


@pytest.mark.parametrize(
    "results,error",
    [
        ((), "TOOL_CORRELATION"),
        (
            (ToolResult(call_id="wrong", name="read_context", result_json='{"fact":"ok"}'),),
            "TOOL_CORRELATION",
        ),
        (
            (ToolResult(call_id="read-1", name="other", result_json='{"fact":"ok"}'),),
            "TOOL_CORRELATION",
        ),
        (
            (ToolResult(call_id="read-1", name="read_context", result_json='{"fact":1}'),),
            "TOOL_CONTRACT",
        ),
        (
            (
                ToolResult(
                    call_id="read-1", name="read_context", result_json='{"fact":"ok","extra":true}'
                ),
            ),
            "TOOL_CONTRACT",
        ),
        (
            (
                ToolResult(
                    call_id="read-1",
                    name="read_context",
                    result_json='{"fact":"' + "x" * 201 + '"}',
                ),
            ),
            "TOOL_CONTRACT",
        ),
    ],
)
async def test_bad_tool_result_never_reaches_next_model_call(results, error):
    cfg = config()
    adapter = FakeAdapter(cfg.route, ("tools", "reply"))
    gateway = ModelGateway(cfg, request(), adapter)
    assert (await gateway.call()).kind == "TOOLS"
    outcome = await gateway.call(results)
    assert outcome.error == error and len(adapter.requests) == 1
    assert outcome.budget.reads_reserved == 1


async def test_duplicate_ids_and_replayed_results_are_rejected():
    cfg = config()
    for script in [
        (tools_response("same", "same"),),
        (tools_response("same"), tools_response("same")),
    ]:
        adapter = FakeAdapter(cfg.route, script)
        gateway = ModelGateway(cfg, request(), adapter)
        result = await gateway.call()
        if result.kind == "TOOLS":
            result = await gateway.call(tool_results(result))
        assert result.error == "TOOL_CORRELATION"
    adapter = FakeAdapter(cfg.route, (tools_response("a", "b"), "reply"))
    gateway = ModelGateway(cfg, request(), adapter)
    results = tool_results(await gateway.call())
    assert (await gateway.call((results[0], results[0]))).error == "TOOL_CORRELATION"
    assert len(adapter.requests) == 1


async def test_unrequested_results_are_rejected_before_first_call():
    cfg = config()
    adapter = FakeAdapter(cfg.route)
    result = await ModelGateway(cfg, request(), adapter).call(
        (ToolResult(call_id="a", name="read_context", result_json='{"fact":"ok"}'),)
    )
    assert result.error == "TOOL_CORRELATION" and not adapter.requests


@pytest.mark.parametrize(
    "limits,script",
    [
        ({"read_executions": 0}, ("tools",)),
        ({"model_calls": 1}, ("tools",)),
        ({}, (tools_response("a", "b", "c", "d"), tools_response("e"))),
        ({}, ("tools", "tools", "tools")),
        ({"cost_budget": Decimal("0.10")}, ("tools",)),
    ],
)
async def test_call_read_and_cost_ceilings_cannot_be_reset_by_tools(limits, script):
    cfg = config(**limits)
    adapter = FakeAdapter(cfg.route, script)
    gateway = ModelGateway(cfg, request(), adapter)
    result = await gateway.call()
    while result.kind == "TOOLS":
        result = await gateway.call(tool_results(result))
    assert result.error == "BUDGET" and len(adapter.requests) <= 3
    assert result.budget.reads_reserved <= 4
    assert (await gateway.call()).error == "CLOSED"


async def test_input_byte_and_token_limits_accept_exact_boundary_reject_above():
    cfg, req = config(), request()
    adapter = FakeAdapter(cfg.route)
    await ModelGateway(cfg, req, adapter).call()
    size = len(adapter.requests[0].input_json().encode("utf-8"))
    for changes, expected in [
        ({"input_bytes": size}, "FINAL"),
        ({"input_bytes": size - 1}, "INPUT_SIZE"),
        ({"input_tokens": size}, "FINAL"),
        ({"input_tokens": size - 1}, "INPUT_TOKENS"),
        ({"total_tokens": size + 1024}, "FINAL"),
        ({"total_tokens": size + 1023}, "BUDGET"),
    ]:
        cfg = config(**changes)
        adapter = FakeAdapter(cfg.route)
        result = await ModelGateway(cfg, req, adapter).call()
        assert (result.error or result.kind) == expected
        assert len(adapter.requests) == (1 if expected == "FINAL" else 0)


async def test_output_bytes_exact_boundary_and_usage_overrun():
    raw = AdapterResponse(kind="OUTPUT", output_json='{"kind":"reply","text":"ok","reason":null}')
    size = len(raw.model_dump_json().encode("utf-8"))
    for maximum, expected in [(size, "FINAL"), (size - 1, "OUTPUT_SIZE")]:
        cfg = config(output_bytes=maximum)
        result = await ModelGateway(cfg, request(), FakeAdapter(cfg.route, (raw,))).call()
        assert (result.error or result.kind) == expected
    for usage in [Usage(input_tokens=100000), Usage(output_tokens=1025)]:
        cfg = config()
        response = AdapterResponse(**(raw.model_dump() | {"usage": usage}))
        result = await ModelGateway(cfg, request(), FakeAdapter(cfg.route, (response,))).call()
        assert result.error == "USAGE_LIMIT"


@pytest.mark.parametrize(
    "cost,error",
    [
        (Cost(status="CONFIRMED", amount=Decimal("0.11"), currency="RUB"), "BUDGET"),
        (Cost(status="ESTIMATE", amount=Decimal("0.11"), currency="RUB"), "BUDGET"),
        (Cost(status="CONFIRMED", amount=Decimal("0.01"), currency="USD"), "INVALID_OUTPUT"),
    ],
)
async def test_cost_mismatch_never_passes_as_success(cost, error):
    cfg = config()
    raw = AdapterResponse(
        kind="OUTPUT", output_json='{"kind":"reply","text":"ok","reason":null}', cost=cost
    )
    result = await ModelGateway(cfg, request(), FakeAdapter(cfg.route, (raw,))).call()
    assert result.error == error and result.cost == cost


async def test_unhandled_adapter_errors_do_not_leak_content_or_keys(caplog):
    sentinel = "synthetic-key-or-private-content"

    class Broken(FakeAdapter):
        async def complete(self, request):
            self.requests.append(request)
            raise RuntimeError(sentinel)

    cfg = config()
    adapter = Broken(cfg.route)
    outcome = await ModelGateway(
        cfg, request(messages=(Message(role="user", text=sentinel),)), adapter
    ).call()
    assert outcome.error == "ADAPTER_ERROR" and outcome.cost.amount is None
    assert sentinel not in repr(outcome) + outcome.model_dump_json() + caplog.text


def test_secrets_unknown_fields_and_unbounded_config_are_rejected():
    cfg = config()
    for extra in [{"api_key": "synthetic-secret"}, {"fallback": True}]:
        with pytest.raises(ValidationError):
            GatewayConfig(**(cfg.model_dump() | extra))
    for endpoint in ["https://user:synthetic-secret@one.invalid", "https://one.invalid?key=x"]:
        with pytest.raises(ValidationError):
            Route(**(cfg.route.model_dump() | {"endpoint": endpoint}))
    with pytest.raises(ValidationError):
        Route(**(cfg.route.model_dump() | {"eligibility": "APPROVED"}))
    for changes in [{"model_calls": 4}, {"read_executions": 5}, {"output_tokens": 8193}]:
        with pytest.raises(ValidationError):
            config(**changes)


async def test_schema_drift_is_rejected_at_gateway_construction(monkeypatch):
    monkeypatch.setattr("asm.ai.gateway.CONVERSATION_RESULT.json_schema", lambda: {})
    cfg = config()
    with pytest.raises(ValueError, match="schema drift"):
        ModelGateway(cfg, request(), FakeAdapter(cfg.route))


@pytest.mark.parametrize(
    "count,error", [(None, "CAPABILITY"), (True, "INVALID_INPUT"), (-1, "INVALID_INPUT")]
)
async def test_unconfirmed_or_invalid_local_token_count_fails_closed(count, error):
    class Counter(FakeAdapter):
        def count_input_tokens(self, request):
            return count

    cfg = config()
    adapter = Counter(cfg.route)
    result = await ModelGateway(cfg, request(), adapter).call()
    assert result.error == error and not adapter.requests
