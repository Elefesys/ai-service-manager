"""Private persistence contracts. A chosen result is a fact, never a send permit."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from asm.ai.context import ContextBinding, Digest
from asm.ai.contracts import DTO, Budget, ConversationResult, Cost, GatewayConfig, Usage


class PreparedRun(DTO):
    run_id: UUID
    binding: ContextBinding = Field(repr=False)
    snapshot: dict[str, Any] = Field(repr=False)
    storage_fingerprint: Digest
    config: GatewayConfig = Field(repr=False)
    deadline: datetime
    budget: Budget
    reads_used: int = Field(ge=0, le=1)


class RuntimeReceipt(DTO):
    run_id: UUID
    job_id: UUID
    turn_id: UUID
    turn_revision: int = Field(gt=0)
    selected_at: datetime
    result: ConversationResult = Field(repr=False)
    send_permit: Literal[False] = False


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
