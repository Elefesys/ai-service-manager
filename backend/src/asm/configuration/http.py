"""Six bounded owner routes on the existing session/CSRF/body boundary."""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import KEY_PATTERN, CanonicalUUID, strict_json
from asm.configuration.errors import ConfigurationCode, ConfigurationError
from asm.configuration.models import (
    ActiveProjection,
    CommandResponse,
    ConfigurationErrorResponse,
    DraftState,
    EditDraft,
    Preview,
    Publish,
    Rollback,
)
from asm.configuration.service import ConfigurationService


def no_options(request: Request) -> None:
    if request.query_params or request.headers.getlist("if-match"):
        raise ConfigurationError(ConfigurationCode.INVALID_INPUT)


def command_key(request: Request) -> str:
    no_options(request)
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or re.fullmatch(KEY_PATTERN, keys[0]) is None:
        raise ConfigurationError(ConfigurationCode.INVALID_INPUT)
    return keys[0]


async def body_as[M: BaseModel](request: Request, model: type[M]) -> M:
    try:
        return model.model_validate(strict_json(await request.body()))
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise ConfigurationError(ConfigurationCode.INVALID_INPUT) from None


def command_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    # DraftState/ActiveProjection register the shared Bundle schemas with the
    # document. JSON Pointers must resolve there, not in a nested $defs object.
    schema.pop("$defs", None)
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
            "content": {
                "application/json": {"schema": schema},
            },
        },
    }


def install_configuration(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    service = ConfigurationService(auth)
    errors: dict[int | str, dict[str, Any]] = {
        code: {"model": ConfigurationErrorResponse}
        for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
    }
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}/configuration",
        tags=["configuration"],
        responses=errors,
    )

    @app.exception_handler(ConfigurationError)
    async def configuration_error(request: Request, error: ConfigurationError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code.value}},
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/draft", response_model=DraftState)
    async def draft(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> DraftState:
        no_options(request)
        return await service.draft(
            required_cookie(request, settings), UUID(workspace_id), UUID(business_id)
        )

    @router.get("/preview", response_model=Preview)
    async def preview(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> Preview:
        no_options(request)
        return await service.preview(
            required_cookie(request, settings), UUID(workspace_id), UUID(business_id)
        )

    @router.get("/active", response_model=ActiveProjection)
    async def active(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> ActiveProjection:
        no_options(request)
        return await service.active(
            required_cookie(request, settings), UUID(workspace_id), UUID(business_id)
        )

    @router.put(
        "/draft",
        response_model=CommandResponse,
        openapi_extra=command_schema(EditDraft),
        description="Live OWNER. Raw UTF-8 request including envelope <=4096 bytes. Saves a draft only; no active release or calculations.",
    )
    async def edit(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, EditDraft)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "EDIT", key, body
        )

    @router.post(
        "/publish",
        response_model=CommandResponse,
        openapi_extra=command_schema(Publish),
        description="Live OWNER including replay. SQL validation, draft/activation CAS and atomic immutable release. Replaying an old result never changes current activation.",
    )
    async def publish(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, Publish)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "PUBLISH", key, body
        )

    @router.post(
        "/rollback",
        response_model=CommandResponse,
        openapi_extra=command_schema(Rollback),
        description="Live OWNER; creates a new activation of an eligible prior release. Removed/changed text is never restored; otherwise ROLLBACK_NOT_ALLOWED.",
    )
    async def rollback(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, Rollback)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "ROLLBACK", key, body
        )

    app.include_router(router)
