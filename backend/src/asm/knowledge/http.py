"""Eight owner routes on the existing 4096-byte session/CSRF boundary."""

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
from asm.knowledge.embeddings import EmbeddingClient
from asm.knowledge.errors import KnowledgeCode, KnowledgeError
from asm.knowledge.models import (
    ConfirmSource,
    CreateBuild,
    KnowledgeCommandResponse,
    KnowledgeErrorResponse,
    KnowledgeOwnerState,
    PublishKnowledge,
    RollbackKnowledge,
    SaveSource,
    WithdrawSource,
)
from asm.knowledge.service import KnowledgeService


def no_options(request: Request) -> None:
    if request.query_params or request.headers.getlist("if-match"):
        raise KnowledgeError(KnowledgeCode.INVALID_INPUT)


def command_key(request: Request) -> str:
    no_options(request)
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or re.fullmatch(KEY_PATTERN, keys[0]) is None:
        raise KnowledgeError(KnowledgeCode.INVALID_INPUT)
    return keys[0]


async def body_as[M: BaseModel](request: Request, model: type[M]) -> M:
    try:
        return model.model_validate(strict_json(await request.body()))
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise KnowledgeError(KnowledgeCode.INVALID_INPUT) from None


def command_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
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
            "content": {"application/json": {"schema": schema}},
        },
    }


def install_knowledge(
    app: FastAPI,
    auth: AuthService,
    settings: AuthSettings,
    *,
    embeddings: EmbeddingClient | None = None,
) -> None:
    service = KnowledgeService(auth, embeddings)
    errors: dict[int | str, dict[str, Any]] = {
        code: {"model": KnowledgeErrorResponse}
        for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
    }
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}/knowledge",
        tags=["knowledge"],
        responses=errors,
    )

    @app.exception_handler(KnowledgeError)
    async def knowledge_error(request: Request, error: KnowledgeError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code.value}},
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("", response_model=KnowledgeOwnerState)
    async def state(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> KnowledgeOwnerState:
        no_options(request)
        return await service.state(
            required_cookie(request, settings), UUID(workspace_id), UUID(business_id)
        )

    @router.post(
        "/sources",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(SaveSource),
    )
    async def save(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, SaveSource)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "KNOWLEDGE_SAVE", key, body
        )

    @router.post(
        "/sources/{source_id}/confirm",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(ConfirmSource),
    )
    async def confirm(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        source_id: CanonicalUUID,
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, ConfirmSource)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "KNOWLEDGE_CONFIRM",
            key,
            body,
            source=UUID(source_id),
        )

    @router.post(
        "/sources/{source_id}/revoke",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(WithdrawSource),
    )
    async def revoke(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        source_id: CanonicalUUID,
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, WithdrawSource)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "KNOWLEDGE_REVOKE",
            key,
            body,
            source=UUID(source_id),
        )

    @router.post(
        "/sources/{source_id}/delete",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(WithdrawSource),
    )
    async def delete(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        source_id: CanonicalUUID,
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, WithdrawSource)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "KNOWLEDGE_DELETE",
            key,
            body,
            source=UUID(source_id),
        )

    @router.post(
        "/builds",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(CreateBuild),
        description="Creates a durable build receipt. Only a new PLANNED build attempts at most four controlled embedding calls outside transactions. Replay never repeats HTTP. Read current state afterward; embeddings default DISABLED.",
    )
    async def build(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, CreateBuild)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "KNOWLEDGE_BUILD_CREATE", key, body
        )

    @router.post(
        "/publish",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(PublishKnowledge),
    )
    async def publish(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, PublishKnowledge)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "KNOWLEDGE_PUBLISH", key, body
        )

    @router.post(
        "/rollback",
        response_model=KnowledgeCommandResponse,
        openapi_extra=command_schema(RollbackKnowledge),
    )
    async def rollback(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> KnowledgeCommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, RollbackKnowledge)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "KNOWLEDGE_ROLLBACK", key, body
        )

    app.include_router(router)
