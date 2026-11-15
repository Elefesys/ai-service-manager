"""Owned current PG20 worker/embedding/AI path, without provider or live Telegram."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from asm.ai.runtime_contracts import PreparedSearchRun, SearchRuntimeReceipt
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind
from generic_pg_schema import current_snapshot
from m5_configuration_fixtures import configuration_bundle
from m5_knowledge_search_fixtures import (
    ControlledEmbeddings,
    application,
    knowledge_command,
    knowledge_state,
    publication,
    vector,
)
from m5_knowledge_search_fixtures import (
    db as db,
)
from m5_knowledge_search_fixtures import (
    search_pg as search_pg,
)
from m5_knowledge_search_fixtures import (
    seeded as seeded,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import query
from test_m2_3_db_postgres import OWNER
from test_m3_1_native_context_postgres import claim_job, incoming, reconcile, scalar
from test_m4_delivery_postgres import enrollment, run_turn, source_turn
from test_m4_reply_rights_postgres import connection, telegram
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_knowledge_postgres import (
    configuration_command,
    configuration_read,
    edit_configuration,
)
from test_tenancy_postgres import BA2, BB, UA, UB, A, B

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def publication_snapshot(h):
    async with h.migrator.connect() as connection:
        return await current_snapshot(connection)


async def assert_legacy_publish_refused(h, body, code, *, key=None):
    before = await publication_snapshot(h)
    with pytest.raises(DBAPIError) as refused:
        await configuration_command(h, "PUBLISH", body, key=key)
    assert refused.value.orig.sqlstate == "P2701"
    assert refused.value.orig.diag.message_primary == code
    assert await publication_snapshot(h) == before


async def test_linked_build_requires_joint_publication_without_breaking_old_replay(search_pg):
    h = search_pg
    await edit_configuration(h)
    draft = await configuration_read(h)
    original_body = {
        "expected_draft_version": draft["draft_version"],
        "expected_activation_version": draft["activation_version"],
    }
    key = str(uuid4())
    original = await configuration_command(h, "PUBLISH", original_body, key=key)
    assert original["outcome"] == "ACCEPTED"
    assert (await knowledge_state(h))["active_build_id"] is None

    _, linked, _ = await publication(h, ["Retain this explicitly published source."])
    assert linked["active_build_id"] is not None
    before = await publication_snapshot(h)
    replay = await configuration_command(h, "PUBLISH", original_body, key=key)
    assert replay == {"outcome": "REPLAY", "result": original["result"]}
    assert await publication_snapshot(h) == before

    draft = await configuration_read(h)
    current = {
        "expected_draft_version": draft["draft_version"],
        "expected_activation_version": draft["activation_version"],
    }
    await assert_legacy_publish_refused(h, current, "KNOWLEDGE_BUILD_REQUIRED")
    await assert_legacy_publish_refused(h, current, "IDEMPOTENCY_KEY_CONFLICT", key=key)
    await assert_legacy_publish_refused(
        h, current | {"expected_activation_version": "0"}, "STALE_STATE"
    )
    await assert_legacy_publish_refused(h, current | {"expected_draft_version": "0"}, "STALE_STATE")
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
            ),
            {"w": A, "u": UA},
        )
    try:
        # Live OWNER admission still precedes replay and the new publish check.
        await assert_legacy_publish_refused(h, original_body, "ACCESS_DENIED", key=key)
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u"
                ),
                {"w": A, "u": UA},
            )


@pytest.mark.parametrize("operation", ["KNOWLEDGE_REVOKE", "KNOWLEDGE_DELETE"])
async def test_last_source_withdrawal_can_publish_explicit_empty_build_without_embedding_calls(
    search_pg, operation
):
    h = search_pg
    private_text = "This withdrawn source must never reach the new reply."
    _, previous, embeddings = await publication(h, [private_text])
    source = previous["sources"][0]
    old_build = next(b for b in previous["builds"] if b["build_id"] == previous["active_build_id"])
    await edit_configuration(h, configuration_bundle() | {"communication_style": "CONCISE"})
    await knowledge_command(
        h,
        operation,
        {
            "schema_version": 1,
            "source_id": source["source_id"],
            "expected_source_version": source["source_version"],
            "expected_activation_version": previous["activation_version"],
        },
    )
    withdrawn = await knowledge_state(h)
    assert withdrawn["release_id"] == previous["release_id"]
    assert withdrawn["active_build_id"] == previous["active_build_id"]
    if operation == "KNOWLEDGE_DELETE":
        assert withdrawn["sources"] == []
    else:
        assert withdrawn["sources"][0]["state"] == "REVOKED"
        assert not withdrawn["sources"][0]["head"]["confirmed"]
    draft = await configuration_read(h)
    await assert_legacy_publish_refused(
        h,
        {
            "expected_draft_version": draft["draft_version"],
            "expected_activation_version": withdrawn["activation_version"],
        },
        "KNOWLEDGE_BUILD_REQUIRED",
    )
    calls = await query(
        h,
        "SELECT to_jsonb(c) AS row FROM platform.knowledge_embedding_calls c WHERE workspace_id=:w ORDER BY id",
        w=A,
    )
    posts = len(embeddings.requests)
    created = await knowledge_command(
        h,
        "KNOWLEDGE_BUILD_CREATE",
        {
            "schema_version": 1,
            "expected_sources_hash": withdrawn["sources_hash"],
            "revision_ids": [],
        },
    )
    prepared = await knowledge_state(h)
    empty = next(b for b in prepared["builds"] if b["build_id"] == created["result"]["build_id"])
    assert empty["state"] == "READY" and empty["revision_ids"] == []
    assert empty["chunk_count"] == empty["calls_reserved"] == empty["calls_completed"] == 0
    raw = (
        await query(
            h,
            "SELECT manifest,plan FROM platform.knowledge_builds WHERE id=:id",
            id=UUID(empty["build_id"]),
        )
    )[0]
    assert raw == {"manifest": [], "plan": []}
    assert (
        prepared["release_id"],
        prepared["active_build_id"],
        prepared["activation_version"],
    ) == (
        withdrawn["release_id"],
        withdrawn["active_build_id"],
        withdrawn["activation_version"],
    )
    with pytest.raises(DBAPIError) as old_refused:
        await knowledge_command(
            h,
            "KNOWLEDGE_PUBLISH",
            {
                "schema_version": 1,
                "expected_draft_version": draft["draft_version"],
                "expected_activation_version": withdrawn["activation_version"],
                "build_id": old_build["build_id"],
                "expected_build_version": old_build["build_version"],
            },
        )
    assert old_refused.value.orig.diag.message_primary == "BUILD_NOT_READY"
    published = await knowledge_command(
        h,
        "KNOWLEDGE_PUBLISH",
        {
            "schema_version": 1,
            "expected_draft_version": draft["draft_version"],
            "expected_activation_version": withdrawn["activation_version"],
            "build_id": empty["build_id"],
            "expected_build_version": empty["build_version"],
        },
    )
    final = await knowledge_state(h)
    assert final["release_id"] == published["result"]["release_id"] != previous["release_id"]
    assert final["active_build_id"] == empty["build_id"]
    assert int(final["activation_version"]) == int(withdrawn["activation_version"]) + 1
    assert (await configuration_read(h, active=True))["bundle"]["communication_style"] == "CONCISE"
    # An explicit empty manifest remains linked; subsequent settings publications
    # must continue using the joint path instead of silently dropping its link.
    await assert_legacy_publish_refused(
        h,
        {
            "expected_draft_version": draft["draft_version"],
            "expected_activation_version": final["activation_version"],
        },
        "KNOWLEDGE_BUILD_REQUIRED",
    )
    _, turn, _ = await source_turn(h, native=True, message_text="What should I prepare?")
    worker, fake = application(h, embeddings)
    await run_turn(h, worker, turn)
    assert len(fake.requests) == 1
    assert fake.views[0]["search"]["status"] == "EMPTY"
    assert fake.views[0]["search"]["fragments"] == []
    assert private_text not in json.dumps(fake.views[0])
    assert len(embeddings.requests) == posts
    assert (
        await query(
            h,
            "SELECT to_jsonb(c) AS row FROM platform.knowledge_embedding_calls c WHERE workspace_id=:w ORDER BY id",
            w=A,
        )
    ) == calls


async def test_fragment_reaches_reply_and_durable_refs_contain_no_text(search_pg):
    h = search_pg
    text = "Owner confirmed: bring a synthetic drawing."
    published, state, embeddings = await publication(h, [text])
    _, source, _ = await source_turn(h, native=True, message_text="Что принести на первую встречу?")
    worker, fake = application(h, embeddings, script=("tools", "reply"))
    claim, delivery = await run_turn(h, worker, source)
    assert len(fake.requests) == 2 and len(embeddings.requests) == 2
    assert (
        delivery["selected_kind"] == "reply"
        and delivery["search_pin"]["build_id"] == state["active_build_id"]
    )
    reply = await scalar(
        h,
        "SELECT m.text FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE o.id=:id",
        id=delivery["outbox_id"],
    )
    assert (
        reply == text
        and fake.views[0]["search"]["fragments"][0]["source_label"] == "Controlled owner source"
    )
    saved = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id))[0]
    assert text not in json.dumps(saved["search_refs"]) and text not in json.dumps(
        saved["read_audit"]
    )
    assert (
        saved["search_refs"]["references"][0]["sha256"]
        == fake.views[0]["search"]["fragments"][0]["sha256"]
    )
    receipt = await worker.ai.database.replay(claim, worker.ai.config)
    assert (
        type(receipt) is SearchRuntimeReceipt
        and receipt.search_refs.model_dump(mode="json") == saved["search_refs"]
    )
    send = await claim_job(h, delivery["send_job_id"])
    await worker.execute(send)
    assert h.adapter.calls == h.adapter.effects == 1
    await worker.execute(claim)
    assert len(fake.requests) == 2 and len(embeddings.requests) == 2 and h.adapter.effects == 1


@pytest.mark.parametrize("mode", ["vector", "keyword", "empty", "unpublished"])
async def test_exact_vector_and_keyword_paths_with_honest_empty(search_pg, mode):
    h = search_pg
    if mode == "unpublished":
        from test_m5_knowledge_postgres import publish_configuration

        await publish_configuration(h)
        embeddings = ControlledEmbeddings()
        expected = "NO_ACTIVE_BUILD"
    else:
        sources = ["orchid owner preparation", "different ceramics source"]
        embeddings = ControlledEmbeddings(
            choose=lambda value: vector(0 if "orchid" in value else 1)
        )
        await publication(h, sources, embeddings)
        if mode == "vector":
            question = "Какие материалы взять на первую встречу?"
            embeddings.choose = lambda value: vector()
        else:
            question = "orchid" if mode == "keyword" else "unseenword"
            embeddings.choose = lambda value: vector(2)
        expected = "NO_MATCH" if mode == "empty" else None
    question = locals().get("question", "Какие сведения опубликованы?")
    _, source, _ = await source_turn(h, native=True, message_text=question)
    worker, fake = application(h, embeddings)
    _, delivery = await run_turn(h, worker, source)
    assert len(fake.requests) == 1 and delivery["selected_kind"] == "reply"
    search = fake.views[0]["search"]
    if expected:
        assert (
            search["status"] == "EMPTY"
            and search["reason_code"] == expected
            and search["fragments"] == []
        )
    else:
        assert search["status"] == "RESULTS" and len(search["fragments"]) == 1
        assert search["fragments"][0]["text"] == "orchid owner preparation"
    queries = [r for r in embeddings.requests if json.loads(r.content)["input"] == [question]]
    assert len(queries) == (0 if mode == "unpublished" else 1)


async def test_claim_conflict_checks_siblings_before_top_four_and_forces_owner_handoff(search_pg):
    h = search_pg
    sources = [
        {"text": f"Statement {i} for labelled preparation.", "claim_key": "preparation"}
        for i in range(6)
    ]
    await publication(h, sources)
    embeddings = ControlledEmbeddings()
    _, source, _ = await source_turn(h, native=True, message_text="Preparation question")
    worker, fake = application(h, embeddings)
    _, delivery = await run_turn(h, worker, source)
    assert delivery["selected_kind"] == "handoff" and delivery["outbox_id"] is None
    assert len(fake.requests) == 1 and len(embeddings.requests) == 1
    search = fake.views[0]["search"]
    assert search["status"] == "CONFLICT" and search["fragments"] == []
    assert (
        len(search["conflicts"][0]["revision_ids"]) == 6 and delivery["escalation_id"] is not None
    )


async def test_four_index_batches_are_separately_committed_and_bounded(search_pg):
    h = search_pg
    _, state, embeddings = await publication(h, ["x" * 2048 for _ in range(8)])
    build = next(b for b in state["builds"] if b["build_id"] == state["active_build_id"])
    assert build["state"] == "READY" and build["chunk_count"] == 32
    assert (
        build["calls_reserved"] == build["calls_completed"] == 4 and len(embeddings.requests) == 4
    )
    assert all(
        len(json.loads(r.content)["input"]) == 8 and len(r.content) <= 8192
        for r in embeddings.requests
    )
    calls = await query(
        h,
        "SELECT state,reserved_cost,outcome,applied_at FROM platform.knowledge_embedding_calls WHERE workspace_id=:ws",
        ws=A,
    )
    assert len(calls) == 4 and all(
        c["state"] == "SUCCESS" and c["applied_at"] is not None and "vectors" not in c["outcome"]
        for c in calls
    )
    assert sum(c["reserved_cost"] for c in calls) == Decimal("0.32")


@pytest.mark.parametrize("boundary", ["MODEL", "READ", "FOLLOWUP", "CANDIDATE", "COMMIT"])
async def test_source_revocation_blocks_each_guarded_boundary(search_pg, boundary, monkeypatch):
    h = search_pg
    _, state, _ = await publication(h, ["Authorized source before revocation."])
    source_state = state["sources"][0]

    async def revoke():
        await knowledge_command(
            h,
            "KNOWLEDGE_REVOKE",
            {
                "schema_version": 1,
                "source_id": source_state["source_id"],
                "expected_source_version": source_state["source_version"],
                "expected_activation_version": state["activation_version"],
            },
        )

    embeddings = ControlledEmbeddings()
    _, source, _ = await source_turn(h, native=True, message_text="Preparation")
    script = ("tools", "reply") if boundary in {"READ", "FOLLOWUP"} else ("reply",)
    worker, fake = application(h, embeddings, script=script, wait=boundary in {"READ", "CANDIDATE"})
    original = worker.ai.database._command

    async def command(claim, operation, **payload):
        if boundary == "COMMIT" and operation == "COMMIT":
            await revoke()
        result = await original(claim, operation, **payload)
        if boundary == "FOLLOWUP" and operation == "READ":
            await revoke()
        return result

    monkeypatch.setattr(worker.ai.database, "_command", command)
    if boundary == "MODEL":
        query_method = worker.ai.database.query

        async def query_then_revoke(claim, run):
            result = await query_method(claim, run)
            await revoke()
            return result

        monkeypatch.setattr(worker.ai.database, "query", query_then_revoke)
    await worker.execute(source)
    enrolled = await enrollment(h, source)
    claim = await h.kernel.claim_job("search-test-ai", ai=True)
    assert claim is not None and claim.job_id == enrolled["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        if fake.wait:
            await asyncio.wait_for(fake.started.wait(), 5)
            await revoke()
            fake.release.set()
        await asyncio.wait_for(task, 10)
    finally:
        fake.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    current = await enrollment(h, source)
    assert current["selected_kind"] is current["outbox_id"] is None
    assert len(fake.requests) == (0 if boundary == "MODEL" else 1)
    saved = (
        await query(
            h,
            "SELECT calls_used,reads_used,result FROM platform.ai_runs WHERE job_id=:id",
            id=claim.job_id,
        )
    )[0]
    assert saved["result"] is None and saved["reads_used"] == (1 if boundary == "FOLLOWUP" else 0)
    assert len(embeddings.requests) == 1 and h.adapter.calls == 0


async def test_future_visibility_of_unselected_source_invalidates_same_activation_pin(search_pg):
    h = search_pg
    transition = datetime.now(UTC) + timedelta(seconds=6)
    later = transition.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    _, state, _ = await publication(
        h,
        [
            "Visible preparation explanation.",
            {"text": "Future unrelated ceramics.", "effective_from": later},
        ],
    )
    _, source, _ = await source_turn(h, native=True, message_text="Preparation")
    embeddings = ControlledEmbeddings()
    worker, fake = application(h, embeddings, wait=True)
    await worker.execute(source)
    enrolled = await enrollment(h, source)
    claim = await h.kernel.claim_job("search-test-ai", ai=True)
    assert claim is not None and claim.job_id == enrolled["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        await asyncio.wait_for(fake.started.wait(), 5)
        run = (
            await query(
                h, "SELECT search_pin FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id
            )
        )[0]
        assert run["search_pin"]["next_transition_at"] == later
        await asyncio.sleep(max(0, (transition - datetime.now(UTC)).total_seconds()) + 0.03)
        fake.release.set()
        await asyncio.wait_for(task, 10)
    finally:
        fake.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert (await knowledge_state(h))["activation_version"] == state["activation_version"]
    assert (await enrollment(h, source))["outbox_id"] is None and len(fake.requests) == 1


async def test_human_takeover_during_query_records_cost_without_applying_or_calling_model(
    search_pg,
):
    h = search_pg
    await publication(h, ["Confirmed preparation."])
    cid, source, _ = await source_turn(h, native=True, message_text="Preparation")

    async def hook(request, body):
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        await owner(h, cid, "TAKEOVER")

    embeddings = ControlledEmbeddings(hook=hook)
    worker, fake = application(h, embeddings)
    _, delivery = await run_turn(h, worker, source)
    calls = await query(
        h,
        "SELECT state,outcome,applied_at FROM platform.knowledge_embedding_calls WHERE kind='QUERY'",
    )
    assert len(calls) == 1 and calls[0]["state"] == "SUCCESS" and calls[0]["applied_at"] is None
    assert calls[0]["outcome"]["cost"]["amount"] == "0.000001"
    assert (
        fake.requests == [] and delivery["selected_kind"] is None and len(embeddings.requests) == 1
    )


@pytest.mark.parametrize("failure", ["unknown", "invalid"])
async def test_failed_query_and_fresh_process_never_resend_or_generate_reply(search_pg, failure):
    h = search_pg
    await publication(h, ["Confirmed preparation."])
    _, source, _ = await source_turn(h, native=True, message_text="Preparation")
    embeddings = ControlledEmbeddings(
        failure=failure == "unknown", choose=lambda value: [0.0] * 1536
    )
    worker, fake = application(h, embeddings)
    claim, delivery = await run_turn(h, worker, source)
    assert (
        len(embeddings.requests) == 1 and fake.requests == [] and delivery["selected_kind"] is None
    )
    calls = await query(
        h, "SELECT state,outcome FROM platform.knowledge_embedding_calls WHERE kind='QUERY'"
    )
    assert calls[0]["state"] == ("UNKNOWN" if failure == "unknown" else "ERROR")
    assert "completion_tokens" not in calls[0]["outcome"]["usage"]
    fresh, unused = application(h, embeddings)
    await fresh.execute(claim)
    await fresh.execute(source)
    assert len(embeddings.requests) == 1 and unused.requests == [] and h.adapter.calls == 0


async def test_actual_query_profile_dimensions_and_zero_norm_are_rejected(search_pg):
    h = search_pg
    await publication(h, ["Confirmed preparation."])
    _, source, _ = await source_turn(h, native=True, message_text="Preparation")
    embeddings = ControlledEmbeddings()
    worker, _ = application(h, embeddings)
    await worker.execute(source)
    enrolled = await enrollment(h, source)
    claim = await h.kernel.claim_job("search-test-ai", ai=True)
    assert claim is not None and claim.job_id == enrolled["job_id"]
    run = await worker.ai.database.prepare(
        claim, worker.ai.config, deadline=datetime.now(UTC) + timedelta(seconds=60)
    )
    assert type(run) is PreparedSearchRun
    with pytest.raises(MessagingError) as rejected:
        async with h.kernel.admit_job(claim.job_id, claim.claim_token) as u:
            await u.knowledge_query_reserve(
                run.run_id, run.search_pin.model_dump(mode="json") | {"profile_id": "other_profile"}
            )
    assert rejected.value.code == Code.AI_STALE
    async with h.kernel.admit_job(claim.job_id, claim.claim_token) as u:
        reservation = await u.knowledge_query_reserve(
            run.run_id, run.search_pin.model_dump(mode="json")
        )
    outcome = await embeddings.client.complete(
        reservation["wire"],
        deadline=datetime.fromisoformat(reservation["deadline"]),
        wire_sha256=reservation["wire_sha256"],
    )
    call, ticket = UUID(reservation["call_id"]), UUID(reservation["ticket"])
    await h.kernel.complete_embedding(call, ticket, outcome)
    for bad in ([[1.0]], [[0.0] * 1536]):
        with pytest.raises(DBAPIError) as invalid:
            async with h.kernel.admit_job(claim.job_id, claim.claim_token) as u:
                await u.knowledge_query_apply(run.run_id, call, ticket, bad)
        assert invalid.value.orig.diag.message_primary == "INVALID_VECTOR"
    assert len(embeddings.requests) == 1
    async with h.kernel.admit_job(claim.job_id, claim.claim_token) as u:
        projection = await u.knowledge_query_apply(run.run_id, call, ticket, outcome["vectors"])
    assert projection["status"] == "RESULTS"


async def test_source_revocation_before_send_and_unknown_after_send_keep_no_resend(
    search_pg, tmp_path
):
    h = search_pg
    _, state, _ = await publication(h, ["Preparation for guarded send."])
    _, source, _ = await source_turn(h, native=True, message_text="Preparation")
    embeddings = ControlledEmbeddings()
    worker, fake = application(h, embeddings)
    claim, delivery = await run_turn(h, worker, source)
    s = state["sources"][0]
    await knowledge_command(
        h,
        "KNOWLEDGE_REVOKE",
        {
            "schema_version": 1,
            "source_id": s["source_id"],
            "expected_source_version": s["source_version"],
            "expected_activation_version": state["activation_version"],
        },
    )
    send = await claim_job(h, delivery["send_job_id"])
    await worker.execute(send)
    assert h.adapter.calls == 0
    # A new current publication may generate a new reply, but an UNKNOWN external
    # send is immutable and neither publication changes nor restart resend it.
    _, state, _ = await publication(h, ["New current preparation."])
    _, second, _ = await source_turn(h, native=True, message_text="Preparation two")
    transport = ControlledAdapter(
        environment="TEST", ledger=tmp_path / "unknown.jsonl", outcome=OutcomeKind.UNKNOWN
    )
    worker2, fake2 = application(h, embeddings, adapter=transport)
    claim2, d2 = await run_turn(h, worker2, second)
    await worker2.execute(await claim_job(h, d2["send_job_id"]))
    assert transport.calls == transport.effects == 1
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d2["outbox_id"])
        == "UNKNOWN"
    )
    s = next(s for s in state["sources"] if s["state"] == "CONFIRMED")
    await knowledge_command(
        h,
        "KNOWLEDGE_REVOKE",
        {
            "schema_version": 1,
            "source_id": s["source_id"],
            "expected_source_version": s["source_version"],
            "expected_activation_version": state["activation_version"],
        },
    )
    await worker2.execute(claim2)
    await worker2.execute(second)
    await h.kernel.recover_expired()
    assert transport.calls == 1 and len(fake2.requests) == 1 and len(fake.requests) == 1


@pytest.mark.parametrize("change", ["OWNER", "input", "native", "observation"])
async def test_existing_owner_reconciliation_and_observation_barriers_remain_effective(
    search_pg, change
):
    h = search_pg
    _, state, _ = await publication(h, ["Current preparation source."])
    cid, source, scope = await source_turn(
        h,
        native=True,
        telegram=change == "observation",
        **({} if change == "observation" else {"message_text": "Preparation"}),
    )
    embeddings = ControlledEmbeddings()
    worker, fake = application(h, embeddings, wait=True)
    await worker.execute(source)
    enrolled = await enrollment(h, source)
    claim = await h.kernel.claim_job("search-original-guards", ai=True)
    assert claim is not None and claim.job_id == enrolled["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        await asyncio.wait_for(fake.started.wait(), 5)
        if change == "OWNER":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET status='REVOKED',version=version+1 WHERE workspace_id=:ws AND user_account_id=:u RETURNING version",
                ws=A,
                u=UA,
            )
        elif change == "input":
            await incoming(h, next(COUNTER), **scope)
        elif change == "observation":
            await incoming(
                h,
                next(COUNTER),
                **(scope | {"sender": OWNER}),
                process=False,
                value="New native owner agreement",
            )
        else:
            await owner(h, cid, "TAKEOVER")
            await reconcile(h, cid, value="Revised owner agreement")
            await owner(h, cid)
        fake.release.set()
        await asyncio.wait_for(task, 10)
        saved = (
            await query(
                h,
                "SELECT result,search_pin FROM platform.ai_runs WHERE job_id=:id",
                id=claim.job_id,
            )
        )[0]
        assert saved["result"] is None and (await enrollment(h, source))["selected_kind"] is None
        assert saved["search_pin"]["release_id"] == state["release_id"] and len(fake.requests) == 1
        assert len(embeddings.requests) == 1 and h.adapter.calls == 0
    finally:
        fake.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if change == "OWNER":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET status='ACTIVE',version=version+1 WHERE workspace_id=:ws AND user_account_id=:u RETURNING version",
                ws=A,
                u=UA,
            )


async def test_same_request_completion_survives_restart_but_other_client_claim_cannot_read_it(
    search_pg,
):
    h = search_pg
    await publication(h, ["Shared business preparation."])
    embeddings = ControlledEmbeddings()
    _, first, _ = await source_turn(h, native=True, message_text="PRIVATE_CLIENT_ONE")
    worker, _ = application(h, embeddings)
    await worker.execute(first)
    d1 = await enrollment(h, first)
    claim1 = await h.kernel.claim_job("query-before-process-exit", ai=True)
    assert claim1 is not None and claim1.job_id == d1["job_id"]
    run = await worker.ai.database.prepare(
        claim1, worker.ai.config, deadline=datetime.now(UTC) + timedelta(seconds=60)
    )
    result = await worker.ai.database.query(claim1, run)
    assert result.status == "RESULTS" and len(embeddings.requests) == 1
    _, second, _ = await source_turn(h, native=True, message_text="PRIVATE_CLIENT_TWO")
    await worker.execute(second)
    d2 = await enrollment(h, second)
    claim2 = await h.kernel.claim_job("other-client-read", ai=True)
    assert claim2 is not None and claim2.job_id == d2["job_id"]
    with pytest.raises(MessagingError) as rejected:
        async with h.kernel.admit_job(claim2.job_id, claim2.claim_token) as u:
            await u.knowledge_runtime_read(run.run_id, run.search_pin.model_dump(mode="json"))
    assert rejected.value.code == Code.NOT_ALLOWED
    fresh, fake1 = application(h, embeddings)
    await fresh.execute(claim1)
    assert len(embeddings.requests) == 1 and len(fake1.requests) == 1
    assert "PRIVATE_CLIENT_TWO" not in fake1.requests[0].input_json()
    fresh2, fake2 = application(h, embeddings)
    await fresh2.execute(claim2)
    assert len(embeddings.requests) == 2 and len(fake2.requests) == 1
    assert "PRIVATE_CLIENT_ONE" not in fake2.requests[0].input_json()
    assert fake1.views[0]["search"]["fragments"] == fake2.views[0]["search"]["fragments"]


async def test_cross_business_and_workspace_sources_never_reach_current_query(search_pg):
    h = search_pg
    await publication(h, ["PUBLIC_BUSINESS_A"])
    await publication(h, ["PRIVATE_OTHER_BUSINESS"], business=BA2)
    await publication(h, ["PRIVATE_OTHER_WORKSPACE"], business=BB, workspace=B, actor=UB)
    _, source, _ = await source_turn(h, native=True, message_text="Question for this business")
    embeddings = ControlledEmbeddings()
    worker, fake = application(h, embeddings)
    await run_turn(h, worker, source)
    wire = fake.requests[0].input_json()
    assert (
        "PUBLIC_BUSINESS_A" in wire
        and "PRIVATE_OTHER_BUSINESS" not in wire
        and "PRIVATE_OTHER_WORKSPACE" not in wire
    )
    assert len(fake.views[0]["search"]["fragments"]) == 1 and len(embeddings.requests) == 1


async def test_expired_source_is_not_read_and_does_not_trigger_query_post(search_pg):
    h = search_pg
    until = datetime.now(UTC) + timedelta(seconds=4)
    await publication(
        h,
        [
            {
                "text": "EXPIRED_SOURCE_MARKER",
                "effective_until": until.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            }
        ],
    )
    _, source, _ = await source_turn(h, native=True, message_text="Preparation")
    await asyncio.sleep(max(0, (until - datetime.now(UTC)).total_seconds()) + 0.02)
    embeddings = ControlledEmbeddings()
    worker, fake = application(h, embeddings)
    await run_turn(h, worker, source)
    assert len(embeddings.requests) == 0 and len(fake.requests) == 1
    assert (
        fake.views[0]["search"]["status"] == "EMPTY"
        and fake.views[0]["search"]["reason_code"] == "NO_ELIGIBLE_SOURCE"
    )
    assert "EXPIRED_SOURCE_MARKER" not in fake.requests[0].input_json()


async def test_source_change_during_reply_rights_http_blocks_commit(search_pg):
    h = search_pg
    _, state, _ = await publication(h, ["Published before rights refresh."])
    _, source, _ = await source_turn(h, telegram=True)
    await scalar(
        h,
        "UPDATE platform.telegram_connection_state SET observed_at=clock_timestamp()-interval '31 seconds' WHERE workspace_id=:ws AND connection_id=:id RETURNING connection_id",
        ws=A,
        id=h.telegram_connection,
    )
    requests = []

    async def handler(request):
        requests.append(request.url.path.rsplit("/", 1)[-1])
        assert requests == ["getBusinessConnection"]
        s = state["sources"][0]
        await knowledge_command(
            h,
            "KNOWLEDGE_REVOKE",
            {
                "schema_version": 1,
                "source_id": s["source_id"],
                "expected_source_version": s["source_version"],
                "expected_activation_version": state["activation_version"],
            },
        )
        return connection()

    client = telegram(handler)
    try:
        embeddings = ControlledEmbeddings()
        worker, fake = application(h, embeddings, telegram=client)
        _, delivery = await run_turn(h, worker, source)
        assert (
            len(fake.requests) == 1
            and len(embeddings.requests) == 1
            and requests == ["getBusinessConnection"]
        )
        assert delivery["selected_kind"] is delivery["outbox_id"] is None
    finally:
        await client.aclose()


async def test_publish_revoke_race_serializes_and_deleted_text_cannot_be_rolled_back(search_pg):
    h = search_pg
    _, state, embeddings = await publication(h, ["Canonical text to delete after race."])
    s = state["sources"][0]
    b = next(b for b in state["builds"] if b["build_id"] == state["active_build_id"])
    activation = state["activation_version"]
    results = await asyncio.gather(
        knowledge_command(
            h,
            "KNOWLEDGE_PUBLISH",
            {
                "schema_version": 1,
                "expected_draft_version": "1",
                "expected_activation_version": activation,
                "build_id": b["build_id"],
                "expected_build_version": b["build_version"],
            },
        ),
        knowledge_command(
            h,
            "KNOWLEDGE_REVOKE",
            {
                "schema_version": 1,
                "source_id": s["source_id"],
                "expected_source_version": s["source_version"],
                "expected_activation_version": activation,
            },
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    denied = next(r for r in results if isinstance(r, Exception))
    assert isinstance(denied, DBAPIError) and denied.orig.diag.message_primary == "STALE_STATE"
    current = await knowledge_state(h)
    source = current["sources"][0]
    assert current["activation_version"] == "2" and len(embeddings.requests) == 1
    await knowledge_command(
        h,
        "KNOWLEDGE_DELETE",
        {
            "schema_version": 1,
            "source_id": source["source_id"],
            "expected_source_version": source["source_version"],
            "expected_activation_version": "2",
        },
    )
    deleted = await knowledge_state(h)
    assert deleted["sources"] == []
    for table in ("knowledge_revisions", "knowledge_chunks", "knowledge_build_chunks"):
        assert (
            await scalar(
                h, "SELECT count(*) FROM platform." + table + " WHERE workspace_id=:ws", ws=A
            )
            == 0
        )
    with pytest.raises(DBAPIError) as refused:
        await knowledge_command(
            h,
            "KNOWLEDGE_ROLLBACK",
            {
                "schema_version": 1,
                "expected_activation_version": deleted["activation_version"],
                "release_id": state["release_id"],
            },
        )
    assert refused.value.orig.diag.message_primary == "ROLLBACK_NOT_ALLOWED"


async def test_query_utf8_limit_rejects_before_reservation_or_http(search_pg):
    h = search_pg
    await publication(h, ["Confirmed preparation."])
    _, source, _ = await source_turn(h, native=True, message_text="я" * 513)
    embeddings = ControlledEmbeddings()
    worker, fake = application(h, embeddings)
    _, delivery = await run_turn(h, worker, source)
    assert embeddings.requests == [] and fake.requests == [] and delivery["selected_kind"] is None
    assert (
        await scalar(
            h, "SELECT count(*) FROM platform.knowledge_embedding_calls WHERE kind='QUERY'"
        )
        == 0
    )
