"""Owned synthetic SQL fixtures; storage and provider effects need separate proofs."""

import hashlib
import io
import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest_asyncio
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest_asyncio.fixture
async def portfolio_pg():
    runtime = create_async_engine(
        os.environ["ASM_DATABASE_URL"], poolclass=NullPool, hide_parameters=True
    )
    migrator = create_async_engine(
        os.environ["ASM_MIGRATION_DATABASE_URL"], poolclass=NullPool, hide_parameters=True
    )
    h = SimpleNamespace(
        runtime=runtime,
        migrator=migrator,
        ws=uuid4(),
        actor=uuid4(),
        business=uuid4(),
        other_business=uuid4(),
        other_ws=uuid4(),
        other_actor=uuid4(),
        foreign_business=uuid4(),
    )
    async with migrator.begin() as c:
        assert (
            await c.execute(
                text(
                    "SELECT current_user,current_database(),(SELECT version_num FROM platform.alembic_version)"
                )
            )
        ).one() == ("asm_migrator", "asm_test", "0035")
        for actor in (h.actor, h.other_actor):
            await c.execute(
                text("INSERT INTO platform.user_accounts(id) VALUES(:id)"), {"id": actor}
            )
        for ws, actor in ((h.ws, h.actor), (h.other_ws, h.other_actor)):
            await c.execute(text("INSERT INTO platform.workspaces(id) VALUES(:id)"), {"id": ws})
            await c.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) VALUES(:ws,:actor,'OWNER')"
                ),
                dict(ws=ws, actor=actor),
            )
        for ws, business in (
            (h.ws, h.business),
            (h.ws, h.other_business),
            (h.other_ws, h.foreign_business),
        ):
            await c.execute(
                text(
                    "INSERT INTO app.businesses(workspace_id,id,name) VALUES(:ws,:id,'portfolio SQL synthetic')"
                ),
                dict(ws=ws, id=business),
            )
    try:
        yield h
    finally:
        # Only this fixture's random workspaces. Retain all other test/user rows.
        async with migrator.begin() as c:
            params = {"a": h.ws, "b": h.other_ws}
            for table in (
                "portfolio_release_builds",
                "knowledge_release_builds",
                "knowledge_embedding_calls",
                "business_configuration_receipts",
                "business_configuration_state",
                "business_configuration_releases",
                "portfolio_build_items",
                "portfolio_builds",
            ):
                await c.execute(
                    text(f"DELETE FROM platform.{table} WHERE workspace_id IN (:a,:b)"), params
                )
            await c.execute(
                text(
                    "UPDATE platform.portfolio_items SET head_revision_id=NULL,confirmed_revision_id=NULL WHERE workspace_id IN (:a,:b)"
                ),
                params,
            )
            for table in ("portfolio_revisions", "portfolio_items", "vision_analyses"):
                await c.execute(
                    text(f"DELETE FROM platform.{table} WHERE workspace_id IN (:a,:b)"), params
                )
            await c.execute(
                text(
                    "UPDATE platform.portfolio_assets SET accepted_version_id=NULL,pending_version_id=NULL WHERE workspace_id IN (:a,:b)"
                ),
                params,
            )
            for table in ("portfolio_asset_versions", "portfolio_assets", "portfolio_ai_sessions"):
                await c.execute(
                    text(f"DELETE FROM platform.{table} WHERE workspace_id IN (:a,:b)"), params
                )
            await c.execute(
                text("DELETE FROM app.businesses WHERE workspace_id IN (:a,:b)"), params
            )
            await c.execute(
                text("DELETE FROM platform.workspace_memberships WHERE workspace_id IN (:a,:b)"),
                params,
            )
            await c.execute(text("DELETE FROM platform.workspaces WHERE id IN (:a,:b)"), params)
            await c.execute(
                text("DELETE FROM platform.user_accounts WHERE id IN (:a,:b)"),
                {"a": h.actor, "b": h.other_actor},
            )
        await runtime.dispose()
        await migrator.dispose()


@asynccontextmanager
async def owner(h, *, ws=None, actor=None):
    async with h.runtime.begin() as c:
        assert (await c.execute(text("SELECT current_user"))).scalar_one() == "asm_runtime"
        await c.execute(
            text(
                "SELECT set_config('asm.workspace_id',:ws,true),set_config('asm.actor_id',:actor,true),set_config('asm.actor_kind','user_account',true),set_config('asm.correlation_id',:correlation,true),set_config('asm.context_xid',pg_current_xact_id()::text,true)"
            ),
            dict(ws=str(ws or h.ws), actor=str(actor or h.actor), correlation=str(uuid4())),
        )
        yield c


async def call(h, name, values, *, ws=None, actor=None):
    # Function and argnames are test constants, never user input.
    params = {
        f"p{i}": json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
        for i, v in enumerate(values)
    }
    expressions = [
        f"CAST(:p{i} AS jsonb)" if isinstance(v, (dict, list)) else f":p{i}"
        for i, v in enumerate(values)
    ]
    async with owner(h, ws=ws, actor=actor) as c:
        return (
            await c.execute(text(f"SELECT platform.{name}({','.join(expressions)})"), params)
        ).scalar_one()


async def command(h, operation, payload, *, key=None, business=None, **scope):
    return await call(
        h,
        "portfolio_owner_command",
        [business or h.business, operation, key or str(uuid4()), {"schema_version": 1, **payload}],
        **scope,
    )


def image_manifest():
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), (50, 80, 110)).save(stream, format="PNG")
    data = stream.getvalue()
    return {
        "mime_type": "image/png",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": 64,
        "height": 64,
    }


async def asset(h, *, origin="MY_WORK", business=None, ready=True):
    business = business or h.business
    manifest = image_manifest()
    created = await command(
        h,
        "PORTFOLIO_UPLOAD_CREATE",
        {
            "asset_id": None,
            "expected_asset_version": "0",
            "origin": origin,
            **{k: manifest[k] for k in ("mime_type", "size_bytes", "sha256")},
        },
        business=business,
    )
    r = created["result"]
    r["asset_id"], r["version_id"], r["upload_id"] = (
        UUID(r[k]) for k in ("asset_id", "version_id", "upload_id")
    )
    if ready:
        receive = await call(
            h, "portfolio_upload_begin", [business, r["asset_id"], r["version_id"], r["upload_id"]]
        )
        ticket = UUID(receive["ticket"])
        permit = await call(
            h,
            "portfolio_upload_prepare",
            [business, r["asset_id"], r["version_id"], r["upload_id"], ticket, manifest],
        )
        assert permit["storage_key"].startswith(f"workspaces/{h.ws}/portfolio/")
        # Explicit synthetic SQL completion; no S3 or decoded-pixel proof claimed here.
        await call(
            h,
            "portfolio_upload_complete",
            [r["upload_id"], ticket, {"kind": "STORED", "manifest": manifest, "error_code": None}],
        )
        r = (
            await command(
                h,
                "PORTFOLIO_UPLOAD_FINALIZE",
                {k: str(r[k]) for k in ("asset_id", "version_id", "upload_id")}
                | {"expected_asset_version": r["asset_version"]},
                business=business,
            )
        )["result"]
        for k in ("asset_id", "version_id", "upload_id"):
            r[k] = UUID(r[k])
    return r, manifest


async def session(h, *, business=None):
    result = await call(
        h,
        "portfolio_session_admit",
        [
            business or h.business,
            None,
            {
                "profile_id": "SYNTHETIC_VISION_PORTFOLIO_V1",
                "execution": "CONTROLLED",
                "eligibility": "EVAL_ONLY",
                "max_calls": 4,
                "max_cost": "10",
                "duration_seconds": 900,
            },
        ],
    )
    return UUID(result["session_id"])


def vision_completion(*, kind="SUCCESS"):
    return {
        "kind": kind,
        "result": {
            "revision": "vision_result_v1",
            "subject": "Rose",
            "styles": ["blackwork"],
            "details": ["Fine lines"],
            "uncertainty": ["Scale cannot be determined"],
            "scale": "UNKNOWN",
        }
        if kind == "SUCCESS"
        else None,
        "derivative_sha256": "d" * 64 if kind == "SUCCESS" else None,
        "usage": {
            "input_tokens": 200 if kind == "SUCCESS" else None,
            "output_tokens": 80 if kind == "SUCCESS" else None,
        },
        "cost": {
            "status": "CONFIRMED" if kind == "SUCCESS" else "UNKNOWN",
            "amount": "0.01" if kind == "SUCCESS" else None,
            "currency": "RUB",
        },
        "identity": {
            "status": "CONFIRMED" if kind == "SUCCESS" else "UNVERIFIED",
            "source": "BODY" if kind == "SUCCESS" else "NONE",
            "provider": "OpenAI" if kind == "SUCCESS" else None,
            "model": "openai/gpt-4o-mini" if kind == "SUCCESS" else None,
        },
        "request_id": "sql-synthetic" if kind == "SUCCESS" else None,
        "error_code": None if kind == "SUCCESS" else "TIMEOUT",
    }
