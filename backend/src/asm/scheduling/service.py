"""Scope availability to a single accepted order and its next session."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, ValidationError

from asm.billing.validation import CanonicalUUID
from asm.configuration.models import (
    ConfigurationModel,
    DepositPolicy,
    Identifier,
    Nonblank,
    OccupiedMinutes,
)
from asm.configuration.permissions import require_owner
from asm.scheduling.availability import calculate_windows
from asm.scheduling.models import (
    AvailabilityCommand,
    AvailabilityPreview,
    AvailabilityReason,
    PolicyInput,
    TimeWindow,
)
from asm.scheduling.repository import SchedulingRepository
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.tenancy import TenantUnitOfWork


class StoredProjection(ConfigurationModel):
    # The M6 owner read returns more data than scheduling needs, including
    # private message text. The preview exposes only the accepted terms below.
    model_config = ConfigDict(extra="ignore")


class AcceptedMaterial(StoredProjection):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    request_id: CanonicalUUID
    service_id: Identifier
    service_name: Nonblank = Field(max_length=100)
    deposit: DepositPolicy
    assessment_id: CanonicalUUID
    decision_id: CanonicalUUID | None
    occupied_minutes: OccupiedMinutes | None = None
    duration_reference_id: CanonicalUUID | None = None


class AcceptedQuote(StoredProjection):
    quote_id: CanonicalUUID
    material: AcceptedMaterial


class AcceptedSession(StoredProjection):
    order_id: CanonicalUUID
    session_id: CanonicalUUID
    status: Literal["PLANNED"]
    scheduled_at: None
    quote: AcceptedQuote


class SelectedSession(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    request_id: CanonicalUUID
    quote_id: CanonicalUUID
    order_id: CanonicalUUID
    session_id: CanonicalUUID


async def selected_terms(unit: TenantUnitOfWork, selection: SelectedSession) -> AcceptedMaterial:
    # The M6 read scopes the Request to its actual Business, Conversation and
    # Client, then joins the immutable acceptance, Quote, Order and Session.
    await require_owner(unit)
    raw = await unit.quote_owner_read(
        UUID(selection.business_id), UUID(selection.conversation_id), UUID(selection.request_id)
    )
    if not isinstance(raw, dict):
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
    if raw.get("agreement") is None:
        raise ServiceRequestError(ServiceRequestCode.NOT_FOUND)
    try:
        agreement = AcceptedSession.model_validate(raw["agreement"])
    except ValidationError:
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
    material = agreement.quote.material
    accepted = SelectedSession(
        workspace_id=material.workspace_id,
        business_id=material.business_id,
        conversation_id=material.conversation_id,
        client_id=material.client_id,
        request_id=material.request_id,
        quote_id=agreement.quote.quote_id,
        order_id=agreement.order_id,
        session_id=agreement.session_id,
    )
    if selection != accepted or accepted.workspace_id != str(unit.context.workspace_id):
        raise ServiceRequestError(ServiceRequestCode.NOT_FOUND)
    return material


async def preview_availability(
    unit: TenantUnitOfWork,
    selection: SelectedSession,
    day: date | None,
    command: AvailabilityCommand | None = None,
) -> AvailabilityPreview:
    terms = await selected_terms(unit, selection)
    business, service = UUID(selection.business_id), terms.service_id
    repository = SchedulingRepository(unit)
    if command is not None:
        if command.action == "schedule":
            await repository.put_schedule(business, service, command.timezone, command.week)
        elif command.action == "policy":
            options = PolicyInput.model_validate(command.model_dump(exclude={"action"}))
            await repository.activate_policy(business, service, options)
        else:
            await repository.put_exception(business, service, command.date, command.windows)
            day = command.date

    schedule = await repository.read(business, service, day)
    minutes, reference_id = terms.occupied_minutes, terms.duration_reference_id
    reason: AvailabilityReason | None = None
    windows: list[TimeWindow] = []
    if (
        minutes is None
        or reference_id is None
        or reference_id not in {terms.assessment_id, terms.decision_id}
    ):
        minutes, reference_id = None, None
        reason = "DURATION_UNAVAILABLE"
    elif schedule.exception is not None and not schedule.exception.windows:
        reason = "DATE_CLOSED"
    elif schedule.timezone is None or (not schedule.week and schedule.exception is None):
        reason = "NO_WORKING_HOURS"
    elif schedule.policy is None:
        reason = "NO_ACTIVE_POLICY"
    else:
        windows = calculate_windows(schedule, minutes)
        if not windows:
            reason = "NO_WINDOWS"

    return AvailabilityPreview(
        request_id=selection.request_id,
        quote_id=selection.quote_id,
        order_id=selection.order_id,
        session_id=selection.session_id,
        service_name=terms.service_name,
        occupied_minutes=minutes,
        duration_reference_id=reference_id,
        deposit=terms.deposit,
        date=schedule.date,
        timezone=schedule.timezone,
        resource_id=schedule.resource_id,
        week=schedule.week,
        policy=schedule.policy,
        exception=schedule.exception,
        reason=reason,
        windows=windows,
    )
