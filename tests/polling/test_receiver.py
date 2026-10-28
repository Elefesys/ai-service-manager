import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx

from scripts.telegram_polling_receiver import (
    ALLOWED_UPDATES,
    MAX_EVENT,
    MAX_RESPONSE,
    LocalIngress,
    PollingError,
    Receiver,
    Wire,
    strict_json,
)


def event(identifier=11):
    return {"update_id": identifier, "business_message": {"text": "private example"}}


class Provider:
    """Provider keeps each event until a later getUpdates offset confirms it."""

    def __init__(self, events):
        self.events = list(events)
        self.offsets = []
        self.fail = None
        self.confirm_then_fail = False

    async def poll(self, offset):
        self.offsets.append(offset)
        if self.fail and not self.confirm_then_fail:
            raise self.fail
        if offset is not None:
            self.events = [x for x in self.events if x["update_id"] >= offset]
        if self.fail:
            raise self.fail
        return self.events[:1]


class DurableIngress:
    """Models the existing receipt transaction, including lost response after commit."""

    def __init__(self):
        self.receipts = set()
        self.calls = []
        self.fail_before = None
        self.fail_after = None

    async def accept(self, update):
        self.calls.append(update["update_id"])
        if self.fail_before:
            raise self.fail_before
        self.receipts.add(update["update_id"])
        if self.fail_after:
            raise self.fail_after


class ReceiverTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_expected_webhook_removal_before_polling(self):
        calls, states = [], []

        async def identity():
            calls.append("identity")

        async def ready():
            calls.append("ready")

        async def webhook():
            calls.append("webhook")
            return "https://expected.invalid" if calls.count("webhook") == 1 else ""

        async def poll(offset):
            calls.append("poll")
            return []

        async def sleep(delay):
            calls.append(delay)
            if delay == 0.25:
                raise asyncio.CancelledError

        receiver = Receiver(
            SimpleNamespace(identity=identity, webhook=webhook, poll=poll),
            SimpleNamespace(ready=ready),
            states.append,
        )
        with mock.patch("scripts.telegram_polling_receiver.asyncio.sleep", sleep):
            with self.assertRaises(asyncio.CancelledError):
                await receiver.run()
        self.assertEqual(
            calls, ["identity", "ready", "webhook", 2, "identity", "ready", "webhook", "poll", 0.25]
        )
        self.assertEqual([x["state"] for x in states], ["WAITING_WEBHOOK_REMOVAL", "RUNNING"])

    async def test_conflict_retries_with_backoff_and_never_mutates_webhook(self):
        wire = mock.AsyncMock()
        wire.webhook.return_value = ""
        wire.poll.side_effect = PollingError("RECEIVER_CONFLICT")
        states, delays = [], []

        async def sleep(delay):
            delays.append(delay)
            if len(delays) == 3:
                raise asyncio.CancelledError

        receiver = Receiver(wire, mock.AsyncMock(), states.append)
        with mock.patch("scripts.telegram_polling_receiver.asyncio.sleep", sleep):
            with self.assertRaises(asyncio.CancelledError):
                await receiver.run()
        self.assertEqual(delays, [2, 4, 8])
        self.assertEqual(wire.poll.call_args_list, [mock.call(None)] * 3)
        self.assertEqual([x["state"] for x in states], ["BLOCKED"] * 3)
        self.assertEqual({x[0] for x in wire.method_calls}, {"identity", "webhook", "poll"})

    async def test_offset_follows_durable_ack_and_empty_reply_resets_it(self):
        provider, ingress = Provider([event(11), event(12)]), DurableIngress()
        receiver = Receiver(provider, ingress, lambda _: None)
        await receiver.step()
        self.assertEqual(provider.offsets, [None])
        self.assertEqual(ingress.receipts, {11})
        self.assertEqual(len(provider.events), 2)
        await receiver.step()
        self.assertEqual(provider.offsets, [None, 12])
        self.assertEqual(ingress.receipts, {11, 12})
        await receiver.step()
        await receiver.step()
        self.assertEqual(provider.offsets, [None, 12, 13, None])
        self.assertEqual(provider.events, [])

    async def test_commit_then_response_loss_replays_without_duplicate_effect(self):
        provider, ingress = Provider([event()]), DurableIngress()
        receiver = Receiver(provider, ingress, lambda _: None)
        ingress.fail_after = PollingError("LOCAL_INGRESS_TIMEOUT")
        with self.assertRaises(PollingError):
            await receiver.step()
        self.assertEqual(provider.offsets, [None])
        self.assertEqual(ingress.receipts, {11})
        self.assertIsNone(receiver.pending)
        ingress.fail_after = None
        await receiver.step()
        await receiver.step()
        self.assertEqual(provider.offsets, [None, None, 12])
        self.assertEqual(ingress.calls, [11, 11])
        self.assertEqual(ingress.receipts, {11})

    async def test_local_rejection_and_cancel_never_advance_offset(self):
        for error in (PollingError("LOCAL_INGRESS_REJECTED"), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                provider, ingress = Provider([event()]), DurableIngress()
                receiver = Receiver(provider, ingress, lambda _: None)
                ingress.fail_before = error
                with self.assertRaises(type(error)):
                    await receiver.step()
                self.assertIsNone(receiver.pending)
                self.assertEqual(ingress.receipts, set())
                self.assertEqual(provider.events, [event()])

    async def test_restart_replays_durable_event_and_then_confirms_it(self):
        provider, ingress = Provider([event()]), DurableIngress()
        await Receiver(provider, ingress, lambda _: None).step()
        receiver = Receiver(provider, ingress, lambda _: None)
        await receiver.step()
        await receiver.step()
        self.assertEqual(provider.offsets, [None, None, 12])
        self.assertEqual(ingress.receipts, {11})

    async def test_lost_provider_response_before_or_after_confirmation(self):
        for after in (False, True):
            with self.subTest(after=after):
                provider, ingress = Provider([event(11), event(12)]), DurableIngress()
                receiver = Receiver(provider, ingress, lambda _: None)
                await receiver.step()
                provider.fail = PollingError("PROVIDER_TIMEOUT")
                provider.confirm_then_fail = after
                with self.assertRaises(PollingError):
                    await receiver.step()
                self.assertIsNone(receiver.pending)
                provider.fail = None
                for _ in range(3):
                    await receiver.step()
                self.assertEqual(ingress.receipts, {11, 12})
                self.assertEqual(provider.events, [])
                self.assertEqual(provider.offsets[2], None)

    async def test_long_suspension_does_not_reuse_stale_offset(self):
        clock = [1.0]
        provider, ingress = Provider([event(100)]), DurableIngress()
        receiver = Receiver(provider, ingress, lambda _: None, clock=lambda: clock[0])
        await receiver.step()
        clock[0] += 61
        provider.events = [event(2)]
        await receiver.step()
        self.assertEqual(provider.offsets, [None, None])
        self.assertEqual(ingress.receipts, {100, 2})

    async def test_status_contains_no_event_data_or_identifiers(self):
        output = []
        receiver = Receiver(Provider([event(8841047995)]), DurableIngress(), output.append)
        await receiver.step()
        raw = json.dumps(output)
        self.assertNotIn("private example", raw)
        self.assertNotIn("8841047995", raw)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def make_wire(self, responder):
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(responder), follow_redirects=False, trust_env=False
        )
        self.addAsyncCleanup(http.aclose)
        client = SimpleNamespace(
            _http=http,
            _url=lambda method: "https://api.telegram.org/bot123:private/" + method,
            settings=SimpleNamespace(
                bot_id="123", webhook_url="https://console.example/webhooks/telegram"
            ),
        )
        return Wire(client)

    async def test_poll_uses_positive_wait_one_event_and_exact_subscription(self):
        requests = []

        def reply(request):
            requests.append(request)
            return httpx.Response(200, json={"ok": True, "result": [event()]})

        wire = await self.make_wire(reply)
        await wire.poll(None)
        await wire.poll(11)
        first, second = [json.loads(x.content) for x in requests]
        self.assertEqual(first, {"limit": 1, "timeout": 20, "allowed_updates": ALLOWED_UPDATES})
        self.assertEqual(second["offset"], 11)
        self.assertEqual(requests[0].extensions["timeout"]["connect"], 5)
        self.assertEqual(requests[0].extensions["timeout"]["read"], 25)

    async def test_provider_error_classes_and_secret_free_exception(self):
        for status, code in (
            (401, "PROVIDER_AUTH_REJECTED"),
            (409, "RECEIVER_CONFLICT"),
            (500, "PROVIDER_REQUEST_FAILED"),
        ):
            with self.subTest(status=status):
                wire = await self.make_wire(
                    lambda _: httpx.Response(
                        status, json={"ok": False, "description": "bot123:private"}
                    )
                )
                with self.assertRaises(PollingError) as error:
                    await wire.poll(None)
                self.assertEqual(str(error.exception), code)

    async def test_rate_limit_is_bounded_and_does_not_ack(self):
        wire = await self.make_wire(
            lambda _: httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 999999}})
        )
        with self.assertRaises(PollingError) as error:
            await wire.poll(None)
        self.assertEqual(error.exception.retry_after, 300)

    async def test_conflicting_webhook_and_wrong_identity_fail_closed(self):
        wire = await self.make_wire(
            lambda _: httpx.Response(
                200, json={"ok": True, "result": {"url": "https://foreign.invalid/"}}
            )
        )
        with self.assertRaisesRegex(PollingError, "FOREIGN_WEBHOOK"):
            await wire.webhook()
        wire = await self.make_wire(
            lambda _: httpx.Response(200, json={"ok": True, "result": {"id": 124, "is_bot": True}})
        )
        with self.assertRaisesRegex(PollingError, "BOT_IDENTITY_MISMATCH"):
            await wire.identity()

    async def test_invalid_batch_id_order_size_and_encoding(self):
        cases = [
            (200, {"ok": True, "result": [event(), event(12)]}, {}, "UPDATE_BATCH_SHAPE"),
            (200, {"ok": True, "result": [event(True)]}, {}, "INVALID_UPDATE_ID"),
            (200, {"ok": True, "result": [event(2)]}, {}, "UPDATE_ORDER"),
            (
                200,
                {"ok": True, "result": []},
                {"content-encoding": "not-identity"},
                "PROVIDER_ENCODING",
            ),
        ]
        for status, body, headers, code in cases:
            with self.subTest(code=code):
                wire = await self.make_wire(
                    lambda _: httpx.Response(status, json=body, headers=headers)
                )
                with self.assertRaisesRegex(PollingError, code):
                    await wire.poll(11)
        wire = await self.make_wire(
            lambda _: httpx.Response(200, content=b" " * (MAX_RESPONSE + 1))
        )
        with self.assertRaisesRegex(PollingError, "PROVIDER_RESPONSE_TOO_LARGE"):
            await wire.poll(None)

    async def test_local_ack_requires_exact_typed_success_and_no_redirect(self):
        for status, body in (
            (200, {"ok": 1}),
            (200, {"ok": True, "extra": 1}),
            (503, {"ok": True}),
            (302, {"ok": True}),
        ):
            with self.subTest(status=status, body=body):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body)),
                    follow_redirects=False,
                ) as http:
                    with self.assertRaises(PollingError):
                        await LocalIngress(http, "private-secret").accept(event())

    async def test_local_forward_is_fixed_private_origin_and_secret_header(self):
        seen = []

        def reply(request):
            seen.append(request)
            return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            await LocalIngress(http, "private-secret").accept(event())
        self.assertEqual(str(seen[0].url), "http://api:8000/webhooks/telegram")
        self.assertEqual(seen[0].headers["X-Telegram-Bot-Api-Secret-Token"], "private-secret")
        self.assertEqual(json.loads(seen[0].content), event())

    async def test_local_body_bound_precedes_network(self):
        calls = []
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: calls.append(request))
        ) as http:
            with self.assertRaisesRegex(PollingError, "LOCAL_EVENT_TOO_LARGE"):
                await LocalIngress(http, "secret").accept(
                    {"update_id": 1, "business_message": {"text": "x" * MAX_EVENT}}
                )
        self.assertEqual(calls, [])


class JsonTests(unittest.TestCase):
    def test_duplicate_nonfinite_and_nonutf8_are_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(PollingError):
                strict_json(raw)


if __name__ == "__main__":
    unittest.main()
