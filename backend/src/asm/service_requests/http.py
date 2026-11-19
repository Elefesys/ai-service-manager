"""Console draft routes on the existing owner, cookie and CSRF boundaries."""

from uuid import UUID

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import CanonicalUUID
from asm.configuration.http import body_as, command_key, command_schema
from asm.configuration.permissions import require_owner
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.service_requests.models import (
    ServiceRequestCommand,
    ServiceRequestDraft,
    ServiceRequestReceipt,
)
from asm.service_requests.repository import ServiceRequestRepository


def install_service_requests(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}/intake"
        "/conversations/{conversation_id}/service-requests",
        tags=["service-requests"],
    )

    @app.exception_handler(ServiceRequestError)
    async def failed(request: Request, error: ServiceRequestError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code.value}},
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("", response_model=ServiceRequestDraft | None)
    async def read(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID | None = None,
    ) -> ServiceRequestDraft | None:
        names = [name for name, _ in request.query_params.multi_items()]
        if names not in ([], ["request_id"]) or request.headers.getlist("if-match"):
            raise ServiceRequestError(ServiceRequestCode.INVALID_INPUT)
        response.headers["Cache-Control"] = "no-store"
        token = required_cookie(request, settings)
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            await require_owner(unit)
            return await ServiceRequestRepository(unit).read(
                UUID(business_id),
                UUID(conversation_id),
                UUID(request_id) if request_id is not None else None,
            )

    @router.post(
        "",
        response_model=ServiceRequestReceipt,
        openapi_extra=command_schema(ServiceRequestCommand),
    )
    async def create(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
    ) -> ServiceRequestReceipt:
        key, token = command_key(request), mutation_token(request, settings)
        command = await body_as(request, ServiceRequestCommand)
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            await require_owner(unit)
            return await ServiceRequestRepository(unit).create(
                UUID(business_id), UUID(conversation_id), key, command
            )

    app.include_router(router)
