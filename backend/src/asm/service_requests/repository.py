"""Validate results of the owner capabilities within the authenticated transaction."""

from uuid import UUID

from pydantic import ValidationError

from asm.service_requests.assessment import (
    AssessmentCommand,
    AssessmentInputs,
    ServiceAssessment,
    evaluate,
)
from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.service_requests.models import (
    ServiceRequestCards,
    ServiceRequestCommand,
    ServiceRequestDraft,
    ServiceRequestReceipt,
    ServiceRequestRevisionCommand,
)
from asm.service_requests.pricing import PriceCalculation, PriceCommand, PriceHistory
from asm.tenancy import TenantUnitOfWork


class ServiceRequestRepository:
    def __init__(self, unit: TenantUnitOfWork):
        self.unit = unit

    async def read(
        self, business: UUID, conversation: UUID, request_id: UUID | None
    ) -> ServiceRequestDraft | None:
        raw = await self.unit.service_request_owner_read(business, conversation, request_id)
        if raw is None and request_id is None:
            return None
        if raw is None:
            raise ServiceRequestError(ServiceRequestCode.NOT_FOUND)
        try:
            draft = ServiceRequestDraft.model_validate(raw)
        except ValidationError:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
        if (
            (draft.workspace_id, draft.business_id, draft.conversation_id)
            != (str(self.unit.context.workspace_id), str(business), str(conversation))
            or request_id is not None
            and draft.request_id != str(request_id)
        ):
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        return draft

    async def list_cards(self, business: UUID, conversation: UUID) -> ServiceRequestCards:
        raw = await self.unit.service_request_owner_list(business, conversation)
        try:
            return ServiceRequestCards.model_validate(raw)
        except ValidationError:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None

    async def create(
        self, business: UUID, conversation: UUID, key: str, body: ServiceRequestCommand
    ) -> ServiceRequestReceipt:
        raw = await self.unit.service_request_owner_create(
            business, conversation, key, body.model_dump(mode="json")
        )
        return receipt_from_database(raw)

    async def revise(
        self,
        business: UUID,
        conversation: UUID,
        request_id: UUID,
        key: str,
        body: ServiceRequestRevisionCommand,
    ) -> ServiceRequestReceipt:
        raw = await self.unit.service_request_owner_revise(
            business, conversation, request_id, key, body.model_dump(mode="json")
        )
        receipt = receipt_from_database(raw)
        if receipt.request_id != str(request_id):
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        return receipt

    async def read_assessment(
        self, business: UUID, conversation: UUID, request_id: UUID
    ) -> ServiceAssessment | None:
        raw = await self.unit.service_assessment_read(business, conversation, request_id)
        return None if raw is None else assessment_from_database(raw, request_id)

    async def assess(
        self, business: UUID, conversation: UUID, request_id: UUID, command: AssessmentCommand
    ) -> ServiceAssessment:
        raw = await self.unit.service_assessment_prepare(
            business, conversation, request_id, command.expected_revision
        )
        try:
            inputs = AssessmentInputs.model_validate(raw)
        except ValidationError:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
        if (
            inputs.workspace_id,
            inputs.business_id,
            inputs.conversation_id,
            inputs.request_id,
            inputs.request_revision,
        ) != (
            str(self.unit.context.workspace_id),
            str(business),
            str(conversation),
            str(request_id),
            command.expected_revision,
        ):
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        decision = evaluate(inputs)
        receipt = await self.unit.service_assessment_record(
            business,
            conversation,
            request_id,
            command.model_dump()
            | {"authority_sha256": inputs.authority_sha256}
            | decision.model_dump(),
        )
        result = assessment_from_database(receipt, request_id)
        if not result.current or (
            result.request_revision,
            result.release_id,
            result.activation_version,
        ) != (
            inputs.request_revision,
            inputs.release_id,
            inputs.activation_version,
        ):
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        return result

    async def price(
        self, business: UUID, conversation: UUID, request_id: UUID, command: PriceCommand
    ) -> PriceCalculation:
        raw = await self.unit.price_calculate(
            business, conversation, request_id, command.expected_revision
        )
        try:
            value = PriceCalculation.model_validate(raw)
        except ValidationError:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
        if not value.current or (value.request_id, value.request_revision) != (
            str(request_id),
            command.expected_revision,
        ):
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        return value

    async def price_history(
        self, business: UUID, conversation: UUID, request_id: UUID, before_id: UUID | None
    ) -> PriceHistory:
        raw = await self.unit.price_history(business, conversation, request_id, before_id)
        try:
            history = PriceHistory.model_validate(raw)
        except ValidationError:
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
        if any(item.request_id != str(request_id) for item in history.items):
            raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        return history


def receipt_from_database(raw: object) -> ServiceRequestReceipt:
    try:
        return ServiceRequestReceipt.model_validate(raw)
    except ValidationError:
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None


def assessment_from_database(raw: object, request_id: UUID) -> ServiceAssessment:
    try:
        value = ServiceAssessment.model_validate(raw)
    except ValidationError:
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
    if value.request_id != str(request_id):
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
    return value
