"""Shared closed owner payload validation entry points."""

from asm.intake.models import DurationCaseInput


def validate_case(value: object) -> DurationCaseInput:
    return DurationCaseInput.model_validate(value)
