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
    PortfolioGatewayConfig,
    SearchGatewayConfig,
    Usage,
)
from asm.ai.knowledge import KnowledgePin, SearchPin, SearchProjection, SearchRefs
from asm.ai.portfolio import (
    MediaPin,
    PortfolioPin,
    PortfolioProjection,
    PortfolioRefs,
    RawVisionObservation,
)
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


class PreparedPortfolioRun(_PreparedRun):
    """One explicit image-profile run; no older config/DTO gains image authority."""

    config: PortfolioGatewayConfig = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)
    active_projection: ActiveProjection = Field(repr=False)
    search_pin: SearchPin = Field(repr=False)
    search_refs: SearchRefs | None = Field(repr=False)
    portfolio_pin: PortfolioPin = Field(repr=False)
    media_pin: MediaPin = Field(repr=False)
    portfolio_refs: PortfolioRefs | None = Field(repr=False)
    portfolio_session_id: UUID = Field(repr=False)
    search_query: str = Field(repr=False, max_length=1024)
    vision_analysis: RawVisionObservation | None = Field(repr=False)

    @model_validator(mode="after")
    def pinned_scope(self) -> Self:
        active, pin, search, portfolio = (
            self.active_projection,
            self.knowledge_pin,
            self.search_pin,
            self.portfolio_pin,
        )
        if (
            self.binding.business_id != pin.business_id
            or str(self.binding.workspace_id) != active.workspace_id
            or str(pin.business_id) != active.business_id
            or (str(pin.release_id) if pin.release_id else None) != active.release_id
            or pin.activation_version != active.activation_version
            or (search.business_id, search.release_id, search.activation_version)
            != (pin.business_id, pin.release_id, pin.activation_version)
            or (portfolio.business_id, portfolio.release_id, portfolio.activation_version)
            != (pin.business_id, pin.release_id, pin.activation_version)
            or not self.media_pin.scope(self.binding)
            or self.search_refs is not None
            and self.search_refs.profile_id != search.profile_id
            or self.portfolio_refs is not None
            and self.portfolio_refs.profile_id != portfolio.profile_id
            or len(self.search_query.encode("utf-8")) > 1024
        ):
            raise ValueError("PORTFOLIO_SCOPE_MISMATCH")
        if self.vision_analysis is None:
            if self.media_pin.analysis_id is not None:
                raise ValueError("VISION_SOURCE_MISMATCH")
        elif (
            self.vision_analysis.analysis_id,
            self.vision_analysis.analysis_sha256,
            self.vision_analysis.source_sha256,
        ) != (
            self.media_pin.analysis_id,
            self.media_pin.analysis_sha256,
            self.media_pin.source_sha256,
        ):
            raise ValueError("VISION_SOURCE_MISMATCH")
        return self


class PortfolioQueryData(DTO):
    knowledge: SearchProjection = Field(repr=False)
    portfolio: PortfolioProjection = Field(repr=False)
    portfolio_pin: PortfolioPin = Field(repr=False)
    media_pin: MediaPin = Field(repr=False)
    portfolio_refs: PortfolioRefs = Field(repr=False)
    portfolio_session_id: UUID = Field(repr=False)
    search_query: str = Field(repr=False, max_length=1024)
    vision_analysis: RawVisionObservation | None = Field(repr=False)

    @model_validator(mode="after")
    def shared_query(self) -> Self:
        if (
            (self.knowledge.profile_id, self.knowledge.query_sha256)
            != (self.portfolio.profile_id, self.portfolio.query_sha256)
            or self.portfolio_refs != self.portfolio.refs()
            or self.portfolio_pin.profile_id != self.portfolio.profile_id
            or len(self.search_query.encode("utf-8")) > 1024
        ):
            raise ValueError("PORTFOLIO_QUERY_MISMATCH")
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


class PortfolioQueryReservation(DTO):
    status: Literal["RESERVED", "REPLAY"]
    call_id: UUID | None
    ticket: UUID | None = Field(repr=False)
    wire: str | None = Field(repr=False, max_length=8192)
    wire_sha256: Digest | None
    profile_id: Literal["polza_openai_text_embedding3small_1536_cosine_v1"]
    deadline: datetime | None
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
        if self.deadline is not None and (
            self.deadline.tzinfo is None or self.deadline.utcoffset() is None
        ):
            valid = False
        if not valid:
            raise ValueError("Invalid query reservation")
        return self


AnyPreparedRun = PreparedRun | PreparedKnowledgeRun | PreparedSearchRun | PreparedPortfolioRun


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


class PortfolioRuntimeReceipt(SearchRuntimeReceipt):
    portfolio_pin: PortfolioPin = Field(repr=False)
    media_pin: MediaPin = Field(repr=False)
    portfolio_refs: PortfolioRefs = Field(repr=False)

    @model_validator(mode="after")
    def portfolio_scope(self) -> Self:
        pin, portfolio = self.knowledge_pin, self.portfolio_pin
        if (
            (portfolio.business_id, portfolio.release_id, portfolio.activation_version)
            != (pin.business_id, pin.release_id, pin.activation_version)
            or self.portfolio_refs.profile_id != portfolio.profile_id
            or self.media_pin.business_id != pin.business_id
        ):
            raise ValueError("PORTFOLIO_SCOPE_MISMATCH")
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
