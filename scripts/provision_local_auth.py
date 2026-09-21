"""Explicit synthetic LOCAL/TEST setup with a dedicated migration identity.

Never pass a password or database URL on the command line. Use the existing
ASM_MIGRATION_DATABASE_URL environment of the isolated setup container. Enter a
password on its terminal, or mount a private password file containing exact UTF-8
bytes (no implicit newline stripping). This script does not activate production.
"""

import argparse
import asyncio
import getpass
import json
import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

from asm.auth.crypto import PASSWORD_HASHER, normalize_login
from asm.foundation import DATABASE_SCHEMA_REVISION
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


class ProvisioningError(RuntimeError):
    pass


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo unknown CLI arguments that might contain an accidental secret.
        raise ProvisioningError("Invalid provisioning arguments")


def validate_target(environment, database_url):
    url = make_url(database_url)
    if (
        environment not in ("LOCAL", "TEST")
        or url.database != {"LOCAL": "asm_local", "TEST": "asm_test"}.get(environment)
        or url.username != "asm_migrator"
        or url.drivername != "postgresql+psycopg"
        or not url.host
    ):
        raise ProvisioningError("Explicit isolated LOCAL/TEST provisioning identity required")
    return url


def read_password(path):
    if path is None:
        if not sys.stdin.isatty():
            raise ProvisioningError("A terminal or private password file is required")
        value = getpass.getpass("Synthetic owner password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if value != confirmation:
            raise ProvisioningError("Password confirmation differs")
        return value
    descriptor = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ProvisioningError("Password file must be private and owned by the current user")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            content = stream.read(1025)
        if len(content) > 1024:
            raise ProvisioningError("Invalid password length")
        return content.decode("utf-8")
    finally:
        os.close(descriptor)


async def provision(environment, database_url, login, password):
    url = validate_target(environment, database_url)
    login = normalize_login(login)
    if not 15 <= len(password) <= 128 or len(password.encode("utf-8")) > 1024:
        raise ProvisioningError("Password must contain 15–128 characters")
    encoded = PASSWORD_HASHER.hash(password)  # No transaction during the expensive hash.
    account, workspace, business = uuid4(), uuid4(), uuid4()
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(10), engine.begin() as connection:
            if (
                await connection.execute(text("SELECT current_user"))
            ).scalar_one() != "asm_migrator":
                raise ProvisioningError("Unexpected provisioning identity")
            if (
                await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one() != DATABASE_SCHEMA_REVISION:
                raise ProvisioningError(
                    f"Upgrade the isolated database to {DATABASE_SCHEMA_REVISION} first"
                )
            # UNIQUE(login) also protects concurrent setup: a collision rolls back all rows.
            await connection.execute(
                text("INSERT INTO platform.user_accounts(id) VALUES (:id)"), {"id": account}
            )
            await connection.execute(
                text(
                    "INSERT INTO platform.auth_credentials(user_account_id,login,password_hash) "
                    "VALUES (:id,:login,:encoded)"
                ),
                {"id": account, "login": login, "encoded": encoded},
            )
            await connection.execute(
                text("INSERT INTO platform.workspaces(id) VALUES (:id)"), {"id": workspace}
            )
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) "
                    "VALUES (:ws,:account,'OWNER')"
                ),
                {"ws": workspace, "account": account},
            )
            await connection.execute(
                text(
                    "INSERT INTO app.businesses(workspace_id,id,name) "
                    "VALUES (:ws,:id,'Synthetic business')"
                ),
                {"ws": workspace, "id": business},
            )
        return {
            "user_account_id": str(account),
            "workspace_id": str(workspace),
            "business_id": str(business),
        }
    finally:
        await engine.dispose()


def main():
    try:
        parser = PrivateArgumentParser(description=__doc__)
        parser.add_argument("--login", required=True)
        parser.add_argument("--password-file")
        args = parser.parse_args()
        environment = os.environ.get("ASM_ENVIRONMENT", "")
        database_url = os.environ.get("ASM_MIGRATION_DATABASE_URL", "")
        validate_target(environment, database_url)
        password = read_password(args.password_file)
        result = asyncio.run(provision(environment, database_url, args.login, password))
        print(json.dumps(result, sort_keys=True))  # Non-secret IDs only.
        return 0
    except Exception:
        print("Synthetic provisioning failed; no credentials have been printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
