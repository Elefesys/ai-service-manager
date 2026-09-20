"""Pure service/wire evidence, including contradictory states prevented by normal DDL."""

import copy
import json
import re
from datetime import UTC, datetime
from uuid import UUID

import pytest
from asm.billing.errors import BillingUnavailable
from asm.billing.models import AuditCursor, BillingStateError, CommonError, ContactPatch
from asm.billing.permissions import BillingPermission, permissions_for
from asm.billing.service import KNOWN_KEYS, EntitlementService
from asm.billing.validation import (
    LimitDecimal,
    PositiveDecimal,
    canonical_json,
    contact_fingerprint,
    decode_cursor,
    encode_cursor,
    strict_json,
)
from asm.tenancy import MembershipRole
from pydantic import TypeAdapter, ValidationError

WS = UUID("01990000-0000-7000-8000-000000000001")
RID, PID = str(UUID(int=2)), str(UUID(int=3))
VECTORS = [
    ("Example name", "813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a"),
    ("  Example name  ", "813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a"),
    ("Анна", "cc4623b8517c225cc787e1eb961997592535ef07fc4184193c43862484b25bd8"),
    ('A"B\\C/D', "a90b071bf4761bda6e42a025e6c7f231b386e453238dddb58cc2db7b94e0d275"),
    ("Studio 🎨", "ffa9252a316a9d8001d20c7d2efe2e842294de6f45710df0faca802fd8a52dbd"),
    ("A\u2028B\u2029C", "fc36542d1fe82f730b56f8ad004d7aab3d6bb26208e0b740e0ac3e479f593d54"),
    ("é", "69ebd81a850211d04df9055a77ff95468dc1ff88acb568514c11f62d416f0c87"),
    ("e\u0301", "07c64318f29cbe6803800928ebf5d4b27436c63f850f1b190eb8418c79d79030"),
]


# Literal bytes copied from accepted R4 §5 (SHA-256 0d33a26a…); docs/tasks
# is deliberately absent from the existing checks image. Trim shares ASCII bytes.
PUBLISHED_BYTES = {
    "813d712466b9605186455d77032311a5e7865f48a5db0524e90b3f120a1d4b2a": "7b22636f6e746163745f646973706c61795f6e616d65223a224578616d706c65206e616d65222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
    "cc4623b8517c225cc787e1eb961997592535ef07fc4184193c43862484b25bd8": "7b22636f6e746163745f646973706c61795f6e616d65223a22d090d0bdd0bdd0b0222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
    "a90b071bf4761bda6e42a025e6c7f231b386e453238dddb58cc2db7b94e0d275": "7b22636f6e746163745f646973706c61795f6e616d65223a22415c22425c5c432f44222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
    "ffa9252a316a9d8001d20c7d2efe2e842294de6f45710df0faca802fd8a52dbd": "7b22636f6e746163745f646973706c61795f6e616d65223a2253747564696f20f09f8ea8222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
    "fc36542d1fe82f730b56f8ad004d7aab3d6bb26208e0b740e0ac3e479f593d54": "7b22636f6e746163745f646973706c61795f6e616d65223a2241e280a842e280a943222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
    "69ebd81a850211d04df9055a77ff95468dc1ff88acb568514c11f62d416f0c87": "7b22636f6e746163745f646973706c61795f6e616d65223a22c3a9222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
    "07c64318f29cbe6803800928ebf5d4b27436c63f850f1b190eb8418c79d79030": "7b22636f6e746163745f646973706c61795f6e616d65223a2265cc81222c2265787065637465645f76657273696f6e223a2237222c226f7065726174696f6e223a225550444154455f42494c4c494e475f434f4e54414354222c22776f726b73706163655f6964223a2230313939303030302d303030302d373030302d383030302d303030303030303030303031227d",
}


def snapshot():
    common = dict(
        workspace_id=str(WS),
        version=1,
        created_at="2026-09-01T00:00:00Z",
        updated_at="2026-09-01T00:00:00Z",
    )
    rows = [
        ("essential_true", "BOOLEAN", True, None, "ESSENTIAL"),
        ("standard_true", "BOOLEAN", True, None, "STANDARD"),
        ("standard_false", "BOOLEAN", False, None, "STANDARD"),
        ("expensive_positive", "INTEGER", None, 3, "EXPENSIVE_OPTIONAL"),
        ("expensive_zero", "INTEGER", None, 0, "EXPENSIVE_OPTIONAL"),
    ]
    return dict(
        evaluated_at=datetime(2026, 9, 20, tzinfo=UTC),
        accounts=[dict(common, billing_account_id=str(UUID(int=4)), contact_display_name="Before")],
        modes=[
            dict(
                common,
                mode="NORMAL",
                reason_code="PROVISIONED_LOCAL",
                is_active=True,
                effective_from="2026-09-01T00:00:00Z",
                effective_until=None,
            )
        ],
        history=[
            dict(
                common,
                subscription_id=str(UUID(int=5)),
                plan_revision_id=RID,
                required_publication_state="SEALED",
                status="ACTIVE",
                funding_mode="COMPED",
                effective_from="2026-09-01T00:00:00Z",
                effective_until="2026-10-01T00:00:00Z",
                is_current=True,
                revision_state=dict(
                    plan_revision_id=RID,
                    plan_id=PID,
                    revision=1,
                    publication_state="SEALED",
                    published_at="2026-09-01T00:00:00Z",
                    plan=dict(plan_id=PID, code="independent-plan", status="ARCHIVED"),
                    entitlements=[
                        dict(
                            plan_revision_id=RID,
                            capability_key="test.m1_3." + key,
                            value_kind=kind,
                            enabled=enabled,
                            limit_value=limit,
                            criticality=criticality,
                        )
                        for key, kind, enabled, limit, criticality in rows
                    ],
                ),
            )
        ],
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("NORMAL", ["ENABLED", "LIMIT", "LIMIT", "NOT_ENTITLED", "ENABLED"]),
        (
            "GRACE",
            [
                "ENABLED",
                "SERVICE_MODE_RESTRICTED",
                "SERVICE_MODE_RESTRICTED",
                "NOT_ENTITLED",
                "ENABLED",
            ],
        ),
        (
            "LIMITED",
            [
                "ENABLED",
                "SERVICE_MODE_RESTRICTED",
                "SERVICE_MODE_RESTRICTED",
                "SERVICE_MODE_RESTRICTED",
                "SERVICE_MODE_RESTRICTED",
            ],
        ),
        ("SUSPENDED", ["SERVICE_MODE_RESTRICTED"] * 5),
    ],
)
def test_service_modes_typed_values_and_all_precedence_layers(mode, expected):
    observed = snapshot()
    observed["modes"][0].update(
        mode=mode, reason_code="PROVISIONED_LOCAL" if mode == "NORMAL" else "TEST_" + mode
    )
    service = EntitlementService()
    result = service.evaluate(WS, observed)
    assert tuple(d.key for d in result.decisions) == KNOWN_KEYS
    assert [d.reason or d.type for d in result.decisions] == expected
    assert (
        result.subscription.plan.code == "independent-plan"
    )  # archived pinned revision remains valid
    if mode == "NORMAL":
        assert [d.limit for d in result.decisions if d.type == "LIMIT"] == ["3", "0"]
    # Missing key precedes mode restriction, for every mode.
    observed["history"][0]["revision_state"]["entitlements"] = []
    assert {d.reason for d in service.evaluate(WS, observed).decisions} == {"NOT_ENTITLED"}
    # Mode inactivity precedes missing key and restrictions, including future mode.
    observed["modes"][0].update(effective_from="2027-01-01T00:00:00Z", is_active=False)
    assert {d.reason for d in service.evaluate(WS, observed).decisions} == {"SERVICE_MODE_INACTIVE"}
    # Subscription inactivity precedes mode inactivity, including valid future history.
    observed["history"][0].update(
        effective_from="2027-01-01T00:00:00Z",
        effective_until="2028-01-01T00:00:00Z",
        is_current=False,
    )
    inactive = service.evaluate(WS, observed)
    assert inactive.subscription is None and inactive.availability == "INACTIVE"
    assert not inactive.mode_active
    assert {d.reason for d in inactive.decisions} == {"SUBSCRIPTION_INACTIVE"}
    # Structural failures precede all inactive/absent/restricted states.
    observed["history"][0]["revision_state"]["publication_state"] = "DRAFT"
    with pytest.raises(BillingUnavailable) as bad:
        service.evaluate(WS, observed)
    assert bad.value.reason == "REVISION_INVALID"
    observed["accounts"].append(copy.deepcopy(observed["accounts"][0]))
    with pytest.raises(BillingUnavailable) as bad:
        service.evaluate(WS, observed)
    assert bad.value.reason == "BILLING_STATE_INVALID"
    observed["modes"] = []
    with pytest.raises(BillingUnavailable) as bad:
        service.evaluate(WS, observed)
    assert bad.value.reason == "BILLING_STATE_MISSING"


@pytest.mark.parametrize(
    "case",
    [
        "overlap",
        "wrong_scope",
        "bad_interval",
        "bad_flag",
        "bad_name",
        "bad_value",
        "duplicate_key",
        "missing_revision",
        "bad_reference",
    ],
)
def test_impossible_snapshots_fail_closed_without_reinterpreting_ddl(case):
    value = snapshot()
    sub = value["history"][0]
    revision = sub["revision_state"]
    reason = "BILLING_STATE_INVALID"
    if case == "overlap":
        value["history"].append(copy.deepcopy(sub))
    elif case == "wrong_scope":
        value["accounts"][0]["workspace_id"] = str(UUID(int=999))
    elif case == "bad_interval":
        sub["effective_until"] = sub["effective_from"]
    elif case == "bad_flag":
        sub["is_current"] = False
    elif case == "bad_name":
        value["accounts"][0]["contact_display_name"] = "not\nvalid"
    else:
        reason = "REVISION_INVALID"
        if case == "bad_value":
            revision["entitlements"][0]["limit_value"] = 0
        elif case == "duplicate_key":
            revision["entitlements"].append(copy.deepcopy(revision["entitlements"][0]))
        elif case == "missing_revision":
            sub["revision_state"] = None
        else:
            revision["plan_id"] = str(UUID(int=999))
    with pytest.raises(BillingUnavailable) as error:
        EntitlementService().evaluate(WS, value)
    assert error.value.reason == reason


def test_half_open_endpoints_and_independent_mode_activity():
    value = snapshot()
    value["evaluated_at"] = datetime(2026, 10, 1, tzinfo=UTC)
    value["history"][0]["is_current"] = False
    result = EntitlementService().evaluate(WS, value)
    assert result.subscription is None and result.mode_active
    value["evaluated_at"] = datetime(2026, 9, 1, tzinfo=UTC)
    value["history"][0]["is_current"] = True
    assert EntitlementService().evaluate(WS, value).subscription is not None


@pytest.mark.parametrize(("name", "expected"), VECTORS)
def test_fingerprint_entire_canonical_bytes_and_digest_match_r4(name, expected):
    body = ContactPatch(expected_version="7", contact_display_name=name)
    wire = canonical_json(
        dict(
            contact_display_name=body.contact_display_name,
            expected_version="7",
            operation="UPDATE_BILLING_CONTACT",
            workspace_id=str(WS),
        ),
        sort=True,
    )
    assert wire.hex() == PUBLISHED_BYTES[expected]
    assert contact_fingerprint(WS, "7", body.contact_display_name).hex() == expected


@pytest.mark.parametrize(
    "value", [0, 1, True, None, "0", "01", "-1", "1.0", "1e2", " 1", "1\n", "9223372036854775808"]
)
def test_positive_decimal_is_strict_and_schema_has_the_same_bound(value):
    adapter = TypeAdapter(PositiveDecimal)
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    if isinstance(value, str):
        assert re.fullmatch(adapter.json_schema()["pattern"], value) is None


def test_zero_limits_and_maximum_versions_are_strings_and_permissions_are_separate():
    for kind, value in [(LimitDecimal, "0"), (PositiveDecimal, "9223372036854775807")]:
        adapter = TypeAdapter(kind)
        assert adapter.validate_python(value) == value
        assert re.fullmatch(adapter.json_schema()["pattern"], value)
    assert permissions_for(MembershipRole.OWNER) == frozenset(BillingPermission)
    assert all(
        not permissions_for(role) for role in (MembershipRole.ADMIN, MembershipRole.PROVIDER, None)
    )


def test_error_union_does_not_extend_auth_or_accept_nullable_reason():
    adapter = TypeAdapter(CommonError | BillingStateError)
    for payload in [
        {"error": {"code": "UNAVAILABLE"}},
        {"error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": "DATABASE_UNAVAILABLE"}},
    ]:
        assert adapter.validate_python(payload).model_dump() == payload
    for payload in [
        {"error": {"code": "UNAVAILABLE", "state_reason": None}},
        {"error": {"code": "BILLING_STATE_UNAVAILABLE"}},
        {"error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": None}},
        {"error": {"code": "BILLING_STATE_UNAVAILABLE", "state_reason": "OTHER"}},
    ]:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_strict_json_cursor_and_name_boundaries():
    for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"\xef\xbb\xbf{}", b"[]"]:
        with pytest.raises((ValueError, UnicodeError)):
            strict_json(raw)
    for name in ["", " ", "x\n", "x\t", "\x00", "\x7f", "\ud800", "x" * 201]:
        with pytest.raises(ValidationError):
            ContactPatch(expected_version="1", contact_display_name=name)
    assert (
        ContactPatch(
            expected_version="1", contact_display_name=" " + "🎨" * 200 + " "
        ).contact_display_name
        == "🎨" * 200
    )
    assert (
        ContactPatch(
            expected_version="1", contact_display_name="\u00a0x\u00a0"
        ).contact_display_name
        == "\u00a0x\u00a0"
    )
    cursor = dict(
        v=1,
        endpoint="AUDIT_EVENTS",
        workspace_id=str(WS),
        direction="DESC",
        occurred_at="2026-09-19T00:00:00.123456Z",
        id=str(UUID(int=8)),
    )
    encoded = encode_cursor(cursor)
    assert AuditCursor.model_validate(decode_cursor(encoded)).model_dump() == cursor
    for value in [encoded + "=", "!", "x" * 1025, "é", "A"]:
        with pytest.raises(ValueError):
            decode_cursor(value)
    for change in [
        dict(v=True),
        dict(v=2),
        dict(direction="ASC"),
        dict(endpoint="BILLING"),
        dict(occurred_at="2026-09-19T00:00:00Z"),
        dict(extra="x"),
    ]:
        with pytest.raises(ValidationError):
            AuditCursor.model_validate({**cursor, **change})
    with pytest.raises(ValueError):
        import base64

        decode_cursor(base64.urlsafe_b64encode(json.dumps(cursor).encode()).decode().rstrip("="))
