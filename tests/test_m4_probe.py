"""Finite plan, accounting admission, synthetic evaluation and secret boundaries."""

import copy
import io
import json
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
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
from test_m4_polza import KEY, history_payloads, history_review, payload, response, review


def test_default_and_plan_do_not_read_secret_or_open_network(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/secret forbidden")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr("asm.ai.probe.load_secret", forbidden)
    for argv in ([], ["--plan"]):
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


@pytest.mark.parametrize("absent_provider", [False, True])
def test_full_finite_mock_run_reports_every_final_and_no_runtime_selection(
    tmp_path, monkeypatch, capsys, absent_provider
):
    cases = load_cases(FIXTURES)
    reviews = tuple((history_review if absent_provider else review)(model) for model in MODELS)
    originals = [r.model_dump(mode="json") for r in reviews]
    entries = [copy.deepcopy(r.catalog_entry) for r in reviews]
    expected_reserves = []
    for i, entry in enumerate(entries):
        entry["providers"][0]["pricing"]["prompt_per_million"] = str(11 + i)
        expected_reserves.append((Decimal(32768) * (11 + i) + 512 * Decimal(40)) / 1000000)
    answers = {
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
    seen = []
    models_seen = []
    history_data = []

    def handler(request):
        seen.append(request.method)
        if request.method == "GET":
            if request.url.path.endswith("/models"):
                return response({"data": entries})
            listing, detail = history_payloads(history_data[-1])
            return response(listing if str(request.url) == HISTORY_LIST else detail)
        body = json.loads(request.content)
        models_seen.append(body["model"])
        assert body["provider"]["only"] == ["Official Fixture Provider"]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["max_price"] == {
            "prompt": 11 + MODELS.index(body["model"]),
            "completion": 40.0,
            "request": 0.0,
        }
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
        data["choices"][0]["message"]["reasoning"] = "PRIVATE CHAIN OF THOUGHT MUST NOT BE SAVED"
        # Different observed charges make accidental omission of model three visible.
        data["usage"]["cost_rub"] = str(Decimal("0.001") * (MODELS.index(body["model"]) + 1))
        if absent_provider:
            data.pop("provider")
            data["id"] = "gen_" + str(len(models_seen))
            history_data.append(data)
        return response(data)

    async def controlled_live(*args):
        return await live(*args, transport=httpx.MockTransport(handler))

    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps([r.model_dump(mode="json") for r in reviews]))
    report_path = tmp_path / "report.jsonl"
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr("asm.ai.probe.live", controlled_live)
    assert (
        main(
            [
                "--live",
                "--review",
                str(review_path),
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
    assert seen.count("POST") == 81 and seen.count("GET") == (163 if absent_provider else 1)
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
    case_rows = [r for r in events if r["event"] == "case"]
    assert len([r for r in case_rows if r["final"]]) == 75
    assert sum(r["reads"] for r in case_rows) == 6
    assert all(sum(r["reads"] for r in case_rows if r["model"] == m) == 2 for m in MODELS)
    recorded_plan = next(r for r in events if r["event"] == "plan")
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
    assert [r["output_cap_parameter"] for r in recorded_plan["reviewed_routes"]] == [
        "max_completion_tokens",
        "max_tokens",
        "max_completion_tokens",
    ]
    for row in case_rows:
        assert row["wire_schema_revision"] == (
            "synthetic_shapes_v1" if row["mode"] == "image" else CONVERSATION_WIRE_REVISION
        )
    reservations = [Decimal(r["rub_reserved"]) for r in events if r["event"] == "reserved"]
    assert reservations == sorted(set(reservations))
    assert len(reservations) == 81
    assert reservations[-1] == sum(r * 27 for r in expected_reserves)
    assert sum(c["history_gets"] for r in case_rows for c in r["calls"]) == (
        162 if absent_provider else 0
    )
    assert all(
        c["route_evidence_source"] == ("HISTORY_LIST_DETAIL" if absent_provider else "BODY")
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
        assert stats["completed"] == 0 and stats["eligibility"] == "FAILED_OR_INCOMPLETE"
        assert stats["cost_status"] == "UNKNOWN" and stats["completed_cost_rub"] is None
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
