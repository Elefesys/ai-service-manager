"""Native Python/ASGI contract and orchestration seams; not PostgreSQL evidence."""

import base64
import copy
import hashlib
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from asm.auth.config import AuthSettings
from asm.auth.crypto import csrf_value, new_token
from asm.auth.http import install_auth
from asm.billing.http import install_billing
from asm.billing.models import AuditPage
from asm.billing.validation import encode_cursor
from asm.conversations.control import ControlCode, ControlError
from asm.conversations.escalation_http_models import EscalationView
from asm.conversations.guards import GuardedTurnSnapshotV3, consume_guarded, parse_guarded_snapshot
from asm.conversations.http import install_control
from asm.conversations.native_context import (
    OwnerNativeContextService,
    decode_observation_cursor,
    reconcile_fingerprint,
)
from asm.conversations.native_context_http import install_native_context, observation_query
from asm.conversations.native_context_http_models import HumanContextState, ReconcileRequest
from asm.conversations.turns import TurnSnapshotV3, consume, native_jsonb, parse_snapshot
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.http import install_messaging
from asm.messaging.results import ContextWorkResultBase, parse_context_work
from asm.messaging.worker import Worker
from asm.tenancy.types import MembershipRole
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request
from test_m3_1_turns import claim as base_claim
from test_m3_2_escalations import page_row

NOW = "2030-01-01T00:00:00.000000Z"
WS, ACTOR, C, CLIENT = (UUID(int=n) for n in (1, 2, 3, 4))


def request_body():
    return dict(
        expected_client_id=str(CLIENT),
        expected_control_generation="1",
        expected_context_version="2",
        expected_policy_epoch="1",
        expected_observation_epoch="0",
        expected_ingress_checkpoint="1",
        expected_input_state_hash="a" * 64,
        expected_revision_id=None,
        disposition="OWNER_TEXT",
        text=" Полный handoff e\u0301 🎨\n",
        source_media="NONE",
        attestation="REVIEWED_AVAILABLE_CONTEXT",
    )


def revision():
    return dict(
        revision_id=str(UUID(int=5)),
        revision_no="1",
        previous_revision_id=None,
        actor_user_account_id=str(ACTOR),
        accepted_at=NOW,
        disposition="OWNER_TEXT",
        text=request_body()["text"],
        source_media="NONE",
        coverage="OWNER_ASSERTED_TEXT_ONLY",
        confirmed_generation="1",
        accepted_context_version="3",
        policy_epoch="1",
        observation_epoch="0",
        reviewed_ingress_checkpoint="1",
        reviewed_input_state_hash="a" * 64,
    )


def sign(value):
    value["snapshot_digest"] = hashlib.sha256(
        native_jsonb(
            {k: v for k, v in value.items() if k not in ("snapshot_digest", "code", "job_id")}
        )
    ).hexdigest()
    return value


def snapshot(*, guarded=False, image=False):
    current = dict(
        schema_version=1,
        state="VISIBLE",
        content_type="PHOTO" if image else "TEXT",
        text="caption" if image else "current",
        image_availability="ORIGINAL_READY" if image else "NOT_APPLICABLE",
        changed=False,
    )
    value = dict(
        code="SNAPSHOT",
        job_id=str(UUID(int=10)),
        schema_version=3,
        workspace_id=str(WS),
        connection_id=str(UUID(int=11)),
        turn_id=str(UUID(int=12)),
        turn_revision=1,
        context_version=4,
        control_generation=2,
        readiness="COMPLETE",
        members=[
            dict(
                message_id=str(UUID(int=13)),
                message_version=1,
                content_type="IMAGE_REFERENCE" if image else "TEXT",
                ingress_at=NOW,
                ingress_seq=2,
                membership_form=None,
                initial_suppression_id=None,
                current=current,
                file=dict(
                    file_id=str(UUID(int=14)),
                    version=2,
                    status="READY",
                    error_code=None,
                    wait_expired=False,
                )
                if image
                else None,
            )
        ],
        human_context=revision(),
        context_policy_epoch="1",
        human_observation_epoch="0",
        resume_receipt_id=str(UUID(int=15)),
        recent_messages=[],
        history_truncated=False,
        coverage_status="OWNER_TEXT",
        context_coverage="OWNER_ASSERTED_TEXT_ONLY",
        context_limitations=["PROVIDER_HISTORY_UNVERIFIED"],
    )
    if guarded:
        value.update(
            conversation_id=str(C),
            client_id=str(CLIENT),
            business_id=str(UUID(int=16)),
            activation_fence_seq=1,
            consumer="CONTROLLED_GUARDS_V1",
        )
    return sign(value)


def cursor():
    return dict(v=1, ws=str(WS), C=str(C), Client=str(CLIENT), P="1", through_N="2", after_N="1")


def query(value):
    return Request({"type": "http", "query_string": value.encode(), "headers": []})


def test_cursor_exact_bytes_order_duplicate_keys_and_types():
    good = encode_cursor(cursor())
    assert decode_observation_cursor(good).model_dump() == cursor()
    assert observation_query(query("")) == (20, None)
    assert observation_query(query("limit=100&cursor=" + good))[0] == 100
    raw = json.dumps(cursor(), separators=(",", ":"))
    bad = [good + "=", "", "A" * 1025, encode_cursor(dict(reversed(list(cursor().items()))))]
    bad += [
        base64.urlsafe_b64encode(s).rstrip(b"=").decode()
        for s in (
            raw.replace('"v":1', '"v":1,"v":1').encode(),
            raw.replace('"v":1', '"v":1.0').encode(),
            raw.replace('"v":1', '"v":true').encode(),
            raw.replace('"P":"1"', '"P":1').encode(),
            raw.replace('"P":"1"', '"P":"01"').encode(),
            b'{"v":1,"bad":"\xff"}',
        )
    ]
    for value in bad:
        with pytest.raises((ValueError, ValidationError)):
            decode_observation_cursor(value)
    for value in (
        "limit=0",
        "limit=01",
        "limit=101",
        "limit=",
        "cursor=",
        "limit=1&limit=2",
        "x=1",
        "cursor=x&cursor=y",
    ):
        with pytest.raises(ControlError, match="INVALID_REQUEST"):
            observation_query(query(value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", ""),
        ("text", " \t\u001c\u00a0"),
        ("text", "\0"),
        ("text", "\ud800"),
        ("text", True),
        ("text", "x" * 4097),
        ("expected_policy_epoch", 1),
        ("expected_observation_epoch", "01"),
        ("expected_revision_id", "BAD"),
        ("expected_input_state_hash", "A" * 64),
        ("disposition", "OTHER"),
        ("attestation", False),
    ],
)
def test_reconcile_strict_scalars_and_bounds(field, value):
    with pytest.raises(ValidationError):
        ReconcileRequest.model_validate(request_body() | {field: value})


def test_text_disposition_and_whole_field_fingerprint():
    body = ReconcileRequest.model_validate(request_body())
    assert body.text == request_body()["text"]
    assert (
        ReconcileRequest.model_validate(request_body() | {"text": "🎨" * 4096}).text == "🎨" * 4096
    )
    assert (
        ReconcileRequest.model_validate(
            request_body() | {"disposition": "UNRESOLVED", "text": None}
        ).text
        is None
    )
    with pytest.raises(ValidationError):
        ReconcileRequest.model_validate(request_body() | {"disposition": "CANONICAL_SUFFICIENT"})
    values = [
        str(WS),
        str(ACTOR),
        str(C),
        *[
            request_body()[k]
            for k in (
                "expected_client_id",
                "expected_control_generation",
                "expected_context_version",
                "expected_policy_epoch",
                "expected_observation_epoch",
                "expected_ingress_checkpoint",
                "expected_input_state_hash",
                "expected_revision_id",
                "disposition",
                "text",
                "source_media",
                "attestation",
            )
        ],
    ]
    golden = b"asm:m3:human_context_reconcile:v1\n" + b"".join(
        b"-1:\n" if v is None else f"{len(v.encode())}:{v}\n".encode() for v in values
    )
    assert reconcile_fingerprint(WS, ACTOR, C, body) == hashlib.sha256(golden).hexdigest()
    assert reconcile_fingerprint(WS, UUID(int=20), C, body) != hashlib.sha256(golden).hexdigest()
    for field in request_body():
        changed = request_body()
        if field.startswith("expected_") and field != "expected_revision_id":
            changed[field] = (
                str(UUID(int=40))
                if field == "expected_client_id"
                else "b" * 64
                if field.endswith("hash")
                else str(int(changed[field]) + 1)
            )
        elif field == "expected_revision_id":
            changed[field] = str(UUID(int=40))
        elif field == "text":
            changed[field] += "x"
        elif field == "source_media":
            changed[field] = "UNAVAILABLE"
        elif field == "disposition":
            changed[field] = "UNRESOLVED"
        else:
            continue  # attestation is a single literal, not an alternative command.
        assert (
            reconcile_fingerprint(WS, ACTOR, C, ReconcileRequest.model_validate(changed))
            != hashlib.sha256(golden).hexdigest()
        )


def test_v3_exact_dispatch_digest_full_owner_text_and_current_counts():
    for guarded in (False, True):
        value = snapshot(guarded=guarded, image=True)
        parsed = parse_guarded_snapshot(value) if guarded else parse_snapshot(value)
        assert type(parsed) is (GuardedTurnSnapshotV3 if guarded else TurnSnapshotV3)
        assert parsed.human_context.text == request_body()["text"]
        assert consume(parsed).ready_file_count == 1
        if guarded:
            assert consume_guarded(parsed).snapshot_digest == value["snapshot_digest"]
        before = copy.deepcopy(value)
        parsed.model_dump_json()
        assert before == value
    assert (
        native_jsonb({"bbb": 1, "aa": [True, None, "e\u0301"], "a": "🎨"})
        == '{"a": "🎨", "aa": [true, null, "e\u0301"], "bbb": 1}'.encode()
    )
    value = snapshot(image=True)
    value["members"][0]["file"].update(status="PENDING", wait_expired=True, version=1)
    value["members"][0]["current"]["image_availability"] = "ORIGINAL_PENDING"
    value["readiness"] = "PARTIAL"
    assert consume(parse_snapshot(sign(value))).wait_expired_count == 1
    value["members"][0]["current"]["image_availability"] = "MEDIA_REPLACED_UNAVAILABLE"
    value["members"][0]["current"]["changed"] = True
    value["members"][0]["message_version"] = 2
    assert consume(parse_snapshot(sign(value))).wait_expired_count == 0


def test_v1_v2_saved_payload_digest_and_effective_file_counts_are_retained():
    from test_m3_1_turns import snapshot as retained_snapshot

    v1 = retained_snapshot().model_dump(mode="json")
    v2 = copy.deepcopy(v1)
    v2["schema_version"] = 2
    for member in v2["members"]:
        member.update(
            membership_form=None,
            initial_suppression_id=None,
            current=dict(
                schema_version=1,
                state="VISIBLE",
                content_type="TEXT" if member["content_type"] == "TEXT" else "PHOTO",
                text="retained" if member["content_type"] == "TEXT" else None,
                image_availability="NOT_APPLICABLE"
                if member["file"] is None
                else "ORIGINAL_" + member["file"]["status"],
                changed=False,
            ),
        )
    for value in (v1, v2):
        before = json.dumps(value, ensure_ascii=False, sort_keys=True)
        parsed = parse_snapshot(value)
        assert (
            json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) == before
        )
        assert parsed.snapshot_digest == "a" * 64
        result = consume(parsed)
        assert (result.member_count, result.ready_file_count, result.wait_expired_count) == (
            4,
            1,
            1,
        )


def test_completed_delivery_history_contract_refuses_raw_pg_timestamp_spelling():
    value = snapshot()
    entry = dict(
        message_id=str(UUID(int=51)),
        version="1",
        direction="OUTBOUND",
        origin="OWNER_MANUAL",
        created_at=NOW,
        current=value["members"][0]["current"],
        file=None,
        delivery=dict(
            status="SENT", error_code=None, completed_at="2030-01-01T00:00:00+00:00", version="2"
        ),
    )
    value["recent_messages"] = [entry]
    # Source-supported DB/contract discrepancy, not an executed PG conversion.
    with pytest.raises(ValidationError, match="completed_at"):
        parse_snapshot(sign(value))
    entry["delivery"]["completed_at"] = NOW
    assert parse_snapshot(sign(value)).recent_messages[0].delivery.status == "SENT"
    entry["delivery"].update(status="UNKNOWN", error_code="UNKNOWN_EXTERNAL_RESULT")
    assert parse_snapshot(sign(value)).recent_messages[0].delivery.status == "UNKNOWN"


def test_v3_capacity_is_checked_before_any_consumer():
    value = snapshot()
    value["oversized_untrusted_field"] = "x" * 2097153
    with pytest.raises(ValidationError, match="size/digest"):
        parse_snapshot(sign(value))


def test_v3_owner_handoff_survives_truncated_tail_and_native_media_is_partial():
    value = snapshot()
    value["recent_messages"] = [
        dict(
            message_id=str(UUID(int=100 + i)),
            version="1",
            direction="INBOUND",
            origin="CLIENT_INBOUND",
            created_at=f"2030-01-01T00:00:{i:02d}.000000Z",
            current=value["members"][0]["current"],
            delivery=None,
            file=None,
        )
        for i in range(16)
    ]
    value["history_truncated"] = True
    assert parse_snapshot(sign(value)).human_context.text == request_body()["text"]
    value["human_context"]["source_media"] = "UNAVAILABLE"
    value["context_limitations"].append("NATIVE_MEDIA_UNAVAILABLE")
    with pytest.raises(ValidationError):
        parse_snapshot(sign(value))
    value["readiness"] = "PARTIAL"
    assert parse_snapshot(sign(value)).context_limitations == (
        "PROVIDER_HISTORY_UNVERIFIED",
        "NATIVE_MEDIA_UNAVAILABLE",
    )
    value["human_context"].update(
        disposition="CANONICAL_SUFFICIENT", text=None, source_media="NONE"
    )
    value.update(
        coverage_status="CANONICAL_COMPLETE", context_limitations=["PROVIDER_HISTORY_UNVERIFIED"]
    )
    with pytest.raises(ValidationError):
        parse_snapshot(sign(value))
    value["history_truncated"] = False
    assert parse_snapshot(sign(value)).coverage_status == "CANONICAL_COMPLETE"


@pytest.mark.parametrize(
    "case",
    [
        "version_bool",
        "version_float",
        "version_null",
        "version_unknown",
        "counter_bool",
        "counter_string",
        "foreign_policy",
        "unresolved",
        "canonical_truncated",
        "limitations",
        "history_duplicate",
        "member_duplicate",
        "file_bool",
        "file_error",
        "unknown_key",
        "digest",
        "owner_text_oversize",
    ],
)
@pytest.mark.parametrize("guarded", [False, True])
def test_resigned_v3_negatives(case, guarded):
    v = snapshot(guarded=guarded, image=True)
    if case.startswith("version_"):
        v["schema_version"] = {
            "version_bool": True,
            "version_float": 3.0,
            "version_null": None,
            "version_unknown": 4,
        }[case]
    elif case == "counter_bool":
        v["turn_revision"] = True
    elif case == "counter_string":
        v["members"][0]["message_version"] = "1"
    elif case == "foreign_policy":
        v["human_context"]["policy_epoch"] = "2"
    elif case == "unresolved":
        v["human_context"]["disposition"] = "UNRESOLVED"
    elif case == "canonical_truncated":
        v["human_context"].update(disposition="CANONICAL_SUFFICIENT", text=None)
        v.update(coverage_status="CANONICAL_COMPLETE", history_truncated=True)
    elif case == "limitations":
        v["context_limitations"] = []
    elif case == "member_duplicate":
        v["members"] *= 2
    elif case == "file_bool":
        v["members"][0]["file"]["wait_expired"] = 0
    elif case == "file_error":
        v["members"][0]["file"]["error_code"] = "SECRET"
    elif case == "unknown_key":
        v["private_pointer"] = "bad"
    elif case == "owner_text_oversize":
        v["human_context"]["text"] = "a" * 4097
    elif case == "history_duplicate":
        entry = dict(
            message_id=str(UUID(int=50)),
            version="1",
            direction="INBOUND",
            origin="CLIENT_INBOUND",
            created_at=NOW,
            current=v["members"][0]["current"],
            delivery=None,
            file=dict(file_id=str(UUID(int=14)), version="2", status="READY"),
        )
        v["recent_messages"] = [entry, entry]
    if case != "version_float":
        sign(v)
    else:
        v["snapshot_digest"] = "b" * 64
    if case == "digest":
        v["snapshot_digest"] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        (parse_guarded_snapshot if guarded else parse_snapshot)(v)


@pytest.mark.parametrize("version", [True, 2.0, None, 1, "3"])
def test_unknown_version_never_uses_v1_fallback(version):
    for parse in (parse_snapshot, parse_guarded_snapshot):
        with pytest.raises((ValidationError, ValueError)):
            parse(snapshot() | {"schema_version": version})


def work_result(claim, code="CONTEXT_WAIT"):
    return dict(
        code=code,
        job_id=str(claim.job_id),
        turn_id=str(getattr(claim, "turn_id", UUID(int=12))),
        turn_revision=1,
        outbox_id=str(claim.outbox_id) if claim.outbox_id else None,
        status="READY" if code == "CONTEXT_WAIT" else "DEAD",
        reason="CONTEXT_INPUT_PENDING"
        if code == "CONTEXT_WAIT"
        else "CONTEXT_WAIT_EXHAUSTED"
        if code == "CONTEXT_WAIT_EXHAUSTED"
        else "NEW_OBSERVATION",
        available_at=NOW if code == "CONTEXT_WAIT" else None,
        recorded_at=NOW,
    )


def boundary_claim(boundary):
    claim = base_claim("SEND_GUARDED_TEXT" if boundary == "send" else "PROCESS_TURN")
    if boundary == "send":
        return claim.model_copy(update={"outbox_id": UUID(int=80)})
    return claim.model_copy(
        update={
            "step": "ESCALATE_OWNER"
            if boundary == "escalation"
            else "GUARDED_TEXT"
            if boundary in ("prepare", "accept")
            else "TEST_CONSUME"
        }
    )


def test_context_work_closed_variants_never_become_permits():
    claim = boundary_claim("prepare")
    for code in ("CONTEXT_WAIT", "CONTEXT_WAIT_EXHAUSTED", "CONTEXT_HOLD"):
        value = work_result(claim, code)
        assert isinstance(parse_context_work(value), ContextWorkResultBase)
        for changes in (
            {"turn_revision": True},
            {"status": "RUNNING"},
            {"reason": "CURRENT"},
            {"permit": True},
            {"recorded_at": NOW.replace("01T", "99T")},
        ):
            with pytest.raises(ValidationError):
                parse_context_work(value | changes)


async def boundary_call(db, boundary, claim):
    if boundary == "prepare":
        return await db.prepare_guarded_turn(claim)
    if boundary == "accept":
        return await db.accept_guarded_text(claim, "a" * 64, "CONTROLLED GUARDS TEST")
    if boundary == "send":
        return await db.begin_guarded_send(claim)
    if boundary == "escalation":
        return await db.request_escalation(claim)
    if boundary == "test_prepare":
        return await db.process_turn(claim)
    return await db.finish_turn(claim, consume(parse_snapshot(snapshot())))


def wrapper_seam(monkeypatch, claim, outcome, failure=None):
    """Actual wrappers/parser/worker; only SQL/commit is instrumented unit seam."""
    import asm.messaging.database as module

    db = MessagingDatabase(
        SimpleNamespace(
            url=SimpleNamespace(
                drivername="postgresql+psycopg", username="asm_runtime", database="asm_test"
            )
        ),
        environment="TEST",
    )
    state = dict(durable=None, pending=None, writes=0, admissions=0, commits=0)

    @asynccontextmanager
    async def transaction():
        try:
            yield None
            if state["pending"] is not None:
                if failure == "rollback":
                    raise SQLAlchemyError("unit commit failure")
                state["durable"] = state["pending"]
                state["commits"] += 1
                state["pending"] = None
                if failure == "ack":
                    raise SQLAlchemyError("unit lost ACK")
        finally:
            state["pending"] = None

    async def call(connection, sql, params):
        if "to_regprocedure" in sql:
            return True
        if "human_context_work_replay" in sql:
            if state["durable"] is not None:
                return state["durable"]
            raise MessagingError(Code.STALE_CLAIM)
        if "_replay(" in sql:
            raise MessagingError(Code.STALE_CLAIM)
        state["writes"] += 1
        state["pending"] = outcome
        return outcome

    @asynccontextmanager
    async def admit(*args):
        async with transaction():
            state["admissions"] += 1
            yield SimpleNamespace(_execute=lambda sql: call(None, sql, {}))

    monkeypatch.setattr(db, "_transaction", transaction)
    monkeypatch.setattr(db, "admit_job", admit)
    monkeypatch.setattr(module, "call", call)
    return db, state


@pytest.mark.parametrize(
    "boundary", ["prepare", "accept", "send", "escalation", "test_prepare", "test_finalize"]
)
@pytest.mark.parametrize("code", ["CONTEXT_WAIT", "CONTEXT_WAIT_EXHAUSTED", "CONTEXT_HOLD"])
async def test_six_wrappers_commit_context_outcome_and_replay_without_admission(
    monkeypatch, boundary, code
):
    claim = boundary_claim(boundary)
    raw = work_result(claim, code)
    db, state = wrapper_seam(monkeypatch, claim, raw)
    result = await boundary_call(db, boundary, claim)
    assert state["durable"] == raw and state["commits"] == state["writes"] == 1
    admissions = state["admissions"]
    assert await boundary_call(db, boundary, claim) == result
    assert state["admissions"] == admissions and state["writes"] == 1
    adapter = ControlledAdapter(environment="TEST")
    if boundary in ("prepare", "send", "escalation", "test_prepare"):
        await Worker(db, adapter).execute(claim)
        assert state["writes"] == 1 and adapter.calls == 0


@pytest.mark.parametrize(
    "boundary", ["prepare", "accept", "send", "escalation", "test_prepare", "test_finalize"]
)
@pytest.mark.parametrize("failure", ["rollback", "ack"])
async def test_six_wrappers_never_return_optimistic_schedule_on_commit_failure(
    monkeypatch, boundary, failure
):
    claim = boundary_claim(boundary)
    raw = work_result(claim)
    db, state = wrapper_seam(monkeypatch, claim, raw, failure)
    with pytest.raises(SQLAlchemyError):
        await boundary_call(db, boundary, claim)
    assert (state["durable"] is not None) == (failure == "ack")
    if failure == "ack":
        assert (
            await db.replay_context_work(claim.job_id, claim.claim_token)
        ).code == "CONTEXT_WAIT"
        adapter = ControlledAdapter(environment="TEST")
        await Worker(db, adapter).execute(claim)
        assert adapter.calls == 0 and state["writes"] == 1
    else:
        with pytest.raises(MessagingError, match="STALE_CLAIM"):
            await db.replay_context_work(claim.job_id, claim.claim_token)


def test_escalation_hold_is_required_visible_and_never_resolvable():
    row = page_row()
    row.update(
        context_hold=dict(
            reason="NEW_OBSERVATION",
            policy="ON",
            policy_epoch="1",
            observation_epoch="1",
            coverage_status="OWNER_TEXT",
        ),
        can_resolve=False,
    )
    assert EscalationView.model_validate(row).context_hold.reason == "NEW_OBSERVATION"
    for changes in (
        {"can_resolve": True},
        {"validity": "CONTEXT_CHANGED"},
        {"context_hold": {**row["context_hold"], "secret": "bad"}},
    ):
        with pytest.raises(ValidationError):
            EscalationView.model_validate(row | changes)


def current_state():
    return dict(
        workspace_id=str(WS),
        conversation_id=str(C),
        client_id=str(CLIENT),
        observed_at=NOW,
        control_mode="HUMAN",
        control_generation="1",
        context_version="2",
        policy="ON",
        policy_epoch="1",
        observation_epoch="0",
        ingress_checkpoint="1",
        input_state_hash="a" * 64,
        input_gap_limit_exceeded=False,
        has_unsequenced_context_input=False,
        current_revision=None,
        review_status="BOOTSTRAP_REQUIRED",
        context_blockers=["CONTEXT_CONFIRMATION_REQUIRED"],
        resume_blockers=["CONTEXT_CONFIRMATION_REQUIRED"],
        history_truncated=False,
        coverage_status="UNCONFIRMED",
        pending_context_input=False,
        has_failed_context_input=False,
        unreviewed_failed_context_input=False,
        automation_work=dict(state="IDLE", reason=None, job_id=None, turn_id=None, observed_at=NOW),
        manual_delivery=dict(has_dispatching=False, has_unknown=False),
    )


def test_current_policy_read_order_and_work_identity_are_closed():
    assert HumanContextState.model_validate(current_state()).current_revision is None
    paused = current_state() | dict(
        policy="PAUSED",
        control_mode="AI",
        review_status="POLICY_PAUSED",
        context_blockers=["POLICY_PAUSED", "CONTEXT_CONFIRMATION_REQUIRED"],
        resume_blockers=["POLICY_PAUSED", "HUMAN_REQUIRED", "CONTEXT_CONFIRMATION_REQUIRED"],
    )
    HumanContextState.model_validate(paused)
    with pytest.raises(ValidationError):
        HumanContextState.model_validate(
            paused
            | {
                "resume_blockers": [
                    "POLICY_PAUSED",
                    "CONTEXT_CONFIRMATION_REQUIRED",
                    "HUMAN_REQUIRED",
                ]
            }
        )
    with pytest.raises(ValidationError):
        HumanContextState.model_validate(current_state() | {"policy_epoch": "0"})


@pytest.mark.parametrize("failure", [False, True])
async def test_owner_service_commit_before_acceptance_and_historical_replay(monkeypatch, failure):
    body = ReconcileRequest.model_validate(request_body())
    events = []
    result = dict(
        workspace_id=str(WS),
        conversation_id=str(C),
        client_id=str(CLIENT),
        receipt_id=str(UUID(int=5)),
        revision_id=str(UUID(int=5)),
        revision_no="1",
        previous_revision_id=None,
        audit_event_id=str(UUID(int=6)),
        control_generation="1",
        previous_context_version="2",
        accepted_context_version="3",
        policy_epoch="1",
        observation_epoch="0",
        reviewed_ingress_checkpoint="1",
        reviewed_input_state_hash="a" * 64,
        disposition="OWNER_TEXT",
        source_media="NONE",
        coverage="OWNER_ASSERTED_TEXT_ONLY",
        accepted_at=NOW,
    )

    async def role():
        return MembershipRole.OWNER

    async def reconcile(*args):
        events.append("sql")
        return dict(outcome="REPLAY", result=result)

    @asynccontextmanager
    async def workspace(*args):
        yield SimpleNamespace(messaging_membership_role=role, human_context_reconcile=reconcile)
        if failure:
            raise SQLAlchemyError("unit commit failure")
        events.append("commit")

    service = OwnerNativeContextService(SimpleNamespace(workspace=workspace))
    if failure:
        with pytest.raises(SQLAlchemyError):
            await service.reconcile("unit", WS, C, body, "key")
        assert events == ["sql"]
    else:
        assert (await service.reconcile("unit", WS, C, body, "key")).outcome == "REPLAY"
        assert events == ["sql", "commit"]


class WireSeam:
    """Synthetic SQL responses only; real auth middleware/CSRF/routes/services."""

    def __init__(self):
        self.calls = 0
        self.commits = 0
        self.fail_commit = False
        self.error = None
        self.role = MembershipRole.OWNER

    @asynccontextmanager
    async def workspace(self, token, workspace):
        self.calls += 1
        yield self
        if self.fail_commit:
            raise SQLAlchemyError("unit commit failure")
        self.commits += 1

    async def messaging_membership_role(self):
        return self.role

    async def human_context_read(self, cid):
        return current_state()

    async def human_context_observations(self, cid, limit, decoded):
        return dict(
            items=[], next_cursor=None, through_epoch="0", current_epoch="0", observed_at=NOW
        )

    async def human_context_reconcile(self, cid, key, body):
        if self.error:
            raise ControlError(self.error)
        return dict(
            outcome="REPLAY",
            result=dict(
                workspace_id=str(WS),
                conversation_id=str(C),
                client_id=body["expected_client_id"],
                receipt_id=str(UUID(int=5)),
                revision_id=str(UUID(int=5)),
                revision_no="1",
                previous_revision_id=None,
                audit_event_id=str(UUID(int=6)),
                control_generation=body["expected_control_generation"],
                previous_context_version=body["expected_context_version"],
                accepted_context_version=str(int(body["expected_context_version"]) + 1),
                policy_epoch=body["expected_policy_epoch"],
                observation_epoch=body["expected_observation_epoch"],
                reviewed_ingress_checkpoint=body["expected_ingress_checkpoint"],
                reviewed_input_state_hash=body["expected_input_state_hash"],
                disposition=body["disposition"],
                source_media=body["source_media"],
                coverage="OWNER_ASSERTED_TEXT_ONLY",
                accepted_at=NOW,
            ),
        )


@asynccontextmanager
async def wire():
    auth, app = WireSeam(), FastAPI()
    settings = AuthSettings(auth_peer_limit=1000, auth_global_limit=10000)
    install_auth(app, auth, settings)
    install_billing(app, auth, settings)
    install_messaging(app, auth, settings, environment="TEST")
    install_control(app, auth, settings)
    install_native_context(app, auth, settings)
    token = new_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        client.cookies.set(settings.auth_cookie_name, token)
        yield (
            auth,
            app,
            client,
            dict(
                Origin="http://localhost:8000",
                **{"X-CSRF-Token": csrf_value(token), "Idempotency-Key": "wire"},
            ),
        )


def route(suffix="human-context"):
    return f"/api/v1/workspaces/{WS}/conversations/{C}/{suffix}"


async def test_three_asgi_routes_exact_body_cap_cookie_csrf_and_strict_order():
    async with wire() as (auth, app, client, headers):
        r = await client.get(route())
        assert (
            r.status_code == 200
            and r.json() == current_state()
            and r.headers["cache-control"] == "no-store"
        )
        assert (await client.get(route("human-context/observations"))).json()["items"] == []
        raw = json.dumps(request_body(), ensure_ascii=False, separators=(",", ":")).encode()
        raw += b" " * (4096 - len(raw))
        assert len(raw) == 4096
        response = await client.post(
            route("human-context/reconcile"),
            content=raw,
            headers=headers | {"Content-Type": "application/json"},
        )
        assert response.status_code == 200 and response.json()["outcome"] == "REPLAY"
        before = auth.calls
        for payload in (raw + b" ", raw + b" " * (65536 - len(raw))):
            too_big = await client.post(
                route("human-context/reconcile"),
                content=payload,
                headers=headers | {"Content-Type": "application/json"},
            )
            assert too_big.status_code == 413 and too_big.json() == {
                "error": {"code": "BODY_TOO_LARGE"}
            }
        assert auth.calls == before
        for bad in (
            b'{"text":"a","text":"b"}',
            b'{"x":NaN}',
            b"[]",
            b"{}",
            json.dumps(request_body() | {"extra": True}).encode(),
        ):
            r = await client.post(
                route("human-context/reconcile"),
                content=bad,
                headers=headers | {"Content-Type": "application/json"},
            )
            assert r.status_code == 422 and r.headers["cache-control"] == "no-store"
        assert auth.calls == before
        # Header/key/query before cookie/strict body, after middleware Origin/body.
        client.cookies.clear()
        assert (await client.get(route() + "?x=1")).status_code == 422
        assert (await client.get(route())).status_code == 401
        assert (
            await client.post(
                route("human-context/reconcile"),
                json={},
                headers={"Origin": "http://localhost:8000"},
            )
        ).status_code == 422
        assert (
            await client.post(
                route("human-context/reconcile"),
                json={},
                headers=headers | {"Origin": "https://foreign.invalid"},
            )
        ).status_code == 403
        assert auth.calls == before


async def test_asgi_native_errors_and_failed_outer_commit_have_no_optimistic_result():
    async with wire() as (auth, app, client, headers):
        for code in (
            ControlCode.CONTEXT_POLICY_INACTIVE,
            ControlCode.CONTEXT_POLICY_PAUSED,
            ControlCode.HUMAN_REQUIRED,
            ControlCode.CONTEXT_CONFIRMATION_REQUIRED,
            ControlCode.CONTEXT_UNRESOLVED,
            ControlCode.CONTEXT_INPUT_PENDING,
            ControlCode.CONTEXT_INPUT_UNRESOLVED,
            ControlCode.CONTEXT_COVERAGE_REQUIRED,
            ControlCode.STALE_STATE,
            ControlCode.VERSION_EXHAUSTED,
        ):
            auth.error = code
            r = await client.post(
                route("human-context/reconcile"), json=request_body(), headers=headers
            )
            assert r.status_code == 409 and r.json() == {"error": {"code": code.value}}
        assert auth.commits == 0
        auth.error, auth.fail_commit = None, True
        r = await client.post(
            route("human-context/reconcile"), json=request_body(), headers=headers
        )
        assert r.status_code == 503 and "result" not in r.json() and auth.commits == 0
        auth.fail_commit, auth.role = False, MembershipRole.PROVIDER
        assert (await client.get(route())).status_code == 403


def test_native_audit_variants_are_redacted_and_version_bound():
    common = dict(
        audit_event_id=str(UUID(int=60)),
        occurred_at=NOW,
        correlation_id=str(UUID(int=61)),
        object_id=str(C),
        object_version="3",
    )
    reconciled = common | dict(
        event_type="HUMAN_CONTEXT_RECONCILED",
        object_type="CONVERSATION",
        actor_kind="USER_ACCOUNT",
        actor_user_account_id=str(ACTOR),
        payload=dict(
            revision_id=str(UUID(int=5)),
            previous_revision_id=None,
            disposition="OWNER_TEXT",
            source_media="NONE",
            control_generation="1",
            previous_context_version="2",
            accepted_context_version="3",
            policy_epoch="1",
            observation_epoch="0",
            reviewed_ingress_checkpoint="1",
        ),
    )
    policy = common | dict(
        event_type="HUMAN_CONTEXT_POLICY_COMMANDED",
        object_type="CHANNEL_CONNECTION",
        object_version="1",
        actor_kind="LOCAL_PROVISIONER",
        actor_user_account_id=None,
        payload=dict(
            receipt_id=str(UUID(int=62)),
            operation="ENABLE",
            change="ENABLED",
            previous_policy="OFF_UNUSED",
            accepted_policy="ON",
            previous_policy_epoch="0",
            accepted_policy_epoch="1",
        ),
    )
    page = AuditPage.model_validate(dict(items=[reconciled, policy], next_cursor=None))
    assert page.items[0].payload.accepted_context_version == "3"
    for event in (reconciled, policy):
        for changes in (
            {"object_version": "99"},
            {"payload": event["payload"] | {"text": "protected"}},
            {"payload": event["payload"] | {"digest": "a" * 64}},
        ):
            with pytest.raises(ValidationError):
                AuditPage.model_validate(dict(items=[event | changes], next_cursor=None))
