"""Explicit v6 photo proposal and exact shown-context READ attestation.

The model sees source identities, never destination or private storage access.
Only the durable server commit and final dispatch can grant a send permit.
"""

import hashlib
import json
from typing import Literal, Protocol

from pydantic import Field, model_validator

from asm.ai.agent import AnyAgentOutcome, Boundary, CurrentContextArgs, StopCode
from asm.ai.context import ContextBinding, ContextFailure, ContextView
from asm.ai.contracts import (
    DTO,
    AnyConversationResult,
    AnyGatewayConfig,
    Budget,
    Handoff,
    IntakeGatewayConfig,
    Message,
    PortfolioDeliveryGatewayConfig,
    PortfolioPhoto,
    PortfolioPhotoSelection,
    ReadTool,
)
from asm.ai.gateway import ModelAdapter
from asm.ai.knowledge import KnowledgeFailure, KnowledgePin, SearchPin, SearchProjection
from asm.ai.portfolio import (
    MediaPin,
    PortfolioAuthority,
    PortfolioAuthorityDecision,
    PortfolioContextBuilder,
    PortfolioContextRead,
    PortfolioConversationAgent,
    PortfolioKnowledgeView,
    PortfolioPin,
    PortfolioProjection,
    RawVisionObservation,
    reduce_portfolio_view,
)
from asm.configuration.models import ActiveProjection


def selection(reference: DTO) -> PortfolioPhotoSelection:
    return PortfolioPhotoSelection.model_validate(
        reference.model_dump(
            include={"item_id", "revision_id", "asset_version_id", "source_sha256"}
        )
    )


class DeliveryEligibility(DTO):
    revision: Literal["portfolio_delivery_eligibility_v1"] = "portfolio_delivery_eligibility_v1"
    references: tuple[PortfolioPhotoSelection, ...] = Field(max_length=3)
    transport: Literal["JPEG_PNG_ORIGINAL_BYTES"] = "JPEG_PNG_ORIGINAL_BYTES"

    @model_validator(mode="after")
    def unique_sources(self) -> "DeliveryEligibility":
        if len({v.item_id for v in self.references}) != len(self.references):
            raise ValueError("PORTFOLIO_DELIVERY_REFS_INVALID")
        return self


class PortfolioDeliveryContextView(DTO):
    revision: Literal["conversation_context_v5"] = "conversation_context_v5"
    conversation: ContextView
    business: PortfolioKnowledgeView
    delivery: DeliveryEligibility

    @model_validator(mode="after")
    def visible_subset(self) -> "PortfolioDeliveryContextView":
        shown = tuple(selection(v) for v in self.business.portfolio.matches)
        if any(v not in shown for v in self.delivery.references):
            raise ValueError("PORTFOLIO_DELIVERY_NOT_SHOWN")
        return self

    def messages(self) -> tuple[Message, ...]:
        context, current = self.conversation.messages()
        payload = self.business.model_dump(mode="json") | {
            "delivery": self.delivery.model_dump(mode="json")
        }
        # Canonical model-view JSON is also bounded by the context builder.
        return (
            context,
            Message(
                role="context", text=json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            ),
            current,
        )

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class PortfolioDeliveryReadView(DTO):
    revision: Literal["conversation_read_v5"] = "conversation_read_v5"
    same_context: Literal[True] = True
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analysis_status: Literal["ANALYSED", "UNAVAILABLE", "NO_IMAGE"]
    portfolio_status: Literal["RESULTS", "EMPTY"]
    delivery: DeliveryEligibility


class PreparedPortfolioDeliveryContext(DTO):
    binding: ContextBinding = Field(repr=False)
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    view: PortfolioDeliveryContextView = Field(repr=False)


class PortfolioDeliveryContextRead(PortfolioContextRead):
    delivery_eligible: tuple[PortfolioPhotoSelection, ...] = Field(max_length=3)


class PortfolioDeliveryAuthority(PortfolioAuthority, Protocol):
    async def read_current(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
    ) -> PortfolioDeliveryContextRead: ...

    async def attest_read(
        self,
        binding: ContextBinding,
        context_sha256: str,
        shown_refs: tuple[PortfolioPhotoSelection, ...],
    ) -> None: ...


class _DeliveryAuthorityAdapter:
    """Reuses the old exact-pin checks without reinterpreting its closed read DTO."""

    def __init__(
        self, inner: PortfolioDeliveryAuthority, eligible: tuple[PortfolioPhotoSelection, ...]
    ):
        self.inner, self.eligible = inner, eligible

    async def authorize(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
        boundary: Boundary,
    ) -> PortfolioAuthorityDecision:
        return await self.inner.authorize(
            binding, knowledge_pin, search_pin, portfolio_pin, media_pin, boundary
        )

    async def read_current(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
    ) -> PortfolioContextRead:
        value = PortfolioDeliveryContextRead.model_validate(
            await self.inner.read_current(
                binding, knowledge_pin, search_pin, portfolio_pin, media_pin
            )
        )
        if value.delivery_eligible != self.eligible:
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return PortfolioContextRead.model_validate(value.model_dump(exclude={"delivery_eligible"}))


class PortfolioDeliveryConversationAgent(PortfolioConversationAgent):
    prompt_revision = "conversation_v6"

    def __init__(
        self,
        config: AnyGatewayConfig,
        adapter: ModelAdapter,
        authority: PortfolioDeliveryAuthority,
        *,
        delivery_eligible: tuple[PortfolioPhotoSelection, ...],
        initial_budget: Budget | None = None,
        knowledge_pin: KnowledgePin,
        active_projection: ActiveProjection,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
        search_projection: SearchProjection,
        portfolio_projection: PortfolioProjection,
        vision_analysis: RawVisionObservation | None,
        search_query: str,
        builder: PortfolioContextBuilder | None = None,
    ):
        if not isinstance(config, (PortfolioDeliveryGatewayConfig, IntakeGatewayConfig)):
            raise ValueError("PORTFOLIO_DELIVERY_CONFIG_INVALID")
        self.eligible = DeliveryEligibility(references=delivery_eligible).references
        self.delivery_authority = authority
        self.shown: PortfolioDeliveryContextView | None = None
        self.attested: tuple[PortfolioPhotoSelection, ...] | None = None
        super().__init__(
            config,
            adapter,
            _DeliveryAuthorityAdapter(authority, self.eligible),
            initial_budget=initial_budget,
            knowledge_pin=knowledge_pin,
            active_projection=active_projection,
            search_pin=search_pin,
            portfolio_pin=portfolio_pin,
            media_pin=media_pin,
            search_projection=search_projection,
            portfolio_projection=portfolio_projection,
            vision_analysis=vision_analysis,
            search_query=search_query,
            builder=builder,
        )
        available = tuple(selection(v) for v in self.portfolio.matches)
        if any(v not in available for v in self.eligible):
            raise ValueError("PORTFOLIO_DELIVERY_SOURCE_INVALID")

    def _project(
        self, snapshot: object, binding: ContextBinding
    ) -> PreparedPortfolioDeliveryContext:
        base = super()._project(snapshot, binding)
        conversation, business = base.view.conversation, base.view.business
        while True:
            actual = tuple(selection(v) for v in business.portfolio.matches)
            view = PortfolioDeliveryContextView(
                conversation=conversation,
                business=business,
                delivery=DeliveryEligibility(
                    references=tuple(v for v in self.eligible if v in actual)
                ),
            )
            if (
                len(view.model_dump_json().encode("utf-8"))
                <= self.portfolio_builder.limits.max_bytes
            ):
                view.messages()
                if self.shown is not None and view != self.shown:
                    raise KnowledgeFailure("KNOWLEDGE_STALE")
                self.shown = view
                return PreparedPortfolioDeliveryContext(
                    binding=base.binding,
                    snapshot_fingerprint=base.snapshot_fingerprint,
                    view=view,
                )
            if conversation.recent:
                conversation = ContextView.model_validate(
                    conversation.model_dump()
                    | {
                        "recent": conversation.recent[1:],
                        "history_omitted": conversation.history_omitted + 1,
                        "history_truncated": True,
                    }
                )
            else:
                reduced = reduce_portfolio_view(business)
                if reduced is None:
                    raise ContextFailure("CONTEXT_TOO_LARGE")
                business = reduced

    def _tool(self) -> ReadTool:
        return ReadTool(
            name="read_context",
            revision="conversation_read_v5",
            description="Revalidate the exact supplied context and its sendable photo references. No mutation or send permission.",
            arguments=CurrentContextArgs,
            result=PortfolioDeliveryReadView,
        )

    def _read_result(self, view: DTO) -> str:
        if not isinstance(view, PortfolioDeliveryContextView) or view != self.shown:
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return PortfolioDeliveryReadView(
            context_sha256=view.digest(),
            analysis_status=view.business.analysis.status,
            portfolio_status=view.business.portfolio.status,
            delivery=view.delivery,
        ).model_dump_json()

    async def _after_read(self, view: DTO, binding: ContextBinding) -> None:
        if (
            not isinstance(view, PortfolioDeliveryContextView)
            or view != self.shown
            or self._reads != 1
        ):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        await self.delivery_authority.attest_read(binding, view.digest(), view.delivery.references)
        # Only successful durable attestation unlocks a photo proposal. A lost ACK
        # stops this invocation; recovery cannot rerun a model call or send effect.
        self.attested = view.delivery.references

    def _outcome(
        self, *, reason: StopCode | None = None, candidate: AnyConversationResult | None = None
    ) -> AnyAgentOutcome:
        if candidate is not None and self.search.status == "CONFLICT":
            candidate = Handoff(
                kind="handoff",
                text=None,
                reason="Published sources conflict on an owner-labelled topic; owner review required.",
            )
        if isinstance(candidate, PortfolioPhoto) and (
            self.attested is None or candidate.selection not in self.attested or self._reads != 1
        ):
            reason, candidate = "INVALID_OUTPUT", None
        # Skip the v5 result interpretation; its outcome DTO remains closed.
        from asm.ai.agent import ConversationAgent

        return ConversationAgent._outcome(self, reason=reason, candidate=candidate)
