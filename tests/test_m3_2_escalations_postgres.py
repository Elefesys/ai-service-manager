"""Actual PG Escalation lifecycle through CONTROLLED Inbox, normal queue and owner UOW."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from asm.conversations.escalation_http_models import (
    EscalationCancelRequest,
    EscalationResolveRequest,
    EscalationView,
)
from asm.conversations.escalations import (
    MARKER,
    EscalationCode,
    EscalationCreationResult,
    EscalationError,
    EscalationProgress,
    decision_fingerprint,
)
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import EscalationTimerClaim
from asm.messaging.worker import Worker
from asm.tenancy import AuthenticatedAccount
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_m2_1_models import event
from test_m2_1_postgres import command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import execute, incoming, process_receipt, state, wait_blocked
from test_m3_1_guards_postgres import next_kind
from test_tenancy_postgres import PROVIDER, UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


async def clock_profile(connection):
    return (
        await connection.execute(
            text("""SELECT pg_get_functiondef(p.oid),p.proowner::regrole::text,p.prosecdef,
      p.provolatile,p.proisstrict,p.proconfig,p.proacl::text FROM pg_proc p
      WHERE p.oid='platform.escalation_now()'::regprocedure""")
        )
    ).one()


@asynccontextmanager
async def serial_clock(h):
    """Committed private clock in disposable asm_test only; exact fresh-tx restore.

    Runtime index, lease/retry, billing and CONTROL clocks remain real. Parent
    owns this fixture, including when a worker child exits or a DB assertion fails.
    """
    async with h.migrator.connect() as c:
        assert (await c.execute(text("SELECT current_user,current_database()"))).one() == (
            "asm_migrator",
            "asm_test",
        )
        original = await clock_profile(c)
        await c.execute(text("SELECT pg_advisory_lock(1295200511,1)"))
        await c.commit()

        async def set_clock(moment):
            assert isinstance(moment, datetime) and moment.tzinfo is UTC
            async with h.migrator.begin() as write:
                await write.execute(
                    text(
                        "CREATE OR REPLACE FUNCTION platform.escalation_now() RETURNS timestamptz LANGUAGE sql VOLATILE SET search_path=pg_catalog,pg_temp AS $$ SELECT '"
                        + moment.isoformat()
                        + "'::timestamptz $$"
                    )
                )
                changed = await clock_profile(write)
                assert changed[1:] == original[1:]

        anchor = datetime.now(UTC) - timedelta(hours=1)
        try:
            await set_clock(anchor)
            yield anchor, set_clock
        finally:
            # The connection carrying a failed assertion/SQL transaction is never
            # reused for restoration. CREATE OR REPLACE preserves owner and ACL.
            async with h.migrator.begin() as restore:
                await restore.execute(text(original[0]))
                assert await clock_profile(restore) == original
            await c.execute(text("SELECT pg_advisory_unlock(1295200511,1)"))
            await c.commit()


async def source(h, *, marker=MARKER, suffix="new", chat="chat-a", conversation=None):
    if conversation is not None:
        cid = conversation
    elif chat == "chat-a":
        cid, _, _ = await incoming(h)
    else:
        initial = await ingest(
            h,
            event(
                event_id="initial-" + suffix,
                message_id="initial-" + suffix,
                chat_id=chat,
                sender_id=chat,
            ),
        )
        projected = await process_receipt(h, initial)
        cid = (
            await query(
                h, "SELECT conversation_id FROM app.messages WHERE id=:id", id=projected.message_id
            )
        )[0]["conversation_id"]
    await execute(h, cid, "RESUME", "resume-" + suffix)
    receipt = await ingest(
        h,
        event(
            event_id="escalation-" + suffix,
            message_id="escalation-" + suffix,
            text=marker,
            chat_id=chat,
            sender_id="user-a" if chat == "chat-a" else chat,
        ),
    )
    await process_receipt(h, receipt)
    claim = await next_kind(
        h, "PROCESS_TURN", "ESCALATE_OWNER" if marker == MARKER else "GUARDED_TEXT"
    )
    return cid, claim


async def created(h, **source_options):
    cid, claim = await source(h, **source_options)
    before = await state(h, cid)
    await h.worker.execute(claim)
    # ESCALATE_OWNER and TEST_CONSUME are independent ordinary Turn jobs.
    # Finish the latter through the normal worker before an assertion about an
    # otherwise idle timer queue. A prematurely admitted timer still fails here;
    # no queue row is deleted, filtered out or rescheduled by the fixture.
    async with asyncio.timeout(5):
        while other := await h.kernel.claim_job("escalation-fixture-consumers"):
            assert other.kind == "PROCESS_TURN" and other.step == "TEST_CONSUME"
            await h.worker.execute(other)
    e = (await query(h, "SELECT * FROM app.escalations WHERE source_job_id=:id", id=claim.job_id))[
        0
    ]
    return e, claim, before


async def read(h, e, actor=UA, workspace=A):
    async with h.runtime.tenancy.transaction(
        AuthenticatedAccount(actor), workspace, uuid4()
    ) as unit:
        return EscalationView.model_validate(await unit.escalation_read(e["id"]))


def body(e, *, answer=None):
    values = dict(
        expected_conversation_id=str(e["conversation_id"]),
        expected_client_id=str(e["client_id"]),
        expected_escalation_version="1",
        expected_control_generation=str(e["control_generation"]),
        expected_context_version=str(e["waiting_context_version"]),
    )
    return (
        EscalationCancelRequest(**values)
        if answer is None
        else EscalationResolveRequest(**values, answer_text=answer)
    )


async def decide(h, e, operation="CANCEL", key="decision", request=None, actor=UA):
    request = request or body(e, answer=" Exact e\u0301\n" if operation == "RESOLVE" else None)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(actor), A, uuid4()) as unit:
        return await unit.escalation_command(
            e["id"],
            UUID(request.expected_conversation_id),
            UUID(request.expected_client_id),
            operation,
            key,
            int(request.expected_escalation_version),
            int(request.expected_control_generation),
            int(request.expected_context_version),
            request.answer_text if isinstance(request, EscalationResolveRequest) else None,
        )


async def facts(h):
    return {
        t: await query(h, f"SELECT to_jsonb(t) AS row FROM {t} t ORDER BY to_jsonb(t)::text")
        for t in (
            "app.conversations",
            "app.conversation_turns",
            "app.escalations",
            "platform.escalation_command_receipts",
            "app.audit_events",
            "platform.messaging_jobs",
            "app.messages",
            "app.outbox_events",
        )
    }


async def test_normal_ingress_dedupe_worker_creation_exact_schedule_origin_and_no_send(control):
    h = control
    cid, _, _ = await incoming(h)
    await execute(h, cid, "RESUME", "runtime-resume")
    value = event(event_id="duplicate-marker", message_id="duplicate-marker", text=MARKER)
    a, b = await asyncio.gather(ingest(h, value), ingest(h, value))
    assert {a.code, b.code} == {"ACCEPTED", "DUPLICATE"} and a.job_id == b.job_id
    async with asyncio.timeout(10):
        while not await query(h, "SELECT id FROM app.escalations"):
            await h.worker.run_once()
            await asyncio.sleep(0.02)
    e = (await query(h, "SELECT * FROM app.escalations"))[0]
    r = EscalationCreationResult.model_validate(e["creation_result"])
    assert (
        r.initial_status == "PENDING"
        and r.initial_version == 1
        and r.waiting_context_version == r.input_context_version + 1
    )
    assert e["assignee_user_account_id"] == UA and e["source_job_step"] == "ESCALATE_OWNER"
    assert e["due_at"] - e["created_at"] == timedelta(minutes=2)
    assert e["second_reminder_at"] - e["created_at"] == timedelta(minutes=5)
    assert e["expires_at"] - e["created_at"] == timedelta(minutes=10)
    timer = await query(
        h,
        "SELECT * FROM platform.messaging_jobs WHERE escalation_id=:id ORDER BY available_at",
        id=e["id"],
    )
    assert [j["step"] for j in timer] == ["REMIND_1", "REMIND_2", "EXPIRE"]
    assert [j["available_at"] for j in timer] == [
        e["due_at"],
        e["second_reminder_at"],
        e["expires_at"],
    ]
    assert all(
        j["kind"] == "ESCALATION_TIMER"
        and j["status"] == "READY"
        and j["attempt_count"] == 0
        and j["connection_id"] == e["connection_id"]
        for j in timer
    )
    assert h.adapter.calls == 0 and not await query(h, "SELECT * FROM app.outbox_events")
    assert not await query(h, "SELECT * FROM app.audit_events WHERE object_type='ESCALATION'")
    assert (await read(h, e)).waiting == "WAITING_FOR_HUMAN"
    assert (
        await h.kernel.replay_escalation(e["source_job_id"], e["source_claim_token"])
    ).model_dump(mode="json") == r.model_dump(mode="json")
    hashes = (
        await query(
            h,
            "SELECT context_fingerprint=sha256(convert_to(request_snapshot::text,'UTF8')) AS context_ok, request_fingerprint=sha256(convert_to(E'asm:m3:escalation_request:v1\\n'||jsonb_build_object('snapshot',request_snapshot,'reason',reason,'assignee_user_account_id',assignee_user_account_id,'question',question,'policy',policy)::text,'UTF8')) AS request_ok FROM app.escalations",
        )
    )[0]
    assert hashes == {"context_ok": True, "request_ok": True}


@pytest.mark.parametrize("operation", ["RESOLVE", "CANCEL"])
async def test_concurrent_owner_replay_exact_fingerprint_and_terminal_freeze(control, operation):
    h = control
    e, claim, before = await created(h)
    req = body(e, answer=" Exact é/e\u0301 🎨\n" if operation == "RESOLVE" else None)
    one, two = await asyncio.gather(
        decide(h, e, operation, request=req), decide(h, e, operation, request=req)
    )
    assert {one["code"], two["code"]} == {"ACCEPTED", "REPLAY"} and one["result"] == two["result"]
    assert one["request_fingerprint"] == decision_fingerprint(A, UA, e["id"], operation, req)
    after = await state(h, e["conversation_id"])
    assert (
        after["version"] == before["version"] + 2
        and after["control_generation"] == before["control_generation"]
    )
    view = await read(h, e)
    assert (
        view.status == ("RESOLVED" if operation == "RESOLVE" else "CANCELLED")
        and view.version == "2"
        and view.waiting is None
    )
    assert (
        view.resolution.answer_text == req.answer_text
        if operation == "RESOLVE"
        else view.closure.reason == "OWNER_CANCELLED"
    )
    assert len(await query(h, "SELECT id FROM platform.escalation_command_receipts")) == 1
    assert (
        len(
            await query(
                h,
                "SELECT audit_event_id FROM app.audit_events WHERE event_type='ESCALATION_DECIDED'",
            )
        )
        == 1
    )
    snapshot = await facts(h)
    for op, key, request in (
        (operation, "new", req),
        (operation, "decision", req.model_copy(update={"expected_context_version": "99"})),
    ):
        with pytest.raises(EscalationError) as caught:
            await decide(h, e, op, key, request)
        assert caught.value.code in (
            EscalationCode.ESCALATION_FINAL,
            EscalationCode.IDEMPOTENCY_KEY_CONFLICT,
        )
    assert await facts(h) == snapshot
    assert (
        await h.kernel.replay_escalation(claim.job_id, claim.claim_token)
    ).initial_status == "PENDING"
    with pytest.raises(DBAPIError) as caught:
        await query(
            h,
            "UPDATE app.escalations SET completed_at=completed_at+interval '1 second' WHERE id=:id RETURNING *",
            id=e["id"],
        )
    assert caught.value.orig.sqlstate == "23514"
    assert h.adapter.calls == 0


async def test_other_live_owner_cancel_revoked_assignee_and_no_product_channel_gate(control):
    h = control
    e, _, _ = await created(h)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING *",
        ws=A,
        actor=PROVIDER,
    )
    with pytest.raises(EscalationError) as caught:
        await decide(h, e, "RESOLVE", actor=PROVIDER)
    assert caught.value.code == EscalationCode.ACCESS_DENIED
    await query(
        h,
        "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING *",
        ws=A,
        actor=UA,
    )
    await query(
        h,
        "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws RETURNING *",
        ws=A,
    )
    await query(
        h, "UPDATE app.businesses SET status='ARCHIVED' WHERE workspace_id=:ws RETURNING *", ws=A
    )
    await query(
        h, "DELETE FROM platform.workspace_subscriptions WHERE workspace_id=:ws RETURNING *", ws=A
    )
    view = await read(h, e, actor=PROVIDER)
    assert view.validity == "ASSIGNEE_REVOKED" and not view.can_resolve and view.can_cancel
    saved = await decide(h, e, actor=PROVIDER)
    assert saved["code"] == "ACCEPTED"
    assert (await read(h, e, actor=PROVIDER)).closure.actor_user_account_id == str(PROVIDER)


@pytest.mark.parametrize("material", ["manual", "takeover", "inbound", "resume"])
async def test_material_change_atomically_cancels_without_extra_context_increment(
    control, material
):
    h = control
    e, _, _ = await created(h)
    prior = await state(h, e["conversation_id"])
    if material == "manual":
        await command(h, e["conversation_id"], "manual exact", "material")
    elif material == "takeover":
        await execute(h, e["conversation_id"], "TAKEOVER", "material")
    elif material == "resume":
        await execute(h, e["conversation_id"], "RESUME", "material")
    else:
        await incoming(h, number=91)
    after = await state(h, e["conversation_id"])
    view = await read(h, e)
    assert view.status == "CANCELLED" and view.closure.reason == (
        "CONTEXT_CHANGED" if material == "inbound" else "CONTROL_CHANGED"
    )
    assert after["version"] == prior["version"] + (material in ("manual", "inbound"))
    assert after["control_generation"] == prior["control_generation"] + (material != "inbound")
    assert not await query(h, "SELECT * FROM platform.escalation_command_receipts")


@pytest.mark.parametrize("phase", ["before", "after"])
async def test_atomic_create_commit_loss_replays_only_committed_origin(control, phase):
    h = control
    cid, claim = await source(h)
    before = await facts(h)

    async def fail(name):
        if name == f"escalation_create_{phase}_commit":
            raise SQLAlchemyError("injected commit boundary")

    h.kernel._barrier = fail
    if phase == "before":
        with pytest.raises(MessagingError) as caught:
            await h.worker.execute(claim)
        assert caught.value.code == Code.STALE_CLAIM
        assert await facts(h) == before
    else:
        await h.worker.execute(claim)  # canonical winning-token replay confirms saved acceptance
        assert len(await query(h, "SELECT * FROM app.escalations")) == 1
        assert (
            len(
                await query(
                    h, "SELECT * FROM platform.messaging_jobs WHERE kind='ESCALATION_TIMER'"
                )
            )
            == 3
        )
    h.kernel._barrier = None
    assert h.adapter.calls == 0


@pytest.mark.parametrize("foreign", ["job", "claim", "step"])
async def test_forged_authority_and_legacy_entrypoints_cannot_create(control, foreign):
    h = control
    _, claim = await source(h)
    before = await facts(h)
    bad = claim.model_copy(
        update={"job_id": uuid4()}
        if foreign == "job"
        else {"claim_token": uuid4()}
        if foreign == "claim"
        else {}
    )
    with pytest.raises(MessagingError) as caught:
        if foreign == "step":
            await h.kernel.process_turn(claim)
        else:
            await h.kernel.request_escalation(bad)
    assert caught.value.code in (Code.STALE_CLAIM, Code.INVALID_INPUT)
    assert await facts(h) == before
    with pytest.raises(MessagingError):
        await h.kernel.prepare_guarded_turn(claim)
    assert await facts(h) == before


async def test_not_due_does_not_spend_attempt_then_slots_once_and_equal_expiry(control):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, before = await created(h)
        timers = await query(
            h,
            "SELECT to_jsonb(j) AS row FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY step",
            id=e["id"],
        )
        assert await h.kernel.claim_job("before-due") is None
        assert (
            await query(
                h,
                "SELECT to_jsonb(j) AS row FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY step",
                id=e["id"],
            )
            == timers
        )
        for minute, slot in ((2, "first_reminded_at"), (5, "second_reminded_at")):
            await set_clock(anchor + timedelta(minutes=minute))
            claim = await h.kernel.claim_job("remind")
            assert isinstance(claim, EscalationTimerClaim)
            result = await h.kernel.execute_escalation_timer(claim)
            assert result.outcome == "REMINDED" and result.recorded_at == anchor + timedelta(
                minutes=minute
            )
            assert (await query(h, f"SELECT {slot} FROM app.escalations WHERE id=:id", id=e["id"]))[
                0
            ][slot] == result.recorded_at
            with pytest.raises(MessagingError):
                await h.kernel.execute_escalation_timer(claim)
            assert (await read(h, e)).version == "1"
        await set_clock(anchor + timedelta(minutes=10))
        view = await read(h, e)
        assert (
            view.status == "PENDING"
            and view.validity == "EXPIRED"
            and view.waiting is None
            and not view.can_cancel
            and not view.can_resolve
        )
        with pytest.raises(EscalationError) as caught:
            await decide(h, e, "RESOLVE")
        assert caught.value.code == EscalationCode.ESCALATION_EXPIRED
        claim = await h.kernel.claim_job("expiry")
        assert claim is None  # due claim maintenance performs the terminal cleanup
        view = await read(h, e)
        assert view.status == "EXPIRED" and view.maintenance == "COMPLETE" and view.version == "2"
        assert (await state(h, e["conversation_id"]))["version"] == before["version"] + 2
        assert (
            await query(
                h,
                "SELECT count(*) n FROM platform.messaging_jobs WHERE escalation_id=:id AND escalation_outcome='EXPIRED'",
                id=e["id"],
            )
        )[0]["n"] == 1


@pytest.mark.parametrize("boundary", [-1, 0, 1])
async def test_expiry_before_equal_after_with_no_scheduler(control, boundary):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=10, microseconds=boundary))
        if boundary < 0:
            assert (await decide(h, e, "RESOLVE"))["code"] == "ACCEPTED"
        else:
            previous = await facts(h)
            with pytest.raises(EscalationError) as caught:
                await decide(h, e, "RESOLVE")
            assert caught.value.code == EscalationCode.ESCALATION_EXPIRED
            assert await facts(h) == previous


@pytest.mark.parametrize(
    "constraint",
    ["escalations_lifecycle_check", "escalations_reminders_check", "escalations_immutable_check"],
)
async def test_allowlisted_invariant_rolls_back_domain_but_commits_dead_and_failed_maintenance(
    control, constraint
):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        claim = await h.kernel.claim_job("poison")
        assert isinstance(claim, EscalationTimerClaim)
        before = (await query(h, "SELECT to_jsonb(e) row FROM app.escalations e"))[0]
        # A genuinely stricter named CHECK, while retaining the original
        # constraint under a temporary name. Production catches the database's
        # own diagnostic tuple; no fake SQL exception supplies this outcome.
        async with h.migrator.begin() as c:
            original = (
                await c.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='app.escalations'::regclass AND conname=:name"
                    ),
                    {"name": constraint},
                )
            ).scalar_one_or_none()
            if original is not None:
                await c.execute(
                    text(
                        f"ALTER TABLE app.escalations RENAME CONSTRAINT {constraint} TO escalation_test_original"
                    )
                )
            await c.execute(
                text(
                    f"ALTER TABLE app.escalations ADD CONSTRAINT {constraint} CHECK(first_reminded_at IS NULL AND second_reminded_at IS NULL)"
                )
            )
        try:
            result = await h.kernel.execute_escalation_timer(claim)
            assert (
                result.status == "DEAD"
                and result.error_code == "INVALID_INPUT"
                and result.outcome is None
                and result.recorded_at is None
            )
            assert (await query(h, "SELECT to_jsonb(e) row FROM app.escalations e"))[0] == before
            view = await read(h, e)
            assert (
                view.maintenance == "FAILED"
                and view.waiting == "WAITING_FOR_HUMAN"
                and view.can_resolve
            )
            assert await h.kernel.claim_job("no-dead-retry") is None
        finally:
            async with h.migrator.begin() as c:
                await c.execute(text(f"ALTER TABLE app.escalations DROP CONSTRAINT {constraint}"))
                if original is not None:
                    await c.execute(
                        text(
                            f"ALTER TABLE app.escalations RENAME CONSTRAINT escalation_test_original TO {constraint}"
                        )
                    )
                    restored = (
                        await c.execute(
                            text(
                                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='app.escalations'::regclass AND conname=:name"
                            ),
                            {"name": constraint},
                        )
                    ).scalar_one()
                    assert restored == original
        await set_clock(anchor + timedelta(minutes=10))
        view = await read(h, e)
        assert (
            view.status == "PENDING"
            and view.maintenance == "FAILED"
            and view.validity == "EXPIRED"
            and not view.can_resolve
            and view.waiting is None
        )
        await h.kernel.claim_job("expire-other-timers")
        assert (await read(h, e)).status == "EXPIRED" and (await read(h, e)).maintenance == "FAILED"


@pytest.mark.parametrize(
    "fault",
    [
        ("23514", "app", "escalations", "not_allowlisted"),
        ("23514", "app", "conversations", "escalations_lifecycle_check"),
        ("23505", "app", "escalations", "escalations_immutable_check"),
    ],
)
async def test_non_allowlisted_failure_never_reports_committed_dead(control, fault):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        claim = await h.kernel.claim_job("non-allowlisted")
        before = await facts(h)
        code, schema, table, constraint = fault
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    f"CREATE FUNCTION platform.escalation_test_fault() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN RAISE EXCEPTION 'injected' USING ERRCODE='{code}',SCHEMA='{schema}',TABLE='{table}',CONSTRAINT='{constraint}'; END $$"
                )
            )
            await c.execute(
                text(
                    "REVOKE ALL ON FUNCTION platform.escalation_test_fault() FROM PUBLIC,asm_runtime"
                )
            )
            await c.execute(
                text(
                    "CREATE TRIGGER zz_escalation_fault BEFORE UPDATE ON app.escalations FOR EACH ROW EXECUTE FUNCTION platform.escalation_test_fault()"
                )
            )
        try:
            with pytest.raises(DBAPIError):
                await h.kernel.execute_escalation_timer(claim)
            assert await facts(h) == before
        finally:
            async with h.migrator.begin() as c:
                await c.execute(text("DROP TRIGGER zz_escalation_fault ON app.escalations"))
                await c.execute(text("DROP FUNCTION platform.escalation_test_fault()"))


@pytest.mark.parametrize("expired", [False, True])
async def test_exhaustion_checks_due_relevance_before_dead_and_never_fails_turn(control, expired):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        job = (
            await query(
                h,
                "SELECT id FROM platform.messaging_jobs WHERE escalation_id=:id AND step='REMIND_1'",
                id=e["id"],
            )
        )[0]["id"]
        # Budget fixture only; saved schedule, wall lease/index clocks and source
        # identity are unchanged. Runtime still performs due preflight normally.
        await query(
            h,
            "UPDATE platform.messaging_jobs SET attempt_count=5,first_started_at=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING *",
            id=job,
        )
        assert await h.kernel.claim_job("before-due-exhausted") is None
        assert (await query(h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=job))[
            0
        ]["status"] == "READY"
        await set_clock(anchor + timedelta(minutes=10 if expired else 2))
        assert await h.kernel.claim_job("exhausted") is None
        row = (
            await query(
                h,
                "SELECT status,error_code,escalation_outcome FROM platform.messaging_jobs WHERE id=:id",
                id=job,
            )
        )[0]
        assert row == (
            {"status": "SUCCEEDED", "error_code": None, "escalation_outcome": "EXPIRED"}
            if expired
            else {"status": "DEAD", "error_code": "RETRY_EXHAUSTED", "escalation_outcome": None}
        )
        assert (
            await query(h, "SELECT state FROM app.conversation_turns WHERE id=:id", id=e["turn_id"])
        )[0]["state"] == "READY"
        assert (await read(h, e)).waiting == (None if expired else "WAITING_FOR_HUMAN")


async def test_timer_reclaim_rejects_old_token_and_owner_keeps_lazy_future_jobs(control):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        old = await h.kernel.claim_job("old")
        await query(
            h,
            "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING *",
            id=old.job_id,
        )
        assert await h.kernel.recover_expired() == 1
        row = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=old.job_id))[
            0
        ]
        assert (
            row["status"] == "READY"
            and row["error_code"] == "DEPENDENCY_TIMEOUT"
            and row["claim_token"] is None
        )
        with pytest.raises(MessagingError) as caught:
            await h.kernel.execute_escalation_timer(old)
        assert caught.value.code == Code.STALE_CLAIM
        new = await next_kind(h, "ESCALATION_TIMER")
        assert new.claim_token != old.claim_token
        await h.worker.execute(new)
        await decide(h, e)
        remaining = await query(
            h,
            "SELECT * FROM platform.messaging_jobs WHERE escalation_id=:id AND status='READY' ORDER BY step",
            id=e["id"],
        )
        assert {r["step"] for r in remaining} == {"REMIND_2", "EXPIRE"}
        assert all(r["claim_token"] is None and r["attempt_count"] == 0 for r in remaining)
        await set_clock(anchor + timedelta(minutes=10))
        assert await h.kernel.claim_job("lazy-noop") is None
        assert (await read(h, e)).maintenance == "COMPLETE"


async def test_owner_wait_rechecks_clock_after_real_conversation_lock(control):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=10, microseconds=-1))
        async with h.migrator.connect() as blocker:
            await blocker.begin()
            pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await blocker.execute(
                text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
                {"id": e["conversation_id"]},
            )
            pending = asyncio.create_task(decide(h, e, "RESOLVE"))
            try:
                await wait_blocked(blocker, pid, pending=pending)
                await set_clock(anchor + timedelta(minutes=10))
                await blocker.commit()
                with pytest.raises(EscalationError) as caught:
                    await pending
                assert caught.value.code == EscalationCode.ESCALATION_EXPIRED
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        assert (await read(h, e)).status == "PENDING" and not await query(
            h, "SELECT * FROM platform.escalation_command_receipts"
        )


async def test_timer_busy_rolls_back_job_lock_and_attempt(control):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        before = await query(
            h,
            "SELECT to_jsonb(j) row FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY id",
            id=e["id"],
        )
        async with h.migrator.begin() as blocker:
            await blocker.execute(
                text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
                {"id": e["conversation_id"]},
            )
            assert await h.kernel.claim_job("busy") is None
            async with h.migrator.begin() as probe:
                locked = await probe.execute(
                    text(
                        "SELECT id FROM platform.messaging_jobs WHERE escalation_id=:id FOR UPDATE NOWAIT"
                    ),
                    {"id": e["id"]},
                )
                assert len(locked.all()) == 3
            assert (
                await query(
                    h,
                    "SELECT to_jsonb(j) row FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY id",
                    id=e["id"],
                )
                == before
            )


@pytest.mark.parametrize("phase", ["before", "after"])
async def test_real_process_creation_crash_recovery_without_clock_override(control, phase):
    h = control
    _, claim = await source(h)
    child_code = r"""
import asyncio,json,os,sys
from sqlalchemy.ext.asyncio import create_async_engine
from asm.messaging.database import MessagingDatabase
from asm.messaging.results import parse_claim
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.worker import Worker
async def main():
 data=json.loads(sys.stdin.read()); engine=create_async_engine(os.environ['ASM_DATABASE_URL'],hide_parameters=True)
 async def barrier(name):
  if name==data['phase']:
   print('ESCALATION_CRASH_BOUNDARY',flush=True); os._exit(86)
 kernel=MessagingDatabase(engine,barrier=barrier,environment='TEST')
 worker=Worker(kernel,ControlledAdapter(environment='TEST'))
 await worker.execute(parse_claim(data['claim']))
asyncio.run(main())
"""
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        child_code,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        import json

        out, err = await asyncio.wait_for(
            child.communicate(
                json.dumps(
                    {
                        "phase": f"escalation_create_{phase}_commit",
                        "claim": claim.model_dump(mode="json"),
                    }
                ).encode()
            ),
            30,
        )
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
    assert child.returncode == 86 and out.strip() == b"ESCALATION_CRASH_BOUNDARY", (out, err)
    fresh = MessagingDatabase(h.runtime.engine, environment="TEST")
    if phase == "before":
        assert not await query(h, "SELECT * FROM app.escalations")
        remaining = (claim.lease_until - datetime.now(UTC)).total_seconds()
        if remaining > 0:
            await asyncio.sleep(remaining + 0.05)
        assert await fresh.recover_expired() == 1
        async with asyncio.timeout(10):
            while not await query(h, "SELECT * FROM app.escalations"):
                await Worker(fresh, h.adapter).run_once()
                await asyncio.sleep(0.02)
    else:
        saved = await fresh.replay_escalation(claim.job_id, claim.claim_token)
        assert saved.initial_status == "PENDING"
        await Worker(fresh, h.adapter).run_once()
    assert len(await query(h, "SELECT * FROM app.escalations")) == 1
    timers = await query(h, "SELECT * FROM platform.messaging_jobs WHERE kind='ESCALATION_TIMER'")
    assert len(timers) == 3 and all(
        t["status"] == "READY" and t["attempt_count"] == 0 for t in timers
    )
    assert h.adapter.calls == 0


@pytest.mark.parametrize(
    "marker", ["CONTROLLED ESCALATION TEST ", "controlled escalation test", "ordinary"]
)
async def test_non_marker_retains_one_guarded_effect(control, marker):
    h = control
    _, claim = await source(h, marker=marker)
    await h.worker.execute(claim)
    send = await next_kind(h, "SEND_GUARDED_TEXT")
    await h.worker.execute(send)
    assert h.adapter.calls == h.adapter.effects == 1
    assert not await query(h, "SELECT * FROM app.escalations")


async def test_caller_refs_do_not_replace_canonical_job_workspace(control):
    h = control
    _, claim = await source(h)
    result = await h.kernel.request_escalation(
        claim.model_copy(update={"workspace_id": B, "connection_id": uuid4(), "turn_id": uuid4()})
    )
    assert result.workspace_id == A and result.turn_id == claim.turn_id
    assert (await query(h, "SELECT workspace_id FROM app.escalations"))[0]["workspace_id"] == A


@pytest.mark.parametrize("change", ["owner", "channel", "product", "takeover"])
async def test_creation_rechecks_live_resume_authority_and_product_after_claim(control, change):
    h = control
    cid, claim = await source(h)
    if change == "owner":
        await query(
            h,
            "UPDATE platform.workspace_memberships SET role='PROVIDER' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING *",
            ws=A,
            actor=UA,
        )
    elif change == "channel":
        await query(
            h,
            "UPDATE app.channel_connections SET status='INACTIVE' WHERE id=:id RETURNING *",
            id=claim.connection_id,
        )
    elif change == "product":
        await query(
            h,
            "UPDATE platform.workspace_subscriptions SET effective_until=clock_timestamp()-interval '1 second' WHERE workspace_id=:ws RETURNING *",
            ws=A,
        )
    else:
        await execute(h, cid, "TAKEOVER", "before-creation")
    before = await state(h, cid)
    result = await h.kernel.request_escalation(claim)
    assert isinstance(result, EscalationProgress) and result.code in ("STALE", "NOT_ALLOWED")
    assert not await query(h, "SELECT * FROM app.escalations")
    assert await state(h, cid) == before and h.adapter.calls == 0
    assert (
        await query(h, "SELECT state FROM app.conversation_turns WHERE id=:id", id=claim.turn_id)
    )[0]["state"] == "READY"


async def test_two_decision_keys_and_cancel_reminder_race_keep_one_terminal(control):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        timer = await h.kernel.claim_job("racing-reminder")
        outcomes = await asyncio.gather(
            decide(h, e, "RESOLVE", "one"),
            decide(h, e, "CANCEL", "two"),
            h.kernel.execute_escalation_timer(timer),
            return_exceptions=True,
        )
        decisions = outcomes[:2]
        assert (
            sum(isinstance(value, dict) and value["code"] == "ACCEPTED" for value in decisions) == 1
        )
        assert (
            sum(
                isinstance(value, EscalationError) and value.code == EscalationCode.ESCALATION_FINAL
                for value in decisions
            )
            == 1
        )
        assert outcomes[2].outcome in ("REMINDED", "NOOP_TERMINAL")
        assert len(await query(h, "SELECT * FROM platform.escalation_command_receipts")) == 1
        assert (
            len(
                await query(
                    h, "SELECT * FROM app.audit_events WHERE event_type='ESCALATION_DECIDED'"
                )
            )
            == 1
        )
        assert (await read(h, e)).version == "2"


async def test_blocked_conversation_does_not_hold_timer_or_starve_other_conversation(control):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        first, _, _ = await created(h)
        second, _, _ = await created(h, suffix="second", chat="other-chat")
        await set_clock(anchor + timedelta(minutes=2))
        async with h.migrator.begin() as blocker:
            await blocker.execute(
                text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
                {"id": first["conversation_id"]},
            )
            claim = await h.kernel.claim_job("healthy-after-busy")
            assert claim.escalation_id == second["id"]
            await h.worker.execute(claim)
            rows = await query(
                h,
                "SELECT attempt_count,status FROM platform.messaging_jobs WHERE escalation_id=:id AND step='REMIND_1'",
                id=first["id"],
            )
            assert rows == [{"attempt_count": 0, "status": "READY"}]
        claim = await h.kernel.claim_job("formerly-busy")
        assert claim.escalation_id == first["id"]


@pytest.mark.parametrize("phase", ["before", "after"])
async def test_timer_commit_fault_has_no_speculative_success_and_fresh_canonical_job(
    control, phase
):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        claim = await h.kernel.claim_job("timer-ack")

        async def fail(name):
            if name == f"escalation_timer_{phase}_commit":
                raise SQLAlchemyError("injected acknowledgement boundary")

        h.kernel._barrier = fail
        try:
            with pytest.raises(SQLAlchemyError):
                await h.worker.execute(claim)
        finally:
            h.kernel._barrier = None
        # Fresh canonical read is evidence; the failed invocation returned none.
        row = (
            await query(
                h,
                "SELECT status,escalation_outcome FROM platform.messaging_jobs WHERE id=:id",
                id=claim.job_id,
            )
        )[0]
        esc = (
            await query(h, "SELECT first_reminded_at FROM app.escalations WHERE id=:id", id=e["id"])
        )[0]
        assert row == (
            {"status": "RUNNING", "escalation_outcome": None}
            if phase == "before"
            else {"status": "SUCCEEDED", "escalation_outcome": "REMINDED"}
        )
        assert esc["first_reminded_at"] == (
            None if phase == "before" else anchor + timedelta(minutes=2)
        )


@pytest.mark.parametrize("phase", ["before", "after"])
async def test_separate_process_timer_commit_boundary_and_restart(control, phase):
    """Only policy time is synthetic; crashed lease expires on the real DB clock."""
    import json

    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        await set_clock(anchor + timedelta(minutes=2))
        claim = await h.kernel.claim_job("timer-process")
        child_code = r"""
import asyncio,json,os,sys
from sqlalchemy.ext.asyncio import create_async_engine
from asm.messaging.database import MessagingDatabase
from asm.messaging.results import parse_claim
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.worker import Worker
async def main():
 data=json.loads(sys.stdin.read())
 engine=create_async_engine(os.environ['ASM_DATABASE_URL'],hide_parameters=True)
 async def barrier(name):
  if name==data['phase']:
   print('ESCALATION_TIMER_CRASH',flush=True); os._exit(86)
 worker=Worker(MessagingDatabase(engine,barrier=barrier,environment='TEST'),ControlledAdapter(environment='TEST'))
 await worker.execute(parse_claim(data['claim']))
asyncio.run(main())
"""
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            child_code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                child.communicate(
                    json.dumps(
                        {
                            "phase": f"escalation_timer_{phase}_commit",
                            "claim": claim.model_dump(mode="json"),
                        }
                    ).encode()
                ),
                30,
            )
        finally:
            if child.returncode is None:
                child.kill()
                await child.wait()
        assert child.returncode == 86 and out.strip() == b"ESCALATION_TIMER_CRASH", (out, err)
        current = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=e["id"]))[0]
        assert current["first_reminded_at"] == (
            None if phase == "before" else anchor + timedelta(minutes=2)
        )
        fresh = MessagingDatabase(h.runtime.engine, environment="TEST")
        if phase == "before":
            remaining = (claim.lease_until - datetime.now(UTC)).total_seconds()
            if remaining > 0:
                await asyncio.sleep(remaining + 0.05)
            assert await fresh.recover_expired() == 1
            async with asyncio.timeout(10):
                while (
                    await query(
                        h,
                        "SELECT status FROM platform.messaging_jobs WHERE id=:id",
                        id=claim.job_id,
                    )
                )[0]["status"] != "SUCCEEDED":
                    await Worker(fresh, h.adapter).run_once()
                    await asyncio.sleep(0.02)
        else:
            assert await fresh.recover_expired() == 0
            assert not await Worker(fresh, h.adapter).run_once()
        with pytest.raises(MessagingError) as caught:
            await fresh.execute_escalation_timer(claim)
        assert caught.value.code == Code.STALE_CLAIM
        row = (
            await query(
                h,
                "SELECT status,escalation_outcome,attempt_count FROM platform.messaging_jobs WHERE id=:id",
                id=claim.job_id,
            )
        )[0]
        assert row == {
            "status": "SUCCEEDED",
            "escalation_outcome": "REMINDED",
            "attempt_count": 2 if phase == "before" else 1,
        }
        current = (
            await query(
                h,
                "SELECT first_reminded_at,second_reminded_at,status,version FROM app.escalations WHERE id=:id",
                id=e["id"],
            )
        )[0]
        assert current == {
            "first_reminded_at": anchor + timedelta(minutes=2),
            "second_reminded_at": None,
            "status": "PENDING",
            "version": 1,
        }
        assert h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize(
    "target", ["context", "request", "REMIND_1", "REMIND_2", "EXPIRE", "source_terminal"]
)
async def test_creation_database_fault_at_each_write_rolls_back_entire_acceptance(control, target):
    h = control
    cid, claim = await source(h)
    current = await state(h, cid)
    before = await facts(h)
    if target == "context":
        table = "app.conversations"
        check = f"id<>'{cid}'::uuid OR version<={current['version']}"
    elif target == "request":
        table, check = "app.escalations", "false"
    elif target == "source_terminal":
        table = "platform.messaging_jobs"
        check = "step IS DISTINCT FROM 'ESCALATE_OWNER' OR status<>'SUCCEEDED'"
    else:
        table = "platform.messaging_jobs"
        check = f"kind<>'ESCALATION_TIMER' OR step<>'{target}'"
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                f"ALTER TABLE {table} ADD CONSTRAINT escalation_creation_fault CHECK({check}) NOT VALID"
            )
        )
    try:
        with pytest.raises(DBAPIError) as caught:
            await h.kernel.request_escalation(claim)
        assert caught.value.orig.sqlstate == "23514"
        assert caught.value.orig.diag.constraint_name == "escalation_creation_fault"
        assert await facts(h) == before
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT escalation_creation_fault"))
    result = await h.kernel.request_escalation(claim)
    assert isinstance(result, EscalationCreationResult)
    assert len(await query(h, "SELECT id FROM app.escalations")) == 1
    assert (
        len(
            await query(
                h,
                "SELECT id FROM platform.messaging_jobs WHERE escalation_id=:id",
                id=result.escalation_id,
            )
        )
        == 3
    )
    assert h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize("material", ["file", "delivery"])
async def test_pending_wait_is_invalidated_by_late_existing_file_or_delivery_result(
    control, material
):
    from asm.files.database import FileDatabase
    from test_m2_2_db_postgres import MANIFEST

    h = control
    cid, _, _ = await incoming(h)
    if material == "file":
        receipt = await ingest(
            h, event(event_id="older-photo", message_id="older-photo", image_file_id="image")
        )
        await process_receipt(h, receipt)
        delayed = await next_kind(h, "FETCH_IMAGE")
    else:
        await command(h, cid, "earlier manual", "older-manual")
        delayed = await next_kind(h, "SEND_MANUAL_TEXT")
    e, _, _ = await created(h, conversation=cid)
    before = await state(h, cid)
    if material == "file":
        files = FileDatabase(h.kernel)
        permit = await files.prepare_upload(delayed, MANIFEST)
        assert (
            await files.finish_fetch(delayed.job_id, delayed.claim_token, permit.intent_id)
        ).status == "READY"
    else:
        await h.worker.execute(delayed)
    view = await read(h, e)
    after = await state(h, cid)
    assert view.status == "CANCELLED" and view.closure.reason == "CONTEXT_CHANGED"
    assert after["version"] == before["version"] + 1
    assert after["control_generation"] == before["control_generation"]
    assert h.adapter.calls == h.adapter.effects == (material == "delivery")
    assert not await query(h, "SELECT id FROM platform.escalation_command_receipts")


@pytest.mark.parametrize("resolved", [False, True])
async def test_late_same_turn_file_revision_preserves_lifetime_escalation_identity(
    control, resolved
):
    from asm.files.database import FileDatabase
    from test_m2_2_db_postgres import MANIFEST

    h = control
    cid, _, _ = await incoming(h)
    await execute(h, cid, "RESUME", "late-file-resume")
    for value in (
        event(event_id="late-marker", message_id="late-marker", text=MARKER),
        event(event_id="late-photo", message_id="late-photo", image_file_id="image"),
    ):
        await process_receipt(h, await ingest(h, value))
    fetch = await next_kind(h, "FETCH_IMAGE")
    # Preserve the accepted real 15-second media deadline; no due/clock mutation.
    async with asyncio.timeout(25):
        while True:
            claim = await h.kernel.claim_job("late-escalation")
            if claim is None:
                await asyncio.sleep(0.03)
                continue
            if claim.kind == "PROCESS_TURN" and claim.step == "ESCALATE_OWNER":
                break
            await h.worker.execute(claim)
    result = await h.kernel.request_escalation(claim)
    assert isinstance(result, EscalationCreationResult)
    e = (await query(h, "SELECT * FROM app.escalations"))[0]
    assert (
        await query(
            h,
            "SELECT turn_id FROM app.conversation_turn_messages WHERE file_id=:id",
            id=fetch.file_id,
        )
    )[0]["turn_id"] == e["turn_id"]
    assert e["request_snapshot"]["readiness"] == "PARTIAL"
    timers = await query(
        h,
        "SELECT to_jsonb(j) row FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY id",
        id=e["id"],
    )
    if resolved:
        await decide(h, e, "RESOLVE")
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(fetch, MANIFEST)
    assert (
        await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    ).status == "READY"
    revised = await next_kind(h, "PROCESS_TURN", "ESCALATE_OWNER")
    progress = await h.kernel.request_escalation(revised)
    assert progress.code == "ALREADY_ESCALATED" and progress.escalation_id == e["id"]
    assert revised.turn_revision > result.turn_revision
    assert len(await query(h, "SELECT id FROM app.escalations")) == 1
    assert (
        await query(
            h,
            "SELECT to_jsonb(j) row FROM platform.messaging_jobs j WHERE escalation_id=:id ORDER BY id",
            id=e["id"],
        )
        == timers
    )
    assert (await read(h, e)).status == ("RESOLVED" if resolved else "CANCELLED")
    assert await h.kernel.replay_escalation(claim.job_id, claim.claim_token) == result
    assert not await query(
        h, "SELECT id FROM platform.turn_guard_receipts WHERE outcome='ACCEPTED'"
    )
    assert h.adapter.calls == h.adapter.effects == 0


@pytest.mark.parametrize("wrong", ["request", "version", "status", "operation", "event_type"])
async def test_typed_receipt_terminal_and_audit_links_reject_each_remaining_substitution(
    control, wrong
):
    h = control
    e, _, _ = await created(h)
    await decide(h, e, "RESOLVE")
    async with h.migrator.begin() as c:
        original = (
            await c.execute(text("SELECT to_jsonb(r) FROM platform.escalation_command_receipts r"))
        ).scalar_one()
        changed = dict(original)
        field, value = {
            "request": ("escalation_id", str(uuid4())),
            "version": ("accepted_version", 3),
            "status": ("accepted_status", "CANCELLED"),
            "operation": ("operation", "CANCEL"),
            "event_type": ("audit_event_type", "CONVERSATION_CONTROL_CHANGED"),
        }[wrong]
        changed[field] = value
        changed["result"] = dict(original["result"])
        if field in changed["result"]:
            changed["result"][field] = str(value) if field == "accepted_version" else value
        # Keep status/operation shape valid for the terminal-status FK probe.
        if wrong == "status":
            changed["operation"] = changed["result"]["operation"] = "CANCEL"
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():
                await c.execute(
                    text("DELETE FROM platform.escalation_command_receipts WHERE id=:id"),
                    {"id": original["id"]},
                )
                await c.execute(
                    text(
                        "INSERT INTO platform.escalation_command_receipts SELECT (jsonb_populate_record(NULL::platform.escalation_command_receipts,CAST(:row AS jsonb))).*"
                    ),
                    {"row": json.dumps(changed)},
                )
        assert caught.value.orig.sqlstate == (
            "23503" if wrong in ("request", "status") else "23514"
        )
        diag = caught.value.orig.diag
        assert (diag.schema_name, diag.table_name) == ("platform", "escalation_command_receipts")
        assert diag.constraint_name is not None
        # The reported database constraint must be one of the actual typed
        # terminal/relation/Audit FKs or the exact scalar/pair CHECK, not a unique
        # collision from reusing the receipt. Preserve the original row on error.
        definition = (
            await c.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='platform.escalation_command_receipts'::regclass AND conname=:name"
                ),
                {"name": diag.constraint_name},
            )
        ).scalar_one()
        if wrong in ("request", "status"):
            assert definition.startswith("FOREIGN KEY (workspace_id,")
            assert (
                "REFERENCES app.escalations(" in definition
                or "REFERENCES app.audit_events(" in definition
            )
        elif wrong == "version":
            assert "accepted_version = 2" in definition
        elif wrong == "event_type":
            assert "audit_event_type = 'ESCALATION_DECIDED'" in definition
        else:
            assert (
                "operation = 'RESOLVE'" in definition
                and "accepted_status = 'RESOLVED'" in definition
            )
        assert (
            await c.execute(text("SELECT to_jsonb(r) FROM platform.escalation_command_receipts r"))
        ).scalar_one() == original


@pytest.mark.parametrize("entry", ["claim", "recovery"])
async def test_allowlisted_expiry_failure_survives_actual_claim_exhaustion_and_recovery(
    control, entry
):
    h = control
    async with serial_clock(h) as (anchor, set_clock):
        e, _, _ = await created(h)
        timer = (
            await query(
                h,
                "SELECT * FROM platform.messaging_jobs WHERE escalation_id=:id AND step='REMIND_1'",
                id=e["id"],
            )
        )[0]
        if entry == "recovery":
            await set_clock(anchor + timedelta(minutes=2))
            claim = await h.kernel.claim_job("poison-recovery")
            assert claim.job_id == timer["id"]
        await query(
            h,
            "UPDATE platform.messaging_jobs SET attempt_count=5,first_started_at=coalesce(first_started_at,clock_timestamp()) WHERE id=:id RETURNING *",
            id=timer["id"],
        )
        before_request = (await query(h, "SELECT to_jsonb(e) row FROM app.escalations e"))[0]
        before_context = await state(h, e["conversation_id"])
        async with h.migrator.begin() as c:
            original = (
                await c.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='app.escalations'::regclass AND conname='escalations_lifecycle_check'"
                    )
                )
            ).scalar_one()
            await c.execute(
                text(
                    "ALTER TABLE app.escalations RENAME CONSTRAINT escalations_lifecycle_check TO escalation_test_lifecycle_original"
                )
            )
            await c.execute(
                text(
                    "ALTER TABLE app.escalations ADD CONSTRAINT escalations_lifecycle_check CHECK(status='PENDING')"
                )
            )
        try:
            await set_clock(anchor + timedelta(minutes=10))
            fresh = MessagingDatabase(h.runtime.engine, environment="TEST")
            if entry == "recovery":
                # The real DB lease expires; only policy time uses the accepted
                # private seam. Do not rewrite lease_until to manufacture recovery.
                remaining = (claim.lease_until - datetime.now(UTC)).total_seconds()
                if remaining > 0:
                    await asyncio.sleep(remaining + 0.05)
                assert await fresh.recover_expired() == 1
                assert await fresh.recover_expired() == 0
            else:
                assert await fresh.claim_job("poison-exhaustion") is None
                assert await fresh.claim_job("no-dead-reclaim") is None
            persisted = (
                await query(
                    h,
                    "SELECT status,error_code,escalation_outcome,claim_token,lease_until,worker_id FROM platform.messaging_jobs WHERE id=:id",
                    id=timer["id"],
                )
            )[0]
            assert persisted == dict(
                status="DEAD",
                error_code="INVALID_INPUT",
                escalation_outcome=None,
                claim_token=None,
                lease_until=None,
                worker_id=None,
            )
            assert (await query(h, "SELECT to_jsonb(e) row FROM app.escalations e"))[
                0
            ] == before_request
            assert await state(h, e["conversation_id"]) == before_context
            view = await read(h, e)
            assert (
                view.status == "PENDING"
                and view.validity == "EXPIRED"
                and view.maintenance == "FAILED"
            )
            assert view.waiting is None and not view.can_resolve and not view.can_cancel
        finally:
            async with h.migrator.begin() as c:
                await c.execute(
                    text("ALTER TABLE app.escalations DROP CONSTRAINT escalations_lifecycle_check")
                )
                await c.execute(
                    text(
                        "ALTER TABLE app.escalations RENAME CONSTRAINT escalation_test_lifecycle_original TO escalations_lifecycle_check"
                    )
                )
                assert (
                    await c.execute(
                        text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='app.escalations'::regclass AND conname='escalations_lifecycle_check'"
                        )
                    )
                ).scalar_one() == original
