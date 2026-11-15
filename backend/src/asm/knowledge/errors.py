"""Closed knowledge errors; SQL and source/provider payloads stay private."""

from enum import StrEnum

from sqlalchemy.exc import DBAPIError


class KnowledgeCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_STATE = "STALE_STATE"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    SOURCE_LIMIT = "SOURCE_LIMIT"
    SOURCE_DELETED = "SOURCE_DELETED"
    SOURCE_REVOKED = "SOURCE_REVOKED"
    SOURCE_EXPIRED = "SOURCE_EXPIRED"
    SOURCE_STALE = "SOURCE_STALE"
    UNCONFIRMED_SOURCE = "UNCONFIRMED_SOURCE"
    CHUNK_LIMIT = "CHUNK_LIMIT"
    BUILD_NOT_READY = "BUILD_NOT_READY"
    PORTFOLIO_BUILD_REQUIRED = "PORTFOLIO_BUILD_REQUIRED"
    PROFILE_MISMATCH = "PROFILE_MISMATCH"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    INVALID_VECTOR = "INVALID_VECTOR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VERSION_EXHAUSTED = "VERSION_EXHAUSTED"
    ROLLBACK_NOT_ALLOWED = "ROLLBACK_NOT_ALLOWED"
    OPERATION_EXPIRED = "OPERATION_EXPIRED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    UNAVAILABLE = "UNAVAILABLE"


class KnowledgeError(RuntimeError):
    def __init__(self, code: KnowledgeCode) -> None:
        self.code = code
        self.status = {
            KnowledgeCode.ACCESS_DENIED: 403,
            KnowledgeCode.NOT_FOUND: 404,
            KnowledgeCode.INVALID_INPUT: 422,
            KnowledgeCode.CHUNK_LIMIT: 422,
            KnowledgeCode.PROFILE_MISMATCH: 422,
            KnowledgeCode.INVALID_REFERENCE: 422,
            KnowledgeCode.INVALID_VECTOR: 422,
            KnowledgeCode.UNAVAILABLE: 503,
        }.get(code, 409)
        super().__init__(code.value)


def database_error(error: DBAPIError) -> KnowledgeError:
    primary = getattr(getattr(error.orig, "diag", None), "message_primary", None)
    if getattr(error.orig, "sqlstate", "") == "P2801" and primary in {
        code.value for code in KnowledgeCode
    }:
        return KnowledgeError(KnowledgeCode(primary))
    return KnowledgeError(KnowledgeCode.UNAVAILABLE)
