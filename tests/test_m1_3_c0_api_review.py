"""C0 regressions for published request constraints, without changing R4 semantics."""

import re

import pytest
from asm.billing.models import ContactPatch
from pydantic import ValidationError
from test_m1_3_http_contract import app


def accepts_string(schema, value):
    # The relevant JSON Schema string keywords; do not apply an invented trim
    # before validating the raw request. This is not a full JSON Schema engine.
    return (
        schema["type"] == "string"
        and len(value) >= schema.get("minLength", 0)
        and len(value) <= schema.get("maxLength", float("inf"))
        and ("pattern" not in schema or re.search(schema["pattern"], value) is not None)
    )


def test_contact_request_schema_applies_the_bound_after_space_only_trim():
    patch = app().openapi()["paths"]["/api/v1/workspaces/{workspace_id}/billing-account"]["patch"]
    schema = patch["requestBody"]["content"]["application/json"]["schema"]["properties"][
        "contact_display_name"
    ]
    for raw, accepted in [
        ("a", True),
        ("  " + "a" * 200 + "  ", True),
        (" " + "🎨" * 200 + " ", True),
        ("\u00a0x\u00a0", True),
        ("A\u2028B\u2029C", True),
        ("e\u0301", True),
        ("a" * 201, False),
        (" " + "🎨" * 201 + " ", False),
        ("", False),
        ("  ", False),
        ("x\n", False),
        ("x\t", False),
        ("\x00", False),
        ("\x7f", False),
        ("\ud800", False),
    ]:
        if accepted:
            assert ContactPatch(
                expected_version="1", contact_display_name=raw
            ).contact_display_name == raw.strip(" ")
        else:
            with pytest.raises(ValidationError):
                ContactPatch(expected_version="1", contact_display_name=raw)
        assert accepts_string(schema, raw) is accepted
