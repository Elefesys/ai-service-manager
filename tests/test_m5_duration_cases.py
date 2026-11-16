"""Measured examples preserve unknowns, contradictions and owner access separation."""

import pytest
from asm.intake.duration_cases import compare_cases
from asm.intake.models import DurationCase
from m5_intake_fixtures import OWNER, RELEASE, case_input
from pydantic import ValidationError


def test_unknown_is_null_and_description_only_case_is_valid():
    case = case_input()
    assert case.occupied_minutes is None and case.asset is None and case.session_minutes is None


@pytest.mark.parametrize(
    "values",
    [
        {"working_minutes": 0},
        {"working_minutes": True},
        {"working_minutes": 60, "occupied_minutes": 30},
        {"session_count": 2, "session_minutes": [30]},
        {"occupied_minutes": 50, "session_count": 2, "session_minutes": [30, 30]},
        {
            "working_minutes": 30,
            "occupied_minutes": 60,
            "setup_minutes": 10,
            "stencil_minutes": 5,
            "break_minutes": 5,
            "cleanup_minutes": 5,
            "treatment": "INCLUDED",
        },
    ],
)
def test_contradictions_are_rejected_without_model_repair(values):
    with pytest.raises(ValidationError):
        case_input(**values)


def test_confirmed_search_reports_differences_and_unknown_without_calculating_estimates():
    case = DurationCase(
        case_id=RELEASE,
        version="2",
        state="CONFIRMED",
        data=case_input(placement="forearm", style="linework", working_minutes=35),
        confirmed_by=OWNER,
        source_current=True,
    )
    matches = compare_cases([case], {"placement": "forearm", "style": "watercolour"})
    assert (
        len(matches) == 1
        and matches[0].matches == ["placement"]
        and matches[0].differences == ["style"]
        and matches[0].unknown == ["detail", "fill"]
    )
    assert compare_cases([case.model_copy(update={"source_current": False})], {}) == []
    assert compare_cases([case.model_copy(update={"state": "REVOKED"})], {}) == []
