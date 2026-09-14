import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fixture: Literal["A", "B", "C", "D"]
    synthetic: Literal[True]
    production_publishable: Literal[False]
    workspace_id: str
    business_id: str
    client_ids: list[str]
    timezone: str
    pricing_mode: Literal["FIXED", "CONFIGURED_FORMULA", "OWNER_QUOTE"]
    duration_mode: Literal["FIXED", "CONFIGURED_RULE", "OWNER_DEFINED"]
    payment_mode: Literal["FIXED_DEPOSIT", "PERCENT_DEPOSIT", "NONE", "FULL_PREPAYMENT"]
    currency: Literal["RUB"]
    amount_minor: Annotated[int, Field(ge=0)] | None
    deposit_minor: Annotated[int, Field(ge=0)] | None
    deposit_basis_points: Annotated[int, Field(ge=0, le=10000)] | None
    duration_minutes: Annotated[int, Field(gt=0)] | None
    rule_case: str | None


def load_fixtures(environment):
    if environment not in ("LOCAL", "TEST"):
        raise ValueError("Synthetic fixtures cannot be loaded outside LOCAL/TEST")
    raw = json.loads((Path(__file__).parent / "fixtures" / "businesses.v1.json").read_text())
    return [Fixture.model_validate(row) for row in raw]


def test_fixture_matrix_and_independent_ids():
    fixtures = load_fixtures("TEST")
    assert [(f.fixture, f.pricing_mode, f.duration_mode, f.payment_mode) for f in fixtures] == [
        ("A", "FIXED", "FIXED", "FIXED_DEPOSIT"),
        ("B", "CONFIGURED_FORMULA", "CONFIGURED_RULE", "PERCENT_DEPOSIT"),
        ("C", "OWNER_QUOTE", "OWNER_DEFINED", "NONE"),
        ("D", "FIXED", "OWNER_DEFINED", "FULL_PREPAYMENT"),
    ]
    identifiers = []
    for fixture in fixtures:
        ZoneInfo(fixture.timezone)
        assert len(fixture.client_ids) == 2
        identifiers += [fixture.workspace_id, fixture.business_id, *fixture.client_ids]
    assert len(set(identifiers)) == len(identifiers)
    for value in identifiers:
        UUID(value)
    assert fixtures[2].amount_minor is None
    assert fixtures[3].duration_minutes is None


@pytest.mark.parametrize("environment", ["PRODUCTION", "STAGING", "UNKNOWN"])
def test_synthetic_fixture_environment_guard(environment):
    with pytest.raises(ValueError):
        load_fixtures(environment)


def test_money_and_publish_marker_are_strict():
    record = load_fixtures("TEST")[0].model_dump()
    for patch in ({"amount_minor": 1.25}, {"amount_minor": True}, {"production_publishable": True}):
        with pytest.raises(ValidationError):
            Fixture.model_validate(record | patch)


def test_edge_case_descriptions_exist_without_claiming_domain_execution():
    raw = json.loads((Path(__file__).parent / "fixtures" / "edge-cases.v1.json").read_text())
    assert {row["id"] for row in raw} == {"RANGE_PERCENT_NO_BASE", "MISSING_DURATION", "PRICE_REVISION_CHANGED", "CROSS_WORKSPACE", "SAME_WORKSPACE_OTHER_CLIENT", "TIMEZONE_CHANGE"}
    assert all(row["status"] == "SPECIFIED_NOT_EXECUTED" for row in raw)
