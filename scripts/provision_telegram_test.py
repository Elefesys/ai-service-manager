"""Explicit LOCAL/TEST Telegram setup. Secrets are accepted only from environment."""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

from asm.telegram.provisioning import (
    NativeHostApproval,
    NativePolicyReceipt,
    NativePolicyRequest,
    ProvisioningError,
    ProvisionRequest,
    commit_native_context_policy,
    inspect_connection,
    migrator_target,
    provision,
    read_native_context_policy,
)


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # Never echo an accidental token in an unknown argument.
        raise ProvisioningError("TELEGRAM_SETUP_ARGUMENTS_INVALID")


def request_from_environment(environment):
    return ProvisionRequest(
        environment=environment["ASM_ENVIRONMENT"],
        workspace_id=UUID(environment["ASM_TELEGRAM_WORKSPACE_ID"]),
        business_id=UUID(environment["ASM_TELEGRAM_BUSINESS_ID"]),
        expected_owner_id=environment["ASM_TELEGRAM_EXPECTED_OWNER_ID"],
        contact_display_name=environment["ASM_TELEGRAM_BILLING_CONTACT"],
        effective_from=datetime.fromisoformat(environment["ASM_TELEGRAM_BILLING_FROM"]),
        effective_until=datetime.fromisoformat(environment["ASM_TELEGRAM_BILLING_UNTIL"]),
        external_connection_id=environment.get("ASM_TELEGRAM_CONNECTION_ID") or None,
    )


async def run(environment, discover=False):
    # Lazy imports keep refusal/help independent from configured credentials.
    from asm.telegram.client import TelegramClient
    from asm.telegram.config import TelegramSettings

    request = request_from_environment(environment)
    migrator_target(request.environment, environment["ASM_MIGRATION_DATABASE_URL"])
    settings = TelegramSettings()
    if not settings.enabled:
        raise ProvisioningError("TELEGRAM_SETUP_DISABLED")
    client = TelegramClient(settings)
    try:
        if discover:
            bot_id, observed = await inspect_connection(
                client, request, settings.bot_id, settings.webhook_url
            )
            return {
                "status": "TELEGRAM_SETUP_DISCOVERED",
                "bot_id": bot_id,
                "external_connection_id": observed.external_connection_id,
                "owner_user_id": observed.owner_user_id,
                "is_enabled": observed.is_enabled,
                "can_reply": observed.can_reply,
            }
        return await provision(
            client,
            request,
            environment["ASM_MIGRATION_DATABASE_URL"],
            settings.bot_id,
            settings.webhook_url,
        )
    finally:
        await client.aclose()


async def run_native_policy(environment, action):
    """Private explicit host operation; does not construct a Telegram client."""
    from scripts import prepare_telegram_egress as host

    try:
        value = host.strict_json(host.private_bytes(environment["ASM_NATIVE_POLICY_INPUT"]))
    except (host.EgressError, KeyError, OSError, ValueError):
        raise ProvisioningError("INVALID_INPUT") from None
    if not isinstance(value, dict) or set(value) != {"request", "approval"}:
        raise ProvisioningError("INVALID_INPUT")
    try:
        request = NativePolicyRequest.model_validate(value["request"])
    except Exception:
        raise ProvisioningError("INVALID_INPUT") from None
    try:
        approval = NativeHostApproval.model_validate(value["approval"])
    except Exception:
        raise ProvisioningError("POLICY_PREREQUISITE_FAILED") from None
    if request.environment != environment["ASM_ENVIRONMENT"]:
        raise ProvisioningError("ACCESS_DENIED")
    target = environment["ASM_MIGRATION_DATABASE_URL"]
    # The key/body and full receipt remain private, never stdout or diagnostics.
    destination = Path(environment["ASM_NATIVE_POLICY_RECEIPT"])
    host.checked_path(destination.parent, directory=True)
    with host.operation_lock(destination.parent):
        saved = None
        if destination.exists() or destination.is_symlink():
            saved = host.strict_json(host.private_bytes(destination))
            if (
                not isinstance(saved, dict)
                or set(saved) != {"request", "receipt", "current"}
                or saved["request"] != request.model_dump(mode="json")
            ):
                raise ProvisioningError("IDEMPOTENCY_KEY_CONFLICT")
            previous = NativePolicyReceipt.model_validate(saved["receipt"]).result
            if (
                previous.workspace_id,
                previous.connection_id,
                previous.operation,
                previous.previous_policy,
                previous.previous_policy_epoch,
            ) != (
                request.workspace_id,
                request.connection_id,
                request.operation,
                request.expected_policy,
                request.expected_policy_epoch,
            ):
                raise ProvisioningError("INVALID_INPUT")
        if action == "commit":
            result = await commit_native_context_policy(request, target, approval)
            if saved is not None and saved["receipt"]["result"] != result.receipt.result.model_dump(
                mode="json"
            ):
                raise ProvisioningError("IDEMPOTENCY_KEY_CONFLICT")
            saved = {
                "request": request.model_dump(mode="json"),
                "receipt": saved["receipt"]
                if saved is not None
                else result.receipt.model_dump(mode="json"),
                "current": result.current.model_dump(mode="json")
                if result.current is not None
                else None,
            }
            host.write_private(destination, json.dumps(saved, sort_keys=True).encode())
            return {
                "status": "NATIVE_POLICY_COMMITTED",
                "outcome": result.receipt.outcome,
                "current_read": "OK" if result.current is not None else "RETRY_READ_ONLY",
                "current_policy": result.current.policy if result.current is not None else None,
            }
        if action == "current" and saved is None:
            raise ProvisioningError("INVALID_INPUT")
        current = await read_native_context_policy(request, target, approval)
        if action == "current":
            saved["current"] = current.model_dump(mode="json")
            host.write_private(destination, json.dumps(saved, sort_keys=True).encode())
        return {
            "status": "NATIVE_POLICY_CHECKED" if action == "check" else "NATIVE_POLICY_CURRENT",
            "current_policy": current.policy,
            "current_epoch": current.policy_epoch,
        }


def main():
    # A transport debug handler can otherwise include /bot<TOKEN>/ in URLs.
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
        logger.handlers = [logging.NullHandler()]
    native_mode = False
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument("--live", action="store_true", help="Allow operator TEST setup HTTP")
        parser.add_argument(
            "--discover", action="store_true", help="Read only; print a verified candidate"
        )
        parser.add_argument(
            "--native-policy",
            choices=("check", "commit", "current"),
            help="Explicit private LOCAL/TEST policy operation; no Telegram HTTP",
        )
        args = parser.parse_args()
        native_mode = bool(args.native_policy)
        if args.native_policy:
            if args.live or args.discover:
                raise ProvisioningError("INVALID_INPUT")
            print(
                json.dumps(
                    asyncio.run(run_native_policy(os.environ, args.native_policy)), sort_keys=True
                )
            )
            return 0
        if not args.live:
            raise ProvisioningError("TELEGRAM_SETUP_EXPLICIT_LIVE_REQUIRED")
        print(json.dumps(asyncio.run(run(os.environ, args.discover)), sort_keys=True))
        return 0
    except ProvisioningError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("UNAVAILABLE" if native_mode else "TELEGRAM_SETUP_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
