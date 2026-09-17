"""Exact Host authority regressions for the real authentication boundary."""

import json

import pytest
from asm.auth.config import AuthSettings
from asm.auth.crypto import RateLimiter
from asm.auth.http import AuthBoundary


class MarkerApp:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, scope, receive, send) -> None:
        self.calls += 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


async def request(
    settings: AuthSettings,
    host_headers: list[bytes],
    *,
    path: str = "/api/v1/auth/session",
    scheme: str = "http",
    extra_headers: list[tuple[bytes, bytes]] | None = None,
):
    marker = MarkerApp()
    boundary = AuthBoundary(marker, settings, RateLimiter(60))
    sent = []
    messages = iter([{"type": "http.request", "body": b"", "more_body": False}])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    headers = [(b"host", value) for value in host_headers]
    headers.extend(extra_headers or [])
    await boundary(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = {key.lower(): value for key, value in start["headers"]}
    body = b"".join(message.get("body", b"") for message in sent)
    return marker, start["status"], response_headers, body


def assert_rejected(result) -> None:
    marker, status, headers, body = result
    assert marker.calls == 0
    assert status == 403
    assert headers[b"cache-control"] == b"no-store"
    assert b"set-cookie" not in headers
    assert json.loads(body) == {"error": {"code": "ORIGIN_DENIED"}}


@pytest.mark.asyncio
async def test_configured_non_default_port_is_exact_original_regression():
    settings = AuthSettings(auth_origins=("http://localhost:8000",))
    marker, status, _, _ = await request(settings, [b"localhost:8000"])
    assert (marker.calls, status) == (1, 204)
    assert_rejected(await request(settings, [b"localhost:9999"]))
    assert_rejected(await request(settings, [b"localhost"]))


@pytest.mark.asyncio
async def test_compose_proxy_exception_is_only_api_8000_and_origin_stays_separate():
    settings = AuthSettings(auth_origins=("http://localhost:8000",))
    marker, status, _, _ = await request(settings, [b"api:8000"])
    assert (marker.calls, status) == (1, 204)
    assert_rejected(await request(settings, [b"api:9999"]))
    assert_rejected(await request(settings, [b"api"]))
    assert_rejected(
        await request(
            settings,
            [b"api:8000"],
            extra_headers=[(b"origin", b"https://attacker.invalid")],
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin,scheme,implicit,explicit,wrong",
    [
        ("http://localhost", "http", b"localhost", b"localhost:80", b"localhost:443"),
        (
            "https://example.test",
            "https",
            b"example.test",
            b"example.test:443",
            b"example.test:80",
        ),
    ],
)
async def test_default_ports_are_equivalent(origin, scheme, implicit, explicit, wrong):
    settings = AuthSettings(auth_origins=(origin,))
    for authority in (implicit, explicit):
        marker, status, _, _ = await request(settings, [authority], scheme=scheme)
        assert (marker.calls, status) == (1, 204)
    assert_rejected(await request(settings, [wrong], scheme=scheme))


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/auth/session", "/api/v1/workspaces/known/businesses"])
async def test_same_hostname_distinguishes_each_configured_port_on_protected_paths(path):
    settings = AuthSettings(auth_origins=("http://localhost:8000", "http://localhost:8080"))
    for authority in (b"localhost:8000", b"localhost:8080"):
        marker, status, _, _ = await request(settings, [authority], path=path)
        assert (marker.calls, status) == (1, 204)
    assert_rejected(await request(settings, [b"localhost:8001"], path=path))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hosts",
    [
        [],
        [b"localhost:8000", b"localhost:8000"],
        [b"localhost:8000", b"localhost:8080"],
        [b"localhost:"],
        [b"localhost:not-a-port"],
        [b"localhost:65536"],
        [b"localhost:8000:extra"],
    ],
)
async def test_absent_duplicate_and_malformed_host_fail_closed(hosts):
    assert_rejected(await request(AuthSettings(auth_origins=("http://localhost:8000",)), hosts))


@pytest.mark.asyncio
async def test_bracketed_ipv6_and_hostname_case_are_normalized_without_changing_port():
    ipv6 = AuthSettings(auth_origins=("http://[::1]:8000",))
    marker, status, _, _ = await request(ipv6, [b"[::1]:8000"])
    assert (marker.calls, status) == (1, 204)
    assert_rejected(await request(ipv6, [b"[::1]:8001"]))

    named = AuthSettings(auth_origins=("https://example.test",))
    marker, status, _, _ = await request(named, [b"EXAMPLE.TEST:443"], scheme="https")
    assert (marker.calls, status) == (1, 204)


@pytest.mark.asyncio
async def test_origin_and_forwarded_headers_never_rescue_wrong_authority():
    settings = AuthSettings(auth_origins=("http://localhost:8000",))
    assert_rejected(
        await request(
            settings,
            [b"localhost:9999"],
            extra_headers=[
                (b"origin", b"http://localhost:8000"),
                (b"forwarded", b"host=localhost:8000;proto=http"),
                (b"x-forwarded-host", b"localhost:8000"),
                (b"x-forwarded-port", b"8000"),
                (b"x-forwarded-proto", b"http"),
            ],
        )
    )
