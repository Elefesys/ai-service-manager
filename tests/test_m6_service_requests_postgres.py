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


@pytest_asyncio.fixture
async def service_request_pg(intake_pg):
    h = intake_pg
    try:
        yield h
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text("DELETE FROM platform.service_request_receipts WHERE workspace_id IN (:a,:b)"),
                {"a": A, "b": B},
            )
            await connection.execute(
                text("DELETE FROM app.service_requests WHERE workspace_id IN (:a,:b)"),
                {"a": A, "b": B},
            )


def create_body(projection, *, anchor=None, selection="ONE_WORK", fields=None):
    if anchor is None:
        anchor = next(
            (f["source"] for f in projection["facts"] if f["field"] == "idea"),
            projection["sources"][-1],
        )
    return {
        "expected_version": projection["version"],
        "expected_fingerprint": projection["fingerprint"],
        "intent_source": {name: anchor[name] for name in ("message_id", "source_version")},
        "fields": [f["field"] for f in projection["facts"]] if fields is None else fields,
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


async def test_q1_corrected_size_revises_same_request_but_separate_work_gets_own_facts(
    service_request_pg,
):
    h = service_request_pg
    cid, worker, model, _, delivery = await application(
        h, {"idea": "flower", "approximate_size": "8 cm"}
    )
    initial = await summary(h, cid)
    first_body = create_body(initial)
    first = await create(h, cid, "first-work", first_body)
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"approximate_size": "10 cm"}
    model.correction = True
    _, delivery = await next_turn(h, worker, "Actually 10 cm for the flower")
    corrected = await summary(h, cid)
    assert corrected["fingerprint"] != initial["fingerprint"]
    assert await create(h, cid, "first-work", first_body) == first
    async with rejected("STALE_STATE"):
        await create(h, cid, "stale-new-key", first_body)
    async with rejected("NEEDS_CLARIFICATION"):
        await create(
            h, cid, "wrong-segment", create_body(corrected, anchor=corrected["sources"][-1])
        )
    assert await create(h, cid, "correct-size", create_body(corrected)) == first
    first_draft = await read(h, cid, first["request_id"])
    assert (
        first_draft["revision"] == "2"
        and first_draft["intent_source"] == first_body["intent_source"]
    )
    assert {f["value"] for f in first_draft["facts"]} == {"10 cm", "flower"}
    assert await request_count(h, cid) == 1

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {}
    model.category = "AMBIGUOUS"
    _, delivery = await next_turn(h, worker, "I also want a bird and mentioned a size for one")
    ambiguous = await summary(h, cid)
    assert ambiguous["category"] == "AMBIGUOUS"
    async with rejected("NEEDS_CLARIFICATION"):
        await create(h, cid, "ambiguous", create_body(ambiguous))
    assert await request_count(h, cid) == 1

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"idea": "bird", "placement": "shoulder"}
    model.category = "NEW_TATTOO"
    model.switch = True
    model.correction = False
    await next_turn(h, worker, "Separate work: a bird on the shoulder")
    separate = await summary(h, cid)
    async with rejected("NEEDS_CLARIFICATION"):
        await create(h, cid, "unclear-association", create_body(separate, selection="UNCLEAR"))
    second = await create(h, cid, "second-work", create_body(separate))
    second_draft = await read(h, cid)
    assert second != first and second_draft["request_id"] == second["request_id"]
    assert second_draft["service_id"] == first_draft["service_id"]
    assert {f["value"] for f in second_draft["facts"]} == {"bird", "shoulder"}
    assert await read(h, cid, first["request_id"]) == first_draft
    async with rejected("NEEDS_CLARIFICATION"):
        await create(
            h,
            cid,
            "old-anchor-new-facts",
            create_body(separate, anchor=first_body["intent_source"]),
        )
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
    async with rejected("NOT_FOUND"):
        await read(h, foreign_cid, accepted["request_id"])
    async with rejected("NOT_FOUND"):
        await read(h, cid, accepted["request_id"], business=BA2)
    async with rejected("NOT_FOUND"):
        await read(h, cid, accepted["request_id"], business=BB, workspace=B, actor=UB)
    changed = await query(
        h,
        "UPDATE platform.workspace_memberships SET role='ADMIN' "
        "WHERE workspace_id=:ws AND user_account_id=:actor RETURNING role",
        ws=A,
        actor=UA,
    )
    assert [row["role"] for row in changed] == ["ADMIN"]
    async with rejected("ACCESS_DENIED"):
        await read(h, cid, accepted["request_id"])
    async with rejected("ACCESS_DENIED"):
        await create(h, cid, "eligible-owner", body)
    assert await request_count(h, cid) == 1


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
    result = await create(h, cid, "observed-request", create_body(projection))
    draft = await read(h, cid, result["request_id"])
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
        h, "SELECT has_table_privilege('asm_runtime','platform.service_request_receipts','INSERT')"
    )
    result = await create(h, cid, "0025-data", create_body(prior, fields=[]))
    with pytest.raises(AssertionError, match="SERVICE_REQUEST_DURABLE_DATA"):
        await _migrate("downgrade", "0024")
    assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0025"
    draft = await read(h, cid)
    assert draft["request_id"] == result["request_id"]
    assert draft["facts"] == [] and "idea" in draft["missing"]
