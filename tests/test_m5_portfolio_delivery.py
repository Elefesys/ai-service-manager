"""v6 proposal, schema and shown-context checks; these are not PG/S3 proofs."""

import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from asm.ai.agent import AgentOutcome, PortfolioDeliveryAgentOutcome
from asm.ai.contracts import (
    CONVERSATION_RESULT,
    CONVERSATION_RESULT_V2,
    AdapterResponse,
    GatewayConfig,
    GatewayResult,
    KnowledgeGatewayConfig,
    PortfolioDeliveryGatewayConfig,
    PortfolioDeliveryGatewayResult,
    PortfolioGatewayConfig,
    PortfolioPhoto,
    SearchGatewayConfig,
)
from asm.ai.database import AIDatabase, decoded
from asm.ai.fake import FakeAdapter
from asm.ai.knowledge import KnowledgeFailure
from asm.ai.portfolio import PortfolioContextBuilder, PortfolioProjection, PortfolioReadView
from asm.ai.portfolio_delivery import (
    PortfolioDeliveryContextRead,
    PortfolioDeliveryConversationAgent,
    PortfolioDeliveryReadView,
    selection,
)
from asm.ai.runtime_contracts import (
    PortfolioDeliveryQueryData,
    PortfolioQueryData,
)
from asm.ai.runtime_settings import PortfolioDeliveryRuntimeSettings, PortfolioRuntimeSettings
from asm.messaging.errors import MessagingError
from pydantic import ValidationError
from test_m5_portfolio_context import Authority, setup


class DeliveryAuthority(Authority):
    def __init__(self, state):
        super().__init__(state)
        self.attestations = []
        self.fail_attestation = False
        self.eligible_changed = False

    async def read_current(self, *args):
        old = await super().read_current(*args)
        return PortfolioDeliveryContextRead.model_validate(
            old.model_dump()
            | {"delivery_eligible": () if self.eligible_changed else self.state.eligible}
        )

    async def attest_read(self, binding, digest, shown_refs):
        if self.fail_attestation:
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        self.attestations.append((binding, digest, shown_refs))


def fixture(*, read=True, eligible=True, candidate=None, conflict=False, count=1, cap=8192):
    s = setup(conflict=conflict)
    matches = s.projection.model_dump()["matches"]
    for i in range(1, count):
        matches += (
            matches[0]
            | {
                "item_id": uuid4(),
                "revision_id": uuid4(),
                "asset_version_id": uuid4(),
                "rank": i + 1,
            },
        )
    s.projection = PortfolioProjection.model_validate(
        s.projection.model_dump() | {"matches": matches}
    )
    s.args["portfolio_projection"] = s.projection
    s.config = decoded(
        PortfolioDeliveryGatewayConfig,
        s.config.model_dump(mode="json")
        | {"prompt_revision": "conversation_v6", "schema_revision": "conversation_result_v2"},
    )
    s.eligible = tuple(selection(v) for v in s.projection.matches) if eligible else ()
    s.chosen = selection(s.projection.matches[-1])
    s.photo = PortfolioPhoto(
        kind="portfolio_photo", selection=s.chosen, caption="Тестовая работа мастера."
    )
    output = candidate if candidate is not None else s.photo.model_dump(mode="json")
    response = AdapterResponse(kind="OUTPUT", output_json=json.dumps(output, ensure_ascii=False))
    s.adapter = FakeAdapter(s.config.route, ("tools", response) if read else (response,))
    s.authority = DeliveryAuthority(s)
    from asm.ai.context import ContextLimits

    s.agent = PortfolioDeliveryConversationAgent(
        s.config,
        s.adapter,
        s.authority,
        delivery_eligible=s.eligible,
        builder=PortfolioContextBuilder(ContextLimits(max_bytes=cap)),
        **s.args,
    )
    return s


async def execute(s):
    return await s.agent.run(
        s.old.binding, s.old.snapshot, run_id=str(s.old.run_id), deadline=s.old.deadline
    )


def test_explicit_v6_old_config_and_result_models_remain_closed():
    s = fixture()
    for model in (
        GatewayConfig,
        KnowledgeGatewayConfig,
        SearchGatewayConfig,
        PortfolioGatewayConfig,
    ):
        with pytest.raises(ValidationError):
            model.model_validate_json(s.config.model_dump_json())
    with pytest.raises(ValidationError):
        CONVERSATION_RESULT.validate_json(s.photo.model_dump_json())
    assert CONVERSATION_RESULT_V2.validate_json(s.photo.model_dump_json()) == s.photo
    budget = s.old.budget
    with pytest.raises(ValidationError):
        GatewayResult(kind="FINAL", result=s.photo, budget=budget)
    with pytest.raises(ValidationError):
        AgentOutcome(
            status="CANDIDATE", candidate=s.photo, budget=budget, reads_executed=1, calls=()
        )
    assert (
        PortfolioDeliveryGatewayResult(kind="FINAL", result=s.photo, budget=budget).result
        == s.photo
    )
    assert (
        PortfolioDeliveryAgentOutcome(
            status="CANDIDATE", candidate=s.photo, budget=budget, reads_executed=1, calls=()
        ).candidate
        == s.photo
    )


@pytest.mark.parametrize(
    "extra",
    ["workspace_id", "client_id", "chat_id", "url", "storage_key", "file_id", "text", "reason"],
)
def test_photo_rejects_hidden_authority_or_second_effect_fields(extra):
    s = fixture()
    raw = s.photo.model_dump(mode="json") | {extra: "untrusted"}
    with pytest.raises(ValidationError):
        CONVERSATION_RESULT_V2.validate_json(json.dumps(raw))
    raw = s.photo.model_dump(mode="json")
    raw["selection"][extra] = "untrusted"
    with pytest.raises(ValidationError):
        CONVERSATION_RESULT_V2.validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "caption,valid",
    [
        ("", False),
        (" \n", False),
        ("a" * 1024, True),
        ("a" * 1025, False),
        ("я" * 1024, True),
        ("\0text", False),
    ],
)
def test_caption_is_nonempty_bounded_scalar_plain_text(caption, valid):
    s = fixture()
    raw = s.photo.model_dump() | {"caption": caption}
    if valid:
        assert PortfolioPhoto.model_validate(raw).caption == caption
    else:
        with pytest.raises(ValidationError):
            PortfolioPhoto.model_validate(raw)


async def test_only_successful_fresh_read_of_shown_source_allows_photo_candidate():
    s = fixture()
    result = await execute(s)
    assert result.status == "CANDIDATE", result
    assert result.candidate == s.photo
    assert result.reads_executed == 1 and len(s.adapter.requests) == 2
    assert s.authority.boundaries == ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"]
    assert s.authority.attestations == [(s.old.binding, s.agent.shown.digest(), (s.chosen,))]
    read = PortfolioDeliveryReadView.model_validate_json(
        s.adapter.requests[1].exchanges[0].results[0].result_json
    )
    assert read.context_sha256 == s.agent.shown.digest()
    assert read.delivery.references == (s.chosen,)
    assert result.runtime_authorized is False
    assert s.agent.shown.revision == "conversation_context_v5"
    with pytest.raises(ValidationError):
        PortfolioReadView.model_validate_json(read.model_dump_json())


async def test_photo_without_read_is_rejected_after_one_call():
    s = fixture(read=False)
    result = await execute(s)
    assert result.status == "STOP" and result.reason == "INVALID_OUTPUT"
    assert len(s.adapter.requests) == 1 and not s.authority.attestations


async def test_non_sendable_or_absent_source_is_not_proposed_as_success():
    s = fixture(eligible=False)
    result = await execute(s)
    assert result.status == "STOP" and result.reason == "INVALID_OUTPUT"
    assert s.authority.attestations[0][2] == ()


@pytest.mark.parametrize("field", ["item_id", "revision_id", "asset_version_id", "source_sha256"])
async def test_selection_requires_exact_four_field_reference(field):
    s = fixture()
    raw = s.photo.model_dump(mode="json")
    raw["selection"][field] = "0" * 64 if field == "source_sha256" else str(uuid4())
    s.adapter.script = ("tools", AdapterResponse(kind="OUTPUT", output_json=json.dumps(raw)))
    result = await execute(s)
    assert result.status == "STOP" and result.reason == "INVALID_OUTPUT"


@pytest.mark.parametrize("stage", ["MODEL", "READ", "FOLLOWUP", "CANDIDATE"])
async def test_each_authority_boundary_remains_required(stage):
    s = fixture()
    s.authority.deny = stage
    result = await execute(s)
    assert result.status == "STOP" and result.reason == "AUTHORITY_STALE"
    assert len(s.adapter.requests) == (2 if stage == "CANDIDATE" else 1 if stage != "MODEL" else 0)


async def test_failed_attestation_stops_before_second_model_call():
    s = fixture()
    s.authority.fail_attestation = True
    result = await execute(s)
    assert result.status == "STOP" and result.reason == "KNOWLEDGE_STALE"
    assert len(s.adapter.requests) == 1


async def test_changed_eligible_set_during_read_is_stale():
    s = fixture()
    s.authority.eligible_changed = True
    result = await execute(s)
    assert result.status == "STOP" and result.reason == "KNOWLEDGE_STALE"
    assert len(s.adapter.requests) == 1 and not s.authority.attestations


async def test_conflicting_knowledge_requires_handoff_even_when_photo_was_proposed():
    s = fixture(conflict=True)
    result = await execute(s)
    assert result.status == "CANDIDATE" and result.candidate.kind == "handoff"


@pytest.mark.parametrize("kind", ["reply", "handoff", "no_reply"])
async def test_v6_preserves_supported_text_handoff_and_no_reply(kind):
    raw = {
        "kind": kind,
        "text": "Тестовый ответ." if kind == "reply" else None,
        "reason": None if kind == "reply" else "Требуется мастер.",
    }
    s = fixture(read=False, candidate=raw)
    result = await execute(s)
    assert result.status == "CANDIDATE" and result.candidate.kind == kind
    assert len(s.adapter.requests) == 1


def test_settings_require_new_explicit_synthetic_admission():
    s = fixture()
    raw = dict(
        session_id=uuid4(),
        workspace_id=s.old.binding.workspace_id,
        business_id=s.old.binding.business_id,
        client_id=s.old.binding.client_id,
        conversation_id=s.old.binding.conversation_id,
        data_profile="SYNTHETIC_PORTFOLIO_PHOTO_V1",
        expires_at=s.old.deadline + timedelta(seconds=60),
        max_calls=2,
        max_cost=s.config.limits.cost_budget,
        config=s.config,
    )
    settings = PortfolioDeliveryRuntimeSettings.model_validate(raw)
    settings.current()
    with pytest.raises(ValidationError):
        PortfolioRuntimeSettings.model_validate(raw)
    db = AIDatabase(
        SimpleNamespace(),
        environment="TEST",
        delivery=True,
        portfolio_session_id=settings.session_id,
    )
    with pytest.raises(MessagingError):
        db.config(s.config)
    admitted = AIDatabase(
        SimpleNamespace(),
        environment="TEST",
        delivery=True,
        portfolio_session_id=settings.session_id,
        portfolio_delivery=True,
    )
    assert admitted.config(s.config) == s.config
    for field, value in (
        ("route", s.config.route.model_copy(update={"execution": "PROVIDER"})),
        ("limits", s.config.limits.model_copy(update={"model_calls": 3})),
    ):
        with pytest.raises(ValidationError):
            PortfolioDeliveryGatewayConfig.model_validate(s.config.model_dump() | {field: value})


def test_v6_query_metadata_is_not_silently_added_to_old_query_dto():
    s = fixture()
    raw = dict(
        knowledge=s.search,
        portfolio=s.projection,
        portfolio_pin=s.pin,
        media_pin=s.media,
        portfolio_refs=s.projection.refs(),
        portfolio_session_id=uuid4(),
        search_query=s.query,
        vision_analysis=s.vision,
        delivery_eligible=s.eligible,
    )
    assert PortfolioDeliveryQueryData.model_validate(raw).delivery_eligible == s.eligible
    with pytest.raises(ValidationError):
        PortfolioQueryData.model_validate(raw)
    raw["delivery_eligible"] = (s.chosen.model_copy(update={"asset_version_id": uuid4()}),)
    with pytest.raises(ValidationError):
        PortfolioDeliveryQueryData.model_validate(raw)


async def test_reduced_context_cannot_select_a_match_omitted_from_model_view():
    s = fixture(count=3, cap=5200)
    result = await execute(s)
    assert len(s.agent.shown.business.portfolio.matches) == 2
    assert s.chosen not in s.agent.shown.delivery.references
    assert s.authority.attestations[0][2] == s.agent.shown.delivery.references
    assert result.status == "STOP" and result.reason == "INVALID_OUTPUT"
    assert len(s.adapter.requests) == 2


async def test_reduced_context_can_select_one_of_the_actual_shown_sendable_sources():
    s = fixture(count=3, cap=5200)
    first = selection(s.projection.matches[0])
    raw = s.photo.model_dump(mode="json") | {"selection": first.model_dump(mode="json")}
    s.adapter.script = ("tools", AdapterResponse(kind="OUTPUT", output_json=json.dumps(raw)))
    result = await execute(s)
    assert result.status == "CANDIDATE" and result.candidate.selection == first
    assert len(s.agent.shown.delivery.references) == 2


def test_new_receipt_allows_only_explicit_v2_result_and_never_send_authority():
    from datetime import UTC, datetime

    from asm.ai.runtime_contracts import PortfolioDeliveryRuntimeReceipt, PortfolioRuntimeReceipt

    s = fixture()
    raw = dict(
        run_id=s.old.run_id,
        job_id=uuid4(),
        turn_id=s.old.binding.turn_id,
        turn_revision=s.old.binding.turn_revision,
        selected_at=datetime.now(UTC),
        result=s.photo,
        knowledge_pin=s.old.knowledge_pin,
        search_pin=s.old.search_pin,
        search_refs=s.search.refs(),
        portfolio_pin=s.pin,
        media_pin=s.media,
        portfolio_refs=s.projection.refs(),
    )
    receipt = PortfolioDeliveryRuntimeReceipt.model_validate(raw)
    assert receipt.result == s.photo and receipt.send_permit is False
    with pytest.raises(ValidationError):
        PortfolioRuntimeReceipt.model_validate(raw)
    with pytest.raises(ValidationError):
        PortfolioDeliveryRuntimeReceipt.model_validate(raw | {"send_permit": True})


@pytest.mark.parametrize(
    "fields,allowed",
    [
        ({"size_bytes": 10_000_000, "width": 2000, "height": 8000}, True),
        ({"size_bytes": 10_000_001}, False),
        ({"width": 2001, "height": 8000}, False),
        ({"width": 20, "height": 1}, True),
        ({"width": 21, "height": 1}, False),
        ({"mime_type": "image/webp"}, False),
    ],
)
def test_telegram_photo_subset_in_addition_to_unchanged_decoder_caps(fields, allowed):
    from asm.files.models import ImageManifest
    from asm.portfolio.delivery import photo_manifest

    manifest = ImageManifest.model_validate(
        {"mime_type": "image/png", "size_bytes": 100, "sha256": "a" * 64, "width": 64, "height": 64}
        | fields
    )
    if allowed:
        assert photo_manifest(manifest) == manifest
    else:
        with pytest.raises(MessagingError):
            photo_manifest(manifest)


@pytest.mark.parametrize("caption", ["", " \n ", "x" * 1025, "x\0", "\ud800"])
def test_plain_caption_is_bounded_without_hidden_truncation(caption):
    from asm.portfolio.delivery import photo_caption

    with pytest.raises(MessagingError):
        photo_caption(caption)


def test_caption_preserves_full_unicode_and_plain_markup():
    from asm.portfolio.delivery import photo_caption

    assert photo_caption("🎨" * 1024) == "🎨" * 1024
    assert photo_caption("  <b> e\u0301 </b>\n") == "  <b> e\u0301 </b>\n"


def test_snapshot4_preserves_photo_history_and_old_snapshot3_closed_shape():
    import copy
    import hashlib

    from asm.ai.context import ContextBuilder
    from asm.conversations.turns import TurnSnapshotV3, TurnSnapshotV4, native_jsonb, parse_snapshot
    from test_m4_context import fixture as snapshot_fixture

    raw, binding = snapshot_fixture()
    raw = copy.deepcopy(raw)
    recent = raw["recent_messages"][0]
    assert recent["direction"] == "OUTBOUND"
    recent.update(
        origin="CONTROLLED_AUTOMATION",
        file=None,
        version="1",
        current={
            "schema_version": 2,
            "state": "VISIBLE",
            "content_type": "PHOTO",
            "text": "A published work",
            "image_availability": "PORTFOLIO_AVAILABLE",
            "changed": False,
        },
    )
    raw["schema_version"] = 4
    raw["snapshot_digest"] = hashlib.sha256(
        native_jsonb(
            {k: v for k, v in raw.items() if k not in {"code", "job_id", "snapshot_digest"}}
        )
    ).hexdigest()
    bound = binding.model_copy(update={"snapshot_digest": raw["snapshot_digest"]})
    assert isinstance(parse_snapshot(raw), TurnSnapshotV4)
    visible = ContextBuilder().build(raw, bound).view.recent[0]
    assert visible.content_type == "PHOTO" and visible.text == "A published work"
    assert visible.image_availability == "HIDDEN" and visible.image_read is False
    with pytest.raises(ValidationError):
        TurnSnapshotV3.model_validate(raw)
    raw["schema_version"] = 3
    raw["snapshot_digest"] = hashlib.sha256(
        native_jsonb(
            {k: v for k, v in raw.items() if k not in {"code", "job_id", "snapshot_digest"}}
        )
    ).hexdigest()
    with pytest.raises(ValidationError):
        TurnSnapshotV3.model_validate(raw)
