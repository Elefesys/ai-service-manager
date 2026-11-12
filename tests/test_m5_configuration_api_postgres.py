"""Actual owner HTTP/session/CSRF plus runtime-role PostgreSQL configuration."""

import asyncio
import json

import pytest
import pytest_asyncio
from asm.auth.crypto import PASSWORD_HASHER, new_token
from asm.configuration.models import ActiveProjection, CommandResponse, Preview
from asm.tenancy import TenantUnitOfWork
from httpx import ASGITransport, AsyncClient
from m5_configuration_fixtures import configuration_bundle
from pydantic import SecretStr
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_tenancy_postgres import BA, BB, UA, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
TABLES = tuple("platform.business_configuration_" + n for n in ("state", "releases", "receipts"))


@pytest_asyncio.fixture
async def configured(auth):
    response = await login(auth)
    assert response.status_code == 200
    auth.csrf = response.json()["csrf_token"]
    try:
        yield auth
    finally:
        async with auth.migrator.begin() as c:
            for table in TABLES:
                await c.execute(
                    text("DELETE FROM " + table + " WHERE workspace_id IN (:a,:b)"),
                    {"a": A, "b": B},
                )
            await c.execute(
                text("DELETE FROM platform.auth_credentials WHERE user_account_id=:id"), {"id": UB}
            )


def route(suffix, workspace=A, business=BA):
    return f"/api/v1/workspaces/{workspace}/businesses/{business}/configuration/{suffix}"


async def send(h, suffix, body, key, *, workspace=A, business=BA, client=None, csrf=None):
    client = client or h.client
    return await client.request(
        "PUT" if suffix == "draft" else "POST",
        route(suffix, workspace, business),
        json=body,
        headers={**headers(client, csrf or h.csrf), "Idempotency-Key": key},
    )


async def edited(h, value=None, version="0", key="edit", **scope):
    response = await send(
        h,
        "draft",
        {
            "expected_draft_version": version,
            "bundle": value if value is not None else configuration_bundle(),
        },
        key,
        **scope,
    )
    assert response.status_code == 200, response.text
    return CommandResponse.model_validate(response.json())


async def published(h, draft="1", activation="0", key="publish", **scope):
    response = await send(
        h,
        "publish",
        {"expected_draft_version": draft, "expected_activation_version": activation},
        key,
        **scope,
    )
    assert response.status_code == 200, response.text
    return CommandResponse.model_validate(response.json())


async def counts(h):
    async with h.migrator.connect() as c:
        return tuple(
            [
                (await c.execute(text("SELECT count(*) FROM " + table))).scalar_one()
                for table in TABLES
            ]
        )


async def test_owner_edit_preview_publish_two_workspaces_and_bounded_active(configured):
    h = configured
    active = await h.client.get(route("active"))
    assert (
        active.status_code == 200 and ActiveProjection.model_validate(active.json()).bundle is None
    )
    for kind, scope in (("tattoo", {}), ("ceramics", {"workspace": B, "business": BB})):
        if scope:
            secret = SecretStr(new_token())
            async with h.migrator.begin() as c:
                await c.execute(
                    text(
                        "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u"
                    ),
                    {"w": B, "u": UB},
                )
                await c.execute(
                    text(
                        "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) VALUES(:u,'synthetic.other',:p)"
                    ),
                    {"u": UB, "p": PASSWORD_HASHER.hash(secret.get_secret_value())},
                )
            other = AsyncClient(
                transport=ASGITransport(app=h.app), base_url=h.settings.auth_origins[0]
            )
            response = await login(h, client=other, login_value="synthetic.other", password=secret)
            assert response.status_code == 200
            scope |= {"client": other, "csrf": response.json()["csrf_token"]}
        client = scope.get("client", h.client)
        try:
            bundle = configuration_bundle(kind)
            await edited(h, bundle, **scope)
            url_scope = {k: v for k, v in scope.items() if k in ("workspace", "business")}
            assert (await client.get(route("active", **url_scope))).json()["bundle"] is None
            preview = Preview.model_validate(
                (await client.get(route("preview", **url_scope))).json()
            )
            assert preview.validation.valid
            assert preview.services[0].owner_handoff == (kind == "ceramics")
            release = await published(h, **scope)
            response = await client.get(route("active", **url_scope))
            dto = ActiveProjection.model_validate(response.json())
            assert dto.bundle.model_dump() == bundle
            assert dto.release_id == release.result.release_id and dto.activation_version == "1"
            assert dto.structured_rules_authoritative is True
            assert response.headers["cache-control"] == "no-store"
        finally:
            if scope:
                await other.aclose()
    assert (await h.client.get(route("active", B, BB))).status_code == 403
    assert (await h.client.get(route("draft", A, BB))).status_code == 404


async def test_http_cas_competing_publications_exact_replay_and_rollback(configured):
    h = configured
    first_edit = await edited(h)
    assert (await edited(h)).result == first_edit.result
    body = {"expected_draft_version": "1", "expected_activation_version": "0"}
    replies = await asyncio.gather(send(h, "publish", body, "one"), send(h, "publish", body, "two"))
    assert sorted(r.status_code for r in replies) == [200, 409]
    accepted = next(r for r in replies if r.status_code == 200)
    accepted_key = "one" if replies[0].status_code == 200 else "two"
    first = CommandResponse.model_validate(accepted.json())
    before = await counts(h)
    replay = await send(h, "publish", body, accepted_key)
    assert replay.json() == accepted.json() | {"outcome": "REPLAY"}
    assert await counts(h) == before == (1, 1, 2)
    conflict = await send(h, "publish", body | {"expected_draft_version": "2"}, accepted_key)
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    )
    value = configuration_bundle()
    value["services"][0]["price"]["amount_minor"] = 150000
    await edited(h, value, "1", "edit-two")
    second = await published(h, "2", "1", "publish-two")
    rollback = {"expected_activation_version": "2", "release_id": first.result.release_id}
    response = await send(h, "rollback", rollback, "rollback")
    assert response.status_code == 200 and response.json()["result"]["activation_version"] == "3"
    assert (await send(h, "rollback", rollback, "rollback")).json()["outcome"] == "REPLAY"
    assert (await published(h, "2", "1", "publish-two")).result == second.result
    current = (await h.client.get(route("active"))).json()
    assert (current["release_id"], current["activation_version"]) == (first.result.release_id, "3")


@pytest.mark.parametrize("bad", ["mode", "rule", "source"])
async def test_invalid_draft_preview_blocks_publish_without_losing_active(configured, bad):
    h = configured
    await edited(h)
    await published(h)
    active = (await h.client.get(route("active"))).json()
    value = configuration_bundle()
    if bad == "mode":
        value["services"][0]["price"]["mode"] = "MODEL_PRICE"
    elif bad == "rule":
        value["faqs"][0]["rule_ids"] = ["absent"]
    else:
        value["faqs"][0]["confirmed"] = False
    await edited(h, value, "1", "bad-edit")
    preview = Preview.model_validate((await h.client.get(route("preview"))).json())
    assert not preview.validation.valid and any(
        i.severity == "ERROR" for i in preview.validation.issues
    )
    before = await counts(h)
    rejected = await send(
        h,
        "publish",
        {"expected_draft_version": "2", "expected_activation_version": "1"},
        "bad-publish",
    )
    assert rejected.status_code == 409 and rejected.json() == {
        "error": {"code": "VALIDATION_FAILED"}
    }
    assert (await h.client.get(route("active"))).json() == active and await counts(h) == before


@pytest.mark.parametrize("operation", ["draft", "publish", "rollback"])
async def test_session_csrf_and_revoked_owner_cannot_mutate_or_replay(configured, operation):
    h = configured
    await edited(h)
    release = await published(h)
    body = {
        "draft": {"expected_draft_version": "0", "bundle": configuration_bundle()},
        "publish": {"expected_draft_version": "1", "expected_activation_version": "0"},
        "rollback": {"expected_activation_version": "1", "release_id": release.result.release_id},
    }[operation]
    key = {"draft": "edit", "publish": "publish", "rollback": "rollback"}[operation]
    if operation == "rollback":
        assert (await send(h, operation, body, key)).status_code == 200
    before = await counts(h)
    no_csrf = await h.client.request(
        "PUT" if operation == "draft" else "POST",
        route(operation),
        json=body,
        headers={"Origin": h.settings.auth_origins[0], "Idempotency-Key": key},
    )
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "CSRF_REJECTED"
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
            ),
            {"w": A, "u": UA},
        )
    denied = await send(h, operation, body, key)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "ACCESS_DENIED"
    assert await counts(h) == before


async def test_logout_session_and_cross_business_replay_are_not_authority(configured):
    h = configured
    await edited(h)
    await published(h)
    body = {"expected_draft_version": "1", "expected_activation_version": "0"}
    before = await counts(h)
    assert (await send(h, "publish", body, "publish", business=BB)).status_code == 404
    response = await h.client.post(
        "/api/v1/auth/logout", json={}, headers=headers(h.client, h.csrf)
    )
    assert response.status_code in (200, 204)
    assert (await send(h, "publish", body, "publish")).status_code == 401
    assert (await h.client.get(route("draft"))).status_code == 401
    assert await counts(h) == before


async def test_http_total_body_duplicate_keys_and_strict_primitives_no_writes(configured):
    h = configured
    base_headers = {
        **headers(h.client, h.csrf),
        "Idempotency-Key": "malformed",
        "Content-Type": "application/json",
    }
    for raw, status in [
        ('{"expected_draft_version":"0","expected_draft_version":"1","bundle":{}}', 422),
        (
            json.dumps({"expected_draft_version": "0", "bundle": configuration_bundle()})
            + " " * 4096,
            413,
        ),
        (json.dumps({"expected_draft_version": 0, "bundle": configuration_bundle()}), 422),
    ]:
        response = await h.client.put(route("draft"), content=raw, headers=base_headers)
        assert response.status_code == status
    response = await h.client.put(
        route("draft") + "?force=true",
        json={"expected_draft_version": "0", "bundle": configuration_bundle()},
        headers=base_headers,
    )
    assert response.status_code == 422
    assert await counts(h) == (0, 0, 0)


async def test_invalid_capability_result_rolls_back_actual_publication(configured, monkeypatch):
    h = configured
    await edited(h)
    actual = TenantUnitOfWork.configuration_command

    async def unreadable(self, *args, **kwargs):
        raw = await actual(self, *args, **kwargs)
        return raw | {"unexpected": "not a valid receipt"}

    with monkeypatch.context() as patch:
        patch.setattr(TenantUnitOfWork, "configuration_command", unreadable)
        response = await send(
            h,
            "publish",
            {"expected_draft_version": "1", "expected_activation_version": "0"},
            "publish",
        )
        assert response.status_code == 503 and response.json() == {"error": {"code": "UNAVAILABLE"}}
    assert await counts(h) == (1, 0, 1)
    assert (await h.client.get(route("active"))).json()["bundle"] is None
    assert (await published(h)).outcome == "ACCEPTED"


async def test_exact_raw_body_limit_and_forbidden_command_options(configured):
    h = configured
    raw = json.dumps({"expected_draft_version": "0", "bundle": configuration_bundle()})
    raw += " " * (4096 - len(raw.encode("utf-8")))
    command_headers = {
        **headers(h.client, h.csrf),
        "Idempotency-Key": "limit",
        "Content-Type": "application/json",
    }
    accepted = await h.client.put(route("draft"), content=raw, headers=command_headers)
    assert accepted.status_code == 200
    before = await counts(h)
    rejected = await h.client.put(route("draft"), content=raw + " ", headers=command_headers)
    assert rejected.status_code == 413 and rejected.json()["error"]["code"] == "BODY_TOO_LARGE"
    for request_headers in (
        command_headers | {"If-Match": '"1"'},
        [*command_headers.items(), ("Idempotency-Key", "second")],
    ):
        response = await h.client.put(route("draft"), content=raw, headers=request_headers)
        assert response.status_code == 422
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:w AND user_account_id=:u"
            ),
            {"w": A, "u": UA},
        )
    denied = await h.client.put(route("draft"), content=raw, headers=command_headers)
    assert denied.status_code == 403
    assert await counts(h) == before
