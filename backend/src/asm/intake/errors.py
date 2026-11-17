"""Redacted domain errors shared by owner capabilities."""

from enum import StrEnum

from sqlalchemy.exc import DBAPIError


class IntakeCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_STATE = "STALE_STATE"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


class IntakeError(Exception):
    def __init__(self, code: IntakeCode):
        self.code = code
        self.status = {
            "ACCESS_DENIED": 403,
            "NOT_FOUND": 404,
            "INVALID_INPUT": 422,
            "STALE_STATE": 409,
            "IDEMPOTENCY_KEY_CONFLICT": 409,
        }.get(code.value, 503)
        super().__init__(code.value)


def database_error(error: DBAPIError) -> IntakeError:
    primary = getattr(getattr(error.orig, "diag", None), "message_primary", None)
    if getattr(error.orig, "sqlstate", "") in {"P3001", "P2801"} and primary in set(IntakeCode):
        return IntakeError(IntakeCode(primary))
    return IntakeError(IntakeCode.UNAVAILABLE)
