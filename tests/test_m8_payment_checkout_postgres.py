"""P2 through real PostgreSQL, Console auth, scheduling and the messaging worker."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from asm.messaging.errors import Code, MessagingError
from asm.messaging.worker import Worker
from generic_pg_schema import assert_current_schema, assert_schema
from m5_knowledge_search_fixtures import owner_unit
from m7_scheduling_fixtures import ZONE
from m8_payment_checkout_fixtures import (
    PaymentWire,
    ProviderWire,
    SimulatedCrash,
    accept_work,
    chat_choice,
    checkout_path,
    checkout_worker,
    open_checkout,
    proof,
    read_checkout,
    run_checkout,
)
from m8_payment_obligation_fixtures import accept_terms, fixed_price, hold_work, post_open
from sqlalchemy import text
from test_m2_1_models import event
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job, scalar
from test_m4_runtime_postgres import owner
from test_m7_scheduling_holds_postgres import backend_pid, command_http, offer, release
from test_m7_scheduling_intents_postgres import (
    approval_pg as approval_pg,
)
from test_m7_scheduling_intents_postgres import (
    assessment_pg as assessment_pg,
)
from test_m7_scheduling_intents_postgres import (
    auth as auth,
)
from test_m7_scheduling_intents_postgres import (
    db as db,
)
from test_m7_scheduling_intents_postgres import (
    intake_pg as intake_pg,
)
from test_m7_scheduling_intents_postgres import (
    portfolio_runtime_pg as portfolio_runtime_pg,
)
from test_m7_scheduling_intents_postgres import (
    pricing_pg as pricing_pg,
)
from test_m7_scheduling_intents_postgres import (
    scheduling_pg as scheduling_pg,
)
from test_m7_scheduling_intents_postgres import (
    search_pg as search_pg,
)
from test_m7_scheduling_intents_postgres import (
    seeded as seeded,
)
from test_m7_scheduling_intents_postgres import (
    service_request_pg as service_request_pg,
)
from test_m7_scheduling_owner_day_postgres import shorten_hold_fixture
from test_m7_scheduling_reschedule_postgres import initial_appointment, owner_booking
from test_tenancy_postgres import BA2

pytestmark = pytest.mark.integration


async def attempts(h):
    # Do not put provider data or capability URLs into the evidence projection.
    return await query(
        h,
        """SELECT a.id, a.obligation_id, a.hold_id, a.allocation_id, a.expires_at,
              a.amount_minor, a.status, a.reason, a.outbox_id, a.send_job_id, a.first_request_at,
              a.request_sha256, o.status AS delivery, m.text AS masked
         FROM app.payment_checkout_attempts a
         LEFT JOIN app.outbox_events o ON (o.workspace_id,o.id)=(a.workspace_id,a.outbox_id)
         LEFT JOIN app.messages m ON (m.workspace_id,m.id)=(a.workspace_id,a.message_id)
         ORDER BY a.created_at""",
    )


async def first(h, auth, provider, *, amount=50_000):
    token, work = await accept_work(h, auth, amount=amount)
    worker, adapter = await checkout_worker(h, provider)
    chat, choice, inbound, picked = await chat_choice(h, work)
    assert picked is not None and picked["result"]["outcome"] == "HELD"
    (attempt,) = await attempts(h)
    result = picked["result"]
    assert str(attempt["hold_id"]) == result["hold_id"]
    assert str(attempt["allocation_id"]) == result["allocation_id"]
    assert attempt["expires_at"] == datetime.fromisoformat(result["expires_at"])
    assert attempt["amount_minor"] == amount
    return token, work, chat, choice, inbound, picked, attempt, worker, adapter


async def modify(h, sql, **values):
    async with h.migrator.begin() as connection:
        await connection.execute(text(sql), values)


async def no_appointment(h):
    assert await scalar(h, "SELECT count(*) FROM app.appointments") == 0


async def test_p2_choice_queues_while_owner_card_is_closed(scheduling_pg, auth):
    h = scheduling_pg
    provider = ProviderWire()
    token, work, chat, phrase, inbound, picked, attempt, worker, adapter = await first(
        h, auth, provider
    )
    try:
        async with h.migrator.connect() as connection:
            await assert_current_schema(connection)
        assert picked["outbox_id"] is None and chat.wire.calls == 1
        assert await scalar(h, "SELECT count(*) FROM platform.payment_obligation_receipts") == 0
        assert (attempt["status"], attempt["delivery"]) == ("QUEUED", "PENDING")

        async def fixed_before_wire():
            (db_attempt,) = await attempts(h)
            assert db_attempt["first_request_at"] is not None and db_attempt["status"] == "UNKNOWN"
            assert db_attempt["request_sha256"] == provider.requests[-1][3]

        provider.start = fixed_before_wire
        await run_checkout(h, worker, attempt)
        (sent,) = await attempts(h)
        assert (sent["status"], sent["delivery"]) == ("READY", "SENT")
        (permit,) = worker.adapter.delivered
        assert permit.chat_id == chat.scope["chat_id"]
        assert "Предоплата 500 ₽" in permit.text and "Время удержано до" in permit.text
        assert "https://" not in sent["masked"] and "[скрыта]" in sent["masked"]
        await chat.repeat_input(inbound)
        _, _, replay = await chat.say(phrase)
        assert replay["outbox_id"] is None

        hold = str(attempt["hold_id"])
        opened = await open_checkout(auth, token, work, hold, "owner-replay")
        assert opened.status_code == 200 and opened.headers["Cache-Control"] == "no-store"
        opened_again = await open_checkout(auth, token, work, hold, "different-key")
        assert opened_again.status_code == 200
        assert opened.json()["checkout"] == opened_again.json()["checkout"]
        link = opened.json()["confirmation_url"]
        assert bool(
            link and link == opened_again.json()["confirmation_url"] and permit.text.endswith(link)
        )
        view = await read_checkout(auth, work, hold)
        assert view.json() == {"checkout": opened.json()["checkout"]}
        foreign = event(
            event_id="p2-different-client",
            message_id="p2-different-client",
            **(
                chat.scope
                | {
                    "chat_id": "p2-foreign-chat",
                    "sender_id": "p2-foreign-client",
                    "text": "Другая работа",
                }
            ),
        )
        foreign_inbox = await h.kernel.ingest_event(
            chat.wire.source(foreign.bot_identity), foreign, uuid4()
        )
        await chat.worker.execute(await claim_job(h, foreign_inbox.job_id))
        other = await scalar(
            h,
            """SELECT id FROM app.clients WHERE workspace_id=:ws AND id<>:client LIMIT 1""",
            ws=UUID(work.selection.workspace_id),
            client=UUID(work.selection.client_id),
        )
        assert other is not None
        for wrong in ({"client_id": str(other)}, {"quote_id": str(uuid4())}):
            denied = await open_checkout(auth, token, work, hold, "foreign-client", **wrong)
            assert denied.status_code == 404 and "confirmation_url" not in denied.json()
        path, refs = checkout_path(work, hold)
        denied = await command_http(
            auth,
            token,
            path.replace(work.selection.business_id, str(BA2)),
            "foreign-business",
            refs,
        )
        assert denied.status_code == 404 and "confirmation_url" not in denied.json()
        assert len(await attempts(h)) == 1
        await no_appointment(h)
        assert provider.counters(worker.adapter) == dict(
            post=1, payment_get=0, shop_get=1, objects=1, send_calls=1, delivered=1
        )
        proof("choice", **sent, **provider.counters(worker.adapter), appointment_count=0)
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("fault", ["timeout", "http500", "crash"])
async def test_p2_same_payment_after_a_lost_provider_response_and_restart(
    scheduling_pg, auth, fault
):
    h = scheduling_pg
    provider = ProviderWire()
    provider.first = fault
    _, _, _, _, _, _, attempt, worker, adapter = await first(h, auth, provider)
    try:
        claim = await claim_job(h, attempt["send_job_id"])
        if fault == "crash":
            with pytest.raises(SimulatedCrash):
                await worker.execute(claim)
            await modify(
                h,
                "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id",
                id=claim.job_id,
            )
            assert await h.kernel.recover_expired() >= 1
        else:
            await worker.execute(claim)
        (unknown,) = await attempts(h)
        assert unknown["status"] == "UNKNOWN" and unknown["first_request_at"] is not None
        assert (len(provider.objects), worker.adapter.calls) == (1, 0)
    finally:
        await adapter.aclose()
    restarted, fresh_adapter = await checkout_worker(h, provider)
    try:
        await run_checkout(h, restarted, attempt)
        (sent,) = await attempts(h)
        assert (sent["id"], sent["first_request_at"], sent["delivery"]) == (
            unknown["id"],
            unknown["first_request_at"],
            "SENT",
        )
        posts = [entry[2:] for entry in provider.requests if entry[0] == "POST"]
        assert len(posts) == 2 and bool(posts[0] == posts[1])
        totals = provider.counters(restarted.adapter)
        assert totals == dict(
            post=2, payment_get=0, shop_get=2, objects=1, send_calls=1, delivered=1
        )
        await no_appointment(h)
        proof(fault, **sent, **totals)
    finally:
        await fresh_adapter.aclose()


@pytest.mark.parametrize(
    "failure",
    ["released", "expired", "human", "channel", "delivery-ack", "delivery-crash", "window", "get"],
)
async def test_p2_delivery_and_reconciliation_boundaries(scheduling_pg, auth, failure):
    h = scheduling_pg
    provider = ProviderWire()
    _, work, _, _, _, _, attempt, worker, adapter = await first(h, auth, provider)
    try:
        hold = SimpleNamespace(hold_id=str(attempt["hold_id"]))
        if failure == "expired":
            # Shorten the synthetic fixture before it goes on the wire. The
            # worker then receives the provider's reply after the DB deadline.
            deadline = await shorten_hold_fixture(h, hold, seconds=2)
            await modify(
                h,
                "UPDATE app.payment_checkout_attempts SET expires_at=:deadline WHERE id=:id",
                id=attempt["id"],
                deadline=deadline,
            )

        async def after_create():
            if failure == "released":
                assert (await release(h, work, hold, "before-response")).outcome == "RELEASED"
            elif failure == "expired":
                await scalar(
                    h,
                    "SELECT pg_sleep(greatest(extract(epoch FROM :deadline - clock_timestamp()),0)+0.02)",
                    deadline=deadline,
                )

        async def before_send(stage):
            if failure == "delivery-crash" and stage == "before_finalize":
                raise SimulatedCrash
            if stage != "checkout_before_send":
                return
            if failure == "human":
                await owner(h, UUID(work.selection.conversation_id), "TAKEOVER")
            elif failure == "channel":
                await modify(
                    h,
                    "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id",
                    id=await scalar(
                        h,
                        "SELECT connection_id FROM app.conversations WHERE id=:id",
                        id=UUID(work.selection.conversation_id),
                    ),
                )

        provider.after_create = after_create
        worker.adapter.barrier = before_send
        if failure == "window":
            provider.first = "http500"
            await run_checkout(h, worker, attempt)
            await modify(
                h,
                """UPDATE app.payment_checkout_attempts SET created_at=statement_timestamp()-interval '25 hours',
                         first_request_at=statement_timestamp()-interval '25 hours' WHERE id=:id""",
                id=attempt["id"],
            )
        elif failure == "get":
            provider.with_link = False
            await run_checkout(h, worker, attempt)
            provider.with_link = True
        else:
            worker.adapter.lose_ack = failure == "delivery-ack"

        claim = await claim_job(h, attempt["send_job_id"])
        if failure == "delivery-crash":
            with pytest.raises(SimulatedCrash):
                await worker.execute(claim)
            await modify(
                h,
                "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id",
                id=claim.job_id,
            )
            assert await h.kernel.recover_expired() == 1
        else:
            await worker.execute(claim)
        (final,) = await attempts(h)
        sent = int(failure in ("delivery-ack", "delivery-crash", "get"))
        assert (worker.adapter.calls, worker.adapter.effects) == (sent, sent)
        assert final["delivery"] == {
            "delivery-ack": "UNKNOWN",
            "delivery-crash": "UNKNOWN",
            "get": "SENT",
        }.get(failure, "FAILED")
        assert final["reason"] == {
            "released": "HOLD_INACTIVE",
            "expired": "HOLD_INACTIVE",
            "human": "CONTEXT_CHANGED",
            "channel": "CHANNEL_RIGHTS_UNAVAILABLE",
            "window": "IDEMPOTENCE_EXPIRED",
        }.get(failure)
        if failure == "released":
            replacement = await hold_work(
                h, work, datetime.now(ZoneInfo(ZONE)).date() + timedelta(days=2), "replacement"
            )
            assert replacement.hold_id != hold.hold_id
            assert await attempts(h) == [final]
        assert len(provider.objects) == 1
        assert sum(method == "POST" for method, *_ in provider.requests) == 1
        restarted = Worker(h.kernel, PaymentWire(), checkout=worker.checkout)
        assert await h.kernel.recover_expired() == 0
        with pytest.raises(MessagingError) as stale:
            await restarted.execute(claim)
        assert stale.value.code == Code.STALE_CLAIM
        assert restarted.adapter.effects == 0 and await attempts(h) == [final]
        await no_appointment(h)
        proof(failure, **final, **provider.counters(worker.adapter))
    finally:
        await adapter.aclose()


async def test_p2_card_minimum_preserves_amount_and_no_checkout_wire(scheduling_pg, auth):
    h = scheduling_pg
    provider = ProviderWire()
    token, work, chat, _, _, picked, row, worker, adapter = await first(
        h, auth, provider, amount=99
    )
    try:
        assert picked["outbox_id"] is not None and chat.wire.calls == 2
        assert (row["reason"], row["amount_minor"], row["outbox_id"]) == ("CARD_MINIMUM", 99, None)
        reply = await open_checkout(auth, token, work, str(row["hold_id"]), "card-limit")
        assert reply.json() == {
            "checkout": (await read_checkout(auth, work, str(row["hold_id"]))).json()["checkout"],
            "confirmation_url": None,
        }
        assert reply.json()["checkout"]["reason"] == "CARD_MINIMUM"
        await no_appointment(h)
        proof("card-minimum", **row, **provider.counters(worker.adapter))
    finally:
        await adapter.aclose()


async def test_p2_upgrade_existing_obligation_and_none_then_two_owner_connections(
    scheduling_pg, auth
):
    h = scheduling_pg
    token, work = await accept_work(h, auth)
    day = datetime.now(ZoneInfo(ZONE)).date() + timedelta(days=1)
    await _migrate("downgrade", "0038")
    try:
        hold = await hold_work(h, work, day)
        before = (await post_open(auth, token, work, hold.hold_id, "0038")).json()
        none = await accept_terms(h, auth, token, "NONE", fixed_price(400_000))
        appointment, _ = await initial_appointment(
            h, none, await offer(h, none, day + timedelta(days=1), "none-before-upgrade")
        )
        none_before = await owner_booking(auth, none)
        async with h.migrator.connect() as connection:
            await assert_schema(connection, "0038", "payment_obligation_schema_profile")
    finally:
        await _migrate("upgrade", "0039")
    await h.runtime.check()
    assert (await post_open(auth, token, work, hold.hold_id, "0038")).json() == before
    assert await owner_booking(auth, none) == none_before
    assert await attempts(h) == []

    provider = ProviderWire()
    worker, adapter = await checkout_worker(h, provider)
    try:
        both = asyncio.Barrier(2)

        async def open_on_connection(key):
            async with owner_unit(h) as unit:
                pid = await backend_pid(unit)
                await both.wait()
                view = await unit.payment_checkout_owner(
                    work.selection.model_dump(mode="json"), UUID(hold.hold_id), key, None
                )
                return pid, view

        (p1, a), (p2, b) = await asyncio.wait_for(
            asyncio.gather(open_on_connection("first"), open_on_connection("second")), timeout=10
        )
        assert p1 != p2 and a == b and a["checkout"]["obligation_id"] == before["obligation"]["id"]
        (queued,) = await attempts(h)
        await run_checkout(h, worker, queued)
        (sent,) = await attempts(h)
        assert sent["delivery"] == "SENT"
        assert sent["expires_at"] == hold.expires_at
        done = await open_checkout(auth, token, none, appointment.hold_id, "no-prepayment")
        assert done.json() == {"checkout": None, "confirmation_url": None}
        assert (await read_checkout(auth, none, appointment.hold_id)).json() == {"checkout": None}
        assert await scalar(h, "SELECT count(*) FROM app.appointments") == 1
        assert await scalar(h, "SELECT count(*) FROM app.payment_obligations") == 1
        proof(
            "upgrade-0038-0039",
            **sent,
            none_appointment=appointment.appointment_id,
            pg_connections=[p1, p2],
            **provider.counters(worker.adapter),
        )
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("status", ["canceled", "succeeded"])
async def test_p2_keeps_the_final_object_without_url(scheduling_pg, auth, status):
    h = scheduling_pg
    provider = ProviderWire()
    provider.status = status
    token, work, _, _, _, _, attempt, worker, adapter = await first(h, auth, provider)
    try:
        await run_checkout(h, worker, attempt)
        (final,) = await attempts(h)
        assert final["status"] == ("CANCELED" if status == "canceled" else "NO_LINK")
        assert (
            await scalar(h, "SELECT provider_status FROM app.payment_checkout_attempts") == status
        )
        orig_hold = str(attempt["hold_id"])
        no_link = await open_checkout(auth, token, work, orig_hold, "read-final")
        assert no_link.status_code == 200 and no_link.json()["confirmation_url"] is None
        assert no_link.json()["checkout"]["id"] == str(attempt["id"])
        assert len(provider.objects) == 1 and worker.adapter.effects == 0
        result = await open_checkout(
            auth, token, work, orig_hold, "replace", replace_attempt_id=str(attempt["id"])
        )
        if status == "canceled":
            assert result.status_code == 200 and result.json()["checkout"]["id"] != str(
                attempt["id"]
            )
            replay = await open_checkout(
                auth, token, work, orig_hold, "replace", replace_attempt_id=str(attempt["id"])
            )
            assert replay.json() == result.json()
            assert len(await attempts(h)) == 2
            bad = await open_checkout(auth, token, work, orig_hold, "replace")
            assert (
                bad.status_code == 409 and bad.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
            )
        else:
            assert result.status_code == 409 and result.json()["error"]["code"] == "STALE_STATE"
            assert len(await attempts(h)) == 1
        totals = provider.counters(worker.adapter)
        assert totals == dict(
            post=1, payment_get=0, shop_get=1, objects=1, send_calls=0, delivered=0
        )
        await no_appointment(h)
        proof("final-" + status, **final, **totals, attempts=len(await attempts(h)))
    finally:
        await adapter.aclose()


async def test_p2_unverified_test_shop_stops_before_creation(scheduling_pg, auth):
    h = scheduling_pg
    token, work = await accept_work(h, auth)
    provider = ProviderWire()
    provider.confirmed = False
    worker, adapter = await checkout_worker(h, provider)
    try:
        _, _, _, picked = await chat_choice(h, work)
        assert picked["result"]["outcome"] == "HELD" and picked["outbox_id"] is not None
        hold = picked["result"]["hold_id"]
        refused = await open_checkout(auth, token, work, hold, "unverified-shop")
        assert refused.json() == {"checkout": None, "confirmation_url": None}
        assert await attempts(h) == []
        totals = provider.counters(worker.adapter)
        assert totals == dict(
            post=0, payment_get=0, shop_get=1, objects=0, send_calls=0, delivered=0
        )
        proof("unverified-test-shop", hold=hold, attempts=0, **totals)
    finally:
        await adapter.aclose()
