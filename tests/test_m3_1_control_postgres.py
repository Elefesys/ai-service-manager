"""CONTROL invariants through real PostgreSQL owner/worker capabilities."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.conversations.control import ControlCode, ControlError, control_fingerprint
from asm.conversations.http_models import ControlCommandRequest
from asm.conversations.turns import TurnSnapshot, consume
from asm.tenancy import AuthenticatedAccount, TenancyError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_models import event
from test_m2_1_postgres import command, ingest, query
from test_m2_1_postgres import messaging as messaging
from test_m2_3_db_postgres import BOT, ingress, projection
from test_m2_3_db_postgres import telegram as telegram
from test_tenancy_postgres import PROVIDER, UA, UB, A, B, raw_context
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def control(telegram):
    try:
        yield telegram
    finally:
        # This wrapper owns CONTROL children before the retained Telegram fixture
        # removes its shared billing Audit. No cascade or constraint bypass.
        async with telegram.migrator.begin() as c:
            await c.execute(
                text(
                    "DELETE FROM platform.conversation_control_receipts WHERE workspace_id IN (:a,:b)"
                ),
                {"a": A, "b": B},
            )
            await c.execute(
                text(
                    "DELETE FROM app.audit_events WHERE workspace_id IN (:a,:b) AND object_type='CONVERSATION'"
                ),
                {"a": A, "b": B},
            )


async def state(h, cid):
    return (await query(h, "SELECT * FROM app.conversations WHERE id=:id", id=cid))[0]


def body(row):
    return ControlCommandRequest(
        expected_client_id=str(row["client_id"]),
        expected_control_generation=str(row["control_generation"]),
        expected_context_version=str(row["version"]),
    )


async def execute(
    h,
    cid,
    operation="TAKEOVER",
    key="control",
    expected=None,
    *,
    actor=UA,
    workspace=A,
    prepare=False,
):
    expected = expected or body(await state(h, cid))
    async with h.runtime.tenancy.transaction(
        AuthenticatedAccount(actor), workspace, uuid4()
    ) as unit:
        args = (
            cid,
            UUID(expected.expected_client_id),
            operation,
            key,
            int(expected.expected_control_generation),
            int(expected.expected_context_version),
        )
        if prepare:
            await unit.conversation_control_prepare(*args)
        return await unit.conversation_control_execute(*args)


async def process_receipt(h, receipt):
    """Use the normal queue; unrelated due jobs execute, never reschedule/filter."""
    target = UUID(str(receipt["job_id"])) if isinstance(receipt, dict) else receipt.job_id
    async with asyncio.timeout(5):
        while True:
            claim = await h.kernel.claim_job("control-test")
            assert claim is not None, "accepted Inbox job must be due"
            if claim.job_id == target:
                return await h.kernel.process_inbox(claim)
            await h.worker.execute(claim)


async def incoming(h, provider="CONTROLLED", number=1, *, process=True, message=None):
    if provider == "CONTROLLED":
        rec = await ingest(
            h, event(event_id=f"control-{number}", message_id=str(message or number))
        )
    else:
        rec = await ingress(
            h, projection(update=str(10000 + number), message=str(message or 20000 + number))
        )
    if not process:
        return rec
    result = await process_receipt(h, rec)
    cid = (
        await query(
            h, "SELECT conversation_id FROM app.messages WHERE id=:id", id=result.message_id
        )
    )[0]["conversation_id"]
    return cid, rec, result


async def wait_blocked(h, blocker):
    async with asyncio.timeout(1.5):
        while True:
            rows = await query(
                h,
                "SELECT pid,wait_event_type FROM pg_stat_activity WHERE :blocker=ANY(pg_blocking_pids(pid))",
                blocker=blocker,
            )
            if rows:
                assert all(row["wait_event_type"] == "Lock" for row in rows)
                return rows
            await asyncio.sleep(0)


async def counts_control(h):
    tables = (
        "app.conversations",
        "app.audit_events",
        "platform.conversation_control_receipts",
        "app.messages",
        "app.outbox_events",
        "platform.messaging_command_receipts",
        "platform.messaging_jobs",
    )
    return {
        table: await query(
            h, f"SELECT to_jsonb(t) AS row FROM {table} t ORDER BY to_jsonb(t)::text"
        )
        for table in tables
    }


@pytest.mark.parametrize("operation", ["TAKEOVER", "RESUME"])
@pytest.mark.parametrize("initial", ["HUMAN", "AI"])
async def test_control_transition_matrix_and_db_fingerprint(control, operation, initial):
    h = control
    cid, _, _ = await incoming(h)
    if initial == "AI":
        await execute(h, cid, "RESUME", "initial")
    before = await state(h, cid)
    expected = body(before)
    jobs = await query(h, "SELECT to_jsonb(j) AS row FROM platform.messaging_jobs j ORDER BY id")
    result = await execute(h, cid, operation, "new-intent", expected)
    after = await state(h, cid)
    assert after["control_mode"] == ("HUMAN" if operation == "TAKEOVER" else "AI")
    assert (
        after["control_generation"] == before["control_generation"] + 1
        and after["version"] == before["version"]
    )
    assert (after["activation_fence_seq"] is None) == (operation == "TAKEOVER")
    if operation == "RESUME" and initial == "AI":
        assert after["activation_fence_seq"] > before["activation_fence_seq"]
    assert result["request_fingerprint"] == control_fingerprint(A, UA, cid, expected, operation)
    assert result["code"] == "ACCEPTED"
    replay = await execute(h, cid, operation, "new-intent", expected)
    assert replay == {**result, "code": "REPLAY"}
    assert await state(h, cid) == after
    assert jobs == await query(
        h, "SELECT to_jsonb(j) AS row FROM platform.messaging_jobs j ORDER BY id"
    )
    audit = (
        await query(
            h,
            "SELECT * FROM app.audit_events WHERE audit_event_id=:id",
            id=UUID(result["result"]["audit_event_id"]),
        )
    )[0]
    assert audit["object_id"] == cid and audit["object_version"] == before["version"]
    assert (
        audit["actor_user_account_id"] == UA
        and audit["conversation_control_generation"] == after["control_generation"]
    )
    assert audit["payload"] == {
        "previous_mode": initial,
        "control_mode": after["control_mode"],
        "previous_generation": str(before["control_generation"]),
        "control_generation": str(after["control_generation"]),
    }


async def test_concurrent_same_key_two_tabs_and_receipt_namespace(control):
    h = control
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid))
    outcomes = await asyncio.gather(
        *(execute(h, cid, "RESUME", "same", expected) for _ in range(4))
    )
    assert sorted(r["code"] for r in outcomes) == ["ACCEPTED", "REPLAY", "REPLAY", "REPLAY"]
    assert len({json.dumps(r["result"], sort_keys=True) for r in outcomes}) == 1
    accepted = outcomes[0]
    expected2 = body(await state(h, cid))
    outcomes = await asyncio.gather(
        *(
            execute(h, cid, op, key, expected2)
            for op, key in (("TAKEOVER", "tab-a"), ("RESUME", "tab-b"))
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) and r["code"] == "ACCEPTED" for r in outcomes) == 1
    errors = [r for r in outcomes if isinstance(r, ControlError)]
    assert len(errors) == 1 and errors[0].code == ControlCode.STALE_STATE
    saved = await execute(h, cid, "RESUME", "same", expected)
    assert saved["result"] == accepted["result"]
    with pytest.raises(ControlError, match="IDEMPOTENCY_KEY_CONFLICT"):
        await execute(h, cid, "TAKEOVER", "same", expected)
    altered = expected.model_copy(update={"expected_context_version": "999"})
    with pytest.raises(ControlError, match="IDEMPOTENCY_KEY_CONFLICT"):
        await execute(h, cid, "RESUME", "same", altered)
    with pytest.raises(ControlError, match="STALE_STATE"):
        await execute(h, cid, "TAKEOVER", "new-stale", expected)


@pytest.mark.parametrize("dimension", ["actor", "context"])
async def test_control_receipt_named_audit_fk_rejects_locally_coherent_substitution(
    control, dimension
):
    h = control
    cid, _, _ = await incoming(h)
    accepted = await execute(h, cid)
    before = await counts_control(h)
    async with h.migrator.begin() as c:
        original = dict(
            (
                await c.execute(
                    text("SELECT * FROM platform.conversation_control_receipts WHERE id=:id"),
                    {"id": UUID(accepted["result"]["receipt_id"])},
                )
            )
            .mappings()
            .one()
        )
        changed = dict(original)
        if dimension == "actor":
            changed["actor_user_account_id"] = PROVIDER
            assert (
                await c.execute(
                    text(
                        "SELECT count(*) FROM platform.workspace_memberships WHERE workspace_id=:ws AND user_account_id IN (:a,:b)"
                    ),
                    {"ws": A, "a": UA, "b": PROVIDER},
                )
            ).scalar_one() == 2
        else:
            changed["expected_context_version"] += 1
            changed["context_version"] += 1
            changed["result"] = {
                **original["result"],
                "context_version": str(changed["context_version"]),
            }
        request = ControlCommandRequest(
            expected_client_id=str(changed["client_id"]),
            expected_control_generation=str(changed["expected_generation"]),
            expected_context_version=str(changed["expected_context_version"]),
        )
        changed["request_fingerprint"] = bytes.fromhex(
            control_fingerprint(
                A, changed["actor_user_account_id"], cid, request, changed["operation"]
            )
        )
        changed.pop("audit_event_type")  # Generated discriminator is never caller supplied.
        changed["result"] = json.dumps(changed["result"])
        columns = tuple(changed)
        values = ",".join("CAST(:result AS jsonb)" if k == "result" else ":" + k for k in columns)
        with pytest.raises(DBAPIError) as failure:
            async with c.begin_nested():
                await c.execute(
                    text("DELETE FROM platform.conversation_control_receipts WHERE id=:id"),
                    {"id": original["id"]},
                )
                await c.execute(
                    text(
                        f"INSERT INTO platform.conversation_control_receipts({','.join(columns)}) VALUES({values})"
                    ),
                    changed,
                )
        assert failure.value.orig.sqlstate == "23503"
        assert failure.value.orig.diag.constraint_name == "conversation_control_receipts_audit_fk"
    assert await counts_control(h) == before


@asynccontextmanager
async def fail_insert(h, table, *, deferred=False):
    """Privileged TEST-only fault at a real write/commit, removed before inventories."""
    assert h.runtime.engine.url.database == "asm_test"
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform._control_test_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'CONTROL_TEST_FAULT' USING ERRCODE='23514'; END $$"
            )
        )
        prefix = "CREATE CONSTRAINT TRIGGER" if deferred else "CREATE TRIGGER"
        delay = " DEFERRABLE INITIALLY DEFERRED" if deferred else ""
        await c.execute(
            text(
                f"{prefix} control_test_fault AFTER INSERT ON {table}{delay} FOR EACH ROW EXECUTE FUNCTION platform._control_test_fault()"
            )
        )
    try:
        yield
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text(f"DROP TRIGGER control_test_fault ON {table}"))
            await c.execute(text("DROP FUNCTION platform._control_test_fault()"))


@pytest.mark.parametrize(
    "table,deferred",
    [
        ("app.audit_events", False),
        ("platform.conversation_control_receipts", False),
        ("platform.conversation_control_receipts", True),
    ],
)
async def test_control_atomic_write_and_late_commit_failure(control, table, deferred):
    h = control
    cid, _, _ = await incoming(h)
    before = await counts_control(h)
    async with fail_insert(h, table, deferred=deferred):
        with pytest.raises(DBAPIError, match="CONTROL_TEST_FAULT"):
            await execute(h, cid, "RESUME")
    assert await counts_control(h) == before
    assert (await execute(h, cid, "RESUME"))["code"] == "ACCEPTED"


@pytest.mark.parametrize(
    "table",
    [
        "app.messages",
        "app.outbox_events",
        "app.audit_events",
        "platform.messaging_command_receipts",
        "platform.messaging_jobs",
    ],
)
async def test_manual_atomic_takeover_rolls_back_at_each_m2_write(control, table):
    h = control
    cid, _, _ = await incoming(h)
    await execute(h, cid, "RESUME")
    before = await counts_control(h)
    async with fail_insert(h, table):
        with pytest.raises(DBAPIError, match="CONTROL_TEST_FAULT"):
            await command(h, cid, " exact manual ", "manual")
    assert await counts_control(h) == before
    old = await state(h, cid)
    accepted = await command(h, cid, " exact manual ", "manual")
    replay = await command(h, cid, " exact manual ", "manual")
    assert replay.message_id == accepted.message_id
    new = await state(h, cid)
    assert new["control_mode"] == "HUMAN" and new["activation_fence_seq"] is None
    assert (
        new["control_generation"] == old["control_generation"] + 1
        and new["version"] == old["version"] + 1
    )
    assert len(await query(h, "SELECT id FROM platform.conversation_control_receipts")) == 1


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
async def test_control_process_death_commit_loss_replays_original(control, point):
    h = control
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid))
    script = """
import asyncio,json,os,sys
from uuid import UUID,uuid4
from asm.foundation import RuntimeDatabase,Settings
from asm.tenancy import AuthenticatedAccount
async def main():
 s=Settings(); assert s.environment=='TEST'
 d=RuntimeDatabase(s); await d.check()
 async with d.tenancy.transaction(AuthenticatedAccount(UUID(sys.argv[1])),UUID(sys.argv[2]),uuid4()) as u:
  r=await u.conversation_control_execute(UUID(sys.argv[3]),UUID(sys.argv[4]),'RESUME','crash',int(sys.argv[5]),int(sys.argv[6]))
  print(json.dumps(r),flush=True)
  if sys.argv[7]=='before_commit': os._exit(43)
 os._exit(44)
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(UA),
        str(A),
        str(cid),
        expected.expected_client_id,
        expected.expected_control_generation,
        expected.expected_context_version,
        point,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, error = await asyncio.wait_for(process.communicate(), 10)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == (43 if point == "before_commit" else 44), (output, error)
    first = json.loads(output)
    result = await execute(h, cid, "RESUME", "crash", expected)
    assert result["code"] == ("ACCEPTED" if point == "before_commit" else "REPLAY")
    if point == "after_commit":
        assert result["result"] == first["result"]
    assert (await state(h, cid))["control_generation"] == 2
    assert len(await query(h, "SELECT id FROM platform.conversation_control_receipts")) == 1


async def test_overflow_replay_and_context_boundary(control):
    h = control
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid))
    saved = await execute(h, cid, "TAKEOVER", "saved", expected)
    await query(
        h,
        "UPDATE app.conversations SET control_generation=9223372036854775807 WHERE id=:id RETURNING id",
        id=cid,
    )
    with pytest.raises(ControlError, match="CONTROL_VERSION_EXHAUSTED"):
        await execute(h, cid, "TAKEOVER", "overflow")
    assert (await execute(h, cid, "TAKEOVER", "saved", expected))["result"] == saved["result"]
    with pytest.raises(Exception, match="NOT_ALLOWED"):
        await command(h, cid)
    await query(
        h,
        "UPDATE app.conversations SET control_generation=3,version=9223372036854775807 WHERE id=:id RETURNING id",
        id=cid,
    )
    with pytest.raises(Exception, match="NOT_ALLOWED"):
        await command(h, cid)
    result = await execute(h, cid, "TAKEOVER", "max-context")
    assert result["result"]["context_version"] == "9223372036854775807"


async def test_owner_client_tenant_and_private_capabilities(control):
    h = control
    cid, _, _ = await incoming(h)
    expected = body(await state(h, cid))
    for actor, ws in ((PROVIDER, A), (UB, B)):
        with pytest.raises((ControlError, TenancyError)):
            await execute(h, cid, actor=actor, workspace=ws, expected=expected)
    with pytest.raises(ControlError, match="NOT_FOUND"):
        await execute(
            h, cid, expected=expected.model_copy(update={"expected_client_id": str(uuid4())})
        )
    async with h.runtime.engine.begin() as c:
        await raw_context(c)
        for sql in (
            "SELECT * FROM platform.conversation_control_receipts",
            "SELECT nextval('platform.turn_ingress_seq')",
            "SELECT platform.conversation_manual_takeover(:ws,:cid)",
            "SELECT platform.conversation_turn_activation_matches(:ws,:cid)",
            "SELECT platform.conversation_control_fingerprint(:ws,:actor,:cid,:client,'TAKEOVER',1,2)",
            "SELECT platform.conversation_control_locked(:cid,:client,'TAKEOVER','forged',1,2)",
        ):
            with pytest.raises(DBAPIError) as failure:
                async with c.begin_nested():
                    await c.execute(
                        text(sql),
                        {
                            "ws": A,
                            "actor": UA,
                            "cid": cid,
                            "client": UUID(expected.expected_client_id),
                        },
                    )
            assert failure.value.orig.sqlstate == "42501"
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        with pytest.raises(TenancyError):
            await asyncio.create_task(unit.conversation_control_read(cid))
    with pytest.raises(TenancyError):
        await unit.post_lock_product_snapshot()
    await query(
        h,
        "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING workspace_id",
        ws=A,
        actor=UA,
    )
    with pytest.raises((ControlError, TenancyError)):
        await execute(h, cid, expected=expected)


@pytest.mark.parametrize("provider", ["CONTROLLED", "TELEGRAM"])
@pytest.mark.parametrize("commit_ingress", [False, True])
async def test_ingress_capture_serializes_resume_and_rollbacks(control, provider, commit_ingress):
    h = control
    cid, _, _ = await incoming(h, provider)
    before = body(await state(h, cid))
    async with h.runtime.engine.connect() as c:
        tx = await c.begin()
        if provider == "CONTROLLED":
            raw = await c.execute(
                text(
                    "SELECT platform.messaging_ingest('CONTROLLED','bot-a',CAST(:event AS jsonb),:corr)"
                ),
                {
                    "event": json.dumps(event(event_id="held", message_id="held").values()),
                    "corr": uuid4(),
                },
            )
        else:
            raw = await c.execute(
                text("SELECT platform.telegram_ingest(:bot,CAST(:event AS jsonb),:corr)"),
                {
                    "bot": BOT,
                    "event": json.dumps(projection(update="10102", message="20102")),
                    "corr": uuid4(),
                },
            )
        held = raw.scalar_one()
        blocker = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        task = asyncio.create_task(execute(h, cid, "RESUME", "after-ingress", before))
        try:
            await wait_blocked(h, blocker)
            assert not task.done()
            await (tx.commit() if commit_ingress else tx.rollback())
            await task
        finally:
            if tx.is_active:
                await tx.rollback()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    current = await state(h, cid)
    rows = await query(
        h, "SELECT * FROM platform.inbox_events WHERE id=:id", id=UUID(held["inbox_id"])
    )
    assert len(rows) == int(commit_ingress)
    if rows:
        assert rows[0]["turn_control_mode"] == "HUMAN" and rows[0]["turn_control_generation"] == 1
        assert rows[0]["turn_ingress_seq"] < current["activation_fence_seq"]
    later = await incoming(h, provider, 103, process=False)
    later_id = UUID(later["inbox_id"]) if isinstance(later, dict) else later.inbox_id
    row = (await query(h, "SELECT * FROM platform.inbox_events WHERE id=:id", id=later_id))[0]
    assert (
        row["turn_control_generation"],
        row["turn_control_mode"],
        row["turn_activation_fence_seq"],
    ) == (2, "AI", current["activation_fence_seq"])
    assert row["turn_ingress_seq"] > current["activation_fence_seq"]


@pytest.mark.parametrize("provider", ["CONTROLLED", "TELEGRAM"])
async def test_unknown_conversation_and_grouping_use_earliest_capture(control, provider):
    h = control
    first = await incoming(h, provider, 1, process=False)
    second = await incoming(h, provider, 2, process=False)
    assert not await query(h, "SELECT id FROM app.conversations")
    with pytest.raises(ControlError, match="NOT_FOUND"):
        await execute(
            h,
            uuid4(),
            "RESUME",
            expected=ControlCommandRequest(
                expected_client_id=str(uuid4()),
                expected_control_generation="1",
                expected_context_version="1",
            ),
        )
    result = await process_receipt(h, first)
    cid = (
        await query(
            h, "SELECT conversation_id FROM app.messages WHERE id=:id", id=result.message_id
        )
    )[0]["conversation_id"]
    await execute(h, cid, "RESUME")
    # Accepted before Conversation creation stays HUMAN even after Resume.
    await process_receipt(h, second)
    old = (await query(h, "SELECT * FROM app.conversation_turns"))[0]
    assert old["control_generation"] == 1 and old["ingress_control_mode"] == "HUMAN"
    await incoming(h, provider, 3)
    groups = await query(h, "SELECT * FROM app.conversation_turns ORDER BY control_generation")
    assert len(groups) == 2 and groups[0]["state"] != "COLLECTING"
    new = groups[1]
    assert new["control_generation"] == 2 and new["ingress_control_mode"] == "AI"
    eligible = (
        await query(
            h,
            "SELECT platform.conversation_turn_activation_matches(:ws,:id) AS value",
            ws=A,
            id=new["id"],
        )
    )[0]["value"]
    assert eligible is True
    assert (
        await query(
            h,
            "SELECT platform.conversation_turn_activation_matches(:ws,:id) AS value",
            ws=A,
            id=old["id"],
        )
    )[0]["value"] is False
    await execute(h, cid, "TAKEOVER", "stop")
    assert (
        await query(
            h,
            "SELECT platform.conversation_turn_activation_matches(:ws,:id) AS value",
            ws=A,
            id=new["id"],
        )
    )[0]["value"] is False


@pytest.mark.parametrize("operation", ["TAKEOVER", "RESUME"])
async def test_test_consumer_stale_after_control_without_revision_mutation(control, operation):
    h = control
    cid, _, _ = await incoming(h)
    async with asyncio.timeout(5):
        while True:
            claim = await h.kernel.claim_job("control-consumer")
            if claim is None:
                due = (
                    await query(
                        h,
                        "SELECT min(available_at) AS due FROM platform.messaging_jobs WHERE status='READY'",
                    )
                )[0]["due"]
                await asyncio.sleep(max(0, (due - datetime.now(UTC)).total_seconds()))
                continue
            value = await h.kernel.process_turn(claim)
            if isinstance(value, TurnSnapshot):
                break
    await execute(h, cid, operation)
    before = await counts_control(h)
    result = await h.kernel.finish_turn(claim, consume(value))
    assert result.code == "STALE" and result.input_control_generation == 1
    replay = await h.kernel.replay_turn(claim.job_id, claim.claim_token)
    assert replay == result
    assert (await state(h, cid))["version"] == value.context_version
    assert len(await query(h, "SELECT id FROM platform.messaging_jobs")) == len(
        before["platform.messaging_jobs"]
    )
    assert not h.ledger.exists()
