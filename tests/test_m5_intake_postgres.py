"""Actual v7 worker/claim commit, with current source and owner-only examples."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.ai.contracts import Budget, IntakeGatewayConfig, IntakeReply
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_contracts import CallCompletion
from asm.ai.runtime_settings import IntakeRuntimeSettings
from asm.conversations.escalations import EscalationCode, EscalationError
from asm.foundation import create_worker
from asm.intake.models import CandidateSet
from asm.messaging.errors import Code, MessagingError
from m5_intake_fixtures import intake_bundle
from m5_knowledge_search_fixtures import db as db
from m5_knowledge_search_fixtures import owner_unit
from m5_knowledge_search_fixtures import search_pg as search_pg
from m5_knowledge_search_fixtures import seeded as seeded
from m5_portfolio_fixtures import call
from sqlalchemy import event, text
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, incoming, reconcile, scalar, wait_blocked
from test_m3_1_turns_postgres import seal
from test_m4_agent import config
from test_m4_delivery_postgres import enrollment, run_turn, source_turn
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_portfolio_runtime_postgres import PrivateBytes, bridge
from test_m5_portfolio_runtime_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_tenancy_postgres import BA, BB, UA, UB, A, B

pytestmark = pytest.mark.integration


class Extractor(FakeAdapter):
    def __init__(self, route, values, *, category="NEW_TATTOO", correction=False, switch=False):
        super().__init__(route, ("reply",) * 4)
        self.values, self.category, self.correction, self.switch = (
            values,
            category,
            correction,
            switch,
        )

    async def complete(self, request):
        response = await super().complete(request)
        context = next(
            json.loads(m.text)
            for m in request.request.messages
            if m.role == "context"
            and json.loads(m.text).get("revision") == "conversation_intake_v1"
        )
        source = context["sources"][-1]
        candidate = {
            "service_id": "consultation",
            "category": self.category,
            "switch_request": self.switch,
            "facts": [
                {
                    "field": field,
                    "value": value,
                    "status": "client-stated",
                    "source": {
                        "message_id": source["message_id"],
                        "source_version": source["source_version"],
                        "quote": value,
                        "analysis_id": None,
                        "analysis_sha256": None,
                    },
                    "explicit_correction": self.correction,
                }
                for field, value in self.values.items()
            ],
        }
        return response.model_copy(
            update={
                "output_json": json.dumps(
                    {
                        "kind": "reply",
                        "text": "Untrusted model wording",
                        "reason": None,
                        "intake": candidate,
                    }
                )
            }
        )


@pytest_asyncio.fixture
async def intake_pg(portfolio_runtime_pg):
    h = portfolio_runtime_pg
    async with owner_unit(h) as u:
        await u.configuration_command(
            BA, "EDIT", str(uuid4()), {"expected_draft_version": "0", "bundle": intake_bundle()}
        )
        await u.configuration_command(
            BA,
            "PUBLISH",
            str(uuid4()),
            {"expected_draft_version": "1", "expected_activation_version": "0"},
        )
    h.intake_workers = []
    try:
        yield h
    finally:
        for worker in h.intake_workers:
            await worker.portfolio_delivery.close()
            if worker.ai.telegram is not None:
                await worker.ai.telegram.aclose()
        async with h.migrator.begin() as c:
            for name in (
                "intake_escalation_links",
                "intake_receipts",
                "duration_cases",
                "intake_state",
            ):
                await c.execute(
                    text(f"DELETE FROM platform.{name} WHERE workspace_id IN (:a,:b)"),
                    {"a": A, "b": B},
                )


async def application(h, values, *, category="NEW_TATTOO", execute=True, telegram=False):
    text_value = "flower forearm 8 cm linework"
    cid, source, scope = await source_turn(
        h, native=True, message_text=text_value, telegram=telegram
    )
    telegram_client = None
    if telegram:
        from test_m4_reply_rights_postgres import connection
        from test_m4_reply_rights_postgres import telegram as telegram_factory

        telegram_client = telegram_factory(lambda request: connection())
        from test_m4_delivery_postgres import refresh_synthetic_observation

        await refresh_synthetic_observation(h, cid)
    admission = await call(
        bridge(h),
        "portfolio_session_admit",
        [
            BA,
            cid,
            {
                "profile_id": "SYNTHETIC_INTAKE_V1",
                "execution": "CONTROLLED",
                "eligibility": "EVAL_ONLY",
                "max_calls": 4,
                "max_cost": "5",
                "duration_seconds": 900,
            },
        ],
    )
    cfg = IntakeGatewayConfig.model_validate(
        config().model_dump()
        | {"prompt_revision": "conversation_v7", "schema_revision": "conversation_result_v3"}
    )
    settings = IntakeRuntimeSettings(
        session_id=UUID(admission["session_id"]),
        workspace_id=A,
        business_id=BA,
        client_id=UUID(admission["client_id"]),
        conversation_id=cid,
        data_profile="SYNTHETIC_INTAKE_V1",
        expires_at=datetime.fromisoformat(admission["expires_at"]),
        max_calls=4,
        max_cost=Decimal(5),
        config=cfg,
    )
    model = Extractor(cfg.route, values, category=category)
    worker = create_worker(
        h.kernel,
        h.adapter,
        environment="TEST",
        intake_settings=settings,
        model=lambda: model,
        ai_telegram=telegram_client,
        portfolio_storage=PrivateBytes(),
    )
    h.intake_workers.append(worker)
    h.intake_scope = scope
    if not execute:
        return cid, worker, model, source, None
    claim, delivery = await run_turn(h, worker, source)
    return cid, worker, model, claim, delivery


async def test_real_worker_applies_sources_and_asks_only_next_missing_question(intake_pg):
    h = intake_pg
    cid, worker, model, claim, delivery = await application(
        h, {"idea": "flower", "placement": "forearm"}
    )
    assert len(model.requests) == 1 and delivery["selected_kind"] == "reply"
    async with owner_unit(h) as u:
        summary = await u.intake_owner(BA, cid, "READ", "", {})
    assert summary["status"] == "CLARIFY" and "размер" in summary["question"]
    assert [(f["field"], f["status"]) for f in summary["facts"]] == [
        ("idea", "client-stated"),
        ("placement", "client-stated"),
    ]
    assert delivery["outbox_id"] is not None
    before = len(model.requests)
    await worker.execute(claim)
    assert len(model.requests) == before
    assert (
        len(await query(h, "SELECT * FROM platform.intake_state WHERE conversation_id=:id", id=cid))
        == 1
    )


@pytest.mark.parametrize("operation,value", [("CONFIRM", "flower"), ("CORRECT", "blue flower")])
async def test_complex_case_uses_existing_action_center_with_closed_summary(
    intake_pg, operation, value
):
    from test_m3_2_escalations_postgres import body, decide

    h = intake_pg
    cid, _, model, _, delivery = await application(h, {"idea": "flower"}, category="COVER_UP")
    assert len(model.requests) == 1 and delivery["selected_kind"] == "handoff"
    eid = delivery["escalation_id"]
    row = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=eid))[0]
    async with owner_unit(h) as u:
        card = await u.escalation_read(eid)
        assert card["policy"] == "PRELIMINARY_INTAKE_OWNER_V1" and card["summary_current"]
        assert card["summary"]["facts"][0]["value"] == "flower" and card["can_resolve"]
        pin = card["summary"]
        command = dict(
            expected_version=pin["version"],
            expected_fingerprint=pin["fingerprint"],
            field="idea",
            value=value,
            source=pin["facts"][0]["source"],
        )
        accepted = await u.intake_owner(BA, cid, operation, "field-decision", command)
    async with owner_unit(h) as u:
        current = await u.escalation_read(eid)
        assert await u.intake_owner(BA, cid, operation, "field-decision", command) == (
            accepted | {"outcome": "REPLAY"}
        )
    assert current["escalation_id"] == card["escalation_id"] == str(eid)
    assert current["status"] == "PENDING" and current["version"] == "1"
    assert current["assignee_user_account_id"] == card["assignee_user_account_id"] == str(UA)
    assert current["summary_current"] and current["can_resolve"]
    assert [(f["status"], f["value"]) for f in current["summary"]["facts"]] == [
        ("owner-confirmed", value)
    ]
    assert (
        len(await query(h, "SELECT id FROM app.escalations WHERE conversation_id=:c", c=cid)) == 1
    )
    stale = body(row, answer="Synthetic internal decision")
    with pytest.raises(EscalationError) as error:
        await decide(h, row, "RESOLVE", "obsolete-decision", stale)
    assert error.value.code == EscalationCode.STALE_STATE
    fresh = stale.model_copy(
        update={"expected_context_version": current["current_context"]["context_version"]}
    )
    result = await decide(h, row, "RESOLVE", "current-decision", fresh)
    replay = await decide(h, row, "RESOLVE", "current-decision", fresh)
    assert result["code"] == "ACCEPTED" and replay == (result | {"code": "REPLAY"})
    async with owner_unit(h) as u:
        final = await u.escalation_read(eid)
    assert final["status"] == "RESOLVED" and final["version"] == "2"


async def overlap_intake_commands(h, worker_call, owner_command, owner_call):
    """Pause the real worker below the configuration lock and above the conversation."""
    loop = asyncio.get_running_loop()
    worker_pid, owner_pid = loop.create_future(), loop.create_future()
    sql_pids = {
        "SELECT platform.ai_delivery_command(": worker_pid,
        f"SELECT platform.{owner_command}(": owner_pid,
    }
    engine = h.runtime.engine.sync_engine

    def record(connection, cursor, statement, parameters, context, executemany):
        for prefix, pid in sql_pids.items():
            if statement.startswith(prefix) and not pid.done():
                pid.set_result(connection.connection.driver_connection.info.backend_pid)

    event.listen(engine, "before_cursor_execute", record)
    try:
        async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
            async with h.migrator.begin() as latch:
                latch_pid = (await latch.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                await latch.execute(
                    text(
                        "SELECT workspace_id FROM platform.workspace_billing_accounts "
                        "WHERE workspace_id=:ws FOR UPDATE"
                    ),
                    {"ws": A},
                )
                worker = tasks.create_task(worker_call())
                await wait_blocked(h, await worker_pid, latch_pid)
                owner = tasks.create_task(owner_call())
                await wait_blocked(h, await owner_pid, worker_pid.result())
                assert await scalar(
                    h,
                    """SELECT EXISTS(
                      SELECT 1 FROM pg_locks waiting JOIN pg_locks held
                        USING (locktype,database,classid,objid,objsubid)
                      WHERE waiting.pid=:waiter AND held.pid=:holder
                        AND waiting.locktype='advisory' AND NOT waiting.granted AND held.granted
                    )""",
                    waiter=owner_pid.result(),
                    holder=worker_pid.result(),
                )
            # Releasing the billing latch lets the worker finish while the owner
            # is still queued on the worker's actual configuration advisory lock.
        return worker.result(), owner.result()
    finally:
        event.remove(engine, "before_cursor_execute", record)


@pytest.mark.parametrize("operation", ["READ", "CONFIRM", "RESOLVE"])
async def test_intake_owner_and_worker_share_configuration_lock_order(intake_pg, operation):
    from test_m3_2_escalations_postgres import decide

    h = intake_pg
    cid, worker, model, _, reply = await application(h, {"idea": "flower"})
    original = await summary(h, cid)
    assert reply["selected_kind"] == "reply" and original["facts"][0]["value"] == "flower"
    source = await queue_turn(h, "Please continue the fictional consultation")
    await worker.execute(source)
    claim = await h.kernel.claim_job("intake-overlap", ai=True)
    assert claim is not None and claim.job_id == (await enrollment(h, source))["job_id"]

    async def prepare():
        return await worker.ai.database.prepare(
            claim, worker.ai.config, deadline=datetime.now(UTC) + timedelta(seconds=20)
        )

    async def read():
        return await summary(h, cid)

    if operation == "READ":
        prepared, read_back = await overlap_intake_commands(h, prepare, "intake_owner", read)
        assert prepared.binding.conversation_id == cid
        assert read_back["facts"] == original["facts"]
        assert read_back["context_version"] == str(prepared.binding.context_version)
        return

    # The already claimed response now competes with a newer intake handoff.
    # PREPARE must reject that response without modifying the pending decision.
    model.category, model.values = "COVER_UP", {}
    _, handoff = await next_turn(h, worker, "This is a fictional cover-up request")
    assert handoff["selected_kind"] == "handoff"
    eid = handoff["escalation_id"]
    row = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=eid))[0]
    async with owner_unit(h) as u:
        card = await u.escalation_read(eid)
    assert card["status"] == "PENDING" and card["can_resolve"]
    pin = card["summary"]
    command = dict(
        expected_version=pin["version"],
        expected_fingerprint=pin["fingerprint"],
        field="idea",
        value="flower",
        source=pin["facts"][0]["source"],
    )

    async def prepare_stale():
        with pytest.raises(MessagingError) as error:
            await prepare()
        return error.value.code

    async def decide_card():
        if operation == "RESOLVE":
            return await decide(h, row, "RESOLVE", "concurrent-resolve")
        async with owner_unit(h) as u:
            return await u.intake_owner(BA, cid, operation, "concurrent-confirm", command)

    rejected, accepted = await overlap_intake_commands(
        h,
        prepare_stale,
        "escalation_command" if operation == "RESOLVE" else "intake_owner",
        decide_card,
    )
    assert rejected == Code.NOT_ALLOWED
    assert h.adapter.calls == h.adapter.effects == 0
    async with owner_unit(h) as u:
        current = await u.escalation_read(eid)
    assert current["escalation_id"] == card["escalation_id"] == str(eid)
    assert current["assignee_user_account_id"] == card["assignee_user_account_id"] == str(UA)
    assert (
        await scalar(h, "SELECT count(*) FROM app.escalations WHERE conversation_id=:c", c=cid) == 1
    )
    if operation == "RESOLVE":
        assert current["status"] == "RESOLVED" and accepted["code"] == "ACCEPTED"
        assert await decide_card() == accepted | {"code": "REPLAY"}
    else:
        assert current["status"] == "PENDING" and accepted["outcome"] == "ACCEPTED"
        assert current["summary"]["facts"][0]["status"] == "owner-confirmed"
        assert await decide_card() == accepted | {"outcome": "REPLAY"}


async def queue_turn(h, text_value):
    field = "value" if h.intake_scope.get("provider") == "TELEGRAM" else "text"
    _, _, cid = await incoming(h, next(COUNTER), **(h.intake_scope | {field: text_value}))
    turn = (
        await query(
            h,
            "SELECT id FROM app.conversation_turns WHERE conversation_id=:c AND state='COLLECTING' ORDER BY id DESC LIMIT 1",
            c=cid,
        )
    )[0]
    sealed = await seal(h, turn["id"])
    job = (
        await query(
            h,
            "SELECT id FROM platform.messaging_jobs WHERE turn_id=:t AND turn_revision=:r AND step='TEST_CONSUME'",
            t=turn["id"],
            r=sealed.turn_revision,
        )
    )[0]["id"]
    return await claim_job(h, job)


async def next_turn(h, worker, text_value):
    return await run_turn(h, worker, await queue_turn(h, text_value))


async def summary(h, cid):
    async with owner_unit(h) as u:
        return await u.intake_owner(BA, cid, "READ", "", {})


async def test_multi_turn_completion_correction_and_owner_confirmation_are_source_bound(intake_pg):
    h = intake_pg
    cid, worker, model, _, delivery = await application(
        h, {"idea": "flower", "placement": "forearm"}
    )
    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"approximate_size": "8 cm", "style": "linework"}
    _, delivery = await next_turn(h, worker, "8 cm linework")
    current = await summary(h, cid)
    assert (
        current["status"] == "PRELIMINARILY_COMPLETE"
        and len(current["facts"]) == 4
        and len(model.requests) == 2
    )
    original = next(f for f in current["facts"] if f["field"] == "approximate_size")
    await worker.execute(await claim_job(h, delivery["send_job_id"]))
    model.values = {"approximate_size": "10 cm"}
    model.correction = True
    _, _ = await next_turn(h, worker, "Actually 10 cm")
    revised = await summary(h, cid)
    fact = next(f for f in revised["facts"] if f["field"] == "approximate_size")
    assert (
        fact["value"] == "10 cm"
        and fact["source"]["message_id"] != original["source"]["message_id"]
    )
    body = {
        "expected_version": revised["version"],
        "expected_fingerprint": revised["fingerprint"],
        "field": fact["field"],
        "value": fact["value"],
        "source": fact["source"],
    }
    async with owner_unit(h) as u:
        accepted = await u.intake_owner(BA, cid, "CONFIRM", "one-field-confirm", body)
    assert accepted["outcome"] == "ACCEPTED"
    confirmed = await summary(h, cid)
    assert (
        next(f for f in confirmed["facts"] if f["field"] == "approximate_size")["status"]
        == "owner-confirmed"
    )
    with pytest.raises(Exception) as error:
        async with owner_unit(h) as u:
            await u.intake_owner(BA, cid, "CONFIRM", "stale-one-field", body)
    assert getattr(error.value, "code", None) == "STALE_STATE"


async def prepared_output(h):
    cid, worker, model, source, _ = await application(h, {}, execute=False)
    await worker.execute(source)
    claim = await h.kernel.claim_job("intake-server-validation", ai=True)
    database = worker.ai.database
    run = await database.prepare(
        claim, worker.ai.config, deadline=datetime.now(UTC) + timedelta(seconds=30)
    )
    first = await database.portfolio_query(claim, run)
    assert first is not None and first.knowledge.status == first.portfolio.status == "EMPTY"
    assert await database.portfolio_query(claim, run) == first
    assert (
        await query(
            h, "SELECT 1 FROM platform.knowledge_embedding_calls WHERE run_id=:id", id=run.run_id
        )
        == []
    )
    run = await database.prepare(claim, worker.ai.config, deadline=run.deadline)
    budget = Budget(
        calls_used=1,
        reads_reserved=0,
        tokens_reserved=100,
        cost_reserved=run.budget.cost_reserved + run.config.limits.call_cost_reservation,
        currency="RUB",
    )
    sequence = await database.reserve(claim, run, budget)
    await database.complete(claim, run, sequence, CallCompletion(kind="OUTPUT"))
    return cid, database, claim, run


@pytest.mark.parametrize("foreign_workspace", [False, True])
async def test_actual_commit_rejects_other_client_source_after_reaching_candidate_guard(
    intake_pg, foreign_workspace
):
    h = intake_pg
    cid, _, _ = await source_turn(
        h,
        native=not foreign_workspace,
        workspace=B if foreign_workspace else A,
        message_text="foreign flower",
    )
    async with owner_unit(
        h, workspace=B if foreign_workspace else A, actor=UB if foreign_workspace else UA
    ) as u:
        foreign = await u.intake_owner(BB if foreign_workspace else BA, cid, "READ", "", {})
    target, database, claim, run = await prepared_output(h)
    source = foreign["sources"][-1]
    candidate = CandidateSet.model_validate_json(
        json.dumps(
            {
                "service_id": "consultation",
                "category": "NEW_TATTOO",
                "switch_request": False,
                "facts": [
                    {
                        "field": "idea",
                        "value": "flower",
                        "status": "client-stated",
                        "source": {
                            "message_id": source["message_id"],
                            "source_version": source["source_version"],
                            "quote": "flower",
                            "analysis_id": None,
                            "analysis_sha256": None,
                        },
                        "explicit_correction": False,
                    }
                ],
            }
        )
    )
    with pytest.raises(MessagingError) as error:
        await database.commit(
            claim,
            run,
            IntakeReply(
                kind="reply",
                text="На каком месте тела вы хотите татуировку?",
                reason=None,
                intake=candidate,
            ),
        )
    assert error.value.code == "AI_STALE"
    assert (await summary(h, target))["facts"] == []


async def test_human_rejects_ai_candidates_and_stale_owner_confirmation(intake_pg):
    h = intake_pg
    cid, database, claim, run = await prepared_output(h)
    before = await summary(h, cid)
    await owner(h, cid, "TAKEOVER")
    candidate = CandidateSet(
        service_id="consultation", category="NEW_TATTOO", switch_request=False, facts=()
    )
    with pytest.raises(MessagingError):
        await database.commit(
            claim,
            run,
            IntakeReply(kind="reply", text="No authority", reason=None, intake=candidate),
        )
    after = await summary(h, cid)
    assert before["control_generation"] != after["control_generation"] and after["facts"] == []
    await reconcile(h, cid)
    await owner(h, cid, "RESUME")
    assert (await summary(h, cid))["facts"] == []


async def test_compatible_publish_and_rollback_retain_fact_while_old_card_stays_stale(
    intake_pg,
):
    h = intake_pg
    cid, _, _, _, delivery = await application(h, {"idea": "flower"}, category="COVER_UP")
    async with owner_unit(h) as u:
        card = await u.escalation_read(delivery["escalation_id"])
        assert card["summary_current"]
        current = card["summary"]
        await u.intake_owner(
            BA,
            cid,
            "CONFIRM",
            "confirm-before-publish",
            {
                "expected_version": current["version"],
                "expected_fingerprint": current["fingerprint"],
                "field": "idea",
                "value": "flower",
                "source": current["facts"][0]["source"],
            },
        )
        before = await u.escalation_read(delivery["escalation_id"])
        release = (await u.intake_owner(BA, cid, "READ", "", {}))["release_id"]
        await u.configuration_command(
            BA, "EDIT", str(uuid4()), {"expected_draft_version": "1", "bundle": intake_bundle()}
        )
        await u.configuration_command(
            BA,
            "PUBLISH",
            str(uuid4()),
            {"expected_draft_version": "2", "expected_activation_version": "1"},
        )
    async with owner_unit(h) as u:
        card = await u.escalation_read(delivery["escalation_id"])
    assert (
        before["summary_current"]
        and not card["summary_current"]
        and card["summary"] is None
        and not card["can_resolve"]
        and card["validity"] == "SOURCE_CHANGED"
    )
    stable = before["summary"]["facts"]
    assert len(stable) == 1 and stable[0]["status"] == "owner-confirmed"
    published = await summary(h, cid)
    assert published["facts"] == stable and published["release_id"] != release
    async with owner_unit(h) as u:
        await u.configuration_command(
            BA,
            "ROLLBACK",
            str(uuid4()),
            {"release_id": release, "expected_activation_version": "2"},
        )
    rolled = await summary(h, cid)
    assert rolled["release_id"] == release and rolled["facts"] == stable
    async with owner_unit(h) as u:
        incompatible = intake_bundle()
        incompatible["services"][0]["intake_fields"] = []
        await u.configuration_command(
            BA, "EDIT", str(uuid4()), {"expected_draft_version": "2", "bundle": incompatible}
        )
        await u.configuration_command(
            BA,
            "PUBLISH",
            str(uuid4()),
            {"expected_draft_version": "3", "expected_activation_version": "3"},
        )
    assert (await summary(h, cid))["facts"] == []


@pytest.mark.parametrize("mutation", ["EDIT", "DELETE", "EDIT_REVERT"])
async def test_actual_material_mutation_removes_cached_fact_and_never_resurrects_old_source(
    intake_pg, mutation
):
    from test_m3_1_provenance_postgres import process, raw

    h = intake_pg
    cid, worker, model, _, delivery = await application(h, {"idea": "flower"}, telegram=True)
    prior = await summary(h, cid)
    fact = prior["facts"][0]
    source = (
        await query(
            h,
            "SELECT provider_message_id,provider_chat_id FROM app.messages WHERE id=:id",
            id=UUID(fact["source"]["message_id"]),
        )
    )[0]
    kind = "DELETE" if mutation == "DELETE" else "EDIT"
    _, _, changed = await process(
        h,
        raw(
            900000 + next(COUNTER),
            int(source["provider_message_id"]),
            kind=kind,
            value="Synthetic edited bird",
            chat=source["provider_chat_id"],
            sender=source["provider_chat_id"],
            date=40,
        ),
    )
    assert changed.code == "MATERIAL_PROCESSED"
    current = await summary(h, cid)
    assert current["facts"] == [] and current["fingerprint"] != prior["fingerprint"]
    if mutation == "EDIT_REVERT":
        await process(
            h,
            raw(
                900000 + next(COUNTER),
                int(source["provider_message_id"]),
                kind="EDIT",
                value="flower forearm 8 cm linework",
                chat=source["provider_chat_id"],
                sender=source["provider_chat_id"],
                date=80,
            ),
        )
        reverted = await summary(h, cid)
        assert reverted["facts"] == []
        assert (
            next(s for s in reverted["sources"] if s["message_id"] == fact["source"]["message_id"])[
                "source_version"
            ]
            != fact["source"]["source_version"]
        )
    assert len(model.requests) == 1


async def test_pending_card_source_change_refuses_old_owner_command_and_hides_summary(intake_pg):
    from asm.intake.errors import IntakeError
    from test_m3_1_provenance_postgres import process, raw
    from test_m3_2_escalations_postgres import decide

    h = intake_pg
    cid, _, _, _, delivery = await application(
        h, {"idea": "flower"}, category="COVER_UP", telegram=True
    )
    eid = delivery["escalation_id"]
    e = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=eid))[0]
    async with owner_unit(h) as u:
        card = await u.escalation_read(eid)
    initial = card["summary"]
    fact = initial["facts"][0]
    msg = (
        await query(
            h,
            "SELECT provider_message_id,provider_chat_id FROM app.messages WHERE id=:id",
            id=UUID(fact["source"]["message_id"]),
        )
    )[0]
    _, _, changed = await process(
        h,
        raw(
            900000 + next(COUNTER),
            int(msg["provider_message_id"]),
            kind="DELETE",
            chat=msg["provider_chat_id"],
            sender=msg["provider_chat_id"],
            date=40,
        ),
    )
    assert changed.code == "MATERIAL_PROCESSED"
    with pytest.raises(IntakeError) as stale:
        async with owner_unit(h) as u:
            await u.intake_owner(
                BA,
                cid,
                "CONFIRM",
                "old-source-confirm",
                {
                    "expected_version": initial["version"],
                    "expected_fingerprint": initial["fingerprint"],
                    "field": "idea",
                    "value": "flower",
                    "source": fact["source"],
                },
            )
    assert stale.value.code == "STALE_STATE"
    with pytest.raises(EscalationError) as invalid:
        await decide(h, e, "RESOLVE", "old-source-decision")
    assert invalid.value.code in {EscalationCode.ESCALATION_FINAL, EscalationCode.STALE_STATE}
    async with owner_unit(h) as u:
        revoked = await u.escalation_read(eid)
    assert (
        not revoked["summary_current"] and revoked["summary"] is None and not revoked["can_resolve"]
    )
    assert revoked["escalation_id"] == str(eid)
    assert (await summary(h, cid))["facts"] == []
