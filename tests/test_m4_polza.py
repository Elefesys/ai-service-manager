"""Controlled HTTP evidence only. These catalog entries are NOT provider proof."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from asm.ai.contracts import (
    CONVERSATION_RESULT,
    GatewayConfig,
    GatewayRequest,
    Message,
    ReadTool,
    ToolResult,
)
from asm.ai.gateway import ModelGateway, ProviderFailure
from asm.ai.polza import (
    ENDPOINT,
    INPUT_TOKENS,
    MODELS,
    OVERHEAD_TOKENS,
    PolzaAdapter,
    RouteReview,
    bounded_http,
    encode,
    fingerprint,
)
from asm.ai.probe import FIXTURES, ReadArgs, ReadResult, configuration, load_cases
from pydantic import SecretStr

KEY = SecretStr("offline-fixture-secret-do-not-log")


def review(model=MODELS[0], **changes):
    entry = {
        "id": model,
        "architecture": {"input_modalities": ["text", "image"]},
        "providers": [
            {
                "name": "Official Fixture Provider",
                "is_unofficial": False,
                "pricing": {
                    "currency": "RUB",
                    "prompt_per_million": "10",
                    "completion_per_million": "40",
                },
                "capabilities": {
                    "tools": {"status": "supported"},
                    "json_schema_strict": {"status": "supported"},
                },
                "supported_parameters": [
                    "tools",
                    "tool_choice",
                    "response_format",
                    "max_completion_tokens",
                ],
                "context_length": 65536,
                "max_completion_tokens": 8192,
            }
        ],
    }
    fields = dict(
        model=model,
        provider_name="Official Fixture Provider",
        response_provider="official-fixture",
        catalog_entry=entry,
        catalog_sha256=fingerprint(entry),
        checked_at=datetime.now(UTC),
    )
    for key in (
        "route_evidence",
        "schema_tools_evidence",
        "token_bound_evidence",
        "billing_bound_evidence",
        "image_bound_evidence",
    ):
        fields[key] = "OFFLINE FIXTURE ONLY; not provider evidence"
    fields.update(changes)
    return RouteReview(**fields)


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay, self.reads = chunks, delay, 0

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            self.reads += 1
            yield chunk


def response(data=None, *, status=200, raw=None, headers=None):
    return httpx.Response(
        status, stream=Stream([raw if raw is not None else encode(data)]), headers=headers
    )


def payload(model=MODELS[0], *, tools=False):
    message = {
        "role": "assistant",
        "content": json.dumps({"kind": "reply", "text": "Улица Модельная, 12", "reason": None}),
    }
    if tools:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "read-1",
                    "type": "function",
                    "function": {"name": "read_current", "arguments": '{"key":"current"}'},
                }
            ],
        }
    return {
        "model": model,
        "provider": "official-fixture",
        "choices": [
            {"index": 0, "message": message, "finish_reason": "tool_calls" if tools else "stop"}
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 20, "cost_rub": 0.001},
    }


def gateway(adapter, *, tools=False, limits=None, deadline=None):
    case = next(
        c for c in load_cases(FIXTURES) if c.id == ("tool_current" if tools else "owner_fact")
    )
    cfg = configuration(adapter.review, case)
    if limits:
        cfg = GatewayConfig.model_validate(
            cfg.model_dump() | {"limits": cfg.limits.model_dump() | limits}
        )
    request = GatewayRequest(
        run_id="controlled_http",
        deadline=deadline or datetime.now(UTC) + timedelta(seconds=60),
        messages=(
            Message(role="context", text="Owner fact; not system policy"),
            Message(role="user", text="Вопрос"),
        ),
        tools=(
            ReadTool(
                name="read_current",
                revision="synthetic_v1",
                description="Synthetic read",
                arguments=ReadArgs,
                result=ReadResult,
            ),
        )
        if tools
        else (),
    )
    return ModelGateway(cfg, request, adapter)


async def test_real_gateway_native_schema_tools_round_trip():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == ENDPOINT and request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + KEY.get_secret_value()
        assert body["provider"]["only"] == ["Official Fixture Provider"]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["response_format"]["json_schema"] == {
            "name": "conversation_result_v1",
            "strict": True,
            "schema": CONVERSATION_RESULT.json_schema(),
        }
        assert body["messages"][1]["role"] == "user"
        assert body["tools"][0]["function"]["parameters"] == ReadArgs.model_json_schema()
        if len(calls) == 2:
            assert body["messages"][-1] == {
                "role": "tool",
                "tool_call_id": "read-1",
                "content": '{"fact":"Модельная, 12"}',
            }
        return response(payload(tools=len(calls) == 1))

    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(handler))
    gw = gateway(adapter, tools=True)
    first = await gw.call()
    assert first.kind == "TOOLS" and first.budget.reads_reserved == 1
    final = await gw.call(
        (ToolResult(call_id="read-1", name="read_current", result_json='{"fact":"Модельная, 12"}'),)
    )
    assert final.kind == "FINAL" and final.result.text == "Улица Модельная, 12"
    assert final.budget.calls_used == 2 and final.cost.status == "CONFIRMED"
    # Full actual wire (including continued tool results) counted before each call.
    assert final.budget.tokens_reserved == sum(
        len(encode(b)) + OVERHEAD_TOKENS + 512 for b in calls
    )
    assert len(calls) == 2 and (await gw.call()).error == "CLOSED"


@pytest.mark.parametrize(
    "status,error",
    [
        (301, "ADAPTER_ERROR"),
        (307, "ADAPTER_ERROR"),
        (400, "ADAPTER_ERROR"),
        (401, "ADAPTER_ERROR"),
        (402, "ADAPTER_ERROR"),
        (403, "ADAPTER_ERROR"),
        (429, "RATE_LIMIT"),
        (500, "UNAVAILABLE"),
        (503, "UNAVAILABLE"),
    ],
)
async def test_http_errors_never_retry_follow_redirect_or_read_error_body(status, error):
    seen = []
    stream = Stream([KEY.get_secret_value().encode()])

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            status, stream=stream, headers={"location": "https://other.invalid/steal"}
        )

    gw = gateway(PolzaAdapter(review(), KEY, transport=httpx.MockTransport(handler)))
    result = await gw.call()
    assert result.error == error and result.result is None and result.cost.status == "UNKNOWN"
    assert result.budget.cost_reserved > 0 and seen == [ENDPOINT] and stream.reads == 0
    assert KEY.get_secret_value() not in repr(result)


@pytest.mark.parametrize(
    "change,error",
    [
        ("route", "ADAPTER_ERROR"),
        ("model", "ADAPTER_ERROR"),
        ("missing_route", "ADAPTER_ERROR"),
        ("invalid_json", "INVALID_OUTPUT"),
        ("extra_field", "INVALID_OUTPUT"),
        ("duplicate_json", "INVALID_OUTPUT"),
        ("length", "TRUNCATED"),
        ("over_usage", "USAGE_LIMIT"),
        ("cost_limit", "BUDGET"),
        ("negative_usage", "ADAPTER_ERROR"),
        ("invalid_cost", "ADAPTER_ERROR"),
        ("mixed", "ADAPTER_ERROR"),
        ("secret", "ADAPTER_ERROR"),
    ],
)
async def test_response_boundaries_never_return_raw_success(change, error):
    data = payload()
    msg = data["choices"][0]["message"]
    if change == "route":
        data["provider"] = "other"
    if change == "model":
        data["model"] = MODELS[1]
    if change == "missing_route":
        del data["provider"]
    if change == "invalid_json":
        msg["content"] = "raw prose must not escape"
    if change == "extra_field":
        msg["content"] = '{"kind":"reply","text":"ok","reason":null,"extra":1}'
    if change == "duplicate_json":
        msg["content"] = '{"kind":"reply","kind":"handoff","text":"x","reason":null}'
    if change == "length":
        data["choices"][0]["finish_reason"] = "length"
    if change == "over_usage":
        data["usage"]["prompt_tokens"] = INPUT_TOKENS
    if change == "cost_limit":
        data["usage"]["cost_rub"] = 90
    if change == "negative_usage":
        data["usage"]["completion_tokens"] = -1
    if change == "invalid_cost":
        data["usage"]["cost_rub"] = "unparseable"
    if change == "mixed":
        msg["tool_calls"] = payload(tools=True)["choices"][0]["message"]["tool_calls"]
    if change == "secret":
        msg["content"] = KEY.get_secret_value()
    result = await gateway(
        PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda _: response(data)))
    ).call()
    assert result.kind == "ERROR" and result.error == error and result.result is None
    if change in (
        "invalid_json",
        "extra_field",
        "duplicate_json",
        "length",
        "over_usage",
        "cost_limit",
    ):
        assert result.cost.status == "CONFIRMED"


@pytest.mark.parametrize("change", ["refusal", "filter", "no_usage", "no_cost"])
async def test_refusal_and_missing_accounting_are_not_invented(change):
    data = payload()
    if change == "refusal":
        data["choices"][0]["message"]["refusal"] = "Private refusal content"
    if change == "filter":
        data["choices"][0]["finish_reason"] = "content_filter"
    if change == "no_usage":
        del data["usage"]
    if change == "no_cost":
        del data["usage"]["cost_rub"]
    result = await gateway(
        PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda _: response(data)))
    ).call()
    if change in ("refusal", "filter"):
        assert result.kind == "REFUSAL" and result.result is None
    else:
        assert result.cost.status == "UNKNOWN" and result.cost.amount is None
    if change == "no_usage":
        assert result.usage.input_tokens is None


@pytest.mark.parametrize(
    "scenario",
    [
        "oversize",
        "declared_oversize",
        "compressed",
        "short_body",
        "duplicate",
        "utf8",
        "timeout",
        "slow_body",
        "connect",
    ],
)
async def test_wire_and_transport_failures_are_bounded(scenario):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if scenario == "timeout":
            raise httpx.ReadTimeout("private details", request=request)
        if scenario == "connect":
            raise httpx.ConnectError("private details", request=request)
        if scenario == "slow_body":
            return httpx.Response(200, stream=Stream([b"x"] * 10, 0.01))
        raw = b"x" * 32769 if scenario == "oversize" else encode(payload())
        if scenario == "duplicate":
            raw = b'{"choices":[],"choices":[]}'
        if scenario == "utf8":
            raw = b"\xff"
        headers = {"content-length": "999999"} if scenario == "declared_oversize" else {}
        if scenario == "short_body":
            headers = {"content-length": str(len(raw) + 1)}
        if scenario == "compressed":
            headers = {"content-encoding": "gzip"}
        return response(raw=raw, headers=headers)

    gw = gateway(
        PolzaAdapter(review(), KEY, transport=httpx.MockTransport(handler)),
        limits={"duration_seconds": 0.025},
    )
    result = await gw.call()
    assert result.kind == "ERROR" and result.result is None and result.cost.status == "UNKNOWN"
    assert count == 1 and result.budget.cost_reserved > 0
    assert result.error == (
        "TIMEOUT"
        if scenario in ("timeout", "slow_body")
        else "UNAVAILABLE"
        if scenario == "connect"
        else "ADAPTER_ERROR"
    )


@pytest.mark.parametrize(
    "limits,error",
    [
        ({"model_calls": 0}, "BUDGET"),
        ({"cost_budget": Decimal(0)}, "BUDGET"),
        ({"input_tokens": 1}, "INPUT_TOKENS"),
        ({"input_bytes": 1}, "INPUT_SIZE"),
        ({"total_tokens": 1}, "BUDGET"),
    ],
)
async def test_exhaustion_is_before_http(limits, error):
    calls = []
    adapter = PolzaAdapter(
        review(), KEY, transport=httpx.MockTransport(lambda req: calls.append(req))
    )
    assert (await gateway(adapter, limits=limits).call()).error == error
    assert not calls


async def test_cancellation_closes_gateway_and_keeps_reservation():
    entered = asyncio.Event()

    async def handler(_):
        entered.set()
        await asyncio.Event().wait()

    gw = gateway(PolzaAdapter(review(), KEY, transport=httpx.MockTransport(handler)))
    task = asyncio.create_task(gw.call())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gw.budget.calls_used == 1 and gw.budget.cost_reserved > 0
    assert (await gw.call()).error == "CLOSED"


@pytest.mark.parametrize(
    "change",
    [
        "unofficial",
        "missing_official",
        "capability",
        "parameter",
        "parameter_shape",
        "modality_shape",
        "currency",
        "fee",
        "tier",
        "context",
        "missing_model",
        "hash",
    ],
)
def test_unknown_review_is_not_admitted(change):
    r = review()
    entry = copy.deepcopy(r.catalog_entry)
    p = entry["providers"][0]
    if change == "unofficial":
        p["is_unofficial"] = True
    if change == "missing_official":
        del p["is_unofficial"]
    if change == "capability":
        p["capabilities"]["json_schema_strict"]["status"] = "unknown"
    if change == "parameter":
        p["supported_parameters"].remove("max_completion_tokens")
    if change == "parameter_shape":
        p["supported_parameters"] = dict.fromkeys(p["supported_parameters"], False)
    if change == "modality_shape":
        entry["architecture"]["input_modalities"] = {"text": False, "image": False}
    if change == "currency":
        p["pricing"]["currency"] = "USD"
    if change == "fee":
        p["pricing"]["request_per_thousand"] = {}
    if change == "tier":
        p["pricing"]["tiers"] = [{"price": "1"}]
    if change == "context":
        p["context_length"] = None
    if change == "missing_model":
        entry["id"] = "another/model"
    changed = review(
        catalog_entry=entry, catalog_sha256="0" * 64 if change == "hash" else fingerprint(entry)
    )
    with pytest.raises(ValueError):
        changed.reservation()


async def test_unapproved_endpoint_rejected_without_transport():
    calls = []
    with pytest.raises(ProviderFailure):
        await bounded_http(
            KEY,
            "https://other.invalid",
            body=b"{}",
            seconds=1,
            maximum=20,
            transport=httpx.MockTransport(lambda r: calls.append(r)),
        )
    assert not calls


async def test_observed_route_is_reported_as_mismatch_not_claimed_as_expected():
    data = payload()
    data["provider"] = "unexpected-upstream"
    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda _: response(data)))
    result = await gateway(adapter).call()
    assert result.result is None and result.error == "ADAPTER_ERROR"
    assert adapter.observation == {
        "observed_provider": "unexpected-upstream",
        "observed_model": MODELS[0],
        "error_detail": "RETURNED_ROUTE_MISMATCH",
    }


async def test_escaped_secret_in_returned_route_cannot_enter_report():
    data = payload()
    data["provider"] = KEY.get_secret_value()
    raw = encode(data).replace(b"-", b"\\u002d")
    adapter = PolzaAdapter(
        review(), KEY, transport=httpx.MockTransport(lambda _: response(raw=raw))
    )
    result = await gateway(adapter).call()
    assert result.error == "ADAPTER_ERROR" and result.result is None
    assert KEY.get_secret_value() not in str(adapter.observation)
