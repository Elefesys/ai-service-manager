"""Private persistence contracts. A chosen result is a fact, never a send permit."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from asm.ai.context import ContextBinding, Digest
from asm.ai.contracts import (
    DTO,
    AnyGatewayConfig,
    Budget,
    ConversationResult,
    Cost,
    GatewayConfig,
    KnowledgeGatewayConfig,
    SearchGatewayConfig,
    Usage,
)
from asm.ai.knowledge import KnowledgePin, SearchPin, SearchRefs
from asm.billing.validation import Timestamp
from asm.configuration.models import ActiveProjection


class _PreparedRun(DTO):
    run_id: UUID
    binding: ContextBinding = Field(repr=False)
    snapshot: dict[str, Any] = Field(repr=False)
    storage_fingerprint: Digest
    config: AnyGatewayConfig = Field(repr=False)
    deadline: datetime
    budget: Budget
    reads_used: int = Field(ge=0, le=1)


class PreparedRun(_PreparedRun):
    config: GatewayConfig = Field(repr=False)


class PreparedKnowledgeRun(_PreparedRun):
    """The new run carries an immutable publication, never a refreshed draft."""

    config: KnowledgeGatewayConfig = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)
    active_projection: ActiveProjection = Field(repr=False)

    @model_validator(mode="after")
    def pinned_scope(self) -> Self:
        projection, pin = self.active_projection, self.knowledge_pin
        if (
            self.config.prompt_revision != "conversation_v3"
            or self.binding.business_id != pin.business_id
            or str(self.binding.workspace_id) != projection.workspace_id
            or str(pin.business_id) != projection.business_id
            or (str(pin.release_id) if pin.release_id else None) != projection.release_id
            or pin.activation_version != projection.activation_version
        ):
            raise ValueError("KNOWLEDGE_SCOPE_MISMATCH")
        return self


class PreparedSearchRun(_PreparedRun):
    """v4 adds a fixed search pin and text-free references; v2/v3 stay closed."""

    config: SearchGatewayConfig = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)
    active_projection: ActiveProjection = Field(repr=False)
    search_pin: SearchPin = Field(repr=False)
    search_refs: SearchRefs | None = Field(repr=False)

    @model_validator(mode="after")
    def pinned_scope(self) -> Self:
        active, pin, search = self.active_projection, self.knowledge_pin, self.search_pin
        if (
            self.binding.business_id != pin.business_id
            or str(self.binding.workspace_id) != active.workspace_id
            or str(pin.business_id) != active.business_id
            or (str(pin.release_id) if pin.release_id else None) != active.release_id
            or pin.activation_version != active.activation_version
            or (search.business_id, search.release_id, search.activation_version)
            != (pin.business_id, pin.release_id, pin.activation_version)
            or self.search_refs is not None
            and self.search_refs.profile_id != search.profile_id
        ):
            raise ValueError("KNOWLEDGE_SCOPE_MISMATCH")
        return self


class QueryReservation(DTO):
    status: Literal["RESERVED", "REPLAY"]
    call_id: UUID | None
    ticket: UUID | None = Field(repr=False)
    wire: str | None = Field(repr=False, max_length=8192)
    wire_sha256: Digest | None
    profile_id: Literal["polza_openai_text_embedding3small_1536_cosine_v1"]
    deadline: Timestamp | None
    reserved_cost: Literal["0.08", "0.00"]
    currency: Literal["RUB"]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.call_id is None:
            valid = (
                self.status == "REPLAY"
                and self.ticket is None
                and self.wire is None
                and self.wire_sha256 is None
                and self.deadline is None
                and self.reserved_cost == "0.00"
            )
        else:
            valid = (
                self.wire_sha256 is not None
                and self.deadline is not None
                and self.reserved_cost == "0.08"
            )
            valid = valid and (
                (self.status == "RESERVED" and self.ticket is not None and self.wire is not None)
                or (self.status == "REPLAY" and self.ticket is None and self.wire is None)
            )
        if not valid:
            raise ValueError("Invalid query reservation")
        return self


AnyPreparedRun = PreparedRun | PreparedKnowledgeRun | PreparedSearchRun


class RuntimeReceipt(DTO):
    run_id: UUID
    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    selected_at: datetime
    result: ConversationResult = Field(repr=False)
    send_permit: Literal[False] = False


class KnowledgeRuntimeReceipt(RuntimeReceipt):
    """A publication pin is evidence, never a current send authorization."""

    knowledge_pin: KnowledgePin = Field(repr=False)


class SearchRuntimeReceipt(KnowledgeRuntimeReceipt):
    search_pin: SearchPin = Field(repr=False)
    search_refs: SearchRefs = Field(repr=False)

    @model_validator(mode="after")
    def consistent_pins(self) -> Self:
        pin, search = self.knowledge_pin, self.search_pin
        if (search.business_id, search.release_id, search.activation_version) != (
            pin.business_id,
            pin.release_id,
            pin.activation_version,
        ) or self.search_refs.profile_id != search.profile_id:
            raise ValueError("KNOWLEDGE_SCOPE_MISMATCH")
        return self


class CallCompletion(DTO):
    """No wire payload, candidate, provider diagnostic or claim in the trace."""

    kind: Literal["OUTPUT", "TOOLS", "REFUSAL", "TRUNCATED", "ERROR", "UNKNOWN"]
    usage: Usage = Usage()
    cost: Cost = Cost()
    error: Literal["ADAPTER_ERROR", "CANCELLED", "INVALID_RESPONSE"] | None = None


class RuntimeStop(DTO):
    run_id: UUID
    reason: Literal["INCOMPLETE", "AGENT_STOP"]
    send_permit: Literal[False] = False
