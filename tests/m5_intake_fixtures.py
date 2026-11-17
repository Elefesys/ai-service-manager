"""Fictional source-backed intake and measured-time examples."""

import json

from asm.configuration.models import ActiveProjection, Bundle
from asm.intake.models import CandidateSet, DurationCaseInput, IntakeProjection
from asm.intake.templates import tattoo_fields
from m5_configuration_fixtures import configuration_bundle

WS, BUSINESS, CLIENT, CONVERSATION, MESSAGE, RELEASE, OWNER = (
    f"00000000-0000-0000-0000-{n:012d}" for n in range(1, 8)
)


def intake_bundle():
    value = configuration_bundle()
    value["services"][0]["intake_fields"] = [f.model_dump() for f in tattoo_fields()]
    return value


def active():
    return ActiveProjection(
        schema_version=1,
        workspace_id=WS,
        business_id=BUSINESS,
        activation_version="1",
        release_id=RELEASE,
        source_draft_version="1",
        published_by=OWNER,
        published_at="2026-11-16T00:00:00.000000Z",
        bundle=Bundle.model_validate(intake_bundle()),
        structured_rules_authoritative=True,
    )


def projection(text="цветок, предплечье, 8 см, графика"):
    return IntakeProjection(
        revision="preliminary_intake_v1",
        workspace_id=WS,
        business_id=BUSINESS,
        conversation_id=CONVERSATION,
        client_id=CLIENT,
        service_id=None,
        release_id=RELEASE,
        activation_version="1",
        template_revision=None,
        control_generation="2",
        context_version="3",
        version="0",
        category="NEW_TATTOO",
        facts=[],
        missing=[],
        conflicts=[],
        status="NOT_STARTED",
        question=None,
        sources=[{"message_id": MESSAGE, "source_version": "a" * 64, "text": text}],
        fingerprint="b" * 64,
        preliminary=True,
    )


def candidates(values=None, **overrides):
    values = {"idea": "цветок"} if values is None else values
    return CandidateSet.model_validate_json(
        json.dumps(
            {
                "service_id": "consultation",
                "category": "NEW_TATTOO",
                "switch_request": False,
                "facts": [
                    {
                        "field": field,
                        "value": value,
                        "status": "client-stated",
                        "source": {
                            "message_id": MESSAGE,
                            "source_version": "a" * 64,
                            "quote": value,
                            "analysis_id": None,
                            "analysis_sha256": None,
                        },
                        "explicit_correction": False,
                    }
                    for field, value in values.items()
                ],
            }
            | overrides
        )
    )


def case_input(**changes):
    return DurationCaseInput.model_validate(
        {
            "description": "Synthetic owner-labelled flower",
            "asset": None,
            "width_mm": None,
            "height_mm": None,
            "placement": None,
            "style": None,
            "detail": None,
            "fill": None,
            "provider": None,
            "working_minutes": None,
            "occupied_minutes": None,
            "setup_minutes": None,
            "stencil_minutes": None,
            "break_minutes": None,
            "cleanup_minutes": None,
            "treatment": "UNKNOWN",
            "session_count": None,
            "session_minutes": None,
            "explanation": None,
        }
        | changes
    )
