"""Synthetic checkout wire and scoped payment scenarios shared by P2."""

import hashlib
import json
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from asm.client_payments.checkout import Checkout
from asm.client_payments.yookassa import TestShop, YooKassa
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import worker_active
from asm.messaging.errors import Code
from asm.messaging.models import OutcomeKind, SendOutcome
from asm.messaging.worker import Worker
from m8_payment_obligation_fixtures import accept_terms, endpoint, fixed_price
from test_m3_1_native_context_postgres import claim_job
from test_m6_pricing_postgres import sign_in
from test_m7_scheduling_holds_postgres import command_http
from test_m7_scheduling_intents_postgres import SchedulingChat, configure_wide, offered, scope_for
from test_tenancy_postgres import BA, A

SHOP = TestShop(
    A, BA, "100500", "https://console.example.test/payment-return", "test_synthetic_receipt"
)


class SimulatedCrash(BaseException):
    pass


class ProviderWire:
    def __init__(self):
        self.requests = []
        self.objects = {}
        self.start = None
        self.after_create = None
        self.first = None
        self.status = "pending"
        self.with_link = True
        self.confirmed = True

    def payment_view(self, old):
        return old | (
            {
                "confirmation": {
                    "type": "redirect",
                    "confirmation_url": f"https://yoomoney.ru/checkout/{old['id']}",
                }
            }
            if self.with_link and old["status"] == "pending"
            else {}
        )

    async def call(self, request):
        assert not worker_active()
        assert request.url.host == "api.yookassa.ru"
        self.requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Idempotence-Key"),
                hashlib.sha256(request.content).hexdigest(),
            )
        )
        if request.method == "GET" and request.url.path == "/v3/payments":
            return httpx.Response(
                200 if self.confirmed else 401, json={"type": "list", "items": []}
            )
        if request.method == "GET":
            old = next(row for row in self.objects.values() if request.url.path.endswith(row["id"]))
            return httpx.Response(200, json=self.payment_view(old))
        if self.start is not None:
            await self.start()
        key = request.headers["Idempotence-Key"]
        saved = self.objects.setdefault(
            key,
            {
                "id": str(uuid4()),
                "test": True,
                "status": self.status,
                "paid": self.status == "succeeded",
                "recipient": {"account_id": SHOP.shop_id},
                "amount": json.loads(request.content)["amount"],
                "metadata": json.loads(request.content)["metadata"],
            },
        )
        if self.after_create is not None:
            await self.after_create()
        if self.first is not None:
            effect, self.first = self.first, None
            if effect == "timeout":
                raise httpx.ReadTimeout("simulated response loss")
            if effect == "http500":
                return httpx.Response(500)
            if effect == "crash":
                raise SimulatedCrash
        return httpx.Response(200, json=self.payment_view(saved))

    def counters(self, wire):
        return {
            "post": sum(method == "POST" for method, *_ in self.requests),
            "payment_get": sum(
                method == "GET" and path != "/v3/payments" for method, path, *_ in self.requests
            ),
            "shop_get": sum(
                method == "GET" and path == "/v3/payments" for method, path, *_ in self.requests
            ),
            "objects": len(self.objects),
            "send_calls": wire.calls,
            "delivered": wire.effects,
        }


class PaymentWire(ControlledAdapter):
    def __init__(self, *, barrier=None, lose_ack=False):
        super().__init__(environment="TEST", barrier=barrier)
        self.delivered = []
        self.lose_ack = lose_ack

    async def send(self, permit):
        assert not worker_active()
        self.delivered.append(permit)
        outcome = await super().send(permit)
        assert outcome.kind is OutcomeKind.SUCCESS
        if self.lose_ack:
            return SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT)
        return outcome


async def checkout_worker(h, provider, *, transport=None):
    wire = transport or PaymentWire()
    adapter = YooKassa(environment="TEST", transport=httpx.MockTransport(provider.call))
    checkout = Checkout(h.kernel, adapter)
    assert await checkout.register((SHOP,)) == int(provider.confirmed)
    return Worker(h.kernel, wire, checkout=checkout), adapter


def checkout_path(work, hold, **overrides):
    path, refs = endpoint(work, hold, **overrides)
    return path.removesuffix("/payment-obligation") + "/payment-checkout", refs


async def open_checkout(auth, token, work, hold, key, **overrides):
    path, refs = checkout_path(work, hold, **overrides)
    return await command_http(auth, token, path, key, refs)


async def read_checkout(auth, work, hold, **overrides):
    path, refs = checkout_path(work, hold, **overrides)
    return await auth.client.get(path + "?" + urlencode(refs))


async def accept_work(h, auth, *, amount=50_000):
    token = await sign_in(auth)
    work = await accept_terms(h, auth, token, "FIXED_DEPOSIT", fixed_price(400_000), amount=amount)
    await configure_wide(h, auth, token, work)
    return token, work


async def chat_choice(h, work):
    conversation = UUID(work.selection.conversation_id)
    chat = SchedulingChat(h, conversation, await scope_for(h, conversation))
    _, _, listing = await chat.say("На завтра после обеда")
    option = offered(listing)["options"][0]
    choice = f"Выбираю {option['code']}"
    inbound, _, chosen = await chat.say(choice)
    return chat, choice, inbound, chosen


async def run_checkout(h, worker, attempt):
    await worker.execute(await claim_job(h, attempt["send_job_id"]))


def proof(case, **fields):
    print(
        "M8.1B P2",
        json.dumps({"case": case, **fields}, default=str, ensure_ascii=False),
        flush=True,
    )
