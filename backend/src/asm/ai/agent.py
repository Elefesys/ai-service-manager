"""One bounded ConversationAgent invocation, returning an effect-free candidate only."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol, Self

from pydantic import Field, model_validator

from asm.ai.context import (
    ContextBinding,
    ContextBuilder,
    ContextCode,
    ContextFailure,
    ContextView,
    KnowledgeContextBuilder,
    KnowledgeContextView,
    PreparedContext,
    PreparedKnowledgeContext,
)
from asm.ai.contracts import (
    DTO,
    AnyGatewayConfig,
    Budget,
    ConversationResult,
    Cost,
    ErrorCode,
    GatewayRequest,
    GatewayResult,
    ReadTool,
    ToolResult,
    Usage,
    validate_gateway_config,
)
from asm.ai.gateway import ModelAdapter, ModelGateway
from asm.ai.knowledge import KnowledgeCode, KnowledgeFailure, KnowledgePin
from asm.configuration.models import ActiveProjection

Boundary = Literal["MODEL", "READ", "FOLLOWUP", "CANDIDATE"]
StopCode = (
    ContextCode
    | KnowledgeCode
    | ErrorCode
    | Literal[
        "AUTHORITY_DENIED", "AUTHORITY_STALE", "AUTHORITY_UNAVAILABLE", "REFUSAL", "CANCELLED"
    ]
)


class AuthorityDecision(DTO):
    status: Literal["ALLOWED", "DENIED", "STALE"]
    binding: ContextBinding = Field(repr=False)


class ContextRead(DTO):
    binding: ContextBinding = Field(repr=False)
    snapshot: dict[str, Any] = Field(repr=False)


class ContextAuthority(Protocol):
    """Mandatory trusted port; no production or default-allow implementation here.

    authorize must freshly check permissions, business/client/conversation scope,
    current AI admission (no HUMAN takeover/paused native policy), control/turn/input/
    native revisions, activation fence and Resume receipt against authoritative state.
    An ALLOWED decision asserts these checks, not UUID equality.
    The implementation owns its trusted principal/job claim separately; neither
    model arguments nor the supplied UUIDs establish that principal's authority.
    read_current must atomically authorize the same binding at its read boundary and
    return only that conversation's stored snapshot. No raw Telegram/media fetch.
    Calls share the agent deadline and must propagate cancellation. A future runtime
    must recheck durably at persistence/send; a candidate grants no lasting authority.
    """

    async def authorize(self, binding: ContextBinding, boundary: Boundary) -> AuthorityDecision: ...

    async def read_current(self, binding: ContextBinding) -> ContextRead: ...


class CurrentContextArgs(DTO):
    query: Literal["current"]


def current_context_tool() -> ReadTool:
    return ReadTool(
        name="read_context",
        revision="conversation_context_v1",
        description="Read the authorized current conversation text and coverage limits. No images or mutations.",
        arguments=CurrentContextArgs,
        result=ContextView,
    )


class CallObservation(DTO):
    kind: Literal["FINAL", "TOOLS", "REFUSAL", "ERROR"]
    error: ErrorCode | None
    usage: Usage
    cost: Cost


class AgentOutcome(DTO):
    status: Literal["CANDIDATE", "STOP"]
    candidate: ConversationResult | None = Field(default=None, repr=False)
    reason: StopCode | None = None
    budget: Budget
    reads_executed: int = Field(ge=0, le=1)
    calls: tuple[CallObservation, ...] = Field(max_length=2)
    runtime_authorized: Literal[False] = False

    @model_validator(mode="after")
    def exclusive(self) -> Self:
        if (
            self.status == "CANDIDATE"
            and (self.candidate is None or self.reason is not None)
            or self.status == "STOP"
            and (self.candidate is not None or self.reason is None)
        ):
            raise ValueError("Invalid agent outcome")
        return self


class AuthorityFailure(Exception):
    def __init__(self, code: StopCode):
        self.code = code
        super().__init__(code)


class ConversationAgent:
    """Single-use in-memory orchestration; no persistence, send, retry or runtime wiring."""

    prompt_revision = "conversation_v2"

    def __init__(
        self,
        config: AnyGatewayConfig,
        adapter: ModelAdapter,
        authority: ContextAuthority,
        *,
        builder: ContextBuilder | None = None,
    ):
        self.config = validate_gateway_config(config)
        if (
            self.config.prompt_revision != self.prompt_revision
            or self.config.route.eligibility != "EVAL_ONLY"
            or self.config.limits.model_calls > 2
            or self.config.limits.read_executions > 1
        ):
            raise ValueError("AGENT_CONFIG")
        self.adapter = adapter
        self.authority = authority
        self.builder = builder if builder is not None else ContextBuilder()
        self._used = False
        self._gateway: ModelGateway | None = None
        self._reads = 0
        self._calls: list[CallObservation] = []
        self._deadline = 0.0

    def _outcome(
        self, *, reason: StopCode | None = None, candidate: ConversationResult | None = None
    ) -> AgentOutcome:
        budget = (
            self._gateway.budget
            if self._gateway
            else Budget(
                calls_used=0,
                reads_reserved=0,
                tokens_reserved=0,
                cost_reserved=Decimal(0),
                currency=self.config.limits.currency,
            )
        )
        return AgentOutcome(
            status="STOP" if reason else "CANDIDATE",
            reason=reason,
            candidate=candidate,
            budget=budget,
            reads_executed=self._reads,
            calls=tuple(self._calls),
        )

    def _time_left(self) -> None:
        if time.monotonic() >= self._deadline:
            raise AuthorityFailure("DEADLINE")

    def _project(
        self, snapshot: object, binding: ContextBinding
    ) -> PreparedContext | PreparedKnowledgeContext:
        return self.builder.build(snapshot, binding)

    def _tool(self) -> ReadTool:
        return current_context_tool()

    async def _authorize(self, binding: ContextBinding, boundary: Boundary) -> None:
        self._time_left()
        try:
            decision = AuthorityDecision.model_validate(
                await self.authority.authorize(binding, boundary)
            )
        except asyncio.CancelledError:
            raise
        except KnowledgeFailure:
            raise
        except Exception:
            raise AuthorityFailure("AUTHORITY_UNAVAILABLE") from None
        self._time_left()
        if decision.status == "DENIED":
            raise AuthorityFailure("AUTHORITY_DENIED")
        if decision.status != "ALLOWED" or decision.binding != binding:
            raise AuthorityFailure("AUTHORITY_STALE")

    async def run(
        self, binding: ContextBinding, snapshot: object, *, run_id: str, deadline: datetime
    ) -> AgentOutcome:
        if self._used:
            return self._outcome(reason="CLOSED")
        self._used = True  # Before the first await; another caller cannot start a new Gateway.
        try:
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                return self._outcome(reason="INVALID_INPUT")
            deadline = min(
                deadline, datetime.now(UTC) + timedelta(seconds=self.config.limits.duration_seconds)
            )
            self._deadline = time.monotonic() + (deadline - datetime.now(UTC)).total_seconds()
            self._time_left()
            async with asyncio.timeout_at(self._deadline):
                context = self._project(snapshot, binding)
                binding = context.binding
                request = GatewayRequest(
                    run_id=run_id,
                    deadline=deadline,
                    messages=context.view.messages(),
                    tools=(self._tool(),) if self.config.limits.read_executions else (),
                )
                await self._authorize(binding, "MODEL")
                self._gateway = ModelGateway(self.config, request, self.adapter)
                result = await self._call()
                if result.kind == "TOOLS":
                    # The existing Gateway already validated allowlist, arguments and budget.
                    await self._authorize(binding, "READ")
                    self._reads += 1
                    try:
                        read = ContextRead.model_validate(
                            await self.authority.read_current(binding)
                        )
                    except asyncio.CancelledError:
                        raise
                    except KnowledgeFailure:
                        raise
                    except Exception:
                        raise AuthorityFailure("AUTHORITY_UNAVAILABLE") from None
                    self._time_left()
                    if read.binding != binding:
                        raise AuthorityFailure("AUTHORITY_STALE")
                    refreshed = self._project(read.snapshot, binding)
                    if refreshed.snapshot_fingerprint != context.snapshot_fingerprint:
                        raise AuthorityFailure("AUTHORITY_STALE")
                    call = result.tool_calls[0]
                    tool_result = ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        result_json=refreshed.view.model_dump_json(),
                    )
                    await self._authorize(binding, "FOLLOWUP")
                    result = await self._call((tool_result,))
                if result.kind == "FINAL":
                    await self._authorize(binding, "CANDIDATE")
                    return self._outcome(candidate=result.result)
                return self._outcome(
                    reason="REFUSAL" if result.kind == "REFUSAL" else result.error or "BUDGET"
                )
        except ContextFailure as exc:
            return self._outcome(reason=exc.code)
        except KnowledgeFailure as knowledge_error:
            return self._outcome(reason=knowledge_error.code)
        except AuthorityFailure as exc:
            return self._outcome(reason=exc.code)
        except TimeoutError:
            return self._outcome(reason="DEADLINE")
        except asyncio.CancelledError:
            # Terminal locally, with reservations retained; no durable recovery claim.
            return self._outcome(reason="CANCELLED")
        except (ValueError, TypeError, AttributeError):
            return self._outcome(reason="INVALID_INPUT")

    async def _call(self, results: tuple[ToolResult, ...] = ()) -> GatewayResult:
        self._time_left()
        assert self._gateway is not None
        result = await self._gateway.call(results)
        self._calls.append(
            CallObservation(
                kind=result.kind, error=result.error, usage=result.usage, cost=result.cost
            )
        )
        return result


class KnowledgeAuthorityDecision(DTO):
    status: Literal["ALLOWED", "DENIED", "STALE"]
    binding: ContextBinding = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)


class KnowledgeContextRead(DTO):
    binding: ContextBinding = Field(repr=False)
    knowledge_pin: KnowledgePin = Field(repr=False)
    active_projection: ActiveProjection = Field(repr=False)
    snapshot: dict[str, Any] = Field(repr=False)


class KnowledgeAuthority(Protocol):
    """V2 port: all original authority checks AND the immutable publication pin.

    The implementation owns the principal/job claim. Authorize/read must serialize
    freshness with publication; a matching DTO alone never grants permission.
    No switch to a newer release is permitted within this invocation.
    """

    async def authorize(
        self, binding: ContextBinding, knowledge_pin: KnowledgePin, boundary: Boundary
    ) -> KnowledgeAuthorityDecision: ...

    async def read_current(
        self, binding: ContextBinding, knowledge_pin: KnowledgePin
    ) -> KnowledgeContextRead: ...


class _PinnedAuthority:
    """Adapt the new mandatory port to the shared finite orchestration, never default allow."""

    def __init__(
        self, inner: KnowledgeAuthority, pin: KnowledgePin, active: ActiveProjection
    ) -> None:
        self.inner, self.pin, self.active = inner, pin, active

    async def authorize(self, binding: ContextBinding, boundary: Boundary) -> AuthorityDecision:
        decision = KnowledgeAuthorityDecision.model_validate(
            await self.inner.authorize(binding, self.pin, boundary)
        )
        if decision.knowledge_pin != self.pin:
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return AuthorityDecision(status=decision.status, binding=decision.binding)

    async def read_current(self, binding: ContextBinding) -> ContextRead:
        read = KnowledgeContextRead.model_validate(await self.inner.read_current(binding, self.pin))
        if read.knowledge_pin != self.pin or read.active_projection != self.active:
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        return ContextRead(binding=read.binding, snapshot=read.snapshot)


class KnowledgeConversationAgent(ConversationAgent):
    """Explicit v3 path sharing the same single-use loop, deadline, limits and Gateway."""

    prompt_revision = "conversation_v3"

    def __init__(
        self,
        config: AnyGatewayConfig,
        adapter: ModelAdapter,
        authority: KnowledgeAuthority,
        *,
        knowledge_pin: KnowledgePin,
        active_projection: ActiveProjection,
        builder: KnowledgeContextBuilder | None = None,
    ):
        self.knowledge_pin = KnowledgePin.model_validate(knowledge_pin)
        # Configuration DTOs contain lists. Copy the saved value so caller mutation
        # cannot silently replace facts during an awaited model call.
        self.active_projection = ActiveProjection.model_validate_json(
            active_projection.model_dump_json()
        )
        self.knowledge_builder = builder if builder is not None else KnowledgeContextBuilder()
        super().__init__(
            config,
            adapter,
            _PinnedAuthority(authority, self.knowledge_pin, self.active_projection),
        )

    def _project(self, snapshot: object, binding: ContextBinding) -> PreparedKnowledgeContext:
        return self.knowledge_builder.build(
            snapshot, binding, self.knowledge_pin, self.active_projection
        )

    def _tool(self) -> ReadTool:
        return ReadTool(
            name="read_context",
            revision="conversation_context_v2",
            description="Read the pinned current conversation and owner-published business facts. No images or mutations.",
            arguments=CurrentContextArgs,
            result=KnowledgeContextView,
        )
