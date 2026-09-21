"""Operator-only LOCAL/TEST binding; no external I/O inside the migrator unit."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from asm.messaging.models import identifier


class ProvisioningError(RuntimeError):
    """Only bounded diagnostics cross the operator CLI boundary."""


def numeric_id(value: str) -> str:
    if re.fullmatch(r"[1-9][0-9]{0,18}", value) is None or int(value) > 2**63 - 1:
        raise ProvisioningError("TELEGRAM_SETUP_ID_INVALID")
    return value


def migrator_target(environment: str, database_url: str) -> URL:
    try:
        url = make_url(database_url)
        if (
            environment not in {"LOCAL", "TEST"}
            or url.database != {"LOCAL": "asm_local", "TEST": "asm_test"}[environment]
            or url.drivername != "postgresql+psycopg"
            or url.username != "asm_migrator"
            or not url.host
        ):
            raise ValueError
        return url
    except Exception:
        raise ProvisioningError("TELEGRAM_SETUP_TARGET_INVALID") from None


@dataclass(frozen=True)
class ProvisionRequest:
    environment: str
    workspace_id: UUID
    business_id: UUID
    expected_owner_id: str
    contact_display_name: str = field(repr=False)
    effective_from: datetime
    effective_until: datetime
    external_connection_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            self.environment not in {"LOCAL", "TEST"}
            or type(self.workspace_id) is not UUID
            or type(self.business_id) is not UUID
            or not self.contact_display_name.strip()
            or len(self.contact_display_name) > 200
            or "\0" in self.contact_display_name
            or self.effective_from.tzinfo is None
            or self.effective_until.tzinfo is None
            or self.effective_from >= self.effective_until
        ):
            raise ProvisioningError("TELEGRAM_SETUP_REQUEST_INVALID")
        numeric_id(self.expected_owner_id)
        if self.external_connection_id is not None:
            identifier(self.external_connection_id)


class ConnectionObservation(Protocol):
    @property
    def external_connection_id(self) -> str: ...

    @property
    def owner_user_id(self) -> str: ...

    @property
    def is_enabled(self) -> bool: ...

    @property
    def can_reply(self) -> bool: ...

    def observation(self, bot_id: str) -> dict[str, object]: ...


class SetupClient(Protocol):
    async def get_me(self) -> str: ...

    async def get_webhook_info(self) -> dict[str, object]: ...

    async def get_updates(self) -> list[dict[str, object]]: ...

    async def get_business_connection(self, external_id: str) -> ConnectionObservation: ...

    async def set_webhook(self) -> None: ...


@dataclass(frozen=True)
class CommittedBinding:
    connection_id: UUID
    billing_outcome: str
    binding_outcome: str


async def commit_binding(
    request: ProvisionRequest, database_url: str, bot_id: str, observation: dict[str, object]
) -> CommittedBinding:
    """The two reviewed typed SQL capabilities commit or roll back together."""
    url = migrator_target(request.environment, database_url)
    engine = create_async_engine(url, hide_parameters=True, connect_args={"connect_timeout": 3})
    try:
        async with asyncio.timeout(10), engine.begin() as connection:
            if (
                await connection.execute(text("SELECT current_user"))
            ).scalar_one() != "asm_migrator":
                raise ProvisioningError("TELEGRAM_SETUP_TARGET_INVALID")
            if (
                await connection.execute(text("SELECT version_num FROM platform.alembic_version"))
            ).scalar_one() != "0007":
                raise ProvisioningError("TELEGRAM_SETUP_SCHEMA_INVALID")
            billing = (
                await connection.execute(
                    text(
                        "SELECT platform.initialize_local_messaging_billing("
                        ":workspace,:contact,:effective_from,:effective_until)"
                    ),
                    {
                        "workspace": request.workspace_id,
                        "contact": request.contact_display_name,
                        "effective_from": request.effective_from,
                        "effective_until": request.effective_until,
                    },
                )
            ).scalar_one()
            binding = (
                await connection.execute(
                    text(
                        "SELECT platform.initialize_telegram_connection("
                        ":workspace,:business,:bot,:external,:owner,CAST(:observation AS jsonb))"
                    ),
                    {
                        "workspace": request.workspace_id,
                        "business": request.business_id,
                        "bot": bot_id,
                        "external": observation["external_connection_id"],
                        "owner": request.expected_owner_id,
                        "observation": json.dumps(observation),
                    },
                )
            ).scalar_one()
            if (
                billing not in {"CREATED", "NOOP"}
                or not isinstance(binding, dict)
                or binding.get("code") not in {"CREATED", "NOOP"}
            ):
                raise ProvisioningError("TELEGRAM_SETUP_COMMIT_INVALID")
            result = CommittedBinding(
                UUID(str(binding["connection_id"])), billing, str(binding["code"])
            )
        return result  # setWebhook may run only after this context has committed.
    finally:
        await engine.dispose()


def discover_connection(updates: list[dict[str, object]], expected_owner_id: str) -> str:
    """Only independently approved Owner lifecycle updates may suggest a candidate."""
    candidates: set[str] = set()
    if len(updates) > 100:
        raise ProvisioningError("TELEGRAM_SETUP_DISCOVERY_INVALID")
    for update in updates:
        value = update.get("business_connection")
        if not isinstance(value, dict):
            continue
        owner = value.get("user")
        if not isinstance(owner, dict) or type(owner.get("id")) is not int:
            continue
        if str(owner["id"]) != expected_owner_id:
            continue
        candidate = value.get("id")
        if isinstance(candidate, str):
            candidates.add(identifier(candidate))
    if len(candidates) != 1:
        raise ProvisioningError("TELEGRAM_SETUP_DISCOVERY_UNRESOLVED")
    return candidates.pop()


async def inspect_connection(
    client: SetupClient,
    request: ProvisionRequest,
    expected_bot_id: str,
    webhook_url: str,
) -> tuple[str, ConnectionObservation]:
    """Read-only discovery; getUpdates occurs once and only without an installed webhook."""
    numeric_id(expected_bot_id)
    async with asyncio.timeout(20):
        webhook = await client.get_webhook_info()
        installed_url = webhook.get("url")
        if not isinstance(installed_url, str) or installed_url not in {"", webhook_url}:
            raise ProvisioningError("TELEGRAM_SETUP_FOREIGN_WEBHOOK")
        bot_id = await client.get_me()
        if bot_id != expected_bot_id:
            raise ProvisioningError("TELEGRAM_SETUP_BOT_MISMATCH")
        external = request.external_connection_id
        if external is None:
            if installed_url:
                raise ProvisioningError("TELEGRAM_SETUP_CONNECTION_REQUIRED")
            external = discover_connection(await client.get_updates(), request.expected_owner_id)
        observed = await client.get_business_connection(external)
        if (
            observed.external_connection_id != external
            or observed.owner_user_id != request.expected_owner_id
            or type(observed.is_enabled) is not bool
            or type(observed.can_reply) is not bool
        ):
            raise ProvisioningError("TELEGRAM_SETUP_OWNER_MISMATCH")
        return bot_id, observed


async def provision(
    client: SetupClient,
    request: ProvisionRequest,
    database_url: str,
    expected_bot_id: str,
    webhook_url: str,
    *,
    commit: Callable[
        [ProvisionRequest, str, str, dict[str, object]], Awaitable[CommittedBinding]
    ] = commit_binding,
) -> dict[str, object]:
    """Discovery never acknowledges updates; retry repairs setWebhook after commit."""
    migrator_target(request.environment, database_url)
    async with asyncio.timeout(40):
        bot_id, observed = await inspect_connection(client, request, expected_bot_id, webhook_url)
        saved = await commit(request, database_url, bot_id, observed.observation(bot_id))
        try:
            await client.set_webhook()
        except Exception:
            raise ProvisioningError("TELEGRAM_SETUP_COMMITTED_WEBHOOK_UNCONFIRMED") from None
        return {
            "status": "TELEGRAM_SETUP_READY",
            "workspace_id": str(request.workspace_id),
            "business_id": str(request.business_id),
            "connection_id": str(saved.connection_id),
            "billing_outcome": saved.billing_outcome,
            "binding_outcome": saved.binding_outcome,
            "is_enabled": observed.is_enabled,
            "can_reply": observed.can_reply,
        }
