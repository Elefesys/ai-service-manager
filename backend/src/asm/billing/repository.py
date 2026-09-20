"""Tenant-scoped queries/command; no independent connection or direct DML."""

from datetime import datetime
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.exc import SQLAlchemyError

from asm.billing.errors import BillingError, BillingUnavailable
from asm.billing.models import (
    AuditCursor,
    AuditItem,
    AuditPage,
    BillingResponse,
    ContactPatch,
    ContactResult,
)
from asm.billing.permissions import BillingPermission, require
from asm.billing.service import EntitlementService
from asm.billing.validation import contact_fingerprint, encode_cursor, timestamp
from asm.tenancy import TenancyError, TenantUnitOfWork

_audit_item: TypeAdapter[AuditItem] = TypeAdapter(AuditItem)


class BillingRepository:
    def __init__(self, unit: TenantUnitOfWork) -> None:
        self.unit = unit

    async def billing(self) -> BillingResponse:
        await require(self.unit, BillingPermission.READ)
        try:
            observed = await self.unit.billing_snapshot()
        except (SQLAlchemyError, TenancyError):
            # Facts were not observed. Never manufacture empty/missing state.
            raise BillingUnavailable("DATABASE_UNAVAILABLE") from None
        return EntitlementService().evaluate(self.unit.context.workspace_id, dict(observed))

    async def change_contact(self, body: ContactPatch, key: str) -> ContactResult:
        await require(self.unit, BillingPermission.MANAGE)
        # The SQL command independently calculates the same fingerprint. Runtime
        # cannot read receipts; cross-language equality is verified by DB tests.
        contact_fingerprint(
            self.unit.context.workspace_id, body.expected_version, body.contact_display_name
        )
        row = await self.unit.billing_contact(
            int(body.expected_version), body.contact_display_name, key
        )
        return ContactResult(
            workspace_id=str(row["workspace_id"]),
            billing_account_id=str(row["billing_account_id"]),
            receipt_id=str(row["receipt_id"]),
            result_version=str(row["result_version"]),
            outcome=row["result_outcome"],
            completed_at=timestamp(row["completed_at"]),
        )

    async def audit(self, limit: int, cursor: AuditCursor | None) -> AuditPage:
        await require(self.unit, BillingPermission.AUDIT)
        at, event_id = None, None
        if cursor is not None:
            if cursor.workspace_id != str(self.unit.context.workspace_id):
                raise BillingError("INVALID_REQUEST", 422)
            at, event_id = datetime.fromisoformat(cursor.occurred_at), UUID(cursor.id)
            if not await self.unit.billing_audit_anchor(at, event_id):
                raise BillingError("INVALID_REQUEST", 422)
        rows = await self.unit.billing_audit_page(limit, at, event_id)
        items: list[AuditItem] = []
        for row in rows[:limit]:
            value = dict(row)
            for key in ("audit_event_id", "actor_user_account_id", "correlation_id", "object_id"):
                if value[key] is not None:
                    value[key] = str(value[key])
            value["occurred_at"] = timestamp(value["occurred_at"])
            value["object_version"] = str(value["object_version"])
            items.append(_audit_item.validate_python(value))
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_cursor(
                AuditCursor(
                    v=1,
                    endpoint="AUDIT_EVENTS",
                    workspace_id=str(self.unit.context.workspace_id),
                    direction="DESC",
                    occurred_at=last.occurred_at,
                    id=last.audit_event_id,
                ).model_dump()
            )
        return AuditPage(items=items, next_cursor=next_cursor)
