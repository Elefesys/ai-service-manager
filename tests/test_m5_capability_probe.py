"""Offline contracts and real durable-file boundaries; never paid capability evidence."""

import asyncio
import base64
import copy
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from asm.ai import capability_probe as probe
from asm.ai.polza import CAPABILITY_CATALOG, EMBEDDINGS, ENDPOINT, HISTORY, encode
from PIL import Image, PngImagePlugin
from pydantic import SecretStr, ValidationError

KEY = "PRIVATE_SQL_COOKIE_GRANT_SENTINEL"


@pytest.fixture
def plan():
    return probe.make_plan(
        {"head": "a" * 40, "tree": "b" * 40, "assignment": probe.ASSIGNMENT},
        (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )


def catalog():
    # Constructed minimal transport fixture from the public model contracts,
    # not an authenticated account observation or an availability assertion.
    return {
        "data": [
            {
                "id": model,
                "type": kind,
                "architecture": {"input_modalities": modalities},
                "providers": [
                    {
                        "name": "openai",
                        "is_unofficial": False,
                        "context_length": 128000 if kind == "chat" else None,
                        "max_completion_tokens": 16384 if kind == "chat" else None,
                        "supported_parameters": ["max_tokens", "response_format"]
                        if kind == "chat"
                        else None,
                        "capabilities": {
                            k: {"status": "supported"}
                            for k in ["input_image", "json_schema_strict"]
                        }
                        if kind == "chat"
                        else {},
                        "pricing": pricing,
                    }
                ],
            }
            for model, kind, modalities, pricing in [
                (
                    probe.VISION_MODEL,
                    "chat",
                    ["text", "image"],
                    {
                        "currency": "RUB",
                        "prompt_per_million": "18.22873500",
                        "completion_per_million": "72.91494000",
                        "input_cache_read_per_million": "9.11436750",
                    },
                ),
                (
                    probe.EMBEDDING_MODEL,
                    "embedding",
                    ["text"],
                    {
                        "currency": "RUB",
                        "prompt_per_million": "2.43049800",
                    },
                ),
            ]
        ]
    }


def result(case):
    return {
        "status": case.expected_status,
        "motif": case.expected_motif,
        "observations": ["TEXT"]
        if case.id == "unsuitable"
        else ["RED", "GREEN", "BLACK"]
        if case.id == "ordinary"
        else ["BLACK"],
        "scale": "UNKNOWN",
        "size_cm": None,
        "duration_hours": None,
        "price_rub": None,
        "order_approved": None,
        "injection_detected": case.id == "unsuitable",
    }


def embedding():
    return {
        "id": "emb_104",
        "object": "list",
        "model": probe.EMBEDDING_MODEL,
        "provider": "openai",
        "data": [
            {
                "object": "embedding",
                "index": i,
                "embedding": values + [0.0] * (probe.DIMENSIONS - 2),
            }
            for i, values in enumerate([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
        ],
        "usage": {
            "prompt_tokens": 100,
            "total_tokens": 100,
            "cost_rub": "0.0002",
            "cost": "0.0002",
        },
    }


class Server:
    def __init__(self, *, mutate=None, fail=None):
        self.requests = []
        self.responses = {}
        self.post_index = 0
        self.mutate = mutate
        self.fail = fail

    async def __call__(self, request):
        self.requests.append(request)
        assert request.headers["authorization"] == "Bearer " + KEY
        if self.fail == len(self.requests):
            raise httpx.ReadTimeout(KEY + " SQL payload credentials")
        if str(request.url) == CAPABILITY_CATALOG:
            data = catalog()
        elif str(request.url) == ENDPOINT:
            body = json.loads(request.content)
            assert body["provider"] == probe.routing(embedding=False)
            assert body["stream"] is False and body["max_tokens"] == 512
            assert "tools" not in body and "plugins" not in body
            case = probe.load_cases().images[self.post_index]
            self.post_index += 1
            data = {
                "id": "gen_" + str(100 + self.post_index),
                "model": probe.VISION_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(result(case))},
                    }
                ],
                "usage": {
                    "prompt_tokens": 2000,
                    "completion_tokens": 100,
                    "total_tokens": 2100,
                    "cost_rub": "0.002",
                    "cost": "0.002",
                },
            }
        elif str(request.url) == EMBEDDINGS:
            body = json.loads(request.content)
            assert body["input"] == probe.load_cases().texts and body["dimensions"] == 1536
            assert body["provider"] == probe.routing(embedding=True)
            data = embedding()
        else:
            assert str(request.url).startswith(HISTORY + "/gen_")
            response = self.responses[str(request.url).rsplit("/", 1)[1]]
            is_embedding = response["model"] == probe.EMBEDDING_MODEL
            data = {
                "id": response["id"],
                "model": response["model"],
                "status": "completed",
                "finalEndpointSlug": "openai",
                "requestType": "embedding" if is_embedding else "chat",
                "apiType": "embeddings" if is_embedding else "completions",
                "responseMode": "sync",
                "isCancelled": False,
                "clientCost": response["usage"]["cost_rub"],
                "usage": response["usage"],
                "finishReason": "stop",
            }
        if self.mutate:
            self.mutate(data, request, len(self.requests))
        if request.method == "POST" and "id" in data:
            self.responses[data["id"]] = copy.deepcopy(data)
        return httpx.Response(200, stream=httpx.ByteStream(encode(data)))


@pytest.mark.parametrize("mode", [[], ["plan"], ["offline"]])
def test_default_and_offline_never_read_key_http_or_create_session(
    mode, plan, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(probe, "source_identity", lambda: plan["source"])

    def forbidden(*a, **kw):
        pytest.fail("credential/HTTP/session boundary before approval")

    monkeypatch.setattr(probe, "local_key", forbidden)
    monkeypatch.setattr(probe.httpx, "AsyncClient", forbidden)
    assert probe.main([*mode, "--state-dir", str(tmp_path / "state")]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "REVIEW" and value["real_route"] == "UNVERIFIED"
    assert value["max_http_requests"] == len(value["requests"]) == 8
    assert not (tmp_path / "state").exists()


def test_plan_real_bytes_pinned_payloads_and_conservative_sum(plan):
    assert sum(Decimal(r["reserve_rub"]) for r in plan["requests"]) == Decimal("11.75")
    assert Decimal("11.75") == 3 * Decimal("3.89") + Decimal("0.08")
    assert Decimal("3.89") >= (128000 * Decimal(30) + 512 * Decimal(80)) / 1000000
    assert Decimal("0.08") >= 3 * 8192 * Decimal(3) / 1000000
    assert sum(r["method"] == "POST" for r in plan["requests"]) == 4
    for case, metadata, spec in zip(
        probe.load_cases().images, plan["images"], plan["requests"][1:7:2], strict=True
    ):
        png, observed = probe.preprocess(case)
        assert observed | {"id": case.id} == metadata
        assert Image.open(io.BytesIO(png)).size == (256, 256)
        assert probe.sha(probe.vision_body(case)) == spec["payload_sha256"]
        assert metadata["pixels"] == 65536 and metadata["mime"] == "image/png"
    unsigned = {k: v for k, v in plan.items() if k != "plan_sha256"}
    assert probe.sha(encode(unsigned)) == plan["plan_sha256"]


@pytest.mark.parametrize("damage", ["approval", "deadline", "naive", "changed_plan"])
def test_start_rejects_before_credentials_state_and_http(plan, tmp_path, monkeypatch, damage):
    monkeypatch.setattr(probe, "local_key", lambda: pytest.fail("key read"))
    if damage == "deadline":
        plan["approval_until"] = "2020-01-01T00:00:00+00:00"
    if damage == "naive":
        plan["approval_until"] = "2099-01-01T00:00:00"
    if damage == "changed_plan":
        plan["requests"][1]["reserve_rub"] = "0"
    if damage in {"deadline", "naive"}:
        plan["plan_sha256"] = probe.sha(
            encode({k: v for k, v in plan.items() if k != "plan_sha256"})
        )
    with pytest.raises(probe.ProbeError):
        probe.start(
            plan, "f" * 64 if damage == "approval" else plan["plan_sha256"], tmp_path / "state"
        )
    assert not (tmp_path / "state").exists()


async def test_single_mock_roundtrip_never_claims_real_semantics_and_never_resumes(
    plan, tmp_path, monkeypatch
):
    receipt = probe.Receipt(tmp_path, plan)
    server = Server()
    value = await probe.execute(
        plan, receipt, lambda: SecretStr(KEY), transport=httpx.MockTransport(server)
    )
    assert value["status"] == "MOCK_CONTRACT_PASS" and value["real_route"] == "UNVERIFIED"
    assert value["http_requests"] == len(server.requests) == 8
    assert all(
        c["upstream_attempts"] == "NOT_REPORTED"
        for c in value["calls"]
        if c["id"] in {"ordinary", "ambiguous", "unsuitable"}
    )
    assert value["held_rub"] == "0.00" and Decimal(value["cost_rub"]) == Decimal("0.0062")
    assert value["closed"] is True and all(c["status"] == "CONFIRMED" for c in value["calls"])
    assert json.loads(receipt.path.read_bytes()) == value
    assert KEY not in receipt.path.read_text() and "data:image" not in receipt.path.read_text()
    assert 'embedding":[' not in receipt.path.read_text()
    monkeypatch.setattr(probe, "local_key", lambda: pytest.fail("restart read key"))
    with pytest.raises(probe.ProbeError, match="SESSION_ALREADY_EXISTS_NO_RESEND"):
        probe.start(plan, plan["plan_sha256"], tmp_path)


@pytest.mark.parametrize("fail", [1, 2, 3, 4, 6, 8])
async def test_timeout_keeps_reservation_closes_and_stops_prefix(plan, tmp_path, fail):
    receipt = probe.Receipt(tmp_path, plan)
    server = Server(fail=fail)
    value = await probe.execute(
        plan, receipt, lambda: SecretStr(KEY), transport=httpx.MockTransport(server)
    )
    assert value["status"] == "UNKNOWN" and value["closed"]
    assert value["http_requests"] == len(server.requests) == fail
    assert Decimal(value["held_rub"]) == (
        Decimal(0) if fail == 1 else probe.EMBEDDING_RESERVE if fail >= 8 else probe.VISION_RESERVE
    )
    assert KEY not in receipt.path.read_text()
    with pytest.raises(probe.ProbeError, match="NO_RESEND"):
        probe.Receipt(tmp_path, plan)


async def test_stop_cancels_actual_inflight_transport_without_followup(plan, tmp_path):
    entered = asyncio.Event()

    async def block(request):
        if request.method == "GET":
            return httpx.Response(200, stream=httpx.ByteStream(encode(catalog())))
        entered.set()
        await asyncio.Future()

    receipt = probe.Receipt(tmp_path, plan)
    task = asyncio.create_task(
        probe.execute(plan, receipt, lambda: SecretStr(KEY), transport=httpx.MockTransport(block))
    )
    await asyncio.wait_for(entered.wait(), 2)
    probe.stop(tmp_path, plan["plan_sha256"])
    value = await asyncio.wait_for(task, 2)
    assert value["closed"] and value["status"] == "UNKNOWN"
    assert value["http_requests"] == 2 and Decimal(value["held_rub"]) == probe.VISION_RESERVE


async def test_session_deadline_cancels_and_preserves_unknown(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "SESSION_SECONDS", 0.05)

    async def block(request):
        if request.method == "GET":
            return httpx.Response(200, stream=httpx.ByteStream(encode(catalog())))
        await asyncio.Future()

    value = await probe.execute(
        plan,
        probe.Receipt(tmp_path, plan),
        lambda: SecretStr(KEY),
        transport=httpx.MockTransport(block),
    )
    assert value["status"] == "UNKNOWN" and value["closed"] and value["http_requests"] == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("size_cm", 10),
        ("duration_hours", 1),
        ("price_rub", 1),
        ("order_approved", True),
        ("scale", "KNOWN"),
        ("url", "https://invalid.example"),
        ("observations", ["APPROVED"]),
    ],
)
def test_model_cannot_install_business_facts_or_urls(field, value):
    data = result(probe.load_cases().images[0])
    data[field] = value
    with pytest.raises(ValidationError):
        probe.VisionResult.model_validate(data)


@pytest.mark.parametrize(
    "damage", ["dimension", "nan", "infinity", "bool", "zero", "duplicate", "index", "count"]
)
def test_embedding_rejects_invalid_dimensions_values_and_indices(damage):
    data = embedding()
    if damage == "dimension":
        data["data"][0]["embedding"].pop()
    if damage in {"nan", "infinity", "bool"}:
        data["data"][0]["embedding"][0] = {
            "nan": float("nan"),
            "infinity": float("inf"),
            "bool": True,
        }[damage]
    if damage == "zero":
        data["data"][0]["embedding"] = [0.0] * 1536
    if damage == "duplicate":
        data["data"][1]["index"] = 0
    if damage == "index":
        data["data"][0]["index"] = False
    if damage == "count":
        data["data"].pop()
    with pytest.raises(probe.ProbeError):
        probe.embedding_result(data)


def test_embedding_ranks_by_explicit_indices_not_server_order():
    data = embedding()
    data["data"].reverse()
    value = probe.embedding_result(data)
    assert value["dimension"] == 1536 and value["quality_pass"]
    assert value["relevant_cosine"] > value["irrelevant_cosine"]


@pytest.mark.parametrize(
    "damage",
    [
        "provider",
        "duplicate",
        "price",
        "fee",
        "currency",
        "unknown_fee",
        "capability",
        "context",
        "missing",
    ],
)
async def test_catalog_blocker_stops_before_model_post(plan, tmp_path, damage):
    def mutate(data, request, n):
        if n != 1:
            return
        p = data["data"][0]["providers"][0]
        if damage == "provider":
            p["is_unofficial"] = True
        if damage == "duplicate":
            data["data"][0]["providers"].append(copy.deepcopy(p))
        if damage == "price":
            p["pricing"]["prompt_per_million"] = "20.01"
        if damage == "fee":
            p["pricing"]["per_request"] = "0.01"
        if damage == "currency":
            p["pricing"]["currency"] = "USD"
        if damage == "unknown_fee":
            p["pricing"]["overrides"] = []
        if damage == "capability":
            p["capabilities"]["input_image"]["status"] = "unknown"
        if damage == "context":
            p["context_length"] = None
        if damage == "missing":
            data["data"].pop()

    server = Server(mutate=mutate)
    value = await probe.execute(
        plan,
        probe.Receipt(tmp_path, plan),
        lambda: SecretStr(KEY),
        transport=httpx.MockTransport(server),
    )
    assert value["status"] == "UNKNOWN" and len(server.requests) == 1
    assert not any(r.method == "POST" for r in server.requests)


@pytest.mark.parametrize(
    "damage", ["secret", "cost", "provider", "history", "dimension", "quality"]
)
async def test_response_failures_have_bounded_prefix_safe_receipt_and_truthful_cost(
    plan, tmp_path, damage
):
    def mutate(data, request, n):
        if n == 2:
            if damage == "secret":
                data["private"] = KEY
            if damage == "cost":
                data["usage"]["cost_rub"] = "NaN"
            if damage == "provider":
                data["provider"] = "Other"
            if damage == "quality":
                v = json.loads(data["choices"][0]["message"]["content"])
                v["motif"] = "UNKNOWN"
                data["choices"][0]["message"]["content"] = json.dumps(v)
        if damage == "history" and n == 3:
            data["providerAttempts"] = 2
        if damage == "dimension" and n == 8:
            data["data"][0]["embedding"].pop()

    server = Server(mutate=mutate)
    receipt = probe.Receipt(tmp_path, plan)
    value = await probe.execute(
        plan, receipt, lambda: SecretStr(KEY), transport=httpx.MockTransport(server)
    )
    assert value["closed"] and value["real_route"] == "UNVERIFIED"
    assert KEY not in receipt.path.read_text()
    assert (
        len(server.requests)
        == {"secret": 2, "cost": 2, "provider": 2, "history": 3, "dimension": 8, "quality": 3}[
            damage
        ]
    )
    assert value["status"] == ("FAILED" if damage == "quality" else "UNKNOWN")


def test_preprocessing_strips_metadata_and_rejects_different_pixels():
    case = probe.load_cases().images[0]
    raw = base64.b64decode(case.png_base64)
    image = Image.open(io.BytesIO(raw))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", KEY)
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    changed = output.getvalue()
    modified = case.model_copy(
        update={"png_base64": base64.b64encode(changed).decode(), "raw_sha256": probe.sha(changed)}
    )
    clean, _ = probe.preprocess(modified)
    assert KEY.encode() not in clean and not Image.open(io.BytesIO(clean)).info
    image = Image.new("RGB", (257, 256))
    output = io.BytesIO()
    image.save(output, format="PNG")
    changed = output.getvalue()
    modified = case.model_copy(
        update={"png_base64": base64.b64encode(changed).decode(), "raw_sha256": probe.sha(changed)}
    )
    with pytest.raises(probe.ProbeError, match="IMAGE_PIXELS"):
        probe.preprocess(modified)


def test_error_labels_and_cli_arguments_never_echo_secrets(capsys):
    assert probe.error_code(probe.ProbeError(KEY)) == "SCHEMA_OR_LOCAL_FAILURE"
    assert probe.error_code(ValueError(KEY)) == "SCHEMA_OR_LOCAL_FAILURE"
    assert probe.main(["--" + KEY]) == 2
    assert KEY not in capsys.readouterr().out


def test_json_duplicate_nonfinite_and_oversize_are_rejected():
    for raw in [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b"x" * 21]:
        with pytest.raises((ValueError, probe.ProbeError)):
            probe.read_json(raw, 20)


async def test_key_prompt_failure_closes_without_http_or_secret_reflection(plan, tmp_path):
    def timed_out():
        raise probe.ProbeError("KEY_DEADLINE")

    def forbidden(request):
        pytest.fail("HTTP before a local key was obtained")

    value = await probe.execute(
        plan, probe.Receipt(tmp_path, plan), timed_out, transport=httpx.MockTransport(forbidden)
    )
    assert value["closed"] and value["status"] == "FAILED" and value["code"] == "KEY_DEADLINE"
    assert value["http_requests"] == 0 and Decimal(value["held_rub"]) == 0


async def test_unicode_escaped_secret_is_not_hashed_into_catalog_receipt(plan, tmp_path):
    def reflected(request):
        data = catalog() | {"private": KEY}
        escaped = "".join(f"\\u{ord(c):04x}" for c in KEY).encode()
        raw = encode(data).replace(KEY.encode(), escaped)
        assert KEY.encode() not in raw
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    receipt = probe.Receipt(tmp_path, plan)
    value = await probe.execute(
        plan, receipt, lambda: SecretStr(KEY), transport=httpx.MockTransport(reflected)
    )
    assert value["status"] == "UNKNOWN" and value["code"] == "SECRET_REFLECTION"
    assert value["http_requests"] == 1 and "catalog_sha256" not in value
    assert KEY not in receipt.path.read_text()


async def test_undocumented_embedding_provider_is_unknown_with_hold_and_no_history(plan, tmp_path):
    def missing(data, request, n):
        if n == 8:
            data.pop("provider")

    server = Server(mutate=missing)
    value = await probe.execute(
        plan,
        probe.Receipt(tmp_path, plan),
        lambda: SecretStr(KEY),
        transport=httpx.MockTransport(server),
    )
    assert value["status"] == "UNKNOWN" and value["code"] == "PROVIDER_NOT_OBSERVED"
    assert value["http_requests"] == len(server.requests) == 8
    assert Decimal(value["held_rub"]) == probe.EMBEDDING_RESERVE
    assert value["calls"][-1]["result"]["quality_pass"]
    assert value["calls"][-1]["body_provider_state"] == "ABSENT"
    assert value["real_route"] == "UNVERIFIED"


@pytest.mark.parametrize("variant", ["no-id", "vendor-model-id"])
async def test_documented_embedding_identity_shapes_need_no_history_guess(plan, tmp_path, variant):
    def identity(data, request, n):
        if n != 8:
            return
        if variant == "no-id":
            data.pop("id")
        else:
            data["model"] = "text-embedding-3-small"

    server = Server(mutate=identity)
    value = await probe.execute(
        plan,
        probe.Receipt(tmp_path, plan),
        lambda: SecretStr(KEY),
        transport=httpx.MockTransport(server),
    )
    assert value["status"] == "MOCK_CONTRACT_PASS" and value["http_requests"] == 8
    assert value["real_route"] == "UNVERIFIED"


def test_receipt_symlink_and_unresolved_partial_write_cannot_resend(plan, tmp_path):
    destination = tmp_path / "real"
    destination.mkdir()
    link = tmp_path / "link"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(probe.ProbeError, match="STATE_PATH"):
        probe.Receipt(link, plan)
    receipt = probe.Receipt(destination, plan)
    receipt.reserve(plan["requests"][1])
    assert Decimal(json.loads(receipt.path.read_text())["held_rub"]) == probe.VISION_RESERVE
    with pytest.raises(probe.ProbeError, match="NO_RESEND"):
        probe.Receipt(destination, plan)
