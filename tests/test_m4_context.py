"""Synthetic projection evidence; no hosted quality, PostgreSQL authority or media I/O."""

import copy
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest
from asm.ai.context import ContextBinding, ContextBuilder, ContextFailure, ContextLimits
from asm.conversations.turns import native_jsonb, parse_snapshot

FIXTURES = Path("tests/fixtures/m4_context_cases.json")


def fixture(name="v3_owner"):
    row = next(c for c in json.loads(FIXTURES.read_text())["cases"] if c["name"] == name)
    return row["snapshot"], ContextBinding.model_validate_json(json.dumps(row["binding"]))


def resign(raw, binding):
    """Only tests sign synthetic V3 data; production never repairs a bad digest."""
    if raw["schema_version"] == 3:
        raw["snapshot_digest"] = hashlib.sha256(
            native_jsonb(
                {k: v for k, v in raw.items() if k not in ("code", "job_id", "snapshot_digest")}
            )
        ).hexdigest()
    return binding.model_copy(update={"snapshot_digest": raw["snapshot_digest"]})


@pytest.mark.parametrize("row", json.loads(FIXTURES.read_text())["cases"], ids=lambda c: c["name"])
def test_v2_v3_guarded_and_unguarded_explicit_projection(row):
    raw, binding = fixture(row["name"])
    saved = copy.deepcopy(raw)
    prepared = ContextBuilder().build(raw, binding)
    view = prepared.view
    expected = row["expected"]
    assert view.current[0].text == expected["current_text"]
    assert view.owner_confirmed_text == expected["owner_text"]
    assert len(view.recent) == expected["recent_count"]
    assert view.source_coverage_status == expected["coverage"]
    assert view.current[0].image_availability == expected["image_availability"]
    assert not view.current[0].image_read and "IMAGES_NOT_READ" in view.context_limitations
    assert raw == saved and prepared.binding == binding
    messages = view.messages()
    assert [m.role for m in messages] == ["context", "user"]
    context, user = [json.loads(m.text) for m in messages]
    assert "current" not in context and user["current"][0]["text"] == expected["current_text"]
    assert len(view.model_dump_json().encode()) <= 8192
    wire = view.model_dump_json()
    for private in (
        str(binding.workspace_id),
        str(binding.client_id),
        str(binding.conversation_id),
        str(binding.business_id),
        str(binding.turn_id),
        str(binding.job_id),
        str(binding.resume_receipt_id),
        binding.snapshot_digest,
    ):
        assert private not in wire
    for key in (
        "message_id",
        "file_id",
        "actor_user_account_id",
        "claim_token",
        "revision_id",
        "control_generation",
        "activation_fence_seq",
        "consumer",
        "reviewed_input_state_hash",
    ):
        assert key not in wire
    if raw["schema_version"] == 2:
        assert view.history_truncated is None and view.owner_confirmed_text is None
        assert "HISTORY_UNAVAILABLE_V2" in view.context_limitations
    else:
        assert "PROVIDER_HISTORY_UNVERIFIED" in view.context_limitations


def test_owner_current_and_history_have_separate_provenance_and_no_duplicate_member():
    raw, binding = fixture()
    view = ContextBuilder().build(raw, binding).view
    assert len(raw["recent_messages"]) == 3 and len(view.recent) == 2
    assert view.recent[0].origin == "OWNER_MANUAL" and view.recent[0].delivery_status == "UNKNOWN"
    assert "Старая" in view.recent[0].text and "Новая" in view.owner_confirmed_text
    assert view.recent_is_historical and all(m.source == "RECENT_HISTORY" for m in view.recent)
    assert view.current[0].source == "CURRENT_TURN"
    assert view.model_dump_json().count(view.current[0].text) == 1
    assert view.context_coverage == "OWNER_ASSERTED_TEXT_ONLY"


@pytest.mark.parametrize("state", ["DELETED", "ORDER_UNCERTAIN", "UNSUPPORTED_CONTENT", "EDITED"])
def test_current_edit_delete_never_revives_old_material_from_recent(state):
    raw, binding = fixture("v3_guarded_image")
    member, recent = raw["members"][0], raw["recent_messages"][-1]
    original = member["current"]["text"]
    member["message_version"] = 2
    member["current"] = dict(
        schema_version=1,
        state="VISIBLE" if state == "EDITED" else state,
        content_type="TEXT" if state == "EDITED" else None,
        text="Только новая редакция" if state == "EDITED" else None,
        image_availability="NOT_APPLICABLE" if state == "EDITED" else "HIDDEN",
        changed=True,
    )
    recent.update(version="2", current=copy.deepcopy(member["current"]), file=None)
    raw["readiness"] = "PARTIAL" if state != "EDITED" else "COMPLETE"
    view = ContextBuilder().build(raw, resign(raw, binding)).view
    assert original not in view.model_dump_json()
    assert view.current[0].text == ("Только новая редакция" if state == "EDITED" else None)
    assert len(view.recent) == 2 and not view.current[0].image_read


@pytest.mark.parametrize(
    "availability",
    [
        "ORIGINAL_READY",
        "ORIGINAL_PENDING",
        "ORIGINAL_FAILED",
        "ORIGINAL_NOT_FETCHED",
        "MEDIA_REPLACED_UNAVAILABLE",
    ],
)
def test_media_state_is_a_limit_and_ready_is_not_read(availability):
    raw, binding = fixture("v3_guarded_image")
    m, r = raw["members"][0], raw["recent_messages"][-1]
    m["current"].update(
        image_availability=availability,
        changed=availability in ("ORIGINAL_NOT_FETCHED", "MEDIA_REPLACED_UNAVAILABLE"),
    )
    if m["current"]["changed"]:
        m["message_version"] = 2
    else:
        status = availability.removeprefix("ORIGINAL_")
        m["file"].update(
            status=status,
            wait_expired=status == "PENDING",
            error_code="DEPENDENCY_TIMEOUT" if status == "FAILED" else None,
        )
        r["file"]["status"] = status
    r.update(version=str(m["message_version"]), current=copy.deepcopy(m["current"]))
    raw["readiness"] = "COMPLETE" if availability == "ORIGINAL_READY" else "PARTIAL"
    view = ContextBuilder().build(raw, resign(raw, binding)).view
    assert view.current[0].image_availability == availability and not view.current[0].image_read
    assert view.current[0].text == "Текущий caption 🎨" and "file" not in view.model_dump_json()


def test_native_owner_text_and_coverage_survive_source_and_local_truncation():
    raw, binding = fixture()
    row = raw["recent_messages"][1]
    raw["recent_messages"] = [
        dict(copy.deepcopy(row), message_id=str(UUID(int=100 + i))) for i in range(16)
    ]
    raw["history_truncated"] = True
    raw["human_context"]["source_media"] = "UNAVAILABLE"
    raw["context_limitations"].append("NATIVE_MEDIA_UNAVAILABLE")
    raw["readiness"] = "PARTIAL"
    view = ContextBuilder(ContextLimits(recent_messages=3)).build(raw, resign(raw, binding)).view
    assert view.owner_confirmed_text == raw["human_context"]["text"]
    assert view.current[0].text == raw["members"][0]["current"]["text"]
    assert view.source_coverage_status == "OWNER_TEXT" and view.source_history_truncated
    assert view.history_truncated and view.history_omitted == 13 and len(view.recent) == 3
    assert (
        view.owner_source_media == "UNAVAILABLE"
        and "NATIVE_MEDIA_UNAVAILABLE" in view.context_limitations
    )


def test_utf8_byte_bound_drops_only_whole_oldest_history_and_keeps_exact_owner_current():
    raw, binding = fixture("v3_unicode_adversarial")
    base = ContextBuilder().build(raw, binding).view
    assert "e\u0301" in base.owner_confirmed_text and "\n" in base.current[0].text
    row = fixture()[0]["recent_messages"][1]
    raw["recent_messages"] = []
    for i in range(3):
        r = copy.deepcopy(row)
        r["message_id"] = str(UUID(int=100 + i))
        r["current"]["text"] = f"history-{i} " + "я🎨" * 100
        raw["recent_messages"].append(r)
    binding = resign(raw, binding)
    cap = len(base.model_dump_json().encode()) + 1100
    view = ContextBuilder(ContextLimits(max_bytes=cap)).build(raw, binding).view
    assert len(view.model_dump_json().encode()) <= cap
    assert view.owner_confirmed_text == base.owner_confirmed_text and view.current == base.current
    assert view.history_truncated and view.history_omitted > 0
    assert [m.text for m in view.recent] == [
        r["current"]["text"] for r in raw["recent_messages"][view.history_omitted :]
    ]


@pytest.mark.parametrize("field", ["owner", "current"])
def test_essential_text_that_cannot_fit_is_a_typed_stop_not_a_truncation(field):
    raw, binding = fixture("v3_unicode_adversarial")
    if field == "owner":
        raw["human_context"]["text"] = "🎨" * 4096
    else:
        raw["members"][0]["current"]["text"] = "🎨" * 4096
    with pytest.raises(ContextFailure, match="CONTEXT_TOO_LARGE"):
        ContextBuilder(ContextLimits(max_bytes=16384)).build(raw, resign(raw, binding))


@pytest.mark.parametrize(
    "bad",
    [
        "v1",
        "unknown_version",
        "bool_version",
        "extra",
        "digest",
        "stale_overlap",
        "hidden_text",
        "duplicate_member",
        "naive",
        "bool_revision",
        "bool_member",
    ],
)
def test_invalid_or_unavailable_snapshot_never_yields_context(bad):
    raw, binding = fixture("v3_owner" if bad in ("digest", "stale_overlap") else "v2")
    if bad == "v1":
        raw.pop("schema_version")
    elif bad == "unknown_version":
        raw["schema_version"] = 9
    elif bad == "bool_version":
        raw["schema_version"] = True
    elif bad == "extra":
        raw["owner_only_secret"] = "PRIVATE"
    elif bad == "digest":
        raw["snapshot_digest"] = "f" * 64
    elif bad == "stale_overlap":
        raw["members"][0]["current"]["text"] = "New current material"
        binding = resign(raw, binding)
    elif bad == "hidden_text":
        raw["members"][0]["current"]["state"] = "DELETED"
    elif bad == "duplicate_member":
        raw["members"].append(copy.deepcopy(raw["members"][0]))
    elif bad == "naive":
        raw["members"][0]["ingress_at"] = "2030-01-01T00:00:00"
    elif bad == "bool_revision":
        raw["turn_revision"] = True
    else:
        raw["members"][0]["message_version"] = True
    with pytest.raises(ContextFailure) as exc:
        ContextBuilder().build(raw, binding)
    assert "PRIVATE" not in str(exc.value)


def test_builder_requires_original_saved_v3_json_not_resigned_normalized_dto():
    raw, binding = fixture()
    with pytest.raises(ContextFailure, match="INVALID_CONTEXT"):
        ContextBuilder().build(parse_snapshot(raw), binding)


def test_local_history_truncation_is_explicit_even_for_canonical_source_coverage():
    raw, binding = fixture("v3_canonical")
    raw["recent_messages"] = fixture()[0]["recent_messages"][:-1]
    view = ContextBuilder(ContextLimits(recent_messages=0)).build(raw, resign(raw, binding)).view
    assert view.source_coverage_status == "CANONICAL_COMPLETE"
    assert view.source_history_truncated is False and view.history_truncated is True
    assert view.history_omitted == 2 and not view.recent


def test_multiple_current_messages_preserve_order_caption_and_effective_material():
    raw, binding = fixture("v2")
    first = raw["members"][0]
    second = copy.deepcopy(first)
    second.update(message_id=str(UUID(int=80)), ingress_seq=3, message_version=2)
    second["current"].update(text="Второй актуальный вопрос", changed=True)
    raw["members"].append(second)
    view = ContextBuilder().build(raw, binding).view
    assert [m.text for m in view.current] == [first["current"]["text"], "Второй актуальный вопрос"]
    raw["members"].reverse()
    with pytest.raises(ContextFailure, match="INVALID_CONTEXT"):
        ContextBuilder().build(raw, binding)


@pytest.mark.parametrize("field", list(ContextBinding.model_fields))
def test_binding_snapshot_mismatch_is_rejected_where_snapshot_carries_the_field(field):
    raw, binding = fixture("v3_guarded_image")
    value = getattr(binding, field)
    changed = (
        UUID(int=900)
        if isinstance(value, UUID)
        else value + 1
        if type(value) is int
        else "f" * 64
        if isinstance(value, str)
        else value.model_copy(update={"revision_no": 2})
    )
    with pytest.raises(ContextFailure, match="CONTEXT_MISMATCH"):
        ContextBuilder().build(raw, binding.model_copy(update={field: changed}))
