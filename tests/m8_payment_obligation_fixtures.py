"""Use the existing M6 acceptance and M7 booking path for P1."""

import json
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from asm.scheduling.commands import HoldResult
from m7_scheduling_fixtures import Work, accept_quote, prepare_quote
from test_m3_1_native_context_postgres import scalar
from test_m6_owner_decisions_postgres import FIXED_DURATION, contract
from test_m6_pricing_postgres import draft_for_size, publish
from test_m6_service_requests_api_postgres import route
from test_m7_scheduling_holds_postgres import configure, offer, pick
from test_m7_scheduling_reschedule_postgres import NO_BUFFERS, option_at


def fixed_price(amount):
    return {"mode": "FIXED", "amount_minor": amount, "formula_note": None}


def terms(mode, price, *, amount=None, percent=None):
    bundle = contract(price, FIXED_DURATION, mode)
    bundle["services"][0]["deposit"].update(amount_minor=amount, percent=percent)
    return bundle


async def send_terms(h, auth, token, mode, price, *, amount=None, percent=None):
    await publish(h, terms(mode, price, amount=amount, percent=percent))
    conversation, _, _, _, request = await draft_for_size(h, auth, token, "21 mm")
    url = f"{route(conversation)}/{request}"
    return url, await prepare_quote(h, auth, token, url)


async def accept_terms(h, auth, token, mode, price, *, amount=None, percent=None):
    url, quote = await send_terms(h, auth, token, mode, price, amount=amount, percent=percent)
    return await accept_quote(h, auth, url, quote)


def endpoint(work: Work, hold_id: str, **overrides):
    params = (
        dict(
            client_id=work.selection.client_id,
            quote_id=work.selection.quote_id,
            order_id=work.selection.order_id,
            hold_id=hold_id,
        )
        | overrides
    )
    path = work.booking_url().partition("?")[0].removesuffix("/booking") + "/payment-obligation"
    return path, params


def get_path(work, hold_id, **overrides):
    path, params = endpoint(work, hold_id, **overrides)
    return f"{path}?{urlencode(params)}"


async def post_open(auth, token, work, hold_id, key, **overrides):
    path, params = endpoint(work, hold_id, **overrides)
    return await auth.client.post(path, json=params, headers=token | {"Idempotency-Key": key})


async def hold_work(h, work, day, key="initial", *, at="10:00"):
    issued = await offer(h, work, day, f"{key}-offer")
    option = option_at(issued, at)
    selected = await pick(h, work, UUID(option.option_id), f"{key}-select")
    assert isinstance(selected, HoldResult)
    return selected


async def prepare_day(h, auth, token, work):
    current, _ = await configure(h, auth, token, work, policy=NO_BUFFERS)
    return current + timedelta(days=1)


async def money_counts(h):
    return await scalar(
        h,
        """
        SELECT jsonb_build_object(
          'obligations',(SELECT count(*) FROM app.payment_obligations),
          'receipts',(SELECT count(*) FROM platform.payment_obligation_receipts))
    """,
    )


def inspect_open(reply, work, hold, *, amount, price, status="HELD"):
    assert reply["hold_id"] == hold.hold_id
    assert reply["allocation_id"] == hold.allocation_id
    assert datetime.fromisoformat(reply["expires_at"]) == hold.expires_at
    assert reply["requires_prepayment"] and reply["hold_status"] == status
    payment = reply["obligation"]
    quote = work.agreement["quote"]
    assert payment["status"] == "UNPAID" and payment["currency"] == "RUB"
    assert payment["acceptance_id"] == work.agreement["acceptance_id"]
    assert payment["quote_version"] == quote["version"]
    assert payment["terms_sha256"] == quote["terms_sha256"]
    assert payment["deposit_terms_version"] == work.material["deposit_terms_version"]
    assert payment["mode"] == work.material["deposit"]["mode"]
    assert payment["amount_minor"] == amount and payment["price_minor"] == price
    assert payment["price_range"] == work.material["price_range"]
    return payment


def proof(case, **fields):
    print("M8.1A P1", json.dumps({"case": case, **fields}, default=str, ensure_ascii=False))
