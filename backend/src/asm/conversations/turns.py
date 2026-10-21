"""Private typed snapshots and an effect-free deterministic TEST consumer."""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BeforeValidator, Field, TypeAdapter, field_validator, model_validator

from asm.billing.models import StrictModel
from asm.billing.validation import (
    MAX_BIGINT,
    CanonicalUUID,
    LimitDecimal,
    PositiveDecimal,
    Timestamp,
)
from asm.conversations.material import MessageCurrent
from asm.conversations.native_context_http_models import HumanContextRevision
from asm.messaging.http_models import DeliveryResponse
from asm.messaging.results import Result


def _exact_snapshot_version(value: object) -> object:
    if type(value) is not int:
        raise ValueError("Invalid snapshot version")
    return value


_snapshot_version: TypeAdapter[Literal[2, 3]] = TypeAdapter(
    Annotated[Literal[2, 3], BeforeValidator(_exact_snapshot_version)]
)


def snapshot_version(value: object) -> Literal[2, 3]:
    return _snapshot_version.validate_python(value)


class TurnFile(Result):
    file_id: UUID
    version: int = Field(gt=0)
    status: Literal["PENDING", "READY", "FAILED"]
    error_code: str | None
    wait_expired: bool


class TurnMember(Result):
    message_id: UUID
    message_version: int = Field(gt=0)
    content_type: Literal["TEXT", "IMAGE_REFERENCE"]
    ingress_at: datetime
    ingress_seq: int = Field(gt=0)
    file: TurnFile | None


class TurnSnapshot(Result):
    code: Literal["SNAPSHOT"]
    job_id: UUID
    workspace_id: UUID
    connection_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    context_version: int = Field(gt=0)
    control_generation: int = Field(gt=0)
    readiness: Literal["COMPLETE", "PARTIAL"]
    members: tuple[TurnMember, ...] = Field(min_length=1, max_length=64)
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$")


class TurnMemberV2(TurnMember):
    membership_form: Literal["INITIAL_FOLD_SUPPRESSED"] | None
    initial_suppression_id: UUID | None
    current: MessageCurrent

    @model_validator(mode="after")
    def membership(self) -> Self:
        if self.current.changed != (self.message_version > 1):
            raise ValueError("Invalid material version")
        if self.membership_form is None:
            if self.initial_suppression_id is not None or (
                (self.content_type == "IMAGE_REFERENCE") != (self.file is not None)
            ):
                raise ValueError("Invalid retained membership")
        elif (
            self.initial_suppression_id is None
            or self.file is not None
            or self.content_type != "IMAGE_REFERENCE"
            or not self.current.changed
        ):
            raise ValueError("Invalid suppressed membership")
        return self


class TurnSnapshotV2(TurnSnapshot):
    schema_version: Literal[2]

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_schema(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Invalid snapshot version")
        return value

    members: tuple[TurnMemberV2, ...] = Field(min_length=1, max_length=64)


def native_jsonb(value: object) -> bytes:
    """0013 jsonb::text for this closed integer/string/boolean snapshot domain.

    PostgreSQL orders object keys by UTF-8 byte length then bytes. V2's codec and
    saved digests are deliberately untouched; this encoder is only for V3.
    """
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Invalid snapshot key")
        return (
            b"{"
            + b", ".join(
                native_jsonb(k) + b": " + native_jsonb(value[k])
                for k in sorted(value, key=lambda k: (len(k.encode("utf-8")), k.encode("utf-8")))
            )
            + b"}"
        )
    if type(value) is list:
        return b"[" + b", ".join(native_jsonb(v) for v in value) + b"]"
    if value is None or type(value) in (str, int, bool):
        return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
    raise ValueError("Invalid snapshot scalar")


def _native_uuid(value: object) -> None:
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Invalid snapshot UUID")


def _native_integer(value: object) -> None:
    if type(value) is not int or not 1 <= value <= MAX_BIGINT:
        raise ValueError("Invalid snapshot integer")


def validate_native_snapshot(value: object) -> object:
    """Reject re-signed type coercions before the retained private DTO parser."""
    if (
        type(value) is not dict
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 3
    ):
        raise ValueError("Invalid V3 snapshot")
    for field in ("workspace_id", "connection_id", "turn_id", "resume_receipt_id", "job_id"):
        _native_uuid(value.get(field))
    for field in ("turn_revision", "context_version", "control_generation"):
        _native_integer(value.get(field))
    if "activation_fence_seq" in value:
        _native_integer(value["activation_fence_seq"])
    for field in ("conversation_id", "client_id", "business_id"):
        if field in value:
            _native_uuid(value[field])
    members = value.get("members")
    if type(members) is not list:
        raise ValueError("Invalid V3 members")
    for member in members:
        if type(member) is not dict:
            raise ValueError("Invalid V3 member")
        _native_uuid(member.get("message_id"))
        for field in ("message_version", "ingress_seq"):
            _native_integer(member.get(field))
        if member.get("initial_suppression_id") is not None:
            _native_uuid(member["initial_suppression_id"])
        if type(member.get("ingress_at")) is not str:
            raise ValueError("Invalid ingress time")
        moment = datetime.fromisoformat(member["ingress_at"])
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("Invalid ingress time")
        file = member.get("file")
        if file is not None:
            if type(file) is not dict:
                raise ValueError("Invalid V3 file")
            _native_uuid(file.get("file_id"))
            _native_integer(file.get("version"))
            if type(file.get("wait_expired")) is not bool or file["wait_expired"] != (
                file.get("status") == "PENDING"
            ):
                raise ValueError("Invalid file wait")
            if file.get("status") == "FAILED":
                if file.get("error_code") not in (
                    "INVALID_INPUT",
                    "DEPENDENCY_TIMEOUT",
                    "DEPENDENCY_UNAVAILABLE",
                    "RETRY_EXHAUSTED",
                ):
                    raise ValueError("Invalid file error")
            elif file.get("error_code") is not None:
                raise ValueError("Invalid file error")
    body = {k: v for k, v in value.items() if k not in ("code", "job_id", "snapshot_digest")}
    encoded = native_jsonb(body)
    if len(encoded) > 2097152 or hashlib.sha256(encoded).hexdigest() != value.get(
        "snapshot_digest"
    ):
        raise ValueError("Invalid V3 size/digest")
    return value


class RecentMessageFile(StrictModel):
    file_id: CanonicalUUID
    version: PositiveDecimal
    status: Literal["PENDING", "READY", "FAILED"]


class RecentMessage(StrictModel):
    message_id: CanonicalUUID
    version: PositiveDecimal
    direction: Literal["INBOUND", "OUTBOUND"]
    origin: Literal[
        "CLIENT_INBOUND", "OWNER_MANUAL", "CONTROLLED_AUTOMATION", "LEGACY_UNATTRIBUTED"
    ]
    created_at: Timestamp
    current: MessageCurrent
    delivery: DeliveryResponse | None
    file: RecentMessageFile | None

    @model_validator(mode="after")
    def identity(self) -> Self:
        if (
            self.current.changed != (int(self.version) > 1)
            or (
                self.direction == "INBOUND"
                and (self.origin != "CLIENT_INBOUND" or self.delivery is not None)
            )
            or (
                self.direction == "OUTBOUND"
                and (self.origin == "CLIENT_INBOUND" or self.file is not None)
            )
        ):
            raise ValueError("Invalid recent message identity")
        if self.current.image_availability in (
            "ORIGINAL_READY",
            "ORIGINAL_PENDING",
            "ORIGINAL_FAILED",
        ) and (
            self.file is None or self.current.image_availability != "ORIGINAL_" + self.file.status
        ):
            raise ValueError("Invalid recent image")
        return self


class TurnSnapshotV3(TurnSnapshot):
    schema_version: Literal[3]
    members: tuple[TurnMemberV2, ...] = Field(min_length=1, max_length=64)
    human_context: HumanContextRevision
    context_policy_epoch: PositiveDecimal
    human_observation_epoch: LimitDecimal
    resume_receipt_id: UUID
    recent_messages: tuple[RecentMessage, ...] = Field(max_length=16)
    history_truncated: bool = Field(strict=True)
    coverage_status: Literal["OWNER_TEXT", "CANONICAL_COMPLETE"]
    context_coverage: Literal["OWNER_ASSERTED_TEXT_ONLY"]
    context_limitations: tuple[
        Literal["PROVIDER_HISTORY_UNVERIFIED", "NATIVE_MEDIA_UNAVAILABLE"], ...
    ]

    @model_validator(mode="before")
    @classmethod
    def raw_contract(cls, value: Any) -> Any:
        return validate_native_snapshot(value)

    @model_validator(mode="after")
    def context(self) -> Self:
        r = self.human_context
        if (r.policy_epoch, r.observation_epoch) != (
            self.context_policy_epoch,
            self.human_observation_epoch,
        ) or int(r.confirmed_generation) + 1 != self.control_generation:
            raise ValueError("Invalid V3 activation")
        if r.disposition == "OWNER_TEXT":
            valid = self.coverage_status == "OWNER_TEXT"
        else:
            valid = (
                r.disposition == "CANONICAL_SUFFICIENT"
                and self.coverage_status == "CANONICAL_COMPLETE"
                and not self.history_truncated
            )
        limitations = ("PROVIDER_HISTORY_UNVERIFIED",) + (
            ("NATIVE_MEDIA_UNAVAILABLE",) if r.source_media == "UNAVAILABLE" else ()
        )
        if (
            not valid
            or self.context_limitations != limitations
            or (r.source_media == "UNAVAILABLE" and self.readiness != "PARTIAL")
        ):
            raise ValueError("Invalid V3 coverage")
        history = [(m.created_at, m.message_id) for m in self.recent_messages]
        member_order = [(m.ingress_at, m.ingress_seq, str(m.message_id)) for m in self.members]
        if (
            history != sorted(set(history))
            or len({m.message_id for m in self.recent_messages}) != len(history)
            or member_order != sorted(set(member_order))
            or len({m.message_id for m in self.members}) != len(self.members)
            or (self.history_truncated and len(history) != 16)
        ):
            raise ValueError("Invalid V3 ordering")
        for m in self.members:
            if m.current.image_availability in (
                "ORIGINAL_READY",
                "ORIGINAL_PENDING",
                "ORIGINAL_FAILED",
            ) and (m.file is None or m.current.image_availability != "ORIGINAL_" + m.file.status):
                raise ValueError("Invalid V3 member image")
            for recent in self.recent_messages:
                if recent.message_id == str(m.message_id) and (
                    int(recent.version) != m.message_version or recent.current != m.current
                ):
                    raise ValueError("Inconsistent same-message projection")
        if self.readiness == "COMPLETE" and any(
            m.current.image_availability not in ("NOT_APPLICABLE", "ORIGINAL_READY")
            for m in self.members
        ):
            raise ValueError("Unavailable V3 input")
        return self


def parse_snapshot(value: object) -> TurnSnapshot:
    if isinstance(value, dict) and "schema_version" in value:
        version = snapshot_version(value["schema_version"])
        return (TurnSnapshotV3 if version == 3 else TurnSnapshotV2).model_validate(value)
    return TurnSnapshot.model_validate(value)


class TurnProgress(Result):
    code: Literal["GROUPED", "WAITING_MEDIA", "SUPERSEDED"]
    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)


class TurnAdmissionProgress(Result):
    """Used-policy TEST admission refused before a consumer receipt exists."""

    code: Literal["STALE", "NOT_ALLOWED"]
    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0, le=MAX_BIGINT, strict=True)


def parse_turn_progress(value: object) -> TurnProgress | TurnAdmissionProgress:
    if isinstance(value, dict) and value.get("code") in ("STALE", "NOT_ALLOWED"):
        return TurnAdmissionProgress.model_validate(value)
    return TurnProgress.model_validate(value)


class ConsumerResult(Result):
    consumer: Literal["TURN_TEST_V1"] = "TURN_TEST_V1"
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$")
    member_count: int = Field(ge=1, le=64)
    ready_file_count: int = Field(ge=0, le=64)
    wait_expired_count: int = Field(ge=0, le=64)


class ConsumerReceipt(Result):
    code: Literal["OBSERVED", "STALE"]
    job_id: UUID
    workspace_id: UUID
    connection_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    consumer: Literal["TURN_TEST_V1"]
    input_context_version: int = Field(gt=0)
    input_control_generation: int = Field(gt=0)
    snapshot_digest: str = Field(pattern="^[0-9a-f]{64}$")
    accepted_at: datetime
    result: ConsumerResult


def consume(snapshot: TurnSnapshot) -> ConsumerResult:
    """Pure computation over saved refs. It cannot issue a send or fetch media."""
    return ConsumerResult(
        snapshot_digest=snapshot.snapshot_digest,
        member_count=len(snapshot.members),
        ready_file_count=sum(
            (
                m.current.image_availability == "ORIGINAL_READY"
                if isinstance(m, TurnMemberV2)
                else m.file is not None and m.file.status == "READY"
            )
            for m in snapshot.members
        ),
        wait_expired_count=sum(
            (
                m.current.image_availability == "ORIGINAL_PENDING"
                if isinstance(m, TurnMemberV2)
                else m.file is not None and m.file.wait_expired
            )
            for m in snapshot.members
        ),
    )
