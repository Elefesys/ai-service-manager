"""Strict R4 DTOs used by both HTTP responses and generated OpenAPI."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from asm.billing.validation import (
    CanonicalUUID,
    CapabilityKey,
    ContactNameInput,
    LimitDecimal,
    PositiveDecimal,
    Timestamp,
    normalize_name,
)

Mode = Literal["NORMAL", "GRACE", "LIMITED", "SUSPENDED"]
Criticality = Literal["ESSENTIAL", "STANDARD", "EXPENSIVE_OPTIONAL"]
DisabledReason = Literal[
    "SUBSCRIPTION_INACTIVE", "SERVICE_MODE_INACTIVE", "NOT_ENTITLED", "SERVICE_MODE_RESTRICTED"
]
StateReason = Literal[
    "BILLING_STATE_MISSING", "BILLING_STATE_INVALID", "REVISION_INVALID", "DATABASE_UNAVAILABLE"
]
CommonCode = Literal[
    "SESSION_REQUIRED",
    "ORIGIN_DENIED",
    "CSRF_REJECTED",
    "ACCESS_DENIED",
    "BODY_TOO_LARGE",
    "UNSUPPORTED_MEDIA_TYPE",
    "INVALID_REQUEST",
    "RATE_LIMITED",
    "UNAVAILABLE",
    "INTERNAL_ERROR",
    "NOT_FOUND",
    "STALE_STATE",
    "IDEMPOTENCY_KEY_CONFLICT",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class CommonErrorDetail(StrictModel):
    code: CommonCode


class CommonError(StrictModel):
    error: CommonErrorDetail


class BillingStateDetail(StrictModel):
    code: Literal["BILLING_STATE_UNAVAILABLE"]
    state_reason: StateReason


class BillingStateError(StrictModel):
    error: BillingStateDetail


class ContactPatch(StrictModel):
    expected_version: PositiveDecimal
    contact_display_name: str = Field(
        min_length=1,
        max_length=200,
        repr=False,
        description="Trim U+0020 only, then 1..200 Unicode scalars, <=800 UTF-8 bytes; no C0/DEL/surrogates.",
    )

    @field_validator("contact_display_name", mode="before", json_schema_input_type=ContactNameInput)
    @classmethod
    def name(cls, value: object) -> str:
        return normalize_name(value)


class BillingAccount(StrictModel):
    billing_account_id: CanonicalUUID
    contact_display_name: str = Field(min_length=1, max_length=200, repr=False)
    version: PositiveDecimal


class Plan(StrictModel):
    plan_id: CanonicalUUID
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    revision_id: CanonicalUUID
    revision: int = Field(ge=1)


class Subscription(StrictModel):
    subscription_id: CanonicalUUID
    status: Literal["TRIALING", "ACTIVE"]
    funding_mode: Literal["TRIAL", "COMPED"]
    effective_from: Timestamp
    effective_until: Timestamp
    version: PositiveDecimal
    plan: Plan

    @model_validator(mode="after")
    def funding(self) -> Self:
        if (self.status, self.funding_mode) not in (("TRIALING", "TRIAL"), ("ACTIVE", "COMPED")):
            raise ValueError("Invalid funding")
        return self


class EnabledDecision(StrictModel):
    key: CapabilityKey
    type: Literal["ENABLED"]
    reason: None
    limit: None


class DisabledDecision(StrictModel):
    key: CapabilityKey
    type: Literal["DISABLED"]
    reason: DisabledReason
    limit: None


class LimitDecision(StrictModel):
    key: CapabilityKey
    type: Literal["LIMIT"]
    reason: None
    limit: LimitDecimal


Decision = Annotated[
    EnabledDecision | DisabledDecision | LimitDecision, Field(discriminator="type")
]


class BillingResponse(StrictModel):
    workspace_id: CanonicalUUID
    evaluated_at: Timestamp
    account: BillingAccount
    subscription: Subscription | None
    mode: Mode
    mode_active: bool
    availability: Literal["ACTIVE", "INACTIVE"]
    decisions: list[Decision] = Field(max_length=100, json_schema_extra={"uniqueItems": True})

    @field_validator("decisions")
    @classmethod
    def unique_sorted(cls, value: list[Decision]) -> list[Decision]:
        keys = [d.key for d in value]
        if keys != sorted(set(keys)):
            raise ValueError("Decisions must have unique sorted keys")
        return value


class ContactResult(StrictModel):
    workspace_id: CanonicalUUID
    billing_account_id: CanonicalUUID
    receipt_id: CanonicalUUID
    result_version: PositiveDecimal
    outcome: Literal["UPDATED", "NOOP"]
    completed_at: Timestamp


class ProvisionPayload(StrictModel):
    pass


class ContactPayload(StrictModel):
    changed_fields: list[Literal["contact_display_name"]] = Field(min_length=1, max_length=1)


class AuditBase(StrictModel):
    audit_event_id: CanonicalUUID
    occurred_at: Timestamp
    correlation_id: CanonicalUUID
    object_type: Literal["WORKSPACE_BILLING_ACCOUNT"]
    object_id: CanonicalUUID
    object_version: PositiveDecimal


class ProvisionAudit(AuditBase):
    event_type: Literal["WORKSPACE_BILLING_PROVISIONED"]
    actor_kind: Literal["LOCAL_PROVISIONER"]
    actor_user_account_id: None
    payload: ProvisionPayload


class ContactAudit(AuditBase):
    event_type: Literal["BILLING_ACCOUNT_CONTACT_UPDATED"]
    actor_kind: Literal["USER_ACCOUNT"]
    actor_user_account_id: CanonicalUUID
    payload: ContactPayload


class MessageSendPayload(StrictModel):
    content_type: Literal["TEXT"]


class MessageSendAudit(StrictModel):
    audit_event_id: CanonicalUUID
    occurred_at: Timestamp
    correlation_id: CanonicalUUID
    object_type: Literal["MESSAGE"]
    object_id: CanonicalUUID
    object_version: Literal["1"]
    event_type: Literal["MESSAGE_SEND_REQUESTED"]
    actor_kind: Literal["USER_ACCOUNT"]
    actor_user_account_id: CanonicalUUID
    payload: MessageSendPayload


AuditItem = Annotated[
    ProvisionAudit | ContactAudit | MessageSendAudit, Field(discriminator="event_type")
]


class AuditPage(StrictModel):
    items: list[AuditItem] = Field(max_length=100)
    next_cursor: str | None = Field(max_length=1024)


class AuditCursor(StrictModel):
    v: Literal[1]
    endpoint: Literal["AUDIT_EVENTS"]
    workspace_id: CanonicalUUID
    direction: Literal["DESC"]
    occurred_at: Timestamp
    id: CanonicalUUID

    @field_validator("v", mode="before")
    @classmethod
    def version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid cursor version")
        return value
