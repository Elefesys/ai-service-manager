"""Python boundary tests; no mocked operation is described as PG evidence."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from asm.ai.database import AIDatabase, DurableAdapter, decoded, runtime_config
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_contracts import CallCompletion, PreparedRun, RuntimeReceipt
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AIJobClaim, TurnJobClaim, parse_claim
from pydantic import ValidationError
from test_m4_agent import config
from test_m4_context import fixture
from test_m4_gateway import request


def prepared():
    raw, binding = fixture("v3_owner")
    from decimal import Decimal

    from asm.ai.contracts import Budget

    return PreparedRun(
        run_id=uuid4(),
        binding=binding,
        snapshot=raw,
        storage_fingerprint="a" * 64,
        config=config(),
        deadline=datetime.now(UTC) + timedelta(seconds=30),
        reads_used=0,
        budget=Budget(
            calls_used=0,
            reads_reserved=0,
            tokens_reserved=0,
            cost_reserved=Decimal(0),
            currency="RUB",
        ),
    )


def test_ai_claim_is_distinct_from_controlled_consumer_and_hides_token():
    run = prepared()
    claim = parse_claim(
        dict(
            job_id=run.binding.job_id,
            workspace_id=run.binding.workspace_id,
            connection_id=run.binding.connection_id,
            kind="PROCESS_TURN",
            step="AI_GENERATE",
            turn_id=run.binding.turn_id,
            turn_revision=1,
            claim_token=uuid4(),
            lease_until=run.deadline,
            correlation_id=uuid4(),
            attempt_count=1,
            inbox_id=None,
            outbox_id=None,
        )
    )
    assert isinstance(claim, AIJobClaim) and not isinstance(claim, TurnJobClaim)
    assert str(claim.claim_token) not in repr(claim)


@pytest.mark.parametrize("field,value", [("model_calls", 3), ("read_executions", 2)])
def test_runtime_rejects_larger_agent_budget(field, value):
    with pytest.raises(MessagingError, match="NOT_ALLOWED"):
        runtime_config(config(**{field: value}))


def test_runtime_requires_explicit_test_environment_and_fake_configuration():
    with pytest.raises(MessagingError, match="NOT_ALLOWED"):
        AIDatabase(None, environment="PRODUCTION")
    cfg = config()
    from asm.ai.contracts import GatewayConfig

    paid = GatewayConfig.model_validate(
        cfg.model_dump()
        | {"route": cfg.route.model_dump() | {"execution": "PROVIDER", "adapter": "polza"}}
    )
    with pytest.raises(MessagingError, match="NOT_ALLOWED"):
        runtime_config(paid)


def test_wire_roundtrip_keeps_original_snapshot_and_unknown_distinct_from_zero():
    run = prepared()
    restored = decoded(PreparedRun, run.model_dump(mode="json"))
    assert restored.snapshot == run.snapshot
    assert restored == run
    assert CallCompletion(kind="UNKNOWN").cost.amount is None
    assert CallCompletion(kind="UNKNOWN").usage.input_tokens is None
    with pytest.raises(ValidationError):
        CallCompletion(kind="UNKNOWN", wire_response="secret")


@pytest.mark.parametrize("phase", ["reserve", "provider", "complete", "cancel"])
async def test_reservation_and_completion_failure_never_repeat_adapter(phase):
    from decimal import Decimal

    from asm.ai.contracts import AdapterRequest, Budget

    run = prepared()
    events = []
    active_transaction = False

    class Store:
        async def reserve(self, *args):
            nonlocal active_transaction
            active_transaction = True
            events.append("reservation")
            active_transaction = False
            if phase == "reserve":
                raise MessagingError(Code.AI_BUDGET)
            return 1

        async def complete(self, *args):
            events.append("completion:" + args[-1].kind)
            if phase in {"complete", "cancel"}:
                raise MessagingError(Code.STALE_CLAIM)

    class Adapter(FakeAdapter):
        async def complete(self, request):
            assert not active_transaction and events == ["reservation"]
            events.append("provider")
            if phase == "provider":
                raise RuntimeError("primary")
            if phase == "cancel":
                raise asyncio.CancelledError()
            return await super().complete(request)

    adapter = Adapter(run.config.route)
    wrapped = DurableAdapter(Store(), None, run, adapter)
    charged = Budget(
        calls_used=1,
        reads_reserved=0,
        tokens_reserved=1000,
        cost_reserved=Decimal("0.10"),
        currency="RUB",
    )
    value = AdapterRequest(
        config=run.config,
        request=request(),
        prompt="synthetic",
        output_schema_json="{}",
        exchanges=(),
        budget=charged,
        remaining_seconds=5.0,
    )
    with pytest.raises((MessagingError, RuntimeError, asyncio.CancelledError)):
        await wrapped.complete(value)
    assert events.count("provider") == (phase != "reserve")
    assert events[0] == "reservation"
    if phase in {"provider", "cancel"}:
        assert events[-1] == "completion:UNKNOWN"


async def test_authority_sends_claim_independently_of_untrusted_binding():
    from asm.ai.database import PostgresAuthority

    run = prepared()
    claim = object()
    other = run.binding.model_copy(update={"client_id": uuid4(), "workspace_id": uuid4()})
    calls = []

    class Store:
        async def _command(self, principal, operation, **payload):
            calls.append((principal, operation, payload))
            raise MessagingError(Code.AI_STALE)

    authority = PostgresAuthority(Store(), claim, run)
    assert (await authority.authorize(other, "MODEL")).status == "STALE"
    assert calls[0][0] is claim
    assert calls[0][2]["run_id"] == str(run.run_id)
    assert calls[0][2]["binding"]["client_id"] == str(other.client_id)


async def test_historical_receipt_short_circuits_agent_and_does_not_grant_send():
    from asm.ai.contracts import Reply

    run = prepared()
    receipt = RuntimeReceipt(
        run_id=run.run_id,
        job_id=run.binding.job_id,
        turn_id=run.binding.turn_id,
        turn_revision=run.binding.turn_revision,
        selected_at=datetime.now(UTC),
        result=Reply(kind="reply", text="saved", reason=None),
    )

    class Stored(AIDatabase):
        async def replay(self, *args):
            return receipt

        async def prepare(self, *args, **kwargs):
            raise AssertionError("replay entered generation")

    adapter = FakeAdapter(run.config.route)
    result = await Stored(SimpleNamespace(), environment="TEST").execute(
        None, run.config, adapter, deadline=run.deadline
    )
    assert result == receipt and not result.send_permit and adapter.requests == []


@pytest.mark.parametrize(
    "fault",
    [
        "valid",
        "missing_case",
        "missing_phase",
        "duplicate_phase",
        "skip",
        "xfail",
        "failure",
        "exit",
    ],
)
def test_runtime_report_never_labels_incomplete_or_skipped_evidence_pass(fault):
    from scripts.m4_pg_observation import summarize

    phases = [dict(phase=p, outcome="passed", xfail=False) for p in ("setup", "call", "teardown")]
    cases = [dict(nodeid="case", phases=phases, overflow=0, invalid_fields=0)]
    if fault == "missing_case":
        cases = []
    elif fault == "missing_phase":
        phases.pop()
    elif fault == "duplicate_phase":
        phases.append(dict(phases[-1]))
    elif fault == "skip":
        phases[1]["outcome"] = "skipped"
    elif fault == "xfail":
        phases[1]["xfail"] = True
    elif fault == "failure":
        phases[1]["outcome"] = "failed"
    summary = summarize(cases, ["case"], 1 if fault == "exit" else 0)
    assert (summary["result"] == "PASS") == (fault == "valid")


def assert_read_audit(audit, binding):
    """Check stored READ metadata against the expected run, without accepting raw content."""
    assert type(audit) is dict
    assert set(audit) == {"outcome", "context_version", "turn_revision", "native", "at"}
    expected = {
        "outcome": "READ",
        "context_version": binding.context_version,
        "turn_revision": binding.turn_revision,
    }
    for key, value in expected.items():
        assert type(audit[key]) is type(value)
        assert audit[key] == value
    native = audit["native"]
    if binding.native is None:
        assert native is None
    else:
        assert type(native) is dict
        assert set(native) == {
            "revision_id",
            "revision_no",
            "policy_epoch",
            "observation_epoch",
            "reviewed_ingress_checkpoint",
            "reviewed_input_state_hash",
        }
        expected_native = binding.native.model_dump(mode="json")
        assert set(native) == set(expected_native)
        for key, value in expected_native.items():
            assert type(native[key]) is type(value)
            assert native[key] == value
    assert type(audit["at"]) is str
    try:
        at = datetime.fromisoformat(audit["at"])
    except ValueError:
        raise AssertionError("READ audit timestamp must be ISO datetime") from None
    assert at.utcoffset() is not None


@pytest.fixture
def read_audit():
    _, binding = fixture("v3_owner")
    return {
        "outcome": "READ",
        "context_version": binding.context_version,
        "turn_revision": binding.turn_revision,
        "native": binding.native.model_dump(mode="json"),
        "at": "2026-10-31T13:00:00+00:00",
    }, binding


@pytest.mark.parametrize("native", [True, False], ids=["native", "no_native"])
def test_read_audit_accepts_metadata_rejected_by_old_substring_check(read_audit, native):
    audit, binding = read_audit
    if not native:
        binding = binding.model_copy(update={"native": None})
        audit["native"] = None
    with pytest.raises(AssertionError):
        assert "text" not in json.dumps(audit)  # context_version contains this substring.
    assert_read_audit(audit, binding)


@pytest.mark.parametrize("scope", ["audit", "native"])
def test_read_audit_rejects_raw_text(read_audit, scope):
    audit, binding = read_audit
    target = audit if scope == "audit" else audit["native"]
    target["text"] = "Synthetic client message must never be copied into audit."
    with pytest.raises(AssertionError):
        assert_read_audit(audit, binding)


@pytest.mark.parametrize(
    "field",
    [
        "outcome",
        "context_version",
        "turn_revision",
        "native.revision_id",
        "native.revision_no",
        "native.policy_epoch",
        "native.observation_epoch",
        "native.reviewed_ingress_checkpoint",
        "native.reviewed_input_state_hash",
    ],
)
def test_read_audit_rejects_changed_metadata(read_audit, field):
    audit, binding = read_audit
    target = audit["native"] if field.startswith("native.") else audit
    key = field.rsplit(".", 1)[-1]
    value = target[key]
    if type(value) is int:
        target[key] = value + 1
    elif key == "reviewed_input_state_hash":
        target[key] = "b" * 64
    else:
        target[key] = str(uuid4())
    with pytest.raises(AssertionError):
        assert_read_audit(audit, binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("context_version", 4.0),
        ("turn_revision", True),
        ("native.revision_no", "1"),
        ("native.observation_epoch", False),
        ("native", None),
        ("native", {}),
        ("at", 1793451600),
        ("at", "2026-10-31T13:00:00"),
        ("at", "Synthetic raw content"),
    ],
)
def test_read_audit_requires_strict_types_complete_native_and_zoned_time(read_audit, field, value):
    audit, binding = read_audit
    target = audit["native"] if field.startswith("native.") else audit
    target[field.rsplit(".", 1)[-1]] = value
    with pytest.raises(AssertionError):
        assert_read_audit(audit, binding)
