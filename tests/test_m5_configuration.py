"""Configuration decisions, input boundaries and explicit unknown values."""

from copy import deepcopy

import pytest
from asm.billing.validation import strict_json
from asm.configuration.models import Bundle, EditDraft
from asm.configuration.validation import validate_bundle
from m5_configuration_fixtures import configuration_bundle
from pydantic import ValidationError


def test_two_small_business_bundles_and_unknowns_never_become_promises():
    first, second = configuration_bundle(), configuration_bundle("ceramics")
    assert validate_bundle(first).model_dump() == {"valid": True, "issues": []}
    report = validate_bundle(second)
    assert report.valid and [(i.code, i.path) for i in report.issues] == [
        ("OWNER_HANDOFF", "services.consultation.price"),
        ("OWNER_HANDOFF", "services.consultation.duration"),
    ]
    assert second["services"][0]["price"]["amount_minor"] is None
    assert second["services"][0]["duration"]["minutes"] is None
    unknown = configuration_bundle()
    unknown["services"][0]["price"]["amount_minor"] = None
    unknown["services"][0]["duration"]["minutes"] = None
    before = deepcopy(unknown)
    assert validate_bundle(unknown).valid
    assert {i.code for i in validate_bundle(unknown).issues} == {"OWNER_HANDOFF"}
    assert unknown == before


@pytest.mark.parametrize(
    "bad,code",
    [
        ("mode", "INVALID_MODE"),
        ("reference", "INVALID_REFERENCE"),
        ("unconfirmed", "UNCONFIRMED_FAQ"),
        ("source", "UNCONFIRMED_FAQ"),
        ("conflict", "CONFLICTING_RULES"),
        ("duplicate", "DUPLICATE_ID"),
        ("inactive", "NO_ACTIVE_SERVICE"),
        ("deposit", "INVALID_POLICY"),
        ("duration", "INVALID_POLICY"),
        ("style", "INVALID_STYLE"),
    ],
)
def test_draft_errors_are_deterministic_and_never_ready(bad, code):
    value = configuration_bundle()
    if bad == "mode":
        value["services"][0]["price"]["mode"] = "MODEL_PRICE"
    elif bad == "reference":
        value["faqs"][0]["rule_ids"] = ["missing"]
    elif bad == "unconfirmed":
        value["faqs"][0]["confirmed"] = False
    elif bad == "source":
        value["faqs"][0]["source"] = "\u00a0"
    elif bad == "conflict":
        value["rules"].append(
            {"id": "different", "service_id": "consultation", "kind": "MIN_AGE", "value": 16}
        )
    elif bad == "duplicate":
        value["services"][0]["intake_fields"] *= 2
    elif bad == "inactive":
        value["services"][0]["active"] = False
    elif bad == "deposit":
        value["services"][0]["deposit"]["percent"] = 30
    elif bad == "duration":
        value["services"][0]["duration"]["minutes"] = 0
    else:
        value["communication_style"] = "SYSTEM_PROMPT"
    parsed = Bundle.model_validate(value)
    report = validate_bundle(parsed)
    assert not report.valid and code in {i.code for i in report.issues}
    assert validate_bundle(parsed) == report


@pytest.mark.parametrize(
    "bad", ["schema_bool", "schema_float", "price_bool", "extra", "nul", "surrogate", "id", "size"]
)
def test_strict_shape_unicode_and_total_bundle_bound(bad):
    value = configuration_bundle()
    if bad.startswith("schema"):
        value["schema_version"] = True if bad == "schema_bool" else 1.0
    elif bad == "price_bool":
        value["services"][0]["price"]["amount_minor"] = True
    elif bad == "extra":
        value["client_id"] = "private-client-is-not-business-knowledge"
    elif bad == "nul":
        value["faqs"][0]["answer"] = "invalid\0text"
    elif bad == "surrogate":
        value["services"][0]["name"] = "\ud800"
    elif bad == "id":
        value["services"][0]["id"] += "\n"
    else:
        value["faqs"] = [
            value["faqs"][0] | {"id": f"faq{i}", "answer": "я" * 500} for i in range(6)
        ]
    with pytest.raises(ValidationError):
        Bundle.model_validate(value)
    assert validate_bundle(value).model_dump() == {
        "valid": False,
        "issues": [
            {
                "severity": "ERROR",
                "code": "INVALID_SHAPE",
                "path": "bundle",
            }
        ],
    }


@pytest.mark.parametrize("version", [True, 1, "01", "-1", "9223372036854775808"])
def test_expected_version_is_canonical_bounded_decimal(version):
    with pytest.raises(ValidationError):
        EditDraft(expected_draft_version=version, bundle=configuration_bundle())


def test_faq_rule_scope_and_structured_authority_are_preserved():
    value = configuration_bundle()
    value["services"].append(deepcopy(value["services"][0]) | {"id": "other"})
    value["rules"][0]["service_id"] = "other"
    assert not validate_bundle(value).valid
    value["rules"][0]["service_id"] = None
    value["faqs"][0]["answer"] = "An explanatory FAQ cannot change the configured minimum age."
    assert validate_bundle(value).valid
    assert value["rules"][0]["value"] == 18


def test_duplicate_json_keys_are_not_discarded_before_shape_validation():
    with pytest.raises(ValueError):
        strict_json(b'{"expected_draft_version":"0","expected_draft_version":"1"}')


def test_generated_configuration_request_refs_resolve_in_the_complete_document():
    from asm.foundation import Settings, create_app
    from pydantic import SecretStr

    class OfflineDatabase:
        async def check(self):
            raise AssertionError("OpenAPI must not access PostgreSQL")

        async def close(self):
            pass

    settings = Settings(
        environment="TEST",
        database_url=SecretStr("postgresql+psycopg://asm_runtime:unused@localhost/asm_test"),
    )
    api = create_app(settings, OfflineDatabase()).openapi()
    assert (
        api["paths"]["/api/v1/auth/session"]["get"]["responses"]["401"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/ErrorResponse"
    )
    assert "ErrorDetail" in api["components"]["schemas"]
    references = []

    def inspect(value):
        if isinstance(value, dict):
            if "$ref" in value:
                references.append(value["$ref"])
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    inspect(api)
    assert "#/components/schemas/Bundle" in references
    for ref in references:
        assert ref.startswith("#/")
        target = api
        for key in ref[2:].split("/"):
            target = target[key.replace("~1", "/").replace("~0", "~")]
        assert isinstance(target, dict)
