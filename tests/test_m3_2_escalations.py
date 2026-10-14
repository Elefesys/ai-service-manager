"""Escalation wire/codec/source checks; these are explicitly not PostgreSQL evidence."""

import hashlib
import importlib.util
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from alembic import op
from asm.billing.models import AuditPage
from asm.billing.validation import TIMESTAMP_PATTERN, decode_cursor, encode_cursor, strict_json
from asm.conversations.escalation_http import escalation_query
from asm.conversations.escalation_http_models import (
    EscalationCancelRequest,
    EscalationCommandResponse,
    EscalationCursor,
    EscalationPage,
    EscalationResolveRequest,
    EscalationView,
)
from asm.conversations.escalations import (
    EscalationCode,
    EscalationError,
    EscalationProgress,
    EscalationTimerResult,
    OwnerEscalationService,
    decision_fingerprint,
)
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import EscalationTimerClaim, TurnJobClaim, parse_claim
from asm.tenancy.types import MembershipRole
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.requests import Request


def expected():
    return dict(
        expected_conversation_id=str(UUID(int=4)),
        expected_client_id=str(UUID(int=5)),
        expected_escalation_version="1",
        expected_control_generation="2",
        expected_context_version="9",
    )


def test_decision_codec_exact_actor_operation_and_utf8_length_no_final_lf():
    answer = " é\ne\u0301 🎨 "
    request = EscalationResolveRequest(**expected(), answer_text=answer)
    prefix = "\n".join(
        (
            "asm:m3:escalation_decision:v1",
            *(str(UUID(int=n)) for n in (1, 2, 3, 4, 5)),
            "RESOLVE",
            "1",
            "2",
            "9",
        )
    )
    wire = prefix.encode() + b"\n" + str(len(answer.encode())).encode() + b":" + answer.encode()
    assert (
        decision_fingerprint(UUID(int=1), UUID(int=2), UUID(int=3), "RESOLVE", request)
        == hashlib.sha256(wire).hexdigest()
    )
    cancel = EscalationCancelRequest(**expected())
    assert (
        decision_fingerprint(UUID(int=1), UUID(int=2), UUID(int=3), "CANCEL", cancel)
        == hashlib.sha256(prefix.replace("RESOLVE", "CANCEL").encode() + b"\n-1:").hexdigest()
    )
    assert request.answer_text == answer
    assert (
        decision_fingerprint(UUID(int=1), UUID(int=6), UUID(int=3), "RESOLVE", request)
        != hashlib.sha256(wire).hexdigest()
    )
    assert EscalationResolveRequest(**expected(), answer_text="🎨" * 512).answer_text == "🎨" * 512


@pytest.mark.parametrize(
    "answer",
    ["", " \t\u00a0", "\x00", "\ud800", "\udfff", "a" * 513, "🎨" * 513, None, 1, True, []],
)
def test_answer_rejects_invalid_scalar_type_and_bounds(answer):
    with pytest.raises(ValidationError):
        EscalationResolveRequest(**expected(), answer_text=answer)


def test_wire_expected_values_no_coercion_and_cancel_has_no_answer():
    for key in expected():
        for value in (None, 1, True, "", "01", "9223372036854775808", "1\n"):
            with pytest.raises(ValidationError):
                EscalationCancelRequest(**(expected() | {key: value}))
    with pytest.raises(ValidationError):
        EscalationCancelRequest(**expected(), answer_text=None)
    for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
        with pytest.raises(ValueError):
            strict_json(raw)
    r = EscalationResolveRequest(**expected(), answer_text="e\u0301")
    assert r.answer_text != "é"


def query(raw):
    return Request({"type": "http", "query_string": raw.encode(), "headers": []})


def test_cursor_is_bounded_exact_scoped_and_filter_bound():
    ws = str(UUID(int=1))
    c = EscalationCursor(
        v=1,
        endpoint="ESCALATIONS",
        workspace_id=ws,
        direction="DESC",
        status="PENDING",
        created_at="2026-10-13T00:00:00.000000Z",
        id=str(UUID(int=2)),
    )
    encoded = encode_cursor(c.model_dump())
    assert escalation_query(query("cursor=" + encoded), ws) == (25, "PENDING", c)
    for raw in (
        "cursor=" + encoded + "&status=ALL",
        "limit=1&limit=2",
        "status=pending",
        "limit=0",
        "limit=101",
        "cursor=" + "a" * 1025,
        "offset=0",
        "status=PENDING&status=PENDING",
    ):
        with pytest.raises(EscalationError):
            escalation_query(query(raw), ws)
    with pytest.raises(EscalationError):
        escalation_query(query("cursor=" + encoded), str(uuid4()))
    for v in (True, 1.0, "1"):
        with pytest.raises(ValidationError):
            EscalationCursor.model_validate(c.model_dump() | {"v": v})


def test_claims_and_private_results_keep_timer_separate_and_dead_has_no_domain_success():
    common = dict(
        job_id=str(uuid4()),
        workspace_id=str(uuid4()),
        connection_id=str(uuid4()),
        inbox_id=None,
        outbox_id=None,
        file_id=None,
        claim_token=str(uuid4()),
        lease_until="2026-10-13T12:00:30Z",
        correlation_id=str(uuid4()),
        attempt_count=1,
    )
    timer = common | dict(kind="ESCALATION_TIMER", escalation_id=str(uuid4()), step="REMIND_1")
    assert isinstance(parse_claim(timer), EscalationTimerClaim)
    for changes in ({"turn_id": str(uuid4())}, {"step": "GROUP"}, {"inbox_id": str(uuid4())}):
        with pytest.raises(ValidationError):
            parse_claim(timer | changes)
    turn = common | dict(
        kind="PROCESS_TURN", turn_id=str(uuid4()), turn_revision=1, step="ESCALATE_OWNER"
    )
    assert isinstance(parse_claim(turn), TurnJobClaim)
    dead = dict(
        job_id=timer["job_id"],
        escalation_id=timer["escalation_id"],
        step="REMIND_1",
        status="DEAD",
        error_code="INVALID_INPUT",
        outcome=None,
        recorded_at=None,
    )
    assert EscalationTimerResult.model_validate(dead).status == "DEAD"
    for changes in (
        {"outcome": "REMINDED"},
        {"recorded_at": "2026-10-13T12:00:00Z"},
        {"error_code": "DEPENDENCY_TIMEOUT"},
        {"status": "SUCCEEDED"},
    ):
        with pytest.raises(ValidationError):
            EscalationTimerResult.model_validate(dead | changes)
    with pytest.raises(ValidationError):
        EscalationProgress(
            code="ALREADY_ESCALATED",
            source_job_id=uuid4(),
            turn_id=uuid4(),
            turn_revision=1,
            escalation_id=None,
        )


@pytest.mark.parametrize(
    "environment,database", [("PRODUCTION", "asm_test"), ("LOCAL", "other"), ("TEST", "other")]
)
async def test_creation_callable_independent_environment_and_database_gates(environment, database):
    engine = create_async_engine(f"postgresql+psycopg://asm_runtime:unused@localhost/{database}")
    db = MessagingDatabase(engine, environment=environment)
    with pytest.raises(MessagingError) as caught:
        await db.request_escalation(None)
    assert caught.value.code == Code.NOT_ALLOWED
    await engine.dispose()


def migration():
    spec = importlib.util.spec_from_file_location(
        "escalations_0011", Path("migrations/versions/0011_escalations.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_migration_profiles_no_legacy_overload_and_refusal_before_ddl():
    m = migration()
    assert (m.revision, m.down_revision) == ("0011", "0010")
    assert len(m.PUBLIC_FUNCTIONS) == 6 and len(m.PRIVATE_FUNCTIONS) == 5
    with patch.object(op, "execute") as execute:
        m.upgrade()
    statements = [str(c.args[0]) for c in execute.call_args_list]
    assert sum(s.startswith("CREATE TABLE ") for s in statements) == 2
    assert not any(
        "CREATE FUNCTION platform.messaging_claim(p_worker text)" in s for s in statements
    )
    with patch.object(op, "execute") as execute:
        m.downgrade()
    reverse = [str(c.args[0]) for c in execute.call_args_list]
    assert reverse[0].startswith("LOCK TABLE")
    assert "55000" in reverse[1] and "ESCALATE_OWNER" in reverse[1]
    assert all(body in reverse for body in m.ORIGINAL.values())
    assert not any("CASCADE" in s for s in reverse)


def test_generated_api_exact_four_routes_closed_dtos_and_mixed_audit_variant():
    api = json.loads(Path("contracts/openapi.json").read_text())
    routes = {p: set(v) for p, v in api["paths"].items() if "/escalations" in p}
    prefix = "/api/v1/workspaces/{workspace_id}/escalations"
    assert routes == {
        prefix: {"get"},
        prefix + "/{escalation_id}": {"get"},
        prefix + "/{escalation_id}/resolve": {"post"},
        prefix + "/{escalation_id}/cancel": {"post"},
    }
    for model in (
        EscalationResolveRequest,
        EscalationCancelRequest,
        EscalationView,
        EscalationPage,
        EscalationCommandResponse,
    ):
        assert model.model_json_schema()["additionalProperties"] is False
    page = api["components"]["schemas"]["EscalationPage"]
    assert (
        set(page["required"]) == set(page["properties"]) == {"items", "next_cursor", "observed_at"}
    )
    assert page["additionalProperties"] is False
    assert page["properties"]["observed_at"] == {
        "type": "string",
        "format": "date-time",
        "pattern": TIMESTAMP_PATTERN,
        "title": "Observed At",
    }
    event = dict(
        audit_event_id=str(uuid4()),
        occurred_at="2026-10-13T12:00:00.000000Z",
        correlation_id=str(uuid4()),
        object_type="ESCALATION",
        object_id=str(uuid4()),
        object_version="2",
        event_type="ESCALATION_DECIDED",
        actor_kind="USER_ACCOUNT",
        actor_user_account_id=str(uuid4()),
        payload={"operation": "RESOLVE", "status": "RESOLVED"},
    )
    assert (
        AuditPage.model_validate(dict(items=[event], next_cursor=None)).items[0].payload.operation
        == "RESOLVE"
    )
    for changes in (
        {"object_type": "MESSAGE"},
        {"object_version": "1"},
        {"actor_user_account_id": None},
        {"payload": {"operation": "RESOLVE", "status": "CANCELLED"}},
        {"payload": event["payload"] | {"answer_text": "private"}},
    ):
        with pytest.raises(ValidationError):
            AuditPage.model_validate(dict(items=[event | changes], next_cursor=None))


PAGE_MOMENT = "2030-01-01T00:01:00.123456Z"


def page_row(number=2):
    """Synthetic projection for validation only; HTTP/PG proof uses normal ingress."""
    return dict(
        workspace_id=str(UUID(int=1)),
        escalation_id=str(UUID(int=number)),
        conversation_id=str(UUID(int=3)),
        client_id=str(UUID(int=4)),
        turn_id=str(UUID(int=5)),
        assignee_user_account_id=str(UUID(int=6)),
        reason="OWNER_DECISION_REQUIRED",
        question="CONTROLLED ESCALATION TEST: требуется решение владельца.",
        policy="LOCAL_TEST_OWNER_WAIT_V1",
        version="1",
        status="PENDING",
        bound_context=dict(
            turn_revision="1", control_generation="2", context_version="3", fingerprint="a" * 64
        ),
        current_context=dict(control_mode="AI", control_generation="2", context_version="3"),
        validity="CURRENT",
        waiting="WAITING_FOR_HUMAN",
        created_at="2030-01-01T00:00:00.000000Z",
        due_at="2030-01-01T00:02:00.000000Z",
        second_reminder_at="2030-01-01T00:05:00.000000Z",
        expires_at="2030-01-01T00:10:00.000000Z",
        observed_at=PAGE_MOMENT,
        reminders=[
            dict(ordinal=1, due_at="2030-01-01T00:02:00.000000Z", recorded_at=None),
            dict(ordinal=2, due_at="2030-01-01T00:05:00.000000Z", recorded_at=None),
        ],
        maintenance="SCHEDULED",
        resolution=None,
        closure=None,
        can_resolve=True,
        can_cancel=True,
    )


@pytest.mark.parametrize(
    "clock",
    [
        {},
        {"observed_at": None},
        {"observed_at": 1},
        {"observed_at": "2030-01-01T00:01:00Z"},
        {"observed_at": "2030-01-01T00:01:00.123456+00:00"},
        {"observed_at": "2030-02-30T00:01:00.123456Z"},
    ],
)
def test_page_requires_canonical_nonnullable_db_timestamp(clock):
    with pytest.raises(ValidationError):
        EscalationPage.model_validate(dict(items=[], next_cursor=None) | clock)


def test_page_clock_empty_nonempty_and_closed_consistent_shape():
    for rows in ([], [page_row()]):
        payload = dict(items=rows, next_cursor=None, observed_at=PAGE_MOMENT)
        assert EscalationPage.model_validate(payload).model_dump(mode="json") == payload
        with pytest.raises(ValidationError):
            EscalationPage.model_validate(payload | {"extra": True})
    with pytest.raises(ValidationError):
        EscalationPage.model_validate(payload | {"observed_at": "2030-01-01T00:01:01.123456Z"})


def list_service(raw):
    unit = SimpleNamespace(
        messaging_membership_role=AsyncMock(return_value=MembershipRole.OWNER),
        escalation_list=AsyncMock(return_value=raw),
    )

    @asynccontextmanager
    async def workspace(token, ws):
        assert token == "session" and ws == UUID(int=1)
        yield unit

    return OwnerEscalationService(SimpleNamespace(workspace=workspace)), unit


@pytest.mark.parametrize("limit,count", [(2, 0), (2, 3), (100, 101)])
async def test_list_envelope_preserves_db_clock_and_bounded_lookahead(limit, count):
    rows = [page_row(i) for i in range(count + 2, 2, -1)]
    service, unit = list_service(dict(items=rows, observed_at=PAGE_MOMENT))
    page = await service.list("session", UUID(int=1), limit, "PENDING", None)
    unit.escalation_list.assert_awaited_once_with(limit + 1, "PENDING", None, None)
    assert page.observed_at == PAGE_MOMENT
    assert [v.model_dump() for v in page.items] == rows[:limit]
    if count > limit:
        assert decode_cursor(page.next_cursor) == dict(
            v=1,
            endpoint="ESCALATIONS",
            workspace_id=str(UUID(int=1)),
            direction="DESC",
            status="PENDING",
            created_at=rows[limit - 1]["created_at"],
            id=rows[limit - 1]["escalation_id"],
        )
    else:
        assert page.next_cursor is None


async def test_list_invalid_envelope_clock_rows_and_lookahead_fail_unavailable():
    envelope = dict(items=[], observed_at=PAGE_MOMENT)
    for raw in (
        [],
        None,
        {},
        {"items": []},
        {"observed_at": PAGE_MOMENT},
        envelope | {"observed_at": None},
        envelope | {"observed_at": "bad"},
        envelope | {"items": None},
        envelope | {"items": {}},
        envelope | {"extra": True},
        envelope | {"items": [{}]},
        envelope | {"items": [page_row()] * 3},  # > limit+1
        envelope | {"items": [page_row() | {"workspace_id": str(UUID(int=99))}]},
        envelope
        | {"items": [page_row(), page_row() | {"observed_at": "2030-01-01T00:01:01.123456Z"}]},
    ):
        service, _ = list_service(raw)
        with pytest.raises(EscalationError) as caught:
            await service.list("session", UUID(int=1), 1, "PENDING", None)
        assert caught.value.code == EscalationCode.UNAVAILABLE
    service, _ = list_service(envelope | {"items": [page_row()]})
    with pytest.raises(EscalationError) as caught:
        await service.list("session", UUID(int=1), 1, "RESOLVED", None)
    assert caught.value.code == EscalationCode.UNAVAILABLE
