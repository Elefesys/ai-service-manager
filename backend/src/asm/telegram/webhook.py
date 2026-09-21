"""Exact webhook boundary. Authentication and durable commit precede provider ACK."""

import asyncio
import hmac
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from asm.messaging.errors import Code, MessagingError
from asm.telegram.config import TelegramSettings
from asm.telegram.database import TelegramIngress
from asm.telegram.normalization import normalize_update, strict_json


class WebhookAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Literal[True] = True


class WebhookErrorCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal[
        "ACCESS_DENIED",
        "PAYLOAD_TOO_LARGE",
        "UNSUPPORTED_MEDIA_TYPE",
        "INVALID_REQUEST",
        "UNAVAILABLE",
        "EVENT_ID_CONFLICT",
    ]


class WebhookError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: WebhookErrorCode


def failure(code: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code}}, status_code=status, headers={"Cache-Control": "no-store"}
    )


class WebhookBoundary:
    def __init__(self, app: ASGIApp, settings: TelegramSettings) -> None:
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/webhooks/telegram":
            await self.app(scope, receive, send)
            return
        if not self.settings.enabled:
            await failure("UNAVAILABLE", 503)(scope, receive, send)
            return
        headers = scope.get("headers", [])
        if sum(len(k) + len(v) + 4 for k, v in headers) > 16384:
            await failure("PAYLOAD_TOO_LARGE", 413)(scope, receive, send)
            return

        def values(name: bytes) -> list[bytes]:
            return [v for k, v in headers if k.lower() == name]

        secret = values(b"x-telegram-bot-api-secret-token")
        if len(secret) != 1 or not hmac.compare_digest(
            secret[0], self.settings.webhook_secret.get_secret_value().encode("ascii")
        ):
            await failure("ACCESS_DENIED", 403)(scope, receive, send)
            return
        types, encodings, lengths = (
            values(b"content-type"),
            values(b"content-encoding"),
            values(b"content-length"),
        )
        if (
            len(types) != 1
            or types[0].split(b";")[0].strip().lower() != b"application/json"
            or (encodings and encodings != [b"identity"])
        ):
            await failure("UNSUPPORTED_MEDIA_TYPE", 415)(scope, receive, send)
            return
        if len(lengths) > 1 or (lengths and (not lengths[0].isdigit() or len(lengths[0]) > 10)):
            await failure("INVALID_REQUEST", 422)(scope, receive, send)
            return
        expected = int(lengths[0]) if lengths else None
        if expected is not None and expected > 262144:
            await failure("PAYLOAD_TOO_LARGE", 413)(scope, receive, send)
            return
        body = bytearray()
        try:
            async with asyncio.timeout(3):
                while True:
                    message = await receive()
                    if message["type"] != "http.request":
                        await failure("INVALID_REQUEST", 422)(scope, receive, send)
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 262144:
                        await failure("PAYLOAD_TOO_LARGE", 413)(scope, receive, send)
                        return
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await failure("INVALID_REQUEST", 422)(scope, receive, send)
            return
        if expected is not None and expected != len(body):
            await failure("INVALID_REQUEST", 422)(scope, receive, send)
            return

        async def buffered() -> Message:
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, buffered, send)


def install_webhook(
    app: FastAPI, settings: TelegramSettings, ingress: TelegramIngress | None
) -> None:
    app.add_middleware(WebhookBoundary, settings=settings)

    @app.post(
        "/webhooks/telegram",
        response_model=WebhookAcknowledgement,
        responses={code: {"model": WebhookError} for code in (403, 409, 413, 415, 422, 503)},
    )
    async def telegram_webhook(request: Request) -> WebhookAcknowledgement | JSONResponse:
        if ingress is None:
            return failure("UNAVAILABLE", 503)
        try:
            projection = normalize_update(settings.bot_id, strict_json(await request.body()))
            await ingress.ingest(projection, uuid4())
        except MessagingError as error:
            if error.code == Code.EVENT_ID_CONFLICT:
                return failure("EVENT_ID_CONFLICT", 409)
            if error.code in {Code.NOT_ALLOWED, Code.ACCESS_DENIED}:
                return failure("ACCESS_DENIED", 403)
            if error.code == Code.INVALID_INPUT:
                return failure("INVALID_REQUEST", 422)
            return failure("UNAVAILABLE", 503)
        except (SQLAlchemyError, TimeoutError):
            return failure("UNAVAILABLE", 503)
        return WebhookAcknowledgement()
