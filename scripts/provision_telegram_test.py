"""Explicit LOCAL/TEST Telegram setup. Secrets are accepted only from environment."""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from uuid import UUID

from asm.telegram.provisioning import (
    ProvisioningError,
    ProvisionRequest,
    inspect_connection,
    migrator_target,
    provision,
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


def main():
    # A transport debug handler can otherwise include /bot<TOKEN>/ in URLs.
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.disabled = True
        logger.propagate = False
        logger.handlers = [logging.NullHandler()]
    try:
        parser = PrivateParser(description=__doc__)
        parser.add_argument("--live", action="store_true", help="Allow operator TEST setup HTTP")
        parser.add_argument(
            "--discover", action="store_true", help="Read only; print a verified candidate"
        )
        args = parser.parse_args()
        if not args.live:
            raise ProvisioningError("TELEGRAM_SETUP_EXPLICIT_LIVE_REQUIRED")
        print(json.dumps(asyncio.run(run(os.environ, args.discover)), sort_keys=True))
        return 0
    except ProvisioningError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print("TELEGRAM_SETUP_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
