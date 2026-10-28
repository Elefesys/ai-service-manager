"""One explicit call at a time, with in-memory budget continuity and no tool execution."""

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from typing import Protocol

from asm.ai.contracts import (
    CONVERSATION_RESULT,
    AdapterRequest,
    AdapterResponse,
    Budget,
    Capabilities,
    Cost,
    ErrorCode,
    GatewayConfig,
    GatewayRequest,
    GatewayResult,
    ToolCall,
    ToolExchange,
    ToolResult,
    Usage,
    strict_json,
)


class ProviderFailure(Exception):
    """Adapters translate provider failures to these public, content-free codes."""

    def __init__(self, code: str) -> None:
        codes: dict[str, ErrorCode] = {
            "RATE_LIMIT": "RATE_LIMIT",
            "UNAVAILABLE": "UNAVAILABLE",
            "TIMEOUT": "TIMEOUT",
        }
        self.code = codes.get(code, "ADAPTER_ERROR")
        super().__init__(self.code)


class ModelAdapter(Protocol):
    @property
    def capabilities(self) -> Capabilities: ...

    def count_input_tokens(self, request: AdapterRequest) -> int | None:
        """Local, side-effect-free count/verified upper bound including protocol overhead.

        Return None when unconfirmed. Fake byte counting proves no real tokenizer.
        """
        ...

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        """Exactly one attempt; honor pinned route and limits, no SDK retries/fallback.

        Secrets stay inside the adapter. Bound wire reads, propagate cancellation,
        and never log raw responses/requests or emit chain-of-thought.
        """
        ...


class ModelGateway:
    """A single logical request, pinned to one config, adapter and absolute deadline.

    call() returns FINAL/REFUSAL/ERROR, or TOOLS. Only TOOLS permits a further call,
    with exactly the correlated, locally validated results. No agent loop, read
    executor, durable AIRun, authorization or send is provided here. A trusted
    future runtime must persist reservations before external effects; constructing
    another instance is not a retry/durable-budget mechanism.
    """

    def __init__(
        self, config: GatewayConfig, request: GatewayRequest, adapter: ModelAdapter
    ) -> None:
        self._config = GatewayConfig.model_validate(config)
        self._request = GatewayRequest.model_validate(request)
        self._adapter = adapter
        self._deadline = time.monotonic() + min(
            config.limits.duration_seconds,
            (request.deadline - datetime.now(UTC)).total_seconds(),
        )
        self._budget = Budget(
            calls_used=0,
            reads_reserved=0,
            tokens_reserved=0,
            cost_reserved=Decimal(0),
            currency=config.limits.currency,
        )
        self._pending: tuple[ToolCall, ...] = ()
        self._exchanges: tuple[ToolExchange, ...] = ()
        self._seen: set[str] = set()
        self._closed = False
        self._busy = False
        self._prompt = files("asm.ai").joinpath("prompts/conversation_v1.txt").read_text("utf-8")
        self._schema = (
            files("asm.ai").joinpath("schemas/conversation_result_v1.json").read_text("utf-8")
        )
        if strict_json(self._schema) != CONVERSATION_RESULT.json_schema():
            raise ValueError("Conversation schema drift")

    @property
    def budget(self) -> Budget:
        return self._budget

    def _error(self, code: ErrorCode, usage: Usage = Usage(), cost: Cost = Cost()) -> GatewayResult:
        self._closed = True
        return GatewayResult(kind="ERROR", error=code, budget=self._budget, usage=usage, cost=cost)

    def _remaining_seconds(self) -> float:
        return min(
            self._deadline - time.monotonic(),
            (self._request.deadline - datetime.now(UTC)).total_seconds(),
        )

    def _capability_error(self) -> ErrorCode | None:
        caps = Capabilities.model_validate(self._adapter.capabilities)
        limits = self._config.limits
        if caps.route != self._config.route:
            return "ROUTE"
        if (
            caps.structured_output is not True
            or caps.token_limits is not True
            or caps.deadline is not True
            or caps.bounded_output is not True
            or (self._request.tools and caps.read_tools is not True)
            or (self._request.tools and caps.tools_with_structured_output is not True)
            or self._config.schema_revision not in caps.schema_revisions
            or caps.max_input_tokens is None
            or limits.input_tokens > caps.max_input_tokens
            or caps.max_output_tokens is None
            or limits.output_tokens > caps.max_output_tokens
        ):
            return "CAPABILITY"
        return None

    def _accept_results(self, results: tuple[ToolResult, ...]) -> ErrorCode | None:
        expected = {(c.call_id, c.name) for c in self._pending}
        if (
            type(results) is not tuple
            or len(results) != len(expected)
            or {(r.call_id, r.name) for r in results} != expected
        ):
            return "TOOL_CORRELATION"
        tools = {t.name: t for t in self._request.tools}
        for result in results:
            result = ToolResult.model_validate(result)
            if len(result.result_json.encode("utf-8")) > self._config.limits.input_bytes:
                return "INPUT_SIZE"
            strict_json(result.result_json)
            tools[result.name].result.model_validate_json(result.result_json)
        if self._pending:
            self._exchanges += (ToolExchange(calls=self._pending, results=results),)
            self._pending = ()
        return None

    async def call(self, tool_results: tuple[ToolResult, ...] = ()) -> GatewayResult:
        if self._busy:
            return GatewayResult(kind="ERROR", error="BUSY", budget=self._budget)
        if self._closed:
            return self._error("CLOSED")
        self._busy = True
        try:
            return await self._call(tool_results)
        except asyncio.CancelledError:
            self._closed = True
            raise
        finally:
            self._busy = False

    async def _call(self, tool_results: tuple[ToolResult, ...]) -> GatewayResult:
        limits = self._config.limits
        if self._remaining_seconds() <= 0:
            return self._error("DEADLINE")
        if (
            self._budget.calls_used >= limits.model_calls
            or (self._request.tools and limits.read_executions == 0)
            or self._budget.tokens_reserved >= limits.total_tokens
            or limits.call_cost_reservation <= 0
            or self._budget.cost_reserved + limits.call_cost_reservation > limits.cost_budget
        ):
            return self._error("BUDGET")
        try:
            code = self._capability_error()
        except Exception:
            return self._error("CAPABILITY")
        if code:
            return self._error(code)
        try:
            code = self._accept_results(tool_results)
        except Exception:
            return self._error("TOOL_CONTRACT")
        if code:
            return self._error(code)
        try:
            remaining = self._remaining_seconds()
            if remaining <= 0:
                return self._error("DEADLINE")
            request = AdapterRequest(
                config=self._config,
                request=self._request,
                prompt=self._prompt,
                output_schema_json=self._schema,
                exchanges=self._exchanges,
                budget=self._budget,
                remaining_seconds=remaining,
            )
            if len(request.input_json().encode("utf-8")) > limits.input_bytes:
                return self._error("INPUT_SIZE")
            tokens = self._adapter.count_input_tokens(request)
            if tokens is None:
                return self._error("CAPABILITY")
            if type(tokens) is not int or tokens < 0:
                return self._error("INVALID_INPUT")
            if tokens > limits.input_tokens:
                return self._error("INPUT_TOKENS")
        except Exception:
            return self._error("INVALID_INPUT")
        reserved_tokens = tokens + limits.output_tokens
        if self._budget.tokens_reserved + reserved_tokens > limits.total_tokens:
            return self._error("BUDGET")
        # Charge before awaiting, including timeout, cancellation and unknown usage.
        self._budget = Budget(
            calls_used=self._budget.calls_used + 1,
            reads_reserved=self._budget.reads_reserved,
            tokens_reserved=self._budget.tokens_reserved + reserved_tokens,
            cost_reserved=self._budget.cost_reserved + limits.call_cost_reservation,
            currency=limits.currency,
        )
        remaining = self._remaining_seconds()
        if remaining <= 0:
            return self._error("DEADLINE")
        try:
            # Send the charged budget and freshly computed remainder, never a new run.
            request = AdapterRequest(
                **(
                    request.model_dump()
                    | {
                        "budget": self._budget,
                        "remaining_seconds": remaining,
                    }
                )
            )
            async with asyncio.timeout(remaining):
                raw = await self._adapter.complete(request)
            if self._remaining_seconds() <= 0:
                return self._error("TIMEOUT")
        except TimeoutError:
            return self._error("TIMEOUT")
        except ProviderFailure as exc:
            return self._error(exc.code)
        except Exception:
            return self._error("ADAPTER_ERROR")
        usage, cost = Usage(), Cost()
        try:
            response = AdapterResponse.model_validate(raw)
            usage, cost = response.usage, response.cost
            if len(response.model_dump_json().encode("utf-8")) > limits.output_bytes:
                return self._error("OUTPUT_SIZE", response.usage, response.cost)
            if (usage.input_tokens is not None and usage.input_tokens > tokens) or (
                usage.output_tokens is not None and usage.output_tokens > limits.output_tokens
            ):
                return self._error("USAGE_LIMIT", usage, cost)
            if cost.currency is not None and cost.currency != limits.currency:
                return self._error("INVALID_OUTPUT", usage, cost)
            if cost.amount is not None and cost.amount > limits.call_cost_reservation:
                return self._error("BUDGET", usage, cost)
            if response.kind == "TRUNCATED":
                return self._error("TRUNCATED", usage, cost)
            if response.kind == "REFUSAL":
                self._closed = True
                return GatewayResult(kind="REFUSAL", budget=self._budget, usage=usage, cost=cost)
            if response.kind == "TOOLS":
                return self._tools(response)
            result = CONVERSATION_RESULT.validate_python(strict_json(response.output_json or ""))
            self._closed = True
            return GatewayResult(
                kind="FINAL", result=result, budget=self._budget, usage=usage, cost=cost
            )
        except Exception:
            return self._error("INVALID_OUTPUT", usage, cost)

    def _tools(self, response: AdapterResponse) -> GatewayResult:
        calls = response.tool_calls
        tools = {t.name: t for t in self._request.tools}
        limits = self._config.limits
        if self._budget.reads_reserved + len(calls) > limits.read_executions:
            return self._error("BUDGET", response.usage, response.cost)
        if (
            self._budget.calls_used >= limits.model_calls
            or self._budget.cost_reserved + limits.call_cost_reservation > limits.cost_budget
            or self._budget.tokens_reserved + limits.output_tokens >= limits.total_tokens
        ):
            return self._error("BUDGET", response.usage, response.cost)
        ids = {c.call_id for c in calls}
        if len(ids) != len(calls) or ids & self._seen:
            return self._error("TOOL_CORRELATION", response.usage, response.cost)
        for call in calls:
            if call.name not in tools:
                return self._error("TOOL_CONTRACT", response.usage, response.cost)
            try:
                strict_json(call.arguments_json)
                tools[call.name].arguments.model_validate_json(call.arguments_json)
            except Exception:
                return self._error("TOOL_CONTRACT", response.usage, response.cost)
        self._pending = calls
        self._seen.update(ids)
        self._budget = Budget(
            **(
                self._budget.model_dump()
                | {
                    "reads_reserved": self._budget.reads_reserved + len(calls),
                }
            )
        )
        return GatewayResult(
            kind="TOOLS",
            tool_calls=calls,
            budget=self._budget,
            usage=response.usage,
            cost=response.cost,
        )
