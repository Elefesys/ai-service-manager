"""Business Console routes on the owner session and CSRF boundaries."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, FastAPI, Query, Request, Response

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import CanonicalUUID
from asm.configuration.models import ConfigurationModel
from asm.scheduling.models import AvailabilityCommand, AvailabilityPreview, LocalDate
from asm.scheduling.service import SelectedSession, preview_availability
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError


class AvailabilityQuery(ConfigurationModel):
    client_id: CanonicalUUID
    quote_id: CanonicalUUID
    order_id: CanonicalUUID
    date: LocalDate | None = None


def check_query(request: Request) -> None:
    names = [name for name, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)) or request.headers.getlist("if-match"):
        raise ServiceRequestError(ServiceRequestCode.INVALID_INPUT)


def install_scheduling(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}/intake"
        "/conversations/{conversation_id}/service-requests/{request_id}/sessions/{session_id}",
        tags=["scheduling"],
    )

    async def availability(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        query: AvailabilityQuery,
        command: AvailabilityCommand | None = None,
    ) -> AvailabilityPreview:
        check_query(request)
        token = (
            required_cookie(request, settings)
            if command is None
            else mutation_token(request, settings)
        )
        response.headers["Cache-Control"] = "no-store"
        selection = SelectedSession(
            workspace_id=workspace_id,
            business_id=business_id,
            conversation_id=conversation_id,
            client_id=query.client_id,
            request_id=request_id,
            quote_id=query.quote_id,
            order_id=query.order_id,
            session_id=session_id,
        )
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await preview_availability(unit, selection, query.date, command)

    @router.get("/availability", response_model=AvailabilityPreview)
    async def read_availability(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        query: Annotated[AvailabilityQuery, Query()],
    ) -> AvailabilityPreview:
        return await availability(
            request,
            response,
            workspace_id,
            business_id,
            conversation_id,
            request_id,
            session_id,
            query,
        )

    @router.post(
        "/availability",
        response_model=AvailabilityPreview,
        responses={409: {"description": "STALE_STATE or a missing scheduling prerequisite"}},
    )
    async def change_availability(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        query: Annotated[AvailabilityQuery, Query()],
        command: AvailabilityCommand,
    ) -> AvailabilityPreview:
        return await availability(
            request,
            response,
            workspace_id,
            business_id,
            conversation_id,
            request_id,
            session_id,
            query,
            command,
        )

    app.include_router(router)
