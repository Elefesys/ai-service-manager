"""Scheduling authority stays outside the versioned model response."""

from datetime import UTC, date, datetime, timedelta

import pytest
from asm.ai.contracts import (
    SchedulingIntentGatewayConfig,
    SchedulingIntentResult,
    ServiceIntentGatewayConfig,
    validate_conversation_result,
)
from asm.scheduling.conversation import _day, _period, _work
from test_m4_agent import config


def test_v9_scheduling_intent_has_only_preference_and_source():
    admission = config().model_dump()
    v8 = ServiceIntentGatewayConfig.model_validate(
        admission
        | {"prompt_revision": "conversation_v8", "schema_revision": "conversation_result_v4"}
    )
    v9 = SchedulingIntentGatewayConfig.model_validate(
        admission
        | {"prompt_revision": "conversation_v9", "schema_revision": "conversation_result_v5"}
    )
    old = {
        "kind": "reply",
        "text": "Вопрос по услуге",
        "reason": None,
        "intake": {
            "service_id": None,
            "category": "FAQ_ONLY",
            "facts": [],
            "switch_request": False,
        },
    }
    assert validate_conversation_result(v8, old) == validate_conversation_result(v9, old)
    query = {
        "kind": "no_reply",
        "text": None,
        "reason": "SCHEDULING",
        "scheduling": {
            "name": "list_availability",
            "period": "AFTERNOON",
            "source": {
                "message_id": "00000000-0000-0000-0000-000000001234",
                "source_version": "b" * 64,
            },
        },
    }
    assert isinstance(validate_conversation_result(v9, query), SchedulingIntentResult)
    with pytest.raises(ValueError):
        validate_conversation_result(v8, query)
    for field in ("option_id", "session_id", "date", "timezone", "duration", "deposit", "code"):
        with pytest.raises(ValueError):
            validate_conversation_result(
                v9, query | {"scheduling": query["scheduling"] | {field: "forged"}}
            )


def test_resolve_local_tomorrow_from_source_at_midnight_and_ask_when_ambiguous():
    zone = "Asia/Novosibirsk"
    before = datetime(2026, 11, 25, 16, 59, 59, tzinfo=UTC)
    assert _day("Завтра после обеда", before, zone) == date(2026, 11, 26)
    assert _day("Завтра после обеда", before + timedelta(seconds=1), zone) == date(2026, 11, 27)
    assert _day("Завтра или послезавтра", before, zone) is None
    assert _day("Завтра, либо в субботу", before, zone) is None
    assert _period("после обеда", "AFTERNOON") == "AFTERNOON"
    assert _period("завтра утром или после обеда", "AFTERNOON") is None
    assert _period("завтра", "AFTERNOON") is None

    rose = {"title": "роза", "service_name": "Татуировка", "request_id": "rose"}
    swallow = {"title": "ласточка", "service_name": "Татуировка", "request_id": "swallow"}
    assert _work("Когда можно на розу завтра?", [rose, swallow]) == rose
    assert _work("Завтра на розу и ласточку?", [rose, swallow]) is None
    assert _work("Когда можно завтра?", [rose, swallow]) is None
