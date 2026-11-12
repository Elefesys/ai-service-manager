"""Failure evidence and offline request construction; no live API/DB calls."""

import asyncio
import hashlib
import json
import ssl
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from asm.ai.database import DurableAdapter
from asm.ai.gateway import ModelGateway
from asm.ai.polza import PolzaAdapter, PolzaFailure, RuntimeRoute, failure_labels, fingerprint
from test_m4_polza import KEY, gateway, payload, response, review
from test_m4_polza_runtime import Wire, settings
from test_m4_runtime_database import prepared

from scripts.m4_offline_wire_check import inspect


def events(caplog):
    return [
        json.loads(row.getMessage().split("AI_PROVIDER_FAILURE ", 1)[1])
        for row in caplog.records
        if row.name == "asm.ai.provider_failure"
    ]


def offline_inputs(**changes):
    run = prepared()
    cfg = settings(
        **{
            name: getattr(run.binding, name)
            for name in ("workspace_id", "client_id", "conversation_id", "connection_id")
        }
        | changes
    )
    return cfg, run.model_copy(update={"config": cfg.gateway()})


@pytest.mark.parametrize("status", [400, 401, 402, 429, 503])
async def test_http_failure_is_logged_once_without_body_or_retry(status, caplog):
    calls = []
    secret = KEY.get_secret_value()

    def wire(request):
        calls.append(request)
        return httpx.Response(status, json={"error": secret, "prompt": "private-client-text"})

    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(wire))
    model = gateway(adapter)
    result = await model.call()
    assert result.kind == "ERROR" and result.budget.calls_used == 1
    assert (await model.call()).error == "CLOSED"
    assert len(calls) == 1
    (event,) = events(caplog)
    assert event["detail"] == f"HTTP_{status}" and event["http_status"] == status
    assert event["stage"] == "MODEL_HTTP" and event["call_sequence"] == 1
    assert secret not in caplog.text and "private-client-text" not in caplog.text
    assert len(event["run_ref"]) == 64


@pytest.mark.parametrize(
    "error,kind",
    [
        (ssl.SSLError("private TLS contents"), "TLS"),
        (ssl.SSLCertVerificationError("private certificate"), "TLS_CERTIFICATE"),
        (httpx.ReadTimeout("private endpoint"), "HTTP_TIMEOUT"),
        (httpx.ConnectError("private network"), "HTTP_CONNECT"),
    ],
)
async def test_transport_type_survives_wrapping(error, kind, caplog):
    def wire(request):
        raise error

    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(wire))
    result = await gateway(adapter).call()
    assert result.kind == "ERROR" and result.budget.calls_used == 1
    (event,) = events(caplog)
    assert kind in (event["exception_type"], event["cause_type"])
    assert event["stage"] == "MODEL_HTTP" and "private" not in caplog.text


async def test_cancel_stays_cancelled_and_log_error_never_replaces_primary(monkeypatch, caplog):
    async def wire(request):
        raise asyncio.CancelledError

    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(wire))
    with pytest.raises(asyncio.CancelledError):
        await gateway(adapter).call()
    assert events(caplog)[0]["exception_type"] == "CANCELLED"
    import asm.ai.polza as module

    monkeypatch.setattr(
        module._FAILURE_LOG, "warning", Mock(side_effect=RuntimeError("log broken"))
    )
    with pytest.raises(asyncio.CancelledError):
        await gateway(adapter).call()


async def test_decode_failure_identified_without_raw_response(caplog):
    adapter = PolzaAdapter(
        review(),
        KEY,
        transport=httpx.MockTransport(lambda req: response({"choices": "private-response"})),
    )
    assert (await gateway(adapter).call()).kind == "ERROR"
    (event,) = events(caplog)
    assert event["stage"] == "DECODE" and event["detail"] == "INVALID_PROVIDER_RESPONSE"
    assert "private-response" not in caplog.text


async def test_history_failure_has_stage_and_hashed_correlation(caplog):
    cfg, wire = settings(), Wire(failure="metadata")
    adapter = PolzaAdapter(
        cfg.review, KEY, transport=httpx.MockTransport(wire), history_profile="gpt_eval_history_v2"
    )
    result = await gateway(adapter).call()
    assert result.kind == "ERROR" and len(wire.posts) == 1 and len(wire.gets) == 2
    (event,) = events(caplog)
    assert event["stage"] == "HISTORY_DETAIL"
    assert event["generation_ref"] == hashlib.sha256(wire.latest["id"].encode()).hexdigest()
    assert wire.latest["id"] not in caplog.text


async def test_review_expiry_is_pre_http_and_success_is_not_logged(caplog):
    checked = review().model_copy(update={"checked_at": datetime.now(UTC) - timedelta(days=2)})
    wire = Mock(side_effect=AssertionError("HTTP forbidden"))
    adapter = PolzaAdapter(checked, KEY, transport=httpx.MockTransport(wire))
    assert (await gateway(adapter).call()).kind == "ERROR"
    wire.assert_not_called()
    (event,) = events(caplog)
    assert event["stage"] == "REVIEW" and event["detail"] == "REVIEW_EXPIRED"
    caplog.clear()
    adapter = PolzaAdapter(
        review(), KEY, transport=httpx.MockTransport(lambda req: response(payload()))
    )
    assert (await gateway(adapter).call()).kind == "FINAL"
    assert events(caplog) == []


@pytest.mark.parametrize(
    "error", [ValueError("PRIVATE_TOKEN"), PolzaFailure("ADAPTER_ERROR", "PRIVATE_TOKEN")]
)
def test_unknown_exception_details_are_never_copied(error):
    assert failure_labels(error)["detail"] == "UNCLASSIFIED"
    assert "PRIVATE_TOKEN" not in json.dumps(failure_labels(error))


@pytest.mark.parametrize("completion_fails", [False, True])
async def test_durable_unknown_hold_and_original_error_survive_diagnostic(completion_fails, caplog):
    wire = Mock(return_value=httpx.Response(402))
    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(wire))
    base = gateway(adapter)
    saved = []

    class Database:
        async def reserve(self, claim, run, budget):
            saved.append(("RESERVE", budget.calls_used))
            return 1

        async def complete(self, claim, run, sequence, completion):
            saved.append(("COMPLETE", sequence, completion))
            if completion_fails:
                raise RuntimeError("private database failure")

    durable = DurableAdapter(Database(), None, SimpleNamespace(config=base._config), adapter)
    model = ModelGateway(base._config, base._request, durable)
    result = await model.call()
    assert result.error == "ADAPTER_ERROR" and result.budget.cost_reserved > 0
    assert saved[0] == ("RESERVE", 1)
    completion = saved[1][2]
    assert completion.kind == "UNKNOWN" and completion.error == "ADAPTER_ERROR"
    assert completion.cost.amount is None and completion.usage.input_tokens is None
    assert wire.call_count == 1 and events(caplog)[0]["http_status"] == 402
    assert (await model.call()).error == "CLOSED" and wire.call_count == 1


def test_offline_exact_context_build_never_enters_http_or_changes_source(monkeypatch):
    cfg, run = offline_inputs()
    before = run.model_dump_json(), cfg.model_dump_json()
    blocked = Mock(side_effect=AssertionError("HTTP forbidden"))
    monkeypatch.setattr(httpx.AsyncClient, "stream", blocked)
    monkeypatch.setattr(PolzaAdapter, "complete", blocked)
    result = inspect(cfg, run, datetime.now(UTC))
    assert result["status"] == "OFFLINE_WIRE_VALID", result
    assert result["catalog_fresh_at_call"] and result["session_current_at_call"]
    assert result["model_posts"] == 0 and result["provider_acceptance"] == "NOT_TESTED"
    assert (run.model_dump_json(), cfg.model_dump_json()) == before
    assert str(run.run_id) not in json.dumps(result)
    blocked.assert_not_called()


def test_offline_historical_expiry_is_reported_without_renewing_window():
    cfg, run = offline_inputs()
    result = inspect(cfg, run, datetime.now(UTC) + timedelta(days=2))
    assert result["status"] == "OFFLINE_WIRE_VALID"
    assert result["catalog_fresh_at_call"] is False and result["session_current_at_call"] is False
    assert result["deadline_current_at_call"] is False


def test_offline_max_tokens_route_preserves_actual_wire_parameter(monkeypatch):
    raw = settings().review.model_dump()
    raw["catalog_entry"]["providers"][0]["supported_parameters"][-1] = "max_tokens"
    raw["catalog_sha256"] = fingerprint(raw["catalog_entry"])
    raw["output_cap_parameter"] = "max_tokens"
    route = RuntimeRoute.model_validate(raw)
    cfg, run = offline_inputs(
        review=route, review_sha256=fingerprint(route.model_dump(mode="json"))
    )
    original = PolzaAdapter.wire
    captured = []

    def capture(self, request):
        result = original(self, request)
        captured.append(json.loads(result))
        return result

    monkeypatch.setattr(PolzaAdapter, "wire", capture)
    assert inspect(cfg, run, datetime.now(UTC))["status"] == "OFFLINE_WIRE_VALID"
    assert captured and all(body["max_tokens"] == 512 for body in captured)
    assert all("max_completion_tokens" not in body for body in captured)
    assert all(body["provider"]["allow_fallbacks"] is False for body in captured)


def test_offline_wrong_config_and_private_invalid_snapshot_are_rejected():
    cfg, run = settings(), prepared()
    assert inspect(cfg, run, datetime.now(UTC))["status"] == "OFFLINE_CHECK_FAILED"
    scope = run.model_copy(update={"config": cfg.gateway()})
    assert inspect(cfg, scope, datetime.now(UTC))["status"] == "OFFLINE_CHECK_FAILED"
    cfg, run = offline_inputs()
    bad = run.model_copy(update={"snapshot": {"private": "do-not-log"}})
    result = inspect(cfg, bad, datetime.now(UTC))
    assert result["status"] == "OFFLINE_CHECK_FAILED" and "do-not-log" not in json.dumps(result)
