"""Finite synthetic M4 probe. Default/--plan never reads credentials or uses HTTP."""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, TextIO

import httpx
from PIL import Image
from pydantic import Field, TypeAdapter, ValidationError

from asm.ai.contracts import (
    CONVERSATION_RESULT,
    DTO,
    GatewayConfig,
    GatewayRequest,
    Limits,
    Message,
    ReadTool,
    ToolResult,
    strict_json,
)
from asm.ai.gateway import ModelGateway, ProviderFailure
from asm.ai.polza import (
    CATALOG,
    CONVERSATION_WIRE_REVISION,
    EXPERIMENT_PROVIDERS,
    GENERATION_ID,
    HISTORY_BYTES,
    HISTORY_SECONDS,
    INPUT_BYTES,
    INPUT_TOKENS,
    MODELS,
    OUTPUT_BYTES,
    OUTPUT_TOKENS,
    OVERHEAD_TOKENS,
    PolzaAdapter,
    PolzaFailure,
    ProbeRoute,
    RouteReview,
    SyntheticRoute,
    bounded_http,
    encode,
    fingerprint,
)
from asm.ai.settings import ProbeSettings, load_secret

FIXTURES = Path("tests/fixtures/m4_probe_cases.json")
CALL_CEILING = 81
RUB_CEILING = Decimal(150)
PRIOR_CONFIRMED_RUB = Decimal("0.01269785")
PRIOR_MODEL_POSTS = 3
STAGE_RUB_CEILING = RUB_CEILING - PRIOR_CONFIRMED_RUB
DURATION = 1800.0
CASE_SECONDS = 60.0
REPEATS = ("unknown_price", "unknown_booking", "injection")
FIXTURE_SHA256 = "7abd25f1e1f08e51eacc3a68975e6099c942d33fad37376366dfdef6c7e025b2"
EVALUATOR_REVISION = "synthetic_quality_flags_v2"
R1_EVALUATOR_REVISION = "b1ff8f1_regex_fail_fast_v1"
R1_SOURCE = "b1ff8f1463e12ff65a64d692b7fc7718aa8d05fc"
R1_SHA256 = "b727cc1ca65c5ef189cc2bddba619136a354c6414b7159e0bde4d521f52f8b48"
R1_APPROVAL = "C0-M4.2-EXECUTABLE-EVAL-ACCEPT-R1:" + R1_SOURCE + ":CI40915999616"
R1_COST = Decimal("0.08303952")
CONTINUATION_PRIOR = PRIOR_CONFIRMED_RUB + R1_COST
CONTINUATION_CEILING = RUB_CEILING - CONTINUATION_PRIOR
PREFIX_DECISION = "e93c156b5ddcf7dcc2351a21755eb759a6f99e80:M4.2-PROBE-QUALITY-CONTINUATION-R1"


@dataclass(frozen=True)
class ReviewedPrefix:
    """Only the exact C0-reviewed R1 receipt; never an arbitrary resume checkpoint."""

    events: tuple[dict[str, Any], ...]

    @property
    def rows(self) -> list[dict[str, Any]]:
        return [e for e in self.events if e["event"] == "case"]

    def receipt(self) -> dict[str, Any]:
        return {
            "event": "imported_receipt",
            "receipt_sha256": R1_SHA256,
            "source_sha": R1_SOURCE,
            "evaluator_revision": R1_EVALUATOR_REVISION,
            "original_events": self.events,
            "manual_assessments": [
                {
                    "model": r["model"],
                    "repeat": r["repeat"],
                    "case": r["case"],
                    "verdict": "SEMANTIC_PASS_FOR_THIS_SAVED_FINAL_ONLY",
                    "authority": "C0",
                    "decision": PREFIX_DECISION,
                    "receipt_sha256": R1_SHA256,
                    "source_sha": R1_SOURCE,
                }
                for r in self.rows
            ],
            "runtime_authorized": False,
        }


class ReadArgs(DTO):
    key: Literal["current"]


class ReadResult(DTO):
    fact: str = Field(min_length=1, max_length=200)


class ImageResult(DTO):
    shape: Literal["square", "circle"]
    color: Literal["red", "blue"]


class Case(DTO):
    id: str = Field(pattern=r"^[a-z_]+$")
    mode: Literal["text", "tool", "image"]
    context: str = Field(min_length=1, max_length=1000)
    question: str = Field(min_length=1, max_length=500)
    outcomes: tuple[Literal["reply", "handoff", "no_reply"], ...]
    required: tuple[str, ...]
    forbidden: tuple[str, ...]
    critical: bool
    read_fact: str | None = None
    image_base64: str | None = None
    image_sha256: str | None = None
    image_expected: ImageResult | None = None

    @property
    def max_calls(self) -> int:
        return 2 if self.mode == "tool" else 1


def load_cases(path: Path) -> tuple[Case, ...]:
    raw = path.read_bytes()
    if len(raw) > 100000:
        raise ValueError("FIXTURE_SIZE")
    strict_json(raw.decode())
    cases = TypeAdapter(tuple[Case, ...]).validate_json(raw)
    if len(cases) != 22 or len({c.id for c in cases}) != 22:
        raise ValueError("FIXTURE_COUNT")
    if sum(c.mode == "image" for c in cases) != 2 or sum(c.mode == "tool" for c in cases) != 2:
        raise ValueError("FIXTURE_MODES")
    for case in cases:
        for pattern in case.required + case.forbidden:
            try:
                re.compile(pattern)
            except re.PatternError:
                raise ValueError("FIXTURE_REGEX") from None
        if not case.outcomes or case.mode == "tool" and not case.read_fact:
            raise ValueError("FIXTURE_EXPECTATION")
        if case.mode == "image":
            image = base64.b64decode(case.image_base64 or "", validate=True)
            if len(image) > 4096 or hashlib.sha256(image).hexdigest() != case.image_sha256:
                raise ValueError("IMAGE_FIXTURE_HASH")
            with Image.open(io.BytesIO(image)) as picture:
                if picture.format != "PNG" or picture.size != (128, 128):
                    raise ValueError("IMAGE_FIXTURE_SIZE")
                picture.verify()
            if case.image_expected is None:
                raise ValueError("IMAGE_EXPECTATION")
    index = {c.id: c for c in cases}
    if any(
        key not in index or not index[key].critical or index[key].mode != "text" for key in REPEATS
    ):
        raise ValueError("REPEAT_EXPECTATION")
    return cases


def schedule(cases: tuple[Case, ...]) -> tuple[Case, ...]:
    index = {c.id: c for c in cases}
    # Tools first: mandatory native schema + read round trip, then remaining cases.
    return (
        tuple(c for c in cases if c.mode == "tool")
        + tuple(c for c in cases if c.mode != "tool")
        + tuple(index[k] for k in REPEATS)
    )


def read_prefix(path: Path, cases: tuple[Case, ...]) -> ReviewedPrefix:
    """Hash the complete bounded input before inspecting it or loading any secret."""
    with path.open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != R1_SHA256:
        raise ValueError("PREFIX_HASH_MISMATCH")
    try:
        events = tuple(strict_json(line) for line in raw.decode("utf-8").splitlines())
        if len(events) != 30 or any(type(e) is not dict for e in events):
            raise ValueError
        source, catalog_event, proposal = events[:3]
        if (
            source["event"] != "source"
            or source["sha"] != R1_SOURCE
            or source["environment"] != "LOCAL_DESKTOP"
            or source["approval_ref"] != R1_APPROVAL
            or source["admission"] != "SYNTHETIC_EXPERIMENT"
            or source["runtime_authorized"] is not False
            or Decimal(source["prior_confirmed_cost_rub"]) != PRIOR_CONFIRMED_RUB
            or Decimal(source["shared_total_budget_rub"]) != RUB_CEILING
            or Decimal(source["stage_approved_rub"]) != STAGE_RUB_CEILING
            or source["prior_model_posts"] != PRIOR_MODEL_POSTS
            or catalog_event["event"] != "catalog_experiment"
            or catalog_event["admission"] != "SYNTHETIC_EXPERIMENT"
            or catalog_event["billing_status"] != "CONDITIONAL_ESTIMATE"
            or Decimal(catalog_event["prior_confirmed_cost_rub"]) != PRIOR_CONFIRMED_RUB
            or proposal["event"] != "plan"
            or proposal["admission"] != "SYNTHETIC_EXPERIMENT"
            or proposal["billing_status"] != "CONDITIONAL_ESTIMATE"
            or proposal["status"] != "SYNTHETIC_EXPERIMENT / EVAL_ONLY"
            or proposal["runtime_authorized"] is not False
            or proposal["model_selected"] is not False
            or proposal["fixture_sha256"] != FIXTURE_SHA256
            or fingerprint([c.model_dump(mode="json") for c in cases]) != FIXTURE_SHA256
            or proposal["models"] != list(MODELS)
            or proposal["total_scenarios"] != 75
            or proposal["max_model_http_calls"] != 81
            or proposal["max_synthetic_reads"] != 6
            or proposal["input_tokens_per_call"] != INPUT_TOKENS
            or proposal["output_tokens_per_call"] != OUTPUT_TOKENS
            or proposal["wire_input_bytes_per_call"] != INPUT_BYTES
            or proposal["wire_output_bytes_per_call"] != OUTPUT_BYTES
            or proposal["case_seconds"] != CASE_SECONDS
            or proposal["overall_seconds"] != DURATION
            or proposal["history_bytes_per_get"] != HISTORY_BYTES
            or proposal["history_seconds_per_post"] != HISTORY_SECONDS
            or proposal["max_history_http_calls"] != 162
            or proposal["catalog_http_calls"] != 1
            or proposal["prior_model_posts"] != 3
            or proposal["max_shared_model_posts"] != 84
            or Decimal(proposal["prior_confirmed_cost_rub"]) != PRIOR_CONFIRMED_RUB
            or Decimal(proposal["approved_rub"]) != STAGE_RUB_CEILING
            or Decimal(proposal["stage_rub_ceiling"]) != STAGE_RUB_CEILING
            or proposal["route_reviews"] != []
            or proposal["reviewed_routes"] != []
            or proposal["experimental_routes"] != catalog_event["routes"]
        ):
            raise ValueError
        routes = catalog_event["routes"]
        if len(routes) != 3:
            raise ValueError
        reserves = []
        for model, selector, route in zip(MODELS, EXPERIMENT_PROVIDERS, routes, strict=True):
            if (
                route["model"] != model
                or route["provider_only"] != selector
                or route["admission"] != "SYNTHETIC_EXPERIMENT"
                or route["eligibility"] != "EVAL_ONLY"
                or route["runtime_authorized"] is not False
                or route["output_cap_parameter"] not in ("max_tokens", "max_completion_tokens")
                or route["reasoning_wire"]
                != ({"effort": "none", "enabled": False} if model == MODELS[2] else None)
                or not re.fullmatch(r"[0-9a-f]{64}", route["catalog_sha256"])
            ):
                raise ValueError
            rates = [Decimal(v) for v in route["rates_rub"]]
            if len(rates) != 3 or any(not v.is_finite() or v < 0 for v in rates):
                raise ValueError
            reserve = max(
                Decimal("0.000000001"),
                (
                    (INPUT_TOKENS * rates[0] + OUTPUT_TOKENS * rates[1]) / 1000000 + rates[2]
                ).quantize(Decimal("0.000000001"), rounding=ROUND_CEILING),
            )
            if reserve != Decimal(route["call_reservation_rub"]):
                raise ValueError
            reserves.append(reserve)
        total = sum(reserves) * 27
        if (
            total != Decimal(proposal["priced_reservation_rub"])
            or total != Decimal(catalog_event["priced_reservation_rub"])
            or total > STAGE_RUB_CEILING
            or proposal["pricing_catalogs"] != [r["catalog_sha256"] for r in routes]
        ):
            raise ValueError
        position, attempts, expense = 3, 0, Decimal(0)
        generations: set[str] = set()
        rows = []
        for repeat, case in enumerate(schedule(cases)[:12]):
            for _ in range(case.max_calls):
                reservation = events[position]
                position += 1
                attempts += 1
                if (
                    reservation["event"] != "reserved"
                    or reservation["model"] != MODELS[0]
                    or reservation["case"] != case.id
                    or type(reservation["repeat"]) is not int
                    or reservation["repeat"] != repeat
                    or type(reservation["calls_reserved"]) is not int
                    or reservation["calls_reserved"] != attempts
                    or Decimal(reservation["rub_reserved"]) != reserves[0] * attempts
                    or Decimal(reservation["shared_rub_committed_or_reserved"])
                    != PRIOR_CONFIRMED_RUB + reserves[0] * attempts
                    or reservation["cost_status"] != "UNKNOWN"
                ):
                    raise ValueError
            row = events[position]
            position += 1
            if (
                row["event"] != "case"
                or row["model"] != MODELS[0]
                or row["case"] != case.id
                or type(row["repeat"]) is not int
                or row["repeat"] != repeat
                or row["mode"] != case.mode
                or row["critical"] is not case.critical
                or row["upstream"] != EXPERIMENT_PROVIDERS[0]
                or row["provider_only"] != EXPERIMENT_PROVIDERS[0]
                or row["upstream_semantics"] != "REQUEST_SELECTOR_NOT_OBSERVATION"
                or row["prompt_revision"] != "conversation_v1"
                or row["schema_revision"] != "conversation_result_v1"
                or row["wire_schema_revision"] != CONVERSATION_WIRE_REVISION
                or type(row["seconds"]) not in (int, float)
                or not 0 <= row["seconds"] <= CASE_SECONDS
                or type(row["reads"]) is not int
                or row["reads"] != (1 if case.mode == "tool" else 0)
                or len(row["calls"]) != case.max_calls
                or row["failures"] != (["FORBIDDEN_CLAIM"] if repeat == 11 else [])
                or row["assessment"]
                != ("FAIL" if repeat == 11 else "AUTOMATED_CHECKS_PASS / HUMAN_REVIEW_REQUIRED")
            ):
                raise ValueError
            CONVERSATION_RESULT.validate_python(row["final"])
            if evaluate(case, row["final"], row["reads"]) != row["failures"]:
                raise ValueError
            for index, call in enumerate(row["calls"]):
                is_tool = case.mode == "tool" and index == 0
                identifier = call["generation_id"]
                if (
                    call["kind"] != ("TOOLS" if is_tool else "FINAL")
                    or call["error"] is not None
                    or not isinstance(identifier, str)
                    or not re.fullmatch(GENERATION_ID, identifier)
                    or identifier in generations
                    or call["provider_field_state"] != "ABSENT"
                    or call["requested_provider"] != EXPERIMENT_PROVIDERS[0]
                    or call["observed_model"] != MODELS[0]
                    or call["observed_body_provider"] is not None
                    or call["observed_provider"] is not None
                    or call["history_family"] != "OpenAI"
                    or call["history_family_evidence"] != "PRIOR_OWNER_OBSERVATION"
                    or call["route_evidence_source"] != "HISTORY_LIST_DETAIL"
                    or call["route_variant"] != "NOT_OBSERVED"
                    or type(call["history_gets"]) is not int
                    or call["history_gets"] != 2
                    or call["finish_reason"] != ("tool_calls" if is_tool else "stop")
                ):
                    raise ValueError
                generations.add(identifier)
                usage, cost = call["usage"], call["cost"]
                if (
                    any(
                        type(usage[k]) is not int or not 0 <= usage[k] <= limit
                        for k, limit in (
                            ("input_tokens", INPUT_TOKENS),
                            ("output_tokens", OUTPUT_TOKENS),
                        )
                    )
                    or call["reasoning_tokens"] is not None
                    and (
                        type(call["reasoning_tokens"]) is not int
                        or not 0 <= call["reasoning_tokens"] <= usage["output_tokens"]
                    )
                    or type(cost["amount"]) is not str
                    or cost["status"] != "CONFIRMED"
                    or cost["currency"] != "RUB"
                ):
                    raise ValueError
                amount = Decimal(cost["amount"])
                if not amount.is_finite() or not 0 <= amount <= reserves[0]:
                    raise ValueError
                expense += amount
            rows.append(row)
        if (
            position != len(events) - 1
            or attempts != 14
            or len(generations) != 14
            or expense != R1_COST
            or events[-1] != r1_summary(rows)
        ):
            raise ValueError
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        InvalidOperation,
        RecursionError,
    ):
        raise ValueError("PREFIX_RECEIPT_INVALID") from None
    return ReviewedPrefix(events)


def remaining_schedule(
    cases: tuple[Case, ...], model: str, prefix: ReviewedPrefix | None
) -> tuple[tuple[int, Case], ...]:
    return tuple(enumerate(schedule(cases)))[12 if prefix and model == MODELS[0] else 0 :]


def read_reviews(path: Path) -> tuple[RouteReview, ...]:
    raw = path.read_bytes()
    if len(raw) > 200000:
        raise ValueError("REVIEW_SIZE")
    strict_json(raw.decode())
    try:
        reviews = TypeAdapter(tuple[RouteReview, ...]).validate_json(raw)
    except ValidationError as exc:
        fields = {
            part
            for error in exc.errors(include_input=False, include_context=False)
            for part in error["loc"]
            if isinstance(part, str)
        }
        if fields & {
            "output_cap_parameter",
            "output_cap_includes_reasoning",
            "output_cap_evidence",
        }:
            raise ValueError("OUTPUT_CAP_REVIEW_REQUIRED") from None
        if "inactive_fee_evidence" in fields:
            raise ValueError("FEE_EXCLUSION_REVIEW_REQUIRED") from None
        raise ValueError("REVIEW_FIELDS_INVALID") from None
    validate_reviews(reviews)
    return reviews


def validate_reviews(reviews: tuple[ProbeRoute, ...]) -> None:
    if tuple(r.model for r in reviews) != MODELS:
        raise ValueError("EXACT_THREE_MODELS_REQUIRED")
    for review in reviews:
        review.fresh()
        review.route()
        review.reservation()


def plan(
    cases: tuple[Case, ...],
    reviews: tuple[ProbeRoute, ...] = (),
    *,
    synthetic_experiment: bool = False,
    prefix: ReviewedPrefix | None = None,
) -> dict[str, Any]:
    if prefix and not synthetic_experiment:
        raise ValueError("CONTINUATION_REQUIRES_EXPERIMENT")
    if any(isinstance(r, SyntheticRoute) != synthetic_experiment for r in reviews):
        raise ValueError("ADMISSION_MODE_MISMATCH")
    if (
        synthetic_experiment
        and fingerprint([c.model_dump(mode="json") for c in cases]) != FIXTURE_SHA256
    ):
        raise ValueError("EXPERIMENT_FIXTURES_CHANGED")
    if reviews:
        validate_reviews(reviews)
    rows = schedule(cases)
    schedules = [remaining_schedule(cases, model, prefix) for model in MODELS]
    calls_per_model = [sum(c.max_calls for _, c in group) for group in schedules]
    total_calls = sum(calls_per_model)
    total = (
        sum(
            (r.reservation() * n for r, n in zip(reviews, calls_per_model, strict=True)), Decimal(0)
        )
        if reviews
        else None
    )
    prior = CONTINUATION_PRIOR if prefix else PRIOR_CONFIRMED_RUB
    ceiling = RUB_CEILING - prior
    if total_calls > (67 if prefix else CALL_CEILING) or total is not None and total > ceiling:
        raise ValueError("PLAN_EXCEEDS_CEILING")
    return {
        "status": "SYNTHETIC_EXPERIMENT / EVAL_ONLY"
        if synthetic_experiment
        else "REVIEW / PAID PROBE NOT RUN",
        "admission": "SYNTHETIC_EXPERIMENT" if synthetic_experiment else "REVIEWED",
        "runtime_authorized": False,
        "model_selected": False,
        "fixture_sha256": fingerprint([c.model_dump(mode="json") for c in cases]),
        "models": MODELS,
        "cases_per_model": {m: len(g) for m, g in zip(MODELS, schedules, strict=True)}
        if prefix
        else len(rows),
        "total_scenarios": sum(len(g) for g in schedules),
        "aggregate_scenarios": 75,
        "aggregate_model_posts": 81,
        "aggregate_probe_reads": 6,
        "imported_scenarios": 12 if prefix else 0,
        "imported_model_posts": 14 if prefix else 0,
        "prefix_receipt_sha256": R1_SHA256 if prefix else None,
        "evaluator_revision": EVALUATOR_REVISION if synthetic_experiment else R1_EVALUATOR_REVISION,
        "stage_schedule": [
            {"model": m, "cases": [{"repeat": i, "case": c.id} for i, c in g], "max_model_posts": n}
            for m, g, n in zip(MODELS, schedules, calls_per_model, strict=True)
        ],
        "base_text_per_model": {MODELS[0]: 8, MODELS[1]: 20, MODELS[2]: 20} if prefix else 20,
        "critical_repeats_per_model": len(REPEATS),
        "images_per_model": 2,
        "max_model_http_calls": total_calls,
        "hard_call_ceiling": 67 if prefix else CALL_CEILING,
        "max_synthetic_reads": sum(c.mode == "tool" for g in schedules for _, c in g),
        "input_tokens_per_call": INPUT_TOKENS,
        "output_tokens_per_call": OUTPUT_TOKENS,
        "total_token_reservation_ceiling": total_calls * (INPUT_TOKENS + OUTPUT_TOKENS),
        "wire_input_bytes_per_call": INPUT_BYTES,
        "wire_output_bytes_per_call": OUTPUT_BYTES,
        "case_seconds": CASE_SECONDS,
        "overall_seconds": DURATION,
        "catalog_http_calls": 1,
        "max_history_http_calls": 2 * total_calls,
        "history_bytes_per_get": HISTORY_BYTES,
        "history_seconds_per_post": HISTORY_SECONDS,
        "proposed_rub_ceiling": str(RUB_CEILING),
        "prior_confirmed_cost_rub": str(prior),
        "prior_model_posts": PRIOR_MODEL_POSTS + (14 if prefix else 0),
        "max_shared_model_posts": PRIOR_MODEL_POSTS + (14 if prefix else 0) + total_calls,
        "stage_rub_ceiling": str(ceiling),
        "priced_reservation_rub": str(total) if total is not None else None,
        "billing_status": "CONDITIONAL_ESTIMATE"
        if synthetic_experiment
        else "REVIEWED_BOUND"
        if reviews
        else "UNKNOWN: account tariff and route review required",
        "prompt_revision": "conversation_v1",
        "schema_revision": "conversation_result_v1",
        "wire_schema_revision": CONVERSATION_WIRE_REVISION,
        "reviewed_routes": [] if synthetic_experiment else [r.metadata() for r in reviews],
        "experimental_routes": (
            [r.metadata() for r in reviews]
            if reviews
            else [
                {
                    "model": model,
                    "provider_only": selector,
                    "upstream_semantics": "REQUEST_SELECTOR_NOT_OBSERVATION",
                    "reasoning_profile": "NON_THINKING_EXPLICIT"
                    if model == MODELS[2]
                    else "PROVIDER_DEFAULT",
                    "reasoning_wire": {"effort": "none", "enabled": False}
                    if model == MODELS[2]
                    else None,
                    "expected_history_family": "OpenAI" if model == MODELS[0] else None,
                    "continuation": "TRANSIENT_GOOGLE_SIGNATURE"
                    if model == MODELS[1]
                    else "NEUTRAL_TOOL_RESULT",
                }
                for model, selector in zip(MODELS, EXPERIMENT_PROVIDERS, strict=True)
            ]
        )
        if synthetic_experiment
        else [],
        "experimental_assumptions": [
            "Total output including reasoning fits selected 512-token cap",
            "Tokenizer and synthetic image input fit wire bytes plus 4096 tokens",
            "Public catalog rates approximate account charges; additive fee reserve",
            "Declared strict schema and tools work together on these hosted routes",
            "History family does not prove requested variant",
        ]
        if synthetic_experiment
        else [],
        "image_revision": "synthetic_shapes_v1/EVAL_ONLY",
    }


def catalog_subset(data: Any) -> list[dict[str, Any]]:
    """Retain model modalities and complete provider configuration for drift checks."""
    result = []
    for model in MODELS:
        matches = [m for m in data["data"] if m.get("id") == model]
        if len(matches) != 1:
            raise ValueError("MODEL_UNAVAILABLE")
        item = matches[0]
        # Keep provider configuration intact: a new non-price field must not silently
        # disappear before the selected route's repricing comparison.
        providers = [dict(p) for p in item.get("providers", [])]
        result.append(
            {"id": model, "architecture": item.get("architecture", {}), "providers": providers}
        )
    return result


async def catalog(
    settings: ProbeSettings, transport: httpx.AsyncBaseTransport | None = None
) -> list[dict[str, Any]]:
    raw = await bounded_http(
        settings.api_key,
        CATALOG,
        body=None,
        seconds=20.0,
        maximum=4 * 1024 * 1024,
        transport=transport,
    )
    selected = catalog_subset(strict_json(raw.decode()))
    if settings.api_key.get_secret_value() in json.dumps(selected, ensure_ascii=False):
        raise ValueError("INVALID_CATALOG")
    return selected


class Ledger:
    """Monotone reservations, written/flushed BEFORE HTTP. No refund, no resume."""

    def __init__(
        self, output: TextIO, approved: Decimal, calls: int, *, prefix: ReviewedPrefix | None = None
    ) -> None:
        self.prior = CONTINUATION_PRIOR if prefix else PRIOR_CONFIRMED_RUB
        if (
            not approved.is_finite()
            or not 0 < approved <= RUB_CEILING - self.prior
            or not 0 < calls <= (67 if prefix else CALL_CEILING)
        ):
            raise ValueError("APPROVAL_LIMIT")
        self.output = output
        self.approved = approved
        self.ceiling = calls
        self.calls = 0
        self.reserved = Decimal(0)
        self.model_calls = dict.fromkeys(MODELS, 0)
        self.model_reserved = dict.fromkeys(MODELS, Decimal(0))
        self.deadline = time.monotonic() + DURATION

    def record(self, value: dict[str, Any]) -> None:
        self.output.write(json.dumps(value, ensure_ascii=False) + "\n")
        self.output.flush()

    def reserve(self, review: ProbeRoute, case: Case, repeat: int) -> None:
        amount = review.reservation()
        if (
            time.monotonic() >= self.deadline
            or self.calls >= self.ceiling
            or self.reserved + amount > self.approved
        ):
            raise ValueError("GLOBAL_BUDGET_EXHAUSTED")
        self.calls += 1
        self.reserved += amount
        self.model_calls[review.model] += 1
        self.model_reserved[review.model] += amount
        self.record(
            {
                "event": "reserved",
                "model": review.model,
                "case": case.id,
                "repeat": repeat,
                "calls_reserved": self.calls,
                "rub_reserved": str(self.reserved),
                "shared_rub_committed_or_reserved": str(self.prior + self.reserved),
                "cost_status": "UNKNOWN",
            }
        )


def configuration(review: ProbeRoute, case: Case) -> GatewayConfig:
    reserve = review.reservation()
    return GatewayConfig(
        revision="m4_2_probe_v1",
        route=review.route(),
        prompt_revision="conversation_v1",
        schema_revision="conversation_result_v1",
        limits=Limits(
            model_calls=case.max_calls,
            read_executions=1 if case.mode == "tool" else 0,
            input_bytes=INPUT_BYTES,
            output_bytes=OUTPUT_BYTES,
            input_tokens=INPUT_TOKENS,
            output_tokens=OUTPUT_TOKENS,
            total_tokens=case.max_calls * (INPUT_TOKENS + OUTPUT_TOKENS),
            duration_seconds=CASE_SECONDS,
            currency="RUB",
            cost_budget=reserve * case.max_calls,
            call_cost_reservation=reserve,
        ),
    )


def evaluate(case: Case, final: dict[str, Any] | None, reads: int) -> list[str]:
    failures = []
    if final is None or final.get("kind") not in case.outcomes:
        failures.append("OUTCOME")
    text = " ".join(str((final or {}).get(k) or "") for k in ("text", "reason"))
    if any(re.search(p, text, re.I) is None for p in case.required):
        failures.append("MISSING_EXPECTED_FACT")
    if any(re.search(p, text, re.I) is not None for p in case.forbidden):
        failures.append("FORBIDDEN_CLAIM")
    if case.mode == "tool" and reads != 1:
        failures.append("READ_ROUND_TRIP")
    return failures


def quality_flags(case: Case, final: dict[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if case.mode == "image":
        if final != (case.image_expected.model_dump() if case.image_expected else None):
            flags.append(
                {
                    "code": "IMAGE_FACT",
                    "expected": case.image_expected.model_dump() if case.image_expected else None,
                    "observed": final,
                }
            )
        return flags
    if final.get("kind") not in case.outcomes:
        flags.append(
            {"code": "OUTCOME", "expected": list(case.outcomes), "observed": final.get("kind")}
        )
    text = " ".join(str(final.get(k) or "") for k in ("text", "reason"))
    for patterns, code in (
        (case.required, "MISSING_EXPECTED_FACT"),
        (case.forbidden, "FORBIDDEN_CLAIM"),
    ):
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if (match is None) == (code == "MISSING_EXPECTED_FACT"):
                flags.append(
                    {
                        "code": code,
                        "pattern": pattern,
                        "match": match.group(0) if match else None,
                        "span": list(match.span()) if match else None,
                    }
                )
    return flags


def metering_failures(result: dict[str, Any], review: ProbeRoute) -> list[str]:
    failures = []
    usage, cost = result["usage"], result["cost"]
    if usage["input_tokens"] is None or usage["output_tokens"] is None:
        failures.append("USAGE_UNKNOWN")
    elif usage["input_tokens"] > INPUT_TOKENS or usage["output_tokens"] > OUTPUT_TOKENS:
        failures.append("USAGE_LIMIT")
    if cost["status"] != "CONFIRMED":
        failures.append("COST_UNKNOWN")
    elif Decimal(cost["amount"]) > review.reservation():
        failures.append("COST_LIMIT")
    return failures


async def run_case(
    adapter: PolzaAdapter, case: Case, ledger: Ledger, repeat: int
) -> dict[str, Any]:
    started = time.monotonic()
    case_deadline = min(started + CASE_SECONDS, ledger.deadline)
    review = adapter.review
    results: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    failures: list[str] = []
    reads = 0
    adapter.clear_continuation()
    try:
        if case.mode == "image":
            body = encode(
                adapter.base_body(
                    [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": case.question},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "data:image/png;base64," + (case.image_base64 or "")
                                    },
                                },
                            ],
                        }
                    ],
                    ImageResult.model_json_schema(),
                    OUTPUT_TOKENS,
                    schema_name="synthetic_shapes_v1",
                )
            )
            if len(body) > INPUT_BYTES or len(body) + OVERHEAD_TOKENS > INPUT_TOKENS:
                raise ValueError("IMAGE_INPUT_LIMIT")
            ledger.reserve(review, case, repeat)
            response = await adapter.image_probe(body, case_deadline - time.monotonic())
            results.append(
                {
                    "kind": response.kind,
                    "usage": response.usage.model_dump(),
                    "cost": response.cost.model_dump(mode="json"),
                    **adapter.observation,
                }
            )
            if (
                response.usage.input_tokens is not None
                and response.usage.input_tokens > len(body) + OVERHEAD_TOKENS
            ):
                failures.append("USAGE_LIMIT")
            if response.kind != "OUTPUT":
                failures.append("IMAGE_OUTCOME")
            else:
                strict_json(response.output_json or "")
                image_result = ImageResult.model_validate_json(response.output_json or "")
                final = image_result.model_dump()
                if image_result != case.image_expected and not adapter.experimental:
                    failures.append("IMAGE_FACT")
        else:
            tool = ReadTool(
                name="read_current",
                revision="synthetic_v1",
                description="Read only the current synthetic fixture fact.",
                arguments=ReadArgs,
                result=ReadResult,
            )
            request = GatewayRequest(
                run_id=f"{case.id}_{repeat}",
                deadline=datetime.now(UTC) + timedelta(seconds=case_deadline - time.monotonic()),
                messages=(
                    Message(role="context", text=case.context),
                    Message(role="user", text=case.question),
                ),
                tools=(tool,) if case.mode == "tool" else (),
            )
            gateway = ModelGateway(configuration(review, case), request, adapter)
            tool_results: tuple[ToolResult, ...] = ()
            for _ in range(case.max_calls):
                ledger.reserve(review, case, repeat)
                response_gw = await gateway.call(tool_results)
                results.append(
                    {
                        "kind": response_gw.kind,
                        "error": response_gw.error,
                        "usage": response_gw.usage.model_dump(),
                        "cost": response_gw.cost.model_dump(mode="json"),
                        **adapter.observation,
                    }
                )
                if response_gw.kind == "FINAL":
                    final = response_gw.result.model_dump() if response_gw.result else None
                    break
                if response_gw.kind != "TOOLS":
                    failures.append(response_gw.error or response_gw.kind)
                    break
                failures.extend(metering_failures(results[-1], review))
                if failures:
                    break
                # Gateway already validated arguments, allowlist, correlation and read reservation.
                if len(response_gw.tool_calls) != 1 or reads != 0:
                    failures.append("READ_LIMIT")
                    break
                call = response_gw.tool_calls[0]
                reads += 1
                tool_results = (
                    ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        result_json=ReadResult(fact=case.read_fact or "").model_dump_json(),
                    ),
                )
            if adapter.experimental:
                if case.mode == "tool" and reads != 1:
                    failures.append("READ_ROUND_TRIP")
                if final is None and not failures:
                    failures.append("FINAL_MISSING")
            else:
                failures.extend(evaluate(case, final, reads))
        for result in results:
            failures.extend(metering_failures(result, review))
    except asyncio.CancelledError:
        # This finite CLI must stop, retaining any confirmed tool call before the
        # cancelled final attempt. live() stops on this row without another POST.
        failures.append("CANCELLED")
    except ProviderFailure as exc:
        failures.append(exc.code)
        results.append(
            {
                "kind": "ERROR",
                "error": exc.code,
                "usage": {"input_tokens": None, "output_tokens": None},
                "cost": {"status": "UNKNOWN", "amount": None, "currency": None},
                **adapter.observation,
            }
        )
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        failures.append("PROBE_INVALID")
    finally:
        adapter.clear_continuation()
    flags = quality_flags(case, final) if final is not None else []
    for result in results:
        result["reservation_rub"] = str(review.reservation())
    return {
        "event": "case",
        "evaluator_revision": EVALUATOR_REVISION if adapter.experimental else R1_EVALUATOR_REVISION,
        "quality_flags": flags,
        "manual_assessment": "PENDING",
        "runtime_authorized": False,
        "model": review.model,
        "upstream": review.route().upstream,
        "upstream_semantics": "REQUEST_SELECTOR_NOT_OBSERVATION"
        if isinstance(review, SyntheticRoute)
        else "REVIEWED_RESPONSE_MAPPING",
        "provider_only": review.provider_name,
        "case": case.id,
        "repeat": repeat,
        "mode": case.mode,
        "critical": case.critical,
        "prompt_revision": "conversation_v1" if case.mode != "image" else "synthetic_shapes_v1",
        "schema_revision": "conversation_result_v1"
        if case.mode != "image"
        else "synthetic_shapes_v1",
        "wire_schema_revision": CONVERSATION_WIRE_REVISION
        if case.mode != "image"
        else "synthetic_shapes_v1",
        "seconds": round(time.monotonic() - started, 3),
        "calls": results,
        "reads": reads,
        "final": final,
        "failures": sorted(set(failures)),
        "assessment": ("TECHNICAL_FAILURE" if failures else "HUMAN_REVIEW_REQUIRED")
        if adapter.experimental
        else "FAIL"
        if failures
        else "AUTOMATED_CHECKS_PASS / HUMAN_REVIEW_REQUIRED",
    }


def r1_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {}
    for model in MODELS:
        selected = [r for r in rows if r["model"] == model]
        times = sorted(r["seconds"] for r in selected)
        completed = [r for r in selected if not r["failures"]]
        cost = sum(
            (Decimal(c["cost"]["amount"]) for r in completed for c in r["calls"]), Decimal(0)
        )
        summary[model] = {
            "n": len(times),
            "p50_seconds": times[math.ceil(len(times) * 0.5) - 1] if times else None,
            "p95_seconds": times[math.ceil(len(times) * 0.95) - 1] if times else None,
            "completed": len(completed),
            "completed_cost_rub": str(cost) if completed else None,
            "mean_completed_cost_rub": str(cost / len(completed)) if completed else None,
            "cost_status": "CONFIRMED" if completed else "UNKNOWN",
            "eligibility": "FAILED_OR_INCOMPLETE"
            if len(completed) != 25
            else "HUMAN_REVIEW_REQUIRED",
        }
    return {
        "event": "summary",
        "status": "HUMAN_REVIEW_REQUIRED"
        if len(rows) == 25 * len(MODELS) and all(not r["failures"] for r in rows)
        else "FAILED_OR_INCOMPLETE",
        "models": summary,
        "selected_model": None,
        "runtime_authorized": False,
        "limitation": "Small synthetic sample; review every final output against fixtures before selection. No runtime authorization.",
    }


def call_accounting(rows: list[dict[str, Any]], attempts: int, reserved: Decimal) -> dict[str, Any]:
    calls = [c for row in rows for c in row["calls"]]
    known = [c for c in calls if c["cost"]["status"] == "CONFIRMED"]
    unknown = max(attempts, len(calls)) - len(known)
    confirmed = sum((Decimal(c["cost"]["amount"]) for c in known), Decimal(0))
    settled_reserve = sum((Decimal(c.get("reservation_rub", "0")) for c in known), Decimal(0))
    return {
        "known_call_count": len(known),
        "confirmed_cost_rub": str(confirmed),
        "unknown_call_count": unknown,
        "unknown_cost_rub": None if unknown else "0",
        "attempt_reservations": attempts,
        "reservation_scope": "NEW_STAGE_ONLY",
        "reserved_rub": str(reserved),
        "unknown_reserved_rub": str(max(Decimal(0), reserved - settled_reserve))
        if unknown
        else "0",
        "cost_status": "UNKNOWN" if unknown else "CONFIRMED" if known else "NOT_RUN",
    }


def summaries(
    rows: list[dict[str, Any]],
    *,
    ledger: Ledger | None = None,
    prefix: ReviewedPrefix | None = None,
) -> dict[str, Any]:
    """All charges count, even when a quality flag or technical error rejects a case."""
    imported = prefix.rows if prefix else []
    combined = imported + rows
    manual_ids = {(r["model"], r["repeat"], r["case"]) for r in imported}
    summary = {}
    for model in MODELS:
        selected = [r for r in combined if r["model"] == model]
        new_rows = [r for r in rows if r["model"] == model]
        prior_rows = [r for r in imported if r["model"] == model]
        times = sorted(r["seconds"] for r in selected)
        completed = [
            r
            for r in selected
            if not r["failures"] or (r["model"], r["repeat"], r["case"]) in manual_ids
        ]
        completed_cost = sum(
            (Decimal(c["cost"]["amount"]) for r in completed for c in r["calls"]), Decimal(0)
        )
        accounting = call_accounting(
            new_rows,
            ledger.model_calls[model] if ledger else sum(len(r["calls"]) for r in new_rows),
            ledger.model_reserved[model] if ledger else Decimal(0),
        )
        accounting["known_call_count"] += sum(len(r["calls"]) for r in prior_rows)
        accounting["confirmed_cost_rub"] = str(
            Decimal(accounting["confirmed_cost_rub"])
            + sum(
                (Decimal(c["cost"]["amount"]) for r in prior_rows for c in r["calls"]), Decimal(0)
            )
        )
        if prior_rows and accounting["cost_status"] == "NOT_RUN":
            accounting["cost_status"] = "CONFIRMED"
        summary[model] = {
            "n": len(times),
            "stage_n": len(new_rows),
            "imported_n": len(prior_rows),
            "p50_seconds": times[math.ceil(len(times) * 0.5) - 1] if times else None,
            "p95_seconds": times[math.ceil(len(times) * 0.95) - 1] if times else None,
            "completed": len(completed),
            "completed_cost_rub": str(completed_cost) if completed else None,
            "mean_completed_cost_rub": str(completed_cost / len(completed)) if completed else None,
            "quality_flagged_cases": sum(bool(r.get("quality_flags")) for r in new_rows),
            "historical_flagged_cases": sum(bool(r["failures"]) for r in prior_rows),
            "manual_reviewed_cases": len(prior_rows),
            "quality_assessment": "HUMAN_REVIEW_REQUIRED",
            **accounting,
            "eligibility": "NOT_RUN"
            if not selected and not accounting["attempt_reservations"]
            else "HUMAN_REVIEW_REQUIRED"
            if len(completed) == 25
            else "FAILED_OR_INCOMPLETE",
        }
    stage = call_accounting(
        rows,
        ledger.calls if ledger else sum(len(r["calls"]) for r in rows),
        ledger.reserved if ledger else Decimal(0),
    )
    prior_cost = R1_COST if prefix else Decimal(0)
    probe_cost = prior_cost + Decimal(stage["confirmed_cost_rub"])
    return {
        "event": "summary",
        "evaluator_revision": EVALUATOR_REVISION,
        "status": "HUMAN_REVIEW_REQUIRED"
        if all(s["eligibility"] == "HUMAN_REVIEW_REQUIRED" for s in summary.values())
        else "FAILED_OR_INCOMPLETE",
        "models": summary,
        "stage_scenarios": len(rows),
        "aggregate_scenarios": len(combined),
        "helper": {"confirmed_cost_rub": str(PRIOR_CONFIRMED_RUB), "model_posts": 3, "reads": 1},
        "imported_r1": {
            "receipt_sha256": R1_SHA256 if prefix else None,
            "confirmed_cost_rub": str(prior_cost),
            "known_call_count": 14 if prefix else 0,
            "reads": 2 if prefix else 0,
        },
        "new_stage": stage,
        "aggregate_probe": {
            "confirmed_cost_rub": str(probe_cost),
            "known_call_count": stage["known_call_count"] + (14 if prefix else 0),
            "unknown_call_count": stage["unknown_call_count"],
            "reads": sum(r["reads"] for r in combined),
            "cost_status": "UNKNOWN"
            if stage["unknown_call_count"]
            else "CONFIRMED"
            if prefix or stage["known_call_count"]
            else "NOT_RUN",
        },
        "shared_total": {
            "confirmed_cost_rub": str(PRIOR_CONFIRMED_RUB + probe_cost),
            "known_call_count": 3 + (14 if prefix else 0) + stage["known_call_count"],
            "unknown_call_count": stage["unknown_call_count"],
            "unknown_reserved_rub": stage["unknown_reserved_rub"],
            "budget_rub": str(RUB_CEILING),
        },
        "selected_model": None,
        "runtime_authorized": False,
        "limitation": "Heuristic flags and full collection are not quality approval. Review all finals, routes and charges; unknown charges are not zero. No runtime authorization.",
    }


async def live(
    cases: tuple[Case, ...],
    reviews: tuple[RouteReview, ...],
    settings: ProbeSettings,
    output: TextIO,
    approved: Decimal,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    synthetic_experiment: bool = False,
    prefix: ReviewedPrefix | None = None,
) -> dict[str, Any]:
    if prefix and not synthetic_experiment:
        raise ValueError("CONTINUATION_REQUIRES_EXPERIMENT")
    if synthetic_experiment:
        if reviews:
            raise ValueError("EXPERIMENT_CANNOT_USE_REVIEWS")
        plan(cases, synthetic_experiment=True, prefix=prefix)
    else:
        if not reviews:
            raise ValueError("EXACT_THREE_MODELS_REQUIRED")
        validate_reviews(reviews)
    ledger = Ledger(output, approved, 67 if prefix else CALL_CEILING, prefix=prefix)
    if prefix:
        ledger.record(prefix.receipt())
    counts = [
        sum(c.max_calls for _, c in remaining_schedule(cases, model, prefix)) for model in MODELS
    ]
    async with asyncio.timeout(ledger.deadline - time.monotonic()):
        current = await catalog(settings, transport)
    price_checked_at = datetime.now(UTC).isoformat()
    priced_reviews: tuple[ProbeRoute, ...]
    if synthetic_experiment:
        priced_reviews = tuple(SyntheticRoute.from_catalog(e, datetime.now(UTC)) for e in current)
        ledger.record(
            {
                "event": "catalog_experiment",
                "admission": "SYNTHETIC_EXPERIMENT",
                "source": "PUBLIC_CATALOG",
                "checked_at": price_checked_at,
                "billing_status": "CONDITIONAL_ESTIMATE",
                "account_tariff": "NOT_ESTABLISHED_BY_CATALOG",
                "routes": [r.metadata() for r in priced_reviews],
                "priced_reservation_rub": str(
                    sum(
                        (r.reservation() * n for r, n in zip(priced_reviews, counts, strict=True)),
                        Decimal(0),
                    )
                ),
                "prior_confirmed_cost_rub": str(ledger.prior),
            }
        )
    else:
        priced_reviews = tuple(r.reprice(e) for r, e in zip(reviews, current, strict=True))
        fresh_reservation = sum(
            (r.reservation() * n for r, n in zip(priced_reviews, counts, strict=True)), Decimal(0)
        )
        ledger.record(
            {
                "event": "catalog_repricing",
                "source": "PUBLIC_CATALOG",
                "account_tariff": "NOT_ESTABLISHED_BY_CATALOG",
                "checked_at": price_checked_at,
                "priced_reservation_rub": str(fresh_reservation),
                "prior_confirmed_cost_rub": str(ledger.prior),
                "shared_rub_committed_or_reserved": str(PRIOR_CONFIRMED_RUB + fresh_reservation),
                "routes": [
                    {
                        "model": old.model,
                        "requested_provider": old.provider_name,
                        "review_sha256": fingerprint(old.model_dump(mode="json")),
                        "review_checked_at": old.checked_at.isoformat(),
                        "old_catalog_sha256": old.catalog_sha256,
                        "new_catalog_sha256": new.catalog_sha256,
                        "provider_configuration_sha256": fingerprint(
                            {k: v for k, v in old.provider().items() if k != "pricing"}
                        ),
                        "old_pricing": old.provider()["pricing"],
                        "new_pricing": new.provider()["pricing"],
                        "fresh_rates_rub": [str(v) for v in new.rates()],
                        "call_reservation_rub": str(new.reservation()),
                    }
                    for old, new in zip(reviews, priced_reviews, strict=True)
                ],
            }
        )
    proposal = plan(cases, priced_reviews, synthetic_experiment=synthetic_experiment, prefix=prefix)
    if Decimal(proposal["priced_reservation_rub"]) > approved:
        raise ValueError("APPROVED_BUDGET_TOO_SMALL")
    ledger.record(
        {
            "event": "plan",
            **proposal,
            "status": "SYNTHETIC_EXPERIMENT / EVAL_ONLY"
            if synthetic_experiment
            else "SYNTHETIC_EVAL_ONLY",
            "route_reviews": [r.catalog_sha256 for r in reviews],
            "reviewed_routes": [r.metadata() for r in reviews],
            "pricing_catalogs": [r.catalog_sha256 for r in priced_reviews],
            "approved_rub": str(approved),
        }
    )
    rows: list[dict[str, Any]] = []
    try:
        for review in priced_reviews:
            adapter = PolzaAdapter(review, settings.api_key, transport=transport)
            for repeat, case in remaining_schedule(cases, review.model, prefix):
                remaining = ledger.deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("GLOBAL_DEADLINE")
                async with asyncio.timeout(remaining):
                    row = await run_case(adapter, case, ledger, repeat)
                ledger.record(row)
                rows.append(row)
                # Experimental quality flags need human review; hard failures still stop.
                if row["failures"]:
                    summary = summaries(rows, ledger=ledger, prefix=prefix)
                    ledger.record(summary)
                    return summary
    except (ValueError, ProviderFailure, TimeoutError):
        ledger.record(summaries(rows, ledger=ledger, prefix=prefix))
        raise
    summary = summaries(rows, ledger=ledger, prefix=prefix)
    ledger.record(summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--synthetic-experiment", action="store_true")
    parser.add_argument("--continue-from", type=Path)
    parser.add_argument("--secret-file", type=Path, default=Path(".env.m4-probe"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--approval-ref")
    parser.add_argument("--approved-rub", type=Decimal)
    parser.add_argument("--source-sha")
    parser.add_argument("--source-environment", choices=("LOCAL_DESKTOP", "LOCAL_BACKEND"))
    args = parser.parse_args(argv)
    try:
        if args.synthetic_experiment and (args.review or args.preflight):
            raise ValueError("EXPERIMENT_CANNOT_USE_REVIEWS_OR_PREFLIGHT")
        if args.continue_from and not args.synthetic_experiment:
            raise ValueError("CONTINUATION_REQUIRES_EXPERIMENT")
        cases = load_cases(args.fixtures)
        prefix = read_prefix(args.continue_from, cases) if args.continue_from else None
        prior = CONTINUATION_PRIOR if prefix else PRIOR_CONFIRMED_RUB
        reviews = read_reviews(args.review) if args.review else ()
        if not args.preflight and not args.live:
            print(
                json.dumps(
                    plan(
                        cases,
                        reviews,
                        synthetic_experiment=args.synthetic_experiment,
                        prefix=prefix,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if not args.approval_ref or not args.report:
            raise ValueError("EXPLICIT_APPROVAL_AND_NEW_REPORT_REQUIRED")
        if args.live and (
            (not args.synthetic_experiment and len(reviews) != len(MODELS))
            or args.approved_rub is None
        ):
            raise ValueError("REVIEW_AND_BUDGET_REQUIRED")
        if args.live and (
            not re.fullmatch(r"[0-9a-f]{40}", args.source_sha or "") or not args.source_environment
        ):
            raise ValueError("SOURCE_IDENTITY_REQUIRED")
        if args.live and (
            not args.approved_rub.is_finite() or not 0 < args.approved_rub <= RUB_CEILING - prior
        ):
            raise ValueError("APPROVAL_LIMIT")
        settings = load_secret(args.secret_file)
        # Exclusive output: an interrupted/unknown run cannot be restarted into the same receipt.
        with args.report.open("x", encoding="utf-8") as output:
            if args.preflight:
                entries = asyncio.run(catalog(settings))
                output.write(
                    json.dumps(
                        {
                            "checked_at": datetime.now(UTC).isoformat(),
                            "source": "PUBLIC_CATALOG",
                            "account_authorization": "NOT_CHECKED",
                            "account_tariff": "NOT_ESTABLISHED_BY_CATALOG",
                            "entries": [
                                {"catalog_entry": e, "catalog_sha256": fingerprint(e)}
                                for e in entries
                            ],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                output.write(
                    json.dumps(
                        {
                            "event": "source",
                            "admission": "SYNTHETIC_EXPERIMENT"
                            if args.synthetic_experiment
                            else "REVIEWED",
                            "runtime_authorized": False,
                            "sha": args.source_sha,
                            "environment": args.source_environment,
                            "approval_ref": args.approval_ref,
                            "prior_confirmed_cost_rub": str(prior),
                            "prefix_receipt_sha256": R1_SHA256 if prefix else None,
                            "evaluator_revision": EVALUATOR_REVISION
                            if args.synthetic_experiment
                            else R1_EVALUATOR_REVISION,
                            "shared_total_budget_rub": str(RUB_CEILING),
                            "stage_approved_rub": str(args.approved_rub),
                            "prior_model_posts": PRIOR_MODEL_POSTS + (14 if prefix else 0),
                        }
                    )
                    + "\n"
                )
                output.flush()
                try:
                    if args.synthetic_experiment:
                        summary = asyncio.run(
                            live(
                                cases,
                                reviews,
                                settings,
                                output,
                                args.approved_rub,
                                synthetic_experiment=True,
                                prefix=prefix,
                            )
                        )
                    else:
                        summary = asyncio.run(
                            live(cases, reviews, settings, output, args.approved_rub)
                        )
                except (
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError,
                    RecursionError,
                    ProviderFailure,
                    TimeoutError,
                ) as exc:
                    output.write(
                        json.dumps(
                            {
                                "event": "stopped",
                                "error": safe_error(exc),
                                "cost_status": "UNKNOWN",
                                "no_automatic_retry": True,
                            }
                        )
                        + "\n"
                    )
                    raise
                if summary["status"] == "FAILED_OR_INCOMPLETE":
                    print("REPORT_WRITTEN / FAILED_OR_INCOMPLETE / NO_AUTOMATIC_RETRY")
                    return 2
        print("REPORT_WRITTEN / NO_RUNTIME_AUTHORIZATION")
        return 0
    except (
        ValueError,
        OSError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        ProviderFailure,
        TimeoutError,
    ) as exc:
        # No path, headers, raw HTTP, exception repr or Pydantic input in terminal logs.
        code = safe_error(exc)
        print(
            f"PROBE_STOPPED / {code}: inspect prerequisites and the existing receipt; no automatic retry"
        )
        return 2


def safe_error(exc: Exception) -> str:
    if isinstance(exc, PolzaFailure):
        return exc.detail
    if isinstance(exc, ProviderFailure):
        return exc.code
    if (
        type(exc) is ValueError
        and len(exc.args) == 1
        and re.fullmatch(r"[A-Z_]{3,60}", str(exc.args[0]))
    ):
        return str(exc.args[0])
    return "INVALID_OR_UNAVAILABLE_INPUT"


if __name__ == "__main__":
    raise SystemExit(main())
