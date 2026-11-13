"""v3 persistence/wire composition. Controlled stores are not PostgreSQL evidence."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from asm.ai.agent import KnowledgeConversationAgent
from asm.ai.contracts import GatewayConfig
from asm.ai.database import AIDatabase, PostgresKnowledgeAuthority, decoded, runtime_config
from asm.ai.fake import FakeAdapter
from asm.ai.polza import PolzaAdapter
from asm.ai.provider_runtime import ProviderRuntime
from asm.ai.runtime_contracts import (
    KnowledgeRuntimeReceipt,
    PreparedKnowledgeRun,
    PreparedRun,
    RuntimeReceipt,
    RuntimeStop,
)
from asm.messaging.errors import Code, MessagingError
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
from m5_knowledge_fixtures import ControlledKnowledgeAuthority, knowledge_run
from pydantic import ValidationError
from test_m4_polza import KEY
from test_m4_polza_runtime import Wire, settings


def knowledge_settings(**changes):
    return settings(
        prompt_revision="conversation_v3",
        data_profile="SYNTHETIC_PUBLISHED_KNOWLEDGE_V1",
        **changes,
    )


def test_explicit_new_provider_scope_preserves_legacy_admission_and_budget():
    legacy = settings()
    current = knowledge_settings()
    assert legacy.gateway().prompt_revision == "conversation_v2"
    assert "prompt_revision" not in legacy.admission()
    assert legacy.admission()["data_profile"] == "SYNTHETIC_TEXT_V1"
    assert "prompt_revision" not in current.admission()
    assert current.admission()["config"]["prompt_revision"] == "conversation_v3"
    assert current.admission()["data_profile"] == "SYNTHETIC_PUBLISHED_KNOWLEDGE_V1"
    assert current.gateway().limits == legacy.gateway().limits
    assert current.gateway().route == legacy.gateway().route
    for mismatch in (
        {"prompt_revision": "conversation_v3"},
        {"data_profile": "SYNTHETIC_PUBLISHED_KNOWLEDGE_V1"},
    ):
        with pytest.raises(ValueError, match="RUNTIME_ADMISSION_INVALID"):
            settings(**mismatch)


@pytest.mark.parametrize("published", [True, False])
def test_new_preparation_is_explicit_and_legacy_dto_stays_closed(published):
    run = knowledge_run(published=published)
    raw = run.model_dump(mode="json")
    assert decoded(PreparedKnowledgeRun, raw) == run
    assert run.knowledge_pin.activation_version == ("1" if published else "0")
    with pytest.raises(ValidationError):
        decoded(PreparedRun, raw)
    for target, field, value in (
        ("knowledge_pin", "business_id", str(uuid4())),
        ("knowledge_pin", "activation_version", "2"),
        ("active_projection", "workspace_id", str(uuid4())),
        ("config", "prompt_revision", "conversation_v2"),
    ):
        changed = run.model_dump(mode="json")
        changed[target][field] = value
        with pytest.raises(ValidationError):
            decoded(PreparedKnowledgeRun, changed)


async def test_prepare_requires_the_new_pin_and_projection_before_agent():
    run = knowledge_run()

    class Store(AIDatabase):
        async def _command(self, claim, operation, **payload):
            assert operation == "PREPARE"
            assert payload["config"]["prompt_revision"] == "conversation_v3"
            return run.model_dump(mode="json")

    store = Store(None, environment="TEST")
    assert await store.prepare(None, run.config, deadline=run.deadline) == run
    assert isinstance(store.authority(None, run), PostgresKnowledgeAuthority)
    assert runtime_config(run.config) == run.config
    for field in ("knowledge_pin", "active_projection"):
        raw = run.model_dump(mode="json")
        raw.pop(field)

        class Missing(Store):
            async def _command(self, *args, **kwargs):
                return raw

        with pytest.raises(ValidationError):
            await Missing(None, environment="TEST").prepare(None, run.config, deadline=run.deadline)


@pytest.mark.parametrize(
    "code,status", [(None, "ALLOWED"), (Code.AI_STALE, "STALE"), (Code.ACCESS_DENIED, "DENIED")]
)
async def test_new_authority_sends_claim_scope_and_pin_independently(code, status):
    run = knowledge_run()
    claim, calls = object(), []

    class Store:
        async def _command(self, principal, operation, **payload):
            calls.append((principal, operation, payload))
            if code:
                raise MessagingError(code)

    authority = PostgresKnowledgeAuthority(Store(), claim, run)
    foreign = run.binding.model_copy(update={"client_id": uuid4()})
    pin = run.knowledge_pin.model_copy(update={"activation_version": "42"})
    decision = await authority.authorize(foreign, pin, "MODEL")
    assert decision.status == status and decision.knowledge_pin == pin
    principal, operation, payload = calls[0]
    assert principal is claim and operation == "AUTHORIZE"
    assert payload["binding"]["client_id"] == str(foreign.client_id)
    assert payload["knowledge_pin"]["activation_version"] == "42"
    assert payload["run_id"] == str(run.run_id)


@pytest.mark.parametrize("knowledge", [False, True])
async def test_saved_receipt_replay_never_enters_model_or_preparation(knowledge):
    run = knowledge_run()
    raw = {
        "run_id": str(run.run_id),
        "job_id": str(run.binding.job_id),
        "turn_id": str(run.binding.turn_id),
        "turn_revision": run.binding.turn_revision,
        "selected_at": datetime.now(UTC).isoformat(),
        "result": {"kind": "reply", "text": "saved", "reason": None},
        "send_permit": False,
    }
    config = run.config
    if knowledge:
        raw["knowledge_pin"] = run.knowledge_pin.model_dump(mode="json")
    else:
        config = GatewayConfig.model_validate(
            config.model_dump() | {"prompt_revision": "conversation_v2"}
        )

    class Store(AIDatabase):
        async def prepare(self, *args, **kwargs):
            raise AssertionError("replay attempted model preparation")

    class Messaging:
        async def replay_ai(self, *args):
            return raw

    adapter = FakeAdapter(config.route)
    result = await Store(Messaging(), environment="TEST").execute(
        SimpleNamespace(job_id=uuid4(), claim_token=uuid4()),
        config,
        adapter,
        deadline=run.deadline,
    )
    assert isinstance(result, KnowledgeRuntimeReceipt if knowledge else RuntimeReceipt)
    assert not result.send_permit and adapter.requests == []


async def test_incomplete_saved_reservation_does_not_regenerate_on_restart():
    run = knowledge_run()
    used = run.model_copy(update={"budget": run.budget.model_copy(update={"calls_used": 1})})

    class Store(AIDatabase):
        async def replay(self, *args):
            raise MessagingError(Code.STALE_CLAIM)

        async def prepare(self, *args, **kwargs):
            return used

    adapter = FakeAdapter(run.config.route)
    for _ in range(2):
        outcome = await Store(None, environment="TEST").execute(
            None, run.config, adapter, deadline=run.deadline
        )
        assert isinstance(outcome, RuntimeStop) and outcome.reason == "INCOMPLETE"
    assert adapter.requests == []


@pytest.mark.parametrize("read", [False, True])
async def test_actual_polza_wire_accepts_v3_data_and_correlated_read_locally(read):
    run = knowledge_run()
    admitted = knowledge_settings()
    wire = Wire(read=read)
    adapter = PolzaAdapter(
        admitted.review,
        KEY,
        transport=httpx.MockTransport(wire),
        history_profile="gpt_eval_history_v2",
    )
    authority = ControlledKnowledgeAuthority(run, allowed=True)
    agent = KnowledgeConversationAgent(
        admitted.gateway(),
        adapter,
        authority,
        knowledge_pin=run.knowledge_pin,
        active_projection=run.active_projection,
    )
    outcome = await agent.run(
        run.binding, run.snapshot, run_id=str(run.run_id), deadline=run.deadline
    )
    assert outcome.candidate is not None and len(wire.posts) == 1 + read
    assert len(wire.gets) == 2 * (1 + read)
    assert len(authority.reads) == read and not outcome.runtime_authorized
    body = json.dumps(wire.posts, ensure_ascii=False)
    assert "conversation_v3" in wire.posts[0]["messages"][0]["content"]
    assert "Synthetic tattoo consultation" in body
    assert "Synthetic owner-confirmed instruction" in body
    for private in (run.knowledge_pin.release_id, run.binding.client_id, run.binding.business_id):
        assert str(private) not in body
    assert all(post["max_completion_tokens"] <= 512 for post in wire.posts)


async def test_provider_v3_cannot_enable_live_transport_from_a_new_settings_file(
    monkeypatch, tmp_path
):
    settings = knowledge_settings()
    telegram = TelegramClient(
        TelegramSettings(
            ASM_ENVIRONMENT="TEST",
            ASM_TELEGRAM_ENABLED=True,
            TG_BOT_TOKEN=settings.bot_identity + ":synthetic_token_123456789",
            TG_WEBHOOK_SECRET="synthetic_webhook_secret_123",
            ASM_TELEGRAM_EXPECTED_BOT_ID=settings.bot_identity,
            ASM_TELEGRAM_WEBHOOK_URL="https://test.invalid/webhooks/telegram",
        ),
        provider_runtime=settings,
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("HTTP"))
        ),
    )

    def denied(path):
        raise AssertionError("v3 live composition read a key")

    monkeypatch.setattr("asm.ai.provider_runtime.load_key", denied)
    try:
        with pytest.raises(MessagingError, match="NOT_ALLOWED"):
            ProviderRuntime(
                None, settings, environment="TEST", key_file=tmp_path / "key", telegram=telegram
            )
    finally:
        await telegram.aclose()
