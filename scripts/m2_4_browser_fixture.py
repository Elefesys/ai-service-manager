"""Finite disposable TEST identities/bindings and read-only messaging counters.

Canonical Message/File/receipt/Audit/Outbox/Job writes belong to the separate
asm_runtime runner and the browser's owner HTTP commands, never this provisioner.
"""

import asyncio
import json
import os
import re
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

MATERIAL_PHOTOS = ("replacement", "text", "delete", "late")

ESCALATION_PRESETS = (
    "esc_happy",
    "esc_narrow",
    "esc_recovery",
    "esc_read",
    "esc_stale",
    "esc_revoked",
)
# Two finite identities retain the existing <128 seed-event guard. Native policy
# is exercised through its accepted capability, not fixture authority DML.
NATIVE_PRESETS = ("native_happy", "native_narrow")
PRESETS = (
    (
        "material",
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
        "ctrl_stale",
        "ctrl_recovery",
        "ctrl_read",
        "ctrl_revoked",
        "ctrl_inactive",
        "ctrl_restricted",
    )
    + ESCALATION_PRESETS
    + NATIVE_PRESETS
)
ACTIONS = (
    "inventory",
    "stats",
    "control-stats",
    "escalation-stats",
    "material-stats",
    "native-stats",
    "native-enable",
    "native-pause",
    "downgrade",
    "disable",
    "restrict",
)


def validate_operation(preset, operation):
    if operation not in ACTIONS or (
        preset is not None if operation == "inventory" else preset not in PRESETS
    ):
        raise ProvisioningError("Invalid finite messaging fixture action")
    allowed = {
        "downgrade": ("revoked", "ctrl_revoked", "esc_revoked") + NATIVE_PRESETS,
        "disable": ("inactive", "ctrl_inactive", "esc_happy", "esc_narrow"),
        "restrict": ("restricted", "ctrl_restricted", "esc_happy", "esc_narrow"),
        "escalation-stats": ESCALATION_PRESETS,
        "material-stats": ("material",),
        "native-stats": NATIVE_PRESETS,
        "native-enable": NATIVE_PRESETS,
        "native-pause": NATIVE_PRESETS,
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
    return "9000012" if preset == "material" else f"m24-{preset}-bot"


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
                    if preset == "material":
                        observation = dict(
                            bot_identity=bot(preset),
                            external_connection_id=route(preset),
                            owner_user_id="8000012",
                            is_enabled=True,
                            can_reply=True,
                            error_code=None,
                        )
                        binding = (
                            await connection.execute(
                                text(
                                    "SELECT platform.initialize_telegram_connection(:ws,:business,:bot,:external,'8000012',CAST(:observation AS jsonb))"
                                ),
                                params | {"observation": json.dumps(observation)},
                            )
                        ).scalar_one()
                        await connection.execute(
                            text(
                                "UPDATE platform.telegram_connection_state SET material_enabled=true WHERE workspace_id=:ws AND connection_id=:id"
                            ),
                            {"ws": ws, "id": UUID(binding["connection_id"])},
                        )
                        continue
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
            for preset in ("isolation", "revoked", "ctrl_revoked", "esc_revoked"):
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
            # A second live OWNER can cancel a revoked assignee's request through
            # the same public owner API. No decision row is provisioned here.
            await connection.execute(
                text(
                    "INSERT INTO platform.workspace_memberships(workspace_id,user_account_id,role) "
                    "VALUES(:ws,:actor,'OWNER')"
                ),
                {
                    "ws": UUID(fixtures["esc_revoked"]["workspace_id"]),
                    "actor": UUID(fixtures["isolation_peer"]["user_account_id"]),
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
                "WHERE c.login=:login AND cc.provider=:provider AND cc.bot_identity=:bot"
            ),
            {
                "login": f"browser.m24-{preset}",
                "bot": bot(preset),
                "provider": "TELEGRAM" if preset == "material" else "CONTROLLED",
            },
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
                        "SELECT id,client_id,provider_chat_id FROM app.conversations "
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
        clients = {row["provider_chat_id"]: str(row["client_id"]) for row in conversations}
        result[preset] = {
            "conversation_id": named["7000012" if preset == "material" else f"m24-{preset}-main"],
            "alternate_conversation_id": named[
                "7000013" if preset == "material" else f"m24-{preset}-alternate"
            ],
            "client_id": clients["7000012" if preset == "material" else f"m24-{preset}-main"],
            "alternate_client_id": clients[
                "7000013" if preset == "material" else f"m24-{preset}-alternate"
            ],
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
        if preset == "material":
            result[preset]["material_photos"] = {
                label: {key: str(row[key]) for key in ("conversation_id", "message_id", "file_id")}
                for label in MATERIAL_PHOTOS
                for row in files
                if row["image_file_id"] == f"m24-material-{label}-original"
            }
            if set(result[preset]["material_photos"]) != set(MATERIAL_PHOTOS):
                raise ProvisioningError("Complete material PHOTO fixture required")
    return result


async def material_stats(connection, params):
    # Read-only disposable evidence. Digests never expose private paths/URLs or
    # rewrite history; they include every original File and upload/WINNER field.
    statements = {
        "files": "SELECT count(*) FROM app.file_objects WHERE workspace_id=:ws",
        "fetches": "SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='FETCH_IMAGE'",
        "ready": "SELECT count(*) FROM app.file_objects WHERE workspace_id=:ws AND status='READY'",
        "winners": "SELECT count(*) FROM platform.file_object_uploads WHERE workspace_id=:ws AND status='WINNER'",
        "terminals": "SELECT count(*) FROM platform.inbox_events WHERE workspace_id=:ws AND result_code='MATERIAL_PROCESSED' AND material_claim_token IS NOT NULL",
        "invalid_terminal": "SELECT count(*) FROM platform.inbox_events i JOIN platform.messaging_jobs j ON (j.workspace_id,j.inbox_id)=(i.workspace_id,i.id) WHERE i.workspace_id=:ws AND i.result_code='MATERIAL_PROCESSED' AND (i.material_claim_token IS NULL OR j.status<>'SUCCEEDED' OR j.error_code IS NOT NULL OR j.last_attempt_id IS NOT NULL OR j.last_claim_token IS NOT NULL OR j.last_outcome IS NOT NULL OR j.last_provider_message_id IS NOT NULL OR j.last_error_code IS NOT NULL)",
        "history_digest": "SELECT encode(sha256(convert_to(coalesce(string_agg((to_jsonb(m)-'version')::text,E'\\n' ORDER BY m.id),''),'UTF8')),'hex') FROM app.messages m WHERE workspace_id=:ws",
        "files_digest": "SELECT encode(sha256(convert_to(coalesce(string_agg(to_jsonb(f)::text,E'\\n' ORDER BY f.id),''),'UTF8')),'hex') FROM app.file_objects f WHERE workspace_id=:ws",
        "uploads_digest": "SELECT encode(sha256(convert_to(coalesce(string_agg(to_jsonb(u)::text,E'\\n' ORDER BY u.id),''),'UTF8')),'hex') FROM platform.file_object_uploads u WHERE workspace_id=:ws",
    }
    return {
        name: (await connection.execute(text(sql), params)).scalar_one()
        for name, sql in statements.items()
    }


def validate_native_source(operation, source_tree):
    # The later C0 clean-source browser gate supplies its actual Git tree. This
    # disposable TEST carrier is not the host/operator rollout/readiness proof.
    if operation in {"native-enable", "native-pause"}:
        if not isinstance(source_tree, str) or re.fullmatch("[0-9a-f]{40}", source_tree) is None:
            raise ProvisioningError("Exact browser TEST source tree required")
    elif source_tree is not None:
        raise ProvisioningError("Source tree only belongs to native policy carrier")


async def native_policy(connection, params, preset, operation, source_tree):
    row = (
        (
            await connection.execute(
                text(
                    "SELECT * FROM app.channel_connections WHERE workspace_id=:ws "
                    "AND provider='CONTROLLED' AND bot_identity=:bot AND external_connection_id=:external"
                ),
                params | {"bot": bot(preset), "external": route(preset)},
            )
        )
        .mappings()
        .one()
    )
    installed = (
        await connection.execute(text("SELECT platform.human_context_schema_profile()"))
    ).scalar_one()
    if (
        not isinstance(installed, dict)
        or set(installed) != {"schema_revision", "valid", "profile_sha256"}
        or installed["schema_revision"] != "0013"
        or installed["valid"] is not True
        or not isinstance(installed["profile_sha256"], str)
        or re.fullmatch("[0-9a-f]{64}", installed["profile_sha256"]) is None
    ):
        raise ProvisioningError("Exact native TEST catalog profile required")
    binding = {
        k: str(row[k])
        for k in ("business_id", "provider", "bot_identity", "external_connection_id")
    } | {"owner_user_id": None}
    # Only a fresh, C0-paired disposable browser stack may invoke this carrier;
    # no old writers are started by it. This is not an operator drain probe.
    profile = dict(
        source_tree=source_tree,
        schema_revision="0013",
        profile_sha256=installed["profile_sha256"],
        drain_confirmed=True,
    )
    await connection.execute(
        text(
            "SELECT platform.human_context_policy_command(:ws,:id,:op,:key,:policy,:epoch,"
            "CAST(:binding AS jsonb),CAST(:profile AS jsonb))"
        ),
        {
            "ws": params["ws"],
            "id": row["id"],
            "op": operation.removeprefix("native-").upper(),
            "key": str(uuid4()),
            "policy": row["human_context_policy"],
            "epoch": row["human_context_policy_epoch"],
            "binding": json.dumps(binding),
            "profile": json.dumps(profile),
        },
    )
    # Never present the historical command result as current state. The browser
    # must GET through the owner API; any SQL/commit failure propagates closed.
    return {"command_completed": True}


async def action(preset, operation, source_tree=None):
    validate_operation(preset, operation)
    validate_native_source(operation, source_tree)
    url = target()
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(15), engine.begin() as connection:
            await guard(connection)
            if operation == "inventory":
                return await inventory(connection)
            owner = await identity(connection, preset)
            params = {"ws": owner.workspace_id, "actor": owner.user_account_id}
            if operation in {"native-enable", "native-pause"}:
                return await native_policy(connection, params, preset, operation, source_tree)
            if operation == "material-stats":
                return await material_stats(connection, params)
            if operation in {"stats", "control-stats", "escalation-stats", "native-stats"}:
                statements = {
                    "messages": "SELECT count(*) FROM app.messages WHERE workspace_id=:ws AND direction='OUTBOUND'",
                    "receipts": "SELECT count(*) FROM platform.messaging_command_receipts WHERE workspace_id=:ws",
                    "audit_events": "SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='MESSAGE_SEND_REQUESTED'",
                    "outbox_events": "SELECT count(*) FROM app.outbox_events WHERE workspace_id=:ws",
                    "jobs": "SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='SEND_MANUAL_TEXT'",
                }
                if operation in {"control-stats", "escalation-stats", "native-stats"}:
                    statements.update(
                        control_receipts="SELECT count(*) FROM platform.conversation_control_receipts WHERE workspace_id=:ws",
                        control_audit_events="SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type IN ('CONVERSATION_TAKEN_OVER','CONVERSATION_RESUMED')",
                    )
                if operation == "native-stats":
                    statements.update(
                        reconciliations="SELECT count(*) FROM platform.human_context_reconciliations WHERE workspace_id=:ws",
                        reconciliation_audit="SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='HUMAN_CONTEXT_RECONCILED'",
                        policy_receipts="SELECT count(*) FROM platform.human_context_policy_receipts WHERE workspace_id=:ws",
                        policy_audit="SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='HUMAN_CONTEXT_POLICY_COMMANDED'",
                    )
                if operation == "escalation-stats":
                    statements.update(
                        escalations="SELECT count(*) FROM app.escalations WHERE workspace_id=:ws",
                        escalation_receipts="SELECT count(*) FROM platform.escalation_command_receipts WHERE workspace_id=:ws",
                        escalation_audit="SELECT count(*) FROM app.audit_events WHERE workspace_id=:ws AND event_type='ESCALATION_DECIDED'",
                        escalation_timers="SELECT count(*) FROM platform.messaging_jobs WHERE workspace_id=:ws AND kind='ESCALATION_TIMER'",
                    )
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
        parser.add_argument("--source-tree")
        args = parser.parse_args()
        print(
            json.dumps(
                asyncio.run(action(args.preset, args.action, args.source_tree)), sort_keys=True
            )
        )
        return 0
    except Exception:
        print("M2_4_BROWSER_FIXTURE_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
