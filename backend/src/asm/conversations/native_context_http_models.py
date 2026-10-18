"""Closed owner-confirmed context wire contract; no transport or send authority."""

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from asm.billing.models import CommonCode, StrictModel
from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal, Timestamp
from asm.conversations.http_models import ManualDeliveryState
from asm.messaging.errors import MessagingError
from asm.messaging.models import manual_text, scalar_text

Disposition = Literal["OWNER_TEXT", "CANONICAL_SUFFICIENT", "UNRESOLVED"]
SourceMedia = Literal["NONE", "UNAVAILABLE"]
CoverageStatus = Literal[
    "UNCONFIRMED", "UNRESOLVED", "OWNER_TEXT", "CANONICAL_COMPLETE", "CANONICAL_TRUNCATED"
]
ContextBlocker = Literal[
    "POLICY_INACTIVE",
    "POLICY_PAUSED",
    "CONTEXT_CONFIRMATION_REQUIRED",
    "CONTEXT_CHANGED",
    "CONTEXT_UNRESOLVED",
    "NEW_OBSERVATION",
    "CONTEXT_INPUT_UNRESOLVED",
    "CONTEXT_COVERAGE_REQUIRED",
    "CONTEXT_INPUT_PENDING",
]
ResumeBlocker = ContextBlocker | Literal["HUMAN_REQUIRED"]
BLOCKER_ORDER = (
    "POLICY_INACTIVE",
    "POLICY_PAUSED",
    "CONTEXT_CONFIRMATION_REQUIRED",
    "CONTEXT_CHANGED",
    "CONTEXT_UNRESOLVED",
    "NEW_OBSERVATION",
    "CONTEXT_INPUT_UNRESOLVED",
    "CONTEXT_COVERAGE_REQUIRED",
    "CONTEXT_INPUT_PENDING",
)
REVIEW_STATUS = (
    "POLICY_INACTIVE",
    "POLICY_PAUSED",
    "BOOTSTRAP_REQUIRED",
    "CONFIRMATION_REQUIRED",
    "UNRESOLVED",
    "NEW_OBSERVATION",
    "INPUT_UNRESOLVED",
    "COVERAGE_REQUIRED",
    "INPUT_PENDING",
)
ContextReason = Literal[
    "CONTEXT_POLICY_PAUSED",
    "CONTEXT_CONFIRMATION_REQUIRED",
    "CONTEXT_UNRESOLVED",
    "NEW_OBSERVATION",
    "CONTEXT_INPUT_UNRESOLVED",
    "CONTEXT_COVERAGE_REQUIRED",
    "CONTEXT_TOO_LARGE",
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)]


def context_text(value: str) -> str:
    try:
        return manual_text(value)
    except MessagingError:
        raise ValueError("Invalid context text") from None


class ReconcileRequest(StrictModel):
    expected_client_id: CanonicalUUID
    expected_control_generation: PositiveDecimal
    expected_context_version: PositiveDecimal
    expected_policy_epoch: LimitDecimal
    expected_observation_epoch: LimitDecimal
    expected_ingress_checkpoint: LimitDecimal
    expected_input_state_hash: Digest = Field(repr=False)
    expected_revision_id: CanonicalUUID | None
    disposition: Disposition
    text: str | None = Field(min_length=1, max_length=4096, repr=False)
    source_media: SourceMedia
    attestation: Literal["REVIEWED_AVAILABLE_CONTEXT"]

    @field_validator("text")
    @classmethod
    def exact_text(cls, value: str | None) -> str | None:
        return context_text(value) if value is not None else None

    @model_validator(mode="after")
    def content(self) -> Self:
        if (self.disposition == "OWNER_TEXT" and self.text is None) or (
            self.disposition == "CANONICAL_SUFFICIENT"
            and (self.text is not None or self.source_media != "NONE")
        ):
            raise ValueError("Invalid reconciliation disposition")
        return self


class HumanContextRevision(StrictModel):
    revision_id: CanonicalUUID
    revision_no: PositiveDecimal
    previous_revision_id: CanonicalUUID | None
    actor_user_account_id: CanonicalUUID
    accepted_at: Timestamp
    disposition: Disposition
    text: str | None = Field(min_length=1, max_length=4096, repr=False)
    source_media: SourceMedia
    coverage: Literal["OWNER_ASSERTED_TEXT_ONLY"]
    confirmed_generation: PositiveDecimal
    accepted_context_version: PositiveDecimal
    policy_epoch: PositiveDecimal
    observation_epoch: LimitDecimal
    reviewed_ingress_checkpoint: LimitDecimal
    reviewed_input_state_hash: Digest = Field(repr=False)

    @field_validator("text")
    @classmethod
    def exact_text(cls, value: str | None) -> str | None:
        return ReconcileRequest.exact_text(value)

    @model_validator(mode="after")
    def content(self) -> Self:
        if (
            (self.disposition == "OWNER_TEXT" and self.text is None)
            or (
                self.disposition == "CANONICAL_SUFFICIENT"
                and (self.text is not None or self.source_media != "NONE")
            )
            or (self.previous_revision_id is None) != (self.revision_no == "1")
        ):
            raise ValueError("Invalid context revision")
        if self.previous_revision_id == self.revision_id:
            raise ValueError("Invalid revision predecessor")
        return self


class IdleAutomationWork(StrictModel):
    state: Literal["IDLE"]
    reason: None
    job_id: None
    turn_id: None
    observed_at: Timestamp


class WaitingAutomationWork(StrictModel):
    state: Literal["WAITING_CONTEXT"]
    reason: Literal["CONTEXT_INPUT_PENDING"]
    job_id: CanonicalUUID
    turn_id: CanonicalUUID
    observed_at: Timestamp


class HeldAutomationWork(StrictModel):
    state: Literal["OPERATOR_REQUIRED"]
    reason: ContextReason | Literal["CONTEXT_WAIT_EXHAUSTED"]
    job_id: CanonicalUUID
    turn_id: CanonicalUUID
    observed_at: Timestamp


AutomationWork = Annotated[
    IdleAutomationWork | WaitingAutomationWork | HeldAutomationWork, Field(discriminator="state")
]


class HumanContextState(StrictModel):
    workspace_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    observed_at: Timestamp
    control_mode: Literal["HUMAN", "AI"]
    control_generation: PositiveDecimal
    context_version: PositiveDecimal
    policy: Literal["OFF_UNUSED", "ON", "PAUSED"]
    policy_epoch: LimitDecimal
    observation_epoch: LimitDecimal
    ingress_checkpoint: LimitDecimal
    input_state_hash: Digest = Field(repr=False)
    input_gap_limit_exceeded: bool
    has_unsequenced_context_input: bool
    current_revision: HumanContextRevision | None
    review_status: Literal[
        "POLICY_INACTIVE",
        "POLICY_PAUSED",
        "BOOTSTRAP_REQUIRED",
        "CONFIRMATION_REQUIRED",
        "UNRESOLVED",
        "NEW_OBSERVATION",
        "INPUT_UNRESOLVED",
        "COVERAGE_REQUIRED",
        "INPUT_PENDING",
        "CONFIRMED",
    ]
    context_blockers: list[ContextBlocker] = Field(max_length=9)
    resume_blockers: list[ResumeBlocker] = Field(max_length=10)
    history_truncated: bool
    coverage_status: CoverageStatus
    pending_context_input: bool
    has_failed_context_input: bool
    unreviewed_failed_context_input: bool
    automation_work: AutomationWork
    manual_delivery: ManualDeliveryState

    @model_validator(mode="after")
    def projection(self) -> Self:
        blockers = self.context_blockers
        if blockers != [b for b in BLOCKER_ORDER if b in blockers]:
            raise ValueError("Invalid blocker order")
        status = REVIEW_STATUS[BLOCKER_ORDER.index(blockers[0])] if blockers else "CONFIRMED"
        if self.review_status != status or self.automation_work.observed_at != self.observed_at:
            raise ValueError("Inconsistent context projection")
        r = self.current_revision
        coverage = (
            "UNCONFIRMED"
            if r is None
            else "UNRESOLVED"
            if r.disposition == "UNRESOLVED"
            else "OWNER_TEXT"
            if r.disposition == "OWNER_TEXT"
            else "CANONICAL_TRUNCATED"
            if self.history_truncated
            else "CANONICAL_COMPLETE"
        )
        if self.coverage_status != coverage:
            raise ValueError("Invalid coverage")
        expected: list[ResumeBlocker] = list(blockers)
        if self.policy == "OFF_UNUSED":
            if (
                self.policy_epoch != "0"
                or self.observation_epoch != "0"
                or r is not None
                or blockers != ["POLICY_INACTIVE"]
            ):
                raise ValueError("Invalid unused policy")
            expected = []
        else:
            if (
                self.policy_epoch == "0"
                or ("POLICY_PAUSED" in blockers) != (self.policy == "PAUSED")
                or "POLICY_INACTIVE" in blockers
            ):
                raise ValueError("Invalid used policy")
            if ("CONTEXT_CONFIRMATION_REQUIRED" in blockers) != (r is None) or (
                "CONTEXT_INPUT_PENDING" in blockers
            ) != self.pending_context_input:
                raise ValueError("Invalid context blockers")
            if self.control_mode == "AI":
                expected.insert(int(self.policy == "PAUSED"), "HUMAN_REQUIRED")
        if self.resume_blockers != expected or (
            self.unreviewed_failed_context_input and not self.has_failed_context_input
        ):
            raise ValueError("Invalid resume projection")
        return self


class ObservationCursor(StrictModel):
    v: Literal[1]
    ws: CanonicalUUID
    C: CanonicalUUID
    Client: CanonicalUUID
    P: LimitDecimal
    through_N: LimitDecimal
    after_N: LimitDecimal

    @field_validator("v", mode="before")
    @classmethod
    def version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid cursor version")
        return value

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if int(self.after_N) > int(self.through_N):
            raise ValueError("Invalid cursor bounds")
        return self


class TextPreview(StrictModel):
    kind: Literal["TEXT"]
    text: str = Field(min_length=1, max_length=4096, repr=False)

    @field_validator("text")
    @classmethod
    def text_bounds(cls, value: str) -> str:
        try:
            return scalar_text(value, 4096, 16384)
        except MessagingError:
            raise ValueError("Invalid preview") from None


class PhotoPreview(StrictModel):
    kind: Literal["PHOTO"]
    caption: str | None = Field(max_length=4096, repr=False)
    image_availability: Literal["NATIVE_UNAVAILABLE"]

    @field_validator("caption")
    @classmethod
    def caption_bounds(cls, value: str | None) -> str | None:
        return TextPreview.text_bounds(value) if value is not None else None


class UnsupportedPreview(StrictModel):
    kind: Literal["UNSUPPORTED"]
    reason: Literal["UNSUPPORTED_CONTENT", "AMBIGUOUS_ORIGIN", "UNAVAILABLE_PROJECTION"]


class DeletePreview(StrictModel):
    kind: Literal["DELETE"]
    target_count: int = Field(ge=1, le=100)


Preview = Annotated[
    TextPreview | PhotoPreview | UnsupportedPreview | DeletePreview, Field(discriminator="kind")
]


class ObservationItem(StrictModel):
    observation_id: CanonicalUUID
    epoch: PositiveDecimal
    classification: Literal[
        "NATIVE_CANDIDATE", "AMBIGUOUS_NONCLIENT", "CANONICAL_MUTATION", "UNBOUND_MUTATION"
    ]
    observed_at: Timestamp
    source_kind: Literal["NEW", "EDIT", "DELETE"]
    preview: Preview
    coverage: Literal["PROVIDER_OBSERVATION_ONLY"]

    @model_validator(mode="after")
    def source(self) -> Self:
        if (self.source_kind == "DELETE") != (self.preview.kind == "DELETE"):
            raise ValueError("Invalid observation source")
        return self


class ObservationPage(StrictModel):
    items: list[ObservationItem] = Field(max_length=100)
    next_cursor: str | None = Field(min_length=1, max_length=1024)
    through_epoch: LimitDecimal
    current_epoch: LimitDecimal
    observed_at: Timestamp

    @model_validator(mode="after")
    def bounds(self) -> Self:
        epochs = [int(i.epoch) for i in self.items]
        if (
            epochs != sorted(set(epochs))
            or int(self.through_epoch) > int(self.current_epoch)
            or any(n > int(self.through_epoch) for n in epochs)
            or (self.next_cursor is not None and not epochs)
        ):
            raise ValueError("Invalid observation page")
        return self


class ReconcileResult(StrictModel):
    workspace_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    receipt_id: CanonicalUUID
    revision_id: CanonicalUUID
    revision_no: PositiveDecimal
    previous_revision_id: CanonicalUUID | None
    audit_event_id: CanonicalUUID
    control_generation: PositiveDecimal
    previous_context_version: PositiveDecimal
    accepted_context_version: PositiveDecimal
    policy_epoch: PositiveDecimal
    observation_epoch: LimitDecimal
    reviewed_ingress_checkpoint: LimitDecimal
    reviewed_input_state_hash: Digest = Field(repr=False)
    disposition: Disposition
    source_media: SourceMedia
    coverage: Literal["OWNER_ASSERTED_TEXT_ONLY"]
    accepted_at: Timestamp

    @model_validator(mode="after")
    def transition(self) -> Self:
        if (
            self.receipt_id != self.revision_id
            or int(self.accepted_context_version) != int(self.previous_context_version) + 1
            or (self.previous_revision_id is None) != (self.revision_no == "1")
        ):
            raise ValueError("Invalid reconciliation acceptance")
        return self


class ReconcileResponse(StrictModel):
    outcome: Literal["ACCEPTED", "REPLAY"]
    result: ReconcileResult


class EscalationContextHold(StrictModel):
    reason: Literal[
        "CONTEXT_POLICY_PAUSED",
        "CONTEXT_CONFIRMATION_REQUIRED",
        "CONTEXT_UNRESOLVED",
        "NEW_OBSERVATION",
        "CONTEXT_INPUT_UNRESOLVED",
        "CONTEXT_COVERAGE_REQUIRED",
        "CONTEXT_INPUT_PENDING",
    ]
    policy: Literal["ON", "PAUSED"]
    policy_epoch: PositiveDecimal
    observation_epoch: LimitDecimal
    coverage_status: CoverageStatus


class NativeContextErrorDetail(StrictModel):
    code: (
        CommonCode
        | Literal[
            "VERSION_EXHAUSTED",
            "CONTEXT_POLICY_INACTIVE",
            "CONTEXT_POLICY_PAUSED",
            "HUMAN_REQUIRED",
            "CONTEXT_CONFIRMATION_REQUIRED",
            "CONTEXT_UNRESOLVED",
            "CONTEXT_INPUT_PENDING",
            "CONTEXT_INPUT_UNRESOLVED",
            "CONTEXT_COVERAGE_REQUIRED",
            "CONTEXT_CURSOR_STALE",
        ]
    )


class NativeContextErrorResponse(StrictModel):
    error: NativeContextErrorDetail
