"""Bounded official Bot API client; no retries, redirects, or caller-owned origin."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from asm.files.models import FetchPermit
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind, SendOutcome, identifier
from asm.messaging.results import SendPermit
from asm.telegram.config import TelegramSettings
from asm.telegram.normalization import connection_fields, numeric_id, object_value, strict_json


class TelegramError(Exception):
    def __init__(self, code: Code, *, definitely_unsent: bool = False) -> None:
        super().__init__(code.value)
        self.code = code
        self.definitely_unsent = definitely_unsent


@dataclass(frozen=True, slots=True)
class BusinessConnection:
    external_connection_id: str
    owner_user_id: str
    is_enabled: bool
    can_reply: bool
    date: str

    def observation(self, bot_id: str) -> dict[str, object]:
        return {
            "bot_identity": bot_id,
            "external_connection_id": self.external_connection_id,
            "owner_user_id": self.owner_user_id,
            "is_enabled": self.is_enabled,
            "can_reply": self.can_reply,
            "error_code": None,
        }


def suppress_transport_logs() -> None:
    # Bot API puts the secret in the URL. Disable before constructing a client,
    # including existing child loggers. Future children inherit a silent parent.
    for name in ("httpx", "httpcore", *tuple(logging.Logger.manager.loggerDict)):
        if name == "httpx" or name == "httpcore" or name.startswith(("httpx.", "httpcore.")):
            logger = logging.getLogger(name)
            logger.disabled = True
            logger.propagate = False
            logger.setLevel(logging.CRITICAL + 1)
            if not logger.handlers:
                logger.addHandler(logging.NullHandler())


class TelegramClient:
    def __init__(
        self,
        settings: TelegramSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        test_origin: str | None = None,
    ) -> None:
        if not settings.enabled:
            raise TelegramError(Code.NOT_ALLOWED)
        origin = "https://api.telegram.org"
        if transport is not None or test_origin is not None:
            if settings.environment != "TEST":
                raise TelegramError(Code.NOT_ALLOWED)
        if test_origin is not None:
            parsed = urlsplit(test_origin)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise TelegramError(Code.INVALID_INPUT)
            origin = test_origin
        suppress_transport_logs()
        self.settings = settings
        self._origin = origin
        self._http = httpx.AsyncClient(
            transport=transport
            or httpx.AsyncHTTPTransport(
                retries=0,
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
                trust_env=False,
            ),
            verify=True,
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
            timeout=httpx.Timeout(connect=5, pool=2, read=5, write=5),
            headers={"Accept-Encoding": "identity"},
        )

    def _url(self, method: str, *, file: bool = False) -> str:
        return (
            self._origin
            + ("/file/bot" if file else "/bot")
            + self.settings.token.get_secret_value()
            + "/"
            + method
        )

    async def _request(
        self, method: str, payload: dict[str, object], *, budget: float = 5
    ) -> tuple[int, dict[str, Any]]:
        try:
            async with (
                asyncio.timeout(budget),
                self._http.stream("POST", self._url(method), json=payload) as response,
            ):
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise TelegramError(Code.INVALID_INPUT)
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise TelegramError(Code.INVALID_INPUT)
                return response.status_code, strict_json(bytes(body), 65536)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise TelegramError(Code.DEPENDENCY_UNAVAILABLE, definitely_unsent=True) from None
        except (TimeoutError, httpx.TimeoutException):
            raise TelegramError(Code.DEPENDENCY_TIMEOUT) from None
        except httpx.HTTPError:
            raise TelegramError(Code.DEPENDENCY_UNAVAILABLE) from None
        except MessagingError:
            raise TelegramError(Code.INVALID_INPUT) from None

    async def _readonly(self, method: str, payload: dict[str, object]) -> Any:
        status, response = await self._request(method, payload)
        if status == 200 and response.get("ok") is True and "result" in response:
            return response["result"]
        if (
            response.get("ok") is False
            and type(response.get("error_code")) is int
            and response["error_code"] == status
            and status in {400, 401, 403, 404}
        ):
            raise TelegramError(Code.NOT_ALLOWED)
        raise TelegramError(Code.DEPENDENCY_UNAVAILABLE)

    async def get_me(self) -> str:
        try:
            result = object_value(await self._readonly("getMe", {}))
            bot = numeric_id(result.get("id"))
            if result.get("is_bot") is not True or bot != self.settings.bot_id:
                raise TelegramError(Code.NOT_ALLOWED)
            return bot
        except MessagingError:
            raise TelegramError(Code.INVALID_INPUT) from None

    async def get_webhook_info(self) -> dict[str, object]:
        result = await self._readonly("getWebhookInfo", {})
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("url"), str)
            or type(result.get("pending_update_count")) is not int
            or result["pending_update_count"] < 0
        ):
            raise TelegramError(Code.INVALID_INPUT)
        # Error messages/URLs in provider diagnostics are not returned to logging.
        return {"url": result["url"], "pending_update_count": result["pending_update_count"]}

    async def get_updates(self) -> list[dict[str, Any]]:
        result = await self._readonly(
            "getUpdates",
            {
                "limit": 100,
                "timeout": 0,
                "allowed_updates": [
                    "business_connection",
                    "business_message",
                    "edited_business_message",
                    "deleted_business_messages",
                ],
            },
        )
        if (
            type(result) is not list
            or len(result) > 100
            or any(type(item) is not dict for item in result)
        ):
            raise TelegramError(Code.INVALID_INPUT)
        return result

    async def get_business_connection(self, external_id: str) -> BusinessConnection:
        try:
            identifier(external_id)
            fields = connection_fields(
                await self._readonly(
                    "getBusinessConnection", {"business_connection_id": external_id}
                )
            )
            if fields["external_connection_id"] != external_id:
                raise TelegramError(Code.NOT_ALLOWED)
            return BusinessConnection(
                fields["external_connection_id"],
                fields["owner_user_id"],
                fields["is_enabled"],
                fields["can_reply"],
                fields["lifecycle_date"],
            )
        except MessagingError:
            raise TelegramError(Code.INVALID_INPUT) from None

    async def observe(self, bot_id: str, external_id: str, owner_id: str) -> dict[str, object]:
        try:
            if bot_id != self.settings.bot_id:
                raise TelegramError(Code.NOT_ALLOWED)
            connection = await self.get_business_connection(external_id)
            if connection.owner_user_id != owner_id:
                raise TelegramError(Code.NOT_ALLOWED)
            return connection.observation(bot_id)
        except TelegramError as error:
            return {
                "bot_identity": None,
                "external_connection_id": None,
                "owner_user_id": None,
                "is_enabled": None,
                "can_reply": None,
                "error_code": error.code.value,
            }

    async def set_webhook(self) -> None:
        result = await self._readonly(
            "setWebhook",
            {
                "url": self.settings.webhook_url,
                "secret_token": self.settings.webhook_secret.get_secret_value(),
                "allowed_updates": [
                    "business_connection",
                    "business_message",
                    "edited_business_message",
                    "deleted_business_messages",
                ],
                "max_connections": 1,
                "drop_pending_updates": False,
            },
        )
        if result is not True:
            raise TelegramError(Code.INVALID_INPUT)

    async def send(self, permit: SendPermit) -> SendOutcome:
        if permit.provider != "TELEGRAM" or permit.bot_identity != self.settings.bot_id:
            return SendOutcome(OutcomeKind.NOT_SENT_PERMANENT, error_code=Code.NOT_ALLOWED)
        try:
            status, response = await self._request(
                "sendMessage",
                {
                    "business_connection_id": permit.external_connection_id,
                    "chat_id": permit.chat_id,
                    "text": permit.text,
                },
                budget=10,
            )
            if status == 200 and response.get("ok") is True:
                result = object_value(response.get("result"))
                chat = object_value(result.get("chat"))
                message_id = numeric_id(result.get("message_id"))
                if (
                    result.get("business_connection_id") == permit.external_connection_id
                    and numeric_id(chat.get("id")) == permit.chat_id
                    and chat.get("type") == "private"
                ):
                    return SendOutcome(OutcomeKind.SUCCESS, message_id)
            if (
                response.get("ok") is False
                and type(response.get("error_code")) is int
                and response["error_code"] == status
                and isinstance(response.get("description"), str)
            ):
                if status in {400, 401, 403}:
                    return SendOutcome(OutcomeKind.NOT_SENT_PERMANENT, error_code=Code.NOT_ALLOWED)
                if status == 429:
                    params = response.get("parameters")
                    delay = params.get("retry_after") if isinstance(params, dict) else None
                    if type(delay) is int and 1 <= delay <= 86400:
                        return SendOutcome(
                            OutcomeKind.NOT_SENT_RETRYABLE,
                            error_code=Code.DEPENDENCY_UNAVAILABLE,
                            retry_after_seconds=delay,
                        )
                    return SendOutcome(OutcomeKind.NOT_SENT_PERMANENT, error_code=Code.NOT_ALLOWED)
        except TelegramError as error:
            if error.definitely_unsent:
                return SendOutcome(OutcomeKind.NOT_SENT_RETRYABLE, error_code=error.code)
        except MessagingError:
            pass
        return SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT)

    async def open_image(self, permit: FetchPermit) -> AsyncIterator[bytes]:
        if permit.provider != "TELEGRAM" or permit.bot_identity != self.settings.bot_id:
            raise MessagingError(Code.INVALID_INPUT)
        try:
            result = object_value(
                await self._readonly("getFile", {"file_id": permit.image_file_id})
            )
            path = result.get("file_path")
            if (
                result.get("file_id") != permit.image_file_id
                or not isinstance(path, str)
                or len(path) > 1024
                or re.fullmatch(r"[A-Za-z0-9_./-]+", path) is None
                or any(segment in {"", ".", ".."} for segment in path.split("/"))
            ):
                raise TelegramError(Code.INVALID_INPUT)
            async with (
                asyncio.timeout(20),
                self._http.stream("GET", self._url(path, file=True)) as response,
            ):
                if response.status_code != 200:
                    raise TelegramError(
                        Code.INVALID_INPUT
                        if response.status_code < 500
                        else Code.DEPENDENCY_UNAVAILABLE
                    )
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    # Reject before HTTPX's decoder can allocate an inflated body.
                    raise TelegramError(Code.INVALID_INPUT)
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    yield chunk
        except TelegramError as error:
            code = Code.INVALID_INPUT if error.code == Code.NOT_ALLOWED else error.code
            raise MessagingError(code) from None
        except (TimeoutError, httpx.TimeoutException):
            raise MessagingError(Code.DEPENDENCY_TIMEOUT) from None
        except httpx.HTTPError:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE) from None

    async def aclose(self) -> None:
        await self._http.aclose()
