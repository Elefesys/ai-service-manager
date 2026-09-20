"""Finite TEST-only billing fixtures; no runtime endpoint or arbitrary SQL input."""

import asyncio
import json
import os
import sys
from uuid import UUID

from provision_local_auth import (
    PrivateArgumentParser,
    ProvisioningError,
    provision,
    validate_target,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

PRESETS = (
    "happy",
    "stale",
    "recovery",
    "isolation",
    "foreign",
    "inactive",
    "restricted",
    "mode_inactive",
)


class FixtureFailure(ProvisioningError):
    def __init__(self, stage, error):
        # Finite stage and error codes only. Never format an exception/SQL/params.
        code = "UNEXPECTED"
        if isinstance(error, TimeoutError):
            code = "TIMEOUT"
        elif isinstance(error, ProvisioningError):
            code = "GUARD"
        elif isinstance(error, DBAPIError):
            sqlstate = getattr(error.orig, "sqlstate", None)
            code = (
                sqlstate
                if sqlstate
                in {
                    "23505",
                    "23514",
                    "42501",
                    "42883",
                    "42804",
                    "42703",
                    "42P01",
                    "55P03",
                    "57014",
                    "P1301",
                }
                else "DATABASE"
            )
        self.code = f"M1_3_FIXTURE_{stage}_{code}"
        super().__init__(self.code)


def target():
    url = os.environ.get("ASM_MIGRATION_DATABASE_URL", "")
    if os.environ.get("ASM_ENVIRONMENT") != "TEST":
        raise ProvisioningError("TEST required")
    validate_target("TEST", url)
    return url


async def guard(connection):
    row = (await connection.execute(text("SELECT current_user,current_database()"))).one()
    if tuple(row) != ("asm_migrator", "asm_test"):
        raise ProvisioningError("Unexpected TEST database or identity")
    if (
        await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
    ).scalar_one() != "0004":
        raise ProvisioningError("Upgrade TEST first")


async def initialize(connection, workspace):
    # Explicit finite TEST interval, independent of the runner's execution date.
    result = await connection.execute(
        text(
            "SELECT platform.initialize_local_billing(:ws,'test',1,'Example name','ACTIVE','COMPED',"
            "'2000-01-01T00:00:00Z','2100-01-01T00:00:00Z','NORMAL')"
        ),
        {"ws": UUID(workspace)},
    )
    if result.scalar_one() != "INITIALIZED":
        raise ProvisioningError("Expected fresh disposable fixture")


async def setup_billing(original, password):
    url = target()
    fixtures = {"owner": original}
    for preset in PRESETS:
        try:
            fixtures[preset] = await provision("TEST", url, f"browser.m13-{preset}", password)
        except Exception as error:
            raise FixtureFailure("IDENTITY", error) from None
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    stage = "GUARD"
    try:
        async with asyncio.timeout(15), engine.begin() as connection:
            await guard(connection)
            stage = "INITIALIZE"
            for fixture in fixtures.values():
                await initialize(connection, fixture["workspace_id"])
            stage = "PRESETS"
            await connection.execute(
                text(
                    "UPDATE platform.workspace_subscriptions SET effective_until='2001-01-01T00:00:00Z' WHERE workspace_id=:ws"
                ),
                {"ws": fixtures["inactive"]["workspace_id"]},
            )
            await connection.execute(
                text(
                    "UPDATE platform.workspace_service_modes SET mode='SUSPENDED' WHERE workspace_id=:ws"
                ),
                {"ws": fixtures["restricted"]["workspace_id"]},
            )
            await connection.execute(
                text(
                    "UPDATE platform.workspace_service_modes SET effective_until='2001-01-01T00:00:00Z' WHERE workspace_id=:ws"
                ),
                {"ws": fixtures["mode_inactive"]["workspace_id"]},
            )
        return fixtures
    except Exception as error:
        raise FixtureFailure(stage, error) from None
    finally:
        await engine.dispose()


async def action(preset, operation):
    url = target()
    if preset not in PRESETS or operation not in ("stats", "downgrade"):
        raise ProvisioningError("Unknown finite fixture operation")
    if operation == "downgrade" and preset != "isolation":
        raise ProvisioningError("Only the isolated revocation fixture can be changed")
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(10), engine.begin() as connection:
            await guard(connection)
            identity = (
                await connection.execute(
                    text(
                        "SELECT m.workspace_id,m.user_account_id FROM platform.auth_credentials c "
                        "JOIN platform.workspace_memberships m ON m.user_account_id=c.user_account_id "
                        "WHERE c.login=:login"
                    ),
                    {"login": f"browser.m13-{preset}"},
                )
            ).one()
            if operation == "downgrade":
                result = await connection.execute(
                    text(
                        "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor AND role='OWNER'"
                    ),
                    {"ws": identity.workspace_id, "actor": identity.user_account_id},
                )
                if result.rowcount != 1:
                    raise ProvisioningError("Expected a fresh owner fixture")
                return {"downgraded": True}
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT version::text AS version, "
                            "(SELECT count(*) FROM platform.billing_contact_command_receipts WHERE workspace_id=:ws) AS receipts, "
                            "(SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='BILLING_ACCOUNT_CONTACT_UPDATED') AS contact_events "
                            "FROM platform.workspace_billing_accounts WHERE workspace_id=:ws"
                        ),
                        {"ws": identity.workspace_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)
    finally:
        await engine.dispose()


def main():
    try:
        parser = PrivateArgumentParser()
        parser.add_argument("--preset", required=True, choices=PRESETS)
        parser.add_argument("--action", required=True, choices=("stats", "downgrade"))
        args = parser.parse_args()
        print(json.dumps(asyncio.run(action(args.preset, args.action))))
        return 0
    except Exception:
        print("M1_3_BROWSER_FIXTURE_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
