"""Finite disposable TEST identities/bindings and read-only messaging counters.

Canonical Message/File/receipt/Audit/Outbox/Job writes belong to the separate
asm_runtime runner and the browser's owner HTTP commands, never this provisioner.
"""

import asyncio
import json
import os
import sys
from uuid import UUID, uuid4

from m1_3_browser_fixture import guard
from provision_local_auth import (
    PrivateArgumentParser,
    ProvisioningError,
    provision,
    validate_target,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PRESETS = (
    "happy",
    "recovery",
    "unknown",
    "read_failure",
    "isolation",
    "isolation_peer",
    "foreign",
    "restricted",
    "inactive",
    "pagination",
    "late",
    "revoked",
    "permanent",
)
ACTIONS = ("inventory", "stats", "downgrade", "disable", "restrict")


def validate_operation(preset, operation):
    if operation not in ACTIONS or (
        preset is not None if operation == "inventory" else preset not in PRESETS
    ):
        raise ProvisioningError("Invalid finite messaging fixture action")
    allowed = {
        "downgrade": ("revoked",),
        "disable": ("inactive",),
        "restrict": ("restricted",),
    }
    if operation in allowed and preset not in allowed[operation]:
        raise ProvisioningError("Invalid finite messaging state change")


def target():
    url = validate_target("TEST", os.environ.get("ASM_MIGRATION_DATABASE_URL", ""))
    if (
        os.environ.get("ASM_ENVIRONMENT") != "TEST"
        or url.host != "postgres"
        or url.port != 5432
        or url.query
    ):
        raise ProvisioningError("Disposable browser TEST target required")
    return url


def bot(preset):
    if preset not in PRESETS:
        raise ProvisioningError("Invalid finite messaging preset")
    return f"m24-{preset}-bot"


def route(preset, index=0):
    bot(preset)
    if type(index) is not int or not 0 <= index < (27 if preset == "pagination" else 1):
        raise ProvisioningError("Invalid finite messaging connection")
    return f"m24-{preset}-connection-{index}"


async def setup_messaging(password):
    url = target()  # No writes or hashing before the finite TEST target guard.
    fixtures = {}
    for preset in PRESETS:
        fixtures[preset] = {
            "login": f"browser.m24-{preset}",
            **await provision("TEST", url, f"browser.m24-{preset}", password),
        }
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(30), engine.begin() as connection:
            await guard(connection)
            for preset, fixture in fixtures.items():
                ws = UUID(fixture["workspace_id"])
                initialized = (
                    await connection.execute(
                        text(
                            "SELECT platform.initialize_local_messaging_billing("
                            ":ws,'M2 browser TEST','2000-01-01T00:00:00Z','2100-01-01T00:00:00Z')"
                        ),
                        {"ws": ws},
                    )
                ).scalar_one()
                if initialized != "CREATED":
                    raise ProvisioningError("Fresh messaging billing required")
                for index in range(27 if preset == "pagination" else 1):
                    params = {
                        "ws": ws,
                        "id": uuid4(),
                        "business": UUID(fixture["business_id"]),
                        "bot": bot(preset),
                        "external": route(preset, index),
                    }
                    await connection.execute(
                        text(
                            "INSERT INTO app.channel_connections(workspace_id,id,business_id,provider,bot_identity,external_connection_id) "
                            "VALUES(:ws,:id,:business,'CONTROLLED',:bot,:external)"
                        ),
                        params,
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO platform.channel_routes(workspace_id,connection_id,provider,bot_identity,route_key) "
                            "VALUES(:ws,:id,'CONTROLLED',:bot,:external)"
                        ),
                        params,
                    )
            # Two authorized Workspaces for browser context races. This does not
            # make the separate foreign Workspace visible to either actor.
            for preset in ("isolation", "revoked"):
                await connection.execute(
                    text(
                        "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) "
                        "VALUES(:ws,:actor,'OWNER')"
                    ),
                    {
                        "ws": UUID(fixtures["isolation_peer"]["workspace_id"]),
                        "actor": UUID(fixtures[preset]["user_account_id"]),
                    },
                )
        return fixtures
    finally:
        await engine.dispose()


async def identity(connection, preset):
    # The original provisioning membership also owns the fixture's named route;
    # a secondary membership must never redirect stats/mutations to its peer.
    row = (
        await connection.execute(
            text(
                "SELECT DISTINCT m.workspace_id,m.user_account_id FROM platform.auth_credentials c "
                "JOIN platform.workspace_memberships m ON m.user_account_id=c.user_account_id "
                "JOIN app.channel_connections cc ON cc.workspace_id=m.workspace_id "
                "WHERE c.login=:login AND cc.provider='CONTROLLED' AND cc.bot_identity=:bot"
            ),
            {"login": f"browser.m24-{preset}", "bot": bot(preset)},
        )
    ).one()
    return row


async def inventory(connection):
    result = {}
    for preset in PRESETS:
        owner = await identity(connection, preset)
        params = {"ws": owner.workspace_id}
        conversations = (
            (
                await connection.execute(
                    text(
                        "SELECT id,provider_chat_id FROM app.conversations "
                        "WHERE workspace_id=:ws ORDER BY created_at DESC,id DESC LIMIT 100"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        connections = (
            await connection.execute(
                text(
                    "SELECT id FROM app.channel_connections WHERE workspace_id=:ws "
                    "ORDER BY created_at DESC,id DESC LIMIT 100"
                ),
                params,
            )
        ).scalars()
        messages = (
            await connection.execute(
                text(
                    "SELECT id FROM app.messages WHERE workspace_id=:ws "
                    "ORDER BY created_at DESC,id DESC LIMIT 200"
                ),
                params,
            )
        ).scalars()
        files = (
            (
                await connection.execute(
                    text(
                        "SELECT f.conversation_id,f.message_id,f.id AS file_id,m.image_file_id "
                        "FROM app.file_objects f JOIN app.messages m "
                        "ON (m.workspace_id,m.id)=(f.workspace_id,f.message_id) "
                        "WHERE f.workspace_id=:ws ORDER BY f.created_at,f.id LIMIT 10"
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        named = {row["provider_chat_id"]: str(row["id"]) for row in conversations}
        result[preset] = {
            "conversation_id": named[f"m24-{preset}-main"],
            "alternate_conversation_id": named[f"m24-{preset}-alternate"],
            "connection_ids": [str(value) for value in connections],
            "conversation_ids": [str(row["id"]) for row in conversations],
            "message_ids": [str(value) for value in messages],
            "images": {
                label: {key: str(row[key]) for key in ("conversation_id", "message_id", "file_id")}
                for row in files
                for label in ("ready", "failed", "pending")
                if row["image_file_id"] == f"m24-image-{label}"
            },
        }
    return result


async def action(preset, operation):
    validate_operation(preset, operation)
    url = target()
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(15), engine.begin() as connection:
            await guard(connection)
            if operation == "inventory":
                return await inventory(connection)
            owner = await identity(connection, preset)
            params = {"ws": owner.workspace_id, "actor": owner.user_account_id}
            if operation == "stats":
                statements = {
                    "messages": "SELECT count(*) FROM app.messages WHERE workspace_id=:ws AND direction='OUTBOUND'",
                    "receipts": "SELECT count(*) FROM platform.messaging_command_receipts WHERE workspace_id=:ws",
                    "audit_events": "SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='MESSAGE_SEND_REQUESTED'",
                    "outbox_events": "SELECT count(*) FROM app.outbox_events WHERE workspace_id=:ws",
                    "jobs": "SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='SEND_MANUAL_TEXT'",
                }
                return {
                    name: (await connection.execute(text(sql), params)).scalar_one()
                    for name, sql in statements.items()
                }
            sql = {
                "downgrade": "UPDATE platform.workspace_memberships SET role='ADMIN' WHERE workspace_id=:ws AND user_account_id=:actor AND role='OWNER'",
                "disable": "UPDATE app.channel_connections SET status='INACTIVE',version=version+1 WHERE workspace_id=:ws AND status='ACTIVE'",
                "restrict": "UPDATE platform.workspace_service_modes SET mode='SUSPENDED',reason_code='TEST_SUSPENDED',version=version+1 WHERE workspace_id=:ws AND mode='NORMAL'",
            }[operation]
            changed = await connection.execute(text(sql), params)
            if changed.rowcount != 1:
                raise ProvisioningError("Expected one fresh finite fixture state change")
            return {"changed": True}
    finally:
        await engine.dispose()


def main():
    try:
        parser = PrivateArgumentParser()
        parser.add_argument("--preset", choices=PRESETS)
        parser.add_argument("--action", required=True, choices=ACTIONS)
        args = parser.parse_args()
        print(json.dumps(asyncio.run(action(args.preset, args.action)), sort_keys=True))
        return 0
    except Exception:
        print("M2_4_BROWSER_FIXTURE_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
