"""Deterministic synthetic adapter. Its declarations certify only this fake protocol."""

import asyncio
from decimal import Decimal
from typing import Literal

from pydantic import Field

from asm.ai.contracts import (
    DTO,
    AdapterRequest,
    AdapterResponse,
    Capabilities,
    Cost,
    ReadTool,
    Route,
    ToolCall,
    Usage,
)
from asm.ai.gateway import ProviderFailure


class SyntheticReadArguments(DTO):
    query: Literal["current"]


class SyntheticReadResult(DTO):
    fact: str = Field(min_length=1, max_length=200, repr=False)


def synthetic_read_tool() -> ReadTool:
    return ReadTool(
        name="read_context",
        revision="synthetic_v1",
        description="Read synthetic fixture context; no DB authorization or access.",
        arguments=SyntheticReadArguments,
        result=SyntheticReadResult,
    )


Scenario = Literal[
    "reply",
    "tools",
    "handoff",
    "no_reply",
    "refusal",
    "invalid",
    "truncated",
    "oversize",
    "429",
    "5xx",
    "timeout",
    "unknown_cost",
]


class FakeAdapter:
    def __init__(self, route: Route, script: tuple[Scenario | AdapterResponse, ...] = ("reply",)):
        if route.execution != "FAKE" or route.adapter != "fake" or route.eligibility != "EVAL_ONLY":
            raise ValueError("FakeAdapter requires an explicit EVAL_ONLY fake route")
        self.capabilities = Capabilities(
            route=route,
            structured_output=True,
            read_tools=True,
            tools_with_structured_output=True,
            token_limits=True,
            deadline=True,
            bounded_output=True,
            schema_revisions=("conversation_result_v1",),
            max_input_tokens=131072,
            max_output_tokens=8192,
        )
        self.script = script
        self.requests: list[AdapterRequest] = []

    def count_input_tokens(self, request: AdapterRequest) -> int:
        # Synthetic byte tokenizer, not a claim about either EVAL_ONLY candidate.
        return len(request.input_json().encode("utf-8"))

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        index = len(self.requests)
        self.requests.append(request)
        if index >= len(self.script):
            raise ProviderFailure("UNAVAILABLE")
        scenario = self.script[index]
        if isinstance(scenario, AdapterResponse):
            return scenario
        if scenario == "429":
            raise ProviderFailure("RATE_LIMIT")
        if scenario == "5xx":
            raise ProviderFailure("UNAVAILABLE")
        if scenario == "timeout":
            # Wait for cancellation, with no long sleeps or external I/O.
            await asyncio.Event().wait()
        usage = Usage(input_tokens=self.count_input_tokens(request), output_tokens=100)
        cost = Cost(
            status="CONFIRMED", amount=Decimal("0.01"), currency=request.config.limits.currency
        )
        if scenario == "refusal":
            return AdapterResponse(kind="REFUSAL", usage=usage, cost=cost)
        if scenario == "truncated":
            return AdapterResponse(kind="TRUNCATED", usage=usage, cost=cost)
        if scenario == "tools":
            return AdapterResponse(
                kind="TOOLS",
                tool_calls=(
                    ToolCall(
                        call_id=f"read-{index + 1}",
                        name="read_context",
                        arguments_json='{"query":"current"}',
                    ),
                ),
                usage=usage,
                cost=cost,
            )
        output = '{"kind":"reply","text":"Уточните, какая услуга вас интересует.","reason":null}'
        if scenario == "handoff":
            output = '{"kind":"handoff","text":null,"reason":"Нужно решение владельца."}'
        if scenario == "no_reply":
            output = '{"kind":"no_reply","text":null,"reason":"Ответ не требуется."}'
        if scenario == "invalid":
            output = '{"kind":"reply","text":'
        if scenario == "oversize":
            output = '"' + "x" * 40000 + '"'
        if scenario == "unknown_cost":
            usage, cost = Usage(), Cost()
        return AdapterResponse(kind="OUTPUT", output_json=output, usage=usage, cost=cost)
