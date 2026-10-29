"""One pinned, reviewed Polza route. No retries, SDK, redirect or runtime wiring."""

import asyncio
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Annotated, Any, Literal

import httpx
from pydantic import Field, SecretStr

from asm.ai.contracts import (
    CONVERSATION_RESULT,
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
HISTORY = "https://polza.ai/api/v1/history/generations"
HISTORY_LIST = HISTORY + "?requestType=chat&page=1&limit=5&sortBy=createdAt&sortOrder=desc"
GENERATION_ID = r"gen_[0-9]{1,64}"
HISTORY_BYTES = 65536
HISTORY_SECONDS = 15.0
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
CONVERSATION_WIRE_REVISION = "conversation_result_envelope_v1"
Evidence = Annotated[str, Field(min_length=20, max_length=2000)]
ConditionalFee = Literal[
    "audio_per_million", "input_audio_cache_per_million", "web_search_per_thousand"
]
CONDITIONAL_FEES = frozenset(
    ("audio_per_million", "input_audio_cache_per_million", "web_search_per_thousand")
)


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


def conversation_wire_schema(schema: Any) -> dict[str, Any]:
    """Wrap only the accepted union; hoist its unchanged definitions for local refs."""
    if schema != CONVERSATION_RESULT.json_schema():
        raise ValueError("WIRE_SCHEMA_UNSUPPORTED")
    inner = strict_json(encode(schema).decode())
    definitions = inner.pop("$defs")
    return {
        "type": "object",
        "properties": {"result": inner},
        "required": ["result"],
        "additionalProperties": False,
        "$defs": definitions,
    }


class HistoryReview(DTO):
    """Reviewed family label; never an assertion that history observes a variant."""

    provider: Identifier
    evidence: Evidence


class RouteReview(DTO):
    """Trusted operator input, NOT model output or auto-generated capability proof.

    Exact catalog entry is pinned separately from provider name -> response ID mapping.
    Evidence fields must cite reviewed provider contracts, not offline test results.
    """

    model: str
    provider_name: str = Field(min_length=1, max_length=128)
    response_provider: Identifier
    history: HistoryReview | None = None
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checked_at: datetime
    route_evidence: str = Field(min_length=20, max_length=2000)
    schema_tools_evidence: str = Field(min_length=20, max_length=2000)
    token_bound_evidence: str = Field(min_length=20, max_length=2000)
    billing_bound_evidence: str = Field(min_length=20, max_length=2000)
    image_bound_evidence: str = Field(min_length=20, max_length=2000)
    output_cap_parameter: Literal["max_tokens", "max_completion_tokens"]
    output_cap_includes_reasoning: Literal[True]
    output_cap_evidence: Evidence
    # Each exclusion needs a reviewed route contract, not just an apparent field name.
    # Actual input_audio_cache units/applicability remain unproven by the public docs.
    inactive_fee_evidence: dict[ConditionalFee, Evidence] = Field(default_factory=dict)
    # Public catalog snapshot, not account authorization; rechecked before generation.
    catalog_entry: dict[str, Any] = Field(repr=False)

    def provider(self) -> dict[str, Any]:
        entry = self.catalog_entry
        if self.model not in MODELS or entry.get("id") != self.model:
            raise ValueError("MODEL_UNAVAILABLE")
        if fingerprint(entry) != self.catalog_sha256:
            raise ValueError("CATALOG_DRIFT")
        matches = [p for p in entry.get("providers", []) if p.get("name") == self.provider_name]
        if len(matches) > 1:
            raise ValueError("AMBIGUOUS_PROVIDER_NAME")
        if len(matches) != 1 or matches[0].get("is_unofficial") is not False:
            raise ValueError("OFFICIAL_ROUTE_UNKNOWN")
        provider: dict[str, Any] = matches[0]
        for name in ("tools", "json_schema_strict", "input_image"):
            status = provider.get("capabilities", {}).get(name, {}).get("status")
            if status == "rejected":
                raise ValueError(name.upper() + "_REJECTED")
            if status != "supported":
                if name == "input_image":
                    raise ValueError("IMAGE_CAPABILITY_UNKNOWN")
                raise ValueError("CAPABILITY_UNKNOWN")
        parameters = provider.get("supported_parameters", [])
        if type(parameters) is not list or any(type(p) is not str for p in parameters):
            raise ValueError("PARAMETER_UNSUPPORTED")
        if not {"tools", "tool_choice", "response_format"} <= set(parameters):
            raise ValueError("PARAMETER_UNSUPPORTED")
        if self.output_cap_parameter not in parameters:
            raise ValueError("OUTPUT_CAP_PARAMETER_UNSUPPORTED")
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
        if not self.inactive_fee_evidence.keys() <= pricing.keys():
            raise ValueError("FEE_EXCLUSION_NOT_IN_CATALOG")
        for key, raw in pricing.items():
            if key == "currency":
                continue
            if key not in inputs | outputs | requests | CONDITIONAL_FEES:
                raise ValueError("TARIFF_UNKNOWN")
            if key in CONDITIONAL_FEES and key not in self.inactive_fee_evidence:
                raise ValueError("CONDITIONAL_FEE_REVIEW_REQUIRED")
            if raw is None:
                continue
            if type(raw) not in (str, int, float):
                raise ValueError("TARIFF_UNKNOWN")
            try:
                number = Decimal(str(raw))
            except InvalidOperation:
                raise ValueError("TARIFF_UNKNOWN") from None
            if not number.is_finite() or not 0 <= number <= 1000000:
                raise ValueError("TARIFF_UNKNOWN")
            if key not in CONDITIONAL_FEES:
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

    def reprice(self, entry: dict[str, Any]) -> "RouteReview":
        """Derive a price view; preserve the source review object and its original date."""
        self.fresh()
        self.rates()
        old = self.provider()
        current = RouteReview.model_validate(
            self.model_dump() | {"catalog_entry": entry, "catalog_sha256": fingerprint(entry)}
        )
        new = current.provider()
        if self.catalog_entry["architecture"] != entry["architecture"] or {
            k: v for k, v in old.items() if k != "pricing"
        } != {k: v for k, v in new.items() if k != "pricing"}:
            raise ValueError("PROVIDER_CONFIGURATION_CHANGED")
        if (
            set(old["pricing"]) != set(new["pricing"])
            or old["pricing"]["currency"] != new["pricing"].get("currency")
            or any((v is None) != (new["pricing"][k] is None) for k, v in old["pricing"].items())
        ):
            raise ValueError("TARIFF_SCHEMA_CHANGED")
        current.rates()
        return current

    def metadata(self) -> dict[str, Any]:
        """Catalog declarations/check dates are not a live test or key authorization."""
        capabilities = self.provider()["capabilities"]
        return {
            "model": self.model,
            "provider_only": self.provider_name,
            "expected_response_provider": self.response_provider,
            "expected_history_family": self.history.provider if self.history else None,
            "catalog_sha256": self.catalog_sha256,
            "review_sha256": fingerprint(self.model_dump(mode="json")),
            "output_cap_parameter": self.output_cap_parameter,
            "output_cap_scope": "TOTAL_OUTPUT_INCLUDING_REASONING",
            "catalog_reasoning": self.provider().get("reasoning"),
            "excluded_fee_components": sorted(self.inactive_fee_evidence),
            "capabilities": {
                name: {
                    "status": capabilities[name]["status"],
                    "verified_at": capabilities[name].get("verified_at"),
                    "evidence": "CATALOG_REPORTED_VERIFICATION"
                    if capabilities[name].get("verified_at")
                    else "CATALOG_DECLARATION_ONLY",
                }
                for name in ("tools", "json_schema_strict", "input_image")
            },
            "live_payload_verification": "NOT_ESTABLISHED_BY_CATALOG",
            "account_authorization": "NOT_ESTABLISHED_BY_CATALOG",
        }


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
    history_url = url == HISTORY_LIST or re.fullmatch(re.escape(HISTORY) + "/" + GENERATION_ID, url)
    if (
        url not in (ENDPOINT, CATALOG)
        and not history_url
        or seconds <= 0
        or history_url
        and (body is not None or seconds > HISTORY_SECONDS or maximum > HISTORY_BYTES)
    ):
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
        self.observation: dict[str, Any] = {}
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
            messages,
            conversation_wire_schema(strict_json(request.output_schema_json)),
            request.config.limits.output_tokens,
            schema_name=CONVERSATION_WIRE_REVISION,
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
        schema_name: str,
    ) -> dict[str, Any]:
        prompt_rate, output_rate, request_rate = self.review.rates()
        return {
            "model": self.review.model,
            "messages": messages,
            "stream": False,
            self.review.output_cap_parameter: output,
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
        result = await self._send(body, request.remaining_seconds, limits.output_bytes)
        if result.kind == "OUTPUT":
            try:
                envelope = strict_json(result.output_json or "")
                if type(envelope) is not dict or set(envelope) != {"result"}:
                    raise ValueError
                inner = encode(envelope["result"]).decode()
            except (ValueError, TypeError, RecursionError):
                self.observation["error_detail"] = "INVALID_RESULT_ENVELOPE"
                # Guaranteed invalid for the unchanged local result DTO. Preserve known
                # usage/cost while the Gateway returns its existing INVALID_OUTPUT error.
                inner = "null"
            result = AdapterResponse(
                kind="OUTPUT", output_json=inner, usage=result.usage, cost=result.cost
            )
        return result

    async def _send(self, body: bytes, seconds: float, maximum: int) -> AdapterResponse:
        try:
            self.check_payload(body)
            deadline = time.monotonic() + seconds
            async with asyncio.timeout(seconds):
                raw = await bounded_http(
                    self._key,
                    ENDPOINT,
                    body=body,
                    seconds=seconds,
                    maximum=maximum,
                    transport=self._transport,
                )
                result = self.decode(raw, history_pending=self.review.history is not None)
                if self.observation["provider_field_state"] == "ABSENT":
                    await self.verify_history(result, deadline)
                return result
        except TimeoutError:
            self.observation["error_detail"] = "REQUEST_DEADLINE"
            raise PolzaFailure("TIMEOUT", "REQUEST_DEADLINE") from None
        except PolzaFailure as exc:
            self.observation["error_detail"] = exc.detail
            raise

    async def verify_history(self, result: AdapterResponse, deadline: float) -> None:
        """Two bounded GETs before returning TOOLS/OUTPUT, including the image path."""
        review = self.review.history
        identifier = self.observation["generation_id"]
        if review is None:
            raise PolzaFailure("ADAPTER_ERROR", "HISTORY_REVIEW_REQUIRED")
        if identifier is None:
            raise PolzaFailure("ADAPTER_ERROR", "GENERATION_ID_INVALID")
        if (
            result.usage.input_tokens is None
            or result.usage.output_tokens is None
            or result.cost.status != "CONFIRMED"
        ):
            raise PolzaFailure("ADAPTER_ERROR", "HISTORY_METERING_UNKNOWN")
        if (
            result.usage.input_tokens > INPUT_TOKENS
            or result.usage.output_tokens > OUTPUT_TOKENS
            or result.cost.amount is None
            or result.cost.amount > self.review.reservation()
        ):
            raise PolzaFailure("ADAPTER_ERROR", "HISTORY_METERING_LIMIT")
        deadline = min(deadline, time.monotonic() + HISTORY_SECONDS)
        total_tokens = result.usage.input_tokens + result.usage.output_tokens

        async def get(url: str) -> Any:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PolzaFailure("TIMEOUT", "HISTORY_DEADLINE")
            self.observation["history_gets"] += 1
            raw = await bounded_http(
                self._key,
                url,
                body=None,
                seconds=remaining,
                maximum=HISTORY_BYTES,
                transport=self._transport,
            )
            data = strict_json(raw.decode())
            if self._key.get_secret_value() in json.dumps(data, ensure_ascii=False):
                raise ValueError
            return data

        def matches(row: Any, *, detail: bool) -> bool:
            usage = row["usage"]
            amount = row["clientCost" if detail else "cost"]
            if type(amount) not in (str, int, float):
                return False
            money = Decimal(str(amount))
            return (
                row["id"] == identifier
                and row["requestType"] == "chat"
                and row["status"] == "completed"
                and row["finalEndpointSlug" if detail else "provider"] == review.provider
                and money.is_finite()
                and money == result.cost.amount
                and all(
                    type(usage.get(k)) is int and usage[k] == v
                    for k, v in (
                        ("prompt_tokens", result.usage.input_tokens),
                        ("completion_tokens", result.usage.output_tokens),
                    )
                )
                and (
                    "total_tokens" not in usage
                    or type(usage["total_tokens"]) is int
                    and usage["total_tokens"] == total_tokens
                )
                and (
                    (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") is None
                    or type(usage["completion_tokens_details"]["reasoning_tokens"]) is int
                    and usage["completion_tokens_details"]["reasoning_tokens"]
                    == self.observation["reasoning_tokens"]
                )
            )

        try:
            listing = await get(HISTORY_LIST)
            items = listing["items"]
            if type(items) is not list or len(items) > 5 or any(type(r) is not dict for r in items):
                raise ValueError
            selected = [r for r in items if r.get("id") == identifier]
            if (
                len(selected) != 1
                or not matches(selected[0], detail=False)
                or selected[0].get("model")
                not in (self.review.model, self.review.model.split("/", 1)[1])
            ):
                raise ValueError
            detail = await get(HISTORY + "/" + identifier)
            if (
                not matches(detail, detail=True)
                # Polza documents chat_completions; the owner's three real
                # 2026-10-29 generations report completions for this same endpoint.
                or detail.get("apiType") not in ("chat_completions", "completions")
                or detail.get("responseMode") != "sync"
                or detail.get("isCancelled") is not False
                or type(detail.get("attemptsCount")) is not int
                or detail["attemptsCount"] != 1
                or detail.get("finishReason") != self.observation["finish_reason"]
                or "model" in detail
                and detail["model"] != selected[0]["model"]
                or detail.get("serverTools")
                or detail.get("parentGenerationId")
                or detail.get("stepsCount", 1) != 1
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation, RecursionError):
            raise PolzaFailure("ADAPTER_ERROR", "HISTORY_VERIFICATION_FAILED") from None
        self.observation.update(
            history_family=review.provider, route_evidence_source="HISTORY_LIST_DETAIL"
        )

    def check_payload(self, raw: bytes) -> None:
        """Fee exclusions apply only to this finite text/PNG/function wire surface."""
        try:
            body = strict_json(raw.decode())
            cap = self.review.output_cap_parameter
            if (
                type(body) is not dict
                or not {"model", "messages", "stream", cap, "provider", "response_format"}
                <= set(body)
                or set(body)
                - {
                    "model",
                    "messages",
                    "stream",
                    cap,
                    "provider",
                    "response_format",
                    "tools",
                    "tool_choice",
                }
                or body.get("model") != self.review.model
                or body.get("stream") is not False
                or type(body.get(cap)) is not int
                or not 0 < body[cap] <= OUTPUT_TOKENS
                or body["provider"]["only"] != [self.review.provider_name]
                or body["provider"]["allow_fallbacks"] is not False
                or set(body["provider"]) != {"only", "allow_fallbacks", "max_price"}
                or body["response_format"]["type"] != "json_schema"
                or body["response_format"]["json_schema"]["strict"] is not True
            ):
                raise ValueError
            for tool in body.get("tools", []):
                if tool.get("type") != "function" or tool["function"].get("strict") is not True:
                    raise ValueError
            for message in body["messages"]:
                if set(message) - {"role", "content", "tool_calls", "tool_call_id"}:
                    raise ValueError
                for call in message.get("tool_calls", []):
                    if call.get("type") != "function":
                        raise ValueError
                content = message.get("content")
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text" and set(part) == {"type", "text"}:
                            if type(part["text"]) is not str:
                                raise ValueError
                        elif part.get("type") == "image_url" and set(part) == {"type", "image_url"}:
                            if set(part["image_url"]) != {"url"} or not part["image_url"][
                                "url"
                            ].startswith("data:image/png;base64,"):
                                raise ValueError
                        else:
                            raise ValueError
                elif content is not None and type(content) is not str:
                    raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise PolzaFailure("ADAPTER_ERROR", "PAYLOAD_OUTSIDE_REVIEWED_SCOPE") from None

    async def image_probe(self, body: bytes, seconds: float) -> AdapterResponse:
        """EVAL_ONLY raw image path, never part of ModelAdapter or the text Gateway."""
        self.observation = {}
        self.review.fresh()
        if len(body) > INPUT_BYTES or len(body) + OVERHEAD_TOKENS > INPUT_TOKENS:
            raise ProviderFailure("ADAPTER_ERROR")
        return await self._send(body, seconds, OUTPUT_BYTES)

    def decode(self, raw: bytes, *, history_pending: bool = False) -> AdapterResponse:
        try:
            if self._key.get_secret_value().encode() in raw:
                raise ValueError
            data = strict_json(raw.decode("utf-8"))
            self.observation.update(
                requested_provider=self.review.provider_name,
                provider_field_state="PRESENT" if "provider" in data else "ABSENT",
                observed_body_provider=None,
                history_family=None,
                route_evidence_source="NONE",
                route_variant="NOT_OBSERVED",
                history_gets=0,
                generation_id=data.get("id")
                if isinstance(data.get("id"), str) and re.fullmatch(GENERATION_ID, data["id"])
                else None,
            )
            for field in ("provider", "model"):
                value = data.get(field)
                self.observation["observed_" + field] = (
                    value
                    if isinstance(value, str)
                    and self._key.get_secret_value() not in value
                    and re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,128}", value)
                    else None
                )
            self.observation["observed_body_provider"] = self.observation["observed_provider"]
            if (
                ("provider" in data and data["provider"] != self.review.response_provider)
                or ("provider" not in data and not history_pending)
                or data.get("model") != self.review.model
            ):
                raise PolzaFailure("ADAPTER_ERROR", "RETURNED_ROUTE_MISMATCH")
            if "provider" in data:
                self.observation["route_evidence_source"] = "BODY"
            usage_data = data.get("usage") or {}
            usage = Usage(
                input_tokens=usage_data.get("prompt_tokens"),
                output_tokens=usage_data.get("completion_tokens"),
            )
            reasoning = (usage_data.get("completion_tokens_details") or {}).get("reasoning_tokens")
            self.observation["reasoning_tokens"] = reasoning
            if reasoning is not None and (
                type(reasoning) is not int
                or reasoning < 0
                or usage.output_tokens is None
                or reasoning > usage.output_tokens
            ):
                raise PolzaFailure("USAGE_LIMIT", "REASONING_OUTSIDE_OUTPUT_BOUND")
            for detail in ("prompt_tokens_details", "completion_tokens_details"):
                if (usage_data.get(detail) or {}).get("audio_tokens") not in (None, 0):
                    raise PolzaFailure("ADAPTER_ERROR", "UNREQUESTED_AUDIO_USAGE")
            if any(value != 0 for value in (usage_data.get("server_tool_use") or {}).values()):
                raise PolzaFailure("ADAPTER_ERROR", "UNREQUESTED_SERVER_TOOL_USAGE")
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
            self.observation["finish_reason"] = (
                reason if reason in ("stop", "tool_calls", "length", "content_filter") else None
            )
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
