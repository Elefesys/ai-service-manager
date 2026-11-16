"""Actual PostgreSQL/auth/ASGI; the object store is explicitly a controlled port.

These tests do not claim private S3 or browser evidence.
"""

import base64
import hashlib
import io
import json
import random
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from asm.ai.vision import VisionClient
from asm.auth.crypto import PASSWORD_HASHER, new_token, token_verifier
from asm.files.config import StorageSettings
from asm.files.models import OwnerCleanupPermit, OwnerDeletePermit, OwnerUploadPermit
from asm.files.storage import ObjectInfo, S3ObjectStorage
from asm.foundation import Settings, create_app
from asm.knowledge.embeddings import EmbeddingClient
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.portfolio.storage import PortfolioCleanupSweep
from asm.tenancy import TenancyError, current_workspace_context
from m5_configuration_fixtures import configuration_bundle
from m5_portfolio_fixtures import portfolio_pg as portfolio_pg
from PIL import Image
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
ORIGIN = "http://localhost:8000"


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


def pixels():
    data = random.Random(8021).randbytes(64 * 64 * 3)
    stream = io.BytesIO()
    Image.frombytes("RGB", (64, 64), data).save(stream, format="PNG")
    assert len(stream.getvalue()) > 4096
    return stream.getvalue()


class ControlledPrivateStore:
    """A test double; only PG/auth/ASGI facts from this module are actual."""

    def __init__(self, h):
        self.h = h
        self.values = {}
        self.calls = []
        self.after_put = None
        self.after_get = None
        self.delete_error = False
        self.put_unknown = False

    async def outside(self):
        with pytest.raises(TenancyError):
            current_workspace_context()
        async with self.h.migrator.begin() as c:
            await c.execute(text("SET LOCAL lock_timeout='1s'"))
            await c.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,2018))"),
                {"scope": f"{self.h.ws}:{self.h.business}|CONFIGURATION_V1"},
            )

    async def put_owner(self, permit, data):
        assert type(permit) is OwnerUploadPermit
        await self.outside()
        self.calls.append("PUT")
        self.values[permit.storage_key] = (data, permit.manifest.mime_type)
        if self.after_put:
            await self.after_put()
        if self.put_unknown:
            raise MessagingError(Code.DEPENDENCY_TIMEOUT)

    async def delete_owner(self, permit):
        assert type(permit) in {OwnerCleanupPermit, OwnerDeletePermit}
        await self.outside()
        self.calls.append("DELETE")
        if self.delete_error:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        self.values.pop(permit.storage_key, None)

    async def head(self, key):
        await self.outside()
        self.calls.append("HEAD")
        if key not in self.values:
            raise MessagingError(Code.NOT_FOUND)
        data, mime = self.values[key]
        return ObjectInfo(
            size_bytes=len(data),
            mime_type=mime,
            checksum_sha256=base64.b64encode(hashlib.sha256(data).digest()).decode(),
        )

    async def get(self, key):
        await self.outside()
        self.calls.append("GET")
        if key not in self.values:
            raise MessagingError(Code.NOT_FOUND)
        data = self.values[key][0]
        if self.after_get:
            await self.after_get()
        return data

    async def put(self, *args):
        raise AssertionError("Owner upload must not impersonate inbound Job permit")

    async def delete(self, *args):
        raise AssertionError("Accepted owner delete is not inbound cleanup")

    def presign_get(self, *args):
        raise AssertionError("Owner preview never issues public/signed storage URL")


class ActualPrivateStore(ControlledPrivateStore):
    """Same observation/fault seams, with every byte operation delegated to S3."""

    def __init__(self, h):
        super().__init__(h)
        self.storage = S3ObjectStorage(StorageSettings())

    async def put_owner(self, permit, data):
        await self.outside()
        self.calls.append("PUT")
        await self.storage.put_owner(permit, data)
        if self.after_put:
            await self.after_put()
        if self.put_unknown:
            raise MessagingError(Code.DEPENDENCY_TIMEOUT)

    async def delete_owner(self, permit):
        await self.outside()
        self.calls.append("DELETE")
        if self.delete_error:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
        await self.storage.delete_owner(permit)

    async def head(self, key):
        await self.outside()
        self.calls.append("HEAD")
        return await self.storage.head(key)

    async def get(self, key):
        await self.outside()
        self.calls.append("GET")
        data = await self.storage.get(key)
        if self.after_get:
            await self.after_get()
        return data

    async def close(self):
        try:
            # Test teardown only: remove exactly this random fixture's keys.
            # Product purge/cleanup continue using their distinct live permits.
            async with self.h.migrator.connect() as c:
                keys = (
                    (
                        await c.execute(
                            text(
                                "SELECT storage_key FROM platform.portfolio_asset_versions WHERE workspace_id=:ws"
                            ),
                            {"ws": self.h.ws},
                        )
                    )
                    .scalars()
                    .all()
                )
            for key in keys:
                assert key.startswith(f"workspaces/{self.h.ws}/portfolio/")
                await self.storage._io(
                    lambda key=key: self.storage._client.delete_object(
                        Bucket=self.storage._settings.bucket, Key=key
                    )
                )
        finally:
            await self.storage.close()


@pytest_asyncio.fixture
async def api(portfolio_pg, request):
    h = portfolio_pg
    h.posts = {"vision": 0, "embedding": 0}
    h.usage_bodies = []
    h.provider_behavior = None
    mode = getattr(request, "param", None)
    h.store = (
        ActualPrivateStore(h) if mode in {"s3", "s3_controlled"} else ControlledPrivateStore(h)
    )
    login = "portfolio." + uuid4().hex[:16]
    password = new_token()
    hashes = []
    try:
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) VALUES(:u,:login,:hash)"
                ),
                {"u": h.actor, "login": login, "hash": PASSWORD_HASHER.hash(password)},
            )

        async def provider(request):
            await h.store.outside()
            body = json.loads(request.content)
            h.usage_bodies.append(body)
            if request.url.path.endswith("/chat/completions"):
                h.posts["vision"] += 1
                if h.provider_behavior == "unknown":
                    raise httpx.ReadTimeout("private diagnostic sentinel")
                if h.provider_behavior == "owner-loss":
                    async with h.migrator.begin() as c:
                        await c.execute(
                            text(
                                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
                            ),
                            {"w": h.ws, "u": h.actor},
                        )
                result = {
                    "revision": "vision_result_v1",
                    "subject": "Synthetic coloured field",
                    "styles": ["geometric"],
                    "details": ["Visible coloured pixels"],
                    "uncertainty": ["No physical scale supplied"],
                    "scale": "UNKNOWN",
                }
                raw = {
                    "id": "gen_123",
                    "model": "openai/gpt-4o-mini",
                    "provider": "OpenAI",
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "total_tokens": 150,
                        "cost": "0.01",
                    },
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": json.dumps(result)},
                        }
                    ],
                }
            else:
                h.posts["embedding"] += 1
                raw = {
                    "id": "gen_124",
                    "model": "openai/text-embedding-3-small",
                    "provider": "OpenAI",
                    "usage": {
                        "prompt_tokens": len(body["input"]),
                        "total_tokens": len(body["input"]),
                        "cost": "0.000001",
                    },
                    "data": [
                        {"index": i, "embedding": [1.0] + [0.0] * 1535}
                        for i in range(len(body["input"]))
                    ],
                }
            return httpx.Response(200, stream=Bytes(json.dumps(raw).encode()))

        controlled = mode in {"controlled", "s3_controlled"}
        settings = Settings(
            auth_origins=(ORIGIN,),
            auth_peer_limit=1000,
            auth_global_limit=10000,
            auth_login_limit=1000,
        )
        app = create_app(
            settings,
            object_storage=h.store,
            portfolio_storage=h.store,
            portfolio_vision=VisionClient(httpx.MockTransport(provider)) if controlled else None,
            portfolio_embeddings=EmbeddingClient(httpx.MockTransport(provider))
            if controlled
            else None,
        )
        h.app = app
        h.settings = settings
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client,
        ):
            h.client = client
            challenge = await client.post(
                "/api/v1/auth/bootstrap",
                json={},
                headers={"Origin": ORIGIN, "X-CSRF-Bootstrap": "1"},
            )
            assert challenge.status_code == 200
            hashes.append(token_verifier(client.cookies.get(settings.auth_cookie_name)))
            response = await client.post(
                "/api/v1/auth/login",
                json={"login": login, "password": password},
                headers={"Origin": ORIGIN, "X-CSRF-Token": challenge.json()["csrf_token"]},
            )
            assert response.status_code == 200
            h.csrf = response.json()["csrf_token"]
            hashes.append(token_verifier(client.cookies.get(settings.auth_cookie_name)))
            yield h
    finally:
        try:
            if isinstance(h.store, ActualPrivateStore):
                await h.store.close()
        finally:
            async with h.migrator.begin() as c:
                await c.execute(
                    text(
                        "DELETE FROM platform.auth_sessions WHERE user_account_id=:u OR token_hash=ANY(:hashes)"
                    ),
                    {"u": h.actor, "hashes": hashes},
                )
                await c.execute(
                    text("DELETE FROM platform.auth_credentials WHERE user_account_id=:u"),
                    {"u": h.actor},
                )


def route(h, suffix="", *, workspace=None, business=None):
    return (
        f"/api/v1/workspaces/{workspace or h.ws}/businesses/{business or h.business}/portfolio"
        + suffix
    )


def headers(h, **changes):
    return {"Origin": ORIGIN, "X-CSRF-Token": h.csrf, **changes}


async def post(h, suffix, body, *, key=True):
    return await h.client.post(
        route(h, suffix),
        json=body,
        headers=headers(h, **({"Idempotency-Key": str(uuid4())} if key else {})),
    )


async def init(h, data=None, origin="MY_WORK"):
    data = data or pixels()
    response = await post(
        h,
        "/assets/uploads",
        {
            "schema_version": 1,
            "asset_id": None,
            "expected_asset_version": "0",
            "origin": origin,
            "mime_type": "image/png",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["result"], data


def upload_path(h, r):
    return route(h, f"/assets/{r['asset_id']}/versions/{r['version_id']}/uploads/{r['upload_id']}")


async def put(h, r, data, **options):
    return await h.client.put(
        upload_path(h, r) + "/content",
        content=data,
        headers=headers(h, **{"Content-Type": "image/png"}),
        **options,
    )


async def ready(h):
    r, data = await init(h)
    response = await put(h, r, data)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "STORED"
    response = await h.client.post(
        upload_path(h, r) + "/finalize",
        json={"schema_version": 1, "expected_asset_version": r["asset_version"]},
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert response.status_code == 200, response.text
    return response.json()["result"], data


async def test_actual_auth_pg_upload_finalize_preview_no_fake_jobs_and_default_zero_provider(api):
    h = api
    async with h.migrator.connect() as c:
        before = (
            await c.execute(text("SELECT count(*) FROM platform.messaging_jobs"))
        ).scalar_one()
    r, data = await ready(h)
    preview = await h.client.get(
        route(h, f"/assets/{r['asset_id']}/versions/{r['version_id']}/preview")
    )
    assert preview.status_code == 200 and preview.content == data
    assert (
        preview.headers["cache-control"] == "no-store"
        and preview.headers["x-content-type-options"] == "nosniff"
    )
    state = await h.client.get(route(h))
    assert state.status_code == 200, state.text
    assert state.json()["vision_mode"] == state.json()["embedding_mode"] == "DISABLED"
    assert (
        "storage_key" not in state.text
        and "ticket" not in state.text
        and "http://" not in state.text
    )
    result = await post(
        h,
        f"/assets/{r['asset_id']}/versions/{r['version_id']}/analysis",
        {"schema_version": 1},
        key=False,
    )
    assert result.status_code == 200 and result.json()["outcome"] == "DISABLED"
    assert h.posts == {"vision": 0, "embedding": 0} and h.store.calls == ["PUT", "GET"]
    async with h.migrator.connect() as c:
        assert (
            await c.execute(text("SELECT count(*) FROM platform.messaging_jobs"))
        ).scalar_one() == before
        assert (
            await c.execute(
                text("SELECT count(*) FROM platform.portfolio_ai_sessions WHERE workspace_id=:w"),
                {"w": h.ws},
            )
        ).scalar_one() == 0


@pytest.mark.parametrize(
    "denial", ["host", "csrf", "origin", "owner", "intent", "expired", "business", "workspace"]
)
async def test_authority_refusals_happen_before_first_upload_body_receive(api, denial):
    h = api
    if denial == "expired":
        # TEST-only aged INIT setup preserves immutable identity and the exact
        # 120-second TTL. All other cases issue their intent through normal HTTP.
        data = pixels()
        asset, version, upload = (uuid4() for _ in range(3))
        params = {
            "w": h.ws,
            "b": h.business,
            "actor": h.actor,
            "a": asset,
            "v": version,
            "u": upload,
            "key": f"workspaces/{h.ws}/portfolio/{asset}/versions/{version}/uploads/{upload}",
            "size": len(data),
            "sha": hashlib.sha256(data).hexdigest(),
        }
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "INSERT INTO platform.portfolio_assets(workspace_id,business_id,id,origin,created_by,created_at) "
                    "VALUES(:w,:b,:a,'MY_WORK',:actor,now()-interval '121 seconds')"
                ),
                params,
            )
            await c.execute(
                text(
                    "INSERT INTO platform.portfolio_asset_versions(workspace_id,business_id,asset_id,id,upload_id,expected_asset_version,storage_key,mime_type,size_bytes,sha256,created_by,created_at,expires_at) "
                    "VALUES(:w,:b,:a,:v,:u,1,:key,'image/png',:size,:sha,:actor,now()-interval '121 seconds',now()-interval '1 second')"
                ),
                params,
            )
            await c.execute(
                text(
                    "UPDATE platform.portfolio_assets SET pending_version_id=:v WHERE workspace_id=:w AND business_id=:b AND id=:a"
                ),
                params,
            )
        r = {"asset_id": str(asset), "version_id": str(version), "upload_id": str(upload)}
    else:
        r, data = await init(h)
    url = upload_path(h, r) + "/content"
    request_headers = headers(h, **{"Content-Type": "image/png"})
    if denial == "host":
        request_headers["Host"] = "foreign.invalid"
    elif denial == "csrf":
        request_headers["X-CSRF-Token"] = "0" * 64
    elif denial == "origin":
        request_headers["Origin"] = "https://foreign.invalid"
    elif denial == "owner":
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
                ),
                {"w": h.ws, "u": h.actor},
            )
    elif denial == "intent":
        url = url.replace(r["upload_id"], str(uuid4()))
    elif denial == "expired":
        pass  # The scoped migrator fixture above created an already expired intent.
    elif denial == "business":
        url = url.replace(str(h.business), str(h.other_business))
    else:
        url = url.replace(str(h.ws), str(h.other_ws))
    reads = 0

    async def body():
        nonlocal reads
        reads += 1
        yield data

    response = await h.client.put(url, content=body(), headers=request_headers)
    assert response.status_code in (400, 403, 404, 409), response.text
    if denial == "expired":
        assert (
            response.status_code == 409 and response.json()["error"]["code"] == "UPLOAD_NOT_ALLOWED"
        )
    assert reads == 0 and h.store.calls == []


async def test_cors_preflight_put_and_foreign_origin_refusal_then_real_handler(api):
    h = api
    r, data = await init(h)
    url = upload_path(h, r) + "/content"
    options = await h.client.options(
        url,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type,X-CSRF-Token",
        },
    )
    assert options.status_code == 200 and options.headers["access-control-allow-origin"] == ORIGIN
    assert h.store.calls == []
    foreign = await h.client.options(
        url, headers={"Origin": "https://foreign.invalid", "Access-Control-Request-Method": "PUT"}
    )
    assert foreign.status_code == 400 and "access-control-allow-origin" not in foreign.headers
    assert (await put(h, r, data)).status_code == 200


async def test_uncertain_put_is_not_retried_and_only_head_get_recovery_can_finalize(api):
    h = api
    r, data = await init(h)
    h.store.put_unknown = True
    response = await put(h, r, data)
    assert response.status_code == 503
    h.store.put_unknown = False
    response = await put(h, r, data)
    assert response.status_code == 409
    assert h.store.calls == ["PUT"]
    response = await h.client.post(
        upload_path(h, r) + "/recover", json={"schema_version": 1}, headers=headers(h)
    )
    assert response.status_code == 200 and response.json()["state"] == "STORED", response.text
    assert h.store.calls == ["PUT", "HEAD", "GET"]
    response = await h.client.post(
        upload_path(h, r) + "/finalize",
        json={"schema_version": 1, "expected_asset_version": r["asset_version"]},
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert response.status_code == 200, response.text


async def test_preview_rechecks_owner_after_storage_get(api):
    h = api
    r, _ = await ready(h)

    async def revoke():
        async with h.migrator.begin() as c:
            await c.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
                ),
                {"w": h.ws, "u": h.actor},
            )

    h.store.after_get = revoke
    response = await h.client.get(
        route(h, f"/assets/{r['asset_id']}/versions/{r['version_id']}/preview")
    )
    assert response.status_code == 403 and response.headers["content-type"].startswith(
        "application/json"
    )


async def test_delete_receipt_replay_get_and_reload_never_repeat_purge(api):
    h = api
    r, _ = await ready(h)
    h.store.delete_error = True
    state = (await h.client.get(route(h))).json()
    key = str(uuid4())
    body = {
        "schema_version": 1,
        "expected_asset_version": r["asset_version"],
        "expected_activation_version": state["activation_version"],
    }
    url = route(h, f"/assets/{r['asset_id']}/delete")
    first = await h.client.post(url, json=body, headers=headers(h, **{"Idempotency-Key": key}))
    assert first.status_code == 200 and h.store.calls.count("DELETE") == 1, first.text
    for _ in range(2):
        view = await h.client.get(route(h))
        assert view.status_code == 200
        assert len(view.json()["pending_purges"]) == 1 and view.json()["purges_omitted"] == 0
        assert "storage_key" not in view.text and "ticket" not in view.text
    replay = await h.client.post(url, json=body, headers=headers(h, **{"Idempotency-Key": key}))
    assert replay.status_code == 200 and replay.json()["outcome"] == "REPLAY"
    assert h.store.calls.count("DELETE") == 1
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.portfolio_asset_versions SET purge_deadline=clock_timestamp()-interval '1 second' WHERE workspace_id=:w AND id=:v"
            ),
            {"w": h.ws, "v": UUID(r["version_id"])},
        )
    h.store.delete_error = False
    retry = await post(
        h,
        f"/assets/{r['asset_id']}/versions/{r['version_id']}/purge",
        {"schema_version": 1},
        key=False,
    )
    assert retry.status_code == 200 and retry.json()["state"] == "PURGED", retry.text
    assert h.store.calls.count("DELETE") == 2
    assert (await h.client.get(route(h))).json()["pending_purges"] == []


@pytest.mark.parametrize("api", ["controlled"], indirect=True)
async def test_controlled_vision_actual_pixels_private_accounting_and_replay(api):
    h = api
    r, data = await ready(h)
    response = await post(
        h,
        f"/assets/{r['asset_id']}/versions/{r['version_id']}/analysis",
        {"schema_version": 1},
        key=False,
    )
    assert response.status_code == 200 and response.json()["applied"] is True, response.text
    image = h.usage_bodies[0]["messages"][1]["content"][1]["image_url"]
    assert image["detail"] == "low"
    with Image.open(io.BytesIO(base64.b64decode(image["url"].split(",", 1)[1]))) as derivative:
        assert derivative.size == (256, 256) and derivative.info == {}
    assert h.posts["vision"] == 1
    replay = await post(
        h,
        f"/assets/{r['asset_id']}/versions/{r['version_id']}/analysis",
        {"schema_version": 1},
        key=False,
    )
    assert (
        replay.status_code == 200
        and replay.json()["outcome"] == "REPLAY"
        and h.posts["vision"] == 1
    )
    state = (await h.client.get(route(h))).json()
    assert state["assets"][0]["analysis"]["result"]["scale"] == "UNKNOWN"
    assert state["items"] == []  # Analysis cannot confirm or classify a canonical work.


@pytest.mark.parametrize("api", ["controlled"], indirect=True)
async def test_owner_loss_during_vision_still_records_cost_before_fresh_apply_denial(api):
    h = api
    r, _ = await ready(h)
    h.provider_behavior = "owner-loss"
    response = await post(
        h,
        f"/assets/{r['asset_id']}/versions/{r['version_id']}/analysis",
        {"schema_version": 1},
        key=False,
    )
    assert response.status_code == 403 and h.posts["vision"] == 1, response.text
    async with h.migrator.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT state,completion->'cost'->>'amount',applied_at FROM platform.vision_analyses WHERE workspace_id=:w"
                ),
                {"w": h.ws},
            )
        ).one()
    assert row == ("SUCCESS", "0.01", None)


@pytest.mark.parametrize("api", ["controlled"], indirect=True)
async def test_unknown_vision_does_not_repeat_with_fresh_service_session_or_request(api):
    h = api
    r, _ = await ready(h)
    h.provider_behavior = "unknown"
    url = f"/assets/{r['asset_id']}/versions/{r['version_id']}/analysis"
    first = await post(h, url, {"schema_version": 1}, key=False)
    assert first.status_code == 200 and first.json()["state"] == "UNKNOWN", first.text
    second = await post(h, url, {"schema_version": 1}, key=False)
    assert (
        second.status_code == 200
        and second.json()["outcome"] == "REPLAY"
        and h.posts["vision"] == 1
    )


@pytest.mark.parametrize("api", ["controlled"], indirect=True)
async def test_http_owner_review_build_publish_settings_reload_and_empty_withdrawal(api):
    h = api
    configuration = route(h).removesuffix("/portfolio") + "/configuration"
    bundle = configuration_bundle()
    edited = await h.client.put(
        configuration + "/draft",
        json={"expected_draft_version": "0", "bundle": bundle},
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert edited.status_code == 200, edited.text
    asset, _ = await ready(h)
    saved = await post(
        h,
        "/items",
        {
            "schema_version": 1,
            "item_id": None,
            "expected_item_version": "0",
            "asset_id": asset["asset_id"],
            "description": "Owner reviewed synthetic geometric work",
            "attributes": {"subject": "coloured field", "styles": ["geometric"], "placement": None},
            "service_id": "consultation",
            "analysis_id": None,
        },
    )
    assert saved.status_code == 200, saved.text
    item = saved.json()["result"]
    confirmed = await post(
        h,
        f"/items/{item['item_id']}/confirm",
        {
            "schema_version": 1,
            "expected_item_version": item["item_version"],
            "revision_id": item["revision_id"],
            "canonical_sha256": item["canonical_sha256"],
            "confirm_my_work": True,
            "show_permission": True,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert h.posts == {"vision": 0, "embedding": 0}
    state = (await h.client.get(route(h))).json()
    build_key = str(uuid4())
    build_body = {
        "schema_version": 1,
        "expected_items_hash": state["items_hash"],
        "revision_ids": [item["revision_id"]],
    }
    built = await h.client.post(
        route(h, "/builds"),
        json=build_body,
        headers=headers(h, **{"Idempotency-Key": build_key}),
    )
    assert built.status_code == 200, built.text
    build_id = built.json()["result"]["build_id"]
    state = (await h.client.get(route(h))).json()
    build = next(b for b in state["builds"] if b["build_id"] == build_id)
    assert build["state"] == "READY" and build["input_count"] == 1
    assert h.posts == {"vision": 0, "embedding": 1}
    replay = await h.client.post(
        route(h, "/builds"),
        json=build_body,
        headers=headers(h, **{"Idempotency-Key": build_key}),
    )
    assert replay.status_code == 200 and replay.json()["outcome"] == "REPLAY", replay.text
    assert h.posts["embedding"] == 1

    async def publish(current, selected):
        response = await post(
            h,
            "/publish",
            {
                "schema_version": 1,
                "expected_draft_version": current["draft_version"],
                "expected_activation_version": current["activation_version"],
                "knowledge_build_id": None,
                "expected_knowledge_build_version": None,
                "portfolio_build_id": selected["build_id"],
                "expected_portfolio_build_version": selected["version"],
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["result"]

    published = await publish(state, build)
    first_release = published["release_id"]
    state = (await h.client.get(route(h))).json()
    assert state["active_release_id"] == first_release
    assert state["active_portfolio_build_id"] == build_id
    assert state["active_knowledge_build_id"] is None
    bundle["communication_style"] = "WARM"
    edited = await h.client.put(
        configuration + "/draft",
        json={"expected_draft_version": state["draft_version"], "bundle": bundle},
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert edited.status_code == 200, edited.text
    state = (await h.client.get(route(h))).json()
    assert state["active_release_id"] == first_release
    assert state["active_portfolio_build_id"] == build_id
    legacy = await h.client.post(
        configuration + "/publish",
        json={
            "expected_draft_version": state["draft_version"],
            "expected_activation_version": state["activation_version"],
        },
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert legacy.status_code == 409, legacy.text
    assert legacy.json()["error"]["code"] == "PORTFOLIO_BUILD_REQUIRED"
    assert (await h.client.get(route(h))).json()["active_release_id"] == first_release
    await publish(state, build)
    state = (await h.client.get(route(h))).json()
    assert state["active_portfolio_build_id"] == build_id
    revoked = await post(
        h,
        f"/items/{item['item_id']}/revoke",
        {
            "schema_version": 1,
            "expected_item_version": confirmed.json()["result"]["item_version"],
            "expected_activation_version": state["activation_version"],
        },
    )
    assert revoked.status_code == 200, revoked.text
    state = (await h.client.get(route(h))).json()
    assert state["items"][0]["state"] == "REVOKED"
    assert next(b for b in state["builds"] if b["build_id"] == build_id)["eligible"] is False
    empty = await post(
        h,
        "/builds",
        {"schema_version": 1, "expected_items_hash": state["items_hash"], "revision_ids": []},
    )
    assert empty.status_code == 200 and empty.json()["result"]["build_state"] == "READY", empty.text
    empty_id = empty.json()["result"]["build_id"]
    state = (await h.client.get(route(h))).json()
    empty_build = next(b for b in state["builds"] if b["build_id"] == empty_id)
    await publish(state, empty_build)
    state = (await h.client.get(route(h))).json()
    assert state["active_portfolio_build_id"] == empty_id and empty_build["input_count"] == 0
    rollback = await post(
        h,
        "/rollback",
        {
            "schema_version": 1,
            "expected_activation_version": state["activation_version"],
            "release_id": first_release,
        },
    )
    assert rollback.status_code == 409, rollback.text
    assert rollback.json()["error"]["code"] == "ROLLBACK_NOT_ALLOWED"
    assert (await h.client.get(route(h))).json()["active_portfolio_build_id"] == empty_id
    assert h.posts == {"vision": 0, "embedding": 1}


async def test_abandoned_cleanup_uses_distinct_permit_and_keeps_late_put_tombstone(api):
    h = api
    r, data = await init(h)
    response = await h.client.post(
        upload_path(h, r) + "/abandon",
        json={"schema_version": 1, "expected_asset_version": r["asset_version"]},
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert response.status_code == 200, response.text
    sweep = PortfolioCleanupSweep(
        MessagingDatabase(h.runtime, environment="TEST"),
        h.store,
    )
    assert await sweep.run_once()
    async with h.migrator.begin() as c:
        row = (
            await c.execute(
                text(
                    "SELECT storage_key,state FROM platform.portfolio_asset_versions WHERE workspace_id=:w AND id=:v"
                ),
                {"w": h.ws, "v": UUID(r["version_id"])},
            )
        ).one()
        assert row.state == "ABANDONED"
        h.store.values[row.storage_key] = (
            data,
            "image/png",
        )  # Explicit controlled late PUT, not S3 evidence.
        await c.execute(
            text(
                "UPDATE platform.portfolio_asset_versions SET next_check_at=clock_timestamp()-interval '1 second' WHERE workspace_id=:w AND id=:v"
            ),
            {"w": h.ws, "v": UUID(r["version_id"])},
        )
    assert await sweep.run_once()
    assert h.store.values == {} and h.store.calls.count("DELETE") == 2
