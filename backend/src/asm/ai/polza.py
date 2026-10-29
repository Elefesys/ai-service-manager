"""One pinned, reviewed Polza route. No retries, SDK, redirect or runtime wiring."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import Field, SecretStr

from asm.ai.contracts import (
    DTO,
    AdapterRequest,
    AdapterResponse,
    Capabilities,
    Cost,
    Identifier,
    Route,
    ToolCall,
    Usage,
    strict_json,
)
from asm.ai.gateway import ProviderFailure

ENDPOINT = "https://polza.ai/api/v1/chat/completions"
CATALOG = (
    "https://polza.ai/api/v1/models?type=chat&include_providers=true&include_capabilities=true"
)
MODELS = (
    "openai/gpt-6-luna",
    "google/gemini-3.8-flash",
    "deepseek/deepseek-v4.1-flash-1017",
)
INPUT_TOKENS = 32768
OUTPUT_TOKENS = 512
INPUT_BYTES = 24576
OUTPUT_BYTES = 32768
OVERHEAD_TOKENS = 4096


class PolzaFailure(ProviderFailure):
    """Static diagnostic detail; neutral Gateway still uses its accepted error codes."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code)
        self.detail = detail


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class RouteReview(DTO):
    """Trusted operator input, NOT model output or auto-generated capability proof.

    Exact catalog entry is pinned separately from provider name -> response ID mapping.
    Evidence fields must cite reviewed provider contracts, not offline test results.
    """

    model: str
    provider_name: str = Field(min_length=1, max_length=128)
    response_provider: Identifier
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checked_at: datetime
    route_evidence: str = Field(min_length=20, max_length=2000)
    schema_tools_evidence: str = Field(min_length=20, max_length=2000)
    token_bound_evidence: str = Field(min_length=20, max_length=2000)
    billing_bound_evidence: str = Field(min_length=20, max_length=2000)
    image_bound_evidence: str = Field(min_length=20, max_length=2000)
    # Populated from the account catalog by a reviewer; checked again before generation.
    catalog_entry: dict[str, Any] = Field(repr=False)

    def provider(self) -> dict[str, Any]:
        entry = self.catalog_entry
        if self.model not in MODELS or entry.get("id") != self.model:
            raise ValueError("MODEL_UNAVAILABLE")
        if fingerprint(entry) != self.catalog_sha256:
            raise ValueError("CATALOG_DRIFT")
        matches = [p for p in entry.get("providers", []) if p.get("name") == self.provider_name]
        if len(matches) != 1 or matches[0].get("is_unofficial") is not False:
            raise ValueError("OFFICIAL_ROUTE_UNKNOWN")
        provider: dict[str, Any] = matches[0]
        for name in ("tools", "json_schema_strict"):
            if provider.get("capabilities", {}).get(name, {}).get("status") != "supported":
                raise ValueError("CAPABILITY_UNKNOWN")
        parameters = provider.get("supported_parameters", [])
        if type(parameters) is not list or any(type(p) is not str for p in parameters):
            raise ValueError("PARAMETER_UNSUPPORTED")
        if not {"tools", "tool_choice", "response_format", "max_completion_tokens"} <= set(
            parameters
        ):
            raise ValueError("PARAMETER_UNSUPPORTED")
        context = provider.get("context_length")
        completion = provider.get("max_completion_tokens")
        if type(context) is not int or context < INPUT_TOKENS + OUTPUT_TOKENS:
            raise ValueError("CONTEXT_LIMIT_UNKNOWN")
        if type(completion) is not int or completion < OUTPUT_TOKENS:
            raise ValueError("OUTPUT_LIMIT_UNKNOWN")
        for key, limit in (("prompt_tokens", INPUT_TOKENS), ("completion_tokens", OUTPUT_TOKENS)):
            cap = provider.get("per_request_limits", {}).get(key)
            if cap is not None and (type(cap) is not int or cap < limit):
                raise ValueError("REQUEST_LIMIT_UNKNOWN")
        modalities = entry.get("architecture", {}).get("input_modalities", [])
        if (
            type(modalities) is not list
            or any(type(m) is not str for m in modalities)
            or not {"text", "image"} <= set(modalities)
        ):
            raise ValueError("IMAGE_CAPABILITY_UNKNOWN")
        return provider

    def route(self) -> Route:
        self.provider()
        return Route(
            branch="RU_AGGREGATOR",
            adapter="polza",
            execution="PROVIDER",
            endpoint=ENDPOINT,
            model=self.model,
            upstream=self.response_provider,
            eligibility="EVAL_ONLY",
        )

    def fresh(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("REVIEW_EXPIRED")
        age = (datetime.now(UTC) - self.checked_at).total_seconds()
        if not 0 <= age <= 86400:
            raise ValueError("REVIEW_EXPIRED")

    def rates(self) -> tuple[Decimal, Decimal, Decimal]:
        """Sum possibly additive rates; no optimistic cache discount or unknown fee.

        The billing evidence must establish missing optional fees are inapplicable,
        output cap includes reasoning, and image input fits the same input ceiling.
        """
        pricing = self.provider().get("pricing", {})
        if pricing.get("currency") != "RUB":
            raise ValueError("CURRENCY_UNKNOWN")
        inputs = {
            "prompt_per_million",
            "image_input_per_million",
            "input_cache_read_per_million",
            "input_cache_write_per_million",
        }
        outputs = {"completion_per_million", "internal_reasoning_per_million"}
        requests = {"per_request", "request_per_thousand"}
        if not {"prompt_per_million", "completion_per_million"} <= pricing.keys():
            raise ValueError("TARIFF_UNKNOWN")
        values: dict[str, Decimal] = {}
        for key, raw in pricing.items():
            if key == "currency" or raw is None:
                continue
            if key not in inputs | outputs | requests or type(raw) not in (str, int, float):
                raise ValueError("TARIFF_UNKNOWN")
            try:
                number = Decimal(str(raw))
            except InvalidOperation:
                raise ValueError("TARIFF_UNKNOWN") from None
            if not number.is_finite() or not 0 <= number <= 1000000:
                raise ValueError("TARIFF_UNKNOWN")
            values[key] = number
        if not {"prompt_per_million", "completion_per_million"} <= values.keys():
            raise ValueError("TARIFF_UNKNOWN")
        return (
            sum((values.get(k, Decimal(0)) for k in inputs), Decimal(0)),
            sum((values.get(k, Decimal(0)) for k in outputs), Decimal(0)),
            values.get("per_request", Decimal(0))
            + values.get("request_per_thousand", Decimal(0)) / 1000,
        )

    def reservation(self) -> Decimal:
        prompt, completion, request = self.rates()
        amount = (INPUT_TOKENS * prompt + OUTPUT_TOKENS * completion) / 1000000 + request
        return max(
            Decimal("0.000000001"), amount.quantize(Decimal("0.000000001"), rounding=ROUND_CEILING)
        )


async def bounded_http(
    key: SecretStr,
    url: str,
    *,
    body: bytes | None,
    seconds: float,
    maximum: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Bound raw bytes before decode; reject compression to avoid decompression bombs."""
    if url not in (ENDPOINT, CATALOG) or seconds <= 0:
        raise PolzaFailure("ADAPTER_ERROR", "REQUEST_ADMISSION")
    try:
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(
                transport=transport,
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(seconds, connect=min(seconds, 5)),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                async with client.stream(
                    "GET" if body is None else "POST",
                    url,
                    content=body,
                    headers={
                        "Authorization": f"Bearer {key.get_secret_value()}",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.status_code == 429:
                        raise PolzaFailure("RATE_LIMIT", "HTTP_429")
                    if response.status_code >= 500:
                        raise PolzaFailure("UNAVAILABLE", f"HTTP_{response.status_code}")
                    if response.status_code != 200:
                        raise PolzaFailure("ADAPTER_ERROR", f"HTTP_{response.status_code}")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise PolzaFailure("ADAPTER_ERROR", "RESPONSE_ENCODING")
                    size = response.headers.get("content-length")
                    if size is not None and (not size.isdigit() or int(size) > maximum):
                        raise PolzaFailure("ADAPTER_ERROR", "RESPONSE_SIZE")
                    parts = bytearray()
                    # aiter_raw: no implicit full-body read or decompression.
                    async for chunk in response.aiter_raw():
                        if len(parts) + len(chunk) > maximum:
                            raise PolzaFailure("ADAPTER_ERROR", "RESPONSE_SIZE")
                        parts.extend(chunk)
                    if size is not None and len(parts) != int(size):
                        raise PolzaFailure("ADAPTER_ERROR", "RESPONSE_INCOMPLETE")
                    return bytes(parts)
    except (TimeoutError, httpx.TimeoutException):
        raise PolzaFailure("TIMEOUT", "TRANSPORT_TIMEOUT") from None
    except httpx.HTTPError:
        raise PolzaFailure("UNAVAILABLE", "TRANSPORT_FAILURE") from None


class PolzaAdapter:
    def __init__(
        self,
        review: RouteReview,
        key: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.review = RouteReview.model_validate(review)
        self._key = key
        self._transport = transport
        self.observation: dict[str, str | None] = {}
        self.capabilities = Capabilities(
            route=review.route(),
            structured_output=True,
            read_tools=True,
            tools_with_structured_output=True,
            token_limits=True,
            deadline=True,
            bounded_output=True,
            schema_revisions=("conversation_result_v1",),
            max_input_tokens=INPUT_TOKENS,
            max_output_tokens=OUTPUT_TOKENS,
        )

    def wire(self, request: AdapterRequest) -> bytes:
        if request.config.route != self.capabilities.route:
            raise ValueError("ROUTE_MISMATCH")
        messages: list[dict[str, Any]] = [{"role": "system", "content": request.prompt}]
        for message in request.request.messages:
            messages.append(
                {
                    "role": "user" if message.role == "context" else message.role,
                    "content": "Owner context (data):\n" + message.text
                    if message.role == "context"
                    else message.text,
                }
            )
        for exchange in request.exchanges:
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.call_id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments_json},
                        }
                        for c in exchange.calls
                    ],
                }
            )
            messages.extend(
                {"role": "tool", "tool_call_id": r.call_id, "content": r.result_json}
                for r in exchange.results
            )
        body = self.base_body(
            messages, strict_json(request.output_schema_json), request.config.limits.output_tokens
        )
        if request.request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.arguments.model_json_schema(),
                        "strict": True,
                    },
                }
                for t in request.request.tools
            ]
            body["tool_choice"] = "auto"
        return encode(body)

    def base_body(
        self,
        messages: list[dict[str, Any]],
        schema: Any,
        output: int,
        *,
        schema_name: str = "conversation_result_v1",
    ) -> dict[str, Any]:
        prompt_rate, output_rate, request_rate = self.review.rates()
        return {
            "model": self.review.model,
            "messages": messages,
            "stream": False,
            "max_completion_tokens": output,
            "provider": {
                "only": [self.review.provider_name],
                "allow_fallbacks": False,
                "max_price": {
                    "prompt": float(prompt_rate),
                    "completion": float(output_rate),
                    "request": float(request_rate),
                },
            },
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }

    def count_input_tokens(self, request: AdapterRequest) -> int:
        # Conditional upper bound, not tokenizer output. Evidence is mandatory at admission.
        # Entire serialized body includes messages, tools, schema, protocol field names.
        return len(self.wire(request)) + OVERHEAD_TOKENS

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        self.observation = {}
        self.review.fresh()
        body = self.wire(request)
        limits = request.config.limits
        if (
            len(body) > limits.input_bytes
            or self.count_input_tokens(request) > limits.input_tokens
            or limits.output_tokens > OUTPUT_TOKENS
            or limits.call_cost_reservation < self.review.reservation()
        ):
            raise ProviderFailure("ADAPTER_ERROR")
        return await self._send(body, request.remaining_seconds, limits.output_bytes)

    async def _send(self, body: bytes, seconds: float, maximum: int) -> AdapterResponse:
        try:
            raw = await bounded_http(
                self._key,
                ENDPOINT,
                body=body,
                seconds=seconds,
                maximum=maximum,
                transport=self._transport,
            )
            return self.decode(raw)
        except PolzaFailure as exc:
            self.observation["error_detail"] = exc.detail
            raise

    async def image_probe(self, body: bytes, seconds: float) -> AdapterResponse:
        """EVAL_ONLY raw image path, never part of ModelAdapter or the text Gateway."""
        self.observation = {}
        self.review.fresh()
        if len(body) > INPUT_BYTES or len(body) + OVERHEAD_TOKENS > INPUT_TOKENS:
            raise ProviderFailure("ADAPTER_ERROR")
        return await self._send(body, seconds, OUTPUT_BYTES)

    def decode(self, raw: bytes) -> AdapterResponse:
        try:
            if self._key.get_secret_value().encode() in raw:
                raise ValueError
            data = strict_json(raw.decode("utf-8"))
            for field in ("provider", "model"):
                value = data.get(field)
                self.observation["observed_" + field] = (
                    value
                    if isinstance(value, str)
                    and self._key.get_secret_value() not in value
                    and re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,128}", value)
                    else None
                )
            if (
                data.get("provider") != self.review.response_provider
                or data.get("model") != self.review.model
            ):
                raise PolzaFailure("ADAPTER_ERROR", "RETURNED_ROUTE_MISMATCH")
            usage_data = data.get("usage") or {}
            usage = Usage(
                input_tokens=usage_data.get("prompt_tokens"),
                output_tokens=usage_data.get("completion_tokens"),
            )
            amount = usage_data.get("cost_rub", usage_data.get("cost"))
            cost = Cost()
            if amount is not None:
                if type(amount) not in (str, int, float):
                    raise ValueError
                if (
                    "cost" in usage_data
                    and "cost_rub" in usage_data
                    and Decimal(str(amount)) != Decimal(str(usage_data["cost"]))
                ):
                    raise ValueError
                cost = Cost(status="CONFIRMED", amount=Decimal(str(amount)), currency="RUB")
            choices = data["choices"]
            if len(choices) != 1:
                raise ValueError
            choice = choices[0]
            message = choice["message"]
            if self._key.get_secret_value() in str(message):
                raise ValueError
            reason = choice["finish_reason"]
            if reason == "length":
                return AdapterResponse(kind="TRUNCATED", usage=usage, cost=cost)
            if reason == "content_filter" or message.get("refusal"):
                return AdapterResponse(kind="REFUSAL", usage=usage, cost=cost)
            calls = message.get("tool_calls")
            if reason == "tool_calls" and calls and not message.get("content"):
                if any(c.get("type") != "function" for c in calls):
                    raise ValueError
                return AdapterResponse(
                    kind="TOOLS",
                    usage=usage,
                    cost=cost,
                    tool_calls=tuple(
                        ToolCall(
                            call_id=c["id"],
                            name=c["function"]["name"],
                            arguments_json=c["function"]["arguments"],
                        )
                        for c in calls
                    ),
                )
            if reason != "stop" or calls or not isinstance(message.get("content"), str):
                raise ValueError
            # Local Gateway validates content; reasoning/other response fields are discarded.
            return AdapterResponse(
                kind="OUTPUT", output_json=message["content"], usage=usage, cost=cost
            )
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            InvalidOperation,
            RecursionError,
        ):
            raise PolzaFailure("ADAPTER_ERROR", "INVALID_PROVIDER_RESPONSE") from None
