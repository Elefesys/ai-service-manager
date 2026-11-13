"""Owned PG18: immutable publications, legacy reads and serialized admissions.

No provider/Telegram requests. Model completions used to arrange SQL stages are
explicit synthetic fixtures; controlled transport effects are counted separately.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from contextvars import Context
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.ai.contracts import KnowledgeGatewayConfig, Reply
from asm.ai.runtime_contracts import CallCompletion, RuntimeReceipt
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AIJobClaim, AISendPermit
from asm.tenancy import AuthenticatedAccount
from m5_configuration_fixtures import configuration_bundle
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, migrate, scalar
from test_m4_agent import config
from test_m4_delivery_postgres import source_turn
from test_m4_runtime_postgres import budget, effects, intent
from test_m4_runtime_postgres import pg as pg
from test_m5_knowledge_migrations import source as migration_source
from test_tenancy_postgres import BA, BA2, BB, UA, UB, A, B

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


def current_config():
    return KnowledgeGatewayConfig.model_validate(
        config(duration_seconds=120).model_dump() | {"prompt_revision": "conversation_v3"}
    )


async def raw_command(h, claim, operation, *, delivery=False, **payload):
    async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
        return await unit.ai_runtime(operation, payload, delivery=delivery)


async def prepare_current(h, claim, *, delivery=False):
    return await raw_command(
        h,
        claim,
        "PREPARE",
        delivery=delivery,
        config=current_config().model_dump(mode="json"),
        deadline=(datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
    )


async def reserve_completion(h, claim, run, kind="OUTPUT", *, calls=1, reads=0, delivery=False):
    reserved = await raw_command(
        h,
        claim,
        "RESERVE",
        delivery=delivery,
        run_id=run["run_id"],
        budget=budget(calls, reads).model_dump(mode="json"),
    )
    assert reserved == {"sequence": calls}
    await raw_command(
        h,
        claim,
        "COMPLETE",
        delivery=delivery,
        run_id=run["run_id"],
        sequence=calls,
        completion=CallCompletion(kind=kind).model_dump(mode="json"),
    )


@asynccontextmanager
async def owner_unit(h, ws=A, actor=UA):
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(actor), ws, uuid4()) as unit:
        yield unit


async def configuration_command(h, operation, payload, *, business=BA, ws=A, actor=UA, key=None):
    async with owner_unit(h, ws, actor) as unit:
        return (
            await unit._execute(
                "SELECT platform.configuration_command(:business,:operation,:key,CAST(:payload AS jsonb))",
                {
                    "business": business,
                    "operation": operation,
                    "key": key or str(uuid4()),
                    "payload": json.dumps(payload),
                },
            )
        ).scalar_one()


async def configuration_read(h, *, business=BA, ws=A, actor=UA, active=False):
    async with owner_unit(h, ws, actor) as unit:
        name = "configuration_active_read" if active else "configuration_owner_read"
        return (
            await unit._execute(
                f"SELECT platform.{name}(:business)",
                {
                    "business": business,
                },
            )
        ).scalar_one()


async def edit_configuration(h, bundle=None, *, business=BA, ws=A, actor=UA):
    current = await configuration_read(h, business=business, ws=ws, actor=actor)
    return await configuration_command(
        h,
        "EDIT",
        {
            "expected_draft_version": current["draft_version"],
            "bundle": configuration_bundle() if bundle is None else bundle,
        },
        business=business,
        ws=ws,
        actor=actor,
    )


async def publish_configuration(h, bundle=None, *, business=BA, ws=A, actor=UA):
    """Actual owner edit/publish; return the immutable active projection."""
    await edit_configuration(h, bundle, business=business, ws=ws, actor=actor)
    draft = await configuration_read(h, business=business, ws=ws, actor=actor)
    await configuration_command(
        h,
        "PUBLISH",
        {
            "expected_draft_version": draft["draft_version"],
            "expected_activation_version": draft["activation_version"],
        },
        business=business,
        ws=ws,
        actor=actor,
    )
    return await configuration_read(h, business=business, ws=ws, actor=actor, active=True)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def knowledge_pg(pg):
    h = pg
    await migrate("upgrade", "0018")
    h.schema_revision = "0018"
    legacy = config(duration_seconds=120).model_dump(mode="json")
    _, claim, _ = await intent(h, native=True)
    raw = await raw_command(
        h,
        claim,
        "PREPARE",
        config=legacy,
        deadline=(datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
    )
    await reserve_completion(h, claim, raw)
    result = Reply(kind="reply", text="Synthetic legacy receipt", reason=None).model_dump(
        mode="json"
    )
    receipt = await raw_command(h, claim, "COMMIT", run_id=raw["run_id"], result=result)
    _, incomplete, _ = await intent(h, native=True)
    incomplete_run = await raw_command(
        h,
        incomplete,
        "PREPARE",
        config=legacy,
        deadline=(datetime.now(UTC) + timedelta(seconds=120)).isoformat(),
    )
    # Both legacy runs and their original snapshots/receipts survive unchanged.
    retained = await scalar(h, "SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM platform.ai_runs r")
    await migrate("upgrade", "0019")
    await migrate("downgrade", "0018")
    await migrate("upgrade", "0019")
    await migrate("upgrade", "0019")
    h.schema_revision = "0019"
    h.legacy = (claim, legacy, receipt, incomplete, incomplete_run, retained)
    return h


async def assert_stale(operation):
    with pytest.raises(MessagingError) as caught:
        await operation
    assert caught.value.code == Code.AI_STALE


async def test_populated_upgrade_preserves_legacy_and_receipts_without_fabricated_pins(
    knowledge_pg,
):
    h = knowledge_pg
    claim, cfg, receipt, incomplete, old, retained = h.legacy
    rows = await query(
        h,
        "SELECT to_jsonb(r)-ARRAY['knowledge_pin','active_projection','knowledge_release_id'] AS row FROM platform.ai_runs r ORDER BY id",
    )
    assert [r["row"] for r in rows] == retained
    assert await h.kernel.replay_ai(claim.job_id, claim.claim_token, {"config": cfg}) == receipt
    historical = await h.ai.replay(claim, config(duration_seconds=120))
    assert type(historical) is RuntimeReceipt
    assert historical == RuntimeReceipt.model_validate_json(json.dumps(receipt))
    assert "knowledge_pin" not in receipt
    assert (
        await scalar(h, "SELECT count(*) FROM platform.ai_runs WHERE knowledge_pin IS NOT NULL")
        == 0
    )
    await assert_stale(
        raw_command(
            h, incomplete, "RESERVE", run_id=old["run_id"], budget=budget().model_dump(mode="json")
        )
    )
    assert (
        await scalar(
            h, "SELECT calls_used FROM platform.ai_runs WHERE id=:id", id=UUID(old["run_id"])
        )
        == 0
    )
    _, new, _ = await intent(h, native=True)
    with pytest.raises(MessagingError) as caught:
        await raw_command(
            h,
            new,
            "PREPARE",
            config=cfg,
            deadline=(datetime.now(UTC) + timedelta(seconds=100)).isoformat(),
        )
    assert caught.value.code == Code.INVALID_INPUT
    assert (
        await scalar(h, "SELECT count(*) FROM platform.ai_runs WHERE job_id=:id", id=new.job_id)
        == 0
    )


async def test_unpublished_pin_first_publication_and_draft_edit_semantics(knowledge_pg):
    h = knowledge_pg
    cid, claim, _ = await intent(h, native=True)
    run = await prepare_current(h, claim)
    assert run["knowledge_pin"] == {
        "projection_revision": "business_knowledge_v1",
        "business_id": str(BA),
        "release_id": None,
        "activation_version": "0",
    }
    assert run["active_projection"]["bundle"] is None
    await edit_configuration(h)
    payload = dict(run_id=run["run_id"], binding=run["binding"], knowledge_pin=run["knowledge_pin"])
    assert await raw_command(h, claim, "AUTHORIZE", boundary="MODEL", **payload) == {
        "allowed": True
    }
    first = await publish_configuration(h)
    assert first["activation_version"] == "1"
    await assert_stale(raw_command(h, claim, "AUTHORIZE", boundary="MODEL", **payload))
    assert await effects(h, cid) == [0, 0, 0]
    assert (
        await scalar(
            h, "SELECT calls_used FROM platform.ai_runs WHERE id=:id", id=UUID(run["run_id"])
        )
        == 0
    )


@pytest.mark.parametrize(
    "boundary", ["MODEL", "READ", "READ_EXECUTION", "FOLLOWUP", "CANDIDATE", "RESERVE", "COMMIT"]
)
async def test_publication_blocks_each_valid_effect_boundary_without_an_extra_call(
    knowledge_pg, boundary
):
    h = knowledge_pg
    cid, claim, _ = await intent(h, native=True)
    run = await prepare_current(h, claim)
    payload = dict(run_id=run["run_id"], binding=run["binding"], knowledge_pin=run["knowledge_pin"])
    old_calls = 0
    old_reads = 0
    if boundary in {"READ", "READ_EXECUTION", "FOLLOWUP"}:
        await reserve_completion(h, claim, run, "TOOLS")
        old_calls = 1
        if boundary == "FOLLOWUP":
            read = await raw_command(h, claim, "READ", **payload)
            assert read == {
                k: run[k] for k in ("binding", "snapshot", "knowledge_pin", "active_projection")
            }
            old_reads = 1
    elif boundary in {"CANDIDATE", "COMMIT"}:
        await reserve_completion(h, claim, run)
        old_calls = 1
    await publish_configuration(h)
    if boundary == "COMMIT":
        operation = raw_command(
            h,
            claim,
            "COMMIT",
            run_id=run["run_id"],
            result=Reply(kind="reply", text="Must not commit", reason=None).model_dump(mode="json"),
        )
    elif boundary == "RESERVE":
        operation = raw_command(
            h, claim, "RESERVE", run_id=run["run_id"], budget=budget().model_dump(mode="json")
        )
    elif boundary == "READ_EXECUTION":
        operation = raw_command(h, claim, "READ", **payload)
    else:
        operation = raw_command(h, claim, "AUTHORIZE", boundary=boundary, **payload)
    await assert_stale(operation)
    persisted = (
        await query(h, "SELECT * FROM platform.ai_runs WHERE id=:id", id=UUID(run["run_id"]))
    )[0]
    assert (persisted["calls_used"], persisted["reads_used"], persisted["result"]) == (
        old_calls,
        old_reads,
        None,
    )
    assert persisted["knowledge_pin"] == run["knowledge_pin"]
    assert persisted["active_projection"] == run["active_projection"]
    assert await effects(h, cid) == [0, 0, 0]


async def test_rollback_reuses_release_with_new_activation_and_never_revives_old_run(knowledge_pg):
    h = knowledge_pg
    first = await publish_configuration(h)
    _, claim, _ = await intent(h, native=True)
    run = await prepare_current(h, claim)
    bundle = configuration_bundle()
    bundle["services"][0]["price"]["amount_minor"] = 250000
    second = await publish_configuration(h, bundle)
    restored = await configuration_command(
        h,
        "ROLLBACK",
        {
            "expected_activation_version": second["activation_version"],
            "release_id": first["release_id"],
        },
    )
    assert restored["result"]["release_id"] == first["release_id"]
    assert int(restored["result"]["activation_version"]) == int(first["activation_version"]) + 2
    await assert_stale(
        raw_command(
            h, claim, "RESERVE", run_id=run["run_id"], budget=budget().model_dump(mode="json")
        )
    )


async def test_two_workspaces_businesses_and_clients_share_only_their_own_published_bundle(
    knowledge_pg,
):
    h = knowledge_pg
    own = await publish_configuration(h)
    other = await publish_configuration(
        h, configuration_bundle("ceramics"), business=BB, ws=B, actor=UB
    )
    runs = []
    for options in ({"native": True}, {"native": True}, {}, {"workspace": B}):
        _, claim, _ = await intent(h, **options)
        runs.append((claim, await prepare_current(h, claim)))
    assert runs[0][1]["binding"]["client_id"] != runs[1][1]["binding"]["client_id"]
    assert runs[0][1]["knowledge_pin"] == runs[1][1]["knowledge_pin"]
    assert runs[0][1]["active_projection"]["bundle"] == own["bundle"]
    assert runs[2][1]["knowledge_pin"]["business_id"] == str(BA2)
    assert runs[2][1]["active_projection"]["bundle"] is None
    assert runs[3][1]["active_projection"]["bundle"] == other["bundle"]
    assert runs[3][1]["knowledge_pin"]["business_id"] == str(BB)
    claim, run = runs[0]
    await assert_stale(
        raw_command(
            h,
            claim,
            "AUTHORIZE",
            run_id=run["run_id"],
            boundary="MODEL",
            binding=run["binding"],
            knowledge_pin=runs[3][1]["knowledge_pin"],
        )
    )
    for claim, run in runs:
        assert run["active_projection"]["business_id"] == run["binding"]["business_id"]
        assert (
            await scalar(
                h, "SELECT calls_used FROM platform.ai_runs WHERE id=:id", id=UUID(run["run_id"])
            )
            == 0
        )


async def test_runtime_cannot_call_private_knowledge_helpers_or_mutate_pins(knowledge_pg):
    h = knowledge_pg
    for signature in ("ai_knowledge_snapshot(uuid,uuid)", "ai_knowledge_current(platform.ai_runs)"):
        assert (
            await scalar(
                h,
                "SELECT has_function_privilege('asm_runtime',:signature,'EXECUTE')",
                signature="platform." + signature,
            )
            is False
        )
    async with h.runtime.engine.connect() as c:
        with pytest.raises(DBAPIError) as caught:
            await c.execute(
                text("SELECT platform.ai_knowledge_snapshot(:ws,:business)"),
                {"ws": A, "business": BA},
            )
        assert caught.value.orig.sqlstate == "42501"
    _, claim, _ = await intent(h, native=True)
    run = await prepare_current(h, claim)
    async with h.migrator.begin() as c:
        with pytest.raises(DBAPIError) as caught:
            await c.execute(
                text(
                    "UPDATE platform.ai_runs SET knowledge_pin=jsonb_set(knowledge_pin,'{activation_version}','\"999\"') WHERE id=:id"
                ),
                {"id": UUID(run["run_id"])},
            )
        assert caught.value.orig.sqlstate == "23514"
    assert (
        await scalar(
            h, "SELECT knowledge_pin FROM platform.ai_runs WHERE id=:id", id=UUID(run["run_id"])
        )
        == run["knowledge_pin"]
    )


async def wait_blocked(h, pid, pending):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if pending.done():
            await pending  # Surface the actual error instead of waiting for a future forever.
            raise AssertionError("Competing operation completed without the expected lock wait")
        if await scalar(h, "SELECT cardinality(pg_blocking_pids(:pid))>0", pid=pid):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Expected an observed PostgreSQL lock wait")


async def ready_pid(ready, pending):
    completed, _ = await asyncio.wait(
        (ready, pending), timeout=3, return_when=asyncio.FIRST_COMPLETED
    )
    if pending in completed:
        await pending
        raise AssertionError("Competing operation completed before publishing its backend PID")
    assert ready in completed, "Competing operation did not open its connection in time"
    return ready.result()


async def publish_in_unit(unit, business, draft):
    return (
        await unit._execute(
            "SELECT platform.configuration_command(:business,'PUBLISH',:key,CAST(:payload AS jsonb))",
            {
                "business": business,
                "key": str(uuid4()),
                "payload": json.dumps(
                    {
                        "expected_draft_version": draft["draft_version"],
                        "expected_activation_version": draft["activation_version"],
                    }
                ),
            },
        )
    ).scalar_one()


async def selected_delivery(h):
    cid, source, _ = await source_turn(h, native=True)
    job = await h.kernel.enqueue_ai(source)
    claim = await h.kernel.claim_job("knowledge-admission-test", ai=True)
    assert isinstance(claim, AIJobClaim) and claim.job_id == job
    run = await prepare_current(h, claim, delivery=True)
    await reserve_completion(h, claim, run, delivery=True)
    await raw_command(
        h,
        claim,
        "COMMIT",
        delivery=True,
        run_id=run["run_id"],
        result=Reply(kind="reply", text="Synthetic pinned answer", reason=None).model_dump(
            mode="json"
        ),
    )
    delivery = (await query(h, "SELECT * FROM platform.ai_deliveries WHERE job_id=:id", id=job))[0]
    assert delivery["knowledge_pin"] == run["knowledge_pin"]
    return cid, await claim_job(h, delivery["send_job_id"]), delivery


@pytest.mark.parametrize("effect", ["RESERVE", "SEND"])
@pytest.mark.parametrize("first", ["PUBLISH", "ADMISSION"])
async def test_publication_and_admission_serialize_in_both_orders(knowledge_pg, effect, first):
    h = knowledge_pg
    if effect == "RESERVE":
        cid, claim, _ = await intent(h, native=True)
        run = await prepare_current(h, claim)
        business = UUID(run["binding"]["business_id"])
    else:
        cid, claim, delivery = await selected_delivery(h)
        business = BA
    await edit_configuration(h)
    draft = await configuration_read(h)
    before_calls, before_effects = h.adapter.calls, h.adapter.effects
    ready = asyncio.Future()

    async def admission(unit):
        if effect == "RESERVE":
            return await unit.ai_runtime(
                "RESERVE", {"run_id": run["run_id"], "budget": budget().model_dump(mode="json")}
            )
        return await unit._execute("SELECT platform.ai_delivery_begin(:job,:token,NULL,NULL,NULL)")

    async def pending_admission():
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            ready.set_result(await unit._execute("SELECT pg_backend_pid()"))
            return await admission(unit)

    async def pending_publication():
        async with owner_unit(h) as unit:
            ready.set_result((await unit._execute("SELECT pg_backend_pid()", {})).scalar_one())
            return await publish_in_unit(unit, business, draft)

    pending = None
    try:
        if first == "PUBLISH":
            async with owner_unit(h) as unit:
                await publish_in_unit(unit, business, draft)
                # A competing request must create its own authority transaction;
                # inheriting the first request's ContextVars is a forbidden nested UoW.
                pending = asyncio.create_task(pending_admission(), context=Context())
                await wait_blocked(h, await ready_pid(ready, pending), pending)
                assert not pending.done()
                assert (h.adapter.calls, h.adapter.effects) == (before_calls, before_effects)
            if effect == "RESERVE":
                await assert_stale(asyncio.wait_for(pending, 5))
            else:
                assert (await asyncio.wait_for(pending, 5))["code"] == "NOT_ALLOWED"
                assert (
                    await scalar(
                        h,
                        "SELECT status FROM app.outbox_events WHERE id=:id",
                        id=delivery["outbox_id"],
                    )
                    == "FAILED"
                )
            assert (h.adapter.calls, h.adapter.effects) == (before_calls, before_effects)
        else:
            async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
                admitted = await admission(unit)
                if effect == "SEND":
                    assert admitted["code"] == "PERMITTED"
                else:
                    assert admitted == {"sequence": 1}
                pending = asyncio.create_task(pending_publication(), context=Context())
                await wait_blocked(h, await ready_pid(ready, pending), pending)
                assert not pending.done()
            await asyncio.wait_for(pending, 5)
            if effect == "SEND":
                permit = AISendPermit.model_validate(admitted)
                outcome = await h.adapter.send(permit)
                await h.kernel.finish_send(
                    claim.job_id, claim.claim_token, permit.attempt_id, outcome
                )
                assert (h.adapter.calls, h.adapter.effects) == (
                    before_calls + 1,
                    before_effects + 1,
                )
                assert (
                    await scalar(
                        h,
                        "SELECT status FROM app.outbox_events WHERE id=:id",
                        id=delivery["outbox_id"],
                    )
                    == "SENT"
                )
            else:
                assert (
                    await scalar(
                        h,
                        "SELECT calls_used FROM platform.ai_runs WHERE id=:id",
                        id=UUID(run["run_id"]),
                    )
                    == 1
                )
                assert (h.adapter.calls, h.adapter.effects) == (before_calls, before_effects)
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_populated_downgrade_refuses_without_discarding_new_durable_knowledge(knowledge_pg):
    h = knowledge_pg
    before = await scalar(
        h, "SELECT count(*) FROM platform.ai_runs WHERE knowledge_pin IS NOT NULL"
    )
    assert before > 0
    migration, _ = migration_source()
    commands = []
    migration.op = SimpleNamespace(execute=commands.append)
    migration.downgrade()
    with pytest.raises(DBAPIError) as caught:
        async with h.migrator.begin() as c:
            for command in commands:
                await c.execute(text(command))
    assert caught.value.orig.sqlstate == "55000"
    assert (
        await scalar(h, "SELECT count(*) FROM platform.ai_runs WHERE knowledge_pin IS NOT NULL")
        == before
    )
    assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0019"
