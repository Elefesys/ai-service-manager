"""Assessment authority, history and owner capability checks on PostgreSQL."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.service_requests.errors import ServiceRequestError
from m5_intake_fixtures import intake_bundle
from m5_knowledge_search_fixtures import db as db
from m5_knowledge_search_fixtures import owner_unit
from m5_knowledge_search_fixtures import search_pg as search_pg
from m5_knowledge_search_fixtures import seeded as seeded
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m3_1_native_context_postgres import claim_job, scalar
from test_m3_1_provenance_postgres import process, raw
from test_m4_delivery_postgres import source_turn
from test_m4_runtime_postgres import COUNTER
from test_m5_intake_postgres import application, next_turn, summary
from test_m5_intake_postgres import intake_pg as intake_pg
from test_m5_portfolio_runtime_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m6_service_requests_postgres import create, create_body, read, revise, revise_body
from test_m6_service_requests_postgres import service_request_pg as service_request_pg
from test_tenancy_postgres import BA, BA2, BB, UA, UB, A, B

pytestmark = pytest.mark.integration
FLOWER = {"idea": "flower", "placement": "forearm", "approximate_size": "8 cm", "style": "linework"}


@pytest_asyncio.fixture
async def assessment_pg(service_request_pg):
    h = service_request_pg
    try:
        yield h
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE app.service_assessments DISABLE TRIGGER service_assessment_immutable"
                )
            )
            await connection.execute(
                text("DELETE FROM app.service_assessments WHERE workspace_id IN (:a,:b)"),
                {"a": A, "b": B},
            )
            await connection.execute(
                text(
                    "ALTER TABLE app.service_assessments ENABLE TRIGGER service_assessment_immutable"
                )
            )


def policy_bundle(duration):
    bundle = intake_bundle()
    bundle["rules"] = []
    bundle["faqs"][0]["rule_ids"] = []
    bundle["services"][0]["price"] = {
        "mode": "OWNER_QUOTE",
        "amount_minor": None,
        "formula_note": None,
    }
    bundle["services"][0]["duration"] = duration
    return bundle


def fixed(minutes):
    return {"mode": "FIXED", "minutes": minutes, "rule_note": None}


async def configure(h, bundle, *, publish=True):
    async with owner_unit(h) as u:
        previous = await u.configuration_owner_read(BA)
        edited = await u.configuration_command(
            BA,
            "EDIT",
            str(uuid4()),
            {"expected_draft_version": previous["draft_version"], "bundle": bundle},
        )
        if not publish:
            return edited["result"]
        result = await u.configuration_command(
            BA,
            "PUBLISH",
            str(uuid4()),
            {
                "expected_draft_version": edited["result"]["draft_version"],
                "expected_activation_version": previous["activation_version"],
            },
        )
        return result["result"]


def result_body(pin, outcome, reason, **values):
    return {
        "expected_revision": pin["request_revision"],
        "authority_sha256": pin["authority_sha256"],
        "outcome": outcome,
        "reason": reason,
        "field": None,
        "rule_id": None,
        "limit": None,
        "size_mm": None,
        "occupied_minutes": None,
    } | values


async def get_assessment(h, cid, request_id):
    async with owner_unit(h) as u:
        return await u.service_assessment_read(BA, cid, request_id)


async def record(h, cid, request_id, result):
    async with owner_unit(h) as u:
        return await u.service_assessment_record(BA, cid, request_id, result)


async def assessment_count(h, request_id):
    return await scalar(
        h, "SELECT count(*) FROM app.service_assessments WHERE request_id=:id", id=request_id
    )


async def test_assessment_tracks_only_selected_draft_revision_and_pin(assessment_pg):
    h = assessment_pg
    published = await configure(h, policy_bundle(fixed(75)))
    cid, worker, model, _, delivery = await application(h, FLOWER)
    first = await create(h, cid, "assess-flower", create_body(await summary(h, cid)))
    first_id = UUID(first["request_id"])
    first_draft = await read(h, cid, str(first_id))
    await worker.execute(await claim_job(h, delivery["send_job_id"]))

    model.values = {"idea": "bird", "placement": "shoulder"}
    model.switch = True
    _, delivery = await next_turn(h, worker, "Separate work: a bird on the shoulder")
    second = await create(h, cid, "assess-bird", create_body(await summary(h, cid)))
    second_id = UUID(second["request_id"])
    second_draft = await read(h, cid, str(second_id))

    async with owner_unit(h) as u:
        pin = await u.service_assessment_prepare(BA, cid, first_id, "1")
        bird = await u.service_assessment_prepare(BA, cid, second_id, "1")
        assert pin["facts"] == first_draft["facts"] and bird["facts"] == second_draft["facts"]
        assert pin["release_id"] == published["release_id"]
        assert pin["service"]["price"]["mode"] == "OWNER_QUOTE"
        assert pin["authority_sha256"] != bird["authority_sha256"]
        result = result_body(pin, "FEASIBLE", "FIXED_DURATION", occupied_minutes=75)
        assert await u.service_assessment_read(BA, cid, first_id) is None
        saved = await u.service_assessment_record(BA, cid, first_id, result)
    assert saved["current"] is True and saved["evidence"] == first_draft["facts"]
    assert await record(h, cid, first_id, result) == saved
    assert await assessment_count(h, first_id) == 1
    with pytest.raises(ServiceRequestError, match="INVALID_INPUT"):
        await record(h, cid, first_id, result | {"occupied_minutes": 74})
    with pytest.raises(ServiceRequestError, match="STALE_STATE"):
        await record(h, cid, second_id, result)

    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"approximate_size": "12 cm"}
    model.switch = False
    model.correction = True
    await next_turn(h, worker, "For the original flower, 12 cm")
    revised = await summary(h, cid)
    async with owner_unit(h) as u:
        assert (
            await revise(
                u,
                cid,
                str(first_id),
                "first-size-confirmation",
                revise_body(revised, first_draft, "approximate_size"),
            )
            == first
        )
    assert await get_assessment(h, cid, first_id) == saved | {"current": False}
    with pytest.raises(ServiceRequestError, match="STALE_STATE"):
        await record(h, cid, first_id, result)
    async with owner_unit(h) as u:
        updated = await u.service_assessment_prepare(BA, cid, first_id, "2")
        fresh = await u.service_assessment_record(
            BA,
            cid,
            first_id,
            result_body(updated, "FEASIBLE", "FIXED_DURATION", occupied_minutes=75),
        )
    assert fresh["assessment_id"] != saved["assessment_id"] and fresh["current"] is True
    assert {f["field"]: f["value"] for f in fresh["evidence"]} == FLOWER | {
        "approximate_size": "12 cm"
    }
    assert await get_assessment(h, cid, second_id) is None
    assert await read(h, cid, str(second_id)) == second_draft
    assert await assessment_count(h, first_id) == 2
    archived = await scalar(
        h,
        "SELECT evidence FROM app.service_assessments WHERE id=:id",
        id=UUID(saved["assessment_id"]),
    )
    assert archived == saved["evidence"]


@pytest.mark.parametrize("mutation", ["EDIT", "DELETE"])
async def test_assessment_source_material_change_keeps_history_but_invalidates_use(
    assessment_pg, mutation
):
    h = assessment_pg
    await configure(h, policy_bundle(fixed(60)))
    cid, _, _, _, _ = await application(h, FLOWER, telegram=True)
    initial = await summary(h, cid)
    request_id = UUID(
        (await create(h, cid, "source-backed-assessment", create_body(initial)))["request_id"]
    )
    async with owner_unit(h) as u:
        pin = await u.service_assessment_prepare(BA, cid, request_id, "1")
        result = result_body(pin, "FEASIBLE", "FIXED_DURATION", occupied_minutes=60)
        saved = await u.service_assessment_record(BA, cid, request_id, result)

    source = (
        await query(
            h,
            "SELECT provider_message_id,provider_chat_id FROM app.messages WHERE id=:id",
            id=UUID(saved["evidence"][0]["source"]["message_id"]),
        )
    )[0]
    _, _, changed = await process(
        h,
        raw(
            900000 + next(COUNTER),
            int(source["provider_message_id"]),
            kind=mutation,
            value="Synthetic corrected size 12 cm",
            chat=source["provider_chat_id"],
            sender=source["provider_chat_id"],
            date=40,
        ),
    )
    assert changed.code == "MATERIAL_PROCESSED"
    assert await get_assessment(h, cid, request_id) == saved | {"current": False}
    with pytest.raises(ServiceRequestError, match="STALE_STATE"):
        await record(h, cid, request_id, result)
    assert await assessment_count(h, request_id) == 1
    async with owner_unit(h) as u:
        current = await u.service_assessment_prepare(BA, cid, request_id, "1")
        assert current["facts"] == [] and current["unavailable_fields"] == sorted(FLOWER)
        assert current["authority_sha256"] != pin["authority_sha256"]
        fresh = await u.service_assessment_record(
            BA,
            cid,
            request_id,
            result_body(current, "NEEDS_DATA", "SOURCE_CHANGED", field="idea"),
        )
    assert (
        fresh["current"] is True and fresh["evidence"] == [] and fresh["occupied_minutes"] is None
    )
    assert await assessment_count(h, request_id) == 2


async def test_assessment_uses_new_activation_even_after_policy_rollback(assessment_pg):
    h = assessment_pg
    first_release = await configure(h, policy_bundle(fixed(65)))
    cid, _, _, _, _ = await application(h, FLOWER)
    request_id = UUID(
        (await create(h, cid, "assessment-activation", create_body(await summary(h, cid))))[
            "request_id"
        ]
    )
    async with owner_unit(h) as u:
        first_pin = await u.service_assessment_prepare(BA, cid, request_id, "1")
        first_body = result_body(first_pin, "FEASIBLE", "FIXED_DURATION", occupied_minutes=65)
        first = await u.service_assessment_record(BA, cid, request_id, first_body)

    duration = {
        "mode": "CONFIGURED_RULE",
        "minutes": None,
        "rule_note": None,
        "size_rule": {"threshold_mm": 80, "at_or_below_minutes": 80, "above_minutes": 110},
    }
    second_release = await configure(h, policy_bundle(duration))
    assert await get_assessment(h, cid, request_id) == first | {"current": False}
    with pytest.raises(ServiceRequestError, match="STALE_STATE"):
        await record(h, cid, request_id, first_body)
    async with owner_unit(h) as u:
        second_pin = await u.service_assessment_prepare(BA, cid, request_id, "1")
        assert second_pin["service"]["duration"] == duration
        second_body = result_body(
            second_pin,
            "FEASIBLE",
            "SIZE_DURATION_RULE",
            field="approximate_size",
            size_mm=80,
            occupied_minutes=80,
        )
        second = await u.service_assessment_record(BA, cid, request_id, second_body)
    assert second["current"] is True and second["occupied_minutes"] == 80
    with pytest.raises(ServiceRequestError, match="INVALID_INPUT"):
        await record(h, cid, request_id, second_body | {"occupied_minutes": 110})
    async with owner_unit(h) as u:
        rolled_back = await u.configuration_command(
            BA,
            "ROLLBACK",
            str(uuid4()),
            {
                "expected_activation_version": second_release["activation_version"],
                "release_id": first_release["release_id"],
            },
        )
    assert await get_assessment(h, cid, request_id) == second | {"current": False}
    with pytest.raises(ServiceRequestError, match="STALE_STATE"):
        await record(h, cid, request_id, first_body)
    async with owner_unit(h) as u:
        new_pin = await u.service_assessment_prepare(BA, cid, request_id, "1")
        assert new_pin["release_id"] == first_pin["release_id"]
        assert new_pin["activation_version"] == rolled_back["result"]["activation_version"]
        new = await u.service_assessment_record(
            BA,
            cid,
            request_id,
            result_body(new_pin, "FEASIBLE", "FIXED_DURATION", occupied_minutes=65),
        )
    assert new["duration_policy"] == first["duration_policy"] and new["current"] is True
    assert new["assessment_id"] != first["assessment_id"]
    assert await assessment_count(h, request_id) == 3


async def test_assessment_owner_access_and_immutable_archive(assessment_pg):
    h = assessment_pg
    await configure(h, policy_bundle(fixed(60)))
    cid, _, _, _, _ = await application(h, FLOWER)
    request_id = UUID(
        (await create(h, cid, "assessment-owner", create_body(await summary(h, cid))))["request_id"]
    )
    foreign, _, _ = await source_turn(h, native=True, message_text="Another client's bird")
    async with owner_unit(h) as u:
        pin = await u.service_assessment_prepare(BA, cid, request_id, "1")
        result = result_body(pin, "FEASIBLE", "FIXED_DURATION", occupied_minutes=60)
        saved = await u.service_assessment_record(BA, cid, request_id, result)
    with pytest.raises(ServiceRequestError, match="NOT_FOUND"):
        async with owner_unit(h) as u:
            await u.service_assessment_prepare(BA, foreign, request_id, "1")
    with pytest.raises(ServiceRequestError, match="NOT_FOUND"):
        async with owner_unit(h) as u:
            await u.service_assessment_record(BA2, cid, request_id, result)
    with pytest.raises(ServiceRequestError, match="NOT_FOUND"):
        async with owner_unit(h, workspace=B, actor=UB) as u:
            await u.service_assessment_read(BB, cid, request_id)
    with pytest.raises(IntegrityError, match="SERVICE_ASSESSMENT_IMMUTABLE"):
        await query(
            h,
            "UPDATE app.service_assessments SET occupied_minutes=1 WHERE id=:id RETURNING id",
            id=UUID(saved["assessment_id"]),
        )
    assert not await scalar(
        h, "SELECT has_table_privilege('asm_runtime','app.service_assessments','SELECT,INSERT')"
    )
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='ADMIN' "
        "WHERE workspace_id=:ws AND user_account_id=:actor RETURNING role",
        ws=A,
        actor=UA,
    )
    with pytest.raises(ServiceRequestError, match="ACCESS_DENIED"):
        await record(h, cid, request_id, result)
    with pytest.raises(ServiceRequestError, match="ACCESS_DENIED"):
        await get_assessment(h, cid, request_id)
    assert await assessment_count(h, request_id) == 1
    with pytest.raises(AssertionError, match="SERVICE_ASSESSMENT_DURABLE_DATA"):
        await _migrate("downgrade", "0025")
    assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0030"


async def test_0026_round_trip_preserves_draft_and_guards_new_config(assessment_pg):
    h = assessment_pg
    cid, _, _, _, _ = await application(h, {"idea": "flower"})
    request_id = (await create(h, cid, "assessment-migration", create_body(await summary(h, cid))))[
        "request_id"
    ]
    prior = await read(h, cid, request_id)
    await _migrate("downgrade", "0025")
    try:
        assert await scalar(h, "SELECT to_regclass('app.service_assessments') IS NULL")
        assert await read(h, cid, request_id) == prior
        assert (await scalar(h, "SELECT platform.service_request_schema_profile()"))[
            "valid"
        ] is True
    finally:
        await _migrate("upgrade", "0030")
    assert await read(h, cid, request_id) == prior
    bundle = policy_bundle(fixed(90))
    bundle["rules"] = [
        {"id": "size-limit", "service_id": "consultation", "kind": "MAX_SIZE_MM", "value": 95}
    ]
    await configure(h, bundle, publish=False)
    with pytest.raises(AssertionError, match="SERVICE_ASSESSMENT_DURABLE_DATA"):
        await _migrate("downgrade", "0025")
    assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0030"
