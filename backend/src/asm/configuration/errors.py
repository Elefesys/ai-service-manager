"""Closed configuration errors; never expose SQL, payloads or credentials."""

from enum import StrEnum


class ConfigurationCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_STATE = "STALE_STATE"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VERSION_EXHAUSTED = "VERSION_EXHAUSTED"
    ROLLBACK_NOT_ALLOWED = "ROLLBACK_NOT_ALLOWED"
    UNAVAILABLE = "UNAVAILABLE"


class ConfigurationError(RuntimeError):
    def __init__(self, code: ConfigurationCode) -> None:
        self.code = code
        self.status = {
            ConfigurationCode.ACCESS_DENIED: 403,
            ConfigurationCode.NOT_FOUND: 404,
            ConfigurationCode.INVALID_INPUT: 422,
            ConfigurationCode.UNAVAILABLE: 503,
        }.get(code, 409)
        super().__init__(code.value)
