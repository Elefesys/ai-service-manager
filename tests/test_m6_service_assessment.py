"""Fictional published duration policies with explicit, request-bound evidence."""

import pytest
from asm.configuration.models import Bundle, Rule, Service
from asm.configuration.validation import validate_bundle
from asm.intake.models import Fact
from asm.service_requests.assessment import AssessmentInputs, evaluate, size_millimetres
from m5_intake_fixtures import (
    BUSINESS,
    CONVERSATION,
    MESSAGE,
    RELEASE,
    WS,
    candidates,
    intake_bundle,
)

SIZE_RULE = {"threshold_mm": 80, "at_or_below_minutes": 90, "above_minutes": 120}


def assessment_inputs(
    *,
    size="8 cm",
    mode="CONFIGURED_RULE",
    price_mode="OWNER_QUOTE",
    rules=(),
    handoff=False,
):
    raw = intake_bundle()["services"][0]
    raw["price"] = {
        "mode": price_mode,
        "amount_minor": 120000 if price_mode == "FIXED" else None,
        "formula_note": None,
    }
    raw["duration"] = {"mode": mode, "minutes": 60 if mode == "FIXED" else None, "rule_note": None}
    if mode == "CONFIGURED_RULE":
        raw["duration"]["size_rule"] = SIZE_RULE
    values = {"idea": "flower", "placement": "forearm", "style": "linework"}
    if size is not None:
        values["approximate_size"] = size
    return AssessmentInputs(
        workspace_id=WS,
        business_id=BUSINESS,
        conversation_id=CONVERSATION,
        request_id=MESSAGE,
        request_revision="1",
        release_id=RELEASE,
        activation_version="2",
        authority_sha256="a" * 64,
        service=Service.model_validate(raw),
        rules=[
            Rule(id=kind.lower(), service_id=None, kind=kind, value=value) for kind, value in rules
        ],
        owner_handoff=handoff,
        facts=[
            Fact(
                **candidate.model_dump(exclude={"explicit_correction"}),
                confirmed_by=None,
                conflict=False,
            )
            for candidate in candidates(values).facts
        ],
        unavailable_fields=[],
    )


@pytest.mark.parametrize(
    ("value", "mm", "minutes"),
    [("79 mm", 79, 90), ("8 см", 80, 90), ("8,1 см", 81, 120)],
)
def test_published_threshold_uses_exact_millimetres(value, mm, minutes):
    result = evaluate(assessment_inputs(size=value))
    assert (result.outcome, result.reason, result.size_mm, result.occupied_minutes) == (
        "FEASIBLE",
        "SIZE_DURATION_RULE",
        mm,
        minutes,
    )


@pytest.mark.parametrize(
    "ambiguous", ["8–12 см", "around 8 cm", "80", "8 inches", "80.5 mm", "0 cm", "101 cm"]
)
def test_unverified_or_out_of_range_lengths_have_no_duration(ambiguous):
    assert size_millimetres(ambiguous) is None
    result = evaluate(assessment_inputs(size=ambiguous))
    assert (result.outcome, result.reason, result.occupied_minutes) == (
        "NEEDS_DATA",
        "SIZE_NEEDS_CONFIRMATION",
        None,
    )


def test_fixed_and_owner_time_are_independent_of_price():
    fixed = evaluate(assessment_inputs(mode="FIXED", price_mode="OWNER_QUOTE"))
    manual = evaluate(assessment_inputs(mode="OWNER_DEFINED", price_mode="FIXED"))
    assert (fixed.outcome, fixed.reason, fixed.occupied_minutes) == (
        "FEASIBLE",
        "FIXED_DURATION",
        60,
    )
    assert (manual.outcome, manual.reason, manual.occupied_minutes) == (
        "NEEDS_OWNER",
        "OWNER_DURATION",
        None,
    )


def test_missing_conflicted_revoked_or_handoff_inputs_never_authorize_minutes():
    complete = assessment_inputs()
    size = next(fact for fact in complete.facts if fact.field == "approximate_size")
    others = [fact for fact in complete.facts if fact.field != "approximate_size"]
    for change, reason in (
        ({"facts": others}, "MISSING_FACT"),
        ({"facts": [*others, size.model_copy(update={"status": "observed"})]}, "MISSING_FACT"),
        ({"facts": [*others, size.model_copy(update={"conflict": True})]}, "CONFLICTING_FACT"),
        ({"facts": others, "unavailable_fields": ["approximate_size"]}, "SOURCE_CHANGED"),
        ({"owner_handoff": True}, "OWNER_HANDOFF"),
    ):
        result = evaluate(complete.model_copy(update=change))
        assert result.reason == reason and result.occupied_minutes is None


def test_refusal_uses_explicit_published_limit_and_current_fact():
    result = evaluate(assessment_inputs(size="81 mm", rules=[("MAX_SIZE_MM", 80)]))
    assert (result.outcome, result.field, result.rule_id, result.limit, result.size_mm) == (
        "DECLINED",
        "approximate_size",
        "max_size_mm",
        80,
        81,
    )
    at_limit = evaluate(assessment_inputs(rules=[("MAX_SIZE_MM", 80)]))
    assert at_limit.occupied_minutes == 90
    unknown = evaluate(assessment_inputs(size=None, rules=[("MAX_SIZE_MM", 80)]))
    assert unknown.outcome == "NEEDS_DATA"
    age = evaluate(assessment_inputs(rules=[("MIN_AGE", 18)]))
    assert (age.outcome, age.reason, age.limit, age.occupied_minutes) == (
        "NEEDS_DATA",
        "MIN_AGE_UNCONFIRMED",
        18,
        None,
    )


def test_publication_shape_preserves_note_only_releases_and_rejects_invalid_policy():
    old = intake_bundle()
    old["services"][0]["duration"] = {
        "mode": "CONFIGURED_RULE",
        "minutes": None,
        "rule_note": "Illustrative text",
    }
    assert Bundle.model_validate(old).model_dump() == old
    assert validate_bundle(old).model_dump()["issues"] == [
        {"code": "OWNER_HANDOFF", "path": "services.consultation.duration", "severity": "WARNING"}
    ]
    active = assessment_inputs()
    assert active.service is not None
    assert (
        evaluate(
            active.model_copy(update={"service": Service.model_validate(old["services"][0])})
        ).reason
        == "DURATION_UNPUBLISHED"
    )

    duration = old["services"][0]["duration"]
    duration["size_rule"] = dict(SIZE_RULE)
    assert validate_bundle(old).valid
    duration["mode"] = "OWNER_DEFINED"
    assert not validate_bundle(old).valid
    duration["mode"] = "CONFIGURED_RULE"
    duration["size_rule"]["threshold_mm"] = 1000
    assert not validate_bundle(old).valid
