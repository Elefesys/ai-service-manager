"""Bounded diagnostics; never expose SQL, provider payloads, text or claims."""

from enum import StrEnum

from sqlalchemy.exc import DBAPIError


class Code(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    EVENT_ID_CONFLICT = "EVENT_ID_CONFLICT"
    MESSAGE_ID_CONFLICT = "MESSAGE_ID_CONFLICT"
    CONVERSATION_IDENTITY_CONFLICT = "CONVERSATION_IDENTITY_CONFLICT"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    STALE_CLAIM = "STALE_CLAIM"
    NOT_ALLOWED = "NOT_ALLOWED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    DEPENDENCY_TIMEOUT = "DEPENDENCY_TIMEOUT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    UNKNOWN_EXTERNAL_RESULT = "UNKNOWN_EXTERNAL_RESULT"
    TRANSACTION_STATE = "TRANSACTION_STATE"


class MessagingError(RuntimeError):
    def __init__(self, code: Code) -> None:
        self.code = code
        super().__init__(code.value)


def database_error(error: DBAPIError) -> MessagingError | None:
    # Messaging codes are checked exactly, never inferred from arbitrary SQL text.
    diagnostic = getattr(error.orig, "diag", None)
    message = getattr(diagnostic, "message_primary", None)
    if getattr(error.orig, "sqlstate", "") == "P2001" and message in Code._value2member_map_:
        return MessagingError(Code(str(message)))
    if getattr(error.orig, "sqlstate", "") == "42501":
        return MessagingError(Code.ACCESS_DENIED)
    if getattr(error.orig, "sqlstate", "") in {"40001", "40P01", "55P03"}:
        return MessagingError(Code.DEPENDENCY_UNAVAILABLE)
    return None
