"""Actual PG/FETCH/v5 worker. Storage, model and provider wires are controlled.

Owner SQL assets never manufacture a Job or a client. Client media comes from
real synthetic ingress, FETCH lease, decode and committed private upload permit.
"""

import base64
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from asm.ai.contracts import PortfolioGatewayConfig
from asm.ai.database import PostgresPortfolioAuthority
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_contracts import PortfolioRuntimeReceipt
from asm.ai.runtime_settings import PortfolioRuntimeSettings
from asm.ai.vision import VisionClient, VisionPreprocessor
from asm.files.database import FileDatabase
from asm.files.provider import ControlledImageProvider
from asm.files.storage import ObjectInfo
from asm.files.transfer import FetchTransfer
from asm.foundation import create_worker
from m5_knowledge_search_fixtures import db as db
from m5_knowledge_search_fixtures import publication, wire_response
from m5_knowledge_search_fixtures import search_pg as search_pg
from m5_knowledge_search_fixtures import seeded as seeded
from m5_portfolio_fixtures import asset, call, command, session
from sqlalchemy import text
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import claim_job, incoming, reconcile, scalar
from test_m3_1_turns_postgres import seal
from test_m4_agent import config
from test_m4_delivery_postgres import run_turn
from test_m4_runtime_postgres import COUNTER, owner
from test_m5_knowledge_postgres import configuration_read
from test_m5_vision_pixels import body as vision_body
from test_m5_vision_pixels import source as source_pixels
from test_tenancy_postgres import BA, UA, A, B

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def bridge(h):
    return SimpleNamespace(
        runtime=h.runtime.engine, migrator=h.migrator, ws=A, actor=UA, business=BA
    )


class PrivateBytes:
    """Controlled byte store; no actual S3 assertion from this module."""

    def __init__(self):
        self.values, self.puts, self.gets = {}, 0, 0

    async def put(self, permit, data):
        self.puts += 1
        self.values[permit.storage_key] = (data, permit.manifest.mime_type)

    async def get(self, key):
        self.gets += 1
        return self.values[key][0]

    async def head(self, key):
        data, mime = self.values[key]
        return ObjectInfo(
            size_bytes=len(data),
            mime_type=mime,
            checksum_sha256=base64.b64encode(hashlib.sha256(data).digest()).decode(),
        )


@pytest_asyncio.fixture
async def portfolio_runtime_pg(search_pg):
    h = search_pg
    h.store = PrivateBytes()
    h.provider = ControlledImageProvider(environment="TEST")
    h.files = FileDatabase(h.kernel)
    h.transfer = FetchTransfer(h.files, h.kernel, h.provider, h.store)
    h.preprocessor = VisionPreprocessor()
    try:
        yield h
    finally:
        await h.transfer.close()
        await h.preprocessor.close()
        # All IDs belong to the outer owned A/B fixture. Remove new children
        # before that fixture's existing atomic cleanup; retain all constraints.
        async with h.migrator.begin() as c:
            params = {"a": A, "b": B}
            await c.execute(
                text(
                    "UPDATE platform.portfolio_items SET head_revision_id=NULL,confirmed_revision_id=NULL WHERE workspace_id IN (:a,:b)"
                ),
                params,
            )
            await c.execute(
                text(
                    "UPDATE platform.portfolio_assets SET accepted_version_id=NULL,pending_version_id=NULL WHERE workspace_id IN (:a,:b)"
                ),
                params,
            )
            tables = (
                "ai_deliveries",
                "ai_provider_calls",
                "knowledge_embedding_calls",
                "ai_runs",
                "portfolio_release_builds",
                "portfolio_build_items",
                "portfolio_builds",
                "portfolio_revisions",
                "portfolio_items",
                "vision_analyses",
                "portfolio_asset_versions",
                "portfolio_assets",
                "portfolio_ai_sessions",
            )
            statement = (
                "WITH "
                + ",".join(
                    f"d{i} AS (DELETE FROM platform.{name} WHERE workspace_id IN (:a,:b) RETURNING 1)"
                    for i, name in enumerate(tables)
                )
                + " SELECT "
                + "+".join(f"(SELECT count(*) FROM d{i})" for i in range(len(tables)))
            )
            await c.execute(text(statement), params)


async def source_image(h, *, caption="Synthetic flower reference"):
    number = next(COUNTER)
    scope = dict(chat_id=f"portfolio-{number}", sender_id=f"portfolio-user-{number}")
    _, _, cid = await incoming(h, number, text="Synthetic owner context", **scope)
    await reconcile(h, cid)
    await owner(h, cid)
    image = await add_photo(h, cid, scope, caption=caption)
    turn = (
        await query(
            h,
            "SELECT id,revision FROM app.conversation_turns WHERE conversation_id=:c AND state='COLLECTING' ORDER BY first_ingress_at DESC,id DESC LIMIT 1",
            c=cid,
        )
    )[0]
    sealed = await seal(h, turn["id"])
    assert sealed.code == "GROUPED"
    job = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE turn_id=:t AND turn_revision=:r AND step='TEST_CONSUME'",
        t=turn["id"],
        r=sealed.turn_revision,
    )
    return cid, await claim_job(h, job), scope, image


async def add_photo(h, cid, scope, *, caption="Synthetic replacement", raw=None):
    number = next(COUNTER)
    ref = f"portfolio-pixels-{number}"
    data = source_pixels() if raw is None else raw
    h.provider.register("bot-a", ref, data, content_type="text/plain", content_length=1)
    _, receipt, same = await incoming(h, number, image_file_id=ref, text=caption, **scope)
    assert same == cid
    file = (
        await query(h, "SELECT * FROM app.file_objects WHERE message_id=:m", m=receipt.message_id)
    )[0]
    fetch = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE' AND file_id=:f",
        f=file["id"],
    )
    await h.transfer.execute(await claim_job(h, fetch))
    saved = (await query(h, "SELECT * FROM app.file_objects WHERE id=:f", f=file["id"]))[0]
    assert saved["status"] == "READY" and saved["sha256"] == hashlib.sha256(data).hexdigest()
    return saved


async def admit(h, cid):
    return await call(
        bridge(h),
        "portfolio_session_admit",
        [
            BA,
            cid,
            {
                "profile_id": "SYNTHETIC_VISION_PORTFOLIO_V1",
                "execution": "CONTROLLED",
                "eligibility": "EVAL_ONLY",
                "max_calls": 4,
                "max_cost": "10",
                "duration_seconds": 900,
            },
        ],
    )


async def analyse(h, cid, *, behavior=None):
    admitted = await admit(h, cid)
    reserved = await call(
        bridge(h), "vision_client_reserve", [BA, cid, UUID(admitted["session_id"])]
    )
    assert reserved["status"] == "RESERVED"
    h.vision_posts = []

    async def transport(request):
        h.vision_posts.append(request)
        if behavior is not None:
            return await behavior(request)
        return wire_response(vision_body())

    client = VisionClient(httpx.MockTransport(transport))
    original = await h.store.get(reserved["storage_key"])
    from asm.files.models import ImageManifest

    pixels = await h.preprocessor.prepare(
        original, ImageManifest.model_validate(reserved["manifest"])
    )
    await call(
        bridge(h), "vision_authorize", [BA, UUID(reserved["analysis_id"]), UUID(reserved["ticket"])]
    )
    outcome = await client.complete(pixels, deadline=datetime.fromisoformat(reserved["deadline"]))
    async with h.kernel._transaction() as c:
        complete = (
            await c.execute(
                text("SELECT platform.vision_complete(:id,:ticket,CAST(:p AS jsonb))"),
                {
                    "id": UUID(reserved["analysis_id"]),
                    "ticket": UUID(reserved["ticket"]),
                    "p": json.dumps(outcome),
                },
            )
        ).scalar_one()
    if outcome["kind"] == "SUCCESS":
        applied = await call(
            bridge(h), "vision_apply", [BA, UUID(reserved["analysis_id"]), UUID(reserved["ticket"])]
        )
        assert applied["applied"]
    return reserved, complete, outcome


async def publish_portfolio(h, embeddings, *, empty=False):
    b = bridge(h)
    if not empty:
        a, _ = await asset(b)
        saved = (
            await command(
                b,
                "PORTFOLIO_SAVE",
                {
                    "item_id": None,
                    "expected_item_version": "0",
                    "asset_id": str(a["asset_id"]),
                    "description": "Owner confirmed flower work",
                    "attributes": {"subject": "flower", "styles": ["linework"], "placement": None},
                    "service_id": "consultation",
                    "analysis_id": None,
                },
            )
        )["result"]
        await command(
            b,
            "PORTFOLIO_CONFIRM",
            {
                "item_id": saved["item_id"],
                "expected_item_version": saved["item_version"],
                "revision_id": saved["revision_id"],
                "canonical_sha256": saved["canonical_sha256"],
                "confirm_my_work": True,
                "show_permission": True,
            },
        )
    state = await call(b, "portfolio_owner_read", [BA])
    built = (
        await command(
            b,
            "PORTFOLIO_BUILD_CREATE",
            {
                "expected_items_hash": state["items_hash"],
                "revision_ids": [] if empty else [saved["revision_id"]],
            },
        )
    )["result"]
    if not empty:
        r = await call(
            b, "portfolio_build_reserve", [BA, UUID(built["build_id"]), await session(b)]
        )
        outcome = await embeddings.client.complete(
            r["wire"], deadline=datetime.fromisoformat(r["deadline"]), wire_sha256=r["wire_sha256"]
        )
        complete = await h.kernel.complete_embedding(UUID(r["call_id"]), UUID(r["ticket"]), outcome)
        assert complete["state"] == "SUCCESS"
        await call(
            b,
            "portfolio_build_apply",
            [BA, UUID(r["call_id"]), UUID(r["ticket"]), outcome["vectors"]],
        )
    state = await call(b, "portfolio_owner_read", [BA])
    actual = next(x for x in state["builds"] if x["build_id"] == built["build_id"])
    assert actual["state"] == "READY"
    kb = state["active_knowledge_build_id"]
    kb_version = (
        None
        if kb is None
        else await scalar(
            h, "SELECT version::text FROM platform.knowledge_builds WHERE id=:id", id=UUID(kb)
        )
    )
    draft = await configuration_read(h)
    await command(
        b,
        "PORTFOLIO_PUBLISH",
        {
            "expected_draft_version": draft["draft_version"],
            "expected_activation_version": state["activation_version"],
            "knowledge_build_id": kb,
            "expected_knowledge_build_version": kb_version,
            "portfolio_build_id": built["build_id"],
            "expected_portfolio_build_version": actual["version"],
        },
    )
    return await call(b, "portfolio_owner_read", [BA])


class PortfolioAnswer(FakeAdapter):
    def __init__(self, route, script=("tools", "reply"), hook=None):
        super().__init__(route, script)
        self.views, self.hook = [], hook

    async def complete(self, request):
        response = await super().complete(request)
        self.views.append(
            next(
                json.loads(m.text)
                for m in request.request.messages
                if m.role == "context"
                and json.loads(m.text).get("revision") == "business_knowledge_v3"
            )
        )
        if self.hook is not None:
            await self.hook(len(self.views))
        return response


async def application(h, cid, embeddings, *, script=("tools", "reply"), hook=None, cost="5"):
    admitted = await admit(h, cid)
    cfg = PortfolioGatewayConfig.model_validate(
        config(
            duration_seconds=120,
            cost_budget=Decimal(cost),
            input_bytes=24576,
            output_tokens=512,
            total_tokens=66560,
        ).model_dump()
        | {"prompt_revision": "conversation_v5"}
    )
    fake = PortfolioAnswer(cfg.route, script, hook)
    client = await scalar(h, "SELECT client_id FROM app.conversations WHERE id=:c", c=cid)
    settings = PortfolioRuntimeSettings(
        session_id=UUID(admitted["session_id"]),
        workspace_id=A,
        business_id=BA,
        client_id=client,
        conversation_id=cid,
        data_profile="SYNTHETIC_VISION_PORTFOLIO_V1",
        expires_at=datetime.fromisoformat(admitted["expires_at"]),
        max_calls=4,
        max_cost=Decimal(10),
        config=cfg,
    )
    worker = create_worker(
        h.kernel,
        h.adapter,
        environment="TEST",
        portfolio_settings=settings,
        model=lambda: fake,
        ai_embeddings=embeddings.client,
    )
    return worker, fake


async def test_real_pixels_shared_query_kb_portfolio_read_receipt_and_send(portfolio_runtime_pg):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic owner preparation"])
    state = await publish_portfolio(h, embeddings)
    cid, source, _, image = await source_image(h)
    reserved, completed, outcome = await analyse(h, cid)
    assert completed["state"] == "SUCCESS" and outcome["kind"] == "SUCCESS"
    before = len(embeddings.requests)
    worker, fake = await application(h, cid, embeddings)
    claim, delivery = await run_turn(h, worker, source)
    assert len(fake.requests) == 2 and len(embeddings.requests) == before + 1
    assert (
        delivery["selected_kind"] == "reply"
        and delivery["portfolio_pin"]["build_id"] == state["active_portfolio_build_id"]
    )
    view = fake.views[0]
    assert view["search"]["status"] == view["portfolio"]["status"] == "RESULTS"
    assert view["analysis"]["result"]["scale"] == "UNKNOWN"
    saved = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id))[0]
    assert saved["media_pin"]["file_id"] == str(image["id"])
    assert saved["media_pin"]["analysis_id"] == reserved["analysis_id"]
    assert saved["cost_reserved"] >= Decimal("3.89") + Decimal("0.08") + Decimal("0.20")
    receipt = await worker.ai.database.replay(claim, worker.ai.config)
    assert type(receipt) is PortfolioRuntimeReceipt and receipt.portfolio_refs is not None
    assert "Owner confirmed flower work" not in json.dumps(saved["portfolio_refs"])
    send = await claim_job(h, delivery["send_job_id"])
    await worker.execute(send)
    assert h.adapter.effects == 1
    await worker.execute(claim)
    assert (
        len(fake.requests) == 2
        and len(embeddings.requests) == before + 1
        and len(h.vision_posts) == 1
    )


async def test_shared_query_unknown_survives_restart_without_second_post(portfolio_runtime_pg):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic owner source"])
    await publish_portfolio(h, embeddings)
    cid, source, _, _ = await source_image(h)
    await analyse(h, cid)
    embeddings.failure = True
    before = len(embeddings.requests)
    worker, fake = await application(h, cid, embeddings)
    claim, delivery = await run_turn(h, worker, source)
    assert (
        len(embeddings.requests) == before + 1
        and not fake.requests
        and delivery["selected_kind"] is None
    )
    calls = await query(
        h,
        "SELECT state,reserved_cost,outcome FROM platform.knowledge_embedding_calls WHERE run_id=(SELECT id FROM platform.ai_runs WHERE job_id=:id)",
        id=claim.job_id,
    )
    assert (
        len(calls) == 1
        and calls[0]["state"] == "UNKNOWN"
        and calls[0]["reserved_cost"] == Decimal("0.08")
    )
    restarted, _ = await application(h, cid, embeddings)
    await restarted.execute(claim)
    assert len(embeddings.requests) == before + 1 and not fake.requests


@pytest.mark.parametrize("change", ["owner_revoked", "human", "replacement", "revoke"])
async def test_changes_during_model_keep_accounting_but_deny_read_followup_and_candidate(
    portfolio_runtime_pg, change
):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic source"])
    state = await publish_portfolio(h, embeddings)
    cid, source, scope, _ = await source_image(h)
    await analyse(h, cid)

    async def changed(sequence):
        assert sequence == 1
        if change == "owner_revoked":
            await scalar(
                h,
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u RETURNING 1",
                w=A,
                u=UA,
            )
        elif change == "human":
            await owner(h, cid, "TAKEOVER")
        elif change == "replacement":
            await add_photo(h, cid, scope, raw=source_pixels(size=(72, 64)))
        else:
            item = state["items"][0]
            await command(
                bridge(h),
                "PORTFOLIO_REVOKE",
                {
                    "item_id": item["item_id"],
                    "expected_item_version": item["version"],
                    "expected_activation_version": state["activation_version"],
                },
            )

    worker, fake = await application(h, cid, embeddings, hook=changed)
    claim, delivery = await run_turn(h, worker, source)
    assert (
        len(fake.requests) == 1
        and delivery["selected_kind"] is None
        and delivery["outbox_id"] is None
    )
    saved = (
        await query(
            h,
            "SELECT r.calls_used,r.cost_reserved,(SELECT count(*) FROM platform.ai_provider_calls c WHERE c.run_id=r.id AND c.completed_at IS NOT NULL) AS completed FROM platform.ai_runs r WHERE job_id=:id",
            id=claim.job_id,
        )
    )[0]
    assert saved["calls_used"] == saved["completed"] == 1 and saved["cost_reserved"] >= Decimal(
        "4.07"
    )
    if change == "owner_revoked":
        await scalar(
            h,
            "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u RETURNING 1",
            w=A,
            u=UA,
        )


async def mutate_current(h, cid, scope, change):
    if change == "owner_revoked":
        await scalar(
            h,
            "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u RETURNING 1",
            w=A,
            u=UA,
        )
    elif change == "human":
        await owner(h, cid, "TAKEOVER")
    elif change == "replacement":
        await add_photo(h, cid, scope, raw=source_pixels(size=(73, 65)))
    elif change == "revoke":
        state = await call(bridge(h), "portfolio_owner_read", [BA])
        item = state["items"][0]
        await command(
            bridge(h),
            "PORTFOLIO_REVOKE",
            {
                "item_id": item["item_id"],
                "expected_item_version": item["version"],
                "expected_activation_version": state["activation_version"],
            },
        )
    else:
        assert change == "publish"
        from m5_configuration_fixtures import configuration_bundle
        from test_m5_knowledge_postgres import edit_configuration

        await edit_configuration(h, configuration_bundle() | {"communication_style": "CONCISE"})
        state = await call(bridge(h), "portfolio_owner_read", [BA])
        p = next(x for x in state["builds"] if x["build_id"] == state["active_portfolio_build_id"])
        kb = state["active_knowledge_build_id"]
        version = await scalar(
            h, "SELECT version::text FROM platform.knowledge_builds WHERE id=:id", id=UUID(kb)
        )
        draft = await configuration_read(h)
        await command(
            bridge(h),
            "PORTFOLIO_PUBLISH",
            {
                "expected_draft_version": draft["draft_version"],
                "expected_activation_version": state["activation_version"],
                "knowledge_build_id": kb,
                "expected_knowledge_build_version": version,
                "portfolio_build_id": p["build_id"],
                "expected_portfolio_build_version": p["version"],
            },
        )


@pytest.mark.parametrize("boundary", ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"])
@pytest.mark.parametrize("change", ["owner_revoked", "human", "replacement", "revoke", "publish"])
async def test_every_agent_boundary_rechecks_actual_current_authority(
    portfolio_runtime_pg, monkeypatch, boundary, change
):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic preparation"])
    await publish_portfolio(h, embeddings)
    cid, source, scope, _ = await source_image(h)
    await analyse(h, cid)
    worker, fake = await application(h, cid, embeddings)
    original = PostgresPortfolioAuthority.authorize
    triggered = []

    async def authorize(self, *args):
        if args[-1] == boundary:
            triggered.append(boundary)
            await mutate_current(h, cid, scope, change)
        return await original(self, *args)

    monkeypatch.setattr(PostgresPortfolioAuthority, "authorize", authorize)
    claim, delivery = await run_turn(h, worker, source)
    assert triggered == [boundary]
    expected = {"MODEL": 0, "READ": 1, "FOLLOWUP": 1, "CANDIDATE": 2}[boundary]
    assert (
        len(fake.requests) == expected
        and delivery["selected_kind"] is None
        and delivery["outbox_id"] is None
    )
    calls = await scalar(
        h,
        "SELECT count(*) FROM platform.ai_provider_calls WHERE run_id=(SELECT id FROM platform.ai_runs WHERE job_id=:id) AND completed_at IS NOT NULL",
        id=claim.job_id,
    )
    assert calls == expected


@pytest.mark.parametrize("boundary", ["COMMIT", "SEND"])
@pytest.mark.parametrize("change", ["owner_revoked", "human", "replacement", "revoke", "publish"])
async def test_reply_commit_and_send_recheck_saved_media_and_publication(
    portfolio_runtime_pg, monkeypatch, boundary, change
):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic owner source"])
    await publish_portfolio(h, embeddings)
    cid, source, scope, _ = await source_image(h)
    await analyse(h, cid)
    worker, fake = await application(h, cid, embeddings, script=("reply",))
    triggered = []
    if boundary == "COMMIT":
        original = worker.ai.database.commit

        async def commit(*args, **kwargs):
            triggered.append("COMMIT")
            await mutate_current(h, cid, scope, change)
            return await original(*args, **kwargs)

        monkeypatch.setattr(worker.ai.database, "commit", commit)
    _, delivery = await run_turn(h, worker, source)
    assert len(fake.requests) == 1
    if boundary == "COMMIT":
        assert (
            triggered == ["COMMIT"]
            and delivery["selected_kind"] is None
            and delivery["outbox_id"] is None
        )
    else:
        assert delivery["selected_kind"] == "reply" and delivery["outbox_id"] is not None
        await mutate_current(h, cid, scope, change)
        send = await claim_job(h, delivery["send_job_id"])
        await worker.execute(send)
        status = await scalar(
            h, "SELECT status FROM app.outbox_events WHERE id=:id", id=delivery["outbox_id"]
        )
        assert status == "FAILED"
    assert h.adapter.calls == h.adapter.effects == 0


async def test_unknown_current_vision_retains_hold_and_identity_across_new_sessions(
    portfolio_runtime_pg,
):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic source"])
    await publish_portfolio(h, embeddings)
    cid, source, _, _ = await source_image(h)

    async def unknown(request):
        raise httpx.ReadTimeout("Controlled Vision UNKNOWN")

    reservation, completed, outcome = await analyse(h, cid, behavior=unknown)
    assert completed["state"] == outcome["kind"] == "UNKNOWN"
    fresh = await admit(h, cid)
    replay = await call(bridge(h), "vision_client_reserve", [BA, cid, UUID(fresh["session_id"])])
    assert replay["status"] == "REPLAY" and replay["analysis_id"] == reservation["analysis_id"]
    before = len(embeddings.requests)
    worker, fake = await application(h, cid, embeddings, cost="0.30")
    _, delivery = await run_turn(h, worker, source)
    assert not fake.requests and len(embeddings.requests) == before and len(h.vision_posts) == 1
    assert delivery["selected_kind"] is None and delivery["outbox_id"] is None
    saved = (
        await query(
            h,
            "SELECT state,reserved_cost,applied_at FROM platform.vision_analyses WHERE id=:id",
            id=UUID(reservation["analysis_id"]),
        )
    )[0]
    assert saved == {"state": "UNKNOWN", "reserved_cost": Decimal("3.89"), "applied_at": None}


async def test_latest_unavailable_reference_never_falls_back_to_previous_ready_image(
    portfolio_runtime_pg,
):
    h = portfolio_runtime_pg
    _, _, embeddings = await publication(h, ["Synthetic source"])
    await publish_portfolio(h, embeddings)
    cid, _, scope, original = await source_image(h)
    await analyse(h, cid)
    number = next(COUNTER)
    _, message, same = await incoming(
        h, number, image_file_id=f"unavailable-{number}", text="New unavailable reference", **scope
    )
    assert same == cid
    current = await call(bridge(h), "portfolio_conversation_read", [BA, cid])
    assert current["media_pin"]["message_id"] == str(message.message_id)
    assert current["media_pin"]["file_id"] != str(original["id"])
    assert current["media_pin"]["availability"] == "UNAVAILABLE"
    assert current["vision_analysis"] is None and current["media_pin"]["analysis_id"] is None
    assert len(h.vision_posts) == 1
