"""Entitlement decisions from one observed DB snapshot, without plan-name rules."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from asm.billing.errors import BillingUnavailable
from asm.billing.models import (
    BillingAccount,
    BillingResponse,
    Criticality,
    Decision,
    DisabledDecision,
    DisabledReason,
    EnabledDecision,
    LimitDecision,
    Mode,
    Plan,
    Subscription,
)
from asm.billing.validation import MAX_BIGINT, CapabilityKey, normalize_name, timestamp

KNOWN_KEYS = tuple(
    sorted(
        (
            "test.m1_3.essential_true",
            "test.m1_3.standard_true",
            "test.m1_3.standard_false",
            "test.m1_3.expensive_positive",
            "test.m1_3.expensive_zero",
        )
    )
)
ALLOWED: dict[Mode, frozenset[Criticality]] = {
    "NORMAL": frozenset(("ESSENTIAL", "STANDARD", "EXPENSIVE_OPTIONAL")),
    "GRACE": frozenset(("ESSENTIAL", "STANDARD")),
    "LIMITED": frozenset(("ESSENTIAL",)),
    "SUSPENDED": frozenset(),
}
Version = Annotated[int, Field(strict=True, ge=1, le=MAX_BIGINT)]


class StateModel(BaseModel):
    # SQL to_jsonb includes physical metadata; it is not a wire DTO.
    model_config = ConfigDict(extra="ignore", frozen=True, hide_input_in_errors=True)


class MutableState(StateModel):
    workspace_id: UUID
    version: Version
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Invalid timestamps")
        return self


class AccountState(MutableState):
    billing_account_id: UUID
    contact_display_name: str = Field(strict=True, repr=False)

    @model_validator(mode="after")
    def contact(self) -> Self:
        if normalize_name(self.contact_display_name) != self.contact_display_name:
            raise ValueError("Invalid stored contact")
        return self


class ModeState(MutableState):
    is_active: bool = Field(strict=True)
    mode: Mode
    reason_code: str
    effective_from: AwareDatetime
    effective_until: AwareDatetime | None

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.effective_until is not None and self.effective_from >= self.effective_until:
            raise ValueError("Invalid mode interval")
        if (
            self.reason_code
            != {
                "NORMAL": "PROVISIONED_LOCAL",
                "GRACE": "TEST_GRACE",
                "LIMITED": "TEST_LIMITED",
                "SUSPENDED": "TEST_SUSPENDED",
            }[self.mode]
        ):
            raise ValueError("Invalid mode reason")
        return self


class SubscriptionState(MutableState):
    is_current: bool = Field(strict=True)
    subscription_id: UUID
    plan_revision_id: UUID
    required_publication_state: str
    status: Literal["TRIALING", "ACTIVE"]
    funding_mode: Literal["TRIAL", "COMPED"]
    effective_from: AwareDatetime
    effective_until: AwareDatetime
    revision_state: dict[str, Any] | None

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.effective_from >= self.effective_until or (self.status, self.funding_mode) not in (
            ("TRIALING", "TRIAL"),
            ("ACTIVE", "COMPED"),
        ):
            raise ValueError("Invalid subscription")
        return self


class Entitlement(StateModel):
    plan_revision_id: UUID
    capability_key: CapabilityKey
    value_kind: Literal["BOOLEAN", "INTEGER"]
    enabled: bool | None = Field(strict=True)
    limit_value: int | None = Field(strict=True, ge=0, le=MAX_BIGINT)
    criticality: Criticality

    @model_validator(mode="after")
    def typed_value(self) -> Self:
        if self.value_kind == "BOOLEAN":
            valid = self.enabled is not None and self.limit_value is None
        else:
            valid = self.enabled is None and self.limit_value is not None
        if not valid:
            raise ValueError("Invalid entitlement value")
        return self


class PlanState(StateModel):
    plan_id: UUID
    code: str = Field(strict=True, pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    status: Literal["ACTIVE", "ARCHIVED"]


class RevisionState(StateModel):
    plan_revision_id: UUID
    plan_id: UUID
    revision: int = Field(strict=True, ge=1)
    publication_state: Literal["SEALED"]
    published_at: AwareDatetime
    plan: PlanState
    entitlements: list[Entitlement]

    @model_validator(mode="after")
    def references(self) -> Self:
        keys = [e.capability_key for e in self.entitlements]
        if (
            self.plan_id != self.plan.plan_id
            or len(keys) != len(set(keys))
            or any(e.plan_revision_id != self.plan_revision_id for e in self.entitlements)
        ):
            raise ValueError("Invalid revision references")
        return self


class Snapshot(StateModel):
    evaluated_at: AwareDatetime
    accounts: list[AccountState]
    modes: list[ModeState]
    history: list[SubscriptionState]


@dataclass(frozen=True)
class EntitlementSnapshot:
    """Validated projection of the single statement, including its interval flags."""

    subscription_active: bool
    mode_active: bool
    mode: Mode
    entitlements: Mapping[str, Entitlement]


class EntitlementService:
    def evaluate(self, workspace_id: UUID, observed: Mapping[str, Any]) -> BillingResponse:
        # Missing evidence takes precedence over contradictory/revision evidence.
        if any(observed.get(key) == [] for key in ("accounts", "modes", "history")):
            raise BillingUnavailable("BILLING_STATE_MISSING")
        try:
            snapshot = Snapshot.model_validate(observed)
            if len(snapshot.accounts) != 1 or len(snapshot.modes) != 1:
                raise ValueError("Invalid singleton")
            all_rows = [*snapshot.accounts, *snapshot.modes, *snapshot.history]
            if any(row.workspace_id != workspace_id for row in all_rows):
                raise ValueError("Invalid scope")
            history = sorted(snapshot.history, key=lambda s: s.effective_from)
            if len({s.subscription_id for s in history}) != len(history) or any(
                a.effective_until > b.effective_from for a, b in zip(history, history[1:])
            ):
                raise ValueError("Contradictory history")
            now = snapshot.evaluated_at
            if any(s.is_current != (s.effective_from <= now < s.effective_until) for s in history):
                raise ValueError("Contradictory current interval")
            mode = snapshot.modes[0]
            if mode.is_active != (
                mode.effective_from <= now
                and (mode.effective_until is None or now < mode.effective_until)
            ):
                raise ValueError("Contradictory mode interval")
        except (ValidationError, ValueError, TypeError):
            raise BillingUnavailable("BILLING_STATE_INVALID") from None
        revisions: dict[UUID, RevisionState] = {}
        try:
            for sub in history:
                revision = RevisionState.model_validate(sub.revision_state)
                if (
                    sub.required_publication_state != "SEALED"
                    or revision.plan_revision_id != sub.plan_revision_id
                ):
                    raise ValueError("Invalid pinned revision")
                if (
                    sub.plan_revision_id in revisions
                    and revisions[sub.plan_revision_id] != revision
                ):
                    raise ValueError("Contradictory revision")
                revisions[sub.plan_revision_id] = revision
        except (ValidationError, ValueError, TypeError):
            raise BillingUnavailable("REVISION_INVALID") from None
        now = snapshot.evaluated_at
        active = next((s for s in history if s.is_current), None)
        mode, account = snapshot.modes[0], snapshot.accounts[0]
        mode_active = mode.is_active
        subscription = None
        entitlements: dict[str, Entitlement] = {}
        if active is not None:
            revision = revisions[active.plan_revision_id]
            entitlements = {e.capability_key: e for e in revision.entitlements}
            subscription = Subscription(
                subscription_id=str(active.subscription_id),
                status=active.status,
                funding_mode=active.funding_mode,
                effective_from=timestamp(active.effective_from),
                effective_until=timestamp(active.effective_until),
                version=str(active.version),
                plan=Plan(
                    plan_id=str(revision.plan_id),
                    code=revision.plan.code,
                    revision_id=str(revision.plan_revision_id),
                    revision=revision.revision,
                ),
            )
        decisions_snapshot = EntitlementSnapshot(
            active is not None, mode_active, mode.mode, entitlements
        )
        return BillingResponse(
            workspace_id=str(workspace_id),
            evaluated_at=timestamp(now),
            account=BillingAccount(
                billing_account_id=str(account.billing_account_id),
                contact_display_name=account.contact_display_name,
                version=str(account.version),
            ),
            subscription=subscription,
            mode=mode.mode,
            mode_active=mode_active,
            availability="ACTIVE" if active is not None else "INACTIVE",
            decisions=[self.decide(decisions_snapshot, key) for key in KNOWN_KEYS],
        )

    @staticmethod
    def decide(snapshot: EntitlementSnapshot, key: CapabilityKey) -> Decision:
        entitlement = snapshot.entitlements.get(key)
        reason: DisabledReason | None = None
        if not snapshot.subscription_active:
            reason = "SUBSCRIPTION_INACTIVE"
        elif not snapshot.mode_active:
            reason = "SERVICE_MODE_INACTIVE"
        elif entitlement is None:
            reason = "NOT_ENTITLED"
        elif entitlement.criticality not in ALLOWED[snapshot.mode]:
            reason = "SERVICE_MODE_RESTRICTED"
        elif entitlement.value_kind == "BOOLEAN" and not entitlement.enabled:
            reason = "NOT_ENTITLED"
        if reason is not None:
            return DisabledDecision(key=key, type="DISABLED", reason=reason, limit=None)
        if entitlement is not None and entitlement.value_kind == "INTEGER":
            return LimitDecision(
                key=key, type="LIMIT", reason=None, limit=str(entitlement.limit_value)
            )
        return EnabledDecision(key=key, type="ENABLED", reason=None, limit=None)
