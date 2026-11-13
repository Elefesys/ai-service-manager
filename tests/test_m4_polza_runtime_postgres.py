"""Owned PG18 provider admission; real Polza codec and worker, HTTP mocks only."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from asm.foundation import RuntimeDatabase, Settings, create_worker
from asm.messaging.errors import MessagingError
from asm.messaging.worker import Worker
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
from generic_pg_schema import assert_current_schema
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_m2_1_postgres import command as manual_command
from test_m2_1_postgres import query
from test_m2_3_db_postgres import BOT, EXTERNAL, OWNER
from test_m3_1_native_context_postgres import claim_job, incoming, migrate, scalar
from test_m3_1_turns_postgres import seal
from test_m4_delivery_postgres import (
    enrollment,
    refresh_synthetic_observation,
    run_turn,
    source_turn,
)
from test_m4_polza import KEY
from test_m4_polza_runtime import Wire, settings
from test_m4_runtime_postgres import COUNTER, owner
from test_m4_runtime_postgres import pg as pg
from test_tenancy_postgres import B

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def provider_pg(pg):
    await migrate("upgrade", "0015")
    await migrate("upgrade", "0019")
    await migrate("upgrade", "0019")
    pg.schema_revision = "0019"
    runtime = RuntimeDatabase(Settings())
    try:
        await runtime.check()
        await migrate("downgrade", "0015")
        with pytest.raises(RuntimeError, match="schema"):
            await runtime.check()
        await migrate("upgrade", "0019")
        await runtime.check()
        yield pg
    finally:
        await runtime.close()


async def command(h, cfg, enable=True):
    p = cfg.admission() if enable else {"session_id": str(cfg.session_id)}
    async with h.migrator.begin() as c:
        return (
            await c.execute(
                text("SELECT platform.ai_provider_session(CAST(:p AS jsonb),:enabled)"),
                {"p": json.dumps(p), "enabled": enable},
            )
        ).scalar_one()


async def admission_settings(h, prompt_revision):
    """Real trusted Telegram scope, operator DTO only; no model or HTTP client."""
    cid, _, _ = await source_turn(h, telegram=True)
    row = (await query(h, "SELECT * FROM app.conversations WHERE id=:id", id=cid))[0]
    return settings(
        prompt_revision=prompt_revision,
        data_profile="SYNTHETIC_PUBLISHED_KNOWLEDGE_V1"
        if prompt_revision == "conversation_v3"
        else "SYNTHETIC_TEXT_V1",
        workspace_id=row["workspace_id"],
        connection_id=row["connection_id"],
        client_id=row["client_id"],
        conversation_id=cid,
        chat_id=row["provider_chat_id"],
        bot_identity=BOT,
    )


@pytest.mark.parametrize("prompt_revision", ["conversation_v2", "conversation_v3"])
async def test_versioned_provider_admission_keeps_closed_operator_shape_without_wire(
    provider_pg, prompt_revision
):
    h = provider_pg
    cfg = await admission_settings(h, prompt_revision)
    payload = cfg.admission()
    assert "prompt_revision" not in payload
    assert payload["config"]["prompt_revision"] == prompt_revision
    assert len(payload) == 15
    before = (h.adapter.calls, h.adapter.effects)
    assert await command(h, cfg) == {"code": "ENABLED"}
    try:
        assert await command(h, cfg) == {"code": "ALREADY_ENABLED"}
        stored = (
            await query(
                h,
                "SELECT data_profile,config FROM platform.ai_provider_sessions WHERE id=:id",
                id=cfg.session_id,
            )
        )[0]
        assert stored["data_profile"] == payload["data_profile"]
        assert stored["config"] == payload["config"]
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.ai_deliveries WHERE provider_session_id=:id",
                id=cfg.session_id,
            )
            == 0
        )
        assert (h.adapter.calls, h.adapter.effects) == before
    finally:
        assert await command(h, cfg, enable=False) == {"code": "DISABLED"}


@pytest.mark.parametrize(
    "variant",
    [
        "missing_nested_prompt",
        "missing_data_profile",
        "mismatched_profile",
        "mismatched_prompt",
        "v3_extra_top_prompt",
        "v3_unknown_field",
        "v2_extra_top_prompt",
    ],
)
async def test_provider_admission_rejects_missing_mismatched_or_extra_version_fields_without_effect(
    provider_pg, variant
):
    h = provider_pg
    cfg = await admission_settings(
        h, "conversation_v2" if variant == "v2_extra_top_prompt" else "conversation_v3"
    )
    payload = cfg.admission()
    if variant == "missing_nested_prompt":
        payload["config"].pop("prompt_revision")
    elif variant == "missing_data_profile":
        payload.pop("data_profile")
    elif variant == "mismatched_profile":
        payload["data_profile"] = "SYNTHETIC_TEXT_V1"
    elif variant == "mismatched_prompt":
        payload["config"]["prompt_revision"] = "conversation_v2"
    elif variant == "v3_unknown_field":
        payload["foreign_business_id"] = str(uuid4())
    else:
        payload["prompt_revision"] = cfg.prompt_revision
    before = (h.adapter.calls, h.adapter.effects)
    with pytest.raises(DBAPIError) as caught:
        async with h.migrator.begin() as c:
            await c.execute(
                text("SELECT platform.ai_provider_session(CAST(:p AS jsonb),true)"),
                {"p": json.dumps(payload)},
            )
    assert caught.value.orig.sqlstate == "P2001"
    assert caught.value.orig.diag.message_primary == "NOT_ALLOWED"
    assert (
        await scalar(
            h, "SELECT count(*) FROM platform.ai_provider_sessions WHERE id=:id", id=cfg.session_id
        )
        == 0
    )
    assert (
        await scalar(
            h,
            "SELECT count(*) FROM platform.ai_deliveries WHERE provider_session_id=:id",
            id=cfg.session_id,
        )
        == 0
    )
    assert (h.adapter.calls, h.adapter.effects) == before


async def setup(
    h,
    tmp_path,
    *,
    kind="reply",
    read=False,
    failure=None,
    send_unknown=False,
    max_calls=4,
    rights=True,
    observe_hook=None,
):
    cid, source, scope = await source_turn(h, telegram=True)
    await refresh_synthetic_observation(h, cid)
    row = (await query(h, "SELECT * FROM app.conversations WHERE id=:id", id=cid))[0]
    cfg = settings(
        prompt_revision="conversation_v3",
        data_profile="SYNTHETIC_PUBLISHED_KNOWLEDGE_V1",
        workspace_id=row["workspace_id"],
        connection_id=row["connection_id"],
        client_id=row["client_id"],
        conversation_id=cid,
        chat_id=row["provider_chat_id"],
        bot_identity=BOT,
        max_calls=max_calls,
    )
    wire = Wire(kind, read=read, failure=failure)
    requests = []

    async def telegram_http(request):
        method = request.url.path.rsplit("/", 1)[-1]
        requests.append(method)
        body = json.loads(request.content)
        if method == "getBusinessConnection":
            if observe_hook is not None:
                await observe_hook()
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "id": EXTERNAL,
                        "user": {"id": int(OWNER), "is_bot": False},
                        "user_chat_id": int(OWNER),
                        "date": 1789990000,
                        "is_enabled": True,
                        "rights": {"can_reply": rights},
                    },
                },
            )
        assert method == "sendMessage"
        if send_unknown:
            raise httpx.ReadTimeout("controlled unknown send")
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 8899,
                    "chat": {"id": int(body["chat_id"]), "type": "private"},
                    "date": int(datetime.now(UTC).timestamp()),
                    "text": body["text"],
                    "business_connection_id": EXTERNAL,
                },
            },
        )

    telegram = TelegramClient(
        TelegramSettings(
            ASM_ENVIRONMENT="TEST",
            ASM_TELEGRAM_ENABLED=True,
            TG_BOT_TOKEN=BOT + ":synthetic_token_123456789",
            TG_WEBHOOK_SECRET="synthetic_webhook_secret_123",
            ASM_TELEGRAM_EXPECTED_BOT_ID=BOT,
            ASM_TELEGRAM_WEBHOOK_URL="https://test.invalid/webhooks/telegram",
        ),
        transport=httpx.MockTransport(telegram_http),
        provider_runtime=cfg,
    )
    key = tmp_path / "private-key"
    key.write_text(KEY.get_secret_value())
    key.chmod(0o600)
    worker = create_worker(
        h.kernel,
        h.adapter,
        environment="TEST",
        provider_settings=cfg,
        provider_key_file=key,
        provider_transport=httpx.MockTransport(wire),
        ai_telegram=telegram,
    )
    assert (await command(h, cfg))["code"] == "ENABLED"
    return cfg, worker, wire, requests, source, scope


@pytest.mark.parametrize(
    "kind,read", [("reply", False), ("reply", True), ("handoff", False), ("no_reply", False)]
)
async def test_provider_end_to_end_and_exact_replay(provider_pg, tmp_path, kind, read):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path, kind=kind, read=read)
    try:
        claim, d = await run_turn(h, worker, source)
        assert d["selected_kind"] == kind and d["provider_session_id"] == cfg.session_id
        await worker.execute(claim)
        assert len(wire.posts) == 1 + read
        calls = await query(
            h,
            "SELECT p.* FROM platform.ai_provider_calls p JOIN platform.ai_runs r ON (r.workspace_id,r.id)=(p.workspace_id,p.run_id) WHERE r.job_id=:id",
            id=claim.job_id,
        )
        assert len(calls) == 1 + read and all(c["completed_at"] for c in calls)
        if kind == "reply":
            send = await claim_job(h, d["send_job_id"])
            await worker.execute(send)
            assert requests == ["getBusinessConnection", "getBusinessConnection", "sendMessage"]
            assert (
                await scalar(
                    h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"]
                )
                == "SENT"
            )
        else:
            assert d["outbox_id"] is None and not requests
    finally:
        await worker.ai.telegram.aclose()


@pytest.mark.parametrize("phase", ["before_model", "before_send"])
async def test_disabled_session_refuses_new_external_admission(provider_pg, tmp_path, phase):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    try:
        if phase == "before_model":
            await command(h, cfg, False)
            with pytest.raises(MessagingError):
                await worker.execute(source)
            assert not wire.posts
        else:
            _, d = await run_turn(h, worker, source)
            await command(h, cfg, False)
            send = await claim_job(h, d["send_job_id"])
            with pytest.raises(MessagingError):
                await worker.execute(send)
        assert requests == ([] if phase == "before_model" else ["getBusinessConnection"])
    finally:
        await worker.ai.telegram.aclose()


@pytest.mark.parametrize("foreign", ["tenant", "chat"])
async def test_server_binding_rejects_foreign_scope(provider_pg, tmp_path, foreign):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    try:
        _, other, _ = (
            await source_turn(h, workspace=B)
            if foreign == "tenant"
            else await source_turn(h, telegram=True)
        )
        with pytest.raises(MessagingError):
            await worker.execute(other)
        assert not wire.posts and not requests
        assert not await query(
            h, "SELECT * FROM platform.ai_deliveries WHERE source_job_id=:id", id=other.job_id
        )
    finally:
        await worker.ai.telegram.aclose()


@pytest.mark.parametrize("change", ["takeover", "new_inbound", "native_owner", "manual_parallel"])
async def test_wait_releases_transactions_and_invalidates_stale_candidate(
    provider_pg, tmp_path, change
):
    h = provider_pg
    cfg, worker, wire, requests, source, scope = await setup(h, tmp_path)
    wire.wait = True
    await worker.execute(source)
    d = await enrollment(h, source)
    claim = await h.kernel.claim_job("provider-ai", ai=True)
    assert claim.job_id == d["job_id"]
    task = asyncio.create_task(worker.execute(claim))
    try:
        await asyncio.wait_for(wire.started.wait(), 5)
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.ai_provider_calls WHERE run_id=(SELECT id FROM platform.ai_runs WHERE job_id=:id)",
                id=claim.job_id,
            )
            == 1
        )
        if change == "takeover":
            await asyncio.wait_for(owner(h, cfg.conversation_id, "TAKEOVER"), 5)
        elif change == "new_inbound":
            await asyncio.wait_for(incoming(h, next(COUNTER), **scope), 5)
        elif change == "native_owner":
            await asyncio.wait_for(incoming(h, next(COUNTER), **(scope | {"sender": OWNER})), 5)
        else:
            _, _, other = await asyncio.wait_for(
                incoming(
                    h,
                    next(COUNTER),
                    chat_id="polza-manual-parallel",
                    external_connection_id="conn-a2",
                ),
                5,
            )
            result = await asyncio.wait_for(manual_command(h, other, key=str(uuid4())), 5)
            jid = await scalar(
                h, "SELECT id FROM platform.messaging_jobs WHERE outbox_id=:id", id=result.outbox_id
            )
            await asyncio.wait_for(Worker(h.kernel, h.adapter).execute(await claim_job(h, jid)), 5)
            assert (
                await scalar(
                    h, "SELECT status FROM app.outbox_events WHERE id=:id", id=result.outbox_id
                )
                == "SENT"
            )
            assert not task.done()
        wire.release.set()
        await asyncio.wait_for(task, 10)
        assert (await enrollment(h, source))["selected_kind"] == (
            "reply" if change == "manual_parallel" else None
        )
        assert len(wire.posts) == 1
        assert requests == (["getBusinessConnection"] if change == "manual_parallel" else [])
    finally:
        wire.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await worker.ai.telegram.aclose()


async def test_telegram_unknown_is_durable_and_never_resent(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path, send_unknown=True)
    try:
        claim, d = await run_turn(h, worker, source)
        send = await claim_job(h, d["send_job_id"])
        await worker.execute(send)
        assert (
            await scalar(h, "SELECT status FROM app.outbox_events WHERE id=:id", id=d["outbox_id"])
            == "UNKNOWN"
        )
        await worker.execute(claim)
        await h.kernel.recover_expired()
        assert len(wire.posts) == 1 and requests.count("sendMessage") == 1
        with pytest.raises(DBAPIError):
            async with h.migrator.begin() as c:
                # Actual rollback guard executes before any DDL on a used session.
                from pathlib import Path

                from scripts.native_context_db_catalog import capture_source

                mods, _ = capture_source(Path("."), "0019")
                statements = []
                mods["0016"]["op"].execute = statements.append
                mods["0016"]["downgrade"]()
                for sql in statements:
                    await c.execute(text(sql))
        assert await scalar(h, "SELECT version_num FROM platform.alembic_version") == "0019"
    finally:
        await worker.ai.telegram.aclose()


async def next_source(h, cfg, scope):
    await incoming(h, next(COUNTER), **scope)
    tid = await scalar(
        h,
        "SELECT id FROM app.conversation_turns WHERE workspace_id=:ws AND conversation_id=:cid ORDER BY first_ingress_at DESC,id DESC LIMIT 1",
        ws=cfg.workspace_id,
        cid=cfg.conversation_id,
    )
    sealed = await seal(h, tid)
    jid = await scalar(
        h,
        "SELECT id FROM platform.messaging_jobs WHERE workspace_id=:ws AND turn_id=:tid AND turn_revision=:revision AND step='TEST_CONSUME'",
        ws=cfg.workspace_id,
        tid=tid,
        revision=sealed.turn_revision,
    )
    return await claim_job(h, jid)


async def test_unknown_reservation_and_call_cap_survive_restart(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, scope = await setup(
        h, tmp_path, failure="metadata", max_calls=1
    )
    try:
        claim, d = await run_turn(h, worker, source)
        assert d["selected_kind"] is None and len(wire.posts) == 1
        row = (
            await query(
                h,
                "SELECT p.completion,r.cost_reserved FROM platform.ai_provider_calls p JOIN platform.ai_runs r ON (r.workspace_id,r.id)=(p.workspace_id,p.run_id) WHERE r.job_id=:id",
                id=claim.job_id,
            )
        )[0]
        assert row["completion"]["kind"] == "UNKNOWN" and row["cost_reserved"] > 0
        # Exact enable replay cannot clear a reservation or increase the finite cap.
        assert (await command(h, cfg))["code"] == "ALREADY_ENABLED"
        restarted = create_worker(
            h.kernel,
            h.adapter,
            environment="TEST",
            provider_settings=cfg,
            provider_key_file=tmp_path / "private-key",
            provider_transport=httpx.MockTransport(wire),
            ai_telegram=worker.ai.telegram,
        )
        await restarted.execute(claim)
        next_claim = await next_source(h, cfg, scope)
        _, next_delivery = await run_turn(h, restarted, next_claim)
        assert next_delivery["selected_kind"] is None and len(wire.posts) == 1 and not requests
    finally:
        await worker.ai.telegram.aclose()


async def test_committed_result_lost_ack_never_regenerates(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    losses = 0

    async def lost(name):
        nonlocal losses
        if name == "ai_reply_after_commit" and losses == 0:
            losses += 1
            raise SQLAlchemyError("CONTROLLED COMMIT ACK LOSS")

    h.kernel._barrier = lost
    try:
        claim, d = await run_turn(h, worker, source)
        assert d["selected_kind"] == "reply" and losses == len(wire.posts) == 1
        await worker.execute(claim)
        assert (
            await enrollment(h, source) == d
            and len(wire.posts) == 1
            and requests == ["getBusinessConnection"]
        )
    finally:
        h.kernel._barrier = None
        await worker.ai.telegram.aclose()


async def test_concurrent_enrollment_and_provider_client_cannot_cross_session(
    provider_pg, tmp_path
):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    try:
        await asyncio.gather(worker.execute(source), worker.execute(source))
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM platform.ai_deliveries WHERE source_job_id=:id",
                id=source.job_id,
            )
            == 1
        )
        assert not wire.posts and not requests
        # Finish this test's enrolled AI job through the worker so a later test
        # cannot claim it. The two source-claim replays still made one enrollment.
        claim = await h.kernel.claim_job("provider-enrollment", ai=True)
        assert claim.job_id == (await enrollment(h, source))["job_id"]
        await worker.execute(claim)
        assert len(wire.posts) == 1 and requests == ["getBusinessConnection"]
        # A separate client identity in the same tenant is still outside the binding.
        _, other, _ = await source_turn(h, telegram=True)
        with pytest.raises(MessagingError):
            await worker.execute(other)
        assert len(wire.posts) == 1 and requests == ["getBusinessConnection"]
    finally:
        await worker.ai.telegram.aclose()


@pytest.mark.parametrize(
    "field",
    ["workspace_id", "client_id", "connection_id", "conversation_id", "chat_id", "bot_identity"],
)
async def test_operator_binding_requires_exact_server_tuple(provider_pg, tmp_path, field):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    try:
        proposed = cfg.admission()
        proposed[field] = "99999999" if field in {"chat_id", "bot_identity"} else str(uuid4())
        with pytest.raises(DBAPIError):
            async with h.migrator.begin() as c:
                await c.execute(
                    text("SELECT platform.ai_provider_session(CAST(:p AS jsonb),true)"),
                    {"p": json.dumps(proposed)},
                )
        assert not wire.posts and not requests
    finally:
        await worker.ai.telegram.aclose()


async def test_server_expiry_cannot_be_bypassed_by_loaded_configuration(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    try:
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "UPDATE platform.ai_provider_sessions SET expires_at=clock_timestamp()-interval '1 millisecond' WHERE id=:id"
                ),
                {"id": cfg.session_id},
            )
        with pytest.raises(MessagingError):
            await worker.execute(source)
        assert not wire.posts and not requests
    finally:
        await worker.ai.telegram.aclose()


async def test_uncertain_inflight_call_cannot_be_restarted_in_parallel(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, _ = await setup(h, tmp_path)
    wire.wait = True
    await worker.execute(source)
    d = await enrollment(h, source)
    claim = await h.kernel.claim_job("provider-inflight", ai=True)
    assert claim.job_id == d["job_id"]
    first = asyncio.create_task(worker.execute(claim))
    try:
        await asyncio.wait_for(wire.started.wait(), 5)
        await asyncio.wait_for(worker.execute(claim), 5)
        assert len(wire.posts) == 1 and not requests
        wire.release.set()
        await asyncio.wait_for(first, 10)
        assert len(wire.posts) == 1 and not requests
        assert (
            await scalar(
                h, "SELECT calls_used FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id
            )
            == 1
        )
    finally:
        wire.release.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await worker.ai.telegram.aclose()


async def test_tariff_overrun_stops_session_without_resetting_reserved_rub(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, scope = await setup(h, tmp_path, failure="cost")
    try:
        claim, d = await run_turn(h, worker, source)
        assert d["selected_kind"] is None and len(wire.posts) == 1
        second = await next_source(h, cfg, scope)
        _, d2 = await run_turn(h, worker, second)
        assert d2["selected_kind"] is None and len(wire.posts) == 1 and not requests
        assert (
            await scalar(
                h, "SELECT cost_reserved FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id
            )
            > 0
        )
    finally:
        await worker.ai.telegram.aclose()


async def test_runtime_role_cannot_read_or_enable_provider_sessions(provider_pg):
    h = provider_pg
    assert await scalar(h, "SELECT to_regclass('platform.ai_provider_sessions')") is not None
    for statement in (
        "SELECT * FROM platform.ai_provider_sessions",
        "SELECT platform.ai_provider_session('{}'::jsonb,false)",
    ):
        with pytest.raises(DBAPIError) as failure:
            async with h.runtime.engine.begin() as c:
                await c.execute(text(statement))
        assert failure.value.orig.sqlstate == "42501"


async def test_current_provider_verifier_rejects_public_execute_grant(provider_pg):
    async with provider_pg.migrator.connect() as c:
        transaction = await c.begin()
        try:
            await c.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION platform.business_configuration_schema_profile() TO PUBLIC"
                )
            )
            with pytest.raises(Exception) as caught:
                await assert_current_schema(c)
            assert type(caught.value).__name__ in {"AssertionError", "Refusal"}
        finally:
            await transaction.rollback()
    async with provider_pg.migrator.begin() as c:
        await assert_current_schema(c)


async def test_confirmed_call_cap_survives_worker_restart(provider_pg, tmp_path):
    h = provider_pg
    cfg, worker, wire, requests, source, scope = await setup(h, tmp_path, max_calls=1)
    try:
        first, delivery = await run_turn(h, worker, source)
        assert delivery["selected_kind"] == "reply" and len(wire.posts) == 1
        call = (
            await query(
                h,
                "SELECT p.completion FROM platform.ai_provider_calls p JOIN platform.ai_runs r ON (r.workspace_id,r.id)=(p.workspace_id,p.run_id) WHERE r.job_id=:id",
                id=first.job_id,
            )
        )[0]["completion"]
        assert call["kind"] == "OUTPUT" and call["cost"]["status"] == "CONFIRMED"
        assert (await command(h, cfg))["code"] == "ALREADY_ENABLED"
        restarted = create_worker(
            h.kernel,
            h.adapter,
            environment="TEST",
            provider_settings=cfg,
            provider_key_file=tmp_path / "private-key",
            provider_transport=httpx.MockTransport(wire),
            ai_telegram=worker.ai.telegram,
        )
        await restarted.execute(first)
        _, second = await run_turn(h, restarted, await next_source(h, cfg, scope))
        assert (
            second["selected_kind"] is None
            and len(wire.posts) == 1
            and requests == ["getBusinessConnection"]
        )
    finally:
        await worker.ai.telegram.aclose()


@pytest.mark.parametrize("fault", ["revoked", "session", "context", "connection"])
async def test_precommit_observation_refusal_keeps_confirmed_cost_and_reservation(
    provider_pg, tmp_path, fault
):
    h = provider_pg

    async def during_http():
        assert (
            await scalar(
                h,
                "SELECT count(*) FROM pg_stat_activity WHERE usename='asm_runtime' AND state='idle in transaction'",
            )
            == 0
        )
        if fault == "session":
            await command(h, cfg, False)
        elif fault == "context":
            await incoming(h, next(COUNTER), **scope)
        elif fault == "connection":
            # A trusted concurrent lifecycle invalidates the original probe.
            await scalar(
                h,
                "UPDATE platform.telegram_connection_state SET generation=generation+1,observation_version=observation_version+1 WHERE connection_id=:id RETURNING connection_id",
                id=cfg.connection_id,
            )

    cfg, worker, wire, requests, source, scope = await setup(
        h, tmp_path, rights=fault != "revoked", observe_hook=during_http
    )
    try:
        claim, d = await run_turn(h, worker, source)
        assert d["selected_kind"] is None and d["outbox_id"] is None
        assert len(wire.posts) == 1 and requests == ["getBusinessConnection"]
        run = (await query(h, "SELECT * FROM platform.ai_runs WHERE job_id=:id", id=claim.job_id))[
            0
        ]
        calls = await query(
            h, "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"]
        )
        assert len(calls) == run["calls_used"] == 1 and run["result"] is None
        assert (
            run["cost_reserved"] > 0
            and Decimal(calls[0]["budget"]["cost_reserved"]) == run["cost_reserved"]
        )
        assert calls[0]["completion"]["kind"] == "OUTPUT"
        assert calls[0]["completion"]["cost"]["status"] == "CONFIRMED"
        if fault == "revoked":
            state = (
                await query(
                    h,
                    "SELECT * FROM platform.telegram_connection_state WHERE connection_id=:id",
                    id=cfg.connection_id,
                )
            )[0]
            assert state["can_reply"] is False and state["error_code"] is None
        await worker.execute(claim)
        assert len(wire.posts) == 1 and requests == ["getBusinessConnection"]
        assert (
            await query(
                h, "SELECT * FROM platform.ai_provider_calls WHERE run_id=:id", id=run["id"]
            )
        ) == calls
    finally:
        await worker.ai.telegram.aclose()
