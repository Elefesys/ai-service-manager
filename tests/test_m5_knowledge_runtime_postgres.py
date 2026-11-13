"""Real runtime-role PG/worker path; fake model reads the actual projected facts."""

import asyncio
import json
from uuid import uuid4

import pytest
from asm.ai.fake import FakeAdapter
from asm.foundation import RuntimeDatabase, Settings
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.models import OutcomeKind
from asm.tenancy import AuthenticatedAccount
from m5_configuration_fixtures import configuration_bundle
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, incoming, reconcile, scalar
from test_m4_delivery_postgres import application, enrollment, run_turn, source_turn
from test_m4_reply_rights_postgres import connection, telegram
from test_m4_runtime_postgres import COUNTER, owner
from test_m4_runtime_postgres import pg as pg
from test_m5_knowledge_postgres import knowledge_pg as knowledge_pg
from test_tenancy_postgres import BA, UA, A

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


async def write_configuration(h, answer, *, publish=True):
    """The ordinary owner capability; publication is not a test-only database UPDATE."""
    bundle = configuration_bundle()
    bundle["faqs"][0].update(question="Synthetic preparation question", answer=answer)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        state = await unit.configuration_owner_read(BA)
        result = await unit.configuration_command(
            BA,
            "EDIT",
            str(uuid4()),
            {"expected_draft_version": state["draft_version"], "bundle": bundle},
        )
        if publish:
            result = await unit.configuration_command(
                BA,
                "PUBLISH",
                str(uuid4()),
                {
                    "expected_draft_version": result["result"]["draft_version"],
                    "expected_activation_version": state["activation_version"],
                },
            )
        return result


class ProjectedAnswer(FakeAdapter):
    """A deterministic synthetic model echoes one FAQ present in its actual input.

    This exercises publication/data plumbing and effects, not LLM semantic quality.
    """

    def __init__(self, route, script=("reply",)):
        super().__init__(route, script)
        self.business_views = []
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.wait = False

    async def complete(self, request):
        response = await super().complete(request)
        data = [json.loads(m.text) for m in request.request.messages if m.role == "context"]
        business = next(v for v in data if v.get("revision") == "business_knowledge_v1")
        self.business_views.append(business)
        self.started.set()
        if self.wait:
            await self.release.wait()
        if response.kind == "TOOLS":
            return response
        assert business["status"] == "PUBLISHED" and business["faqs"]
        answer = business["faqs"][0]["fact"]["answer"]
        return response.model_copy(
            update={"output_json": json.dumps({"kind": "reply", "text": answer, "reason": None})}
        )


async def model_run(h, source, *, script=("reply",), transport=None):
    worker, _ = application(h, adapter=transport)
    fake = ProjectedAnswer(worker.ai.config.route, script)
    worker.ai.model = lambda: fake
    claim, delivery = await run_turn(h, worker, source)
    return worker, fake, claim, delivery


async def outbound_text(h, delivery):
    return await scalar(
        h,
        "SELECT m.text FROM app.outbox_events o JOIN app.messages m ON (m.workspace_id,m.id)=(o.workspace_id,o.message_id) WHERE o.id=:id",
        id=delivery["outbox_id"],
    )


async def test_current0019_application_readiness_and_published_faq_effect(knowledge_pg, tmp_path):
    h = knowledge_pg
    current = RuntimeDatabase(Settings())
    try:
        await current.check()
    finally:
        await current.close()
    publication = await write_configuration(h, "Owner published preparation alpha.")
    await write_configuration(h, "PRIVATE UNPUBLISHED DRAFT MUST NOT REACH MODEL", publish=False)
    _, source, _ = await source_turn(h, native=True, message_text="Synthetic preparation question")
    transport = ControlledAdapter(environment="TEST", ledger=tmp_path / "effect.jsonl")
    worker, fake, claim, delivery = await model_run(h, source, transport=transport)
    assert len(fake.requests) == 1 and delivery["selected_kind"] == "reply"
    assert await outbound_text(h, delivery) == "Owner published preparation alpha."
    saved = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id))[0]
    assert saved["knowledge_pin"]["release_id"] == publication["result"]["release_id"]
    assert saved["knowledge_pin"] == delivery["knowledge_pin"]
    wire = fake.requests[0].input_json()
    assert "PRIVATE UNPUBLISHED" not in wire
    assert "OWNER_PUBLISHED_CONFIGURATION" in wire
    assert "Synthetic owner-confirmed instruction" in wire
    assert "MIN_AGE" in wire
    send = await claim_job(h, delivery["send_job_id"])
    await worker.execute(send)
    assert transport.calls == transport.effects == 1
    await worker.execute(claim)
    assert len(fake.requests) == 1 and transport.effects == 1
    assert (
        await scalar(
            h, "SELECT status FROM app.outbox_events WHERE id=:id", id=delivery["outbox_id"]
        )
        == "SENT"
    )


async def test_clients_share_business_publication_without_private_context_leak(knowledge_pg):
    h = knowledge_pg
    await write_configuration(h, "Shared owner-published FAQ.")
    _, first, _ = await source_turn(
        h, native=True, message_text="Synthetic private-client-one question"
    )
    _, fake_a, _, delivery_a = await model_run(h, first)
    _, second, _ = await source_turn(
        h, native=True, message_text="Synthetic private-client-two question"
    )
    _, fake_b, _, delivery_b = await model_run(h, second)
    assert fake_a.business_views == fake_b.business_views
    assert "private-client-two" not in fake_a.requests[0].input_json()
    assert "private-client-one" not in fake_b.requests[0].input_json()
    assert (
        await outbound_text(h, delivery_a)
        == await outbound_text(h, delivery_b)
        == "Shared owner-published FAQ."
    )


@pytest.mark.parametrize("boundary", ["CANDIDATE", "READ", "FOLLOWUP"])
async def test_publication_during_model_or_read_blocks_remaining_calls_and_selection(
    knowledge_pg, boundary, monkeypatch
):
    h = knowledge_pg
    await write_configuration(h, "Old authorized publication.")
    _, source, _ = await source_turn(h, native=True)
    worker, _ = application(h)
    fake = ProjectedAnswer(
        worker.ai.config.route, ("reply",) if boundary == "CANDIDATE" else ("tools", "reply")
    )
    worker.ai.model = lambda: fake
    reads = 0
    original = worker.ai.database._command

    async def command(claim, operation, **payload):
        nonlocal reads
        result = await original(claim, operation, **payload)
        if operation == "READ":
            reads += 1
            if boundary == "FOLLOWUP":
                await write_configuration(h, "New publication after READ.")
        return result

    monkeypatch.setattr(worker.ai.database, "_command", command)
    fake.wait = boundary != "FOLLOWUP"
    await worker.execute(source)
    delivery = await enrollment(h, source)
    claim = await h.kernel.claim_job("knowledge-boundary", ai=True)
    assert claim is not None and claim.job_id == delivery["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        if fake.wait:
            await asyncio.wait_for(fake.started.wait(), 5)
            await write_configuration(h, "New publication during model await.")
            fake.release.set()
        await asyncio.wait_for(task, 10)
    finally:
        fake.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    saved = await enrollment(h, source)
    assert len(fake.requests) == 1 and reads == (1 if boundary == "FOLLOWUP" else 0)
    assert saved["selected_kind"] is saved["outbox_id"] is None
    assert (
        await scalar(h, "SELECT result FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id)
        is None
    )


async def test_publication_inside_rights_http_blocks_commit_before_outbox(knowledge_pg):
    h = knowledge_pg
    await write_configuration(h, "Authorized before rights refresh.")
    _, source, _ = await source_turn(h, telegram=True)
    # Negative TTL fault forces the ordinary pre-COMMIT observation path.
    await scalar(
        h,
        "UPDATE platform.telegram_connection_state SET observed_at=clock_timestamp()-interval '31 seconds' WHERE workspace_id=:ws AND connection_id=:id RETURNING connection_id",
        ws=A,
        id=h.telegram_connection,
    )
    requests = []

    async def handler(request):
        method = request.url.path.rsplit("/", 1)[-1]
        requests.append(method)
        assert method == "getBusinessConnection"
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        await write_configuration(h, "Publication won during rights HTTP.")
        return connection()

    client = telegram(handler)
    try:
        worker, _ = application(h, telegram=client)
        fake = ProjectedAnswer(worker.ai.config.route)
        worker.ai.model = lambda: fake
        _, delivery = await run_turn(h, worker, source)
        assert len(fake.requests) == 1 and requests == ["getBusinessConnection"]
        assert delivery["selected_kind"] is delivery["outbox_id"] is None
    finally:
        await client.aclose()


async def test_unknown_transport_after_admission_is_not_resent_after_publication(
    knowledge_pg, tmp_path
):
    h = knowledge_pg
    await write_configuration(h, "Published at admitted send.")
    _, source, _ = await source_turn(h, native=True)
    transport = ControlledAdapter(
        environment="TEST", ledger=tmp_path / "unknown.jsonl", outcome=OutcomeKind.UNKNOWN
    )
    worker, fake, claim, delivery = await model_run(h, source, transport=transport)
    send = await claim_job(h, delivery["send_job_id"])
    await worker.execute(send)
    assert transport.calls == transport.effects == 1
    assert (
        await scalar(
            h, "SELECT status FROM app.outbox_events WHERE id=:id", id=delivery["outbox_id"]
        )
        == "UNKNOWN"
    )
    await write_configuration(h, "New publication cannot authorize resend.")
    await worker.execute(claim)
    await h.kernel.recover_expired()
    assert len(fake.requests) == 1 and transport.calls == transport.effects == 1


@pytest.mark.parametrize("change", ["HUMAN", "revoke", "native", "input"])
async def test_valid_publication_pin_preserves_owner_and_current_input_guards(knowledge_pg, change):
    h = knowledge_pg
    publication = await write_configuration(
        h, "Published facts remain current during control change."
    )
    cid, source, scope = await source_turn(h, native=True)
    worker, _ = application(h)
    fake = ProjectedAnswer(worker.ai.config.route)
    fake.wait = True
    worker.ai.model = lambda: fake
    await worker.execute(source)
    delivery = await enrollment(h, source)
    claim = await h.kernel.claim_job("knowledge-current-guard", ai=True)
    assert claim is not None and claim.job_id == delivery["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        await asyncio.wait_for(fake.started.wait(), 5)
        if change == "revoke":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET status='REVOKED',version=version+1 WHERE workspace_id=:ws AND user_account_id=:actor RETURNING version",
                ws=A,
                actor=UA,
            )
        elif change == "input":
            await incoming(h, next(COUNTER), **scope)
        else:
            await owner(h, cid, "TAKEOVER")
            if change == "native":
                await reconcile(h, cid, value="Reconciled new native agreement.")
                await owner(h, cid)
        fake.release.set()
        await asyncio.wait_for(task, 10)
        saved = await enrollment(h, source)
        row = (
            await query(
                h,
                "SELECT knowledge_pin,result FROM platform.ai_runs WHERE job_id=:id",
                id=claim.job_id,
            )
        )[0]
        assert row["knowledge_pin"]["release_id"] == publication["result"]["release_id"]
        assert row["result"] is saved["selected_kind"] is saved["outbox_id"] is None
        assert len(fake.requests) == 1
    finally:
        fake.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if change == "revoke":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET status='ACTIVE',version=version+1 WHERE workspace_id=:ws AND user_account_id=:actor RETURNING version",
                ws=A,
                actor=UA,
            )
