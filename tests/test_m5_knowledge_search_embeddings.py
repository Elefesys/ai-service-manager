import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from asm.knowledge import embeddings as e


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


def response(data, *, headers=None):
    raw = json.dumps(data, ensure_ascii=False).encode()
    return httpx.Response(
        200, headers={"content-type": "application/json", **(headers or {})}, stream=Bytes(raw)
    )


def wire():
    return json.dumps(
        {
            "model": e.MODEL,
            "input": ["подготовка"],
            "encoding_format": "float",
            "dimensions": 1536,
            "provider": {
                "only": ["openai"],
                "allow_fallbacks": False,
                "require_parameters": True,
                "max_price": {"prompt": 3, "completion": 0, "image": 0, "audio": 0, "request": 0},
            },
        },
        ensure_ascii=False,
    )


def body(*, provider=True):
    result = {
        "id": "gen_123",
        "model": e.MODEL,
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": [1.0] + [0.0] * 1535}],
        "usage": {"prompt_tokens": 8, "total_tokens": 8, "cost": "0.000001"},
    }
    if provider:
        result["provider"] = "OpenAI"
    return result


def history():
    item = {
        "id": "gen_123",
        "model": e.MODEL,
        "provider": "OpenAI",
        "requestType": "embeddings",
        "status": "completed",
        "cost": "0.000001",
        "usage": {"prompt_tokens": 8, "total_tokens": 8},
    }
    detail = {
        "id": "gen_123",
        "finalEndpointSlug": "OpenAI",
        "requestType": "embeddings",
        "apiType": "embeddings",
        "responseMode": "sync",
        "status": "completed",
        "isCancelled": False,
        "attemptsCount": 1,
        "clientCost": "0.000001",
        "usage": {"prompt_tokens": 8, "total_tokens": 8},
    }
    return item, detail


async def run(data, item=None, detail=None):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return response(data)
        if request.url.query:
            return response({"items": [item], "meta": {"page": 1}})
        return response(detail)

    text = wire()
    value = await e.EmbeddingClient(httpx.MockTransport(handler)).complete(
        text,
        deadline=datetime.now(UTC) + timedelta(seconds=10),
        wire_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    return value, requests


@pytest.mark.asyncio
async def test_body_observation_keeps_exact_wire_and_absent_usage():
    data = body()
    original = deepcopy(data)
    out, requests = await run(data)
    assert out["kind"] == "SUCCESS" and out["identity"]["source"] == "BODY"
    assert len(requests) == 1 and requests[0].content == wire().encode()
    assert "completion_tokens" not in out["usage"] and data == original
    assert len(out["vectors"][0]) == 1536


@pytest.mark.asyncio
async def test_actual_history_shape_correlates_list_model_and_detail_provider():
    data = body(provider=False)
    item, detail = history()
    original = deepcopy((data, item, detail))
    out, requests = await run(data, item, detail)
    assert out["kind"] == "SUCCESS" and out["identity"]["source"] == "HISTORY"
    assert [r.method for r in requests] == ["POST", "GET", "GET"]
    assert requests[1].url.path == requests[2].url.path.rsplit("/", 1)[0]
    assert "model" not in detail and "completion_tokens" not in out["usage"]
    assert (data, item, detail) == original


@pytest.mark.parametrize(
    "completion,success", [(0, True), (None, False), ("0", False), (False, False), (1, False)]
)
@pytest.mark.asyncio
async def test_embedding_completion_tokens_modality_rule(completion, success):
    data = body()
    data["usage"]["completion_tokens"] = completion
    out, requests = await run(data)
    assert (out["kind"] == "SUCCESS") == success and len(requests) == 1
    assert data["usage"]["completion_tokens"] is completion


@pytest.mark.parametrize(
    "target,key,value",
    [
        ("list", "id", "gen_999"),
        ("list", "model", "other"),
        ("list", "provider", "Other"),
        ("detail", "id", "gen_999"),
        ("detail", "finalEndpointSlug", "Other"),
        ("detail", "attemptsCount", True),
        ("detail", "attemptsCount", 2),
        ("detail", "requestType", "chat"),
        ("detail", "apiType", "chat_completions"),
        ("detail", "isCancelled", True),
        ("detail", "stepsCount", 2),
    ],
)
@pytest.mark.asyncio
async def test_no_unrelated_history_confirms_route(target, key, value):
    item, detail = history()
    (item if target == "list" else detail)[key] = value
    out, requests = await run(body(provider=False), item, detail)
    assert out["kind"] != "SUCCESS" and out["vectors"] is None
    assert len(requests) <= 3 and sum(r.method == "POST" for r in requests) == 1


@pytest.mark.parametrize("damage", ["dimensions", "integer", "bool", "zero", "duplicate_index"])
@pytest.mark.asyncio
async def test_invalid_vectors_cannot_apply_but_reported_cost_is_separate(damage):
    data = body()
    vector = data["data"][0]["embedding"]
    if damage == "dimensions":
        vector.pop()
    elif damage == "integer":
        vector[0] = 1
    elif damage == "bool":
        vector[0] = True
    elif damage == "zero":
        vector[0] = 0.0
    else:
        data["data"][0]["index"] = 1
    out, requests = await run(data)
    assert out["kind"] == "ERROR" and out["vectors"] is None and len(requests) == 1
    assert out["cost"] == {"status": "CONFIRMED", "amount": "0.000001", "currency": "RUB"}


@pytest.mark.asyncio
async def test_disabled_default_and_uncertain_call_never_retry():
    text = wire()
    kwargs = {
        "deadline": datetime.now(UTC) + timedelta(seconds=10),
        "wire_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    assert (await e.EmbeddingClient().complete(text, **kwargs))["error_code"] == "DISABLED"
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("PRIVATE transport error must not escape")

    out = await e.EmbeddingClient(httpx.MockTransport(handler)).complete(text, **kwargs)
    assert out["kind"] == "UNKNOWN" and len(calls) == 1 and out["vectors"] is None
    assert "PRIVATE" not in str(out)


@pytest.mark.asyncio
async def test_invalid_wire_stops_before_transport():
    calls = []

    def handler(request):
        calls.append(request)
        return response(body())

    client = e.EmbeddingClient(httpx.MockTransport(handler))
    bad = wire().replace('"only": ["openai"]', '"only": ["Other"]')
    with pytest.raises(e.EmbeddingFailure, match="PROFILE_MISMATCH"):
        await client.complete(
            bad,
            deadline=datetime.now(UTC) + timedelta(seconds=10),
            wire_sha256=hashlib.sha256(bad.encode()).hexdigest(),
        )
    assert not calls


@pytest.mark.asyncio
async def test_cost_over_reservation_is_recorded_and_never_applied():
    data = body()
    data["usage"]["cost"] = "0.09"
    out, requests = await run(data)
    assert out["kind"] == "ERROR" and out["error_code"] == "COST_LIMIT" and out["vectors"] is None
    assert out["cost"] == {"status": "CONFIRMED", "amount": "0.09", "currency": "RUB"}
    assert len(requests) == 1 and out["usage"] == data["usage"]


@pytest.mark.asyncio
async def test_invalid_usage_preserves_observed_raw_and_separate_cost():
    data = body()
    data["usage"]["completion_tokens"] = None
    out, requests = await run(data)
    assert out["kind"] == "ERROR" and out["error_code"] == "USAGE_INVALID"
    assert out["usage"] == data["usage"] and out["usage"]["completion_tokens"] is None
    assert out["cost"]["status"] == "CONFIRMED" and len(requests) == 1
