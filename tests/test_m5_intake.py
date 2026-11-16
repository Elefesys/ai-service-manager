"""Authority, source evidence and progressive-intake behavior without a model loop."""

import json

import pytest
from asm.ai.contracts import CONVERSATION_RESULT, CONVERSATION_RESULT_V2, CONVERSATION_RESULT_V3
from asm.intake.models import CandidateSet
from asm.intake.projection import COMPLETE_TEXT, reduce_candidates
from asm.intake.templates import template_revision
from m5_intake_fixtures import OWNER, active, candidates, projection
from pydantic import ValidationError


def test_known_fields_produce_only_the_next_missing_question_and_no_photo_requirement():
    facts, status, question = reduce_candidates(
        projection(), candidates({"idea": "цветок", "placement": "предплечье"}), active()
    )
    assert status == "CLARIFY" and "размер" in question
    current = projection().model_copy(update={"service_id": "consultation", "facts": facts})
    facts, status, question = reduce_candidates(
        current, candidates({"approximate_size": "8 см", "style": "графика"}), active()
    )
    assert status == "PRELIMINARILY_COMPLETE" and question is None and len(facts) == 4
    assert "пока не согласованы" in COMPLETE_TEXT


def test_correction_replaces_explicit_value_while_implicit_conflict_stays_unresolved():
    current = projection("цветок, птица")
    facts, _, _ = reduce_candidates(current, candidates(), active())
    current = current.model_copy(update={"service_id": "consultation", "facts": facts})
    new = candidates({"idea": "птица"})
    facts, status, question = reduce_candidates(current, new, active())
    assert facts[0].value == "цветок" and facts[0].conflict and "противоречивое" in question
    new = new.model_copy(
        update={"facts": (new.facts[0].model_copy(update={"explicit_correction": True}),)}
    )
    facts, _, _ = reduce_candidates(current, new, active())
    assert facts[0].value == "птица" and not facts[0].conflict


@pytest.mark.parametrize(
    "change",
    [{"message_id": OWNER}, {"source_version": "c" * 64}, {"quote": "выдуманный источник"}],
)
def test_source_spoofing_and_stale_material_are_rejected(change):
    candidate = candidates()
    fact = candidate.facts[0]
    fact = fact.model_copy(update={"source": fact.source.model_copy(update=change)})
    with pytest.raises(ValueError):
        reduce_candidates(projection(), candidate.model_copy(update={"facts": (fact,)}), active())


def test_model_cannot_confirm_owner_authority_or_hide_extra_fields():
    value = candidates().model_dump(mode="json")
    value["facts"][0]["status"] = "owner-confirmed"
    with pytest.raises(ValidationError):
        CandidateSet.model_validate(value)
    result = {
        "kind": "reply",
        "text": "test",
        "reason": None,
        "intake": candidates().model_dump(mode="json"),
    }
    assert CONVERSATION_RESULT_V3.validate_json(json.dumps(result)).intake.category == "NEW_TATTOO"
    for legacy in (CONVERSATION_RESULT, CONVERSATION_RESULT_V2):
        with pytest.raises(ValidationError):
            legacy.validate_json(json.dumps(result))


@pytest.mark.parametrize("category", ["COVER_UP", "OTHER_COMPLEX"])
def test_complex_case_needs_one_owner_question(category):
    facts, status, question = reduce_candidates(
        projection(), candidates(category=category), active()
    )
    assert status == "OWNER_HANDOFF" and question and len(facts) == 1


def test_faq_and_ambiguous_topic_do_not_start_or_mix_requests():
    _, status, _ = reduce_candidates(
        projection(), candidates({}, category="FAQ_ONLY", service_id=None), active()
    )
    assert status == "NOT_STARTED"
    facts, status, question = reduce_candidates(
        projection(), candidates({}, category="AMBIGUOUS", service_id=None), active()
    )
    assert facts == [] and status == "CLARIFY" and question


def test_old_published_bundle_is_not_silently_reinterpreted_as_tattoo_template():
    from asm.configuration.models import Service
    from m5_configuration_fixtures import configuration_bundle

    assert template_revision(Service.model_validate(configuration_bundle()["services"][0])) is None
    assert template_revision(active().bundle.services[0]) == "tattoo_intake_v1"


def test_observation_remains_unconfirmed_and_unscaled_image_cannot_establish_size():
    value = candidates({"style": "графика"})
    observed = value.facts[0].model_copy(
        update={
            "status": "observed",
            "source": value.facts[0].source.model_copy(
                update={"analysis_id": OWNER, "analysis_sha256": "d" * 64}
            ),
        }
    )
    facts, status, _ = reduce_candidates(
        projection(), value.model_copy(update={"facts": (observed,)}), active()
    )
    assert facts[0].status == "observed" and status == "CLARIFY"
    bad = observed.model_copy(update={"field": "approximate_size", "value": "8 см"})
    with pytest.raises(ValueError):
        reduce_candidates(projection(), value.model_copy(update={"facts": (bad,)}), active())


def test_repeated_candidate_cannot_remove_owner_confirmation_or_clear_conflict():
    facts, _, _ = reduce_candidates(projection(), candidates(), active())
    confirmed = facts[0].model_copy(update={"status": "owner-confirmed", "confirmed_by": OWNER})
    current = projection().model_copy(update={"service_id": "consultation", "facts": [confirmed]})
    repeated, _, _ = reduce_candidates(current, candidates(), active())
    assert repeated == [confirmed]
    conflict = confirmed.model_copy(update={"conflict": True})
    current = current.model_copy(update={"facts": [conflict]})
    repeated, state, _ = reduce_candidates(current, candidates(), active())
    assert repeated == [conflict] and state == "CLARIFY"


def test_facts_without_published_service_are_schema_rejected():
    with pytest.raises(ValidationError):
        candidates(service_id=None)
