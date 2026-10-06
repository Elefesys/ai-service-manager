"""ENV04-05: cold, verified TLS sockets; no mocked I/O or shortened deadlines.

Only the TEST CA and TCP destination are injected. HTTP Host/SNI stays official;
the real HTTPX/httpcore connect, TLS, pool, read/write and cancellation paths run.
Monotonic timing tolerance is -0.2/+1.0s for timeout scheduling on a loaded runner.
The successful 3s TLS handshake must still finish its readonly HTTP call below 5s.
Every case owns a new client/peer; accepted TCP and HTTP calls count all attempts.
"""

import asyncio
import json
import socket
import ssl
import subprocess
import time
from contextlib import asynccontextmanager, suppress
from types import SimpleNamespace

import httpx
import pytest
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind
from asm.telegram.client import TelegramClient, TelegramError
from httpcore import AsyncNetworkBackend
from httpcore._backends.anyio import AnyIOBackend
from test_m2_3_transport import BOT, config, fetch_permit, permit


@pytest.fixture(scope="session")
def connect_tls_material(tmp_path_factory):
    directory = tmp_path_factory.mktemp("connect-test-ca")

    def openssl(*args):
        subprocess.run(
            ["openssl", *args], cwd=directory, check=True, capture_output=True, timeout=10
        )

    # Same strict X.509 extensions as the existing real-relay TEST CA. All keys
    # are generated in the disposable fixture, never product/runtime trust.
    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-subj",
        "/CN=Connect budget TEST CA",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
    )
    for name, hostname in (("server", "api.telegram.org"), ("wrong", "wrong.test.invalid")):
        openssl(
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=" + hostname,
            "-keyout",
            name + ".key",
            "-out",
            name + ".csr",
        )
        (directory / "extensions").write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            f"subjectAltName=DNS:{hostname}\nextendedKeyUsage=serverAuth\n"
            "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
        )
        openssl(
            "x509",
            "-req",
            "-in",
            name + ".csr",
            "-CA",
            "ca.pem",
            "-CAkey",
            "ca.key",
            "-CAcreateserial",
            "-out",
            name + ".pem",
            "-days",
            "1",
            "-extfile",
            "extensions",
        )
        openssl(
            "verify",
            "-x509_strict",
            "-purpose",
            "sslserver",
            "-verify_hostname",
            hostname,
            "-CAfile",
            "ca.pem",
            name + ".pem",
        )
    return directory


@asynccontextmanager
async def tls_peer(material, *, delay=0, mode="valid", certificate="server"):
    """Delay raw accepted TCP before starting TLS, not after receiving HTTP."""
    loop = asyncio.get_running_loop()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.setblocking(False)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(material / (certificate + ".pem"), material / (certificate + ".key"))
    state = SimpleNamespace(
        port=listener.getsockname()[1],
        accepted=0,
        closed=0,
        requests=[],
        sni=[],
        handshakes=[],
        tasks=set(),
        failures=[],
        received=asyncio.Event(),
        chunks=0,
    )
    context.set_servername_callback(lambda _socket, name, _context: state.sni.append(name))

    async def handle(sock):
        started = time.monotonic()
        transport = None
        try:
            if mode == "stall_tls":
                # Consume ClientHello, send no TLS bytes; observe peer close.
                while await loop.sock_recv(sock, 65536):
                    state.received.set()
                return
            await asyncio.sleep(delay)
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            transport, _ = await loop.connect_accepted_socket(
                lambda: protocol, sock, ssl=context, ssl_handshake_timeout=6
            )
            state.handshakes.append(time.monotonic() - started)
            writer = asyncio.StreamWriter(transport, protocol, reader, loop)
            head = await reader.readuntil(b"\r\n\r\n")
            lines = head.split(b"\r\n")
            headers = dict(line.split(b":", 1) for line in lines[1:] if b":" in line)
            assert headers[b"Host"].strip() == b"api.telegram.org"
            length = int(headers.get(b"Content-Length", b"0"))
            await reader.readexactly(length)
            operation = lines[0].split(b" ")[1].rsplit(b"/", 1)[-1].decode()
            state.requests.append(operation)
            state.received.set()
            if operation == "getFile":
                result = {"file_id": "opaque-photo", "file_path": "photos/connect.jpg"}
            else:
                result = {"id": BOT, "is_bot": True}
                if mode == "stall_response":
                    assert await reader.read() == b""
                    return
                if mode == "trickle":
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n")
                    while True:
                        writer.write(b" ")
                        await writer.drain()
                        state.chunks += 1
                        await asyncio.sleep(0.2)  # Activity is always below the 5s read timeout.
            body = json.dumps({"ok": True, "result": result}).encode()
            status = b"302 Found" if mode == "redirect" else b"200 OK"
            writer.write(
                b"HTTP/1.1 " + status + b"\r\nConnection: close\r\n"
                b"Location: https://api.telegram.org/forbidden-redirect\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()
        except (ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
            pass  # Expected client timeout/cancel/certificate rejection closes the socket.
        except Exception as error:
            state.failures.append(type(error).__name__)
        finally:
            if transport is not None:
                transport.abort()
            sock.close()
            state.closed += 1

    async def accept():
        while True:
            sock, _ = await loop.sock_accept(listener)
            state.accepted += 1
            task = asyncio.create_task(handle(sock))
            state.tasks.add(task)
            task.add_done_callback(state.tasks.discard)

    accepting = asyncio.create_task(accept())
    try:
        yield state
    finally:
        accepting.cancel()
        with suppress(asyncio.CancelledError):
            await accepting
        listener.close()
        for task in tuple(state.tasks):
            task.cancel()
        await asyncio.gather(*tuple(state.tasks), return_exceptions=True)
        assert not state.failures, state.failures
        assert state.closed == state.accepted


def tls_client(material, peer, *, trusted=True):
    context = ssl.create_default_context(cafile=str(material / "ca.pem") if trusted else None)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED

    class LocalDestination(AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            assert host == "api.telegram.org" and port == 443
            return await AnyIOBackend().connect_tcp("127.0.0.1", peer.port, **kwargs)

    # Production construction keeps its real limits/retry policy. The TEST-only
    # seam replaces CA and destination; neither deadlines nor wire I/O are mocked.
    transport = httpx.AsyncHTTPTransport(
        verify=context,
        retries=0,
        trust_env=False,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
    )
    transport._pool._network_backend = LocalDestination()
    client = TelegramClient(config(), transport=transport)
    assert client._origin == "https://api.telegram.org"
    return client


async def released(client, peer):
    # Observe cleanup before test teardown cancels server tasks or closes client.
    assert client._http._transport._pool.connections == []
    try:
        async with asyncio.timeout(2):
            while peer.closed != peer.accepted:
                await asyncio.sleep(0.01)
    except TimeoutError:
        pytest.fail(
            f"TCP_PEER_STILL_OPEN: accepted={peer.accepted} closed={peer.closed}; "
            "HTTPX pool empty before client/server teardown"
        )
    assert all(task.done() for task in peer.tasks)


def elapsed_timeout(start, seconds):
    elapsed = time.monotonic() - start
    assert seconds - 0.2 <= elapsed <= seconds + 1.0, (seconds, elapsed)
    return elapsed


async def test_cold_verified_tls_over_two_seconds_finishes_readonly_under_five(
    connect_tls_material,
):
    async with tls_peer(connect_tls_material, delay=3) as peer:
        client = tls_client(connect_tls_material, peer)
        try:
            started = time.monotonic()
            try:
                result = await client.get_me()
            except TelegramError as error:
                print(
                    f"COLD_TLS_READONLY_FAIL elapsed={time.monotonic() - started:.3f}s "
                    f"code={error.code.value} definitely_unsent={error.definitely_unsent} "
                    f"tcp={peer.accepted} tls={len(peer.handshakes)} http={len(peer.requests)}"
                )
                raise
            assert result == str(BOT)
            elapsed = time.monotonic() - started
            assert 3 <= elapsed < 5, elapsed
            assert len(peer.handshakes) == 1 and 3 <= peer.handshakes[0] < 5
            assert peer.accepted == 1 and peer.requests == ["getMe"]
            assert peer.sni == ["api.telegram.org"]
            await released(client, peer)
            print(
                f"COLD_TLS_READONLY_PASS handshake={peer.handshakes[0]:.3f}s total={elapsed:.3f}s attempts=1"
            )
        finally:
            await client.aclose()


async def test_default_limits_and_no_environment_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent-test-ca")
    client = TelegramClient(config())
    try:
        assert client._http.timeout == httpx.Timeout(connect=5, pool=2, read=5, write=5)
        assert not client._http.follow_redirects and not client._http._trust_env
        assert client._http._mounts == {}
        pool = client._http._transport._pool
        assert pool._max_connections == pool._max_keepalive_connections == 4
        assert pool._retries == 0
        assert pool._ssl_context.check_hostname
        assert pool._ssl_context.verify_mode == ssl.CERT_REQUIRED
    finally:
        await client.aclose()


@pytest.mark.parametrize("mode", ["stall_tls", "stall_response"])
async def test_stalled_readonly_total_deadline_and_release(connect_tls_material, mode):
    async with tls_peer(connect_tls_material, mode=mode) as peer:
        client = tls_client(connect_tls_material, peer)
        try:
            started = time.monotonic()
            with pytest.raises(TelegramError) as error:
                await client.get_me()
            elapsed_timeout(started, 5)
            assert error.value.code == Code.DEPENDENCY_TIMEOUT
            assert not error.value.definitely_unsent  # Outer timeout proves no wire phase.
            assert peer.accepted == 1
            assert peer.requests == ([] if mode == "stall_tls" else ["getMe"])
            await released(client, peer)
        finally:
            await client.aclose()


@pytest.mark.parametrize("operation,budget", [("readonly", 5), ("send", 10), ("image", 20)])
async def test_trickle_does_not_renew_wall_deadline(connect_tls_material, operation, budget):
    # For readonly/send, TLS itself takes 3s inside the SAME wall budget.
    async with tls_peer(
        connect_tls_material, mode="trickle", delay=0 if operation == "image" else 3
    ) as peer:
        client = tls_client(connect_tls_material, peer)
        try:
            started = time.monotonic()
            if operation == "send":
                assert (await client.send(permit())).kind == OutcomeKind.UNKNOWN
            elif operation == "readonly":
                with pytest.raises(TelegramError) as error:
                    await client.get_me()
                assert error.value.code == Code.DEPENDENCY_TIMEOUT
                assert not error.value.definitely_unsent
            else:
                with pytest.raises(MessagingError, match="DEPENDENCY_TIMEOUT"):
                    _ = [chunk async for chunk in client.open_image(fetch_permit())]
            elapsed_timeout(started, budget)
            expected = (
                ["getFile", "connect.jpg"]
                if operation == "image"
                else ["getMe" if operation == "readonly" else "sendMessage"]
            )
            assert peer.requests == expected and peer.accepted == len(expected)
            assert peer.chunks >= 5
            await released(client, peer)
        finally:
            await client.aclose()


@pytest.mark.parametrize("mode", ["stall_tls", "stall_response"])
async def test_explicit_cancellation_closes_real_socket(connect_tls_material, mode):
    async with tls_peer(connect_tls_material, mode=mode) as peer:
        client = tls_client(connect_tls_material, peer)
        task = asyncio.create_task(client.send(permit()))
        try:
            await asyncio.wait_for(peer.received.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await released(client, peer)
            assert peer.accepted == 1
            assert peer.requests == ([] if mode == "stall_tls" else ["sendMessage"])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await client.aclose()


@pytest.mark.parametrize(
    "mode,kind",
    [("stall_tls", OutcomeKind.NOT_SENT_RETRYABLE), ("stall_response", OutcomeKind.UNKNOWN)],
)
async def test_send_phase_timeout_preserves_proven_unsent_boundary(
    connect_tls_material, mode, kind
):
    async with tls_peer(connect_tls_material, mode=mode) as peer:
        client = tls_client(connect_tls_material, peer)
        try:
            started = time.monotonic()
            assert (await client.send(permit())).kind == kind
            elapsed_timeout(started, 5)  # Connect/read phase, inside unchanged 10s send budget.
            assert peer.accepted == 1
            assert peer.requests == ([] if mode == "stall_tls" else ["sendMessage"])
            await released(client, peer)
        finally:
            await client.aclose()


@pytest.mark.parametrize("certificate,trusted", [("wrong", True), ("server", False)])
async def test_wrong_hostname_or_untrusted_certificate_never_reaches_http(
    connect_tls_material, certificate, trusted
):
    async with tls_peer(connect_tls_material, certificate=certificate) as peer:
        client = tls_client(connect_tls_material, peer, trusted=trusted)
        try:
            with pytest.raises(TelegramError) as error:
                await client.get_me()
            assert error.value.definitely_unsent and error.value.code == Code.DEPENDENCY_UNAVAILABLE
            assert peer.accepted == 1 and peer.requests == []
            assert peer.sni == ["api.telegram.org"]
            await released(client, peer)
        finally:
            await client.aclose()


async def test_redirect_is_not_followed_on_actual_wire(connect_tls_material):
    async with tls_peer(connect_tls_material, mode="redirect") as peer:
        client = tls_client(connect_tls_material, peer)
        try:
            assert (await client.send(permit())).kind == OutcomeKind.UNKNOWN
            assert peer.requests == ["sendMessage"] and peer.accepted == 1
            await released(client, peer)
        finally:
            await client.aclose()


async def test_real_pool_wait_two_seconds_and_four_connection_limit(connect_tls_material):
    async with tls_peer(connect_tls_material, mode="stall_response") as peer:
        client = tls_client(connect_tls_material, peer)
        tasks = [asyncio.create_task(client.send(permit())) for _ in range(4)]
        try:
            async with asyncio.timeout(2):
                while len(peer.requests) != 4:
                    await asyncio.sleep(0.01)
            started = time.monotonic()
            outcome = await client.send(permit())
            elapsed_timeout(started, 2)
            assert outcome.kind == OutcomeKind.NOT_SENT_RETRYABLE
            assert peer.accepted == 4 and peer.requests == ["sendMessage"] * 4
            for task in tasks:
                task.cancel()
            assert all(
                isinstance(result, asyncio.CancelledError)
                for result in await asyncio.gather(*tasks, return_exceptions=True)
            )
            await released(client, peer)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await client.aclose()
