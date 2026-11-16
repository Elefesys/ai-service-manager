"""Explicit v5 derived observations and published MY_WORK, never business authority."""

import hashlib
import json
import unicodedata
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, model_validator

from asm.ai.agent import (
    AnyAgentOutcome,
    AuthorityDecision,
    Boundary,
    ContextRead,
    ConversationAgent,
    CurrentContextArgs,
    StopCode,
)
from asm.ai.context import (
    ContextBinding,
    ContextBuilder,
    ContextFailure,
    ContextLimits,
    ContextView,
)
from asm.ai.contracts import (
    DTO,
    AnyConversationResult,
    AnyGatewayConfig,
    Budget,
    Handoff,
    Message,
    ReadTool,
)
from asm.ai.gateway import ModelAdapter
from asm.ai.knowledge import (
    KnowledgeFailure,
    KnowledgePin,
    KnowledgeView,
    SearchKnowledgeView,
    SearchPin,
    SearchProfile,
    SearchProjection,
    SearchRefs,
    project_search_knowledge,
    reduce_search_view,
)
from asm.ai.vision_contracts import PREPROCESS_PROFILE, VISION_PROFILE, VisionResult
from asm.billing.validation import LimitDecimal
from asm.configuration.models import ActiveProjection

if TYPE_CHECKING:
    from asm.ai.portfolio_delivery import PreparedPortfolioDeliveryContext

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PortfolioPin(DTO):
    projection_revision: Literal["portfolio_v1"]
    business_id: UUID
    release_id: UUID | None
    activation_version: LimitDecimal
    build_id: UUID | None
    profile_id: SearchProfile
    preprocessing: Literal["nfc_crlf_ascii_trim_v1"]
    visible_items_sha256: Digest

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            (self.activation_version == "0") != (self.release_id is None)
            or self.release_id is None
            and self.build_id is not None
        ):
            raise ValueError("PORTFOLIO_PIN_INVALID")
        return self


class MediaPin(DTO):
    projection_revision: Literal["current_image_v1"]
    business_id: UUID
    client_id: UUID
    conversation_id: UUID
    message_id: UUID | None
    message_version: LimitDecimal | None
    file_id: UUID | None
    file_version: LimitDecimal | None
    source_sha256: Digest | None
    availability: Literal["READY", "NO_IMAGE", "MEDIA_REPLACED_UNAVAILABLE", "UNAVAILABLE"]
    analysis_id: UUID | None
    analysis_sha256: Digest | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            (self.message_id is None) != (self.message_version is None)
            or (self.file_id is None) != (self.file_version is None)
            or (self.analysis_id is None) != (self.analysis_sha256 is None)
            or self.availability == "READY"
            and (self.file_id is None or self.message_id is None or self.source_sha256 is None)
            or self.availability == "NO_IMAGE"
            and (self.message_id is not None or self.file_id is not None)
            or self.analysis_id is not None
            and self.availability != "READY"
        ):
            raise ValueError("MEDIA_PIN_INVALID")
        return self

    def scope(self, binding: ContextBinding) -> bool:
        return (self.business_id, self.client_id, self.conversation_id) == (
            binding.business_id,
            binding.client_id,
            binding.conversation_id,
        )


class PortfolioReference(DTO):
    item_id: UUID
    revision_id: UUID
    asset_version_id: UUID
    source_sha256: Digest
    analysis_id: UUID | None
    rank: int = Field(ge=1, le=3)
    score: float = Field(ge=-1, le=2)
    reason_code: Literal["SEMANTIC", "KEYWORD", "STRUCTURED"]


class PortfolioMatch(PortfolioReference):
    text: str = Field(min_length=1, max_length=160, repr=False)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.text.encode("utf-8")) > 160:
            raise ValueError("PORTFOLIO_TEXT_LIMIT")
        return self

    def reference(self) -> PortfolioReference:
        return PortfolioReference.model_validate(self.model_dump(exclude={"text"}))


class _PortfolioResult(DTO):
    revision: Literal["portfolio_search_result_v1"]
    profile_id: SearchProfile
    query_sha256: Digest
    status: Literal["RESULTS", "EMPTY"]
    reason_code: Literal["NO_ACTIVE_BUILD", "NO_QUERY", "NO_ELIGIBLE_SOURCE", "NO_MATCHES"] | None

    def check(self, values: tuple[PortfolioReference, ...]) -> None:
        if (
            len({v.item_id for v in values}) != len(values)
            or [v.rank for v in values] != list(range(1, len(values) + 1))
            or (self.status == "RESULTS") != bool(values)
            or (self.status == "RESULTS") != (self.reason_code is None)
        ):
            raise ValueError("PORTFOLIO_RESULT_INVALID")


class PortfolioRefs(_PortfolioResult):
    references: tuple[PortfolioReference, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self.check(self.references)
        return self


class PortfolioProjection(_PortfolioResult):
    matches: tuple[PortfolioMatch, ...] = Field(max_length=3, repr=False)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self.check(tuple(v.reference() for v in self.matches))
        if len(self.model_dump_json().encode("utf-8")) > 2048:
            raise ValueError("PORTFOLIO_RESULT_LIMIT")
        return self

    def refs(self) -> PortfolioRefs:
        return PortfolioRefs.model_validate(
            self.model_dump(exclude={"matches"})
            | {"references": tuple(v.reference() for v in self.matches)}
        )


class RawVisionObservation(DTO):
    """Only returned by a trusted scoped DB capability, not by the model."""

    source_kind: Literal["CLIENT_REFERENCE"]
    asset_version_id: None
    vision_profile: Literal["polza_openai_gpt4omini_pixels_v1"]
    preprocessing: Literal["exif_contain_white_rgb_png256_strip_v1"]
    schema_revision: Literal["vision_result_v1"]
    state: Literal["SUCCESS"]
    applied: Literal[True]
    analysis_id: UUID
    analysis_sha256: Digest
    source_sha256: Digest
    derivative_sha256: Digest
    result: VisionResult = Field(repr=False)


class AnalysisView(DTO):
    revision: Literal["vision_observation_v1"] = "vision_observation_v1"
    status: Literal["ANALYSED", "UNAVAILABLE", "NO_IMAGE"]
    analysis_id: UUID | None
    source_sha256: Digest | None
    derivative_sha256: Digest | None
    vision_profile: Literal["polza_openai_gpt4omini_pixels_v1"] = VISION_PROFILE
    preprocessing: Literal["exif_contain_white_rgb_png256_strip_v1"] = PREPROCESS_PROFILE
    result: VisionResult | None = Field(repr=False)
    observations_omitted: bool

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (
            (self.status == "ANALYSED") != (self.result is not None)
            or (self.result is not None)
            != (
                self.analysis_id is not None
                and self.source_sha256 is not None
                and self.derivative_sha256 is not None
            )
            or len(self.model_dump_json().encode("utf-8")) > 1024
        ):
            raise ValueError("VISION_VIEW_INVALID")
        return self


def visible_analysis(raw: RawVisionObservation | None, pin: MediaPin) -> AnalysisView:
    if raw is None:
        if pin.analysis_id is not None:
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return AnalysisView(
            status="NO_IMAGE" if pin.availability == "NO_IMAGE" else "UNAVAILABLE",
            analysis_id=None,
            source_sha256=pin.source_sha256,
            derivative_sha256=None,
            result=None,
            observations_omitted=False,
        )
    if (raw.analysis_id, raw.analysis_sha256, raw.source_sha256) != (
        pin.analysis_id,
        pin.analysis_sha256,
        pin.source_sha256,
    ) or pin.availability != "READY":
        raise KnowledgeFailure("KNOWLEDGE_STALE")
    data = {
        "status": "ANALYSED",
        "analysis_id": raw.analysis_id,
        "source_sha256": raw.source_sha256,
        "derivative_sha256": raw.derivative_sha256,
        "vision_profile": VISION_PROFILE,
        "preprocessing": PREPROCESS_PROFILE,
        "result": raw.result,
        "observations_omitted": False,
    }
    # Drop complete observations. Keep the subject and at least one uncertainty;
    # never edit the saved analysis or claim the omitted details are unavailable.
    result = raw.result
    while True:
        wire = json.dumps(
            data
            | {
                "analysis_id": str(raw.analysis_id),
                "result": result.model_dump(mode="json"),
                "revision": "vision_observation_v1",
            },
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(wire.encode("utf-8")) <= 1024:
            return AnalysisView.model_validate(data | {"result": result})
        if result.details:
            result = VisionResult.model_validate(
                result.model_dump() | {"details": result.details[:-1]}
            )
        elif result.styles:
            result = VisionResult.model_validate(
                result.model_dump() | {"styles": result.styles[:-1]}
            )
        elif len(result.uncertainty) > 1:
            result = VisionResult.model_validate(
                result.model_dump() | {"uncertainty": result.uncertainty[:-1]}
            )
        else:
            raise KnowledgeFailure("KNOWLEDGE_TOO_LARGE")
        data["observations_omitted"] = True


class PortfolioKnowledgeView(DTO):
    revision: Literal["business_knowledge_v3"] = "business_knowledge_v3"
    configuration: KnowledgeView
    search: SearchProjection
    analysis: AnalysisView
    portfolio: PortfolioProjection
    fragments_omitted: int = Field(ge=0, le=3)
    matches_omitted: int = Field(ge=0, le=2)
    structured_rules_authoritative: Literal[True] = True


def reduce_portfolio_view(view: PortfolioKnowledgeView) -> PortfolioKnowledgeView | None:
    old = SearchKnowledgeView(
        configuration=view.configuration,
        search=view.search,
        fragments_omitted=view.fragments_omitted,
    )
    reduced = reduce_search_view(old)
    if reduced is not None:
        return PortfolioKnowledgeView.model_validate(
            view.model_dump()
            | {
                "configuration": reduced.configuration,
                "search": reduced.search,
                "fragments_omitted": reduced.fragments_omitted,
            }
        )
    if len(view.portfolio.matches) > 1:
        projection = PortfolioProjection.model_validate(
            view.portfolio.model_dump() | {"matches": view.portfolio.matches[:-1]}
        )
        return PortfolioKnowledgeView.model_validate(
            view.model_dump()
            | {"portfolio": projection, "matches_omitted": view.matches_omitted + 1}
        )
    return None


class PortfolioContextView(DTO):
    revision: Literal["conversation_context_v4"] = "conversation_context_v4"
    conversation: ContextView
    business: PortfolioKnowledgeView

    def messages(self) -> tuple[Message, ...]:
        context, current = self.conversation.messages()
        return context, Message(role="context", text=self.business.model_dump_json()), current


class PortfolioReadView(DTO):
    """A fresh READ attests the exact already supplied view without duplicating it."""

    revision: Literal["conversation_read_v4"] = "conversation_read_v4"
    same_context: Literal[True] = True
    context_sha256: Digest
    analysis_status: Literal["ANALYSED", "UNAVAILABLE", "NO_IMAGE"]
    portfolio_status: Literal["RESULTS", "EMPTY"]


class PreparedPortfolioContext(DTO):
    binding: ContextBinding = Field(repr=False)
    snapshot_fingerprint: Digest = Field(repr=False)
    view: PortfolioContextView = Field(repr=False)


class PortfolioContextBuilder:
    def __init__(self, limits: ContextLimits = ContextLimits()):
        self.limits = ContextLimits.model_validate(limits)
        if self.limits.max_bytes > 8192:
            raise ValueError("PORTFOLIO_CONTEXT_LIMIT")

    def build(
        self,
        value: object,
        binding: ContextBinding,
        pin: KnowledgePin,
        active: ActiveProjection,
        search_pin: SearchPin,
        search: SearchProjection,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
        portfolio: PortfolioProjection,
        analysis: AnalysisView,
        query: str,
    ) -> PreparedPortfolioContext:
        if (
            str(binding.workspace_id) != active.workspace_id
            or binding.business_id != pin.business_id
            or not media_pin.scope(binding)
            or (
                portfolio_pin.business_id,
                portfolio_pin.release_id,
                portfolio_pin.activation_version,
            )
            != (pin.business_id, pin.release_id, pin.activation_version)
            or (search.profile_id, search.query_sha256)
            != (portfolio.profile_id, portfolio.query_sha256)
            or portfolio_pin.profile_id != portfolio.profile_id
            or media_pin.analysis_id != analysis.analysis_id
        ):
            raise ContextFailure("CONTEXT_MISMATCH")
        canonical = unicodedata.normalize("NFC", query.replace("\r\n", "\n")).strip(" \t\n\r\f\v")
        if (
            query != canonical
            or len(query.encode("utf-8")) > 1024
            or hashlib.sha256(query.encode("utf-8")).hexdigest() != search.query_sha256
        ):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        old = project_search_knowledge(active, pin, search_pin, search, query)
        business = PortfolioKnowledgeView(
            configuration=old.configuration,
            search=old.search,
            analysis=analysis,
            portfolio=portfolio,
            fragments_omitted=old.fragments_omitted,
            matches_omitted=0,
        )
        base = ContextBuilder(self.limits).build(value, binding)
        conversation = base.view
        while True:
            view = PortfolioContextView(conversation=conversation, business=business)
            if (
                len(business.model_dump_json().encode("utf-8")) <= 6144
                and len(view.model_dump_json().encode("utf-8")) <= self.limits.max_bytes
            ):
                view.messages()
                return PreparedPortfolioContext(
                    binding=base.binding, snapshot_fingerprint=base.snapshot_fingerprint, view=view
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


class PortfolioAuthorityDecision(DTO):
    status: Literal["ALLOWED", "DENIED", "STALE"]
    binding: ContextBinding = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)
    search_pin: SearchPin = Field(repr=False)
    portfolio_pin: PortfolioPin = Field(repr=False)
    media_pin: MediaPin = Field(repr=False)


class PortfolioContextRead(DTO):
    binding: ContextBinding = Field(repr=False)
    snapshot: dict[str, Any] = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)
    active_projection: ActiveProjection = Field(repr=False)
    search_pin: SearchPin = Field(repr=False)
    search_refs: SearchRefs = Field(repr=False)
    search_projection: SearchProjection = Field(repr=False)
    portfolio_pin: PortfolioPin = Field(repr=False)
    media_pin: MediaPin = Field(repr=False)
    portfolio_refs: PortfolioRefs = Field(repr=False)
    portfolio_projection: PortfolioProjection = Field(repr=False)
    vision_analysis: RawVisionObservation | None = Field(repr=False)
    search_query: str = Field(repr=False, max_length=1024)


class PortfolioAuthority(Protocol):
    async def authorize(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
        boundary: Boundary,
    ) -> PortfolioAuthorityDecision: ...
    async def read_current(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
    ) -> PortfolioContextRead: ...


class _PinnedPortfolioAuthority:
    def __init__(
        self,
        inner: PortfolioAuthority,
        pin: KnowledgePin,
        active: ActiveProjection,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
        search: SearchProjection,
        portfolio: PortfolioProjection,
        vision: RawVisionObservation | None,
        query: str,
    ):
        self.inner, self.pin, self.active, self.search_pin = inner, pin, active, search_pin
        self.portfolio_pin, self.media_pin, self.search, self.portfolio = (
            portfolio_pin,
            media_pin,
            search,
            portfolio,
        )
        self.vision, self.query = vision, query

    async def authorize(self, binding: ContextBinding, boundary: Boundary) -> AuthorityDecision:
        decision = PortfolioAuthorityDecision.model_validate(
            await self.inner.authorize(
                binding, self.pin, self.search_pin, self.portfolio_pin, self.media_pin, boundary
            )
        )
        if (
            decision.knowledge_pin,
            decision.search_pin,
            decision.portfolio_pin,
            decision.media_pin,
        ) != (self.pin, self.search_pin, self.portfolio_pin, self.media_pin):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return AuthorityDecision(status=decision.status, binding=decision.binding)

    async def read_current(self, binding: ContextBinding) -> ContextRead:
        read = PortfolioContextRead.model_validate(
            await self.inner.read_current(
                binding, self.pin, self.search_pin, self.portfolio_pin, self.media_pin
            )
        )
        if (
            (
                read.knowledge_pin,
                read.active_projection,
                read.search_pin,
                read.portfolio_pin,
                read.media_pin,
                read.search_projection,
                read.portfolio_projection,
                read.vision_analysis,
                read.search_query,
            )
            != (
                self.pin,
                self.active,
                self.search_pin,
                self.portfolio_pin,
                self.media_pin,
                self.search,
                self.portfolio,
                self.vision,
                self.query,
            )
            or read.search_refs != self.search.refs()
            or read.portfolio_refs != self.portfolio.refs()
        ):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return ContextRead(binding=read.binding, snapshot=read.snapshot)


class PortfolioConversationAgent(ConversationAgent):
    prompt_revision = "conversation_v5"

    def __init__(
        self,
        config: AnyGatewayConfig,
        adapter: ModelAdapter,
        authority: PortfolioAuthority,
        *,
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
        initial_budget: Budget | None = None,
    ):
        self.pin, self.search_pin = knowledge_pin, search_pin
        self.active = ActiveProjection.model_validate_json(active_projection.model_dump_json())
        self.portfolio_pin, self.media_pin = portfolio_pin, media_pin
        self.search, self.portfolio = search_projection, portfolio_projection
        self.vision, self.query = vision_analysis, search_query
        self.analysis = visible_analysis(vision_analysis, media_pin)
        self.portfolio_builder = builder or PortfolioContextBuilder()
        super().__init__(
            config,
            adapter,
            _PinnedPortfolioAuthority(
                authority,
                self.pin,
                self.active,
                self.search_pin,
                self.portfolio_pin,
                self.media_pin,
                self.search,
                self.portfolio,
                self.vision,
                self.query,
            ),
            initial_budget=initial_budget,
        )

    def _project(
        self, snapshot: object, binding: ContextBinding
    ) -> "PreparedPortfolioContext | PreparedPortfolioDeliveryContext":
        return self.portfolio_builder.build(
            snapshot,
            binding,
            self.pin,
            self.active,
            self.search_pin,
            self.search,
            self.portfolio_pin,
            self.media_pin,
            self.portfolio,
            self.analysis,
            self.query,
        )

    def _tool(self) -> ReadTool:
        return ReadTool(
            name="read_context",
            revision="conversation_read_v4",
            description="Revalidate the exact supplied text, structured policy, derived observations and authorized portfolio. Return a fresh receipt for the same context; no new analysis, mutation or image send.",
            arguments=CurrentContextArgs,
            result=PortfolioReadView,
        )

    def _read_result(self, view: DTO) -> str:
        if not isinstance(view, PortfolioContextView):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return PortfolioReadView(
            context_sha256=hashlib.sha256(view.model_dump_json().encode("utf-8")).hexdigest(),
            analysis_status=view.business.analysis.status,
            portfolio_status=view.business.portfolio.status,
        ).model_dump_json()

    def _outcome(
        self, *, reason: StopCode | None = None, candidate: AnyConversationResult | None = None
    ) -> AnyAgentOutcome:
        if candidate is not None and self.search.status == "CONFLICT":
            candidate = Handoff(
                kind="handoff",
                text=None,
                reason="Published sources conflict on an owner-labelled topic; owner review required.",
            )
        return super()._outcome(reason=reason, candidate=candidate)
