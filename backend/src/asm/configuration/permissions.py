"""Configuration owner authority is separate from ADMIN's tenancy:write."""

from asm.configuration.errors import ConfigurationCode, ConfigurationError
from asm.tenancy import MembershipRole, TenantUnitOfWork


async def require_owner(unit: TenantUnitOfWork) -> None:
    if await unit.billing_membership_role() is not MembershipRole.OWNER:
        raise ConfigurationError(ConfigurationCode.ACCESS_DENIED)
