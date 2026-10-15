"""P-A03-01/07: exact V2 codec, closed private unions and paired current DTO."""

import copy
import hashlib
from uuid import uuid4

import pytest
from asm.conversations.material import MessageCurrent, TargetResult, TelegramProjectionV2
from asm.conversations.turns import TurnSnapshot, TurnSnapshotV2, parse_snapshot
from asm.messaging.errors import MessagingError
from asm.messaging.http_models import MessageResponse
from asm.messaging.results import MutationInboxProcessingResult, parse_inbox_result
from asm.telegram.normalization import (
    normalize_update,
    normalize_update_v2,
    update_fingerprint,
    update_fingerprint_v2,
)
from pydantic import ValidationError

BOT = "9000001"
DATE = 1792051200


def update(number=101, message=201, *, edit=False, delete=False, **changes):
    body = {
        "business_connection_id": "material-test",
        "chat": {"id": 7000001, "type": "private"},
        "message_id": message,
        "from": {"id": 7000001, "is_bot": False},
        "date": DATE,
        "text": "A",
        **changes,
    }
    if edit:
        return {"update_id": number, "edited_business_message": body}
    if delete:
        return {
            "update_id": number,
            "deleted_business_messages": {
                "business_connection_id": "material-test",
                "chat": {"id": 7000001},
                "message_ids": changes.get("message_ids", [message]),
            },
        }
    return {"update_id": number, "business_message": body}


def photo(fid="F", caption="A"):
    return {
        "photo": [{"width": 2, "height": 3, "file_id": fid, "file_unique_id": "u" + fid}],
        "caption": caption,
    }


def photo_update(number=101, message=201, *, edit=False, fid="F", caption="A", **changes):
    raw = update(number, message, edit=edit, **changes)
    body = raw["edited_business_message" if edit else "business_message"]
    del body["text"]
    body.update(photo(fid, caption))
    if caption is None:
        del body["caption"]
    return raw


@pytest.mark.parametrize(
    "raw",
    [
        update(),
        update(edit=True, edit_date=DATE + 20),
        update(delete=True, message_ids=[8, 2, 8]),
        photo_update(),
        photo_update(edit=True),
        {"update_id": 103},
        {
            "update_id": 104,
            "business_connection": {
                "id": "material-test",
                "user": {"id": 8},
                "date": DATE,
                "is_enabled": True,
            },
        },
    ],
)
def test_p_a03_01_full_legacy_namespace_and_exact_length_vectors(raw):
    projection = normalize_update_v2(BOT, raw)
    assert projection.legacy_v1 == normalize_update(BOT, raw)
    p = projection.model_dump()
    origin, content = p["origin"] or {}, p["content"] or {}
    parts = [
        BOT,
        p["update_id"],
        update_fingerprint(BOT, p["legacy_v1"]),
        p["discriminator"],
        p["chat_type"],
        origin.get("sender_is_bot"),
        origin.get("offline"),
        p["unsupported_reason"],
        p["edited_at"],
        content.get("kind"),
        content.get("selected_unique_id"),
        content.get("reason"),
    ]
    encoded = b"asm:m3:telegram_provenance:v2\n"
    for value in parts:
        encoded += (
            b"-1:\n"
            if value is None
            else str(len(value.encode())).encode() + b":" + value.encode() + b"\n"
        )
    assert update_fingerprint_v2(projection) == hashlib.sha256(encoded).hexdigest()
    assert TelegramProjectionV2.model_validate_json(projection.model_dump_json()) == projection


@pytest.mark.parametrize(
    "change",
    [
        {"is_from_offline": False},
        {"is_from_offline": None},
        {"edit_date": None},
        {"edit_date": True},
        {"edit_date": "1"},
        {"from": None},
        {"chat": {"id": 7000001, "type": None}},
        {"photo": None},
        {"sender_chat": None},
        {"voice": False},
        {"text": None},
    ],
)
def test_p_a03_01_malformed_known_is_not_missing(change):
    with pytest.raises(MessagingError):
        normalize_update_v2(BOT, update(edit=True, **change))


def test_p_a03_01_opaque_photo_tie_unique_id_and_missing_false_are_distinct():
    raw = photo_update()
    first = normalize_update_v2(BOT, raw)
    raw["business_message"]["photo"].append(
        {"width": 2, "height": 3, "file_id": "F", "file_unique_id": "other"}
    )
    with pytest.raises(MessagingError):
        normalize_update_v2(BOT, raw)
    raw = photo_update()
    raw["business_message"]["photo"][0]["file_unique_id"] = "other"
    second = normalize_update_v2(BOT, raw)
    assert first.legacy_v1 == second.legacy_v1
    assert update_fingerprint_v2(first) != update_fingerprint_v2(second)
    assert update_fingerprint_v2(normalize_update_v2(BOT, update())) != update_fingerprint_v2(
        normalize_update_v2(BOT, update(is_from_offline=True))
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("extra", 1),
        ("bot", "09"),
        ("update_id", "999"),
        ("connection", None),
        ("chat_id", None),
        ("message_id", "222"),
        ("sent_at", None),
        ("origin", None),
        ("content", None),
        ("discriminator", "DELETE"),
        ("unsupported_reason", "NONBUSINESS"),
    ],
)
def test_p_a03_01_closed_projection_equality(key, value):
    p = normalize_update_v2(BOT, update()).model_dump()
    p[key] = value
    with pytest.raises(ValidationError):
        TelegramProjectionV2.model_validate(p)


def current(**changes):
    return {
        "schema_version": 1,
        "state": "VISIBLE",
        "content_type": "TEXT",
        "text": "B",
        "image_availability": "NOT_APPLICABLE",
        "changed": True,
        **changes,
    }


@pytest.mark.parametrize(
    "value",
    [
        current(),
        current(changed=False),
        *[
            current(content_type="PHOTO", text=None, image_availability=x)
            for x in (
                "ORIGINAL_PENDING",
                "ORIGINAL_READY",
                "ORIGINAL_FAILED",
                "ORIGINAL_NOT_FETCHED",
                "MEDIA_REPLACED_UNAVAILABLE",
            )
        ],
        *[
            current(state=x, content_type=None, text=None, image_availability="HIDDEN")
            for x in ("DELETED", "ORDER_UNCERTAIN", "UNSUPPORTED_CONTENT")
        ],
    ],
)
def test_p_a03_07_current_complete_matrix(value):
    assert MessageCurrent.model_validate(value).model_dump() == value


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"schema_version": "1"},
        {"changed": 1},
        {"text": ""},
        {"state": "DELETED"},
        {"image_availability": "HIDDEN"},
        {"content_type": None},
        {"text": "\ud800"},
        {"text": "\0"},
        {"text": "x" * 4097},
        {"extra": None},
    ],
)
def test_p_a03_07_closed_current_negative_matrix(change):
    with pytest.raises(ValidationError):
        MessageCurrent.model_validate(current(**change))


def test_p_a03_07_initial_suppressed_history_is_truthful_and_changed_is_versioned():
    body = {
        "message_id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "direction": "INBOUND",
        "content_type": "IMAGE_REFERENCE",
        "text": "original",
        "occurred_at": "2026-10-15T00:00:00.000000Z",
        "created_at": "2026-10-15T00:00:00.000000Z",
        "version": "2",
        "file": None,
        "delivery": None,
        "current": current(),
    }
    assert MessageResponse.model_validate(body).current.text == "B"
    with pytest.raises(ValidationError):
        MessageResponse.model_validate(body | {"version": "1"})
    restored = body | {
        "version": "3",
        "current": current(
            content_type="PHOTO", text="original", image_availability="ORIGINAL_NOT_FETCHED"
        ),
    }
    assert MessageResponse.model_validate(restored).current.changed


@pytest.mark.parametrize(
    "code",
    [
        "APPLIED",
        "NOOP_CONTENT",
        "STALE_EDIT",
        "ALREADY_DELETED",
        "ALREADY_UNCERTAIN",
        "DEFERRED_TARGET",
        "IDENTITY_CONFLICT",
    ],
)
def test_p_a03_01_private_target_union(code):
    value = {
        "ordinal": 1,
        "code": code,
        "target_id": str(uuid4()),
        "message_id": str(uuid4()),
        "effect_id": None,
        "audit_event_id": None,
        "previous_version": "1",
        "accepted_version": "1",
    }
    if code == "APPLIED":
        value.update(effect_id=str(uuid4()), audit_event_id=str(uuid4()), accepted_version="2")
    elif code in ("DEFERRED_TARGET", "IDENTITY_CONFLICT"):
        value.update(message_id=None, previous_version=None, accepted_version=None)
        if code == "IDENTITY_CONFLICT":
            value["target_id"] = None
    assert TargetResult.model_validate(value).code == code
    for change in (
        {"ordinal": True},
        {"extra": None},
        {"accepted_version": "0"},
        {"audit_event_id": "bad"},
    ):
        with pytest.raises(ValidationError):
            TargetResult.model_validate(value | change)
    terminal = {
        "code": "MATERIAL_PROCESSED",
        "inbox_id": str(uuid4()),
        "status": "PROCESSED",
        "message_id": None,
    }
    assert isinstance(parse_inbox_result(terminal), MutationInboxProcessingResult)
    with pytest.raises(ValidationError):
        parse_inbox_result(terminal | {"message_id": str(uuid4())})


def test_r3_t5_saved_v1_decoder_does_not_adopt_new_member_form():
    from test_m3_1_turns import snapshot

    old = snapshot().model_dump(mode="json")
    assert isinstance(parse_snapshot(old), TurnSnapshot)
    assert not isinstance(parse_snapshot(old), TurnSnapshotV2)
    before = copy.deepcopy(old)
    bad = copy.deepcopy(old)
    bad["members"][0]["membership_form"] = "INITIAL_FOLD_SUPPRESSED"
    with pytest.raises(ValidationError):
        parse_snapshot(bad)
    assert old == before


def test_r3_t1_v2_snapshot_keeps_photo_identity_but_consumes_current_text():
    from asm.conversations.turns import consume
    from test_m3_1_turns import snapshot

    value = snapshot().model_dump(mode="json")
    member = value["members"][0] | {
        "content_type": "IMAGE_REFERENCE",
        "message_version": 2,
        "file": None,
        "membership_form": "INITIAL_FOLD_SUPPRESSED",
        "initial_suppression_id": str(uuid4()),
        "current": current(),
    }
    value.update(schema_version=2, members=[member], readiness="COMPLETE")
    result = parse_snapshot(value)
    assert isinstance(result, TurnSnapshotV2) and result.members[0].current.content_type == "TEXT"
    assert consume(result).ready_file_count == consume(result).wait_expired_count == 0
    for invalid in (
        {"schema_version": 2.0},
        {"schema_version": "2"},
        {"members": [member | {"initial_suppression_id": None}]},
        {"members": [member | {"content_type": "TEXT"}]},
        {"members": [member | {"membership_form": None}]},
    ):
        with pytest.raises(ValidationError):
            parse_snapshot(value | invalid)


def test_material_audit_closed_actor_payload_and_accepted_version():
    from asm.billing.models import MessageMaterialAudit

    body = {
        "audit_event_id": str(uuid4()),
        "occurred_at": "2026-10-15T00:00:00.000000Z",
        "correlation_id": str(uuid4()),
        "event_type": "MESSAGE_MATERIAL_CHANGED",
        "object_type": "MESSAGE",
        "object_id": str(uuid4()),
        "object_version": "2",
        "actor_kind": "CHANNEL_EVENT",
        "actor_user_account_id": None,
        "payload": {
            "target_id": str(uuid4()),
            "source_receipt_id": str(uuid4()),
            "previous_version": "1",
            "accepted_version": "2",
            "reason": "CONTENT_CHANGED",
        },
    }
    assert MessageMaterialAudit.model_validate(body).payload.reason == "CONTENT_CHANGED"
    for invalid in (
        {"actor_user_account_id": str(uuid4())},
        {"actor_kind": "USER_ACCOUNT"},
        {"object_version": "3"},
        {"payload": body["payload"] | {"text": "private"}},
        {"payload": body["payload"] | {"accepted_version": "1"}},
    ):
        with pytest.raises(ValidationError):
            MessageMaterialAudit.model_validate(body | invalid)
