"""Private GUARDS codec, closed caller profile and exact migration delta."""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from alembic import op
from asm.conversations.guards import (
    GUARD_TEXT,
    GuardedTurnSnapshot,
    GuardProgress,
    GuardReceipt,
    GuardTextResult,
    consume_guarded,
)
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import TurnJobClaim, parse_claim
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine


def snapshot():
    return GuardedTurnSnapshot.model_validate(
        {
            "code": "SNAPSHOT",
            "job_id": str(UUID(int=1)),
            "workspace_id": str(UUID(int=2)),
            "connection_id": str(UUID(int=3)),
            "turn_id": str(UUID(int=4)),
            "turn_revision": 1,
            "context_version": 2,
            "control_generation": 2,
            "readiness": "COMPLETE",
            "members": [
                {
                    "message_id": str(UUID(int=5)),
                    "message_version": 1,
                    "content_type": "TEXT",
                    "ingress_at": "2026-10-12T12:00:00Z",
                    "ingress_seq": 2,
                    "file": None,
                }
            ],
            "snapshot_digest": "a" * 64,
            "conversation_id": str(UUID(int=6)),
            "client_id": str(UUID(int=7)),
            "business_id": str(UUID(int=8)),
            "activation_fence_seq": 1,
            "resume_receipt_id": str(UUID(int=9)),
            "consumer": "CONTROLLED_GUARDS_V1",
        }
    )


def test_guarded_snapshot_is_separate_closed_and_consumer_is_pure():
    value = snapshot()
    result = consume_guarded(value)
    assert result.text == GUARD_TEXT == "CONTROLLED GUARDS TEST"
    assert result.snapshot_digest == value.snapshot_digest
    assert result.consumer == "CONTROLLED_GUARDS_V1"
    for changes in (
        {"origin": "AUTOMATED"},
        {"consumer": "TURN_TEST_V1"},
        {"activation_fence_seq": "1"},
    ):
        with pytest.raises(ValidationError):
            GuardedTurnSnapshot.model_validate({**value.model_dump(), **changes})
    with pytest.raises(ValidationError):
        GuardTextResult(consumer="OTHER", snapshot_digest="a" * 64, text=GUARD_TEXT)


@pytest.mark.parametrize("value", [" exact e\u0301\né🙂 ", "é" * 4096])
def test_exact_result_text_is_not_normalized(value):
    assert GuardTextResult(snapshot_digest="a" * 64, text=value).text == value


@pytest.mark.parametrize("value", ["", " \n\t\u001c", "x" * 4097, "\ud800", "\x00"])
def test_invalid_guarded_text_uses_existing_m2_bounds(value):
    with pytest.raises((ValidationError, MessagingError)):
        GuardTextResult(snapshot_digest="a" * 64, text=value)


def test_progress_and_receipt_cannot_hide_partial_intent():
    progress = dict(
        code="STALE",
        job_id=UUID(int=1),
        turn_id=UUID(int=2),
        turn_revision=1,
        accepted_job_id=None,
        message_id=None,
        outbox_id=None,
        send_job_id=None,
    )
    GuardProgress.model_validate(progress)
    with pytest.raises(ValidationError):
        GuardProgress.model_validate({**progress, "code": "ALREADY_ACCEPTED"})
    base = snapshot().model_dump()
    receipt = {
        key: base[key]
        for key in (
            "job_id",
            "workspace_id",
            "connection_id",
            "conversation_id",
            "client_id",
            "turn_id",
            "turn_revision",
            "resume_receipt_id",
            "activation_fence_seq",
            "snapshot_digest",
            "consumer",
        )
    }
    receipt.update(
        code="ACCEPTED",
        input_context_version=2,
        input_control_generation=2,
        request_fingerprint="b" * 64,
        result_text=GUARD_TEXT,
        accepted_at="2026-10-12T12:00:00Z",
        intent_context_version=3,
        message_id=UUID(int=10),
        outbox_id=UUID(int=11),
        send_job_id=UUID(int=12),
    )
    GuardReceipt.model_validate(receipt)
    for changes in ({"code": "STALE"}, {"outbox_id": None}, {"intent_context_version": 2}):
        with pytest.raises(ValidationError):
            GuardReceipt.model_validate({**receipt, **changes})


def test_new_claim_kinds_parse_without_altering_old_shapes():
    base = dict(
        job_id=UUID(int=1),
        workspace_id=UUID(int=2),
        connection_id=UUID(int=3),
        inbox_id=None,
        outbox_id=UUID(int=4),
        claim_token=UUID(int=5),
        lease_until="2026-10-12T12:00:00Z",
        correlation_id=UUID(int=6),
        attempt_count=1,
    )
    for kind in ("SEND_MANUAL_TEXT", "SEND_GUARDED_TEXT"):
        assert parse_claim({**base, "kind": kind}).kind == kind
    claim = parse_claim(
        {
            **base,
            "kind": "PROCESS_TURN",
            "outbox_id": None,
            "turn_id": UUID(int=7),
            "turn_revision": 1,
            "step": "GUARDED_TEXT",
        }
    )
    assert isinstance(claim, TurnJobClaim)


@pytest.mark.parametrize(
    "environment,database,allowed",
    [
        ("TEST", "asm_test", True),
        ("LOCAL", "asm_local", True),
        ("PRODUCTION", "asm_test", False),
        ("TEST", "production", False),
        (None, "asm_test", False),
    ],
)
async def test_python_guard_requires_server_environment_and_known_database(
    environment, database, allowed
):
    engine = create_async_engine(f"postgresql+psycopg://asm_runtime@localhost/{database}")
    try:
        with patch.dict(os.environ, {}, clear=True):
            kernel = MessagingDatabase(engine, environment=environment)
        if allowed:
            kernel._require_guards()
        else:
            with pytest.raises(MessagingError) as caught:
                kernel._require_guards()
            assert caught.value.code == Code.NOT_ALLOWED
    finally:
        await engine.dispose()


def test_migration_replaces_exact_c_bodies_and_adds_only_six_profiles():
    def module(path):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        result = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(result)
        return result

    statements = []
    with patch.object(op, "execute", side_effect=statements.append):
        for path in sorted(Path("migrations/versions").glob("000[5-9]*.py")):
            module(path).upgrade()
    candidate = module(Path("migrations/versions/0010_conversation_guards.py"))
    assert (candidate.revision, candidate.down_revision) == ("0010", "0009")
    for name, expected in candidate.ORIGINAL.items():
        bodies = [
            s.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
            for s in statements
            if s.startswith(
                (
                    f"CREATE FUNCTION platform.{name}(",
                    f"CREATE OR REPLACE FUNCTION platform.{name}(",
                )
            )
        ]
        if name == "messaging_reschedule":
            bodies = [s for s in bodies if "p_nowait boolean" in s]
        assert bodies[-1] == expected, name
    statements.clear()
    with patch.object(op, "execute", side_effect=statements.append):
        candidate.upgrade()
    assert sum(s.startswith("CREATE FUNCTION") for s in statements) == 6
    assert sum(s.startswith("CREATE TABLE") for s in statements) == 1
    legacy = next(
        s for s in statements if s.startswith("CREATE OR REPLACE FUNCTION platform.turn_execute(")
    )
    assert legacy.index("j.step NOT IN") < legacy.index("PERFORM platform.turn_preflight")
