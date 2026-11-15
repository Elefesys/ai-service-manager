"""Actual PostgreSQL capability isolation, one-shot accounting and publication.

These are SQL protocol tests. Private S3/browser/pixel evidence is separate.
"""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from m5_configuration_fixtures import configuration_bundle
from m5_portfolio_fixtures import asset, call, command, owner, session, vision_completion
from m5_portfolio_fixtures import portfolio_pg as portfolio_pg
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def rejected(awaitable, code):
    with pytest.raises(DBAPIError) as error:
        await awaitable
    assert code in str(error.value.orig)


async def test_fresh_owner_purge_permit_can_finish_after_prior_failed_delete(portfolio_pg):
    h = portfolio_pg
    created, _ = await asset(h)
    state = await call(h, "portfolio_owner_read", [h.business])
    await command(
        h,
        "PORTFOLIO_DELETE",
        {
            "schema_version": 1,
            "asset_id": str(created["asset_id"]),
            "expected_asset_version": state["assets"][0]["version"],
            "expected_activation_version": state["activation_version"],
        },
    )
    args = [h.business, created["asset_id"], created["version_id"]]
    first = await call(h, "portfolio_purge_begin", args)
    failed = await call(
        h,
        "portfolio_purge_complete",
        [created["version_id"], UUID(first["ticket"]), "DEPENDENCY_UNAVAILABLE"],
    )
    assert failed["state"] == "PURGE_PENDING"
    # Explicit TEST clock advance on only this fixture's version; no real DELETE.
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.portfolio_asset_versions SET purge_deadline=clock_timestamp()-interval '1 second' WHERE workspace_id=:ws AND id=:version"
            ),
            {"ws": h.ws, "version": created["version_id"]},
        )
    second = await call(h, "portfolio_purge_begin", args)
    assert first["ticket"] != second["ticket"]
    await rejected(
        call(h, "portfolio_purge_complete", [created["version_id"], UUID(first["ticket"]), None]),
        "ACCESS_DENIED",
    )
    complete = await call(
        h, "portfolio_purge_complete", [created["version_id"], UUID(second["ticket"]), None]
    )
    assert complete == {
        "version_id": str(created["version_id"]),
        "state": "PURGED",
        "outcome": "DELETED",
    }


async def test_tables_are_forced_rls_private_and_owner_scope_is_not_a_bare_uuid(portfolio_pg):
    h = portfolio_pg
    async with h.migrator.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT relname,relowner::regrole::text,relrowsecurity,relforcerowsecurity,has_table_privilege('asm_runtime',oid,'SELECT,INSERT,UPDATE,DELETE') FROM pg_class WHERE relnamespace='platform'::regnamespace AND relname IN ('portfolio_assets','portfolio_asset_versions','portfolio_ai_sessions','vision_analyses','portfolio_items','portfolio_revisions','portfolio_builds','portfolio_build_items','portfolio_release_builds') ORDER BY relname"
                )
            )
        ).all()
    assert len(rows) == 9 and all(row[1:] == ("asm_migrator", True, True, False) for row in rows)
    await rejected(call(h, "portfolio_owner_read", [h.foreign_business]), "NOT_FOUND")
    await rejected(
        call(h, "portfolio_owner_read", [h.business], ws=h.other_ws, actor=h.other_actor),
        "NOT_FOUND",
    )
    async with h.runtime.connect() as c:
        with pytest.raises(DBAPIError):
            await c.execute(text("SELECT * FROM platform.portfolio_assets"))


async def test_upload_prepare_finalize_private_preview_and_receipt_replay(portfolio_pg):
    h = portfolio_pg
    r, manifest = await asset(h)
    preview = await call(h, "portfolio_preview", [h.business, r["asset_id"], r["version_id"]])
    assert preview["manifest"] == manifest and preview["state"] == "READY"
    await rejected(
        call(h, "portfolio_preview", [h.other_business, r["asset_id"], r["version_id"]]),
        "NOT_FOUND",
    )
    await rejected(
        call(
            h,
            "portfolio_upload_begin",
            [h.business, r["asset_id"], r["version_id"], r["upload_id"]],
        ),
        "UPLOAD_NOT_ALLOWED",
    )
    state = await call(h, "portfolio_owner_read", [h.business])
    assert state["assets"][0]["accepted_version_id"] == str(r["version_id"])
    assert "storage_key" not in json.dumps(state) and "ticket" not in json.dumps(state)


async def test_upload_ticket_binds_manifest_and_uncertain_put_cannot_begin_again(portfolio_pg):
    h = portfolio_pg
    r, m = await asset(h, ready=False)
    args = [h.business, r["asset_id"], r["version_id"], r["upload_id"]]
    receive = await call(h, "portfolio_upload_begin", args)
    ticket = UUID(receive["ticket"])
    await rejected(
        call(h, "portfolio_upload_prepare", args + [ticket, m | {"sha256": "f" * 64}]),
        "MANIFEST_MISMATCH",
    )
    await call(h, "portfolio_upload_prepare", args + [ticket, m])
    await call(
        h,
        "portfolio_upload_complete",
        [
            r["upload_id"],
            ticket,
            {"kind": "UNKNOWN", "manifest": None, "error_code": "DEPENDENCY_TIMEOUT"},
        ],
    )
    await rejected(call(h, "portfolio_upload_begin", args), "UPLOAD_NOT_ALLOWED")
    await rejected(
        command(
            h,
            "PORTFOLIO_UPLOAD_FINALIZE",
            {
                "asset_id": str(r["asset_id"]),
                "expected_asset_version": r["asset_version"],
                "version_id": str(r["version_id"]),
                "upload_id": str(r["upload_id"]),
            },
        ),
        "UPLOAD_NOT_READY",
    )
    recovery = await call(h, "portfolio_upload_recover", args)
    assert recovery["operation"] == "HEAD_GET_ONLY" and recovery["storage_key"].endswith(
        str(r["upload_id"])
    )
    await rejected(call(h, "portfolio_upload_recover", args), "UPLOAD_NOT_ALLOWED")


async def test_abandoned_intent_remains_tombstone_even_after_delete_ack(portfolio_pg):
    h = portfolio_pg
    r, m = await asset(h, ready=False)
    await command(
        h,
        "PORTFOLIO_UPLOAD_ABANDON",
        {
            "asset_id": str(r["asset_id"]),
            "expected_asset_version": r["asset_version"],
            "version_id": str(r["version_id"]),
            "upload_id": str(r["upload_id"]),
        },
    )
    claimed = await call(h, "portfolio_cleanup_claim", [1])
    assert len(claimed) == 1
    result = await call(
        h,
        "portfolio_cleanup_complete",
        [UUID(claimed[0]["version_id"]), UUID(claimed[0]["claim_token"]), None],
    )
    assert result["outcome"] == "DELETED" and result["next_check_at"] is not None
    async with h.migrator.connect() as c:
        row = (
            await c.execute(
                text(
                    "SELECT state,cleanup_attempts,cleanup_outcome FROM platform.portfolio_asset_versions WHERE id=:id"
                ),
                {"id": r["version_id"]},
            )
        ).one()
    assert row == ("ABANDONED", 1, "DELETED")


async def test_unknown_vision_is_identity_deduped_across_fresh_sessions(portfolio_pg):
    h = portfolio_pg
    r, m = await asset(h)
    reserved = await call(
        h, "vision_owner_reserve", [h.business, r["asset_id"], r["version_id"], await session(h)]
    )
    await call(
        h,
        "vision_complete",
        [
            UUID(reserved["analysis_id"]),
            UUID(reserved["ticket"]),
            vision_completion(kind="UNKNOWN"),
        ],
    )
    replay = await call(
        h, "vision_owner_reserve", [h.business, r["asset_id"], r["version_id"], await session(h)]
    )
    assert (
        replay["status"] == "REPLAY"
        and replay["ticket"] is None
        and replay["analysis_id"] == reserved["analysis_id"]
        and replay["state"] == "UNKNOWN"
    )
    async with h.migrator.connect() as c:
        assert (
            await c.execute(
                text("SELECT count(*) FROM platform.vision_analyses WHERE workspace_id=:ws"),
                {"ws": h.ws},
            )
        ).scalar_one() == 1


async def test_completion_accounts_after_owner_loss_but_apply_is_fresh(portfolio_pg):
    h = portfolio_pg
    r, m = await asset(h)
    s = await session(h)
    reserved = await call(
        h, "vision_owner_reserve", [h.business, r["asset_id"], r["version_id"], s]
    )
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET status='REVOKED',version=version+1 WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            dict(ws=h.ws, actor=h.actor),
        )
    # Completion has only its opaque ticket; no OWNER context is used or needed.
    async with h.runtime.begin() as c:
        result = (
            await c.execute(
                text("SELECT platform.vision_complete(:analysis,:ticket,CAST(:outcome AS jsonb))"),
                {
                    "analysis": UUID(reserved["analysis_id"]),
                    "ticket": UUID(reserved["ticket"]),
                    "outcome": json.dumps(vision_completion()),
                },
            )
        ).scalar_one()
    assert result["state"] == "SUCCESS"
    await rejected(
        call(
            h, "vision_apply", [h.business, UUID(reserved["analysis_id"]), UUID(reserved["ticket"])]
        ),
        "ACCESS_DENIED",
    )
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.workspace_memberships SET status='ACTIVE',version=version+1 WHERE workspace_id=:ws AND user_account_id=:actor"
            ),
            dict(ws=h.ws, actor=h.actor),
        )
    applied = await call(
        h, "vision_apply", [h.business, UUID(reserved["analysis_id"]), UUID(reserved["ticket"])]
    )
    assert applied["applied"]


async def test_aggregate_reservation_budget_serializes_competing_vision_operations(portfolio_pg):
    h = portfolio_pg
    s = await session(h)
    assets = [(await asset(h))[0] for _ in range(3)]
    first = await call(
        h, "vision_owner_reserve", [h.business, assets[0]["asset_id"], assets[0]["version_id"], s]
    )
    await call(
        h,
        "vision_complete",
        [UUID(first["analysis_id"]), UUID(first["ticket"]), vision_completion(kind="UNKNOWN")],
    )
    outcomes = await asyncio.gather(
        *(
            call(h, "vision_owner_reserve", [h.business, a["asset_id"], a["version_id"], s])
            for a in assets[1:]
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(o, dict) for o in outcomes) == 1
    assert (
        sum(isinstance(o, DBAPIError) and "BUDGET_EXHAUSTED" in str(o.orig) for o in outcomes) == 1
    )
    async with h.migrator.connect() as c:
        usage = (
            await c.execute(
                text("SELECT platform.portfolio_session_usage(:ws,:business,:s)"),
                dict(ws=h.ws, business=h.business, s=s),
            )
        ).scalar_one()
    assert usage["calls"] == 2 and float(usage["held_cost"]) == 7.78


async def test_inspiration_cannot_be_confirmed_as_my_work_and_origins_are_immutable(portfolio_pg):
    h = portfolio_pg
    r, m = await asset(h, origin="INSPIRATION")
    saved = await command(
        h,
        "PORTFOLIO_SAVE",
        {
            "item_id": None,
            "expected_item_version": "0",
            "asset_id": str(r["asset_id"]),
            "description": "A rose sample",
            "attributes": {"subject": "rose", "styles": [], "placement": None},
            "service_id": None,
            "analysis_id": None,
        },
    )
    x = saved["result"]
    await rejected(
        command(
            h,
            "PORTFOLIO_CONFIRM",
            {
                "item_id": x["item_id"],
                "expected_item_version": x["item_version"],
                "revision_id": x["revision_id"],
                "canonical_sha256": x["canonical_sha256"],
                "confirm_my_work": True,
                "show_permission": True,
            },
        ),
        "MY_WORK_REQUIRED",
    )
    await rejected(
        command(
            h,
            "PORTFOLIO_UPLOAD_CREATE",
            {
                "asset_id": str(r["asset_id"]),
                "expected_asset_version": r["asset_version"],
                "origin": "MY_WORK",
                **{k: m[k] for k in ("mime_type", "size_bytes", "sha256")},
            },
        ),
        "ORIGIN_IMMUTABLE",
    )


async def test_explicit_empty_composite_publish_has_no_ai_reservation_and_legacy_cannot_drop_link(
    portfolio_pg,
):
    h = portfolio_pg
    async with owner(h) as c:
        await c.execute(
            text("SELECT platform.configuration_command(:business,'EDIT',:key,CAST(:p AS jsonb))"),
            dict(
                business=h.business,
                key=str(uuid4()),
                p=json.dumps({"expected_draft_version": "0", "bundle": configuration_bundle()}),
            ),
        )
    state = await call(h, "portfolio_owner_read", [h.business])
    build = (
        await command(
            h,
            "PORTFOLIO_BUILD_CREATE",
            {"expected_items_hash": state["items_hash"], "revision_ids": []},
        )
    )["result"]
    assert build["build_state"] == "READY"
    published = await command(
        h,
        "PORTFOLIO_PUBLISH",
        {
            "expected_draft_version": "1",
            "expected_activation_version": "0",
            "knowledge_build_id": None,
            "expected_knowledge_build_version": None,
            "portfolio_build_id": build["build_id"],
            "expected_portfolio_build_version": build["build_version"],
        },
    )
    assert published["result"]["activation_version"] == "1"
    async with owner(h) as c:
        with pytest.raises(DBAPIError) as refused:
            await c.execute(
                text(
                    "SELECT platform.configuration_command(:business,'PUBLISH',:key,CAST(:p AS jsonb))"
                ),
                dict(
                    business=h.business,
                    key=str(uuid4()),
                    p=json.dumps(
                        {"expected_draft_version": "1", "expected_activation_version": "1"}
                    ),
                ),
            )
        assert "PORTFOLIO_BUILD_REQUIRED" in str(refused.value.orig)
    async with h.migrator.connect() as c:
        assert (
            await c.execute(
                text(
                    "SELECT count(*) FROM platform.knowledge_embedding_calls WHERE workspace_id=:ws"
                ),
                {"ws": h.ws},
            )
        ).scalar_one() == 0
        assert (
            await c.execute(
                text("SELECT count(*) FROM platform.vision_analyses WHERE workspace_id=:ws"),
                {"ws": h.ws},
            )
        ).scalar_one() == 0


async def test_confirmed_my_work_nonempty_build_applies_exact_vectors_and_publishes(portfolio_pg):
    h = portfolio_pg
    r, _ = await asset(h)
    async with owner(h) as c:
        await c.execute(
            text("SELECT platform.configuration_command(:business,'EDIT',:key,CAST(:p AS jsonb))"),
            dict(
                business=h.business,
                key=str(uuid4()),
                p=json.dumps({"expected_draft_version": "0", "bundle": configuration_bundle()}),
            ),
        )
    saved = (
        await command(
            h,
            "PORTFOLIO_SAVE",
            {
                "item_id": None,
                "expected_item_version": "0",
                "asset_id": str(r["asset_id"]),
                "description": "Rose with fine black lines",
                "attributes": {"subject": "rose", "styles": ["blackwork"], "placement": None},
                "service_id": "consultation",
                "analysis_id": None,
            },
        )
    )["result"]
    confirmed = (
        await command(
            h,
            "PORTFOLIO_CONFIRM",
            {
                "item_id": saved["item_id"],
                "expected_item_version": saved["item_version"],
                "revision_id": saved["revision_id"],
                "canonical_sha256": saved["canonical_sha256"],
                "confirm_my_work": True,
                "show_permission": True,
            },
        )
    )["result"]
    state = await call(h, "portfolio_owner_read", [h.business])
    build = (
        await command(
            h,
            "PORTFOLIO_BUILD_CREATE",
            {
                "expected_items_hash": state["items_hash"],
                "revision_ids": [saved["revision_id"]],
            },
        )
    )["result"]
    assert build["build_state"] == "PLANNED"
    reserved = await call(
        h, "portfolio_build_reserve", [h.business, UUID(build["build_id"]), await session(h)]
    )
    assert reserved["status"] == "RESERVED" and len(json.loads(reserved["wire"])["input"]) == 1
    vectors = [[1.0] + [0.0] * 1535]
    completed = await call(
        h,
        "knowledge_embedding_complete",
        [
            UUID(reserved["call_id"]),
            UUID(reserved["ticket"]),
            {
                "kind": "SUCCESS",
                "vectors": vectors,
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
                "cost": {"status": "CONFIRMED", "amount": "0.001", "currency": "RUB"},
                "identity": {
                    "status": "CONFIRMED",
                    "source": "BODY",
                    "provider": "OpenAI",
                    "model": "openai/text-embedding-3-small",
                },
                "request_id": "synthetic-index",
                "error_code": None,
            },
        ],
    )
    assert completed["state"] == "SUCCESS"
    applied = await call(
        h,
        "portfolio_build_apply",
        [h.business, UUID(reserved["call_id"]), UUID(reserved["ticket"]), vectors],
    )
    assert applied["state"] == "READY"
    published = await command(
        h,
        "PORTFOLIO_PUBLISH",
        {
            "expected_draft_version": "1",
            "expected_activation_version": "0",
            "knowledge_build_id": None,
            "expected_knowledge_build_version": None,
            "portfolio_build_id": build["build_id"],
            "expected_portfolio_build_version": applied["build_version"],
        },
    )
    state = await call(h, "portfolio_owner_read", [h.business])
    assert state["active_release_id"] == published["result"]["release_id"]
    assert state["active_portfolio_build_id"] == build["build_id"]
    assert state["items"][0]["head"]["confirmed"] and state["items"][0]["show_permission"]
    # Actual pgvector execution as the migrator checks the private selector;
    # this is not a substitute for runtime Client authorization proof.
    async with h.migrator.connect() as c:
        projection = (
            await c.execute(
                text(
                    "SELECT platform.portfolio_select(:ws,:business,platform.portfolio_availability(:ws,:business,:release,1),CAST(:vector AS extensions.vector(1536)),'rose')"
                ),
                dict(
                    ws=h.ws,
                    business=h.business,
                    release=UUID(published["result"]["release_id"]),
                    vector=json.dumps(vectors[0]),
                ),
            )
        ).scalar_one()
    assert projection["status"] == "RESULTS"
    assert projection["matches"][0]["item_id"] == saved["item_id"]
    assert len(json.dumps(projection, ensure_ascii=False).encode()) <= 2048
    await command(
        h,
        "PORTFOLIO_REVOKE",
        {
            "item_id": saved["item_id"],
            "expected_item_version": confirmed["item_version"],
            "expected_activation_version": "1",
        },
    )
    async with h.migrator.connect() as c:
        projection = (
            await c.execute(
                text(
                    "SELECT platform.portfolio_select(:ws,:business,platform.portfolio_availability(:ws,:business,:release,2),CAST(:vector AS extensions.vector(1536)),'rose')"
                ),
                dict(
                    ws=h.ws,
                    business=h.business,
                    release=UUID(published["result"]["release_id"]),
                    vector=json.dumps(vectors[0]),
                ),
            )
        ).scalar_one()
    assert projection["status"] == "EMPTY"
