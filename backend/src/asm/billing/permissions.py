"""Separate owner-only policy; tenancy:write also belongs to ADMIN."""

from enum import StrEnum

from asm.billing.errors import BillingError
from asm.tenancy.database import TenantUnitOfWork
from asm.tenancy.types import MembershipRole


class BillingPermission(StrEnum):
    READ = "billing:read"
    MANAGE = "billing:manage"
    AUDIT = "audit:read"


def permissions_for(role: MembershipRole | None) -> frozenset[BillingPermission]:
    return frozenset(BillingPermission) if role is MembershipRole.OWNER else frozenset()


async def require(unit: TenantUnitOfWork, permission: BillingPermission) -> None:
    if permission not in permissions_for(await unit.billing_membership_role()):
        raise BillingError("ACCESS_DENIED", 403)
