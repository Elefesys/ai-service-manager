"""Auth fresh/upgrade/replay/reversal/provisioning evidence: disposable asm_test only."""

import os
from uuid import UUID, uuid4

import pytest
from asm.auth.crypto import new_token
from asm.foundation import RuntimeDatabase, Settings, create_app
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from test_tenancy_migrations import migrate

from scripts.provision_local_auth import provision

pytestmark = pytest.mark.integration


async def test_auth_m11_upgrade_replay_provisioning_disposable_downgrade_reupgrade():
    settings = Settings()
    migration_url = os.environ["ASM_MIGRATION_DATABASE_URL"]
    assert settings.environment == "TEST"
    assert make_url(settings.database_url.get_secret_value()).database == "asm_test"
    assert make_url(migration_url).database == "asm_test"
    assert make_url(migration_url).username == "asm_migrator"
    runtime = RuntimeDatabase(settings)
    migrator = create_async_engine(migration_url, hide_parameters=True)
    marker = uuid4()
    ids = None
    try:
        await migrate("downgrade", "0002")
        with pytest.raises(RuntimeError, match="capability/schema mismatch"):
            await runtime.check()
        async with migrator.begin() as connection:
            await connection.execute(
                text("INSERT INTO platform.workspaces(id) VALUES (:id)"), {"id": marker}
            )
        await migrate("upgrade", "head")
        await migrate("upgrade", "head")
        await runtime.check()
        password = SecretStr(new_token())
        identifier = "synthetic." + uuid4().hex
        ids = await provision("TEST", migration_url, identifier, password.get_secret_value())
        # Repeat setup cannot reset a password or silently create another owner.
        with pytest.raises(Exception):
            await provision("TEST", migration_url, identifier, new_token())
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://localhost:8000"
            ) as client:
                challenge = await client.post(
                    "/api/v1/auth/bootstrap",
                    json={},
                    headers={"Origin": "http://localhost:8000", "X-CSRF-Bootstrap": "1"},
                )
                assert challenge.status_code == 200
                login = await client.post(
                    "/api/v1/auth/login",
                    json={"login": identifier, "password": password.get_secret_value()},
                    headers={
                        "Origin": "http://localhost:8000",
                        "X-CSRF-Token": challenge.json()["csrf_token"],
                    },
                )
                assert login.status_code == 200
                result = await client.get(
                    f"/api/v1/workspaces/{ids['workspace_id']}/businesses/{ids['business_id']}"
                )
                assert result.status_code == 200
        await migrate("downgrade", "0002")
        async with migrator.connect() as connection:
            assert (
                await connection.execute(text("SELECT to_regclass('platform.auth_sessions')"))
            ).scalar_one() is None
            assert (
                await connection.execute(text("SELECT to_regclass('platform.auth_credentials')"))
            ).scalar_one() is None
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM platform.workspaces WHERE id=:id"), {"id": marker}
                )
            ).scalar_one() == 1
            assert (
                await connection.execute(
                    text("SELECT count(*) FROM app.businesses WHERE workspace_id=:id"),
                    {"id": UUID(ids["workspace_id"])},
                )
            ).scalar_one() == 1
        await migrate("upgrade", "head")
        await runtime.check()
        async with migrator.connect() as connection:
            assert (
                await connection.execute(text("SELECT count(*) FROM platform.auth_sessions"))
            ).scalar_one() == 0
            assert (
                await connection.execute(text("SELECT count(*) FROM platform.auth_credentials"))
            ).scalar_one() == 0
    finally:
        await migrate("upgrade", "head")
        async with migrator.begin() as connection:
            if ids is not None:
                account, workspace = UUID(ids["user_account_id"]), UUID(ids["workspace_id"])
                await connection.execute(
                    text(
                        "DELETE FROM platform.auth_sessions WHERE user_account_id=:id OR user_account_id IS NULL"
                    ),
                    {"id": account},
                )
                await connection.execute(
                    text("DELETE FROM platform.auth_credentials WHERE user_account_id=:id"),
                    {"id": account},
                )
                await connection.execute(
                    text("DELETE FROM app.businesses WHERE workspace_id=:id"), {"id": workspace}
                )
                await connection.execute(
                    text("DELETE FROM platform.workspace_memberships WHERE workspace_id=:id"),
                    {"id": workspace},
                )
                await connection.execute(
                    text("DELETE FROM platform.workspaces WHERE id=:id"), {"id": workspace}
                )
                await connection.execute(
                    text("DELETE FROM platform.user_accounts WHERE id=:id"), {"id": account}
                )
            await connection.execute(
                text("DELETE FROM platform.workspaces WHERE id=:id"), {"id": marker}
            )
        await runtime.close()
        await migrator.dispose()
