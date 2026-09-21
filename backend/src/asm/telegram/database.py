"""Typed Telegram ingress using the kernel's existing runtime transaction guards."""

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from asm.messaging.database import MessagingDatabase, call, require_uuid
from asm.messaging.results import Result


class TelegramReceipt(Result):
    code: Literal["ACCEPTED", "DUPLICATE"]
    receipt_id: UUID
    workspace_id: UUID | None
    connection_id: UUID | None
    inbox_id: UUID | None
    job_id: UUID | None
    accepted_at: datetime
    result_code: Literal[
        "QUEUED",
        "LIFECYCLE_INVALIDATED",
        "IGNORED_NATIVE_OWNER_MESSAGE",
        "IGNORED_ECHO",
        "IGNORED_MESSAGE_EDITED",
        "IGNORED_MESSAGE_DELETED",
        "IGNORED_UNSUPPORTED",
    ]


class TelegramProbe(Result):
    workspace_id: UUID
    connection_id: UUID
    bot_identity: str = Field(repr=False)
    external_connection_id: str = Field(repr=False)
    owner_user_id: str = Field(repr=False)
    generation: int = Field(strict=True, ge=1)
    observation_version: int = Field(strict=True, ge=1)


class TelegramIngress:
    def __init__(self, database: MessagingDatabase, bot_identity: str) -> None:
        self.database, self.bot_identity = database, bot_identity

    async def ingest(self, projection: dict[str, Any], correlation_id: UUID) -> TelegramReceipt:
        require_uuid(correlation_id)
        async with self.database._transaction() as connection:
            result = TelegramReceipt.model_validate(
                await call(
                    connection,
                    "SELECT platform.telegram_ingest(:bot, CAST(:projection AS jsonb), :correlation)",
                    {
                        "bot": self.bot_identity,
                        "projection": json.dumps(
                            projection, ensure_ascii=False, separators=(",", ":")
                        ),
                        "correlation": correlation_id,
                    },
                )
            )
            await self.database.checkpoint("telegram_ingest_before_commit")
        await self.database.checkpoint("telegram_ingest_after_commit")
        return result
