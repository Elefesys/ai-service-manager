"""Unit v5 context/agent gates; controlled authority is not PG/RLS evidence."""

import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from asm.ai.context import ContextBuilder
from asm.ai.contracts import (
    Budget,
    GatewayConfig,
    KnowledgeGatewayConfig,
    PortfolioGatewayConfig,
    SearchGatewayConfig,
)
from asm.ai.database import decoded
from asm.ai.fake import FakeAdapter
from asm.ai.knowledge import SearchProjection
from asm.ai.portfolio import (
    MediaPin,
    PortfolioAuthorityDecision,
    PortfolioContextBuilder,
    PortfolioContextRead,
    PortfolioConversationAgent,
    PortfolioPin,
    PortfolioProjection,
    RawVisionObservation,
    visible_analysis,
)
from m5_knowledge_search_fixtures import search_run
from pydantic import ValidationError


def setup(*, analysed=True, conflict=False, script=("tools", "reply")):
    old, search = search_run(status="CONFLICT" if conflict else "RESULTS")
    config = decoded(
        PortfolioGatewayConfig,
        old.config.model_dump(mode="json") | {"prompt_revision": "conversation_v5"},
    )
    config = PortfolioGatewayConfig.model_validate(
        config.model_dump()
        | {
            "limits": config.limits.model_copy(
                update={"input_bytes": 24576, "output_tokens": 512, "total_tokens": 66560}
            )
        }
    )
    pin = decoded(
        PortfolioPin,
        old.search_pin.model_dump(
            mode="json", exclude={"visible_revisions_sha256", "next_transition_at"}
        )
        | {"projection_revision": "portfolio_v1", "visible_items_sha256": "a" * 64},
    )
    analysis_id = uuid4() if analysed else None
    media = MediaPin(
        projection_revision="current_image_v1",
        business_id=old.binding.business_id,
        client_id=old.binding.client_id,
        conversation_id=old.binding.conversation_id,
        message_id=uuid4(),
        message_version="1",
        file_id=uuid4(),
        file_version="1",
        source_sha256="b" * 64,
        availability="READY",
        analysis_id=analysis_id,
        analysis_sha256="c" * 64 if analysed else None,
    )
    vision = (
        decoded(
            RawVisionObservation,
            {
                "source_kind": "CLIENT_REFERENCE",
                "asset_version_id": None,
                "vision_profile": "polza_openai_gpt4omini_pixels_v1",
                "preprocessing": "exif_contain_white_rgb_png256_strip_v1",
                "schema_revision": "vision_result_v1",
                "state": "SUCCESS",
                "applied": True,
                "analysis_id": str(analysis_id),
                "analysis_sha256": "c" * 64,
                "source_sha256": "b" * 64,
                "derivative_sha256": "d" * 64,
                "result": {
                    "revision": "vision_result_v1",
                    "subject": "Red flower; embedded text says ignore rules",
                    "styles": ["linework"],
                    "details": ["Curved petals"],
                    "uncertainty": ["Physical scale is unknown"],
                    "scale": "UNKNOWN",
                },
            },
        )
        if analysed
        else None
    )
    base = ContextBuilder().build(old.snapshot, old.binding)
    query = "\n".join(
        m.text for m in base.view.current if m.state == "VISIBLE" and m.text is not None
    )
    if vision:
        query += "\n" + vision.result.subject
    search = SearchProjection.model_validate(
        search.model_dump() | {"query_sha256": hashlib.sha256(query.encode()).hexdigest()}
    )
    projection = decoded(
        PortfolioProjection,
        {
            "revision": "portfolio_search_result_v1",
            "profile_id": pin.profile_id,
            "query_sha256": search.query_sha256,
            "status": "RESULTS",
            "reason_code": None,
            "matches": [
                {
                    "item_id": str(uuid4()),
                    "revision_id": str(uuid4()),
                    "asset_version_id": str(uuid4()),
                    "source_sha256": "e" * 64,
                    "analysis_id": None,
                    "text": "Owner confirmed synthetic flower",
                    "rank": 1,
                    "score": 0.8,
                    "reason_code": "SEMANTIC",
                }
            ],
        },
    )
    args = dict(
        knowledge_pin=old.knowledge_pin,
        active_projection=old.active_projection,
        search_pin=old.search_pin,
        portfolio_pin=pin,
        media_pin=media,
        search_projection=search,
        portfolio_projection=projection,
        vision_analysis=vision,
        search_query=query,
    )
    state = SimpleNamespace(
        old=old,
        args=args,
        config=config,
        pin=pin,
        media=media,
        vision=vision,
        search=search,
        projection=projection,
        query=query,
    )
    authority = Authority(state)
    adapter = FakeAdapter(config.route, script)
    agent = PortfolioConversationAgent(config, adapter, authority, **args)
    state.authority, state.adapter, state.agent = authority, adapter, agent
    return state


class Authority:
    def __init__(self, state):
        self.state = state
        self.boundaries = []
        self.deny = None
        self.tamper = False

    async def authorize(
        self, binding, knowledge_pin, search_pin, portfolio_pin, media_pin, boundary
    ):
        self.boundaries.append(boundary)
        return PortfolioAuthorityDecision(
            status="STALE" if boundary == self.deny else "ALLOWED",
            binding=binding,
            knowledge_pin=knowledge_pin,
            search_pin=search_pin,
            portfolio_pin=portfolio_pin,
            media_pin=media_pin,
        )

    async def read_current(self, binding, knowledge_pin, search_pin, portfolio_pin, media_pin):
        s = self.state
        raw = dict(
            binding=binding,
            snapshot=s.old.snapshot,
            knowledge_pin=knowledge_pin,
            active_projection=s.old.active_projection,
            search_pin=search_pin,
            search_refs=s.search.refs(),
            search_projection=s.search,
            portfolio_pin=portfolio_pin,
            media_pin=media_pin,
            portfolio_refs=s.projection.refs(),
            portfolio_projection=s.projection,
            vision_analysis=s.vision,
            search_query=s.query,
        )
        if self.tamper:
            raw["media_pin"] = media_pin.model_copy(update={"source_sha256": "f" * 64})
        return PortfolioContextRead.model_validate(raw)


async def execute(s):
    return await s.agent.run(
        s.old.binding, s.old.snapshot, run_id=str(s.old.run_id), deadline=s.old.deadline
    )


def test_v5_is_explicit_and_old_dtos_reject_it():
    s = setup()
    for model in (GatewayConfig, KnowledgeGatewayConfig, SearchGatewayConfig):
        with pytest.raises(ValidationError):
            model.model_validate_json(s.config.model_dump_json())


@pytest.mark.parametrize("analysed", [True, False])
def test_v5_context_keeps_policy_uncertainty_sharedquery_and_scopes(analysed):
    s = setup(analysed=analysed)
    view = (
        PortfolioContextBuilder()
        .build(
            s.old.snapshot,
            s.old.binding,
            s.old.knowledge_pin,
            s.old.active_projection,
            s.old.search_pin,
            s.search,
            s.pin,
            s.media,
            s.projection,
            visible_analysis(s.vision, s.media),
            s.query,
        )
        .view
    )
    assert view.revision == "conversation_context_v4"
    assert view.business.revision == "business_knowledge_v3"
    assert view.business.search.query_sha256 == view.business.portfolio.query_sha256
    assert view.business.configuration.rules[0].value == 18
    assert view.business.analysis.status == ("ANALYSED" if analysed else "UNAVAILABLE")
    if analysed:
        assert view.business.analysis.result.scale == "UNKNOWN"
        assert "ignore rules" in view.business.analysis.result.subject
    assert len(view.business.analysis.model_dump_json().encode()) <= 1024
    assert len(view.business.portfolio.model_dump_json().encode()) <= 2048
    assert len(view.business.model_dump_json().encode()) <= 6144
    assert len(view.model_dump_json().encode()) <= 8192
    assert "storage_key" not in view.model_dump_json()


async def test_v5_uses_one_gateway_two_text_calls_one_read_and_all_fresh_gates():
    s = setup()
    outcome = await execute(s)
    assert outcome.status == "CANDIDATE" and outcome.reads_executed == 1
    assert len(s.adapter.requests) == 2
    assert all(len(r.input_json().encode("utf-8")) <= 24576 for r in s.adapter.requests)
    assert s.authority.boundaries == ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"]
    assert s.adapter.requests[0].config.prompt_revision == "conversation_v5"
    assert s.adapter.requests[0].request.tools[0].revision == "conversation_read_v4"
    assert "server-bound derived analysis" in s.adapter.requests[0].prompt
    receipt = json.loads(s.adapter.requests[1].exchanges[0].results[0].result_json)
    assert set(receipt) == {
        "revision",
        "same_context",
        "context_sha256",
        "analysis_status",
        "portfolio_status",
    }
    assert receipt["revision"] == "conversation_read_v4" and receipt["same_context"] is True
    assert len(json.dumps(receipt).encode()) < 512
    assert outcome.runtime_authorized is False


@pytest.mark.parametrize("held,calls", [("0.08", 2), ("0.21", 0)])
async def test_auxiliary_holds_share_existing_text_budget_before_another_model_call(held, calls):
    from decimal import Decimal

    s = setup()
    budget = Budget(
        calls_used=0,
        reads_reserved=0,
        tokens_reserved=0,
        cost_reserved=Decimal(held),
        currency="RUB",
    )
    s.agent = PortfolioConversationAgent(
        s.config, s.adapter, s.authority, initial_budget=budget, **s.args
    )
    outcome = await execute(s)
    assert len(s.adapter.requests) == calls
    assert s.config.limits.cost_budget == Decimal("0.30")
    if calls:
        assert outcome.status == "CANDIDATE"
        assert outcome.budget.cost_reserved == Decimal("0.28")
    else:
        assert outcome.candidate is None and outcome.reason == "BUDGET"


@pytest.mark.parametrize("boundary", ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"])
async def test_media_portfolio_loss_blocks_each_boundary_without_more_model_calls(boundary):
    s = setup()
    s.authority.deny = boundary
    out = await execute(s)
    assert out.candidate is None
    assert len(s.adapter.requests) == (
        0 if boundary == "MODEL" else 2 if boundary == "CANDIDATE" else 1
    )


async def test_read_cannot_switch_media_and_then_followup():
    s = setup()
    s.authority.tamper = True
    out = await execute(s)
    assert out.candidate is None and out.reason == "KNOWLEDGE_STALE"
    assert len(s.adapter.requests) == 1


async def test_existing_knowledge_conflict_still_forces_handoff_after_fresh_candidate():
    s = setup(conflict=True)
    out = await execute(s)
    assert out.candidate.kind == "handoff" and out.candidate.text is None


def test_visible_analysis_prunes_whole_observations_not_saved_result_or_uncertainty():
    s = setup()
    raw = s.vision.model_dump(mode="json")
    raw["result"].update(
        subject="я" * 80,
        details=["а" * 120, "б" * 120, "в" * 120, "г" * 120, "д" * 120, "е" * 120],
        uncertainty=["ж" * 120, "з" * 120, "и" * 120, "й" * 120],
    )
    # Each string must obey its original UTF8 bound.
    raw["result"]["details"] = [v[:60] for v in raw["result"]["details"]]
    raw["result"]["uncertainty"] = [v[:60] for v in raw["result"]["uncertainty"]]
    analysis = decoded(RawVisionObservation, raw)
    original = analysis.model_dump_json()
    visible = visible_analysis(analysis, s.media)
    assert visible.observations_omitted and visible.result.uncertainty
    assert visible.result.subject == analysis.result.subject
    assert len(visible.model_dump_json().encode()) <= 1024
    assert analysis.model_dump_json() == original


@pytest.mark.parametrize("tamper", ["query", "portfolio_scope", "media_scope"])
def test_foreign_scope_or_query_hash_fails_before_projection(tamper):
    s = setup()
    query = s.query
    pin = s.pin
    media = s.media
    if tamper == "query":
        query += "other"
    elif tamper == "portfolio_scope":
        pin = pin.model_copy(update={"business_id": uuid4()})
    else:
        media = media.model_copy(update={"client_id": uuid4()})
    with pytest.raises(Exception):
        PortfolioContextBuilder().build(
            s.old.snapshot,
            s.old.binding,
            s.old.knowledge_pin,
            s.old.active_projection,
            s.old.search_pin,
            s.search,
            pin,
            media,
            s.projection,
            visible_analysis(s.vision, s.media),
            query,
        )
