"""The five authenticated owner routes on the existing cookie/Origin/CSRF boundary."""

from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.errors import BillingUnavailable
from asm.billing.models import BillingStateError
from asm.billing.validation import (
    KEY_PATTERN,
    CanonicalUUID,
    decode_cursor,
    strict_json,
    timestamp,
)
from asm.files.service import read_image_in_unit
from asm.files.storage import ObjectStorage
from asm.messaging.errors import Code, MessagingError
from asm.messaging.http_models import (
    CollectionCursor,
    ConnectionsPage,
    ConversationsPage,
    Endpoint,
    ManualTextRequest,
    MessagesCursor,
    MessagesPage,
    MessagingErrorResponse,
    ReadGrantRequest,
    ReadGrantResponse,
    SendResponse,
)
from asm.messaging.http_service import (
    OwnerAPIRepository,
    OwnerConnectionRefresher,
    OwnerMessagingService,
)
from asm.messaging.models import command_key
from asm.messaging.policy import Permission, require


def no_query(request: Request) -> None:
    if request.query_params:
        raise MessagingError(Code.INVALID_INPUT)


async def strict_body[T: BaseModel](request: Request, model: type[T]) -> T:
    try:
        return model.model_validate(strict_json(await request.body()))
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise MessagingError(Code.INVALID_INPUT) from None


def collection_query(
    request: Request,
    endpoint: Endpoint,
    workspace_id: str,
    conversation_id: str | None = None,
) -> tuple[int, CollectionCursor | MessagesCursor | None]:
    try:
        values: dict[str, str] = {}
        for name, value in request.query_params.multi_items():
            if name not in ("limit", "cursor") or name in values:
                raise ValueError("Invalid query")
            values[name] = value
        raw_limit = values.get("limit", "25")
        if not raw_limit.isascii() or not raw_limit.isdigit() or len(raw_limit) > 3:
            raise ValueError("Invalid limit")
        limit = int(raw_limit)
        if not 1 <= limit <= 100:
            raise ValueError("Invalid limit")
        cursor: CollectionCursor | MessagesCursor | None = None
        if "cursor" in values:
            decoded = decode_cursor(values["cursor"])
            cursor = (
                MessagesCursor.model_validate(decoded)
                if endpoint == "MESSAGES"
                else CollectionCursor.model_validate(decoded)
            )
            if cursor.endpoint != endpoint or cursor.workspace_id != workspace_id:
                raise ValueError("Wrong cursor scope")
            if isinstance(cursor, MessagesCursor) and cursor.conversation_id != conversation_id:
                raise ValueError("Wrong conversation scope")
        return limit, cursor
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise MessagingError(Code.INVALID_INPUT) from None


_QUERY_PARAMETERS = [
    {
        "in": "query",
        "name": "limit",
        "required": False,
        "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
    },
    {
        "in": "query",
        "name": "cursor",
        "required": False,
        "schema": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1024,
            "pattern": "^[A-Za-z0-9_-]+$",
        },
    },
]


def install_messaging(
    app: FastAPI,
    auth: AuthService,
    settings: AuthSettings,
    *,
    environment: Literal["LOCAL", "TEST"],
    storage: ObjectStorage | None = None,
    telegram: OwnerConnectionRefresher | None = None,
) -> None:
    service = OwnerMessagingService(auth, environment, telegram)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": MessagingErrorResponse}
        for status in (401, 403, 404, 409, 413, 415, 422, 429, 500, 503)
    }
    router = APIRouter(prefix="/api/v1/workspaces", responses=errors, tags=["messaging"])

    @app.exception_handler(MessagingError)
    async def messaging_error(request: Request, error: MessagingError) -> JSONResponse:
        code, status = {
            Code.INVALID_INPUT: ("INVALID_REQUEST", 422),
            Code.ACCESS_DENIED: ("ACCESS_DENIED", 403),
            Code.NOT_FOUND: ("NOT_FOUND", 404),
            Code.NOT_ALLOWED: ("NOT_ALLOWED", 409),
            Code.IDEMPOTENCY_KEY_CONFLICT: ("IDEMPOTENCY_KEY_CONFLICT", 409),
        }.get(error.code, ("UNAVAILABLE", 503))
        return JSONResponse(
            {"error": {"code": code}}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    @app.exception_handler(BillingUnavailable)
    async def billing_state_error(request: Request, error: BillingUnavailable) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": error.reason}},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    @router.get(
        "/{workspace_id}/channel-connections",
        response_model=ConnectionsPage,
        description="Live OWNER messaging:read. Observed connection status does not guarantee an open reply window or product entitlement.",
        openapi_extra={"parameters": _QUERY_PARAMETERS},
    )
    async def connections(request: Request, workspace_id: CanonicalUUID) -> ConnectionsPage:
        async with auth.workspace(required_cookie(request, settings), UUID(workspace_id)) as unit:
            await require(unit, Permission.READ)
            limit, cursor = collection_query(request, "CHANNEL_CONNECTIONS", workspace_id)
            result = await OwnerAPIRepository(unit).connections(
                limit, cast(CollectionCursor | None, cursor)
            )
        return result

    @router.get(
        "/{workspace_id}/conversations",
        response_model=ConversationsPage,
        description="Live OWNER messaging:read. Stable creation order; cursor does not freeze history.",
        openapi_extra={"parameters": _QUERY_PARAMETERS},
    )
    async def conversations(request: Request, workspace_id: CanonicalUUID) -> ConversationsPage:
        async with auth.workspace(required_cookie(request, settings), UUID(workspace_id)) as unit:
            await require(unit, Permission.READ)
            limit, cursor = collection_query(request, "CONVERSATIONS", workspace_id)
            result = await OwnerAPIRepository(unit).conversations(
                limit, cast(CollectionCursor | None, cursor)
            )
        return result

    @router.get(
        "/{workspace_id}/conversations/{conversation_id}/messages",
        response_model=MessagesPage,
        description="Live OWNER messaging:read. Creation order with current file and delivery status; provider occurred_at is separate.",
        openapi_extra={"parameters": _QUERY_PARAMETERS},
    )
    async def messages(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> MessagesPage:
        async with auth.workspace(required_cookie(request, settings), UUID(workspace_id)) as unit:
            await require(unit, Permission.READ)
            limit, cursor = collection_query(request, "MESSAGES", workspace_id, conversation_id)
            result = await OwnerAPIRepository(unit).messages(
                UUID(conversation_id), limit, cast(MessagesCursor | None, cursor)
            )
        return result

    @router.post(
        "/{workspace_id}/conversations/{conversation_id}/messages",
        status_code=202,
        response_model=SendResponse,
        responses={503: {"model": MessagingErrorResponse | BillingStateError}},
        description="Live OWNER messaging:send. Exact text and one Idempotency-Key; no If-Match or query parameters. ACCEPTED/REPLAY confirms a durable intention, not delivery. Preserve text/key/context on response loss.",
        openapi_extra={
            "parameters": [
                {
                    "in": "header",
                    "name": "Idempotency-Key",
                    "required": True,
                    "schema": {
                        "type": "string",
                        "pattern": KEY_PATTERN,
                        "minLength": 1,
                        "maxLength": 128,
                    },
                }
            ],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ManualTextRequest.model_json_schema()}},
            },
        },
    )
    async def send_text(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> SendResponse:
        no_query(request)
        keys = request.headers.getlist("idempotency-key")
        if len(keys) != 1 or "if-match" in request.headers:
            raise MessagingError(Code.INVALID_INPUT)
        key = command_key(keys[0])
        token = mutation_token(request, settings)
        body = await strict_body(request, ManualTextRequest)
        receipt = await service.send(
            token, UUID(workspace_id), UUID(conversation_id), body.text, key
        )
        return SendResponse(
            workspace_id=str(receipt.workspace_id),
            receipt_id=str(receipt.receipt_id),
            message_id=str(receipt.message_id),
            accepted_at=timestamp(receipt.accepted_at),
            outcome=receipt.code,
        )

    @router.post(
        "/{workspace_id}/conversations/{conversation_id}/messages/{message_id}/files/{file_id}/read-grant",
        response_model=ReadGrantResponse,
        description="Live OWNER messaging:read. Exact empty object and CSRF. Private signed GET expires after 60 seconds; existing issued URLs remain usable until expiry.",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ReadGrantRequest.model_json_schema()}},
            }
        },
    )
    async def read_grant(
        request: Request,
        workspace_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        message_id: CanonicalUUID,
        file_id: CanonicalUUID,
    ) -> ReadGrantResponse:
        no_query(request)
        token = mutation_token(request, settings)
        await strict_body(request, ReadGrantRequest)
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            await require(unit, Permission.READ)
            if storage is None:
                raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
            grant = await read_image_in_unit(
                unit, UUID(conversation_id), UUID(message_id), UUID(file_id), storage
            )
            result = ReadGrantResponse(url=grant.url, expires_at=timestamp(grant.expires_at))
        return result

    app.include_router(router)
