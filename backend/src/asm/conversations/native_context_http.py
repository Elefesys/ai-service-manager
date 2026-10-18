"""Three protected context routes on the retained 4096-byte auth boundary."""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import KEY_PATTERN, CanonicalUUID
from asm.conversations.control import ControlCode, ControlError
from asm.conversations.native_context import OwnerNativeContextService, decode_observation_cursor
from asm.conversations.native_context_http_models import (
    HumanContextState,
    NativeContextErrorResponse,
    ObservationCursor,
    ObservationPage,
    ReconcileRequest,
    ReconcileResponse,
)
from asm.messaging.http import no_query, strict_body


def observation_query(request: Request) -> tuple[int, ObservationCursor | None]:
    try:
        values: dict[str, str] = {}
        for name, value in request.query_params.multi_items():
            if name not in ("limit", "cursor") or name in values or not value:
                raise ValueError("Invalid query")
            values[name] = value
        limit = values.get("limit", "20")
        if re.fullmatch(r"[1-9][0-9]{0,2}", limit) is None or int(limit) > 100:
            raise ValueError("Invalid limit")
        return int(limit), decode_observation_cursor(
            values["cursor"]
        ) if "cursor" in values else None
    except (ValueError, TypeError, RecursionError):
        raise ControlError(ControlCode.INVALID_REQUEST) from None


def install_native_context(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    service = OwnerNativeContextService(auth)
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": NativeContextErrorResponse}
        for status in (401, 403, 404, 409, 413, 415, 422, 429, 500, 503)
    }
    router = APIRouter(prefix="/api/v1/workspaces", tags=["human-context"], responses=errors)

    @router.get(
        "/{workspace_id}/conversations/{conversation_id}/human-context",
        response_model=HumanContextState,
    )
    async def read(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> HumanContextState:
        no_query(request)
        return await service.read(
            required_cookie(request, settings), UUID(workspace_id), UUID(conversation_id)
        )

    @router.get(
        "/{workspace_id}/conversations/{conversation_id}/human-context/observations",
        response_model=ObservationPage,
        openapi_extra={
            "parameters": [
                {
                    "in": "query",
                    "name": "limit",
                    "schema": {
                        "type": "string",
                        "pattern": r"^(?:[1-9][0-9]?|100)$",
                        "default": "20",
                    },
                },
                {
                    "in": "query",
                    "name": "cursor",
                    "schema": {
                        "type": "string",
                        "pattern": r"^[A-Za-z0-9_-]+$",
                        "minLength": 1,
                        "maxLength": 1024,
                    },
                },
            ]
        },
    )
    async def observations(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> ObservationPage:
        limit, cursor = observation_query(request)
        return await service.observations(
            required_cookie(request, settings),
            UUID(workspace_id),
            UUID(conversation_id),
            limit,
            cursor,
        )

    @router.post(
        "/{workspace_id}/conversations/{conversation_id}/human-context/reconcile",
        response_model=ReconcileResponse,
        description="Live OWNER reconciliation in HUMAN; no send entitlement, Resume, Takeover or provider I/O. Total serialized UTF-8 request body <=4096 bytes. Retry ambiguous commit with the same actor/key/body; saved replay is not current state.",
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
                "content": {"application/json": {"schema": ReconcileRequest.model_json_schema()}},
            },
        },
    )
    async def reconcile(
        request: Request, workspace_id: CanonicalUUID, conversation_id: CanonicalUUID
    ) -> ReconcileResponse:
        no_query(request)
        keys = request.headers.getlist("idempotency-key")
        if (
            len(keys) != 1
            or re.fullmatch(KEY_PATTERN, keys[0]) is None
            or request.headers.getlist("if-match")
        ):
            raise ControlError(ControlCode.INVALID_REQUEST)
        token = mutation_token(request, settings)
        body = await strict_body(request, ReconcileRequest)
        return await service.reconcile(
            token, UUID(workspace_id), UUID(conversation_id), body, keys[0]
        )

    app.include_router(router)
