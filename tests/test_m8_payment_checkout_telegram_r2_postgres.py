"""Two Telegram deliveries with overlapping connection-rights observations."""

import asyncio
import hashlib
import json
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from functools import partial
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from asm.messaging.database import worker_active
from m7_scheduling_fixtures import ZONE
from m8_payment_checkout_fixtures import (
    ProviderWire,
    accept_telegram_agreement,
    accept_telegram_work,
    checkout_worker,
    open_checkout,
    proof,
    run_checkout,
)
from m8_payment_obligation_fixtures import hold_work
from test_m2_1_postgres import query
from test_m2_3_db_postgres import EXTERNAL
from test_m3_1_native_context_postgres import scalar
from test_m4_delivery_postgres import refresh_synthetic_observation
from test_m4_reply_rights_postgres import connection, telegram
from test_m7_scheduling_owner_day_postgres import shorten_hold_fixture
from test_m8_payment_checkout_postgres import (
    approval_pg as approval_pg,
)
from test_m8_payment_checkout_postgres import (
    assessment_pg as assessment_pg,
)
from test_m8_payment_checkout_postgres import (
    attempts,
    modify,
    no_appointment,
)
from test_m8_payment_checkout_postgres import (
    auth as auth,
)
from test_m8_payment_checkout_postgres import (
    db as db,
)
from test_m8_payment_checkout_postgres import (
    intake_pg as intake_pg,
)
from test_m8_payment_checkout_postgres import (
    portfolio_runtime_pg as portfolio_runtime_pg,
)
from test_m8_payment_checkout_postgres import (
    pricing_pg as pricing_pg,
)
from test_m8_payment_checkout_postgres import (
    scheduling_pg as scheduling_pg,
)
from test_m8_payment_checkout_postgres import (
    search_pg as search_pg,
)
from test_m8_payment_checkout_postgres import (
    seeded as seeded,
)
from test_m8_payment_checkout_postgres import (
    service_request_pg as service_request_pg,
)

pytestmark = pytest.mark.integration


def link_digest(link):
    return hashlib.sha256(link.encode()).hexdigest() if link is not None else None


@pytest.mark.parametrize(
    "case", ["sent", "revoked", "expired", "generation", "unknown", "exhausted"]
)
async def test_r2_concurrent_telegram_checkout(scheduling_pg, auth, case):
    h = scheduling_pg
    token, work_a = await accept_telegram_work(h, auth)
    chat_a = h.intake_scope["chat"]
    work_b = await accept_telegram_agreement(h, auth, token)
    chats = {"A": chat_a, "B": h.intake_scope["chat"]}
    works = {"A": work_a, "B": work_b}
    assert chats["A"] != chats["B"] and work_a.selection.client_id != work_b.selection.client_id
    day = datetime.now(ZoneInfo(ZONE)).date() + timedelta(days=1)
    holds = {
        "A": await hold_work(h, work_a, day, "r2-a"),
        "B": await hold_work(h, work_b, day + timedelta(days=1), "r2-b"),
    }
    provider = ProviderWire()
    probes = {"A": 0, "B": 0}
    sends = {"A": 0, "B": 0}
    messages = {"A": [], "B": []}
    first_probe, release_first = asyncio.Event(), asyncio.Event()
    conversation_b = UUID(work_b.selection.conversation_id)

    async def wire(label, request):
        assert not worker_active() and request.method == "POST"
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        assert body["business_connection_id"] == EXTERNAL
        if method == "getBusinessConnection":
            probes[label] += 1
            if label == "A" and probes[label] == 1:
                first_probe.set()
                await release_first.wait()
            elif label == "A" and case == "exhausted":
                await refresh_synthetic_observation(h, conversation_b)
            return connection(reply=not (label == "A" and probes[label] > 1 and case == "revoked"))
        assert method == "sendMessage"
        sends[label] += 1
        assert body["chat_id"] == chats[label]
        messages[label].append(body["text"])
        if label == "A" and case == "unknown":
            raise httpx.ReadTimeout("simulated loss after delivery", request=request)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 91239 if label == "A" else 91240,
                    "chat": {"id": int(body["chat_id"]), "type": "private"},
                    "business_connection_id": EXTERNAL,
                },
            },
        )

    async def rights():
        (row,) = await query(
            h,
            "SELECT generation, observation_version, can_reply FROM platform.telegram_connection_state WHERE connection_id=:id",
            id=h.telegram_connection,
        )
        return row

    async with AsyncExitStack() as resources:

        async def start(label):
            client = telegram(partial(wire, label))
            resources.push_async_callback(client.aclose)
            worker, adapter = await checkout_worker(h, provider, telegram_client=client)
            resources.push_async_callback(adapter.aclose)
            return worker

        worker_a, worker_b = await start("A"), await start("B")
        assert worker_a.worker_id != worker_b.worker_id
        deadlines = {label: hold.expires_at for label, hold in holds.items()}
        if case == "expired":
            deadlines["A"] = await shorten_hold_fixture(h, holds["A"], seconds=8)
        queued = {}
        for label, hold in holds.items():
            response = await open_checkout(auth, token, works[label], hold.hold_id, "r2-" + label)
            assert response.status_code == 200
            queued[label] = response.json()["checkout"]["id"]
        assert queued["A"] != queued["B"] and deadlines["A"] != deadlines["B"]
        outgoing = {str(row["id"]): row for row in await attempts(h)}

        parked = asyncio.create_task(run_checkout(h, worker_a, outgoing[queued["A"]]))
        try:
            await asyncio.wait_for(first_probe.wait(), timeout=5)
            original = await rights()
            await run_checkout(h, worker_b, outgoing[queued["B"]])
            newer = await rights()
            assert (newer["generation"], newer["observation_version"], newer["can_reply"]) == (
                original["generation"],
                original["observation_version"] + 1,
                True,
            )
            if case == "generation":
                await modify(
                    h,
                    """UPDATE platform.telegram_connection_state SET generation=generation+1,
                           observation_version=observation_version+1 WHERE connection_id=:id""",
                    id=h.telegram_connection,
                )
                await refresh_synthetic_observation(h, conversation_b)
        finally:
            release_first.set()
            await parked

        async def snapshot(stage):
            state = {str(row["id"]): row for row in await attempts(h)}
            captured = {}
            for label, attempt_id in queued.items():
                row = state[attempt_id]
                (job,) = await query(
                    h,
                    """SELECT j.status AS job_status,j.error_code AS job_error,
                              j.attempt_count,o.attempt_id AS dispatch_id
                       FROM platform.messaging_jobs j
                       JOIN app.outbox_events o ON (o.workspace_id,o.id)=(j.workspace_id,j.outbox_id)
                       WHERE j.id=:id""",
                    id=row["send_job_id"],
                )
                ((key, payment),) = [
                    (key, value)
                    for key, value in provider.objects.items()
                    if value["metadata"]["asm_attempt_id"] == attempt_id
                ]
                posts = sum(op == "POST" and k == key for op, _, k, _ in provider.requests)
                response = await open_checkout(
                    auth, token, works[label], holds[label].hold_id, "r2-" + label
                )
                assert response.status_code == 200
                view = response.json()
                link = view["confirmation_url"]
                original_link = provider.payment_view(payment)["confirmation"]["confirmation_url"]
                assert link is None or bool(link == original_link)
                assert view["checkout"]["id"] == attempt_id
                assert view["checkout"]["delivery"] == row["delivery"]
                assert view["checkout"]["reason"] == row["reason"]
                assert (row["expires_at"], row["amount_minor"]) == (deadlines[label], 50_000)
                assert payment["amount"] == {"value": "500.00", "currency": "RUB"}
                assert sends[label] == len(messages[label])
                label_time = (
                    deadlines[label].astimezone(ZoneInfo(ZONE)).strftime("%d.%m.%Y %H:%M:%S")
                )
                if messages[label]:
                    assert bool(
                        messages[label]
                        == [
                            f"Предоплата 500 ₽. Время удержано до {label_time} ({ZONE}).\nСсылка на оплату: {original_link}"
                        ]
                    )
                proof(
                    "telegram-r2",
                    case_variant=case,
                    stage=stage,
                    chat=label,
                    **row,
                    **job,
                    payment=payment["id"],
                    post=posts,
                    objects=1,
                    get_business_connection=probes[label],
                    send_message=sends[label],
                    delivered=len(messages[label]),
                    replay_has_link=bool(link),
                )
                captured[label] = (row, job, link_digest(link))
            assert provider.counters(worker_a.adapter) == dict(
                post=2,
                payment_get=0,
                shop_get=3 if stage == "restart" else 2,
                objects=2,
                send_calls=0,
                delivered=0,
            )
            await no_appointment(h)
            return captured

        collision = await snapshot("collision")
        row, job, link_a = collision["A"]
        assert collision["B"][0]["delivery"] == "SENT" and len(messages["B"]) == 1
        assert (row["status"], probes["A"], len(messages["A"]), job["dispatch_id"]) == (
            "READY",
            1,
            0,
            None,
        )
        if case == "generation":
            assert (row["delivery"], row["reason"], job["job_status"], link_a) == (
                "FAILED",
                "CHANNEL_RIGHTS_UNAVAILABLE",
                "DEAD",
                None,
            )
            return
        assert (row["delivery"], row["reason"], job["job_status"], job["attempt_count"]) == (
            "PENDING",
            None,
            "READY",
            1,
        )
        assert link_a

        if case == "expired":
            await scalar(
                h,
                "SELECT pg_sleep(greatest(extract(epoch FROM :deadline-clock_timestamp()),0)+0.02)",
                deadline=deadlines["A"],
            )
        for _ in range(4 if case == "exhausted" else 1):
            await run_checkout(h, worker_a, row)
        final = await snapshot("final")
        sent, finished, link = final["A"]
        assert (sent["id"], sent["outbox_id"], sent["send_job_id"], sent["first_request_at"]) == (
            row["id"],
            row["outbox_id"],
            row["send_job_id"],
            row["first_request_at"],
        )
        if case == "exhausted":
            assert (
                sent["delivery"],
                sent["reason"],
                finished["job_status"],
                finished["job_error"],
            ) == ("FAILED", None, "DEAD", "RETRY_EXHAUSTED")
            assert finished["attempt_count"] == probes["A"] == 5
            assert not messages["A"] and bool(link == link_a)
            return
        assert finished["attempt_count"] == 2
        if case in ("revoked", "expired"):
            reason = "CHANNEL_RIGHTS_UNAVAILABLE" if case == "revoked" else "HOLD_INACTIVE"
            assert (sent["delivery"], sent["reason"], finished["job_status"], link) == (
                "FAILED",
                reason,
                "DEAD",
                None,
            )
            assert not messages["A"] and probes["A"] == (2 if case == "revoked" else 1)
            return

        assert (sent["delivery"], probes["A"]) == ("UNKNOWN" if case == "unknown" else "SENT", 2)
        assert len(messages["A"]) == 1 and bool(link == link_a)
        assert final["A"][2] and final["B"][2] and final["A"][2] != final["B"][2]
        await h.runtime.engine.dispose()
        fresh = await start("A")
        for label, hold in holds.items():
            repeated = await open_checkout(
                auth, token, works[label], hold.hold_id, "fresh-" + label
            )
            assert repeated.status_code == 200
            assert repeated.json()["checkout"]["id"] == queued[label]
            assert link_digest(repeated.json()["confirmation_url"]) == final[label][2]
        await fresh.database.recover_expired()
        await fresh.run_once()
        assert await snapshot("restart") == final
        assert probes == {"A": 2, "B": 1} and len(messages["A"]) == len(messages["B"]) == 1
