"""DB-only 0013 proofs on an explicitly owned disposable PostgreSQL 18 cluster.

These tests reset asm_test through its bootstrap administrator. They are a
separate DB lane, never a compatibility bypass for foundation/API/worker startup.
The SQL caller uses the real asm_runtime login and trusted tenancy/claim factory;
policy uses the real asm_migrator login. No HTTP, provider, storage or adapter I/O.
"""

import asyncio
import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio
from asm.conversations.turns import consume
from asm.foundation import RuntimeDatabase, Settings
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code
from asm.messaging.models import OutcomeKind, SendOutcome
from asm.telegram.database import TelegramIngress
from asm.tenancy import AuthenticatedAccount, TenancyError, TenantDatabase
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from test_m2_1_models import event
from test_m2_1_postgres import CA, provision, query
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER, observed
from test_m3_1_native_context_migrations import migration, source_statements
from test_m3_1_provenance_postgres import raw
from test_m3_1_turns_postgres import seal
from test_tenancy_postgres import BA, BA2, BB, PROVIDER, UA, UB, A, B

pytestmark = pytest.mark.integration
ALLOWLIST = (
    "migrations/versions/0013_native_context.py",
    "tests/test_m3_1_native_context_migrations.py",
    "tests/test_m3_1_native_context_postgres.py",
    "tests/test_tenancy_postgres.py",
    "docs/tasks/M3_CONTRACT.md",
)


def source_tree_identity():
    """Actual test-source identity, explicitly not a C0 deployment approval."""
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        subprocess.run(["git", "read-tree", "HEAD"], env=env, check=True, capture_output=True)
        subprocess.run(["git", "add", "--", *ALLOWLIST], env=env, check=True, capture_output=True)
        return subprocess.check_output(["git", "write-tree"], env=env, text=True).strip()


def reset_disposable():
    assert os.environ["ASM_NATIVE_TEST_ALLOW_RESET"] == "1"
    url = make_url(os.environ["ASM_NATIVE_TEST_ADMIN_URL"])
    runtime = make_url(os.environ["ASM_DATABASE_URL"])
    migrator = make_url(os.environ["ASM_MIGRATION_DATABASE_URL"])
    assert url.host in ("127.0.0.1", "localhost") and url.database == "postgres"
    assert runtime.host == migrator.host == url.host and runtime.port == migrator.port == url.port
    assert runtime.database == migrator.database == "asm_test"
    assert runtime.username == "asm_runtime" and migrator.username == "asm_migrator"
    kwargs = dict(host=url.host, port=url.port, user=url.username, password=url.password)
    with psycopg.connect(**kwargs, dbname="postgres", autocommit=True) as c:
        assert c.execute("SHOW server_version_num").fetchone()[0].startswith("18")
        c.execute("DROP DATABASE IF EXISTS asm_test WITH (FORCE)")
        c.execute("CREATE DATABASE asm_test")
    with psycopg.connect(**kwargs, dbname="asm_test") as c:
        c.execute("REVOKE ALL ON DATABASE asm_test FROM PUBLIC")
        c.execute("GRANT CONNECT ON DATABASE asm_test TO asm_migrator,asm_runtime")
        c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        c.execute("CREATE SCHEMA platform AUTHORIZATION asm_migrator")
        c.execute("CREATE SCHEMA app AUTHORIZATION asm_migrator")
        c.execute("CREATE SCHEMA extensions")
        c.execute("CREATE EXTENSION vector WITH SCHEMA extensions VERSION '0.8.6'")
        c.execute("CREATE EXTENSION btree_gist WITH SCHEMA extensions VERSION '1.8'")
        c.execute("GRANT USAGE ON SCHEMA extensions TO asm_migrator,asm_runtime")
        c.execute(
            "ALTER ROLE asm_runtime IN DATABASE asm_test SET search_path=pg_catalog,app,extensions"
        )
        c.execute(
            "ALTER ROLE asm_migrator IN DATABASE asm_test SET search_path=pg_catalog,platform,app,extensions"
        )
        c.execute("ALTER ROLE asm_runtime IN DATABASE asm_test SET timezone='UTC'")
        c.execute("ALTER ROLE asm_runtime IN DATABASE asm_test SET statement_timeout='5s'")
        c.execute("ALTER ROLE asm_runtime IN DATABASE asm_test SET lock_timeout='2s'")
        c.execute(
            "ALTER ROLE asm_runtime IN DATABASE asm_test SET idle_in_transaction_session_timeout='10s'"
        )


async def migrate(direction, target):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        direction,
        target,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 0, (stdout.decode(), stderr.decode())


@pytest_asyncio.fixture
async def native(request, tmp_path):
    await asyncio.to_thread(reset_disposable)
    target = getattr(request, "param", "0013")
    await migrate("upgrade", target)
    runtime = create_async_engine(
        os.environ["ASM_DATABASE_URL"], pool_size=8, max_overflow=0, hide_parameters=True
    )
    migrator = create_async_engine(
        os.environ["ASM_MIGRATION_DATABASE_URL"], poolclass=NullPool, hide_parameters=True
    )
    h = SimpleNamespace(
        runtime=SimpleNamespace(engine=runtime, tenancy=TenantDatabase(runtime)),
        migrator=migrator,
        kernel=MessagingDatabase(runtime),
        adapter=ControlledAdapter(environment="TEST", ledger=tmp_path / "unused-ledger"),
        source_tree=source_tree_identity(),
    )
    try:
        async with migrator.begin() as c:
            for actor in (UA, UB, PROVIDER):
                await c.execute(
                    text("INSERT INTO platform.user_accounts(id) VALUES(:id)"), {"id": actor}
                )
            for ws, actor in ((A, UA), (B, UB)):
                await c.execute(text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": ws})
                await c.execute(
                    text(
                        "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
                    ),
                    {"ws": ws, "actor": actor},
                )
            await c.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'PROVIDER')"
                ),
                {"ws": A, "actor": PROVIDER},
            )
            for ws, business in ((A, BA), (A, BA2), (B, BB)):
                await c.execute(
                    text(
                        "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:id,'synthetic')"
                    ),
                    {"ws": ws, "id": business},
                )
            start = datetime.now(UTC) - timedelta(days=1)
            for ws in (A, B):
                assert (
                    await c.execute(
                        text(
                            "SELECT platform.initialize_local_messaging_billing(:ws,'Native DB TEST',:start,:end)"
                        ),
                        {"ws": ws, "start": start, "end": start + timedelta(days=30)},
                    )
                ).scalar_one() == "CREATED"
        await provision(migrator)
        async with migrator.begin() as c:
            h.telegram_connection = UUID(
                (
                    await c.execute(
                        text(
                            "SELECT platform.initialize_telegram_connection(:ws,:b,:bot,:external,:owner,CAST(:observation AS jsonb))"
                        ),
                        {
                            "ws": A,
                            "b": BA,
                            "bot": BOT,
                            "external": EXTERNAL,
                            "owner": OWNER,
                            "observation": json.dumps(observed()),
                        },
                    )
                ).scalar_one()["connection_id"]
            )
            if target >= "0012":
                # Retained trusted MATERIAL fixture primitive. Native policy is
                # enabled only through the new command below, never by UPDATE.
                await c.execute(
                    text(
                        "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE workspace_id=:ws AND connection_id=:id"
                    ),
                    {"ws": A, "id": h.telegram_connection},
                )
        yield h
    finally:
        await runtime.dispose()
        await migrator.dispose()
        # Keep all native evidence until the next explicit whole disposable DB
        # reset. In particular, no cleanup is used to make a used downgrade pass.


async def scalar(h, sql, **params):
    async with h.migrator.begin() as c:
        return (await c.execute(text(sql), params)).scalar_one()


async def owner(h, sql, *, actor=UA, workspace=A, **params):
    async with h.runtime.tenancy.transaction(
        AuthenticatedAccount(actor), workspace, uuid4()
    ) as unit:
        return (await unit._execute(sql, params)).scalar_one()


async def worker(h, claim, sql, **params):
    async with h.runtime.engine.begin() as c:
        if not any(
            name in sql
            for name in ("platform.guard_turn_accept(", "platform.turn_consumer_finalize(")
        ):
            await c.execute(
                text("SELECT platform.messaging_admit(:job,:claim)"),
                {"job": claim.job_id, "claim": claim.claim_token},
            )
        return (
            await c.execute(text(sql), {"job": claim.job_id, "claim": claim.claim_token, **params})
        ).scalar_one()


async def replay(h, claim):
    async with h.runtime.engine.begin() as c:
        return (
            await c.execute(
                text("SELECT platform.human_context_work_replay(:job,:token)"),
                {"job": claim.job_id, "token": claim.claim_token},
            )
        ).scalar_one()


async def claim_job(h, job, *, due=True):
    # The bounded scan cursor selects the exact real job without changing other
    # jobs, resetting budgets or moving deadlines. For a context wait we wait for
    # its actual persisted due time; no scheduling-marker fields are forged.
    row = (
        await query(
            h, "SELECT id,available_at,status FROM platform.messaging_jobs WHERE id=:id", id=job
        )
    )[0]
    if due:
        left = (row["available_at"] - datetime.now(UTC)).total_seconds()
        if left > 0:
            assert left <= 60
            await asyncio.sleep(left)
    async with h.runtime.engine.begin() as c:
        return_value = (
            await c.execute(
                text("SELECT platform.messaging_claim('native-test',:cutoff,:at,:id)"),
                {
                    "cutoff": datetime.now(UTC),
                    "at": row["available_at"],
                    "id": UUID(int=job.int - 1),
                },
            )
        ).scalar_one()
    assert return_value["step"] == "CLAIMED" and return_value["id"] == str(job), return_value
    from asm.messaging.results import parse_claim

    return parse_claim(return_value["claim"])


async def incoming(
    h, number=1, *, provider="CONTROLLED", process=True, sender=None, kind="NEW", **changes
):
    if provider == "CONTROLLED":
        value = event(
            **dict(event_id=f"native-{number}", message_id=f"native-message-{number}") | changes
        )
        receipt = await h.kernel.ingest_event(h.adapter.source(value.bot_identity), value, uuid4())
    else:
        body = raw(
            100000 + number,
            500 + number,
            kind=kind,
            **({"sender": sender} if sender else {}),
            **changes,
        )
        receipt = await TelegramIngress(h.kernel, BOT).ingest_update(body, uuid4())
    if not process or receipt.job_id is None:
        return receipt
    claim = await claim_job(h, receipt.job_id)
    result = await h.kernel.process_inbox(claim)
    if result.message_id is None:
        return receipt, result, None
    cid = await scalar(
        h, "SELECT conversation_id FROM app.messages WHERE id=:id", id=result.message_id
    )
    return receipt, result, cid


async def read(h, cid):
    return await owner(h, "SELECT platform.human_context_read(:c)", c=cid)


async def policy(
    h,
    connection=CA,
    operation="ENABLE",
    key=None,
    *,
    expected=None,
    profile=None,
    after_statement=None,
):
    row = (await query(h, "SELECT * FROM app.channel_connections WHERE id=:id", id=connection))[0]
    state = await query(
        h, "SELECT * FROM platform.telegram_connection_state WHERE connection_id=:id", id=connection
    )
    binding = {
        k: str(row[k])
        for k in ("business_id", "provider", "bot_identity", "external_connection_id")
    }
    binding["owner_user_id"] = state[0]["owner_user_id"] if state else None
    installed = await scalar(h, "SELECT platform.human_context_schema_profile()")
    assert installed["valid"], installed
    profile = profile or dict(
        source_tree=h.source_tree,
        schema_revision="0013",
        profile_sha256=installed["profile_sha256"],
        drain_confirmed=True,
    )
    expected = expected or (row["human_context_policy"], row["human_context_policy_epoch"])
    async with h.migrator.begin() as c:
        assert (await c.execute(text("SELECT session_user"))).scalar_one() == "asm_migrator"
        result = (
            await c.execute(
                text(
                    "SELECT platform.human_context_policy_command(:ws,:c,:op,:key,:policy,:epoch,CAST(:binding AS jsonb),CAST(:profile AS jsonb))"
                ),
                {
                    "ws": row["workspace_id"],
                    "c": connection,
                    "op": operation,
                    "key": key or str(uuid4()),
                    "policy": expected[0],
                    "epoch": expected[1],
                    "binding": json.dumps(binding),
                    "profile": json.dumps(profile),
                },
            )
        ).scalar_one()
        if after_statement is not None:
            await after_statement(c, result)
        return result


def reconcile_body(
    p, disposition="OWNER_TEXT", value="Owner confirmed the replacement agreement.", media="NONE"
):
    return dict(
        expected_client_id=p["client_id"],
        expected_control_generation=p["control_generation"],
        expected_context_version=p["context_version"],
        expected_policy_epoch=p["policy_epoch"],
        expected_observation_epoch=p["observation_epoch"],
        expected_ingress_checkpoint=p["ingress_checkpoint"],
        expected_input_state_hash=p["input_state_hash"],
        expected_revision_id=p["current_revision"]["revision_id"]
        if p["current_revision"]
        else None,
        disposition=disposition,
        text=value if disposition != "CANONICAL_SUFFICIENT" else None,
        source_media=media,
        attestation="REVIEWED_AVAILABLE_CONTEXT",
    )


async def reconcile(
    h,
    cid,
    *,
    body=None,
    key=None,
    disposition="OWNER_TEXT",
    value="Owner confirmed the replacement agreement.",
    media="NONE",
):
    body = body or reconcile_body(await read(h, cid), disposition, value, media)
    return await owner(
        h,
        "SELECT platform.human_context_reconcile(:c,:key,CAST(:body AS jsonb))",
        c=cid,
        key=key or str(uuid4()),
        body=json.dumps(body, ensure_ascii=False),
    )


async def control(h, cid, operation="RESUME", *, key=None):
    p = await read(h, cid)
    return await owner(
        h,
        "SELECT platform.conversation_control_execute(:c,:client,:op,:key,:g,:v)",
        c=cid,
        client=UUID(p["client_id"]),
        op=operation,
        key=key or str(uuid4()),
        g=int(p["control_generation"]),
        v=int(p["context_version"]),
    )


async def activate(h, *, provider="CONTROLLED", disposition="OWNER_TEXT"):
    _, _, cid = await incoming(h, provider=provider)
    await policy(h, CA if provider == "CONTROLLED" else h.telegram_connection)
    saved = await reconcile(h, cid, disposition=disposition)
    resume = await control(h, cid)
    return cid, saved, resume


async def prepared(h, cid, number=2):
    await incoming(h, number)
    turn = (
        await query(
            h,
            "SELECT * FROM app.conversation_turns WHERE conversation_id=:c AND ingress_control_mode='AI' ORDER BY first_ingress_at DESC,id DESC LIMIT 1",
            c=cid,
        )
    )[0]
    await seal(h, turn["id"])
    turn = (await query(h, "SELECT * FROM app.conversation_turns WHERE id=:t", t=turn["id"]))[0]
    jobs = await query(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE turn_id=:t AND turn_revision=:r AND step='GUARDED_TEXT'",
        t=turn["id"],
        r=turn["revision"],
    )
    assert len(jobs) == 1
    claim = await claim_job(h, jobs[0]["id"])
    snapshot = await worker(h, claim, "SELECT platform.guard_turn_prepare(:job,:claim)")
    return claim, snapshot, turn


def sqlstate(error):
    return getattr(error.value.orig, "sqlstate", None)


async def test_fresh_catalog_exact_security_and_foundation_fail_closed(native):
    h = native
    module, _ = source_statements()
    async with h.migrator.connect() as c:
        columns = (
            await c.execute(
                text(
                    "SELECT n.nspname||'.'||r.relname,array_agg(a.attname::text ORDER BY a.attnum) FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r' GROUP BY 1"
                )
            )
        ).all()
        assert {name: tuple(cols) for name, cols in columns} == module.NATIVE_COLUMNS
        assert (
            await c.execute(
                text(
                    "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app','platform') AND p.prokind='f'"
                )
            )
        ).scalar_one() == 167
        for signature in module.NEW_FUNCTIONS:
            row = (
                await c.execute(
                    text(
                        "SELECT p.proowner::regrole::text,p.prosecdef,p.proconfig,has_function_privilege('asm_runtime',p.oid,'EXECUTE'),EXISTS(SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE') FROM pg_proc p WHERE p.oid=CAST(:s AS regprocedure)"
                    ),
                    {"s": signature},
                )
            ).one()
            assert row == (
                "asm_migrator",
                True,
                ["search_path=pg_catalog, pg_temp"],
                signature in module.PUBLIC_FUNCTIONS,
                False,
            ), signature
        for table in module.TABLES:
            row = (
                await c.execute(
                    text(
                        "SELECT relowner::regrole::text,relrowsecurity,relforcerowsecurity,has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE') FROM pg_class WHERE oid=CAST(:t AS regclass)"
                    ),
                    {"t": table},
                )
            ).one()
            assert row == ("asm_migrator", True, True, False)
    for table in module.TABLES:
        with pytest.raises(DBAPIError) as denied:
            async with h.runtime.engine.begin() as c:
                await c.execute(text(f"SELECT * FROM {table}"))
        assert sqlstate(denied) == "42501"
    runtime = RuntimeDatabase(Settings())
    try:
        with pytest.raises(RuntimeError, match="schema"):
            await runtime.check()
    finally:
        await runtime.close()
    assert (await scalar(h, "SELECT platform.human_context_schema_profile()"))["valid"] is True


async def test_policy_replay_pause_noop_and_migrator_authority(native):
    h = native
    enabled = await policy(h, key="enable-A", expected=("OFF_UNUSED", 0))
    assert enabled["outcome"] == "ACCEPTED" and enabled["result"]["accepted_policy_epoch"] == "1"
    noop = await policy(h, key="enable-noop")
    assert noop["result"]["change"] == "UNCHANGED"
    paused = await policy(h, operation="PAUSE", key="pause-B")
    assert paused["result"]["accepted_policy"] == "PAUSED"
    replayed = await policy(h, key="enable-A", expected=("OFF_UNUSED", 0))
    assert replayed == dict(outcome="REPLAY", result=enabled["result"])
    assert (
        await query(
            h,
            "SELECT human_context_policy,human_context_policy_epoch FROM app.channel_connections WHERE id=:id",
            id=CA,
        )
    )[0] == dict(human_context_policy="PAUSED", human_context_policy_epoch=1)
    assert (await policy(h, key="reenable"))["result"]["accepted_policy_epoch"] == "2"
    with pytest.raises(DBAPIError) as stale:
        await policy(h, key="different-old-key", expected=("OFF_UNUSED", 0))
    assert sqlstate(stale) == "P2601" and "STALE_STATE" in str(stale.value)
    with pytest.raises(DBAPIError) as denied:
        async with h.runtime.engine.begin() as c:
            await c.execute(text("SELECT set_config('asm.actor_kind','LOCAL_PROVISIONER',true)"))
            await c.execute(
                text(
                    "SELECT platform.human_context_policy_command(NULL,NULL,'ENABLE','forged','OFF_UNUSED',0,'{}'::jsonb,'{}'::jsonb)"
                )
            )
    assert sqlstate(denied) == "42501"
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_policy_receipts") == 4
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM app.audit_events WHERE event_type='HUMAN_CONTEXT_POLICY_COMMANDED'",
        )
        == 4
    )


async def test_reconcile_resume_v3_replacement_and_old_ack_replay(native):
    h = native
    cid, saved, activation = await activate(h)
    p = await read(h, cid)
    assert p["review_status"] == "CONFIRMED" and p["control_mode"] == "AI"
    assert p["resume_blockers"] == ["HUMAN_REQUIRED"]
    claim, snapshot, _ = await prepared(h, cid)
    assert (
        snapshot["schema_version"] == 3
        and snapshot["human_context"]["revision_id"] == saved["result"]["revision_id"]
    )
    assert snapshot["human_context"]["text"] == "Owner confirmed the replacement agreement."
    final_body = {
        k: v for k, v in snapshot.items() if k not in ("snapshot_digest", "code", "job_id")
    }
    assert (
        await scalar(
            h,
            "SELECT encode(sha256(convert_to(CAST(:b AS jsonb)::text,'UTF8')),'hex')",
            b=json.dumps(final_body),
        )
        == snapshot["snapshot_digest"]
    )
    assert (
        await scalar(
            h,
            "SELECT platform.human_context_snapshot_valid(CAST(:b AS jsonb),'GUARDED')",
            b=json.dumps({k: v for k, v in snapshot.items() if k not in ("code", "job_id")}),
        )
        is True
    )
    await control(h, cid, "TAKEOVER")
    body = reconcile_body(
        await read(h, cid), value="Replacement R2 preserves all material agreements."
    )
    r2 = await reconcile(h, cid, body=body, key="R2")
    assert r2["result"]["previous_revision_id"] == saved["result"]["revision_id"]
    old_body = reconcile_body(
        dict(
            p,
            control_generation=saved["result"]["control_generation"],
            context_version=saved["result"]["previous_context_version"],
            current_revision=None,
        ),
        value="Owner confirmed the replacement agreement.",
    )
    # Replay the exact accepted body from the receipt's immutable request fields.
    row = (
        await query(
            h,
            "SELECT * FROM platform.human_context_reconciliations WHERE id=:id",
            id=UUID(saved["result"]["revision_id"]),
        )
    )[0]
    old_body.update(
        expected_policy_epoch=str(row["policy_epoch"]),
        expected_observation_epoch=str(row["observation_epoch"]),
        expected_ingress_checkpoint=str(row["reviewed_ingress_seq"]),
        expected_input_state_hash=row["reviewed_input_state_hash"],
    )
    replayed = await reconcile(h, cid, body=old_body, key=row["idempotency_key"])
    assert replayed == dict(outcome="REPLAY", result=saved["result"])
    assert (await read(h, cid))["current_revision"]["revision_id"] == r2["result"]["revision_id"]
    assert await scalar(h, "SELECT count(*) FROM app.messages WHERE conversation_id=:c", c=cid) == 2


def consumer_result(snapshot):
    return dict(
        consumer="TURN_TEST_V1",
        snapshot_digest=snapshot["snapshot_digest"],
        member_count=len(snapshot["members"]),
        ready_file_count=sum(
            m["current"]["image_availability"] == "ORIGINAL_READY" for m in snapshot["members"]
        ),
        wait_expired_count=sum(
            m["current"]["image_availability"] == "ORIGINAL_PENDING" for m in snapshot["members"]
        ),
    )


async def current_turn(h, cid):
    return (
        await query(
            h,
            "SELECT * FROM app.conversation_turns WHERE conversation_id=:c AND ingress_control_mode='AI' ORDER BY first_ingress_at DESC,id DESC LIMIT 1",
            c=cid,
        )
    )[0]


async def work_for(h, turn, step):
    rows = await query(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE turn_id=:t AND turn_revision=:r AND step=:step",
        t=turn["id"],
        r=turn["revision"],
        step=step,
    )
    assert len(rows) == 1
    return await claim_job(h, rows[0]["id"])


async def duplicate_pending(h, *, number=90, message=2, value=None):
    return await incoming(
        h,
        number,
        process=False,
        message_id=f"native-message-{message}",
        **({"text": value} if value else {}),
    )


@pytest.mark.parametrize(
    "boundary", ["prepare", "accept", "send", "escalation", "test_prepare", "test_finalize"]
)
async def test_pending_same_job_wait_replay_and_single_continuation(native, boundary):
    from asm.conversations.guards import GUARD_TEXT

    h = native
    cid, _, _ = await activate(h)
    marker = "CONTROLLED ESCALATION TEST" if boundary == "escalation" else None
    await incoming(h, 2, **({"text": marker} if marker else {}))
    t = await current_turn(h, cid)
    await seal(h, t["id"])
    t = await current_turn(h, cid)
    step = (
        "ESCALATE_OWNER"
        if boundary == "escalation"
        else "TEST_CONSUME"
        if boundary.startswith("test_")
        else "GUARDED_TEXT"
    )
    claim = await work_for(h, t, step)
    snapshot = None
    if boundary in ("accept", "send"):
        snapshot = await worker(h, claim, "SELECT platform.guard_turn_prepare(:job,:claim)")
    elif boundary == "test_finalize":
        snapshot = await worker(h, claim, "SELECT platform.turn_execute(:job,:claim)")
    accepted = None
    if boundary == "send":
        accepted = await worker(
            h,
            claim,
            "SELECT platform.guard_turn_accept(:job,:claim,:digest,:value)",
            digest=snapshot["snapshot_digest"],
            value=GUARD_TEXT,
        )
        claim = await claim_job(h, UUID(accepted["send_job_id"]))
    before = (
        await query(
            h,
            "SELECT version,control_generation,activation_fence_seq,human_observation_epoch FROM app.conversations WHERE id=:c",
            c=cid,
        )
    )[0]
    before_job = (
        await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:j", j=claim.job_id)
    )[0]
    box_before = (
        (
            await query(
                h, "SELECT * FROM app.outbox_events WHERE id=:id", id=UUID(accepted["outbox_id"])
            )
        )[0]
        if accepted
        else None
    )
    duplicate = await duplicate_pending(h, value=marker)
    if boundary == "prepare":
        sql = "SELECT platform.guard_turn_prepare(:job,:claim)"
        params = {}
    elif boundary == "accept":
        sql = "SELECT platform.guard_turn_accept(:job,:claim,:digest,:value)"
        params = {"digest": snapshot["snapshot_digest"], "value": GUARD_TEXT}
    elif boundary == "send":
        sql = "SELECT platform.guard_send_begin(:job,:claim)"
        params = {}
    elif boundary == "escalation":
        sql = "SELECT platform.escalation_request_for_turn(:job,:claim)"
        params = {}
    elif boundary == "test_prepare":
        sql = "SELECT platform.turn_execute(:job,:claim)"
        params = {}
    else:
        sql = "SELECT platform.turn_consumer_finalize(:job,:claim,CAST(:result AS jsonb))"
        params = {"result": json.dumps(consumer_result(snapshot))}
    waited = await worker(h, claim, sql, **params)
    assert set(waited) == {
        "code",
        "job_id",
        "turn_id",
        "turn_revision",
        "outbox_id",
        "status",
        "reason",
        "available_at",
        "recorded_at",
    }
    assert (
        waited["code"] == "CONTEXT_WAIT"
        and waited["status"] == "READY"
        and waited["reason"] == "CONTEXT_INPUT_PENDING"
    )
    assert (
        waited["job_id"] == str(claim.job_id)
        and waited["turn_id"] == str(t["id"])
        and waited["turn_revision"] == t["revision"]
    )
    after_job = (
        await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:j", j=claim.job_id)
    )[0]
    assert (
        after_job["status"] == "READY"
        and after_job["attempt_count"] == before_job["attempt_count"] == 1
    )
    assert (
        after_job["first_started_at"] == before_job["first_started_at"]
        and after_job["turn_revision"] == before_job["turn_revision"]
    )
    assert (
        after_job["context_wait_result"] == waited
        and after_job["context_wait_claim_token"] == claim.claim_token
    )
    assert (
        await query(
            h,
            "SELECT version,control_generation,activation_fence_seq,human_observation_epoch FROM app.conversations WHERE id=:c",
            c=cid,
        )
    )[0] == before
    assert (await read(h, cid))["automation_work"]["state"] == "WAITING_CONTEXT"
    assert await replay(h, claim) == waited
    async with h.runtime.engine.begin() as c:
        assert (
            await c.execute(text(sql), {"job": claim.job_id, "claim": claim.claim_token, **params})
        ).scalar_one() == waited
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == (
        1 if accepted else 0
    )
    assert await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM app.escalations") == 0
    if accepted:
        assert (
            await query(
                h, "SELECT * FROM app.outbox_events WHERE id=:id", id=UUID(accepted["outbox_id"])
            )
        )[0] == box_before
    duplicate_claim = await claim_job(h, duplicate.job_id)
    assert (await h.kernel.process_inbox(duplicate_claim)).code == "DUPLICATE"
    next_claim = await claim_job(h, claim.job_id)
    assert next_claim.claim_token != claim.claim_token and next_claim.attempt_count == 2
    with pytest.raises(DBAPIError) as old:
        await replay(h, claim)
    assert sqlstate(old) == "P2001" and "STALE_CLAIM" in str(old.value)
    if boundary == "send":
        permit = await worker(h, next_claim, "SELECT platform.guard_send_begin(:job,:claim)")
        assert permit["code"] == "PERMITTED" and permit["text"] == GUARD_TEXT
        await h.kernel.finish_send(
            next_claim.job_id,
            next_claim.claim_token,
            UUID(permit["attempt_id"]),
            SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
        )
        assert (
            await scalar(
                h,
                "SELECT status FROM app.outbox_events WHERE id=:id",
                id=UUID(accepted["outbox_id"]),
            )
            == "UNKNOWN"
        )
    elif boundary == "escalation":
        assert (await worker(h, next_claim, sql))["code"] == "ESCALATED"
        assert await scalar(h, "SELECT count(*) FROM app.escalations") == 1
    elif boundary.startswith("test_"):
        fresh = await worker(h, next_claim, "SELECT platform.turn_execute(:job,:claim)")
        assert fresh["schema_version"] == 3
        finished = await worker(
            h,
            next_claim,
            "SELECT platform.turn_consumer_finalize(:job,:claim,CAST(:result AS jsonb))",
            result=json.dumps(consumer_result(fresh)),
        )
        assert (
            finished["code"] == "OBSERVED"
            and await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 1
        )
    else:
        fresh = await worker(h, next_claim, "SELECT platform.guard_turn_prepare(:job,:claim)")
        accepted = await worker(
            h,
            next_claim,
            "SELECT platform.guard_turn_accept(:job,:claim,:digest,:value)",
            digest=fresh["snapshot_digest"],
            value=GUARD_TEXT,
        )
        assert (
            accepted["code"] == "ACCEPTED"
            and await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 1
        )
    assert (await read(h, cid))["automation_work"]["state"] == "IDLE"
    assert not h.adapter.ledger.exists()


async def test_canonical_coverage_and_own_accepted_outbound_eviction(native):
    from asm.conversations.guards import GUARD_TEXT

    h = native
    _, _, cid = await incoming(h)
    for number in range(2, 16):
        await incoming(h, number)
    await policy(h)
    await reconcile(h, cid, disposition="CANONICAL_SUFFICIENT")
    await control(h, cid)
    claim, snapshot, _ = await prepared(h, cid, number=16)
    assert (
        snapshot["coverage_status"] == "CANONICAL_COMPLETE"
        and snapshot["history_truncated"] is False
    )
    assert len(snapshot["recent_messages"]) == 16
    accepted = await worker(
        h,
        claim,
        "SELECT platform.guard_turn_accept(:job,:claim,:digest,:value)",
        digest=snapshot["snapshot_digest"],
        value=GUARD_TEXT,
    )
    assert accepted["code"] == "ACCEPTED"
    before = (
        await query(
            h,
            "SELECT version,control_generation,activation_fence_seq,human_observation_epoch FROM app.conversations WHERE id=:id",
            id=cid,
        )
    )[0]
    send = await claim_job(h, UUID(accepted["send_job_id"]))
    result = await worker(h, send, "SELECT platform.guard_send_begin(:job,:claim)")
    assert result["code"] == "CONTEXT_HOLD" and result["reason"] == "CONTEXT_COVERAGE_REQUIRED"
    box = (
        await query(
            h, "SELECT * FROM app.outbox_events WHERE id=:id", id=UUID(accepted["outbox_id"])
        )
    )[0]
    assert (
        box["status"] == "FAILED"
        and box["attempt_id"] is None
        and box["error_code"] == "NOT_ALLOWED"
    )
    after = (
        await query(
            h,
            "SELECT version,control_generation,activation_fence_seq,human_observation_epoch FROM app.conversations WHERE id=:id",
            id=cid,
        )
    )[0]
    assert after == dict(before, version=before["version"] + 1)
    p = await read(h, cid)
    assert p["control_mode"] == "AI" and p["coverage_status"] == "CANONICAL_TRUNCATED"
    assert (
        p["automation_work"]["state"] == "OPERATOR_REQUIRED"
        and p["automation_work"]["reason"] == "CONTEXT_COVERAGE_REQUIRED"
    )
    assert await replay(h, send) == result
    await control(h, cid, "TAKEOVER")
    with pytest.raises(DBAPIError) as canonical:
        await reconcile(h, cid, disposition="CANONICAL_SUFFICIENT")
    assert sqlstate(canonical) == "P2401" and "CONTEXT_COVERAGE_REQUIRED" in str(canonical.value)
    await reconcile(h, cid, value="Full retained agreement even after canonical tail eviction.")
    await control(h, cid)
    fresh_claim, fresh, _ = await prepared(h, cid, number=17)
    assert fresh["coverage_status"] == "OWNER_TEXT" and fresh["history_truncated"] is True
    assert (
        fresh["human_context"]["text"]
        == "Full retained agreement even after canonical tail eviction."
    )
    assert (
        await scalar(h, "SELECT status FROM platform.messaging_jobs WHERE id=:id", id=send.job_id)
        == "DEAD"
    )
    assert not h.adapter.ledger.exists()


async def legacy_exports(h):
    result = {}
    for table, columns in migration().BASELINE_COLUMNS.items():
        if table == "platform.alembic_version":
            continue
        rows = await query(
            h,
            "SELECT to_jsonb(r) AS v FROM (SELECT " + ",".join(columns) + " FROM " + table + ") r",
        )
        values = sorted(json.dumps(row["v"], sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = (len(values), hashlib.sha256("\n".join(values).encode()).hexdigest())
    return result


@pytest.mark.parametrize("native", ["0011"], indirect=True)
async def test_populated_v1_v2_unknown_winner_repeat_upgrade_and_exact_unused_reverse(native):
    from asm.files.database import FileDatabase
    from test_m2_1_postgres import command
    from test_m2_2_db_postgres import MANIFEST
    from test_m3_1_control_migrations import definitions

    h = native
    snapshots = []
    for number, version in ((1, None), (2, 2)):
        if version == 2:
            await migrate("upgrade", "0012")
        receipt, result, cid = await incoming(h, number)
        tid = await scalar(
            h,
            "SELECT turn_id FROM app.conversation_turn_messages WHERE message_id=:id",
            id=result.message_id,
        )
        await seal(h, tid)
        t = (await query(h, "SELECT * FROM app.conversation_turns WHERE id=:id", id=tid))[0]
        claim = await work_for(h, t, "TEST_CONSUME")
        snapshot = await h.kernel.process_turn(claim)
        assert getattr(snapshot, "schema_version", None) == version
        finished = await h.kernel.finish_turn(claim, consume(snapshot))
        assert finished.code == "OBSERVED"
        snapshots.append((claim, snapshot, finished))
    requested = await command(h, cid, value="Retained unknown send.", key="legacy-unknown")
    send_id = await scalar(
        h, "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id", id=requested.outbox_id
    )
    claim = await claim_job(h, send_id)
    permit = await h.kernel.begin_send(claim)
    await h.kernel.finish_send(
        claim.job_id,
        claim.claim_token,
        permit.attempt_id,
        SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
    )
    _, image, cid = await incoming(h, 3, image_file_id="synthetic-original-reference")
    fetch_id = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE' AND file_id=(SELECT id FROM app.file_objects WHERE message_id=:id)",
        id=image.message_id,
    )
    fetch = await claim_job(h, fetch_id)
    files = FileDatabase(h.kernel)
    intent = await files.prepare_upload(fetch, MANIFEST)
    await files.finish_fetch(fetch.job_id, fetch.claim_token, intent.intent_id)
    before = await legacy_exports(h)
    async with h.migrator.connect() as c:
        catalog = await definitions(c)
    for _ in range(2):
        await migrate("upgrade", "0013")
        await migrate("upgrade", "0013")
        assert await legacy_exports(h) == before
        assert await scalar(h, "SELECT count(*) FROM platform.human_context_observations") == 0
        assert await scalar(h, "SELECT count(*) FROM platform.human_context_reconciliations") == 0
        assert await scalar(h, "SELECT count(*) FROM platform.human_context_policy_receipts") == 0
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM app.conversations WHERE human_observation_epoch IS NOT NULL OR human_context_revision_id IS NOT NULL",
            )
            == 0
        )
        assert (await scalar(h, "SELECT platform.human_context_schema_profile()"))["valid"]
        await migrate("downgrade", "0012")
        async with h.migrator.connect() as c:
            assert await definitions(c) == catalog
        assert await legacy_exports(h) == before
    for claim, snapshot, finished in snapshots:
        # Winning historical consumer receipt still carries the original bytes.
        async with h.runtime.engine.begin() as c:
            saved = (
                await c.execute(
                    text("SELECT platform.turn_consumer_replay(:job,:token)"),
                    {"job": claim.job_id, "token": claim.claim_token},
                )
            ).scalar_one()
        assert (
            saved["snapshot_digest"] == snapshot.snapshot_digest and saved["code"] == finished.code
        )
    assert (
        await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=requested.outbox_id)
        == "UNKNOWN"
    )
    assert await scalar(h, "SELECT count(*) FROM app.file_objects WHERE status='READY'") == 1


async def test_used_refusal_before_any_ddl_and_policy_profile_drift(native):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from test_m3_1_control_migrations import definitions

    h = native
    await policy(h)
    async with h.migrator.connect() as c:
        before = await definitions(c)
    async with h.migrator.connect() as c:
        async with c.begin():
            savepoint = await c.begin_nested()
            with pytest.raises(DBAPIError) as used:

                def reverse(sync):
                    module = migration()
                    module.op = Operations(MigrationContext.configure(sync))
                    module.downgrade()

                await c.run_sync(reverse)
            assert sqlstate(used) == "55000"
            await savepoint.rollback()
            assert await definitions(c) == before
    assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0013"
    profile = await scalar(h, "SELECT platform.human_context_schema_profile()")
    request = dict(
        source_tree=h.source_tree,
        schema_revision="0013",
        profile_sha256=profile["profile_sha256"],
        drain_confirmed=True,
    )
    async with h.migrator.connect() as c:
        async with c.begin():
            await c.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION platform.human_context_hash(text,text[]) TO asm_runtime"
                )
            )
            assert (
                await c.execute(text("SELECT platform.human_context_schema_profile()"))
            ).scalar_one()["valid"] is False
            # Roll back catalog fault injection; no gate is relaxed for a command.
            await c.rollback()
    assert (await scalar(h, "SELECT platform.human_context_schema_profile()"))["valid"] is True
    bad = dict(request, profile_sha256="0" * 64)
    with pytest.raises(DBAPIError) as drift:
        await policy(h, operation="PAUSE", profile=bad)
    assert sqlstate(drift) == "P2601" and "POLICY_PREREQUISITE_FAILED" in str(drift.value)
    assert (
        await scalar(
            h, "SELECT human_context_policy FROM app.channel_connections WHERE id=:id", id=CA
        )
        == "ON"
    )


async def test_native_observation_duplicate_source_links_previews_and_exclusions(native):
    h = native
    cid, _, _ = await activate(h, provider="TELEGRAM")
    before = await read(h, cid)
    first = await incoming(
        h, 11, provider="TELEGRAM", sender=OWNER, process=False, value="Native known agreement."
    )
    p = await read(h, cid)
    assert p["observation_epoch"] == "1" and p["context_blockers"] == ["NEW_OBSERVATION"]
    assert (
        p["context_version"] == before["context_version"]
        and p["control_generation"] == before["control_generation"]
    )
    # Exact semantic duplicate: new update key, the same message/origin/date/body.
    duplicate_raw = raw(100012, 511, sender=OWNER, value="Native known agreement.")
    duplicate = await TelegramIngress(h.kernel, BOT).ingest_update(duplicate_raw, uuid4())
    assert (await read(h, cid))["observation_epoch"] == "1"
    links = await query(
        h,
        "SELECT human_context_observation_id FROM platform.telegram_provenance WHERE receipt_id IN (:a,:b)",
        a=first.receipt_id,
        b=duplicate.receipt_id,
    )
    assert (
        len(links) == 2
        and links[0]["human_context_observation_id"]
        == links[1]["human_context_observation_id"]
        is not None
    )
    page = await owner(h, "SELECT platform.human_context_observations(:c,1,NULL)", c=cid)
    assert page["items"][0]["preview"] == dict(kind="TEXT", text="Native known agreement.")
    assert page["items"][0]["classification"] == "NATIVE_CANDIDATE" and page["next_cursor"] is None
    assert not any(
        key in json.dumps(page)
        for key in ("provider_chat_id", "file_id", "selected_file_id", "sender_id")
    )
    for offset, change in enumerate(("offline", "bot", "own_bot"), 20):
        body = raw(100000 + offset, 500 + offset, sender=OWNER)
        message = body["business_message"]
        if change == "offline":
            message["is_from_offline"] = True
        elif change == "bot":
            message["from"]["is_bot"] = True
        else:
            message["sender_business_bot"] = {
                "id": int(BOT),
                "is_bot": True,
                "first_name": "synthetic",
            }
        await TelegramIngress(h.kernel, BOT).ingest_update(body, uuid4())
    assert (await read(h, cid))["observation_epoch"] == "1"
    photo = await incoming(
        h,
        30,
        provider="TELEGRAM",
        sender=OWNER,
        process=False,
        photo="unfetched-native",
        value="caption",
    )
    assert photo.inbox_id is None
    assert (await read(h, cid))["observation_epoch"] == "2"
    assert await scalar(h, "SELECT count(*) FROM app.file_objects") == 0
    await control(h, cid, "TAKEOVER")
    with pytest.raises(DBAPIError) as media:
        await reconcile(h, cid, media="NONE")
    assert sqlstate(media) == "P2401" and "INVALID_REQUEST" in str(media.value)
    await reconcile(
        h, cid, media="UNAVAILABLE", value="Full text describes the unavailable native media."
    )
    await control(h, cid)
    assert (await read(h, cid))["review_status"] == "CONFIRMED"
    assert await scalar(h, "SELECT count(*) FROM app.messages WHERE conversation_id=:c", c=cid) == 1


async def test_job_inbox_only_failure_snapshot_and_input_hash_cas(native):
    h = native
    _, _, cid = await incoming(h)
    await policy(h)
    pending = await duplicate_pending(h, message=1)
    claim = await claim_job(h, pending.job_id)
    key = 918240013
    async with h.runtime.engine.connect() as b, h.migrator.connect() as a:
        await b.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        await b.commit()
        async with a.begin():
            await a.execute(
                text("SELECT 1 FROM app.channel_connections WHERE id=:id FOR UPDATE"), {"id": CA}
            )
            await a.execute(
                text("SELECT 1 FROM app.conversations WHERE id=:id FOR NO KEY UPDATE"), {"id": cid}
            )
            task = asyncio.create_task(
                a.execute(
                    text(
                        "WITH gate AS MATERIALIZED (SELECT pg_advisory_xact_lock(:key)) SELECT platform.human_context_projection(:ws,:c,statement_timestamp()) FROM gate"
                    ),
                    {"key": key, "ws": A, "c": cid},
                )
            )
            async with asyncio.timeout(3):
                while not await scalar(
                    h,
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE 'WITH gate AS MATERIALIZED%')",
                ):
                    await asyncio.sleep(0.01)
            async with b.begin():
                await b.execute(
                    text("SELECT platform.messaging_admit(:job,:token)"),
                    {"job": claim.job_id, "token": claim.claim_token},
                )
                terminal = (
                    await b.execute(
                        text(
                            "SELECT platform.messaging_retry(:job,:token,'DEPENDENCY_UNAVAILABLE',false)"
                        ),
                        {"job": claim.job_id, "token": claim.claim_token},
                    )
                ).scalar_one()
                assert terminal["status"] == "DEAD"
            await b.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            await b.commit()
            old = (await asyncio.wait_for(task, 3)).scalar_one()
            assert old["pending_context_input"] is True and old["has_failed_context_input"] is False
        current = await read(h, cid)
        assert (
            current["pending_context_input"] is False
            and current["has_failed_context_input"] is True
        )
        assert (
            current["input_state_hash"] != old["input_state_hash"]
            and current["context_version"] == old["context_version"]
        )
    with pytest.raises(DBAPIError) as stale:
        await reconcile(h, cid, body=reconcile_body(old))
    assert sqlstate(stale) == "P2401" and "STALE_STATE" in str(stale.value)
    with pytest.raises(DBAPIError) as gap:
        await reconcile(h, cid, disposition="CANONICAL_SUFFICIENT")
    assert sqlstate(gap) == "P2401" and "CONTEXT_INPUT_UNRESOLVED" in str(gap.value)
    await reconcile(h, cid)
    assert (await read(h, cid))["unreviewed_failed_context_input"] is False


@pytest.mark.parametrize("count", [0, 1, 1024, 1025])
async def test_pre_c_unsequenced_failed_overlap_and_gap_cap(native, count):
    h = native
    await policy(h, h.telegram_connection)
    for number in range(count):
        value = raw(
            200000 + number,
            300000 + number,
            kind="EDIT",
            value="Deferred material before a canonical conversation exists.",
        )
        receipt = await TelegramIngress(h.kernel, BOT).ingest_update(value, uuid4())
        claim = await claim_job(h, receipt.job_id)
        if number == 0:
            result = await worker(
                h,
                claim,
                "SELECT platform.messaging_retry(:job,:claim,'DEPENDENCY_UNAVAILABLE',false)",
            )
            assert result["status"] == "DEAD"
        else:
            assert (await h.kernel.process_inbox(claim)).code == "MATERIAL_PROCESSED"
    _, _, cid = await incoming(h, 1, provider="TELEGRAM")
    p = await read(h, cid)
    private = await scalar(
        h, "SELECT platform.human_context_projection(:ws,:c,clock_timestamp())", ws=A, c=cid
    )
    assert private["_gap_count"] == count and p["observation_epoch"] == "0"
    assert p["has_unsequenced_context_input"] == bool(count) and p[
        "has_failed_context_input"
    ] == bool(count)
    assert p["input_gap_limit_exceeded"] == (count > 1024)
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_observations") == 0
    if count:
        # The first FAILED unsequenced mutation is present in both branches,
        # and still occupies one identity in UNION DISTINCT/probe1025.
        with pytest.raises(DBAPIError) as insufficient:
            await reconcile(h, cid, disposition="CANONICAL_SUFFICIENT")
        assert sqlstate(insufficient) == "P2401" and "CONTEXT_INPUT_UNRESOLVED" in str(
            insufficient.value
        )
    if count > 1024:
        assert private["_gap_digest"] is None
        with pytest.raises(DBAPIError) as overflow:
            await reconcile(h, cid)
        assert sqlstate(overflow) == "P2401" and "CONTEXT_INPUT_UNRESOLVED" in str(overflow.value)
        await reconcile(h, cid, disposition="UNRESOLVED", value=None)
        assert (await read(h, cid))["current_revision"]["disposition"] == "UNRESOLVED"
        with pytest.raises(DBAPIError) as hold:
            await control(h, cid)
        assert sqlstate(hold) == "P2401" and "CONTEXT_UNRESOLVED" in str(hold.value)
    else:
        assert len(private["_gap_digest"]) == 64
        await reconcile(h, cid)
        p = await read(h, cid)
        assert p["unreviewed_failed_context_input"] is False and p["context_blockers"] == []
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.inbox_events WHERE status<>'PENDING' AND normalized_event->>'kind'='MESSAGE_EDITED'",
            )
            == count
        )
        await control(h, cid)
        assert (await read(h, cid))["review_status"] == "CONFIRMED"


async def test_wait_live_exhaustion_maintenance_and_no_budget_reset(native):
    h = native
    cid, _, _ = await activate(h)
    claim, snapshot, t = await prepared(h, cid)
    await duplicate_pending(h)
    first_started = await scalar(
        h, "SELECT first_started_at FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
    )
    for attempt in range(1, 6):
        result = await worker(h, claim, "SELECT platform.guard_turn_prepare(:job,:claim)")
        assert claim.attempt_count == attempt
        assert (
            await scalar(
                h,
                "SELECT first_started_at FROM platform.messaging_jobs WHERE id=:id",
                id=claim.job_id,
            )
            == first_started
        )
        if attempt < 5:
            assert result["code"] == "CONTEXT_WAIT"
            claim = await claim_job(h, claim.job_id)
        else:
            assert (
                result["code"] == "CONTEXT_WAIT_EXHAUSTED"
                and result["status"] == "DEAD"
                and result["available_at"] is None
            )
            assert await replay(h, claim) == result
    current = await read(h, cid)
    assert (
        current["automation_work"]["state"] == "OPERATOR_REQUIRED"
        and current["automation_work"]["reason"] == "CONTEXT_WAIT_EXHAUSTED"
    )
    assert (
        await scalar(h, "SELECT revision FROM app.conversation_turns WHERE id=:id", id=t["id"])
        == t["revision"]
    )
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0


async def test_scheduler_exhaustion_clears_old_wait_pair_without_rewriting_token(native):
    h = native
    cid, _, _ = await activate(h)
    claim, _, _ = await prepared(h, cid)
    await duplicate_pending(h)
    waited = await worker(h, claim, "SELECT platform.guard_turn_prepare(:job,:claim)")
    assert await replay(h, claim) == waited
    # Targeted age fault shortens the budget; it never resets or extends it.
    await query(
        h,
        "UPDATE platform.messaging_jobs SET first_started_at=clock_timestamp()-interval '16 minutes' WHERE id=:id RETURNING id",
        id=claim.job_id,
    )
    row = (
        await query(
            h, "SELECT available_at FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
        )
    )[0]
    left = (row["available_at"] - datetime.now(UTC)).total_seconds()
    if left > 0:
        await asyncio.sleep(left)
    async with h.runtime.engine.begin() as c:
        scanned = (
            await c.execute(
                text(
                    "SELECT platform.messaging_claim('native-maintenance',clock_timestamp(),:at,:id)"
                ),
                {"at": row["available_at"], "id": UUID(int=claim.job_id.int - 1)},
            )
        ).scalar_one()
    assert scanned["step"] == "TERMINALIZED" and scanned["id"] == str(claim.job_id)
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id))[0]
    assert job["status"] == "DEAD" and job["context_block_reason"] == "CONTEXT_WAIT_EXHAUSTED"
    assert (
        job["context_wait_claim_token"] is None
        and job["context_wait_result"] is None
        and job["turn_outcome"] == "FAILED"
    )
    with pytest.raises(DBAPIError) as old:
        await replay(h, claim)
    assert sqlstate(old) == "P2001" and "STALE_CLAIM" in str(old.value)
    assert (await read(h, cid))["automation_work"]["state"] == "OPERATOR_REQUIRED"


async def test_material_supersede_before_claim_removes_false_wait_projection(native):
    h = native
    cid, _, _ = await activate(h, provider="TELEGRAM")
    _, processed, _ = await incoming(h, 2, provider="TELEGRAM")
    t = await current_turn(h, cid)
    await seal(h, t["id"])
    t = await current_turn(h, cid)
    claim = await work_for(h, t, "TEST_CONSUME")
    # Same canonical projection/new transport key -> pending duplicate.
    value = raw(100090, 502)
    await TelegramIngress(h.kernel, BOT).ingest_update(value, uuid4())
    waited = await worker(h, claim, "SELECT platform.turn_execute(:job,:claim)")
    assert waited["code"] == "CONTEXT_WAIT"
    mutation = await TelegramIngress(h.kernel, BOT).ingest_update(
        raw(100091, 502, kind="EDIT", value="Changed canonical content."), uuid4()
    )
    assert (
        await h.kernel.process_inbox(await claim_job(h, mutation.job_id))
    ).code == "MATERIAL_PROCESSED"
    due = await scalar(
        h, "SELECT available_at FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
    )
    left = (due - datetime.now(UTC)).total_seconds()
    if left > 0:
        await asyncio.sleep(left)
    async with h.runtime.engine.begin() as c:
        scanned = (
            await c.execute(
                text(
                    "SELECT platform.messaging_claim('native-supersede',clock_timestamp(),:at,:id)"
                ),
                {"at": due, "id": UUID(int=claim.job_id.int - 1)},
            )
        ).scalar_one()
    assert scanned["step"] == "TERMINALIZED"
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id))[0]
    assert job["turn_outcome"] == "SUPERSEDED" and job["context_block_reason"] is None
    assert job["context_wait_claim_token"] is None and job["context_wait_result"] is None
    assert (await read(h, cid))["automation_work"]["state"] == "IDLE"
    assert (
        await scalar(
            h, "SELECT material_invalidated FROM app.conversation_turns WHERE id=:id", id=t["id"]
        )
        is True
    )


async def test_retained_tenancy_security_surface_on_native_db_lane(native):
    from test_tenancy_postgres import test_runtime_roles_policies_functions_and_platform_surface

    # Invoke the actual unchanged old assertions plus the exact successor delta
    # on real role connections. Foundation rejection is asserted separately;
    # this deliberately is not a claim that the full application can start.
    await test_runtime_roles_policies_functions_and_platform_surface(
        (native.runtime, native.migrator)
    )


async def create_escalation(h, cid):
    await incoming(h, 2, text="CONTROLLED ESCALATION TEST")
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    claim = await work_for(h, turn, "ESCALATE_OWNER")
    result = await worker(h, claim, "SELECT platform.escalation_request_for_turn(:job,:claim)")
    assert result["code"] == "ESCALATED"
    return UUID(result["escalation_id"])


async def escalation_arguments(h, eid, operation="RESOLVE", key=None):
    row = (
        await query(
            h,
            "SELECT e.*,c.version AS cv,c.control_generation AS cg FROM app.escalations e JOIN app.conversations c ON (c.workspace_id,c.id)=(e.workspace_id,e.conversation_id) WHERE e.id=:id",
            id=eid,
        )
    )[0]
    return dict(
        e=eid,
        c=row["conversation_id"],
        client=row["client_id"],
        op=operation,
        key=key or str(uuid4()),
        v=row["version"],
        g=row["cg"],
        cv=row["cv"],
        answer="Explicit owner decision." if operation == "RESOLVE" else None,
    )


ESCALATION_SQL = "SELECT platform.escalation_command(:e,:c,:client,:op,:key,:v,:g,:cv,:answer)"


async def test_escalation_own_bump_pause_hold_cancel_and_retained_replay(native):
    h = native
    cid, saved, _ = await activate(h)
    eid = await create_escalation(h, cid)
    view = await owner(h, "SELECT platform.escalation_read(:e)", e=eid)
    assert int(view["current_context"]["context_version"]) > int(
        saved["result"]["accepted_context_version"]
    )
    assert view["context_hold"] is None and view["can_resolve"] is True
    accepted_args = await escalation_arguments(h, eid)
    accepted = await owner(h, ESCALATION_SQL, **accepted_args)
    assert accepted["code"] == "ACCEPTED"
    await policy(h, operation="PAUSE")
    assert (await owner(h, "SELECT platform.escalation_read(:e)", e=eid))["context_hold"] is None
    await control(h, cid, "TAKEOVER")
    before = await legacy_exports(h)
    # Winning replay requires current live owner, but acquires no new connection
    # lock or context permission even after a newer pause/Takeover.
    async with h.migrator.connect() as blocker:
        async with blocker.begin():
            await blocker.execute(
                text("SELECT 1 FROM app.channel_connections WHERE id=:c FOR UPDATE"), {"c": CA}
            )
            replayed = await asyncio.wait_for(owner(h, ESCALATION_SQL, **accepted_args), 1.5)
    assert replayed == dict(
        code="REPLAY",
        result=accepted["result"],
        request_fingerprint=accepted["request_fingerprint"],
    )
    assert await legacy_exports(h) == before


async def test_escalation_pause_hold_refuses_resolve_and_cancel_needs_no_connection(native):
    h = native
    cid, _, _ = await activate(h)
    eid = await create_escalation(h, cid)
    before = await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid)
    await policy(h, operation="PAUSE")
    view = await owner(h, "SELECT platform.escalation_read(:e)", e=eid)
    assert (
        view["validity"] == "CURRENT"
        and view["waiting"] == "WAITING_FOR_HUMAN"
        and view["can_resolve"] is False
    )
    assert view["context_hold"]["reason"] == "CONTEXT_POLICY_PAUSED"
    page = await owner(h, "SELECT platform.escalation_list(20,'ALL',NULL,NULL)")
    assert page["items"][0]["context_hold"] == view["context_hold"]
    with pytest.raises(DBAPIError) as held:
        await owner(h, ESCALATION_SQL, **(await escalation_arguments(h, eid)))
    assert sqlstate(held) == "P2501" and "STALE_STATE" in str(held.value)
    assert await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid) == before
    assert await scalar(h, "SELECT count(*) FROM platform.escalation_command_receipts") == 0
    args = await escalation_arguments(h, eid, "CANCEL")
    async with h.migrator.connect() as blocker:
        async with blocker.begin():
            await blocker.execute(
                text("SELECT 1 FROM app.channel_connections WHERE id=:c FOR UPDATE"), {"c": CA}
            )
            cancelled = await asyncio.wait_for(owner(h, ESCALATION_SQL, **args), 1.5)
    assert cancelled["result"]["accepted_status"] == "CANCELLED"
    assert (
        await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid) == before + 1
    )


async def wait_blocked(h, pid, blocker, timeout=1.5):
    async with asyncio.timeout(timeout):
        while not await scalar(
            h,
            "SELECT :blocker=ANY(pg_blocking_pids(:pid))",
            pid=pid,
            blocker=blocker,
        ):
            await asyncio.sleep(0.01)


async def test_resolve_waits_for_worker_connection_before_c_and_rechecks_after_wait(native):
    h = native
    cid, _, _ = await activate(h)
    eid = await create_escalation(h, cid)
    duplicate = await duplicate_pending(h, message=2, value="CONTROLLED ESCALATION TEST")
    claim = await claim_job(h, duplicate.job_id)
    args = await escalation_arguments(h, eid)
    resolve_pid = asyncio.get_running_loop().create_future()

    async def resolve():
        async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            resolve_pid.set_result(
                (await unit._execute("SELECT pg_backend_pid()", {})).scalar_one()
            )
            return (await unit._execute(ESCALATION_SQL, args)).scalar_one()

    async with h.runtime.engine.connect() as connection:
        async with connection.begin():
            worker_pid = (await connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await connection.execute(
                text("SELECT platform.messaging_admit(:j,:t)"),
                {"j": claim.job_id, "t": claim.claim_token},
            )
            # C is a latch: the actual worker takes Connection UPDATE and then
            # waits on C. RESOLVE must wait on that worker, rather than on C's
            # latch. pg_blocking_pids is visible without monitoring privileges.
            async with h.migrator.begin() as latch:
                latch_pid = (await latch.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                await latch.execute(
                    text("SELECT 1 FROM app.conversations WHERE id=:c FOR NO KEY UPDATE"),
                    {"c": cid},
                )
                processing = asyncio.create_task(
                    connection.execute(
                        text("SELECT platform.messaging_process_inbox(:j,:t)"),
                        {"j": claim.job_id, "t": claim.claim_token},
                    )
                )
                await wait_blocked(h, worker_pid, latch_pid)
                task = asyncio.create_task(resolve())
                await wait_blocked(h, await resolve_pid, worker_pid)
            processed = (await processing).scalar_one()
            assert processed["code"] == "DUPLICATE"
        resolved = await asyncio.wait_for(task, 3)
    assert resolved["result"]["accepted_status"] == "RESOLVED"
    assert (await owner(h, "SELECT platform.escalation_read(:e)", e=eid))["status"] == "RESOLVED"


async def test_takeover_then_reconcile_cancels_pending_escalation_only_once(native):
    h = native
    cid, _, _ = await activate(h)
    eid = await create_escalation(h, cid)
    before = await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid)
    await control(h, cid, "TAKEOVER")
    assert await scalar(h, "SELECT status FROM app.escalations WHERE id=:id", id=eid) == "CANCELLED"
    terminal = (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=eid))[0]
    assert await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid) == before
    await reconcile(h, cid, value="Current full replacement after explicit takeover.")
    assert (await query(h, "SELECT * FROM app.escalations WHERE id=:id", id=eid))[0] == terminal
    assert (
        await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid) == before + 1
    )


async def test_hash_vectors_actual_reconcile_fingerprint_and_closed_body(native):
    h = native
    parts = [None, "", "é", "e\u0301", "line\n:delimiter", "🎨"]
    prefix = "asm:m3:vector:v1\n"
    encoded = prefix.encode() + b"".join(
        b"-1:\n" if v is None else str(len(v.encode())).encode() + b":" + v.encode() + b"\n"
        for v in parts
    )
    assert (
        await scalar(
            h,
            "SELECT encode(platform.human_context_hash(:p,CAST(:v AS text[])),'hex')",
            p=prefix,
            v=parts,
        )
        == hashlib.sha256(encoded).hexdigest()
    )
    _, _, cid = await incoming(h)
    await policy(h)
    text_value = " \té e\u0301 :\n 🎨\r "
    body = reconcile_body(await read(h, cid), value=text_value)
    accepted = await reconcile(h, cid, body=body, key="exact-byte-vector")
    fields = [
        str(A),
        str(UA),
        str(cid),
        body["expected_client_id"],
        body["expected_control_generation"],
        body["expected_context_version"],
        body["expected_policy_epoch"],
        body["expected_observation_epoch"],
        body["expected_ingress_checkpoint"],
        body["expected_input_state_hash"],
        body["expected_revision_id"],
        body["disposition"],
        body["text"],
        body["source_media"],
        body["attestation"],
    ]
    expected = b"asm:m3:human_context_reconcile:v1\n" + b"".join(
        b"-1:\n" if v is None else str(len(v.encode())).encode() + b":" + v.encode() + b"\n"
        for v in fields
    )
    assert (
        await scalar(
            h,
            "SELECT encode(request_fingerprint,'hex') FROM platform.human_context_reconciliations WHERE id=:id",
            id=UUID(accepted["result"]["revision_id"]),
        )
        == hashlib.sha256(expected).hexdigest()
    )
    assert (await read(h, cid))["current_revision"]["text"] == text_value
    payload = await scalar(
        h, "SELECT payload FROM app.audit_events WHERE event_type='HUMAN_CONTEXT_RECONCILED'"
    )
    assert set(payload) == {
        "revision_id",
        "previous_revision_id",
        "disposition",
        "source_media",
        "control_generation",
        "previous_context_version",
        "accepted_context_version",
        "policy_epoch",
        "observation_epoch",
        "reviewed_ingress_checkpoint",
    }
    for field, value in [
        ("text", ""),
        ("text", "\u2003\t"),
        ("text", 1),
        ("expected_policy_epoch", 1),
        ("expected_observation_epoch", "00"),
        ("attestation", None),
        ("source_media", None),
        ("disposition", None),
    ]:
        bad = dict(reconcile_body(await read(h, cid)), **{field: value})
        with pytest.raises(DBAPIError) as invalid:
            await reconcile(h, cid, body=bad)
        assert sqlstate(invalid) == "P2401" and "INVALID_REQUEST" in str(invalid.value)
    bad = dict(body, text="changed")
    with pytest.raises(DBAPIError) as conflict:
        await reconcile(h, cid, body=bad, key="exact-byte-vector")
    assert sqlstate(conflict) == "P2401" and "IDEMPOTENCY_KEY_CONFLICT" in str(conflict.value)
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_reconciliations") == 1


async def test_strict_v3_sql_shapes_digest_types_and_capacity(native):
    h = native
    cid, _, _ = await activate(h)
    _, snapshot, _ = await prepared(h, cid)
    valid = {k: v for k, v in snapshot.items() if k not in ("code", "job_id")}
    sql = """WITH body AS (SELECT CAST(:b AS jsonb)-'snapshot_digest' AS v), signed AS
      (SELECT v||jsonb_build_object('snapshot_digest',encode(sha256(convert_to(v::text,'UTF8')),'hex')) AS v FROM body)
      SELECT platform.human_context_snapshot_valid(v,'GUARDED') FROM signed"""
    assert await scalar(h, sql, b=json.dumps(valid)) is True
    variants = []
    for field, values in {
        "schema_version": [True, 3.0, 4, "3", None],
        "turn_revision": [True, 0, -1, "1", 9223372036854775808, None],
        "context_policy_epoch": ["0", "01", 1, None],
        "human_observation_epoch": ["00", "-1", True, None],
        "history_truncated": [None, "false"],
        "members": [None, [], {}, "bad", True],
        "recent_messages": [None, {}, "bad", True],
        "coverage_status": [None, "UNCONFIRMED"],
        "readiness": [None, "UNKNOWN"],
        "context_limitations": [[], ["NATIVE_MEDIA_UNAVAILABLE", "PROVIDER_HISTORY_UNVERIFIED"]],
    }.items():
        for value in values:
            bad = copy.deepcopy(valid)
            bad[field] = value
            variants.append((field, bad))
    for field, value in [
        ("text", None),
        ("text", " \t"),
        ("source_media", None),
        ("coverage", None),
        ("accepted_at", "2026-02-30T00:00:00.000000Z"),
    ]:
        bad = copy.deepcopy(valid)
        bad["human_context"][field] = value
        variants.append(("R." + field, bad))
    for field, value in [
        ("changed", None),
        ("schema_version", 1.0),
        ("image_availability", "HIDDEN"),
        ("text", None),
        ("content_type", None),
    ]:
        bad = copy.deepcopy(valid)
        bad["members"][0]["current"][field] = value
        variants.append(("current." + field, bad))
    bad = copy.deepcopy(valid)
    bad["members"][0]["initial_suppression_id"] = str(uuid4())
    variants.append(("partial member", bad))
    bad = copy.deepcopy(valid)
    bad["members"][0]["current"]["changed"] = True
    variants.append(("changed/version", bad))
    bad = copy.deepcopy(valid)
    bad["members"][0]["ingress_at"] = "now"
    variants.append(("literal clock", bad))
    bad = copy.deepcopy(valid)
    bad["recent_messages"] = list(reversed(bad["recent_messages"]))
    variants.append(("history order", bad))
    bad = copy.deepcopy(valid)
    bad["recent_messages"].append(bad["recent_messages"][-1])
    variants.append(("duplicate history", bad))
    bad = copy.deepcopy(valid)
    del bad["human_context"]
    variants.append(("missing R", bad))
    bad = copy.deepcopy(valid)
    bad["override"] = True
    variants.append(("extra", bad))
    for name, bad in variants:
        assert await scalar(h, sql, b=json.dumps(bad)) is False, name
    bad = copy.deepcopy(valid)
    bad["human_context"]["text"] = "x" * 2097153
    assert (
        await scalar(
            h,
            "SELECT platform.human_context_snapshot_check(CAST(:b AS jsonb),'GUARDED')",
            b=json.dumps(bad),
        )
        == "CONTEXT_TOO_LARGE"
    )
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM app.outbox_events") == 0


async def test_same_workspace_client_revision_source_and_null_link_negatives(native):
    h = native
    _, _, cid = await incoming(h)
    legacy = await control(h, cid)
    old_args = dict(
        c=cid,
        client=UUID(legacy["result"]["client_id"]),
        op="RESUME",
        key="unused-explicit",
        g=1,
        v=int(legacy["result"]["context_version"]),
    )
    # Use a fresh independent conversation for an exact legacy NULL-link receipt.
    _, _, legacy_c = await incoming(h, 30, chat_id="legacy-chat", sender_id="legacy-user")
    old_state = await read(h, legacy_c)
    old_args.update(
        c=legacy_c,
        client=UUID(old_state["client_id"]),
        g=int(old_state["control_generation"]),
        v=int(old_state["context_version"]),
    )
    old = await owner(
        h, "SELECT platform.conversation_control_execute(:c,:client,:op,:key,:g,:v)", **old_args
    )
    assert (
        await query(
            h,
            "SELECT human_context_revision_id,human_context_policy_epoch,human_observation_epoch FROM platform.conversation_control_receipts WHERE id=:id",
            id=UUID(old["result"]["receipt_id"]),
        )
    )[0] == dict(
        human_context_revision_id=None,
        human_context_policy_epoch=None,
        human_observation_epoch=None,
    )
    await policy(h)
    await control(h, cid, "TAKEOVER")
    r1 = await reconcile(h, cid)
    _, _, other = await incoming(h, 31, chat_id="other-chat", sender_id="other-user")
    r2 = await reconcile(h, other)
    body = reconcile_body(await read(h, cid))
    for bad in (
        dict(body, expected_client_id=r2["result"]["client_id"]),
        dict(body, expected_revision_id=r2["result"]["revision_id"]),
    ):
        with pytest.raises(DBAPIError) as denied:
            await reconcile(h, cid, body=bad)
        assert sqlstate(denied) == "P2401" and "NOT_FOUND" in str(denied.value)
    with pytest.raises(DBAPIError) as foreign:
        await owner(h, "SELECT platform.human_context_read(:c)", workspace=B, actor=UB, c=cid)
    assert sqlstate(foreign) == "P2401" and "NOT_FOUND" in str(foreign.value)
    activated = await control(h, cid)
    receipt = (
        await query(
            h,
            "SELECT to_jsonb(r) AS data FROM platform.conversation_control_receipts r WHERE id=:id",
            id=UUID(activated["result"]["receipt_id"]),
        )
    )[0]["data"]
    insertable = await scalar(
        h,
        """SELECT string_agg(quote_ident(column_name),',' ORDER BY ordinal_position)
      FROM information_schema.columns WHERE table_schema='platform' AND table_name='conversation_control_receipts'
      AND is_generated='NEVER'""",
    )
    for fields in (
        {"human_context_revision_id": None},
        {
            "human_context_revision_id": None,
            "human_context_policy_epoch": None,
            "human_observation_epoch": None,
        },
    ):
        bad = dict(receipt, id=str(uuid4()), idempotency_key=str(uuid4()), **fields)
        with pytest.raises(DBAPIError) as partial:
            await scalar(
                h,
                f"INSERT INTO platform.conversation_control_receipts({insertable}) SELECT {insertable} FROM jsonb_populate_record(NULL::platform.conversation_control_receipts,CAST(:b AS jsonb)) RETURNING id",
                b=json.dumps(bad),
            )
        assert sqlstate(partial) == "23514"
    # A historical NULL relation is not retroactively invalidated by ON.
    before = await legacy_exports(h)
    replayed = await owner(
        h, "SELECT platform.conversation_control_execute(:c,:client,:op,:key,:g,:v)", **old_args
    )
    assert replayed["code"] == "REPLAY" and replayed["result"] == old["result"]
    assert await legacy_exports(h) == before
    with pytest.raises(DBAPIError) as immutable:
        await query(
            h,
            "UPDATE platform.human_context_reconciliations SET context_text='forged' WHERE id=:id RETURNING id",
            id=UUID(r1["result"]["revision_id"]),
        )
    assert sqlstate(immutable) == "23514"
    with pytest.raises(DBAPIError) as runtime_dml:
        async with h.runtime.engine.begin() as c:
            await c.execute(
                text(
                    "UPDATE platform.messaging_jobs SET context_block_reason='CONTEXT_INPUT_PENDING'"
                )
            )
    assert sqlstate(runtime_dml) == "42501"


@pytest.mark.parametrize("counter", ["version", "control_generation"])
async def test_checked_conversation_overflow_whole_rollback(native, counter):
    h = native
    _, _, cid = await incoming(h)
    await policy(h)
    # Targeted counter fault on a legitimate C; no receipt, entitlement or permit
    # is fabricated and no counter is reset to regain a budget.
    await query(
        h,
        f"UPDATE app.conversations SET {counter}=9223372036854775807 WHERE id=:id RETURNING id",
        id=cid,
    )
    before = await legacy_exports(h)
    with pytest.raises(DBAPIError) as exhausted:
        if counter == "version":
            await reconcile(h, cid)
        else:
            await control(h, cid)
    assert sqlstate(exhausted) == "P2401"
    assert (
        "CONTROL_VERSION_EXHAUSTED" if counter == "control_generation" else "VERSION_EXHAUSTED"
    ) in str(exhausted.value)
    assert await legacy_exports(h) == before
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_reconciliations") == 0


async def test_policy_epoch_max_checked_without_wrap_and_noop_remains_safe(native):
    h = native
    connection = uuid4()
    # An explicit upper-bound data fault on a new synthetic connection. Normal
    # P0/ON/PAUSED/P+1 flows above all use the actual policy command.
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id,human_context_policy,human_context_policy_epoch) VALUES(:ws,:id,:b,'CONTROLLED','bound-bot','bound-connection','PAUSED',9223372036854775807)"
            ),
            {"ws": A, "id": connection, "b": BA},
        )
        await c.execute(
            text(
                "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:id,'CONTROLLED','bound-bot','bound-connection')"
            ),
            {"ws": A, "id": connection},
        )
    with pytest.raises(DBAPIError) as overflow:
        await policy(h, connection)
    assert sqlstate(overflow) == "P2601" and "POLICY_VERSION_EXHAUSTED" in str(overflow.value)
    safe = await policy(h, connection, operation="PAUSE")
    assert (
        safe["result"]["change"] == "UNCHANGED"
        and safe["result"]["accepted_policy_epoch"] == "9223372036854775807"
    )
    assert (
        await scalar(
            h,
            "SELECT human_context_policy_epoch FROM app.channel_connections WHERE id=:id",
            id=connection,
        )
        == 9223372036854775807
    )


async def test_observation_cursor_canonical_bytes_fixed_bound_and_relation(native):
    h = native
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    for n in range(3):
        await incoming(h, 10 + n, provider="TELEGRAM", sender=OWNER, value=f"review {n}")
    sql = "SELECT platform.human_context_observations(:c,:limit,CAST(:cursor AS jsonb))"
    page = await owner(h, sql, c=cid, limit=1, cursor=None)
    encoded = page["next_cursor"]
    assert (
        isinstance(encoded, str)
        and "=" not in encoded
        and "+" not in encoded
        and "/" not in encoded
    )
    raw_cursor = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    cursor = json.loads(raw_cursor)
    assert raw_cursor == json.dumps(cursor, separators=(",", ":")).encode()
    assert list(cursor) == ["v", "ws", "C", "Client", "P", "through_N", "after_N"]
    assert cursor["through_N"] == "3" and cursor["after_N"] == "1"
    await incoming(h, 20, provider="TELEGRAM", sender=OWNER, value="arrived after page one")
    next_page = await owner(h, sql, c=cid, limit=100, cursor=json.dumps(cursor))
    assert [v["epoch"] for v in next_page["items"]] == ["2", "3"]
    assert next_page["through_epoch"] == "3" and next_page["current_epoch"] == "4"
    assert next_page["next_cursor"] is None
    for field, value, error in [
        ("v", 1.0, "INVALID_REQUEST"),
        ("P", "01", "INVALID_REQUEST"),
        ("through_N", "5", "INVALID_REQUEST"),
        ("after_N", "4", "INVALID_REQUEST"),
        ("Client", str(uuid4()), "NOT_FOUND"),
        ("C", str(uuid4()), "NOT_FOUND"),
        ("ws", str(B), "ACCESS_DENIED"),
        ("after_N", None, "INVALID_REQUEST"),
    ]:
        with pytest.raises(DBAPIError) as bad:
            await owner(h, sql, c=cid, limit=1, cursor=json.dumps(dict(cursor, **{field: value})))
        assert sqlstate(bad) == "P2401" and error in str(bad.value)
    await policy(h, h.telegram_connection, "PAUSE")
    assert (await owner(h, sql, c=cid, limit=1, cursor=json.dumps(cursor)))["through_epoch"] == "3"
    await policy(h, h.telegram_connection)
    with pytest.raises(DBAPIError) as stale:
        await owner(h, sql, c=cid, limit=1, cursor=json.dumps(cursor))
    assert sqlstate(stale) == "P2401" and "CONTEXT_CURSOR_STALE" in str(stale.value)


async def test_indexed_projection_ignores_large_unrelated_pending_history(native):
    h = native
    _, _, cid = await incoming(h)
    await policy(h)
    # Actual ingress capabilities create 2400 unrelated pending rows. There is
    # no bulk SQL fabrication, disabled constraint, or planner forcing GUC.
    async with h.runtime.engine.begin() as c:
        for n in range(2400):
            value = event(
                event_id=f"unrelated-{n}",
                message_id=f"unrelated-{n}",
                chat_id=f"unrelated-chat-{n}",
                sender_id=f"unrelated-user-{n}",
            )
            await c.execute(
                text("SELECT platform.messaging_ingest('CONTROLLED',:bot,CAST(:e AS jsonb),:corr)"),
                {"bot": value.bot_identity, "e": json.dumps(value.values()), "corr": uuid4()},
            )
    # Also retain already sequenced duplicate history on the actual chat.
    for n in range(24):
        receipt = await duplicate_pending(h, number=500 + n, message=1)
        assert (
            await h.kernel.process_inbox(await claim_job(h, receipt.job_id))
        ).code == "DUPLICATE"
    async with h.migrator.begin() as c:
        await c.execute(text("ANALYZE platform.inbox_events"))
        await c.execute(text("ANALYZE app.messages"))
        sql = (
            await c.execute(
                text(
                    "SELECT prosrc FROM pg_proc WHERE oid='platform.human_context_projection(uuid,uuid,timestamptz)'::regprocedure"
                )
            )
        ).scalar_one()
        # EXPLAIN the exact installed core with only parameter substitution;
        # SECURITY DEFINER prevents the function call itself from being inlined.
        sql = sql.replace("p_conversation", "CAST(:c AS uuid)").replace(
            "p_clock", "CAST(:clock AS timestamptz)"
        )
        import re

        sql = re.sub(r"\bws\b", "CAST(:ws AS uuid)", sql)
        plan = (
            await c.execute(
                text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + sql),
                {"ws": A, "c": cid, "clock": datetime.now(UTC)},
            )
        ).scalar_one()[0]["Plan"]

    def nodes(p):
        yield p
        for child in p.get("Plans", []):
            yield from nodes(child)

    all_nodes = list(nodes(plan))
    inbox = [v for v in all_nodes if v.get("Relation Name") == "inbox_events"]
    assert inbox and all(v["Node Type"] != "Seq Scan" for v in inbox)
    assert max(v.get("Actual Rows", 0) for v in inbox) <= 25
    names = {v.get("Index Name") for v in all_nodes}
    assert "native_inbox_checkpoint_idx" in names and "native_inbox_pending_idx" in names
    assert "native_inbox_failed_idx" in names and "native_inbox_unsequenced_idx" in names
    assert (await read(h, cid))["pending_context_input"] is False
    assert (
        await scalar(
            h, "SELECT platform.human_context_projection(:ws,:c,clock_timestamp())", ws=A, c=cid
        )
    )["_gap_count"] == 0


@pytest.mark.parametrize("native", ["0007"], indirect=True)
async def test_legacy_null_ingress_and_old_ignored_key_are_not_backfilled(native):
    from test_m2_3_db_postgres import ingress, projection

    h = native
    old = await ingress(h, projection(message="503"))
    old_job = UUID(old["job_id"])
    await migrate("upgrade", "0012")
    assert (
        await scalar(
            h,
            "SELECT codec FROM platform.telegram_update_receipts WHERE id=:id",
            id=UUID(old["receipt_id"]),
        )
        is None
    )
    await query(
        h,
        "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE connection_id=:id RETURNING connection_id",
        id=h.telegram_connection,
    )
    old_body = raw(180000, 900, sender=OWNER, value="Previously ignored owner text")
    ignored = await TelegramIngress(h.kernel, BOT).ingest_update(old_body, uuid4())
    assert ignored.result_code == "IGNORED_NATIVE_OWNER_MESSAGE"
    await migrate("upgrade", "0013")
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    before = await read(h, cid)
    replayed = await TelegramIngress(h.kernel, BOT).ingest_update(old_body, uuid4())
    assert replayed.code == "DUPLICATE" and replayed.receipt_id == ignored.receipt_id
    assert (await read(h, cid))["observation_epoch"] == before["observation_epoch"] == "0"
    assert (
        await scalar(
            h,
            "SELECT human_context_observation_id FROM platform.telegram_provenance WHERE receipt_id=:id",
            id=ignored.receipt_id,
        )
        is None
    )
    assert before["pending_context_input"] is True
    old_claim = await claim_job(h, old_job)
    await worker(
        h, old_claim, "SELECT platform.messaging_retry(:job,:claim,'DEPENDENCY_UNAVAILABLE',false)"
    )
    after = await read(h, cid)
    assert (
        after["pending_context_input"] is False and after["has_unsequenced_context_input"] is True
    )
    assert (
        after["has_failed_context_input"] is True
        and after["input_state_hash"] != before["input_state_hash"]
    )
    await reconcile(h, cid)
    await control(h, cid)
    assert (await read(h, cid))["review_status"] == "CONFIRMED"


@pytest.mark.parametrize("outcome,changed", [("SENT", True), ("SENT", False), ("UNKNOWN", False)])
async def test_completion_without_connection_edge_and_exact_physical_fold(native, outcome, changed):
    from test_m2_3_db_postgres import begin_observed, probe_worker, request

    h = native
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    await reconcile(h, cid)
    pointer = (await read(h, cid))["current_revision"]["revision_id"]
    intent = await request(h, cid, value="reply")
    send_id = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id",
        id=UUID(intent["outbox_id"]),
    )
    claim = await claim_job(h, send_id)
    permit = await begin_observed(h, claim, await probe_worker(h, claim))
    receipt, processed, _ = await incoming(
        h,
        2,
        provider="TELEGRAM",
        kind="EDIT",
        sender=OWNER,
        value="changed reply" if changed else "reply",
    )
    assert processed.code == "MATERIAL_PROCESSED"
    # The provider id of the real deferred target is the new edit's message id.
    provider_id = "502"
    target = (
        await query(
            h,
            "SELECT * FROM platform.message_material_targets WHERE provider_message_id=:p",
            p=provider_id,
        )
    )[0]
    assert target["message_id"] is None
    before = await scalar(h, "SELECT version FROM app.conversations WHERE id=:id", id=cid)
    async with h.migrator.begin() as blocker:
        await blocker.execute(
            text("SELECT id FROM app.channel_connections WHERE id=:id FOR UPDATE"),
            {"id": h.telegram_connection},
        )
        async with h.runtime.engine.begin() as c:
            initial_updates = dict(
                (
                    await c.execute(
                        text(
                            "SELECT relname,n_tup_upd FROM pg_stat_xact_user_tables WHERE schemaname IN ('platform','app')"
                        )
                    )
                ).all()
            )
            result = (
                await asyncio.wait_for(
                    c.execute(
                        text(
                            "SELECT platform.messaging_finish_send(:job,:token,:attempt,:kind,:provider,:error)"
                        ),
                        {
                            "job": claim.job_id,
                            "token": claim.claim_token,
                            "attempt": UUID(permit["attempt_id"]),
                            "kind": "SUCCESS" if outcome == "SENT" else "UNKNOWN",
                            "provider": provider_id if outcome == "SENT" else None,
                            "error": None if outcome == "SENT" else "UNKNOWN_EXTERNAL_RESULT",
                        },
                    ),
                    1.5,
                )
            ).scalar_one()
            updates = dict(
                (
                    await c.execute(
                        text(
                            "SELECT relname,n_tup_upd FROM pg_stat_xact_user_tables WHERE schemaname IN ('platform','app')"
                        )
                    )
                ).all()
            )
            updates = {name: count - initial_updates[name] for name, count in updates.items()}
    assert result["status"] == outcome
    # Retained MATERIAL folds delivery and material impact into ONE physical C
    # write (+2 if changed); the target is likewise bound/folded only once.
    assert updates["conversations"] == 1
    assert updates["message_material_targets"] == int(outcome == "SENT")
    assert await scalar(
        h, "SELECT version FROM app.conversations WHERE id=:id", id=cid
    ) == before + 1 + int(outcome == "SENT" and changed)
    p = await read(h, cid)
    assert p["current_revision"]["revision_id"] == pointer
    if outcome == "SENT":
        exact = raw(100099, 502, sender=OWNER, value="reply")
        echo = await TelegramIngress(h.kernel, BOT).ingest_update(exact, uuid4())
        assert echo.result_code == "IGNORED_ECHO" and echo.job_id is None
        assert (await read(h, cid))["observation_epoch"] == p["observation_epoch"]


async def test_native_file_winner_completion_and_v3_consumer_counts(native):
    from asm.files.database import FileDatabase
    from test_m2_2_db_postgres import MANIFEST

    h = native
    cid, _, _ = await activate(h, provider="TELEGRAM")
    _, image, same = await incoming(
        h, 2, provider="TELEGRAM", photo="native-original-photo", value="Caption"
    )
    assert same == cid
    fid = await scalar(h, "SELECT id FROM app.file_objects WHERE message_id=:m", m=image.message_id)
    jid = await scalar(
        h, "SELECT id FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE' AND file_id=:f", f=fid
    )
    claim = await claim_job(h, jid)
    files = FileDatabase(h.kernel)
    intent = await files.prepare_upload(claim, MANIFEST)
    before = await read(h, cid)
    async with h.migrator.begin() as blocker:
        await blocker.execute(
            text("SELECT 1 FROM app.channel_connections WHERE id=:id FOR UPDATE"),
            {"id": h.telegram_connection},
        )
        result = await asyncio.wait_for(
            files.finish_fetch(claim.job_id, claim.claim_token, intent.intent_id), 1.5
        )
    assert result.status == "READY"
    assert (await read(h, cid))["current_revision"] == before["current_revision"]
    assert (
        await scalar(
            h, "SELECT status FROM platform.file_object_uploads WHERE id=:i", i=intent.intent_id
        )
        == "WINNER"
    )
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    consume_claim = await work_for(h, turn, "TEST_CONSUME")
    snapshot = await worker(h, consume_claim, "SELECT platform.turn_execute(:job,:claim)")
    assert snapshot["schema_version"] == 3 and snapshot["readiness"] == "COMPLETE"
    assert snapshot["members"][0]["current"]["image_availability"] == "ORIGINAL_READY"
    expected = consumer_result(snapshot)
    assert expected["ready_file_count"] == 1 and expected["wait_expired_count"] == 0
    with pytest.raises(DBAPIError) as invalid_count:
        await worker(
            h,
            consume_claim,
            "SELECT platform.turn_consumer_finalize(:job,:claim,CAST(:result AS jsonb))",
            result=json.dumps(dict(expected, ready_file_count=0)),
        )
    assert sqlstate(invalid_count) == "P2001" and "INVALID_INPUT" in str(invalid_count.value)
    finished = await worker(
        h,
        consume_claim,
        "SELECT platform.turn_consumer_finalize(:job,:claim,CAST(:result AS jsonb))",
        result=json.dumps(expected),
    )
    assert finished["code"] == "OBSERVED"
    assert await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 1


async def insert_record(connection, table, record):
    schema, name = table.split(".")
    columns = (
        await connection.execute(
            text(
                "SELECT string_agg(quote_ident(column_name),',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema=:s AND table_name=:t AND is_generated='NEVER'"
            ),
            {"s": schema, "t": name},
        )
    ).scalar_one()
    await connection.execute(
        text(
            f"INSERT INTO {table}({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::{table},CAST(:r AS jsonb))"
        ),
        {"r": json.dumps(record)},
    )


async def test_compound_source_actor_audit_links_and_late_commit_rollback(native):
    h = native
    _, _, cid = await incoming(h)
    await policy(h)
    r = await reconcile(h, cid)
    _, _, tcid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    source = await incoming(h, 3, provider="TELEGRAM", sender=OWNER, value="Native observation")
    observation = await scalar(
        h,
        "SELECT human_context_observation_id FROM platform.telegram_provenance WHERE receipt_id=:s",
        s=source.receipt_id,
    )
    inbox = await scalar(
        h, "SELECT id FROM platform.inbox_events WHERE connection_id=:c LIMIT 1", c=CA
    )
    for mark, expected in ((observation, "23503"), (None, "23514")):
        with pytest.raises(DBAPIError) as mismatch:
            await query(
                h,
                "UPDATE platform.inbox_events SET human_context_source_receipt_id=:s,human_context_observation_id=:o WHERE id=:i RETURNING id",
                s=source.receipt_id,
                o=mark,
                i=inbox,
            )
        assert sqlstate(mismatch) == expected
    row = (
        await query(
            h,
            "SELECT to_jsonb(r) AS v FROM platform.human_context_reconciliations r WHERE id=:r",
            r=UUID(r["result"]["revision_id"]),
        )
    )[0]["v"]
    current = await read(h, cid)
    attempted = dict(
        row,
        id=str(uuid4()),
        idempotency_key=str(uuid4()),
        previous_revision_id=row["id"],
        revision_no=2,
        expected_context_version=int(current["context_version"]),
        accepted_context_version=int(current["context_version"]) + 1,
    )
    for fields, expected in (
        ({}, "23503"),
        ({"actor_user_account_id": str(PROVIDER)}, "23514"),
        ({"client_id": (await read(h, tcid))["client_id"]}, "23514"),
    ):
        with pytest.raises(DBAPIError) as rejected:
            async with h.migrator.begin() as c:
                await insert_record(
                    c, "platform.human_context_reconciliations", dict(attempted, **fields)
                )
        assert sqlstate(rejected) == expected
    # A late database failure is armed after the capability's statement has
    # otherwise succeeded. All ordinary constraints remain enabled throughout.
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "CREATE FUNCTION platform.test_native_commit_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.human_context_revision_id IS DISTINCT FROM OLD.human_context_revision_id THEN RAISE EXCEPTION 'forced native commit failure' USING ERRCODE='23514'; END IF; RETURN NULL; END $$"
            )
        )
        await c.execute(
            text(
                "CREATE CONSTRAINT TRIGGER test_native_commit_failure AFTER UPDATE ON app.conversations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION platform.test_native_commit_failure()"
            )
        )
    before = await legacy_exports(h)
    body = reconcile_body(
        await read(h, cid), value="Retry the same full replacement after rollback"
    )
    try:
        with pytest.raises(TenancyError) as late:
            async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
                accepted = (
                    await unit._execute(
                        "SELECT platform.human_context_reconcile(:c,'late-commit',CAST(:b AS jsonb))",
                        {"c": cid, "b": json.dumps(body)},
                    )
                ).scalar_one()
                assert accepted["outcome"] == "ACCEPTED"
        assert str(late.value) == "INVALID_STATE"  # trusted UOW redacts late SQLSTATE 23514
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text("DROP TRIGGER test_native_commit_failure ON app.conversations"))
            await c.execute(text("DROP FUNCTION platform.test_native_commit_failure()"))
    assert await legacy_exports(h) == before
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_reconciliations") == 1
    assert (await read(h, cid))["current_revision"]["revision_id"] == row["id"]
    accepted = await reconcile(h, cid, body=body, key="late-commit")
    assert accepted["result"]["revision_no"] == "2"
    assert (await reconcile(h, cid, body=body, key="late-commit"))["outcome"] == "REPLAY"


async def test_policy_audit_commit_failure_rolls_back_state_receipt_and_audit(native):
    h = native
    await policy(h)
    before = await legacy_exports(h)

    async def orphan_audit(c, result):
        # Negative uncommitted row only: native_consistent must reject an Audit
        # without its matching policy receipt when the outer COMMIT executes.
        a = (
            await c.execute(
                text("SELECT to_jsonb(a) FROM app.audit_events a WHERE audit_event_id=:id"),
                {"id": UUID(result["result"]["audit_event_id"])},
            )
        ).scalar_one()
        a["audit_event_id"] = str(uuid4())
        a["payload"]["receipt_id"] = str(uuid4())
        await insert_record(c, "app.audit_events", a)

    with pytest.raises(DBAPIError) as late:
        await policy(h, operation="PAUSE", key="policy-commit-retry", after_statement=orphan_audit)
    assert sqlstate(late) == "23514" and "missing native policy audit atom" in str(late.value)
    assert await legacy_exports(h) == before
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_policy_receipts") == 1
    retried = await policy(h, operation="PAUSE", key="policy-commit-retry")
    assert retried["result"]["accepted_policy"] == "PAUSED"
    assert (await policy(h, operation="PAUSE", key="policy-commit-retry", expected=("ON", 1)))[
        "outcome"
    ] == "REPLAY"


@pytest.mark.parametrize("order", ["policy_first", "admission_first"])
async def test_policy_admission_both_connection_lock_orders(native, order):
    from asm.conversations.guards import GUARD_TEXT

    h = native
    cid, _, _ = await activate(h)
    await incoming(h, 2)
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    claim = await work_for(h, turn, "GUARDED_TEXT")
    ready = asyncio.get_running_loop().create_future()
    release = asyncio.Event()

    async def paused(c, result):
        ready.set_result((await c.execute(text("SELECT pg_backend_pid()"))).scalar_one())
        await release.wait()

    if order == "policy_first":
        pausing = asyncio.create_task(policy(h, operation="PAUSE", after_statement=paused))
        policy_pid = await ready
        async with h.runtime.engine.begin() as c:
            pid = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await c.execute(
                text("SELECT platform.messaging_admit(:j,:t)"),
                {"j": claim.job_id, "t": claim.claim_token},
            )
            preparing = asyncio.create_task(
                c.execute(
                    text("SELECT platform.guard_turn_prepare(:j,:t)"),
                    {"j": claim.job_id, "t": claim.claim_token},
                )
            )
            await wait_blocked(h, pid, policy_pid)
            async with h.migrator.begin() as monitor:
                await monitor.execute(
                    text("SELECT 1 FROM app.conversations WHERE id=:c FOR NO KEY UPDATE NOWAIT"),
                    {"c": cid},
                )
            release.set()
            await pausing
            result = (await preparing).scalar_one()
    else:
        async with h.runtime.engine.begin() as c:
            pid = (await c.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            await c.execute(
                text("SELECT platform.messaging_admit(:j,:t)"),
                {"j": claim.job_id, "t": claim.claim_token},
            )
            snapshot = (
                await c.execute(
                    text("SELECT platform.guard_turn_prepare(:j,:t)"),
                    {"j": claim.job_id, "t": claim.claim_token},
                )
            ).scalar_one()
            assert snapshot["schema_version"] == 3
            pausing = asyncio.create_task(policy(h, operation="PAUSE", after_statement=paused))
            async with asyncio.timeout(1.5):
                while not await scalar(
                    h,
                    "SELECT EXISTS(SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid WHERE NOT l.granted AND :p=ANY(pg_blocking_pids(l.pid)) AND a.usename='asm_migrator')",
                    p=pid,
                ):
                    await asyncio.sleep(0.01)
            release.set()
        await pausing
        result = await worker(
            h,
            claim,
            "SELECT platform.guard_turn_accept(:job,:claim,:digest,:value)",
            digest=snapshot["snapshot_digest"],
            value=GUARD_TEXT,
        )
    assert result["code"] == "CONTEXT_HOLD" and result["reason"] == "CONTEXT_POLICY_PAUSED"
    assert await scalar(h, "SELECT count(*) FROM app.outbox_events") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0
    assert h.adapter.calls == 0


async def test_observation_epoch_max_rolls_back_real_ingress_atom(native):
    from asm.messaging.errors import MessagingError

    h = native
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    base = (await query(h, "SELECT to_jsonb(c) AS v FROM app.conversations c WHERE id=:c", c=cid))[
        0
    ]["v"]
    # New synthetic C with a targeted max-counter fault, using existing exact
    # workspace/connection/Client/identity keys. No native receipt is fabricated.
    broken = dict(
        base,
        id=str(uuid4()),
        provider_chat_id="900001",
        human_observation_epoch=9223372036854775807,
    )
    async with h.migrator.begin() as c:
        await insert_record(c, "app.conversations", broken)
    before = await legacy_exports(h)
    receipts = await scalar(h, "SELECT count(*) FROM platform.telegram_update_receipts")
    with pytest.raises((MessagingError, DBAPIError)) as exhausted:
        await TelegramIngress(h.kernel, BOT).ingest_update(
            raw(190001, 991, chat="900001", sender=OWNER, value="max N"), uuid4()
        )
    assert "VERSION_EXHAUSTED" in str(exhausted.value)
    assert await legacy_exports(h) == before
    assert await scalar(h, "SELECT count(*) FROM platform.telegram_update_receipts") == receipts
    assert await scalar(h, "SELECT count(*) FROM platform.human_context_observations") == 0


async def test_wait_rollback_running_expiry_recovery_preserves_same_budget(native):
    h = native
    cid, _, _ = await activate(h)
    claim, _, _ = await prepared(h, cid)
    duplicate = await duplicate_pending(h)
    before = await legacy_exports(h)
    with pytest.raises(RuntimeError, match="before wait commit"):
        async with h.runtime.engine.begin() as c:
            await c.execute(
                text("SELECT platform.messaging_admit(:j,:t)"),
                {"j": claim.job_id, "t": claim.claim_token},
            )
            saved = (
                await c.execute(
                    text("SELECT platform.guard_turn_prepare(:j,:t)"),
                    {"j": claim.job_id, "t": claim.claim_token},
                )
            ).scalar_one()
            assert saved["code"] == "CONTEXT_WAIT"
            raise RuntimeError("before wait commit")
    assert await legacy_exports(h) == before
    assert (
        await scalar(
            h,
            "SELECT context_wait_result FROM platform.messaging_jobs WHERE id=:id",
            id=claim.job_id,
        )
        is None
    )
    waited = await worker(h, claim, "SELECT platform.guard_turn_prepare(:job,:claim)")
    assert waited["code"] == "CONTEXT_WAIT"
    second = await claim_job(h, claim.job_id)
    first_started = await scalar(
        h, "SELECT first_started_at FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
    )
    # Shorten an actual RUNNING lease to model a crashed worker. This never
    # extends a lease or moves first_started_at / available_at to regain budget.
    await query(
        h,
        "UPDATE platform.messaging_jobs SET lease_until=clock_timestamp()-interval '1 millisecond' WHERE id=:id RETURNING id",
        id=second.job_id,
    )
    assert await h.kernel.recover_expired() >= 1
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:id", id=second.job_id))[
        0
    ]
    assert job["status"] == "READY" and job["context_block_reason"] == "CONTEXT_INPUT_PENDING"
    assert job["context_wait_claim_token"] is None and job["context_wait_result"] is None
    assert job["attempt_count"] == 2 and job["first_started_at"] == first_started
    assert job["last_attempt_id"] is None
    for old in (claim, second):
        with pytest.raises(DBAPIError) as stale:
            await replay(h, old)
        assert sqlstate(stale) == "P2001"
    assert (await h.kernel.process_inbox(await claim_job(h, duplicate.job_id))).code == "DUPLICATE"
    third = await claim_job(h, claim.job_id)
    assert third.attempt_count == 3
    assert (await worker(h, third, "SELECT platform.guard_turn_prepare(:job,:claim)"))[
        "schema_version"
    ] == 3
    assert (await read(h, cid))["automation_work"]["state"] == "IDLE"


async def test_catalog_constraint_index_and_rls_drift_fail_closed(native):
    h = native
    for mutation in (
        "DROP INDEX platform.native_inbox_pending_idx",
        "ALTER TABLE platform.human_context_policy_receipts DROP CONSTRAINT native_policy_receipt_transition_check",
        "ALTER TABLE platform.human_context_observations NO FORCE ROW LEVEL SECURITY",
        "ALTER FUNCTION platform.human_context_schema_profile() VOLATILE",
    ):
        async with h.migrator.connect() as c:
            tx = await c.begin()
            try:
                await c.execute(text(mutation))
                assert (
                    await c.execute(text("SELECT platform.human_context_schema_profile()"))
                ).scalar_one()["valid"] is False
            finally:
                await tx.rollback()
    assert (await scalar(h, "SELECT platform.human_context_schema_profile()"))["valid"] is True


async def test_policy_actual_login_guard_and_pause_after_real_test_expiry(native):
    h = native
    signature = "platform.human_context_policy_command(uuid,uuid,text,text,text,bigint,jsonb,jsonb)"
    async with h.migrator.begin() as c:
        await c.execute(text("GRANT EXECUTE ON FUNCTION " + signature + " TO asm_runtime"))
    try:
        with pytest.raises(DBAPIError) as login:
            async with h.runtime.engine.begin() as c:
                await c.execute(
                    text("SELECT set_config('asm.actor_kind','LOCAL_PROVISIONER',true)")
                )
                await c.execute(
                    text(
                        "SELECT platform.human_context_policy_command(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)"
                    )
                )
        assert sqlstate(login) == "P2601" and "ACCESS_DENIED" in str(login.value)
    finally:
        async with h.migrator.begin() as c:
            await c.execute(text("REVOKE EXECUTE ON FUNCTION " + signature + " FROM asm_runtime"))
    ws, business, connection = uuid4(), uuid4(), uuid4()
    until = datetime.now(UTC) + timedelta(seconds=3)
    async with h.migrator.begin() as c:
        await c.execute(text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": ws})
        await c.execute(
            text(
                "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:u,'OWNER')"
            ),
            {"ws": ws, "u": UA},
        )
        await c.execute(
            text("INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:b,'TEST expiry')"),
            {"ws": ws, "b": business},
        )
        await c.execute(
            text(
                "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) VALUES(:ws,:c,:b,'CONTROLLED','expiry-bot','expiry-connection')"
            ),
            {"ws": ws, "c": connection, "b": business},
        )
        await c.execute(
            text(
                "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) VALUES(:ws,:c,'CONTROLLED','expiry-bot','expiry-connection')"
            ),
            {"ws": ws, "c": connection},
        )
        assert (
            await c.execute(
                text(
                    "SELECT platform.initialize_local_messaging_billing(:ws,'Native expiry TEST',:start,:end)"
                ),
                {"ws": ws, "start": until - timedelta(days=1), "end": until},
            )
        ).scalar_one() == "CREATED"
    enabled = await policy(h, connection, key="expiry-enable", expected=("OFF_UNUSED", 0))
    await asyncio.sleep(max(0, (until - datetime.now(UTC)).total_seconds()) + 0.01)
    assert (await policy(h, connection, "PAUSE"))["result"]["accepted_policy"] == "PAUSED"
    assert (await policy(h, connection, key="expiry-enable", expected=("OFF_UNUSED", 0)))[
        "result"
    ] == enabled["result"]
    with pytest.raises(DBAPIError) as expired:
        await policy(h, connection)
    assert sqlstate(expired) == "P2601" and "POLICY_PREREQUISITE_FAILED" in str(expired.value)


async def native_exports(h):
    """All 45 table rows/columns plus the ingress sequence, before a rejected command."""
    result = {}
    for table, columns in migration().NATIVE_COLUMNS.items():
        rows = await query(
            h,
            "SELECT to_jsonb(r) AS v FROM (SELECT " + ",".join(columns) + " FROM " + table + ") r",
        )
        values = sorted(json.dumps(row["v"], sort_keys=True, separators=(",", ":")) for row in rows)
        result[table] = (len(values), hashlib.sha256("\n".join(values).encode()).hexdigest())
    result["platform.turn_ingress_seq"] = (
        await query(h, "SELECT last_value,is_called FROM platform.turn_ingress_seq")
    )[0]
    return result


async def resume_rejected_without_writes(h, cid, reason, *, actor=UA, stale=False):
    p = await read(h, cid)
    before = await native_exports(h)
    with pytest.raises(DBAPIError) as rejected:
        await owner(
            h,
            "SELECT platform.conversation_control_execute(:c,:client,'RESUME',:key,:g,:v)",
            actor=actor,
            c=cid,
            client=UUID(p["client_id"]),
            key=str(uuid4()),
            g=int(p["control_generation"]) - int(stale),
            v=int(p["context_version"]),
        )
    assert sqlstate(rejected) == "P2401" and reason in str(rejected.value)
    assert await native_exports(h) == before
    assert h.adapter.calls == 0 and not h.adapter.ledger.exists()


@pytest.mark.parametrize(
    "case", ["legacy_ai_missing_r", "on_ai_stale_r", "paused_ai_stale_r_pending"]
)
async def test_resume_semantic_priority_before_filtered_context_reasons(native, case):
    h = native
    if case == "legacy_ai_missing_r":
        _, _, cid = await incoming(h)
        unused_human = await read(h, cid)
        assert unused_human["policy"] == "OFF_UNUSED" and unused_human["control_mode"] == "HUMAN"
        assert unused_human["context_blockers"] == ["POLICY_INACTIVE"]
        assert unused_human["resume_blockers"] == []
        await control(h, cid)
        unused_ai = await read(h, cid)
        assert unused_ai["control_mode"] == "AI" and unused_ai["resume_blockers"] == []
        assert unused_ai["context_blockers"] == ["POLICY_INACTIVE"]
        await policy(h)
        expected_context = ["CONTEXT_CONFIRMATION_REQUIRED"]
        expected_resume = ["HUMAN_REQUIRED", *expected_context]
        expected_review = "BOOTSTRAP_REQUIRED"
    else:
        cid, _, _ = await activate(h)
        await policy(h, operation="PAUSE")
        await policy(h)  # P2 makes the legitimate R(P1) stale; no fixture UPDATE.
        expected_context = ["CONTEXT_CHANGED"]
        expected_resume = ["HUMAN_REQUIRED", *expected_context]
        expected_review = "CONFIRMATION_REQUIRED"
        if case == "paused_ai_stale_r_pending":
            await policy(h, operation="PAUSE")
            pending = await duplicate_pending(h, message=1)
            assert pending.job_id is not None
            expected_context = ["POLICY_PAUSED", "CONTEXT_CHANGED", "CONTEXT_INPUT_PENDING"]
            expected_resume = [
                "POLICY_PAUSED",
                "HUMAN_REQUIRED",
                "CONTEXT_CHANGED",
                "CONTEXT_INPUT_PENDING",
            ]
            expected_review = "POLICY_PAUSED"
    p = await read(h, cid)
    assert p["control_mode"] == "AI"
    assert p["context_blockers"] == expected_context and p["resume_blockers"] == expected_resume
    assert p["review_status"] == expected_review
    if case == "legacy_ai_missing_r":
        assert p["policy_epoch"] == "1" and p["current_revision"] is None
        assert p["pending_context_input"] is False
    reason = "CONTEXT_POLICY_PAUSED" if p["policy"] == "PAUSED" else "HUMAN_REQUIRED"
    await resume_rejected_without_writes(h, cid, reason)
    # Retained authority and CAS checks still win over native policy/HUMAN_REQUIRED.
    await resume_rejected_without_writes(h, cid, "ACCESS_DENIED", actor=PROVIDER, stale=True)
    await resume_rejected_without_writes(h, cid, "STALE_STATE", stale=True)
    await control(h, cid, "TAKEOVER")
    human = await read(h, cid)
    assert human["control_mode"] == "HUMAN"
    assert human["context_blockers"] == expected_context
    assert human["resume_blockers"] == expected_context
    assert human["review_status"] == expected_review


async def test_resume_new_observation_maps_to_confirmation_without_writes(native):
    h = native
    _, _, cid = await incoming(h, provider="TELEGRAM")
    await policy(h, h.telegram_connection)
    saved = await reconcile(h, cid)
    before = await read(h, cid)
    assert before["control_mode"] == "HUMAN" and before["policy"] == "ON"
    assert before["observation_epoch"] == "0" and before["resume_blockers"] == []
    assert before["current_revision"]["disposition"] == "OWNER_TEXT"
    observed = await incoming(
        h, 11, provider="TELEGRAM", sender=OWNER, process=False, value="Native owner agreement."
    )
    assert observed.job_id is None
    p = await read(h, cid)
    assert p["observation_epoch"] == "1" and p["pending_context_input"] is False
    for field in (
        "control_mode",
        "control_generation",
        "context_version",
        "ingress_checkpoint",
        "policy_epoch",
        "current_revision",
    ):
        assert p[field] == before[field], field
    assert p["current_revision"]["revision_id"] == saved["result"]["revision_id"]
    assert p["context_blockers"] == p["resume_blockers"] == ["NEW_OBSERVATION"]
    assert p["review_status"] == "NEW_OBSERVATION"
    reasons = await scalar(
        h,
        "SELECT jsonb_build_array(platform.human_context_reason(p,true),platform.human_context_reason(p,false)) FROM (SELECT platform.human_context_projection(:ws,:c,clock_timestamp()) AS p) q",
        ws=A,
        c=cid,
    )
    assert reasons == ["CONTEXT_CONFIRMATION_REQUIRED", "NEW_OBSERVATION"]
    await resume_rejected_without_writes(h, cid, "CONTEXT_CONFIRMATION_REQUIRED")


async def test_worker_new_observation_keeps_permanent_hold_reason(native):
    h = native
    cid, _, _ = await activate(h, provider="TELEGRAM")
    await incoming(h, 2, provider="TELEGRAM")
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    turn = await current_turn(h, cid)
    claim = await work_for(h, turn, "TEST_CONSUME")
    snapshot = await worker(h, claim, "SELECT platform.turn_execute(:job,:claim)")
    assert snapshot["schema_version"] == 3
    before = await read(h, cid)
    assert before["control_mode"] == "AI" and before["context_blockers"] == []
    observed = await incoming(
        h, 11, provider="TELEGRAM", sender=OWNER, process=False, value="Native owner changed terms."
    )
    assert observed.job_id is None
    p = await read(h, cid)
    assert p["observation_epoch"] == "1" and p["pending_context_input"] is False
    for field in (
        "context_version",
        "control_generation",
        "ingress_checkpoint",
        "current_revision",
    ):
        assert p[field] == before[field], field
    assert p["context_blockers"] == ["NEW_OBSERVATION"]
    held = await worker(h, claim, "SELECT platform.turn_execute(:job,:claim)")
    assert held["code"] == "CONTEXT_HOLD" and held["reason"] == "NEW_OBSERVATION"
    assert held["status"] == "DEAD" and held["job_id"] == str(claim.job_id)
    assert await replay(h, claim) == held
    job = (await query(h, "SELECT * FROM platform.messaging_jobs WHERE id=:j", j=claim.job_id))[0]
    assert job["status"] == "DEAD" and job["turn_outcome"] == "FAILED"
    assert job["context_block_reason"] == "NEW_OBSERVATION" and job["error_code"] == "NOT_ALLOWED"
    assert (
        job["context_wait_result"] == held and job["context_wait_claim_token"] == claim.claim_token
    )
    assert await scalar(h, "SELECT count(*) FROM app.outbox_events") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_guard_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM platform.turn_consumer_receipts") == 0
    assert await scalar(h, "SELECT count(*) FROM app.escalations") == 0
    assert h.adapter.calls == 0 and not h.adapter.ledger.exists()


async def native_manual_delivery_history(h):
    """Real capabilities; explicit transport outcomes are TEST seams, not provider I/O."""
    from asm.billing.validation import timestamp

    h.kernel = MessagingDatabase(h.runtime.engine, environment="TEST")
    _, _, cid = await incoming(h)
    await policy(h)
    expected = {}
    for status in ("SENT", "FAILED", "UNKNOWN", "PENDING", "DISPATCHING"):
        async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            manual = await unit.messaging_request_text(
                cid, "Manual history " + status, "utc6-history-" + status
            )
        outbox = UUID(manual["outbox_id"])
        if status != "PENDING":
            claim = await claim_job(
                h,
                await scalar(
                    h, "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id", id=outbox
                ),
            )
            permit = await h.kernel.begin_send(claim)
            assert permit.code == "PERMITTED"
            if status != "DISPATCHING":
                outcome = {
                    "SENT": SendOutcome(OutcomeKind.SUCCESS, "utc6-manual-sent"),
                    "FAILED": SendOutcome(
                        OutcomeKind.NOT_SENT_PERMANENT, error_code=Code.NOT_ALLOWED
                    ),
                    "UNKNOWN": SendOutcome(
                        OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT
                    ),
                }[status]
                finished = await h.kernel.finish_send(
                    claim.job_id, claim.claim_token, permit.attempt_id, outcome
                )
                assert finished.status == status
        row = (
            await query(
                h,
                "SELECT status,error_code,completed_at,version FROM app.outbox_events WHERE id=:id",
                id=outbox,
            )
        )[0]
        assert row["status"] == status
        # Expected text comes from the stored instant, never from normalizing or
        # re-signing a produced snapshot. No completed_at/state DML is used.
        expected[manual["message_id"]] = dict(
            status=row["status"],
            error_code=row["error_code"],
            completed_at=timestamp(row["completed_at"]) if row["completed_at"] else None,
            version=str(row["version"]),
        )
    await reconcile(h, cid)
    await control(h, cid)
    await incoming(h, 2, text="CONTROLLED ESCALATION TEST")
    turn = await current_turn(h, cid)
    await seal(h, turn["id"])
    return cid, await current_turn(h, cid), expected


async def native_worker_at_timezone(h, claim, sql, timezone):
    async with h.runtime.engine.begin() as c:
        await c.execute(text("SELECT set_config('TimeZone',:tz,true)"), {"tz": timezone})
        assert (await c.execute(text("SHOW TimeZone"))).scalar_one() == timezone
        await c.execute(
            text("SELECT platform.messaging_admit(:job,:claim)"),
            {"job": claim.job_id, "claim": claim.claim_token},
        )
        return (
            await c.execute(text(sql), {"job": claim.job_id, "claim": claim.claim_token})
        ).scalar_one()


@pytest.mark.parametrize("timezone", ["UTC", "Asia/Novosibirsk"])
async def test_completed_manual_delivery_history_utc6_before_v3_digest(native, timezone):
    from asm.conversations.guards import parse_guarded_snapshot
    from asm.conversations.turns import native_jsonb, parse_snapshot
    from asm.messaging.http_models import DeliveryResponse

    h = native
    cid, turn, expected = await native_manual_delivery_history(h)
    boxes_before = await query(h, "SELECT to_jsonb(o) AS v FROM app.outbox_events o ORDER BY id")
    async with h.migrator.begin() as c:
        await c.execute(text("SELECT set_config('TimeZone',:tz,true)"), {"tz": timezone})
        projection = (
            await c.execute(
                text("SELECT platform.human_context_projection(:ws,:cid,clock_timestamp())"),
                {"ws": A, "cid": cid},
            )
        ).scalar_one()
    sources = {"projection": projection["_recent_messages"]}
    for shape, step, sql, parse in (
        ("BASE", "TEST_CONSUME", "SELECT platform.turn_execute(:job,:claim)", parse_snapshot),
        (
            "GUARDED",
            "GUARDED_TEXT",
            "SELECT platform.guard_turn_prepare(:job,:claim)",
            parse_guarded_snapshot,
        ),
    ):
        claim = await work_for(h, turn, step)
        snapshot = await native_worker_at_timezone(h, claim, sql, timezone)
        assert snapshot["schema_version"] == 3
        body = {k: v for k, v in snapshot.items() if k not in ("code", "job_id")}
        assert (
            snapshot["snapshot_digest"]
            == hashlib.sha256(
                native_jsonb({k: v for k, v in body.items() if k != "snapshot_digest"})
            ).hexdigest()
        )
        before = json.dumps(snapshot, sort_keys=True)
        parsed = parse(snapshot)  # Strict current Python parser; no normalization/re-sign.
        assert json.dumps(snapshot, sort_keys=True) == before
        for message in parsed.recent_messages:
            if message.message_id in expected:
                assert message.delivery.model_dump(mode="json") == expected[message.message_id]
        assert (
            await scalar(
                h, "SELECT turn_input FROM platform.messaging_jobs WHERE id=:id", id=claim.job_id
            )
            == body
        )
        sources[shape] = snapshot["recent_messages"]
    claim = await work_for(h, turn, "ESCALATE_OWNER")
    escalated = await native_worker_at_timezone(
        h, claim, "SELECT platform.escalation_request_for_turn(:job,:claim)", timezone
    )
    assert escalated["code"] == "ESCALATED"
    escalation = await scalar(
        h,
        "SELECT request_snapshot FROM app.escalations WHERE id=:id",
        id=UUID(escalated["escalation_id"]),
    )
    assert (
        await scalar(
            h,
            "SELECT platform.human_context_snapshot_valid(CAST(:s AS jsonb),'ESCALATION')",
            s=json.dumps(escalation),
        )
        is True
    )
    sources["ESCALATION"] = escalation["recent_messages"]
    for shape, recent in sources.items():
        actual = {m["message_id"]: m["delivery"] for m in recent if m["message_id"] in expected}
        assert actual == expected, shape
        for delivery in actual.values():
            assert DeliveryResponse.model_validate(delivery).model_dump(mode="json") == delivery
    assert (
        await query(h, "SELECT to_jsonb(o) AS v FROM app.outbox_events o ORDER BY id")
        == boxes_before
    )
    assert h.adapter.calls == 0 and not h.adapter.ledger.exists()


@pytest.mark.parametrize("timezone", ["UTC", "Asia/Novosibirsk"])
async def test_recent_delivery_utc6_resigned_vectors_all_shapes(native, timezone):
    """Validator/serializer vectors only; no candidate is persisted as a receipt/permit."""
    import re

    from test_m3_1_native_context import snapshot as protocol_snapshot
    from test_m3_1_native_context_migrations import UTC6_INVALID_TIMESTAMPS, UTC6_VALID_TIMESTAMPS

    h = native
    module, _ = source_statements()
    projection = module.FUNCTIONS["platform.human_context_projection(uuid,uuid,timestamptz)"]
    expression = re.search(r"'completed_at',(to_char\(b.completed_at.*?\)),'version'", projection)[
        1
    ]
    signed_sql = text("""WITH body AS (SELECT CAST(:b AS jsonb)-'snapshot_digest' AS v), signed AS
      (SELECT CASE WHEN :shape='ESCALATION' THEN v ELSE v||jsonb_build_object(
        'snapshot_digest',encode(sha256(convert_to(v::text,'UTF8')),'hex')) END AS v FROM body)
      SELECT v AS body,platform.human_context_snapshot_valid(v,:shape) AS valid FROM signed""")
    async with h.migrator.begin() as c:
        await c.execute(text("SELECT set_config('TimeZone',:tz,true)"), {"tz": timezone})
        assert (await c.execute(text("SHOW TimeZone"))).scalar_one() == timezone
        # Evaluate the actual captured producer expression at deterministic zero/
        # fractional instants and NULL. This is not a fabricated stored delivery.
        for instant, expected in (
            (None, None),
            ("2030-01-01T07:00:00+07:00", "2030-01-01T00:00:00.000000Z"),
            ("2032-02-29T16:59:59.123400-07:00", "2032-02-29T23:59:59.123400Z"),
            ("2000-02-29T12:34:56.999999Z", "2000-02-29T12:34:56.999999Z"),
        ):
            assert (
                await c.execute(
                    text(
                        "SELECT "
                        + expression
                        + " FROM (SELECT CAST(:v AS timestamptz) AS completed_at) b"
                    ),
                    {"v": instant},
                )
            ).scalar_one() == expected
        for shape in ("BASE", "GUARDED", "ESCALATION"):
            value = protocol_snapshot(guarded=shape != "BASE")
            source_job = value.pop("job_id")
            value.pop("code")
            if shape == "ESCALATION":
                value.pop("consumer")
                value.pop("snapshot_digest")
                value.update(
                    source_job_id=source_job,
                    source_claim_token=str(uuid4()),
                    source_job_kind="PROCESS_TURN",
                    source_job_step="ESCALATE_OWNER",
                )
            value["recent_messages"] = [
                dict(
                    message_id=str(UUID(int=51)),
                    version="1",
                    direction="OUTBOUND",
                    origin="OWNER_MANUAL",
                    created_at=UTC6_VALID_TIMESTAMPS[0],
                    current=copy.deepcopy(value["members"][0]["current"]),
                    delivery={},
                    file=None,
                )
            ]

            async def valid(delivery):
                candidate = copy.deepcopy(value)
                candidate["recent_messages"][0]["delivery"] = delivery
                result = (
                    (await c.execute(signed_sql, {"b": json.dumps(candidate), "shape": shape}))
                    .mappings()
                    .one()
                )
                # BASE/GUARDED are fully re-signed by PG; ESCALATION has the
                # contract's closed unsigned request shape, never an extra key.
                assert ("snapshot_digest" in result["body"]) == (shape != "ESCALATION")
                return result["valid"]

            delivery = dict(status="SENT", error_code=None, completed_at=None, version="2")
            for moment in UTC6_VALID_TIMESTAMPS:
                assert await valid(dict(delivery, completed_at=moment)) is True, (shape, moment)
            for moment in UTC6_INVALID_TIMESTAMPS:
                assert await valid(dict(delivery, completed_at=moment)) is False, (shape, moment)
            for status, error in (
                ("PENDING", None),
                ("PENDING", "DEPENDENCY_TIMEOUT"),
                ("DISPATCHING", None),
                ("SENT", None),
                ("FAILED", "NOT_ALLOWED"),
                ("UNKNOWN", "UNKNOWN_EXTERNAL_RESULT"),
            ):
                completed = status in ("SENT", "FAILED", "UNKNOWN")
                current = dict(
                    delivery,
                    status=status,
                    error_code=error,
                    completed_at=UTC6_VALID_TIMESTAMPS[0] if completed else None,
                )
                assert await valid(current) is True, (shape, status)
                assert (
                    await valid(
                        dict(current, completed_at=None if completed else UTC6_VALID_TIMESTAMPS[0])
                    )
                    is False
                ), (shape, status)
            for change in (
                dict(status="FAILED"),
                dict(status="UNKNOWN"),
                dict(error_code="NOT_ALLOWED"),
                dict(error_code="BOGUS"),
                dict(error_code=True),
                dict(status=None),
                dict(status="BOGUS"),
                dict(version=2),
                dict(version=True),
                dict(version="02"),
                dict(extra=True),
            ):
                assert (
                    await valid(dict(delivery, completed_at=UTC6_VALID_TIMESTAMPS[0]) | change)
                    is False
                ), (shape, change)
            assert await valid({k: v for k, v in delivery.items() if k != "completed_at"}) is False
