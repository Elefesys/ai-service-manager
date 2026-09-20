"""Bounded domain errors; command diagnostics are never returned or logged."""

from sqlalchemy.exc import DBAPIError

from asm.billing.models import CommonCode, StateReason


class BillingError(RuntimeError):
    def __init__(self, code: CommonCode, status: int) -> None:
        self.code, self.status = code, status
        super().__init__(code)


class BillingUnavailable(RuntimeError):
    def __init__(self, reason: StateReason) -> None:
        self.reason = reason
        super().__init__("BILLING_STATE_UNAVAILABLE")


def contact_error(error: DBAPIError) -> BillingError | None:
    # Only the fixed contact command's intentional RAISEs have domain meaning.
    # A serialization failure elsewhere (including a trigger) stays infrastructure.
    diagnostic = getattr(error.orig, "diag", None)
    message = getattr(diagnostic, "message_primary", None)
    if not isinstance(message, str):
        return None
    context = getattr(diagnostic, "context", "") or ""
    if not context.startswith(
        "PL/pgSQL function platform.update_billing_contact(bigint,text,text)"
    ):
        return None
    mapping: dict[tuple[str, str], tuple[CommonCode, int]] = {
        ("40001", "stale state"): ("STALE_STATE", 409),
        ("23505", "idempotency key conflict"): ("IDEMPOTENCY_KEY_CONFLICT", 409),
        ("P0002", "billing account not found"): ("NOT_FOUND", 404),
        ("22023", "invalid request"): ("INVALID_REQUEST", 422),
        ("42501", "access denied"): ("ACCESS_DENIED", 403),
        ("42501", "invalid workspace context"): ("ACCESS_DENIED", 403),
    }
    result = mapping.get((getattr(error.orig, "sqlstate", ""), message))
    return BillingError(*result) if result is not None else None
