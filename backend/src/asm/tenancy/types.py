"""Server-only tenancy values. None of these types authenticates a request."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal
from uuid import UUID

SCHEMA_REVISION = "0002"
CONTEXT_SETTINGS = (
    "asm.workspace_id",
    "asm.actor_id",
    "asm.actor_kind",
    "asm.correlation_id",
    "asm.context_xid",
)


class ErrorCode(StrEnum):
    CONTEXT_REQUIRED = "CONTEXT_REQUIRED"
    CONTEXT_INVALID = "CONTEXT_INVALID"
    ACCESS_DENIED = "ACCESS_DENIED"
    TRANSACTION_STATE = "TRANSACTION_STATE"
    NOT_FOUND = "NOT_FOUND"
    STALE_STATE = "STALE_STATE"
    INVALID_RELATION = "INVALID_RELATION"
    INVALID_STATE = "INVALID_STATE"
    CONFLICT = "CONFLICT"
    RETRY_TRANSACTION = "RETRY_TRANSACTION"


class TenancyError(RuntimeError):
    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class Permission(StrEnum):
    READ = "tenancy:read"
    WRITE = "tenancy:write"


class MembershipRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    PROVIDER = "PROVIDER"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


def permissions_for(role: MembershipRole) -> frozenset[Permission]:
    if role in (MembershipRole.OWNER, MembershipRole.ADMIN):
        return frozenset((Permission.READ, Permission.WRITE))
    if role is MembershipRole.PROVIDER:
        return frozenset((Permission.READ,))
    raise TenancyError(ErrorCode.ACCESS_DENIED)


def require_uuid(value: object) -> None:
    if not isinstance(value, UUID):
        raise TenancyError(ErrorCode.CONTEXT_INVALID)


@dataclass(frozen=True, slots=True)
class AuthenticatedAccount:
    """Created ONLY by a trusted auth adapter, never from a claimed request ID."""

    user_account_id: UUID
    kind: Literal["user_account"] = field(default="user_account", init=False)

    def __post_init__(self) -> None:
        require_uuid(self.user_account_id)


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    workspace_id: UUID
    actor: AuthenticatedAccount
    permissions: frozenset[Permission]
    correlation_id: UUID
