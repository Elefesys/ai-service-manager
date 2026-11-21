"""Customer wording and owner delivery reads for a frozen commercial offer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.service_requests.quotes import QuoteDeliveryView, QuoteInput, render_quote
from asm.service_requests.repository import ServiceRequestRepository
from pydantic import ValidationError


def uuid(index):
    return str(UUID(int=index))


def quote_payload(mode="FIXED_DEPOSIT", *, provisional=False, deposit=None, percent=None):
    intent = {"message_id": uuid(6), "source_version": "1" * 64}
    source = intent | {
        "quote": "Текст исходного сообщения",
        "analysis_id": None,
        "analysis_sha256": None,
    }
    return {
        "quote_id": uuid(10),
        "code": "Q-39BEE8CA10",
        "expires_at": "2026-11-21T11:15:00.000000Z",
        "material": {
            "workspace_id": uuid(1),
            "business_id": uuid(2),
            "conversation_id": uuid(3),
            "client_id": uuid(4),
            "request_id": uuid(5),
            "request_revision": "1",
            "service_id": "tattoo",
            "service_name": "Татуировка",
            "facts": [
                {
                    "field": "style",
                    "value": "Пока только предположение",
                    "status": "observed",
                    "source": source,
                    "confirmed_by": None,
                    "conflict": False,
                },
                {
                    "field": "idea",
                    "value": "Лист\nклёна",
                    "status": "client-stated",
                    "source": source,
                    "confirmed_by": None,
                    "conflict": False,
                },
            ],
            "intent_source": intent,
            "complex_work": None,
            "release_id": uuid(7),
            "activation_version": "2",
            "assessment_id": uuid(8),
            "assessment_reason": "FIXED_DURATION",
            "price_calculation_id": uuid(9),
            "price_reason": "SIZE_FORMULA" if provisional else "FIXED_PRICE",
            "approval_id": None,
            "decision_id": None,
            "price_reference_id": uuid(9),
            "duration_reference_id": uuid(8),
            "currency": "RUB",
            "amount_minor": None if provisional else 350_001,
            "price_range": (
                {"authority": "PROVISIONAL", "lower_minor": 350_001, "upper_minor": 510_050}
                if provisional
                else None
            ),
            "occupied_minutes": 65,
            "deposit_terms_version": uuid(7),
            "deposit": {"mode": mode, "amount_minor": deposit, "percent": percent},
            "conditions": [
                {"id": "max_size", "service_id": "tattoo", "kind": "MAX_SIZE_MM", "value": 100}
            ],
        },
    }


def test_exact_quote_shows_only_selected_confirmed_facts_and_published_terms():
    quote = QuoteInput.model_validate(quote_payload(deposit=50_050))
    assert render_quote(quote) == (
        "Предложение по работе «Татуировка»\n"
        "Идея — Лист клёна\n"
        "Цена — 3\u202f500,01 ₽.\n"
        "Длительность следующего сеанса — 65 мин.\n"
        "Предоплата — 500,50 ₽.\n"
        "Максимальный размер — 100 мм.\n"
        "Предложение действует до 21.11.2026 11:15:00 UTC.\n"
        "\n"
        "Чтобы принять предложение, отправьте команду\n"
        "Принимаю Q-39BEE8CA10"
    )


@pytest.mark.parametrize(
    ("mode", "deposit", "terms"),
    [
        ("NONE", None, "Предоплата не требуется."),
        ("FIXED_DEPOSIT", 50_050, "Предоплата — 500,50 ₽."),
    ],
)
def test_provisional_quote_keeps_both_bounds(mode, deposit, terms):
    quote = QuoteInput.model_validate(quote_payload(mode, provisional=True, deposit=deposit))
    message = render_quote(quote)
    assert "Предварительный диапазон цены — 3\u202f500,01–5\u202f100,50 ₽." in message
    assert terms in message


@pytest.mark.parametrize(
    ("mode", "deposit", "percent"),
    [
        ("PERCENT_DEPOSIT", None, 25),
        ("FULL_PREPAYMENT", None, None),
        ("FIXED_DEPOSIT", 350_002, None),
    ],
)
def test_range_requires_terms_applicable_to_every_amount(mode, deposit, percent):
    with pytest.raises(
        ValidationError, match="price conflicts with the published prepayment terms"
    ):
        QuoteInput.model_validate(
            quote_payload(mode, provisional=True, deposit=deposit, percent=percent)
        )


@pytest.mark.parametrize(
    ("mode", "percent", "terms"),
    [
        ("PERCENT_DEPOSIT", 25, "Предоплата — 25% от указанной цены."),
        ("FULL_PREPAYMENT", None, "Предоплата — полная стоимость работы."),
    ],
)
def test_exact_price_allows_percentage_and_full_prepayment(mode, percent, terms):
    quote = QuoteInput.model_validate(quote_payload(mode, percent=percent))
    assert terms in render_quote(quote)


def delivery_snapshot(status, reason=None):
    payload = quote_payload("NONE")
    quote = payload | {
        "version": "1",
        "created_at": "2026-11-20T11:15:00.000000Z",
        "terms_sha256": "a" * 64,
        "text": render_quote(QuoteInput.model_validate(payload)),
    }
    return {"quote": quote, "status": status, "reason": reason}


EXACT_PRICE_CLARIFICATION = {
    "quote": None,
    "status": "NEEDS_CLARIFICATION",
    "reason": "EXACT_PRICE_REQUIRED",
}


@pytest.mark.parametrize(
    ("status", "reason"),
    [("DISPATCHING", None), ("SENT", None), ("UNKNOWN", "UNKNOWN_EXTERNAL_RESULT")],
)
def test_read_quote_preserves_delivery_separately_from_current_clarification(status, reason):
    snapshot = delivery_snapshot(status, reason)
    current = QuoteDeliveryView.model_validate(snapshot)
    assert current.model_dump(mode="json") == snapshot
    blocked = EXACT_PRICE_CLARIFICATION | {"previous": snapshot}
    assert QuoteDeliveryView.model_validate(blocked).model_dump(mode="json") == blocked


def test_previous_snapshot_requires_current_exact_price_clarification():
    previous = delivery_snapshot("SENT")
    with pytest.raises(ValidationError, match="Previous delivery requires an exact price"):
        QuoteDeliveryView.model_validate(previous | {"previous": previous})
    with pytest.raises(ValidationError):
        QuoteDeliveryView.model_validate(
            EXACT_PRICE_CLARIFICATION | {"previous": EXACT_PRICE_CLARIFICATION}
        )


async def test_owner_read_rejects_previous_quote_from_a_different_work():
    previous = delivery_snapshot("SENT")
    previous["quote"]["material"]["request_id"] = uuid(11)
    unit = SimpleNamespace(
        context=SimpleNamespace(workspace_id=UUID(uuid(1))),
        quote_owner_read=AsyncMock(return_value=EXACT_PRICE_CLARIFICATION | {"previous": previous}),
    )
    repository = ServiceRequestRepository(unit)
    with pytest.raises(ServiceRequestError) as caught:
        await repository.read_quote(UUID(uuid(2)), UUID(uuid(3)), UUID(uuid(5)))
    assert caught.value.code == ServiceRequestCode.UNAVAILABLE
