"""Browser boundary: exact origins, bounded input, no secret-bearing error payloads."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from asm.auth.config import AuthSettings
from asm.auth.crypto import RateLimiter, check_csrf, normalize_login, token_verifier
from asm.auth.models import (
    AuthCode,
    AuthError,
    BootstrapResponse,
    BusinessesResponse,
    BusinessResponse,
    EmptyRequest,
    ErrorResponse,
    LoginRequest,
    SessionResponse,
)
from asm.auth.service import AuthService
from asm.tenancy import TenancyError

BODY_LIMIT = 4096
HEADER_LIMIT = 16384


def error_response(code: AuthCode, status: int, retry_after: int = 60) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if status == 429:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse({"error": {"code": code.value}}, status_code=status, headers=headers)


def session_cookie(request: Request, settings: AuthSettings, required: bool = True) -> str | None:
    # A cookie parser alone silently accepts ambiguous duplicate cookie names.
    values = []
    for header in request.headers.getlist("cookie"):
        for item in header.split(";"):
            name, separator, value = item.strip().partition("=")
            if name == settings.auth_cookie_name and separator:
                values.append(value)
    if len(values) > 1:
        raise AuthError(AuthCode.SESSION_REQUIRED, 401)
    if not values:
        if required:
            raise AuthError(AuthCode.SESSION_REQUIRED, 401)
        return None
    token_verifier(values[0])
    return values[0]


def required_cookie(request: Request, settings: AuthSettings) -> str:
    token = session_cookie(request, settings)
    if token is None:
        raise AuthError(AuthCode.SESSION_REQUIRED, 401)
    return token


def mutation_token(request: Request, settings: AuthSettings) -> str:
    token = required_cookie(request, settings)
    values = request.headers.getlist("x-csrf-token")
    if len(values) != 1:
        raise AuthError(AuthCode.CSRF_REJECTED, 403)
    check_csrf(token, values[0])
    return token


def set_cookie(response: Response, token: str, expires: datetime, settings: AuthSettings) -> None:
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=max(1, int((expires - datetime.now(UTC)).total_seconds())),
        # HTTP cookie dates require datetime.UTC, not merely a zero-offset ZoneInfo.
        expires=expires.astimezone(UTC),
        path="/",
        secure=settings.auth_secure,
        httponly=True,
        samesite="lax",
    )


class AuthBoundary:
    def __init__(self, app: ASGIApp, settings: AuthSettings, limiter: RateLimiter) -> None:
        self.app, self.settings, self.limiter = app, settings, limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (
            path.startswith("/api/v1/auth/") or path.startswith("/api/v1/workspaces/")
        ):
            await self.app(scope, receive, send)
            return
        started = False

        async def secured_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"pragma", b"no-cache"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            headers = Headers(scope=scope)
            if sum(len(k) + len(v) for k, v in scope["headers"]) > HEADER_LIMIT:
                raise AuthError(AuthCode.BODY_TOO_LARGE, 413)
            try:
                hosts = headers.getlist("host")
                authority = urlsplit("//" + hosts[0]) if len(hosts) == 1 else None
                host = authority.hostname if authority else None
                if authority and (
                    authority.username is not None
                    or authority.password is not None
                    or authority.path
                    or authority.query
                    or authority.fragment
                ):
                    host = None
                if authority:
                    _ = authority.port
            except ValueError:
                host = None
            if host not in self.settings.auth_hosts:
                raise AuthError(AuthCode.ORIGIN_DENIED, 403)
            origins = headers.getlist("origin")
            if origins and (len(origins) != 1 or origins[0] not in self.settings.auth_origins):
                raise AuthError(AuthCode.ORIGIN_DENIED, 403)
            if scope["method"] not in ("GET", "HEAD", "OPTIONS"):
                if len(origins) != 1:
                    raise AuthError(AuthCode.ORIGIN_DENIED, 403)
                types = headers.getlist("content-type")
                if (
                    len(types) != 1
                    or types[0].split(";", 1)[0].strip().lower() != "application/json"
                ):
                    raise AuthError(AuthCode.UNSUPPORTED_MEDIA_TYPE, 415)
                peer = (scope.get("client") or ("unknown", 0))[0]
                # Forwarded/X-Forwarded-For are not used as limiter identities.
                self.limiter.consume("global", self.settings.auth_global_limit)
                self.limiter.consume("peer:" + peer, self.settings.auth_peer_limit)
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise AuthError(AuthCode.UNSUPPORTED_MEDIA_TYPE, 415)
            lengths = headers.getlist("content-length")
            if len(lengths) > 1:
                raise AuthError(AuthCode.INVALID_REQUEST, 422)
            if lengths:
                if not lengths[0].isascii() or not lengths[0].isdigit():
                    raise AuthError(AuthCode.INVALID_REQUEST, 422)
                if len(lengths[0]) > 6 or int(lengths[0]) > BODY_LIMIT:
                    raise AuthError(AuthCode.BODY_TOO_LARGE, 413)
            body = bytearray()
            async with asyncio.timeout(3):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > BODY_LIMIT:
                        raise AuthError(AuthCode.BODY_TOO_LARGE, 413)
                    if not message.get("more_body", False):
                        break
            if lengths and int(lengths[0]) != len(body):
                raise AuthError(AuthCode.INVALID_REQUEST, 422)
            delivered = False

            async def replay() -> Message:
                nonlocal delivered
                if delivered:
                    return {"type": "http.disconnect"}
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, secured_send)
        except AuthError as error:
            if started:
                raise
            await error_response(error.code, error.status, self.settings.auth_rate_window_seconds)(
                scope, receive, secured_send
            )
        except (SQLAlchemyError, TimeoutError):
            if started:
                raise
            await error_response(AuthCode.UNAVAILABLE, 503)(scope, receive, secured_send)
        except Exception:
            if started:
                raise
            # No exception repr, request body, cookies, verifier or database URL in logs.
            await error_response(AuthCode.INTERNAL_ERROR, 500)(scope, receive, secured_send)


def install_auth(app: FastAPI, service: AuthService, settings: AuthSettings) -> None:
    limiter = RateLimiter(settings.auth_rate_window_seconds)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorResponse} for status in (401, 403, 404, 413, 415, 422, 429, 500, 503)
    }
    router = APIRouter(prefix="/api/v1", responses=errors)

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, error: AuthError) -> JSONResponse:
        return error_response(error.code, error.status, settings.auth_rate_window_seconds)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(AuthCode.INVALID_REQUEST, 422)

    @app.exception_handler(TenancyError)
    async def tenant_error(request: Request, error: TenancyError) -> JSONResponse:
        if error.code.value == "ACCESS_DENIED":
            return error_response(AuthCode.ACCESS_DENIED, 403)
        if error.code.value == "NOT_FOUND":
            return error_response(AuthCode.NOT_FOUND, 404)
        return error_response(AuthCode.UNAVAILABLE, 503)

    @router.post("/auth/bootstrap", response_model=BootstrapResponse, tags=["auth"])
    async def bootstrap(
        request: Request, body: EmptyRequest, response: Response
    ) -> BootstrapResponse:
        if request.headers.getlist("x-csrf-bootstrap") != ["1"]:
            raise AuthError(AuthCode.CSRF_REJECTED, 403)
        result, fresh = await service.bootstrap(session_cookie(request, settings, required=False))
        if fresh is not None:
            set_cookie(response, fresh, result.expires_at, settings)
        return result

    @router.post("/auth/login", response_model=SessionResponse, tags=["auth"])
    async def login(request: Request, body: LoginRequest, response: Response) -> SessionResponse:
        token = mutation_token(request, settings)
        normalized = normalize_login(body.login)
        limiter.consume("login:" + normalized, settings.auth_login_limit)
        result, fresh = await service.login(token, normalized, body.password.get_secret_value())
        set_cookie(response, fresh, result.expires_at, settings)
        return result

    @router.get("/auth/session", response_model=SessionResponse, tags=["auth"])
    async def current_session(request: Request) -> SessionResponse:
        return await service.current(required_cookie(request, settings))

    @router.post("/auth/rotate", response_model=SessionResponse, tags=["auth"])
    async def rotate(request: Request, body: EmptyRequest, response: Response) -> SessionResponse:
        result, fresh = await service.rotate(mutation_token(request, settings))
        set_cookie(response, fresh, result.expires_at, settings)
        return result

    @router.post("/auth/logout", status_code=204, tags=["auth"])
    async def logout(request: Request, body: EmptyRequest) -> Response:
        await service.logout(mutation_token(request, settings))
        response = Response(status_code=204)
        response.delete_cookie(
            settings.auth_cookie_name,
            path="/",
            secure=settings.auth_secure,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get(
        "/workspaces/{workspace_id}/businesses",
        response_model=BusinessesResponse,
        tags=["businesses"],
    )
    async def businesses(request: Request, workspace_id: UUID) -> BusinessesResponse:
        async with service.workspace(required_cookie(request, settings), workspace_id) as unit:
            return BusinessesResponse(
                businesses=[
                    BusinessResponse.model_validate(row) for row in await unit.list_businesses()
                ]
            )

    @router.get(
        "/workspaces/{workspace_id}/businesses/{business_id}",
        response_model=BusinessResponse,
        tags=["businesses"],
    )
    async def business(request: Request, workspace_id: UUID, business_id: UUID) -> BusinessResponse:
        async with service.workspace(required_cookie(request, settings), workspace_id) as unit:
            return BusinessResponse.model_validate(await unit.get_business(business_id))

    app.include_router(router)
    app.add_middleware(AuthBoundary, settings=settings, limiter=limiter)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.auth_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-CSRF-Bootstrap"],
        max_age=600,
    )
