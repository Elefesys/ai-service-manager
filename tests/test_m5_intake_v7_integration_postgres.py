"""Exercise v7 through the actual worker, PostgreSQL guards and private delivery."""

import asyncio
import hashlib
import json
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.ai.contracts import IntakeGatewayConfig
from asm.ai.fake import FakeAdapter
from asm.ai.intake import IntakeConversationAgent
from asm.ai.runtime_settings import IntakeRuntimeSettings
from asm.foundation import create_worker
from asm.messaging.errors import Code, MessagingError
from m5_intake_fixtures import intake_bundle
from m5_knowledge_search_fixtures import owner_unit
from m5_portfolio_delivery_fixtures import CAPTION, published_photo, revoke
from m5_portfolio_fixtures import call
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, incoming, reconcile, scalar
from test_m3_1_turns_postgres import seal
from test_m4_agent import config
from test_m4_delivery_postgres import (
    enrollment,
    refresh_synthetic_observation,
    run_turn,
    source_turn,
)
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_intake_postgres import db as db
from test_m5_intake_postgres import next_turn, queue_turn, summary
from test_m5_intake_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_m5_intake_postgres import search_pg as search_pg
from test_m5_intake_postgres import seeded as seeded
from test_m5_portfolio_delivery_postgres import send, status
from test_m5_portfolio_runtime_postgres import analyse, bridge, source_image
from test_tenancy_postgres import BA, UA, A, B

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DETAILS = "CurrentV7Marker flower forearm 8 cm linework"
VALUES = dict(idea="flower", placement="forearm", approximate_size="8 cm", style="linework")


@pytest_asyncio.fixture
async def v7_photo_pg(portfolio_runtime_pg, request):
    async with published_photo(
        portfolio_runtime_pg,
        actual=getattr(request, "param", "controlled") == "s3",
        bundle=intake_bundle(),
    ) as h:
        try:
            yield h
        finally:
            async with h.migrator.begin() as c:
                for table in ("intake_escalation_links", "intake_receipts", "intake_state"):
                    await c.execute(
                        text(f"DELETE FROM platform.{table} WHERE workspace_id IN (:a,:b)"),
                        {"a": A, "b": B},
                    )


def context(messages, revision):
    return next(
        payload
        for msg in messages
        if msg.role == "context"
        if (payload := json.loads(msg.text)).get("revision") == revision
    )


class IntakePhotoModel(FakeAdapter):
    def __init__(
        self,
        route,
        trace,
        *,
        values=None,
        photo=True,
        mutate=None,
        before_reply=None,
        category="NEW_TATTOO",
        switch=False,
        correction=False,
        quote_full=False,
    ):
        super().__init__(route, ("tools", "reply") * 4)
        self.trace = trace
        self.values = VALUES if values is None else values
        self.photo = photo
        self.mutate = mutate
        self.before_reply = before_reply
        self.category = category
        self.switch = switch
        self.correction = correction
        self.quote_full = quote_full

    async def complete(self, request):
        assert request.config.prompt_revision == "conversation_v7"
        result = await super().complete(request)
        self.trace.append("MODEL" if result.kind == "TOOLS" else "FOLLOWUP")
        if result.kind != "OUTPUT":
            return result
        messages = request.request.messages
        source = context(messages, "conversation_intake_v1")["sources"][-1]
        proposed = {
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
                        "quote": source["text"] if self.quote_full else value,
                        "analysis_id": None,
                        "analysis_sha256": None,
                    },
                    "explicit_correction": self.correction,
                }
                for field, value in self.values.items()
            ],
        }
        shown = context(messages, "business_knowledge_v3")["delivery"]["references"]
        value = (
            {
                "kind": "portfolio_photo",
                "caption": CAPTION,
                "selection": dict(shown[0]),
                "intake": proposed,
            }
            if self.photo
            else {"kind": "reply", "text": "Synthetic answer", "reason": None, "intake": proposed}
        )
        if self.mutate:
            self.mutate(value)
        if self.before_reply:
            await self.before_reply()
        return result.model_copy(update={"output_json": json.dumps(value, ensure_ascii=False)})


async def compose(h, cid, trace, *, settings=None, telegram=None, **behavior):
    cfg = IntakeGatewayConfig.model_validate(
        config(
            duration_seconds=120,
            cost_budget=Decimal(5),
            input_bytes=24576,
            output_tokens=512,
            total_tokens=66560,
        ).model_dump()
        | {"prompt_revision": "conversation_v7", "schema_revision": "conversation_result_v3"}
    )
    if settings is None:
        admission = await session(h, cid)
        settings = IntakeRuntimeSettings(
            session_id=UUID(admission["session_id"]),
            workspace_id=A,
            business_id=BA,
            client_id=UUID(admission["client_id"]),
            conversation_id=cid,
            data_profile="SYNTHETIC_INTAKE_V1",
            expires_at=datetime.fromisoformat(admission["expires_at"]),
            max_calls=4,
            max_cost=Decimal(10),
            config=cfg,
        )
    model = IntakePhotoModel(cfg.route, trace, **behavior)
    worker = create_worker(
        h.kernel,
        h.adapter,
        environment="TEST",
        intake_settings=settings,
        model=lambda: model,
        portfolio_storage=h.photo_store,
        ai_embeddings=h.photo_embeddings.client,
        ai_telegram=telegram,
    )
    h.photo_workers.append(worker)
    db = worker.ai.database
    command, embed, commit = db._command, db.embeddings.complete, db.commit

    async def observe_command(claim, operation, **payload):
        tracked = {"READ": "READ", "DELIVERY_READ": "ATTEST"}
        if operation in tracked:
            trace.append(tracked[operation])
        return await command(claim, operation, **payload)

    async def observe_query(*args, **kwargs):
        trace.append("QUERY")
        return await embed(*args, **kwargs)

    async def observe_commit(*args, **kwargs):
        trace.append("COMMIT")
        return await commit(*args, **kwargs)

    db._command = observe_command
    # Each worker has private tracing; sharing the controlled HTTP fixture must
    # not wrap its client across workers or across a recovery.
    db.embeddings = SimpleNamespace(complete=observe_query)
    db.commit = observe_commit
    return worker, model, settings


async def counts(h, cid):
    statements = {
        "intent": "SELECT count(*) FROM platform.portfolio_delivery_intents WHERE conversation_id=:c",
        "message": "SELECT count(*) FROM app.messages WHERE conversation_id=:c AND direction='OUTBOUND'",
        "outbox": "SELECT count(*) FROM app.outbox_events o JOIN app.messages m ON m.id=o.message_id WHERE m.conversation_id=:c",
        "query": "SELECT count(*) FROM platform.knowledge_embedding_calls k JOIN platform.ai_runs r ON r.id=k.run_id WHERE r.conversation_id=:c AND k.kind='QUERY'",
    }
    return {name: await scalar(h, sql, c=cid) for name, sql in statements.items()}


@pytest.mark.parametrize("v7_photo_pg", ["controlled", "s3"], indirect=True)
async def test_v7_current_vision_shared_query_read_attestation_one_private_photo(
    v7_photo_pg, monkeypatch
):
    h = v7_photo_pg
    trace = []
    cid, source, _, image = await source_image(h, caption=DETAILS)
    reserved, completed, _ = await analyse(h, cid)
    assert completed["state"] == "SUCCESS" and len(h.vision_posts) == 1
    worker, model, _ = await compose(h, cid, trace)
    sent = h.adapter.send_photo

    async def observe_send(*args, **kwargs):
        trace.append("SEND")
        return await sent(*args, **kwargs)

    async def observe_get():
        trace.append("PRIVATE_GET")

    monkeypatch.setattr(h.adapter, "send_photo", observe_send)
    h.photo_store.after_get = observe_get
    before = len(h.photo_embeddings.requests)
    claim, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] == "portfolio_photo"
    assert len(model.requests) == 2 and len(h.photo_embeddings.requests) == before + 1
    views = [context(r.request.messages, "business_knowledge_v3") for r in model.requests]
    assert views[0] == views[1]
    view = views[0]
    assert view["search"]["status"] == view["portfolio"]["status"] == "RESULTS"
    assert view["analysis"]["result"]["scale"] == "UNKNOWN"
    run = (await query(h, "SELECT * FROM platform.ai_runs WHERE id=:id", id=delivery["run_id"]))[0]
    assert (
        run["workspace_id"] == A
        and run["business_id"] == BA
        and run["conversation_id"] == cid
        and run["media_pin"]["file_id"] == str(image["id"])
        and run["media_pin"]["analysis_id"] == reserved["analysis_id"]
    )
    assert run["calls_used"] == 2 and run["reads_used"] == 1
    selected = run["result"]["selection"]
    assert set(selected) == {"item_id", "revision_id", "asset_version_id", "source_sha256"}
    assert selected["asset_version_id"] == str(h.photo_source["id"])
    assert selected["source_sha256"] == hashlib.sha256(h.photo_content).hexdigest()
    receipt = run["delivery_read_audit"]
    assert receipt["shown_refs"] == [selected] == view["delivery"]["references"]
    assert len(receipt["context_sha256"]) == 64
    read = json.loads(model.requests[1].exchanges[0].results[0].result_json)
    assert read["context_sha256"] == receipt["context_sha256"]
    assert read["delivery"] == view["delivery"]
    assert len(run["search_refs"]["references"]) == 1
    assert run["portfolio_pin"]["build_id"] == h.photo_state["active_portfolio_build_id"]
    assert len(run["portfolio_refs"]["references"]) == 1
    provenance = (await summary(h, cid))["facts"]
    assert set(f["field"] for f in provenance) == set(VALUES)
    assert {f["source"]["message_id"] for f in provenance} == {str(image["message_id"])}
    await send(h, worker, delivery)
    assert await status(h, delivery) == "SENT"
    assert trace == [
        "QUERY",
        "MODEL",
        "READ",
        "ATTEST",
        "FOLLOWUP",
        "COMMIT",
        "PRIVATE_GET",
        "SEND",
    ]
    assert await counts(h, cid) == dict(intent=1, message=1, outbox=1, query=1)
    assert h.photo_store.gets == 1 and h.adapter.calls == h.adapter.effects == 1
    assert h.adapter.photo_payloads == [(selected["source_sha256"], CAPTION)]
    await worker.execute(claim)
    assert len(trace) == 8 and len(h.photo_embeddings.requests) == before + 1


async def session(h, cid, *, profile="SYNTHETIC_INTAKE_V1", duration=900, cost="10"):
    return await call(
        bridge(h),
        "portfolio_session_admit",
        [
            BA,
            cid,
            {
                "profile_id": profile,
                "execution": "CONTROLLED",
                "eligibility": "EVAL_ONLY",
                "max_calls": 4,
                "max_cost": cost,
                "duration_seconds": duration,
            },
        ],
    )


@pytest.mark.parametrize(
    "wrong", ["profile", "expired", "foreign_owner", "foreign_conversation", "budget"]
)
async def test_v7_nonempty_query_checks_scope_expiry_profile_and_budget_under_lock(
    v7_photo_pg, wrong
):
    h = v7_photo_pg
    cid, source, _ = await source_turn(h, native=True, message_text=DETAILS)
    trace = []
    worker, _, _ = await compose(h, cid, trace)
    await worker.execute(source)
    claim = await h.kernel.claim_job("v7-query-only", ai=True)
    assert claim is not None and claim.job_id == (await enrollment(h, source))["job_id"]
    db = worker.ai.database
    cfg = worker.ai.config
    if wrong == "foreign_conversation":
        foreign, _, _ = await source_turn(
            h, native=True, message_text="Distinct synthetic conversation"
        )
        admitted = await session(h, foreign)
    elif wrong == "profile":
        admitted = await session(h, cid, profile="SYNTHETIC_PORTFOLIO_PHOTO_V1")
    elif wrong == "expired":
        admitted = await session(h, cid, duration=3)
    elif wrong == "budget":
        admitted = await session(h, cid, cost="0.05")
        cfg = IntakeGatewayConfig.model_validate(
            cfg.model_dump()
            | {
                "limits": cfg.limits.model_dump()
                | {"cost_budget": Decimal("0.05"), "call_cost_reservation": Decimal("0.01")}
            }
        )
    else:
        admitted = None
    if admitted is not None:
        db.portfolio_session_id = UUID(admitted["session_id"])
    deadline = datetime.now(UTC) + timedelta(seconds=45)
    if wrong in {"profile", "foreign_conversation"}:
        with pytest.raises(MessagingError) as error:
            await db.prepare(claim, cfg, deadline=deadline)
        assert error.value.code in {Code.AI_STALE, Code.NOT_ALLOWED}
    else:
        run = await db.prepare(claim, cfg, deadline=deadline)
        if wrong == "expired":
            expiry = datetime.fromisoformat(admitted["expires_at"])
            await asyncio.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.05)
        if wrong == "foreign_owner":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u RETURNING 1",
                w=A,
                u=UA,
            )
        try:
            with pytest.raises(MessagingError) as error:
                await db.portfolio_query(claim, run)
            assert error.value.code in {Code.AI_STALE, Code.NOT_ALLOWED, Code.AI_BUDGET}
        finally:
            if wrong == "foreign_owner":
                await scalar(
                    h,
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u RETURNING 1",
                    w=A,
                    u=UA,
                )
    assert trace == [] and (await counts(h, cid))["query"] == 0


async def test_v7_nonempty_query_replay_returns_same_joined_result_once(v7_photo_pg):
    h = v7_photo_pg
    cid, source, _ = await source_turn(h, native=True, message_text=DETAILS)
    trace = []
    worker, _, _ = await compose(h, cid, trace)
    await worker.execute(source)
    claim = await h.kernel.claim_job("v7-query-only", ai=True)
    assert claim is not None and claim.job_id == (await enrollment(h, source))["job_id"]
    db = worker.ai.database
    run = await db.prepare(
        claim, worker.ai.config, deadline=datetime.now(UTC) + timedelta(seconds=45)
    )
    one = await db.portfolio_query(claim, run)
    two = await db.portfolio_query(claim, run)
    assert one == two and one is not None
    assert one.knowledge.status == one.portfolio.status == "RESULTS"
    assert trace == ["QUERY"] and (await counts(h, cid))["query"] == 1


@pytest.mark.parametrize("field", ["item_id", "revision_id", "asset_version_id", "source_sha256"])
async def test_v7_rejects_unattested_selection_without_text_fallback(v7_photo_pg, field):
    h = v7_photo_pg

    def mutate(value):
        value["selection"][field] = "f" * 64 if field == "source_sha256" else str(UUID(int=5))

    cid, source, _ = await source_turn(h, native=True, message_text=DETAILS)
    trace = []
    worker, _, _ = await compose(h, cid, trace, mutate=mutate)
    _, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] is None
    assert trace == ["QUERY", "MODEL", "READ", "ATTEST", "FOLLOWUP"]
    assert await counts(h, cid) == dict(intent=0, message=0, outbox=0, query=1)
    assert h.photo_store.gets == h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize("change", ["revoke", "human", "publish"])
async def test_v7_authority_change_after_read_prevents_commit(v7_photo_pg, change):
    h = v7_photo_pg
    trace = []
    cid, source, scope = await source_turn(h, native=True, message_text=DETAILS)

    async def invalidate():
        from test_m5_portfolio_runtime_postgres import mutate_current

        await mutate_current(h, cid, scope, change)

    worker, _, _ = await compose(h, cid, trace, before_reply=invalidate)
    _, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] is None
    assert trace[:5] == ["QUERY", "MODEL", "READ", "ATTEST", "FOLLOWUP"]
    assert await counts(h, cid) == dict(intent=0, message=0, outbox=0, query=1)
    assert h.photo_store.gets == h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize("after_get", [False, True])
async def test_v7_revoked_photo_rights_stop_send_on_both_sides_of_get(v7_photo_pg, after_get):
    h = v7_photo_pg
    cid, source, _ = await source_turn(h, native=True, message_text=DETAILS)
    trace = []
    worker, _, _ = await compose(h, cid, trace)
    _, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] == "portfolio_photo"

    async def invalidate():
        await revoke(h)

    if after_get:
        h.photo_store.after_get = invalidate
    else:
        await invalidate()
    await send(h, worker, delivery)
    assert h.photo_store.gets == int(after_get) and h.adapter.calls == h.adapter.effects == 0
    assert await status(h, delivery) == "FAILED"
    assert await counts(h, cid) == dict(intent=1, message=1, outbox=1, query=1)


async def test_v7_dispatch_ack_loss_restart_is_unknown_without_another_send(v7_photo_pg):
    h = v7_photo_pg
    cid, source, _ = await source_turn(h, native=True, message_text=DETAILS)
    trace = []
    worker, model, settings = await compose(h, cid, trace)
    claim, delivery = await run_turn(h, worker, source)
    send_claim = await claim_job(h, delivery["send_job_id"])

    async def lost(name):
        if name == "start_after_commit":
            raise SQLAlchemyError("synthetic dispatch ACK loss")

    h.kernel._barrier = lost
    try:
        with pytest.raises(SQLAlchemyError, match="synthetic dispatch ACK loss"):
            await worker.execute(send_claim)
    finally:
        h.kernel._barrier = None
    assert await status(h, delivery) == "DISPATCHING"
    await scalar(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp() WHERE id=:id RETURNING 1",
        id=send_claim.job_id,
    )
    fresh, restarted_model, _ = await compose(h, cid, [], settings=settings)
    await h.kernel.recover_expired()
    assert await status(h, delivery) == "UNKNOWN"
    with pytest.raises(MessagingError):
        await fresh.execute(send_claim)
    await fresh.execute(claim)
    assert await status(h, delivery) == "UNKNOWN"
    assert h.adapter.calls == h.adapter.effects == 0 and h.photo_store.gets == 1
    assert restarted_model.requests == [] and len(model.requests) == 2
    assert await counts(h, cid) == dict(intent=1, message=1, outbox=1, query=1)


async def confirm_idea(h, cid, key):
    row = await summary(h, cid)
    fact = next(f for f in row["facts"] if f["field"] == "idea")
    async with owner_unit(h) as u:
        await u.intake_owner(
            BA,
            cid,
            "CONFIRM",
            key,
            {
                "expected_version": row["version"],
                "expected_fingerprint": row["fingerprint"],
                "field": "idea",
                "value": fact["value"],
                "source": fact["source"],
            },
        )
    return next(f for f in (await summary(h, cid))["facts"] if f["field"] == "idea")


@pytest.mark.parametrize("native", [False, True], ids=["off_unused", "owner_native"])
async def test_v7_serialized_model_read_followup_scope_and_omission(
    v7_photo_pg, monkeypatch, native
):
    h = v7_photo_pg
    old = "OldSameV7_ClientMarker"
    near = "RecentSameV7_ClientMarker"
    foreign = "DifferentV7_ClientMarker"
    current = "OnlyCurrentV7_ClientMarker"
    owner_marker = "VerifiedV7_OwnerReconciliation"
    await source_turn(h, native=True, message_text=foreign)
    if native:
        cid, source, scope = await source_turn(h, native=True, message_text=f"{old} flower")
    else:
        connection = uuid4()
        async with h.migrator.begin() as c:
            keys = {"w": A, "b": BA, "c": connection}
            await c.execute(
                text(
                    "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) "
                    "VALUES(:w,:c,:b,'CONTROLLED','bot-a','off-v7')"
                ),
                keys,
            )
            await c.execute(
                text(
                    "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) "
                    "VALUES(:w,:c,'CONTROLLED','bot-a','off-v7')"
                ),
                keys,
            )
        scope = dict(
            chat_id="off-v7-synthetic", sender_id="off-v7-client", external_connection_id="off-v7"
        )
        _, _, cid = await incoming(h, next(COUNTER), text=f"{old} flower", **scope)
        await owner(h, cid)
        h.intake_scope = scope
        source = await queue_turn(h, f"{old} flower")
    worker, _, _ = await compose(
        h, cid, [], photo=False, values={"idea": "flower"}, quote_full=True
    )
    _, delivered = await run_turn(h, worker, source)
    assert delivered["selected_kind"] == "reply"
    await send(h, worker, delivered)
    original = await confirm_idea(h, cid, "history-confirmation")
    assert old in original["source"]["quote"]

    if native:
        # Owner reconciliation happens in HUMAN, and a later AI generation uses
        # the newly pinned observation. This also exercises fact carry-forward.
        await owner(h, cid, "TAKEOVER")
        await reconcile(h, cid, value=owner_marker)
        await owner(h, cid, "RESUME")
    clean_scope = {k: v for k, v in scope.items() if k != "text"}
    for index in range(12):
        await incoming(h, next(COUNTER), **clean_scope, text=f"HistoryV7Fixture{index} " + near)
    turns = await query(
        h,
        "SELECT id FROM app.conversation_turns WHERE conversation_id=:c AND state='COLLECTING'",
        c=cid,
    )
    assert len(turns) == 1
    await seal(h, turns[0]["id"])

    read_views = []
    read_result = IntakeConversationAgent._read_result

    def observe_read(self, view):
        body = read_result(self, view)
        read_views.append((view.model_dump_json(), body))
        return body

    monkeypatch.setattr(IntakeConversationAgent, "_read_result", observe_read)
    h.intake_scope = clean_scope
    trace = []
    worker, model, _ = await compose(h, cid, trace, photo=False, values={})
    _, delivery = await next_turn(h, worker, f"{current} forearm")
    assert delivery["selected_kind"] == "reply" and len(read_views) == 1
    assert trace == ["QUERY", "MODEL", "READ", "ATTEST", "FOLLOWUP", "COMMIT"]
    assert len(model.requests) == 2
    for request in model.requests:
        wire = request.input_json()
        assert current in wire and old not in wire and foreign not in wire
        assert (near in wire) is native and (owner_marker in wire) is native
        intake = context(request.request.messages, "conversation_intake_v1")
        assert len(intake["sources"]) == 1 and current in intake["sources"][0]["text"]
        assert [
            (f["field"], f["value"], f["source"]["quote"], f["confirmed_by"])
            for f in intake["facts"]
        ] == [("idea", "flower", "", None)]
        history = context(request.request.messages, "conversation_context_v1")
        if native:
            assert history["history_truncated"] and history["history_omitted"] > 0
            assert 0 < len(history["recent"]) <= 8
        else:
            assert history["recent"] == [] and history["history_omitted"] == 0
    full_read, tool_read = read_views[0]
    assert current in full_read and old not in full_read and foreign not in full_read
    assert (near in full_read) is native and (owner_marker in full_read) is native
    assert not any(marker in tool_read for marker in (current, near, old, foreign))
    assert model.requests[1].exchanges[0].results[0].result_json == tool_read
    assert (await summary(h, cid))["facts"] == [original]


async def test_v7_equal_current_candidates_preserve_confirmation_conflict_and_ambiguous_progress(
    v7_photo_pg,
):
    h = v7_photo_pg
    cid, source, h.intake_scope = await source_turn(h, native=True, message_text=DETAILS)
    worker, _, _ = await compose(h, cid, [], photo=False, values={"idea": "flower"})
    _, reply = await run_turn(h, worker, source)
    await send(h, worker, reply)
    confirmed = await confirm_idea(h, cid, "confirmed-before-conflict")

    async def turn(message, values, **options):
        worker, _, _ = await compose(h, cid, [], photo=False, values=values, **options)
        _, reply = await next_turn(h, worker, message)
        assert reply["selected_kind"] == "reply"
        await send(h, worker, reply)
        return await summary(h, cid)

    conflicting = await turn("I am also considering a bird", {"idea": "bird"})
    assert conflicting["facts"] == [confirmed | {"conflict": True}]
    equal = await turn("The flower is still a possibility", {"idea": "flower"})
    assert equal["facts"] == conflicting["facts"]
    ambiguous = await turn("About the other thing?", {}, category="AMBIGUOUS")
    assert ambiguous["facts"] == conflicting["facts"] and ambiguous["category"] == "AMBIGUOUS"
    corrected = await turn("Correction: use bird instead", {"idea": "bird"}, correction=True)
    revised = corrected["facts"][0]
    assert revised["value"] == "bird" and not revised["conflict"]
    assert revised["source"]["message_id"] != confirmed["source"]["message_id"]
    switched = await turn("Start a separate request for a rose", {"idea": "rose"}, switch=True)
    assert len(switched["facts"]) == 1 and switched["facts"][0]["value"] == "rose"
    assert switched["facts"][0]["source"]["message_id"] != revised["source"]["message_id"]


@pytest.mark.parametrize("mutation", ["EDIT", "DELETE"])
async def test_v7_material_change_during_followup_prevents_commit(v7_photo_pg, mutation):
    from test_m3_1_provenance_postgres import process, raw
    from test_m4_reply_rights_postgres import connection, telegram

    h = v7_photo_pg
    cid, source, _ = await source_turn(h, telegram=True, message_text=DETAILS)
    await refresh_synthetic_observation(h, cid)
    message = (
        await query(
            h,
            "SELECT m.provider_message_id,m.provider_chat_id FROM app.messages m "
            "JOIN app.conversation_turn_messages tm ON tm.message_id=m.id WHERE tm.turn_id=:t",
            t=source.turn_id,
        )
    )[0]
    trace = []

    async def invalidate():
        _, _, result = await process(
            h,
            raw(
                900000 + next(COUNTER),
                int(message["provider_message_id"]),
                kind=mutation,
                value="Synthetic updated reference",
                chat=message["provider_chat_id"],
                sender=message["provider_chat_id"],
                date=40,
            ),
        )
        assert result.code == "MATERIAL_PROCESSED"

    requests = []

    async def provider(request):
        requests.append(request.url.path.rsplit("/", 1)[-1])
        assert requests[-1] == "getBusinessConnection"
        return connection()

    async with aclosing(telegram(provider)) as client:
        worker, _, _ = await compose(h, cid, trace, before_reply=invalidate, telegram=client)
        _, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] is None
    assert trace == ["QUERY", "MODEL", "READ", "ATTEST", "FOLLOWUP"]
    assert await counts(h, cid) == dict(intent=0, message=0, outbox=0, query=1)
    assert h.photo_store.gets == h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize("reply_right", [True, False])
async def test_v7_telegram_controlled_transport_checks_fresh_rights_before_send(
    v7_photo_pg, reply_right
):
    from email.parser import BytesParser
    from email.policy import default

    import httpx
    from test_m2_3_db_postgres import EXTERNAL
    from test_m4_reply_rights_postgres import connection, telegram

    h = v7_photo_pg
    cid, source, _ = await source_turn(h, telegram=True, message_text=DETAILS)
    await refresh_synthetic_observation(h, cid)
    requests = []
    trace = []

    async def provider(request):
        method = request.url.path.rsplit("/", 1)[-1]
        requests.append(method)
        if method == "getBusinessConnection":
            return connection(reply=len(requests) == 1 or reply_right)
        assert method == "sendPhoto"
        parts = BytesParser(policy=default).parsebytes(
            b"Content-Type: "
            + request.headers["content-type"].encode()
            + b"\r\n\r\n"
            + await request.aread()
        )
        values = {
            part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
            for part in parts.iter_parts()
        }
        assert values["photo"] == h.photo_content and values["caption"].decode() == CAPTION
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 9578,
                    "business_connection_id": EXTERNAL,
                    "chat": {"id": int(values["chat_id"]), "type": "private"},
                    "date": int(datetime.now(UTC).timestamp()),
                    "caption": CAPTION,
                    "photo": [
                        {
                            "file_id": "v7-synthetic-photo",
                            "file_unique_id": "v7-synthetic-unique",
                            "width": 64,
                            "height": 64,
                        }
                    ],
                },
            },
        )

    async with aclosing(telegram(provider)) as client:
        worker, model, _ = await compose(h, cid, trace, telegram=client)
        _, delivery = await run_turn(h, worker, source)
        assert delivery["selected_kind"] == "portfolio_photo"
        await send(h, worker, delivery)
    assert len(model.requests) == 2 and h.photo_store.gets == 1
    assert requests == ["getBusinessConnection", "getBusinessConnection"] + (
        ["sendPhoto"] if reply_right else []
    )
    assert await status(h, delivery) == ("SENT" if reply_right else "FAILED")
    assert await counts(h, cid) == dict(intent=1, message=1, outbox=1, query=1)
    assert h.adapter.calls == h.adapter.effects == 0


async def test_v7_human_reconcile_resume_new_observation_enables_only_fresh_turn(v7_photo_pg):
    from test_m2_3_db_postgres import OWNER
    from test_m3_1_native_context_postgres import read
    from test_m4_reply_rights_postgres import connection, telegram

    h = v7_photo_pg
    cid, source, h.intake_scope = await source_turn(h, telegram=True, message_text=DETAILS)
    await refresh_synthetic_observation(h, cid)
    trace, probes = [], []

    async def takeover():
        await owner(h, cid, "TAKEOVER")

    async def provider(request):
        probes.append(request.url.path.rsplit("/", 1)[-1])
        assert probes[-1] == "getBusinessConnection"
        return connection()

    async with aclosing(telegram(provider)) as client:
        worker, model, _ = await compose(h, cid, trace, before_reply=takeover, telegram=client)
        claim, old = await run_turn(h, worker, source)
        assert old["selected_kind"] is None and h.adapter.calls == h.photo_store.gets == 0
        assert trace == ["QUERY", "MODEL", "READ", "ATTEST", "FOLLOWUP"] and probes == []
        epoch = int((await read(h, cid))["observation_epoch"])
        observation = await incoming(
            h,
            next(COUNTER),
            process=False,
            **(h.intake_scope | {"sender": OWNER, "value": "SyntheticHumanInputV7"}),
        )
        assert observation.job_id is None
        review = await read(h, cid)
        assert int(review["observation_epoch"]) == epoch + 1
        current = await reconcile(h, cid, value="VerifiedNewV7Observation")
        assert current["outcome"] == "ACCEPTED"
        await owner(h, cid, "RESUME")
        await refresh_synthetic_observation(h, cid)
        fresh, newer, _ = await compose(h, cid, [], telegram=client)
        _, delivery = await next_turn(h, fresh, "FreshV7Turn " + DETAILS)
    assert delivery["selected_kind"] == "portfolio_photo"
    assert len(newer.requests) == 2 and len(model.requests) == 2
    assert "VerifiedNewV7Observation" in newer.requests[0].input_json()
    current_pin = (
        await query(h, "SELECT binding FROM platform.ai_runs WHERE id=:id", id=delivery["run_id"])
    )[0]["binding"]["native"]
    old_pin = (
        await query(h, "SELECT binding FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id)
    )[0]["binding"]["native"]
    assert current_pin["revision_id"] != old_pin["revision_id"]
    assert current_pin["observation_epoch"] == epoch + 1
    assert await counts(h, cid) == dict(intent=1, message=1, outbox=1, query=2)
    assert probes == ["getBusinessConnection"] and h.adapter.calls == h.photo_store.gets == 0


@pytest.mark.parametrize("field", ["item_id", "revision_id", "asset_version_id", "source_sha256"])
async def test_v7_sql_commit_binds_every_attested_reference_field(v7_photo_pg, field):
    h = v7_photo_pg
    cid, source, _ = await source_turn(h, native=True, message_text=DETAILS)
    trace = []
    worker, _, _ = await compose(h, cid, trace)
    database = worker.ai.database
    command = database._command

    async def adjust_commit(claim, operation, **payload):
        if operation == "COMMIT":
            payload["result"]["selection"][field] = (
                "f" * 64 if field == "source_sha256" else str(uuid4())
            )
        return await command(claim, operation, **payload)

    database._command = adjust_commit
    claim, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] is None
    assert trace == ["QUERY", "MODEL", "READ", "ATTEST", "FOLLOWUP", "COMMIT"]
    run = (
        await query(
            h,
            "SELECT result,delivery_read_audit FROM platform.ai_runs WHERE job_id=:id",
            id=claim.job_id,
        )
    )[0]
    assert run["result"] is None and len(run["delivery_read_audit"]["shown_refs"]) == 1
    assert await counts(h, cid) == dict(intent=0, message=0, outbox=0, query=1)
    assert h.photo_store.gets == h.adapter.calls == h.adapter.effects == 0
