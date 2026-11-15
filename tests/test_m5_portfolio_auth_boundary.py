"""Exact upload HTTP boundary regression checks; endpoint stubs are UNIT only."""

import asyncio
import hashlib
import io
import json
import random
from time import monotonic
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from asm.auth.config import AuthSettings
from asm.auth.crypto import RateLimiter, csrf_value, new_token
from asm.auth.http import AuthBoundary, install_auth, mutation_token
from asm.auth.models import AuthCode, AuthError
from asm.auth.service import AuthService
from asm.files.validation import decode_image
from fastapi import FastAPI
from PIL import Image
from starlette.requests import Request

W = "10000000-0000-0000-0000-000000000001"
B = "20000000-0000-0000-0000-000000000001"
A = "aaaaaaaa-0000-0000-0000-000000000001"
V = "bbbbbbbb-0000-0000-0000-000000000001"
U = "cccccccc-0000-0000-0000-000000000001"
PATH = (
    f"/api/v1/workspaces/{W}/businesses/{B}/portfolio/assets/{A}/versions/{V}/uploads/{U}/content"
)
MAX = 10_485_760
SETTINGS = AuthSettings(auth_origins=("http://localhost:8000",))


@pytest.mark.parametrize(
    "origin,expected", [("http://localhost:8000", 200), ("https://evil.invalid", 400)]
)
async def test_existing_cors_admits_put_only_for_exact_allowed_origin(origin, expected):
    app = FastAPI()
    # Preflight must neither call the service nor consume an upload body.
    install_auth(app, cast(AuthService, object()), SETTINGS)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000"
    ) as client:
        result = await client.options(
            PATH,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token,Idempotency-Key",
            },
        )
    assert result.status_code == expected
    if expected == 200:
        assert result.headers["access-control-allow-origin"] == origin
        assert result.headers["access-control-allow-credentials"] == "true"
        assert "PUT" in result.headers["access-control-allow-methods"].split(", ")
    else:
        assert "access-control-allow-origin" not in result.headers


async def dispatch(
    chunks,
    *,
    path=PATH,
    method="PUT",
    mime="image/png",
    lengths="auto",
    raw_path=None,
    query=b"",
    host=b"localhost:8000",
    origin=b"http://localhost:8000",
    cookie=True,
    csrf=True,
    extra=(),
    deny_before_read=None,
    validate_pixels=False,
    delays=(),
    settings=SETTINGS,
    limiter=None,
):
    state = SimpleNamespace(calls=0, reads=0, completed=False, manifest=None)
    token = new_token()
    headers = [(b"host", host)]
    if origin is not None:
        headers.append((b"origin", origin))
    if mime is not None:
        headers.append((b"content-type", mime.encode()))
    if cookie:
        headers.append((b"cookie", f"{settings.auth_cookie_name}={token}".encode()))
    if csrf is not None:
        headers.append((b"x-csrf-token", (csrf_value(token) if csrf else "x" * 64).encode()))
    if lengths == "auto":
        lengths = [str(sum(len(c) for c in chunks)).encode()]
    if lengths is not None:
        headers.extend((b"content-length", n) for n in lengths)
    headers.extend(extra)
    sent = []

    async def receive():
        index = state.reads
        state.reads += 1
        if index < len(delays):
            await asyncio.sleep(delays[index])
        if index >= len(chunks):
            return {"type": "http.disconnect"}
        return {
            "type": "http.request",
            "body": chunks[index],
            "more_body": index < len(chunks) - 1,
        }

    async def endpoint(scope, receive, send):
        state.calls += 1
        request = Request(scope, receive)
        mutation_token(request, settings)
        # Explicit unit stub for a denied endpoint, not a fake live OWNER check.
        if deny_before_read is not None:
            raise AuthError(
                AuthCode.SESSION_REQUIRED if deny_before_read == 401 else AuthCode.CSRF_REJECTED,
                deny_before_read,
            )
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
        if validate_pixels:
            state.manifest = decode_image(bytes(data))
        state.completed = True
        body = json.dumps({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}).encode()
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": body})

    async def send(message):
        sent.append(message)

    started = monotonic()
    await AuthBoundary(endpoint, settings, limiter or RateLimiter(60))(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode() if raw_path is None else raw_path,
            "query_string": query,
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 8000),
        },
        receive,
        send,
    )
    start = next(m for m in sent if m["type"] == "http.response.start")
    state.status = start["status"]
    state.headers = dict(start["headers"])
    state.body = b"".join(m.get("body", b"") for m in sent)
    state.elapsed = monotonic() - started
    assert state.headers[b"cache-control"] == b"no-store"
    assert state.headers[b"x-content-type-options"] == b"nosniff"
    return state


async def test_exact_upload_streams_real_large_png_and_keeps_pixels():
    image = Image.frombytes("RGB", (64, 64), random.Random(7).randbytes(64 * 64 * 3))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    raw = buf.getvalue()
    assert 4096 < len(raw) < MAX
    r = await dispatch([raw[:7000], raw[7000:]], validate_pixels=True)
    assert r.status == 201 and r.completed and r.reads == 2
    assert r.manifest.sha256 == hashlib.sha256(raw).hexdigest()
    assert r.manifest.mime_type == "image/png"


@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp"])
async def test_exact_binary_mime_admission_framing_only(mime):
    r = await dispatch([b"x" * 5000], mime=mime)
    assert r.status == 201 and r.completed


async def test_exact_maximum_byte_framing_is_accepted_without_raising_limit():
    r = await dispatch([b"x" * (MAX // 2), b"x" * (MAX // 2)])
    assert r.status == 201 and json.loads(r.body)["bytes"] == MAX


async def test_over_limit_declared_length_is_rejected_before_receiving():
    r = await dispatch([b""], lengths=[str(MAX + 1).encode()])
    assert r.status == 413 and r.reads == 0 and r.calls == 0


async def test_chunked_actual_byte_overflow_is_rejected():
    r = await dispatch([b"x" * MAX, b"x"], lengths=None)
    assert r.status == 413 and not r.completed


@pytest.mark.parametrize("lengths", [[b"5", b"5"], [b"abc"], [b"-1"], [b"5.0"], [b"\xff"]])
async def test_ambiguous_or_invalid_content_length_is_rejected(lengths):
    r = await dispatch([b"12345"], lengths=lengths)
    assert r.status == 422 and r.reads == 0


@pytest.mark.parametrize("length", [b"4", b"6"])
async def test_content_length_mismatch_is_rejected(length):
    r = await dispatch([b"12345"], lengths=[length])
    assert r.status == 422 and not r.completed


@pytest.mark.parametrize(
    "mime",
    [None, "application/json", "application/octet-stream", "image/gif", "image/png; charset=utf-8"],
)
async def test_non_image_media_types_do_not_open_binary_ingress(mime):
    r = await dispatch([b"12345"], mime=mime)
    assert r.status == 415 and r.reads == 0


@pytest.mark.parametrize(
    "extra",
    [
        [(b"content-encoding", b"gzip")],
        [(b"content-encoding", b"identity"), (b"content-encoding", b"gzip")],
        [(b"content-type", b"image/png")],
        [(b"x-padding", b"x" * 16384)],
    ],
)
async def test_encoding_duplicate_type_and_header_bounds(extra):
    r = await dispatch([b"12345"], extra=extra)
    assert r.status in (413, 415) and r.reads == 0


@pytest.mark.parametrize(
    "host,origin",
    [
        (b"evil.invalid", b"http://localhost:8000"),
        (b"localhost:8000", None),
        (b"localhost:8000", b"https://evil.invalid"),
    ],
)
async def test_host_and_origin_are_checked_before_body(host, origin):
    r = await dispatch([b"12345"], host=host, origin=origin)
    assert r.status == 403 and r.reads == 0 and r.calls == 0


@pytest.mark.parametrize(
    "cookie,csrf,expected", [(False, True, 401), (True, None, 403), (True, False, 403)]
)
async def test_endpoint_cookie_csrf_can_reject_before_any_body(cookie, csrf, expected):
    r = await dispatch([b"x" * 10000], cookie=cookie, csrf=csrf)
    assert r.status == expected and r.calls == 1 and r.reads == 0


@pytest.mark.parametrize("status", [401, 403])
async def test_endpoint_authorization_denial_can_precede_receive(status):
    r = await dispatch([b"x" * 10000], deny_before_read=status)
    assert r.status == status and r.calls == 1 and r.reads == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"path": PATH + "/"},
        {"path": PATH.replace("/portfolio/", "/portfolio-extra/")},
        {"path": PATH.replace(A, A.upper())},
        {"method": "POST"},
        {"query": b"x=1"},
        {"raw_path": PATH.replace("/assets/", "/%61ssets/").encode()},
    ],
)
async def test_lookalike_or_noncanonical_paths_do_not_get_binary_exception(changes):
    r = await dispatch([b"12345"], **changes)
    assert r.status == 415 and r.reads == 0


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/auth/login", "POST"),
        (f"/api/v1/workspaces/{W}/businesses/{B}/configuration/draft", "PUT"),
        (f"/api/v1/workspaces/{W}/businesses/{B}/knowledge/sources", "POST"),
        (f"/api/v1/workspaces/{W}/businesses/{B}/portfolio/assets/uploads", "POST"),
    ],
)
async def test_old_json_body_cap_remains_4096(path, method):
    valid = b'{"x":"' + b"x" * 4088 + b'"}'
    assert len(valid) == 4096
    assert (
        await dispatch([valid], path=path, method=method, mime="application/json")
    ).status == 201
    assert (
        await dispatch([valid + b" "], path=path, method=method, mime="application/json")
    ).status == 413
    assert (await dispatch([valid], path=path, method=method)).status == 415


async def test_existing_manual_send_json_65536_cap_stays_separate():
    path = f"/api/v1/workspaces/{W}/conversations/{B}/messages"
    assert (
        await dispatch([b"x" * 65536], path=path, method="POST", mime="application/json")
    ).status == 201
    assert (
        await dispatch([b"x" * 65537], path=path, method="POST", mime="application/json")
    ).status == 413
    assert (await dispatch([b"x" * 5000], path=path, method="POST")).status == 415


async def test_binary_route_keeps_peer_rate_limit():
    settings = AuthSettings(auth_origins=("http://localhost:8000",), auth_peer_limit=1)
    limiter = RateLimiter(60)
    assert (await dispatch([b"x"], settings=settings, limiter=limiter)).status == 201
    r = await dispatch([b"x"], settings=settings, limiter=limiter)
    assert r.status == 429 and r.reads == 0


async def test_binary_receive_uses_one_actual_15_second_deadline_for_trickle():
    r = await dispatch([b"12", b"345"], delays=[8, 8])
    assert r.status == 503 and not r.completed
    assert 14.5 <= r.elapsed <= 18


async def test_old_json_receive_deadline_remains_three_seconds():
    r = await dispatch(
        [b"{}"], path="/api/v1/auth/login", method="POST", mime="application/json", delays=[3.2]
    )
    assert r.status == 503 and not r.completed
    assert 2.5 <= r.elapsed <= 5
