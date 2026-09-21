"""Messaging capability set is separate from frozen tenancy.v1 permissions."""

from enum import StrEnum

from asm.messaging.errors import Code, MessagingError
from asm.tenancy import TenantUnitOfWork
from asm.tenancy.types import MembershipRole


class Permission(StrEnum):
    READ = "messaging:read"
    SEND = "messaging:send"


async def require(unit: TenantUnitOfWork, permission: Permission) -> None:
    if (
        type(permission) is not Permission
        or await unit.messaging_membership_role() != MembershipRole.OWNER
    ):
        raise MessagingError(Code.ACCESS_DENIED)
