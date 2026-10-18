"""Strict CONTROL wire values; receipt results are distinct from current state."""

from typing import Literal, Self

from pydantic import model_validator

from asm.billing.models import CommonCode, StrictModel
from asm.billing.validation import CanonicalUUID, PositiveDecimal, Timestamp

PositiveVersion = PositiveDecimal
ControlMode = Literal["HUMAN", "AI"]
ControlOperation = Literal["TAKEOVER", "RESUME"]


class ControlCommandRequest(StrictModel):
    expected_client_id: CanonicalUUID
    expected_control_generation: PositiveVersion
    expected_context_version: PositiveVersion


class ManualDeliveryState(StrictModel):
    has_dispatching: bool
    has_unknown: bool


class ControlStateResponse(StrictModel):
    workspace_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    control_mode: ControlMode
    control_generation: PositiveVersion
    context_version: PositiveVersion
    observed_at: Timestamp
    manual_delivery: ManualDeliveryState


class ControlAcceptedResult(StrictModel):
    workspace_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    receipt_id: CanonicalUUID
    audit_event_id: CanonicalUUID
    operation: ControlOperation
    previous_mode: ControlMode
    accepted_mode: ControlMode
    previous_generation: PositiveVersion
    accepted_generation: PositiveVersion
    context_version: PositiveVersion
    accepted_at: Timestamp

    @model_validator(mode="after")
    def transition(self) -> Self:
        if self.accepted_mode != ("HUMAN" if self.operation == "TAKEOVER" else "AI"):
            raise ValueError("Invalid control transition")
        if int(self.accepted_generation) != int(self.previous_generation) + 1:
            raise ValueError("Invalid control generation")
        return self


class ControlCommandResponse(StrictModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: ControlAcceptedResult


class ControlErrorDetail(StrictModel):
    code: (
        CommonCode
        | Literal[
            "NOT_ALLOWED",
            "CONTROL_VERSION_EXHAUSTED",
            "CONTEXT_POLICY_INACTIVE",
            "CONTEXT_POLICY_PAUSED",
            "HUMAN_REQUIRED",
            "CONTEXT_CONFIRMATION_REQUIRED",
            "CONTEXT_UNRESOLVED",
            "CONTEXT_INPUT_PENDING",
            "CONTEXT_INPUT_UNRESOLVED",
            "CONTEXT_COVERAGE_REQUIRED",
        ]
    )


class ControlErrorResponse(StrictModel):
    error: ControlErrorDetail
