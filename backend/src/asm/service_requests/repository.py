"""Validate results of the owner capabilities within the authenticated transaction."""

from uuid import UUID

from pydantic import ValidationError

from asm.service_requests.errors import ServiceRequestCode, ServiceRequestError
from asm.service_requests.models import (
    ServiceRequestCards,
    ServiceRequestCommand,
    ServiceRequestDraft,
    ServiceRequestReceipt,
    ServiceRequestRevisionCommand,
)
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


def receipt_from_database(raw: object) -> ServiceRequestReceipt:
    try:
        return ServiceRequestReceipt.model_validate(raw)
    except ValidationError:
        raise ServiceRequestError(ServiceRequestCode.UNAVAILABLE) from None
