"""Owner-only bounded JSON API using the existing cookie/CSRF boundary."""

from uuid import UUID

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import CanonicalUUID
from asm.configuration.http import body_as, command_key, command_schema, no_options
from asm.intake.errors import IntakeError
from asm.intake.models import (
    CaseCommand,
    CasePage,
    CaseSearch,
    IntakeCommand,
    IntakeProjection,
    IntakeReceipt,
)
from asm.intake.service import IntakeService


def install_intake(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    service = IntakeService(auth)
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}/intake", tags=["intake"]
    )

    @app.exception_handler(IntakeError)
    async def failed(request: Request, error: IntakeError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code.value}},
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/conversations/{conversation_id}", response_model=IntakeProjection)
    async def summary(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> IntakeProjection:
        no_options(request)
        return await service.summary(
            required_cookie(request, settings),
            UUID(workspace_id),
            UUID(business_id),
            UUID(conversation_id),
        )

    @router.post(
        "/conversations/{conversation_id}/confirm",
        response_model=IntakeReceipt,
        openapi_extra=command_schema(IntakeCommand),
    )
    async def confirm(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> IntakeReceipt:
        key, token = command_key(request), mutation_token(request, settings)
        body = await body_as(request, IntakeCommand)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            UUID(conversation_id),
            "CONFIRM",
            key,
            body,
        )

    @router.post(
        "/conversations/{conversation_id}/correct",
        response_model=IntakeReceipt,
        openapi_extra=command_schema(IntakeCommand),
    )
    async def correct(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> IntakeReceipt:
        key, token = command_key(request), mutation_token(request, settings)
        body = await body_as(request, IntakeCommand)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            UUID(conversation_id),
            "CORRECT",
            key,
            body,
        )

    @router.get("/duration-cases", response_model=CasePage)
    async def cases(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID
    ) -> CasePage:
        no_options(request)
        return await service.cases(
            required_cookie(request, settings), UUID(workspace_id), UUID(business_id)
        )

    @router.get("/duration-cases/search", response_model=CaseSearch)
    async def search(
        request: Request,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        placement: str = "",
        style: str = "",
        detail: str = "",
        fill: str = "",
    ) -> CaseSearch:
        from asm.intake.errors import IntakeCode

        if set(request.query_params) - {"placement", "style", "detail", "fill"} or any(
            len(v) > 300 for v in (placement, style, detail, fill)
        ):
            raise IntakeError(IntakeCode.INVALID_INPUT)
        return await service.search(
            required_cookie(request, settings),
            UUID(workspace_id),
            UUID(business_id),
            {"placement": placement, "style": style, "detail": detail, "fill": fill},
        )

    @router.post(
        "/duration-cases/{operation}",
        response_model=IntakeReceipt,
        openapi_extra=command_schema(CaseCommand),
    )
    async def command(
        request: Request, workspace_id: CanonicalUUID, business_id: CanonicalUUID, operation: str
    ) -> IntakeReceipt:
        from asm.intake.errors import IntakeCode

        if operation not in {"create", "edit", "confirm", "revoke"}:
            raise IntakeError(IntakeCode.INVALID_INPUT)
        key, token = command_key(request), mutation_token(request, settings)
        body = await body_as(request, CaseCommand)
        return await service.command(
            token,
            UUID(workspace_id),
            UUID(business_id),
            None,
            "CASE_" + operation.upper(),
            key,
            body,
        )

    app.include_router(router)
