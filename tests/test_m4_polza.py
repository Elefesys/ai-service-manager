"""Controlled HTTP evidence only. These catalog entries are NOT provider proof."""

import asyncio
import copy
import io
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
    CONVERSATION_WIRE_REVISION,
    ENDPOINT,
    EXPERIMENT_PROVIDERS,
    HISTORY,
    HISTORY_LIST,
    INPUT_TOKENS,
    MODELS,
    OVERHEAD_TOKENS,
    SIGNATURE_BYTES,
    PolzaAdapter,
    RouteReview,
    SyntheticRoute,
    bounded_http,
    conversation_wire_schema,
    encode,
    fingerprint,
)
from asm.ai.probe import FIXTURES, Ledger, ReadArgs, ReadResult, configuration, load_cases, run_case
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
                    "input_image": {"status": "supported", "verified_at": None},
                },
                "supported_parameters": [
                    "tools",
                    "tool_choice",
                    "response_format",
                    "max_tokens" if model == MODELS[1] else "max_completion_tokens",
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
        output_cap_parameter="max_tokens" if model == MODELS[1] else "max_completion_tokens",
        output_cap_includes_reasoning=True,
        output_cap_evidence="OFFLINE FIXTURE ONLY; not provider evidence",
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


def experiment_entry(model=MODELS[0]):
    """CONTROLLED catalog declaration, not a fetched tariff or verified RouteReview."""
    entry = review(model).catalog_entry
    provider = entry["providers"][0]
    provider["name"] = EXPERIMENT_PROVIDERS[MODELS.index(model)]
    provider["supported_parameters"] = [
        "tools",
        "tool_choice",
        "response_format",
        "max_tokens",
        "reasoning",
        "reasoning_effort",
    ]
    provider["capabilities"].update(
        {
            "reasoning_toggle": {"status": "supported"},
            "reasoning_effort": {"status": "supported", "values": ["none"]},
        }
    )
    provider["reasoning"] = {
        "mandatory": False,
        "default_enabled": True,
        "supported_efforts": ["none"],
    }
    provider["pricing"].update(
        {
            "image_input_per_million": "2",
            "input_cache_read_per_million": "1",
            "input_cache_write_per_million": "1",
            "input_audio_cache_per_million": "3",
            "internal_reasoning_per_million": "5",
            "audio_per_million": "999",
            "web_search_per_thousand": "999",
        }
    )
    return entry


def experiment_route(model=MODELS[0]):
    return SyntheticRoute.from_catalog(experiment_entry(model), datetime.now(UTC))


def experiment_history(data, family=None):
    listing, detail = history_payloads(data)
    family = (
        family
        or ("OpenAI", "controlled-google-family", "controlled-wafer-family")[
            MODELS.index(data["model"])
        ]
    )
    listing["items"][0]["provider"] = detail["finalEndpointSlug"] = family
    detail["apiType"] = "completions"
    return listing, detail


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
        "content": json.dumps(
            {"result": {"kind": "reply", "text": "Улица Модельная, 12", "reason": None}}
        ),
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
    if tools and model == MODELS[1]:
        message["tool_calls"][0]["extra_content"] = {
            "google": {"thought_signature": "CONTROLLED_OPAQUE_SIGNATURE"}
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


def history_review(model=MODELS[0]):
    return review(
        model,
        history={
            "provider": "official-fixture",
            "evidence": "CONTROLLED FIXTURE ONLY; no actual family mapping is asserted",
        },
    )


def history_payloads(data):
    """Minimal documented list/detail shape; synthetic metadata must not reach reports."""
    item = {
        "id": data["id"],
        "model": data["model"].split("/", 1)[1],
        "requestType": "chat",
        "provider": "official-fixture",
        "status": "completed",
        "cost": str(data["usage"]["cost_rub"]),
        "usage": copy.deepcopy(data["usage"]),
        "apiKeyShort": "PRIVATE_ACCOUNT_METADATA",
    }
    detail = {
        "id": data["id"],
        "requestType": "chat",
        "apiType": "chat_completions",
        "responseMode": "sync",
        "status": "completed",
        "isCancelled": False,
        "finishReason": data["choices"][0]["finish_reason"],
        "attemptsCount": 1,
        "finalEndpointSlug": "official-fixture",
        "clientCost": str(data["usage"]["cost_rub"]),
        "usage": copy.deepcopy(data["usage"]),
        "organizationId": "PRIVATE_ACCOUNT_METADATA",
    }
    return {"items": [item]}, detail


@pytest.mark.parametrize("model", MODELS)
async def test_real_gateway_native_schema_tools_round_trip(model):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == ENDPOINT and request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + KEY.get_secret_value()
        assert body["provider"]["only"] == ["Official Fixture Provider"]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["model"] == model
        assert body["response_format"]["json_schema"] == {
            "name": CONVERSATION_WIRE_REVISION,
            "strict": True,
            "schema": conversation_wire_schema(CONVERSATION_RESULT.json_schema()),
        }
        cap = "max_tokens" if model == MODELS[1] else "max_completion_tokens"
        assert body[cap] == 512
        assert set(body) & {"max_tokens", "max_completion_tokens"} == {cap}
        assert body["messages"][1]["role"] == "user"
        assert body["tools"][0]["function"]["parameters"] == ReadArgs.model_json_schema()
        if len(calls) == 2:
            assert body["messages"][-1] == {
                "role": "tool",
                "tool_call_id": "read-1",
                "content": '{"fact":"Модельная, 12"}',
            }
        return response(payload(model, tools=len(calls) == 1))

    adapter = PolzaAdapter(review(model), KEY, transport=httpx.MockTransport(handler))
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
        # Only slow_body tests the elapsed deadline. Other cases must reach
        # the transport failure even when local schema preparation takes >25ms.
        limits={"duration_seconds": 0.025 if scenario == "slow_body" else 1.0},
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


@pytest.mark.parametrize("model", MODELS)
async def test_observed_route_is_reported_as_mismatch_not_claimed_as_expected(model):
    data = payload(model)
    data["provider"] = "unexpected-upstream"
    adapter = PolzaAdapter(
        review(model), KEY, transport=httpx.MockTransport(lambda _: response(data))
    )
    result = await gateway(adapter).call()
    assert result.result is None and result.error == "ADAPTER_ERROR"
    assert (
        adapter.observation.items()
        >= {
            "observed_provider": "unexpected-upstream",
            "observed_model": model,
            "error_detail": "RETURNED_ROUTE_MISMATCH",
            "observed_body_provider": "unexpected-upstream",
            "history_family": None,
            "history_gets": 0,
            "route_evidence_source": "NONE",
        }.items()
    )


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


def test_duplicate_name_repair_exposes_alias_and_conditional_fee_blockers():
    original = review()
    entry = copy.deepcopy(original.catalog_entry)
    provider = entry["providers"][0]
    provider["supported_parameters"].remove("max_completion_tokens")
    provider["supported_parameters"].append("max_tokens")
    provider["pricing"]["web_search_per_thousand"] = "1000"
    entry["providers"].append(copy.deepcopy(provider))
    # Different rows with the same wire selector may not be merged or first-picked.
    entry["providers"][1]["pricing"]["prompt_per_million"] = "1"
    with pytest.raises(ValueError, match="AMBIGUOUS_PROVIDER_NAME"):
        review(catalog_entry=entry, catalog_sha256=fingerprint(entry)).reservation()
    entry["providers"].pop()
    with pytest.raises(ValueError, match="OUTPUT_CAP_PARAMETER_UNSUPPORTED"):
        review(catalog_entry=entry, catalog_sha256=fingerprint(entry)).reservation()
    with pytest.raises(ValueError, match="CONDITIONAL_FEE_REVIEW_REQUIRED"):
        review(
            catalog_entry=entry,
            catalog_sha256=fingerprint(entry),
            output_cap_parameter="max_tokens",
        ).reservation()
    fixed = review(
        catalog_entry=entry,
        catalog_sha256=fingerprint(entry),
        output_cap_parameter="max_tokens",
        inactive_fee_evidence={
            "web_search_per_thousand": "OFFLINE FIXTURE ONLY; no actual route proof"
        },
    )
    assert fixed.reservation() == original.reservation()


@pytest.mark.parametrize(
    "fee", ["audio_per_million", "input_audio_cache_per_million", "web_search_per_thousand"]
)
async def test_conditional_fee_requires_explicit_review_and_inactive_payload(fee):
    base = review(MODELS[1])
    entry = copy.deepcopy(base.catalog_entry)
    entry["providers"][0]["pricing"][fee] = "1000"
    with pytest.raises(ValueError, match="CONDITIONAL_FEE_REVIEW_REQUIRED"):
        review(MODELS[1], catalog_entry=entry, catalog_sha256=fingerprint(entry)).rates()
    accepted = review(
        MODELS[1],
        catalog_entry=entry,
        catalog_sha256=fingerprint(entry),
        inactive_fee_evidence={fee: "OFFLINE FIXTURE ONLY; this is not contractual proof"},
    )
    assert accepted.rates() == base.rates()
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return response(payload(MODELS[1]))

    result = await gateway(
        PolzaAdapter(accepted, KEY, transport=httpx.MockTransport(handler))
    ).call()
    assert result.kind == "FINAL" and len(sent) == 1
    assert sent[0]["max_tokens"] == 512 and "max_completion_tokens" not in sent[0]
    assert accepted.metadata()["excluded_fee_components"] == [fee]


@pytest.mark.parametrize("value", [None, "0", "1", {"units": "tokens", "amount": "1"}])
def test_unknown_fee_is_never_ignored_even_if_null_or_zero(value):
    entry = copy.deepcopy(review().catalog_entry)
    entry["providers"][0]["pricing"]["unreviewed_fee"] = value
    with pytest.raises(ValueError, match="TARIFF_UNKNOWN"):
        review(catalog_entry=entry, catalog_sha256=fingerprint(entry)).rates()
    with pytest.raises(ValueError):
        review(
            inactive_fee_evidence={"unreviewed_fee": "OFFLINE ONLY; arbitrary waiver is forbidden"}
        )


@pytest.mark.parametrize("value", ["NaN", "-1", {}, True])
def test_excluded_fee_still_requires_valid_numeric_rate(value):
    entry = copy.deepcopy(review().catalog_entry)
    entry["providers"][0]["pricing"]["audio_per_million"] = value
    with pytest.raises(ValueError, match="TARIFF_UNKNOWN"):
        review(
            catalog_entry=entry,
            catalog_sha256=fingerprint(entry),
            inactive_fee_evidence={"audio_per_million": "OFFLINE FIXTURE ONLY; not provider proof"},
        ).rates()


def test_cache_and_reasoning_rates_remain_additive_and_cannot_be_waived():
    entry = copy.deepcopy(review().catalog_entry)
    entry["providers"][0]["pricing"].update(
        {
            "image_input_per_million": "10",
            "input_cache_read_per_million": "2",
            "input_cache_write_per_million": "3",
            "internal_reasoning_per_million": "40",
            "per_request": "0.01",
            "request_per_thousand": "20",
        }
    )
    r = review(catalog_entry=entry, catalog_sha256=fingerprint(entry))
    assert r.rates() == (Decimal(25), Decimal(80), Decimal("0.03"))
    assert r.reservation() == (32768 * Decimal(25) + 512 * Decimal(80)) / 1000000 + Decimal("0.03")
    with pytest.raises(ValueError):
        review(
            inactive_fee_evidence={
                "input_cache_read_per_million": "OFFLINE ONLY; do not waive cache rates"
            }
        )


@pytest.mark.parametrize("capability", ["tools", "json_schema_strict", "input_image"])
@pytest.mark.parametrize("status", ["unknown", "rejected"])
def test_selected_provider_capabilities_cannot_borrow_from_another_route(capability, status):
    entry = copy.deepcopy(review().catalog_entry)
    other = copy.deepcopy(entry["providers"][0])
    other["name"] = "Other supported provider"
    entry["providers"].append(other)
    entry["providers"][0]["capabilities"][capability] = {"status": status, "verified_at": None}
    with pytest.raises(ValueError):
        review(catalog_entry=entry, catalog_sha256=fingerprint(entry)).route()
    # A manually selected, uniquely named different route is a separate review.
    assert (
        review(
            catalog_entry=entry,
            catalog_sha256=fingerprint(entry),
            provider_name=other["name"],
        )
        .route()
        .model
        == MODELS[0]
    )


def test_null_catalog_verification_never_becomes_live_or_account_proof():
    entry = copy.deepcopy(review().catalog_entry)
    for cap in entry["providers"][0]["capabilities"].values():
        cap["verified_at"] = None
    r = review(catalog_entry=entry, catalog_sha256=fingerprint(entry))
    assert all(
        v["evidence"] == "CATALOG_DECLARATION_ONLY" for v in r.metadata()["capabilities"].values()
    )
    entry["providers"][0]["capabilities"]["tools"]["verified_at"] = "2026-10-23T11:22:10.757Z"
    r = review(catalog_entry=entry, catalog_sha256=fingerprint(entry))
    meta = r.metadata()
    assert meta["capabilities"]["tools"]["evidence"] == "CATALOG_REPORTED_VERIFICATION"
    assert meta["live_payload_verification"] == "NOT_ESTABLISHED_BY_CATALOG"
    assert meta["account_authorization"] == "NOT_ESTABLISHED_BY_CATALOG"


@pytest.mark.parametrize(
    "inner",
    [
        {"kind": "reply", "text": "Известный факт", "reason": None},
        {"kind": "handoff", "text": None, "reason": "Нужен владелец"},
        {"kind": "no_reply", "text": None, "reason": "Нет вопроса"},
    ],
)
async def test_wire_envelope_round_trips_each_canonical_result(inner):
    data = payload()
    data["choices"][0]["message"]["content"] = json.dumps({"result": inner})
    result = await gateway(
        PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda _: response(data)))
    ).call()
    assert result.kind == "FINAL" and result.result.model_dump() == inner
    assert result.cost.status == "CONFIRMED"


def test_wire_wrapper_preserves_union_constraints_definitions_and_local_refs():
    canonical = CONVERSATION_RESULT.json_schema()
    untouched = copy.deepcopy(canonical)
    wrapped = conversation_wire_schema(canonical)
    assert canonical == untouched
    assert wrapped["type"] == "object" and wrapped["required"] == ["result"]
    assert wrapped["additionalProperties"] is False
    assert wrapped["properties"]["result"] == {k: v for k, v in canonical.items() if k != "$defs"}
    assert wrapped["$defs"] == canonical["$defs"]
    for variant in wrapped["properties"]["result"]["anyOf"]:
        target = wrapped
        for part in variant["$ref"][2:].split("/"):
            target = target[part]
        assert target == canonical["$defs"][variant["$ref"].rsplit("/", 1)[1]]
        assert target["additionalProperties"] is False
    canonical["$defs"]["Reply"]["properties"]["text"].pop("maxLength")
    with pytest.raises(ValueError, match="WIRE_SCHEMA_UNSUPPORTED"):
        conversation_wire_schema(canonical)


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        '{"kind":"reply","text":"bare result","reason":null}',
        '{"result":{"kind":"reply","text":"valid","reason":null},"extra":1}',
        '{"result":null,"result":{"kind":"reply","text":"duplicate","reason":null}}',
        '{"result":null}',
        '{"result":{"kind":"unknown","text":"x","reason":null}}',
        '{"result":{"kind":"reply","text":"","reason":null}}',
        '{"result":{"kind":"reply","text":"x","reason":null,"extra":1}}',
    ],
)
async def test_invalid_envelope_or_inner_result_preserves_charge_but_never_final(raw):
    data = payload()
    data["choices"][0]["message"]["content"] = raw
    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda _: response(data)))
    result = await gateway(adapter).call()
    assert result.kind == "ERROR" and result.error == "INVALID_OUTPUT" and result.result is None
    assert result.cost.status == "CONFIRMED" and result.cost.amount == Decimal("0.001")
    assert result.budget.calls_used == 1 and result.budget.cost_reserved > 0


@pytest.mark.parametrize(
    "change",
    [
        "audio",
        "audio_output",
        "search",
        "plugin",
        "server_tool",
        "both_caps",
        "over_cap",
        "fallback",
    ],
)
async def test_conditional_fees_cannot_be_activated_via_raw_image_payload(change):
    sent = []
    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda r: sent.append(r)))
    body = adapter.base_body(
        [{"role": "user", "content": "synthetic text"}],
        {"type": "object"},
        512,
        schema_name="synthetic_shapes_v1",
    )
    if change == "audio":
        body["messages"][0]["content"] = [
            {"type": "input_audio", "input_audio": {"data": "eA==", "format": "wav"}}
        ]
    elif change == "audio_output":
        body["modalities"] = ["text", "audio"]
    elif change == "search":
        body["web_search_options"] = {}
    elif change == "plugin":
        body["plugins"] = [{"id": "web"}]
    elif change == "server_tool":
        body["tools"] = [{"type": "web_search"}]
    elif change == "both_caps":
        body["max_tokens"] = 512
    elif change == "over_cap":
        body["max_completion_tokens"] = 513
    else:
        body["provider"]["allow_fallbacks"] = True
    with pytest.raises(ProviderFailure):
        await adapter.image_probe(encode(body), 1)
    assert not sent and adapter.observation["error_detail"] == "PAYLOAD_OUTSIDE_REVIEWED_SCOPE"


@pytest.mark.parametrize(
    "change,detail",
    [
        ("reasoning", "REASONING_OUTSIDE_OUTPUT_BOUND"),
        ("audio", "UNREQUESTED_AUDIO_USAGE"),
        ("search", "UNREQUESTED_SERVER_TOOL_USAGE"),
    ],
)
async def test_observed_usage_cannot_escape_reviewed_billing_scope(change, detail):
    data = payload()
    if change == "reasoning":
        data["usage"]["completion_tokens_details"] = {"reasoning_tokens": 513}
    elif change == "audio":
        data["usage"]["prompt_tokens_details"] = {"audio_tokens": 1}
    else:
        data["usage"]["server_tool_use"] = {"web_search_requests": 1}
    seen = []

    def handler(request):
        seen.append(request.method)
        return response(data)

    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(handler))
    result = await gateway(adapter).call()
    assert result.kind == "ERROR" and result.result is None and seen == ["POST"]
    assert result.cost.status == "UNKNOWN" and result.budget.cost_reserved > 0
    assert adapter.observation["error_detail"] == detail


@pytest.mark.parametrize("limit", [511, "512", None, True])
def test_max_tokens_alias_does_not_bypass_numeric_catalog_output_limit(limit):
    entry = copy.deepcopy(review(MODELS[1]).catalog_entry)
    entry["providers"][0]["max_completion_tokens"] = limit
    entry["providers"][0]["reasoning"] = {"mandatory": True}
    with pytest.raises(ValueError, match="OUTPUT_LIMIT_UNKNOWN"):
        review(MODELS[1], catalog_entry=entry, catalog_sha256=fingerprint(entry)).reservation()


async def test_reasoning_usage_within_confirmed_output_is_not_added_twice():
    data = payload(MODELS[1])
    data["usage"]["completion_tokens_details"] = {"reasoning_tokens": 15}
    data["usage"]["server_tool_use"] = {"web_search_requests": 0}
    adapter = PolzaAdapter(
        review(MODELS[1]), KEY, transport=httpx.MockTransport(lambda _: response(data))
    )
    result = await gateway(adapter).call()
    assert result.kind == "FINAL" and result.usage.output_tokens == 20
    assert result.cost.amount == Decimal("0.001")


@pytest.mark.parametrize("api_type", ["chat_completions", "completions"])
async def test_absent_body_provider_requires_history_before_read_and_final(api_type):
    data = [payload(tools=True), payload()]
    generation_ids = ("gen_2227091293761835009", "gen_2227091341204393985")
    for i, (entry, prompt, completion, reasoning, cost) in enumerate(
        zip(data, (560, 611), (18, 56), (0, 12), ("0.00379969", "0.00515641"), strict=True)
    ):
        entry.pop("provider")
        entry["id"] = generation_ids[i]
        entry["usage"].update(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cost_rub=cost,
            completion_tokens_details={"reasoning_tokens": reasoning},
        )
    seen, current = [], []

    def handler(request):
        seen.append(request.method)
        if request.method == "POST":
            if current:
                assert seen == ["POST", "GET", "GET", "POST"]
                assert json.loads(request.content)["messages"][-1]["role"] == "tool"
            current.append(data[len(current)])
            return response(current[-1])
        listing, detail = history_payloads(current[-1])
        detail["apiType"] = api_type
        return response(listing if str(request.url) == HISTORY_LIST else detail)

    adapter = PolzaAdapter(history_review(), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(1), 2), 0)
    assert not row["failures"] and row["reads"] == 1 and row["final"]["kind"] == "reply"
    assert seen == ["POST", "GET", "GET", "POST", "GET", "GET"]
    for call in row["calls"]:
        assert call["observed_body_provider"] is None
        assert call["history_family"] == "official-fixture"
        assert call["requested_provider"] == "Official Fixture Provider"
        assert call["route_evidence_source"] == "HISTORY_LIST_DETAIL"
        assert call["route_variant"] == "NOT_OBSERVED"
    assert "PRIVATE_ACCOUNT_METADATA" not in json.dumps(row)


@pytest.mark.parametrize(
    "stage,field,value",
    [
        ("list", "id", "gen_999"),
        ("detail", "id", "gen_999"),
        ("list", "model", "different-model"),
        ("detail", "model", "different-model"),
        ("list", "provider", "other"),
        ("detail", "finalEndpointSlug", "other"),
        ("list", "cost", "0.002"),
        ("detail", "clientCost", "0.002"),
        ("list", "usage", {"prompt_tokens": 30, "completion_tokens": 21}),
        ("detail", "usage", {"prompt_tokens": 31, "completion_tokens": 20}),
        ("detail", "finishReason", "stop"),
        ("detail", "attemptsCount", 2),
        ("detail", "attemptsCount", True),
        ("list", "status", "pending"),
        ("detail", "status", "failed"),
        ("list", "cost", None),
        ("detail", "usage", None),
        ("detail", "isCancelled", True),
        ("detail", "responseMode", "async"),
        ("detail", "apiType", "responses"),
        ("detail", "apiType", "media"),
        ("detail", "apiType", None),
        ("detail", "apiType", ""),
        ("detail", "requestType", "audio"),
        ("detail", "serverTools", {"steps": 2}),
    ],
)
async def test_history_mismatch_stops_before_read_or_next_post(stage, field, value):
    data = payload(tools=True)
    data.pop("provider")
    data["id"] = "gen_123"
    listing, detail = history_payloads(data)
    (listing["items"][0] if stage == "list" else detail)[field] = value
    seen = []

    def handler(request):
        seen.append(request.method)
        return response(
            data
            if request.method == "POST"
            else listing
            if str(request.url) == HISTORY_LIST
            else detail
        )

    adapter = PolzaAdapter(history_review(), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    ledger = Ledger(io.StringIO(), Decimal(1), 2)
    row = await run_case(adapter, case, ledger, 0)
    assert row["failures"] and row["reads"] == 0 and row["final"] is None
    assert seen == ["POST", "GET"] + (["GET"] if stage == "detail" else [])
    assert adapter.observation["error_detail"] == "HISTORY_VERIFICATION_FAILED"
    assert ledger.calls == 1 and ledger.reserved > 0
    assert row["calls"][0]["cost"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("provider", ["wrong", None, "", {}, 123])
async def test_present_wrong_or_malformed_provider_never_uses_history(provider):
    data = payload(tools=True)
    data.update(provider=provider, id="gen_123")
    seen = []
    adapter = PolzaAdapter(
        history_review(),
        KEY,
        transport=httpx.MockTransport(lambda r: (seen.append(r.method), response(data))[1]),
    )
    result = await gateway(adapter, tools=True).call()
    assert result.error == "ADAPTER_ERROR" and seen == ["POST"]
    assert adapter.observation["error_detail"] == "RETURNED_ROUTE_MISMATCH"


@pytest.mark.parametrize(
    "identifier", [None, "", "https://other.invalid/gen_1", "gen_1/../../key", "gen_x", 1]
)
async def test_missing_or_invalid_generation_id_stops_without_history(identifier):
    data = payload(tools=True)
    data.pop("provider")
    data["id"] = identifier
    seen = []
    adapter = PolzaAdapter(
        history_review(),
        KEY,
        transport=httpx.MockTransport(lambda r: (seen.append(r.method), response(data))[1]),
    )
    result = await gateway(adapter, tools=True).call()
    assert result.error == "ADAPTER_ERROR" and seen == ["POST"]
    assert adapter.observation["error_detail"] == "GENERATION_ID_INVALID"


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "duplicate",
        "items_limit",
        "bytes",
        "encoding",
        "redirect",
        "timeout",
        "case_deadline",
    ],
)
async def test_history_is_bounded_and_never_polled_or_retried(failure, monkeypatch):
    data = payload(tools=True)
    data.pop("provider")
    data["id"] = "gen_123"
    listing, detail = history_payloads(data)
    if failure == "empty":
        listing["items"] = []
    elif failure in ("duplicate", "items_limit"):
        listing["items"] *= 2 if failure == "duplicate" else 6
    seen = []

    def handler(request):
        seen.append(request.method)
        if request.method == "POST":
            return response(data)
        if failure == "bytes":
            return response(raw=b"x" * 65537)
        if failure == "encoding":
            return response(listing, headers={"content-encoding": "gzip"})
        if failure == "redirect":
            return response(status=302, headers={"location": "https://other.invalid/"})
        if failure in ("timeout", "case_deadline"):
            return httpx.Response(200, stream=Stream([encode(listing)], delay=1))
        return response(listing)

    if failure == "timeout":
        monkeypatch.setattr("asm.ai.polza.HISTORY_SECONDS", 0.01)
    adapter = PolzaAdapter(history_review(), KEY, transport=httpx.MockTransport(handler))
    result = await gateway(
        adapter,
        tools=True,
        limits={"duration_seconds": 0.5} if failure == "case_deadline" else None,
    ).call()
    assert result.kind == "ERROR" and seen == ["POST", "GET"]
    assert result.budget.calls_used == 1 and result.budget.cost_reserved > 0
    assert adapter.observation["history_gets"] == 1


@pytest.mark.parametrize(
    "url,body,seconds,maximum",
    [
        (HISTORY + "/gen_1/children", None, 1, 65536),
        (HISTORY.replace("polza.ai", "polzaXai") + "/gen_1", None, 1, 65536),
        (HISTORY + "/gen_1?url=https://other.invalid", None, 1, 65536),
        (HISTORY_LIST, b"{}", 1, 65536),
        (HISTORY_LIST, None, 16, 65536),
        (HISTORY_LIST, None, 1, 65537),
    ],
)
async def test_history_transport_allowlist_rejects_other_paths_methods_and_limits(
    url, body, seconds, maximum
):
    with pytest.raises(ProviderFailure):
        await bounded_http(
            KEY,
            url,
            body=body,
            seconds=seconds,
            maximum=maximum,
            transport=httpx.MockTransport(lambda _: pytest.fail("unexpected HTTP")),
        )


@pytest.mark.parametrize(
    "bad", ["missing", "wrong_path", "extra", "null", "empty", "number", "oversized", "control"]
)
async def test_gemini_invalid_signature_stops_before_read_and_continuation(bad):
    posts = []
    data = payload(MODELS[1], tools=True)
    call = data["choices"][0]["message"]["tool_calls"][0]
    if bad == "missing":
        call.pop("extra_content")
    elif bad == "wrong_path":
        call["extra_content"] = {"thought_signature": "PRIVATE_BAD_SIGNATURE"}
    elif bad == "extra":
        call["extra_content"]["unexpected"] = "PRIVATE_BAD_SIGNATURE"
    else:
        call["extra_content"]["google"]["thought_signature"] = {
            "null": None,
            "empty": "",
            "number": 123,
            "oversized": "S" * (SIGNATURE_BYTES + 1),
            "control": "PRIVATE\nSIGNATURE",
        }[bad]

    def handler(request):
        posts.append(request)
        return response(data)

    adapter = PolzaAdapter(review(MODELS[1]), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    assert len(posts) == 1 and row["reads"] == 0 and row["final"] is None
    expected = {
        "missing": "SIGNATURE_EXTRA_MISSING",
        "wrong_path": "SIGNATURE_GOOGLE_MISSING",
        "extra": "SIGNATURE_EXTRA_KEYS",
        "null": "SIGNATURE_NULL",
        "empty": "SIGNATURE_EMPTY",
        "number": "SIGNATURE_TYPE",
        "oversized": "SIGNATURE_OVERSIZE",
        "control": "SIGNATURE_CONTROL",
    }[bad]
    assert row["calls"][0]["error_detail"] == expected
    diagnostic = row["calls"][0]["signature_diagnostic"]
    assert diagnostic["code"] == expected
    assert diagnostic["byte_limit"] == SIGNATURE_BYTES
    assert (
        diagnostic["utf8_bytes_bounded"] is None
        or diagnostic["utf8_bytes_bounded"] <= SIGNATURE_BYTES + 1
    )
    assert row["calls"][0]["body_metering"]["reported_cost_rub"] == "0.001"
    assert row["calls"][0]["body_metering"]["verification"] == "FIELD_VALIDATED_ONLY"
    assert row["calls"][0]["cost"]["status"] == "UNKNOWN"
    assert "PRIVATE" not in json.dumps(row)
    assert adapter._continuation is None and adapter._run_key is None


@pytest.mark.parametrize("change", ["call_id", "arguments", "run", "route", "size", "reflect"])
async def test_gemini_continuation_is_bound_and_bounded(change):
    posts = []
    captured = []

    def handler(request):
        posts.append(json.loads(request.content))
        data = payload(MODELS[1], tools=len(posts) == 1)
        if change == "reflect" and len(posts) == 2:
            data["choices"][0]["message"]["content"] = "CONTROLLED_OPAQUE_SIGNATURE"
        return response(data)

    adapter = PolzaAdapter(review(MODELS[1]), KEY, transport=httpx.MockTransport(handler))
    original = adapter.wire

    def capture(request):
        captured.append(request)
        return original(request)

    adapter.wire = capture
    gw = gateway(adapter, tools=True)
    first = await gw.call()
    assert first.kind == "TOOLS"
    result = ToolResult(call_id="read-1", name="read_current", result_json='{"fact":"current"}')
    if change == "reflect":
        second = await gw.call((result,))
        assert second.kind == "ERROR" and len(posts) == 2
        assert adapter.observation["error_detail"] == "SIGNATURE_IN_RESPONSE"
        assert adapter._continuation is None
        return
    if change == "run":
        # Another run with the same run_id but its own deadline must clear old state.
        other = gateway(adapter, tools=True)
        await other.call()
    elif change == "route":
        adapter._run_key = ("controlled_http", "different-route", "different-route")
    elif change == "size":
        # Exercise the unchanged wire-byte limit after a valid response's metadata.
        adapter._continuation = (first.tool_calls[0], "S" * SIGNATURE_BYTES)
        # A large but valid synthetic READ result plus metadata cannot fit the wire.
        result = ToolResult(
            call_id="read-1", name="read_current", result_json='{"fact":"' + "я" * 190 + '"}'
        )
        original_body = adapter.base_body

        def padded(*args, **kwargs):
            body = original_body(*args, **kwargs)
            body["messages"][0]["content"] += "я" * 8000
            return body

        adapter.base_body = padded
    else:
        changed = first.tool_calls[0].model_copy(
            update={"call_id": "wrong-id"}
            if change == "call_id"
            else {"arguments_json": '{"key":"other"}'}
        )
        adapter._continuation = (changed, "CONTROLLED_OPAQUE_SIGNATURE")
    before = len(posts)
    second = await gw.call((result,))
    assert second.kind == "ERROR" and len(posts) == before
    # No field in the neutral request/response DTO carries vendor metadata.
    assert "thought_signature" not in first.model_dump_json()
    assert all("thought_signature" not in r.input_json() for r in captured)


@pytest.mark.parametrize("kind", ["reasoning_content", "reasoning", "reasoning_details", "usage"])
async def test_deepseek_non_thinking_response_required_before_read(kind):
    posts = []
    data = payload(MODELS[2], tools=True)
    data["id"] = "gen_901"
    if kind == "usage":
        data["usage"]["completion_tokens_details"] = {"reasoning_tokens": 1}
    else:
        data["choices"][0]["message"][kind] = "PRIVATE_REASONING_MUST_NOT_SURVIVE"

    def handler(request):
        assert request.method == "POST"
        wire = json.loads(request.content)
        assert wire["reasoning"] == {"effort": "none", "enabled": False}
        posts.append(wire)
        return response(data)

    adapter = PolzaAdapter(experiment_route(MODELS[2]), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    assert len(posts) == 1 and row["reads"] == 0 and row["final"] is None
    assert row["calls"][0]["error_detail"] == "NON_THINKING_NOT_OBSERVED"
    assert "PRIVATE_REASONING" not in json.dumps(row)


@pytest.mark.parametrize(
    "model,bad",
    [
        (model, bad)
        for model in MODELS
        for bad in (
            "invalid_family",
            "different_detail",
            "changed_family",
            "cost",
            "usage",
            "attempts",
        )
    ]
    + [(MODELS[0], "known_gpt_family")],
)
async def test_experiment_history_observations_never_bypass_identity_or_metering(model, bad):
    posts, gets = [], []
    latest = None

    def handler(request):
        nonlocal latest
        if request.method == "POST":
            posts.append(json.loads(request.content))
            latest = payload(model, tools=len(posts) == 1)
            latest.pop("provider")
            latest["id"] = "gen_" + str(900 + len(posts))
            return response(latest)
        gets.append(str(request.url))
        listing, detail = experiment_history(latest)
        if bad == "invalid_family":
            listing["items"][0]["provider"] = None
        if bad == "different_detail":
            detail["finalEndpointSlug"] = "another-family"
        if bad == "changed_family" and len(posts) == 2 or bad == "known_gpt_family":
            listing["items"][0]["provider"] = detail["finalEndpointSlug"] = "different-family"
        if bad == "cost":
            detail["clientCost"] = "0.002"
        if bad == "usage":
            detail["usage"]["prompt_tokens"] = 31
        if bad == "attempts":
            detail["attemptsCount"] = 2
        return response(listing if str(request.url) == HISTORY_LIST else detail)

    adapter = PolzaAdapter(experiment_route(model), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    assert len(posts) == (2 if bad == "changed_family" else 1)
    assert row["reads"] == (1 if bad == "changed_family" else 0)
    assert row["final"] is None and row["failures"]
    assert row["calls"][-1]["error_detail"] == "HISTORY_VERIFICATION_FAILED"
    assert len(gets) <= 2 * len(posts)
    assert adapter._continuation is None


@pytest.mark.parametrize("bad", ["input", "output", "cost", "unknown_cost"])
async def test_experimental_actual_usage_and_cost_stop_before_history_or_read(bad):
    posts = []
    data = payload(tools=True)
    data["id"] = "gen_989"
    if bad == "input":
        data["usage"]["prompt_tokens"] = INPUT_TOKENS + 1
    if bad == "output":
        data["usage"]["completion_tokens"] = 513
    if bad == "cost":
        data["usage"]["cost_rub"] = "100"
    if bad == "unknown_cost":
        data["usage"].pop("cost_rub")

    def handler(request):
        assert request.method == "POST"
        posts.append(request)
        return response(data)

    adapter = PolzaAdapter(experiment_route(), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    assert len(posts) == 1 and row["reads"] == 0 and row["final"] is None
    assert row["calls"][0]["error_detail"] == (
        "HISTORY_METERING_UNKNOWN" if bad == "unknown_cost" else "HISTORY_METERING_LIMIT"
    )


@pytest.mark.parametrize("model", MODELS[1:])
async def test_experiment_family_stays_pinned_across_cases(model):
    posts = []
    latest = None

    def handler(request):
        nonlocal latest
        if request.method == "POST":
            posts.append(request)
            latest = payload(model, tools=len(posts) == 1)
            latest["id"] = "gen_" + str(700 + len(posts))
            return response(latest)
        listing, detail = experiment_history(latest)
        if len(posts) == 3:
            listing["items"][0]["provider"] = detail["finalEndpointSlug"] = "other-family"
        return response(listing if str(request.url) == HISTORY_LIST else detail)

    adapter = PolzaAdapter(experiment_route(model), KEY, transport=httpx.MockTransport(handler))
    cases = load_cases(FIXTURES)
    ledger = Ledger(io.StringIO(), Decimal(10), 3)
    first = await run_case(adapter, next(c for c in cases if c.id == "tool_current"), ledger, 0)
    assert not first["failures"] and first["reads"] == 1
    assert adapter._continuation is None
    second = await run_case(adapter, next(c for c in cases if c.id == "owner_fact"), ledger, 1)
    assert second["final"] is None and second["reads"] == 0 and len(posts) == 3
    assert second["calls"][0]["error_detail"] == "HISTORY_VERIFICATION_FAILED"


@pytest.mark.parametrize("alteration", ["missing", "enabled", "raw_reasoning", "extra_content"])
async def test_non_thinking_finite_wire_cannot_be_silently_changed(alteration):
    adapter = PolzaAdapter(
        experiment_route(MODELS[2]),
        KEY,
        transport=httpx.MockTransport(lambda _: pytest.fail("POST forbidden")),
    )
    body = adapter.base_body(
        [{"role": "user", "content": "synthetic"}], {}, 512, schema_name="test"
    )
    if alteration == "missing":
        body.pop("reasoning")
    if alteration == "enabled":
        body["reasoning"]["enabled"] = True
    if alteration == "raw_reasoning":
        body["messages"][0]["reasoning_content"] = "PRIVATE_RAW_REASONING"
    if alteration == "extra_content":
        body["messages"][0]["extra_content"] = {"arbitrary": "PRIVATE_METADATA"}
    with pytest.raises(ProviderFailure) as exc:
        await adapter.image_probe(encode(body), 1)
    assert exc.value.detail == "PAYLOAD_OUTSIDE_REVIEWED_SCOPE"
    assert "PRIVATE" not in json.dumps(adapter.observation)


@pytest.mark.parametrize("size", [1, SIGNATURE_BYTES])
async def test_valid_gemini_signature_bytes_count_towards_input_and_are_not_logged(size):
    signature = "Z" * size
    posts, counts = [], []

    def handler(request):
        body = json.loads(request.content)
        posts.append(body)
        data = payload(MODELS[1], tools=len(posts) == 1)
        if len(posts) == 1:
            data["choices"][0]["message"]["tool_calls"][0]["extra_content"]["google"][
                "thought_signature"
            ] = signature
        else:
            assert (
                body["messages"][-2]["tool_calls"][0]["extra_content"]["google"][
                    "thought_signature"
                ]
                == signature
            )
        return response(data)

    adapter = PolzaAdapter(review(MODELS[1]), KEY, transport=httpx.MockTransport(handler))
    original_count = adapter.count_input_tokens

    def measured(request):
        tokens = original_count(request)
        wire = adapter.wire(request)
        assert tokens == len(wire) + OVERHEAD_TOKENS
        if request.exchanges:
            counts.append(len(wire))
            body = json.loads(wire)
            without = copy.deepcopy(body)
            without["messages"][-2]["tool_calls"][0].pop("extra_content")
            assert len(wire) - len(encode(without)) > size
        return tokens

    adapter.count_input_tokens = measured
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    assert not row["failures"] and row["reads"] == 1 and len(posts) == 2 and counts
    assert "thought_signature" not in json.dumps(row)
    if size > 1:
        assert signature not in json.dumps(row)
    assert adapter._continuation is None and adapter._run_key is None


@pytest.mark.parametrize("field", ["provider", "reasoning_tokens", "arguments"])
async def test_gemini_signature_reflection_never_enters_observations_or_dto(field):
    signature = "PRIVATE_SIGNATURE_FOR_REFLECTION_TEST"
    data = payload(MODELS[1], tools=True)
    call = data["choices"][0]["message"]["tool_calls"][0]
    call["extra_content"]["google"]["thought_signature"] = signature
    if field == "provider":
        data["provider"] = signature
    elif field == "reasoning_tokens":
        data["usage"]["completion_tokens_details"] = {"reasoning_tokens": signature}
    else:
        call["function"]["arguments"] = json.dumps({"key": signature})
    adapter = PolzaAdapter(
        review(MODELS[1]), KEY, transport=httpx.MockTransport(lambda _: response(data))
    )
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    assert row["reads"] == 0 and row["final"] is None
    assert row["calls"][0]["error_detail"] == "SIGNATURE_IN_RESPONSE"
    assert signature not in json.dumps(row) and adapter._continuation is None


@pytest.mark.parametrize(
    "shape,code",
    [
        (None, "SIGNATURE_EXTRA_TYPE"),
        ({"google": None}, "SIGNATURE_GOOGLE_TYPE"),
        ({"google": {}}, "SIGNATURE_FIELD_MISSING"),
        (
            {"google": {"thought_signature": "PRIVATE_OPAQUE", "PRIVATE_KEY": "PRIVATE_VALUE"}},
            "SIGNATURE_GOOGLE_KEYS",
        ),
        ({"google": {"thought_signature": True}}, "SIGNATURE_TYPE"),
        ({"google": {"thought_signature": {"PRIVATE_KEY": "PRIVATE_VALUE"}}}, "SIGNATURE_TYPE"),
    ],
)
async def test_signature_container_diagnostics_do_not_expose_keys_or_values(shape, code):
    data = payload(MODELS[1], tools=True)
    data["id"] = "gen_9001"
    data["choices"][0]["message"]["tool_calls"][0]["extra_content"] = shape
    adapter = PolzaAdapter(
        review(MODELS[1]), KEY, transport=httpx.MockTransport(lambda _: response(data))
    )
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 2), 0)
    call = row["calls"][0]
    assert call["error_detail"] == code and call["signature_diagnostic"]["code"] == code
    assert call["generation_id"] == "gen_9001" and call["observed_model"] == MODELS[1]
    assert call["body_metering"]["usage"] == {"input_tokens": 30, "output_tokens": 20}
    assert call["body_metering"]["reported_cost_rub"] == "0.001"
    assert call["route_evidence_source"] == "BODY" and call["history_family"] is None
    assert call["cost"]["status"] == "UNKNOWN" and call["history_gets"] == 0
    assert "PRIVATE" not in json.dumps(row) and row["reads"] == 0
    assert adapter._continuation is None and adapter._diagnostic_redactions == ()


@pytest.mark.parametrize("field", ["provider", "id", "reasoning"])
async def test_malformed_signature_reflection_is_redacted_from_failure_metadata(field):
    hidden = "gen_90015555" if field == "id" else "PRIVATE_MALFORMED_VALUE"
    data = payload(MODELS[1], tools=True)
    data["id"] = "gen_9001"
    data["choices"][0]["message"]["tool_calls"][0]["extra_content"]["PRIVATE_KEY"] = hidden
    if field == "reasoning":
        data["choices"][0]["message"]["reasoning_content"] = hidden
        data["provider"] = hidden
    else:
        data[field] = hidden
    adapter = PolzaAdapter(
        review(MODELS[1]), KEY, transport=httpx.MockTransport(lambda _: response(data))
    )
    row = await run_case(
        adapter,
        next(c for c in load_cases(FIXTURES) if c.id == "tool_current"),
        Ledger(io.StringIO(), Decimal(10), 2),
        0,
    )
    assert row["calls"][0]["error_detail"] == "SIGNATURE_EXTRA_KEYS"
    assert hidden not in json.dumps(row) and "PRIVATE_KEY" not in json.dumps(row)
    assert row["reads"] == 0 and row["final"] is None


@pytest.mark.parametrize(
    "bad",
    [
        "usage_type",
        "usage_cap",
        "reasoning",
        "total",
        "cost_null",
        "cost_bool",
        "cost_nan",
        "cost_alias",
        "cost_currency",
    ],
)
async def test_signature_failure_keeps_only_validated_metering_fields(bad):
    data = payload(MODELS[1], tools=True)
    data["id"] = "gen_9001"
    data["choices"][0]["message"]["tool_calls"][0].pop("extra_content")
    if bad == "usage_type":
        data["usage"]["prompt_tokens"] = True
    if bad == "usage_cap":
        data["usage"]["completion_tokens"] = 513
    if bad == "reasoning":
        data["usage"]["completion_tokens_details"] = {"reasoning_tokens": 21}
    if bad == "total":
        data["usage"]["total_tokens"] = 51
    if bad == "cost_null":
        data["usage"]["cost_rub"] = None
    if bad == "cost_bool":
        data["usage"]["cost_rub"] = True
    if bad == "cost_nan":
        data["usage"]["cost_rub"] = "NaN"
    if bad == "cost_alias":
        data["usage"]["cost"] = "0.002"
    if bad == "cost_currency":
        data["usage"]["currency"] = "USD"
    adapter = PolzaAdapter(
        experiment_route(MODELS[1]), KEY, transport=httpx.MockTransport(lambda _: response(data))
    )
    row = await run_case(
        adapter,
        next(c for c in load_cases(FIXTURES) if c.id == "tool_current"),
        Ledger(io.StringIO(), Decimal(10), 2),
        0,
    )
    call = row["calls"][0]
    assert call["error_detail"] == "SIGNATURE_EXTRA_MISSING"
    assert call["cost"]["status"] == "UNKNOWN" and call["history_gets"] == 0
    assert call["body_metering"]["reported_cost_rub"] == (
        None if bad.startswith("cost_") else "0.001"
    )
    assert call["body_metering"]["usage"]["input_tokens"] == (
        30 if bad.startswith("cost_") else None
    )
    assert row["reads"] == 0 and row["final"] is None


@pytest.mark.parametrize(
    "stage,field,value,reason,kind",
    [
        ("LIST", "items", None, "ITEMS", "NULL"),
        ("LIST", "no_id", None, "ID_MATCH_COUNT", "INT"),
        ("LIST", "duplicate", None, "ID_MATCH_COUNT", "INT"),
        ("LIST", "model", "wrong", "MODEL", "STRING"),
        ("LIST", "provider", None, "PROVIDER", "NULL"),
        ("LIST", "provider", {"PRIVATE_KEY": "PRIVATE_VALUE"}, "PROVIDER", "OBJECT"),
        ("LIST", "provider", "private spaces", "PROVIDER", "STRING"),
        ("LIST", "missing_provider", None, "PROVIDER", "MISSING"),
        ("LIST", "cost", "0.02", "COST", "STRING"),
        ("LIST", "cost", "NaN", "COST", "STRING"),
        ("LIST", "cost", [], "COST", "ARRAY"),
        ("LIST", "prompt_tokens", True, "USAGE_INPUT", "BOOL"),
        ("LIST", "completion_tokens", 999, "USAGE_OUTPUT", "INT"),
        ("LIST", "total_tokens", 999, "USAGE_TOTAL", "INT"),
        ("LIST", "reasoning_tokens", 1, "USAGE_REASONING", "INT"),
        ("DETAIL", "clientCost", "0.02", "COST", "STRING"),
        ("DETAIL", "finalEndpointSlug", None, "PROVIDER", "NULL"),
        ("DETAIL", "id", "gen_999", "GENERATION_ID", "STRING"),
        ("DETAIL", "model", "wrong", "MODEL", "STRING"),
        ("DETAIL", "requestType", "embedding", "REQUEST_TYPE", "STRING"),
        ("DETAIL", "status", "failed", "STATUS", "STRING"),
        ("DETAIL", "apiType", "private", "API_TYPE", "STRING"),
        ("DETAIL", "responseMode", "async", "RESPONSE_MODE", "STRING"),
        ("DETAIL", "isCancelled", True, "CANCELLED", "BOOL"),
        ("DETAIL", "attemptsCount", 2, "ATTEMPTS", "INT"),
        ("DETAIL", "finishReason", "length", "FINISH_REASON", "STRING"),
        ("DETAIL", "serverTools", ["PRIVATE_TOOL"], "SERVER_TOOLS", "ARRAY"),
        ("DETAIL", "parentGenerationId", "PRIVATE_ID", "PARENT_GENERATION", "STRING"),
        ("DETAIL", "stepsCount", 2, "STEPS", "INT"),
    ],
)
async def test_history_branch_diagnostics_keep_acceptance_and_primary_error(
    stage, field, value, reason, kind
):
    data = payload(MODELS[2], tools=True)
    data.pop("provider")
    data["id"] = "gen_123"
    listing, detail = experiment_history(data)
    row = listing["items"][0] if stage == "LIST" else detail
    if field == "items":
        listing["items"] = value
    elif field == "no_id":
        listing["items"] = []
    elif field == "duplicate":
        listing["items"] *= 2
    elif field == "missing_provider":
        row.pop("provider")
    elif field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        row["usage"][field] = value
    elif field == "reasoning_tokens":
        row["usage"]["completion_tokens_details"] = {field: value}
    else:
        row[field] = value
    seen = []

    def handler(request):
        seen.append(request.method)
        if request.method == "POST":
            return response(data)
        return response(listing if str(request.url) == HISTORY_LIST else detail)

    adapter = PolzaAdapter(experiment_route(MODELS[2]), KEY, transport=httpx.MockTransport(handler))
    gw = gateway(adapter, tools=True)
    result = await gw.call()
    assert result.kind == "ERROR" and result.error == "ADAPTER_ERROR"
    assert result.budget.reads_reserved == 0
    assert adapter.observation["error_detail"] == "HISTORY_VERIFICATION_FAILED"
    assert adapter.observation["history_diagnostic"] == {
        "stage": stage,
        "reason": reason,
        "observed_type": kind,
    }
    assert seen == ["POST"] + ["GET"] * (1 if stage == "LIST" else 2)
    assert "PRIVATE" not in json.dumps(adapter.observation)
    assert (await gw.call()).kind == "ERROR" and seen.count("POST") == 1


@pytest.mark.parametrize(
    "stage,bad,reason",
    [
        ("LIST", "json", "JSON"),
        ("DETAIL", "json", "JSON"),
        ("LIST", "escaped_key", "PRIVATE_REFLECTION"),
        ("DETAIL", "escaped_key", "PRIVATE_REFLECTION"),
        ("LIST", "oversize", "TRANSPORT"),
        ("DETAIL", "transport", "TRANSPORT"),
    ],
)
async def test_history_diagnostics_never_echo_raw_or_json_escaped_private_input(stage, bad, reason):
    data = payload(MODELS[2], tools=True)
    data.pop("provider")
    data["id"] = "gen_123"
    listing, detail = experiment_history(data)
    seen = []

    def handler(request):
        seen.append(request.method)
        if request.method == "POST":
            return response(data)
        current = "LIST" if str(request.url) == HISTORY_LIST else "DETAIL"
        row = listing if current == "LIST" else detail
        if current == stage:
            if bad == "json":
                return response(raw=b'{"PRIVATE_KEY":')
            if bad == "oversize":
                return response(raw=b"x" * 65537)
            if bad == "transport":
                raise httpx.ReadError("PRIVATE_ACCOUNT_METADATA")
            row["private"] = KEY.get_secret_value()
            raw = (
                json.dumps(row)
                .replace(
                    KEY.get_secret_value(),
                    "".join(f"\\u{ord(c):04x}" for c in KEY.get_secret_value()),
                )
                .encode()
            )
            return response(raw=raw)
        return response(row)

    adapter = PolzaAdapter(experiment_route(MODELS[2]), KEY, transport=httpx.MockTransport(handler))
    result = await gateway(adapter, tools=True).call()
    assert result.kind == "ERROR"
    diag = adapter.observation["history_diagnostic"]
    assert diag["stage"] == stage and diag["reason"] == reason
    assert seen == ["POST"] + ["GET"] * (1 if stage == "LIST" else 2)
    rendered = json.dumps(adapter.observation)
    assert KEY.get_secret_value() not in rendered and "PRIVATE_KEY" not in rendered
    assert "PRIVATE_ACCOUNT_METADATA" not in rendered
