"""Provider response, origin and TEST shop admission without network access."""

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from asm.client_payments.yookassa import CheckoutRequest, YooKassa
from m8_payment_checkout_fixtures import SHOP


def checkout_request(shop=SHOP):
    attempt = uuid4()
    body = json.dumps(
        {
            "amount": {"value": "500.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": shop.return_url},
            "payment_method_data": {"type": "bank_card"},
            "metadata": {"asm_attempt_id": str(attempt)},
            "description": "Предоплата за визит",
        },
        ensure_ascii=False,
    )
    return CheckoutRequest(
        attempt, uuid4(), body, hashlib.sha256(body.encode()).hexdigest(), 50_000
    )


@pytest.mark.parametrize(
    "change",
    [
        {"test": False},
        {"recipient": {"account_id": "100501"}},
        {"amount": {"value": "499.00", "currency": "RUB"}},
        {"amount": {"value": "500.00", "currency": "USD"}},
        {"metadata": {"asm_attempt_id": "foreign"}},
        {"paid": True},
    ],
)
async def test_authentic_response_must_describe_this_test_payment(change):
    request = checkout_request()
    data = {
        "id": str(uuid4()),
        "test": True,
        "status": "pending",
        "paid": False,
        "recipient": {"account_id": SHOP.shop_id},
        "amount": {"value": "500.00", "currency": "RUB"},
        "metadata": {"asm_attempt_id": str(request.attempt_id)},
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=data | change))
    adapter = YooKassa(environment="TEST", transport=transport)
    try:
        assert await adapter.payment(SHOP, request) is None
    finally:
        await adapter.aclose()


@pytest.mark.parametrize(
    "link",
    [
        "http://yoomoney.ru/pay",
        "https://yoomoney.ru.example.test/pay",
        "https://user@yoomoney.ru/pay",
        "https://yoomoney.ru:444/pay",
        "https://yoomoney.ru/path#fragment",
        "https://127.0.0.1/pay",
    ],
)
async def test_unapproved_link_keeps_known_id_for_get(link):
    request = checkout_request()
    data = {
        "id": str(uuid4()),
        "test": True,
        "status": "pending",
        "paid": False,
        "recipient": {"account_id": SHOP.shop_id},
        "amount": {"value": "500.00", "currency": "RUB"},
        "metadata": {"asm_attempt_id": str(request.attempt_id)},
        "confirmation": {"type": "redirect", "confirmation_url": link},
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    adapter = YooKassa(environment="TEST", transport=transport)
    try:
        payment = await adapter.payment(SHOP, request)
        assert payment is not None and payment.id == data["id"] and payment.link is None
    finally:
        await adapter.aclose()


async def test_rejects_live_key_and_wrong_request_before_any_post():
    with pytest.raises(ValueError):
        replace(SHOP, secret="live_synthetic_key")
    with pytest.raises(ValueError):
        YooKassa(environment="LOCAL")
    calls = []

    def request_seen(request):
        calls.append(request.method)
        return httpx.Response(401)

    adapter = YooKassa(environment="TEST", transport=httpx.MockTransport(request_seen))
    try:
        assert not await adapter.verify_shop(SHOP)
        for request in [
            replace(checkout_request(), amount_minor=99),
            replace(checkout_request(), sha256="0" * 64),
            checkout_request(replace(SHOP, return_url="https://other.example.test/payment-return")),
        ]:
            assert await adapter.payment(SHOP, request) is None
        assert calls == ["GET"]
    finally:
        await adapter.aclose()
