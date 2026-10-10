"""A01–A09: real runtime PostgreSQL, real HTTP effects and private S3, no wire mocks."""

import asyncio
import hashlib
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from asm.auth.http import install_auth
from asm.files.database import FileDatabase
from asm.files.transfer import FetchTransfer
from asm.messaging.commands import request_manual_text
from asm.messaging.database import MessagingDatabase
from asm.messaging.worker import Worker
from asm.telegram.client import TelegramClient
from asm.telegram.database import TelegramIngress
from asm.telegram.normalization import normalize_update, update_fingerprint
from asm.telegram.webhook import install_webhook
from asm.tenancy import AuthenticatedAccount
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_m2_1_postgres import cleanup, delivery, expire, finish_text_turns, query
from test_m2_1_postgres import messaging as messaging
from test_m2_2_storage_postgres import image_bytes
from test_m2_2_storage_postgres import images as images
from test_m2_2_storage_postgres import request as private_request
from test_m2_3_transport import (
    BOT,
    CHAT,
    EXTERNAL,
    OWNER,
    SECRET,
    TOKEN,
    business_connection,
    config,
    update,
)
from test_telegram_connect_budget import connect_tls_material as connect_tls_material
from test_telegram_connect_budget import (
    elapsed_timeout,
    released,
    tls_client,
    tls_peer,
)
from test_tenancy_postgres import BA, UA, A
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def telegram_case(messaging):
    h = messaging
    async with h.migrator.begin() as c:
        observation = dict(
            bot_identity=str(BOT),
            external_connection_id=EXTERNAL,
            owner_user_id=str(OWNER),
            is_enabled=True,
            can_reply=True,
            error_code=None,
        )
        binding = (
            await c.execute(
                text(
                    "SELECT platform.initialize_telegram_connection(:ws,:business,:bot,:external,:owner,CAST(:obs AS jsonb))"
                ),
                dict(
                    ws=A,
                    business=BA,
                    bot=str(BOT),
                    external=EXTERNAL,
                    owner=str(OWNER),
                    obs=json.dumps(observation),
                ),
            )
        ).scalar_one()
        h.telegram_connection = UUID(binding["connection_id"])
        await c.execute(
            text(
                "SELECT platform.initialize_local_messaging_billing(:ws,'Telegram TEST','2000-01-01T00:00:00Z','2100-01-01T00:00:00Z')"
            ),
            dict(ws=A),
        )
    h.ingress = TelegramIngress(h.kernel, str(BOT))
    try:
        yield h
    finally:
        # Unbound ignored receipts have no Workspace; delete only this TEST bot.
        async with h.migrator.begin() as c:
            await c.execute(
                text("DELETE FROM platform.telegram_update_receipts WHERE bot_identity=:bot"),
                dict(bot=str(BOT)),
            )
        await cleanup(h.migrator)
        async with h.migrator.begin() as c:
            for table in (
                "platform.billing_contact_command_receipts",
                "app.audit_events",
                "platform.workspace_service_modes",
                "platform.workspace_subscriptions",
                "platform.workspace_billing_accounts",
            ):
                await c.execute(text(f"DELETE FROM {table} WHERE workspace_id=:ws"), dict(ws=A))


async def inbound(h, raw=None):
    receipt = await h.ingress.ingest(normalize_update(str(BOT), raw or update()), uuid4())
    assert await h.worker.run_once()
    rows = await query(
        h, "SELECT * FROM app.conversations WHERE connection_id=:id", id=h.telegram_connection
    )
    return receipt, rows[0]["id"]


@asynccontextmanager
async def wire_server(
    tmp_path, *, disconnect_send=False, trickle_send=False, content=None, inspect=None
):
    ledger = tmp_path / "wire-calls.jsonl"
    seen = []
    failures = []

    async def handle(reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            lines = head.split(b"\r\n")
            method, path, _ = lines[0].decode().split(" ")
            hs = dict(line.split(b":", 1) for line in lines[1:] if b":" in line)
            length = int(next((v for k, v in hs.items() if k.lower() == b"content-length"), b"0"))
            body = await asyncio.wait_for(reader.readexactly(length), 5)
            if inspect is not None:
                await inspect()
            operation = path.rsplit("/", 1)[-1]
            seen.append(operation)
            if operation == "sendMessage":
                fd = os.open(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, b'{"event":"WIRE_SEND"}\n')
                    os.fsync(fd)
                finally:
                    os.close(fd)
                data = json.loads(body)
                assert data == dict(
                    business_connection_id=EXTERNAL, chat_id=str(CHAT), text="Wire exact 🎨"
                )
                if disconnect_send:
                    return
                if trickle_send:
                    # The effect is durable in the external ledger. Keep read
                    # activity below 5s but never finish a response: only the
                    # unchanged 10s send wall deadline can terminate this call.
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n")
                    while True:
                        writer.write(b" ")
                        await writer.drain()
                        await asyncio.sleep(0.2)
                result = {
                    "message_id": 900,
                    "business_connection_id": EXTERNAL,
                    "chat": {"id": CHAT, "type": "private"},
                }
            elif operation == "getBusinessConnection":
                result = business_connection()
            elif operation == "getFile":
                result = {"file_id": "telegram-photo", "file_path": "photos/file_77.jpg"}
            elif method == "GET" and path.endswith("/photos/file_77.jpg"):
                raw = content
                writer.write(
                    b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: text/plain\r\nContent-Length: "
                    + str(len(raw)).encode()
                    + b"\r\n\r\n"
                    + raw
                )
                await writer.drain()
                return
            else:
                raise AssertionError("UNEXPECTED_TEST_OPERATION")
            raw = json.dumps({"ok": True, "result": result}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(raw)).encode()
                + b"\r\n\r\n"
                + raw
            )
            await writer.drain()
        except ConnectionError:
            if not trickle_send:
                failures.append("UNEXPECTED_CONNECTION_LOSS")
        except Exception as error:
            failures.append(type(error).__name__)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                if not trickle_send:
                    raise

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    address = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    try:
        yield SimpleNamespace(origin=address, seen=seen, ledger=ledger)
    finally:
        server.close()
        await server.wait_closed()
        assert not failures, failures


CHILD = r"""
import asyncio,os
from asm.foundation import Settings,RuntimeDatabase
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.worker import Worker
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
async def main():
    async def barrier(stage):
        if stage == os.environ['M23_CRASH_STAGE']:os._exit(42)
    db=RuntimeDatabase(Settings())
    client=TelegramClient(TelegramSettings(),test_origin=os.environ['M23_TEST_ORIGIN'])
    async def outside_transaction(request):
        assert db.engine.pool.checkedout()==0
    client._http.event_hooks['request']=[outside_transaction]
    try:
        worked=await Worker(MessagingDatabase(db.engine,barrier=barrier),ControlledAdapter(environment='TEST'),telegram=client).run_once()
        print('WORKED' if worked else 'NO_CLAIM',flush=True)
    finally:
        await client.aclose();await db.close()
asyncio.run(main())
"""


@pytest.mark.parametrize("stage", ["finalize_before_commit", "finalize_after_commit"])
@pytest.mark.parametrize("loss", ["disconnect", "trickle_deadline"])
async def test_real_http_accept_lost_response_process_restart_never_second_wire_call(
    telegram_case, tmp_path, stage, loss
):
    h = telegram_case
    _, cid = await inbound(h)
    await finish_text_turns(h)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        prepared = await unit.messaging_prepare_text(cid, "Wire exact 🎨", "wire-1")
        probe = prepared["probe"]
        observed = await unit.telegram_owner_observe(
            cid,
            probe["generation"],
            probe["observation_version"],
            dict(
                bot_identity=str(BOT),
                external_connection_id=EXTERNAL,
                owner_user_id=str(OWNER),
                is_enabled=True,
                can_reply=True,
                error_code=None,
            ),
        )
        assert observed["code"] == "OBSERVED"
        receipt = await request_manual_text(unit, cid, "Wire exact 🎨", "wire-1")

    async def no_business_transaction():
        assert h.runtime.engine.pool.checkedout() == 0
        # Also observe the child runtime identity from PostgreSQL while the
        # server has the complete request, before returning any HTTP response.
        # Use the runtime identity, which can see its own sessions' xact_start;
        # an unprivileged different role could get NULL and falsely pass.
        async with h.runtime.engine.connect() as inspection:
            rows = (
                await inspection.execute(
                    text(
                        "SELECT pid FROM pg_stat_activity WHERE usename=current_user "
                        "AND pid<>pg_backend_pid() AND xact_start IS NOT NULL"
                    )
                )
            ).all()
        assert rows == []

    async with wire_server(
        tmp_path,
        disconnect_send=loss == "disconnect",
        trickle_send=loss == "trickle_deadline",
        inspect=no_business_transaction,
    ) as server:
        env = {
            **os.environ,
            "M23_TEST_ORIGIN": server.origin,
            "M23_CRASH_STAGE": stage,
            "ASM_TELEGRAM_ENABLED": "true",
            "ASM_TELEGRAM_EXPECTED_BOT_ID": str(BOT),
            "TG_BOT_TOKEN": TOKEN,
            "TG_WEBHOOK_SECRET": SECRET,
            "ASM_TELEGRAM_WEBHOOK_URL": "https://test.invalid/webhooks/telegram",
        }
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            CHILD,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        assert process.returncode == 42, (stdout.decode(), stderr.decode())
        if loss == "trickle_deadline":
            # Includes interpreter/DB preflight startup; wire duration is never
            # extended by chunk activity and the 30s lease is not exhausted.
            assert 9.8 <= time.monotonic() - started < 15
        assert len(server.ledger.read_text().splitlines()) == 1
        assert (await delivery(h, receipt.message_id))["status"] == (
            "DISPATCHING" if stage == "finalize_before_commit" else "UNKNOWN"
        )
        await expire(h)
        assert (await delivery(h, receipt.message_id))["status"] == "UNKNOWN"
        restarted = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            CHILD,
            env={**env, "M23_CRASH_STAGE": "none"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(restarted.communicate(), 15)
        finally:
            if restarted.returncode is None:
                restarted.kill()
                await restarted.wait()
        assert restarted.pid != process.pid
        assert restarted.returncode == 0 and stdout.strip() == b"NO_CLAIM" and stderr == b""
        assert (await delivery(h, receipt.message_id))["status"] == "UNKNOWN"
        assert len(server.ledger.read_text().splitlines()) == 1
        assert server.seen == ["getBusinessConnection", "sendMessage"]
        jobs = await query(
            h,
            "SELECT status,attempt_count FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT'",
        )
        assert len(jobs) == 1 and jobs[0]["status"] == "DEAD" and jobs[0]["attempt_count"] == 1


async def test_fetch_twenty_second_wall_includes_cold_tls_metadata_and_trickle(
    telegram_case, images, connect_tls_material
):
    h = telegram_case
    async with tls_peer(connect_tls_material, delay=3, mode="trickle") as peer:
        client = tls_client(connect_tls_material, peer)
        transfer = FetchTransfer(FileDatabase(h.kernel), h.kernel, client, images.storage)
        try:
            raw = update(photo=[{"width": 23, "height": 17, "file_id": "opaque-photo"}])
            del raw["business_message"]["text"]
            await inbound(h, raw)
            started = time.monotonic()
            assert await Worker(h.kernel, h.adapter, files=transfer, telegram=client).run_once()
            elapsed_timeout(started, 20)
            assert peer.requests == ["getFile", "connect.jpg"] and peer.accepted == 2
            assert len(peer.handshakes) == 2 and all(
                3 <= duration < 5 for duration in peer.handshakes
            )
            assert peer.chunks >= 5
            await released(client, peer)
            jobs = await query(
                h,
                "SELECT status,attempt_count FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'",
            )
            assert len(jobs) == 1 and jobs[0]["status"] == "READY" and jobs[0]["attempt_count"] == 1
            assert (
                await query(
                    h, "SELECT * FROM platform.file_object_uploads WHERE workspace_id=:ws", ws=A
                )
                == []
            )
        finally:
            await transfer.close()
            await client.aclose()


async def test_http_webhook_durable_concurrent_dedupe_conflict_unknown_route_and_fingerprint(
    telegram_case,
):
    h = telegram_case
    app = FastAPI()
    install_webhook(app, config(), h.ingress)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        raw = update()
        hs = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
        responses = await asyncio.gather(
            *(client.post("/webhooks/telegram", json=raw, headers=hs) for _ in range(6))
        )
        assert [r.status_code for r in responses] == [200] * 6
        row = (
            await query(
                h,
                "SELECT * FROM platform.telegram_update_receipts WHERE bot_identity=:bot",
                bot=str(BOT),
            )
        )[0]
        assert bytes(row["fingerprint"]).hex() == update_fingerprint(
            str(BOT), normalize_update(str(BOT), raw)
        )
        assert (
            len(
                await query(
                    h,
                    "SELECT id FROM platform.inbox_events WHERE connection_id=:id",
                    id=h.telegram_connection,
                )
            )
            == 1
        )
        assert (
            len(
                await query(
                    h,
                    "SELECT id FROM platform.messaging_jobs WHERE connection_id=:id",
                    id=h.telegram_connection,
                )
            )
            == 1
        )
        assert await h.worker.run_once()
        assert (
            len(
                await query(
                    h,
                    "SELECT id FROM app.messages WHERE connection_id=:id",
                    id=h.telegram_connection,
                )
            )
            == 1
        )
        changed = json.loads(json.dumps(raw))
        changed["business_message"]["text"] = "conflict"
        assert (
            await client.post("/webhooks/telegram", json=changed, headers=hs)
        ).status_code == 409
        unknown = update(124, business_connection_id="unknown-binding")
        assert (
            await client.post("/webhooks/telegram", json=unknown, headers=hs)
        ).status_code == 503
        assert (
            len(
                await query(
                    h,
                    "SELECT id FROM platform.telegram_update_receipts WHERE bot_identity=:bot",
                    bot=str(BOT),
                )
            )
            == 1
        )


@pytest.mark.parametrize("stage", ["telegram_ingest_before_commit", "telegram_ingest_after_commit"])
async def test_webhook_commit_ack_loss_atomic_rollback_and_safe_replay(telegram_case, stage):
    h = telegram_case

    async def barrier(name):
        if name == stage:
            raise SQLAlchemyError("SYNTHETIC_ACK_LOSS")

    ingress = TelegramIngress(MessagingDatabase(h.runtime.engine, barrier=barrier), str(BOT))
    app = FastAPI()
    install_webhook(app, config(), ingress)
    raw = update()
    hs = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/webhooks/telegram", json=raw, headers=hs)).status_code == 503
    for table in (
        "platform.telegram_update_receipts",
        "platform.inbox_events",
        "platform.messaging_jobs",
    ):
        assert len(await query(h, f"SELECT * FROM {table} WHERE workspace_id=:ws", ws=A)) == int(
            stage.endswith("after_commit")
        )
    receipt = await h.ingress.ingest(normalize_update(str(BOT), raw), uuid4())
    assert receipt.code == ("DUPLICATE" if stage.endswith("after_commit") else "ACCEPTED")
    assert await h.worker.run_once()
    assert (
        len(
            await query(
                h, "SELECT id FROM app.messages WHERE connection_id=:id", id=h.telegram_connection
            )
        )
        == 1
    )


async def test_real_telegram_photo_http_pg_s3_owner_grant_and_signed_get(
    telegram_case, images, auth, tmp_path
):
    from asm.messaging.http import install_messaging

    h = telegram_case
    content = image_bytes("JPEG")

    async def no_database():
        assert h.runtime.engine.pool.checkedout() == 0

    async with wire_server(tmp_path, content=content, inspect=no_database) as server:
        client = TelegramClient(config(), test_origin=server.origin)
        transfer = FetchTransfer(FileDatabase(h.kernel), h.kernel, client, images.storage)
        try:
            raw = update(
                photo=[{"width": 23, "height": 17, "file_id": "telegram-photo"}],
                caption="photo exact",
            )
            del raw["business_message"]["text"]
            _, cid = await inbound(h, raw)
            assert await Worker(h.kernel, h.adapter, files=transfer, telegram=client).run_once()
            row = (await query(h, "SELECT * FROM app.file_objects WHERE workspace_id=:ws", ws=A))[0]
            assert row["status"] == "READY" and row["sha256"] == hashlib.sha256(content).hexdigest()
            app = FastAPI()
            install_auth(app, auth.service, auth.settings)
            install_messaging(
                app, auth.service, auth.settings, environment="TEST", storage=images.storage
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=auth.settings.auth_origins[0]
            ) as browser:
                signed_in = await login(auth, client=browser)
                assert signed_in.status_code == 200
                csrf = signed_in.json()["csrf_token"]
                path = f"/api/v1/workspaces/{A}/conversations/{cid}/messages/{row['message_id']}/files/{row['id']}/read-grant"
                grant = await browser.post(path, json={}, headers=headers(browser, csrf))
                assert grant.status_code == 200, grant.status_code
                data = grant.json()
                assert set(data) == {"url", "expires_at"}
                result = await private_request("GET", data["url"])
                assert result.status_code == 200 and result.content == content
                assert "X-Amz-Expires=60" in data["url"]
                unsigned = data["url"].split("?", 1)[0]
                assert (await private_request("GET", unsigned)).status_code == 403
                denied = await browser.post(
                    path.replace(str(row["message_id"]), str(uuid4())),
                    json={},
                    headers=headers(browser, csrf),
                )
                assert denied.status_code == 404
            assert server.seen == ["getFile", "file_77.jpg"]
        finally:
            await transfer.close()
            await client.aclose()


async def test_real_tcp_webhook_never_acknowledges_before_durable_commit(telegram_case):
    import socket

    import uvicorn

    h = telegram_case
    arrived, release = asyncio.Event(), asyncio.Event()

    async def barrier(stage):
        if stage == "telegram_ingest_before_commit":
            arrived.set()
            await asyncio.wait_for(release.wait(), 3)

    ingress = TelegramIngress(MessagingDatabase(h.runtime.engine, barrier=barrier), str(BOT))
    app = FastAPI()
    install_webhook(app, config(), ingress)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    sock.setblocking(False)
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="error", access_log=False, lifespan="off")
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{sock.getsockname()[1]}", trust_env=False
        ) as client:
            pending = asyncio.create_task(
                client.post(
                    "/webhooks/telegram",
                    json=update(),
                    headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
                )
            )
            await asyncio.wait_for(arrived.wait(), 3)
            assert not pending.done()
            assert (
                await query(
                    h,
                    "SELECT id FROM platform.telegram_update_receipts WHERE bot_identity=:bot",
                    bot=str(BOT),
                )
                == []
            )
            release.set()
            assert (await pending).status_code == 200
            assert (
                len(
                    await query(
                        h,
                        "SELECT id FROM platform.telegram_update_receipts WHERE bot_identity=:bot",
                        bot=str(BOT),
                    )
                )
                == 1
            )
    finally:
        release.set()
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()
