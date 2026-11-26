"""Q1 against PostgreSQL with the ordinary owner unit and M5 intake worker."""

import asyncio
import json
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
import pytest_asyncio
from m5_knowledge_search_fixtures import ControlledEmbeddings, owner_unit
from m5_knowledge_search_fixtures import db as db
from m5_knowledge_search_fixtures import search_pg as search_pg
from m5_knowledge_search_fixtures import seeded as seeded
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job, scalar, wait_blocked
from test_m3_1_provenance_postgres import process, raw
from test_m4_delivery_postgres import run_turn, source_turn
from test_m4_runtime_postgres import COUNTER
from test_m5_intake_postgres import application, next_turn, summary
from test_m5_intake_postgres import intake_pg as intake_pg
from test_m5_intake_v7_integration_postgres import compose
from test_m5_portfolio_runtime_postgres import analyse, source_image
from test_m5_portfolio_runtime_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_tenancy_postgres import BA, BA2, BB, UA, UB, A, B

pytestmark = pytest.mark.integration


async def clear_quote_rows(connection):
    if not (
        await connection.execute(text("SELECT to_regclass('app.quotes') IS NOT NULL"))
    ).scalar_one():
        return
    scope = {"a": A, "b": B}
    if (
        await connection.execute(text("SELECT to_regclass('app.quote_acceptances') IS NOT NULL"))
    ).scalar_one():
        tables = "platform.quote_reply_events,app.service_sessions,app.service_orders,app.quote_acceptances"
        if (
            await connection.execute(
                text("SELECT to_regclass('app.availability_offers') IS NOT NULL")
            )
        ).scalar_one():
            tables += (
                ",app.availability_offers,app.availability_options,app.reservation_holds,"
                "app.resource_allocations,platform.scheduling_command_receipts"
            )
        if (
            await connection.execute(text("SELECT to_regclass('app.appointments') IS NOT NULL"))
        ).scalar_one():
            tables += ",app.appointments"
        await connection.execute(text(f"TRUNCATE {tables}"))
    await connection.execute(
        text("DELETE FROM platform.quote_delivery_intents WHERE workspace_id IN (:a,:b)"), scope
    )
    await connection.execute(text("ALTER TABLE app.quotes DISABLE TRIGGER quote_immutable"))
    await connection.execute(text("DELETE FROM app.quotes WHERE workspace_id IN (:a,:b)"), scope)
    await connection.execute(text("ALTER TABLE app.quotes ENABLE TRIGGER quote_immutable"))


@pytest_asyncio.fixture
async def service_request_pg(intake_pg):
    h = intake_pg
    try:
        yield h
    finally:
        async with h.migrator.begin() as connection:
            await clear_quote_rows(connection)
            await connection.execute(
                text("DELETE FROM platform.service_request_receipts WHERE workspace_id IN (:a,:b)"),
                {"a": A, "b": B},
            )
            await connection.execute(
                text("DELETE FROM app.service_requests WHERE workspace_id IN (:a,:b)"),
                {"a": A, "b": B},
            )


def source_pin(source):
    return {name: source[name] for name in ("message_id", "source_version")}


def create_body(projection, *, anchor=None, selection="ONE_WORK", fields=None):
    if anchor is None:
        anchor = next(
            (f["source"] for f in projection["facts"] if f["field"] == "idea"),
            projection["sources"][-1],
        )
    return {
        "expected_version": projection["version"],
        "expected_fingerprint": projection["fingerprint"],
        "intent_source": source_pin(anchor),
        "fields": [f["field"] for f in projection["facts"]] if fields is None else fields,
        "selection": selection,
    }


def revise_body(projection, draft, field, *, source=None, selection="ONE_WORK"):
    if source is None:
        source = next(f["source"] for f in projection["facts"] if f["field"] == field)
    return {
        "expected_revision": draft["revision"],
        "expected_version": projection["version"],
        "expected_fingerprint": projection["fingerprint"],
        "field": field,
        "source": source_pin(source),
        "selection": selection,
    }


async def create(
    h, cid, key, body, *, business=BA, workspace=A, actor=UA, started: asyncio.Queue | None = None
):
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        if started is not None:
            pid = (await u._execute("SELECT pg_backend_pid()", {})).scalar_one()
            started.put_nowait(pid)
        result = await u._execute(
            "SELECT platform.service_request_owner_create(:b,:c,:key,CAST(:body AS jsonb))",
            {"b": business, "c": cid, "key": key, "body": json.dumps(body)},
        )
        return result.scalar_one()


async def read(h, cid, request_id=None, *, business=BA, workspace=A, actor=UA):
    if request_id is not None:
        request_id = UUID(request_id)
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        result = await u._execute(
            "SELECT platform.service_request_owner_read(:b,:c,:rid)",
            {"b": business, "c": cid, "rid": request_id},
        )
        return result.scalar_one()


async def list_drafts(h, cid, *, business=BA, workspace=A, actor=UA):
    async with owner_unit(h, workspace=workspace, actor=actor) as u:
        result = await u._execute(
            "SELECT platform.service_request_owner_list(:b,:c)", {"b": business, "c": cid}
        )
        return result.scalar_one()


async def revise(u, cid, request_id, key, body, *, business=BA):
    result = await u._execute(
        "SELECT platform.service_request_owner_revise(:b,:c,:rid,:key,CAST(:body AS jsonb))",
        {"b": business, "c": cid, "rid": UUID(request_id), "key": key, "body": json.dumps(body)},
    )
    return result.scalar_one()


@asynccontextmanager
async def rejected(code):
    with pytest.raises(DBAPIError) as error:
        yield
    assert error.value.orig.sqlstate == "P3101"
    assert error.value.orig.diag.message_primary == code


async def request_count(h, cid):
    return await scalar(
        h, "SELECT count(*) FROM app.service_requests WHERE conversation_id=:c", c=cid
    )


async def test_q1_concurrent_transactions_return_one_request_and_replay_after_lost_result(
    service_request_pg,
):
    h = service_request_pg
    cid, _, _, _, _ = await application(h, {"idea": "flower", "placement": "forearm"})
    projection = await summary(h, cid)
    body = create_body(projection)
    assert await read(h, cid) is None

    started = asyncio.Queue()
    async with asyncio.TaskGroup() as group:
        async with h.migrator.begin() as latch:
            latch_pid = (await latch.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await latch.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "CAST(:ws AS text)||':'||CAST(:b AS text)||'|CONFIGURATION_V1',2018))"
                ),
                {"ws": A, "b": BA},
            )
            first = group.create_task(create(h, cid, "first-tab", body, started=started))
            second = group.create_task(create(h, cid, "second-tab", body, started=started))
            async with asyncio.timeout(1.5):
                pids = (await started.get(), await started.get())
                assert len(set(pids)) == 2
                for pid in pids:
                    await wait_blocked(h, pid, latch_pid)

    accepted = first.result()
    request_id = accepted["request_id"]
    assert second.result() == accepted
    assert await create(h, cid, "first-tab", body) == accepted
    assert await request_count(h, cid) == 1
    async with rejected("IDEMPOTENCY_KEY_CONFLICT"):
        await create(h, cid, "first-tab", body | {"fields": []})

    draft = await read(h, cid)
    assert draft == await read(h, cid, request_id)
    assert (
        draft["request_id"] == request_id and draft["revision"] == "1" and draft["state"] == "DRAFT"
    )
    assert draft["service_id"] == "consultation" and draft["release_id"] == projection["release_id"]
    assert draft["intent_source"] == body["intent_source"]
    assert draft["missing"] and draft["question"] and draft["conflicts"] == []
    assert draft["facts"] == [
        f | {"source": f["source"] | {"quote": ""}}
        for f in sorted(projection["facts"], key=lambda fact: fact["field"])
    ]
    receipts = await query(
        h,
        "SELECT effect,accepted_revision,actor_user_account_id,correlation_id,"
        "octet_length(request_fingerprint) AS fingerprint_bytes FROM platform.service_request_receipts "
        "WHERE workspace_id=:ws AND request_id=:rid",
        ws=A,
        rid=UUID(request_id),
    )
    assert {r["effect"] for r in receipts} == {"CREATE", "OPEN"}
    assert len(receipts) == 2 and len({r["correlation_id"] for r in receipts}) == 2
    assert all(
        r["accepted_revision"] == 1
        and r["actor_user_account_id"] == UA
        and r["fingerprint_bytes"] == 32
        for r in receipts
    )


async def test_q1_late_correction_revises_only_selected_work_and_field(service_request_pg):
    h = service_request_pg
    cid, worker, model, _, delivery = await application(
        h, {"idea": "flower", "approximate_size": "8 cm"}
    )
    initial = await summary(h, cid)
    first_body = create_body(initial)
    first = await create(h, cid, "first-work", first_body)
    first_id = first["request_id"]
    original = await read(h, cid, first_id)
    assert original["revision"] == "1"
    assert {f["value"] for f in original["facts"]} == {"flower", "8 cm"}
    assert await create(h, cid, "reopen-empty", first_body | {"fields": []}) == first
    assert await read(h, cid, first_id) == original
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"idea": "bird", "placement": "shoulder"}
    model.switch = True
    _, delivery = await next_turn(h, worker, "Separate work: a bird on the shoulder")
    separate = await summary(h, cid)
    async with rejected("NEEDS_CLARIFICATION"):
        await create(h, cid, "unclear-association", create_body(separate, selection="UNCLEAR"))
    second_body = create_body(separate)
    second = await create(h, cid, "second-work", second_body)
    second_id = second["request_id"]
    second_draft = await read(h, cid, second_id)
    assert second_id != first_id and second_draft["revision"] == "1"
    assert second_draft["service_id"] == original["service_id"]
    assert {f["value"] for f in second_draft["facts"]} == {"bird", "shoulder"}
    async with rejected("NEEDS_CLARIFICATION"), owner_unit(h) as u:
        await revise(
            u, cid, first_id, "other-work-anchor", revise_body(separate, original, "placement")
        )
    assert await read(h, cid, first_id) == original
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"approximate_size": "12 cm", "style": "fine line"}
    model.switch = False
    model.correction = True
    _, delivery = await next_turn(h, worker, "For the first flower tattoo, size 12 cm, fine line")
    corrected = await summary(h, cid)
    size = revise_body(corrected, original, "approximate_size")
    assert size["source"] == source_pin(corrected["sources"][-1])
    assert size["source"]["message_id"] not in {
        first_body["intent_source"]["message_id"],
        second_body["intent_source"]["message_id"],
    }
    assert await create(h, cid, "first-work", first_body) == first
    async with rejected("STALE_STATE"):
        await create(h, cid, "stale-new-key", first_body)
    async with rejected("NEEDS_CLARIFICATION"):
        await create(h, cid, "wrong-segment", create_body(corrected, anchor=size["source"]))
    async with rejected("STALE_STATE"), owner_unit(h) as u:
        await revise(u, cid, first_id, "old-intake", revise_body(initial, original, "idea"))
    async with rejected("STALE_STATE"), owner_unit(h) as u:
        await revise(
            u,
            cid,
            first_id,
            "old-source-version",
            size | {"source": size["source"] | {"source_version": "0" * 64}},
        )
    async with rejected("NEEDS_CLARIFICATION"), owner_unit(h) as u:
        await revise(u, cid, first_id, "unclear-correction", size | {"selection": "UNCLEAR"})

    stale_style = revise_body(corrected, original, "style")
    started = asyncio.Queue()
    first_effect = asyncio.Event()

    async def stale_tab():
        await first_effect.wait()
        async with rejected("STALE_STATE"), owner_unit(h) as u:
            started.put_nowait((await u._execute("SELECT pg_backend_pid()", {})).scalar_one())
            await revise(u, cid, first_id, "stale-tab", stale_style)

    async with asyncio.TaskGroup() as group:
        group.create_task(stale_tab())
        async with owner_unit(h) as u:
            first_pid = (await u._execute("SELECT pg_backend_pid()", {})).scalar_one()
            assert await revise(u, cid, first_id, "correct-size", size) == first
            first_effect.set()
            async with asyncio.timeout(1.5):
                stale_pid = await started.get()
                assert stale_pid != first_pid
                await wait_blocked(h, stale_pid, first_pid)

    corrected_fact = next(f for f in corrected["facts"] if f["field"] == "approximate_size")
    assert (
        corrected_fact["value"] == "12 cm"
        and source_pin(corrected_fact["source"]) == size["source"]
    )
    revised = original | {
        "revision": "2",
        "facts": [
            corrected_fact | {"source": corrected_fact["source"] | {"quote": ""}}
            if f["field"] == "approximate_size"
            else f
            for f in original["facts"]
        ],
    }
    async with rejected("NEEDS_CLARIFICATION"), owner_unit(h) as u:
        await revise(
            u,
            cid,
            second_id,
            "pin-already-in-first",
            revise_body(corrected, second_draft, "approximate_size"),
        )
    async with rejected("IDEMPOTENCY_KEY_CONFLICT"), owner_unit(h) as u:
        await revise(u, cid, second_id, "correct-size", size)
    async with rejected("IDEMPOTENCY_KEY_CONFLICT"), owner_unit(h) as u:
        await revise(u, cid, first_id, "first-work", size)
    async with rejected("IDEMPOTENCY_KEY_CONFLICT"), owner_unit(h) as u:
        await revise(u, cid, first_id, "correct-size", stale_style)

    # A new read reopens the selected ID after B exists and does not advance anything.
    assert await read(h, cid) == second_draft
    assert await read(h, cid, first_id) == revised
    assert await list_drafts(h, cid) == {
        "items": [
            {
                name: draft[name]
                for name in ("request_id", "revision", "service_name", "intent_source")
            }
            | {"idea": idea}
            for draft, idea in ((second_draft, "bird"), (revised, "flower"))
        ]
    }
    assert await read(h, cid, first_id) == revised

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {}
    model.category = "AMBIGUOUS"
    await next_turn(h, worker, "Or 15 cm for one of them, I am unsure which")
    ambiguous = await summary(h, cid)
    assert ambiguous["category"] == "AMBIGUOUS"
    async with rejected("NEEDS_CLARIFICATION"):
        await create(h, cid, "ambiguous", create_body(ambiguous))
    async with rejected("NEEDS_CLARIFICATION"), owner_unit(h) as u:
        await revise(
            u,
            cid,
            first_id,
            "ambiguous-correction",
            revise_body(ambiguous, revised, "approximate_size", source=size["source"]),
        )
    # The first successful response can be lost while another tab and Intake advance.
    async with owner_unit(h) as u:
        assert await revise(u, cid, first_id, "correct-size", size) == first
    assert await read(h, cid, first_id) == revised
    assert await read(h, cid, second_id) == second_draft
    assert await request_count(h, cid) == 2
    receipts = await query(
        h,
        "SELECT command_key,effect,accepted_revision FROM platform.service_request_receipts "
        "WHERE request_id IN (:first,:second)",
        first=UUID(first_id),
        second=UUID(second_id),
    )
    assert {r["command_key"]: (r["effect"], r["accepted_revision"]) for r in receipts} == {
        "first-work": ("CREATE", 1),
        "reopen-empty": ("OPEN", 1),
        "second-work": ("CREATE", 1),
        "correct-size": ("REVISE", 2),
    }


async def test_q1_delayed_creation_rejects_size_already_saved_for_another_work(service_request_pg):
    h = service_request_pg
    cid, worker, model, _, delivery = await application(
        h, {"idea": "flower", "approximate_size": "8 cm"}
    )
    initial = await summary(h, cid)
    first = await create(h, cid, "first-work", create_body(initial))
    first_id = first["request_id"]
    original = await read(h, cid, first_id)
    assert original["revision"] == "1"
    assert {f["value"] for f in original["facts"]} == {"flower", "8 cm"}
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"idea": "bird", "placement": "shoulder"}
    model.switch = True
    _, delivery = await next_turn(h, worker, "Separate work: a bird on the shoulder")
    separate = await summary(h, cid)
    second_start = create_body(separate)["intent_source"]
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"approximate_size": "12 cm"}
    model.switch = False
    model.correction = True
    await next_turn(h, worker, "12 cm only for the first flower")
    corrected = await summary(h, cid)
    assert {f["field"]: f["value"] for f in corrected["facts"]} == {
        "idea": "bird",
        "placement": "shoulder",
        "approximate_size": "12 cm",
    }
    size = revise_body(corrected, original, "approximate_size")
    assert size["source"] == source_pin(corrected["sources"][-1])
    assert size["source"]["message_id"] != second_start["message_id"]
    async with owner_unit(h) as u:
        assert await revise(u, cid, first_id, "correct-first-size", size) == first
    revised = await read(h, cid, first_id)
    revised_size = next(f for f in revised["facts"] if f["field"] == "approximate_size")
    assert revised_size["value"] == "12 cm" and source_pin(revised_size["source"]) == size["source"]
    assert revised["revision"] == "2" and revised["intent_source"] == original["intent_source"]
    assert await request_count(h, cid) == 1

    disputed = create_body(corrected, anchor=second_start)
    key = "second-with-first-size"
    async with rejected("NEEDS_CLARIFICATION"):
        await create(h, cid, key, disputed)
    assert await request_count(h, cid) == 1
    assert await read(h, cid, first_id) == revised
    assert not await scalar(
        h,
        "SELECT EXISTS(SELECT 1 FROM platform.service_request_receipts "
        "WHERE (workspace_id,actor_user_account_id,command_key)=(:ws,:actor,:key))",
        ws=A,
        actor=UA,
        key=key,
    )

    second = await create(
        h,
        cid,
        "second-own-fields",
        create_body(corrected, anchor=second_start, fields=["idea", "placement"]),
    )
    assert second != first
    second_draft = await read(h, cid, second["request_id"])
    assert second_draft["revision"] == "1" and second_draft["intent_source"] == second_start
    assert {f["field"]: f["value"] for f in second_draft["facts"]} == {
        "idea": "bird",
        "placement": "shoulder",
    }
    assert "approximate_size" in second_draft["missing"]
    assert await request_count(h, cid) == 2
    assert await read(h, cid, first_id) == revised


async def test_q1_separate_sources_can_support_the_same_size(service_request_pg):
    h = service_request_pg
    cid, worker, model, _, delivery = await application(
        h, {"idea": "flower", "approximate_size": "8 cm"}
    )
    initial = await summary(h, cid)
    first = await create(h, cid, "first-work", create_body(initial))
    original = await read(h, cid, first["request_id"])
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"idea": "bird", "approximate_size": "8 cm"}
    model.switch = True
    await next_turn(h, worker, "Separate work: a bird, 8 cm")
    separate = await summary(h, cid)
    second = await create(h, cid, "second-work", create_body(separate))
    second_draft = await read(h, cid, second["request_id"])
    assert second != first
    first_size = next(f for f in original["facts"] if f["field"] == "approximate_size")
    second_size = next(f for f in second_draft["facts"] if f["field"] == "approximate_size")
    assert first_size["value"] == second_size["value"] == "8 cm"
    assert source_pin(first_size["source"]) == original["intent_source"]
    assert source_pin(second_size["source"]) == second_draft["intent_source"]
    assert first_size["source"]["message_id"] != second_size["source"]["message_id"]
    assert await request_count(h, cid) == 2


async def test_q1_rejects_foreign_scope_and_rechecks_access_for_read_and_replay(service_request_pg):
    h = service_request_pg
    cid, _, _, _, _ = await application(h, {"idea": "flower"})
    projection = await summary(h, cid)
    body = create_body(projection)
    foreign_cid, _, _ = await source_turn(h, native=True, message_text="Another client's bird")
    foreign = await summary(h, foreign_cid)
    assert foreign["client_id"] != projection["client_id"]
    # Carry the correct expected projection yet a source from a different client.
    async with rejected("STALE_STATE"):
        await create(
            h, cid, "foreign-source", create_body(projection, anchor=foreign["sources"][-1])
        )
    async with rejected("NOT_FOUND"):
        await create(h, cid, "foreign-business", body, business=BA2)
    async with rejected("NOT_FOUND"):
        await create(h, cid, "foreign-workspace", body, business=BB, workspace=B, actor=UB)
    async with rejected("INVALID_INPUT"):
        await create(h, cid, "client-supplied-facts", body | {"facts": projection["facts"]})
    assert await request_count(h, cid) == 0
    assert await request_count(h, foreign_cid) == 0

    accepted = await create(h, cid, "eligible-owner", body)
    request_id = accepted["request_id"]
    draft = await read(h, cid, request_id)
    change = revise_body(projection, draft, "idea")
    assert await list_drafts(h, foreign_cid) == {"items": []}
    async with rejected("STALE_STATE"), owner_unit(h) as u:
        await revise(
            u,
            cid,
            request_id,
            "revise-foreign-source",
            change | {"source": source_pin(foreign["sources"][-1])},
        )
    async with rejected("NOT_FOUND"), owner_unit(h) as u:
        await revise(u, foreign_cid, request_id, "revise-foreign-client", change)
    async with rejected("NOT_FOUND"), owner_unit(h) as u:
        await revise(u, cid, request_id, "revise-foreign-business", change, business=BA2)
    async with rejected("NOT_FOUND"), owner_unit(h, workspace=B, actor=UB) as u:
        await revise(u, cid, request_id, "revise-foreign-workspace", change, business=BB)
    async with rejected("NOT_FOUND"):
        await list_drafts(h, cid, business=BA2)
    async with rejected("NOT_FOUND"):
        await list_drafts(h, cid, business=BB, workspace=B, actor=UB)
    async with rejected("NOT_FOUND"):
        await read(h, foreign_cid, request_id)
    async with rejected("NOT_FOUND"):
        await read(h, cid, request_id, business=BA2)
    async with rejected("NOT_FOUND"):
        await read(h, cid, request_id, business=BB, workspace=B, actor=UB)
    assert await read(h, cid, request_id) == draft
    async with owner_unit(h) as u:
        assert await revise(u, cid, request_id, "eligible-correction", change) == accepted
    assert await read(h, cid, request_id) == draft
    changed = await query(
        h,
        "UPDATE platform.workspace_memberships SET role='ADMIN' "
        "WHERE workspace_id=:ws AND user_account_id=:actor RETURNING role",
        ws=A,
        actor=UA,
    )
    assert [row["role"] for row in changed] == ["ADMIN"]
    async with rejected("ACCESS_DENIED"):
        await read(h, cid, request_id)
    async with rejected("ACCESS_DENIED"):
        await list_drafts(h, cid)
    async with rejected("ACCESS_DENIED"):
        await create(h, cid, "eligible-owner", body)
    async with rejected("ACCESS_DENIED"), owner_unit(h) as u:
        await revise(u, cid, request_id, "eligible-correction", change)
    assert await request_count(h, cid) == 1
    receipts = await query(
        h,
        "SELECT command_key FROM platform.service_request_receipts WHERE request_id=:id",
        id=UUID(request_id),
    )
    assert {row["command_key"] for row in receipts} == {"eligible-owner", "eligible-correction"}


async def test_q1_rejects_conflicted_fact_even_with_confirmed_work(service_request_pg):
    h = service_request_pg
    cid, worker, model, _, delivery = await application(
        h, {"idea": "flower", "approximate_size": "8 cm"}
    )
    initial = await summary(h, cid)
    result = await create(h, cid, "before-conflict", create_body(initial))
    request_id = result["request_id"]
    original = await read(h, cid, request_id)
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"approximate_size": "12 cm"}
    await next_turn(h, worker, "A possible size is 12 cm")
    projection = await summary(h, cid)
    assert projection["conflicts"] == ["approximate_size"]
    async with rejected("NEEDS_CLARIFICATION"), owner_unit(h) as u:
        await revise(
            u,
            cid,
            request_id,
            "conflicted-fact",
            revise_body(projection, original, "approximate_size"),
        )
    assert await read(h, cid, request_id) == original
    receipt = await scalar(
        h,
        "SELECT count(*) FROM platform.service_request_receipts WHERE request_id=:id",
        id=UUID(request_id),
    )
    assert receipt == 1


@pytest.mark.parametrize("mutation", ["EDIT", "DELETE"])
async def test_q1_source_changed_or_revoked_before_new_creation(service_request_pg, mutation):
    h = service_request_pg
    cid, _, _, _, _ = await application(h, {"idea": "flower"}, telegram=True)
    prior = await summary(h, cid)
    body = create_body(prior)
    source = (
        await query(
            h,
            "SELECT provider_message_id,provider_chat_id FROM app.messages WHERE id=:id",
            id=UUID(body["intent_source"]["message_id"]),
        )
    )[0]
    _, _, changed = await process(
        h,
        raw(
            900000 + next(COUNTER),
            int(source["provider_message_id"]),
            kind=mutation,
            value="Synthetic edited bird",
            chat=source["provider_chat_id"],
            sender=source["provider_chat_id"],
            date=40,
        ),
    )
    assert changed.code == "MATERIAL_PROCESSED"
    current = await summary(h, cid)
    assert current["fingerprint"] != prior["fingerprint"] and current["facts"] == []
    async with rejected("STALE_STATE"):
        await create(h, cid, "old-projection", body)
    async with rejected("STALE_STATE"):
        await create(
            h, cid, "old-source", create_body(current, fields=[], anchor=body["intent_source"])
        )
    assert await request_count(h, cid) == 0


async def test_q1_observed_fact_retains_current_analysis_identity(service_request_pg):
    h = service_request_pg
    cid, source_job, _, image = await source_image(h, caption="Synthetic flower reference")
    reserved, completed, _ = await analyse(h, cid)
    assert completed["state"] == "SUCCESS"
    digest = await scalar(
        h,
        "SELECT encode(sha256(convert_to((completion->'result')::text,'UTF8')),'hex') "
        "FROM platform.vision_analyses WHERE id=:id",
        id=UUID(reserved["analysis_id"]),
    )
    h.photo_embeddings = ControlledEmbeddings()
    h.photo_store = h.store
    h.photo_workers = h.intake_workers

    def observed(result):
        fact = result["intake"]["facts"][0]
        fact["status"] = "observed"
        fact["source"].update(
            quote="",
            analysis_id=reserved["analysis_id"],
            analysis_sha256=digest,
        )

    worker, _, _ = await compose(
        h, cid, [], photo=False, mutate=observed, values={"idea": "flower"}
    )
    await run_turn(h, worker, source_job)
    projection = await summary(h, cid)
    assert len(projection["facts"]) == 1
    result = await create(h, cid, "observed-request", create_body(projection, fields=[]))
    empty = await read(h, cid, result["request_id"])
    assert empty["facts"] == []
    async with owner_unit(h) as u:
        assert (
            await revise(
                u,
                cid,
                result["request_id"],
                "observed-revision",
                revise_body(projection, empty, "idea"),
            )
            == result
        )
    draft = await read(h, cid, result["request_id"])
    assert draft["revision"] == "2"
    assert "idea" in draft["missing"]
    assert draft["facts"] == projection["facts"]
    fact = draft["facts"][0]
    assert fact["status"] == "observed"
    assert fact["source"]["message_id"] == str(image["message_id"])
    assert fact["source"]["analysis_id"] == reserved["analysis_id"]
    assert fact["source"]["analysis_sha256"] == digest


async def test_0025_upgrade_preserves_0024_intake_and_rejects_downgrade_with_requests(
    service_request_pg,
):
    h = service_request_pg
    cid, _, _, _, _ = await application(h, {"idea": "flower"})
    prior = await summary(h, cid)
    await _migrate("downgrade", "0025")
    try:
        await _migrate("downgrade", "0024")
        try:
            assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0024"
            assert await scalar(h, "SELECT to_regclass('app.service_requests') IS NULL")
            assert (await scalar(h, "SELECT platform.intake_v7_schema_profile()"))["valid"] is True
            assert await summary(h, cid) == prior
        finally:
            await _migrate("upgrade", "0025")
        assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0025"
        assert await summary(h, cid) == prior
        assert not await scalar(
            h, "SELECT has_table_privilege('asm_runtime','app.service_requests','SELECT')"
        )
        assert not await scalar(
            h,
            "SELECT has_table_privilege('asm_runtime','platform.service_request_receipts','INSERT')",
        )
        assert not await scalar(
            h,
            "SELECT has_function_privilege('asm_runtime',"
            "'platform.service_request_command(app.conversations,text,text,uuid,jsonb)','EXECUTE')",
        )
        assert not await scalar(
            h,
            "SELECT has_function_privilege('asm_runtime',"
            "'platform.service_request_fact_available(app.conversations,uuid,jsonb)','EXECUTE')",
        )
        result = await create(h, cid, "0025-data", create_body(prior, fields=[]))
        with pytest.raises(AssertionError, match="SERVICE_REQUEST_DURABLE_DATA"):
            await _migrate("downgrade", "0024")
        assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0025"
        draft = await read(h, cid)
        assert draft["request_id"] == result["request_id"]
        assert draft["facts"] == [] and "idea" in draft["missing"]
        old_question = draft["question"]
        async with owner_unit(h) as u:
            assert (
                await revise(
                    u,
                    cid,
                    draft["request_id"],
                    "supply-first-field",
                    revise_body(prior, draft, "idea"),
                )
                == result
            )
        updated = await read(h, cid, draft["request_id"])
        assert "idea" not in updated["missing"] and updated["question"] != old_question
    finally:
        await _migrate("upgrade", "0036")
