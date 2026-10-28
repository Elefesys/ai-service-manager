"""Single-bot TEST receiver: official getUpdates -> existing durable webhook handler.

No direct database access, sends, webhook mutation, or persistent acknowledgement
cursor. After a restart the provider replays unconfirmed events; the existing
ingress receipt makes replay idempotent. Only a successful local durable ACK
authorizes the next offset. Runtime uses the already accepted Telegram transport.
"""

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ALLOWED_UPDATES = [
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]
LOCAL_ORIGIN = "http://api:8000"
STATUS_PATH = Path("/run/asm-polling/status.json")
MAX_EVENT = 262144
MAX_RESPONSE = MAX_EVENT * 2
POLL_SECONDS = 20


class PollingError(Exception):
    def __init__(self, code: str, *, retry_after: int = 0):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)


def strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("nonfinite number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, RecursionError, UnicodeError):
        raise PollingError("INVALID_JSON") from None


def update_id(event: Any) -> int:
    if type(event) is not dict:
        raise PollingError("INVALID_UPDATE")
    value = event.get("update_id")
    if type(value) is not int or not 0 <= value < 2**63 - 1:
        raise PollingError("INVALID_UPDATE_ID")
    return value


class Wire:
    def __init__(self, client):
        self.client = client

    async def api(self, method: str, payload: dict, *, polling: bool = False):
        # Same verified TLS, fixed origin, no proxy env/redirects/retries and
        # owned TCP/TLS cleanup as TelegramClient. Only the long-poll read and
        # response-size budgets differ from its ordinary five-second calls.
        budget = 35 if polling else 5
        timeout = httpx.Timeout(connect=5, pool=2, read=25 if polling else 5, write=5)
        try:
            async with (
                asyncio.timeout(budget),
                self.client._http.stream(
                    "POST", self.client._url(method), json=payload, timeout=timeout
                ) as response,
            ):
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise PollingError("PROVIDER_ENCODING")
                raw = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise PollingError("PROVIDER_RESPONSE_TOO_LARGE")
                body = strict_json(bytes(raw))
                if type(body) is not dict:
                    raise PollingError("PROVIDER_RESPONSE_SHAPE")
                if response.status_code == 200 and body.get("ok") is True and "result" in body:
                    return body["result"]
                if response.status_code == 429:
                    params = body.get("parameters")
                    delay = params.get("retry_after") if type(params) is dict else None
                    raise PollingError(
                        "PROVIDER_RATE_LIMITED",
                        retry_after=min(300, max(1, delay)) if type(delay) is int else 30,
                    )
                if response.status_code == 409:
                    raise PollingError("RECEIVER_CONFLICT")
                if response.status_code in {401, 403}:
                    raise PollingError("PROVIDER_AUTH_REJECTED")
                raise PollingError("PROVIDER_REQUEST_FAILED")
        except (TimeoutError, httpx.TimeoutException):
            raise PollingError("PROVIDER_TIMEOUT") from None
        except httpx.HTTPError:
            raise PollingError("PROVIDER_UNAVAILABLE") from None

    async def identity(self):
        result = await self.api("getMe", {})
        if (
            type(result) is not dict
            or result.get("is_bot") is not True
            or type(result.get("id")) is not int
            or str(result["id"]) != self.client.settings.bot_id
        ):
            raise PollingError("BOT_IDENTITY_MISMATCH")

    async def webhook(self):
        result = await self.api("getWebhookInfo", {})
        if type(result) is not dict or type(result.get("url")) is not str:
            raise PollingError("WEBHOOK_RESPONSE_SHAPE")
        if result["url"] not in {"", self.client.settings.webhook_url}:
            raise PollingError("FOREIGN_WEBHOOK")
        return result["url"]

    async def poll(self, offset):
        payload = {"limit": 1, "timeout": POLL_SECONDS, "allowed_updates": ALLOWED_UPDATES}
        if offset is not None:
            payload["offset"] = offset
        result = await self.api("getUpdates", payload, polling=True)
        if type(result) is not list or len(result) > 1:
            raise PollingError("UPDATE_BATCH_SHAPE")
        for event in result:
            identifier = update_id(event)
            if offset is not None and identifier < offset:
                raise PollingError("UPDATE_ORDER")
        return result


class LocalIngress:
    def __init__(self, http, secret: str):
        self.http, self.secret = http, secret

    async def exchange(self, method, path, *, raw=None):
        headers = {"Accept-Encoding": "identity"}
        if raw is not None:
            headers.update(
                {"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": self.secret}
            )
        try:
            async with (
                asyncio.timeout(10),
                self.http.stream(
                    method,
                    LOCAL_ORIGIN + path,
                    headers=headers,
                    content=raw,
                    timeout=httpx.Timeout(connect=2, pool=2, read=8, write=3),
                ) as response,
            ):
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > 4096:
                        raise PollingError("LOCAL_RESPONSE_TOO_LARGE")
                if response.status_code != 200:
                    raise PollingError("LOCAL_INGRESS_REJECTED")
                return strict_json(bytes(body))
        except (TimeoutError, httpx.TimeoutException):
            # The database may already have committed. Replay without advancing
            # the provider offset; never infer a durable ACK from a timeout.
            raise PollingError("LOCAL_INGRESS_TIMEOUT") from None
        except httpx.HTTPError:
            raise PollingError("LOCAL_INGRESS_UNAVAILABLE") from None

    async def ready(self):
        if await self.exchange("GET", "/health/ready") != {"status": "ok", "component": "database"}:
            raise PollingError("LOCAL_NOT_READY")

    async def accept(self, event):
        update_id(event)
        try:
            raw = json.dumps(
                event, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode()
        except (ValueError, UnicodeError, RecursionError, TypeError):
            raise PollingError("INVALID_UPDATE") from None
        if len(raw) > MAX_EVENT:
            raise PollingError("LOCAL_EVENT_TOO_LARGE")
        result = await self.exchange("POST", "/webhooks/telegram", raw=raw)
        if type(result) is not dict or set(result) != {"ok"} or result["ok"] is not True:
            raise PollingError("LOCAL_ACK_INVALID")


class Receiver:
    def __init__(self, wire, ingress, report, *, clock=time.monotonic):
        self.wire, self.ingress, self.report, self.clock = wire, ingress, report, clock
        self.pending = None
        self.pending_at = 0.0
        self.polls = 0
        self.durable_deliveries = 0
        self.confirmed = 0

    def emit(self, state, code=None):
        self.report(
            {
                "version": 1,
                "state": state,
                "code": code,
                "updated_at": time.time(),
                "successful_polls": self.polls,
                "durable_deliveries": self.durable_deliveries,
                "confirmed_responses": self.confirmed,
                "ack_pending": self.pending is not None,
            }
        )

    async def step(self):
        # No offset survives a restart, transport error or a long suspension.
        # The provider can replay the event; durable ingress owns deduplication.
        offset = (
            self.pending + 1
            if self.pending is not None and self.clock() - self.pending_at < 60
            else None
        )
        try:
            batch = await self.wire.poll(offset)
            self.polls += 1
            if offset is not None:
                self.confirmed += 1
            self.pending = None
            for event in batch:
                identifier = update_id(event)
                await self.ingress.accept(event)
                self.durable_deliveries += 1
                self.pending, self.pending_at = identifier, self.clock()
            self.emit("ACK_PENDING" if self.pending is not None else "RUNNING")
        except BaseException:
            self.pending = None
            raise

    async def run(self):
        booted = False
        failures = 0
        while True:
            try:
                if not booted:
                    await self.wire.identity()
                    await self.ingress.ready()
                    if await self.wire.webhook():
                        self.emit("WAITING_WEBHOOK_REMOVAL")
                        await asyncio.sleep(2)
                        continue
                    booted = True
                await self.step()
                failures = 0
                # Limit an unexpectedly immediate empty response too.
                await asyncio.sleep(0.25)
            except PollingError as error:
                self.pending = None
                failures += 1
                blocked = error.code in {
                    "FOREIGN_WEBHOOK",
                    "BOT_IDENTITY_MISMATCH",
                    "RECEIVER_CONFLICT",
                    "PROVIDER_AUTH_REJECTED",
                    "LOCAL_INGRESS_REJECTED",
                    "INVALID_UPDATE",
                    "INVALID_UPDATE_ID",
                    "UPDATE_BATCH_SHAPE",
                    "UPDATE_ORDER",
                }
                self.emit("BLOCKED" if blocked else "RETRYING", error.code)
                await asyncio.sleep(max(error.retry_after, min(30, 2 ** min(failures, 5))))


def write_status(value):
    STATUS_PATH.parent.mkdir(exist_ok=True, mode=0o700)
    temporary = STATUS_PATH.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, sort_keys=True)
    os.replace(temporary, STATUS_PATH)


def read_status():
    raw = STATUS_PATH.read_bytes()
    if len(raw) > 4096:
        raise ValueError("STATUS_SIZE")
    value = strict_json(raw)
    if type(value) is not dict or value.get("version") != 1:
        raise ValueError("STATUS_SHAPE")
    return value


async def run():
    from asm.telegram.client import TelegramClient
    from asm.telegram.config import TelegramSettings

    settings = TelegramSettings()
    client = TelegramClient(settings)
    local = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=10)
    receiver = Receiver(
        Wire(client), LocalIngress(local, settings.webhook_secret.get_secret_value()), write_status
    )
    receiver.emit("STARTING")
    task = asyncio.current_task()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, task.cancel)
    try:
        await receiver.run()
    except asyncio.CancelledError:
        receiver.emit("STOPPED")
    finally:
        try:
            async with asyncio.timeout(5):
                await local.aclose()
                await client.aclose()
        except Exception:
            pass


def main():
    os.umask(0o077)
    try:
        if sys.argv[1:] == ["--status"]:
            print(json.dumps(read_status(), sort_keys=True))
        elif sys.argv[1:] == ["--health"]:
            value = read_status()
            if (
                value.get("state") not in {"RUNNING", "ACK_PENDING"}
                or not 0 <= time.time() - value["updated_at"] < 90
            ):
                return 1
        elif not sys.argv[1:]:
            asyncio.run(run())
        else:
            return 2
        return 0
    except Exception:
        # Never render transport exceptions: Bot API URLs contain the credential.
        print("ASM_POLLING_RECEIVER=FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
