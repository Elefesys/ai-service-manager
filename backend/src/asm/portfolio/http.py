"""Owner session/CSRF API; binary content is read only after committed authority."""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.billing.validation import KEY_PATTERN, CanonicalUUID, strict_json
from asm.portfolio.errors import PortfolioCode, PortfolioError
from asm.portfolio.models import (
    AnalysisResponse,
    CommandResponse,
    ConfirmItem,
    ConversationState,
    CreateBuild,
    DeleteAsset,
    EmptyRequest,
    ErrorResponse,
    FinishUpload,
    InitUpload,
    OwnerState,
    PublishPortfolio,
    PurgeResponse,
    RevokeItem,
    RollbackPortfolio,
    SaveItem,
    UploadResponse,
)
from asm.portfolio.service import PortfolioService


def no_options(request: Request) -> None:
    if request.query_params or request.headers.getlist("if-match"):
        raise PortfolioError(PortfolioCode.INVALID_INPUT)


def command_key(request: Request) -> str:
    no_options(request)
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or re.fullmatch(KEY_PATTERN, keys[0]) is None:
        raise PortfolioError(PortfolioCode.INVALID_INPUT)
    return keys[0]


async def body_as[M: BaseModel](request: Request, model: type[M]) -> M:
    try:
        return model.model_validate(strict_json(await request.body()))
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise PortfolioError(PortfolioCode.INVALID_INPUT) from None


def command_schema(model: type[BaseModel], *, receipt: bool = True) -> dict[str, Any]:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    schema.pop("$defs", None)  # Shared attributes are also in OwnerState responses.
    value: dict[str, Any] = {
        "requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}
    }
    if receipt:
        value["parameters"] = [
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
        ]
    return value


def install_portfolio(app: FastAPI, service: PortfolioService, settings: AuthSettings) -> None:
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}/portfolio",
        tags=["portfolio"],
        responses={
            code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 415, 422, 429, 503)
        },
    )

    @app.exception_handler(PortfolioError)
    async def portfolio_error(request: Request, error: PortfolioError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code.value}},
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("", response_model=OwnerState)
    async def state(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> OwnerState:
        no_options(request)
        return await service.state(
            required_cookie(request, settings), UUID(workspace_id), UUID(business_id)
        )

    @router.put(
        "/assets/{asset_id}/versions/{version_id}/uploads/{upload_id}/content",
        response_model=UploadResponse,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    mime: {"schema": {"type": "string", "format": "binary", "maxLength": 10485760}}
                    for mime in ("image/jpeg", "image/png", "image/webp")
                },
            }
        },
        description="One binary attempt for a server-issued intent. Cookie/CSRF/live OWNER and intent are checked before receive. No automatic PUT retry; UNKNOWN requires explicit recovery.",
    )
    async def content(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
        upload_id: CanonicalUUID,
    ) -> UploadResponse:
        no_options(request)
        token = mutation_token(request, settings)
        length = request.headers.get("content-length")
        # AuthBoundary has already checked duplicate/type/length/encoding/header
        # limits and supplies a total 15-second streaming receive wrapper.
        return await service.upload(
            token,
            UUID(workspace_id),
            UUID(business_id),
            UUID(asset_id),
            UUID(version_id),
            UUID(upload_id),
            request.stream(),
            request.headers.get("content-type", "").strip().lower(),
            int(length) if length is not None else None,
        )

    @router.post(
        "/assets/{asset_id}/versions/{version_id}/uploads/{upload_id}/recover",
        response_model=UploadResponse,
        openapi_extra=command_schema(EmptyRequest, receipt=False),
    )
    async def recover(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
        upload_id: CanonicalUUID,
    ) -> UploadResponse:
        no_options(request)
        token = mutation_token(request, settings)
        await body_as(request, EmptyRequest)
        return await service.recover(
            token,
            UUID(workspace_id),
            UUID(business_id),
            UUID(asset_id),
            UUID(version_id),
            UUID(upload_id),
        )

    @router.get(
        "/assets/{asset_id}/versions/{version_id}/preview",
        response_class=Response,
        responses={
            200: {
                "content": {
                    mime: {"schema": {"type": "string", "format": "binary"}}
                    for mime in ("image/jpeg", "image/png", "image/webp")
                }
            }
        },
    )
    async def preview(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
    ) -> Response:
        no_options(request)
        content, mime = await service.preview(
            required_cookie(request, settings),
            UUID(workspace_id),
            UUID(business_id),
            UUID(asset_id),
            UUID(version_id),
        )
        return Response(
            content=content,
            media_type=mime,
            headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"},
        )

    @router.post(
        "/assets/{asset_id}/versions/{version_id}/purge",
        response_model=PurgeResponse,
        openapi_extra=command_schema(EmptyRequest, receipt=False),
    )
    async def purge(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
    ) -> PurgeResponse:
        no_options(request)
        token = mutation_token(request, settings)
        await body_as(request, EmptyRequest)
        return await service.purge(
            token, UUID(workspace_id), UUID(business_id), UUID(asset_id), UUID(version_id)
        )

    @router.post(
        "/assets/{asset_id}/versions/{version_id}/analysis",
        response_model=AnalysisResponse,
        openapi_extra=command_schema(EmptyRequest, receipt=False),
        description="Explicit EVAL_ONLY analysis. Disabled by default; only injected MockTransport can run. Replays use immutable source identity. Lost ACK requires GET/review, never an automatic retry.",
    )
    async def asset_analysis(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
    ) -> AnalysisResponse:
        no_options(request)
        token = mutation_token(request, settings)
        await body_as(request, EmptyRequest)
        return await service.analysis(
            token,
            UUID(workspace_id),
            UUID(business_id),
            asset=UUID(asset_id),
            version=UUID(version_id),
        )

    @router.get("/conversations/{conversation_id}", response_model=ConversationState)
    async def conversation(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> ConversationState:
        no_options(request)
        return await service.conversation(
            required_cookie(request, settings),
            UUID(workspace_id),
            UUID(business_id),
            UUID(conversation_id),
        )

    @router.post(
        "/conversations/{conversation_id}/analysis",
        response_model=AnalysisResponse,
        openapi_extra=command_schema(EmptyRequest, receipt=False),
        description="Explicitly analyse the latest current server-bound client image, then match when controlled embeddings are enabled. HUMAN/Resume/native guards remain active. No photo send.",
    )
    async def reference_analysis(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> AnalysisResponse:
        no_options(request)
        token = mutation_token(request, settings)
        await body_as(request, EmptyRequest)
        return await service.analysis(
            token, UUID(workspace_id), UUID(business_id), conversation=UUID(conversation_id)
        )

    @router.post(
        "/conversations/{conversation_id}/matches",
        response_model=ConversationState,
        openapi_extra=command_schema(EmptyRequest, receipt=False),
        description="Explicit bounded lookup for the current applied analysis. One QUERY, or fresh reselection using the existing compatible vector; no uncertain retry.",
    )
    async def matches(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> ConversationState:
        no_options(request)
        token = mutation_token(request, settings)
        await body_as(request, EmptyRequest)
        return await service.matches(
            token, UUID(workspace_id), UUID(business_id), UUID(conversation_id)
        )

    @router.post(
        "/assets/uploads", response_model=CommandResponse, openapi_extra=command_schema(InitUpload)
    )
    async def init_upload(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, InitUpload)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "PORTFOLIO_UPLOAD_CREATE", key, body
        )

    @router.post(
        "/assets/{asset_id}/versions/{version_id}/uploads/{upload_id}/finalize",
        response_model=CommandResponse,
        openapi_extra=command_schema(FinishUpload),
    )
    async def finalize_upload(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
        upload_id: CanonicalUUID,
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, FinishUpload)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "PORTFOLIO_UPLOAD_FINALIZE",
            key,
            body,
            asset=UUID(asset_id),
            version=UUID(version_id),
            upload=UUID(upload_id),
        )

    @router.post(
        "/assets/{asset_id}/versions/{version_id}/uploads/{upload_id}/abandon",
        response_model=CommandResponse,
        openapi_extra=command_schema(FinishUpload),
    )
    async def abandon_upload(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
        version_id: CanonicalUUID,
        upload_id: CanonicalUUID,
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, FinishUpload)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "PORTFOLIO_UPLOAD_ABANDON",
            key,
            body,
            asset=UUID(asset_id),
            version=UUID(version_id),
            upload=UUID(upload_id),
        )

    @router.post("/items", response_model=CommandResponse, openapi_extra=command_schema(SaveItem))
    async def save_item(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, SaveItem)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "PORTFOLIO_SAVE", key, body
        )

    @router.post(
        "/items/{item_id}/confirm",
        response_model=CommandResponse,
        openapi_extra=command_schema(ConfirmItem),
    )
    async def confirm_item(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        item_id: CanonicalUUID,
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, ConfirmItem)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "PORTFOLIO_CONFIRM",
            key,
            body,
            item=UUID(item_id),
        )

    @router.post(
        "/items/{item_id}/revoke",
        response_model=CommandResponse,
        openapi_extra=command_schema(RevokeItem),
    )
    async def revoke_item(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        item_id: CanonicalUUID,
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, RevokeItem)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "PORTFOLIO_REVOKE",
            key,
            body,
            item=UUID(item_id),
        )

    @router.post(
        "/assets/{asset_id}/delete",
        response_model=CommandResponse,
        openapi_extra=command_schema(DeleteAsset),
    )
    async def delete_asset(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        asset_id: CanonicalUUID,
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, DeleteAsset)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            "PORTFOLIO_DELETE",
            key,
            body,
            asset=UUID(asset_id),
        )

    @router.post(
        "/builds", response_model=CommandResponse, openapi_extra=command_schema(CreateBuild)
    )
    async def build(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, CreateBuild)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "PORTFOLIO_BUILD_CREATE", key, body
        )

    @router.post(
        "/publish", response_model=CommandResponse, openapi_extra=command_schema(PublishPortfolio)
    )
    async def publish(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, PublishPortfolio)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "PORTFOLIO_PUBLISH", key, body
        )

    @router.post(
        "/rollback", response_model=CommandResponse, openapi_extra=command_schema(RollbackPortfolio)
    )
    async def rollback(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CommandResponse:
        key = command_key(request)
        token = mutation_token(request, settings)
        body = await body_as(request, RollbackPortfolio)
        return await service.command(
            token, UUID(workspace_id), UUID(business_id), "PORTFOLIO_ROLLBACK", key, body
        )

    app.include_router(router)
