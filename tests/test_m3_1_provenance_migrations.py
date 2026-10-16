"""P-A03-08 actual 0011 -> 0012 lifecycle and complete catalog assertions.

P_COLUMNS is the closed source inventory. It becomes catalog evidence only when
these integration tests execute on disposable PostgreSQL.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from asm.telegram.database import TelegramIngress
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_m2_1_postgres import messaging as messaging
from test_m2_1_postgres import query
from test_m2_1_schema_postgres import _migrate
from test_m2_3_db_postgres import BOT, ingress, lifecycle, projection
from test_m2_3_db_postgres import telegram as telegram
from test_m3_1_control_migrations import definitions
from test_m3_1_control_postgres import control as control
from test_m3_1_provenance_postgres import material as material
from test_m3_1_provenance_postgres import process, raw
from test_m3_1_turns_postgres import claim_exact
from test_m3_2_escalations_migrations import E_COLUMNS
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
P_COLUMNS = {
    **E_COLUMNS,
    "platform.telegram_connection_state": E_COLUMNS["platform.telegram_connection_state"]
    + ("material_enabled",),
    "platform.telegram_update_receipts": E_COLUMNS["platform.telegram_update_receipts"]
    + ("codec",),
    "platform.inbox_events": E_COLUMNS["platform.inbox_events"]
    + ("material_result", "material_claim_token"),
    "app.conversation_turns": E_COLUMNS["app.conversation_turns"] + ("material_invalidated",),
    "app.conversation_turn_messages": E_COLUMNS["app.conversation_turn_messages"]
    + ("membership_form", "initial_suppression_id", "suppression_disposition"),
    "app.audit_events": E_COLUMNS["app.audit_events"]
    + ("material_target_id", "material_source_receipt_id"),
    "platform.telegram_provenance": tuple(
        "receipt_id codec bot_identity update_id workspace_id connection_id inbox_id projection material_enabled".split()
    ),
    "platform.message_material_targets": tuple(
        "workspace_id id connection_id provider_chat_id provider_message_id message_id conversation_id client_id direction outbox_id inbound_provider_id required_sent quarantined original_grouping_closed origin_identity deleted undated_seen max_edit_at candidate dated_conflict delete_receipt undated_receipt candidate_receipt conflict_receipt current_material".split()
    ),
    "platform.message_material_effects": tuple(
        "workspace_id id target_id message_id source_receipt_id audit_event_id event_type previous_version accepted_version reason accepted_at".split()
    ),
    "platform.message_initial_suppressions": tuple(
        "workspace_id id message_id target_id origin_inbox_id effect_id source_receipt_id previous_version accepted_version initial_material fold_witnesses membership_disposition".split()
    ),
}
assert len(P_COLUMNS) == 42


def migration():
    spec = importlib.util.spec_from_file_location(
        "material_0012", Path("migrations/versions/0012_message_provenance.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def assert_schema(c):
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == "0012"
    rows = (
        await c.execute(
            text(
                "SELECT n.nspname||'.'||r.relname,array_agg(a.attname ORDER BY a.attnum) FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r' GROUP BY 1"
            )
        )
    ).all()
    assert {table: tuple(columns) for table, columns in rows} == P_COLUMNS


async def fingerprints(c, *, legacy=False):
    result = {}
    for table, columns in (E_COLUMNS if legacy else P_COLUMNS).items():
        if table == "platform.alembic_version":
            continue
        selected = ",".join('"' + v + '"' for v in columns)
        rows = (
            await c.execute(text(f"SELECT to_jsonb(r) FROM (SELECT {selected} FROM {table}) r"))
        ).scalars()
        canonical = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = (len(canonical), hashlib.sha256("\n".join(canonical).encode()).hexdigest())
    return result


async def catalog(c):
    # Definition equality includes constraints, indexes and triggers, not just
    # a count or the mere existence of predecessor functions.
    extra = []
    for sql in (
        "SELECT n.nspname,r.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class r ON r.oid=k.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname IN ('app','platform') ORDER BY 1,2,3",
        "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname IN ('app','platform') ORDER BY 1,2,3",
        "SELECT n.nspname,r.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname IN ('app','platform') AND NOT t.tgisinternal ORDER BY 1,2,3",
    ):
        extra.append((await c.execute(text(sql))).all())
    return await definitions(c), extra


async def test_fresh_head_full42_columns_profiles_rls_and_no_unused_backfill(control):
    h = control
    m = migration()
    async with h.migrator.connect() as c:
        await assert_schema(c)
        assert (
            await c.execute(
                text(
                    "SELECT count(*) FROM platform.inbox_events WHERE material_result IS NOT NULL OR material_claim_token IS NOT NULL"
                )
            )
        ).scalar_one() == 0
        assert (
            await c.execute(
                text(
                    "SELECT data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='platform' AND table_name='inbox_events' AND column_name='material_claim_token'"
                )
            )
        ).one() == ("uuid", "YES", None)
        for table in m.TABLES:
            assert (await c.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
        for signature in (*m.PUBLIC_FUNCTIONS, *m.PRIVATE_FUNCTIONS):
            row = (
                await c.execute(
                    text(
                        "SELECT p.proowner::regrole::text,p.proconfig,has_function_privilege('asm_runtime',p.oid,'EXECUTE'),coalesce(bool_or(a.grantee=0 AND a.privilege_type='EXECUTE'),false) FROM pg_proc p LEFT JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a ON true WHERE p.oid=CAST(:sig AS regprocedure) GROUP BY p.oid"
                    ),
                    {"sig": signature},
                )
            ).one()
            assert row == (
                "asm_migrator",
                ["search_path=pg_catalog, pg_temp"],
                signature in m.PUBLIC_FUNCTIONS,
                False,
            )
        for table in m.TABLES:
            row = (
                await c.execute(
                    text(
                        "SELECT relowner::regrole::text,relrowsecurity,relforcerowsecurity,has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE') FROM pg_class WHERE oid=CAST(:t AS regclass)"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == ("asm_migrator", True, True, False)


async def test_populated_0011_repeat_upgrade_and_exact_unused_reverse(control):
    h = control
    try:
        await _migrate("downgrade", "0011")
        with pytest.raises(RuntimeError, match="schema"):
            await h.runtime.check()
        legacy_projection = projection()
        receipt = await ingress(h, legacy_projection)
        claim = await claim_exact(h, UUID(receipt["job_id"]))
        result = await h.kernel.process_inbox(claim)
        cid = (
            await query(
                h, "SELECT conversation_id FROM app.messages WHERE id=:id", id=result.message_id
            )
        )[0]["conversation_id"]
        await ingress(h, projection("102", "202"))  # pending original
        await ingress(h, lifecycle())  # immutable ignored/lifecycle
        from test_m2_3_db_postgres import request

        await request(h, cid, "old-pending", "legacy exact")
        from asm.conversations.turns import consume
        from asm.files.database import FileDatabase
        from asm.messaging.errors import Code
        from asm.messaging.models import OutcomeKind, SendOutcome
        from test_m2_2_db_postgres import MANIFEST
        from test_m2_3_db_postgres import begin_observed, probe_worker
        from test_m3_1_turns_postgres import seal, snapshot, turn_claim, wait_due

        unknown = await request(h, cid, "old-unknown", "retained UNKNOWN")
        job = (
            await query(
                h,
                "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id",
                id=UUID(unknown["outbox_id"]),
            )
        )[0]["id"]
        send = await claim_exact(h, job)
        permit = await begin_observed(h, send, await probe_worker(h, send))
        await h.kernel.finish_send(
            send.job_id,
            send.claim_token,
            UUID(permit["attempt_id"]),
            SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
        )
        image = projection("103", "203")
        image["event"]["image_file_id"] = "retained-F"
        pic = await ingress(h, image)
        await h.kernel.process_inbox(await claim_exact(h, UUID(pic["job_id"])))
        fetch_id = (
            await query(h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")
        )[0]["id"]
        fetch = await claim_exact(h, fetch_id)
        files = FileDatabase(h.kernel)
        upload = await files.prepare_upload(fetch, MANIFEST)
        await files.finish_fetch(fetch.job_id, fetch.claim_token, upload.intent_id)
        # Frozen V1 snapshot/digest/receipt and WINNER are in the old-column hash.
        for turn in await query(h, "SELECT id FROM app.conversation_turns"):

            async def current_stage():
                rows = await query(
                    h, "SELECT state FROM app.conversation_turns WHERE id=:id", id=turn["id"]
                )
                assert len(rows) == 1
                return rows[0]["state"]

            # File WINNER can already seal/bump this Turn. Claim only the job
            # for its actual stage and current revision; never recreate GROUP.
            if await current_stage() == "COLLECTING":
                await seal(h, turn["id"])
            if await current_stage() == "WAITING_MEDIA":
                await wait_due(h, turn["id"], "MEDIA")
                media = await turn_claim(h, turn["id"], "MEDIA")
                assert (await h.kernel.process_turn(media)).code == "GROUPED"
            assert await current_stage() == "READY"
            consumer, snap = await snapshot(h, turn["id"])
            assert not hasattr(snap, "schema_version")
            await h.kernel.finish_turn(consumer, consume(snap))
        async with h.migrator.connect() as c:
            before, ddl = await fingerprints(c, legacy=True), await catalog(c)
        for _ in range(2):
            await _migrate("upgrade", "0012")
            await _migrate("upgrade", "0012")
            await h.runtime.check()
            async with h.migrator.connect() as c:
                await assert_schema(c)
                assert await fingerprints(c, legacy=True) == before
                assert (
                    await c.execute(
                        text(
                            "SELECT count(*) FROM platform.inbox_events WHERE material_result IS NOT NULL OR material_claim_token IS NOT NULL"
                        )
                    )
                ).scalar_one() == 0
                for table in migration().TABLES:
                    assert (
                        await c.execute(text(f"SELECT count(*) FROM {table}"))
                    ).scalar_one() == 0
                assert (
                    await c.execute(
                        text(
                            "SELECT count(*) FROM platform.telegram_update_receipts WHERE codec IS NOT NULL"
                        )
                    )
                ).scalar_one() == 0
            with pytest.raises(DBAPIError) as invalid_legacy:
                async with h.migrator.begin() as c:
                    await c.execute(
                        text("""UPDATE platform.inbox_events SET status='PROCESSED',result_code='MATERIAL_PROCESSED',completed_at=clock_timestamp(),
                      material_claim_token=:token,material_result=jsonb_build_array(jsonb_build_object('ordinal',1,'code','IDENTITY_CONFLICT','target_id',NULL,'message_id',NULL,'effect_id',NULL,'audit_event_id',NULL,'previous_version',NULL,'accepted_version',NULL))
                      WHERE event_id='102'"""),
                        {"token": uuid4()},
                    )
                    await c.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            assert invalid_legacy.value.orig.sqlstate == "23514"
            assert invalid_legacy.value.orig.diag.message_primary == "V1 material completion"
            # Invalid V2-only marker never parses for an already saved V1 key.
            old = legacy_projection
            replay = await TelegramIngress(h.kernel, BOT).ingest(old, uuid4())
            assert replay.code == "DUPLICATE" and str(replay.receipt_id) == receipt["receipt_id"]
            await _migrate("downgrade", "0011")
            async with h.migrator.connect() as c:
                assert await fingerprints(c, legacy=True) == before and await catalog(c) == ddl
    finally:
        await _migrate("upgrade", "head")
        await h.runtime.engine.dispose()


@pytest.mark.parametrize("used", ["codec-off", "target", "effect", "suppression", "enabled-only"])
async def test_owned_used_refusal_precedes_every_ddl_and_preserves_all42(control, used):
    h = control
    if used != "codec-off":
        await query(
            h,
            "UPDATE platform.telegram_connection_state SET material_enabled=true RETURNING connection_id",
        )
    if used == "codec-off":
        await TelegramIngress(h.kernel, BOT).ingest_update(raw(), uuid4())
    elif used == "target":
        await process(h, raw(100002, kind="DELETE"))
    elif used == "effect":
        await process(h, raw())
        await process(h, raw(100002, kind="DELETE"))
    elif used == "suppression":
        await process(h, raw(100002, kind="EDIT", value="B"))
        await process(h, raw(photo="F"))
    async with h.migrator.begin() as c:
        before, ddl = await fingerprints(c), await catalog(c)
        with pytest.raises(DBAPIError) as caught:
            async with c.begin_nested():

                def down(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        migration().downgrade()

                await c.run_sync(down)
        assert caught.value.orig.sqlstate == "55000"
        await assert_schema(c)
        assert await fingerprints(c) == before and await catalog(c) == ddl


async def test_cutover_saved_v1_replay_precedes_new_field_parse_and_fresh_v1_refused(control):
    h = control
    from asm.telegram.normalization import normalize_update

    value = raw()
    try:
        await _migrate("downgrade", "0011")
        old = await ingress(h, normalize_update(BOT, value))
    finally:
        await _migrate("upgrade", "head")
    malformed = copy_json(value)
    malformed["business_message"]["is_from_offline"] = False
    instance = TelegramIngress(h.kernel, BOT)
    replay = await instance.ingest_update(malformed, uuid4())
    assert replay.code == "DUPLICATE" and str(replay.receipt_id) == old["receipt_id"]
    with pytest.raises(Exception, match="INVALID_INPUT"):
        await instance.ingest(normalize_update(BOT, raw(100002)), uuid4())
    fresh = await instance.ingest_update(raw(100003), uuid4())
    row = (
        await query(
            h,
            "SELECT codec FROM platform.telegram_update_receipts WHERE id=:id",
            id=fresh.receipt_id,
        )
    )[0]
    assert row["codec"] == 2


def copy_json(value):
    return json.loads(json.dumps(value))


async def test_legacy_ineligible_photo_first_original_stays_suppressed_after_restore(control):
    from asm.telegram.normalization import normalize_update
    from test_m3_1_provenance_postgres import current, saved_results, traces

    h = control
    original = raw(photo="F")
    try:
        await _migrate("downgrade", "0007")
        receipt = await ingress(h, normalize_update(BOT, original))
    finally:
        await _migrate("upgrade", "head")
    await query(
        h,
        "UPDATE platform.telegram_connection_state SET material_enabled=true RETURNING connection_id",
    )
    deferred, _, _ = await process(h, raw(100002, kind="EDIT", value="B"))
    await h.kernel.process_inbox(await claim_exact(h, UUID(receipt["job_id"])))
    evidence = (await query(h, "SELECT * FROM platform.message_initial_suppressions"))[0]
    assert evidence["membership_disposition"] == "INELIGIBLE_ORIGIN"
    assert (await current(h))["current"]["text"] == "B"
    await process(h, raw(100003, kind="EDIT", photo="F", date=30))
    await process(h, raw(100004, photo="F"))
    assert (await current(h))["current"]["image_availability"] == "ORIGINAL_NOT_FETCHED"
    assert not await query(h, "SELECT * FROM app.conversation_turn_messages")
    assert not await query(h, "SELECT * FROM app.conversation_turns")
    assert (await query(h, "SELECT * FROM platform.message_initial_suppressions"))[0] == evidence
    assert (await saved_results(h, deferred))[0].code == "DEFERRED_TARGET"
    assert await traces(h) == dict(effects=2, audits=2, files=0, fetches=0)
