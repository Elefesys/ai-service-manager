"""Private consumer and bounded scan orchestration (no simulated DB evidence)."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from asm.conversations.turns import TurnSnapshot, consume
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase, worker_active
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import JobClaim, TurnJobClaim, parse_claim
from asm.messaging.worker import Worker
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError


def snapshot():
    return TurnSnapshot.model_validate(
        {
            "code": "SNAPSHOT",
            "job_id": uuid4(),
            "workspace_id": uuid4(),
            "connection_id": uuid4(),
            "turn_id": uuid4(),
            "turn_revision": 4,
            "context_version": 8,
            "control_generation": 1,
            "readiness": "PARTIAL",
            "snapshot_digest": "a" * 64,
            "members": [
                {
                    "message_id": uuid4(),
                    "message_version": 1,
                    "content_type": kind,
                    "ingress_at": datetime.now(UTC),
                    "ingress_seq": i + 1,
                    "file": file,
                }
                for i, (kind, file) in enumerate(
                    [
                        ("TEXT", None),
                        (
                            "IMAGE_REFERENCE",
                            {
                                "file_id": uuid4(),
                                "version": 2,
                                "status": "READY",
                                "error_code": None,
                                "wait_expired": False,
                            },
                        ),
                        (
                            "IMAGE_REFERENCE",
                            {
                                "file_id": uuid4(),
                                "version": 1,
                                "status": "PENDING",
                                "error_code": None,
                                "wait_expired": True,
                            },
                        ),
                        (
                            "IMAGE_REFERENCE",
                            {
                                "file_id": uuid4(),
                                "version": 2,
                                "status": "FAILED",
                                "error_code": "RETRY_EXHAUSTED",
                                "wait_expired": False,
                            },
                        ),
                    ]
                )
            ],
        }
    )


def claim(kind="PROCESS_TURN"):
    values = dict(
        job_id=uuid4(),
        kind=kind,
        workspace_id=uuid4(),
        connection_id=uuid4(),
        inbox_id=None,
        outbox_id=None,
        file_id=None,
        claim_token=uuid4(),
        lease_until=datetime.now(UTC),
        correlation_id=uuid4(),
        attempt_count=1,
    )
    if kind == "PROCESS_TURN":
        values.update(turn_id=uuid4(), turn_revision=1, step="TEST_CONSUME")
    return parse_claim(values)


def test_consumer_is_pure_deterministic_refs_only_and_typed():
    value = snapshot()
    before = value.model_dump_json()
    assert consume(value).model_dump() == {
        "consumer": "TURN_TEST_V1",
        "snapshot_digest": "a" * 64,
        "member_count": 4,
        "ready_file_count": 1,
        "wait_expired_count": 1,
    }
    assert consume(value) == consume(value)
    assert value.model_dump_json() == before and not worker_active()
    for extra in ("signed_url", "bytes", "owner", "send"):
        with pytest.raises(ValidationError):
            TurnSnapshot.model_validate({**value.model_dump(), extra: "forged"})
    with pytest.raises(ValidationError):
        value.turn_revision = 2


def test_new_job_refs_do_not_change_old_claim_shapes():
    old = claim("PROCESS_INBOX")
    assert type(old) is JobClaim and "turn_id" not in old.model_dump()
    assert type(claim()) is TurnJobClaim
    with pytest.raises(ValidationError):
        parse_claim({**old.model_dump(), "turn_id": uuid4()})
    with pytest.raises(ValidationError):
        parse_claim({**claim().model_dump(), "step": "SEND"})


@pytest.mark.parametrize("terminal", [False, True])
async def test_claim_scans_one_physical_transaction_per_candidate_and_continues_after_100(
    monkeypatch, terminal
):
    import asm.messaging.database as module

    db = MessagingDatabase(
        SimpleNamespace(
            url=SimpleNamespace(drivername="postgresql+psycopg", username="asm_runtime")
        )
    )
    opened, closed, positions = [], [], []
    now, selected = datetime.now(UTC), claim()

    @asynccontextmanager
    async def transaction():
        number = len(opened)
        assert len(opened) == len(closed)
        opened.append(number)
        try:
            yield number
        finally:
            closed.append(number)

    async def call(connection, sql, params):
        assert opened[-1] == connection and len(opened) == len(closed) + 1
        positions.append(params)
        number = len(positions)
        return {
            "step": "CLAIMED" if number == 102 else "TERMINALIZED" if terminal else "BUSY",
            "scan_until": now,
            "at": now,
            "id": selected.job_id if number == 102 else uuid4(),
            **({"claim": selected.model_dump()} if number == 102 else {}),
        }

    monkeypatch.setattr(db, "_transaction", transaction)
    monkeypatch.setattr(module, "call", call)
    assert await db.claim_job("cursor") is None
    assert len(opened) == len(closed) == 100
    saved = db._claim_scan["cursor"]
    assert await db.claim_job("cursor") == selected
    assert positions[100]["until"] == now and positions[100]["id"] == saved.id
    assert len(opened) == len(closed) == 102
    assert "cursor" not in db._claim_scan


async def test_claim_commit_error_does_not_publish_position_or_idle(monkeypatch):
    import asm.messaging.database as module

    db = MessagingDatabase(
        SimpleNamespace(
            url=SimpleNamespace(drivername="postgresql+psycopg", username="asm_runtime")
        )
    )
    failure = SQLAlchemyError("commit lost")

    @asynccontextmanager
    async def transaction():
        yield None
        raise failure

    async def call(*args):
        return {"step": "END", "scan_until": datetime.now(UTC)}

    monkeypatch.setattr(db, "_transaction", transaction)
    monkeypatch.setattr(module, "call", call)
    with pytest.raises(SQLAlchemyError) as caught:
        await db.claim_job("commit")
    assert caught.value is failure and not db._claim_scan


@pytest.mark.parametrize("operation", ["inbox", "turn", "send"])
async def test_worker_secondary_failure_keeps_primary_as_cause(operation):
    primary, secondary = SQLAlchemyError("primary"), MessagingError(Code.STALE_CLAIM)

    async def fail(*args):
        raise primary

    async def stale(*args):
        raise secondary

    db = SimpleNamespace(process_inbox=fail, process_turn=fail, retry=stale, finish_send=fail)
    worker = Worker(db, ControlledAdapter(environment="TEST"))
    if operation == "send":
        calls = 0

        async def finish(*args):
            nonlocal calls
            calls += 1
            raise primary if calls == 1 else secondary

        db.finish_send = finish
        with pytest.raises(MessagingError) as caught:
            await worker._finish(
                SimpleNamespace(job_id=uuid4(), claim_token=uuid4(), attempt_id=uuid4()), None
            )
    else:
        with pytest.raises(MessagingError) as caught:
            await worker.execute(claim("PROCESS_INBOX" if operation == "inbox" else "PROCESS_TURN"))
    assert caught.value is secondary and caught.value.__cause__ is primary


async def test_turn_lost_ack_reads_terminal_capability_before_any_new_mutation():
    calls = []

    async def finish(*args):
        calls.append("finalize")
        raise SQLAlchemyError("commit ACK lost")

    async def replay(*args):
        calls.append("canonical replay")
        return object()

    worker = Worker(
        SimpleNamespace(finish_turn=finish, replay_turn=replay),
        ControlledAdapter(environment="TEST"),
    )
    await worker._finish_turn(claim(), consume(snapshot()))
    assert calls == ["finalize", "canonical replay"]
