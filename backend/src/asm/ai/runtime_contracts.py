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
    Usage,
)
from asm.ai.knowledge import KnowledgePin
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


AnyPreparedRun = PreparedRun | PreparedKnowledgeRun


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
