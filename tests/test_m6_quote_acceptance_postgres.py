"""M6.3C uses ordinary input, the leased worker and the owner quote read."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code
from asm.messaging.worker import Worker
from asm.telegram.database import TelegramIngress
from asm.telegram.normalization import normalize_update_v2
from sqlalchemy import text
from test_m2_1_postgres import event
from test_m2_1_schema_postgres import _migrate
from test_m2_3_db_postgres import BOT
from test_m3_1_native_context_postgres import claim_job, control, reconcile, scalar
from test_m3_1_provenance_postgres import raw
from test_m4_reply_rights_postgres import connection, telegram
from test_m4_runtime_postgres import COUNTER
from test_m5_intake_postgres import next_turn, summary
from test_m6_owner_decisions_postgres import FIXED_DURATION, contract, owner_get
from test_m6_pricing_postgres import draft_for_size, formula_price, price, publish, sign_in
from test_m6_quote_delivery_postgres import (
    DeliveryWire,
    delivery,
    exact_ready,
    run_quote,
)
from test_m6_quote_delivery_postgres import approval_pg as approval_pg
from test_m6_quote_delivery_postgres import assessment_pg as assessment_pg
from test_m6_quote_delivery_postgres import auth as auth
from test_m6_quote_delivery_postgres import db as db
from test_m6_quote_delivery_postgres import intake_pg as intake_pg
from test_m6_quote_delivery_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_quote_delivery_postgres import pricing_pg as pricing_pg
from test_m6_quote_delivery_postgres import search_pg as search_pg
from test_m6_quote_delivery_postgres import seeded as seeded
from test_m6_quote_delivery_postgres import service_request_pg as service_request_pg
from test_m6_service_assessments_api_postgres import create_draft, request_assessment
from test_m6_service_requests_api_postgres import route

pytestmark = pytest.mark.integration


def tg_reply(h, value, *, chat=None, old_date=None, **extras):
    n = next(COUNTER)
    chat = chat or h.intake_scope["chat"]
    event = raw(n, n, value=value, chat=chat, sender=chat)
    body = event["business_message"]
    body["date"] = int(datetime.now(UTC).timestamp()) if old_date is None else old_date
    body.update(extras)
    return event


async def telegram_inbox(h, event, *, legacy_projection=False):
    ingress = TelegramIngress(h.kernel, BOT)
    if legacy_projection:
        return await ingress.ingest(normalize_update_v2(BOT, event).model_dump(), uuid4())
    return await ingress.ingest_update(event, uuid4())


async def process(h, receipt, kernel=None):
    claim = await claim_job(h, receipt.job_id)
    return await (kernel or h.kernel).process_inbox(claim)


async def new_reply(h, text_value, **kwargs):
    return await process(h, await telegram_inbox(h, tg_reply(h, text_value, **kwargs)))


async def controlled_reply(h, value):
    number = str(next(COUNTER))
    message = event(
        event_id=number,
        message_id=number,
        occurred_at=datetime.now(UTC),
        **(h.intake_scope | {"text": value}),
    )
    return await h.kernel.ingest_event(h.adapter.source(message.bot_identity), message, uuid4())


def edit_reply(h, original, replacement):
    edited = tg_reply(h, replacement)
    edit = edited.pop("business_message")
    edit["message_id"] = original["business_message"]["message_id"]
    edit["date"] = original["business_message"]["date"]
    edit["edit_date"] = int(datetime.now(UTC).timestamp())
    edited["edited_business_message"] = edit
    return edited


async def telegram_send(h, quote, *, unknown=False, inflight=None):
    calls = []

    async def wire(req):
        method = req.url.path.rsplit("/", 1)[-1]
        calls.append(method)
        if method == "getBusinessConnection":
            return connection()
        assert method == "sendMessage"
        if inflight:
            await inflight()
        if unknown:
            raise httpx.ReadTimeout("synthetic lost ACK", request=req)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 91231 + len(calls),
                    "chat": {"id": int(h.intake_scope["chat"]), "type": "private"},
                    "business_connection_id": connection().json()["result"]["id"],
                },
            },
        )

    client = telegram(wire)
    try:
        await run_quote(h, Worker(h.kernel, DeliveryWire(h), telegram=client), quote)
    finally:
        await client.aclose()
    assert calls == ["getBusinessConnection", "sendMessage"]
    assert (await delivery(h, quote))["status"] == ("UNKNOWN" if unknown else "SENT")
    if not unknown:
        # Telegram only supplies whole seconds for a NEW message's original date.
        await asyncio.sleep(1.01)


async def counts(h):
    return tuple(
        [
            await scalar(h, f"SELECT count(*) FROM app.{table}")
            for table in ("quote_acceptances", "service_orders", "service_sessions")
        ]
    )


async def read(h, auth, url, outcome=None):
    result = await owner_get(auth, url + "/quote")
    if outcome:
        assert result["reply_notice"]["outcome"] == outcome
    return result


async def test_real_telegram_requires_new_own_text_and_replays_the_first_message(approval_pg, auth):
    h = approval_pg
    cid, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    phrase = f"Принимаю {quote['code']}"
    forwarded = await new_reply(h, phrase, forward_origin={"type": "hidden_user"})
    quoted = await new_reply(
        h, phrase, entities=[{"type": "blockquote", "offset": 0, "length": len(phrase)}]
    )
    legacy = tg_reply(h, phrase)
    legacy_receipt = await telegram_inbox(h, legacy, legacy_projection=True)
    assert (await telegram_inbox(h, legacy)).code == "DUPLICATE"
    legacy_result = await process(h, legacy_receipt)
    unrelated = await new_reply(h, phrase, chat=str(int(h.intake_scope["chat"]) + 9999))
    prefix = await new_reply(h, "Цитата: " + phrase)
    caption = tg_reply(h, phrase)
    payload = caption["business_message"]
    payload["caption"] = payload.pop("text")
    payload["photo"] = [{"file_id": "test-acceptance-caption", "width": 10, "height": 10}]
    photo = await process(h, await telegram_inbox(h, caption))
    old = tg_reply(h, "Уточнение")
    await process(h, await telegram_inbox(h, old))
    edit_receipt = await telegram_inbox(h, edit_reply(h, old, phrase))
    if edit_receipt.job_id is not None:
        await process(h, edit_receipt)
    for result in (forwarded, quoted, legacy_result, unrelated, prefix, photo):
        assert result.message_id and result.quote_reply is None
    assert await counts(h) == (0, 0, 0)
    ambiguous = await new_reply(h, "да")
    assert ambiguous.quote_reply.outcome == "NEEDS_CLARIFICATION"
    assert (await read(h, auth, url, "NEEDS_CLARIFICATION"))["reply_notice"]["message_id"] == str(
        ambiguous.message_id
    )

    # Review the real Telegram edit observation before resuming automation.
    await control(h, cid, "TAKEOVER")
    await reconcile(h, cid)
    await control(h, cid)
    await asyncio.sleep(1.01)
    original = tg_reply(h, phrase)
    result = await process(h, await telegram_inbox(h, original))
    first = result.quote_reply
    assert first.outcome == "ACCEPTED" and first.message_id == result.message_id
    repeated = await new_reply(h, phrase)
    assert repeated.message_id != result.message_id and repeated.quote_reply == first
    saved = (await read(h, auth, url))["agreement"]
    assert (
        saved["quote"] == quote and saved["scheduled_at"] is None and saved["status"] == "PLANNED"
    )
    assert saved["source"]["message_id"] == str(result.message_id)
    assert saved["source"]["text"] == phrase and saved["source"]["status"] == "AVAILABLE"
    assert await counts(h) == (1, 1, 1)
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.audit_events WHERE event_type='QUOTE_ACCEPTED' AND object_id=:o",
            o=first.order_id,
        )
        == 1
    )
    await process(h, await telegram_inbox(h, edit_reply(h, original, "Изменённая реплика")))
    changed = (await read(h, auth, url))["agreement"]
    assert changed == saved | {"source": saved["source"] | {"status": "CHANGED", "text": None}}
    assert await counts(h) == (1, 1, 1)
    print("M6.3C Telegram", json.dumps(saved, ensure_ascii=False))


async def test_ack_loss_concurrency_and_atomic_rollback(approval_pg, auth):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    phrase = f"Принимаю {quote['code']}"
    a, b = [await telegram_inbox(h, tg_reply(h, phrase)) for _ in range(2)]
    ca, cb = [await claim_job(h, receipt.job_id) for receipt in (a, b)]

    class Fault(RuntimeError):
        pass

    async def before(name):
        if name == "process_before_commit":
            raise Fault("rollback after all three writes")

    with pytest.raises(Fault):
        await MessagingDatabase(h.runtime.engine, environment="TEST", barrier=before).process_inbox(
            ca
        )
    assert await counts(h) == (0, 0, 0)
    assert "agreement" not in await read(h, auth, url)

    async def after(name):
        if name == "process_after_commit":
            raise Fault("lose response after commit")

    lossy = MessagingDatabase(h.runtime.engine, environment="TEST", barrier=after)
    lost, normal = await asyncio.gather(
        lossy.process_inbox(ca), h.kernel.process_inbox(cb), return_exceptions=True
    )
    assert isinstance(lost, Fault)
    replay = await h.kernel.process_inbox(ca)
    replay_b = await h.kernel.process_inbox(cb)
    assert normal.message_id == replay_b.message_id
    assert replay.quote_reply.outcome == "ACCEPTED" and replay.quote_reply == replay_b.quote_reply
    assert replay.quote_reply.message_id == replay.message_id
    assert await counts(h) == (1, 1, 1)
    assert (await read(h, auth, url))["agreement"]["source"]["message_id"] == str(
        replay.quote_reply.message_id
    )
    print("M6.3C concurrent replay", replay.quote_reply.model_dump_json())


@pytest.mark.parametrize("mode", ["early", "unknown", "human"])
async def test_reply_requiring_review_is_never_upgraded_retroactively(approval_pg, auth, mode):
    h = approval_pg
    cid, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    phrase = f"Принимаю {quote['code']}"
    receipt = None
    if mode == "early":

        async def reply_while_dispatching():
            nonlocal receipt
            assert (await delivery(h, quote))["status"] == "DISPATCHING"
            receipt = await telegram_inbox(h, tg_reply(h, phrase))

        await telegram_send(h, quote, inflight=reply_while_dispatching)
    else:
        await telegram_send(h, quote, unknown=mode == "unknown")
        if mode == "human":
            await control(h, cid, operation="TAKEOVER")
        receipt = await telegram_inbox(h, tg_reply(h, phrase))
    assert receipt is not None
    claim = await claim_job(h, receipt.job_id)
    result = await h.kernel.process_inbox(claim)
    outcome = "HUMAN_CONTROL" if mode == "human" else "DELIVERY_UNCONFIRMED"
    assert result.message_id and result.quote_reply.outcome == outcome
    assert await h.kernel.process_inbox(claim) == result
    assert (await read(h, auth, url, outcome))["reply_notice"]["message_id"] == str(
        result.message_id
    )
    assert await counts(h) == (0, 0, 0)
    if mode == "human":
        await reconcile(h, cid)
        await control(h, cid)
        await asyncio.sleep(1.01)
    if mode != "unknown":
        assert await h.kernel.process_inbox(claim) == result
        fresh = await new_reply(h, phrase)
        assert fresh.quote_reply.outcome == "ACCEPTED"
        assert await counts(h) == (1, 1, 1)


async def test_replaced_quote_decline_and_current_terms_are_serialized(approval_pg, auth):
    h = approval_pg
    _, token, _, url, old = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, old)
    old_reply = await telegram_inbox(h, tg_reply(h, f"Принимаю {old['code']}"))
    revised = contract(formula_price(), FIXED_DURATION, deposit="FULL_PREPAYMENT")
    await publish(h, revised)
    await price(auth, url + "/pricing", token)
    await request_assessment(auth, url + "/assessment", token)
    new = (await read(h, auth, url))["quote"]
    assert new["code"] != old["code"] and new["material"]["deposit"]["mode"] == "FULL_PREPAYMENT"
    assert (await process(h, old_reply)).quote_reply.outcome == "STALE"
    await price(auth, url + "/pricing", token)
    await telegram_send(h, new)
    decline = await new_reply(h, f"Отклоняю {new['code']}")
    assert decline.quote_reply.outcome == "DECLINED"
    assert (await new_reply(h, f"Принимаю {new['code']}")).quote_reply.outcome == "DECLINED"
    assert await counts(h) == (0, 0, 0)


async def ready_two_works(h, auth, *, use_telegram=False):
    await publish(h, contract(formula_price(range_add_minor=50_000), FIXED_DURATION))
    token = await sign_in(auth)
    cid, intake, model, _, a_id = await draft_for_size(
        h, auth, token, "20 mm", telegram=use_telegram
    )
    a_url = f"{route(cid)}/{a_id}"
    await price(auth, a_url + "/pricing", token)
    await request_assessment(auth, a_url + "/assessment", token)
    a = (await read(h, auth, a_url))["quote"]
    worker = Worker(h.kernel, DeliveryWire(h))
    if use_telegram:
        await telegram_send(h, a)
    else:
        await run_quote(h, worker, a)
    model.values = dict(
        idea="bird", placement="shoulder", approximate_size="21 mm", style="linework"
    )
    model.switch = True
    await next_turn(h, intake, "Separate bird shoulder 21 mm linework")
    b_id = await create_draft(auth, cid, token, await summary(h, cid))
    b_url = f"{route(cid)}/{b_id}"
    await price(auth, b_url + "/pricing", token)
    await request_assessment(auth, b_url + "/assessment", token)
    b = (await read(h, auth, b_url))["quote"]
    if use_telegram:
        await telegram_send(h, b)
    else:
        await run_quote(h, worker, b)
    return token, a_url, a, b_url, b


async def test_two_works_keep_separate_orders_and_published_range(approval_pg, auth):
    h = approval_pg
    token, a_url, a, b_url, b = await ready_two_works(h, auth)

    async def send(value):
        return await process(h, await controlled_reply(h, value))

    await send("Нейтральная реплика")
    after_b = await send(f"Принимаю {b['code']}")
    assert after_b.quote_reply.outcome == "ACCEPTED"
    assert "agreement" not in await read(h, auth, a_url)
    saved_b = (await read(h, auth, b_url))["agreement"]
    assert saved_b["quote"]["material"]["price_range"] == {
        "authority": "PROVISIONAL",
        "lower_minor": 400000,
        "upper_minor": 450000,
    }
    assert await counts(h) == (1, 1, 1)
    after_a = await send(f"Принимаю {a['code']}")
    assert after_a.quote_reply.outcome == "ACCEPTED"
    saved_a = (await read(h, auth, a_url))["agreement"]
    assert saved_a["quote"] == a and saved_b["quote"] == b
    keys = ("acceptance_id", "order_id", "session_id")
    assert len({entry[k] for entry in (saved_a, saved_b) for k in keys}) == 6
    assert await counts(h) == (2, 2, 2)
    await publish(h, contract(formula_price(), FIXED_DURATION, deposit="FULL_PREPAYMENT"))
    await request_assessment(auth, b_url + "/assessment", token)
    await price(auth, b_url + "/pricing", token)
    assert (await read(h, auth, b_url))["agreement"] == saved_b
    assert (await read(h, auth, a_url))["agreement"] == saved_a
    print("M6.3C two works", json.dumps({"A": saved_a, "B": saved_b}, ensure_ascii=False))


def outcome(result):
    return result.quote_reply.outcome if result.quote_reply else None


def report_r1(case, **fields):
    print("M6.3C-R1", json.dumps({"case": case, **fields}, default=str, ensure_ascii=False))


@pytest.mark.parametrize(
    ("case", "use_telegram"),
    [
        ("decline-before-accept", True),
        ("two-queued-works", True),
        ("two-queued-works", False),
        ("accept-before-thanks", True),
    ],
)
async def test_r1_prequeued_inbox_keeps_decisions_in_received_order(
    approval_pg, auth, case, use_telegram
):
    h = approval_pg
    if case == "two-queued-works":
        _, a_url, a, b_url, b = await ready_two_works(h, auth, use_telegram=use_telegram)
        phrases = (f"Принимаю {b['code']}", f"Принимаю {a['code']}")
    else:
        _, _, _, a_url, a = await exact_ready(h, auth, use_telegram=True)
        await telegram_send(h, a)
        phrases = (
            (f"Отклоняю {a['code']}", f"Принимаю {a['code']}")
            if case == "decline-before-accept"
            else (f"Принимаю {a['code']}", "Спасибо")
        )
    receipts = [
        await telegram_inbox(h, tg_reply(h, phrase))
        if use_telegram
        else await controlled_reply(h, phrase)
        for phrase in phrases
    ]
    assert receipts[0].accepted_at < receipts[1].accepted_at
    claims = [await claim_job(h, r.job_id) for r in receipts]
    processed = [await h.kernel.process_inbox(c) for c in claims]
    first = await h.kernel.process_inbox(claims[0])
    second = processed[1]
    a_view = await read(h, auth, a_url)
    b_view = await read(h, auth, b_url) if case == "two-queued-works" else {}
    triples = await counts(h)
    report_r1(
        case,
        provider="TELEGRAM" if use_telegram else "CONTROLLED",
        first_processing=outcome(processed[0]),
        outcomes=[outcome(first), outcome(second)],
        triples=triples,
        inbox_messages=[first.message_id, second.message_id],
        a=a_view.get("reply_notice"),
        b=b_view.get("reply_notice"),
        accepted=[
            {
                k: record["agreement"][k]
                for k in ("acceptance_id", "order_id", "session_id", "source")
            }
            for record in (a_view, b_view)
            if "agreement" in record
        ],
    )
    assert outcome(processed[0]) is None
    if case == "decline-before-accept":
        assert triples == (0, 0, 0)
        assert [outcome(first), outcome(second)] == ["DECLINED", "DECLINED"]
        assert a_view["reply_notice"] == {
            "outcome": "DECLINED",
            "message_id": str(first.message_id),
        }
        return

    a_source = first if case == "accept-before-thanks" else second
    assert outcome(a_source) == "ACCEPTED"
    assert a_view["agreement"]["source"]["message_id"] == str(a_source.message_id)
    if case == "two-queued-works":
        assert triples == (2, 2, 2)
        assert outcome(first) == "ACCEPTED"
        assert b_view["agreement"]["source"]["message_id"] == str(first.message_id)
        fields = ("acceptance_id", "order_id", "session_id")
        assert len({v["agreement"][k] for v in (a_view, b_view) for k in fields}) == 6
        assert (await h.kernel.process_inbox(claims[1])).quote_reply == second.quote_reply
    else:
        assert triples == (1, 1, 1)
        assert outcome(second) is None
    assert (await h.kernel.process_inbox(claims[0])).quote_reply == first.quote_reply


@pytest.mark.parametrize("with_open_b", [False, True])
async def test_r1_yes_only_clarifies_open_sent_offers(approval_pg, auth, with_open_b):
    h = approval_pg
    if with_open_b:
        _, a_url, a, b_url, _ = await ready_two_works(h, auth, use_telegram=True)
    else:
        _, _, _, a_url, a = await exact_ready(h, auth, use_telegram=True)
        await telegram_send(h, a)
    decline = await new_reply(h, f"Отклоняю {a['code']}")
    assert await read(h, auth, a_url, "DECLINED")
    yes = await new_reply(h, "да")
    a_notice = (await read(h, auth, a_url)).get("reply_notice")
    b_notice = (await read(h, auth, b_url)).get("reply_notice") if with_open_b else None
    triples = await counts(h)
    report_r1("decline-then-yes", with_open_b=with_open_b, a=a_notice, b=b_notice, triples=triples)
    assert triples == (0, 0, 0)
    assert a_notice == {"outcome": "DECLINED", "message_id": str(decline.message_id)}
    if with_open_b:
        assert b_notice == {"outcome": "NEEDS_CLARIFICATION", "message_id": str(yes.message_id)}
    else:
        assert yes.quote_reply is None


async def test_r1_reversed_workers_keep_decline_before_accept(approval_pg, auth):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    decline = await telegram_inbox(h, tg_reply(h, f"Отклоняю {quote['code']}"))
    accept = await telegram_inbox(h, tg_reply(h, f"Принимаю {quote['code']}"))
    decline_claim, accept_claim = [await claim_job(h, r.job_id) for r in (decline, accept)]
    awaited = await h.kernel.process_inbox(accept_claim)
    assert awaited.message_id and outcome(awaited) is None
    assert await h.kernel.process_inbox(accept_claim) == awaited
    assert await counts(h) == (0, 0, 0)
    final = await h.kernel.process_inbox(decline_claim)
    assert outcome(final) == "DECLINED"
    assert outcome(await h.kernel.process_inbox(accept_claim)) == "DECLINED"
    assert (await read(h, auth, url, "DECLINED"))["reply_notice"]["message_id"] == str(
        final.message_id
    )
    assert await counts(h) == (0, 0, 0)


@pytest.mark.parametrize("blocker", ["edit", "failed-input"])
async def test_r1_recheck_never_bypasses_a_pending_edit_or_failed_input(approval_pg, auth, blocker):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    original = tg_reply(h, f"Принимаю {quote['code']}")
    accept = await telegram_inbox(h, original)
    event = edit_reply(h, original, "Уточню позже") if blocker == "edit" else tg_reply(h, "Спасибо")
    later = await telegram_inbox(h, event)
    accept_claim, later_claim = [await claim_job(h, r.job_id) for r in (accept, later)]
    waiting = await h.kernel.process_inbox(accept_claim)
    assert waiting.message_id and outcome(waiting) is None
    assert await counts(h) == (0, 0, 0)

    if blocker == "edit":
        assert (await h.kernel.process_inbox(later_claim)).code == "MATERIAL_PROCESSED"
        expected = "INVALID_MESSAGE"
    else:
        resent = await h.kernel.retry(later_claim, Code.DEPENDENCY_UNAVAILABLE, retryable=False)
        assert resent["status"] == "DEAD"
        expected = "REVIEW_REQUIRED"
    final = await h.kernel.process_inbox(accept_claim)
    assert outcome(final) == expected and final.message_id == waiting.message_id
    assert "agreement" not in await read(h, auth, url)
    assert await counts(h) == (0, 0, 0)
    report_r1("native-barrier", blocker=blocker, outcome=outcome(final), triples=await counts(h))


async def test_expiry_after_ingest_and_before_commit_leaves_no_order(approval_pg, auth):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    receipt = await telegram_inbox(h, tg_reply(h, f"Принимаю {quote['code']}"))
    # Change only the disposable fixture clock boundary on this immutable quote.
    # Recompute the fingerprint so the expiry predicate is the one that rejects.
    async with h.migrator.begin() as c:
        await c.execute(text("ALTER TABLE app.quotes DISABLE TRIGGER quote_immutable"))
        await c.execute(
            text("""WITH expiry AS (SELECT clock_timestamp() AS moment)
          UPDATE app.quotes SET expires_at=expiry.moment,
           terms_sha256=platform.quote_hash(jsonb_build_array('quote_v1',id,version,code,
            platform.quote_timestamp(expiry.moment),material,app.quotes.text))
          FROM expiry WHERE id=CAST(:id AS uuid)"""),
            {"id": quote["quote_id"]},
        )
        await c.execute(text("ALTER TABLE app.quotes ENABLE TRIGGER quote_immutable"))
    result = await process(h, receipt)
    assert result.quote_reply.outcome == "EXPIRED"
    assert "agreement" not in await read(h, auth, url, "EXPIRED")
    assert await counts(h) == (0, 0, 0)


async def test_publication_waits_for_the_acceptance_transaction(approval_pg, auth):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    receipt = await telegram_inbox(h, tg_reply(h, f"Принимаю {quote['code']}"))
    claim = await claim_job(h, receipt.job_id)
    writes, release = asyncio.Event(), asyncio.Event()

    async def barrier(name):
        if name == "process_before_commit":
            writes.set()
            await release.wait()

    db_with_barrier = MessagingDatabase(h.runtime.engine, environment="TEST", barrier=barrier)
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        accepting = tasks.create_task(db_with_barrier.process_inbox(claim))
        await writes.wait()
        # Independent connection cannot acquire the exact configuration fence
        # while approval and all three records are still uncommitted.
        async with h.migrator.begin() as conn:
            lock = await conn.execute(
                text("""
                SELECT pg_try_advisory_xact_lock(hashtextextended(
                    CAST(:workspace AS text)||':'||CAST(:business AS text)||'|CONFIGURATION_V1',2018))
            """),
                {
                    "workspace": quote["material"]["workspace_id"],
                    "business": quote["material"]["business_id"],
                },
            )
            assert lock.scalar_one() is False
        publication = tasks.create_task(
            publish(h, contract(formula_price(), FIXED_DURATION, deposit="FULL_PREPAYMENT"))
        )
        release.set()

    assert accepting.result().quote_reply.outcome == "ACCEPTED"
    saved = (await read(h, auth, url))["agreement"]
    assert saved["quote"] == quote and saved["quote"]["material"]["deposit"]["mode"] == "NONE"
    assert publication.result()["release_id"] != quote["material"]["deposit_terms_version"]
    assert await counts(h) == (1, 1, 1)


async def test_revocation_before_commit_keeps_the_reply_visible(approval_pg, auth):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    receipt = await telegram_inbox(h, tg_reply(h, f"Принимаю {quote['code']}"))
    await scalar(
        h,
        """UPDATE platform.workspace_memberships SET version=version+1
        WHERE workspace_id=CAST(:ws AS uuid) AND role='OWNER' RETURNING version""",
        ws=quote["material"]["workspace_id"],
    )
    result = await process(h, receipt)
    assert result.message_id and result.quote_reply.outcome == "REVOKED"
    assert (await read(h, auth, url, "REVOKED"))["reply_notice"]["message_id"] == str(
        result.message_id
    )
    assert await counts(h) == (0, 0, 0)


async def test_upgrade_from_0029_preserves_sent_quote_without_promoting_waiting_inbox(
    approval_pg, auth
):
    h = approval_pg
    _, _, _, url, quote = await exact_ready(h, auth, use_telegram=True)
    await telegram_send(h, quote)
    pending_event = tg_reply(h, f"Принимаю {quote['code']}")
    await _migrate("downgrade", "0029")
    try:
        assert (await scalar(h, "SELECT platform.quote_schema_profile()"))["valid"] is True
        pending = await telegram_inbox(h, pending_event)
    finally:
        await _migrate("upgrade", "0031")
    assert (await scalar(h, "SELECT platform.service_intent_schema_profile()"))["valid"] is True
    assert (await read(h, auth, url))["quote"] == quote
    assert (await telegram_inbox(h, pending_event)).code == "DUPLICATE"
    assert (await process(h, pending)).quote_reply is None
    assert await counts(h) == (0, 0, 0)
    fresh = await new_reply(h, f"Принимаю {quote['code']}")
    assert fresh.quote_reply.outcome == "ACCEPTED"
    assert await counts(h) == (1, 1, 1)
