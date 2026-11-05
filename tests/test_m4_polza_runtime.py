"""Actual Polza HTTP codec/Gateway/agent, mock HTTP; no PostgreSQL claim here."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from asm.ai.agent import ConversationAgent
from asm.ai.polza import HISTORY_LIST, PolzaAdapter, RuntimeRoute, fingerprint
from asm.ai.runtime_settings import RuntimeSettings, load_key, load_settings
from asm.foundation import create_worker
from asm.messaging.errors import MessagingError
from test_m4_agent import ControlledAuthority, run
from test_m4_context import fixture
from test_m4_polza import KEY, experiment_history, payload, response, review


def settings(**changes):
    reviewed = review().model_dump()
    entry = reviewed["catalog_entry"]
    entry["providers"][0]["name"] = "openai/flex"
    reviewed.update(
        provider_name="openai/flex",
        response_provider="OpenAI",
        catalog_sha256=fingerprint(entry),
        history={"provider": "OpenAI", "evidence": "OFFLINE MOCK ONLY; not a live review"},
    )
    route = RuntimeRoute.model_validate(reviewed)
    now = datetime.now(UTC)
    values = dict(
        session_id=uuid4(),
        workspace_id=uuid4(),
        client_id=uuid4(),
        conversation_id=uuid4(),
        connection_id=uuid4(),
        chat_id="1234",
        bot_identity="10001",
        starts_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=10),
        data_profile="SYNTHETIC_TEXT_V1",
        max_calls=4,
        max_rub=Decimal(10),
        review=route,
        review_sha256=fingerprint(route.model_dump(mode="json")),
    )
    return RuntimeSettings(**(values | changes))


class Wire:
    def __init__(self, kind="reply", *, read=False, failure=None):
        self.kind, self.read, self.failure = kind, read, failure
        self.posts, self.gets = [], []
        self.latest = None
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.wait = False

    async def __call__(self, request):
        if request.method == "POST":
            body = json.loads(request.content)
            self.posts.append(body)
            self.started.set()
            assert body["model"] == "openai/gpt-6-luna"
            assert body["provider"]["only"] == ["openai/flex"]
            assert body["provider"]["allow_fallbacks"] is False
            assert len(request.content) <= 24576 and body["max_completion_tokens"] <= 512
            if self.wait:
                await self.release.wait()
            if self.failure == "timeout":
                raise httpx.ReadTimeout("CONTROLLED")
            if self.failure == "cancel":
                raise asyncio.CancelledError
            tools = self.read and len(self.posts) == 1
            self.latest = payload(tools=tools)
            self.latest.update(id="gen_" + str(700 + len(self.posts)), provider="OpenAI")
            if self.failure == "cost":
                self.latest["usage"]["cost_rub"] = 10
            message = self.latest["choices"][0]["message"]
            if tools:
                message["tool_calls"][0]["function"] = {
                    "name": "read_context",
                    "arguments": '{"query":"current"}',
                }
            else:
                result = {
                    "kind": self.kind,
                    "text": "Синтетический ответ" if self.kind == "reply" else None,
                    "reason": None if self.kind == "reply" else "Требуется владелец",
                }
                message["content"] = (
                    "invalid" if self.failure == "schema" else json.dumps({"result": result})
                )
            return response(self.latest)
        self.gets.append(str(request.url))
        listing, detail = experiment_history(self.latest)
        if self.failure == "metadata":
            detail["attemptsCount"] = 0
        return response(listing if str(request.url) == HISTORY_LIST else detail)


@pytest.mark.parametrize(
    "kind,read", [("reply", False), ("reply", True), ("handoff", False), ("no_reply", False)]
)
async def test_real_polza_agent_closed_route_and_read(kind, read):
    cfg = settings()
    wire = Wire(kind, read=read)
    adapter = PolzaAdapter(
        cfg.review, KEY, transport=httpx.MockTransport(wire), history_profile="gpt_eval_history_v2"
    )
    raw, binding = fixture("v3_owner")
    authority = ControlledAuthority(binding, raw, allowed=True)
    result = await run(ConversationAgent(cfg.gateway(), adapter, authority), raw, binding)
    assert result.status == "CANDIDATE", result
    assert result.candidate.kind == kind and not result.runtime_authorized
    assert len(wire.posts) == 1 + read and len(wire.gets) == 2 * (1 + read)
    assert len(authority.reads) == read
    assert adapter.observation["history_family"] == "OpenAI"
    assert adapter.observation["route_variant"] == "NOT_OBSERVED"


@pytest.mark.parametrize("failure", ["schema", "metadata", "timeout", "cancel"])
async def test_provider_failure_stops_before_candidate_or_followup(failure):
    cfg, wire = settings(), Wire(failure=failure)
    adapter = PolzaAdapter(
        cfg.review, KEY, transport=httpx.MockTransport(wire), history_profile="gpt_eval_history_v2"
    )
    raw, binding = fixture("v3_owner")
    authority = ControlledAuthority(binding, raw, allowed=True)
    result = await run(ConversationAgent(cfg.gateway(), adapter, authority), raw, binding)
    assert result.candidate is None and len(wire.posts) == 1 and not authority.reads


@pytest.mark.parametrize(
    "change",
    [
        {"max_calls": 5},
        {"max_rub": Decimal(11)},
        {"data_profile": "REAL_CLIENTS"},
        {"review_sha256": "0" * 64},
        {"chat_id": "different"},
        {"expires_at": datetime.now(UTC) + timedelta(hours=1)},
    ],
)
def test_invalid_finite_admission(change):
    with pytest.raises(ValueError):
        settings(**change)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "google/gemini-3.5-flash"),
        ("provider_name", "openai/other"),
        ("response_provider", "other"),
    ],
)
def test_runtime_never_inherits_other_probe_routes(field, value):
    cfg = settings()
    route = RuntimeRoute.model_validate(cfg.review.model_dump() | {field: value})
    with pytest.raises(ValueError):
        route.route()


def test_expired_session_and_default_off():
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="EXPIRED"):
        settings(
            starts_at=now - timedelta(minutes=2), expires_at=now - timedelta(seconds=1)
        ).current()
    worker = create_worker(None, None, environment="TEST")
    assert worker.ai is None
    with pytest.raises(MessagingError):
        create_worker(None, None, environment="TEST", provider_settings=settings())


def test_private_sources_and_offline_plan(tmp_path, monkeypatch):
    from scripts.m4_runtime_pilot import plan

    path = tmp_path / "key"
    path.write_text(KEY.get_secret_value())
    path.chmod(0o600)
    assert load_key(path) == KEY
    path.chmod(0o644)
    with pytest.raises(ValueError, match="RUNTIME_SECRET_INVALID"):
        load_key(path)
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        load_key(link)
    cfg = settings()
    config = tmp_path / "config.json"
    config.write_text(cfg.model_dump_json())
    config.chmod(0o600)

    def denied(*a, **k):
        raise AssertionError("offline plan attempted HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "send", denied)
    result = plan(load_settings(config))
    assert result["max_model_posts"] == 4 and result["max_session_rub"] == "10"
    assert result["live_authorized"] is False and KEY.get_secret_value() not in json.dumps(result)
