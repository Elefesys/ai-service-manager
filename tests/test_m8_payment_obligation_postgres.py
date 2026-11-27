"""P1 through the owner API, including durable replay on independent PG connections."""

import asyncio
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from asm.messaging.worker import Worker
from asm.service_requests.errors import ServiceRequestError
from generic_pg_schema import assert_current_schema, assert_schema
from m5_knowledge_search_fixtures import owner_unit
from m7_scheduling_fixtures import Work, accept_pair, prepare_quote
from m8_payment_obligation_fixtures import (
    accept_terms,
    draft_terms,
    endpoint,
    fixed_price,
    get_path,
    hold_work,
    inspect_open,
    money_counts,
    post_open,
    prepare_day,
    proof,
    quote_deliveries,
    run_pending_quote_deliveries,
    send_terms,
    terms,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job, scalar
from test_m6_owner_decisions_postgres import owner_get
from test_m6_pricing_postgres import formula_price, price, publish, sign_in
from test_m6_quote_acceptance_postgres import controlled_reply, counts, outcome, process, read
from test_m6_quote_delivery_postgres import DeliveryWire, delivery, run_quote
from test_m6_service_assessments_api_postgres import request_assessment
from test_m7_scheduling_holds_postgres import (
    backend_pid,
    blocked_by,
    client_effects,
    compete,
    offer,
    release,
)
from test_m7_scheduling_owner_day_postgres import shorten_hold_fixture
from test_m7_scheduling_postgres import approval_pg as approval_pg
from test_m7_scheduling_postgres import assessment_pg as assessment_pg
from test_m7_scheduling_postgres import auth as auth
from test_m7_scheduling_postgres import db as db
from test_m7_scheduling_postgres import intake_pg as intake_pg
from test_m7_scheduling_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m7_scheduling_postgres import pricing_pg as pricing_pg
from test_m7_scheduling_postgres import scheduling_pg as scheduling_pg
from test_m7_scheduling_postgres import search_pg as search_pg
from test_m7_scheduling_postgres import seeded as seeded
from test_m7_scheduling_postgres import service_request_pg as service_request_pg
from test_m7_scheduling_reschedule_postgres import initial_appointment, legacy_facts, owner_booking
from test_tenancy_postgres import BA, BA2, BB, A, B

pytestmark = pytest.mark.integration


def forbidden(response, status, error):
    assert response.status_code == status, response.text
    assert response.json() == {"error": {"code": error}}


async def worker_reply(h, worker, phrase):
    receipt = await controlled_reply(h, phrase)
    claim = await claim_job(h, receipt.job_id)
    await worker.execute(claim)
    reply = (await h.kernel.process_inbox(claim)).quote_reply
    return reply.model_dump(mode="json", exclude_none=True) if reply else None


@pytest.mark.parametrize(
    "mode,price,deposit,percent,expected,label",
    [
        ("FIXED_DEPOSIT", 400_000, 50_000, None, 50_000, "fixed"),
        ("FULL_PREPAYMENT", 100_010, None, None, 100_010, "full"),
        ("PERCENT_DEPOSIT", 100_010, None, 5, 5_001, "percent"),
        ("FIXED_DEPOSIT", None, 50_000, None, 50_000, "range"),
        ("FIXED_DEPOSIT", 40_000, 99, None, 99, "99-kopecks"),
    ],
    ids=["fixed", "full", "percent", "range", "99-kopecks"],
)
async def test_p1_opens_accepted_terms_via_owner_card(
    scheduling_pg, auth, monkeypatch, mode, price, deposit, percent, expected, label
):
    h = scheduling_pg
    token = await sign_in(auth)
    pricing = fixed_price(price) if price is not None else formula_price(range_add_minor=50_000)
    work = await accept_terms(h, auth, token, mode, pricing, amount=deposit, percent=percent)
    if mode == "PERCENT_DEPOSIT":
        assert work.material["percent_prepayment"] == {
            "amount_minor": 5_001,
            "rounding_version": "HALF_UP_V1",
        }
        assert "Предоплата — 50,01 ₽ (5%)." in work.agreement["quote"]["text"]

    newer = await publish(h, terms("NONE", fixed_price(900_000)))
    assert newer["release_id"] != work.material["release_id"]
    hold = await hold_work(h, work, await prepare_day(h, auth, token, work))
    before = await client_effects(h)
    calls = 0

    async def external_http(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("Opening an obligation must never call external HTTP")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", external_http)
    path = get_path(work, hold.hold_id)
    for _ in range(2):
        read = await owner_get(auth, path)
        assert read["obligation"] is None and read["hold_status"] == "HELD"
    assert await money_counts(h) == {"obligations": 0, "receipts": 0}
    url, body = endpoint(work, hold.hold_id)
    denied = await auth.client.post(url, json=body, headers={"Idempotency-Key": "missing-csrf"})
    assert denied.status_code == 403
    assert await money_counts(h) == {"obligations": 0, "receipts": 0}

    response = await post_open(auth, token, work, hold.hold_id, "open")
    assert response.status_code == 200, response.text
    result = response.json()
    payment = inspect_open(result, work, hold, amount=expected, price=price)
    assert (payment["percent"], payment["rounding_version"]) == (
        percent,
        "HALF_UP_V1" if percent is not None else None,
    )
    assert result == await owner_get(auth, path)
    assert result == (await post_open(auth, token, work, hold.hold_id, "open")).json()
    assert (await owner_get(auth, work.url + "/quote"))["agreement"] == work.agreement
    assert (await owner_booking(auth, work))["booking"]["hold_id"] == hold.hold_id
    assert await client_effects(h) == before and calls == 0
    counts = await money_counts(h)
    assert counts == {"obligations": 1, "receipts": 1}
    proof(
        label, **work.proof(), hold=result, counts=counts, new_appointments=0, external_calls=calls
    )


async def test_p1_concurrency_replay_replacement_and_scope(scheduling_pg, auth):
    h = scheduling_pg
    token, a, b = await accept_pair(h, auth)
    assert a.selection.client_id == b.selection.client_id
    other = await accept_terms(h, auth, token, "FIXED_DEPOSIT", fixed_price(300_000), amount=50_000)
    assert other.selection.client_id != a.selection.client_id
    date = await prepare_day(h, auth, token, a)
    first = await hold_work(h, a, date)
    second = await hold_work(h, b, date, at="12:00")
    foreign_hold = await hold_work(h, other, date, at="14:00")
    before = await client_effects(h)
    pids = []

    async def open_in_transaction(unit, key):
        pids.append(await backend_pid(unit))
        return await unit.payment_obligation_owner(
            a.selection.model_dump(), UUID(first.hold_id), key
        )

    # Keep the first transaction's result in the database and lose its reply.
    # The second real connection must wait for the first and see that commit.
    original, replay, blocked_at = await compete(
        h,
        lambda unit: open_in_transaction(unit, "lost"),
        lambda unit: open_in_transaction(unit, "parallel-key"),
    )
    assert len(set(pids)) == 2 and blocked_at < first.expires_at
    assert original == replay
    assert await money_counts(h) == {"obligations": 1, "receipts": 2}
    saved = inspect_open(original, a, first, amount=50_000, price=a.material["amount_minor"])
    await h.runtime.engine.dispose()
    for key in ("lost", "new-key"):
        result = await post_open(auth, token, a, first.hold_id, key)
        assert result.status_code == 200 and result.json() == original
    forbidden(
        await post_open(auth, token, b, second.hold_id, "lost"), 409, "IDEMPOTENCY_KEY_CONFLICT"
    )
    for work, hold, overrides in (
        (a, second, {}),
        (a, foreign_hold, {}),
        (a, first, {"client_id": other.selection.client_id}),
        (b, first, {}),
    ):
        forbidden(
            await post_open(auth, token, work, hold.hold_id, "foreign", **overrides),
            404,
            "NOT_FOUND",
        )
    path, command = endpoint(a, first.hold_id)
    for altered, code in (
        (path.replace(str(BA), str(BA2)), "NOT_FOUND"),
        (path.replace(str(A), str(B)).replace(str(BA), str(BB)), "ACCESS_DENIED"),
    ):
        denied = await auth.client.post(
            altered, json=command, headers=token | {"Idempotency-Key": "foreign"}
        )
        forbidden(denied, 403 if code == "ACCESS_DENIED" else 404, code)

    await release(h, a, first, "release-first")
    released = await post_open(auth, token, a, first.hold_id, "lost")
    assert released.status_code == 200
    assert released.json() == original | {"hold_status": "RELEASED"}
    replacement = await hold_work(h, a, date, "replacement", at="10:15")
    opened = await post_open(auth, token, a, replacement.hold_id, "another-hold")
    assert opened.status_code == 200
    assert (
        inspect_open(opened.json(), a, replacement, amount=50_000, price=a.material["amount_minor"])
        == saved
    )
    forbidden(
        await post_open(auth, token, a, replacement.hold_id, "lost"),
        409,
        "IDEMPOTENCY_KEY_CONFLICT",
    )
    assert await money_counts(h) == {"obligations": 1, "receipts": 4}

    new_work = await post_open(auth, token, b, second.hold_id, "separate-work")
    assert new_work.status_code == 200
    other_payment = inspect_open(
        new_work.json(), b, second, amount=50_000, price=b.material["amount_minor"]
    )
    assert other_payment["id"] != saved["id"]
    deadline = await shorten_hold_fixture(h, replacement)
    async with h.migrator.begin() as db:
        await db.execute(
            text("SELECT pg_sleep(greatest(0, extract(epoch FROM (:until-clock_timestamp()))))"),
            {"until": deadline},
        )
    expired = await post_open(auth, token, a, replacement.hold_id, "another-hold")
    assert expired.status_code == 200
    assert expired.json()["hold_status"] == "EXPIRED" and expired.json()["obligation"] == saved
    assert await client_effects(h) == before
    counts = await money_counts(h)
    assert counts == {"obligations": 2, "receipts": 5}
    proof(
        "replay",
        first=saved["id"],
        pids=pids,
        previous=first.hold_id,
        replacement=replacement.hold_id,
        second=other_payment["id"],
        expired=expired.json(),
        counts=counts,
        new_appointments=0,
    )


async def test_p1_first_open_checks_deadline_after_resource_lock_and_released_allocation(
    scheduling_pg, auth
):
    h = scheduling_pg
    token, work, other = await accept_pair(h, auth)
    day = await prepare_day(h, auth, token, work)
    held = await hold_work(h, work, day)
    removed = await hold_work(h, other, day, at="12:00")
    await release(h, other, removed, "remove-unused")
    forbidden(
        await post_open(auth, token, other, removed.hold_id, "open-removed"), 409, "STALE_STATE"
    )

    pid = asyncio.get_running_loop().create_future()

    async def open_while_blocked():
        async with owner_unit(h) as unit:
            pid.set_result(await backend_pid(unit))
            return await unit.payment_obligation_owner(
                work.selection.model_dump(), UUID(held.hold_id), "on-deadline"
            )

    deadline = await shorten_hold_fixture(h, held, seconds=1)
    async with h.migrator.begin() as lock:
        locker = (await lock.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await lock.execute(
            text("SELECT id FROM app.scheduling_resources WHERE business_id=:id FOR UPDATE"),
            {"id": BA},
        )
        waiter = asyncio.create_task(open_while_blocked())
        try:
            blocked = await blocked_by(h, await asyncio.wait_for(pid, 1), locker)
            assert blocked < deadline
            released_at = (
                await lock.execute(
                    text("""
                SELECT clock_timestamp() FROM pg_sleep(greatest(0, extract(epoch FROM (:until-clock_timestamp()))))
            """),
                    {"until": deadline},
                )
            ).scalar_one()
            assert released_at >= deadline
        except BaseException:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
            raise
    with pytest.raises(ServiceRequestError) as rejected:
        await waiter
    assert rejected.value.code == "STALE_STATE"
    expired = await owner_get(auth, get_path(work, held.hold_id))
    assert expired["hold_status"] == "EXPIRED" and expired["obligation"] is None
    counts = await money_counts(h)
    assert counts == {"obligations": 0, "receipts": 0}
    proof(
        "deadline",
        hold=held.hold_id,
        allocation=held.allocation_id,
        blocked=blocked,
        deadline=deadline,
        released_at=released_at,
        removed=removed.hold_id,
        counts=counts,
    )


async def test_p1_upgrade_preserves_0037_agreements_holds_and_none_appointment(scheduling_pg, auth):
    h = scheduling_pg
    token = await sign_in(auth)
    await _migrate("downgrade", "0037")
    try:
        exact = await accept_terms(
            h, auth, token, "PERCENT_DEPOSIT", fixed_price(100_000), percent=5
        )
        fractional = await accept_terms(
            h, auth, token, "PERCENT_DEPOSIT", fixed_price(100_010), percent=5
        )
        tiny = await accept_terms(h, auth, token, "PERCENT_DEPOSIT", fixed_price(1), percent=5)
        none = await accept_terms(h, auth, token, "NONE", fixed_price(400_000))
        day = await prepare_day(h, auth, token, exact)
        live = [
            (exact, await hold_work(h, exact, day)),
            (fractional, await hold_work(h, fractional, day, at="11:15")),
            (tiny, await hold_work(h, tiny, day, at="12:30")),
        ]
        for work, _ in live:
            assert "percent_prepayment" not in work.material
            assert "Предоплата — 5% от указанной цены." in work.agreement["quote"]["text"]
        appointment, _ = await initial_appointment(
            h, none, await offer(h, none, day + timedelta(days=1), "none")
        )
        before_booking = await owner_booking(auth, none)
        before = await legacy_facts(h)
        async with h.migrator.connect() as connection:
            await assert_schema(connection, "0037", "scheduling_intent_schema_profile")
    finally:
        await _migrate("upgrade", "0038")

    async with h.migrator.connect() as connection:
        await assert_current_schema(connection)
    await h.runtime.check()
    assert await legacy_facts(h) == before
    assert await owner_booking(auth, none) == before_booking
    for work in (exact, fractional, tiny, none):
        assert (await owner_get(auth, work.url + "/quote"))["agreement"] == work.agreement

    assert appointment.hold_id is not None
    without = await post_open(auth, token, none, appointment.hold_id, "no-prepayment")
    assert without.status_code == 200, without.text
    assert without.json()["hold_status"] == "CONFIRMED"
    assert without.json()["requires_prepayment"] is False and without.json()["obligation"] is None
    for work, hold in live[1:]:
        forbidden(
            await post_open(auth, token, work, hold.hold_id, "clarify"), 409, "NEEDS_CLARIFICATION"
        )
    assert await money_counts(h) == {"obligations": 0, "receipts": 0}
    result = await post_open(auth, token, exact, live[0][1].hold_id, "legacy-exact")
    assert result.status_code == 200
    payment = inspect_open(result.json(), exact, live[0][1], amount=5_000, price=100_000)
    assert payment["percent"] == 5 and payment["rounding_version"] is None
    assert await legacy_facts(h) == before

    async with h.runtime.engine.connect() as connection:
        for table in ("app.payment_obligations", "platform.payment_obligation_receipts"):
            with pytest.raises(DBAPIError) as denied:
                await connection.execute(text(f"SELECT * FROM {table}"))
            assert denied.value.orig.sqlstate == "42501"
            await connection.rollback()
    assert await scalar(h, "SELECT count(*) FROM app.appointments") == 1
    proof(
        "upgrade",
        revision="0038",
        none=before_booking["booking"],
        exact=result.json(),
        clarification=[work.proof() | {"hold": hold.hold_id} for work, hold in live[1:]],
        counts=await money_counts(h),
        none_money=0,
        new_appointments=0,
    )


@pytest.mark.parametrize(
    "case,price_minor", [("exact", 100_000), ("fractional", 100_010), ("changed", 100_000)]
)
async def test_r1_sent_percent_quote_after_upgrade(scheduling_pg, auth, case, price_minor):
    h = scheduling_pg
    token = await sign_in(auth)
    await _migrate("downgrade", "0037")
    try:
        url, old = await send_terms(
            h, auth, token, "PERCENT_DEPOSIT", fixed_price(price_minor), percent=5
        )
        sent = await delivery(h, old)
        assert sent["status"] == "SENT" and sent["text"] == old["text"]
        assert "Предоплата — 5% от указанной цены." in old["text"]
        assert "percent_prepayment" not in old["material"]
        assert await counts(h) == (0, 0, 0)
    finally:
        await _migrate("upgrade", "0038")

    assert (await read(h, auth, url))["quote"] == old
    assert await delivery(h, old) == sent
    if case == "changed":
        await publish(h, terms("PERCENT_DEPOSIT", fixed_price(200_000), percent=5))

    worker = Worker(h.kernel, DeliveryWire(h))

    ambiguous = None
    if case == "exact":
        ambiguous = outcome(await process(h, await controlled_reply(h, "да")))
    decision = await worker_reply(h, worker, f"Принимаю {old['code']}")
    legacy_view = await read(h, auth, url)
    triples = await counts(h)
    proof(
        f"r1-sent-{case}",
        quote_id=old["quote_id"],
        code=old["code"],
        terms_sha256=old["terms_sha256"],
        delivered="SENT",
        ambiguous=ambiguous,
        worker_reply=decision,
        counts=dict(zip(("acceptances", "orders", "sessions"), triples, strict=True)),
        money=await money_counts(h),
    )
    assert legacy_view["quote"] == old
    if case != "exact":
        assert decision["outcome"] == "STALE"
        assert triples == (0, 0, 0)
        assert await money_counts(h) == {"obligations": 0, "receipts": 0}
        quote = await prepare_quote(h, auth, token, url)
        assert quote["code"] != old["code"]
        assert (await delivery(h, quote))["status"] == "SENT"
        if case == "changed":
            assert quote["material"]["amount_minor"] == 200_000
            assert quote["material"]["percent_prepayment"] == {
                "amount_minor": 10_000,
                "rounding_version": "HALF_UP_V1",
            }
            assert await counts(h) == (0, 0, 0)
            proof("r2-changed-terms", original=old["code"], current=quote)
            return
        assert "Предоплата — 50,01 ₽ (5%)." in quote["text"]
        assert quote["material"]["percent_prepayment"] == {
            "amount_minor": 5_001,
            "rounding_version": "HALF_UP_V1",
        }
        amount, rounding = 5_001, "HALF_UP_V1"
    else:
        assert decision["outcome"] == "ACCEPTED" and triples == (1, 1, 1)
        assert ambiguous == "NEEDS_CLARIFICATION"
        quote, amount, rounding = old, 5_000, None

    accepted = await worker_reply(h, worker, f"Принимаю {quote['code']}")
    assert accepted["outcome"] == "ACCEPTED"
    agreement = (await read(h, auth, url))["agreement"]
    assert agreement["quote"] == quote
    if case == "exact":
        assert agreement == legacy_view["agreement"]
        assert accepted == decision
    assert await counts(h) == (1, 1, 1)
    work = Work(url, agreement)
    hold = await hold_work(h, work, await prepare_day(h, auth, token, work))
    response = await post_open(auth, token, work, hold.hold_id, "sent-before-upgrade")
    assert response.status_code == 200, response.text
    payment = inspect_open(response.json(), work, hold, amount=amount, price=price_minor)
    assert payment["rounding_version"] == rounding
    charges = await money_counts(h)
    assert charges == {"obligations": 1, "receipts": 1}
    proof(
        f"r1-sent-{case}-opened",
        **work.proof(),
        worker_reply=accepted,
        hold=response.json(),
        counts=charges,
        acceptances=1,
        orders=1,
        sessions=1,
    )


@pytest.mark.parametrize("command", ["pricing", "assessment"])
async def test_r2_owner_replay_preserves_sent_percent_quote(scheduling_pg, auth, command):
    h = scheduling_pg
    token = await sign_in(auth)
    repeat = {"pricing": price, "assessment": request_assessment}[command]
    await _migrate("downgrade", "0037")
    try:
        url, old = await send_terms(
            h, auth, token, "PERCENT_DEPOSIT", fixed_price(100_000), percent=5
        )
        sent = await delivery(h, old)
        assert sent["status"] == "SENT" and sent["attempt_id"] is not None
        assert sent["text"] == old["text"] and "percent_prepayment" not in old["material"]
        before = await quote_deliveries(h, old)
        assert len(before) == 1 and before[0]["outbox_id"] == sent["outbox_id"]
        original_result = await repeat(auth, f"{url}/{command}", token)
        assert (await read(h, auth, url))["quote"] == old
        assert await quote_deliveries(h, old) == before
        assert await counts(h) == (0, 0, 0)
    finally:
        await _migrate("upgrade", "0038")

    assert await repeat(auth, f"{url}/{command}", token) == original_result
    view = await read(h, auth, url)
    after = await quote_deliveries(h, old)
    transport = DeliveryWire(h)
    worker = Worker(h.kernel, transport)
    phrase = f"Принимаю {old['code']}"
    first = await worker_reply(h, worker, phrase)
    replay = await worker_reply(h, worker, phrase)
    triples = await counts(h)
    # Process any second delivery only after the client has answered the original
    # code, so a new pending version cannot hide behind its eventual send result.
    await run_pending_quote_deliveries(h, worker, after)
    proof(
        f"r2-{command}",
        command_result_id=original_result[
            "calculation_id" if command == "pricing" else "assessment_id"
        ],
        original=old,
        visible=view["quote"],
        before=before,
        after=after,
        final=await quote_deliveries(h, old),
        worker_reply=first,
        replay=replay,
        counts=dict(zip(("acceptances", "orders", "sessions"), triples, strict=True)),
        additional_sends=transport.calls,
        additional_effects=transport.effects,
    )
    assert view["status"] == "SENT" and view["quote"] == old
    assert before == after == await quote_deliveries(h, old)
    assert await delivery(h, old) == sent
    assert (transport.calls, transport.effects) == (0, 0)
    assert first["outcome"] == "ACCEPTED" and replay == first and triples == (1, 1, 1)

    agreement = (await read(h, auth, url))["agreement"]
    assert agreement["quote"] == old
    work = Work(url, agreement)
    hold = await hold_work(h, work, await prepare_day(h, auth, token, work))
    opened = await post_open(auth, token, work, hold.hold_id, "replayed-legacy-percent")
    assert opened.status_code == 200, opened.text
    payment = inspect_open(opened.json(), work, hold, amount=5_000, price=100_000)
    assert payment["percent"] == 5 and payment["rounding_version"] is None
    charges = await money_counts(h)
    assert charges == {"obligations": 1, "receipts": 1}
    proof(f"r2-{command}-opened", hold=opened.json(), counts=charges)


@pytest.mark.parametrize(
    "state,original_status,final_status,additional",
    [
        ("PENDING", "PENDING", "SENT", 1),
        ("UNKNOWN", "UNKNOWN", "UNKNOWN", 0),
        ("DECLINED", "SENT", "SENT", 0),
    ],
    ids=["pending", "unknown", "declined"],
)
async def test_r3_legacy_percent_replay_preserves_delivery_and_decline(
    scheduling_pg, auth, state, original_status, final_status, additional
):
    h = scheduling_pg
    token = await sign_in(auth)
    first_wire = DeliveryWire(h, lose_reply=state == "UNKNOWN")
    first_worker = Worker(h.kernel, first_wire)
    declined = None
    await _migrate("downgrade", "0037")
    try:
        url = await draft_terms(h, auth, token, "PERCENT_DEPOSIT", fixed_price(100_000), percent=5)
        await price(auth, url + "/pricing", token)
        await request_assessment(auth, url + "/assessment", token)
        old = (await read(h, auth, url))["quote"]
        assert "percent_prepayment" not in old["material"]
        if state != "PENDING":
            await run_quote(h, first_worker, old)
        if state == "DECLINED":
            declined = await worker_reply(h, first_worker, f"Отклоняю {old['code']}")
            assert declined["outcome"] == "DECLINED"
        original = await delivery(h, old)
        before = await quote_deliveries(h, old)
        assert len(before) == 1 and before[0]["outbox_id"] == original["outbox_id"]
        assert original["status"] == original_status and original["text"] == old["text"]
        before_view = await read(h, auth, url)
        if declined:
            assert before_view["reply_notice"] == {
                "outcome": "DECLINED",
                "message_id": declined["message_id"],
            }
        command = await price(auth, url + "/pricing", token)
        assert await read(h, auth, url) == before_view
        assert await quote_deliveries(h, old) == before
        assert await delivery(h, old) == original
        assert await counts(h) == (0, 0, 0)
    finally:
        await _migrate("upgrade", "0038")

    assert await price(auth, url + "/pricing", token) == command
    view = await read(h, auth, url)
    after = await quote_deliveries(h, old)
    wire = DeliveryWire(h)
    worker = Worker(h.kernel, wire)
    await run_pending_quote_deliveries(h, worker, after)
    final = await quote_deliveries(h, old)
    settled_view = await read(h, auth, url)
    rejected = None
    if declined or state == "UNKNOWN":
        rejected = await worker_reply(h, worker, f"Принимаю {old['code']}")
    triples = await counts(h)
    money = await money_counts(h)
    proof(
        f"r3-{state.lower()}",
        original=old,
        visible=view["quote"],
        before=before,
        after=after,
        final=final,
        decline=declined,
        notice=settled_view.get("reply_notice"),
        attempted_acceptance=rejected,
        before_calls=first_wire.calls,
        before_effects=first_wire.effects,
        calls=wire.calls,
        effects=wire.effects,
        sent_texts=[p.text for p in wire.permits],
        counts=dict(zip(("acceptances", "orders", "sessions"), triples, strict=True)),
        money=money,
    )
    assert view == before_view and settled_view["quote"] == old
    assert before == after and final == [before[0] | {"status": final_status}]
    previous_calls = 0 if state == "PENDING" else 1
    assert (first_wire.calls, first_wire.effects) == (previous_calls, previous_calls)
    assert (wire.calls, wire.effects) == (additional, additional)
    if additional:
        assert [p.text for p in wire.permits] == [old["text"]]
    else:
        assert await delivery(h, old) == original
        assert rejected["outcome"] == ("DECLINED" if declined else "DELIVERY_UNCONFIRMED")
    assert settled_view.get("reply_notice") == before_view.get("reply_notice")
    assert triples == (0, 0, 0) and money == {"obligations": 0, "receipts": 0}


@pytest.mark.parametrize("status", ["RELEASED", "EXPIRED"])
async def test_r1_first_open_of_inactive_replacement(scheduling_pg, auth, monkeypatch, status):
    h = scheduling_pg
    token = await sign_in(auth)
    work = await accept_terms(h, auth, token, "FIXED_DEPOSIT", fixed_price(400_000), amount=50_000)
    day = await prepare_day(h, auth, token, work)
    a = await hold_work(h, work, day)
    effects = await client_effects(h)
    calls = 0

    async def external_http(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("Opening an obligation must never call external HTTP")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", external_http)
    first = await post_open(auth, token, work, a.hold_id, "open-a")
    assert first.status_code == 200, first.text
    payment = inspect_open(first.json(), work, a, amount=50_000, price=400_000)
    await release(h, work, a, "release-a")
    b = await hold_work(h, work, day, "replacement-b", at="11:15")
    if status == "RELEASED":
        await release(h, work, b, "release-b")
    else:
        deadline = await shorten_hold_fixture(h, b, seconds=1)
        async with h.migrator.begin() as db:
            await db.execute(
                text(
                    "SELECT pg_sleep(greatest(0, extract(epoch FROM (:until-clock_timestamp()))))"
                ),
                {"until": deadline},
            )
    assert (await owner_get(auth, get_path(work, b.hold_id)))["hold_status"] == status
    before_first_b = await money_counts(h)
    first_b = await post_open(auth, token, work, b.hold_id, "open-b")
    after_first_b = await money_counts(h)
    proof(
        f"r1-replacement-{status.lower()}",
        hold_a=a.hold_id,
        hold_b=b.hold_id,
        obligation_id=payment["id"],
        response={"status": first_b.status_code, "body": first_b.json()},
        before=before_first_b,
        after=after_first_b,
    )
    forbidden(first_b, 409, "STALE_STATE")
    assert before_first_b == after_first_b == {"obligations": 1, "receipts": 1}
    replay = await post_open(auth, token, work, a.hold_id, "open-a")
    assert replay.status_code == 200
    assert replay.json() == first.json() | {"hold_status": "RELEASED"}
    assert await owner_get(auth, get_path(work, a.hold_id)) == replay.json()
    forbidden(
        await post_open(auth, token, work, b.hold_id, "open-a"), 409, "IDEMPOTENCY_KEY_CONFLICT"
    )
    assert await money_counts(h) == after_first_b
    active = await hold_work(h, work, day, "active-replacement", at="10:30")
    opened = await post_open(auth, token, work, active.hold_id, "active-replacement")
    assert opened.status_code == 200, opened.text
    assert inspect_open(opened.json(), work, active, amount=50_000, price=400_000) == payment
    final = await money_counts(h)
    assert final == {"obligations": 1, "receipts": 2}
    assert await client_effects(h) == effects and calls == 0
    proof(
        f"r1-sequence-{status.lower()}",
        obligation_id=payment["id"],
        replay_a={"status": replay.status_code, "body": replay.json()},
        active={"status": opened.status_code, "body": opened.json()},
        counts=final,
        new_appointments=0,
        external_calls=calls,
    )
