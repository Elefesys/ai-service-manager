"""The one product capability uses the validated R4 snapshot and its precedence."""

import pytest
from asm.billing.errors import BillingUnavailable
from asm.billing.service import KNOWN_KEYS, MANUAL_SEND_KEY, EntitlementService
from test_m1_3_service import RID, WS, snapshot


def messaging_snapshot():
    value = snapshot()
    value["history"][0]["revision_state"]["entitlements"] = [
        {
            "plan_revision_id": RID,
            "capability_key": MANUAL_SEND_KEY,
            "value_kind": "BOOLEAN",
            "enabled": True,
            "limit_value": None,
            "criticality": "ESSENTIAL",
        }
    ]
    return value


@pytest.mark.parametrize("mode", ["NORMAL", "GRACE", "LIMITED", "SUSPENDED"])
def test_manual_product_policy_keeps_five_key_billing_projection(mode):
    observed = messaging_snapshot()
    observed["modes"][0].update(
        mode=mode, reason_code="PROVISIONED_LOCAL" if mode == "NORMAL" else "TEST_" + mode
    )
    service = EntitlementService()
    decision = service.evaluate_product(WS, observed, MANUAL_SEND_KEY)
    assert decision.key == MANUAL_SEND_KEY
    assert decision.type == ("DISABLED" if mode == "SUSPENDED" else "ENABLED")
    assert decision.reason == ("SERVICE_MODE_RESTRICTED" if mode == "SUSPENDED" else None)
    assert [item.key for item in service.evaluate(WS, observed).decisions] == list(KNOWN_KEYS)
    assert len(KNOWN_KEYS) == 5 and MANUAL_SEND_KEY not in KNOWN_KEYS


@pytest.mark.parametrize("case", ["missing", "false", "subscription", "mode"])
def test_manual_product_denials_use_current_snapshot_intervals(case):
    observed = messaging_snapshot()
    if case == "missing":
        observed["history"][0]["revision_state"]["entitlements"] = []
    elif case == "false":
        observed["history"][0]["revision_state"]["entitlements"][0]["enabled"] = False
    else:
        row = observed["history"][0] if case == "subscription" else observed["modes"][0]
        row["effective_until"] = "2026-09-02T00:00:00Z"
        row["is_current" if case == "subscription" else "is_active"] = False
    decision = EntitlementService().evaluate_product(WS, observed, MANUAL_SEND_KEY)
    assert decision.type == "DISABLED"
    assert (
        decision.reason
        == {
            "missing": "NOT_ENTITLED",
            "false": "NOT_ENTITLED",
            "subscription": "SUBSCRIPTION_INACTIVE",
            "mode": "SERVICE_MODE_INACTIVE",
        }[case]
    )


@pytest.mark.parametrize("case", ["missing", "scope", "unsealed", "integer", "criticality"])
def test_structural_policy_failure_remains_unavailable_before_business_denial(case):
    observed = messaging_snapshot()
    observed["modes"][0].update(mode="SUSPENDED", reason_code="TEST_SUSPENDED")
    revision = observed["history"][0]["revision_state"]
    if case == "missing":
        observed["accounts"] = []
    elif case == "scope":
        observed["accounts"][0]["workspace_id"] = RID
    elif case == "unsealed":
        revision["publication_state"] = "DRAFT"
    elif case == "integer":
        revision["entitlements"][0].update(value_kind="INTEGER", enabled=None, limit_value=1)
    else:
        revision["entitlements"][0]["criticality"] = "STANDARD"
    with pytest.raises(BillingUnavailable) as failure:
        EntitlementService().evaluate_product(WS, observed, MANUAL_SEND_KEY)
    assert (
        failure.value.reason
        == {
            "missing": "BILLING_STATE_MISSING",
            "scope": "BILLING_STATE_INVALID",
            "unsealed": "REVISION_INVALID",
            "integer": "REVISION_INVALID",
            "criticality": "REVISION_INVALID",
        }[case]
    )


def test_unknown_product_does_not_open_a_generic_capability_api():
    with pytest.raises(ValueError, match="Unknown product"):
        EntitlementService().evaluate_product(WS, messaging_snapshot(), "future.capability")


@pytest.mark.parametrize(
    "kind,enabled,limit,criticality",
    [
        ("INTEGER", None, 1, "ESSENTIAL"),
        ("BOOLEAN", True, None, "STANDARD"),
        ("INTEGER", None, 1, "STANDARD"),
    ],
)
def test_product_shape_validation_does_not_change_legacy_billing_get(
    kind, enabled, limit, criticality
):
    observed = snapshot()
    service = EntitlementService()
    original = service.evaluate(WS, observed)
    observed["history"][0]["revision_state"]["entitlements"].append(
        {
            "plan_revision_id": RID,
            "capability_key": MANUAL_SEND_KEY,
            "value_kind": kind,
            "enabled": enabled,
            "limit_value": limit,
            "criticality": criticality,
        }
    )
    # This is valid generic catalog data for R4, whose five decisions ignore it.
    legacy = service.evaluate(WS, observed)
    assert legacy == original
    assert [item.key for item in legacy.decisions] == list(KNOWN_KEYS)
    assert len(legacy.decisions) == 5
    with pytest.raises(BillingUnavailable) as failure:
        service.evaluate_product(WS, observed, MANUAL_SEND_KEY)
    assert failure.value.reason == "REVISION_INVALID"
