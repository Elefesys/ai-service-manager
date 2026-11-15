"""Closed public errors; database/provider/storage details remain private."""

from enum import StrEnum

from sqlalchemy.exc import DBAPIError


class PortfolioCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_STATE = "STALE_STATE"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    ASSET_LIMIT = "ASSET_LIMIT"
    UPLOAD_LIMIT = "UPLOAD_LIMIT"
    UPLOAD_NOT_ALLOWED = "UPLOAD_NOT_ALLOWED"
    ASSET_UNAVAILABLE = "ASSET_UNAVAILABLE"
    ASSET_DELETED = "ASSET_DELETED"
    ORIGIN_IMMUTABLE = "ORIGIN_IMMUTABLE"
    UPLOAD_PENDING = "UPLOAD_PENDING"
    UPLOAD_NOT_READY = "UPLOAD_NOT_READY"
    MANIFEST_MISMATCH = "MANIFEST_MISMATCH"
    INVALID_IMAGE = "INVALID_IMAGE"
    ITEM_LIMIT = "ITEM_LIMIT"
    ITEM_EXISTS = "ITEM_EXISTS"
    MY_WORK_REQUIRED = "MY_WORK_REQUIRED"
    UNCONFIRMED_SOURCE = "UNCONFIRMED_SOURCE"
    CLIENT_MODEL_NOT_ALLOWED = "CLIENT_MODEL_NOT_ALLOWED"
    INVALID_VECTOR = "INVALID_VECTOR"
    SOURCE_STALE = "SOURCE_STALE"
    SOURCE_REVOKED = "SOURCE_REVOKED"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    BUILD_NOT_READY = "BUILD_NOT_READY"
    PROFILE_MISMATCH = "PROFILE_MISMATCH"
    WIRE_LIMIT = "WIRE_LIMIT"
    QUERY_LIMIT = "QUERY_LIMIT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VERSION_EXHAUSTED = "VERSION_EXHAUSTED"
    ROLLBACK_NOT_ALLOWED = "ROLLBACK_NOT_ALLOWED"
    KNOWLEDGE_BUILD_REQUIRED = "KNOWLEDGE_BUILD_REQUIRED"
    SESSION_NOT_ALLOWED = "SESSION_NOT_ALLOWED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    MEDIA_UNAVAILABLE = "MEDIA_UNAVAILABLE"
    NOT_ALLOWED = "NOT_ALLOWED"
    DEPENDENCY_TIMEOUT = "DEPENDENCY_TIMEOUT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PortfolioError(RuntimeError):
    def __init__(self, code: PortfolioCode):
        self.code = code
        self.status = {
            PortfolioCode.ACCESS_DENIED: 403,
            PortfolioCode.NOT_FOUND: 404,
            PortfolioCode.INVALID_INPUT: 422,
            PortfolioCode.INVALID_IMAGE: 422,
            PortfolioCode.MANIFEST_MISMATCH: 422,
            PortfolioCode.WIRE_LIMIT: 422,
            PortfolioCode.QUERY_LIMIT: 422,
            PortfolioCode.INVALID_REFERENCE: 422,
            PortfolioCode.PROFILE_MISMATCH: 422,
            PortfolioCode.DEPENDENCY_TIMEOUT: 503,
            PortfolioCode.DEPENDENCY_UNAVAILABLE: 503,
            PortfolioCode.UNAVAILABLE: 503,
        }.get(code, 409)
        super().__init__(code.value)


def database_error(error: DBAPIError) -> PortfolioError:
    primary = getattr(getattr(error.orig, "diag", None), "message_primary", None)
    if getattr(error.orig, "sqlstate", "") == "P2901" and primary in {
        v.value for v in PortfolioCode
    }:
        return PortfolioError(PortfolioCode(primary))
    return PortfolioError(PortfolioCode.UNAVAILABLE)
