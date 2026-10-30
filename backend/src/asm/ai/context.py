"""Bounded text projections of existing M3 snapshots, never authority or media access."""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from asm.ai.contracts import DTO, Message
from asm.conversations.guards import (
    GuardedTurnSnapshot,
    GuardedTurnSnapshotV2,
    parse_guarded_snapshot,
)
from asm.conversations.material import MessageCurrent
from asm.conversations.turns import (
    TurnSnapshotV2,
    TurnSnapshotV3,
    parse_snapshot,
)

Positive = Annotated[int, Field(gt=0, le=9223372036854775807)]
Nonnegative = Annotated[int, Field(ge=0, le=9223372036854775807)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ContextCode = Literal[
    "UNSUPPORTED_SNAPSHOT", "INVALID_CONTEXT", "CONTEXT_MISMATCH", "CONTEXT_TOO_LARGE"
]


class ContextFailure(Exception):
    def __init__(self, code: ContextCode):
        self.code = code
        super().__init__(code)


class NativeFence(DTO):
    """Private expected native revision, checked by the future authority implementation."""

    revision_id: UUID
    revision_no: Positive
    policy_epoch: Positive
    observation_epoch: Nonnegative
    reviewed_ingress_checkpoint: Nonnegative
    reviewed_input_state_hash: Digest


class ContextBinding(DTO):
    """Server-supplied expected scope/fences; equality is NOT authorization."""

    workspace_id: UUID
    client_id: UUID
    conversation_id: UUID
    business_id: UUID
    connection_id: UUID
    job_id: UUID
    turn_id: UUID
    turn_revision: Positive
    context_version: Positive
    control_generation: Positive
    activation_fence_seq: Positive
    resume_receipt_id: UUID
    snapshot_digest: Digest
    native: NativeFence | None


class ContextLimits(DTO):
    max_bytes: int = Field(default=8192, ge=512, le=16384)
    recent_messages: int = Field(default=8, ge=0, le=16)


class VisibleMessage(DTO):
    """Only current material and non-identifying provenance reach the model."""

    source: Literal["CURRENT_TURN", "RECENT_HISTORY"]
    origin: Literal[
        "CLIENT_INBOUND", "OWNER_MANUAL", "CONTROLLED_AUTOMATION", "LEGACY_UNATTRIBUTED"
    ]
    at: datetime
    state: Literal["VISIBLE", "DELETED", "ORDER_UNCERTAIN", "UNSUPPORTED_CONTENT"]
    content_type: Literal["TEXT", "PHOTO"] | None
    text: str | None = Field(max_length=4096, repr=False)
    changed: bool
    image_availability: Literal[
        "NOT_APPLICABLE",
        "ORIGINAL_PENDING",
        "ORIGINAL_READY",
        "ORIGINAL_FAILED",
        "ORIGINAL_NOT_FETCHED",
        "MEDIA_REPLACED_UNAVAILABLE",
        "HIDDEN",
    ]
    image_read: Literal[False] = False
    delivery_status: Literal["PENDING", "DISPATCHING", "SENT", "FAILED", "UNKNOWN"] | None


class ContextView(DTO):
    """Closed model-visible READ result, not the private snapshot or a send permit."""

    revision: Literal["conversation_context_v1"] = "conversation_context_v1"
    current: tuple[VisibleMessage, ...] = Field(min_length=1, max_length=64)
    recent: tuple[VisibleMessage, ...] = Field(max_length=16)
    recent_is_historical: Literal[True] = True
    owner_confirmed_text: str | None = Field(max_length=4096, repr=False)
    owner_source_media: Literal["NONE", "UNAVAILABLE"] | None
    source_coverage_status: Literal["OWNER_TEXT", "CANONICAL_COMPLETE", "UNAVAILABLE_V2"]
    context_coverage: Literal["OWNER_ASSERTED_TEXT_ONLY", "UNAVAILABLE_V2"]
    context_limitations: tuple[
        Literal[
            "PROVIDER_HISTORY_UNVERIFIED",
            "NATIVE_MEDIA_UNAVAILABLE",
            "IMAGES_NOT_READ",
            "HISTORY_UNAVAILABLE_V2",
        ],
        ...,
    ]
    readiness: Literal["COMPLETE", "PARTIAL"]
    source_history_truncated: bool | None
    history_truncated: bool | None
    history_omitted: int = Field(ge=0, le=16)

    def messages(self) -> tuple[Message, ...]:
        # Separate history/owner facts from the current user input. Neither is policy.
        return (
            Message(
                role="context",
                text=json.dumps(
                    self.model_dump(mode="json", exclude={"current"}),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            ),
            Message(
                role="user",
                text=json.dumps(
                    {"current": [m.model_dump(mode="json") for m in self.current]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            ),
        )


class PreparedContext(DTO):
    binding: ContextBinding = Field(repr=False)
    snapshot_fingerprint: Digest = Field(repr=False)
    view: ContextView = Field(repr=False)


def _visible(
    current: MessageCurrent,
    *,
    source: Literal["CURRENT_TURN", "RECENT_HISTORY"],
    at: datetime,
    origin: Literal[
        "CLIENT_INBOUND", "OWNER_MANUAL", "CONTROLLED_AUTOMATION", "LEGACY_UNATTRIBUTED"
    ],
    delivery: Literal["PENDING", "DISPATCHING", "SENT", "FAILED", "UNKNOWN"] | None = None,
) -> VisibleMessage:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ContextFailure("INVALID_CONTEXT")
    return VisibleMessage(
        source=source,
        origin=origin,
        at=at,
        state=current.state,
        content_type=current.content_type,
        text=current.text,
        changed=current.changed,
        image_availability=current.image_availability,
        delivery_status=delivery,
    )


class ContextBuilder:
    def __init__(self, limits: ContextLimits = ContextLimits()):
        self.limits = ContextLimits.model_validate(limits)

    def build(self, value: object, binding: ContextBinding) -> PreparedContext:
        """Parse the original saved JSON; only the explicit projection is model-visible.

        V2's historical digest codec is unchanged. The mandatory authority port must
        attest stored scope/fences; this local fingerprint only detects read drift.
        Do not dump/re-sign an already parsed V3 DTO: datetime normalization can
        change bytes covered by its original M3 digest.
        """
        try:
            binding = ContextBinding.model_validate(binding)
            if not isinstance(value, dict):
                raise ContextFailure("INVALID_CONTEXT")
            if "schema_version" not in value or value["schema_version"] == 1:
                raise ContextFailure("UNSUPPORTED_SNAPSHOT")
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode(
                "utf-8"
            )
            if len(raw) > 2097152:
                raise ContextFailure("CONTEXT_TOO_LARGE")
            snapshot = (
                parse_guarded_snapshot(value) if "consumer" in value else parse_snapshot(value)
            )
            if not isinstance(snapshot, (TurnSnapshotV2, TurnSnapshotV3, GuardedTurnSnapshotV2)):
                raise ContextFailure("UNSUPPORTED_SNAPSHOT")
            # Keep V2 top-level coercions from manufacturing revision equality.
            for name in ("turn_revision", "context_version", "control_generation"):
                if type(value.get(name)) is not int:
                    raise ContextFailure("INVALID_CONTEXT")
            for member in value["members"]:
                if any(
                    type(member.get(name)) is not int for name in ("message_version", "ingress_seq")
                ):
                    raise ContextFailure("INVALID_CONTEXT")
            for name in (
                "workspace_id",
                "connection_id",
                "job_id",
                "turn_id",
                "turn_revision",
                "context_version",
                "control_generation",
                "snapshot_digest",
            ):
                if getattr(snapshot, name) != getattr(binding, name):
                    raise ContextFailure("CONTEXT_MISMATCH")
            if isinstance(snapshot, GuardedTurnSnapshot):
                for name in (
                    "client_id",
                    "conversation_id",
                    "business_id",
                    "activation_fence_seq",
                    "resume_receipt_id",
                ):
                    if getattr(snapshot, name) != getattr(binding, name):
                        raise ContextFailure("CONTEXT_MISMATCH")
            native = None
            if isinstance(snapshot, TurnSnapshotV3):
                h = snapshot.human_context
                native = NativeFence(
                    revision_id=UUID(h.revision_id),
                    revision_no=int(h.revision_no),
                    policy_epoch=int(snapshot.context_policy_epoch),
                    observation_epoch=int(snapshot.human_observation_epoch),
                    reviewed_ingress_checkpoint=int(h.reviewed_ingress_checkpoint),
                    reviewed_input_state_hash=h.reviewed_input_state_hash,
                )
                if snapshot.resume_receipt_id != binding.resume_receipt_id:
                    raise ContextFailure("CONTEXT_MISMATCH")
            if native != binding.native:
                raise ContextFailure("CONTEXT_MISMATCH")

            members = snapshot.members
            order = [(m.ingress_at, m.ingress_seq, str(m.message_id)) for m in members]
            if order != sorted(set(order)) or len({m.message_id for m in members}) != len(members):
                raise ContextFailure("INVALID_CONTEXT")
            current = tuple(
                _visible(m.current, source="CURRENT_TURN", at=m.ingress_at, origin="CLIENT_INBOUND")
                for m in members
            )
            recent: list[VisibleMessage] = []
            if isinstance(snapshot, TurnSnapshotV3):
                ids = {str(m.message_id) for m in members}
                for m in snapshot.recent_messages:
                    if m.message_id in ids:
                        if m.direction != "INBOUND":
                            raise ContextFailure("INVALID_CONTEXT")
                        continue  # The parser already checked identical current/version.
                    recent.append(
                        _visible(
                            m.current,
                            source="RECENT_HISTORY",
                            at=datetime.fromisoformat(m.created_at),
                            origin=m.origin,
                            delivery=m.delivery.status if m.delivery else None,
                        )
                    )
                view = ContextView(
                    current=current,
                    recent=(),
                    owner_confirmed_text=snapshot.human_context.text,
                    owner_source_media=snapshot.human_context.source_media,
                    source_coverage_status=snapshot.coverage_status,
                    context_coverage=snapshot.context_coverage,
                    context_limitations=(*snapshot.context_limitations, "IMAGES_NOT_READ"),
                    readiness=snapshot.readiness,
                    source_history_truncated=snapshot.history_truncated,
                    history_truncated=snapshot.history_truncated,
                    history_omitted=0,
                )
            else:
                view = ContextView(
                    current=current,
                    recent=(),
                    owner_confirmed_text=None,
                    owner_source_media=None,
                    source_coverage_status="UNAVAILABLE_V2",
                    context_coverage="UNAVAILABLE_V2",
                    context_limitations=("HISTORY_UNAVAILABLE_V2", "IMAGES_NOT_READ"),
                    readiness=snapshot.readiness,
                    source_history_truncated=None,
                    history_truncated=None,
                    history_omitted=0,
                )
            omitted = max(0, len(recent) - self.limits.recent_messages)
            while True:
                bounded = ContextView.model_validate(
                    view.model_dump()
                    | {
                        "recent": tuple(recent[omitted:]),
                        "history_omitted": omitted,
                        "history_truncated": True if omitted else view.history_truncated,
                    }
                )
                if len(bounded.model_dump_json().encode("utf-8")) <= self.limits.max_bytes:
                    # Validate Message limits here too; Gateway checks whole input/tokens.
                    bounded.messages()
                    return PreparedContext(
                        binding=binding,
                        snapshot_fingerprint=hashlib.sha256(raw).hexdigest(),
                        view=bounded,
                    )
                if omitted == len(recent):
                    raise ContextFailure("CONTEXT_TOO_LARGE")
                omitted += 1  # Drop whole oldest history entries, never owner/current text.
        except ContextFailure:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
            raise ContextFailure("INVALID_CONTEXT") from None
