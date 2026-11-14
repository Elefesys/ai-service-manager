"""Actual owner session/CSRF + runtime-role capabilities; controlled embedding HTTP only."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from asm.foundation import create_app
from asm.knowledge.embeddings import MODEL, EmbeddingClient
from asm.knowledge.models import KnowledgeCommandResponse, KnowledgeOwnerState
from asm.tenancy import TenancyError, current_workspace_context
from m5_configuration_fixtures import configuration_bundle
from sqlalchemy import text
from test_auth_postgres import auth as auth
from test_auth_postgres import headers, login
from test_tenancy_postgres import BA, BB, UA, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration
PREFIX = f"/api/v1/workspaces/{A}/businesses/{BA}"
KNOWLEDGE = PREFIX + "/knowledge"
CONFIGURATION = PREFIX + "/configuration"


class Bytes(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


@pytest_asyncio.fixture
async def knowledge(auth, request):
    h = SimpleNamespace(**vars(auth), posts=0, behavior=None, inputs=[])

    async def provider(request):
        with pytest.raises(TenancyError):
            current_workspace_context()
        h.posts += 1
        body = json.loads(request.content)
        h.inputs.extend(body["input"])
        async with h.migrator.begin() as connection:
            # A separate physical transaction can acquire the exact publication
            # lock while the provider runs. No owner transaction spans HTTP.
            locked = (
                await connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:scope,2018))"),
                    {"scope": f"{A}:{BA}|CONFIGURATION_V1"},
                )
            ).scalar_one()
            assert locked
            count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM platform.knowledge_embedding_calls WHERE workspace_id=:w AND state='RESERVED'"
                    ),
                    {"w": A},
                )
            ).scalar_one()
            assert count == 1  # Reservation is committed before HTTP entry.
            if h.behavior == "owner-loss":
                await connection.execute(text("SET LOCAL lock_timeout='1s'"))
                await connection.execute(
                    text(
                        "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
                    ),
                    {"w": A, "u": UA},
                )
        if h.behavior == "unknown":
            raise httpx.ReadError("private SQL/payload/credentials sentinel")
        raw = json.dumps(
            {
                "model": MODEL,
                "provider": "OpenAI",
                "data": [
                    {"index": i, "embedding": [1.0] + [0.0] * 1535}
                    for i in range(len(body["input"]))
                ],
                "usage": {
                    "prompt_tokens": len(body["input"]),
                    "total_tokens": len(body["input"]),
                    "cost": "0.000001",
                },
            }
        ).encode()
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=Bytes(raw))

    enabled = getattr(request, "param", True)
    app = create_app(
        h.settings,
        knowledge_embeddings=EmbeddingClient(httpx.MockTransport(provider)) if enabled else None,
    )
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=h.settings.auth_origins[0]
            ) as client:
                h.app, h.client = app, client
                response = await login(auth, client=client)
                assert response.status_code == 200
                h.csrf = response.json()["csrf_token"]
                yield h
    finally:
        async with h.migrator.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u"
                ),
                {"w": A, "u": UA},
            )
            for table in (
                "knowledge_embedding_calls",
                "knowledge_release_builds",
                "knowledge_build_chunks",
                "knowledge_builds",
            ):
                await connection.execute(
                    text("DELETE FROM platform." + table + " WHERE workspace_id IN (:a,:b)"),
                    {"a": A, "b": B},
                )
            await connection.execute(
                text(
                    "UPDATE platform.knowledge_sources SET head_revision_id=NULL,confirmed_revision_id=NULL WHERE workspace_id IN (:a,:b)"
                ),
                {"a": A, "b": B},
            )
            for table in (
                "knowledge_chunks",
                "knowledge_revisions",
                "knowledge_sources",
                "business_configuration_receipts",
                "business_configuration_state",
                "business_configuration_releases",
            ):
                await connection.execute(
                    text("DELETE FROM platform." + table + " WHERE workspace_id IN (:a,:b)"),
                    {"a": A, "b": B},
                )


async def send(h, suffix, body, key, *, url=None):
    return await h.client.post(
        url or KNOWLEDGE + suffix,
        json=body,
        headers={**headers(h.client, h.csrf), "Idempotency-Key": key},
    )


async def state(h):
    response = await h.client.get(KNOWLEDGE)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return KnowledgeOwnerState.model_validate(response.json())


async def save(
    h, *, key="save", source=None, version="0", content="Synthetic published preparation."
):
    response = await send(
        h,
        "/sources",
        {
            "schema_version": 1,
            "source_id": source,
            "expected_source_version": version,
            "title": "Synthetic preparation",
            "format": "MARKDOWN",
            "text": content,
            "source_label": "Synthetic owner handbook",
            "service_id": "consultation",
            "claim_key": "preparation",
        },
        key,
    )
    assert response.status_code == 200, response.text
    return KnowledgeCommandResponse.model_validate(response.json())


async def confirmed(h):
    saved = await save(h)
    source = (await state(h)).sources[0]
    assert source.head.canonical_text == "Synthetic published preparation."
    response = await send(
        h,
        f"/sources/{source.source_id}/confirm",
        {
            "schema_version": 1,
            "expected_source_version": source.source_version,
            "revision_id": source.head.revision_id,
            "canonical_sha256": source.head.canonical_sha256,
        },
        "confirm",
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["source_version"] == "2"
    return saved.result.source_id


async def build_body(h):
    current = await state(h)
    return {
        "schema_version": 1,
        "expected_sources_hash": current.sources_hash,
        "revision_ids": [s.head.revision_id for s in current.sources if s.head.confirmed],
    }


async def configuration(h, *, publish=False):
    response = await h.client.put(
        CONFIGURATION + "/draft",
        json={"expected_draft_version": "0", "bundle": configuration_bundle()},
        headers={**headers(h.client, h.csrf), "Idempotency-Key": "configuration-edit"},
    )
    assert response.status_code == 200, response.text
    if publish:
        response = await send(
            h,
            "",
            {"expected_draft_version": "1", "expected_activation_version": "0"},
            "configuration-publish",
            url=CONFIGURATION + "/publish",
        )
        assert response.status_code == 200, response.text
        return response.json()["result"]["release_id"]


async def calls(h):
    async with h.migrator.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT state,outcome,applied_at FROM platform.knowledge_embedding_calls WHERE workspace_id=:w ORDER BY reserved_at,id"
            ),
            {"w": A},
        )
        return list(rows.mappings())


async def test_owner_build_publish_draft_revoke_delete_and_legacy_rollback_guard(knowledge):
    h = knowledge
    await configuration(h)
    source = await confirmed(h)
    body = await build_body(h)
    created = await send(h, "/builds", body, "build")
    assert created.status_code == 200, created.text
    receipt = KnowledgeCommandResponse.model_validate(created.json())
    current = await state(h)
    build = current.builds[0]
    assert h.posts == 1 and build.state == "READY"
    assert receipt.result.build_version == "1" and build.build_version == "3"
    assert h.inputs == ["Synthetic published preparation."]
    ledger = await calls(h)
    assert (
        len(ledger) == 1 and ledger[0]["state"] == "SUCCESS" and ledger[0]["applied_at"] is not None
    )
    assert ledger[0]["outcome"]["completion_tokens_state"] == "NOT_APPLICABLE"
    assert "completion_tokens" not in ledger[0]["outcome"]["usage"]
    assert not ({"ticket", "vectors", "wire"} & set(created.json()["result"]))
    replay = await send(h, "/builds", body, "build")
    assert replay.json() == created.json() | {"outcome": "REPLAY"}
    assert (await send(h, "/builds", body, "build-dedup")).status_code == 200
    assert h.posts == 1 and len(await calls(h)) == 1
    published = await send(
        h,
        "/publish",
        {
            "schema_version": 1,
            "expected_draft_version": "1",
            "expected_activation_version": "0",
            "build_id": build.build_id,
            "expected_build_version": build.build_version,
        },
        "publish",
    )
    assert published.status_code == 200, published.text
    release = published.json()["result"]["release_id"]
    active = (await h.client.get(CONFIGURATION + "/active")).json()
    assert (active["release_id"], active["activation_version"]) == (release, "1")
    await save(
        h,
        key="draft-only",
        source=source,
        version="2",
        content="Synthetic draft must stay private.",
    )
    current = await state(h)
    assert current.active_build_id == build.build_id and current.activation_version == "1"
    assert current.rollback_targets[0].eligible
    rollback = await send(
        h,
        "/rollback",
        {"schema_version": 1, "expected_activation_version": "1", "release_id": release},
        "rollback",
    )
    assert rollback.status_code == 200 and rollback.json()["result"]["activation_version"] == "2"
    revoked = await send(
        h,
        f"/sources/{source}/revoke",
        {"schema_version": 1, "expected_source_version": "3", "expected_activation_version": "2"},
        "revoke",
    )
    assert revoked.status_code == 200 and revoked.json()["result"]["activation_version"] == "3"
    legacy = await send(
        h,
        "",
        {"expected_activation_version": "3", "release_id": release},
        "legacy-rollback",
        url=CONFIGURATION + "/rollback",
    )
    assert legacy.status_code == 409 and legacy.json()["error"]["code"] == "ROLLBACK_NOT_ALLOWED"
    deleted = await send(
        h,
        f"/sources/{source}/delete",
        {"schema_version": 1, "expected_source_version": "4", "expected_activation_version": "3"},
        "delete",
    )
    assert deleted.status_code == 200, deleted.text
    assert not (await state(h)).sources
    async with h.migrator.connect() as connection:
        for table in ("knowledge_revisions", "knowledge_chunks", "knowledge_build_chunks"):
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM platform." + table + " WHERE workspace_id=:w"),
                    {"w": A},
                )
            ).scalar_one() == 0


@pytest.mark.parametrize("knowledge", [False], indirect=True)
async def test_disabled_build_error_is_visible_and_old_publication_survives_replays(knowledge):
    h = knowledge
    release = await configuration(h, publish=True)
    await confirmed(h)
    body = await build_body(h)
    response = await send(h, "/builds", body, "build")
    assert response.status_code == 200
    current = await state(h)
    build = current.builds[0]
    assert current.embedding_mode == "DISABLED" and build.state == "ERROR"
    assert build.error_code == "EMBEDDING_ERROR" and (
        current.release_id,
        current.activation_version,
    ) == (release, "1")
    ledger = await calls(h)
    assert len(ledger) == 1 and ledger[0]["outcome"]["error_code"] == "DISABLED"
    await send(h, "/builds", body, "build")
    await send(h, "/builds", body, "new-key")
    assert h.posts == 0 and len(await calls(h)) == 1
    rejected = await send(
        h,
        "/publish",
        {
            "schema_version": 1,
            "expected_draft_version": "1",
            "expected_activation_version": "1",
            "build_id": build.build_id,
            "expected_build_version": build.build_version,
        },
        "publish-bad",
    )
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "BUILD_NOT_READY"


async def test_completion_accounts_after_actual_owner_loss_but_vectors_are_not_applied(knowledge):
    h = knowledge
    await configuration(h)
    await confirmed(h)
    body = await build_body(h)
    h.behavior = "owner-loss"
    response = await send(h, "/builds", body, "build")
    assert response.status_code == 403 and response.json()["error"]["code"] == "ACCESS_DENIED"
    ledger = await calls(h)
    assert len(ledger) == 1 and ledger[0]["state"] == "SUCCESS" and ledger[0]["applied_at"] is None
    assert ledger[0]["outcome"]["cost"]["status"] == "CONFIRMED"
    async with h.migrator.begin() as connection:
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM platform.knowledge_build_chunks WHERE workspace_id=:w AND embedding IS NOT NULL"
                ),
                {"w": A},
            )
        ).scalar_one() == 0
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:w AND user_account_id=:u"
            ),
            {"w": A, "u": UA},
        )
    assert (await send(h, "/builds", body, "build")).json()["outcome"] == "REPLAY"
    assert (await send(h, "/builds", body, "new-key")).status_code == 200
    assert h.posts == 1 and len(await calls(h)) == 1


async def test_unknown_transport_and_competing_build_replay_do_not_resend(knowledge):
    h = knowledge
    await confirmed(h)
    body = await build_body(h)
    h.behavior = "unknown"
    responses = await asyncio.gather(
        send(h, "/builds", body, "build"), send(h, "/builds", body, "build")
    )
    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(response.json()["outcome"] for response in responses) == ["ACCEPTED", "REPLAY"]
    assert (await state(h)).builds[0].state == "UNKNOWN"
    await send(h, "/builds", body, "new-key")
    assert h.posts == 1 and len(await calls(h)) == 1


async def test_source_confirmation_cas_and_chunk_limit_before_any_embedding(knowledge):
    h = knowledge
    await save(h, content="€" * 682)
    source = (await state(h)).sources[0]
    assert source.preview.issues == ["CHUNK_LIMIT"] and not source.preview.chunks
    response = await send(
        h,
        f"/sources/{source.source_id}/confirm",
        {
            "schema_version": 1,
            "expected_source_version": "1",
            "revision_id": source.head.revision_id,
            "canonical_sha256": source.head.canonical_sha256,
        },
        "confirm-bad",
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "CHUNK_LIMIT"
    await save(
        h, key="fixed", source=source.source_id, version="1", content="Synthetic bounded text."
    )
    source = (await state(h)).sources[0]
    body = {
        "schema_version": 1,
        "expected_source_version": "2",
        "revision_id": source.head.revision_id,
        "canonical_sha256": source.head.canonical_sha256,
    }
    responses = await asyncio.gather(
        send(h, f"/sources/{source.source_id}/confirm", body, "one"),
        send(h, f"/sources/{source.source_id}/confirm", body, "two"),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert h.posts == 0 and not await calls(h)


async def test_http_isolation_owner_csrf_raw_body_and_closed_path_payload(knowledge):
    h = knowledge
    assert (
        await h.client.get(KNOWLEDGE.replace(str(A), str(B)).replace(str(BA), str(BB)))
    ).status_code == 403
    assert (await h.client.get(KNOWLEDGE.replace(str(BA), str(BB)))).status_code == 404
    body = {
        "schema_version": 1,
        "source_id": None,
        "expected_source_version": "0",
        "title": "Synthetic",
        "format": "TEXT",
        "text": "Synthetic text.",
        "source_label": "Synthetic owner",
    }
    raw = json.dumps(body)
    raw += " " * (4096 - len(raw.encode()))
    command_headers = {
        **headers(h.client, h.csrf),
        "Idempotency-Key": "limit",
        "Content-Type": "application/json",
    }
    accepted = await h.client.post(KNOWLEDGE + "/sources", content=raw, headers=command_headers)
    assert accepted.status_code == 200, accepted.text
    rejected = await h.client.post(
        KNOWLEDGE + "/sources", content=raw + " ", headers=command_headers
    )
    assert rejected.status_code == 413
    assert (
        await h.client.post(
            KNOWLEDGE + "/sources",
            json=body,
            headers={"Origin": str(h.client.base_url).rstrip("/"), "Idempotency-Key": "csrf"},
        )
    ).status_code == 403
    assert (
        await h.client.post(
            KNOWLEDGE + "/sources",
            json=body,
            headers=command_headers | {"Origin": "http://evil.invalid"},
        )
    ).status_code == 403
    for options in (
        command_headers | {"If-Match": '"1"'},
        [*command_headers.items(), ("Idempotency-Key", "second")],
    ):
        assert (
            await h.client.post(KNOWLEDGE + "/sources", json=body, headers=options)
        ).status_code == 422
    source = (await state(h)).sources[0]
    path_body = {
        "schema_version": 1,
        "expected_source_version": "1",
        "revision_id": source.head.revision_id,
        "canonical_sha256": source.head.canonical_sha256,
        "source_id": source.source_id,
    }
    assert (
        await send(h, f"/sources/{source.source_id}/confirm", path_body, "forged")
    ).status_code == 422
    async with h.migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:w AND user_account_id=:u"
            ),
            {"w": A, "u": UA},
        )
    assert (await h.client.get(KNOWLEDGE)).status_code == 403
    assert (
        await h.client.post(KNOWLEDGE + "/sources", content=raw, headers=command_headers)
    ).status_code == 403
    assert not await calls(h)
