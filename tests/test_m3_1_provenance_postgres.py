"""P-A03 actual PostgreSQL proofs; no SQLite, mocks, skips or live Telegram.

Ingress, claims, materialization and replay use runtime capabilities. Migrator is
used for bounded fixture setup, catalog assertions and deliberately invalid SQL.
"""

import asyncio
import copy
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from asm.conversations.guards import GUARD_TEXT
from asm.conversations.material import MessageCurrent, TargetResult
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.http_models import MessageResponse
from asm.messaging.models import OutcomeKind, SendOutcome
from asm.telegram.database import TelegramIngress
from asm.telegram.normalization import normalize_update_v2, update_fingerprint_v2
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import messaging as messaging
from test_m2_1_postgres import query
from test_m2_3_db_postgres import BOT, CLIENT, EXTERNAL, OWNER, owner_sql
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_postgres import control as control
from test_m3_1_control_postgres import wait_blocked
from test_m3_1_guards_postgres import accepted, prepared
from test_m3_1_turns_postgres import claim_exact, seal, snapshot
from test_tenancy_postgres import PROVIDER, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
SENT_AT = int(datetime.now(UTC).timestamp()) - 60


def raw(
    update=100001,
    message=501,
    *,
    kind="NEW",
    value="A",
    photo=None,
    date=20,
    chat=CLIENT,
    sender=CLIENT,
    ids=None,
):
    if kind == "DELETE":
        return {
            "update_id": update,
            "deleted_business_messages": {
                "business_connection_id": EXTERNAL,
                "chat": {"id": int(chat)},
                "message_ids": ids if ids is not None else [message],
            },
        }
    body = {
        "business_connection_id": EXTERNAL,
        "message_id": message,
        "date": SENT_AT,
        "chat": {"id": int(chat), "type": "private"},
        "from": {"id": int(sender), "is_bot": False},
    }
    if photo is None:
        body["text"] = value
    else:
        body["photo"] = [{"file_id": photo, "width": 20, "height": 10}]
        if value is not None:
            body["caption"] = value
    if kind == "EDIT" and date is not None:
        body["edit_date"] = SENT_AT + date
    return {
        "update_id": update,
        "business_message" if kind == "NEW" else "edited_business_message": body,
    }


@pytest_asyncio.fixture
async def material(control):
    h = control
    await query(
        h,
        "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE connection_id=:id RETURNING connection_id",
        id=h.telegram_connection,
    )
    yield h


async def ingest_raw(h, value):
    return await TelegramIngress(h.kernel, BOT).ingest_update(value, uuid4())


async def process(h, value):
    receipt = await ingest_raw(h, value)
    assert receipt.code == "ACCEPTED" and receipt.result_code == "QUEUED"
    claim = await claim_exact(h, receipt.job_id)
    result = await h.kernel.process_inbox(claim)
    return receipt, claim, result


async def current(h, message=501, chat=CLIENT):
    rows = await query(
        h,
        "SELECT m.*,platform.message_effective(m.workspace_id,m.id) AS current,c.version AS context_version FROM app.messages m JOIN app.conversations c ON (c.workspace_id,c.id)=(m.workspace_id,m.conversation_id) WHERE m.provider_message_id=:message AND m.provider_chat_id=:chat",
        message=str(message),
        chat=chat,
    )
    assert len(rows) == 1
    MessageCurrent.model_validate(rows[0]["current"])
    return rows[0]


async def traces(h):
    return (
        await query(
            h,
            "SELECT (SELECT count(*) FROM platform.message_material_effects) AS effects,(SELECT count(*) FROM app.audit_events WHERE event_type='MESSAGE_MATERIAL_CHANGED') AS audits,(SELECT count(*) FROM app.file_objects) AS files,(SELECT count(*) FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE') AS fetches",
        )
    )[0]


async def saved_results(h, receipt):
    row = (await query(h, "SELECT * FROM platform.inbox_events WHERE id=:id", id=receipt.inbox_id))[
        0
    ]
    assert (row["status"], row["result_code"], row["message_id"]) == (
        "PROCESSED",
        "MATERIAL_PROCESSED",
        None,
    )
    result = [TargetResult.model_validate(v) for v in row["material_result"]]
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=receipt.job_id))[
        0
    ]
    assert job["status"] == "SUCCEEDED" and job["error_code"] is None and job["last_claim_token"]
    return result


TRACES = [
    [(None, "A", 1), (10, "B", 0)],
    [(10, "B", 1), (None, "A", 1)],
    [(None, "B", 1), (10, "B", 0)],
    [(10, "B", 1), (None, "B", 1)],
    [(10, "B", 1), (20, "C", 1)],
    [(20, "C", 1), (10, "B", 0)],
    [(10, "B", 1), (20, "A", 1)],
    [(20, "A", 0), (10, "B", 0)],
    [(10, "B", 1), (10, "C", 1)],
    [(10, "C", 1), (10, "B", 1)],
    [(10, "B", 1), (10, "C", 1), (20, "A", 1)],
    [(10, "C", 1), (10, "B", 1), (20, "A", 1)],
    [(20, "A", 0), (10, "B", 0), (10, "C", 0)],
    [(20, "A", 0), (10, "C", 0), (10, "B", 0)],
    [(10, "B", 1), (10, "B", 0)],
    [(None, "A", 1), (None, "A", 0), (10, "B", 0)],
    [(10, "B", 1), ("X", None, 1), (20, "C", 0), ("X", None, 0)],
    [("X", None, 1), (10, "B", 0), (20, "C", 0), ("X", None, 0)],
]


@pytest.mark.parametrize("steps", TRACES)
async def test_known_order_per_commit_counters_and_sticky_turn(material, steps):
    h = material
    await process(h, raw())
    original = await current(h)
    turn = (await query(h, "SELECT * FROM app.conversation_turns"))[0]
    increments = 0
    for index, (date, value, delta) in enumerate(steps, 1):
        value_raw = raw(
            100001 + index, kind="DELETE" if date == "X" else "EDIT", date=date, value=value
        )
        before = await current(h)
        receipt, claim, _ = await process(h, value_raw)
        increments += delta
        after = await current(h)
        assert (
            after["text"] == "A"
            and after["projection_fingerprint"] == original["projection_fingerprint"]
        )
        assert after["version"] == before["version"] + delta == 1 + increments
        assert after["context_version"] == original["context_version"] + increments
        t = (await query(h, "SELECT * FROM app.conversation_turns WHERE id=:id", id=turn["id"]))[0]
        assert t["revision"] == turn["revision"] + increments
        assert t["material_invalidated"] == bool(increments)
        assert (
            t["member_count"],
            t["quiet_at"],
            t["hard_at"],
            t["control_generation"],
            t["activation_fence_seq"],
        ) == tuple(
            turn[k]
            for k in (
                "member_count",
                "quiet_at",
                "hard_at",
                "control_generation",
                "activation_fence_seq",
            )
        )
        assert await traces(h) == dict(effects=increments, audits=increments, files=0, fetches=0)
        saved = await saved_results(h, receipt)
        assert saved[0].code == "APPLIED" if delta else saved[0].code != "APPLIED"
        duplicate = await ingest_raw(h, value_raw)
        assert duplicate.code == "DUPLICATE" and duplicate.receipt_id == receipt.receipt_id
        assert (await h.kernel.process_inbox(claim)).code == "MATERIAL_PROCESSED"
        assert await current(h) == after and await saved_results(h, receipt) == saved
    target = (await query(h, "SELECT * FROM platform.message_material_targets"))[0]
    if any(x[0] == "X" for x in steps):
        assert target["deleted"] and target["max_edit_at"] is None and target["candidate"] is None
        assert after["current"]["state"] == "DELETED"
    elif any(x[0] is None for x in steps):
        assert target["undated_seen"] and after["current"]["state"] == "ORDER_UNCERTAIN"


@pytest.mark.parametrize("steps", TRACES)
async def test_deferred_order_fold_has_no_domain_writes_before_original(material, steps):
    h = material
    saved = []
    for index, (date, value, _) in enumerate(steps, 1):
        receipt, _, _ = await process(
            h, raw(100001 + index, kind="DELETE" if date == "X" else "EDIT", date=date, value=value)
        )
        result = await saved_results(h, receipt)
        assert result[0].code == "DEFERRED_TARGET"
        saved.append((receipt, result))
        for table in (
            "app.clients",
            "app.conversations",
            "app.messages",
            "app.conversation_turns",
            "app.file_objects",
        ):
            assert not await query(h, f"SELECT * FROM {table}")
        assert await traces(h) == dict(effects=0, audits=0, files=0, fetches=0)
    await process(h, raw())
    m = await current(h)
    changed = m["current"]["state"] != "VISIBLE" or m["current"]["text"] != "A"
    assert m["version"] == 1 + changed and m["context_version"] == 2 + changed
    assert await traces(h) == dict(effects=int(changed), audits=int(changed), files=0, fetches=0)
    ts = await query(h, "SELECT * FROM app.conversation_turns")
    if m["current"]["state"] == "VISIBLE":
        assert len(ts) == 1 and (
            ts[0]["revision"],
            ts[0]["member_count"],
            ts[0]["material_invalidated"],
        ) == (1, 1, False)
    else:
        assert not ts
    for receipt, result in saved:
        assert await saved_results(h, receipt) == result


async def test_mixed_delete_batch_sorted_unique_context_n_turn_once_and_late_original(material):
    h = material
    await process(h, raw())
    await process(h, raw(100002, 502, value="B"))
    before = await current(h)
    turn = (await query(h, "SELECT * FROM app.conversation_turns"))[0]
    receipt, claim, _ = await process(h, raw(100003, kind="DELETE", ids=[502, 501, 502, 503]))
    result = await saved_results(h, receipt)
    assert [r.ordinal for r in result] == [1, 2, 3]
    assert [r.code for r in result] == ["APPLIED", "APPLIED", "DEFERRED_TARGET"]
    assert (await current(h))["context_version"] == before["context_version"] + 2
    assert (
        await query(h, "SELECT revision FROM app.conversation_turns WHERE id=:id", id=turn["id"])
    )[0]["revision"] == turn["revision"] + 1
    await h.kernel.process_inbox(claim)
    await process(h, raw(100004, 503, value="C"))
    assert (await current(h, 503))["version"] == 2
    assert await saved_results(h, receipt) == result
    assert await traces(h) == dict(effects=3, audits=3, files=0, fetches=0)
    assert len(await query(h, "SELECT * FROM app.conversation_turn_messages")) == 2


@pytest.mark.parametrize("photo", [None, "G"], ids=["R3-T1-text", "R3-T2-photo"])
@pytest.mark.parametrize("existing", [False, True], ids=["fresh-turn", "existing-turn"])
async def test_initial_photo_suppression_visible_snapshot_and_duplicate(material, photo, existing):
    h = material
    before = None
    if existing:
        await process(h, raw(100010, 510, value="existing"))
        before = (await query(h, "SELECT * FROM app.conversation_turns"))[0]
    receipt, _, _ = await process(h, raw(100002, kind="EDIT", value="B", photo=photo))
    await process(h, raw(photo="F"))
    m = await current(h)
    assert (
        m["content_type"] == "IMAGE_REFERENCE" and m["image_file_id"] == "F" and m["version"] == 2
    )
    assert m["current"]["text"] == "B" and m["current"]["content_type"] == (
        "TEXT" if photo is None else "PHOTO"
    )
    assert m["current"]["image_availability"] == (
        "NOT_APPLICABLE" if photo is None else "MEDIA_REPLACED_UNAVAILABLE"
    )
    assert await traces(h) == dict(effects=1, audits=1, files=0, fetches=0)
    member = (
        await query(
            h, "SELECT * FROM app.conversation_turn_messages WHERE message_id=:id", id=m["id"]
        )
    )[0]
    proof = (await query(h, "SELECT * FROM platform.message_initial_suppressions"))[0]
    assert (
        member["file_id"] is None
        and member["content_type"] == "IMAGE_REFERENCE"
        and member["membership_form"] == "INITIAL_FOLD_SUPPRESSED"
    )
    assert (
        member["initial_suppression_id"] == proof["id"]
        and proof["membership_disposition"] == "ELIGIBLE_VISIBLE"
    )
    t = (await query(h, "SELECT * FROM app.conversation_turns WHERE id=:id", id=member["turn_id"]))[
        0
    ]
    assert (t["revision"], t["member_count"], t["material_invalidated"]) == (
        (before["revision"] + 1, before["member_count"] + 1, False) if existing else (1, 1, False)
    )
    initial_context = m["context_version"]
    duplicate, _, _ = await process(h, raw(100003, photo="F"))
    assert (await current(h))["context_version"] == initial_context
    assert (await query(h, "SELECT revision FROM app.conversation_turns WHERE id=:id", id=t["id"]))[
        0
    ]["revision"] == t["revision"]
    assert (await saved_results(h, receipt))[0].code == "DEFERRED_TARGET"
    assert duplicate.inbox_id != receipt.inbox_id
    await seal(h, t["id"])
    _, snap = await snapshot(h, t["id"])
    assert snap.schema_version == 2 and snap.readiness == (
        "COMPLETE" if photo is None else "PARTIAL"
    )
    selected = [x for x in snap.members if x.message_id == m["id"]][0]
    assert (
        selected.current.text == "B"
        and selected.membership_form == "INITIAL_FOLD_SUPPRESSED"
        and selected.file is None
    )
    assert await traces(h) == dict(effects=1, audits=1, files=0, fetches=0)


async def test_r3_t3_hidden_restore_and_t5_no_late_group_or_fetch(material):
    h = material
    await process(h, raw(100002, kind="EDIT", photo="G", date=10))
    await process(h, raw(100003, kind="EDIT", photo="H", date=10))
    await process(h, raw(photo="F"))
    first = await current(h)
    proof = (await query(h, "SELECT * FROM platform.message_initial_suppressions"))[0]
    assert (
        first["version"] == 2
        and first["current"]["state"] == "ORDER_UNCERTAIN"
        and proof["membership_disposition"] == "HIDDEN"
    )
    await process(h, raw(100004, kind="EDIT", photo="F", date=20))
    restored = await current(h)
    assert restored["version"] == 3 and restored["context_version"] == first["context_version"] + 1
    assert restored["current"]["image_availability"] == "ORIGINAL_NOT_FETCHED"
    assert (await query(h, "SELECT * FROM platform.message_initial_suppressions"))[0] == proof
    await process(h, raw(100005, photo="F"))
    assert await current(h) == restored
    assert not await query(h, "SELECT * FROM app.conversation_turn_messages")
    assert not await query(h, "SELECT * FROM app.conversation_turns")
    assert await traces(h) == dict(effects=2, audits=2, files=0, fetches=0)


async def test_identity_conflict_does_not_poison_trusted_original_and_chat_isolation(material):
    h = material
    await process(h, raw(100002, kind="EDIT", sender=OWNER, value="untrusted"))
    await process(h, raw())
    assert (await current(h))["current"]["text"] == "A"
    t = (await query(h, "SELECT * FROM platform.message_material_targets"))[0]
    assert t["quarantined"] and t["message_id"] is None
    other = str(int(CLIENT) + 1)
    await process(h, raw(100003, chat=other, sender=other, value="other"))
    receipt, _, _ = await process(h, raw(100004, kind="DELETE", chat=other))
    assert (await saved_results(h, receipt))[0].code == "APPLIED"
    assert (await current(h))["version"] == 1 and (await current(h, chat=other))["version"] == 2


async def test_full_codec_sql_python_parity_closed_null_matrix_and_immutable_sidecar(material):
    h = material
    values = [
        raw(),
        raw(100002, kind="EDIT", photo="F"),
        raw(100003, kind="DELETE", ids=[502, 501, 502]),
        {"update_id": 100004, "unknown": {}},
        {
            "update_id": 100005,
            "business_connection": {
                "id": EXTERNAL,
                "user": {"id": int(OWNER)},
                "user_chat_id": int(OWNER),
                "date": SENT_AT,
                "is_enabled": True,
                "rights": {"can_reply": True},
            },
        },
    ]
    for v in values:
        p = normalize_update_v2(BOT, v)
        rec = await ingest_raw(h, v)
        row = (
            await query(
                h,
                "SELECT encode(r.fingerprint,'hex') AS hash,s.projection FROM platform.telegram_update_receipts r JOIN platform.telegram_provenance s ON s.receipt_id=r.id WHERE r.id=:id",
                id=rec.receipt_id,
            )
        )[0]
        assert row["hash"] == update_fingerprint_v2(p) and row["projection"] == p.model_dump()
    base = normalize_update_v2(BOT, raw(100006, kind="EDIT")).model_dump()
    for key, value in (
        ("chat_id", None),
        ("sent_at", None),
        ("bot", "1"),
        ("content", {}),
        ("origin", None),
        ("unexpected", True),
    ):
        bad = copy.deepcopy(base)
        bad[key] = value
        with pytest.raises(MessagingError, match="INVALID_INPUT"):
            await TelegramIngress(h.kernel, BOT).ingest(bad, uuid4())
    with pytest.raises(DBAPIError):
        async with h.migrator.begin() as c:
            await c.execute(text("UPDATE platform.telegram_provenance SET material_enabled=false"))
    assert not await query(
        h, "SELECT * FROM platform.telegram_update_receipts WHERE update_id='100006'"
    )


@pytest.mark.parametrize(
    "table",
    [
        "platform.telegram_provenance",
        "platform.message_material_targets",
        "platform.message_material_effects",
        "platform.message_initial_suppressions",
    ],
)
async def test_runtime_nonowner_force_rls_and_no_raw_table_or_private_function_access(
    material, table
):
    h = material
    await process(h, raw(100002, kind="DELETE"))
    async with h.runtime.engine.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
                )
            )
        ).one()
        assert row == ("asm_runtime", False, False)
    for statement in (
        f"SELECT * FROM {table}",
        f"DELETE FROM {table}",
        "SELECT platform.material_apply_context(:ws,:id,:corr)",
    ):
        with pytest.raises(DBAPIError):
            async with h.runtime.engine.begin() as c:
                await c.execute(text(statement), dict(ws=A, id=uuid4(), corr=uuid4()))
    row = (
        await query(
            h,
            "SELECT relrowsecurity,relforcerowsecurity,relowner::regrole::text AS owner FROM pg_class WHERE oid=CAST(:t AS regclass)",
            t=table,
        )
    )[0]
    assert row == dict(relrowsecurity=True, relforcerowsecurity=True, owner="asm_migrator")


@pytest.mark.parametrize("phase", ["process_before_commit", "process_after_commit"])
async def test_rollback_and_lost_ack_restart_exact_terminal_replay(material, phase):
    h = material
    await process(h, raw())
    before = await current(h)
    rec = await ingest_raw(h, raw(100002, kind="EDIT", value="B"))
    claim = await claim_exact(h, rec.job_id)

    from test_m3_1_turns_postgres import child_process

    await child_process(h, claim, phase)
    if phase == "process_before_commit":
        assert await current(h) == before and (await traces(h))["effects"] == 0
    restarted = MessagingDatabase(h.runtime.engine)
    assert (await restarted.process_inbox(claim)).code == "MATERIAL_PROCESSED"
    assert (await restarted.process_inbox(claim)).code == "MATERIAL_PROCESSED"
    assert (await current(h))["version"] == 2 and (await traces(h))["effects"] == 1
    with pytest.raises(MessagingError):
        await restarted.process_inbox(claim.model_copy(update={"claim_token": uuid4()}))


@pytest.mark.parametrize("barrier", ["connection", "conversation"])
async def test_real_barrier_recheck_and_postwait_claim_expiry(material, barrier):
    h = material
    await process(h, raw())
    before = await current(h)
    rec = await ingest_raw(h, raw(100002, kind="EDIT", value="B"))
    claim = await claim_exact(h, rec.job_id)
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()+interval '500 milliseconds' WHERE id=:id"
            ),
            {"id": claim.job_id},
        )
    async with h.migrator.begin() as blocker:
        pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        if barrier == "connection":
            await blocker.execute(
                text("SELECT id FROM app.channel_connections WHERE id=:id FOR UPDATE"),
                {"id": h.telegram_connection},
            )
        else:
            await blocker.execute(
                text("SELECT id FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"),
                {"id": before["conversation_id"]},
            )
        pending = asyncio.create_task(h.kernel.process_inbox(claim))
        await wait_blocked(blocker, pid, pending=pending)
        await asyncio.sleep(0.6)
    with pytest.raises(MessagingError) as caught:
        await pending
    assert caught.value.code == Code.STALE_CLAIM
    assert await current(h) == before and (await traces(h))["effects"] == 0


async def test_original_and_material_workers_serialize_unknown_chat_without_deadlock(material):
    h = material
    edit = await ingest_raw(h, raw(100002, kind="EDIT", value="B"))
    original = await ingest_raw(h, raw())
    ce = await claim_exact(h, edit.job_id)
    co = await claim_exact(h, original.job_id)
    async with h.migrator.begin() as blocker:
        pid = (await blocker.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await blocker.execute(
            text("SELECT id FROM app.channel_connections WHERE id=:id FOR UPDATE"),
            {"id": h.telegram_connection},
        )
        e = asyncio.create_task(h.kernel.process_inbox(ce))
        await wait_blocked(blocker, pid, pending=e)
        o = asyncio.create_task(h.kernel.process_inbox(co))
        await wait_blocked(blocker, pid, pending=o)
    async with asyncio.timeout(5):
        await asyncio.gather(e, o)
    m = await current(h)
    assert m["version"] == 2 and m["current"]["text"] == "B"
    assert (await traces(h))["effects"] == 1


async def test_api_current_closed_history_and_same_workspace_wrong_client(material):
    h = material
    await process(h, raw(photo="F"))
    await process(h, raw(100002, kind="EDIT", value="B", photo="F"))
    m = await current(h)
    values = await owner_sql(
        h, "SELECT platform.messaging_read_messages(:id,25,NULL,NULL)", id=m["conversation_id"]
    )
    dto = MessageResponse.model_validate(values[0])
    assert dto.text == "A" and dto.current.text == "B" and dto.current.changed
    for actor, ws in ((UB, B), (PROVIDER, A)):
        with pytest.raises(DBAPIError):
            await owner_sql(
                h,
                "SELECT platform.messaging_read_messages(:id,25,NULL,NULL)",
                id=m["conversation_id"],
                actor=actor,
                workspace=ws,
            )
    other = str(int(CLIENT) + 1)
    await process(h, raw(100003, chat=other, sender=other))
    wrong = await current(h, chat=other)
    from asm.files.database import FileDatabase
    from test_m2_2_db_postgres import MANIFEST

    file = (await query(h, "SELECT * FROM app.file_objects WHERE message_id=:id", id=m["id"]))[0]
    fetch_id = (
        await query(h, "SELECT id FROM platform.messaging_jobs WHERE file_id=:id", id=file["id"])
    )[0]["id"]
    fetch = await claim_exact(h, fetch_id)
    files = FileDatabase(h.kernel)
    upload = await files.prepare_upload(fetch, MANIFEST)
    await files.finish_fetch(fetch.job_id, fetch.claim_token, upload.intent_id)
    assert await owner_sql(
        h,
        "SELECT platform.files_read_manifest(:c,:m,:f)",
        c=m["conversation_id"],
        m=m["id"],
        f=file["id"],
    )
    with pytest.raises(DBAPIError):
        await owner_sql(
            h,
            "SELECT platform.files_read_manifest(:c,:m,:f)",
            c=wrong["conversation_id"],
            m=m["id"],
            f=file["id"],
        )


@asynccontextmanager
async def shared_controlled_apply(h, message):
    """Finite TEST wrapper around the SAME context/invalidation body.

    This proves CONTROLLED guarded admission; provider/route/Client are never
    changed and it is explicitly not automated Telegram delivery evidence.
    """
    async with h.migrator.begin() as c:
        assert (await c.execute(text("SELECT current_user,current_database()"))).one() == (
            "asm_migrator",
            "asm_test",
        )
        await c.execute(
            text(
                """CREATE FUNCTION platform.test_material_controlled_delta() RETURNS void
          LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
          DECLARE m app.messages%ROWTYPE;
          BEGIN
            IF current_database()<>'asm_test' THEN RAISE EXCEPTION 'TEST only'; END IF;
            SELECT * INTO STRICT m FROM app.messages WHERE workspace_id='"""
                + str(A)
                + "' AND id='"
                + str(message)
                + """';
            PERFORM 1 FROM app.channel_connections WHERE workspace_id=m.workspace_id AND id=m.connection_id AND provider='CONTROLLED' FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'finite CONTROLLED delta only'; END IF;
            PERFORM 1 FROM app.conversations WHERE workspace_id=m.workspace_id AND id=m.conversation_id FOR NO KEY UPDATE;
            PERFORM 1 FROM app.messages WHERE workspace_id=m.workspace_id AND id=m.id FOR NO KEY UPDATE;
            PERFORM platform.material_apply_context(m.workspace_id,m.id,'00000000-0000-0000-0000-000000000012');
          END $$"""
            )
        )
        await c.execute(
            text(
                "REVOKE ALL ON FUNCTION platform.test_material_controlled_delta() FROM PUBLIC,asm_runtime"
            )
        )
    try:

        async def apply():
            async with h.migrator.begin() as c:
                await c.execute(text("SELECT platform.test_material_controlled_delta()"))

        yield apply
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text("DROP FUNCTION platform.test_material_controlled_delta()"))


@pytest.mark.parametrize("stage", ["before-accept", "before-begin", "after-dispatch"])
async def test_shared_body_guards_stale_admission_and_retained_dispatch(control, stage):
    h = control
    if stage == "before-accept":
        _, claim, snap = await prepared(h)
    else:
        _, claim, snap, receipt, send = await accepted(h)
    message = snap.members[-1].message_id
    if stage == "after-dispatch":
        permit = await h.kernel.begin_guarded_send(send)
    async with shared_controlled_apply(h, message) as apply:
        await apply()
    if stage == "before-accept":
        result = await h.kernel.accept_guarded_text(claim, snap.snapshot_digest, GUARD_TEXT)
        assert result.code in {"STALE", "SUPERSEDED"}
        assert not await query(h, "SELECT * FROM app.outbox_events")
    elif stage == "before-begin":
        result = await h.kernel.begin_guarded_send(send)
        assert result.code == "NOT_ALLOWED"
        assert not h.adapter.calls
    else:
        outcome = SendOutcome(OutcomeKind.SUCCESS, "retained-controlled-id", None)
        await h.kernel.finish_send(send.job_id, send.claim_token, permit.attempt_id, outcome)
        row = (
            await query(h, "SELECT * FROM app.outbox_events WHERE id=:id", id=receipt.outbox_id)
        )[0]
        assert row["status"] == "SENT"


@pytest.mark.parametrize(
    "corruption",
    [
        "null-form",
        "missing-proof",
        "text-member",
        "wrong-tenant",
        "wrong-message",
        "wrong-origin",
        "wrong-effect",
        "forged-basis",
        "pending-file",
        "failed-file",
    ],
)
async def test_r3_t4_invalid_first_suppression_rolls_back_entire_original_atom(
    material, corruption
):
    h = material
    await process(h, raw(100002, kind="EDIT", value="B"))
    rec = await ingest_raw(h, raw(photo="F"))
    claim = await claim_exact(h, rec.job_id)
    table = (
        "app.conversation_turn_messages"
        if corruption in {"null-form", "missing-proof", "text-member"}
        else "platform.message_initial_suppressions"
    )
    body = {
        "null-form": "NEW.membership_form:=NULL;NEW.initial_suppression_id:=NULL;",
        "missing-proof": "NEW.initial_suppression_id:='00000000-0000-0000-0000-000000009990';",
        "text-member": "NEW.content_type:='TEXT';",
        "wrong-tenant": f"NEW.workspace_id:='{B}';",
        "wrong-message": "NEW.message_id:='00000000-0000-0000-0000-000000009991';",
        "wrong-origin": "NEW.origin_inbox_id:='00000000-0000-0000-0000-000000009992';",
        "wrong-effect": "NEW.effect_id:='00000000-0000-0000-0000-000000009993';",
        "forged-basis": 'NEW.initial_material:=\'{"state":"DELETED","content":null}\'::jsonb;',
        "pending-file": "PERFORM platform.files_plan(NEW.workspace_id,NEW.message_id,'00000000-0000-0000-0000-000000009994');",
        "failed-file": "PERFORM platform.files_plan(NEW.workspace_id,NEW.message_id,'00000000-0000-0000-0000-000000009994'); UPDATE app.file_objects SET status='FAILED',error_code='INVALID_INPUT',completed_at=clock_timestamp(),version=version+1 WHERE workspace_id=NEW.workspace_id AND message_id=NEW.message_id;",
    }[corruption]
    async with h.migrator.begin() as c:
        assert (await c.execute(text("SELECT current_database()"))).scalar_one() == "asm_test"
        await c.execute(
            text(
                "CREATE FUNCTION platform.test_material_corrupt() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$ BEGIN "
                + body
                + " RETURN NEW; END $$"
            )
        )
        await c.execute(
            text("REVOKE ALL ON FUNCTION platform.test_material_corrupt() FROM PUBLIC,asm_runtime")
        )
        await c.execute(
            text(
                f"CREATE TRIGGER aaa_test_material_corrupt BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION platform.test_material_corrupt()"
            )
        )
    try:
        from test_m3_1_provenance_migrations import fingerprints

        async with h.migrator.connect() as c:
            before = await fingerprints(c)
        with pytest.raises((DBAPIError, MessagingError)):
            await h.kernel.process_inbox(claim)
        async with h.migrator.connect() as c:
            assert await fingerprints(c) == before
        assert not await query(h, "SELECT * FROM app.messages")
        assert await traces(h) == dict(effects=0, audits=0, files=0, fetches=0)
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text(f"DROP TRIGGER aaa_test_material_corrupt ON {table}"))
            await c.execute(text("DROP FUNCTION platform.test_material_corrupt()"))


async def test_cross_binding_fk_null_bypasses_and_historical_effect_versions(material):
    h = material
    await process(h, raw())
    await process(h, raw(100002, kind="EDIT", value="B"))
    old = (await query(h, "SELECT * FROM platform.message_material_effects"))[0]
    await process(h, raw(100003, kind="EDIT", value="C", date=30))
    assert (
        await query(h, "SELECT * FROM platform.message_material_effects WHERE id=:id", id=old["id"])
    )[0] == old
    t = (await query(h, "SELECT * FROM platform.message_material_targets"))[0]
    invalid = [
        "UPDATE platform.message_material_targets SET client_id=NULL",
        "UPDATE platform.message_material_targets SET direction=NULL",
        "UPDATE platform.message_material_targets SET inbound_provider_id=NULL",
        "UPDATE platform.message_material_targets SET message_id=NULL",
        "UPDATE platform.message_material_targets SET provider_chat_id='7000999'",
        "UPDATE platform.message_material_targets SET workspace_id=:other",
        "UPDATE platform.telegram_update_receipts SET codec=NULL WHERE codec=2",
        "UPDATE platform.message_material_effects SET accepted_version=accepted_version+1",
        "UPDATE platform.inbox_events SET material_result='[]'::jsonb WHERE result_code='MATERIAL_PROCESSED'",
    ]
    for statement in invalid:
        with pytest.raises(DBAPIError):
            async with h.migrator.begin() as c:
                await c.execute(text(statement), {"other": B})
                await c.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert (await query(h, "SELECT * FROM platform.message_material_targets"))[0] == t
    assert (await current(h))["version"] == 3


@pytest.mark.parametrize("counter", ["message", "context", "turn"])
async def test_overflow_is_full_rollback_without_effect_or_audit(material, counter):
    h = material
    await process(h, raw())
    table, column = {
        "message": ("app.messages", "version"),
        "context": ("app.conversations", "version"),
        "turn": ("app.conversation_turns", "revision"),
    }[counter]
    await query(h, f"UPDATE {table} SET {column}=9223372036854775807 RETURNING id")
    rec = await ingest_raw(h, raw(100002, kind="EDIT", value="B"))
    claim = await claim_exact(h, rec.job_id)
    from test_m3_1_provenance_migrations import fingerprints

    async with h.migrator.connect() as c:
        before = await fingerprints(c)
    with pytest.raises(DBAPIError) as caught:
        await h.kernel.process_inbox(claim)
    assert caught.value.orig.sqlstate == "22003"
    async with h.migrator.connect() as c:
        assert await fingerprints(c) == before


@pytest.mark.parametrize("mutation", ["caption", "replacement", "text", "delete"])
async def test_late_original_fetch_retains_winner_and_context_but_never_stale_image(
    material, mutation
):
    from asm.files.database import FileDatabase
    from test_m2_2_db_postgres import MANIFEST

    h = material
    await process(h, raw(photo="F"))
    m = await current(h)
    file = (await query(h, "SELECT * FROM app.file_objects"))[0]
    fid = (await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'"))[0][
        "id"
    ]
    fetch = await claim_exact(h, fid)
    files = FileDatabase(h.kernel)
    permit = await files.prepare_upload(fetch, MANIFEST)
    change = raw(
        100002,
        kind="DELETE" if mutation == "delete" else "EDIT",
        value="B",
        photo="F" if mutation == "caption" else "G" if mutation == "replacement" else None,
    )
    await process(h, change)
    before = await current(h)
    turn = (await query(h, "SELECT * FROM app.conversation_turns"))[0]
    await files.finish_fetch(fetch.job_id, fetch.claim_token, permit.intent_id)
    after = await current(h)
    t = (await query(h, "SELECT * FROM app.conversation_turns"))[0]
    assert (
        after["version"] == before["version"]
        and after["context_version"] == before["context_version"] + 1
    )
    assert (
        t["revision"] == turn["revision"] + int(mutation == "caption") and t["material_invalidated"]
    )
    winner = (
        await query(
            h, "SELECT * FROM platform.file_object_uploads WHERE id=:id", id=permit.intent_id
        )
    )[0]
    assert winner["status"] == "WINNER"
    if mutation == "caption":
        assert after["current"]["image_availability"] == "ORIGINAL_READY"
        manifest = await owner_sql(
            h,
            "SELECT platform.files_read_manifest(:c,:m,:f)",
            c=m["conversation_id"],
            m=m["id"],
            f=file["id"],
        )
        assert manifest["file_id"] == str(file["id"])
    else:
        with pytest.raises(DBAPIError):
            await owner_sql(
                h,
                "SELECT platform.files_read_manifest(:c,:m,:f)",
                c=m["conversation_id"],
                m=m["id"],
                f=file["id"],
            )
    before_traces = await traces(h)
    await process(h, raw(100003, photo="F"))
    assert await traces(h) == before_traces
    assert len(await query(h, "SELECT * FROM app.file_objects")) == 1


@pytest.mark.parametrize("outcome", ["SENT", "UNKNOWN"])
async def test_exact_sent_binding_only_and_deferred_finalizer_without_connection_reverse(
    material, outcome
):
    from test_m2_3_db_postgres import begin_observed, probe_worker, request

    h = material
    await process(h, raw())
    cid = (await current(h))["conversation_id"]
    intent = await request(h, cid, value="reply")
    send_id = (
        await query(
            h,
            "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id",
            id=UUID(intent["outbox_id"]),
        )
    )[0]["id"]
    send = await claim_exact(h, send_id)
    permit = await begin_observed(h, send, await probe_worker(h, send))
    # No invented mapping from local intent timestamp or echo body.
    mutation, _, _ = await process(
        h, raw(100002, 901, kind="EDIT", sender=OWNER, value="changed reply")
    )
    assert (await saved_results(h, mutation))[0].code == "DEFERRED_TARGET"
    t = (
        await query(
            h, "SELECT * FROM platform.message_material_targets WHERE provider_message_id='901'"
        )
    )[0]
    assert t["message_id"] is None
    result = (
        SendOutcome(OutcomeKind.SUCCESS, "901")
        if outcome == "SENT"
        else SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT)
    )
    # A connection lock held by another transaction must not block SENT's
    # C -> existing target binding (including its implicit FK checks).
    async with h.migrator.begin() as blocker:
        await blocker.execute(
            text("SELECT id FROM app.channel_connections WHERE id=:id FOR UPDATE"),
            {"id": h.telegram_connection},
        )
        async with asyncio.timeout(3):
            await h.kernel.finish_send(
                send.job_id, send.claim_token, UUID(permit["attempt_id"]), result
            )
    target = (
        await query(h, "SELECT * FROM platform.message_material_targets WHERE id=:id", id=t["id"])
    )[0]
    assert (target["message_id"] is not None) == (outcome == "SENT")
    assert (await traces(h))["effects"] == int(outcome == "SENT")
    assert (await saved_results(h, mutation))[0].code == "DEFERRED_TARGET"


async def test_material_reclaim_nowait_skips_locked_candidate_and_old_token_cannot_apply(material):
    h = material
    await process(h, raw())
    rec = await ingest_raw(h, raw(100002, kind="EDIT", value="B"))
    claim = await claim_exact(h, rec.job_id)
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    async with h.migrator.begin() as c:
        await c.execute(
            text("SELECT id FROM platform.messaging_jobs WHERE id=:id FOR UPDATE"),
            {"id": claim.job_id},
        )
        async with asyncio.timeout(1):
            assert await h.kernel.recover_expired() == 0
    assert await h.kernel.recover_expired() == 1
    with pytest.raises(MessagingError):
        await h.kernel.process_inbox(claim)
    fresh = await claim_exact(h, claim.job_id)
    assert fresh.claim_token != claim.claim_token
    await h.kernel.process_inbox(fresh)
    assert (await current(h))["version"] == 2 and (await traces(h))["effects"] == 1


@pytest.mark.parametrize("prior", ["PENDING", "CANCELLED", "RESOLVED"])
async def test_shared_body_escalation_context_cancel_once_terminal_precedence_and_saved_replay(
    control, prior
):
    from asm.conversations.escalations import EscalationError
    from test_m3_2_escalations_postgres import created, decide

    h = control
    e, _, _ = await created(h)
    receipt = None
    if prior != "PENDING":
        receipt = await decide(h, e, "CANCEL" if prior == "CANCELLED" else "RESOLVE", key="winning")
    message = (
        await query(
            h,
            "SELECT message_id FROM app.conversation_turn_messages WHERE turn_id=:id ORDER BY turn_ingress_seq DESC LIMIT 1",
            id=e["turn_id"],
        )
    )[0]["message_id"]
    before = (
        await query(
            h, "SELECT version FROM app.conversations WHERE id=:id", id=e["conversation_id"]
        )
    )[0]["version"]
    async with shared_controlled_apply(h, message) as apply:
        await apply()
    after = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=e["id"]))[0]
    assert after["status"] == ("CANCELLED" if prior == "PENDING" else prior)
    assert after["version"] == 2
    if prior == "PENDING":
        assert after["closure_reason"] == "CONTEXT_CHANGED"
    assert (
        await query(
            h, "SELECT version FROM app.conversations WHERE id=:id", id=e["conversation_id"]
        )
    )[0]["version"] == before + 1
    with pytest.raises(EscalationError) as caught:
        await decide(h, e, key="new-after-material")
    assert caught.value.code.value == "ESCALATION_FINAL"
    if receipt is not None:
        replay = await decide(h, e, "CANCEL" if prior == "CANCELLED" else "RESOLVE", key="winning")
        assert replay["result"] == receipt["result"] and replay["code"] == "REPLAY"


async def test_shared_body_retains_expired_escalation_precedence(control):
    from asm.conversations.escalations import EscalationError
    from test_m3_2_escalations_postgres import created, decide, serial_clock

    h = control
    async with serial_clock(h) as (_, set_clock):
        e, _, _ = await created(h)
        await set_clock(e["expires_at"])
        assert await h.kernel.claim_job("material-expired-maintenance") is None
        m = (
            await query(
                h,
                "SELECT message_id FROM app.conversation_turn_messages WHERE turn_id=:id LIMIT 1",
                id=e["turn_id"],
            )
        )[0]["message_id"]
        async with shared_controlled_apply(h, m) as apply:
            await apply()
        with pytest.raises(EscalationError) as caught:
            await decide(h, e, key="after-expired-material")
        assert caught.value.code.value == "ESCALATION_EXPIRED"
        assert (await query(h, "SELECT status FROM app.escalations WHERE id=:id", id=e["id"]))[0][
            "status"
        ] == "EXPIRED"


async def test_same_provider_id_across_workspace_and_connection_never_aliases(material):
    import json

    from test_tenancy_postgres import BA, BB

    h = material
    await process(h, raw())
    for ws, business, bot in ((A, BA, "9000002"), (B, BB, "9000003")):
        external = "material-other-" + bot
        observation = dict(
            bot_identity=bot,
            external_connection_id=external,
            owner_user_id=OWNER,
            is_enabled=True,
            can_reply=True,
            error_code=None,
        )
        async with h.migrator.begin() as c:
            binding = (
                await c.execute(
                    text(
                        "SELECT platform.initialize_telegram_connection(:ws,:business,:bot,:external,:owner,CAST(:observation AS jsonb))"
                    ),
                    dict(
                        ws=ws,
                        business=business,
                        bot=bot,
                        external=external,
                        owner=OWNER,
                        observation=json.dumps(observation),
                    ),
                )
            ).scalar_one()
            await c.execute(
                text(
                    "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE connection_id=:id"
                ),
                {"id": UUID(binding["connection_id"])},
            )
        value = raw()
        value["business_message"]["business_connection_id"] = external
        receipt = await TelegramIngress(h.kernel, bot).ingest_update(value, uuid4())
        await h.kernel.process_inbox(await claim_exact(h, receipt.job_id))
    before = await query(
        h, "SELECT id,workspace_id,connection_id,version FROM app.messages ORDER BY id"
    )
    assert len(before) == 3 and len({r["id"] for r in before}) == 3
    await process(h, raw(100002, kind="DELETE"))
    after = await query(
        h, "SELECT id,workspace_id,connection_id,version FROM app.messages ORDER BY id"
    )
    for old, new in zip(before, after, strict=True):
        assert new["version"] == old["version"] + int(old["connection_id"] == h.telegram_connection)
    assert (await traces(h))["effects"] == 1
