"""P-A03-01/07: exact V2 codec, closed private unions and paired current DTO."""

import copy
import hashlib
import runpy
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
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
from sqlalchemy.dialects.postgresql import psycopg
from sqlalchemy.sql.elements import TextClause

BOT = "9000001"
DATE = 1792051200


def assert_online_empty_parameters(statement, parameters):
    """Exercise psycopg parameter construction before any database call."""
    assert isinstance(statement, TextClause)
    assert not parameters
    compiled = statement.compile(dialect=psycopg.dialect())
    assert compiled.construct_params(parameters) == {}


def test_material_upgrade_online_has_no_required_parameters():
    statements = []

    def execute(statement, parameters):
        assert_online_empty_parameters(statement, parameters)
        statements.append(statement)

    connection = SimpleNamespace(
        dialect=psycopg.dialect(), execute=execute, in_transaction=lambda: False
    )
    context = MigrationContext.configure(connection)
    assert not context.as_sql
    source = Path(__file__).resolve().parents[1] / "migrations/versions/0012_message_provenance.py"
    # Real op.execute -> online Alembic _exec -> TextClause + empty parameters.
    # The sink compiles the untouched expanded strings, never supplies null.
    with Operations.context(context):
        runpy.run_path(str(source))["upgrade"]()
    assert len(statements) == 131


async def test_material_forged_basis_setup_online_has_no_required_parameters(monkeypatch):
    import test_m3_1_provenance_postgres as pg

    class SetupCompiled(Exception):
        """Stop the actual PG case immediately after its CREATE reaches the sink."""

    statements = []

    async def execute(statement, parameters=None):
        assert_online_empty_parameters(statement, {} if parameters is None else parameters)
        statements.append(statement)
        if statement.text == "SELECT current_database()":
            return SimpleNamespace(scalar_one=lambda: "asm_test")
        assert statement.text.startswith("CREATE FUNCTION platform.test_material_corrupt() ")
        raise SetupCompiled

    @asynccontextmanager
    async def begin():
        yield SimpleNamespace(execute=execute)

    # Bypass only the earlier domain fixture work. The PG test itself constructs
    # its real forged-basis CREATE/text(...) and calls the empty-parameter sink.
    monkeypatch.setattr(pg, "process", AsyncMock())
    monkeypatch.setattr(pg, "ingest_raw", AsyncMock(return_value=SimpleNamespace(job_id=uuid4())))
    monkeypatch.setattr(pg, "claim_exact", AsyncMock())
    with pytest.raises(SetupCompiled):
        await pg.test_r3_t4_invalid_first_suppression_rolls_back_entire_original_atom(
            SimpleNamespace(migrator=SimpleNamespace(begin=begin)), "forged-basis"
        )
    assert len(statements) == 2


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


def _sent_failure_diagnostic(error, outcome):
    """Same-call metadata only: closed identifiers, no exception/SQL rendering."""
    import json
    import re

    classes = {
        "MessagingError",
        "DBAPIError",
        "OperationalError",
        "ProgrammingError",
        "IntegrityError",
        "DatabaseError",
        "InternalError",
        "InterfaceError",
        "TimeoutError",
        "CancelledError",
        "DeadlockDetected",
        "LockNotAvailable",
        "ForeignKeyViolation",
        "CheckViolation",
        "NotNullViolation",
        "UniqueViolation",
        "SerializationFailure",
        "InFailedSqlTransaction",
    }
    tables = {
        "channel_connections",
        "conversations",
        "messages",
        "outbox_events",
        "messaging_jobs",
        "conversation_turns",
        "conversation_turn_messages",
        "message_material_targets",
        "message_material_effects",
        "message_initial_suppressions",
        "telegram_provenance",
        "telegram_update_receipts",
        "audit_events",
        "escalations",
    }
    constraints = {
        "messaging_jobs_turn_fkey",
        "messaging_jobs_turn_step_key",
        "messaging_jobs_turn_check",
        "messaging_jobs_workspace_id_connection_id_fkey",
        "conversation_turn_messages_check",
        "audit_material_target_fkey",
        "audit_material_source_fkey",
        "audit_events_discriminator_payload_check",
        "turn_member_suppression_fkey",
        "material_integrity",
        "material_target_consistency",
        "material_suppression_completeness",
    }
    functions = {
        "messaging_finish_send",
        "messaging_guard",
        "messaging_immutable",
        "turn_preflight",
        "turn_material",
        "turn_enqueue",
        "turn_seal",
        "turn_immutable",
        "turn_member_check",
        "material_bind",
        "material_apply",
        "material_apply_context",
        "material_bump_turns",
        "material_fold",
        "material_integrity",
        "material_target_check",
        "material_suppression_check",
        "material_turn_usable",
        "message_effective",
        "escalation_context_changed",
        "escalation_validity",
    }

    def field(obj, name):
        try:
            return getattr(obj, name, None)
        except BaseException:
            return None

    def known(value, allowed):
        return value if type(value) is str and len(value) <= 63 and value in allowed else "UNKNOWN"

    chain, seen, pending = [], set(), [("primary", error)]
    while pending and len(chain) < 4:
        via, fault = pending.pop(0)
        if not isinstance(fault, BaseException) or id(fault) in seen:
            continue
        seen.add(id(fault))
        diag = field(fault, "diag")
        state = field(fault, "sqlstate")
        if not (type(state) is str and re.fullmatch(r"[0-9A-Z]{5}", state)):
            state = "UNKNOWN"
        frames = []
        context = field(diag, "context")
        # Inspect a bounded string without ever emitting its SQL/arguments/text.
        if type(context) is str and len(context) <= 16384:
            for match in re.finditer(
                r"^PL/pgSQL function (?:platform\.)?([a-z_][a-z0-9_]{0,62})"
                r"\([a-z0-9_.,\[\] ]{0,240}\) line ([1-9][0-9]{0,5}) at [^\n]*$",
                context,
                re.MULTILINE,
            ):
                name, line = match.groups()
                if name in functions:
                    frames.append({"function": "platform." + name, "line": int(line)})
                    if len(frames) == 3:
                        break
        chain.append(
            {
                "via": via,
                "exception": known(type(fault).__name__, classes),
                "sqlstate": state,
                "schema": known(field(diag, "schema_name"), {"app", "platform"}),
                "table": known(field(diag, "table_name"), tables),
                "constraint": known(field(diag, "constraint_name"), constraints),
                "frames": frames or [{"function": "UNKNOWN", "line": "UNKNOWN"}],
            }
        )
        for attr in ("orig", "__cause__", "__context__"):
            linked = field(fault, attr)
            if isinstance(linked, BaseException) and id(linked) not in seen:
                pending.append((attr, linked))
    report = {
        "stage": "material_deferred_finalization",
        "action": "finish_send",
        "outcome": known(outcome, {"SENT", "UNKNOWN"}),
        "chain": chain,
        "chain_limited": any(id(fault) not in seen for _, fault in pending),
    }
    # Four nodes, three closed function/line pairs per node; ASCII JSON plus LF.
    encoded = json.dumps(report, ensure_ascii=True, separators=(",", ":"))
    assert len(encoded) < 4096
    return encoded


@contextmanager
def _sent_failure_scope(outcome):
    """Record at the call site, retaining that primary through lock cleanup."""
    import sys

    primary = None

    def record(error):
        nonlocal primary
        primary = (error, error.__traceback__)
        try:
            diagnostic = _sent_failure_diagnostic(error, outcome)
        except BaseException:
            diagnostic = (
                '{"stage":"material_deferred_finalization","action":"finish_send",'
                '"outcome":"UNKNOWN","exception":"UNKNOWN","sqlstate":"UNKNOWN",'
                '"schema":"UNKNOWN","table":"UNKNOWN","constraint":"UNKNOWN",'
                '"function":"UNKNOWN","line":"UNKNOWN"}'
            )
        try:
            print(diagnostic, file=sys.stderr)
        except BaseException:
            # A diagnostic sink failure has no authority over outcome.
            pass

    try:
        yield record
    except BaseException:
        if primary is None:
            raise
    # Also retain the primary if an enclosing cleanup context swallowed it.
    if primary is not None:
        error, traceback = primary
        raise error.with_traceback(traceback) from None


def test_sent_failure_diagnostic_reads_original_suppressed_chain_without_payload():
    import json

    from asm.messaging.errors import Code

    secret = "private_canary_sql_text_claim_token"
    original = TimeoutError(secret)
    original.sqlstate = "55P03"
    original.diag = SimpleNamespace(
        schema_name="platform",
        table_name="messaging_jobs",
        constraint_name="messaging_jobs_turn_fkey",
        message_detail=secret,
        context=(
            'SQL statement "' + secret + '"\n'
            "PL/pgSQL function platform.turn_enqueue(uuid,uuid,uuid) line 8 at SQL statement\n"
            "PL/pgSQL function material_bind(uuid,uuid,boolean,uuid) line 52 at PERFORM"
        ),
    )
    wrapped = RuntimeError(secret)
    wrapped.orig = original
    primary = MessagingError(Code.DEPENDENCY_UNAVAILABLE)
    try:
        try:
            raise wrapped
        except RuntimeError:
            raise primary from None
    except MessagingError:
        pass
    assert primary.__suppress_context__ and primary.__context__ is wrapped
    encoded = _sent_failure_diagnostic(primary, "SENT")
    value = json.loads(encoded)
    assert secret not in encoded and len(encoded.encode()) + 1 <= 4096
    assert value["stage"] == "material_deferred_finalization"
    assert value["action"] == "finish_send" and value["outcome"] == "SENT"
    assert [node["via"] for node in value["chain"]] == ["primary", "__context__", "orig"]
    assert [node["exception"] for node in value["chain"]] == [
        "MessagingError",
        "UNKNOWN",
        "TimeoutError",
    ]
    assert value["chain"][0]["sqlstate"] == "UNKNOWN"
    assert value["chain"][2] == {
        "via": "orig",
        "exception": "TimeoutError",
        "sqlstate": "55P03",
        "schema": "platform",
        "table": "messaging_jobs",
        "constraint": "messaging_jobs_turn_fkey",
        "frames": [
            {"function": "platform.turn_enqueue", "line": 8},
            {"function": "platform.material_bind", "line": 52},
        ],
    }
    assert not value["chain_limited"]


def test_sent_failure_diagnostic_absent_and_untrusted_fields_remain_unknown():
    import json

    class Untrusted:
        def __str__(self):
            raise AssertionError("arbitrary rendering")

        __repr__ = __str__

        def __getattr__(self, name):
            raise RuntimeError("private_canary_attribute")

    secret = "private_canary_identifier"
    # Even a syntactically valid identifier/class name must be allowlisted.
    error = type(secret, (RuntimeError,), {})(secret)
    for bad in (None, {}, [], 123, True, Untrusted(), secret, "x" * 20000):
        error.sqlstate = bad
        error.diag = SimpleNamespace(
            schema_name=bad,
            table_name=bad,
            constraint_name=bad,
            context=bad,
            message_primary=secret,
            message_detail=secret,
        )
        encoded = _sent_failure_diagnostic(error, bad)
        value = json.loads(encoded)
        assert secret not in encoded and len(encoded.encode()) + 1 <= 4096
        assert value["outcome"] == "UNKNOWN"
        assert value["chain"] == [
            {
                "via": "primary",
                "exception": "UNKNOWN",
                "sqlstate": "UNKNOWN",
                "schema": "UNKNOWN",
                "table": "UNKNOWN",
                "constraint": "UNKNOWN",
                "frames": [{"function": "UNKNOWN", "line": "UNKNOWN"}],
            }
        ]
    error.diag = Untrusted()
    assert json.loads(_sent_failure_diagnostic(error, "SENT"))["chain"][0]["table"] == "UNKNOWN"
    absent = json.loads(_sent_failure_diagnostic(RuntimeError(secret), "UNKNOWN"))
    assert absent["chain"][0]["sqlstate"] == "UNKNOWN" and not absent["chain_limited"]


def test_sent_failure_diagnostic_rejects_malformed_and_oversized_context():
    import json

    error = TimeoutError("private_canary_context")
    for context in (
        "PL/pgSQL function private.material_bind(uuid) line 1 at SQL statement",
        "PL/pgSQL function platform.private_canary_context() line 1 at SQL statement",
        "PL/pgSQL function platform.material_bind(private_canary_context) line -1 at SQL statement",
        "PL/pgSQL function platform.material_bind() line 1000000 at SQL statement",
        "PL/pgSQL function platform.material_bind() line 7 at SQL statement\n" + "x" * 16384,
    ):
        error.diag = SimpleNamespace(context=context)
        encoded = _sent_failure_diagnostic(error, "SENT")
        assert "private_canary_context" not in encoded
        assert json.loads(encoded)["chain"][0]["frames"] == [
            {"function": "UNKNOWN", "line": "UNKNOWN"}
        ]


def test_sent_failure_diagnostic_cycles_and_maximum_shape_are_bounded():
    import json

    errors = [TimeoutError("private_canary_cycle") for _ in range(8)]
    for i, error in enumerate(errors):
        error.__cause__ = errors[(i + 1) % len(errors)]
        error.__context__ = error
        error.orig = error
        error.sqlstate = "23503"
        error.diag = SimpleNamespace(
            schema_name="platform",
            table_name="message_initial_suppressions",
            constraint_name="audit_events_discriminator_payload_check",
            context=(
                "PL/pgSQL function platform.material_suppression_check() line 999999 at SQL statement\n"
                * 50
            ),
        )
    encoded = _sent_failure_diagnostic(errors[0], "SENT")
    report = json.loads(encoded)
    assert len(encoded.encode()) + 1 <= 4096 and "private_canary_cycle" not in encoded
    assert report["chain_limited"] and len(report["chain"]) == 4
    assert all(len(node["frames"]) == 3 for node in report["chain"])
    errors[0].__cause__ = errors[0]
    report = json.loads(_sent_failure_diagnostic(errors[0], "SENT"))
    assert len(report["chain"]) == 1 and not report["chain_limited"]


def test_sent_failure_scope_preserves_primary_through_diagnostic_and_cleanup_faults():
    import json
    from contextlib import ExitStack, contextmanager, redirect_stderr
    from io import StringIO
    from unittest.mock import patch

    from asm.messaging.errors import Code

    for mode in ("normal", "formatter", "sink", "cleanup-raise", "cleanup-suppress"):
        primary = MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        output = StringIO()

        @contextmanager
        def cleanup():
            try:
                yield
            except BaseException:
                if mode != "cleanup-suppress":
                    raise
            finally:
                if mode == "cleanup-raise":
                    raise LookupError("private_canary_cleanup")

        with ExitStack() as stack:
            stack.enter_context(redirect_stderr(output))
            if mode == "formatter":
                stack.enter_context(
                    patch(
                        __name__ + "._sent_failure_diagnostic",
                        side_effect=ValueError("private_canary_formatter"),
                    )
                )
            if mode == "sink":
                stack.enter_context(
                    patch("builtins.print", side_effect=OSError("private_canary_sink"))
                )
            try:
                with _sent_failure_scope("SENT") as record:
                    with cleanup():
                        try:
                            raise primary
                        except BaseException as error:
                            record(error)
                            raise
            except BaseException as caught:
                assert caught is primary
            else:
                raise AssertionError("primary failure suppressed")
        lines = output.getvalue().splitlines()
        assert len(lines) == (0 if mode == "sink" else 1)
        assert "private_canary" not in output.getvalue()
        if lines:
            assert len(output.getvalue().encode()) <= 4096
            assert json.loads(lines[0])["action"] == "finish_send"


def test_sent_failure_scope_is_silent_on_success_and_preserves_unrecorded_failure():
    from contextlib import redirect_stderr
    from io import StringIO

    output = StringIO()
    primary = RuntimeError("private_canary_setup")
    with redirect_stderr(output):
        with _sent_failure_scope("UNKNOWN"):
            pass
        try:
            with _sent_failure_scope("SENT"):
                raise primary
        except RuntimeError as caught:
            assert caught is primary
        else:
            raise AssertionError("setup failure suppressed")
    assert output.getvalue() == ""
