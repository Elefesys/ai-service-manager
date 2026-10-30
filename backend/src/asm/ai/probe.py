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
    Cost,
    GatewayConfig,
    GatewayRequest,
    Limits,
    Message,
    ReadTool,
    ToolResult,
    Usage,
    strict_json,
)
from asm.ai.gateway import ModelGateway, ProviderFailure
from asm.ai.polza import (
    CATALOG,
    CONVERSATION_WIRE_REVISION,
    EXPERIMENT_PROVIDERS,
    GENERATION_ID,
    HISTORY,
    HISTORY_BYTES,
    HISTORY_LIST,
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
DIAGNOSTIC_DECISION = "affe545a468c9ec161421bbd52e6f390f3ad8f2c:M4.2-GEMINI-DIAGNOSTIC-R1"
R2_SOURCE = "cd60e5e16d8bcada53597d660a15f4d82640e956"
R2_ANCHOR = "gen_2227337132904026113"
R2_CATALOG_AT = datetime.fromisoformat("2026-10-30T06:41:00.956181+00:00")
R2_CONFIRMED_RUB = Decimal("0.17509189")
R2_UNKNOWN_RESERVE = Decimal("3.464879664")
DIAGNOSTIC_CEILING = RUB_CEILING - R2_CONFIRMED_RUB - R2_UNKNOWN_RESERVE
HISTORY_RECONCILE_SECONDS = 60.0
HISTORY_RECONCILE_GETS = 4
GEMINI_DIAGNOSTIC_SECONDS = 120.0


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


def catalog_subset(data: Any, models: tuple[str, ...] = MODELS) -> list[dict[str, Any]]:
    """Retain model modalities and complete provider configuration for drift checks."""
    result = []
    for model in models:
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
    settings: ProbeSettings,
    transport: httpx.AsyncBaseTransport | None = None,
    *,
    models: tuple[str, ...] = MODELS,
) -> list[dict[str, Any]]:
    raw = await bounded_http(
        settings.api_key,
        CATALOG,
        body=None,
        seconds=20.0,
        maximum=4 * 1024 * 1024,
        transport=transport,
    )
    selected = catalog_subset(strict_json(raw.decode()), models)
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
                settled = adapter.failure_metering() if response_gw.kind == "ERROR" else None
                if settled:
                    results[-1].update(
                        usage=settled[0].model_dump(),
                        cost=settled[1].model_dump(mode="json"),
                        metering_source="HISTORY_LIST_DETAIL",
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


def diagnostic_budget() -> dict[str, Any]:
    return {
        "shared_budget_rub": str(RUB_CEILING),
        "prior_confirmed_rub": str(R2_CONFIRMED_RUB),
        "prior_confirmed_posts": 30,
        "prior_unknown_posts": 1,
        "prior_unknown_cost_rub": None,
        "prior_unknown_reserved_rub": str(R2_UNKNOWN_RESERVE),
        "remaining_with_unknown_held_rub": str(DIAGNOSTIC_CEILING),
        "automatic_reserve_release": False,
    }


def history_r2_plan() -> dict[str, Any]:
    return {
        "mode": "R2_HISTORY_ONLY",
        "decision": DIAGNOSTIC_DECISION,
        "r2_source_sha": R2_SOURCE,
        "lost_response_id": None,
        "anchor_id": R2_ANCHOR,
        "anchor_model": MODELS[0],
        "anchor_cost_rub": "0.00631386",
        "anchor_usage": [521, 114],
        "stage_from": R2_CATALOG_AT.isoformat(),
        "stage_to": (R2_CATALOG_AT + timedelta(seconds=DURATION)).isoformat(),
        "list_scope": "FIRST_PAGE_5_NEWEST; ANCHOR_MUST_BE_PRESENT; NO_PAGINATION",
        "max_history_gets": HISTORY_RECONCILE_GETS,
        "history_bytes_per_get": HISTORY_BYTES,
        "seconds_per_get": HISTORY_SECONDS,
        "overall_seconds": HISTORY_RECONCILE_SECONDS,
        "model_posts": 0,
        "catalog_gets": 0,
        "reads": 0,
        "correlation": "MODEL_TIME_CANDIDATE_ONLY",
        "signature_shape": "NOT_AVAILABLE_FROM_HISTORY",
        "auto_transition_to_paid": False,
        "runtime_authorized": False,
        **diagnostic_budget(),
    }


def history_time(value: Any) -> datetime:
    if type(value) is not str or len(value) > 40:
        raise ValueError("HISTORY_TIME_INVALID")
    when = datetime.fromisoformat(value)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("HISTORY_TIME_INVALID")
    when = when.astimezone(UTC)
    if not R2_CATALOG_AT <= when < R2_CATALOG_AT + timedelta(seconds=DURATION):
        raise ValueError("HISTORY_TIME_OUTSIDE_STAGE")
    return when


def history_metadata(row: Any, model: str, *, detail: bool = False) -> dict[str, Any]:
    """Closed receipt fields only; account/key names, logs and extra keys are discarded."""
    if (
        type(row) is not dict
        or type(row.get("id")) is not str
        or not re.fullmatch(GENERATION_ID, row["id"])
        or row.get("model", model if detail else None) not in (model, model.split("/", 1)[1])
        or row.get("requestType") != "chat"
        or row.get("status") != "completed"
        or type(row.get("usage")) is not dict
    ):
        raise ValueError("HISTORY_IDENTITY_OR_STATUS_INVALID")
    usage = row["usage"]
    normalized = Usage(
        input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens")
    )
    if (
        normalized.input_tokens is None
        or normalized.output_tokens is None
        or normalized.input_tokens > INPUT_TOKENS
        or normalized.output_tokens > OUTPUT_TOKENS
        or "total_tokens" in usage
        and (
            type(usage["total_tokens"]) is not int
            or usage["total_tokens"] != normalized.input_tokens + normalized.output_tokens
        )
    ):
        raise ValueError("HISTORY_USAGE_INVALID")
    amount = row.get("clientCost" if detail else "cost")
    if type(amount) not in (str, int, float) or ("currency" in row and row["currency"] != "RUB"):
        raise ValueError("HISTORY_COST_UNKNOWN")
    cost = Cost(status="CONFIRMED", amount=Decimal(str(amount)), currency="RUB")
    provider = row.get("finalEndpointSlug" if detail else "provider")
    if type(provider) is not str or not re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,128}", provider):
        raise ValueError("HISTORY_PROVIDER_UNKNOWN")
    stamp = history_time(row.get("createdAt"))
    result = {
        "id": row["id"],
        "model": model,
        "provider_family": provider,
        "created_at": stamp.isoformat(),
        "usage": normalized.model_dump(),
        "cost_rub": str(cost.amount),
        "currency": "RUB",
        "status": "completed",
    }
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if reasoning is not None and (
        type(reasoning) is not int or not 0 <= reasoning <= normalized.output_tokens
    ):
        raise ValueError("HISTORY_REASONING_INVALID")
    result["reasoning_tokens"] = reasoning
    if detail:
        finish = row.get("finishReason")
        end = history_time(row.get("completedAt"))
        if (
            row.get("apiType") not in ("chat_completions", "completions")
            or row.get("responseMode") != "sync"
            or row.get("isCancelled") is not False
            or type(row.get("attemptsCount")) is not int
            or row["attemptsCount"] != 1
            or finish not in ("stop", "tool_calls", "length", "content_filter")
            or end < stamp
            or row.get("parentGenerationId")
            or row.get("serverTools")
            or type(row.get("stepsCount", 1)) is not int
            or row.get("stepsCount", 1) != 1
        ):
            raise ValueError("HISTORY_PROTOCOL_INVALID")
        result.update(completed_at=end.isoformat(), finish_reason=finish, attempts_count=1)
    return result


def match_history_pair(listed: dict[str, Any], detail: dict[str, Any]) -> None:
    for key in (
        "id",
        "model",
        "provider_family",
        "created_at",
        "usage",
        "cost_rub",
        "currency",
        "status",
    ):
        # Decimal normalization permits 0.001 and 0.0010 without changing the amount.
        if (
            Decimal(listed[key]) != Decimal(detail[key])
            if key == "cost_rub"
            else listed[key] != detail[key]
        ):
            raise ValueError("HISTORY_LIST_DETAIL_MISMATCH")
    if (
        listed["reasoning_tokens"] is not None
        and listed["reasoning_tokens"] != detail["reasoning_tokens"]
    ):
        raise ValueError("HISTORY_LIST_DETAIL_MISMATCH")


async def reconcile_r2_history(
    settings: ProbeSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "event": "history_reconciliation",
        **history_r2_plan(),
        "status": "UNKNOWN",
        "r2_charge_status": "UNKNOWN",
        "r2_charge_rub": None,
        "history_gets": 0,
        "candidate": None,
        "anchor": None,
        "candidate_is_exact_response_correlation": False,
    }
    deadline = time.monotonic() + HISTORY_RECONCILE_SECONDS

    async def get(url: str) -> Any:
        remaining = deadline - time.monotonic()
        if result["history_gets"] >= HISTORY_RECONCILE_GETS or remaining <= 0:
            raise ValueError("HISTORY_GET_OR_DEADLINE_LIMIT")
        result["history_gets"] += 1
        raw = await bounded_http(
            settings.api_key,
            url,
            body=None,
            seconds=min(HISTORY_SECONDS, remaining),
            maximum=HISTORY_BYTES,
            transport=transport,
        )
        if settings.api_key.get_secret_value().encode() in raw:
            raise ValueError("HISTORY_PRIVATE_DATA")
        data = strict_json(raw.decode())
        if settings.api_key.get_secret_value() in json.dumps(data, ensure_ascii=False):
            raise ValueError("HISTORY_PRIVATE_DATA")
        return data

    try:
        async with asyncio.timeout(HISTORY_RECONCILE_SECONDS):
            listing = await get(HISTORY_LIST)
            items = listing["items"]
            if type(items) is not list or len(items) > 5 or any(type(r) is not dict for r in items):
                raise ValueError("HISTORY_LIST_INVALID")
            if "meta" in listing and (
                listing["meta"].get("page") != 1 or listing["meta"].get("limit") != 5
            ):
                raise ValueError("HISTORY_PAGE_INVALID")
            identifiers = [r.get("id") for r in items]
            if any(
                type(v) is not str or not re.fullmatch(GENERATION_ID, v) for v in identifiers
            ) or len(set(identifiers)) != len(items):
                raise ValueError("HISTORY_IDS_INVALID")
            anchors = [r for r in items if r["id"] == R2_ANCHOR]
            if len(anchors) != 1:
                raise ValueError("HISTORY_ANCHOR_ABSENT")
            anchor = history_metadata(anchors[0], MODELS[0])
            if (
                Decimal(anchor["cost_rub"]) != Decimal("0.00631386")
                or anchor["usage"] != {"input_tokens": 521, "output_tokens": 114}
                or anchor["provider_family"] != "OpenAI"
            ):
                raise ValueError("HISTORY_ANCHOR_MISMATCH")
            # Only rows newer than the known anchor can be the missing request.
            # Older rows need not be in the stage; no omitted later page can add a newer candidate.
            stamps = [datetime.fromisoformat(r["createdAt"]) for r in items]
            if any(t.tzinfo is None or t.utcoffset() is None for t in stamps) or stamps != sorted(
                stamps, reverse=True
            ):
                raise ValueError("HISTORY_ORDER_INVALID")
            candidates = [
                r
                for r, t in zip(items, stamps, strict=True)
                if r.get("model") in (MODELS[1], MODELS[1].split("/", 1)[1])
                and history_time(anchor["created_at"])
                < t
                < R2_CATALOG_AT + timedelta(seconds=DURATION)
            ]
            if len(candidates) != 1:
                raise ValueError("HISTORY_NO_CANDIDATE" if not candidates else "HISTORY_AMBIGUOUS")
            candidate = history_metadata(candidates[0], MODELS[1])
            candidate_detail = history_metadata(
                await get(HISTORY + "/" + candidate["id"]), MODELS[1], detail=True
            )
            match_history_pair(candidate, candidate_detail)
            anchor_detail = history_metadata(
                await get(HISTORY + "/" + R2_ANCHOR), MODELS[0], detail=True
            )
            match_history_pair(anchor, anchor_detail)
            if anchor_detail["finish_reason"] != "stop" or history_time(
                candidate_detail["created_at"]
            ) < history_time(anchor_detail["completed_at"]):
                raise ValueError("HISTORY_ANCHOR_ORDER_MISMATCH")
            result.update(
                status="CANDIDATE_REQUIRES_C0",
                candidate=candidate_detail,
                anchor=anchor_detail,
                candidate_evidence="HISTORY_LIST_DETAIL / MODEL_TIME_ONLY",
                candidate_within_old_reserve=Decimal(candidate_detail["cost_rub"])
                <= R2_UNKNOWN_RESERVE,
                model_evidence="LIST_MODEL_WITH_EXACT_DETAIL_ID; OPTIONAL_DETAIL_MODEL_CHECKED",
            )
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        InvalidOperation,
        RecursionError,
        ProviderFailure,
        TimeoutError,
    ) as exc:
        result["error"] = "HISTORY_DEADLINE" if isinstance(exc, TimeoutError) else safe_error(exc)
    return result


def gemini_diagnostic_plan(
    cases: tuple[Case, ...], review: SyntheticRoute | None = None
) -> dict[str, Any]:
    if fingerprint([c.model_dump(mode="json") for c in cases]) != FIXTURE_SHA256:
        raise ValueError("EXPERIMENT_FIXTURES_CHANGED")
    if review is not None and review.model != MODELS[1]:
        raise ValueError("DIAGNOSTIC_MODEL_MISMATCH")
    reserve = review.reservation() if review else None
    if reserve is not None and reserve > DIAGNOSTIC_CEILING:
        raise ValueError("PLAN_EXCEEDS_CEILING")
    return {
        "mode": "GEMINI_PROTOCOL_DIAGNOSTIC",
        "status": "PLAN_ONLY / PAID_NOT_AUTHORIZED",
        "decision": DIAGNOSTIC_DECISION,
        "model": MODELS[1],
        "provider_only": EXPERIMENT_PROVIDERS[1],
        "case": "tool_current",
        "repeat": 0,
        "fixture_sha256": FIXTURE_SHA256,
        "profile": "PROVIDER_DEFAULT / TRANSIENT_GOOGLE_SIGNATURE",
        "route": review.metadata() if review else None,
        "max_model_posts": 1,
        "max_catalog_gets": 1,
        "max_exact_id_history_gets": 2,
        "reads": 0,
        "followup_posts": 0,
        "gpt_posts": 0,
        "roundtrip_pass": False,
        "input_tokens": INPUT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "input_bytes": INPUT_BYTES,
        "output_bytes": OUTPUT_BYTES,
        "case_seconds": CASE_SECONDS,
        "overall_seconds": GEMINI_DIAGNOSTIC_SECONDS,
        "history_bytes_per_get": HISTORY_BYTES,
        "history_seconds_per_post": HISTORY_SECONDS,
        "priced_reservation_rub": str(reserve) if reserve is not None else None,
        "billing_status": "CONDITIONAL_ESTIMATE",
        "runtime_authorized": False,
        "live_requires_separate_c0_decision": True,
        **diagnostic_budget(),
    }


def write_metadata(output: TextIO, value: dict[str, Any]) -> None:
    output.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    output.flush()


async def run_gemini_diagnostic(
    cases: tuple[Case, ...],
    settings: ProbeSettings,
    output: TextIO,
    approved: Decimal,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    gemini_diagnostic_plan(cases)
    if not approved.is_finite() or not 0 < approved <= DIAGNOSTIC_CEILING:
        raise ValueError("APPROVAL_LIMIT")
    deadline = time.monotonic() + GEMINI_DIAGNOSTIC_SECONDS
    async with asyncio.timeout(GEMINI_DIAGNOSTIC_SECONDS):
        entries = await catalog(settings, transport, models=(MODELS[1],))
        review = SyntheticRoute.from_catalog(entries[0], datetime.now(UTC))
        proposal = gemini_diagnostic_plan(cases, review)
        write_metadata(
            output, {"event": "diagnostic_plan", **proposal, "approved_rub": str(approved)}
        )
        reserve = review.reservation()
        if reserve > approved:
            raise ValueError("APPROVED_BUDGET_TOO_SMALL")
        case = next(c for c in cases if c.id == "tool_current")
        adapter = PolzaAdapter(review, settings.api_key, transport=transport)
        config = configuration(review, case)
        # Keep the original Gateway tool validation, which requires continuation
        # capacity. This finite diagnostic invokes call() exactly once, reserves
        # only that POST and never creates a ToolResult or performs another call.
        request = GatewayRequest(
            run_id="tool_current_0",
            deadline=datetime.now(UTC)
            + timedelta(seconds=min(CASE_SECONDS, deadline - time.monotonic())),
            messages=(
                Message(role="context", text=case.context),
                Message(role="user", text=case.question),
            ),
            tools=(
                ReadTool(
                    name="read_current",
                    revision="synthetic_v1",
                    description="Read only the current synthetic fixture fact.",
                    arguments=ReadArgs,
                    result=ReadResult,
                ),
            ),
        )
        gateway = ModelGateway(config, request, adapter)
        write_metadata(
            output,
            {
                "event": "reserved",
                "model": MODELS[1],
                "case": case.id,
                "repeat": 0,
                "calls_reserved": 1,
                "rub_reserved": str(reserve),
                "cost_status": "UNKNOWN",
                "shared_rub_committed_or_reserved": str(
                    R2_CONFIRMED_RUB + R2_UNKNOWN_RESERVE + reserve
                ),
            },
        )
        usage, cost = Usage(), Cost()
        kind: str = "ERROR"
        error: str | None = None
        try:
            response = await gateway.call()
            kind, error, usage, cost = response.kind, response.error, response.usage, response.cost
            settled = adapter.failure_metering() if kind == "ERROR" else None
            if settled:
                usage, cost = settled
        except asyncio.CancelledError:
            error = "CANCELLED"
        finally:
            adapter.clear_continuation()
        call = {
            "kind": kind,
            "error": error,
            "usage": usage.model_dump(),
            "cost": cost.model_dump(mode="json"),
            "metering_source": "HISTORY_LIST_DETAIL" if cost.status == "CONFIRMED" else "UNKNOWN",
            **adapter.observation,
        }
        failures = metering_failures(call, review)
        if error or kind != "TOOLS":
            failures.append(error or "DIAGNOSTIC_TOOLS_NOT_OBSERVED")
        known = cost.status == "CONFIRMED"
        expense = cost.amount if cost.amount is not None else Decimal(0)
        unknown_reserve = Decimal(0) if known else reserve
        result = {
            "event": "gemini_diagnostic",
            "model": MODELS[1],
            "case": case.id,
            "repeat": 0,
            "status": "TECHNICAL_FAILURE" if failures else "TOOLS_OBSERVED / ROUNDTRIP_NOT_RUN",
            "failures": sorted(set(failures)),
            "call": call,
            "attempt_reservations": 1,
            "reads": 0,
            "followup_posts": 0,
            "roundtrip_pass": False,
            "runtime_authorized": False,
            "new_confirmed_cost_rub": str(expense),
            "new_known_call_count": int(known),
            "new_unknown_call_count": int(not known),
            "shared_known_call_count": 30 + int(known),
            "shared_unknown_call_count": 1 + int(not known),
            "new_unknown_cost_rub": None if not known else "0",
            "new_unknown_reserved_rub": str(unknown_reserve),
            "shared_confirmed_cost_rub": str(R2_CONFIRMED_RUB + expense),
            "shared_unknown_reserved_rub": str(R2_UNKNOWN_RESERVE + unknown_reserve),
            "remaining_with_unknown_held_rub": str(DIAGNOSTIC_CEILING - expense - unknown_reserve),
            "old_unknown_reserve_released": False,
            "selected_model": None,
        }
        write_metadata(output, result)
        return result


def diagnostic_main(args: argparse.Namespace) -> int:
    if args.review or args.continue_from or args.synthetic_experiment or args.preflight:
        raise ValueError("DIAGNOSTIC_MODE_CONFLICT")
    if args.history_r2 and (args.live or args.approved_rub is not None or args.approval_ref):
        raise ValueError("HISTORY_MODE_CANNOT_SPEND")
    cases = load_cases(args.fixtures) if args.gemini_diagnostic else ()
    proposal = gemini_diagnostic_plan(cases) if args.gemini_diagnostic else history_r2_plan()
    if args.plan or args.gemini_diagnostic and not args.live:
        print(json.dumps(proposal, ensure_ascii=False, indent=2))
        return 0
    if (
        not args.report
        or not re.fullmatch(r"[0-9a-f]{40}", args.source_sha or "")
        or not args.source_environment
    ):
        raise ValueError("SOURCE_AND_EXCLUSIVE_REPORT_REQUIRED")
    if args.gemini_diagnostic and (
        not args.approval_ref
        or not args.approval_ref.startswith("C0-M4.2-GEMINI-DIAGNOSTIC-R1:" + args.source_sha + ":")
        or args.approved_rub is None
        or not args.approved_rub.is_finite()
        or not 0 < args.approved_rub <= DIAGNOSTIC_CEILING
    ):
        raise ValueError("SEPARATE_DIAGNOSTIC_APPROVAL_REQUIRED")
    with args.report.open("x", encoding="utf-8") as output:
        settings = load_secret(args.secret_file)
        write_metadata(
            output,
            {
                "event": "source",
                "mode": proposal["mode"],
                "sha": args.source_sha,
                "environment": args.source_environment,
                "decision": DIAGNOSTIC_DECISION,
                "approval_ref": args.approval_ref,
                "runtime_authorized": False,
            },
        )
        if args.history_r2:
            result = asyncio.run(reconcile_r2_history(settings))
            write_metadata(output, result)
            print("REPORT_WRITTEN / " + result["status"] + " / NO_PAID_TRANSITION")
            return 0 if result["status"] == "CANDIDATE_REQUIRES_C0" else 2
        try:
            result = asyncio.run(run_gemini_diagnostic(cases, settings, output, args.approved_rub))
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RecursionError,
            ProviderFailure,
            TimeoutError,
        ) as exc:
            write_metadata(
                output,
                {
                    "event": "stopped",
                    "error": safe_error(exc),
                    "cost_status": "UNKNOWN",
                    "no_automatic_retry": True,
                    "runtime_authorized": False,
                },
            )
            raise
        print("REPORT_WRITTEN / " + result["status"] + " / NO_READ_OR_FOLLOWUP")
        return 2 if result["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--synthetic-experiment", action="store_true")
    diagnostic_mode = parser.add_mutually_exclusive_group()
    diagnostic_mode.add_argument("--history-r2", action="store_true")
    diagnostic_mode.add_argument("--gemini-diagnostic", action="store_true")
    parser.add_argument("--continue-from", type=Path)
    parser.add_argument("--secret-file", type=Path, default=Path(".env.m4-probe"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--approval-ref")
    parser.add_argument("--approved-rub", type=Decimal)
    parser.add_argument("--source-sha")
    parser.add_argument("--source-environment", choices=("LOCAL_DESKTOP", "LOCAL_BACKEND"))
    args = parser.parse_args(argv)
    try:
        if args.history_r2 or args.gemini_diagnostic:
            return diagnostic_main(args)
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
