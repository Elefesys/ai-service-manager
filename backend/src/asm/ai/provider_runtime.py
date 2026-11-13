"""Explicit Polza composition, sharing durable execution without fake admission."""

from pathlib import Path

import httpx
from sqlalchemy.exc import SQLAlchemyError

from asm.ai.database import AIDatabase
from asm.ai.polza import PolzaAdapter
from asm.ai.runtime import RuntimeExecution
from asm.ai.runtime_settings import RuntimeSettings, load_key
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import JobClaim
from asm.telegram.client import TelegramClient


class ProviderRuntime(RuntimeExecution):
    def __init__(
        self,
        database: MessagingDatabase,
        settings: RuntimeSettings,
        *,
        environment: str,
        key_file: Path,
        telegram: TelegramClient,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = RuntimeSettings.model_validate(settings)
        settings.current()
        if (
            environment != "TEST"
            or type(telegram) is not TelegramClient
            or telegram.provider_runtime != settings
            or transport is not None
            and type(transport) is not httpx.MockTransport
            or settings.prompt_revision == "conversation_v3"
            and type(transport) is not httpx.MockTransport
        ):
            raise MessagingError(Code.NOT_ALLOWED)
        self.config = settings.gateway()
        self.database = AIDatabase(
            database, environment=environment, delivery=True, provider=settings
        )
        self.telegram = telegram
        self._key_file = key_file
        self._transport = transport
        load_key(key_file)  # Fail closed at startup; no credentials in configuration/DB.

    def new_adapter(self) -> PolzaAdapter:
        self.settings.current()
        return PolzaAdapter(
            self.settings.review,
            load_key(self._key_file),
            transport=self._transport,
            history_profile="gpt_eval_history_v2",
        )

    async def enqueue(self, claim: JobClaim) -> None:
        try:
            await self.database.messaging.enqueue_ai(claim, self.settings.session_id)
        except SQLAlchemyError:
            await self.database.messaging.enqueue_ai(claim, self.settings.session_id)
