"""Owned disposable PG18, DB-only 0014. No application compatibility bypass.

Native policy is established through the real 0013 command before upgrade.
Every run starts with trusted synthetic ingress, GROUP, TEST_CONSUME and a real
AI_GENERATE lease. The sole fault injection is explicit lease expiry; no forged
worker GUC or imported ContextBinding supplies authority.
"""

import asyncio
import itertools
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.ai.agent import ConversationAgent
from asm.ai.context import ContextBuilder
from asm.ai.contracts import Budget, Reply
from asm.ai.database import AIDatabase, DurableAdapter
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_contracts import CallCompletion, RuntimeReceipt, RuntimeStop
from asm.foundation import RuntimeDatabase, Settings
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AIJobClaim
from asm.tenancy import AuthenticatedAccount, TenantDatabase
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_m2_1_postgres import CA, CA2, provision, query
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER, observed
from test_m3_1_native_context_postgres import (
    claim_job,
    incoming,
    migrate,
    policy,
    reconcile,
    scalar,
)
from test_m3_1_turns_postgres import seal
from test_m4_agent import config
from test_tenancy_postgres import BA, BA2, BB, PROVIDER, UA, UB, A, B

from scripts.m4_pg_observation import preparation, source_tree_from_evidence

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
COUNTER = itertools.count(10000)


async def owner(h, conversation, operation="RESUME", *, workspace=A, actor=UA):
    row = (await query(h, "SELECT * FROM app.conversations WHERE id=:id", id=conversation))[0]
    async with h.runtime.tenancy.transaction(
        AuthenticatedAccount(actor), workspace, uuid4()
    ) as unit:
        return (
            await unit._execute(
                "SELECT platform.conversation_control_execute(:c,:client,:op,:key,:g,:v)",
                dict(
                    c=conversation,
                    client=row["client_id"],
                    op=operation,
                    key=str(uuid4()),
                    g=row["control_generation"],
                    v=row["version"],
                ),
            )
        ).scalar_one()


async def schema(h):
    return await scalar(h, "SELECT version_num FROM platform.alembic_version")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pg(tmp_path_factory):
    # The existing executor owns and destroys the entire disposable cluster.
    # No administrator URL, reset facility, or application readiness override.
    runtime = create_async_engine(
        os.environ["ASM_DATABASE_URL"], poolclass=NullPool, hide_parameters=True
    )
    migrator = create_async_engine(
        os.environ["ASM_MIGRATION_DATABASE_URL"], poolclass=NullPool, hide_parameters=True
    )
    h = SimpleNamespace(
        runtime=SimpleNamespace(engine=runtime, tenancy=TenantDatabase(runtime)),
        migrator=migrator,
        kernel=MessagingDatabase(runtime, environment="TEST"),
        adapter=ControlledAdapter(
            environment="TEST", ledger=tmp_path_factory.mktemp("ai-runtime") / "unused.jsonl"
        ),
        source_tree=source_tree_from_evidence(),
    )
    h.ai = AIDatabase(h.kernel, environment="TEST")
    try:
        assert await schema(h) == "0014"  # clean upgrade performed by the executor
        await migrate("upgrade", "head")
        await migrate("downgrade", "0013")
        assert await schema(h) == "0013"
        profile = await scalar(h, "SELECT platform.human_context_schema_profile()")
        assert profile["valid"], profile
        h.old_constraint = await scalar(
            h,
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='platform.messaging_jobs'::regclass AND conname='messaging_jobs_turn_check'",
        )
        h.old_reschedule = await scalar(
            h,
            "SELECT prosrc FROM pg_proc WHERE oid='platform.messaging_reschedule(uuid,text,boolean,integer,boolean)'::regprocedure",
        )
        async with migrator.begin() as c:
            for actor in (UA, UB, PROVIDER):
                await c.execute(
                    text("INSERT INTO platform.user_accounts(id) VALUES(:id)"), {"id": actor}
                )
            for ws, actor in ((A, UA), (B, UB)):
                await c.execute(text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": ws})
                await c.execute(
                    text(
                        "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
                    ),
                    dict(ws=ws, actor=actor),
                )
            for ws, business in ((A, BA), (A, BA2), (B, BB)):
                await c.execute(
                    text(
                        "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:id,'synthetic AI')"
                    ),
                    dict(ws=ws, id=business),
                )
            for ws in (A, B):
                start = datetime.now(UTC) - timedelta(days=1)
                assert (
                    await c.execute(
                        text(
                            "SELECT platform.initialize_local_messaging_billing(:ws,'AI DB TEST',:start,:end)"
                        ),
                        dict(ws=ws, start=start, end=start + timedelta(days=30)),
                    )
                ).scalar_one() == "CREATED"
        await provision(migrator)
        async with migrator.begin() as c:
            h.telegram_connection = UUID(
                (
                    await c.execute(
                        text(
                            "SELECT platform.initialize_telegram_connection(:ws,:b,:bot,:external,:owner,CAST(:observation AS jsonb))"
                        ),
                        dict(
                            ws=A,
                            b=BA,
                            bot=BOT,
                            external=EXTERNAL,
                            owner=OWNER,
                            observation=json.dumps(observed()),
                        ),
                    )
                ).scalar_one()["connection_id"]
            )
            # Same trusted pre-0014 MATERIAL fixture primitive as M3 native tests.
            await c.execute(
                text(
                    "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE workspace_id=:ws AND connection_id=:id"
                ),
                dict(ws=A, id=h.telegram_connection),
            )
        await policy(h, h.telegram_connection)
        await policy(h, CA)
        # One retained M3 conversation/receipt across the upgrade, not just empty DDL.
        _, _, h.retained = await incoming(h, next(COUNTER), chat_id="retained-0013")
        await reconcile(h, h.retained)
        await owner(h, h.retained)
        h.retained_before = (
            await query(
                h, "SELECT to_jsonb(c) AS row FROM app.conversations c WHERE id=:id", id=h.retained
            )
        )[0]["row"]
        await migrate("upgrade", "0014")
        await migrate("upgrade", "head")
        yield h
    finally:
        await runtime.dispose()
        await migrator.dispose()


async def intent(h, *, native=False, workspace=A, ready=True, telegram=False, proof=None):
    number = next(COUNTER)
    chat = f"ai-{number}"
    scope = dict(chat_id=chat, sender_id=f"user-{number}")
    if telegram:
        native = True
        scope = dict(provider="TELEGRAM", chat=str(number), sender=str(number))
    elif workspace == B:
        scope.update(bot_identity="bot-b", external_connection_id="conn-b")
    elif not native:
        scope["external_connection_id"] = "conn-a2"
    preparation("INGRESS", workspace_id=workspace)
    _, _, cid = await incoming(h, number, **scope)
    if native:
        preparation("RECONCILE", workspace_id=workspace, conversation_id=cid)
        await reconcile(h, cid)
    preparation("RESUME", workspace_id=workspace, conversation_id=cid)
    await owner(h, cid, workspace=workspace, actor=UA if workspace == A else UB)
    preparation("AI_INGRESS", workspace_id=workspace, conversation_id=cid)
    await incoming(h, next(COUNTER), **scope)
    turn = (
        await query(
            h,
            "SELECT id,workspace_id,connection_id,revision,state FROM app.conversation_turns WHERE workspace_id=:ws AND conversation_id=:id AND ingress_control_mode='AI' ORDER BY first_ingress_at DESC,id DESC LIMIT 1",
            ws=workspace,
            id=cid,
        )
    )[0]
    identity = dict(workspace_id=workspace, connection_id=turn["connection_id"], turn_id=turn["id"])
    preparation("PRE_SEAL", **identity, turn_revision=turn["revision"], state=turn["state"])
    assert turn["workspace_id"] == workspace and turn["state"] == "COLLECTING"
    sealed = await seal(h, turn["id"])
    current = (
        await query(
            h,
            "SELECT id,workspace_id,connection_id,revision,state FROM app.conversation_turns WHERE workspace_id=:ws AND id=:id",
            ws=workspace,
            id=turn["id"],
        )
    )[0]
    preparation(
        "POST_SEAL",
        **identity,
        before_revision=turn["revision"],
        turn_revision=current["revision"],
        state=current["state"],
    )
    assert sealed.code == "GROUPED" and sealed.turn_id == turn["id"] == current["id"]
    assert (
        current["workspace_id"] == workspace and current["connection_id"] == turn["connection_id"]
    )
    assert current["state"] == "READY" and current["revision"] == sealed.turn_revision
    assert current["revision"] != turn["revision"]
    # Keep the revision predicate: the pre-seal revision must not select a consumer.
    lookup = "SELECT id FROM platform.messaging_jobs WHERE workspace_id=:ws AND connection_id=:connection AND turn_id=:id AND turn_revision=:r AND kind='PROCESS_TURN' AND step='TEST_CONSUME'"
    parameters = dict(ws=workspace, connection=turn["connection_id"], id=turn["id"])
    assert await query(h, lookup, **parameters, r=turn["revision"]) == []
    jobs = await query(h, lookup, **parameters, r=current["revision"])
    assert len(jobs) == 1
    source_id = jobs[0]["id"]
    preparation(
        "SOURCE_CLAIM", **identity, source_job_id=source_id, turn_revision=current["revision"]
    )
    source = await claim_job(h, source_id)
    assert (
        source.job_id,
        source.workspace_id,
        source.connection_id,
        source.turn_id,
        source.turn_revision,
        source.step,
    ) == (
        source_id,
        workspace,
        turn["connection_id"],
        turn["id"],
        current["revision"],
        "TEST_CONSUME",
    )
    preparation("ENQUEUE", **identity, source_job_id=source_id, turn_revision=current["revision"])
    ai_id = await h.ai.enqueue(source)
    assert await h.ai.enqueue(source) == ai_id
    job = (
        await query(
            h,
            "SELECT workspace_id,connection_id,turn_id,turn_revision,kind,step FROM platform.messaging_jobs WHERE id=:id",
            id=ai_id,
        )
    )[0]
    assert (
        job["workspace_id"],
        job["connection_id"],
        job["turn_id"],
        job["turn_revision"],
        job["kind"],
        job["step"],
    ) == (
        workspace,
        turn["connection_id"],
        turn["id"],
        current["revision"],
        "PROCESS_TURN",
        "AI_GENERATE",
    )
    if proof is not None:
        proof.update(
            identity,
            before_revision=turn["revision"],
            turn_revision=current["revision"],
            source_job_id=source_id,
            job_id=ai_id,
        )
    if not ready:
        return cid, source, ai_id, scope
    preparation("AI_CLAIM", **identity, job_id=ai_id, turn_revision=current["revision"])
    claim = await claim_job(h, ai_id)
    assert isinstance(claim, AIJobClaim)
    assert (
        claim.job_id,
        claim.workspace_id,
        claim.connection_id,
        claim.turn_id,
        claim.turn_revision,
    ) == (ai_id, workspace, turn["connection_id"], turn["id"], current["revision"])
    return cid, claim, scope


async def prepare(h, claim, cfg=None):
    identity = dict(
        workspace_id=claim.workspace_id,
        connection_id=claim.connection_id,
        turn_id=claim.turn_id,
        turn_revision=claim.turn_revision,
        job_id=claim.job_id,
    )
    preparation("PREPARE", **identity)
    run = await h.ai.prepare(
        claim, cfg or config(), deadline=datetime.now(UTC) + timedelta(seconds=100)
    )
    preparation("PREPARED", **identity, run_id=run.run_id)
    return run


def budget(calls=1, reads=0):
    return Budget(
        calls_used=calls,
        reads_reserved=reads,
        tokens_reserved=2000 * calls,
        cost_reserved=Decimal("0.10") * calls,
        currency="RUB",
    )


async def rows(h, run):
    return (await query(h, "SELECT * FROM platform.ai_runs WHERE id=:id", id=run.run_id))[0]


async def calls(h, run):
    return await query(
        h,
        "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id ORDER BY sequence",
        id=run.run_id,
    )


async def effects(h, cid):
    return await scalar(
        h,
        "SELECT jsonb_build_array((SELECT count(*) FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE m.conversation_id=:id),(SELECT count(*) FROM app.escalations WHERE conversation_id=:id),(SELECT count(*) FROM app.messages WHERE conversation_id=:id AND direction='OUTBOUND'))",
        id=cid,
    )


async def test_clean_and_previous_upgrade_preserve_m3_and_application_refuses_0014(pg):
    h = pg
    assert await schema(h) == "0014"
    after = (
        await query(
            h, "SELECT to_jsonb(c) AS row FROM app.conversations c WHERE id=:id", id=h.retained
        )
    )[0]["row"]
    assert after == h.retained_before
    new = await scalar(
        h,
        "SELECT prosrc FROM pg_proc WHERE oid='platform.messaging_reschedule(uuid,text,boolean,integer,boolean)'::regprocedure",
    )
    assert (
        new.replace(
            "j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER','AI_GENERATE')",
            "j.step NOT IN ('GUARDED_TEXT','ESCALATE_OWNER')",
        )
        == h.old_reschedule
    )
    assert not (await scalar(h, "SELECT platform.human_context_schema_profile()"))["valid"]
    app = RuntimeDatabase(Settings())
    try:
        with pytest.raises(RuntimeError, match="Database capability/schema mismatch"):
            await app.check()
    finally:
        await app.close()
    # Real policy command remains closed on 0014; do not use helper assertion as proof.
    row = (await query(h, "SELECT * FROM app.channel_connections WHERE id=:id", id=CA2))[0]
    binding = {
        k: str(row[k])
        for k in ("business_id", "provider", "bot_identity", "external_connection_id")
    } | {"owner_user_id": None}
    with pytest.raises(DBAPIError):
        await scalar(
            h,
            "SELECT platform.human_context_policy_command(:ws,:c,'ENABLE',:key,'OFF_UNUSED',1,CAST(:binding AS jsonb),CAST(:profile AS jsonb))",
            ws=A,
            c=CA2,
            key=str(uuid4()),
            binding=json.dumps(binding),
            profile=json.dumps(
                dict(
                    source_tree=h.source_tree,
                    schema_revision="0013",
                    profile_sha256="a" * 64,
                    drain_confirmed=True,
                )
            ),
        )
    assert (
        await scalar(
            h, "SELECT human_context_policy FROM app.channel_connections WHERE id=:id", id=CA2
        )
        == "OFF_UNUSED"
    )


async def test_actual_runtime_roles_rls_capabilities_and_no_ddl(pg):
    h = pg
    async with h.runtime.engine.begin() as c:
        role = (
            await c.execute(
                text(
                    "SELECT current_user,rolsuper,rolbypassrls,has_schema_privilege(current_user,'platform','CREATE') FROM pg_roles WHERE rolname=current_user"
                )
            )
        ).one()
        assert role == ("asm_runtime", False, False, False)
    for table in ("ai_runs", "ai_provider_calls"):
        row = (
            await query(
                h,
                "SELECT relowner::regrole::text AS owner,relrowsecurity,relforcerowsecurity,has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE') AS access FROM pg_class WHERE oid=CAST(:name AS regclass)",
                name="platform." + table,
            )
        )[0]
        assert tuple(row.values()) == ("asm_migrator", True, True, False)
        with pytest.raises(DBAPIError) as denied:
            async with h.runtime.engine.begin() as c:
                await c.execute(text(f"SELECT * FROM platform.{table}"))
        assert denied.value.orig.sqlstate == "42501"
    with pytest.raises(DBAPIError) as denied:
        async with h.runtime.engine.begin() as c:
            await c.execute(text("CREATE TABLE platform.ai_runtime_forbidden(id integer)"))
    assert denied.value.orig.sqlstate == "42501"


@pytest.mark.parametrize(
    "native,kind", [(False, "reply"), (True, "reply"), (False, "handoff"), (True, "no_reply")]
)
async def test_real_agent_selected_result_survives_new_connection_and_replays_without_adapter(
    pg, native, kind
):
    h = pg
    cid, claim, _ = await intent(h, native=native)
    run = await prepare(h, claim)
    expected = ContextBuilder().build(run.snapshot, run.binding)
    assert run.snapshot["schema_version"] == (3 if native else 2)
    assert (await prepare(h, claim)).run_id == run.run_id
    adapter = FakeAdapter(run.config.route, (kind,))
    receipt = await h.ai.execute(claim, run.config, adapter, deadline=run.deadline)
    assert (
        isinstance(receipt, RuntimeReceipt)
        and receipt.result.kind == kind
        and not receipt.send_permit
    )
    assert len(adapter.requests) == 1
    fresh = AIDatabase(MessagingDatabase(h.runtime.engine, environment="TEST"), environment="TEST")
    again = await fresh.execute(claim, run.config, adapter, deadline=run.deadline)
    assert again == receipt and len(adapter.requests) == 1
    stored = await rows(h, run)
    assert stored["snapshot"] == run.snapshot
    assert (
        ContextBuilder().build(stored["snapshot"], run.binding).snapshot_fingerprint
        == expected.snapshot_fingerprint
    )
    assert stored["calls_used"] == 1 and len(await calls(h, run)) == 1
    assert await effects(h, cid) == [0, 0, 0]
    await owner(h, cid, "TAKEOVER")
    assert await fresh.replay(claim, run.config) == receipt  # fact survives authority revocation
    assert (
        await fresh.authority(claim, run).authorize(run.binding, "CANDIDATE")
    ).status != "ALLOWED"


async def test_two_calls_one_read_original_snapshot_and_bounded_audit(pg):
    h = pg
    cid, claim, _ = await intent(h, native=True)
    run = await prepare(h, claim)
    adapter = FakeAdapter(run.config.route, ("tools", "reply"))
    result = await h.ai.execute(claim, run.config, adapter, deadline=run.deadline)
    assert isinstance(result, RuntimeReceipt) and len(adapter.requests) == 2
    state = await rows(h, run)
    assert (state["calls_used"], state["reads_used"], state["cost_reserved"]) == (
        2,
        1,
        Decimal("0.2"),
    )
    assert set(state["read_audit"]) == {
        "outcome",
        "context_version",
        "turn_revision",
        "native",
        "at",
    }
    assert "text" not in json.dumps(state["read_audit"]) and len(await calls(h, run)) == 2
    assert state["snapshot"] == run.snapshot and await effects(h, cid) == [0, 0, 0]


@pytest.mark.parametrize("foreign", ["workspace", "client", "job", "native", "snapshot"])
async def test_foreign_scope_binding_and_snapshot_do_not_grant_authority(pg, foreign):
    h = pg
    _, claim, _ = await intent(h, native=True)
    run = await prepare(h, claim)
    _, other_claim, _ = await intent(h, workspace=B if foreign == "workspace" else A)
    other = await prepare(h, other_claim)
    changes = {
        "workspace": {"workspace_id": other.binding.workspace_id},
        "client": {"client_id": other.binding.client_id},
        "job": {"job_id": other.binding.job_id},
        "native": {"native": run.binding.native.model_copy(update={"observation_epoch": 999})},
        "snapshot": {"snapshot_digest": other.binding.snapshot_digest},
    }[foreign]
    forged = run.binding.model_copy(update=changes)
    auth = h.ai.authority(claim, run)
    assert (await auth.authorize(forged, "MODEL")).status == "STALE"
    with pytest.raises(MessagingError):
        await auth.read_current(forged)
    with pytest.raises(MessagingError):
        await h.ai._command(
            other_claim,
            "AUTHORIZE",
            run_id=str(run.run_id),
            binding=run.binding.model_dump(mode="json"),
            boundary="MODEL",
        )
    assert (await rows(h, run))["calls_used"] == 0 and not await calls(h, run)


async def test_forged_expired_and_unadmitted_claims_and_tenant_fk(pg):
    h = pg
    _, claim, _ = await intent(h)
    run = await prepare(h, claim)
    for forged in (
        claim.model_copy(update={"claim_token": uuid4()}),
        claim.model_copy(update={"job_id": uuid4()}),
    ):
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            await prepare(h, forged)
    with pytest.raises(DBAPIError):
        async with h.runtime.engine.begin() as c:
            await c.execute(
                text(
                    "SELECT platform.ai_runtime_command(:job,:token,'AUTHORIZE',CAST(:p AS jsonb))"
                ),
                dict(
                    job=claim.job_id,
                    token=claim.claim_token,
                    p=json.dumps(
                        dict(
                            run_id=str(run.run_id),
                            binding=run.binding.model_dump(mode="json"),
                            boundary="MODEL",
                        )
                    ),
                ),
            )
    with pytest.raises(DBAPIError) as fk:
        await scalar(
            h,
            "UPDATE platform.ai_runs SET workspace_id=:ws WHERE id=:id RETURNING id",
            ws=B,
            id=run.run_id,
        )
    assert fk.value.orig.sqlstate == "23503"
    await scalar(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    assert (await h.ai.authority(claim, run).authorize(run.binding, "MODEL")).status == "STALE"
    assert not await calls(h, run)


async def test_one_real_claim_winner_and_no_duplicate_run_under_concurrency(pg):
    h = pg
    _, _, job, _ = await intent(h, ready=False)
    row = (await query(h, "SELECT available_at FROM platform.messaging_jobs WHERE id=:id", id=job))[
        0
    ]

    async def attempt():
        async with h.runtime.engine.begin() as c:
            return (
                await c.execute(
                    text("SELECT platform.messaging_claim('ai-race',:until,:at,:id)"),
                    dict(until=datetime.now(UTC), at=row["available_at"], id=UUID(int=job.int - 1)),
                )
            ).scalar_one()

    results = await asyncio.gather(attempt(), attempt())
    winners = [r for r in results if r["step"] == "CLAIMED" and r["id"] == str(job)]
    assert len(winners) == 1
    from asm.messaging.results import parse_claim

    claim = parse_claim(winners[0]["claim"])
    runs = await asyncio.gather(prepare(h, claim), prepare(h, claim))
    assert runs[0] == runs[1]
    results = await asyncio.gather(
        h.ai.reserve(claim, runs[0], budget()),
        h.ai.reserve(claim, runs[1], budget()),
        return_exceptions=True,
    )
    assert sum(type(r) is int for r in results) == 1 and len(await calls(h, runs[0])) == 1


@pytest.mark.parametrize("when", ["MODEL", "READ"])
@pytest.mark.parametrize("change", ["takeover", "revoke", "input", "native", "observation"])
async def test_changes_during_await_block_result_read_and_followup(pg, when, change):
    h = pg
    cid, claim, scope = await intent(h, native=change == "native", telegram=change == "observation")
    run = await prepare(h, claim)
    entered, release = asyncio.Event(), asyncio.Event()

    class Adapter(FakeAdapter):
        async def complete(self, request):
            if when == "MODEL":
                entered.set()
                await release.wait()
            return await super().complete(request)

    adapter = Adapter(run.config.route, ("reply",) if when == "MODEL" else ("tools", "reply"))
    authority = h.ai.authority(claim, run)
    original_read = authority.read_current
    if when == "READ":

        async def blocked(binding):
            entered.set()
            await release.wait()
            return await original_read(binding)

        authority.read_current = blocked
    agent = ConversationAgent(run.config, DurableAdapter(h.ai, claim, run, adapter), authority)
    task = asyncio.create_task(
        agent.run(run.binding, run.snapshot, run_id=str(run.run_id), deadline=run.deadline)
    )
    revoked = False
    try:
        await asyncio.wait_for(entered.wait(), 5)
        # Actual DB shows no model-wait transaction or held runtime connection.
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND datname=current_database()",
            )
            == 0
        )
        if change == "revoke":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET status='REVOKED',version=version+1 WHERE workspace_id=:ws AND user_account_id=:actor RETURNING version",
                ws=A,
                actor=UA,
            )
            revoked = True
        elif change == "observation":
            before = (
                await query(
                    h,
                    "SELECT control_mode,control_generation,version,human_context_revision_id,human_observation_epoch FROM app.conversations WHERE id=:id",
                    id=cid,
                )
            )[0]
            observed_receipt = await incoming(
                h,
                next(COUNTER),
                **(scope | dict(sender=OWNER)),
                process=False,
                value="Synthetic native owner agreement",
            )
            assert observed_receipt.job_id is None
            after = (
                await query(
                    h,
                    "SELECT control_mode,control_generation,version,human_context_revision_id,human_observation_epoch FROM app.conversations WHERE id=:id",
                    id=cid,
                )
            )[0]
            assert after["human_observation_epoch"] == before["human_observation_epoch"] + 1
            assert {k: v for k, v in after.items() if k != "human_observation_epoch"} == {
                k: v for k, v in before.items() if k != "human_observation_epoch"
            }
        elif change == "input":
            await incoming(h, next(COUNTER), **scope)
        else:
            await owner(h, cid, "TAKEOVER")
            if change == "native":
                await reconcile(h, cid, value="Revised owner-confirmed context")
                await owner(h, cid)
        release.set()
        outcome = await asyncio.wait_for(task, 5)
        assert outcome.status == "STOP" and outcome.candidate is None
        assert len(adapter.requests) == 1
        state = await rows(h, run)
        assert state["result"] is None and state["reads_used"] == 0
        assert await effects(h, cid) == [0, 0, 0]
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if revoked:
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET status='ACTIVE',version=version+1 WHERE workspace_id=:ws AND user_account_id=:actor RETURNING version",
                ws=A,
                actor=UA,
            )


async def test_crash_reservation_unknown_reclaim_cannot_repeat(pg):
    h = pg
    cid, claim, _ = await intent(h)
    cfg = config(duration_seconds=120.0)
    run = await prepare(h, claim, cfg)
    await h.ai.reserve(claim, run, budget())  # process lost before reliable completion
    record = (await calls(h, run))[0]
    assert record["completion"]["cost"]["amount"] is None and record["completed_at"] is None
    await scalar(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    row = (
        await query(
            h, "SELECT lease_until FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
        )
    )[0]
    async with h.runtime.engine.begin() as c:
        recovered = (
            await c.execute(
                text("SELECT platform.messaging_recover_expired(:until,:at,:id)"),
                dict(
                    until=datetime.now(UTC),
                    at=row["lease_until"],
                    id=UUID(int=claim.job_id.int - 1),
                ),
            )
        ).scalar_one()
    assert recovered["step"] == "RECOVERED"
    next_claim = await claim_job(h, claim.job_id)
    assert next_claim.claim_token != claim.claim_token
    again = await prepare(h, next_claim, cfg)
    assert again.run_id == run.run_id and again.budget.calls_used == 1
    adapter = FakeAdapter(cfg.route)
    result = await h.ai.execute(next_claim, cfg, adapter, deadline=run.deadline)
    assert (
        isinstance(result, RuntimeStop) and result.reason == "INCOMPLETE" and adapter.requests == []
    )
    assert len(await calls(h, run)) == 1 and await effects(h, cid) == [0, 0, 0]


async def test_crash_before_reservation_rollback_leaves_no_provider_budget(pg):
    h = pg
    _, claim, _ = await intent(h)
    run = await prepare(h, claim)

    class Abort(Exception):
        pass

    with pytest.raises(Abort):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            await unit.ai_runtime(
                "RESERVE", dict(run_id=str(run.run_id), budget=budget().model_dump(mode="json"))
            )
            raise Abort()
    assert not await calls(h, run) and (await rows(h, run))["calls_used"] == 0
    adapter = FakeAdapter(run.config.route)
    assert isinstance(
        await h.ai.execute(claim, run.config, adapter, deadline=run.deadline), RuntimeReceipt
    )
    assert len(adapter.requests) == 1


async def test_result_rollback_and_completed_call_crash_cannot_regenerate(pg):
    h = pg
    cid, claim, _ = await intent(h)
    run = await prepare(h, claim)
    await h.ai.reserve(claim, run, budget())
    await h.ai.complete(claim, run, 1, CallCompletion(kind="OUTPUT"))
    candidate = Reply(kind="reply", text="chosen only after commit", reason=None)

    class Abort(Exception):
        pass

    with pytest.raises(Abort):
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
            await unit.ai_runtime(
                "COMMIT", dict(run_id=str(run.run_id), result=candidate.model_dump(mode="json"))
            )
            raise Abort()
    assert (await rows(h, run))["result"] is None
    assert (
        await scalar(h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id)
        == "RUNNING"
    )
    fresh = AIDatabase(MessagingDatabase(h.runtime.engine, environment="TEST"), environment="TEST")
    adapter = FakeAdapter(run.config.route)
    assert (
        await fresh.execute(claim, run.config, adapter, deadline=run.deadline)
    ).reason == "INCOMPLETE"
    assert not adapter.requests and len(await calls(h, run)) == 1
    receipt = await fresh.commit(claim, run, candidate)
    assert (
        receipt.result == candidate
        and not receipt.send_permit
        and await effects(h, cid) == [0, 0, 0]
    )


async def test_read_budget_unknown_cost_cancel_and_conflicting_completion(pg):
    h = pg
    _, claim, _ = await intent(h)
    run = await prepare(h, claim)
    await h.ai.reserve(claim, run, budget())
    await h.ai.complete(claim, run, 1, CallCompletion(kind="TOOLS"))
    auth = h.ai.authority(claim, run)
    first = await auth.read_current(run.binding)
    assert first.snapshot == run.snapshot
    with pytest.raises(MessagingError, match="AI_BUDGET"):
        await auth.read_current(run.binding)
    with pytest.raises(MessagingError, match="IDEMPOTENCY_KEY_CONFLICT"):
        await h.ai.complete(claim, run, 1, CallCompletion(kind="OUTPUT"))
    await h.ai.reserve(claim, run, budget(2, 1))
    with pytest.raises(MessagingError, match="AI_BUDGET"):
        await h.ai.reserve(claim, run, budget(3, 1))
    assert (await calls(h, run))[1]["completion"]["usage"]["input_tokens"] is None
    _, cancel_claim, _ = await intent(h)
    cancel_run = await prepare(h, cancel_claim)
    entered = asyncio.Event()

    class Waiting(FakeAdapter):
        async def complete(self, request):
            entered.set()
            await asyncio.Event().wait()

    adapter = Waiting(cancel_run.config.route)
    task = asyncio.create_task(
        h.ai.execute(cancel_claim, cancel_run.config, adapter, deadline=cancel_run.deadline)
    )
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    records = await calls(h, cancel_run)
    assert len(records) == 1 and records[0]["completion"]["kind"] == "UNKNOWN"
    retry = FakeAdapter(cancel_run.config.route)
    assert isinstance(
        await h.ai.execute(cancel_claim, cancel_run.config, retry, deadline=cancel_run.deadline),
        RuntimeStop,
    )
    assert retry.requests == []


async def test_atomic_result_conflict_and_selected_receipt_survives_process(pg):
    h = pg
    cid, claim, _ = await intent(h)
    run = await prepare(h, claim)
    await h.ai.reserve(claim, run, budget())
    await h.ai.complete(claim, run, 1, CallCompletion(kind="OUTPUT"))
    one, two = (
        Reply(kind="reply", text="one", reason=None),
        Reply(kind="reply", text="two", reason=None),
    )
    result = await asyncio.gather(
        h.ai.commit(claim, run, one), h.ai.commit(claim, run, two), return_exceptions=True
    )
    winners = [v for v in result if isinstance(v, RuntimeReceipt)]
    errors = [v for v in result if isinstance(v, MessagingError)]
    assert len(winners) == len(errors) == 1 and errors[0].code == Code.IDEMPOTENCY_KEY_CONFLICT
    assert await h.ai.commit(claim, run, winners[0].result) == winners[0]
    # Claim passed only via stdin, never argv/logs. New Python process/engine.
    source = """import asyncio,json,sys
from datetime import UTC,datetime,timedelta
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from asm.ai.database import AIDatabase
from asm.ai.contracts import GatewayConfig
from asm.ai.fake import FakeAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.results import parse_claim
import os
async def main():
 p=json.load(sys.stdin); e=create_async_engine(os.environ["ASM_DATABASE_URL"],poolclass=NullPool,hide_parameters=True)
 try:
  cfg=GatewayConfig.model_validate_json(json.dumps(p["config"])); a=FakeAdapter(cfg.route)
  r=await AIDatabase(MessagingDatabase(e,environment="TEST"),environment="TEST").execute(parse_claim(p["claim"]),cfg,a,deadline=datetime.now(UTC)+timedelta(seconds=20))
  print(json.dumps({"run_id":str(r.run_id),"send_permit":r.send_permit,"calls":len(a.requests)}))
 finally: await e.dispose()
asyncio.run(main())"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        source,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(
            json.dumps(
                dict(config=run.config.model_dump(mode="json"), claim=claim.model_dump(mode="json"))
            ).encode()
        ),
        20,
    )
    assert process.returncode == 0, "subprocess failed; sensitive stderr withheld"
    assert json.loads(stdout) == dict(run_id=str(run.run_id), send_permit=False, calls=0)
    assert not stderr and await effects(h, cid) == [0, 0, 0]


async def test_changed_config_input_and_retained_turn_consumer_rejected_ai_step(pg):
    h = pg
    cid, claim, scope = await intent(h)
    run = await prepare(h, claim)
    with pytest.raises(MessagingError, match="IDEMPOTENCY_KEY_CONFLICT"):
        await prepare(h, claim, config(cost_budget=Decimal("0.40")))
    with pytest.raises(MessagingError, match="INVALID_INPUT"):
        await h.kernel.process_turn(claim)
    await incoming(h, next(COUNTER), **scope)
    with pytest.raises(MessagingError, match="IDEMPOTENCY_KEY_CONFLICT"):
        await prepare(h, claim)
    assert (await rows(h, run))["result"] is None and not await calls(h, run)
    assert await effects(h, cid) == [0, 0, 0]


async def test_retained_consumer_and_ai_terminal_retry_do_not_change_canonical_turn(pg):
    from asm.conversations.turns import consume

    h = pg
    cid, source, job, _ = await intent(h, ready=False)
    snapshot = await h.kernel.process_turn(source)
    old = await h.kernel.finish_turn(source, consume(snapshot))
    assert old.code == "OBSERVED"
    claim = await claim_job(h, job)
    run = await prepare(h, claim)
    before = (
        await query(
            h, "SELECT revision,state FROM app.conversation_turns WHERE id=:id", id=claim.turn_id
        )
    )[0]
    async with h.kernel.admit_job(claim.job_id, claim.claim_token) as unit:
        await unit.retry(Code.DEPENDENCY_UNAVAILABLE, False)
    after = (
        await query(
            h, "SELECT revision,state FROM app.conversation_turns WHERE id=:id", id=claim.turn_id
        )
    )[0]
    assert before == after and after["state"] == "READY"
    assert (await rows(h, run))["result"] is None and await effects(h, cid) == [0, 0, 0]


async def test_used_downgrade_refuses_before_any_change(pg):
    h = pg
    _, claim, _ = await intent(h)
    own_run = await prepare(h, claim)
    stored = await rows(h, own_run)
    assert (stored["id"], stored["job_id"], stored["turn_id"], stored["turn_revision"]) == (
        own_run.run_id,
        claim.job_id,
        claim.turn_id,
        claim.turn_revision,
    )
    preparation(
        "DOWNGRADE_READY",
        run_id=own_run.run_id,
        job_id=claim.job_id,
        turn_id=claim.turn_id,
        turn_revision=claim.turn_revision,
    )
    ddl_before = await scalar(
        h,
        "SELECT jsonb_build_array(to_regclass('platform.ai_runs')::oid,to_regclass('platform.ai_provider_calls')::oid,to_regprocedure('platform.ai_runtime_command(uuid,uuid,text,jsonb)')::oid,to_regprocedure('platform.ai_runtime_replay(uuid,uuid,jsonb)')::oid)",
    )
    before = await scalar(
        h,
        "SELECT jsonb_build_array((SELECT count(*) FROM platform.ai_runs),(SELECT count(*) FROM platform.ai_provider_calls),(SELECT count(*) FROM platform.messaging_jobs))",
    )
    assert before[0] > 0
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "downgrade",
        "0013",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode != 0 and b"AI_RUNTIME_DURABLE_DATA" in stderr
    after = await scalar(
        h,
        "SELECT jsonb_build_array((SELECT count(*) FROM platform.ai_runs),(SELECT count(*) FROM platform.ai_provider_calls),(SELECT count(*) FROM platform.messaging_jobs))",
    )
    assert before == after and await schema(h) == "0014"
    assert await rows(h, own_run) == stored
    assert (
        await scalar(
            h,
            "SELECT jsonb_build_array(to_regclass('platform.ai_runs')::oid,to_regclass('platform.ai_provider_calls')::oid,to_regprocedure('platform.ai_runtime_command(uuid,uuid,text,jsonb)')::oid,to_regprocedure('platform.ai_runtime_replay(uuid,uuid,jsonb)')::oid)",
        )
        == ddl_before
    )


@pytest.mark.parametrize("mode", ["controlled", "native", "telegram"])
async def test_post_seal_revision_binds_real_claim_and_run_and_rejects_stale(pg, mode):
    h, proof = pg, {}
    cid, claim, _ = await intent(
        h, native=mode == "native", telegram=mode == "telegram", proof=proof
    )
    assert proof["before_revision"] != proof["turn_revision"]
    run = await prepare(h, claim)
    stored = await rows(h, run)
    expected = (
        proof["workspace_id"],
        proof["connection_id"],
        proof["turn_id"],
        proof["turn_revision"],
        proof["job_id"],
    )
    assert (
        claim.workspace_id,
        claim.connection_id,
        claim.turn_id,
        claim.turn_revision,
        claim.job_id,
    ) == expected
    assert (
        run.binding.workspace_id,
        run.binding.connection_id,
        run.binding.turn_id,
        run.binding.turn_revision,
        run.binding.job_id,
    ) == expected
    assert (
        stored["workspace_id"],
        stored["connection_id"],
        stored["turn_id"],
        stored["turn_revision"],
        stored["job_id"],
    ) == expected
    assert stored["id"] == run.run_id and run.binding.conversation_id == cid
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.ai_runs WHERE workspace_id=:ws AND turn_id=:id AND turn_revision=:r",
            ws=proof["workspace_id"],
            id=proof["turn_id"],
            r=proof["before_revision"],
        )
        == 0
    )
    authority = h.ai.authority(claim, run)
    assert (await authority.authorize(run.binding, "MODEL")).status == "ALLOWED"
    stale = run.binding.model_copy(update={"turn_revision": proof["before_revision"]})
    assert (await authority.authorize(stale, "MODEL")).status == "STALE"
    with pytest.raises(MessagingError) as denied:
        await authority.read_current(stale)
    assert denied.value.code == Code.AI_STALE
    assert (await rows(h, run))["result"] is None and await calls(h, run) == []
    assert await effects(h, cid) == [0, 0, 0]
    preparation("STALE_REVISION_REJECTED", **proof, run_id=run.run_id)
