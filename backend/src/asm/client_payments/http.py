"""Owner Console access to an accepted prepayment obligation."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, Query, Request, Response
from pydantic import Field, ValidationError

from asm.auth.config import AuthSettings
from asm.auth.http import mutation_token, required_cookie
from asm.auth.service import AuthService
from asm.billing.validation import CanonicalUUID, PositiveDecimal, Timestamp
from asm.configuration.http import body_as, command_key, command_schema
from asm.configuration.models import ConfigurationModel, PriceMinor
from asm.intake.models import Digest
from asm.scheduling.http import SessionReferences, check_query, selected_session
from asm.scheduling.service import SelectedSession
from asm.service_requests.approvals import ProvisionalPriceRange
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError


class HoldReferences(SessionReferences):
    hold_id: CanonicalUUID


class PaymentObligation(ConfigurationModel):
    id: CanonicalUUID
    status: Literal["UNPAID"]
    quote_version: PositiveDecimal
    terms_sha256: Digest
    deposit_terms_version: CanonicalUUID
    acceptance_id: CanonicalUUID
    currency: Literal["RUB"]
    price_minor: PriceMinor | None
    price_range: ProvisionalPriceRange | None
    mode: Literal["FIXED_DEPOSIT", "PERCENT_DEPOSIT", "FULL_PREPAYMENT"]
    amount_minor: PriceMinor
    percent: Annotated[int, Field(ge=1, le=100)] | None
    rounding_version: Literal["HALF_UP_V1"] | None


class HoldPaymentObligation(ConfigurationModel):
    hold_id: CanonicalUUID
    allocation_id: CanonicalUUID
    expires_at: Timestamp
    hold_status: Literal["HELD", "EXPIRED", "RELEASED", "CONFIRMED"]
    requires_prepayment: bool
    obligation: PaymentObligation | None


def install_client_payments(app: FastAPI, auth: AuthService, settings: AuthSettings) -> None:
    router = APIRouter(
        prefix="/api/v1/workspaces/{workspace_id}/businesses/{business_id}"
        "/intake/conversations/{conversation_id}/service-requests/{request_id}/sessions/{session_id}",
        tags=["client-payments"],
    )

    async def load(
        token: str,
        selection: SelectedSession,
        hold_id: str,
        key: str | None,
    ) -> HoldPaymentObligation:
        async with auth.workspace(token, UUID(selection.workspace_id)) as unit:
            raw = await unit.payment_obligation_owner(
                selection.model_dump(mode="json"), UUID(hold_id), key
            )
            try:
                return HoldPaymentObligation.model_validate(raw)
            except ValidationError:
                raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None

    @router.get("/payment-obligation", response_model=HoldPaymentObligation)
    async def read_payment_obligation(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
        query: Annotated[HoldReferences, Query()],
    ) -> HoldPaymentObligation:
        check_query(request)
        token = required_cookie(request, settings)
        response.headers["Cache-Control"] = "no-store"
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, query
        )
        return await load(token, selection, query.hold_id, None)

    @router.post(
        "/payment-obligation",
        response_model=HoldPaymentObligation,
        openapi_extra=command_schema(HoldReferences),
        responses={
            409: {"description": "Expired or released hold, conflicting key, or clarification required"},
        },
        description=(
            "Open the agreed prepayment obligation for an active hold. "
            "Replay returns the original obligation and the current hold status."
        ),
    )
    async def open_payment_obligation(
        request: Request,
        response: Response,
        workspace_id: CanonicalUUID,
        business_id: CanonicalUUID,
        conversation_id: CanonicalUUID,
        request_id: CanonicalUUID,
        session_id: CanonicalUUID,
    ) -> HoldPaymentObligation:
        token = mutation_token(request, settings)
        key = command_key(request)
        references = await body_as(request, HoldReferences)
        response.headers["Cache-Control"] = "no-store"
        selection = selected_session(
            workspace_id, business_id, conversation_id, request_id, session_id, references
        )
        return await load(token, selection, references.hold_id, key)

    app.include_router(router)
