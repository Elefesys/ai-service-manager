"""Controlled-only fixed embedding profile. Construction never enables real HTTP."""

import asyncio
import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import httpx
from pydantic import SecretStr

from asm.ai.contracts import strict_json
from asm.ai.polza import HISTORY, PolzaFailure, _bounded_http, bounded_capability_http

PROFILE = "polza_openai_text_embedding3small_1536_cosine_v1"
MODEL = "openai/text-embedding-3-small"
DIMENSIONS = 1536
RESERVATION = Decimal("0.08")
MAX_RESPONSE = 262144


class EmbeddingFailure(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require(value: object, code: str) -> None:
    if not value:
        raise EmbeddingFailure(code)


def amount(value: object) -> Decimal:
    require(type(value) in (str, int, float), "COST_LIMIT")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise EmbeddingFailure("COST_LIMIT") from None
    require(result.is_finite() and Decimal(0) <= result <= Decimal("1000000"), "COST_LIMIT")
    exponent = result.as_tuple().exponent
    require(type(exponent) is int and exponent >= -9, "COST_LIMIT")
    return result


def validate_usage(value: Any) -> dict[str, Any]:
    require(type(value) is dict, "USAGE_MISMATCH")
    assert isinstance(value, dict)
    require(
        set(value)
        <= {
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost",
            "cost_rub",
            "prompt_tokens_details",
            "completion_tokens_details",
            "server_tool_use",
        },
        "USAGE_MISMATCH",
    )
    prompt = value.get("prompt_tokens")
    require(type(prompt) is int and 0 < prompt <= 8192, "USAGE_MISMATCH")
    require(
        type(value.get("total_tokens")) is int and value["total_tokens"] == prompt, "USAGE_MISMATCH"
    )
    require(
        "completion_tokens" not in value
        or type(value["completion_tokens"]) is int
        and value["completion_tokens"] == 0,
        "USAGE_MISMATCH",
    )
    for key in ("prompt_tokens_details", "completion_tokens_details", "server_tool_use"):
        details = value.get(key)
        require(details is None or type(details) is dict and len(details) <= 8, "USAGE_MISMATCH")
        for name, count in (details or {}).items():
            require(
                type(name) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name), "USAGE_MISMATCH"
            )
            require(type(count) is int and 0 <= count <= 8192, "USAGE_MISMATCH")
            if name in {"audio_tokens", "reasoning_tokens"} or key == "server_tool_use":
                require(count == 0, "USAGE_MISMATCH")
    cost = amount(value.get("cost_rub", value.get("cost")))
    if "cost_rub" in value and "cost" in value:
        require(cost == amount(value["cost"]), "COST_LIMIT")
    return deepcopy(value)  # Raw ABSENT stays ABSENT, never insert completion_tokens.


def validate_vectors(value: Any, count: int) -> list[list[float]]:
    require(type(value) is list and len(value) == count, "INVALID_EMBEDDING")
    result: list[list[float]] = []
    for row in value:
        require(type(row) is list and len(row) == DIMENSIONS, "INVALID_EMBEDDING")
        require(
            all(type(n) is float and math.isfinite(n) and abs(n) <= 1_000_000 for n in row),
            "INVALID_EMBEDDING",
        )
        norm = sum(n * n for n in row)
        require(math.isfinite(norm) and norm > 0, "INVALID_EMBEDDING")
        result.append(list(row))
    return result


def validate_wire(wire: str) -> dict[str, Any]:
    raw = wire.encode("utf-8")
    require(0 < len(raw) <= 8192, "INVALID_INPUT")
    body = strict_json(wire)
    require(
        type(body) is dict
        and set(body) == {"model", "input", "encoding_format", "dimensions", "provider"},
        "PROFILE_MISMATCH",
    )
    require(
        body["model"] == MODEL
        and body["encoding_format"] == "float"
        and type(body["dimensions"]) is int
        and body["dimensions"] == DIMENSIONS,
        "PROFILE_MISMATCH",
    )
    inputs = body["input"]
    require(type(inputs) is list and 1 <= len(inputs) <= 8, "INVALID_INPUT")
    require(
        all(
            type(text) is str
            and text.strip()
            and len(text.encode("utf-8")) <= (1024 if len(inputs) == 1 else 512)
            and "\0" not in text
            for text in inputs
        ),
        "INVALID_INPUT",
    )
    routing = body["provider"]
    require(
        type(routing) is dict
        and routing.get("only") in (["openai"], ["OpenAI"])
        and routing.get("allow_fallbacks") is False
        and routing.get("require_parameters") is True,
        "PROFILE_MISMATCH",
    )
    require(
        set(routing) <= {"only", "allow_fallbacks", "require_parameters", "max_price"},
        "PROFILE_MISMATCH",
    )
    if "max_price" in routing:
        require(
            routing["max_price"]
            == {"prompt": 3, "completion": 0, "image": 0, "audio": 0, "request": 0}
            and all(type(n) is int for n in routing["max_price"].values()),
            "PROFILE_MISMATCH",
        )
    return cast(dict[str, Any], body)


def completion_code(code: str) -> str:
    return {
        "EMBEDDING_DISABLED": "DISABLED",
        "INVALID_EMBEDDING": "INVALID_RESPONSE",
        "IDENTITY_MISMATCH": "IDENTITY_UNVERIFIED",
        "USAGE_MISMATCH": "USAGE_INVALID",
        "EMBEDDING_UNKNOWN": "TRANSPORT",
        "DEADLINE": "TIMEOUT",
        "INVALID_INPUT": "INVALID_RESPONSE",
    }.get(
        code,
        code
        if code
        in {
            "TRANSPORT",
            "TIMEOUT",
            "INVALID_RESPONSE",
            "PROFILE_MISMATCH",
            "IDENTITY_UNVERIFIED",
            "USAGE_INVALID",
            "COST_UNKNOWN",
            "COST_LIMIT",
            "DISABLED",
            "CANCELLED",
            "SOURCE_STALE",
        }
        else "INVALID_RESPONSE",
    )


def unavailable(code: str, *, unknown: bool = False) -> dict[str, Any]:
    return {
        "kind": "UNKNOWN" if unknown else "ERROR",
        "vectors": None,
        "usage": {},
        "cost": {"status": "UNKNOWN", "amount": None, "currency": "RUB"},
        "identity": {"status": "UNVERIFIED", "source": "NONE", "provider": None, "model": None},
        "request_id": None,
        "error_code": completion_code(code),
    }


class EmbeddingClient:
    """The only enabled mode requires the exact controlled transport class.

    No ambient secret, real adapter, endpoint argument, retry or automatic fallback.
    BODY/HISTORY identify observations of this MockTransport, never a real route.
    """

    def __init__(self, transport: httpx.MockTransport | None = None) -> None:
        if transport is not None and type(transport) is not httpx.MockTransport:
            raise ValueError("CONTROLLED_TRANSPORT_REQUIRED")
        self.transport = transport

    @property
    def enabled(self) -> bool:
        return type(self.transport) is httpx.MockTransport

    async def complete(self, wire: str, *, deadline: datetime, wire_sha256: str) -> dict[str, Any]:
        if self.transport is None:
            return unavailable("EMBEDDING_DISABLED")
        require(type(self.transport) is httpx.MockTransport, "EMBEDDING_DISABLED")
        body = validate_wire(wire)  # Caller validates the full build plan before reserving.
        require(hashlib.sha256(wire.encode()).hexdigest() == wire_sha256, "INVALID_INPUT")
        require(deadline.tzinfo is not None, "INVALID_INPUT")
        outcome = unavailable("INVALID_EMBEDDING")
        sent = False
        try:
            remaining = min(30.0, (deadline - datetime.now(UTC)).total_seconds())
            require(remaining > 0, "DEADLINE")
            async with asyncio.timeout(remaining):
                sent = True
                raw = await bounded_capability_http(
                    SecretStr("CONTROLLED-NO-REAL-KEY"),
                    "embedding",
                    body=wire.encode(),
                    seconds=min(10.0, remaining),
                    maximum=MAX_RESPONSE,
                    transport=self.transport,
                )
                response = strict_json(raw.decode("utf-8"))
                require(
                    type(response) is dict
                    and response.get("model") in (MODEL, "text-embedding-3-small"),
                    "PROFILE_MISMATCH",
                )
                raw_usage = response.get("usage")
                if (
                    type(raw_usage) is dict
                    and len(json.dumps(raw_usage, ensure_ascii=False).encode("utf-8")) <= 2048
                ):
                    outcome["usage"] = deepcopy(raw_usage)
                    try:
                        recorded_cost = amount(raw_usage.get("cost_rub", raw_usage.get("cost")))
                        outcome["cost"] = {
                            "status": "CONFIRMED",
                            "amount": format(recorded_cost, "f"),
                            "currency": "RUB",
                        }
                    except EmbeddingFailure:
                        pass
                usage = validate_usage(raw_usage)
                require(
                    usage["total_tokens"]
                    <= sum(len(text.encode("utf-8")) for text in body["input"]),
                    "USAGE_MISMATCH",
                )
                require(
                    amount(usage.get("cost_rub", usage.get("cost"))) <= RESERVATION, "COST_LIMIT"
                )
                identifier = response.get("id")
                require(
                    identifier is None
                    or type(identifier) is str
                    and re.fullmatch(r"(?:gen_[0-9]{1,64}|emb_[a-zA-Z0-9_-]{1,64})", identifier),
                    "INVALID_EMBEDDING",
                )
                outcome["request_id"] = identifier
                if "provider" in response:
                    require(response["provider"] in ("OpenAI", "openai"), "IDENTITY_MISMATCH")
                    source = "BODY"
                else:
                    # Same documented detail endpoint. No guessed embedding history type,
                    # scan or pagination: exactly the response ID and actual observed fields.
                    require(type(identifier) is str, "IDENTITY_MISMATCH")
                    rows_raw = await self._history("list", identifier, deadline)
                    listing = strict_json(rows_raw.decode("utf-8"))
                    require(
                        type(listing) is dict
                        and type(listing.get("items")) is list
                        and len(listing["items"]) <= 5,
                        "IDENTITY_MISMATCH",
                    )
                    matches = [
                        row
                        for row in listing["items"]
                        if type(row) is dict and row.get("id") == identifier
                    ]
                    require(len(matches) == 1, "IDENTITY_MISMATCH")
                    item = matches[0]
                    require(
                        item.get("model") in (MODEL, "text-embedding-3-small")
                        and item.get("provider") in ("OpenAI", "openai")
                        and item.get("status") == "completed",
                        "IDENTITY_MISMATCH",
                    )
                    require(item.get("requestType") == "embeddings", "IDENTITY_MISMATCH")
                    checked = validate_usage(item.get("usage", {}) | {"cost": item.get("cost")})
                    require(
                        checked["prompt_tokens"] == usage["prompt_tokens"]
                        and checked["total_tokens"] == usage["total_tokens"]
                        and amount(item.get("cost")) == amount(outcome["cost"]["amount"]),
                        "USAGE_MISMATCH",
                    )
                    history_raw = await self._history("detail", identifier, deadline)
                    history = strict_json(history_raw.decode("utf-8"))
                    require(
                        type(history) is dict and history.get("id") == identifier,
                        "IDENTITY_MISMATCH",
                    )
                    require(
                        "model" not in history
                        or history["model"] in (MODEL, "text-embedding-3-small"),
                        "IDENTITY_MISMATCH",
                    )
                    require(
                        history.get("status") == "completed"
                        and history.get("isCancelled") is False,
                        "IDENTITY_MISMATCH",
                    )
                    require(
                        history.get("requestType") == "embeddings"
                        and history.get("apiType") == "embeddings"
                        and history.get("responseMode") == "sync",
                        "IDENTITY_MISMATCH",
                    )
                    require(
                        history.get("finalEndpointSlug") in ("OpenAI", "openai"),
                        "IDENTITY_MISMATCH",
                    )
                    require(
                        type(history.get("attemptsCount")) is int
                        and history["attemptsCount"] == 1
                        and not history.get("parentGenerationId")
                        and not history.get("serverTools"),
                        "IDENTITY_MISMATCH",
                    )
                    require(
                        "stepsCount" not in history
                        or type(history["stepsCount"]) is int
                        and history["stepsCount"] == 1,
                        "IDENTITY_MISMATCH",
                    )
                    require(type(history.get("usage")) is dict, "USAGE_MISMATCH")
                    checked = validate_usage(history["usage"] | {"cost": history.get("clientCost")})
                    require(
                        checked["prompt_tokens"] == usage["prompt_tokens"]
                        and checked["total_tokens"] == usage["total_tokens"]
                        and amount(history.get("clientCost")) == amount(outcome["cost"]["amount"]),
                        "USAGE_MISMATCH",
                    )
                    source = "HISTORY"
                outcome["identity"] = {
                    "status": "CONFIRMED",
                    "source": source,
                    "provider": "OpenAI",
                    "model": MODEL,
                }
                data = response.get("data")
                require(type(data) is list and len(data) == len(body["input"]), "INVALID_EMBEDDING")
                require(
                    all(type(row) is dict and type(row.get("index")) is int for row in data),
                    "INVALID_EMBEDDING",
                )
                require(
                    [row["index"] for row in data] == list(range(len(data))), "INVALID_EMBEDDING"
                )
                vectors = validate_vectors([row.get("embedding") for row in data], len(data))
                outcome.update(kind="SUCCESS", vectors=vectors, error_code=None)
                return outcome
        except asyncio.CancelledError:
            # The caller owns best-effort UNKNOWN persistence then re-raises cancellation.
            raise
        except (TimeoutError, PolzaFailure) as error:
            code = (
                "TIMEOUT"
                if isinstance(error, TimeoutError) or error.code == "TIMEOUT"
                else "TRANSPORT"
            )
            outcome.update(kind="UNKNOWN" if sent else "ERROR", vectors=None, error_code=code)
            return outcome
        except EmbeddingFailure as error:
            outcome["error_code"] = completion_code(error.code)
            return outcome
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            outcome["error_code"] = "INVALID_RESPONSE"
            return outcome

    async def _history(self, operation: str, identifier: str, deadline: datetime) -> bytes:
        # Independent admission. Existing chat HTTP allowlists remain unchanged.
        require(type(self.transport) is httpx.MockTransport, "EMBEDDING_DISABLED")
        require(
            operation in ("list", "detail")
            and re.fullmatch(r"(?:gen_[0-9]{1,64}|emb_[a-zA-Z0-9_-]{1,64})", identifier),
            "IDENTITY_MISMATCH",
        )
        endpoint = HISTORY + (
            "?page=1&limit=5&sortBy=createdAt&sortOrder=desc"
            if operation == "list"
            else "/" + identifier
        )
        remaining = min(10.0, (deadline - datetime.now(UTC)).total_seconds())
        require(remaining > 0, "DEADLINE")
        return await _bounded_http(
            SecretStr("CONTROLLED-NO-REAL-KEY"),
            endpoint,
            body=None,
            seconds=remaining,
            maximum=65536,
            transport=self.transport,
        )
