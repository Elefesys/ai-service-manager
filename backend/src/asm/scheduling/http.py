"""Business Console routes on the owner session and CSRF boundaries."""

from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.models import EmptyRequest
from asm.auth.service import AuthService
from asm.billing.validation import CanonicalUUID
from asm.configuration.http import body_as, command_key, command_schema, no_options
from asm.configuration.models import ConfigurationModel
from asm.scheduling.commands import (
    AppointmentChange,
    AvailabilityOffer,
    CalendarBlock,
    CalendarBlockInput,
    CalendarConflictResult,
    cancel_appointment,
    change_owner_day_exception,
    create_block,
    issue_offer,
    issue_reschedule_offer,
    read_booking,
    read_owner_day,
    read_owner_day_conflicts,
    release_block,
    reschedule_appointment,
)
from asm.scheduling.models import (
    OWNER_CONFLICT_LOOKUP_LIMIT,
    AppointmentReason,
    AvailabilityCommand,
    AvailabilityPreview,
    LocalDate,
    OwnerDay,
    OwnerDayConflicts,
    OwnerDayException,
    SessionBooking,
)
from asm.scheduling.service import SelectedSession, preview_availability
from asm.service_requests.errors import (
    AffectedAllocation,
    CalendarConflict,
    ServiceRequestCode,
    ServiceRequestError,
)


class SessionReferences(ConfigurationModel):
    client_id: CanonicalUUID
    quote_id: CanonicalUUID
    order_id: CanonicalUUID


class AvailabilityQuery(SessionReferences):
    date: LocalDate | None = None


class OwnerDayQuery(ConfigurationModel):
    date: LocalDate | None = None


class OwnerDayConflictsQuery(ConfigurationModel):
    appointment_id: list[CanonicalUUID] = Field(
        default_factory=list, max_length=OWNER_CONFLICT_LOOKUP_LIMIT
    )
    hold_id: list[CanonicalUUID] = Field(
        default_factory=list, max_length=OWNER_CONFLICT_LOOKUP_LIMIT
    )
    block_id: list[CanonicalUUID] = Field(
        default_factory=list, max_length=OWNER_CONFLICT_LOOKUP_LIMIT
    )

    @model_validator(mode="after")
    def bounded(self) -> Self:
        count = len(self.appointment_id) + len(self.hold_id) + len(self.block_id)
        if not 1 <= count <= OWNER_CONFLICT_LOOKUP_LIMIT:
            raise ValueError("Provide one to 32 affected identifiers")
        return self

    def affected(self) -> list[AffectedAllocation]:
        return [
            *(AffectedAllocation(kind="APPOINTMENT", id=value) for value in self.appointment_id),
            *(AffectedAllocation(kind="HOLD", id=value) for value in self.hold_id),
            *(AffectedAllocation(kind="BLOCK", id=value) for value in self.block_id),
        ]


class AppointmentCancellation(SessionReferences):
    reason: AppointmentReason


class AppointmentReschedule(AppointmentCancellation):
    option_id: CanonicalUUID


class SchedulingConflictDetail(ConfigurationModel):
    code: ServiceRequestCode
    affected: list[AffectedAllocation] | None = None


class SchedulingConflictResponse(ConfigurationModel):
    error: SchedulingConflictDetail


def check_query(request: Request) -> None:
    names = [name for name, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)) or request.headers.getlist("if-match"):
        raise ServiceRequestError(ServiceRequestCode.INVALID_INPUT)


def selected_session(
    workspace_id: str,
    business_id: str,
    conversation_id: str,
    request_id: str,
    session_id: str,
    references: SessionReferences,
) -> SelectedSession:
    return SelectedSession(
        workspace_id=workspace_id,
        business_id=business_id,
        conversation_id=conversation_id,
        client_id=references.client_id,
        request_id=request_id,
        quote_id=references.quote_id,
        order_id=references.order_id,
        session_id=session_id,
    )


def install_scheduling(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    business_path = "/api/v1/workspaces/{workspace_id}/businesses/{business_id}"
    router = APIRouter(
        prefix=business_path + "/intake/conversations/{conversation_id}"
        "/service-requests/{request_id}/sessions/{session_id}",
        tags=["scheduling"],
    )
    calendar = APIRouter(prefix=business_path + "/scheduling", tags=["scheduling"])

    @app.exception_handler(CalendarConflict)
    async def calendar_conflict_response(
        _request: Request, error: CalendarConflict
    ) -> JSONResponse:
        body = SchedulingConflictResponse(
            error=SchedulingConflictDetail(code=error.code, affected=error.affected)
        )
        return JSONResponse(
            body.model_dump(mode="json", exclude_none=True),
            status_code=error.status,
            headers={"Cache-Control": "no-store"},
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
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, query
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
        responses={
            409: {
                "model": SchedulingConflictResponse,
                "description": (
                    "STALE_STATE, a missing scheduling prerequisite, or CALENDAR_CONFLICT "
                    "with affected allocations"
                ),
            },
        },
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

    @router.post(
        "/availability-offers",
        response_model=AvailabilityOffer,
        openapi_extra=command_schema(AvailabilityQuery),
        description="Persist the currently available options for this agreed session.",
    )
    async def issue_availability_offer(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
    ) -> AvailabilityOffer:
        token = mutation_token(request, settings)
        key = command_key(request)
        references = await body_as(request, AvailabilityQuery)
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, references
        )
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await issue_offer(unit, selection, references.date, key)

    @router.get("/booking", response_model=SessionBooking)
    async def read_session_booking(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        query: Annotated[SessionReferences, Query()],
    ) -> SessionBooking:
        check_query(request)
        token = required_cookie(request, settings)
        response.headers["Cache-Control"] = "no-store"
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, query
        )
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await read_booking(unit, selection)

    @router.post(
        "/booking/{appointment_id}/reschedule-offers",
        response_model=AvailabilityOffer,
        openapi_extra=command_schema(AvailabilityQuery),
        description="Issue replacement options for the current appointment of this session.",
    )
    async def offer_appointment_reschedule(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        appointment_id: CanonicalUUID,
    ) -> AvailabilityOffer:
        token = mutation_token(request, settings)
        key = command_key(request)
        references = await body_as(request, AvailabilityQuery)
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, references
        )
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await issue_reschedule_offer(
                unit, selection, UUID(appointment_id), references.date, key
            )

    @router.post(
        "/booking/{appointment_id}/reschedule",
        response_model=AppointmentChange,
        openapi_extra=command_schema(AppointmentReschedule),
        responses={
            409: {
                "model": SchedulingConflictResponse,
                "description": "Calendar conflict, stale appointment or offer, or mismatched retry",
            },
        },
    )
    async def move_session_appointment(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        appointment_id: CanonicalUUID,
    ) -> AppointmentChange:
        token = mutation_token(request, settings)
        key = command_key(request)
        body = await body_as(request, AppointmentReschedule)
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, body
        )
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            result = await reschedule_appointment(
                unit, selection, UUID(appointment_id), UUID(body.option_id), body.reason, key
            )
        if isinstance(result, CalendarConflictResult):
            raise CalendarConflict(result.affected)
        return result

    @router.post(
        "/booking/{appointment_id}/cancel",
        response_model=AppointmentChange,
        openapi_extra=command_schema(AppointmentCancellation),
    )
    async def cancel_session_appointment(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        appointment_id: CanonicalUUID,
    ) -> AppointmentChange:
        token = mutation_token(request, settings)
        key = command_key(request)
        body = await body_as(request, AppointmentCancellation)
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, body
        )
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await cancel_appointment(unit, selection, UUID(appointment_id), body.reason, key)

    @calendar.get(
        "/day",
        response_model=OwnerDay,
        description="Read this business's calendar day, defaulting to today in the resource time zone.",
    )
    async def read_calendar_day(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        query: Annotated[OwnerDayQuery, Query()],
    ) -> OwnerDay:
        check_query(request)
        token = required_cookie(request, settings)
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await read_owner_day(unit, UUID(business_id), query.date)

    @calendar.post(
        "/day/exception",
        response_model=OwnerDay,
        responses={
            409: {
                "model": SchedulingConflictResponse,
                "description": "Stale calendar revision or conflict with a protected booking",
            },
        },
        description="Save or remove a date exception for the displayed resource and version.",
    )
    async def change_calendar_day_exception(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        command: OwnerDayException,
    ) -> OwnerDay:
        no_options(request)
        token = mutation_token(request, settings)
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await change_owner_day_exception(unit, UUID(business_id), command)

    @calendar.get(
        "/conflicts",
        response_model=OwnerDayConflicts,
        description="Resolve up to 32 affected calendar identifiers in this business.",
    )
    async def read_calendar_conflicts(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        query: Annotated[OwnerDayConflictsQuery, Query()],
    ) -> OwnerDayConflicts:
        if request.headers.getlist("if-match"):
            raise ServiceRequestError(ServiceRequestCode.INVALID_INPUT)
        token = required_cookie(request, settings)
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await read_owner_day_conflicts(unit, UUID(business_id), query.affected())

    @calendar.post(
        "/blocks",
        response_model=CalendarBlock,
        openapi_extra=command_schema(CalendarBlockInput),
        responses={
            409: {
                "model": SchedulingConflictResponse,
                "description": "Conflict with an active allocation or a different retry",
            },
        },
    )
    async def create_calendar_block(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
    ) -> CalendarBlock:
        token = mutation_token(request, settings)
        key = command_key(request)
        block = await body_as(request, CalendarBlockInput)
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            result = await create_block(unit, UUID(business_id), block, key)
        if isinstance(result, CalendarConflictResult):
            raise CalendarConflict(result.affected)
        return result

    @calendar.post(
        "/blocks/{block_id}/release",
        response_model=CalendarBlock,
        openapi_extra=command_schema(EmptyRequest),
    )
    async def release_calendar_block(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        block_id: CanonicalUUID,
    ) -> CalendarBlock:
        token = mutation_token(request, settings)
        key = command_key(request)
        await body_as(request, EmptyRequest)
        response.headers["Cache-Control"] = "no-store"
        async with auth.workspace(token, UUID(workspace_id)) as unit:
            return await release_block(unit, UUID(business_id), UUID(block_id), key)

    app.include_router(router)
    app.include_router(calendar)
