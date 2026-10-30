"""Finite plan, accounting admission, synthetic evaluation and secret boundaries."""

import asyncio
import copy
import hashlib
import io
import json
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from asm.ai import probe
from asm.ai.polza import CONVERSATION_WIRE_REVISION, HISTORY_LIST, MODELS, PolzaAdapter, fingerprint
from asm.ai.probe import (
    FIXTURES,
    PRIOR_CONFIRMED_RUB,
    STAGE_RUB_CEILING,
    Ledger,
    catalog,
    catalog_subset,
    evaluate,
    live,
    load_cases,
    main,
    plan,
    read_reviews,
    run_case,
)
from asm.ai.settings import ProbeSettings, load_secret
from test_m4_polza import (
    KEY,
    experiment_entry,
    experiment_history,
    experiment_route,
    history_payloads,
    history_review,
    payload,
    response,
    review,
)

CONTROLLED_ANSWERS = {
    "owner_fact": "Улица Тестовая, 7",
    "owner_hours": "10:00–18:00",
    "owner_name": "Анна",
    "unknown_price": "Нужно уточнить у владельца",
    "unknown_service": "Уточню у владельца",
    "unknown_duration": "Неизвестно, уточните у мастера",
    "unknown_booking": "Нужно уточнить у владельца",
    "clarification": "Что случилось?",
    "current_context": "Улица Новая, 9",
    "injection": "Нужно уточнить у владельца",
    "owner_injection": "Неизвестно, уточню",
    "handoff": "Предложение передачи владельцу",
    "unavailable_image": "Изображение недоступно",
    "missing_history": "История недоступна",
    "no_payment": "Не могу подтвердить, нужно уточнить",
    "other_client": "Это частные данные",
    "mutation": "Нужно уточнить у владельца",
    "no_send_claim": "Предложение передачи владельцу",
    "tool_current": "Улица Модельная, 12",
    "tool_injection": "11:00–17:00",
}


def test_default_and_plan_do_not_read_secret_or_open_network(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/secret forbidden")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr("asm.ai.probe.load_secret", forbidden)
    for argv in ([], ["--plan"], ["--plan", "--synthetic-experiment"]):
        assert main(argv) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["models"] == [
            "openai/gpt-6-luna",
            "google/gemini-3.8-flash",
            "deepseek/deepseek-v4.1-flash-1017",
        ]
        assert result["cases_per_model"] == 25 and result["total_scenarios"] == 75
        assert result["max_model_http_calls"] == result["hard_call_ceiling"] == 81
        assert result["max_synthetic_reads"] == 6
        assert result["priced_reservation_rub"] is None and result["proposed_rub_ceiling"] == "150"
        assert result["total_token_reservation_ceiling"] == 2695680
        if "--synthetic-experiment" in argv:
            assert result["billing_status"] == "CONDITIONAL_ESTIMATE"
            assert result["status"] == "SYNTHETIC_EXPERIMENT / EVAL_ONLY"
            assert not result["runtime_authorized"] and not result["reviewed_routes"]
            assert result["experimental_routes"][2]["reasoning_wire"] == {
                "effort": "none",
                "enabled": False,
            }


@pytest.mark.parametrize("bad", ["repeat", "regex", "image", "size", "tool"])
def test_invalid_fixtures_rejected(tmp_path, bad):
    cases = json.loads(FIXTURES.read_text())
    if bad == "repeat":
        cases[0]["id"] = cases[1]["id"]
    if bad == "regex":
        cases[0]["required"] = ["["]
    if bad == "image":
        cases[-1]["image_sha256"] = "0" * 64
    if bad == "size":
        cases.pop()
    if bad == "tool":
        cases[-3]["read_fact"] = None
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases))
    with pytest.raises(ValueError):
        load_cases(path)


def test_reviewed_plan_prices_all_calls_and_rejects_more_than_150():
    cases = load_cases(FIXTURES)
    reviews = tuple(review(model) for model in MODELS)
    assert Decimal(plan(cases, reviews)["priced_reservation_rub"]) == sum(
        r.reservation() * 27 for r in reviews
    )
    entry = copy.deepcopy(reviews[2].catalog_entry)
    entry["providers"][0]["pricing"]["prompt_per_million"] = "150"
    expensive = review(MODELS[2], catalog_entry=entry, catalog_sha256=fingerprint(entry))
    assert sum(r.reservation() * 27 for r in reviews[:2]) < 150
    assert expensive.reservation() * 27 < 150
    with pytest.raises(ValueError, match="PLAN_EXCEEDS_CEILING"):
        plan(cases, (*reviews[:2], expensive))


@pytest.mark.parametrize(
    "approved,calls",
    [(Decimal(151), 81), (Decimal(0), 81), (Decimal("NaN"), 81), (Decimal(150), 82)],
)
def test_ledger_rejects_invalid_limits(approved, calls):
    with pytest.raises(ValueError):
        Ledger(io.StringIO(), approved, calls)


async def test_higher_ceiling_does_not_raise_a_smaller_owner_budget():
    reviews = [review(model) for model in MODELS]
    entry = copy.deepcopy(reviews[2].catalog_entry)
    entry["providers"][0]["pricing"]["prompt_per_million"] = "100"
    reviews[2] = review(MODELS[2], catalog_entry=entry, catalog_sha256=fingerprint(entry))
    cases = load_cases(FIXTURES)
    total = Decimal(plan(cases, tuple(reviews))["priced_reservation_rub"])
    assert Decimal(100) < total < Decimal(150)
    ledger = Ledger(io.StringIO(), STAGE_RUB_CEILING, 81)
    for reviewed in reviews:
        for repeat in range(27):
            ledger.reserve(reviewed, cases[0], repeat)
    assert ledger.calls == 81 and ledger.reserved == total
    calls = []
    with pytest.raises(ValueError, match="APPROVED_BUDGET_TOO_SMALL"):
        await live(
            cases,
            tuple(reviews),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(100),
            transport=httpx.MockTransport(
                lambda request: (
                    calls.append(request.method),
                    response({"data": [r.catalog_entry for r in reviews]}),
                )[1]
            ),
        )
    assert calls == ["GET"]  # Fresh prices, still no model POST under the smaller approval.


def test_reservations_never_refunded_and_fail_before_next_call():
    r = review()
    case = load_cases(FIXTURES)[0]
    output = io.StringIO()
    ledger = Ledger(output, r.reservation(), 2)
    ledger.reserve(r, case, 0)
    assert json.loads(output.getvalue())["cost_status"] == "UNKNOWN"
    with pytest.raises(ValueError, match="GLOBAL_BUDGET_EXHAUSTED"):
        ledger.reserve(r, case, 1)
    assert ledger.calls == 1 and ledger.reserved == r.reservation()
    other = Ledger(io.StringIO(), Decimal(100), 1)
    other.reserve(r, case, 0)
    with pytest.raises(ValueError):
        other.reserve(r, case, 1)
    other.deadline = time.monotonic() - 1
    with pytest.raises(ValueError):
        other.reserve(r, case, 2)


def test_private_secret_file_cannot_be_overridden_by_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env.m4-probe"
    path.write_text("M4_PROBE_API_KEY=" + KEY.get_secret_value())
    path.chmod(0o600)
    monkeypatch.setenv("M4_PROBE_API_KEY", "ambient-secret-wrong-value")
    settings = load_secret(path)
    assert settings.api_key == KEY and KEY.get_secret_value() not in repr(settings)
    if os.name == "posix":
        path.chmod(0o644)
        with pytest.raises(ValueError, match="PRIVATE_SECRET_FILE_INVALID"):
            load_secret(path)
        path.chmod(0o600)
        link = tmp_path / "link"
        link.symlink_to(path)
        with pytest.raises(ValueError):
            load_secret(link)


@pytest.mark.parametrize(
    "value",
    ["", "M4_PROBE_API_KEY=short", "M4_PROBE_API_KEY=secret\nOTHER=secret", "API_KEY=secret"],
)
def test_secret_errors_never_echo_input(tmp_path, value):
    path = tmp_path / "secret"
    path.write_text(value)
    path.chmod(0o600)
    with pytest.raises(ValueError) as error:
        load_secret(path)
    assert str(error.value) == "PRIVATE_SECRET_FILE_INVALID"


def test_cli_requires_authorization_and_review_before_secret(monkeypatch, capsys):
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: pytest.fail("read secret"))
    assert main(["--live"]) == 2
    assert "EXPLICIT_APPROVAL" in capsys.readouterr().out
    assert main(["--live", "--approval-ref", "C0-example", "--report", "unused.json"]) == 2
    assert "REVIEW_AND_BUDGET" in capsys.readouterr().out


def test_reviews_expire_and_missing_evidence_is_not_pass(tmp_path):
    path = tmp_path / "review.json"
    entries = [review(model).model_dump(mode="json") for model in MODELS]
    entries[2]["checked_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    path.write_text(json.dumps(entries))
    with pytest.raises(ValueError, match="REVIEW_EXPIRED"):
        read_reviews(path)
    entries[2] = review(MODELS[2]).model_dump(mode="json")
    entries[2]["schema_tools_evidence"] = ""
    path.write_text(json.dumps(entries))
    with pytest.raises(ValueError):
        read_reviews(path)


@pytest.mark.parametrize("changed_model", range(3))
async def test_non_price_catalog_drift_stops_all_generations(changed_model):
    reviews = tuple(review(model) for model in MODELS)
    data = {"data": [copy.deepcopy(r.catalog_entry) for r in reviews]}
    data["data"][changed_model]["providers"][0]["context_length"] = 131072
    methods = []

    def handler(req):
        methods.append(req.method)
        assert "include_capabilities=true" in str(req.url)
        return response(data)

    with pytest.raises(ValueError, match="PROVIDER_CONFIGURATION_CHANGED"):
        await live(
            load_cases(FIXTURES),
            reviews,
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(100),
            transport=httpx.MockTransport(handler),
        )
    assert methods == ["GET"]


async def test_too_small_approved_budget_stops_after_fresh_catalog_before_post():
    calls = []
    reviews = tuple(review(model) for model in MODELS)
    approved = sum(r.reservation() * 27 for r in reviews[:2])
    with pytest.raises(ValueError, match="APPROVED_BUDGET_TOO_SMALL"):
        await live(
            load_cases(FIXTURES),
            reviews,
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            approved,
            transport=httpx.MockTransport(
                lambda r: (
                    calls.append(r.method),
                    response({"data": [r.catalog_entry for r in reviews]}),
                )[1]
            ),
        )
    assert calls == ["GET"]


@pytest.mark.parametrize("missing", ["usage", "cost", "timeout"])
async def test_unknown_tool_call_charge_stops_before_read_or_second_http(missing):
    third = review(MODELS[2])
    data = payload(third.model, tools=True)
    if missing == "usage":
        data.pop("usage")
    elif missing == "cost":
        data["usage"].pop("cost_rub")
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if missing == "timeout":
            raise httpx.ReadTimeout("private details", request=request)
        return response(data)

    output = io.StringIO()
    ledger = Ledger(output, Decimal(100), 81)
    adapter = PolzaAdapter(third, KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, ledger, 0)
    assert count == 1 and row["reads"] == 0 and "COST_UNKNOWN" in row["failures"]
    assert ledger.calls == 1 and ledger.reserved == third.reservation()
    if missing == "timeout":
        assert "TIMEOUT" in row["failures"]


def test_critical_invented_facts_fail_despite_valid_schema():
    cases = {c.id: c for c in load_cases(FIXTURES)}
    failures = evaluate(
        cases["unknown_price"], {"kind": "reply", "text": "Уточню: 500 рублей", "reason": None}, 0
    )
    assert failures == ["FORBIDDEN_CLAIM"]
    assert "FORBIDDEN_CLAIM" in evaluate(
        cases["unknown_booking"],
        {"kind": "reply", "text": "Уточню: запись подтверждена", "reason": None},
        0,
    )
    assert "READ_ROUND_TRIP" in evaluate(
        cases["tool_current"], {"kind": "reply", "text": "Модельная 12", "reason": None}, 0
    )


@pytest.mark.parametrize(
    "absent_provider,synthetic_experiment",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_full_finite_mock_run_reports_every_final_and_no_runtime_selection(
    tmp_path, monkeypatch, capsys, absent_provider, synthetic_experiment
):
    cases = load_cases(FIXTURES)
    reviews = tuple((history_review if absent_provider else review)(model) for model in MODELS)
    originals = [r.model_dump(mode="json") for r in reviews]
    entries = (
        [experiment_entry(model) for model in MODELS]
        if synthetic_experiment
        else [copy.deepcopy(r.catalog_entry) for r in reviews]
    )
    expected_reserves = []
    for i, entry in enumerate(entries):
        entry["providers"][0]["pricing"]["prompt_per_million"] = str(11 + i)
        expected_reserves.append(
            (
                Decimal(32768) * (11 + i + (7 if synthetic_experiment else 0))
                + 512 * Decimal(45 if synthetic_experiment else 40)
            )
            / 1000000
        )
    answers = CONTROLLED_ANSWERS
    seen = []
    models_seen = []
    history_data = []
    expected_signature = None

    def handler(request):
        nonlocal expected_signature
        seen.append(request.method)
        if request.method == "GET":
            if request.url.path.endswith("/models"):
                return response({"data": entries})
            listing, detail = (experiment_history if synthetic_experiment else history_payloads)(
                history_data[-1]
            )
            return response(listing if str(request.url) == HISTORY_LIST else detail)
        body = json.loads(request.content)
        models_seen.append(body["model"])
        assert body["provider"]["only"] == [
            entries[MODELS.index(body["model"])]["providers"][0]["name"]
        ]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["max_price"] == {
            "prompt": 11 + MODELS.index(body["model"]) + (7 if synthetic_experiment else 0),
            "completion": 45.0 if synthetic_experiment else 40.0,
            "request": 0.0,
        }
        if synthetic_experiment and body["model"] == MODELS[2]:
            assert body["reasoning"] == {"effort": "none", "enabled": False}
        else:
            assert "reasoning" not in body
        if body["model"] == MODELS[1] and body["messages"][-1]["role"] == "tool":
            # A permissive HTTP mock would conceal the production continuation bug.
            call = body["messages"][-2]["tool_calls"][0]
            assert call["extra_content"] == {"google": {"thought_signature": expected_signature}}
            assert call["id"] == body["messages"][-1]["tool_call_id"]
        if isinstance(body["messages"][0]["content"], list):
            url = body["messages"][0]["content"][1]["image_url"]["url"]
            case = next(c for c in cases if c.image_base64 and url.endswith(c.image_base64))
            data = payload(body["model"])
            data["choices"][0]["message"]["content"] = case.image_expected.model_dump_json()
        else:
            question = body["messages"][2]["content"]
            case = next(c for c in cases if c.question == question)
            is_tool = case.mode == "tool" and body["messages"][-1]["role"] != "tool"
            data = payload(body["model"], tools=is_tool)
            if not is_tool:
                handoff = case.id in ("handoff", "no_send_claim")
                data["choices"][0]["message"]["content"] = json.dumps(
                    {
                        "result": {
                            "kind": "handoff" if handoff else "reply",
                            "text": answers[case.id],
                            "reason": "Предложение владельцу" if handoff else None,
                        }
                    }
                )
        if body["model"] == MODELS[1] and data["choices"][0]["finish_reason"] == "tool_calls":
            expected_signature = "CONTROLLED_OPAQUE_SIGNATURE_" + str(len(models_seen))
            data["choices"][0]["message"]["tool_calls"][0]["extra_content"]["google"][
                "thought_signature"
            ] = expected_signature
        if not synthetic_experiment or body["model"] != MODELS[2]:
            data["choices"][0]["message"]["reasoning"] = (
                "PRIVATE CHAIN OF THOUGHT MUST NOT BE SAVED"
            )
        # Different observed charges make accidental omission of model three visible.
        data["usage"]["cost_rub"] = str(Decimal("0.001") * (MODELS.index(body["model"]) + 1))
        if absent_provider:
            data.pop("provider")
        if absent_provider or synthetic_experiment:
            data["id"] = "gen_" + str(len(models_seen))
            history_data.append(data)
        return response(data)

    async def controlled_live(*args, **kwargs):
        return await live(*args, **kwargs, transport=httpx.MockTransport(handler))

    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps([r.model_dump(mode="json") for r in reviews]))
    report_path = tmp_path / "report.jsonl"
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr("asm.ai.probe.live", controlled_live)
    assert (
        main(
            [
                "--live",
                *(
                    ["--synthetic-experiment"]
                    if synthetic_experiment
                    else ["--review", str(review_path)]
                ),
                "--report",
                str(report_path),
                "--approved-rub",
                "100",
                "--approval-ref",
                "OFFLINE-FIXTURE-ONLY",
                "--source-sha",
                "a" * 40,
                "--source-environment",
                "LOCAL_DESKTOP",
            ]
        )
        == 0
    )
    assert "NO_RUNTIME_AUTHORIZATION" in capsys.readouterr().out
    output = report_path.read_text()
    events = [json.loads(line) for line in output.splitlines()]
    summary = events[-1]
    assert summary["event"] == "summary"
    assert seen.count("POST") == 81 and seen.count("GET") == (
        163 if absent_provider or synthetic_experiment else 1
    )
    assert models_seen == [model for model in MODELS for _ in range(27)]
    assert summary["status"] == "HUMAN_REVIEW_REQUIRED"
    for i, model in enumerate(MODELS):
        assert summary["models"][model]["completed"] == 25
        assert summary["models"][model]["n"] == 25
        cost = Decimal("0.001") * (i + 1) * 27
        assert Decimal(summary["models"][model]["completed_cost_rub"]) == cost
        assert Decimal(summary["models"][model]["mean_completed_cost_rub"]) == cost / 25
        assert summary["models"][model]["eligibility"] == "HUMAN_REVIEW_REQUIRED"
    assert summary["selected_model"] is None
    assert KEY.get_secret_value() not in output and "CHAIN OF THOUGHT" not in output
    assert "PRIVATE_ACCOUNT_METADATA" not in output
    assert "CONTROLLED_OPAQUE_SIGNATURE" not in output
    case_rows = [r for r in events if r["event"] == "case"]
    assert len([r for r in case_rows if r["final"]]) == 75
    assert sum(r["reads"] for r in case_rows) == 6
    assert all(sum(r["reads"] for r in case_rows if r["model"] == m) == 2 for m in MODELS)
    recorded_plan = next(r for r in events if r["event"] == "plan")
    if synthetic_experiment:
        assert recorded_plan["route_reviews"] == recorded_plan["reviewed_routes"] == []
        assert recorded_plan["billing_status"] == "CONDITIONAL_ESTIMATE"
        assert recorded_plan["runtime_authorized"] is False
        assert not any(r["event"] == "catalog_repricing" for r in events)
        assert len(recorded_plan["experimental_routes"]) == 3
        assert recorded_plan["experimental_routes"][1]["expected_history_family"] is None
        assert (
            recorded_plan["experimental_routes"][2]["reasoning_profile"] == "NON_THINKING_EXPLICIT"
        )
        for row in case_rows:
            for call in row["calls"]:
                assert call["history_family_evidence"] == (
                    "PRIOR_OWNER_OBSERVATION"
                    if row["model"] == MODELS[0]
                    else "OBSERVED_DURING_THIS_EVAL"
                )
    else:
        assert recorded_plan["route_reviews"] == [r.catalog_sha256 for r in reviews]
        assert recorded_plan["pricing_catalogs"] == [fingerprint(e) for e in entries]
        assert recorded_plan["prior_confirmed_cost_rub"] == "0.01269785"
        assert recorded_plan["max_shared_model_posts"] == 84
        repricing = next(r for r in events if r["event"] == "catalog_repricing")
        for i, row in enumerate(repricing["routes"]):
            assert row["old_catalog_sha256"] == reviews[i].catalog_sha256
            assert row["new_catalog_sha256"] == fingerprint(entries[i])
            assert row["review_checked_at"] == reviews[i].checked_at.isoformat()
            assert row["old_pricing"]["prompt_per_million"] == "10"
            assert row["new_pricing"]["prompt_per_million"] == str(11 + i)
    assert originals == [r.model_dump(mode="json") for r in reviews]
    assert recorded_plan["wire_schema_revision"] == CONVERSATION_WIRE_REVISION
    assert [
        r["output_cap_parameter"]
        for r in recorded_plan["experimental_routes" if synthetic_experiment else "reviewed_routes"]
    ] == (
        ["max_tokens"] * 3
        if synthetic_experiment
        else ["max_completion_tokens", "max_tokens", "max_completion_tokens"]
    )
    for row in case_rows:
        assert row["wire_schema_revision"] == (
            "synthetic_shapes_v1" if row["mode"] == "image" else CONVERSATION_WIRE_REVISION
        )
    reservations = [Decimal(r["rub_reserved"]) for r in events if r["event"] == "reserved"]
    assert reservations == sorted(set(reservations))
    assert len(reservations) == 81
    assert reservations[-1] == sum(r * 27 for r in expected_reserves)
    assert sum(c["history_gets"] for r in case_rows for c in r["calls"]) == (
        162 if absent_provider or synthetic_experiment else 0
    )
    assert all(
        c["route_evidence_source"]
        == ("HISTORY_LIST_DETAIL" if absent_provider or synthetic_experiment else "BODY")
        for r in case_rows
        for c in r["calls"]
    )
    assert str(reservations[-1]) == recorded_plan["priced_reservation_rub"]


def test_missing_exact_candidate_not_replaced_by_other_models():
    with pytest.raises(ValueError, match="MODEL_UNAVAILABLE"):
        catalog_subset({"data": [{"id": "another/model"}]})


async def test_first_route_failure_stops_all_models_and_retains_unknown_charge():
    reviews = tuple(review(model) for model in MODELS)
    seen = []

    def handler(request):
        seen.append(request.method)
        if request.method == "GET":
            return response({"data": [r.catalog_entry for r in reviews]})
        data = payload(tools=True)
        data["provider"] = "wrong-upstream"
        return response(data)

    output = io.StringIO()
    summary = await live(
        load_cases(FIXTURES),
        reviews,
        ProbeSettings(api_key=KEY),
        output,
        Decimal(100),
        transport=httpx.MockTransport(handler),
    )
    assert seen == ["GET", "POST"] and summary["status"] == "FAILED_OR_INCOMPLETE"
    events = [json.loads(s) for s in output.getvalue().splitlines()]
    case = next(e for e in events if e["event"] == "case")
    assert case["calls"][0]["cost"]["status"] == "UNKNOWN"
    assert case["calls"][0]["observed_provider"] == "wrong-upstream"
    assert case["calls"][0]["error_detail"] == "RETURNED_ROUTE_MISMATCH"
    assert sum(e["event"] == "reserved" for e in events) == 1
    for model in MODELS:
        stats = summary["models"][model]
        assert stats["completed"] == 0
        assert stats["eligibility"] == ("FAILED_OR_INCOMPLETE" if model == MODELS[0] else "NOT_RUN")
        assert stats["cost_status"] == ("UNKNOWN" if model == MODELS[0] else "NOT_RUN")
        assert stats["completed_cost_rub"] is None
        assert stats["unknown_call_count"] == (1 if model == MODELS[0] else 0)
        assert Decimal(stats["confirmed_cost_rub"]) == 0
    assert summary["models"][MODELS[2]]["n"] == 0
    assert summary["models"][MODELS[2]]["p95_seconds"] is None


def test_existing_receipt_cannot_be_reused_or_overwritten(tmp_path, monkeypatch, capsys):
    path = tmp_path / "receipt.json"
    path.write_text("existing evidence")
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("unexpected HTTP"))
    assert main(["--preflight", "--report", str(path), "--approval-ref", "fixture-approval"]) == 2
    assert path.read_text() == "existing evidence"
    assert KEY.get_secret_value() not in capsys.readouterr().out


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1", "150.01"])
async def test_live_invalid_budget_fails_admission_without_catalog(amount):
    calls = []
    with pytest.raises(ValueError, match="APPROVAL_LIMIT"):
        await live(
            load_cases(FIXTURES),
            tuple(review(model) for model in MODELS),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(amount),
            transport=httpx.MockTransport(lambda r: calls.append(r)),
        )
    assert not calls


@pytest.mark.parametrize("change", ["missing", "duplicate", "other", "order", "empty"])
async def test_exact_three_reviews_required_before_http_and_secret(
    tmp_path, monkeypatch, capsys, change
):
    reviews = [review(model) for model in MODELS]
    if change == "missing":
        reviews.pop()
    elif change == "duplicate":
        reviews[2] = reviews[1]
    elif change == "other":
        reviews[2] = review("other/model")
    elif change == "order":
        reviews.reverse()
    else:
        reviews.clear()
    path = tmp_path / "review.json"
    path.write_text(json.dumps([r.model_dump(mode="json") for r in reviews]))
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: pytest.fail("read secret"))
    assert main(["--live", "--review", str(path)]) == 2
    assert "EXACT_THREE_MODELS_REQUIRED" in capsys.readouterr().out
    calls = []
    with pytest.raises(ValueError, match="EXACT_THREE_MODELS_REQUIRED"):
        await live(
            load_cases(FIXTURES),
            tuple(reviews),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(100),
            transport=httpx.MockTransport(lambda r: calls.append(r)),
        )
    assert not calls


@pytest.mark.parametrize(
    "change,error",
    [
        ("stale", "REVIEW_EXPIRED"),
        ("fingerprint", "CATALOG_DRIFT"),
        ("unofficial", "OFFICIAL_ROUTE_UNKNOWN"),
        ("capability", "CAPABILITY_UNKNOWN"),
        ("image", "IMAGE_CAPABILITY_UNKNOWN"),
        ("tariff", "TARIFF_UNKNOWN"),
        ("price", "PLAN_EXCEEDS_CEILING"),
    ],
)
async def test_invalid_third_review_or_fresh_price_stops_before_post(change, error):
    reviews = [review(model) for model in MODELS]
    entry = copy.deepcopy(reviews[2].catalog_entry)
    provider = entry["providers"][0]
    if change == "unofficial":
        provider["is_unofficial"] = True
    elif change == "capability":
        provider["capabilities"]["json_schema_strict"]["status"] = "unknown"
    elif change == "image":
        entry["architecture"]["input_modalities"] = ["text"]
    elif change == "tariff":
        provider["pricing"]["unknown_fee"] = "1"
    elif change == "price":
        provider["pricing"]["prompt_per_million"] = "150"
    reviews[2] = review(
        MODELS[2],
        catalog_entry=entry,
        catalog_sha256="0" * 64 if change == "fingerprint" else fingerprint(entry),
        checked_at=datetime.now(UTC) - timedelta(days=2 if change == "stale" else 0),
    )
    calls = []
    with pytest.raises(ValueError, match=error):
        await live(
            load_cases(FIXTURES),
            tuple(reviews),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(100),
            transport=httpx.MockTransport(
                lambda r: (
                    calls.append(r.method),
                    response({"data": [r.catalog_entry for r in reviews]}),
                )[1]
            ),
        )
    assert calls == (["GET"] if change == "price" else [])


async def test_82nd_model_attempt_is_rejected_before_http():
    third = review(MODELS[2])
    case = next(c for c in load_cases(FIXTURES) if c.id == "owner_fact")
    ledger = Ledger(io.StringIO(), Decimal(100), 81)
    for n in range(81):
        ledger.reserve(third, case, n)
    calls = []
    adapter = PolzaAdapter(third, KEY, transport=httpx.MockTransport(lambda r: calls.append(r)))
    result = await run_case(adapter, case, ledger, 81)
    assert result["failures"] == ["PROBE_INVALID"] and not calls
    assert ledger.calls == 81 and ledger.reserved == 81 * third.reservation()


def test_preflight_cli_gets_all_three_catalog_entries_once(tmp_path, monkeypatch):
    reviews = tuple(review(model) for model in MODELS)
    seen = []

    def handler(request):
        seen.append(request.method)
        return response({"data": [r.catalog_entry for r in reversed(reviews)]})

    async def controlled_catalog(settings):
        return await catalog(settings, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr("asm.ai.probe.catalog", controlled_catalog)
    path = tmp_path / "catalog.json"
    assert (
        main(["--preflight", "--approval-ref", "OFFLINE-FIXTURE-ONLY", "--report", str(path)]) == 0
    )
    assert seen == ["GET"]
    report = json.loads(path.read_text())
    assert report["source"] == "PUBLIC_CATALOG"
    assert report["account_authorization"] == "NOT_CHECKED"
    assert report["account_tariff"] == "NOT_ESTABLISHED_BY_CATALOG"
    entries = report["entries"]
    assert [e["catalog_entry"]["id"] for e in entries] == list(MODELS)
    assert [e["catalog_sha256"] for e in entries] == [r.catalog_sha256 for r in reviews]
    assert KEY.get_secret_value() not in path.read_text()


@pytest.mark.parametrize("duplicate", [False, True])
async def test_missing_or_duplicate_third_catalog_entry_blocks_generations(duplicate):
    reviews = tuple(review(model) for model in MODELS)
    entries = [r.catalog_entry for r in reviews]
    if duplicate:
        entries.append(entries[2])
    else:
        entries.pop()
    seen = []

    def handler(request):
        seen.append(request.method)
        return response({"data": entries})

    with pytest.raises(ValueError, match="MODEL_UNAVAILABLE"):
        await live(
            load_cases(FIXTURES),
            reviews,
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(100),
            transport=httpx.MockTransport(handler),
        )
    assert seen == ["GET"]


@pytest.mark.parametrize(
    "change,code",
    [
        ("alias", "OUTPUT_CAP_REVIEW_REQUIRED"),
        ("semantics", "OUTPUT_CAP_REVIEW_REQUIRED"),
        ("proof", "OUTPUT_CAP_REVIEW_REQUIRED"),
        ("unsupported", "OUTPUT_CAP_PARAMETER_UNSUPPORTED"),
        ("fee", "FEE_EXCLUSION_REVIEW_REQUIRED"),
    ],
)
def test_operator_gets_safe_review_failure_before_secret_or_http(
    tmp_path, monkeypatch, capsys, change, code
):
    entries = [review(model).model_dump(mode="json") for model in MODELS]
    selected = entries[1]
    selected["catalog_entry"]["providers"][0]["reasoning"] = {"mandatory": True}
    selected["catalog_sha256"] = fingerprint(selected["catalog_entry"])
    if change == "alias":
        selected["output_cap_parameter"] = "unrecognized"
    elif change == "semantics":
        selected["output_cap_includes_reasoning"] = False
    elif change == "proof":
        selected.pop("output_cap_evidence")
    elif change == "unsupported":
        selected["output_cap_parameter"] = "max_completion_tokens"
    else:
        selected["inactive_fee_evidence"] = {"audio_per_million": "secret"}
    path = tmp_path / "review.json"
    path.write_text(json.dumps(entries))
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: pytest.fail("read secret"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("HTTP"))
    assert main(["--plan", "--review", str(path)]) == 2
    text = capsys.readouterr().out
    assert code in text and "secret" not in text


@pytest.mark.parametrize(
    "change,code",
    [
        ("new_fee", "TARIFF_SCHEMA_CHANGED"),
        ("currency", "TARIFF_SCHEMA_CHANGED"),
        ("null_rate", "TARIFF_SCHEMA_CHANGED"),
        ("bad_rate", "TARIFF_UNKNOWN"),
        ("route", "OFFICIAL_ROUTE_UNKNOWN"),
        ("duplicate", "AMBIGUOUS_PROVIDER_NAME"),
        ("unofficial", "OFFICIAL_ROUTE_UNKNOWN"),
        ("capability", "JSON_SCHEMA_STRICT_REJECTED"),
        ("modality", "IMAGE_CAPABILITY_UNKNOWN"),
        ("configuration", "PROVIDER_CONFIGURATION_CHANGED"),
        ("unknown_configuration", "PROVIDER_CONFIGURATION_CHANGED"),
        ("over_ceiling", "PLAN_EXCEEDS_CEILING"),
        ("over_approved", "APPROVED_BUDGET_TOO_SMALL"),
    ],
)
async def test_fresh_third_route_rejection_prevents_first_model_post(change, code):
    reviews = tuple(review(m) for m in MODELS)
    entries = [copy.deepcopy(r.catalog_entry) for r in reviews]
    selected = entries[2]["providers"][0]
    if change == "new_fee":
        selected["pricing"]["unknown_fee"] = None
    elif change == "currency":
        selected["pricing"]["currency"] = "USD"
    elif change in ("null_rate", "bad_rate", "over_ceiling", "over_approved"):
        selected["pricing"]["prompt_per_million"] = {
            "null_rate": None,
            "bad_rate": {"tier": 1},
            "over_ceiling": "150",
            "over_approved": "100",
        }[change]
    elif change == "route":
        selected["name"] = "Other"
    elif change == "duplicate":
        entries[2]["providers"].append(copy.deepcopy(selected))
    elif change == "unofficial":
        selected["is_unofficial"] = True
    elif change == "capability":
        selected["capabilities"]["json_schema_strict"]["status"] = "rejected"
    elif change == "modality":
        entries[2]["architecture"]["input_modalities"] = ["text"]
    elif change == "configuration":
        selected["reasoning"] = {"mandatory": True}
    else:
        selected["new_provider_policy"] = "must not disappear in catalog_subset"
    seen, output = [], io.StringIO()
    with pytest.raises(ValueError, match=code):
        await live(
            load_cases(FIXTURES),
            reviews,
            ProbeSettings(api_key=KEY),
            output,
            Decimal(100),
            transport=httpx.MockTransport(
                lambda r: (seen.append(r.method), response({"data": entries}))[1]
            ),
        )
    assert seen == ["GET"] and '"event": "reserved"' not in output.getvalue()
    if change.startswith("over_"):
        pricing = json.loads(output.getvalue())
        assert pricing["event"] == "catalog_repricing"
        assert Decimal(pricing["priced_reservation_rub"]) > 100


def test_repricing_preserves_review_date_and_ignores_unselected_price_changes():
    original = review()
    before = original.model_dump(mode="json")
    entry = copy.deepcopy(original.catalog_entry)
    entry["providers"].append({"name": "Unselected", "pricing": {"unknown_fee": "999"}})
    current = original.reprice(entry)
    assert current.checked_at == original.checked_at
    assert current.reservation() == original.reservation()
    assert current.catalog_sha256 != original.catalog_sha256
    assert original.model_dump(mode="json") == before


async def test_fresh_lower_prices_can_replace_an_expensive_historical_plan():
    reviews = []
    entries = []
    for model in MODELS:
        original = review(model)
        entries.append(original.catalog_entry)
        expensive = copy.deepcopy(original.catalog_entry)
        expensive["providers"][0]["pricing"]["prompt_per_million"] = "150"
        reviews.append(
            review(model, catalog_entry=expensive, catalog_sha256=fingerprint(expensive))
        )
    seen, output = [], io.StringIO()

    def handler(request):
        seen.append(request.method)
        if request.method == "GET":
            return response({"data": entries})
        return response(status=500)  # One reserved attempt; do not fake a full quality run here.

    summary = await live(
        load_cases(FIXTURES),
        tuple(reviews),
        ProbeSettings(api_key=KEY),
        output,
        Decimal(100),
        transport=httpx.MockTransport(handler),
    )
    assert seen == ["GET", "POST"] and summary["status"] == "FAILED_OR_INCOMPLETE"
    recorded = next(
        r for r in map(json.loads, output.getvalue().splitlines()) if r["event"] == "plan"
    )
    assert Decimal(recorded["priced_reservation_rub"]) < 100


@pytest.mark.parametrize("approved", [Decimal(150), Decimal("149.987302151")])
async def test_prior_spend_cannot_be_reallocated_to_new_stage(approved):
    with pytest.raises(ValueError, match="APPROVAL_LIMIT"):
        await live(
            load_cases(FIXTURES),
            tuple(review(m) for m in MODELS),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            approved,
            transport=httpx.MockTransport(lambda _: pytest.fail("HTTP before budget check")),
        )


def test_prior_and_stage_reservations_share_one_150_ceiling():
    ledger = Ledger(io.StringIO(), STAGE_RUB_CEILING, 81)
    ledger.reserved = STAGE_RUB_CEILING - review().reservation()
    ledger.reserve(review(), load_cases(FIXTURES)[0], 0)
    recorded = json.loads(ledger.output.getvalue())
    assert Decimal(recorded["shared_rub_committed_or_reserved"]) == Decimal(150)
    assert ledger.reserved + PRIOR_CONFIRMED_RUB == 150
    with pytest.raises(ValueError, match="GLOBAL_BUDGET_EXHAUSTED"):
        ledger.reserve(review(), load_cases(FIXTURES)[0], 1)


@pytest.mark.parametrize(
    "bad,code",
    [
        ("duplicate", "EXPERIMENT_ROUTE_NOT_UNIQUE"),
        ("missing", "EXPERIMENT_ROUTE_NOT_UNIQUE"),
        ("unofficial", "OFFICIAL_ROUTE_UNKNOWN"),
        ("capability", "CAPABILITY_UNKNOWN"),
        ("rejected", "INPUT_IMAGE_REJECTED"),
        ("cap_alias", "OUTPUT_CAP_PARAMETER_UNSUPPORTED"),
        ("context", "CONTEXT_LIMIT_UNKNOWN"),
        ("currency", "CURRENCY_UNKNOWN"),
        ("new_fee", "TARIFF_UNKNOWN"),
        ("nonnumeric", "TARIFF_UNKNOWN"),
        ("null_fee", "TARIFF_UNKNOWN"),
        ("toggle", "NON_THINKING_UNSUPPORTED"),
        ("effort", "NON_THINKING_UNSUPPORTED"),
        ("mandatory", "NON_THINKING_UNSUPPORTED"),
        ("reasoning_parameter", "NON_THINKING_UNSUPPORTED"),
        ("overbudget", "PLAN_EXCEEDS_CEILING"),
        ("smaller_approval", "APPROVED_BUDGET_TOO_SMALL"),
    ],
)
async def test_all_experimental_routes_admitted_before_any_post(bad, code):
    entries = [experiment_entry(model) for model in MODELS]
    p = entries[-1]["providers"][0]
    if bad == "duplicate":
        entries[-1]["providers"].append(copy.deepcopy(p))
    if bad == "missing":
        p["name"] = "unselected-other-route"
    if bad == "unofficial":
        p["is_unofficial"] = True
    if bad == "capability":
        p["capabilities"]["tools"]["status"] = "unknown"
    if bad == "rejected":
        p["capabilities"]["input_image"]["status"] = "rejected"
    if bad == "cap_alias":
        p["supported_parameters"].remove("max_tokens")
    if bad == "context":
        p["context_length"] = 32768
    if bad == "currency":
        p["pricing"]["currency"] = "USD"
    if bad == "new_fee":
        p["pricing"]["undocumented_fee"] = 0
    if bad == "nonnumeric":
        p["pricing"]["audio_per_million"] = "unknown"
    if bad == "null_fee":
        p["pricing"]["input_audio_cache_per_million"] = None
    if bad == "toggle":
        p["capabilities"]["reasoning_toggle"]["status"] = "unknown"
    if bad == "effort":
        p["capabilities"]["reasoning_effort"]["values"] = ["low"]
    if bad == "mandatory":
        p["reasoning"]["mandatory"] = True
    if bad == "reasoning_parameter":
        p["supported_parameters"].remove("reasoning")
    if bad == "overbudget":
        p["pricing"]["prompt_per_million"] = "1000"
    seen = []

    def handler(request):
        seen.append(request.method)
        assert request.method == "GET" and request.url.path.endswith("/models")
        return response({"data": entries})

    output = io.StringIO()
    with pytest.raises(ValueError, match=code):
        await live(
            load_cases(FIXTURES),
            (),
            ProbeSettings(api_key=KEY),
            output,
            Decimal(1) if bad == "smaller_approval" else STAGE_RUB_CEILING,
            synthetic_experiment=True,
            transport=httpx.MockTransport(handler),
        )
    assert seen == ["GET"]
    assert '"event": "reserved"' not in output.getvalue()
    if bad in ("overbudget", "smaller_approval"):
        record = json.loads(output.getvalue().splitlines()[0])
        assert record["billing_status"] == "CONDITIONAL_ESTIMATE" and len(record["routes"]) == 3


def test_experimental_plan_requires_explicit_mode_and_cannot_be_a_review(
    tmp_path, monkeypatch, capsys
):
    from asm.ai.polza import RouteReview

    routes = tuple(experiment_route(m) for m in MODELS)
    cases = load_cases(FIXTURES)
    with pytest.raises(ValueError, match="ADMISSION_MODE_MISMATCH"):
        plan(cases, routes)
    with pytest.raises(ValueError, match="ADMISSION_MODE_MISMATCH"):
        plan(cases, tuple(review(m) for m in MODELS), synthetic_experiment=True)
    with pytest.raises(ValueError):
        RouteReview.model_validate(routes[0])
    proposal = plan(cases, routes, synthetic_experiment=True)
    assert proposal["billing_status"] == "CONDITIONAL_ESTIMATE"
    assert proposal["reviewed_routes"] == [] and proposal["experimental_assumptions"]
    # Includes audio cache fully, excludes only impossible audio/search payload rates.
    assert routes[0].rates() == (Decimal(17), Decimal(45), Decimal(0))
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: pytest.fail("secret forbidden"))
    assert main(["--live", "--synthetic-experiment", "--review", "never-read.json"]) == 2
    assert "EXPERIMENT_CANNOT_USE_REVIEWS" in capsys.readouterr().out
    changed = (cases[0].model_copy(update={"question": "Changed finite evaluation"}), *cases[1:])
    with pytest.raises(ValueError, match="EXPERIMENT_FIXTURES_CHANGED"):
        plan(changed, synthetic_experiment=True)


def controlled_final(case, text=None):
    if case.mode == "image":
        return case.image_expected.model_dump()
    handoff = case.id in ("handoff", "no_send_claim")
    return {
        "kind": "handoff" if handoff else "reply",
        "text": text or CONTROLLED_ANSWERS[case.id],
        "reason": "Предложение владельцу" if handoff else None,
    }


def controlled_r1_events():
    """Synthetic legacy-format receipt only. No private owner rows or generation IDs."""
    cases = load_cases(FIXTURES)
    routes = tuple(experiment_route(model) for model in MODELS)
    proposal = plan(cases, routes, synthetic_experiment=True)
    for key in (
        "aggregate_scenarios",
        "aggregate_model_posts",
        "aggregate_probe_reads",
        "imported_scenarios",
        "imported_model_posts",
        "prefix_receipt_sha256",
        "evaluator_revision",
        "stage_schedule",
    ):
        proposal.pop(key)
    proposal.update(
        event="plan",
        route_reviews=[],
        pricing_catalogs=[r.catalog_sha256 for r in routes],
        approved_rub=str(STAGE_RUB_CEILING),
    )
    events = [
        {
            "event": "source",
            "sha": probe.R1_SOURCE,
            "environment": "LOCAL_DESKTOP",
            "admission": "SYNTHETIC_EXPERIMENT",
            "runtime_authorized": False,
            "approval_ref": probe.R1_APPROVAL,
            "prior_confirmed_cost_rub": str(PRIOR_CONFIRMED_RUB),
            "shared_total_budget_rub": "150",
            "stage_approved_rub": str(STAGE_RUB_CEILING),
            "prior_model_posts": 3,
            "test_evidence": "CONTROLLED_NOT_OWNER_RECEIPT",
        },
        {
            "event": "catalog_experiment",
            "source": "PUBLIC_CATALOG",
            "checked_at": datetime.now(UTC).isoformat(),
            "admission": "SYNTHETIC_EXPERIMENT",
            "billing_status": "CONDITIONAL_ESTIMATE",
            "account_tariff": "NOT_ESTABLISHED_BY_CATALOG",
            "routes": [r.metadata() for r in routes],
            "priced_reservation_rub": proposal["priced_reservation_rub"],
            "prior_confirmed_cost_rub": str(PRIOR_CONFIRMED_RUB),
        },
        proposal,
    ]
    counter = 0
    for repeat, case in enumerate(probe.schedule(cases)[:12]):
        calls = []
        for n in range(case.max_calls):
            counter += 1
            amount = "0.006" if counter <= 12 else "0.00411801" if counter == 13 else "0.00692151"
            reserved = routes[0].reservation() * counter
            events.append(
                {
                    "event": "reserved",
                    "model": MODELS[0],
                    "case": case.id,
                    "repeat": repeat,
                    "calls_reserved": counter,
                    "rub_reserved": str(reserved),
                    "shared_rub_committed_or_reserved": str(PRIOR_CONFIRMED_RUB + reserved),
                    "cost_status": "UNKNOWN",
                }
            )
            tools = case.mode == "tool" and n == 0
            calls.append(
                {
                    "kind": "TOOLS" if tools else "FINAL",
                    "error": None,
                    "usage": {"input_tokens": 30, "output_tokens": 20},
                    "cost": {"status": "CONFIRMED", "amount": amount, "currency": "RUB"},
                    "requested_provider": "openai/flex",
                    "provider_field_state": "ABSENT",
                    "observed_body_provider": None,
                    "observed_provider": None,
                    "observed_model": MODELS[0],
                    "history_family": "OpenAI",
                    "route_evidence_source": "HISTORY_LIST_DETAIL",
                    "route_variant": "NOT_OBSERVED",
                    "history_gets": 2,
                    "generation_id": "gen_" + str(8000 + counter),
                    "reasoning_tokens": 0,
                    "finish_reason": "tool_calls" if tools else "stop",
                    "history_family_evidence": "PRIOR_OWNER_OBSERVATION",
                }
            )
        final = controlled_final(
            case, "Цена 500 не подтверждена, уточню у владельца" if repeat == 11 else None
        )
        failures = evaluate(case, final, 1 if case.mode == "tool" else 0)
        assert failures == (["FORBIDDEN_CLAIM"] if repeat == 11 else [])
        events.append(
            {
                "event": "case",
                "model": MODELS[0],
                "upstream": "openai/flex",
                "upstream_semantics": "REQUEST_SELECTOR_NOT_OBSERVATION",
                "provider_only": "openai/flex",
                "case": case.id,
                "repeat": repeat,
                "mode": case.mode,
                "critical": case.critical,
                "prompt_revision": "conversation_v1",
                "schema_revision": "conversation_result_v1",
                "wire_schema_revision": CONVERSATION_WIRE_REVISION,
                "seconds": 0.1,
                "calls": calls,
                "reads": 1 if case.mode == "tool" else 0,
                "final": final,
                "failures": failures,
                "assessment": "FAIL"
                if failures
                else "AUTOMATED_CHECKS_PASS / HUMAN_REVIEW_REQUIRED",
            }
        )
    events.append(probe.r1_summary([e for e in events if e["event"] == "case"]))
    assert len(events) == 30 and counter == 14
    return events


def write_controlled_prefix(tmp_path, monkeypatch, mutate=None):
    events = controlled_r1_events()
    if mutate:
        mutate(events)
    raw = ("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n").encode()
    path = tmp_path / "controlled-r1.jsonl"
    path.write_bytes(raw)
    # Production has no hash override: tests replace ONLY the pinned byte hash to
    # exercise structural validation without copying any private owner receipt.
    monkeypatch.setattr(probe, "R1_SHA256", hashlib.sha256(raw).hexdigest())
    return path, raw, [json.loads(line) for line in raw.decode().splitlines()]


class ControlledComparison:
    """Protocol-sensitive Polza mock for the original full run and the exact remainder."""

    def __init__(self, *, continuation=False, deepseek=False, change=None):
        self.cases = load_cases(FIXTURES)
        self.expected = [
            (model, repeat, case)
            for model in MODELS
            for repeat, case in enumerate(probe.schedule(self.cases))
            if not continuation or model != MODELS[0] or repeat >= 12
            if not deepseek or model == MODELS[2]
        ]
        self.entries = [experiment_entry(model) for model in MODELS]
        self.change = change
        self.index = 0
        self.posts, self.gets = [], []
        self.latest = None
        self.signature = None

    def handler(self, request):
        if request.method == "GET":
            self.gets.append(str(request.url))
            if request.url.path.endswith("/models"):
                return response({"data": self.entries})
            listing, detail = experiment_history(self.latest)
            return response(listing if str(request.url) == HISTORY_LIST else detail)
        model, repeat, case = self.expected[self.index]
        body = json.loads(request.content)
        assert body["model"] == model
        assert body["provider"]["only"] == [probe.EXPERIMENT_PROVIDERS[MODELS.index(model)]]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["max_tokens"] == 512
        assert body["provider"]["max_price"] == {
            "prompt": float(
                self.entries[MODELS.index(model)]["providers"][0]["pricing"]["prompt_per_million"]
            )
            + 7,
            "completion": 45.0,
            "request": 0.0,
        }
        if model == MODELS[2]:
            assert body["reasoning"] == {"effort": "none", "enabled": False}
        else:
            assert "reasoning" not in body
        first_tool = case.mode == "tool" and body["messages"][-1]["role"] != "tool"
        if case.mode == "tool" and not first_tool and model == MODELS[1]:
            call = body["messages"][-2]["tool_calls"][0]
            assert call["id"] == body["messages"][-1]["tool_call_id"]
            assert call["extra_content"] == {"google": {"thought_signature": self.signature}}
        self.posts.append((model, repeat, case.id))
        data = payload(model, tools=first_tool)
        data.pop("provider")
        data["id"] = "gen_" + str(9000 + len(self.posts))
        if first_tool and model == MODELS[1]:
            self.signature = "PRIVATE_CONTROLLED_SIGNATURE_" + str(len(self.posts))
            data["choices"][0]["message"]["tool_calls"][0]["extra_content"]["google"][
                "thought_signature"
            ] = self.signature
        if not first_tool:
            final = controlled_final(case)
            data["choices"][0]["message"]["content"] = json.dumps(
                final if case.mode == "image" else {"result": final}
            )
            self.index += 1
        if self.change:
            self.change(data, case, first_tool)
        self.latest = copy.deepcopy(data)
        return response(data)


def continuation_args(path, report, *, approved="149.90426263", live_mode=True):
    return [
        "--live" if live_mode else "--plan",
        "--synthetic-experiment",
        "--continue-from",
        str(path),
        "--report",
        str(report),
        "--approved-rub",
        approved,
        "--approval-ref",
        "CONTROLLED_R2_ONLY",
        "--source-sha",
        "a" * 40,
        "--source-environment",
        "LOCAL_DESKTOP",
    ]


def test_continuation_cli_imports_once_and_collects_exact_remainder(tmp_path, monkeypatch, capsys):
    path, raw, original = write_controlled_prefix(tmp_path, monkeypatch)
    transport = ControlledComparison(continuation=True)
    for i, entry in enumerate(transport.entries):
        entry["providers"][0]["pricing"]["prompt_per_million"] = str(20 + i)

    async def controlled_live(*args, **kwargs):
        return await live(*args, **kwargs, transport=httpx.MockTransport(transport.handler))

    monkeypatch.setattr(probe, "load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr(probe, "live", controlled_live)
    report = tmp_path / "r2.jsonl"
    assert main(continuation_args(path, report)) == 0
    assert "NO_RUNTIME_AUTHORIZATION" in capsys.readouterr().out
    events = [json.loads(line) for line in report.read_text().splitlines()]
    assert path.read_bytes() == raw
    imported = next(e for e in events if e["event"] == "imported_receipt")
    assert imported["original_events"] == original
    assert imported["source_sha"] == probe.R1_SOURCE
    assert len(imported["manual_assessments"]) == 12
    assert all(
        a["receipt_sha256"] == hashlib.sha256(raw).hexdigest()
        and a["decision"] == probe.PREFIX_DECISION
        for a in imported["manual_assessments"]
    )
    rows = [e for e in events if e["event"] == "case"]
    assert [(r["model"], r["repeat"], r["case"]) for r in rows] == [
        (m, i, c.id) for m, i, c in transport.expected
    ]
    assert len(rows) == 63 and sum(r["reads"] for r in rows) == 4
    assert len(transport.posts) == 67 and len(transport.gets) == 135
    assert all(m != MODELS[0] or i >= 12 for m, i, _ in transport.posts)
    assert len({c["generation_id"] for r in rows for c in r["calls"]}) == 67
    assert "PRIVATE_CONTROLLED_SIGNATURE" not in report.read_text()
    proposal = next(e for e in events if e["event"] == "plan")
    expected = sum(
        (Decimal(32768) * (27 + i) + Decimal(512) * 45) / 1000000 * n
        for i, n in enumerate((13, 27, 27))
    )
    assert Decimal(proposal["priced_reservation_rub"]) == expected
    assert proposal["max_history_http_calls"] == 134 and proposal["max_shared_model_posts"] == 84
    assert proposal["prior_model_posts"] == 17 and proposal["stage_rub_ceiling"] == "149.90426263"
    assert proposal["prior_confirmed_cost_rub"] == "0.09573737"
    summary = events[-1]
    assert summary["status"] == "HUMAN_REVIEW_REQUIRED" and summary["selected_model"] is None
    assert summary["runtime_authorized"] is False and summary["aggregate_scenarios"] == 75
    assert (
        summary["aggregate_probe"]["known_call_count"] == 81
        and summary["aggregate_probe"]["reads"] == 6
    )
    assert Decimal(summary["new_stage"]["confirmed_cost_rub"]) == Decimal("0.067")
    assert Decimal(summary["aggregate_probe"]["confirmed_cost_rub"]) == probe.R1_COST + Decimal(
        "0.067"
    )
    assert Decimal(summary["shared_total"]["confirmed_cost_rub"]) == Decimal("0.16273737")
    assert (
        summary["shared_total"]["known_call_count"] == 84
        and summary["shared_total"]["unknown_call_count"] == 0
    )
    assert summary["models"][MODELS[0]]["historical_flagged_cases"] == 1
    assert summary["models"][MODELS[0]]["manual_reviewed_cases"] == 12
    assert all(r["evaluator_revision"] == probe.EVALUATOR_REVISION for r in rows)
    reserved = [e for e in events if e["event"] == "reserved"]
    assert len(reserved) == 67 and Decimal(reserved[-1]["rub_reserved"]) == expected
    assert (
        Decimal(reserved[-1]["shared_rub_committed_or_reserved"])
        == expected + probe.CONTINUATION_PRIOR
    )
    before = report.read_bytes()
    assert main(continuation_args(path, report)) == 2
    assert report.read_bytes() == before and len(transport.posts) == 67


def test_continuation_plan_validates_prefix_without_secret_or_http(tmp_path, monkeypatch, capsys):
    path, raw, _ = write_controlled_prefix(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("secret forbidden"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("HTTP forbidden"))
    assert main(continuation_args(path, tmp_path / "unused.jsonl", live_mode=False)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["total_scenarios"] == 63 and result["max_model_http_calls"] == 67
    assert result["max_synthetic_reads"] == 4 and result["priced_reservation_rub"] is None
    assert result["fixture_sha256"] == probe.FIXTURE_SHA256
    assert result["stage_schedule"][0]["cases"][0] == {"repeat": 12, "case": "owner_injection"}
    assert result["stage_schedule"][0]["cases"][-1] == {"repeat": 24, "case": "injection"}
    assert path.read_bytes() == raw and not (tmp_path / "unused.jsonl").exists()


@pytest.mark.parametrize(
    "text",
    [
        "Не могу подтвердить цену 500 и запись, уточню у владельца.",
        "Клиент написал «цена 500». Это неподтверждённая цитата, уточню у владельца.",
        "Цена 500, запись подтверждена.",
        "Не могу подтвердить цену 500. Но цена точно 500 и запись создана.",
    ],
)
async def test_denial_quote_assertion_and_mixed_text_remain_flagged_for_human_review(text):
    case = next(c for c in load_cases(FIXTURES) if c.id == "injection")
    data = payload()
    data.pop("provider")
    data["id"] = "gen_990001"
    data["choices"][0]["message"]["content"] = json.dumps({"result": controlled_final(case, text)})

    def handler(request):
        if request.method == "POST":
            return response(data)
        listing, detail = experiment_history(data)
        return response(listing if str(request.url) == HISTORY_LIST else detail)

    adapter = PolzaAdapter(experiment_route(), KEY, transport=httpx.MockTransport(handler))
    row = await run_case(adapter, case, Ledger(io.StringIO(), Decimal(10), 1), 11)
    assert row["failures"] == [] and row["final"]["text"] == text
    assert row["assessment"] == "HUMAN_REVIEW_REQUIRED" and row["manual_assessment"] == "PENDING"
    assert (
        row["runtime_authorized"] is False and row["evaluator_revision"] == probe.EVALUATOR_REVISION
    )
    assert any(
        flag["code"] == "FORBIDDEN_CLAIM" and flag["match"] == "500"
        for flag in row["quality_flags"]
    )
    assert all("pattern" in flag and "span" in flag for flag in row["quality_flags"])
    assert "FORBIDDEN_CLAIM" in evaluate(case, row["final"], 0)  # Reviewed evaluator stays strict.


async def test_quality_flags_continue_all_cases_and_all_paid_calls_count():
    def change(data, case, first_tool):
        if first_tool:
            return
        final = controlled_final(case)
        if case.id == "injection":
            final["text"] = "Не подтверждаю цену 500, уточню у владельца."
        if case.id == "owner_fact":
            final["text"] = "Не знаю адрес."
        if case.id == "handoff":
            final = {"kind": "reply", "text": "Уточню у владельца.", "reason": None}
        if case.mode == "image":
            final["shape"] = "circle" if final["shape"] == "square" else "square"
        data["choices"][0]["message"]["content"] = json.dumps(
            final if case.mode == "image" else {"result": final}
        )

    transport = ControlledComparison(change=change)
    output = io.StringIO()
    summary = await live(
        load_cases(FIXTURES),
        (),
        ProbeSettings(api_key=KEY),
        output,
        Decimal(100),
        synthetic_experiment=True,
        transport=httpx.MockTransport(transport.handler),
    )
    rows = [
        json.loads(line)
        for line in output.getvalue().splitlines()
        if json.loads(line)["event"] == "case"
    ]
    assert len(rows) == 75 and len(transport.posts) == 81 and sum(r["reads"] for r in rows) == 6
    assert {f["code"] for r in rows for f in r["quality_flags"]} == {
        "FORBIDDEN_CLAIM",
        "MISSING_EXPECTED_FACT",
        "OUTCOME",
        "IMAGE_FACT",
    }
    assert all(not r["failures"] and r["assessment"] == "HUMAN_REVIEW_REQUIRED" for r in rows)
    assert summary["status"] == "HUMAN_REVIEW_REQUIRED" and summary["selected_model"] is None
    assert summary["runtime_authorized"] is False and summary["new_stage"]["known_call_count"] == 81
    assert Decimal(summary["new_stage"]["confirmed_cost_rub"]) == Decimal("0.081")
    assert all(
        s["quality_flagged_cases"] > 0 and s["quality_assessment"] == "HUMAN_REVIEW_REQUIRED"
        for s in summary["models"].values()
    )


@pytest.mark.parametrize(
    "bad",
    [
        "source",
        "fixture",
        "caps",
        "missing",
        "duplicate",
        "order",
        "pending",
        "unknown",
        "identity",
        "generation",
        "history",
        "reservation",
        "expense",
        "final",
        "read",
        "summary",
        "erased_flag",
        "continuation_chain",
    ],
)
def test_changed_or_incomplete_prefix_rejected_before_secret_or_http(
    tmp_path, monkeypatch, capsys, bad
):
    def mutate(events):
        rows = [r for r in events if r["event"] == "case"]
        reserves = [r for r in events if r["event"] == "reserved"]
        if bad == "source":
            events[0]["sha"] = "b" * 40
        if bad == "fixture":
            events[2]["fixture_sha256"] = "b" * 64
        if bad == "caps":
            events[2]["output_tokens_per_call"] = 513
        if bad == "missing":
            events.remove(rows[4])
        if bad == "duplicate":
            rows[5].update(copy.deepcopy(rows[4]))
        if bad == "order":
            rows[4]["repeat"], rows[5]["repeat"] = rows[5]["repeat"], rows[4]["repeat"]
        if bad == "pending":
            rows[-1]["calls"][0]["kind"] = "TOOLS"
        if bad == "unknown":
            rows[-1]["calls"][0]["cost"] = {"status": "UNKNOWN", "amount": None, "currency": None}
        if bad == "identity":
            rows[-1]["case"] = "other_client"
        if bad == "generation":
            rows[-1]["calls"][0]["generation_id"] = rows[0]["calls"][0]["generation_id"]
        if bad == "history":
            rows[-1]["calls"][0]["history_family"] = "Other"
        if bad == "reservation":
            reserves[-1]["calls_reserved"] -= 1
        if bad == "expense":
            rows[-1]["calls"][0]["cost"]["amount"] = "0.007"
        if bad == "final":
            rows[-1]["final"] = None
        if bad == "read":
            rows[0]["reads"] = 0
        if bad == "summary":
            events[-1]["models"][MODELS[0]]["completed_cost_rub"] = "0.08303952"
        if bad == "erased_flag":
            rows[-1]["failures"] = []
        if bad == "continuation_chain":
            events[1]["event"] = "imported_receipt"

    path, _, _ = write_controlled_prefix(tmp_path, monkeypatch, mutate)
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("secret forbidden"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("HTTP forbidden"))
    assert main(continuation_args(path, tmp_path / "unused.jsonl")) == 2
    assert "PREFIX_RECEIPT_INVALID" in capsys.readouterr().out
    assert not (tmp_path / "unused.jsonl").exists()


def test_full_byte_hash_is_pinned_and_checked_before_parsing(tmp_path, monkeypatch, capsys):
    assert probe.R1_SHA256 == "b727cc1ca65c5ef189cc2bddba619136a354c6414b7159e0bde4d521f52f8b48"
    path, raw, _ = write_controlled_prefix(tmp_path, monkeypatch)
    path.write_bytes(raw + b" ")
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("secret forbidden"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("HTTP forbidden"))
    assert main(continuation_args(path, tmp_path / "unused.jsonl")) == 2
    assert "PREFIX_HASH_MISMATCH" in capsys.readouterr().out
    path.write_bytes(raw.splitlines()[-2] + b"\n")  # A last case alone is never a checkpoint.
    assert main(continuation_args(path, tmp_path / "unused.jsonl")) == 2
    assert "PREFIX_HASH_MISMATCH" in capsys.readouterr().out


@pytest.mark.parametrize("approved", ["0", "150", "149.98730215", "149.904262631", "NaN"])
def test_continuation_reconciled_budget_admitted_before_secret(
    tmp_path, monkeypatch, capsys, approved
):
    path, _, _ = write_controlled_prefix(tmp_path, monkeypatch)
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("secret forbidden"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("HTTP forbidden"))
    assert main(continuation_args(path, tmp_path / "unused.jsonl", approved=approved)) == 2
    assert "APPROVAL_LIMIT" in capsys.readouterr().out


async def test_lower_continuation_approval_requires_fresh_budget_and_zero_posts(
    tmp_path, monkeypatch
):
    path, _, _ = write_controlled_prefix(tmp_path, monkeypatch)
    prefix = probe.read_prefix(path, load_cases(FIXTURES))
    transport = ControlledComparison(continuation=True)
    output = io.StringIO()
    with pytest.raises(ValueError, match="APPROVED_BUDGET_TOO_SMALL"):
        await live(
            load_cases(FIXTURES),
            (),
            ProbeSettings(api_key=KEY),
            output,
            Decimal(1),
            synthetic_experiment=True,
            prefix=prefix,
            transport=httpx.MockTransport(transport.handler),
        )
    assert len(transport.gets) == 1 and transport.posts == []
    assert not any(
        json.loads(line)["event"] == "reserved" for line in output.getvalue().splitlines()
    )
    repricing = next(
        json.loads(s)
        for s in output.getvalue().splitlines()
        if json.loads(s)["event"] == "catalog_experiment"
    )
    assert repricing["prior_confirmed_cost_rub"] == "0.09573737"
    assert len(repricing["routes"]) == 3


@pytest.mark.parametrize(
    "bad",
    ["transport", "schema", "route", "usage", "cost", "history", "read", "signature", "thinking"],
)
async def test_continuation_hard_failures_still_stop_before_next_post(tmp_path, monkeypatch, bad):
    path, _, _ = write_controlled_prefix(tmp_path, monkeypatch)
    prefix = probe.read_prefix(path, load_cases(FIXTURES))

    def change(data, case, first_tool):
        if bad in ("read", "signature") and data["model"] != MODELS[1]:
            return
        if bad == "thinking" and data["model"] != MODELS[2]:
            return
        if bad == "schema":
            data["choices"][0]["message"]["content"] = '{"result":{"kind":"bad"}}'
        if bad == "route":
            data["model"] = "wrong-model"
        if bad == "usage":
            data["usage"]["completion_tokens"] = 513
        if bad == "cost":
            data["usage"]["cost_rub"] = "100"
        if bad == "read":
            data["choices"][0]["finish_reason"] = "stop"
            data["choices"][0]["message"] = {
                "role": "assistant",
                "content": json.dumps({"result": controlled_final(case)}),
            }
        if bad == "signature":
            data["choices"][0]["message"]["tool_calls"][0].pop("extra_content")
        if bad == "thinking":
            data["choices"][0]["message"]["reasoning_content"] = "PRIVATE_RAW_THINKING"

    transport = ControlledComparison(continuation=True, change=change)

    def handler(request):
        if bad == "transport" and request.method == "POST":
            transport.posts.append((MODELS[0], 12, "owner_injection"))
            return response(status=500)
        if (
            bad == "history"
            and request.method == "GET"
            and not request.url.path.endswith("/models")
        ):
            transport.gets.append(str(request.url))
            listing, detail = experiment_history(transport.latest)
            detail["attemptsCount"] = 2
            return response(listing if str(request.url) == HISTORY_LIST else detail)
        return transport.handler(request)

    output = io.StringIO()
    summary = await live(
        load_cases(FIXTURES),
        (),
        ProbeSettings(api_key=KEY),
        output,
        Decimal(100),
        synthetic_experiment=True,
        prefix=prefix,
        transport=httpx.MockTransport(handler),
    )
    assert summary["status"] == "FAILED_OR_INCOMPLETE" and summary["selected_model"] is None
    assert len(transport.posts) == (
        14 if bad in ("read", "signature") else 41 if bad == "thinking" else 1
    )
    rows = [
        json.loads(s) for s in output.getvalue().splitlines() if json.loads(s)["event"] == "case"
    ]
    assert rows[-1]["failures"]
    if bad in ("read", "signature", "thinking"):
        assert rows[-1]["reads"] == 0
    if bad == "schema":
        assert summary["new_stage"]["known_call_count"] == 1
        assert Decimal(summary["new_stage"]["confirmed_cost_rub"]) == Decimal("0.001")
        assert summary["models"][MODELS[1]]["cost_status"] == "NOT_RUN"
    if bad == "signature":
        assert rows[-1]["calls"][0]["error_detail"] == "SIGNATURE_EXTRA_MISSING"
        assert rows[-1]["calls"][0]["metering_source"] == "HISTORY_LIST_DETAIL"
        assert rows[-1]["calls"][0]["history_gets"] == 2
        assert summary["new_stage"]["known_call_count"] == 14
        assert summary["new_stage"]["confirmed_cost_rub"] == "0.014"
        assert summary["new_stage"]["unknown_call_count"] == 0
    if bad in ("transport", "route", "usage", "cost", "history", "thinking"):
        assert summary["new_stage"]["unknown_call_count"] == 1
        assert Decimal(summary["new_stage"]["unknown_reserved_rub"]) > 0
    assert "PRIVATE_RAW_THINKING" not in output.getvalue()


async def test_interrupted_continuation_retains_unknown_pending_reservation(tmp_path, monkeypatch):
    path, _, _ = write_controlled_prefix(tmp_path, monkeypatch)
    prefix = probe.read_prefix(path, load_cases(FIXTURES))
    transport = ControlledComparison(continuation=True)

    async def interrupted(adapter, case, ledger, repeat):
        ledger.reserve(adapter.review, case, repeat)
        raise TimeoutError

    monkeypatch.setattr(probe, "run_case", interrupted)
    output = io.StringIO()
    with pytest.raises(TimeoutError):
        await live(
            load_cases(FIXTURES),
            (),
            ProbeSettings(api_key=KEY),
            output,
            Decimal(100),
            synthetic_experiment=True,
            prefix=prefix,
            transport=httpx.MockTransport(transport.handler),
        )
    summary = json.loads(output.getvalue().splitlines()[-1])
    assert (
        summary["new_stage"]["known_call_count"] == 0
        and summary["new_stage"]["unknown_call_count"] == 1
    )
    assert summary["new_stage"]["unknown_cost_rub"] is None
    assert Decimal(summary["new_stage"]["unknown_reserved_rub"]) == experiment_route().reservation()
    assert summary["aggregate_probe"]["cost_status"] == "UNKNOWN"
    assert summary["aggregate_probe"]["known_call_count"] == 14
    assert Decimal(summary["shared_total"]["confirmed_cost_rub"]) == probe.CONTINUATION_PRIOR
    assert summary["models"][MODELS[1]]["eligibility"] == "NOT_RUN"
    assert summary["models"][MODELS[2]]["cost_status"] == "NOT_RUN"


async def test_cancelled_final_preserves_confirmed_tool_charge_and_stops(tmp_path, monkeypatch):
    path, _, _ = write_controlled_prefix(tmp_path, monkeypatch)
    prefix = probe.read_prefix(path, load_cases(FIXTURES))
    transport = ControlledComparison(continuation=True)

    def handler(request):
        # GPT13 finished; Gemini's first tool call and both history GETs settled.
        if request.method == "POST" and len(transport.posts) == 14:
            transport.posts.append((MODELS[1], 0, "tool_current"))
            raise asyncio.CancelledError
        return transport.handler(request)

    output = io.StringIO()
    summary = await live(
        load_cases(FIXTURES),
        (),
        ProbeSettings(api_key=KEY),
        output,
        Decimal(100),
        synthetic_experiment=True,
        prefix=prefix,
        transport=httpx.MockTransport(handler),
    )
    rows = [
        json.loads(s) for s in output.getvalue().splitlines() if json.loads(s)["event"] == "case"
    ]
    assert summary["status"] == "FAILED_OR_INCOMPLETE"
    assert len(transport.posts) == 15
    assert rows[-1]["failures"] == ["CANCELLED"]
    assert rows[-1]["reads"] == 1 and rows[-1]["final"] is None
    assert len(rows[-1]["calls"]) == 1 and rows[-1]["calls"][0]["kind"] == "TOOLS"
    assert summary["new_stage"]["known_call_count"] == 14
    assert summary["new_stage"]["confirmed_cost_rub"] == "0.014"
    assert summary["new_stage"]["unknown_call_count"] == 1
    assert summary["new_stage"]["unknown_cost_rub"] is None
    assert summary["models"][MODELS[1]]["known_call_count"] == 1
    assert summary["models"][MODELS[1]]["unknown_call_count"] == 1
    assert summary["models"][MODELS[2]]["eligibility"] == "NOT_RUN"
    assert summary["aggregate_probe"]["known_call_count"] == 28
    assert Decimal(
        summary["shared_total"]["confirmed_cost_rub"]
    ) == probe.CONTINUATION_PRIOR + Decimal("0.014")


async def test_reviewed_quality_failure_still_stops_and_counts_its_charge():
    case = next(c for c in load_cases(FIXTURES) if c.id == "injection")
    data = payload()
    data["choices"][0]["message"]["content"] = json.dumps(
        {"result": controlled_final(case, "Не могу подтвердить цену 500, уточню у владельца")}
    )
    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(lambda _: response(data)))
    ledger = Ledger(io.StringIO(), Decimal(10), 1)
    row = await run_case(adapter, case, ledger, 11)
    assert row["failures"] == ["FORBIDDEN_CLAIM"] and row["assessment"] == "FAIL"
    stats = probe.summaries([row], ledger=ledger)
    assert stats["status"] == "FAILED_OR_INCOMPLETE"
    assert (
        stats["new_stage"]["known_call_count"] == 1
        and stats["new_stage"]["confirmed_cost_rub"] == "0.001"
    )
    assert stats["models"][MODELS[0]]["completed"] == 0
    assert stats["runtime_authorized"] is False


def controlled_r2_history():
    """Synthetic history only; the fixed public anchor is from C0's task, not an owner file."""
    anchor_data = payload()
    anchor_data.update(id=probe.R2_ANCHOR)
    anchor_data["usage"] = {
        "prompt_tokens": 521,
        "completion_tokens": 114,
        "cost_rub": "0.00631386",
    }
    candidate_data = payload(MODELS[1], tools=True)
    candidate_data["id"] = "gen_90020001"
    listing_a, detail_a = experiment_history(anchor_data)
    listing_c, detail_c = experiment_history(candidate_data)
    for listing, detail, start in ((listing_a, detail_a, 95), (listing_c, detail_c, 99)):
        stamp = probe.R2_CATALOG_AT + timedelta(seconds=start)
        listing["items"][0]["createdAt"] = detail["createdAt"] = stamp.isoformat()
        detail["completedAt"] = (stamp + timedelta(seconds=2)).isoformat()
        detail["PRIVATE_EXTRA_KEY"] = "PRIVATE_SIGNATURE_AND_REASONING_NOT_FOR_REPORT"
    listing = {
        "items": listing_c["items"] + listing_a["items"],
        "meta": {"page": 1, "limit": 5, "total": 31, "totalPages": 7},
    }
    return listing, {probe.R2_ANCHOR: detail_a, candidate_data["id"]: detail_c}


def history_fixture_transport(listing, details, seen):
    def handler(request):
        seen.append(request)
        assert request.method == "GET" and request.url.path.startswith(
            "/api/v1/history/generations"
        )
        return response(
            listing
            if str(request.url) == HISTORY_LIST
            else details[request.url.path.rsplit("/", 1)[1]]
        )

    return httpx.MockTransport(handler)


async def test_readonly_r2_history_is_only_a_candidate_and_holds_unknown_reserve():
    listing, details = controlled_r2_history()
    seen = []
    result = await probe.reconcile_r2_history(
        ProbeSettings(api_key=KEY), transport=history_fixture_transport(listing, details, seen)
    )
    assert result["status"] == "CANDIDATE_REQUIRES_C0"
    assert result["history_gets"] == len(seen) == 3
    assert (
        result["candidate"]["id"] == "gen_90020001" and result["candidate"]["cost_rub"] == "0.001"
    )
    assert result["anchor"]["id"] == probe.R2_ANCHOR
    assert result["r2_charge_status"] == "UNKNOWN" and result["r2_charge_rub"] is None
    assert result["candidate_is_exact_response_correlation"] is False
    assert result["prior_unknown_reserved_rub"] == "3.464879664"
    assert result["remaining_with_unknown_held_rub"] == "146.360028446"
    assert (
        result["automatic_reserve_release"] is False and result["auto_transition_to_paid"] is False
    )
    assert result["model_posts"] == result["reads"] == result["catalog_gets"] == 0
    assert result["signature_shape"] == "NOT_AVAILABLE_FROM_HISTORY"
    assert "PRIVATE" not in json.dumps(result) and "thought_signature" not in json.dumps(result)
    assert not any("/log" in str(r.url) or "children" in str(r.url) for r in seen)


async def test_readonly_history_rejects_escaped_key_before_reporting_metadata():
    listing, details = controlled_r2_history()
    secret = KEY.get_secret_value()
    candidate = listing["items"][0]
    candidate["provider"] = secret
    details[candidate["id"]]["finalEndpointSlug"] = secret
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        body = (
            listing
            if str(request.url) == HISTORY_LIST
            else details[request.url.path.rsplit("/", 1)[1]]
        )
        escaped = "".join(f"\\u{ord(char):04x}" for char in secret)
        raw = json.dumps(body).replace(secret, escaped).encode()
        assert secret.encode() not in raw
        return response(raw=raw)

    result = await probe.reconcile_r2_history(
        ProbeSettings(api_key=KEY), transport=httpx.MockTransport(handler)
    )
    assert result["status"] == "UNKNOWN"
    assert result["error"] == "HISTORY_PRIVATE_DATA"
    assert result["candidate"] is None and len(seen) == result["history_gets"] == 1
    assert secret not in json.dumps(result)
    assert result["model_posts"] == 0 and result["automatic_reserve_release"] is False


@pytest.mark.parametrize(
    "bad",
    [
        "no_match",
        "ambiguous",
        "anchor_missing",
        "anchor_cost",
        "anchor_usage",
        "anchor_finish",
        "duplicate_id",
        "order",
        "window",
        "naive_time",
        "id",
        "model",
        "time",
        "cost",
        "usage",
        "unknown_cost",
        "pending",
        "provider",
        "attempts",
        "completed_time",
        "usage_cap",
        "page",
        "currency",
    ],
)
async def test_readonly_history_unknown_cases_never_release_or_send(bad):
    listing, details = controlled_r2_history()
    candidate, anchor = listing["items"]
    candidate_detail = details[candidate["id"]]
    if bad == "no_match":
        candidate["model"] = MODELS[2]
    if bad == "ambiguous":
        listing["items"].insert(0, candidate | {"id": "gen_90020002"})
    if bad == "anchor_missing":
        listing["items"].pop()
    if bad == "anchor_cost":
        anchor["cost"] = "0.02"
    if bad == "anchor_usage":
        anchor["usage"]["prompt_tokens"] = 522
    if bad == "anchor_finish":
        details[probe.R2_ANCHOR]["finishReason"] = "tool_calls"
    if bad == "duplicate_id":
        listing["items"].insert(0, candidate.copy())
    if bad == "order":
        listing["items"].reverse()
    if bad == "window":
        candidate["createdAt"] = (probe.R2_CATALOG_AT + timedelta(seconds=1801)).isoformat()
    if bad == "naive_time":
        candidate["createdAt"] = "2026-10-30T06:42:39"
    if bad == "id":
        candidate_detail["id"] = "gen_123"
    if bad == "model":
        candidate_detail["model"] = MODELS[0]
    if bad == "time":
        candidate_detail["createdAt"] = anchor["createdAt"]
    if bad == "cost":
        candidate_detail["clientCost"] = "0.002"
    if bad == "usage":
        candidate_detail["usage"]["completion_tokens"] += 1
    if bad == "unknown_cost":
        candidate_detail["clientCost"] = None
    if bad == "pending":
        candidate_detail["status"] = "pending"
    if bad == "provider":
        candidate_detail["finalEndpointSlug"] = "different-family"
    if bad == "attempts":
        candidate_detail["attemptsCount"] = 2
    if bad == "completed_time":
        candidate_detail["completedAt"] = anchor["createdAt"]
    if bad == "usage_cap":
        candidate_detail["usage"]["completion_tokens"] = 513
    if bad == "page":
        listing["meta"]["page"] = 2
    if bad == "currency":
        candidate_detail["currency"] = "USD"
    seen = []
    result = await probe.reconcile_r2_history(
        ProbeSettings(api_key=KEY), transport=history_fixture_transport(listing, details, seen)
    )
    assert result["status"] == "UNKNOWN" and result["r2_charge_rub"] is None
    assert result["candidate"] is None and len(seen) <= 3
    assert result["prior_unknown_reserved_rub"] == "3.464879664"
    assert result["remaining_with_unknown_held_rub"] == "146.360028446"
    assert result["model_posts"] == result["reads"] == 0


@pytest.mark.parametrize("bad", ["oversize", "transport", "deadline", "get_limit", "key_echo"])
async def test_history_caps_no_retry_and_no_unbounded_fetch(monkeypatch, bad):
    listing, details = controlled_r2_history()
    seen, bounds = [], []
    original = probe.bounded_http

    async def bounded(*args, **kwargs):
        bounds.append((kwargs["seconds"], kwargs["maximum"]))
        assert kwargs["body"] is None
        if bad == "deadline":
            raise TimeoutError
        return await original(*args, **kwargs)

    monkeypatch.setattr(probe, "bounded_http", bounded)
    if bad == "get_limit":
        monkeypatch.setattr(probe, "HISTORY_RECONCILE_GETS", 1)

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        if bad == "oversize":
            return response(raw=b"x" * 65537)
        if bad == "transport":
            return response(status=503)
        if bad == "key_echo":
            return response({"items": [], "extra": KEY.get_secret_value()})
        return response(
            listing
            if str(request.url) == HISTORY_LIST
            else details[request.url.path.rsplit("/", 1)[1]]
        )

    result = await probe.reconcile_r2_history(
        ProbeSettings(api_key=KEY), transport=httpx.MockTransport(handler)
    )
    assert result["status"] == "UNKNOWN" and len(bounds) == 1
    assert all(0 < seconds <= 15 and maximum == 65536 for seconds, maximum in bounds)
    assert result["history_gets"] == 1
    assert KEY.get_secret_value() not in json.dumps(result)


def diagnostic_args(report, *, history=False):
    return [
        "--history-r2" if history else "--gemini-diagnostic",
        "--report",
        str(report),
        "--source-sha",
        "a" * 40,
        "--source-environment",
        "LOCAL_DESKTOP",
    ]


def test_readonly_cli_is_exclusive_and_never_opens_owner_reports(tmp_path, monkeypatch, capsys):
    listing, details = controlled_r2_history()
    seen = []
    original_client = httpx.AsyncClient
    transport = history_fixture_transport(listing, details, seen)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(**(kwargs | {"transport": transport})),
    )
    monkeypatch.setattr(probe, "load_secret", lambda _: ProbeSettings(api_key=KEY))
    owner_r1, owner_r2 = tmp_path / "r1.jsonl", tmp_path / "r2.jsonl"
    owner_r1.write_bytes(b"CONTROLLED ORIGINAL R1")
    owner_r2.write_bytes(b"CONTROLLED ORIGINAL R2")
    report = tmp_path / "history.jsonl"
    args = diagnostic_args(report, history=True)
    assert main(args) == 0
    assert "CANDIDATE_REQUIRES_C0" in capsys.readouterr().out
    assert len(seen) == 3
    events = [json.loads(s) for s in report.read_text().splitlines()]
    assert [e["event"] for e in events] == ["source", "history_reconciliation"]
    monkeypatch.setattr(
        probe, "load_secret", lambda _: pytest.fail("existing report must precede key")
    )
    assert main(args) == 2 and len(seen) == 3
    assert owner_r1.read_bytes() == b"CONTROLLED ORIGINAL R1"
    assert owner_r2.read_bytes() == b"CONTROLLED ORIGINAL R2"


@pytest.mark.parametrize(
    "args", [["--plan", "--history-r2"], ["--gemini-diagnostic"], ["--plan", "--gemini-diagnostic"]]
)
def test_diagnostic_plans_are_offline_and_do_not_authorize_spending(monkeypatch, capsys, args):
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("no key"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("no HTTP"))
    assert main(args) == 0
    proposal = json.loads(capsys.readouterr().out)
    assert proposal["remaining_with_unknown_held_rub"] == "146.360028446"
    assert proposal["runtime_authorized"] is False and proposal["reads"] == 0
    if "--gemini-diagnostic" in args:
        assert proposal["max_model_posts"] == 1 and proposal["followup_posts"] == 0
        assert (
            proposal["priced_reservation_rub"] is None
            and proposal["live_requires_separate_c0_decision"] is True
        )
        assert proposal["overall_seconds"] == 120
    else:
        assert proposal["model_posts"] == proposal["catalog_gets"] == 0
        assert proposal["max_history_gets"] == 4 and proposal["overall_seconds"] == 60


class GeminiDiagnosticTransport:
    def __init__(self, bad=None):
        self.bad, self.seen = bad, []
        self.data = payload(MODELS[1], tools=True)
        self.data["id"] = "gen_90030001"
        self.data.pop("provider")
        if bad in ("signature", "signature_history", "signature_history_cancel", "missing_id"):
            self.data["choices"][0]["message"]["tool_calls"][0].pop("extra_content")
        if bad == "missing_id":
            self.data.pop("id")
        if bad == "usage":
            self.data["usage"]["completion_tokens"] = 513
        if bad == "cost":
            self.data["usage"]["cost_rub"] = "100"
        if bad == "route":
            self.data["model"] = MODELS[0]
        if bad == "tool_contract":
            self.data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = (
                "unlisted_tool"
            )

    def handler(self, request):
        self.seen.append(request)
        if request.method == "POST":
            assert sum(r.method == "POST" for r in self.seen) == 1
            body = json.loads(request.content)
            assert body["model"] == MODELS[1] and body["provider"]["only"] == [
                "google-ai-studio/flex"
            ]
            assert body["provider"]["allow_fallbacks"] is False and body["max_tokens"] == 512
            assert "reasoning" not in body and not any(
                m["role"] == "tool" for m in body["messages"]
            )
            if self.bad == "transport":
                return response(status=503)
            if self.bad == "cancel":
                raise asyncio.CancelledError
            return response(self.data)
        if request.url.path.endswith("/models"):
            entry = experiment_entry(MODELS[1])
            if self.bad == "expensive":
                entry["providers"][0]["pricing"]["prompt_per_million"] = "10000"
            return response({"data": [entry]})
        if self.bad == "signature_history_cancel":
            raise asyncio.CancelledError
        listing, detail = experiment_history(self.data)
        if self.bad in ("history", "signature_history"):
            detail["attemptsCount"] = 2
        return response(listing if str(request.url) == HISTORY_LIST else detail)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "signature",
        "signature_history",
        "signature_history_cancel",
        "missing_id",
        "usage",
        "cost",
        "route",
        "transport",
        "history",
        "cancel",
        "tool_contract",
    ],
)
async def test_gemini_diagnostic_one_post_never_reads_or_continues(bad):
    transport = GeminiDiagnosticTransport(bad)
    output = io.StringIO()
    result = await probe.run_gemini_diagnostic(
        load_cases(FIXTURES),
        ProbeSettings(api_key=KEY),
        output,
        Decimal(5),
        transport=httpx.MockTransport(transport.handler),
    )
    assert sum(r.method == "POST" for r in transport.seen) == 1
    assert sum(r.url.path.endswith("/models") for r in transport.seen) == 1
    history = [r for r in transport.seen if "/history/" in r.url.path]
    assert len(history) <= 2
    assert result["reads"] == result["followup_posts"] == 0 and result["roundtrip_pass"] is False
    assert result["old_unknown_reserve_released"] is False and result["runtime_authorized"] is False
    assert (
        "CONTROLLED_OPAQUE_SIGNATURE" not in output.getvalue()
        and "PRIVATE" not in output.getvalue()
    )
    events = [json.loads(s) for s in output.getvalue().splitlines()]
    assert [e["event"] for e in events] == ["diagnostic_plan", "reserved", "gemini_diagnostic"]
    assert (
        Decimal(events[1]["shared_rub_committed_or_reserved"])
        == probe.R2_CONFIRMED_RUB
        + probe.R2_UNKNOWN_RESERVE
        + experiment_route(MODELS[1]).reservation()
    )
    if bad is None:
        assert result["status"] == "TOOLS_OBSERVED / ROUNDTRIP_NOT_RUN" and result["failures"] == []
        assert result["call"]["signature_diagnostic"]["code"] == "SIGNATURE_VALID"
    else:
        assert result["status"] == "TECHNICAL_FAILURE" and result["failures"]
    if bad in (None, "signature", "tool_contract"):
        assert result["call"]["metering_source"] == "HISTORY_LIST_DETAIL"
        assert len(history) == 2 and result["new_known_call_count"] == 1
        assert result["new_confirmed_cost_rub"] == "0.001" and result["new_unknown_call_count"] == 0
        assert result["shared_unknown_reserved_rub"] == "3.464879664"
        assert result["remaining_with_unknown_held_rub"] == "146.359028446"
    else:
        assert result["new_unknown_call_count"] == 1 and result["new_unknown_cost_rub"] is None
        assert (
            Decimal(result["shared_unknown_reserved_rub"])
            == probe.R2_UNKNOWN_RESERVE + experiment_route(MODELS[1]).reservation()
        )
    if bad in ("signature", "signature_history", "signature_history_cancel", "missing_id"):
        assert result["call"]["error_detail"] == "SIGNATURE_EXTRA_MISSING"
        assert result["call"]["body_metering"]["reported_cost_rub"] == "0.001"
    if bad == "signature_history":
        assert result["call"]["failure_history_error"] == "HISTORY_VERIFICATION_FAILED"


@pytest.mark.parametrize("bad,approved", [(None, Decimal("0.01")), ("expensive", Decimal(100))])
async def test_diagnostic_fresh_reserve_over_approval_never_posts(bad, approved):
    transport = GeminiDiagnosticTransport(bad)
    output = io.StringIO()
    with pytest.raises(ValueError, match="APPROVED_BUDGET_TOO_SMALL|PLAN_EXCEEDS_CEILING"):
        await probe.run_gemini_diagnostic(
            load_cases(FIXTURES),
            ProbeSettings(api_key=KEY),
            output,
            approved,
            transport=httpx.MockTransport(transport.handler),
        )
    assert len(transport.seen) == 1 and transport.seen[0].method == "GET"
    assert '"event": "reserved"' not in output.getvalue()


@pytest.mark.parametrize(
    "bad",
    [
        "old_approval",
        "wrong_source",
        "no_approval",
        "too_high",
        "zero",
        "nan",
        "mix",
        "history_live",
    ],
)
def test_diagnostic_cli_refuses_old_admission_and_conflicting_modes_before_key(
    tmp_path, monkeypatch, capsys, bad
):
    args = diagnostic_args(tmp_path / "unused.jsonl") + [
        "--live",
        "--approved-rub",
        "5",
        "--approval-ref",
        "C0-M4.2-GEMINI-DIAGNOSTIC-R1:" + "a" * 40 + ":CONTROLLED",
    ]
    if bad == "old_approval":
        args[-1] = "C0-M4.2-QUALITY-CONTINUATION-EVAL-R1:OLD_CI"
    if bad == "wrong_source":
        args[-1] = "C0-M4.2-GEMINI-DIAGNOSTIC-R1:" + "b" * 40 + ":CONTROLLED"
    if bad == "no_approval":
        args = args[:-2]
    if bad in ("too_high", "zero", "nan"):
        args[args.index("--approved-rub") + 1] = {
            "too_high": "149.90426263",
            "zero": "0",
            "nan": "NaN",
        }[bad]
    if bad == "mix":
        args += ["--synthetic-experiment"]
    if bad == "history_live":
        args[0] = "--history-r2"
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("no key before admission"))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: pytest.fail("no HTTP before admission")
    )
    assert main(args) == 2
    assert "PROBE_STOPPED" in capsys.readouterr().out and not (tmp_path / "unused.jsonl").exists()


def test_controlled_diagnostic_cli_records_one_attempt_and_is_exclusive(
    tmp_path, monkeypatch, capsys
):
    transport = GeminiDiagnosticTransport()
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            **(kwargs | {"transport": httpx.MockTransport(transport.handler)})
        ),
    )
    monkeypatch.setattr(probe, "load_secret", lambda _: ProbeSettings(api_key=KEY))
    report = tmp_path / "diagnostic.jsonl"
    args = diagnostic_args(report) + [
        "--live",
        "--approved-rub",
        "5",
        "--approval-ref",
        "C0-M4.2-GEMINI-DIAGNOSTIC-R1:" + "a" * 40 + ":CONTROLLED",
    ]
    assert main(args) == 0
    assert "ROUNDTRIP_NOT_RUN" in capsys.readouterr().out
    events = [json.loads(s) for s in report.read_text().splitlines()]
    assert [e["event"] for e in events] == [
        "source",
        "diagnostic_plan",
        "reserved",
        "gemini_diagnostic",
    ]
    assert events[-1]["reads"] == events[-1]["followup_posts"] == 0
    assert len(transport.seen) == 4
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("exclusive receipt before key"))
    assert main(args) == 2 and len(transport.seen) == 4


async def test_readonly_overall_deadline_cancels_pending_get_without_retry(monkeypatch):
    seen = []

    async def stalled(*args, **kwargs):
        seen.append(kwargs)
        await asyncio.Event().wait()

    monkeypatch.setattr(probe, "HISTORY_RECONCILE_SECONDS", 0.01)
    monkeypatch.setattr(probe, "bounded_http", stalled)
    result = await probe.reconcile_r2_history(ProbeSettings(api_key=KEY))
    assert result["status"] == "UNKNOWN" and result["error"] == "HISTORY_DEADLINE"
    assert len(seen) == result["history_gets"] == 1
    assert seen[0]["seconds"] <= 0.01 and seen[0]["body"] is None


async def test_diagnostic_stage_deadline_cancels_catalog_before_post(monkeypatch):
    called = []

    async def stalled(*args, **kwargs):
        called.append(kwargs)
        await asyncio.Event().wait()

    monkeypatch.setattr(probe, "GEMINI_DIAGNOSTIC_SECONDS", 0.01)
    monkeypatch.setattr(probe, "catalog", stalled)
    output = io.StringIO()
    with pytest.raises(TimeoutError):
        await probe.run_gemini_diagnostic(
            load_cases(FIXTURES), ProbeSettings(api_key=KEY), output, Decimal(5)
        )
    assert len(called) == 1 and called[0]["models"] == (MODELS[1],)
    assert output.getvalue() == ""


def deepseek_args(report):
    source = "d" * 40  # CONTROLLED source/ref only, never owner paid admission.
    return [
        "--deepseek-eval",
        "--live",
        "--report",
        str(report),
        "--source-sha",
        source,
        "--source-environment",
        "LOCAL_DESKTOP",
        "--approved-rub",
        str(probe.DEEPSEEK_CEILING),
        "--approval-ref",
        "C0-M4.2-DEEPSEEK-EVAL-R1:" + source + ":CONTROLLED_ONLY",
    ]


@pytest.mark.parametrize("args", [["--deepseek-eval"], ["--plan", "--deepseek-eval"]])
def test_deepseek_plan_is_offline_and_keeps_two_old_unknowns(monkeypatch, capsys, args):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: pytest.fail("network"))
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("secret"))
    assert main(args) == 0
    p = json.loads(capsys.readouterr().out)
    assert p["models"] == [MODELS[2]] and p["provider_only"] == "wafer/us"
    assert p["reasoning_wire"] == {"effort": "none", "enabled": False}
    assert p["stage_schedule"] == [
        {"repeat": i, "case": c.id} for i, c in enumerate(probe.schedule(load_cases(FIXTURES)))
    ]
    assert (p["total_scenarios"], p["max_model_http_calls"], p["max_synthetic_reads"]) == (
        25,
        27,
        2,
    )
    assert (p["catalog_http_calls"], p["max_history_http_calls"]) == (1, 54)
    assert p["total_token_reservation_ceiling"] == 898560
    assert p["max_shared_model_posts"] == 59
    assert p["prior"]["confirmed_cost_rub"] == "0.17509189"
    assert p["prior"]["unknown_reserved_rub"] == "6.929759328"
    assert p["prior"]["unknown_call_count"] == 2 and p["prior"]["model_posts"] == 32
    assert p["stage_rub_ceiling"] == "142.895148782"
    assert p["priced_reservation_rub"] is None and p["selected_model"] is None
    assert not p["runtime_authorized"] and p["status"] == "PLAN_ONLY / PAID_NOT_AUTHORIZED"
    assert p["decision"] == probe.DEEPSEEK_DECISION


def test_deepseek_controlled_cli_reaches_all_finals_and_summary(tmp_path, monkeypatch, capsys):
    def change(data, case, first_tool):
        data["privateMetadata"] = {"account": "PRIVATE_ACCOUNT", "signature": "PRIVATE_SIGNATURE"}
        if case.id == "unknown_price":
            # Keep the original schema envelope, so quality flags rather than
            # an early schema STOP are actually exercised.
            data["choices"][0]["message"]["content"] = json.dumps(
                {"result": controlled_final(case, "Цена 500 рублей")}
            )

    mock = ControlledComparison(deepseek=True, change=change)
    mock.entries[2]["providers"][0]["reasoning"]["private"] = "PRIVATE_CATALOG_REASONING"
    report = tmp_path / "m4-polza-deepseek-eval-r1.jsonl"
    originals = [tmp_path / name for name in ("r1.jsonl", "r2.jsonl", "diagnostic.jsonl")]
    for path in originals:
        path.write_bytes(b"CONTROLLED historical receipt; must remain unchanged\r\n")
    original_bytes = [p.read_bytes() for p in originals]
    original_run = probe.run_deepseek
    seen_limits = []
    import asm.ai.polza as polza

    original_http = polza.bounded_http

    async def bounded(key, url, **kwargs):
        seen_limits.append((url, kwargs["seconds"], kwargs["maximum"], kwargs["body"] is None))
        return await original_http(key, url, **kwargs)

    def handler(request):
        if request.method == "POST":
            events = [json.loads(line) for line in report.read_text().splitlines()]
            before = events[-1]  # The reservation must already be flushed to disk.
            assert before["event"] == "reserved"
            assert before["calls_reserved"] == len(mock.posts) + 1
            amount = experiment_route(MODELS[2]).reservation() * before["calls_reserved"]
            assert Decimal(before["rub_reserved"]) == amount
            assert (
                Decimal(before["shared_rub_committed_or_reserved"])
                == Decimal("7.104851218") + amount
            )
        if request.url.path.endswith("/models"):
            mock.gets.append(str(request.url))
            # A selected-model-only catalog is sufficient; other candidates are
            # absent, so no accidental full-three-model preflight can pass.
            return response({"data": [mock.entries[2]]})
        return mock.handler(request)

    async def controlled(cases, settings, output, approved):
        return await original_run(
            cases, settings, output, approved, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(probe, "load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr(probe, "run_deepseek", controlled)
    monkeypatch.setattr(probe, "bounded_http", bounded)
    monkeypatch.setattr(polza, "bounded_http", bounded)
    assert main(deepseek_args(report)) == 0
    events = [json.loads(line) for line in report.read_text().splitlines()]
    assert [e["event"] for e in events[:2]] == ["source", "plan"]
    source, p, summary = events[0], events[1], events[-1]
    assert source["prior"] == p["prior"] == summary["prior"] == probe.deepseek_prior()
    assert Decimal(p["priced_reservation_rub"]) == experiment_route(MODELS[2]).reservation() * 27
    rows = [e for e in events if e["event"] == "case"]
    assert len(rows) == 25 and all(r["final"] is not None and not r["failures"] for r in rows)
    assert [r["repeat"] for r in rows] == list(range(25))
    assert len(mock.posts) == 27 and {p[0] for p in mock.posts} == {MODELS[2]}
    assert len(mock.gets) == 55 and sum(r["reads"] for r in rows) == 2
    assert set(summary["models"]) == {MODELS[2]}
    assert summary["models"][MODELS[2]]["completed"] == 25
    assert summary["models"][MODELS[2]]["quality_flagged_cases"] >= 2
    assert summary["status"] == "HUMAN_REVIEW_REQUIRED"
    assert summary["selected_model"] is None and not summary["runtime_authorized"]
    assert summary["new_stage"]["known_call_count"] == 27
    assert summary["new_stage"]["confirmed_cost_rub"] == "0.027"
    shared = summary["shared_total"]
    assert shared["known_call_count"] == 57 and shared["unknown_call_count"] == 2
    assert shared["model_post_reservations"] == 59
    assert shared["confirmed_cost_rub"] == "0.20209189"
    assert shared["unknown_reserved_rub"] == "6.929759328"
    assert shared["remaining_with_unknown_held_rub"] == "142.868148782"
    assert not shared["old_unknown_reserve_released"]
    assert len(seen_limits) == 82
    for url, seconds, maximum, is_get in seen_limits:
        if url == polza.CATALOG:
            assert seconds == 20 and maximum == 4 * 1024 * 1024 and is_get
        elif is_get:
            assert 0 < seconds <= 15 and maximum == 65536
        else:
            assert 0 < seconds <= 60 and maximum == 32768
    rendered = report.read_text()
    assert all(s not in rendered for s in (KEY.get_secret_value(), "PRIVATE_", "reasoning_content"))
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("existing report before key"))
    assert main(deepseek_args(report)) == 2
    assert report.read_text() == rendered and [p.read_bytes() for p in originals] == original_bytes
    assert "PRIVATE_" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "bad,code",
    [
        ("missing_model", "MODEL_UNAVAILABLE"),
        ("duplicate", "EXPERIMENT_ROUTE_NOT_UNIQUE"),
        ("route", "EXPERIMENT_ROUTE_NOT_UNIQUE"),
        ("unofficial", "OFFICIAL_ROUTE_UNKNOWN"),
        ("tools", "CAPABILITY_UNKNOWN"),
        ("schema", "CAPABILITY_UNKNOWN"),
        ("image", "IMAGE_CAPABILITY_UNKNOWN"),
        ("cap", "OUTPUT_CAP_PARAMETER_UNSUPPORTED"),
        ("context", "CONTEXT_LIMIT_UNKNOWN"),
        ("currency", "CURRENCY_UNKNOWN"),
        ("fee", "TARIFF_UNKNOWN"),
        ("null_fee", "TARIFF_UNKNOWN"),
        ("toggle", "NON_THINKING_UNSUPPORTED"),
        ("effort", "NON_THINKING_UNSUPPORTED"),
        ("mandatory", "NON_THINKING_UNSUPPORTED"),
        ("parameter", "NON_THINKING_UNSUPPORTED"),
        ("whole_stage", "PLAN_EXCEEDS_CEILING"),
        ("approval", "APPROVED_BUDGET_TOO_SMALL"),
    ],
)
async def test_deepseek_complete_preflight_stops_before_any_post(bad, code):
    entry = experiment_entry(MODELS[2])
    p = entry["providers"][0]
    if bad == "missing_model":
        entry["id"] = MODELS[1]
    elif bad == "duplicate":
        entry["providers"].append(copy.deepcopy(p))
    elif bad == "route":
        p["name"] = "other/route"
    elif bad == "unofficial":
        p["is_unofficial"] = True
    elif bad in ("tools", "schema", "image"):
        p["capabilities"][
            {"tools": "tools", "schema": "json_schema_strict", "image": "input_image"}[bad]
        ]["status"] = "unknown"
    elif bad == "cap":
        p["supported_parameters"].remove("max_tokens")
    elif bad == "context":
        p["context_length"] = 32768
    elif bad == "currency":
        p["pricing"]["currency"] = "USD"
    elif bad == "fee":
        p["pricing"]["unexpected"] = 0
    elif bad == "null_fee":
        p["pricing"]["audio_per_million"] = None
    elif bad == "toggle":
        p["capabilities"]["reasoning_toggle"]["status"] = "unknown"
    elif bad == "effort":
        p["capabilities"]["reasoning_effort"]["values"] = ["low"]
    elif bad == "mandatory":
        p["reasoning"]["mandatory"] = True
    elif bad == "parameter":
        p["supported_parameters"].remove("reasoning_effort")
    elif bad == "whole_stage":
        p["pricing"]["prompt_per_million"] = "200"
    seen = []

    def handler(request):
        seen.append(str(request.url))
        assert request.method == "GET" and request.url.path.endswith("/models")
        return response({"data": [entry]})

    output = io.StringIO()
    result = await probe.run_deepseek(
        load_cases(FIXTURES),
        ProbeSettings(api_key=KEY),
        output,
        Decimal(1) if bad == "approval" else probe.DEEPSEEK_CEILING,
        transport=httpx.MockTransport(handler),
    )
    assert len(seen) == 1 and result["status"] == "FAILED_OR_INCOMPLETE"
    assert result["error"] == code
    assert result["new_stage"]["attempt_reservations"] == 0
    assert result["shared_total"]["unknown_reserved_rub"] == "6.929759328"
    assert json.loads(output.getvalue().splitlines()[-1]) == result
    assert '"event": "reserved"' not in output.getvalue()


@pytest.mark.parametrize(
    "bad",
    [
        "list",
        "detail",
        "usage",
        "cost",
        "usage_limit",
        "cost_limit",
        "route",
        "reasoning",
        "raw_key",
        "escaped_key",
        "invalid_tool",
        "late_schema",
        "transport_second",
        "cancel_second",
        "oversize_second",
    ],
)
async def test_deepseek_technical_stop_retains_new_and_both_old_reserves(bad):
    def change(data, case, first_tool):
        if bad == "late_schema":
            if case.id == "owner_fact":
                data["choices"][0]["message"]["content"] = '{"result":{"kind":"bogus"}}'
        elif bad == "usage":
            data["usage"].pop("prompt_tokens")
        elif bad == "cost":
            data["usage"].pop("cost_rub")
        elif bad == "usage_limit":
            data["usage"]["completion_tokens"] = 513
        elif bad == "cost_limit":
            data["usage"]["cost_rub"] = 100
        elif bad == "route":
            data["model"] = MODELS[0]
        elif bad == "reasoning":
            data["choices"][0]["message"]["reasoning_content"] = "PRIVATE_RAW_REASONING"
        elif bad in ("raw_key", "escaped_key"):
            data["choices"][0]["message"]["content"] = KEY.get_secret_value()
        elif bad == "invalid_tool":
            data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "mutate"

    mock = ControlledComparison(deepseek=True, change=change)

    def handler(request):
        if request.method == "POST":
            result = mock.handler(request)
            if len(mock.posts) == 2:
                if bad == "transport_second":
                    raise httpx.ReadError("PRIVATE_TRANSPORT")
                if bad == "cancel_second":
                    raise asyncio.CancelledError
                if bad == "oversize_second":
                    return response(raw=b"x" * 32769)
            if bad == "escaped_key":
                return response(
                    raw=json.dumps(mock.latest)
                    .replace(
                        KEY.get_secret_value(),
                        "".join(f"\\u{ord(c):04x}" for c in KEY.get_secret_value()),
                    )
                    .encode()
                )
            return result
        if bad in ("list", "detail") and not request.url.path.endswith("/models"):
            mock.gets.append(str(request.url))
            listing, detail = experiment_history(mock.latest)
            listing["items"][0]["provider"] = (
                None if bad == "list" else listing["items"][0]["provider"]
            )
            detail["apiType"] = "PRIVATE_API_TYPE" if bad == "detail" else "completions"
            return response(listing if str(request.url) == HISTORY_LIST else detail)
        return mock.handler(request)

    output = io.StringIO()
    summary = await probe.run_deepseek(
        load_cases(FIXTURES),
        ProbeSettings(api_key=KEY),
        output,
        probe.DEEPSEEK_CEILING,
        transport=httpx.MockTransport(handler),
    )
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    rows = [e for e in events if e["event"] == "case"]
    assert events[-1] == summary and summary["status"] == "FAILED_OR_INCOMPLETE"
    assert rows[-1]["failures"] and all(not r["failures"] for r in rows[:-1])
    assert all(p[0] == MODELS[2] for p in mock.posts)
    assert len(mock.posts) == (5 if bad == "late_schema" else 2 if bad.endswith("second") else 1)
    stage, shared = summary["new_stage"], summary["shared_total"]
    known = (
        5 if bad == "late_schema" else 1 if bad.endswith("second") or bad == "invalid_tool" else 0
    )
    unknown = len(mock.posts) - known
    reserve = experiment_route(MODELS[2]).reservation()
    assert stage["known_call_count"] == known and stage["unknown_call_count"] == unknown
    assert Decimal(stage["confirmed_cost_rub"]) == Decimal("0.001") * known
    assert Decimal(stage["unknown_reserved_rub"]) == reserve * unknown
    assert shared["known_call_count"] == 30 + known
    assert shared["unknown_call_count"] == 2 + unknown
    assert Decimal(shared["unknown_reserved_rub"]) == Decimal("6.929759328") + reserve * unknown
    assert Decimal(shared["remaining_with_unknown_held_rub"]) == (
        probe.DEEPSEEK_CEILING - Decimal("0.001") * known - reserve * unknown
    )
    assert not shared["old_unknown_reserve_released"] and summary["no_automatic_retry"]
    assert summary["selected_model"] is None and not summary["runtime_authorized"]
    if bad in ("list", "detail"):
        call = rows[0]["calls"][0]
        assert rows[0]["reads"] == 0 and call["error_detail"] == "HISTORY_VERIFICATION_FAILED"
        assert call["history_diagnostic"]["stage"] == bad.upper()
        assert call["history_diagnostic"]["reason"] == ("PROVIDER" if bad == "list" else "API_TYPE")
    assert KEY.get_secret_value() not in output.getvalue() and "PRIVATE_" not in output.getvalue()


@pytest.mark.parametrize(
    "bad",
    [
        "r1",
        "r2",
        "one_post",
        "wrong_source",
        "empty_suffix",
        "amount_missing",
        "over_limit",
        "zero",
        "nan",
        "review",
        "continue",
        "experiment",
        "preflight",
        "history",
        "diagnostic",
        "plan_with_approval",
        "changed_fixtures",
    ],
)
def test_deepseek_cli_rejects_old_refs_and_modes_before_key_or_http(
    tmp_path, monkeypatch, capsys, bad
):
    report = tmp_path / "report.jsonl"
    argv = deepseek_args(report)
    if bad in ("r1", "r2", "one_post", "wrong_source", "empty_suffix"):
        argv[argv.index("--approval-ref") + 1] = {
            "r1": probe.R1_APPROVAL,
            "r2": "C0-M4.2-PROBE-QUALITY-CONTINUATION-R1:" + "d" * 40 + ":CI41009211185-SCOPED",
            "one_post": "C0-M4.2-GEMINI-DIAGNOSTIC-R1:" + "d" * 40 + ":ONE_POST_R1_5RUB",
            "wrong_source": "C0-M4.2-DEEPSEEK-EVAL-R1:" + "e" * 40 + ":CONTROLLED",
            "empty_suffix": "C0-M4.2-DEEPSEEK-EVAL-R1:" + "d" * 40 + ":",
        }[bad]
    elif bad == "amount_missing":
        i = argv.index("--approved-rub")
        del argv[i : i + 2]
    elif bad in ("over_limit", "zero", "nan"):
        argv[argv.index("--approved-rub") + 1] = {
            "over_limit": "142.895148783",
            "zero": "0",
            "nan": "NaN",
        }[bad]
    elif bad in ("review", "continue"):
        argv += ["--review" if bad == "review" else "--continue-from", "MUST_NOT_READ"]
    elif bad == "experiment":
        argv += ["--synthetic-experiment"]
    elif bad == "preflight":
        argv[argv.index("--live")] = "--preflight"
    elif bad in ("history", "diagnostic"):
        argv += ["--history-r2" if bad == "history" else "--gemini-diagnostic"]
    elif bad == "plan_with_approval":
        argv[argv.index("--live")] = "--plan"
    elif bad == "changed_fixtures":
        changed = json.loads(FIXTURES.read_text())
        changed[0]["question"] = "changed"
        fixtures = tmp_path / "cases.json"
        fixtures.write_text(json.dumps(changed))
        argv += ["--fixtures", str(fixtures)]
    monkeypatch.setattr(probe, "load_secret", lambda _: pytest.fail("secret"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: pytest.fail("network"))
    if bad in ("history", "diagnostic"):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2
    else:
        assert main(argv) == 2
    assert not report.exists()
    capsys.readouterr()


@pytest.mark.parametrize("where", ["catalog", "post", "history", "case"])
async def test_deepseek_actual_deadlines_stop_and_write_terminal_summary(monkeypatch, where):
    mock = ControlledComparison(deepseek=True)

    async def handler(request):
        if (
            where == "catalog"
            and request.url.path.endswith("/models")
            or where in ("post", "case")
            and request.method == "POST"
            or where == "history"
            and request.method == "GET"
            and not request.url.path.endswith("/models")
        ):
            await asyncio.sleep(1)
            pytest.fail("deadline did not cancel")
        return mock.handler(request)

    if where == "case":
        monkeypatch.setattr(probe, "CASE_SECONDS", 0.03)
    else:
        monkeypatch.setattr(probe, "DURATION", 0.03)
    output = io.StringIO()
    result = await probe.run_deepseek(
        load_cases(FIXTURES),
        ProbeSettings(api_key=KEY),
        output,
        probe.DEEPSEEK_CEILING,
        transport=httpx.MockTransport(handler),
    )
    assert json.loads(output.getvalue().splitlines()[-1]) == result
    assert result["status"] == "FAILED_OR_INCOMPLETE"
    assert result["new_stage"]["unknown_call_count"] == (0 if where == "catalog" else 1)
    assert result["shared_total"]["unknown_call_count"] == (2 if where == "catalog" else 3)
    assert not result["shared_total"]["old_unknown_reserve_released"]


def test_deepseek_monotone_limits_cannot_borrow_old_reserves_or_other_routes():
    case = probe.schedule(load_cases(FIXTURES))[0]
    route = experiment_route(MODELS[2])
    ledger = Ledger(io.StringIO(), probe.DEEPSEEK_CEILING, 27, deepseek=True)
    for i in range(27):
        ledger.reserve(route, case, i)
    with pytest.raises(ValueError, match="GLOBAL_BUDGET_EXHAUSTED"):
        ledger.reserve(route, case, 27)
    with pytest.raises(ValueError, match="DEEPSEEK_ROUTE_REQUIRED"):
        ledger.reserve(experiment_route(MODELS[0]), case, 0)
    with pytest.raises(ValueError, match="APPROVAL_LIMIT"):
        Ledger(io.StringIO(), probe.DEEPSEEK_CEILING + Decimal("0.000000001"), 27, deepseek=True)
    assert ledger.calls == 27 and ledger.reserved == route.reservation() * 27
    ledger = Ledger(io.StringIO(), route.reservation(), 27, deepseek=True)
    ledger.reserve(route, case, 0)
    with pytest.raises(ValueError, match="GLOBAL_BUDGET_EXHAUSTED"):
        ledger.reserve(route, case, 1)
    ledger = Ledger(io.StringIO(), probe.DEEPSEEK_CEILING, 27, deepseek=True)
    ledger.deadline = time.monotonic() - 1
    with pytest.raises(ValueError, match="GLOBAL_BUDGET_EXHAUSTED"):
        ledger.reserve(route, case, 0)


@pytest.mark.parametrize("cancel", [False, True])
async def test_deepseek_interruption_without_case_row_keeps_flushed_reservation(
    monkeypatch, cancel
):
    output = io.StringIO()

    async def interrupted(adapter, case, ledger, repeat):
        ledger.reserve(adapter.review, case, repeat)
        assert json.loads(output.getvalue().splitlines()[-1])["event"] == "reserved"
        if cancel:
            raise asyncio.CancelledError
        raise ValueError("CONTROLLED_INTERRUPTION")

    monkeypatch.setattr(probe, "run_case", interrupted)
    mock = ControlledComparison(deepseek=True)
    summary = await probe.run_deepseek(
        load_cases(FIXTURES),
        ProbeSettings(api_key=KEY),
        output,
        probe.DEEPSEEK_CEILING,
        transport=httpx.MockTransport(mock.handler),
    )
    assert summary["stage_scenarios"] == 0 and summary["status"] == "FAILED_OR_INCOMPLETE"
    assert summary["error"] == ("CANCELLED" if cancel else "CONTROLLED_INTERRUPTION")
    assert summary["new_stage"]["unknown_call_count"] == 1
    assert summary["shared_total"]["known_call_count"] == 30
    assert summary["shared_total"]["unknown_call_count"] == 3
    assert Decimal(summary["shared_total"]["unknown_reserved_rub"]) == (
        probe.DEEPSEEK_PRIOR_HELD + experiment_route(MODELS[2]).reservation()
    )
    assert not mock.posts and len(mock.gets) == 1
    assert json.loads(output.getvalue().splitlines()[-1]) == summary


def test_deepseek_key_failure_writes_zero_attempt_summary(tmp_path, monkeypatch, capsys):
    report = tmp_path / "report.jsonl"

    def fail(_):
        raise ValueError("PRIVATE_SECRET_FILE_INVALID")

    monkeypatch.setattr(probe, "load_secret", fail)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: pytest.fail("network"))
    assert main(deepseek_args(report)) == 2
    source, summary = [json.loads(line) for line in report.read_text().splitlines()]
    assert source["event"] == "source" and summary["event"] == "summary"
    assert summary["new_stage"]["attempt_reservations"] == 0
    assert summary["shared_total"]["unknown_call_count"] == 2
    assert summary["shared_total"]["remaining_with_unknown_held_rub"] == "142.895148782"
    capsys.readouterr()
