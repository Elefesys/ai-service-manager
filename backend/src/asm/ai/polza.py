"""Pinned Polza evaluation routes. No retries, SDK, redirect or runtime wiring."""

import asyncio
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Annotated, Any, Literal, NoReturn

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
EXPERIMENT_PROVIDERS = ("openai/flex", "google-ai-studio/flex", "wafer/us")
SIGNATURE_BYTES = 8192
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


class CatalogRoute(DTO):
    """Shared catalog validation; declarations alone never certify a route."""

    model: str
    provider_name: str = Field(min_length=1, max_length=128)
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checked_at: datetime
    output_cap_parameter: Literal["max_tokens", "max_completion_tokens"]
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

    def fresh(self) -> None:
        if self.checked_at.tzinfo is None:
            raise ValueError("REVIEW_EXPIRED")
        age = (datetime.now(UTC) - self.checked_at).total_seconds()
        if not 0 <= age <= 86400:
            raise ValueError("REVIEW_EXPIRED")

    def rates(
        self, *, excluded_fees: frozenset[str] = frozenset()
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Sum possibly additive rates; no optimistic cache discount or unknown fee.

        Reviewed routes require evidence for exclusions. The explicit synthetic
        profile reports its token/image/billing bounds as conditional assumptions.
        """
        pricing = self.provider().get("pricing", {})
        if pricing.get("currency") != "RUB":
            raise ValueError("CURRENCY_UNKNOWN")
        inputs = {
            "prompt_per_million",
            "image_input_per_million",
            "input_cache_read_per_million",
            "input_cache_write_per_million",
            "input_audio_cache_per_million",
        }
        outputs = {"completion_per_million", "internal_reasoning_per_million"}
        requests = {"per_request", "request_per_thousand"}
        if not {"prompt_per_million", "completion_per_million"} <= pricing.keys():
            raise ValueError("TARIFF_UNKNOWN")
        values: dict[str, Decimal] = {}
        for key, raw in pricing.items():
            if key == "currency":
                continue
            if key not in inputs | outputs | requests | CONDITIONAL_FEES:
                raise ValueError("TARIFF_UNKNOWN")
            if key in CONDITIONAL_FEES - inputs and key not in excluded_fees:
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
            if key not in excluded_fees:
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


class RouteReview(CatalogRoute):
    """Trusted operator input, NOT model output or auto-generated capability proof.

    Exact catalog entry is pinned separately from provider name -> response ID mapping.
    Evidence fields must cite reviewed provider contracts, not offline test results.
    """

    response_provider: Identifier
    history: HistoryReview | None = None
    route_evidence: str = Field(min_length=20, max_length=2000)
    schema_tools_evidence: str = Field(min_length=20, max_length=2000)
    token_bound_evidence: str = Field(min_length=20, max_length=2000)
    billing_bound_evidence: str = Field(min_length=20, max_length=2000)
    image_bound_evidence: str = Field(min_length=20, max_length=2000)
    output_cap_includes_reasoning: Literal[True]
    output_cap_evidence: Evidence
    # Each exclusion needs a reviewed route contract, not just an apparent field name.
    # Actual input_audio_cache units/applicability remain unproven by the public docs.
    inactive_fee_evidence: dict[ConditionalFee, Evidence] = Field(default_factory=dict)

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

    def rates(
        self, *, excluded_fees: frozenset[str] = frozenset()
    ) -> tuple[Decimal, Decimal, Decimal]:
        pricing = self.provider().get("pricing", {})
        if not self.inactive_fee_evidence.keys() <= pricing.keys():
            raise ValueError("FEE_EXCLUSION_NOT_IN_CATALOG")
        if CONDITIONAL_FEES & pricing.keys() - self.inactive_fee_evidence.keys():
            raise ValueError("CONDITIONAL_FEE_REVIEW_REQUIRED")
        return super().rates(excluded_fees=frozenset(self.inactive_fee_evidence))

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


class SyntheticRoute(CatalogRoute):
    """C0's finite experimental profile, deliberately separate from RouteReview."""

    @classmethod
    def from_catalog(cls, entry: dict[str, Any], checked_at: datetime) -> "SyntheticRoute":
        model = entry.get("id")
        if model not in MODELS:
            raise ValueError("MODEL_UNAVAILABLE")
        name = EXPERIMENT_PROVIDERS[MODELS.index(model)]
        selected = [p for p in entry.get("providers", []) if p.get("name") == name]
        if len(selected) != 1:
            raise ValueError("EXPERIMENT_ROUTE_NOT_UNIQUE")
        parameters = selected[0].get("supported_parameters", [])
        cap: Literal["max_tokens", "max_completion_tokens"] = (
            "max_tokens" if "max_tokens" in parameters else "max_completion_tokens"
        )
        result = cls(
            model=model,
            provider_name=name,
            catalog_entry=entry,
            catalog_sha256=fingerprint(entry),
            checked_at=checked_at,
            output_cap_parameter=cap,
        )
        result.provider()
        result.rates()
        return result

    def provider(self) -> dict[str, Any]:
        if (
            self.model not in MODELS
            or self.provider_name != EXPERIMENT_PROVIDERS[MODELS.index(self.model)]
        ):
            raise ValueError("EXPERIMENT_ROUTE_MISMATCH")
        provider = super().provider()
        if self.model == MODELS[2]:
            caps = provider.get("capabilities", {})
            reasoning = provider.get("reasoning", {})
            if (
                not {"reasoning", "reasoning_effort"} <= set(provider["supported_parameters"])
                or caps.get("reasoning_toggle", {}).get("status") != "supported"
                or caps.get("reasoning_effort", {}).get("status") != "supported"
                or "none" not in caps.get("reasoning_effort", {}).get("values", [])
                or reasoning.get("mandatory") is not False
                or "none" not in reasoning.get("supported_efforts", [])
            ):
                raise ValueError("NON_THINKING_UNSUPPORTED")
        return provider

    def route(self) -> Route:
        self.provider()
        return Route(
            branch="RU_AGGREGATOR",
            adapter="polza",
            execution="PROVIDER",
            endpoint=ENDPOINT,
            model=self.model,
            upstream=self.provider_name,
            eligibility="EVAL_ONLY",
        )

    def rates(
        self, *, excluded_fees: frozenset[str] = frozenset()
    ) -> tuple[Decimal, Decimal, Decimal]:
        if any(v is None for v in self.provider()["pricing"].values()):
            raise ValueError("TARIFF_UNKNOWN")
        # Audio/search cannot occur in the checked wire surface. Audio cache is
        # conservatively INCLUDED in full; its applicability is not certified.
        return super().rates(
            excluded_fees=frozenset(("audio_per_million", "web_search_per_thousand"))
        )

    def metadata(self) -> dict[str, Any]:
        provider = self.provider()
        return {
            "model": self.model,
            "provider_only": self.provider_name,
            "upstream_semantics": "REQUEST_SELECTOR_NOT_OBSERVATION",
            "eligibility": "EVAL_ONLY",
            "admission": "SYNTHETIC_EXPERIMENT",
            "catalog_sha256": self.catalog_sha256,
            "checked_at": self.checked_at.isoformat(),
            "billing_status": "CONDITIONAL_ESTIMATE",
            "catalog_pricing": provider["pricing"],
            "rates_rub": [str(v) for v in self.rates()],
            "call_reservation_rub": str(self.reservation()),
            "output_cap_parameter": self.output_cap_parameter,
            "output_cap_scope": "ASSUMED_TOTAL_OUTPUT_INCLUDING_REASONING",
            "input_bound": "ASSUMED_WIRE_BYTES_PLUS_4096_INCLUDING_IMAGES",
            "fee_assumptions": {
                "input_audio_cache_per_million": "INCLUDED_IN_FULL",
                "audio_per_million": "EXCLUDED_BY_FINITE_PAYLOAD",
                "web_search_per_thousand": "EXCLUDED_BY_FINITE_PAYLOAD",
            },
            "capabilities": {
                name: {
                    "status": provider["capabilities"][name]["status"],
                    "evidence": "CATALOG_DECLARATION_ONLY",
                }
                for name in ("tools", "json_schema_strict", "input_image")
            },
            "catalog_reasoning": provider.get("reasoning"),
            "reasoning_profile": "NON_THINKING_EXPLICIT"
            if self.model == MODELS[2]
            else "PROVIDER_DEFAULT",
            "reasoning_wire": {"effort": "none", "enabled": False}
            if self.model == MODELS[2]
            else None,
            "continuation": "TRANSIENT_GOOGLE_SIGNATURE"
            if self.model == MODELS[1]
            else "NEUTRAL_TOOL_RESULT",
            "expected_history_family": "OpenAI" if self.model == MODELS[0] else None,
            "history_family_evidence": "PRIOR_OWNER_OBSERVATION"
            if self.model == MODELS[0]
            else "UNKNOWN_UNTIL_THIS_EVAL",
            "route_variant": "NOT_OBSERVED",
            "account_tariff": "NOT_ESTABLISHED_BY_CATALOG",
            "live_payload_verification": "NOT_ESTABLISHED_BY_CATALOG",
            "runtime_authorized": False,
        }


ProbeRoute = RouteReview | SyntheticRoute


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


class ToolCompatRoute(SyntheticRoute):
    """One DeepSeek named-read/none-final experiment; not the original auto eval."""

    @classmethod
    def from_catalog(cls, entry: dict[str, Any], checked_at: datetime) -> "ToolCompatRoute":
        return cls.model_validate(super().from_catalog(entry, checked_at))

    def provider(self) -> dict[str, Any]:
        if self.model != MODELS[2]:
            raise ValueError("TOOL_COMPAT_ROUTE_REQUIRED")
        provider = super().provider()
        # Polza's documented names, not an inferred meaning of tools support:
        # https://polza.ai/docs/gaidy/models#возможности-провайдера-capabilities
        for name in ("tool_choice_function", "tool_choice_none"):
            if provider["capabilities"].get(name, {}).get("status") != "supported":
                raise ValueError(name.upper() + "_UNSUPPORTED")
        return provider


class PolzaAdapter:
    def __init__(
        self,
        review: ProbeRoute,
        key: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.review: ProbeRoute = (
            SyntheticRoute.model_validate(review)
            if isinstance(review, SyntheticRoute)
            else RouteReview.model_validate(review)
        )
        self.experimental = isinstance(self.review, SyntheticRoute)
        self.non_thinking = self.experimental and review.model == MODELS[2]
        self._history_family: str | None = (
            ("OpenAI" if review.model == MODELS[0] else None)
            if self.experimental
            else review.history.provider
            if isinstance(review, RouteReview) and review.history
            else None
        )
        self._run_key: tuple[str, str, str] | None = None
        self._continuation: tuple[ToolCall, str] | None = None
        self._diagnostic_redactions: tuple[str, ...] = ()
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

    def clear_continuation(self) -> None:
        self._run_key = None
        self._continuation = None
        self._diagnostic_redactions = ()

    def continuation_call(self, call: ToolCall) -> dict[str, Any]:
        wire: dict[str, Any] = {
            "id": call.call_id,
            "type": "function",
            "function": {"name": call.name, "arguments": call.arguments_json},
        }
        if self.review.model == MODELS[1]:
            if self._continuation is None or self._continuation[0] != call:
                self.clear_continuation()
                raise PolzaFailure("ADAPTER_ERROR", "SIGNATURE_CORRELATION_FAILED")
            wire["extra_content"] = {"google": {"thought_signature": self._continuation[1]}}
        return wire

    @staticmethod
    def signature_metadata(calls: Any) -> dict[str, Any]:
        """Closed categories only: never values, arbitrary keys or a signature hash."""
        metadata: dict[str, Any] = {
            "code": "SIGNATURE_CORRELATION_FAILED",
            "expected_field_present": None,
            "shape_category": "CALL_CONTAINER",
            "field_type": "UNKNOWN",
            "utf8_bytes_bounded": None,
            "byte_limit": SIGNATURE_BYTES,
            "length_exceeds_limit": None,
        }
        if type(calls) is not list or len(calls) != 1 or type(calls[0]) is not dict:
            return metadata
        node = calls[0]
        for key, missing, wrong_type, extra_keys in (
            ("extra_content", "EXTRA_MISSING", "EXTRA_TYPE", "EXTRA_KEYS"),
            ("google", "GOOGLE_MISSING", "GOOGLE_TYPE", "GOOGLE_KEYS"),
        ):
            metadata["shape_category"] = (
                "EXTRA_CONTENT" if key == "extra_content" else "GOOGLE_CONTAINER"
            )
            if key not in node:
                metadata["expected_field_present"] = False
                metadata["code"] = "SIGNATURE_" + missing
                return metadata
            child = node[key]
            if type(child) is not dict:
                metadata["code"] = "SIGNATURE_" + wrong_type
                return metadata
            expected = "google" if key == "extra_content" else "thought_signature"
            if expected in child and len(child) != 1:
                metadata["code"] = "SIGNATURE_" + extra_keys
                # Presence/type/length remain UNKNOWN until the expected path is closed.
                return metadata
            node = child
        if "thought_signature" not in node:
            metadata["expected_field_present"] = False
            metadata["code"] = "SIGNATURE_FIELD_MISSING"
            return metadata
        value = node["thought_signature"]
        metadata["shape_category"] = "EXPECTED_FIELD"
        metadata["expected_field_present"] = True
        metadata["field_type"] = {
            str: "STRING",
            type(None): "NULL",
            int: "NUMBER",
            float: "NUMBER",
            bool: "BOOLEAN",
            list: "ARRAY",
            dict: "OBJECT",
        }.get(type(value), "UNKNOWN")
        if value is None:
            metadata["code"] = "SIGNATURE_NULL"
        elif type(value) is not str:
            metadata["code"] = "SIGNATURE_TYPE"
        else:
            try:
                size = len(value.encode("utf-8"))
            except UnicodeError:
                metadata["code"] = "SIGNATURE_ENCODING"
                return metadata
            metadata["utf8_bytes_bounded"] = min(size, SIGNATURE_BYTES + 1)
            metadata["length_exceeds_limit"] = size > SIGNATURE_BYTES
            metadata["code"] = (
                "SIGNATURE_EMPTY"
                if not value.strip()
                else "SIGNATURE_CONTROL"
                if not value.isprintable()
                else "SIGNATURE_OVERSIZE"
                if size > SIGNATURE_BYTES
                else "SIGNATURE_VALID"
            )
        return metadata

    @staticmethod
    def google_signature(calls: Any) -> str:
        metadata = PolzaAdapter.signature_metadata(calls)
        if metadata["code"] != "SIGNATURE_VALID":
            raise PolzaFailure("ADAPTER_ERROR", metadata["code"])
        value: str = calls[0]["extra_content"]["google"]["thought_signature"]
        return value

    def observe_signature_failure(self, data: dict[str, Any]) -> None:
        """Retain validated body metadata without turning it into verified history."""
        opaque: list[str] = [self._key.get_secret_value()]
        if self._continuation:
            opaque.append(self._continuation[1])

        def redact_values(value: Any) -> None:
            if (
                type(value) is str
                and value
                and value not in ("assistant", "function", "tool_calls", "stop", "read_current")
            ):
                opaque.append(value)
            elif type(value) is dict:
                for k, v in value.items():
                    if k not in {
                        "index",
                        "message",
                        "role",
                        "content",
                        "tool_calls",
                        "id",
                        "type",
                        "function",
                        "name",
                        "arguments",
                        "extra_content",
                        "google",
                        "thought_signature",
                        "reasoning",
                        "reasoning_content",
                        "reasoning_details",
                        "refusal",
                        "finish_reason",
                    }:
                        redact_values(k)
                    redact_values(v)
            elif type(value) is list:
                for v in value:
                    redact_values(v)

        # All message strings/keys are excluded, including malformed extra content,
        # a signature at a wrong path, raw reasoning and reflected continuation data.
        redact_values(data.get("choices"))
        self._diagnostic_redactions = tuple(opaque)

        def label(value: Any, pattern: str) -> str | None:
            return (
                value
                if (
                    type(value) is str
                    and re.fullmatch(pattern, value)
                    and not any(v in value for v in opaque)
                )
                else None
            )

        self.observation.update(
            requested_provider=self.review.provider_name,
            provider_field_state="PRESENT" if "provider" in data else "ABSENT",
            generation_id=label(data.get("id"), GENERATION_ID),
            observed_model=label(data.get("model"), r"[a-zA-Z0-9_.:/-]{1,128}"),
            observed_provider=label(data.get("provider"), r"[a-zA-Z0-9_.:/-]{1,128}"),
            history_family=None,
            history_gets=0,
            route_evidence_source="NONE",
            route_variant="NOT_OBSERVED",
            body_metadata_evidence="RESPONSE_BODY / FIELD_VALIDATED_ONLY",
        )
        self.observation["observed_body_provider"] = self.observation["observed_provider"]
        if self.observation["observed_provider"] is not None:
            self.observation["route_evidence_source"] = "BODY"
        usage, cost = Usage(), Cost()
        body_usage = data.get("usage")
        if type(body_usage) is dict:
            try:
                if any(v in json.dumps(body_usage, ensure_ascii=False) for v in opaque):
                    raise ValueError
                proposed = Usage(
                    input_tokens=body_usage.get("prompt_tokens"),
                    output_tokens=body_usage.get("completion_tokens"),
                )
                reasoning = (body_usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens"
                )
                if (
                    proposed.input_tokens is not None
                    and proposed.input_tokens <= INPUT_TOKENS
                    and proposed.output_tokens is not None
                    and proposed.output_tokens <= OUTPUT_TOKENS
                    and (
                        reasoning is None
                        or type(reasoning) is int
                        and 0 <= reasoning <= proposed.output_tokens
                    )
                    and body_usage.get(
                        "total_tokens", proposed.input_tokens + proposed.output_tokens
                    )
                    == proposed.input_tokens + proposed.output_tokens
                    and (
                        "total_tokens" not in body_usage or type(body_usage["total_tokens"]) is int
                    )
                    and all(
                        (body_usage.get(k) or {}).get("audio_tokens") in (None, 0)
                        for k in ("prompt_tokens_details", "completion_tokens_details")
                    )
                    and not any((body_usage.get("server_tool_use") or {}).values())
                ):
                    usage = proposed
                    self.observation["reasoning_tokens"] = reasoning
            except (ValueError, TypeError, AttributeError):
                pass
            try:
                amount = body_usage.get("cost_rub", body_usage.get("cost"))
                if any(v in json.dumps(amount, ensure_ascii=False) for v in opaque):
                    raise ValueError
                if type(amount) not in (str, int, float):
                    raise ValueError
                if any(
                    "currency" in part and part["currency"] != "RUB" for part in (data, body_usage)
                ):
                    raise ValueError
                if (
                    "cost_rub" in body_usage
                    and "cost" in body_usage
                    and Decimal(str(amount)) != Decimal(str(body_usage["cost"]))
                ):
                    raise ValueError
                cost = Cost(status="CONFIRMED", amount=Decimal(str(amount)), currency="RUB")
            except (ValueError, TypeError, InvalidOperation):
                pass
        self.observation.setdefault("reasoning_tokens", None)
        reason = data["choices"][0].get("finish_reason")
        self.observation["finish_reason"] = (
            reason if reason in ("stop", "tool_calls", "length", "content_filter") else None
        )
        self.observation["body_metering"] = {
            "source": "RESPONSE_BODY",
            "verification": "FIELD_VALIDATED_ONLY",
            "usage": usage.model_dump(),
            "reported_cost_rub": str(cost.amount) if cost.amount is not None else None,
            "currency": cost.currency,
        }

    def failure_metering(self) -> tuple[Usage, Cost] | None:
        """Body-only amounts remain reported, never confirmed ledger settlements."""
        body = self.observation.get("body_metering")
        if not body or self.observation.get("route_evidence_source") != "HISTORY_LIST_DETAIL":
            return None
        return Usage.model_validate(body["usage"]), Cost(
            status="CONFIRMED", amount=Decimal(body["reported_cost_rub"]), currency="RUB"
        )

    def wire(self, request: AdapterRequest) -> bytes:
        if request.config.route != self.capabilities.route:
            self.clear_continuation()
            raise ValueError("ROUTE_MISMATCH")
        run_key = (
            request.request.run_id,
            request.request.deadline.isoformat(),
            fingerprint(request.config.route.model_dump()),
        )
        if run_key != self._run_key:
            self.clear_continuation()
            if request.exchanges and self.review.model == MODELS[1]:
                raise PolzaFailure("ADAPTER_ERROR", "SIGNATURE_RUN_MISMATCH")
            self._run_key = run_key
        if (
            self.review.model == MODELS[1]
            and request.exchanges
            and (len(request.exchanges) != 1 or len(request.exchanges[0].calls) != 1)
        ):
            raise PolzaFailure("ADAPTER_ERROR", "SIGNATURE_CORRELATION_FAILED")
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
                    "tool_calls": [self.continuation_call(c) for c in exchange.calls],
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
        body = {
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

        if self.non_thinking:
            body["reasoning"] = {"effort": "none", "enabled": False}
        return body

    def count_input_tokens(self, request: AdapterRequest) -> int:
        # Conditional upper bound, not tokenizer output. The admission mode states
        # whether these bounds are reviewed or experimental assumptions.
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
        keep_continuation = False
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
                result = self.decode(
                    raw,
                    history_pending=self.experimental
                    or (isinstance(self.review, RouteReview) and self.review.history is not None),
                )
                if self.experimental or self.observation["provider_field_state"] == "ABSENT":
                    await self.verify_history(result.usage, result.cost, deadline)
                keep_continuation = result.kind == "TOOLS"
                return result
        except TimeoutError:
            self.observation["error_detail"] = "REQUEST_DEADLINE"
            raise PolzaFailure("TIMEOUT", "REQUEST_DEADLINE") from None
        except PolzaFailure as exc:
            # Diagnose this same generation before stopping; never retry the POST,
            # return TOOLS, or execute READ after a signature failure.
            self.observation["error_detail"] = exc.detail
            body_metering = self.observation.get("body_metering")
            if (
                self.experimental
                and exc.detail.startswith("SIGNATURE_")
                and exc.detail != "SIGNATURE_IN_RESPONSE"
                and body_metering
                and self.observation.get("observed_model") == self.review.model
                and self.observation.get("generation_id") is not None
                and (
                    self.observation.get("provider_field_state") == "ABSENT"
                    or self.observation.get("observed_provider") is not None
                )
            ):
                try:
                    await self.verify_history(
                        Usage.model_validate(body_metering["usage"]),
                        Cost(
                            status="CONFIRMED",
                            amount=Decimal(body_metering["reported_cost_rub"]),
                            currency="RUB",
                        ),
                        deadline,
                    )
                except PolzaFailure as history_error:
                    self.observation["failure_history_error"] = history_error.detail
                except (ValueError, TypeError, InvalidOperation):
                    self.observation["failure_history_error"] = "HISTORY_METERING_UNKNOWN"
            raise
        finally:
            if not keep_continuation:
                self.clear_continuation()

    async def verify_history(self, result_usage: Usage, result_cost: Cost, deadline: float) -> None:
        """Two bounded GETs before returning TOOLS/OUTPUT, including the image path."""
        # Fixed branch/type diagnostics only. Never retain a history value, raw
        # response, arbitrary key, exception text, account label or opaque token.
        stage = "PREFLIGHT"
        diagnostic: dict[str, str] = {}
        missing = object()

        def mark(reason: str, value: Any = missing) -> None:
            diagnostic.update(
                stage=stage,
                reason=reason,
                observed_type="MISSING"
                if value is missing
                else {
                    type(None): "NULL",
                    bool: "BOOL",
                    int: "INT",
                    float: "FLOAT",
                    str: "STRING",
                    list: "ARRAY",
                    dict: "OBJECT",
                }.get(type(value), "OTHER"),
            )

        def field(row: Any, key: str, reason: str, default: Any = missing) -> Any:
            mark(reason, row)
            value = row.get(key, missing)
            mark(reason, value)
            if value is missing:
                if default is missing:
                    raise ValueError
                return default
            return value

        def reject(detail: str, reason: str) -> NoReturn:
            mark(reason)
            self.observation["history_diagnostic"] = dict(diagnostic)
            raise PolzaFailure("ADAPTER_ERROR", detail)

        identifier = self.observation["generation_id"]
        if not self.experimental and self._history_family is None:
            reject("HISTORY_REVIEW_REQUIRED", "REVIEW_REQUIRED")
        if identifier is None:
            reject("GENERATION_ID_INVALID", "GENERATION_ID")
        if (
            result_usage.input_tokens is None
            or result_usage.output_tokens is None
            or result_cost.status != "CONFIRMED"
        ):
            reject("HISTORY_METERING_UNKNOWN", "METERING_UNKNOWN")
        if (
            result_usage.input_tokens > INPUT_TOKENS
            or result_usage.output_tokens > OUTPUT_TOKENS
            or result_cost.amount is None
            or result_cost.amount > self.review.reservation()
        ):
            reject("HISTORY_METERING_LIMIT", "METERING_LIMIT")
        deadline = min(deadline, time.monotonic() + HISTORY_SECONDS)
        total_tokens = result_usage.input_tokens + result_usage.output_tokens

        async def get(url: str) -> Any:
            mark("DEADLINE")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PolzaFailure("TIMEOUT", "HISTORY_DEADLINE")
            self.observation["history_gets"] += 1
            mark("TRANSPORT")
            raw = await bounded_http(
                self._key,
                url,
                body=None,
                seconds=remaining,
                maximum=HISTORY_BYTES,
                transport=self._transport,
            )
            mark("JSON")
            data = strict_json(raw.decode())
            mark("PRIVATE_REFLECTION", data)
            serialized = json.dumps(data, ensure_ascii=False)
            if (
                self._key.get_secret_value() in serialized
                or self._continuation
                and self._continuation[1] in serialized
                or any(value in serialized for value in self._diagnostic_redactions)
            ):
                raise ValueError
            return data

        def matches(row: Any, *, detail: bool) -> bool:
            usage = field(row, "usage", "USAGE")
            amount = field(row, "clientCost" if detail else "cost", "COST")
            if type(amount) not in (str, int, float):
                return False
            money = Decimal(str(amount))
            if field(row, "id", "GENERATION_ID") != identifier:
                return False
            if field(row, "requestType", "REQUEST_TYPE") != "chat":
                return False
            if field(row, "status", "STATUS") != "completed":
                return False
            mark("COST", amount)
            if not money.is_finite() or money != result_cost.amount:
                return False
            for key, expected, reason in (
                ("prompt_tokens", result_usage.input_tokens, "USAGE_INPUT"),
                ("completion_tokens", result_usage.output_tokens, "USAGE_OUTPUT"),
            ):
                value = field(usage, key, reason, None)
                if type(value) is not int or value != expected:
                    return False
            mark("USAGE_TOTAL", usage)
            if "total_tokens" in usage:
                value = field(usage, "total_tokens", "USAGE_TOTAL")
                if type(value) is not int or value != total_tokens:
                    return False
            details = field(usage, "completion_tokens_details", "USAGE_REASONING", None)
            reasoning = field(details or {}, "reasoning_tokens", "USAGE_REASONING", None)
            return reasoning is None or (
                type(reasoning) is int and reasoning == self.observation["reasoning_tokens"]
            )

        try:
            stage = "LIST"
            listing = await get(HISTORY_LIST)
            items = field(listing, "items", "ITEMS")
            if type(items) is not list or len(items) > 5 or any(type(r) is not dict for r in items):
                raise ValueError
            selected = [r for r in items if r.get("id") == identifier]
            mark("ID_MATCH_COUNT", len(selected))
            if len(selected) != 1 or not matches(selected[0], detail=False):
                raise ValueError
            if field(selected[0], "model", "MODEL", None) not in (
                self.review.model,
                self.review.model.split("/", 1)[1],
            ):
                raise ValueError
            family = field(selected[0], "provider", "PROVIDER", None)
            if (
                type(family) is not str
                or not re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,128}", family)
                or self._history_family is not None
                and family != self._history_family
            ):
                raise ValueError
            stage = "DETAIL"
            detail = await get(HISTORY + "/" + identifier)
            if (
                field(detail, "finalEndpointSlug", "PROVIDER", None) != family
                or not matches(detail, detail=True)
                # Polza documents chat_completions; the owner's three real
                # 2026-10-29 generations report completions for this same endpoint.
                or field(detail, "apiType", "API_TYPE", None)
                not in ("chat_completions", "completions")
                or field(detail, "responseMode", "RESPONSE_MODE", None) != "sync"
                or field(detail, "isCancelled", "CANCELLED", None) is not False
                or type(field(detail, "attemptsCount", "ATTEMPTS", None)) is not int
                or detail["attemptsCount"] != 1
                or field(detail, "finishReason", "FINISH_REASON", None)
                != self.observation["finish_reason"]
                or "model" in detail
                and field(detail, "model", "MODEL") != selected[0]["model"]
                or field(detail, "serverTools", "SERVER_TOOLS", None)
                or field(detail, "parentGenerationId", "PARENT_GENERATION", None)
                or field(detail, "stepsCount", "STEPS", 1) != 1
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation, RecursionError):
            self.observation["history_diagnostic"] = dict(diagnostic)
            raise PolzaFailure("ADAPTER_ERROR", "HISTORY_VERIFICATION_FAILED") from None
        except (PolzaFailure, asyncio.CancelledError, TimeoutError):
            self.observation["history_diagnostic"] = dict(diagnostic)
            raise
        self._history_family = family
        self.observation.update(
            history_family=family,
            route_evidence_source="HISTORY_LIST_DETAIL",
            history_family_evidence=(
                "PRIOR_OWNER_OBSERVATION"
                if self.review.model == MODELS[0]
                else "OBSERVED_DURING_THIS_EVAL"
            )
            if self.experimental
            else "REVIEWED_MAPPING",
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
                    *(("reasoning",) if self.non_thinking else ()),
                }
                or self.non_thinking
                and body.get("reasoning") != {"effort": "none", "enabled": False}
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
                    expected = self.continuation_call(
                        ToolCall(
                            call_id=call["id"],
                            name=call["function"]["name"],
                            arguments_json=call["function"]["arguments"],
                        )
                    )
                    if call != expected:
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
        self.clear_continuation()
        self.observation = {}
        self.review.fresh()
        if len(body) > INPUT_BYTES or len(body) + OVERHEAD_TOKENS > INPUT_TOKENS:
            raise ProviderFailure("ADAPTER_ERROR")
        return await self._send(body, seconds, OUTPUT_BYTES)

    def decode(self, raw: bytes, *, history_pending: bool = False) -> AdapterResponse:
        data: Any = None
        try:
            if self._key.get_secret_value().encode() in raw:
                raise ValueError
            data = strict_json(raw.decode("utf-8"))
            choices = data["choices"]
            if type(choices) is not list or len(choices) != 1:
                raise ValueError
            message = choices[0]["message"]
            calls = message.get("tool_calls")
            if self.review.model == MODELS[1] and calls:
                self.observation["signature_diagnostic"] = self.signature_metadata(calls)
                signature = self.google_signature(calls)
                extra = calls[0].pop("extra_content")
                try:
                    # A signature reflected in another field must not enter even
                    # the bounded observation labels or neutral tool arguments.
                    if signature in json.dumps(data, ensure_ascii=False):
                        raise PolzaFailure("ADAPTER_ERROR", "SIGNATURE_IN_RESPONSE")
                finally:
                    calls[0]["extra_content"] = extra
            if self._continuation and self._continuation[1] in json.dumps(data, ensure_ascii=False):
                raise PolzaFailure("ADAPTER_ERROR", "SIGNATURE_IN_RESPONSE")
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
                (
                    "provider" in data
                    and (
                        self.observation["observed_body_provider"] is None
                        if self.experimental
                        else isinstance(self.review, RouteReview)
                        and data["provider"] != self.review.response_provider
                    )
                )
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
            self.observation["reasoning_tokens"] = reasoning if type(reasoning) is int else None
            if self.non_thinking:
                self.observation["reasoning_profile"] = "NON_THINKING_EXPLICIT"
                self.observation["reasoning_usage_evidence"] = (
                    "NOT_REPORTED" if reasoning is None else "REPORTED"
                )
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
            choice = choices[0]
            if self._key.get_secret_value() in str(message):
                raise ValueError
            if self.non_thinking and (
                reasoning not in (None, 0)
                or any(
                    message.get(k) not in (None, "", [])
                    for k in ("reasoning", "reasoning_content", "reasoning_details")
                )
            ):
                raise PolzaFailure("ADAPTER_ERROR", "NON_THINKING_NOT_OBSERVED")
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
                result = AdapterResponse(
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
                if self.review.model == MODELS[1]:
                    if len(calls) != 1 or self._run_key is None:
                        raise PolzaFailure("ADAPTER_ERROR", "SIGNATURE_CORRELATION_FAILED")
                    self._continuation = (result.tool_calls[0], self.google_signature(calls))
                return result
            if reason != "stop" or calls or not isinstance(message.get("content"), str):
                raise ValueError
            # Local Gateway validates content; reasoning/other response fields are discarded.
            return AdapterResponse(
                kind="OUTPUT", output_json=message["content"], usage=usage, cost=cost
            )
        except PolzaFailure as exc:
            if (
                exc.detail.startswith("SIGNATURE_")
                and exc.detail != "SIGNATURE_IN_RESPONSE"
                and type(data) is dict
            ):
                self.observe_signature_failure(data)
            raise
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


class ToolCompatAdapter(PolzaAdapter):
    """Closed EVAL_ONLY two-phase profile. No caller-supplied tool_choice or raw path."""

    def __init__(
        self,
        review: ToolCompatRoute,
        key: SecretStr,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(review, ToolCompatRoute):
            raise ValueError("TOOL_COMPAT_ROUTE_REQUIRED")
        super().__init__(review, key, transport=transport)
        self.review = ToolCompatRoute.model_validate(review)
        self._compat_first: AdapterRequest | None = None
        self._compat_call: ToolCall | None = None
        self._compat_wire: bytes | None = None
        self._compat_attempts = 0
        self._compat_stopped = False

    def wire(self, request: AdapterRequest) -> bytes:
        tools = request.request.tools
        exchanges = request.exchanges
        if (
            self._compat_stopped
            or request.request.run_id != "tool_current_0"
            or len(tools) != 1
            or tools[0].name != "read_current"
            or tools[0].arguments.model_json_schema()
            != {
                "type": "object",
                "title": "ReadArgs",
                "additionalProperties": False,
                "properties": {"key": {"const": "current", "title": "Key", "type": "string"}},
                "required": ["key"],
            }
            or len(exchanges) != self._compat_attempts
            or len(exchanges) > 1
            or self._compat_first is not None
            and (
                request.request != self._compat_first.request
                or request.config != self._compat_first.config
            )
            or exchanges
            and (
                self._compat_call is None
                or exchanges[0].calls != (self._compat_call,)
                or len(exchanges[0].results) != 1
                or exchanges[0].results[0].call_id != self._compat_call.call_id
                or exchanges[0].results[0].name != "read_current"
            )
        ):
            raise PolzaFailure("ADAPTER_ERROR", "TOOL_COMPAT_PHASE_INVALID")
        body = strict_json(super().wire(request).decode())
        body["tool_choice"] = (
            "none" if exchanges else {"type": "function", "function": {"name": "read_current"}}
        )
        self._compat_first = self._compat_first or request
        self._compat_wire = encode(body)
        return self._compat_wire

    def check_payload(self, raw: bytes) -> None:
        if self._compat_stopped or self._compat_attempts >= 2 or raw != self._compat_wire:
            raise PolzaFailure("ADAPTER_ERROR", "TOOL_COMPAT_PAYLOAD_INVALID")
        super().check_payload(raw)
        # count_input_tokens/wire may run repeatedly; consume only at the HTTP boundary.
        self._compat_wire = None
        self._compat_attempts += 1

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        try:
            result = await super().complete(request)
            if (
                self._compat_attempts == 1
                and result.kind == "TOOLS"
                and len(result.tool_calls) == 1
            ):
                # _send has already verified history identity, usage and cost.
                # Gateway validates the typed call before the runner can execute READ.
                self._compat_call = result.tool_calls[0]
            else:
                self._compat_stopped = True
            return result
        except BaseException:
            self._compat_stopped = True
            raise
        finally:
            self._compat_wire = None
            self.observation.update(
                compatibility_phase="STRICT_FINAL" if request.exchanges else "NAMED_READ",
                response_format_semantics="STRICT_FINAL_ENVELOPE"
                if request.exchanges
                else "IGNORED_BY_DOCUMENTED_TOOL_MODE",
                auto_tools_compatibility="NOT_TESTED_BY_THIS_PROFILE",
            )

    async def image_probe(self, body: bytes, seconds: float) -> AdapterResponse:
        raise PolzaFailure("ADAPTER_ERROR", "TOOL_COMPAT_RAW_PATH_FORBIDDEN")
