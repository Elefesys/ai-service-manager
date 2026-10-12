"""Three additive owner routes on the retained cookie/Origin/CSRF boundary."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.models import BillingStateError
from asm.billing.validation import KEY_PATTERN, CanonicalUUID
from asm.conversations.control import ControlCode, ControlError, OwnerControlService
from asm.conversations.http_models import (
    ControlCommandRequest,
    ControlCommandResponse,
    ControlErrorResponse,
    ControlOperation,
    ControlStateResponse,
)
from asm.messaging.http import no_query, strict_body
from asm.messaging.models import command_key


def install_control(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    service = OwnerControlService(auth)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ControlErrorResponse}
        for status in (401, 403, 404, 409, 413, 415, 422, 429, 500)
    }
    errors[503] = {"model": ControlErrorResponse | BillingStateError}
    router = APIRouter(prefix="/api/v1/workspaces", responses=errors, tags=["conversations"])

    @app.exception_handler(ControlError)
    async def control_error(request: Request, error: ControlError) -> JSONResponse:
        status = {
            ControlCode.ACCESS_DENIED: 403,
            ControlCode.INVALID_REQUEST: 422,
            ControlCode.NOT_FOUND: 404,
            ControlCode.UNAVAILABLE: 503,
        }.get(error.code, 409)
        return JSONResponse(
            {"error": {"code": error.code.value}},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get(
        "/{workspace_id}/conversations/{conversation_id}/control",
        response_model=ControlStateResponse,
        description="Live OWNER messaging:read. One current state snapshot, with bounded manual delivery flags; no channel refresh.",
    )
    async def read(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> ControlStateResponse:
        no_query(request)
        return await service.read(
            required_cookie(request, settings), UUID(workspace_id), UUID(conversation_id)
        )

    async def command(
        request: Request, workspace_id: str, conversation_id: str, operation: ControlOperation
    ) -> ControlCommandResponse:
        no_query(request)
        keys = request.headers.getlist("idempotency-key")
        if len(keys) != 1 or request.headers.getlist("if-match"):
            raise ControlError(ControlCode.INVALID_REQUEST)
        key = command_key(keys[0])
        token = mutation_token(request, settings)
        body = await strict_body(request, ControlCommandRequest)
        return await service.command(
            token, UUID(workspace_id), UUID(conversation_id), operation, body, key
        )

    extra = {
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
            "content": {"application/json": {"schema": ControlCommandRequest.model_json_schema()}},
        },
    }

    @router.post(
        "/{workspace_id}/conversations/{conversation_id}/takeover",
        response_model=ControlCommandResponse,
        openapi_extra=extra,
        description="Live OWNER conversations:control, expected client/generation/context and exact Idempotency-Key. Stop automation locally, independently of product/channel availability. Replay is the saved acceptance, not current state.",
    )
    async def takeover(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> ControlCommandResponse:
        return await command(request, workspace_id, conversation_id, "TAKEOVER")

    @router.post(
        "/{workspace_id}/conversations/{conversation_id}/resume",
        response_model=ControlCommandResponse,
        openapi_extra=extra,
        description="Live OWNER conversations:control, active Business/connection and messaging.manual_send product availability. Activates only future ingress; no channel refresh, send or backlog processing. Recover ambiguous commit with the same key/body.",
    )
    async def resume(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> ControlCommandResponse:
        return await command(request, workspace_id, conversation_id, "RESUME")

    app.include_router(router)
