"""Independent C8 M1.1 probes; real disposable PostgreSQL, no implementation changes."""

import asyncio
from uuid import uuid4

import pytest
from asm.tenancy import AuthenticatedAccount, Permission, TenancyError, TenantDatabase
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from test_tenancy_postgres import (
    A,
    B,
    BA,
    BA2,
    BB,
    LA,
    LB,
    MEMBER_A,
    MEMBER_B,
    PROVIDER,
    UA,
    UB,
    db as db,
    seeded as seeded,
)

pytestmark = pytest.mark.integration


async def test_c8_autocommit_cannot_publish_context_without_database_transaction(seeded):
    runtime, _ = seeded
    engine = create_async_engine(
        runtime.engine.url, isolation_level="AUTOCOMMIT", hide_parameters=True
    )
    try:
        try:
            async with TenantDatabase(engine).transaction(
                AuthenticatedAccount(UA), A, uuid4()
            ) as unit:
                # An unsupported engine may be rejected, but never publish a false context.
                row = (
                    (
                        await unit._execute(
                            "SELECT app.current_workspace_id() AS workspace, "
                            "pg_current_xact_id_if_assigned()::text AS xid, "
                            "NULLIF(current_setting('asm.context_xid', true), '') AS context_xid",
                            {},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert row["workspace"] == unit.context.workspace_id, dict(row)
                assert row["xid"] is not None and row["xid"] == row["context_xid"]
                assert {item["id"] for item in await unit.list_businesses()} == {BA, BA2}
        except TenancyError as error:
            assert error.code.value in {"CONTEXT_INVALID", "TRANSACTION_STATE"}
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE platform.workspace_memberships SET role='PROVIDER' "
        "WHERE workspace_id=:workspace AND user_account_id=:actor",
        "UPDATE platform.user_accounts SET status='DISABLED' WHERE id=:actor",
        "UPDATE platform.workspaces SET status='ARCHIVED' WHERE id=:workspace",
    ],
    ids=["membership-role", "disabled-account", "archived-workspace"],
)
async def test_c8_platform_changes_wait_for_active_unit_and_apply_to_next_unit(seeded, change):
    runtime, migrator = seeded
    params = {"workspace": A, "actor": UA}
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        assert unit.context.permissions == {Permission.READ, Permission.WRITE}
        with pytest.raises(DBAPIError) as caught:
            async with migrator.begin() as connection:
                await connection.execute(text("SET LOCAL lock_timeout='100ms'"))
                await connection.execute(text(change), params)
        assert caught.value.orig.sqlstate == "55P03"
        assert (await unit.get_business(BA))["id"] == BA
    async with migrator.begin() as connection:
        await connection.execute(text(change), params)
    if "SET role=" in change:
        async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            assert unit.context.permissions == {Permission.READ}
            with pytest.raises(TenancyError, match="ACCESS_DENIED"):
                await unit.rename_business(BA, "forbidden", 1)
    else:
        with pytest.raises(TenancyError, match="ACCESS_DENIED"):
            async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()):
                pytest.fail("inactive identity accepted")


async def test_c8_cancellation_during_blocked_sql_rolls_back_prior_successful_write(seeded):
    runtime, migrator = seeded
    started = asyncio.Event()
    backend_pid = []

    async def operation():
        async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
            backend_pid.append((await unit._execute("SELECT pg_backend_pid()", {})).scalar_one())
            await unit.rename_business(BA2, "must roll back", 1)
            started.set()
            await unit.rename_business(BA, "blocked", 1)

    async with migrator.begin() as locker:
        await locker.execute(
            text("SELECT id FROM app.businesses WHERE workspace_id=:ws AND id=:id FOR UPDATE"),
            {"ws": A, "id": BA},
        )
        task = asyncio.create_task(operation())
        try:
            await asyncio.wait_for(started.wait(), 3)
            async with asyncio.timeout(1):
                while not (
                    await locker.execute(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": backend_pid[0]}
                    )
                ).scalar_one():
                    await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with runtime.tenancy.transaction(AuthenticatedAccount(UA), A, uuid4()) as unit:
        for identifier, name in ((BA, "A"), (BA2, "A2")):
            row = await unit.get_business(identifier)
            assert row["name"] == name and row["version"] == 1
    async with runtime.tenancy.transaction(AuthenticatedAccount(UB), B, uuid4()) as unit:
        assert {row["id"] for row in await unit.list_businesses()} == {BB}


async def test_c8_business_owner_role_does_not_promote_workspace_provider(seeded):
    runtime, migrator = seeded
    async with migrator.begin() as connection:
        await connection.execute(
            text(
                "UPDATE app.business_members SET user_account_id=:actor, role='OWNER' "
                "WHERE workspace_id=:ws AND id=:id"
            ),
            {"actor": PROVIDER, "ws": A, "id": MEMBER_A},
        )
    async with runtime.tenancy.transaction(AuthenticatedAccount(PROVIDER), A, uuid4()) as unit:
        assert (await unit.get_business_member(BA, MEMBER_A))["role"] == "OWNER"
        assert unit.context.permissions == {Permission.READ}
        with pytest.raises(TenancyError, match="ACCESS_DENIED"):
            await unit.rename_business(BA, "forbidden", 1)


@pytest.mark.parametrize(
    "workspace,actor,business,other_business,other_member,other_location",
    [(A, UA, BA, BB, MEMBER_B, LB), (B, UB, BB, BA, MEMBER_A, LA)],
    ids=["A-to-B", "B-to-A"],
)
async def test_c8_forged_child_ids_are_not_found_in_both_directions(
    seeded, workspace, actor, business, other_business, other_member, other_location
):
    runtime, _ = seeded
    async with runtime.tenancy.transaction(AuthenticatedAccount(actor), workspace, uuid4()) as unit:
        with pytest.raises(TenancyError, match="NOT_FOUND"):
            await unit.get_business(other_business)
        with pytest.raises(TenancyError, match="NOT_FOUND"):
            await unit.get_business_member(business, other_member)
        with pytest.raises(TenancyError, match="NOT_FOUND"):
            await unit.get_location(business, other_location)
