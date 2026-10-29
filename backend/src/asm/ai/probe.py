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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, TextIO

import httpx
from PIL import Image
from pydantic import Field, TypeAdapter, ValidationError

from asm.ai.contracts import (
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
    INPUT_BYTES,
    INPUT_TOKENS,
    MODELS,
    OUTPUT_BYTES,
    OUTPUT_TOKENS,
    OVERHEAD_TOKENS,
    PolzaAdapter,
    PolzaFailure,
    RouteReview,
    bounded_http,
    encode,
    fingerprint,
)
from asm.ai.settings import ProbeSettings, load_secret

FIXTURES = Path("tests/fixtures/m4_probe_cases.json")
CALL_CEILING = 81
RUB_CEILING = Decimal(150)
DURATION = 1800.0
CASE_SECONDS = 60.0
REPEATS = ("unknown_price", "unknown_booking", "injection")


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


def validate_reviews(reviews: tuple[RouteReview, ...]) -> None:
    if tuple(r.model for r in reviews) != MODELS:
        raise ValueError("EXACT_THREE_MODELS_REQUIRED")
    for review in reviews:
        review.fresh()
        review.route()
        review.reservation()


def plan(cases: tuple[Case, ...], reviews: tuple[RouteReview, ...] = ()) -> dict[str, Any]:
    if reviews:
        validate_reviews(reviews)
    rows = schedule(cases)
    calls = sum(c.max_calls for c in rows)
    total_calls = calls * len(MODELS)
    total = sum((r.reservation() * calls for r in reviews), Decimal(0)) if reviews else None
    if total_calls > CALL_CEILING or total is not None and total > RUB_CEILING:
        raise ValueError("PLAN_EXCEEDS_CEILING")
    return {
        "status": "REVIEW / PAID PROBE NOT RUN",
        "fixture_sha256": fingerprint([c.model_dump(mode="json") for c in cases]),
        "models": MODELS,
        "cases_per_model": len(rows),
        "total_scenarios": len(rows) * len(MODELS),
        "base_text_per_model": 20,
        "critical_repeats_per_model": len(REPEATS),
        "images_per_model": 2,
        "max_model_http_calls": total_calls,
        "hard_call_ceiling": CALL_CEILING,
        "max_synthetic_reads": sum(c.mode == "tool" for c in rows) * len(MODELS),
        "input_tokens_per_call": INPUT_TOKENS,
        "output_tokens_per_call": OUTPUT_TOKENS,
        "total_token_reservation_ceiling": total_calls * (INPUT_TOKENS + OUTPUT_TOKENS),
        "wire_input_bytes_per_call": INPUT_BYTES,
        "wire_output_bytes_per_call": OUTPUT_BYTES,
        "case_seconds": CASE_SECONDS,
        "overall_seconds": DURATION,
        "catalog_http_calls": 1,
        "proposed_rub_ceiling": str(RUB_CEILING),
        "priced_reservation_rub": str(total) if total is not None else None,
        "billing_status": "REVIEWED_BOUND"
        if reviews
        else "UNKNOWN: account tariff and route review required",
        "prompt_revision": "conversation_v1",
        "schema_revision": "conversation_result_v1",
        "wire_schema_revision": CONVERSATION_WIRE_REVISION,
        "reviewed_routes": [r.metadata() for r in reviews],
        "image_revision": "synthetic_shapes_v1/EVAL_ONLY",
    }


def catalog_subset(data: Any) -> list[dict[str, Any]]:
    """Copy only documented routing/tariff/capability fields for these exact models."""
    result = []
    for model in MODELS:
        matches = [m for m in data["data"] if m.get("id") == model]
        if len(matches) != 1:
            raise ValueError("MODEL_UNAVAILABLE")
        item = matches[0]
        providers = []
        for p in item.get("providers", []):
            providers.append(
                {
                    k: p[k]
                    for k in (
                        "name",
                        "is_unofficial",
                        "pricing",
                        "supported_parameters",
                        "capabilities",
                        "context_length",
                        "max_completion_tokens",
                        "per_request_limits",
                        "reasoning",
                    )
                    if k in p
                }
            )
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

    def __init__(self, output: TextIO, approved: Decimal, calls: int) -> None:
        if (
            not approved.is_finite()
            or not 0 < approved <= RUB_CEILING
            or not 0 < calls <= CALL_CEILING
        ):
            raise ValueError("APPROVAL_LIMIT")
        self.output = output
        self.approved = approved
        self.ceiling = calls
        self.calls = 0
        self.reserved = Decimal(0)
        self.deadline = time.monotonic() + DURATION

    def record(self, value: dict[str, Any]) -> None:
        self.output.write(json.dumps(value, ensure_ascii=False) + "\n")
        self.output.flush()

    def reserve(self, review: RouteReview, case: Case, repeat: int) -> None:
        amount = review.reservation()
        if (
            time.monotonic() >= self.deadline
            or self.calls >= self.ceiling
            or self.reserved + amount > self.approved
        ):
            raise ValueError("GLOBAL_BUDGET_EXHAUSTED")
        self.calls += 1
        self.reserved += amount
        self.record(
            {
                "event": "reserved",
                "model": review.model,
                "case": case.id,
                "repeat": repeat,
                "calls_reserved": self.calls,
                "rub_reserved": str(self.reserved),
                "cost_status": "UNKNOWN",
            }
        )


def configuration(review: RouteReview, case: Case) -> GatewayConfig:
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


def metering_failures(result: dict[str, Any], review: RouteReview) -> list[str]:
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
    review = adapter.review
    results: list[dict[str, Any]] = []
    final: dict[str, Any] | None = None
    failures: list[str] = []
    reads = 0
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
            response = await adapter.image_probe(
                body, min(CASE_SECONDS, ledger.deadline - time.monotonic())
            )
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
                if image_result != case.image_expected:
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
                deadline=datetime.now(UTC) + timedelta(seconds=CASE_SECONDS),
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
            failures.extend(evaluate(case, final, reads))
        for result in results:
            failures.extend(metering_failures(result, review))
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
    return {
        "event": "case",
        "model": review.model,
        "upstream": review.response_provider,
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
        "assessment": "FAIL" if failures else "AUTOMATED_CHECKS_PASS / HUMAN_REVIEW_REQUIRED",
    }


def summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
        "limitation": "Small synthetic sample; review every final output against fixtures before selection. No runtime authorization.",
    }


async def live(
    cases: tuple[Case, ...],
    reviews: tuple[RouteReview, ...],
    settings: ProbeSettings,
    output: TextIO,
    approved: Decimal,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    if not reviews:
        raise ValueError("EXACT_THREE_MODELS_REQUIRED")
    proposal = plan(cases, reviews)
    ledger = Ledger(output, approved, proposal["max_model_http_calls"])
    if Decimal(proposal["priced_reservation_rub"]) > approved:
        raise ValueError("APPROVED_BUDGET_TOO_SMALL")
    current = await catalog(settings, transport)
    for review, entry in zip(reviews, current, strict=True):
        review.fresh()
        if fingerprint(entry) != review.catalog_sha256:
            raise ValueError("CATALOG_CHANGED")
    ledger.record(
        {
            "event": "plan",
            **proposal,
            "status": "SYNTHETIC_EVAL_ONLY",
            "route_reviews": [r.catalog_sha256 for r in reviews],
            "approved_rub": str(approved),
        }
    )
    rows = []
    for review in reviews:
        adapter = PolzaAdapter(review, settings.api_key, transport=transport)
        for repeat, case in enumerate(schedule(cases)):
            remaining = ledger.deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("GLOBAL_DEADLINE")
            async with asyncio.timeout(remaining):
                row = await run_case(adapter, case, ledger, repeat)
            ledger.record(row)
            rows.append(row)
            # All contract/usage/cost/quality failures stop spending, never averaged away.
            if row["failures"]:
                summary = summaries(rows)
                ledger.record(summary)
                return summary
    summary = summaries(rows)
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
    parser.add_argument("--secret-file", type=Path, default=Path(".env.m4-probe"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--approval-ref")
    parser.add_argument("--approved-rub", type=Decimal)
    parser.add_argument("--source-sha")
    parser.add_argument("--source-environment", choices=("LOCAL_DESKTOP", "LOCAL_BACKEND"))
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.fixtures)
        reviews = read_reviews(args.review) if args.review else ()
        if not args.preflight and not args.live:
            print(json.dumps(plan(cases, reviews), ensure_ascii=False, indent=2))
            return 0
        if not args.approval_ref or not args.report:
            raise ValueError("EXPLICIT_APPROVAL_AND_NEW_REPORT_REQUIRED")
        if args.live and (len(reviews) != len(MODELS) or args.approved_rub is None):
            raise ValueError("REVIEW_AND_BUDGET_REQUIRED")
        if args.live and (
            not re.fullmatch(r"[0-9a-f]{40}", args.source_sha or "") or not args.source_environment
        ):
            raise ValueError("SOURCE_IDENTITY_REQUIRED")
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
                            "sha": args.source_sha,
                            "environment": args.source_environment,
                            "approval_ref": args.approval_ref,
                        }
                    )
                    + "\n"
                )
                output.flush()
                try:
                    summary = asyncio.run(live(cases, reviews, settings, output, args.approved_rub))
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
