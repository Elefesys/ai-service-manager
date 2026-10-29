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
from asm.ai.polza import MODELS, PolzaAdapter, fingerprint
from asm.ai.probe import (
    FIXTURES,
    Ledger,
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
from test_m4_polza import KEY, payload, response, review


def test_default_and_plan_do_not_read_secret_or_open_network(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/secret forbidden")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr("asm.ai.probe.load_secret", forbidden)
    for argv in ([], ["--plan"]):
        assert main(argv) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["cases_per_model"] == 25 and result["max_model_http_calls"] == 54
        assert result["priced_reservation_rub"] is None and result["proposed_rub_ceiling"] == "100"
        assert result["total_token_reservation_ceiling"] == 1797120


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


def test_reviewed_plan_prices_all_calls_and_rejects_more_than_100():
    cases = load_cases(FIXTURES)
    reviews = (review(), review(MODELS[1]))
    assert Decimal(plan(cases, reviews)["priced_reservation_rub"]) == sum(
        r.reservation() * 27 for r in reviews
    )
    entry = copy.deepcopy(reviews[0].catalog_entry)
    entry["providers"][0]["pricing"]["prompt_per_million"] = "1000"
    expensive = review(catalog_entry=entry, catalog_sha256=fingerprint(entry))
    with pytest.raises(ValueError, match="PLAN_EXCEEDS_CEILING"):
        plan(cases, (expensive, reviews[1]))


@pytest.mark.parametrize(
    "approved,calls",
    [(Decimal(101), 54), (Decimal(0), 54), (Decimal("NaN"), 54), (Decimal(100), 81)],
)
def test_ledger_rejects_invalid_limits(approved, calls):
    with pytest.raises(ValueError):
        Ledger(io.StringIO(), approved, calls)


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
    entries = [review().model_dump(mode="json"), review(MODELS[1]).model_dump(mode="json")]
    entries[0]["checked_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    path.write_text(json.dumps(entries))
    with pytest.raises(ValueError, match="REVIEW_EXPIRED"):
        read_reviews(path)
    entries[0] = review().model_dump(mode="json")
    entries[0]["schema_tools_evidence"] = ""
    path.write_text(json.dumps(entries))
    with pytest.raises(ValueError):
        read_reviews(path)


async def test_catalog_drift_stops_all_generations():
    reviews = (review(), review(MODELS[1]))
    data = {"data": [copy.deepcopy(r.catalog_entry) for r in reviews]}
    data["data"][1]["providers"][0]["pricing"]["completion_per_million"] = "99"
    methods = []

    def handler(req):
        methods.append(req.method)
        assert "include_capabilities=true" in str(req.url)
        return response(data)

    with pytest.raises(ValueError, match="ACCOUNT_CATALOG_CHANGED"):
        await live(
            load_cases(FIXTURES),
            reviews,
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(100),
            transport=httpx.MockTransport(handler),
        )
    assert methods == ["GET"]


async def test_too_small_approved_budget_stops_before_catalog():
    calls = []
    with pytest.raises(ValueError, match="APPROVED_BUDGET_TOO_SMALL"):
        await live(
            load_cases(FIXTURES),
            (review(), review(MODELS[1])),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal("0.01"),
            transport=httpx.MockTransport(lambda r: calls.append(r)),
        )
    assert not calls


@pytest.mark.parametrize("missing", ["usage", "cost"])
async def test_unknown_tool_call_charge_stops_before_read_or_second_http(missing):
    data = payload(tools=True)
    if missing == "usage":
        data.pop("usage")
    else:
        data["usage"].pop("cost_rub")
    count = 0

    def handler(_):
        nonlocal count
        count += 1
        return response(data)

    output = io.StringIO()
    ledger = Ledger(output, Decimal(100), 54)
    adapter = PolzaAdapter(review(), KEY, transport=httpx.MockTransport(handler))
    case = next(c for c in load_cases(FIXTURES) if c.id == "tool_current")
    row = await run_case(adapter, case, ledger, 0)
    assert count == 1 and row["reads"] == 0 and "COST_UNKNOWN" in row["failures"]
    assert ledger.reserved == review().reservation()


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


async def test_full_finite_mock_run_reports_every_final_and_no_runtime_selection():
    cases = load_cases(FIXTURES)
    reviews = (review(), review(MODELS[1]))
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

    def handler(request):
        seen.append(request.method)
        if request.method == "GET":
            return response({"data": [r.catalog_entry for r in reviews]})
        body = json.loads(request.content)
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
                        "kind": "handoff" if handoff else "reply",
                        "text": answers[case.id],
                        "reason": "Предложение владельцу" if handoff else None,
                    }
                )
        data["choices"][0]["message"]["reasoning"] = "PRIVATE CHAIN OF THOUGHT MUST NOT BE SAVED"
        return response(data)

    output = io.StringIO()
    summary = await live(
        cases,
        reviews,
        ProbeSettings(api_key=KEY),
        output,
        Decimal(100),
        transport=httpx.MockTransport(handler),
    )
    assert seen.count("POST") == 54 and seen.count("GET") == 1
    for model in MODELS:
        assert summary["models"][model]["completed"] == 25
        assert summary["models"][model]["eligibility"] == "HUMAN_REVIEW_REQUIRED"
    assert summary["selected_model"] is None
    assert (
        KEY.get_secret_value() not in output.getvalue()
        and "CHAIN OF THOUGHT" not in output.getvalue()
    )
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len([r for r in events if r["event"] == "case" and r["final"]]) == 50
    reservations = [Decimal(r["rub_reserved"]) for r in events if r["event"] == "reserved"]
    assert reservations == sorted(set(reservations))


def test_missing_exact_candidate_not_replaced_by_other_models():
    with pytest.raises(ValueError, match="MODEL_UNAVAILABLE"):
        catalog_subset({"data": [{"id": "another/model"}]})


async def test_first_route_failure_stops_both_models_and_retains_unknown_charge():
    reviews = (review(), review(MODELS[1]))
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


def test_existing_receipt_cannot_be_reused_or_overwritten(tmp_path, monkeypatch, capsys):
    path = tmp_path / "receipt.json"
    path.write_text("existing evidence")
    monkeypatch.setattr("asm.ai.probe.load_secret", lambda _: ProbeSettings(api_key=KEY))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: pytest.fail("unexpected HTTP"))
    assert main(["--preflight", "--report", str(path), "--approval-ref", "fixture-approval"]) == 2
    assert path.read_text() == "existing evidence"
    assert KEY.get_secret_value() not in capsys.readouterr().out


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1"])
async def test_live_invalid_budget_fails_admission_without_catalog(amount):
    calls = []
    with pytest.raises(ValueError, match="APPROVAL_LIMIT"):
        await live(
            load_cases(FIXTURES),
            (review(), review(MODELS[1])),
            ProbeSettings(api_key=KEY),
            io.StringIO(),
            Decimal(amount),
            transport=httpx.MockTransport(lambda r: calls.append(r)),
        )
    assert not calls
