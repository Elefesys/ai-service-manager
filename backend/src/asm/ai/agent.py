"""One bounded ConversationAgent invocation, returning an effect-free candidate only."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol, Self

from pydantic import Field, model_validator

from asm.ai.context import ContextBinding, ContextBuilder, ContextCode, ContextFailure, ContextView
from asm.ai.contracts import (
    DTO,
    Budget,
    ConversationResult,
    Cost,
    ErrorCode,
    GatewayConfig,
    GatewayRequest,
    GatewayResult,
    ReadTool,
    ToolResult,
    Usage,
)
from asm.ai.gateway import ModelAdapter, ModelGateway

Boundary = Literal["MODEL", "READ", "FOLLOWUP", "CANDIDATE"]
StopCode = (
    ContextCode
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

    def __init__(
        self,
        config: GatewayConfig,
        adapter: ModelAdapter,
        authority: ContextAuthority,
        *,
        builder: ContextBuilder | None = None,
    ):
        self.config = GatewayConfig.model_validate(config)
        if (
            self.config.prompt_revision != "conversation_v2"
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

    async def _authorize(self, binding: ContextBinding, boundary: Boundary) -> None:
        self._time_left()
        try:
            decision = AuthorityDecision.model_validate(
                await self.authority.authorize(binding, boundary)
            )
        except asyncio.CancelledError:
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
                context = self.builder.build(snapshot, binding)
                binding = context.binding
                request = GatewayRequest(
                    run_id=run_id,
                    deadline=deadline,
                    messages=context.view.messages(),
                    tools=(current_context_tool(),) if self.config.limits.read_executions else (),
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
                    except Exception:
                        raise AuthorityFailure("AUTHORITY_UNAVAILABLE") from None
                    self._time_left()
                    if read.binding != binding:
                        raise AuthorityFailure("AUTHORITY_STALE")
                    refreshed = self.builder.build(read.snapshot, binding)
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
