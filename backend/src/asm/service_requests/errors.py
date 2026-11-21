"""Bounded errors for service request capabilities."""

from enum import StrEnum

from sqlalchemy.exc import DBAPIError


class ServiceRequestCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_STATE = "STALE_STATE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


class ServiceRequestError(Exception):
    def __init__(self, code: ServiceRequestCode):
        self.code = code
        self.status = {
            ServiceRequestCode.ACCESS_DENIED: 403,
            ServiceRequestCode.NOT_FOUND: 404,
            ServiceRequestCode.INVALID_INPUT: 422,
            ServiceRequestCode.STALE_STATE: 409,
            ServiceRequestCode.APPROVAL_EXPIRED: 409,
            ServiceRequestCode.APPROVAL_REVOKED: 409,
            ServiceRequestCode.NEEDS_CLARIFICATION: 409,
            ServiceRequestCode.IDEMPOTENCY_KEY_CONFLICT: 409,
            ServiceRequestCode.UNAVAILABLE: 503,
        }[code]
        super().__init__(code.value)


def database_error(error: DBAPIError) -> ServiceRequestError:
    detail = getattr(getattr(error.orig, "diag", None), "message_primary", None)
    if getattr(error.orig, "sqlstate", "") == "P3101" and detail in set(ServiceRequestCode):
        return ServiceRequestError(ServiceRequestCode(detail))
    return ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
