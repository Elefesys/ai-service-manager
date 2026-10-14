"""Four owner routes; request creation remains a private worker capability."""

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import KEY_PATTERN, CanonicalUUID, decode_cursor
from asm.conversations.escalation_http_models import (
    EscalationCancelRequest,
    EscalationCommandResponse,
    EscalationCursor,
    EscalationErrorResponse,
    EscalationPage,
    EscalationResolveRequest,
    EscalationView,
    Operation,
    StatusFilter,
)
from asm.conversations.escalations import EscalationCode, EscalationError, OwnerEscalationService
from asm.messaging.http import no_query, strict_body
from asm.messaging.models import command_key


def escalation_query(
    request: Request, workspace: str
) -> tuple[int, StatusFilter, EscalationCursor | None]:
    try:
        values: dict[str, str] = {}
        for name, value in request.query_params.multi_items():
            if name not in ("limit", "status", "cursor") or name in values:
                raise ValueError("Invalid query")
            values[name] = value
        limit = values.get("limit", "25")
        if (
            not limit.isascii()
            or not limit.isdigit()
            or len(limit) > 3
            or not 1 <= int(limit) <= 100
        ):
            raise ValueError("Invalid limit")
        status = values.get("status", "PENDING")
        if status not in ("PENDING", "RESOLVED", "CANCELLED", "EXPIRED", "ALL"):
            raise ValueError("Invalid status")
        cursor = (
            EscalationCursor.model_validate(decode_cursor(values["cursor"]))
            if "cursor" in values
            else None
        )
        if cursor and (cursor.workspace_id != workspace or cursor.status != status):
            raise ValueError("Wrong cursor scope")
        return int(limit), cast(StatusFilter, status), cursor
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise EscalationError(EscalationCode.INVALID_REQUEST) from None


def install_escalations(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    service = OwnerEscalationService(auth)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": EscalationErrorResponse}
        for status in (401, 403, 404, 409, 413, 415, 422, 429, 500, 503)
    }
    router = APIRouter(prefix="/api/v1/workspaces", responses=errors, tags=["escalations"])

    @app.exception_handler(EscalationError)
    async def error(request: Request, exc: EscalationError) -> JSONResponse:
        status = {
            EscalationCode.ACCESS_DENIED: 403,
            EscalationCode.INVALID_REQUEST: 422,
            EscalationCode.NOT_FOUND: 404,
            EscalationCode.UNAVAILABLE: 503,
        }.get(exc.code, 409)
        return JSONResponse(
            {"error": {"code": exc.code.value}},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get(
        "/{workspace_id}/escalations",
        response_model=EscalationPage,
        openapi_extra={
            "parameters": [
                {
                    "in": "query",
                    "name": "limit",
                    "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
                },
                {
                    "in": "query",
                    "name": "status",
                    "schema": {
                        "type": "string",
                        "enum": ["PENDING", "RESOLVED", "CANCELLED", "EXPIRED", "ALL"],
                        "default": "PENDING",
                    },
                },
                {
                    "in": "query",
                    "name": "cursor",
                    "schema": {"type": "string", "minLength": 1, "maxLength": 1024},
                },
            ]
        },
        description="Live OWNER escalations:read. Stored status filter; one current projection and descending keyset pagination. No external I/O.",
    )
    async def listing(request: Request, workspace_id: CanonicalUUID) -> EscalationPage:
        limit, status, cursor = escalation_query(request, workspace_id)
        return await service.list(
            required_cookie(request, settings), UUID(workspace_id), limit, status, cursor
        )

    @router.get("/{workspace_id}/escalations/{escalation_id}", response_model=EscalationView)
    async def read(
        request: Request, workspace_id: CanonicalUUID, escalation_id: CanonicalUUID
    ) -> EscalationView:
        no_query(request)
        return await service.read(
            required_cookie(request, settings), UUID(workspace_id), UUID(escalation_id)
        )

    async def command(
        request: Request, workspace: str, escalation: str, operation: Operation
    ) -> EscalationCommandResponse:
        no_query(request)
        keys = request.headers.getlist("idempotency-key")
        if len(keys) != 1 or request.headers.getlist("if-match"):
            raise EscalationError(EscalationCode.INVALID_REQUEST)
        key = command_key(keys[0])
        token = mutation_token(request, settings)
        body = await strict_body(
            request, EscalationResolveRequest if operation == "RESOLVE" else EscalationCancelRequest
        )
        return await service.command(token, UUID(workspace), UUID(escalation), operation, body, key)

    def extra(model: type[EscalationCancelRequest]) -> dict[str, Any]:
        return {
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
                "content": {"application/json": {"schema": model.model_json_schema()}},
            },
        }

    @router.post(
        "/{workspace_id}/escalations/{escalation_id}/resolve",
        response_model=EscalationCommandResponse,
        openapi_extra=extra(EscalationResolveRequest),
        description="Live OWNER assignee only. Save the exact internal answer with CAS and an actor-bound key. Replay returns the saved acceptance; no send or Resume.",
    )
    async def resolve(
        request: Request, workspace_id: CanonicalUUID, escalation_id: CanonicalUUID
    ) -> EscalationCommandResponse:
        return await command(request, workspace_id, escalation_id, "RESOLVE")

    @router.post(
        "/{workspace_id}/escalations/{escalation_id}/cancel",
        response_model=EscalationCommandResponse,
        openapi_extra=extra(EscalationCancelRequest),
        description="Any live Workspace OWNER; no billing/channel dependency. Atomic cancellation, receipt and Audit; exact replay after commit ambiguity.",
    )
    async def cancel(
        request: Request, workspace_id: CanonicalUUID, escalation_id: CanonicalUUID
    ) -> EscalationCommandResponse:
        return await command(request, workspace_id, escalation_id, "CANCEL")

    app.include_router(router)
