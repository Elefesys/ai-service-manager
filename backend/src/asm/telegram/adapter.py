"""Explicit dispatch alongside CONTROLLED, without a registry or hidden retries."""

from typing import TYPE_CHECKING

from asm.messaging.models import SendOutcome
from asm.messaging.results import SendPermit
from asm.telegram.client import TelegramClient

if TYPE_CHECKING:
    from asm.messaging.http_service import ConnectionObservation, ConnectionProbe


class TelegramAdapter:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def checkpoint(self, name: str) -> None:
        pass

    async def send(self, permit: SendPermit) -> SendOutcome:
        return await self.client.send(permit)


class TelegramRefresher:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def refresh(self, probe: "ConnectionProbe") -> "ConnectionObservation":
        from asm.messaging.http_service import ConnectionObservation

        return ConnectionObservation.model_validate(
            await self.client.observe(
                probe.bot_identity, probe.external_connection_id, probe.owner_user_id
            )
        )
