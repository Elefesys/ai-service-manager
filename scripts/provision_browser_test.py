"""Provision the single synthetic fixture used by the disposable browser TEST database."""

import argparse
import asyncio
import json
import os
import sys

from m1_3_browser_fixture import setup_billing, target
from provision_local_auth import ProvisioningError, provision, read_password, validate_target
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

LOGIN = "browser.owner"


async def setup(url: str, password: str):
    target()  # TEST environment/database/identity checked before any write.
    result = await provision("TEST", url, LOGIN, password)
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            user = (await connection.execute(text("SELECT current_user"))).scalar_one()
            if user != "asm_migrator":
                raise ProvisioningError("Unexpected provisioning identity")
            await connection.execute(
                text(
                    "UPDATE app.businesses SET name='Synthetic browser business' "
                    "WHERE workspace_id=:workspace AND id=:business"
                ),
                {"workspace": result["workspace_id"], "business": result["business_id"]},
            )
        fixtures = await setup_billing(result, password)
        return {**result, "billing_fixtures": fixtures}
    finally:
        await engine.dispose()


def main() -> int:
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--password-file", required=True)
        args = parser.parse_args()
        url = os.environ.get("ASM_MIGRATION_DATABASE_URL", "")
        validate_target("TEST", url)
        result = asyncio.run(setup(url, read_password(args.password_file)))
        print(json.dumps({"login": LOGIN, **result}, sort_keys=True))
        return 0
    except Exception:
        print(
            "Browser fixture provisioning failed; no credentials have been printed.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
