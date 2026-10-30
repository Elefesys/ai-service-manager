"""Small, immutable contracts. Configuration and tool models belong to trusted code."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:/-]+$")]
Text = Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]
Reason = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]
JsonText = Annotated[str, Field(min_length=1, max_length=65536)]
Money = Annotated[Decimal, Field(ge=0, le=Decimal("1000000"), max_digits=18, decimal_places=9)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class DTO(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )


class Route(DTO):
    branch: Literal["RU_AGGREGATOR", "DIRECT_PROVIDER"]
    adapter: Identifier
    execution: Literal["FAKE", "PROVIDER"]
    endpoint: Annotated[str, Field(min_length=1, max_length=512, repr=False)]
    model: Identifier
    upstream: Identifier
    eligibility: Literal["EVAL_ONLY", "APPROVED"]

    @model_validator(mode="after")
    def endpoint_without_credentials(self) -> Self:
        try:
            url = urlsplit(self.endpoint)
            port = url.port
        except ValueError:
            raise ValueError("Invalid endpoint URL") from None
        if (
            url.scheme not in ("https", "http")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or (port is not None and port == 0)
            or any(c.isspace() or ord(c) < 32 for c in self.endpoint)
        ):
            raise ValueError("Endpoint must be an explicit URL without credentials or query")
        if self.execution == "FAKE" and (self.adapter != "fake" or self.eligibility != "EVAL_ONLY"):
            raise ValueError("Fake routes must remain explicitly EVAL_ONLY")
        return self


class Limits(DTO):
    model_calls: int = Field(ge=0, le=3)
    read_executions: int = Field(ge=0, le=4)
    input_bytes: int = Field(gt=0, le=131072)
    output_bytes: int = Field(gt=0, le=65536)
    input_tokens: int = Field(gt=0, le=131072)
    output_tokens: int = Field(gt=0, le=8192)
    total_tokens: int = Field(ge=0, le=417792)
    duration_seconds: float = Field(gt=0, le=120)
    currency: Currency
    cost_budget: Money
    call_cost_reservation: Money


class GatewayConfig(DTO):
    revision: Identifier
    route: Route
    prompt_revision: Literal["conversation_v1", "conversation_v2"]
    schema_revision: Literal["conversation_result_v1"]
    limits: Limits


class Message(DTO):
    # Context/owner facts are data, never caller-supplied platform policy.
    role: Literal["user", "assistant", "context"]
    text: Annotated[str, Field(min_length=1, max_length=16384, repr=False)]


class ReadTool(DTO):
    """Local Pydantic contracts supply both schemas and strict validators.

    Defining a tool grants no DB authority and executes nothing. The future runtime
    binds and authorizes reads. Only trusted application code supplies these types.
    """

    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
    revision: Identifier
    description: Reason
    arguments: type[DTO] = Field(repr=False)
    result: type[DTO] = Field(repr=False)
    effect: Literal["READ"] = "READ"

    @model_validator(mode="after")
    def strict_contracts(self) -> Self:
        for model in (self.arguments, self.result):
            if (
                model.model_config.get("strict") is not True
                or model.model_config.get("extra") != "forbid"
                or model.model_config.get("frozen") is not True
            ):
                raise ValueError("Read tool models must be strict, closed and frozen")
        return self


class GatewayRequest(DTO):
    run_id: Identifier
    deadline: datetime
    messages: tuple[Message, ...] = Field(min_length=1, max_length=64, repr=False)
    tools: tuple[ReadTool, ...] = Field(max_length=4)

    @model_validator(mode="after")
    def unique_tools_and_aware_deadline(self) -> Self:
        if self.deadline.tzinfo is None or self.deadline.utcoffset() is None:
            raise ValueError("Deadline must include a timezone")
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("Duplicate tool definition")
        return self


class Reply(DTO):
    kind: Literal["reply"]
    text: Text = Field(repr=False)
    reason: None


class Handoff(DTO):
    kind: Literal["handoff"]
    text: Text | None = Field(repr=False)
    reason: Reason = Field(repr=False)


class NoReply(DTO):
    kind: Literal["no_reply"]
    text: None
    reason: Reason = Field(repr=False)


ConversationResult = Reply | Handoff | NoReply
CONVERSATION_RESULT: TypeAdapter[ConversationResult] = TypeAdapter(ConversationResult)


class ToolCall(DTO):
    call_id: Identifier
    name: Identifier
    arguments_json: JsonText = Field(repr=False)


class ToolResult(DTO):
    call_id: Identifier
    name: Identifier
    result_json: JsonText = Field(repr=False)


class ToolExchange(DTO):
    calls: tuple[ToolCall, ...] = Field(min_length=1, max_length=4, repr=False)
    results: tuple[ToolResult, ...] = Field(min_length=1, max_length=4, repr=False)


class Usage(DTO):
    # Missing usage is not a measured zero; no refund is based on this value.
    input_tokens: int | None = Field(default=None, ge=0, le=10000000)
    output_tokens: int | None = Field(default=None, ge=0, le=10000000)


class Cost(DTO):
    status: Literal["CONFIRMED", "ESTIMATE", "UNKNOWN"] = "UNKNOWN"
    amount: Money | None = None
    currency: Currency | None = None

    @model_validator(mode="after")
    def amount_status(self) -> Self:
        if self.status == "UNKNOWN":
            if self.amount is not None:
                raise ValueError("Unknown cost cannot have an amount")
        elif self.amount is None or self.currency is None:
            raise ValueError("Known or estimated cost needs amount and currency")
        return self


class Budget(DTO):
    """Monotone reservations, not durable accounting or confirmed expenditure."""

    calls_used: int = Field(ge=0, le=3)
    reads_reserved: int = Field(ge=0, le=4)
    tokens_reserved: int = Field(ge=0, le=417792)
    cost_reserved: Money
    currency: Currency


class Capabilities(DTO):
    # Declarations are route-specific; None is unconfirmed, never permission.
    route: Route
    structured_output: bool | None = None
    read_tools: bool | None = None
    tools_with_structured_output: bool | None = None
    token_limits: bool | None = None
    deadline: bool | None = None
    bounded_output: bool | None = None
    schema_revisions: tuple[Identifier, ...] = ()
    max_input_tokens: int | None = Field(default=None, gt=0, le=131072)
    max_output_tokens: int | None = Field(default=None, gt=0, le=8192)


class AdapterRequest(DTO):
    config: GatewayConfig
    request: GatewayRequest = Field(repr=False)
    prompt: str = Field(min_length=1, max_length=16384, repr=False)
    output_schema_json: JsonText = Field(repr=False)
    exchanges: tuple[ToolExchange, ...] = Field(max_length=4, repr=False)
    budget: Budget
    remaining_seconds: float = Field(gt=0, le=120)

    def input_json(self) -> str:
        """Complete neutral input for size checks/local token counting, no secrets."""
        return json.dumps(
            {
                "prompt": self.prompt,
                "schema": strict_json(self.output_schema_json),
                "messages": [m.model_dump() for m in self.request.messages],
                "tools": [
                    {
                        "name": t.name,
                        "revision": t.revision,
                        "description": t.description,
                        "effect": t.effect,
                        "arguments": t.arguments.model_json_schema(),
                        "result": t.result.model_json_schema(),
                    }
                    for t in self.request.tools
                ],
                "exchanges": [x.model_dump() for x in self.exchanges],
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )


class AdapterResponse(DTO):
    kind: Literal["OUTPUT", "TOOLS", "REFUSAL", "TRUNCATED"]
    output_json: JsonText | None = Field(default=None, repr=False)
    tool_calls: tuple[ToolCall, ...] = Field(default=(), max_length=4, repr=False)
    usage: Usage = Usage()
    cost: Cost = Cost()

    @model_validator(mode="after")
    def exclusive_output(self) -> Self:
        if self.kind == "OUTPUT":
            valid = self.output_json is not None and not self.tool_calls
        elif self.kind == "TOOLS":
            valid = bool(self.tool_calls) and self.output_json is None
        else:
            valid = self.output_json is None and not self.tool_calls
        if not valid:
            raise ValueError("Inconsistent adapter response")
        return self


ErrorCode = Literal[
    "CLOSED",
    "BUSY",
    "DEADLINE",
    "BUDGET",
    "CAPABILITY",
    "ROUTE",
    "INPUT_SIZE",
    "INPUT_TOKENS",
    "INVALID_INPUT",
    "INVALID_OUTPUT",
    "OUTPUT_SIZE",
    "USAGE_LIMIT",
    "TOOL_CONTRACT",
    "TOOL_CORRELATION",
    "RATE_LIMIT",
    "UNAVAILABLE",
    "TIMEOUT",
    "ADAPTER_ERROR",
    "TRUNCATED",
]


class GatewayResult(DTO):
    kind: Literal["FINAL", "TOOLS", "REFUSAL", "ERROR"]
    result: ConversationResult | None = Field(default=None, repr=False)
    tool_calls: tuple[ToolCall, ...] = Field(default=(), max_length=4, repr=False)
    error: ErrorCode | None = None
    budget: Budget
    usage: Usage = Usage()
    cost: Cost = Cost()

    @model_validator(mode="after")
    def exclusive_result(self) -> Self:
        if self.kind == "FINAL":
            valid = self.result is not None and not self.tool_calls and self.error is None
        elif self.kind == "TOOLS":
            valid = bool(self.tool_calls) and self.result is None and self.error is None
        elif self.kind == "ERROR":
            valid = self.error is not None and self.result is None and not self.tool_calls
        else:
            valid = self.result is None and not self.tool_calls and self.error is None
        if not valid:
            raise ValueError("Inconsistent gateway result")
        return self


def strict_json(raw: str) -> Any:
    """Reject ambiguous duplicate keys, non-JSON numbers and invalid Unicode."""
    raw.encode("utf-8", "strict")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError("Invalid JSON constant")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
    return value
