"""Bounded errors for service request capabilities."""

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from sqlalchemy.exc import DBAPIError

from asm.billing.validation import CanonicalUUID


class ServiceRequestCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_STATE = "STALE_STATE"
    DURATION_UNAVAILABLE = "DURATION_UNAVAILABLE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    CALENDAR_CONFLICT = "CALENDAR_CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


class ServiceRequestError(Exception):
    def __init__(self, code: ServiceRequestCode):
        self.code = code
        self.status = {
            ServiceRequestCode.ACCESS_DENIED: 403,
            ServiceRequestCode.NOT_FOUND: 404,
            ServiceRequestCode.INVALID_INPUT: 422,
            ServiceRequestCode.STALE_STATE: 409,
            ServiceRequestCode.DURATION_UNAVAILABLE: 409,
            ServiceRequestCode.APPROVAL_EXPIRED: 409,
            ServiceRequestCode.APPROVAL_REVOKED: 409,
            ServiceRequestCode.NEEDS_CLARIFICATION: 409,
            ServiceRequestCode.IDEMPOTENCY_KEY_CONFLICT: 409,
            ServiceRequestCode.CALENDAR_CONFLICT: 409,
            ServiceRequestCode.UNAVAILABLE: 503,
        }[code]
        super().__init__(code.value)


class AffectedAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["HOLD", "BLOCK", "APPOINTMENT"]
    id: CanonicalUUID


class CalendarConflict(ServiceRequestError):
    def __init__(self, affected: list[AffectedAllocation]):
        self.affected = affected
        super().__init__(ServiceRequestCode.CALENDAR_CONFLICT)


def calendar_conflict(affected: object) -> ServiceRequestError:
    try:
        return CalendarConflict(TypeAdapter(list[AffectedAllocation]).validate_python(affected))
    except ValidationError:
        return ServiceRequestError(ServiceRequestCode.UNAVAILABLE)


def database_error(error: DBAPIError) -> ServiceRequestError:
    if getattr(error.orig, "sqlstate", "") == "P3101":
        diagnostic = getattr(error.orig, "diag", None)
        code = getattr(diagnostic, "message_primary", None)
        if code == ServiceRequestCode.CALENDAR_CONFLICT:
            detail = getattr(diagnostic, "message_detail", None)
            if not isinstance(detail, str):
                return ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
            try:
                return calendar_conflict(json.loads(detail))
            except (TypeError, ValueError, RecursionError):
                return ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
        if code in set(ServiceRequestCode):
            return ServiceRequestError(ServiceRequestCode(code))
    return ServiceRequestError(ServiceRequestCode.UNAVAILABLE)
