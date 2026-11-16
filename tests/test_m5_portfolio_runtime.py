"""Explicit finite v5 composition. No unit test claims database authority."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from asm.ai.database import AIDatabase, decoded, runtime_config
from asm.ai.runtime import PortfolioSyntheticRuntime
from asm.ai.runtime_contracts import PortfolioQueryReservation, QueryReservation
from asm.ai.runtime_settings import PortfolioRuntimeSettings, RuntimeSettings
from asm.foundation import create_worker
from asm.messaging.errors import MessagingError
from pydantic import ValidationError
from test_m5_portfolio_context import setup


def settings():
    s = setup()
    return PortfolioRuntimeSettings(
        session_id=uuid4(),
        workspace_id=s.old.binding.workspace_id,
        business_id=s.old.binding.business_id,
        client_id=s.old.binding.client_id,
        conversation_id=s.old.binding.conversation_id,
        data_profile="SYNTHETIC_VISION_PORTFOLIO_V1",
        expires_at=datetime.now(UTC) + timedelta(seconds=120),
        max_calls=4,
        max_cost=Decimal(10),
        config=s.config,
    )


def test_v5_requires_new_explicit_test_anchor_and_preserves_disabled_default():
    s = settings()
    db = SimpleNamespace()
    worker = create_worker(db, SimpleNamespace(), environment="TEST")
    assert worker.ai is None
    with pytest.raises((MessagingError, ValueError)):
        runtime_config(s.config)
    old = AIDatabase(db, environment="TEST", delivery=True)
    with pytest.raises(MessagingError):
        old.config(s.config)
    current = create_worker(
        db,
        SimpleNamespace(),
        environment="TEST",
        portfolio_settings=s,
        model=lambda: setup().adapter,
    )
    assert type(current.ai) is PortfolioSyntheticRuntime
    assert not current.ai.database.embeddings.enabled
    assert current.ai.database.portfolio_session_id == s.session_id
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(s.model_dump())


@pytest.mark.parametrize("damage", ["local", "no_delivery", "provider", "string_id"])
def test_anchor_cannot_enter_old_local_or_provider_paths(damage):
    kwargs = {"environment": "TEST", "delivery": True, "portfolio_session_id": uuid4()}
    if damage == "local":
        kwargs["environment"] = "LOCAL"
    elif damage == "no_delivery":
        kwargs["delivery"] = False
    elif damage == "provider":
        kwargs["provider"] = SimpleNamespace()
    else:
        kwargs["portfolio_session_id"] = str(uuid4())
    with pytest.raises(MessagingError):
        AIDatabase(SimpleNamespace(), **kwargs)


@pytest.mark.parametrize("damage", ["profile", "expiry", "calls", "cost", "currency", "provider"])
def test_portfolio_settings_remain_finite_and_synthetic(damage):
    raw = settings().model_dump(mode="json")
    if damage == "profile":
        raw["data_profile"] = "SYNTHETIC_TEXT_ONLY_V1"
    elif damage == "expiry":
        raw["expires_at"] = (datetime.now(UTC) + timedelta(seconds=901)).isoformat()
    elif damage == "calls":
        raw["max_calls"] = 5
    elif damage == "cost":
        raw["max_cost"] = "10.01"
    elif damage == "currency":
        raw["config"]["limits"]["currency"] = "USD"
    else:
        raw["config"]["route"]["execution"] = "PROVIDER"
    with pytest.raises(ValueError):
        value = decoded(PortfolioRuntimeSettings, raw)
        value.current()


def test_new_query_deadline_accepts_sql_timezone_without_reinterpreting_old_dto():
    raw = {
        "status": "RESERVED",
        "call_id": str(uuid4()),
        "ticket": str(uuid4()),
        "wire": "{}",
        "wire_sha256": "a" * 64,
        "profile_id": "polza_openai_text_embedding3small_1536_cosine_v1",
        "deadline": "2030-01-01T01:00:00+00:00",
        "reserved_cost": "0.08",
        "currency": "RUB",
    }
    assert decoded(PortfolioQueryReservation, raw).deadline.tzinfo is not None
    with pytest.raises(ValidationError):
        decoded(QueryReservation, raw)
    with pytest.raises(ValidationError):
        decoded(PortfolioQueryReservation, raw | {"deadline": "2030-01-01T01:00:00"})
