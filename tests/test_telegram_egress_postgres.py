"""Mandatory E02–E04 Docker lane: official-host TLS through the real Xray pair.

The ordinary PostgreSQL suite has no relay topology. Its default ``Test*`` class
collector therefore does not select ``TelegramEgressPostgresChecks``. The additive
``scripts/test_telegram_egress.sh`` invokes this file with
``-o python_classes=TelegramEgressPostgresChecks``; every case then executes, with
no skip/xfail or transport mocks. Existing direct-wire cases remain unchanged.

``--serve`` is the isolated synthetic TLS recipient, never an application entry
point. Its CA, private key, scenario, control files and fsynced wire ledger live
only in the disposable TEST directory. No Docker socket enters any container.
"""

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import runpy
import socket
import ssl
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from asm.auth.crypto import PASSWORD_HASHER, new_token, token_verifier
from asm.files.config import StorageSettings
from asm.files.database import FileDatabase
from asm.files.storage import S3ObjectStorage
from asm.files.transfer import FetchTransfer
from asm.foundation import RuntimeDatabase, Settings
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.commands import request_manual_text
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code
from asm.messaging.worker import Worker
from asm.telegram.client import TelegramClient, TelegramError
from asm.telegram.database import TelegramIngress
from asm.tenancy import AuthenticatedAccount
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from test_auth_postgres import LOGIN, login
from test_auth_postgres import auth as auth
from test_m2_1_postgres import cleanup, delivery, due, expire, finish_text_turns, query, receive
from test_m2_1_postgres import messaging as messaging
from test_m2_2_storage_postgres import grant, image_bytes, plan
from test_m2_2_storage_postgres import images as images
from test_m2_2_storage_postgres import request as private_request
from test_m2_3_db_postgres import telegram as telegram
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
from test_m2_3_wire_postgres import inbound
from test_m2_3_wire_postgres import telegram_case as telegram_case
from test_m3_1_control_postgres import control as control
from test_tenancy_postgres import BA, UA, A
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
MODES = {"normal", "hold_readonly", "hold_media", "hold_send", "redirect", "oversized"}


def fixture_directory():
    directory = Path(os.environ["ASM_EGRESS_TEST_DIR"])
    assert directory.is_absolute() and directory.is_dir() and not directory.is_symlink()
    return directory


def write_json(path, value):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, json.dumps(value, sort_keys=True).encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def append_event(directory, value, *, filename="wire-calls.jsonl"):
    descriptor = os.open(directory / filename, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, (json.dumps(value, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json(path):
    return json.loads(path.read_text())


async def relay_action(directory, action):
    """Fixed action protocol; the host driver owns Docker and validates topology."""
    assert action in {"stop", "recreate"}
    identity = uuid4().hex
    lock = directory / "control.lock"
    async with asyncio.timeout(30):
        while True:
            try:
                descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                await asyncio.sleep(0.05)
            else:
                os.close(descriptor)
                break
        try:
            write_json(directory / "control-request.json", {"id": identity, "action": action})
            while True:
                response_path = directory / "control-response.json"
                if response_path.exists():
                    response = read_json(response_path)
                    if response.get("id") == identity:
                        assert response.get("action") == action
                        assert response.get("relay_ip") == os.environ["ASM_EGRESS_RELAY_IP"]
                        assert re.fullmatch(r"[a-f0-9]{12,64}", response.get("relay_id", ""))
                        return response
                await asyncio.sleep(0.05)
        finally:
            lock.unlink(missing_ok=True)


def tls_context(directory):
    context = ssl.create_default_context(cafile=str(directory / "ca.pem"))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    return context


def official_client(directory):
    # The accepted TEST injection changes only trusted CA material. Real HTTPX
    # sockets, official origin, hostname/SNI verification and all budgets remain.
    client = TelegramClient(
        config(),
        transport=httpx.AsyncHTTPTransport(
            verify=tls_context(directory),
            retries=0,
            trust_env=False,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
        ),
    )
    assert client._origin == "https://api.telegram.org"
    assert client._http.timeout == httpx.Timeout(connect=5, pool=2, read=5, write=5)
    assert not client._http.follow_redirects
    return client


async def assert_mapping():
    expected = {
        ipaddress.ip_address(os.environ[key])
        for key in ("ASM_EGRESS_RELAY_IP", "ASM_EGRESS_RELAY_IPV6")
    }
    for family in (socket.AF_UNSPEC, socket.AF_INET, socket.AF_INET6):
        addresses = await asyncio.wait_for(
            asyncio.to_thread(
                socket.getaddrinfo, "api.telegram.org", 443, family, socket.SOCK_STREAM, 0, 0
            ),
            5,
        )
        assert addresses, "OFFICIAL_HOST_MAPPING_MISSING"
        for _, _, _, _, endpoint in addresses:
            address = ipaddress.ip_address(endpoint[0])
            assert address in expected, "DIRECT_OR_DNS_FALLBACK_ADDRESS"
            if family != socket.AF_UNSPEC:
                assert address.version == (4 if family == socket.AF_INET else 6)


async def both_relay_families(directory, *, available):
    for family, key in (
        (socket.AF_INET, "ASM_EGRESS_RELAY_IP"),
        (socket.AF_INET6, "ASM_EGRESS_RELAY_IPV6"),
    ):
        if not available:
            with pytest.raises((OSError, TimeoutError)):
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(os.environ[key], 443, family=family), 2
                )
                writer.close()
            continue
        # End-to-end verified TLS reaches the synthetic recipient through each
        # actual Xray listener. No extra HTTP request/send or provider retry.
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(
                os.environ[key],
                443,
                family=family,
                ssl=tls_context(directory),
                server_hostname="api.telegram.org",
            ),
            8,
        )
        assert writer.get_extra_info("ssl_object").version() == "TLSv1.3"
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), 2)


def case_events(case, event=None):
    ledger = case.directory / "wire-calls.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
    return [
        row
        for row in rows
        if row["case"] == case.identity and (event is None or row["event"] == event)
    ]


def assert_wire_identity(case):
    rows = case_events(case, "REQUEST")
    assert rows, "NO_CONTROLLED_RELAY_WIRE_REQUEST"
    assert all(row["peer"] == os.environ["ASM_EGRESS_PEER_IP"] for row in rows)
    assert all(row["sni"] == row["host"] == "api.telegram.org" for row in rows)


def record_pass(case, criterion, assertion, **evidence):
    append_event(
        case.directory,
        {
            "case": case.identity,
            "criterion": criterion,
            "assertion": assertion,
            "result": "PASS",
            **evidence,
        },
        filename="assertions.jsonl",
    )


def scenario(case, mode):
    assert mode in MODES
    write_json(case.directory / "scenario.json", {"case": case.identity, "mode": mode})


async def wait_stopped(case):
    path = case.directory / ("stopped-" + case.identity + ".json")
    async with asyncio.timeout(30):
        while not path.exists():
            await asyncio.sleep(0.05)
    result = read_json(path)
    assert result["action"] == "stop"
    assert result["relay_id"] == case.relay_id
    return result


@pytest_asyncio.fixture
async def egress_case():
    directory = fixture_directory()
    initial = await relay_action(directory, "recreate")
    case = SimpleNamespace(directory=directory, identity=uuid4().hex, relay_id=initial["relay_id"])
    scenario(case, "normal")
    try:
        yield case
    finally:
        failure_path = directory / "wire-failures.jsonl"
        failures = (
            [json.loads(line) for line in failure_path.read_text().splitlines()]
            if failure_path.exists()
            else []
        )
        assert not [row for row in failures if row.get("case") in {None, case.identity}]


CHILD = r"""
import asyncio,os,ssl,sys
import httpx
from asm.foundation import Settings,RuntimeDatabase
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.worker import Worker
from asm.telegram.client import TelegramClient
from asm.telegram.config import TelegramSettings
async def main():
    async def barrier(stage):
        if stage == os.environ['ENV04_CRASH_STAGE']:os._exit(42)
    db=RuntimeDatabase(Settings())
    context=ssl.create_default_context(cafile=os.environ['ASM_EGRESS_TEST_DIR']+'/ca.pem')
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    transport=httpx.AsyncHTTPTransport(verify=context,retries=0,trust_env=False,
        limits=httpx.Limits(max_connections=4,max_keepalive_connections=4))
    client=TelegramClient(TelegramSettings(),transport=transport)
    assert client._origin=='https://api.telegram.org'
    try:
        worked=await Worker(MessagingDatabase(db.engine,barrier=barrier),
            ControlledAdapter(environment='TEST'),telegram=client).run_once()
        print('WORKED' if worked else 'NO_CLAIM',flush=True)
    finally:
        await client.aclose();await db.close()
try:asyncio.run(main())
except Exception as error:
    print('WORKER_CHILD_FAILURE='+type(error).__name__,file=sys.stderr,flush=True)
    sys.exit(1)
"""


async def worker_process(stage):
    env = {
        **os.environ,
        "ENV04_CRASH_STAGE": stage,
        "ASM_TELEGRAM_ENABLED": "true",
        "ASM_TELEGRAM_EXPECTED_BOT_ID": str(BOT),
        "TG_BOT_TOKEN": TOKEN,
        "TG_WEBHOOK_SECRET": SECRET,
        "ASM_TELEGRAM_WEBHOOK_URL": "https://test.invalid/webhooks/telegram",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        CHILD,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 25)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    assert not stderr, "WORKER_CHILD_FAILURE"
    return process.pid, process.returncode, stdout.decode().strip()


async def unknown_scenario(case, h, stage):
    _, conversation_id = await inbound(h)
    await stabilize_turns(h)
    async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        prepared = await unit.messaging_prepare_text(
            conversation_id, "Wire exact 🎨", "egress-send"
        )
        probe = prepared["probe"]
        observed = await unit.telegram_owner_observe(
            conversation_id,
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
        receipt = await request_manual_text(unit, conversation_id, "Wire exact 🎨", "egress-send")
    scenario(case, "hold_send")
    pid, result, output = await worker_process(stage)
    assert result == 42 and output == ""
    await wait_stopped(case)
    await assert_mapping()
    assert len(case_events(case, "SEND_EFFECT")) == 1
    state = await delivery(h, receipt.message_id)
    if stage == "finalize_before_commit":
        assert state["status"] == "DISPATCHING"
    else:
        assert state["status"] == "UNKNOWN"
    # Existing canonical lease recovery, without fabricating another intent.
    await expire(h)
    assert (await delivery(h, receipt.message_id))["status"] == "UNKNOWN"
    replacement = await relay_action(case.directory, "recreate")
    assert replacement["relay_id"] != case.relay_id
    await assert_mapping()
    scenario(case, "normal")
    new_pid, result, output = await worker_process("none")
    assert new_pid != pid and result == 0 and output == "NO_CLAIM"
    assert (await delivery(h, receipt.message_id))["status"] == "UNKNOWN"
    jobs = await query(
        h,
        "SELECT status,attempt_count FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT'",
    )
    assert len(jobs) == 1 and jobs[0]["status"] == "DEAD" and jobs[0]["attempt_count"] == 1
    # Re-read the fsynced file after both restarts; no process-local counter.
    assert len(case_events(case, "SEND_EFFECT")) == 1
    assert [row["operation"] for row in case_events(case, "REQUEST")] == [
        "getBusinessConnection",
        "sendMessage",
    ]
    assert_wire_identity(case)
    return SimpleNamespace(
        message_id=receipt.message_id,
        evidence=dict(
            stage=stage,
            wire_counter=1,
            attempts=1,
            relay_before=case.relay_id,
            relay_after=replacement["relay_id"],
            worker_before=pid,
            worker_after=new_pid,
        ),
    )


class TelegramEgressPostgresChecks:
    async def test_readonly_tls_mapping_and_auth_db_s3_survive_relay_failure(
        self, egress_case, telegram_case, images, auth, monkeypatch
    ):
        case, h = egress_case, telegram_case
        monkeypatch.setenv("HTTPS_PROXY", "http://unusable-proxy.invalid:9")
        await assert_mapping()
        await both_relay_families(case.directory, available=True)
        # A globally trusted CA was not installed. The frozen default client
        # rejects the synthetic certificate; the explicit TEST transport trusts it.
        untrusted = TelegramClient(config())
        try:
            with pytest.raises(TelegramError) as bad_ca:
                await untrusted.get_me()
            assert bad_ca.value.definitely_unsent
        finally:
            await untrusted.aclose()
        assert not case_events(case, "REQUEST")
        with pytest.raises(ssl.SSLCertVerificationError) as bad_hostname:
            await asyncio.wait_for(
                asyncio.open_connection(
                    os.environ["ASM_EGRESS_RELAY_IP"],
                    443,
                    ssl=tls_context(case.directory),
                    server_hostname="wrong-host.invalid",
                ),
                8,
            )
        assert bad_hostname.value.verify_code == 62  # X509_V_ERR_HOSTNAME_MISMATCH
        client = official_client(case.directory)
        try:
            scenario(case, "hold_readonly")
            started = asyncio.get_running_loop().time()
            with pytest.raises(TelegramError) as interrupted:
                await client.get_me()
            assert interrupted.value.code in {Code.DEPENDENCY_TIMEOUT, Code.DEPENDENCY_UNAVAILABLE}
            assert asyncio.get_running_loop().time() - started < 7
            await wait_stopped(case)
            await assert_mapping()
            await both_relay_families(case.directory, available=False)
            assert len(case_events(case, "REQUEST")) == 1
            assert not case_events(case, "SEND_EFFECT")
            offline_started = asyncio.get_running_loop().time()
            with pytest.raises(TelegramError) as offline:
                await client.get_me()
            offline_elapsed = asyncio.get_running_loop().time() - offline_started
            assert offline_elapsed <= 6, offline_elapsed  # Outer5 + at most1s runner tolerance.
            # Connect5 is inside outer5. A total timeout proves no wire phase;
            # only a proven connect failure may be classified definitely_unsent.
            assert (offline.value.code, offline.value.definitely_unsent) in {
                (Code.DEPENDENCY_TIMEOUT, False),
                (Code.DEPENDENCY_UNAVAILABLE, True),
            }
            assert len(case_events(case, "REQUEST")) == 1
            assert not case_events(case, "SEND_EFFECT")
            await h.runtime.check()
            assert (await auth.client.get("/health/ready")).json() == {
                "status": "ok",
                "component": "database",
            }
            assert (await login(auth)).status_code == 200
            # The Compose API uses this same real asm_test database. This checks
            # the actual API container, in addition to the accepted ASGI fixture.
            async with httpx.AsyncClient(
                base_url="http://api:8000",
                headers={"Host": "localhost:8000"},
                timeout=5,
                trust_env=False,
            ) as api:
                ready = await api.get("/health/ready")
                assert ready.status_code == 200 and ready.json() == {
                    "status": "ok",
                    "component": "database",
                }
                origin = auth.settings.auth_origins[0]
                bootstrap = await api.post(
                    "/api/v1/auth/bootstrap",
                    json={},
                    headers={"Origin": origin, "X-CSRF-Bootstrap": "1"},
                )
                assert bootstrap.status_code == 200
                signed_in = await api.post(
                    "/api/v1/auth/login",
                    json={"login": LOGIN, "password": auth.password.get_secret_value()},
                    headers={"Origin": origin, "X-CSRF-Token": bootstrap.json()["csrf_token"]},
                )
                assert signed_in.status_code == 200
                businesses = await api.get(f"/api/v1/workspaces/{A}/businesses")
                assert businesses.status_code == 200
            # The ordinary private storage path remains independent of relay state.
            content = image_bytes()
            row = await plan(images, content, "relay-down")
            assert await images.image_worker.run_once()
            private = await grant(images, row)
            assert (await private_request("GET", private.url)).content == content
            assert (await private_request("GET", private.url.split("?", 1)[0])).status_code == 403
            replacement = await relay_action(case.directory, "recreate")
            assert replacement["relay_id"] != case.relay_id
            await assert_mapping()
            await both_relay_families(case.directory, available=True)
            scenario(case, "normal")
            assert await client.get_me() == str(BOT)
            connection = await client.get_business_connection(EXTERNAL)
            assert connection.is_enabled and connection.can_reply
            assert connection.owner_user_id == str(OWNER)
            assert [row["operation"] for row in case_events(case, "REQUEST")] == [
                "getMe",
                "getMe",
                "getBusinessConnection",
            ]
            assert_wire_identity(case)
            record_pass(
                case,
                "E02/E03",
                "READONLY_TLS_MAPPING_AUTH_DB_PRIVATE_S3",
                native_ipv4_ipv6_tls_and_fail_closed=True,
                offline_readonly_elapsed_seconds=round(offline_elapsed, 3),
                offline_readonly_code=offline.value.code.value,
                offline_readonly_definitely_unsent=offline.value.definitely_unsent,
                relay_before=case.relay_id,
                relay_after=replacement["relay_id"],
            )
        finally:
            await client.aclose()

    async def test_media_interruption_retries_same_file_and_preserves_private_original(
        self, egress_case, telegram_case, images
    ):
        case, h = egress_case, telegram_case
        client = official_client(case.directory)
        transfer = FetchTransfer(FileDatabase(h.kernel), h.kernel, client, images.storage)
        try:
            raw = update(photo=[{"width": 23, "height": 17, "file_id": "telegram-photo"}])
            del raw["business_message"]["text"]
            await inbound(h, raw)
            scenario(case, "hold_media")
            worker = Worker(h.kernel, h.adapter, files=transfer, telegram=client)
            assert await worker.run_once()
            await wait_stopped(case)
            files = await query(h, "SELECT * FROM app.file_objects WHERE workspace_id=:ws", ws=A)
            assert len(files) == 1 and files[0]["status"] == "PENDING"
            file_id, message_id = files[0]["id"], files[0]["message_id"]
            jobs = await query(h, "SELECT * FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")
            assert len(jobs) == 1
            job = jobs[0]
            assert job["status"] == "READY" and job["attempt_count"] == 1
            assert job["error_code"] in {"DEPENDENCY_UNAVAILABLE", "DEPENDENCY_TIMEOUT"}
            assert not await query(
                h, "SELECT id FROM platform.file_object_uploads WHERE file_id=:id", id=file_id
            )
            assert h.runtime.engine.pool.checkedout() == 0
            await assert_mapping()
            replacement = await relay_action(case.directory, "recreate")
            assert replacement["relay_id"] != case.relay_id
            await assert_mapping()
            scenario(case, "normal")
            await due(h)
            assert await Worker(h.kernel, h.adapter, files=transfer, telegram=client).run_once()
            ready = (await query(h, "SELECT * FROM app.file_objects WHERE id=:id", id=file_id))[0]
            content = image_bytes("JPEG")
            assert ready["message_id"] == message_id and ready["status"] == "READY"
            assert (
                ready["sha256"],
                ready["size_bytes"],
                ready["mime_type"],
                ready["width"],
                ready["height"],
            ) == (hashlib.sha256(content).hexdigest(), len(content), "image/jpeg", 23, 17)
            jobs = await query(h, "SELECT * FROM platform.messaging_jobs WHERE kind='FETCH_IMAGE'")
            assert len(jobs) == 1 and jobs[0]["id"] == job["id"]
            assert jobs[0]["status"] == "SUCCEEDED" and jobs[0]["attempt_count"] == 2
            assert (
                len(await query(h, "SELECT id FROM app.messages WHERE id=:id", id=message_id)) == 1
            )
            signed = await grant(images, ready)
            downloaded = await private_request("GET", signed.url)
            assert downloaded.status_code == 200 and downloaded.content == content
            ttl_is_60 = "X-Amz-Expires=60" in signed.url
            assert ttl_is_60
            assert (await private_request("GET", signed.url.split("?", 1)[0])).status_code == 403
            assert [row["operation"] for row in case_events(case, "REQUEST")] == [
                "getFile",
                "download",
                "getFile",
                "download",
            ]
            assert_wire_identity(case)
            record_pass(
                case,
                "E03",
                "MEDIA_INTERRUPTION_SAME_FETCH_PRIVATE_ORIGINAL",
                relay_before=case.relay_id,
                relay_after=replacement["relay_id"],
                attempts=2,
                original_sha256=hashlib.sha256(content).hexdigest(),
            )
        finally:
            await transfer.close()
            await client.aclose()

    @pytest.mark.parametrize("mode", ["redirect", "oversized"])
    async def test_media_redirect_and_actual_size_are_rejected_before_private_publication(
        self, egress_case, telegram_case, images, mode
    ):
        case, h = egress_case, telegram_case
        scenario(case, mode)
        client = official_client(case.directory)
        transfer = FetchTransfer(FileDatabase(h.kernel), h.kernel, client, images.storage)
        try:
            raw = update(photo=[{"width": 23, "height": 17, "file_id": "telegram-photo"}])
            del raw["business_message"]["text"]
            await inbound(h, raw)
            assert await Worker(h.kernel, h.adapter, files=transfer, telegram=client).run_once()
            row = (await query(h, "SELECT * FROM app.file_objects WHERE workspace_id=:ws", ws=A))[0]
            assert row["status"] == "FAILED" and row["error_code"] == "INVALID_INPUT"
            assert row["storage_key"] is None and row["winner_intent_id"] is None
            assert not await query(
                h, "SELECT id FROM platform.file_object_uploads WHERE file_id=:id", id=row["id"]
            )
            assert [row["operation"] for row in case_events(case, "REQUEST")] == [
                "getFile",
                "download",
            ]
            assert_wire_identity(case)
            record_pass(case, "E03", "MEDIA_GUARD_" + mode.upper())
        finally:
            await transfer.close()
            await client.aclose()

    @pytest.mark.parametrize("stage", ["finalize_before_commit", "finalize_after_commit"])
    async def test_effect_then_relay_loss_unknown_restart_never_second_wire_send(
        self, egress_case, telegram_case, stage
    ):
        result = await unknown_scenario(egress_case, telegram_case, stage)
        record_pass(
            egress_case, "E04", "EFFECT_RELAY_LOSS_UNKNOWN_RESTART_NO_RESEND", **result.evidence
        )


DATABASE_IDENTITY_SQL = (
    "SELECT current_database() AS database, "
    "(SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid, "
    "inet_server_addr()::text AS server_address, inet_server_port() AS server_port, "
    "pg_postmaster_start_time()::text AS postmaster_started"
)


async def database_identity(connection):
    return dict((await connection.execute(text(DATABASE_IDENTITY_SQL))).mappings().one())


def require_same_database(actual, expected):
    assert actual == expected, "E05_CALLER_DATABASE_IDENTITY_MISMATCH"


def durable_target():
    """Only the host-attested disposable project's actual LOCAL database is writable."""
    assert os.environ["ASM_ENVIRONMENT"] == "TEST"
    path = fixture_directory() / "durable-target.json"
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
    assert info.st_uid == os.getuid()
    target = read_json(path)
    assert set(target) == {"project", "postgres_id", "database_identity", "callers"}
    assert target["project"] == "asm-telegram-egress-test"
    assert re.fullmatch(r"[0-9a-f]{64}", target["postgres_id"])
    identity = target["database_identity"]
    assert set(identity) == {
        "database",
        "database_oid",
        "server_address",
        "server_port",
        "postmaster_started",
    }
    assert identity["database"] == "asm_local" and identity["server_port"] == 5432
    assert type(identity["database_oid"]) is int and identity["database_oid"] > 0
    # PostgreSQL inet::text includes its host mask (/32 or /128). Preserve
    # the exact SQL identity and require a private single-host address.
    endpoint = ipaddress.ip_interface(identity["server_address"])
    assert endpoint.ip.is_private and endpoint.network.prefixlen == endpoint.max_prefixlen
    assert isinstance(identity["postmaster_started"], str) and identity["postmaster_started"]
    assert set(target["callers"]) == {"api", "worker"}
    for caller in target["callers"].values():
        require_same_database(caller, identity)
    for variable, user in (
        ("ASM_DATABASE_URL", "asm_runtime"),
        ("ASM_MIGRATION_DATABASE_URL", "asm_migrator"),
    ):
        url = make_url(os.environ[variable])
        valid = (
            url.drivername == "postgresql+psycopg"
            and url.host == "postgres"
            and url.port == 5432
            and url.database == "asm_local"
            and url.username == user
            and bool(url.password)
            and not url.query
        )
        assert valid, "E05_EXACT_ISOLATED_LOCAL_ENDPOINT_REQUIRED"
    return target


async def stabilize_turns(h):
    # The shared helper imports through the existing tests-directory path in
    # both pytest and the direct Python E05 entrypoint. Empty queues alone are
    # insufficient: require the exact current OBSERVED receipt before intent.
    await finish_text_turns(h)


class TestEgressTurnSuccessGate:
    # Ordinary TEST PostgreSQL suite only. The explicit wire and held LOCAL
    # collectors select their own classes in this same dual-entrypoint module.
    @pytest.mark.parametrize("damage", ["failed", "missing", "stale", "noncurrent", "extra"])
    async def test_egress_turn_success_gate_rejects_actual_invalid_state(self, messaging, damage):
        from asm.conversations.turns import consume
        from test_m2_1_postgres import command
        from test_m3_1_turns_postgres import claim_exact, seal, snapshot, turns, wait_due
        from test_m3_1_turns_postgres import receive as receive_turn

        h = messaging
        await receive(h)
        turn = (await turns(h))[0]
        if damage == "failed":
            # A real admitted failure, not a fabricated terminal success/status.
            await wait_due(h, turn["id"])
            claim = await h.kernel.claim_job("egress-negative")
            assert claim.kind == "PROCESS_TURN"
            await h.kernel.retry(claim, Code.INVALID_INPUT, False)
            assert (await query(h, "SELECT state FROM app.conversation_turns")) == [
                {"state": "FAILED"}
            ]
            assert (
                await query(
                    h, "SELECT status FROM platform.messaging_jobs WHERE kind='PROCESS_TURN'"
                )
            ) == [{"status": "DEAD"}]
        elif damage == "stale":
            await seal(h, turn["id"])
            claim, value = await snapshot(h, turn["id"])
            await command(h, turn["conversation_id"], "context change", "stale-gate")
            send = (
                await query(
                    h, "SELECT id FROM platform.messaging_jobs WHERE kind='SEND_MANUAL_TEXT'"
                )
            )[0]["id"]
            await h.worker.execute(await claim_exact(h, send))
            result = await h.kernel.finish_turn(claim, consume(value))
            assert result.code == "STALE"
            assert (
                await query(
                    h, "SELECT result->>'code' AS code FROM platform.turn_consumer_receipts"
                )
            ) == [{"code": "STALE"}]
        else:
            await stabilize_turns(h)  # real Worker success is a prerequisite
            if damage == "missing":
                await query(h, "DELETE FROM platform.turn_consumer_receipts RETURNING job_id")
            elif damage == "noncurrent":
                await query(h, "UPDATE app.conversation_turns SET revision=revision+1 RETURNING id")
            else:
                await receive_turn(h, chat_id="extra")
                extra = (await turns(h))[-1]
                await seal(h, extra["id"])
                claim, value = await snapshot(h, extra["id"])
                await h.kernel.finish_turn(claim, consume(value))
                assert (
                    len(await query(h, "SELECT job_id FROM platform.turn_consumer_receipts")) == 2
                )
        assert not await query(
            h, "SELECT id FROM platform.messaging_jobs WHERE status IN ('READY','RUNNING')"
        )
        with pytest.raises(AssertionError):
            await stabilize_turns(h)


async def canonical_fingerprint(connection, *, revision="0012"):
    assert revision in {"0009", "0010", "0011", "0012"}
    tables = (
        await connection.execute(
            text(
                "SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('app','platform') AND c.relkind='r' ORDER BY n.nspname,c.relname"
            )
        )
    ).all()
    # The held after command runs this file directly, without pytest's root
    # pythonpath. Load the exact checked-out guard in both entrypoints.
    schema_inventory = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/prepare_telegram_egress.py")
    )["schema_inventory"]

    assert (
        await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == revision
    schema_inventory(revision, (namespace + "." + table for namespace, table in tables))
    fingerprint = {}
    for namespace, table in tables:
        assert re.fullmatch(r"[a-z_][a-z_0-9]*", namespace)
        assert re.fullmatch(r"[a-z_][a-z_0-9]*", table)
        rows = (
            (
                await connection.execute(
                    text(f'SELECT to_jsonb(t) FROM "{namespace}"."{table}" AS t')
                )
            )
            .scalars()
            .all()
        )
        # Stable multiset comparison covers UUIDs, statuses, receipts,
        # timestamps, fingerprints, exact text bytes and Console state.
        canonical = sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        fingerprint[namespace + "." + table] = {
            "count": len(rows),
            "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
        }
    return fingerprint


def migration_storage():
    # Explicit test CA, never verify=False. Both API and S3 remain on real HTTPS.
    previous = os.environ.get("AWS_CA_BUNDLE")
    os.environ["AWS_CA_BUNDLE"] = str(fixture_directory() / "ca.pem")
    try:
        return S3ObjectStorage(StorageSettings(environment="LOCAL", bucket="asm-private-local"))
    finally:
        if previous is None:
            os.environ.pop("AWS_CA_BUNDLE", None)
        else:
            os.environ["AWS_CA_BUNDLE"] = previous


async def seed_migration_private_original(h):
    content = image_bytes()

    class SyntheticMedia:
        # Only media acquisition is deterministic fixture input. Canonical ingest,
        # FileObject/permit/upload/READY transitions, private S3 and HTTPS are real.
        async def open_image(self, permit):
            assert permit.provider == "TELEGRAM" and permit.bot_identity == str(BOT)
            assert permit.image_file_id == "migration-private-original"
            yield content

    storage = migration_storage()
    transfer = FetchTransfer(FileDatabase(h.kernel), h.kernel, SyntheticMedia(), storage)
    try:
        raw = update(
            uid=122,
            message_id=76,
            photo=[{"width": 23, "height": 17, "file_id": "migration-private-original"}],
        )
        del raw["business_message"]["text"]
        await inbound(h, raw)
        assert await Worker(h.kernel, h.adapter, files=transfer).run_once()
        rows = await query(h, "SELECT * FROM app.file_objects WHERE workspace_id=:ws", ws=A)
        assert len(rows) == 1 and rows[0]["status"] == "READY"
        row = rows[0]
        assert row["sha256"] == hashlib.sha256(content).hexdigest()
        assert row["mime_type"] == "image/png" and row["size_bytes"] == len(content)
        write_json(
            fixture_directory() / "migration-private-original.json",
            {k: str(row[k]) for k in ("id", "conversation_id", "message_id", "storage_key")},
        )
    finally:
        await transfer.close()
        await storage.close()


async def migration_private_snapshot():
    raw = read_json(fixture_directory() / "migration-private-original.json")
    row = {k: UUID(raw[k]) for k in ("id", "conversation_id", "message_id")}
    runtime, storage = RuntimeDatabase(Settings(environment="LOCAL")), migration_storage()
    try:
        content = image_bytes()
        info = await storage.head(raw["storage_key"])
        assert await storage.get(raw["storage_key"]) == content
        assert info.size_bytes == len(content) and info.mime_type == "image/png"
        signed = await grant(SimpleNamespace(runtime=runtime, storage=storage), row)
        async with httpx.AsyncClient(
            verify=tls_context(fixture_directory()), timeout=5, trust_env=False
        ) as client:
            # No bearer URL appears in failure messages or evidence.
            try:
                response = await client.get(signed.url)
                anonymous = await client.get(signed.url.split("?", 1)[0])
            except httpx.HTTPError:
                pytest.fail("MIGRATION_PRIVATE_HTTPS_UNAVAILABLE", pytrace=False)
            assert response.status_code == 200 and response.content == content
            assert response.headers["cache-control"] == "private, no-store"
            assert anonymous.status_code == 403
        return {
            "file_id": raw["id"],
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "mime_type": info.mime_type,
            "authenticated_https_get": 200,
            "anonymous_get": 403,
        }
    finally:
        await storage.close()
        await runtime.close()


@pytest_asyncio.fixture
async def durable_local():
    """Dedicated fresh LOCAL fixture; frozen asm_test fixtures are never overridden."""
    target = durable_target()
    settings = Settings(environment="LOCAL")
    runtime = RuntimeDatabase(settings, pool_size=2)
    migrator = create_async_engine(os.environ["ASM_MIGRATION_DATABASE_URL"], hide_parameters=True)
    kernel = MessagingDatabase(runtime.engine)
    h = SimpleNamespace(runtime=runtime, migrator=migrator, kernel=kernel)
    h.adapter = ControlledAdapter(environment="TEST")
    h.worker = Worker(kernel, h.adapter)
    h.ingress = TelegramIngress(kernel, str(BOT))
    password = SecretStr(new_token())
    session_hashes = []
    seeded_local = False
    catalog = None
    lifecycle = os.environ["ASM_EGRESS_LIFECYCLE"]
    assert lifecycle in {
        "fresh",
        "recovery",
        "recover-stopped",
        "recover-missing",
        "legacy-disable",
        "legacy-stop",
        "migration",
    }
    catalog_file = fixture_directory() / "durable-catalog.json"
    try:
        await runtime.check()
        for engine in (runtime.engine, migrator):
            async with engine.connect() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                require_same_database(
                    await database_identity(connection), target["database_identity"]
                )
        async with migrator.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            empty = await canonical_fingerprint(connection)
            assert empty["platform.alembic_version"]["count"] == 1
            if lifecycle in {"fresh", "migration"}:
                assert not catalog_file.exists(), "E05_FRESH_CATALOG_RECEIPT_MUST_BE_ABSENT"
                assert all(
                    row["count"] == 0
                    for name, row in empty.items()
                    if name != "platform.alembic_version"
                ), "E05_FRESH_EMPTY_LOCAL_DATABASE_REQUIRED"
            else:
                # The first case's sealed billing catalog is immutable by contract.
                # Require its complete attested cleanup fingerprint (all current tables),
                # not a relaxed empty-DB check or a destructive catalog reset.
                previous = read_json(catalog_file)
                assert previous["database_identity"] == target["database_identity"]
                assert previous["fingerprint"] == empty, "E05_PREVIOUS_FIXTURE_STATE_DRIFT"
        # Reproduce the reviewed mismatch on the real, separate PostgreSQL service.
        # A complete set of asm_test row hashes cannot satisfy the callers' identity.
        reviewed_url = make_url(os.environ["ASM_MIGRATION_DATABASE_URL"]).set(
            host="postgres-test", database="asm_test"
        )
        reviewed = create_async_engine(reviewed_url, hide_parameters=True)
        try:
            async with reviewed.connect() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                other = await database_identity(connection)
                assert other["database"] == "asm_test"
                with pytest.raises(AssertionError, match="E05_CALLER_DATABASE_IDENTITY_MISMATCH"):
                    require_same_database(other, target["database_identity"])
        finally:
            await reviewed.dispose()
        async with migrator.begin() as connection:
            await connection.execute(
                text("INSERT INTO platform.user_accounts(id) VALUES(:id)"), {"id": UA}
            )
            await connection.execute(
                text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": A}
            )
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:user,'OWNER')"
                ),
                {"ws": A, "user": UA},
            )
            await connection.execute(
                text(
                    "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:id,'Synthetic E05')"
                ),
                {"ws": A, "id": BA},
            )
            await connection.execute(
                text(
                    "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) VALUES(:id,:login,:encoded)"
                ),
                {
                    "id": UA,
                    "login": LOGIN,
                    "encoded": PASSWORD_HASHER.hash(password.get_secret_value()),
                },
            )
            observation = dict(
                bot_identity=str(BOT),
                external_connection_id=EXTERNAL,
                owner_user_id=str(OWNER),
                is_enabled=True,
                can_reply=True,
                error_code=None,
            )
            binding = (
                await connection.execute(
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
            await connection.execute(
                text(
                    "SELECT platform.initialize_local_messaging_billing(:ws,'Telegram TEST','2000-01-01T00:00:00Z','2100-01-01T00:00:00Z')"
                ),
                {"ws": A},
            )
        seeded_local = True
        async with migrator.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            seeded = await canonical_fingerprint(connection)
            catalog = {
                name: seeded[name]
                for name in (
                    "platform.saas_plans",
                    "platform.saas_plan_revisions",
                    "platform.plan_entitlements",
                )
            }
            assert all(row["count"] == 1 for row in catalog.values())
        assert settings.auth_origins == ("https://console.egress.test:8443",)
        assert settings.auth_secure and settings.auth_cookie_name == "__Host-asm_session"
        assert os.environ["ASM_STORAGE_ENDPOINT"] == "https://files.egress.test:8443"
        async with httpx.AsyncClient(
            base_url=settings.auth_origins[0],
            verify=tls_context(fixture_directory()),
            timeout=5,
            trust_env=False,
        ) as api:
            h.api = api
            bootstrap = await api.post(
                "/api/v1/auth/bootstrap",
                json={},
                headers={"Origin": settings.auth_origins[0], "X-CSRF-Bootstrap": "1"},
            )
            assert bootstrap.status_code == 200
            session_hashes.append(token_verifier(api.cookies.get(settings.auth_cookie_name)))
            signed_in = await api.post(
                "/api/v1/auth/login",
                json={"login": LOGIN, "password": password.get_secret_value()},
                headers={
                    "Origin": settings.auth_origins[0],
                    "X-CSRF-Token": bootstrap.json()["csrf_token"],
                },
            )
            assert signed_in.status_code == 200
            assert api.cookies.jar and all(cookie.secure for cookie in api.cookies.jar)
            session_hashes.append(token_verifier(api.cookies.get(settings.auth_cookie_name)))
            anonymous = await api.get(
                os.environ["ASM_STORAGE_ENDPOINT"] + "/asm-private-local/not-public"
            )
            assert anonymous.status_code == 403
            await assert_durable_console(h)
            if lifecycle == "migration":
                await seed_migration_private_original(h)
            yield h
    finally:
        if seeded_local:
            if lifecycle == "migration":
                storage = migration_storage()
                try:
                    rows = await query(
                        h,
                        "SELECT storage_key FROM platform.file_object_uploads WHERE workspace_id=:ws",
                        ws=A,
                    )
                    for row in rows:
                        await storage._io(
                            lambda key=row["storage_key"]: storage._client.delete_object(
                                Bucket=storage._settings.bucket, Key=key
                            )
                        )
                finally:
                    await storage.close()
            # Only this attested disposable fixture's canonical rows are removed,
            # after the held before/after assertions, never by deploy or rollback.
            async with migrator.begin() as connection:
                require_same_database(
                    await database_identity(connection), target["database_identity"]
                )
                # Fresh V2 receipts own a sidecar even while material is OFF.
                # Dispose only this attested TEST fixture after every held proof;
                # deployment/reversal never calls this teardown.
                from test_m2_3_db_postgres import cleanup_material

                await cleanup_material(connection)
                await connection.execute(
                    text(
                        "DELETE FROM platform.auth_sessions WHERE user_account_id=:user OR token_hash=ANY(:hashes)"
                    ),
                    {"user": UA, "hashes": session_hashes},
                )
                await connection.execute(
                    text("DELETE FROM platform.auth_credentials WHERE user_account_id=:id"),
                    {"id": UA},
                )
                await connection.execute(
                    text("DELETE FROM platform.telegram_update_receipts WHERE bot_identity=:bot"),
                    {"bot": str(BOT)},
                )
            await cleanup(migrator)
            async with migrator.begin() as connection:
                for table in (
                    "platform.billing_contact_command_receipts",
                    "app.audit_events",
                    "platform.workspace_service_modes",
                    "platform.workspace_subscriptions",
                    "platform.workspace_billing_accounts",
                    "app.businesses",
                    "platform.workspace_memberships",
                ):
                    await connection.execute(
                        text(f"DELETE FROM {table} WHERE workspace_id=:ws"), {"ws": A}
                    )
                await connection.execute(
                    text("DELETE FROM platform.workspaces WHERE id=:id"), {"id": A}
                )
                await connection.execute(
                    text("DELETE FROM platform.user_accounts WHERE id=:id"), {"id": UA}
                )
                cleaned = await canonical_fingerprint(connection)
                assert {name: cleaned[name] for name in catalog} == catalog
                assert all(
                    row["count"] == 0
                    for name, row in cleaned.items()
                    if name not in {*catalog, "platform.alembic_version"}
                ), "E05_FIXTURE_CLEANUP_INCOMPLETE"
                assert cleaned["platform.alembic_version"]["count"] == 1
            if lifecycle in {"fresh", "migration"}:
                write_json(
                    catalog_file,
                    {"database_identity": target["database_identity"], "fingerprint": cleaned},
                )
            else:
                assert read_json(catalog_file) == {
                    "database_identity": target["database_identity"],
                    "fingerprint": cleaned,
                }
        await runtime.close()
        await migrator.dispose()


async def assert_durable_console(h):
    session = await h.api.get("/api/v1/auth/session")
    assert session.status_code == 200 and session.json()["user_account_id"] == str(UA)
    businesses = await h.api.get(f"/api/v1/workspaces/{A}/businesses")
    assert businesses.status_code == 200
    assert [row["id"] for row in businesses.json()["businesses"]] == [str(BA)]


async def durable_snapshot():
    """Read-only rows of the actual callers' attested LOCAL DB; no raw rows escape."""
    target = durable_target()
    engine = create_async_engine(os.environ["ASM_MIGRATION_DATABASE_URL"], hide_parameters=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            identity = await database_identity(connection)
            require_same_database(identity, target["database_identity"])
            fingerprint = await canonical_fingerprint(connection)
            assert fingerprint["app.outbox_events"]["count"] == 1
            assert fingerprint["platform.messaging_command_receipts"]["count"] == 1
            assert fingerprint["platform.auth_credentials"]["count"] == 1
            assert fingerprint["platform.auth_sessions"]["count"] >= 1
            states = (
                (await connection.execute(text("SELECT status FROM app.outbox_events")))
                .scalars()
                .all()
            )
            assert states == ["UNKNOWN"]
            result = {
                "identity": identity,
                "tables": fingerprint,
                "sha256": hashlib.sha256(
                    json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        if os.environ["ASM_EGRESS_LIFECYCLE"] == "migration":
            assert fingerprint["app.file_objects"]["count"] == 1
            result["private_original"] = await migration_private_snapshot()
        return result
    finally:
        await engine.dispose()


class TelegramEgressDurableRollbackCheck:
    """Keep actual LOCAL callers' UNKNOWN/Console rows through exact CLI rollback."""

    async def test_deploy_rollback_preserves_console_unknown_receipts_and_wire_counter(
        self, egress_case, durable_local
    ):
        case, h = egress_case, durable_local
        result = await unknown_scenario(case, h, "finalize_after_commit")
        before = await durable_snapshot()
        assert len(case_events(case, "SEND_EFFECT")) == 1
        write_json(
            case.directory / "durable-before.json",
            {
                "case": case.identity,
                "database": before,
                "wire_counter": 1,
                "message_id": str(result.message_id),
                "status": "UNKNOWN",
            },
        )
        # The host now performs the actual disabled deploy / rollback commands.
        # Fixtures remain open until the separate read-only after command agrees.
        async with asyncio.timeout(180):
            release = case.directory / "durable-release.json"
            while not release.exists():
                await asyncio.sleep(0.1)
        assert read_json(release) == {"case": case.identity, "verified": True}
        await assert_durable_console(h)
        assert await durable_snapshot() == before
        assert (await delivery(h, result.message_id))["status"] == "UNKNOWN"
        assert len(case_events(case, "SEND_EFFECT")) == 1
        record_pass(
            case,
            "E05",
            "DEPLOY_ROLLBACK_PRESERVES_CANONICAL_UNKNOWN_CONSOLE_RECEIPTS",
            lifecycle=os.environ["ASM_EGRESS_LIFECYCLE"],
            database_identity=before["identity"],
            database_sha256=before["sha256"],
            reviewed_mismatch_rejected=True,
            persistent_console_session=True,
            wire_counter=1,
        )


async def durable_after():
    directory = fixture_directory()
    before = read_json(directory / "durable-before.json")
    assert re.fullmatch(r"[0-9a-f]{32}", before["case"])
    current = await durable_snapshot()
    case = SimpleNamespace(directory=directory, identity=before["case"])
    counter = len(case_events(case, "SEND_EFFECT"))
    after = {
        "case": case.identity,
        "database": current,
        "wire_counter": counter,
        "message_id": before["message_id"],
        "status": "UNKNOWN",
    }
    write_json(directory / "durable-after.json", after)
    assert after == before, "E05_CANONICAL_DURABLE_STATE_OR_COUNTER_CHANGED"
    write_json(directory / "durable-release.json", {"case": case.identity, "verified": True})
    print("E05_DURABLE_UNKNOWN_CONSOLE_RECEIPTS_PRESERVED_PASS", flush=True)


async def serve():
    directory = fixture_directory()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(directory / "server.pem", directory / "server.key")
    context.set_alpn_protocols(["h2", "http/1.1"])
    names = {}

    def remember_sni(connection, name, _context):
        names[id(connection)] = name

    context.set_servername_callback(remember_sni)

    async def response(writer, raw, *, status=b"200 OK", extra=b""):
        writer.write(
            b"HTTP/1.1 "
            + status
            + b"\r\nConnection: close\r\nContent-Length: "
            + str(len(raw)).encode()
            + b"\r\n"
            + extra
            + b"\r\n"
            + raw
        )
        await writer.drain()

    async def handle(reader, writer):
        case = None
        stage = "header"
        ssl_object = writer.get_extra_info("ssl_object")
        try:
            try:
                header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 8)
            except (asyncio.IncompleteReadError, TimeoutError) as error:
                # REALITY's cover handshake and negative TLS probes need no HTTP.
                append_event(
                    directory,
                    {"stage": stage, "error": type(error).__name__},
                    filename="wire-stages.jsonl",
                )
                return
            assert len(header) <= 16384
            stage = "scenario"
            state = read_json(directory / "scenario.json")
            case, mode = state["case"], state["mode"]
            assert re.fullmatch(r"[a-f0-9]{32}", case) and mode in MODES
            stage = "header_fields"
            method, path, _ = header.split(b"\r\n", 1)[0].decode().split(" ")
            headers = {}
            for line in header.split(b"\r\n")[1:]:
                if b":" in line:
                    key, value = line.split(b":", 1)
                    headers[key.decode().lower()] = value.strip().decode()
            length = int(headers.get("content-length", "0"))
            assert 0 <= length <= 16384
            stage = "body"
            body = await asyncio.wait_for(reader.readexactly(length), 5)
            stage = "wire_identity"
            peer = writer.get_extra_info("peername")[0]
            sni = names.get(id(ssl_object))
            assert peer == os.environ["ASM_EGRESS_PEER_IP"]
            assert sni == headers.get("host") == "api.telegram.org"
            stage = "operation"
            if path == "/file/bot" + TOKEN + "/photos/file_77.jpg":
                operation = "download"
                assert method == "GET" and body == b""
            else:
                prefix = "/bot" + TOKEN + "/"
                assert path.startswith(prefix) and method == "POST"
                operation = path[len(prefix) :]
                assert operation in {"getMe", "getBusinessConnection", "getFile", "sendMessage"}
            append_event(
                directory,
                dict(
                    case=case,
                    event="REQUEST",
                    operation=operation,
                    peer=peer,
                    sni=sni,
                    host=headers["host"],
                ),
            )
            if operation == "getMe":
                assert json.loads(body) == {}
                result = {"id": BOT, "is_bot": True, "username": "synthetic_fixture_bot"}
            elif operation == "getBusinessConnection":
                assert json.loads(body) == {"business_connection_id": EXTERNAL}
                result = business_connection()
            elif operation == "getFile":
                assert json.loads(body) == {"file_id": "telegram-photo"}
                result = {"file_id": "telegram-photo", "file_path": "photos/file_77.jpg"}
            elif operation == "sendMessage":
                assert json.loads(body) == dict(
                    business_connection_id=EXTERNAL, chat_id=str(CHAT), text="Wire exact 🎨"
                )
                append_event(directory, dict(case=case, event="SEND_EFFECT"))
                result = {
                    "message_id": 900,
                    "business_connection_id": EXTERNAL,
                    "chat": {"id": CHAT, "type": "private"},
                }
            else:
                result = None
            if (mode, operation) in {
                ("hold_readonly", "getMe"),
                ("hold_send", "sendMessage"),
                ("hold_media", "download"),
            }:
                stage = "fault_action"
                if mode == "hold_media":
                    raw = image_bytes("JPEG")
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "
                        + str(len(raw)).encode()
                        + b"\r\n\r\n"
                        + raw[:32]
                    )
                    await writer.drain()
                    append_event(directory, dict(case=case, event="MEDIA_PARTIAL"))
                stopped = await relay_action(directory, "stop")
                write_json(directory / ("stopped-" + case + ".json"), stopped)
                # No successful HTTP response: the relay really disappears after
                # the fsynced effect / partial response, before worker recovery.
                try:
                    await asyncio.wait_for(reader.read(), 12)
                except (OSError, TimeoutError):
                    pass
                return
            if operation == "download":
                stage = "media_response"
                if mode == "redirect":
                    await response(
                        writer,
                        b"",
                        status=b"302 Found",
                        extra=b"Location: https://off-origin.invalid/never\r\n",
                    )
                else:
                    raw = (
                        b"x" * (10 * 1024 * 1024 + 1)
                        if mode == "oversized"
                        else image_bytes("JPEG")
                    )
                    await response(writer, raw, extra=b"Content-Type: text/plain\r\n")
                return
            stage = "json_response"
            await response(
                writer,
                json.dumps({"ok": True, "result": result}).encode(),
                extra=b"Content-Type: application/json\r\n",
            )
        except (ConnectionError, ssl.SSLError):
            # Transport interruption and early oversized-body rejection are the
            # behavior under test. Scenario/HTTP assertion failures are separate.
            pass
        except Exception as error:
            append_event(
                directory,
                {"case": case, "stage": stage, "error": type(error).__name__},
                filename="wire-failures.jsonl",
            )
        finally:
            names.pop(id(ssl_object), None)
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass

    front = await asyncio.start_server(handle, "0.0.0.0", 443, ssl=context)
    cover = await asyncio.start_server(handle, "0.0.0.0", 8443, ssl=context)
    write_json(directory / "wire-ready.json", {"ready": True})
    async with front, cover:
        await asyncio.gather(front.serve_forever(), cover.serve_forever())


def material_ddl_operations(path):
    """Expand the checked-out migration source only; no connection/catalog claim."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("egress_ddl_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements = []
    module.op = SimpleNamespace(execute=statements.append)
    module.upgrade()
    return module, statements


def material_function_source(statement):
    match = re.fullmatch(
        r"CREATE(?: OR REPLACE)? FUNCTION ([\w.]+)\((.*?)\)\s+RETURNS\s+(.*?)\s+LANGUAGE (\w+)(.*?)\$\$(.*?)\$\$\s*;?\s*",
        statement.strip(),
        re.S | re.I,
    )
    if match is None:
        return None
    name, arguments, returns, language, attributes, body = match.groups()
    types = [
        arg.strip().split(None, 1)[1].split(" DEFAULT ", 1)[0].strip()
        for arg in arguments.split(",")
        if arg.strip()
    ]
    return {
        "signature": name + "(" + ",".join(types) + ")",
        "body": body,
        "name": name,
        "arity": len(types),
        "returns": returns.strip(),
        "language": language.lower(),
        "definer": "SECURITY DEFINER" in attributes.upper(),
        "strict": bool(re.search(r"\bSTRICT\b", attributes, re.I)),
        "volatility": "i"
        if "IMMUTABLE" in attributes.upper()
        else "s"
        if "STABLE" in attributes.upper()
        else "v",
    }


def material_sql_fields(body):
    """Finite source inventory lexer: commas inside SQL strings/expressions stay put."""
    depth, quoted, start, fields = 0, False, 0, []
    for index, char in enumerate(body):
        if char == "'":
            quoted = not quoted
        elif not quoted:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                fields.append(body[start:index].strip())
                start = index + 1
        assert depth >= 0, "MATERIAL_DDL_UNBALANCED"
    assert depth == 0 and not quoted, "MATERIAL_DDL_UNBALANCED"
    return [*fields, body[start:].strip()]


def material_source_profile():
    from test_m3_1_provenance_migrations import P_COLUMNS
    from test_m3_2_escalations_migrations import E_COLUMNS

    root = Path(__file__).resolve().parents[1]
    module, statements = material_ddl_operations(
        root / "migrations/versions/0012_message_provenance.py"
    )
    assert module.revision == "0012" and module.down_revision == "0011"
    columns = dict(E_COLUMNS)
    additions, changed = {}, {}
    for statement in statements:
        match = re.fullmatch(r"\s*CREATE TABLE ([\w.]+)\((.*)\)\s*", statement, re.S)
        if match:
            name, body = match.groups()
            fields = [
                field.split()[0]
                for field in material_sql_fields(body)
                if not re.match(r"^(PRIMARY|UNIQUE|FOREIGN|CHECK|CONSTRAINT)\b", field)
            ]
            assert name not in columns
            columns[name] = tuple(fields)
            additions[name] = tuple(fields)
        if material_function_source(statement) is None:
            for table, body in re.findall(r"ALTER TABLE ([\w.]+)\s+(.*?)(?:;|$)", statement, re.S):
                extra = tuple(re.findall(r"\bADD COLUMN ([a-z_]+)\b", body))
                if extra:
                    columns[table] += extra
                    changed[table] = changed.get(table, ()) + extra
    assert columns == P_COLUMNS, "MATERIAL_DDL_COLUMN_PROJECTION"
    assert set(additions) == set(module.TABLES) and len(additions) == 4
    assert len(changed) == 6 and sum(map(len, changed.values())) == 10
    functions = {}
    for path in sorted((root / "migrations/versions").glob("[0-9][0-9][0-9][0-9]_*.py")):
        assert path.name[:4] <= "0012", "MATERIAL_UNASSIGNED_REVISION"
        _, sql = material_ddl_operations(path)
        for statement in sql:
            definition = material_function_source(statement)
            if definition:
                functions[definition["signature"]] = definition
            for signature in re.findall(
                r"DROP FUNCTION\s+(?:IF EXISTS\s+)?([\w.]+\([^)]*\))", statement
            ):
                functions.pop(signature.replace(", ", ","), None)
    delta = {
        definition["signature"]: definition
        for statement in statements
        if (definition := material_function_source(statement)) is not None
    }
    new = set(module.PUBLIC_FUNCTIONS) | set(module.PRIVATE_FUNCTIONS)
    replaced = set(delta) - new
    assert len(new) == 23 and len(module.PUBLIC_FUNCTIONS) == 2 and len(replaced) == 17
    assert new <= set(delta) and len(functions) == 132, "MATERIAL_FUNCTION_INVENTORY"
    assert {
        f["name"].split(".")[1] + "(" + str(f["arity"]) + ")"
        for sig, f in delta.items()
        if sig in replaced
    } == set(module.ORIGINAL)
    return {
        "module": module,
        "statements": statements,
        "columns": columns,
        "new_columns": changed,
        "new_tables": additions,
        "functions": functions,
        "delta": delta,
        "new_functions": new,
        "replaced_functions": replaced,
    }


async def material_catalog_profile(c, *, predecessor_runtime=None):
    from test_m3_1_control_migrations import definitions, digest
    from test_m3_1_provenance_migrations import assert_schema

    await assert_schema(c)
    profile = material_source_profile()
    expected_oids = set()
    runtime = {}
    for signature, source in profile["functions"].items():
        row = (
            (
                await c.execute(
                    text(
                        "SELECT p.oid,p.prosrc,p.proowner::regrole::text AS owner,p.prosecdef,p.provolatile,p.proisstrict,p.proconfig,l.lanname,"
                        "has_function_privilege('asm_runtime',p.oid,'EXECUTE') AS runtime,"
                        "EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) WHERE grantee=0) AS public "
                        "FROM pg_proc p JOIN pg_language l ON l.oid=p.prolang WHERE p.oid=CAST(:sig AS regprocedure)"
                    ),
                    {"sig": signature},
                )
            )
            .mappings()
            .one()
        )
        expected_oids.add(row["oid"])
        assert row["prosrc"] == source["body"], signature
        assert row["owner"] == "asm_migrator" and not row["public"], signature
        assert (row["prosecdef"], row["provolatile"], row["proisstrict"], row["lanname"]) == (
            source["definer"],
            source["volatility"],
            source["strict"],
            source["language"],
        ), signature
        assert row["proconfig"] == ["search_path=pg_catalog, pg_temp"], signature
        if signature in profile["delta"]:
            assert (
                await c.execute(
                    text(
                        "SELECT prorettype=to_regtype(:result) FROM pg_proc WHERE oid=CAST(:sig AS regprocedure)"
                    ),
                    {"result": source["returns"], "sig": signature},
                )
            ).scalar_one(), signature
        runtime[signature] = row["runtime"]
        if signature in profile["new_functions"]:
            assert row["runtime"] == (signature in profile["module"].PUBLIC_FUNCTIONS)
        elif predecessor_runtime is not None:
            assert row["runtime"] == predecessor_runtime[signature], signature
    actual_oids = set(
        (
            await c.execute(
                text(
                    "SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('app','platform') AND p.prokind='f'"
                )
            )
        ).scalars()
    )
    assert actual_oids == expected_oids, "MATERIAL_CATALOG_FUNCTION_SET"
    for table in profile["new_tables"]:
        row = (
            await c.execute(
                text(
                    "SELECT relowner::regrole::text,relrowsecurity,relforcerowsecurity,"
                    "has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),"
                    "EXISTS(SELECT 1 FROM aclexplode(coalesce(relacl,acldefault('r',relowner))) WHERE grantee=0) "
                    "FROM pg_class WHERE oid=CAST(:t AS regclass)"
                ),
                {"t": table},
            )
        ).one()
        assert row == ("asm_migrator", True, True, False, False)
        policies = (
            await c.execute(
                text(
                    "SELECT policyname,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname||'.'||tablename=:t"
                ),
                {"t": table},
            )
        ).all()
        assert policies == [("material_migrator", ["asm_migrator"], "ALL", "true", "true")]
    return {
        "catalog_sha256": digest(await definitions(c)),
        "runtime": runtime,
        "tables": 42,
        "functions": len(expected_oids),
    }


async def material_exact_columns(c, revision):
    from test_m3_1_provenance_migrations import P_COLUMNS
    from test_m3_2_escalations_migrations import E_COLUMNS

    assert revision in {"0011", "0012"}
    assert (
        await c.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() == revision
    rows = (
        await c.execute(
            text(
                "SELECT n.nspname||'.'||r.relname,array_agg(a.attname ORDER BY a.attnum) FROM pg_class r JOIN pg_namespace n ON n.oid=r.relnamespace JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped WHERE n.nspname IN ('app','platform') AND r.relkind='r' GROUP BY 1"
            )
        )
    ).all()
    assert {table: tuple(columns) for table, columns in rows} == (
        E_COLUMNS if revision == "0011" else P_COLUMNS
    )


async def material_no_backfill(c):
    from test_m3_1_provenance_migrations import migration

    for table in migration().TABLES:
        assert (await c.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
    for table, predicate in (
        ("platform.telegram_update_receipts", "codec IS NOT NULL"),
        ("platform.telegram_connection_state", "material_enabled"),
        (
            "platform.inbox_events",
            "material_result IS NOT NULL OR material_claim_token IS NOT NULL",
        ),
        ("app.conversation_turns", "material_invalidated"),
        (
            "app.conversation_turn_messages",
            "membership_form IS NOT NULL OR initial_suppression_id IS NOT NULL OR suppression_disposition IS NOT NULL",
        ),
        (
            "app.audit_events",
            "material_target_id IS NOT NULL OR material_source_receipt_id IS NOT NULL",
        ),
    ):
        assert (
            await c.execute(text(f"SELECT count(*) FROM {table} WHERE {predicate}"))
        ).scalar_one() == 0


async def material_used_refusal(c):
    """Execute actual downgrade until its SQLSTATE55000, proving no DDL ran."""
    from alembic import op
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import DBAPIError
    from test_m3_1_control_migrations import definitions, digest
    from test_m3_1_provenance_migrations import migration

    before, catalog = await canonical_fingerprint(c), digest(await definitions(c))
    executed = []
    module = migration()

    def execute(statement):
        executed.append(statement)
        return op.execute(statement)

    module.op = SimpleNamespace(execute=execute)
    with pytest.raises(DBAPIError) as caught:
        async with c.begin_nested():

            def down(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.downgrade()

            await c.run_sync(down)
    assert caught.value.orig.sqlstate == "55000"
    assert (
        len(executed) == 2
        and executed[0].startswith("LOCK TABLE")
        and executed[1].startswith("DO $$ BEGIN")
    )
    assert "RAISE EXCEPTION 'Material history prevents downgrade'" in executed[1]
    assert await canonical_fingerprint(c) == before and digest(await definitions(c)) == catalog
    return {
        "sqlstate": "55000",
        "before_ddl": True,
        "statements": 2,
        "tables": 42,
        "catalog_sha256": catalog,
        "fingerprint_sha256": digest(before),
    }


async def material_runtime_fingerprint(c, old):
    """Keep the exact accepted E timer transition rule during caller restarts.

    Migration/reversal and the before/after55000 check always hash all raw rows.
    Only across real runtime execution may these three precisely bound E timers
    move from READY to their canonical NOOP_TERMINAL; no history is deleted.
    """
    from test_m3_2_escalations_migrations import canonical_residual_timers

    timers = await canonical_residual_timers(c, old)
    result = await canonical_fingerprint(c)
    original = {row["id"]: row for row in old["timers"]}
    rows = (await c.execute(text("SELECT to_jsonb(j) FROM platform.messaging_jobs j"))).scalars()
    canonical = sorted(
        json.dumps(original.get(row["id"], row), sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    result["platform.messaging_jobs"] = {
        "count": len(canonical),
        "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
    }
    return result, timers


async def material_schema_controller(action, state_path):
    """Explicit disposable LOCAL only. E fixtures remain in their own unchanged image."""
    from sqlalchemy.pool import NullPool
    from test_m3_1_control_migrations import definitions, digest
    from test_m3_1_provenance_migrations import fingerprints

    target = make_url(os.environ["ASM_MIGRATION_DATABASE_URL"])
    assert (target.username, target.database, target.host, target.port) == (
        "asm_migrator",
        "asm_local",
        "postgres",
        5432,
    )
    assert os.environ["ASM_ENVIRONMENT"] == "LOCAL"
    path = Path(state_path)
    assert path.parent == Path("/state") and path.name == "material.json"
    saved = read_json(path) if path.exists() else {}
    migrator = create_async_engine(target, hide_parameters=True, poolclass=NullPool)

    async def identity(c):
        old = read_json(path.with_name("receipt.json"))
        rows = (
            await c.execute(
                text(
                    "SELECT w.id AS workspace,u.id AS owner,m.id AS unknown,m.projection_fingerprint,m.created_at "
                    "FROM platform.workspaces w CROSS JOIN platform.user_accounts u CROSS JOIN app.messages m "
                    "WHERE w.id=:ws AND u.id=:owner AND m.workspace_id=w.id AND m.id=:message"
                ),
                {
                    "ws": old["workspace"],
                    "owner": old["owner"],
                    "message": old["unknown"]["message_id"],
                },
            )
        ).all()
        assert len(rows) == 1
        return {**await database_identity(c), "seed_sha256": digest(rows)}

    async def private_original():
        old = read_json(path.with_name("receipt.json"))
        storage = S3ObjectStorage(StorageSettings())
        try:
            assert (
                hashlib.sha256(await storage.get(old["object"]["key"])).hexdigest()
                == old["object"]["sha256"]
            )
        finally:
            await storage.close()
        saved["private_original"] = "SHA256_MATCH"

    try:
        async with migrator.connect() as c:
            if action in {"pairing-before", "pairing-after"}:
                revision = (
                    await c.execute(text("SELECT version_num FROM platform.alembic_version"))
                ).scalar_one()
                await material_exact_columns(c, revision)
                proof = {
                    "revision": revision,
                    "rows": await canonical_fingerprint(c, revision=revision),
                    "catalog": digest(await definitions(c)),
                }
                if action == "pairing-before":
                    saved["pairing_before"] = proof
                else:
                    assert proof == saved.pop("pairing_before"), "MATERIAL_PAIRING_RUNTIME_EFFECT"
                    saved.setdefault("pairing_checks", []).append(
                        {"revision": revision, "rows_catalog_sha256": digest(proof)}
                    )
            elif action == "empty11":
                await material_exact_columns(c, "0011")
                saved["empty11_catalog"] = digest(await definitions(c))
                # Signatures come from source; preserve all predecessor execute grants.
                profile = material_source_profile()
                saved["runtime11"] = {}
                for sig in set(profile["functions"]) - profile["new_functions"]:
                    saved["runtime11"][sig] = (
                        await c.execute(
                            text(
                                "SELECT has_function_privilege('asm_runtime',CAST(:sig AS regprocedure),'EXECUTE')"
                            ),
                            {"sig": sig},
                        )
                    ).scalar_one()
            elif action == "empty12":
                saved["fresh12"] = await material_catalog_profile(
                    c, predecessor_runtime=saved["runtime11"]
                )
                await material_no_backfill(c)
            elif action == "empty11-check":
                await material_exact_columns(c, "0011")
                assert digest(await definitions(c)) == saved["empty11_catalog"]
            elif action == "seed11":
                await material_exact_columns(c, "0011")
                old = read_json(path.with_name("receipt.json"))
                assert old["populated_refusal"] == "PASS" and len(old["timers"]) == 3
                from test_m3_2_escalations_migrations import (
                    canonical_residual_timers,
                    phase_fingerprint,
                )

                await canonical_residual_timers(c, old)
                assert await phase_fingerprint(c, old) == old["protected11"]
                saved.update(
                    identity=await identity(c),
                    projection11=digest(await fingerprints(c, legacy=True)),
                    catalog11=digest(await definitions(c)),
                )
                await private_original()
            else:
                assert await identity(c) == saved["identity"], "MATERIAL_SEED_IDENTITY"
                revision = (
                    await c.execute(text("SELECT version_num FROM platform.alembic_version"))
                ).scalar_one()
                await material_exact_columns(c, revision)
                if action == "observe":
                    observed = {
                        **await identity(c),
                        "revision": revision,
                        "role": (await c.execute(text("SELECT current_user"))).scalar_one(),
                        "backend_pid": (
                            await c.execute(text("SELECT pg_backend_pid()"))
                        ).scalar_one(),
                        "reader_pid": os.getpid(),
                        "reader_namespace": os.readlink("/proc/self/ns/pid"),
                        "reader_start_ticks": int(
                            Path("/proc/self/stat").read_text().rpartition(")")[2].split()[19]
                        ),
                        "reader_boot_id": Path("/proc/sys/kernel/random/boot_id")
                        .read_text()
                        .strip(),
                    }
                    print(json.dumps(observed), flush=True)
                    return
                if action in {"check11", "check12"}:
                    assert revision == ("0011" if action == "check11" else "0012")
                    assert digest(await fingerprints(c, legacy=True)) == saved["projection11"]
                    if revision == "0011":
                        assert digest(await definitions(c)) == saved["catalog11"]
                    else:
                        assert (
                            await material_catalog_profile(
                                c, predecessor_runtime=saved["runtime11"]
                            )
                            == saved["fresh12"]
                        )
                        await material_no_backfill(c)
                    await private_original()
                elif action == "refuse":
                    assert revision == "0012"
                    protected, timers = await material_runtime_fingerprint(
                        c, read_json(path.with_name("receipt.json"))
                    )
                    assert digest(protected) == saved["protected12"]
                    saved["observed_timers"] = timers
                    saved["refusal"] = await material_used_refusal(c)
                    saved["populated_refusal"] = "PASS"
                    await private_original()
                elif action != "fresh":
                    raise AssertionError("EXPLICIT_MATERIAL_SCHEMA_PHASE_REQUIRED")
        if action == "fresh":
            old = read_json(path.with_name("receipt.json"))
            runtime = RuntimeDatabase(Settings())
            try:
                await runtime.check()
                kernel = MessagingDatabase(runtime.engine, environment="LOCAL")
                ingress = TelegramIngress(kernel, "123456789")
                value = {"update_id": 901234567}
                first = await ingress.ingest_update(value, uuid4())
                again = await ingress.ingest_update(value, uuid4())
                assert (
                    first.code == "ACCEPTED"
                    and again.code == "DUPLICATE"
                    and first.receipt_id == again.receipt_id
                )
                async with migrator.connect() as c:
                    row = (
                        await c.execute(
                            text(
                                "SELECT r.codec,p.material_enabled,p.workspace_id,p.codec FROM platform.telegram_update_receipts r JOIN platform.telegram_provenance p ON p.receipt_id=r.id WHERE r.id=:id"
                            ),
                            {"id": first.receipt_id},
                        )
                    ).one()
                    assert row == (2, False, None, 2)
                    from asm.conversations.turns import parse_snapshot

                    snapshots = (
                        (
                            await c.execute(
                                text(
                                    "SELECT turn_input FROM platform.messaging_jobs WHERE turn_input IS NOT NULL"
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert snapshots and all("schema_version" not in value for value in snapshots)
                    for value in snapshots:
                        parse_snapshot(value)
                    saved["saved_v1_reader"] = len(snapshots)
                from asm.messaging.http_models import MessageResponse

                async with runtime.tenancy.transaction(
                    AuthenticatedAccount(UUID(old["owner"])), UUID(old["workspace"]), uuid4()
                ) as unit:
                    page = await unit.messaging_messages_page(
                        UUID(old["conversation"]), 100, None, None
                    )
                    assert page
                    for row in page:
                        assert "current" in row
                        MessageResponse.model_validate(row)
                async with migrator.connect() as c:
                    protected, timers = await material_runtime_fingerprint(c, old)
                    saved["protected12"] = digest(protected)
                    saved["observed_timers"] = timers
                    assert (
                        await material_catalog_profile(c, predecessor_runtime=saved["runtime11"])
                        == saved["fresh12"]
                    )
                saved["fresh_v2_off"] = {
                    "receipt_id": str(first.receipt_id),
                    "codec": 2,
                    "material_enabled": False,
                }
            finally:
                await runtime.close()
        write_json(path, saved)
        print("MATERIAL_SCHEMA_" + action.upper() + "_PASS", flush=True)
    finally:
        await migrator.dispose()


class TestEgressMaterialCompatibility:
    async def test_current_0012_profile_v2_off_receipt_dto_and_snapshot(self, control):
        from asm.conversations.turns import consume, parse_snapshot
        from asm.messaging.http_models import MessageResponse
        from test_m2_3_db_postgres import BOT
        from test_m3_1_provenance_postgres import process, raw
        from test_m3_1_turns_postgres import seal, snapshot

        h = control
        async with h.migrator.connect() as c:
            await material_catalog_profile(c)
            await material_no_backfill(c)
        receipt, _, result = await process(h, raw())
        assert receipt.result_code == "QUEUED" and result.message_id
        proof = (
            await query(
                h,
                "SELECT r.codec,p.codec AS sidecar_codec,p.material_enabled FROM platform.telegram_update_receipts r JOIN platform.telegram_provenance p ON p.receipt_id=r.id WHERE r.id=:id",
                id=receipt.receipt_id,
            )
        )[0]
        assert proof == {"codec": 2, "sidecar_codec": 2, "material_enabled": False}
        assert not await query(h, "SELECT id FROM platform.message_material_targets")
        replay = await TelegramIngress(h.kernel, BOT).ingest_update(raw(), uuid4())
        assert replay.code == "DUPLICATE" and replay.receipt_id == receipt.receipt_id
        turn = (await query(h, "SELECT id,conversation_id FROM app.conversation_turns"))[0]
        await seal(h, turn["id"])
        claim, value = await snapshot(h, turn["id"])
        assert value.schema_version == 2
        decoded = parse_snapshot(value.model_dump(mode="json"))
        assert decoded == value and all(member.current.changed is False for member in value.members)
        await h.kernel.finish_turn(claim, consume(value))
        async with h.runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            page = await unit.messaging_messages_page(turn["conversation_id"], 10, None, None)
        assert len(page) == 1
        assert MessageResponse.model_validate(page[0]).current.changed is False

    @pytest.mark.parametrize(
        "used",
        [
            "codec-off",
            "enabled-gate",
            "target",
            "effect-audit",
            "suppression-member",
            "material-result",
            "invalidated-turn",
        ],
    )
    async def test_used_0012_refuses_before_ddl_and_preserves_all42(self, control, used):
        from test_m2_3_db_postgres import BOT
        from test_m3_1_provenance_postgres import process, raw

        h = control
        if used != "codec-off":
            await query(
                h,
                "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE connection_id=:id RETURNING connection_id",
                id=h.telegram_connection,
            )
        if used == "codec-off":
            await TelegramIngress(h.kernel, BOT).ingest_update(raw(), uuid4())
            witness = "SELECT count(*) AS n FROM platform.telegram_provenance WHERE NOT material_enabled AND codec=2"
        elif used == "enabled-gate":
            witness = "SELECT count(*) AS n FROM platform.telegram_connection_state WHERE material_enabled"
        elif used in {"target", "material-result"}:
            await process(h, raw(100002, kind="DELETE"))
            witness = (
                "SELECT count(*) AS n FROM platform.message_material_targets"
                if used == "target"
                else "SELECT count(*) AS n FROM platform.inbox_events WHERE material_result IS NOT NULL AND material_claim_token IS NOT NULL AND result_code='MATERIAL_PROCESSED'"
            )
        elif used == "suppression-member":
            await process(h, raw(100002, kind="EDIT", value="B"))
            await process(h, raw(photo="F"))
            witness = "SELECT count(*) AS n FROM platform.message_initial_suppressions s JOIN app.conversation_turn_messages m ON m.workspace_id=s.workspace_id AND m.initial_suppression_id=s.id WHERE m.membership_form='INITIAL_FOLD_SUPPRESSED'"
        else:
            await process(h, raw())
            await process(h, raw(100002, kind="DELETE"))
            witness = (
                "SELECT count(*) AS n FROM platform.message_material_effects e JOIN app.audit_events a ON a.workspace_id=e.workspace_id AND a.audit_event_id=e.audit_event_id WHERE a.event_type='MESSAGE_MATERIAL_CHANGED'"
                if used == "effect-audit"
                else "SELECT count(*) AS n FROM app.conversation_turns WHERE material_invalidated"
            )
        assert (await query(h, witness))[0]["n"] > 0, used
        async with h.migrator.begin() as c:
            proof = await material_used_refusal(c)
            assert proof["before_ddl"] and proof["tables"] == 42
        await h.runtime.check()


def material_schema_cli(action, state_path):
    try:
        if action in {"upgrade-lost-result", "downgrade-lost-result"}:
            from alembic import command as alembic_command
            from alembic.config import Config

            assert os.environ["ASM_ENVIRONMENT"] == "LOCAL"
            target = make_url(os.environ["ASM_MIGRATION_DATABASE_URL"])
            assert (target.username, target.database, target.host, target.port) == (
                "asm_migrator",
                "asm_local",
                "postgres",
                5432,
            )
            path = Path(state_path)
            assert path == Path("/state/material.json")
            saved = read_json(path)
            assert "identity" in saved
            if action == "upgrade-lost-result":
                alembic_command.upgrade(Config("alembic.ini"), "0012")
            else:
                alembic_command.downgrade(Config("alembic.ini"), "0011")
            saved["lost_result_process"] = {
                "pid": os.getpid(),
                "namespace": os.readlink("/proc/self/ns/pid"),
                "start_ticks": int(
                    Path("/proc/self/stat").read_text().rpartition(")")[2].split()[19]
                ),
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            }
            write_json(path, saved)
            print("MATERIAL_MIGRATION_COMMITTED_RESULT_LOST", flush=True)
            os._exit(86)
        asyncio.run(material_schema_controller(action, state_path))
    except BaseException as error:
        import traceback

        write_json(
            Path(state_path).with_name("controller-failure.json"),
            {
                "action": action,
                "type": type(error).__name__,
                "sqlstate": getattr(getattr(error, "orig", None), "sqlstate", None),
                "frames": [
                    {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                    for f in traceback.extract_tb(error.__traceback__)
                ],
            },
        )
        raise


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--material-schema-phase":
        material_schema_cli(sys.argv[2], sys.argv[3])
    elif sys.argv[1:] == ["--serve"]:
        asyncio.run(serve())
    elif sys.argv[1:] == ["--durable-receipt", "before"]:
        raise SystemExit(
            pytest.main(
                [
                    "-q",
                    "--tb=short",
                    "-o",
                    "python_classes=TelegramEgressDurableRollbackCheck",
                    __file__,
                ]
            )
        )
    elif sys.argv[1:] == ["--durable-receipt", "after"]:
        try:
            asyncio.run(durable_after())
        except Exception as error:
            print("E05_DURABLE_RECEIPT_FAILURE_" + type(error).__name__, flush=True)
            raise SystemExit(1) from None
    else:
        raise SystemExit("TEST_ONLY_ARGUMENTS_REQUIRED")
