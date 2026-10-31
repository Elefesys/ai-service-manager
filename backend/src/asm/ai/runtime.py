"""Explicit LOCAL/TEST composition. No provider key, probe CLI or live transport."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from asm.ai.contracts import GatewayConfig
from asm.ai.database import AIDatabase, runtime_config
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_contracts import RuntimeStop
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AIJobClaim, JobClaim
from asm.telegram.client import TelegramClient


class SyntheticRuntime:
    """One durable AI lane alongside the ordinary inbound/manual worker.

    The factory returns a new bounded fake model per job; it is never a recovery
    mechanism. PostgreSQL reserves calls and refuses regeneration after restart.
    """

    def __init__(
        self,
        database: MessagingDatabase,
        config: GatewayConfig,
        model: Callable[[], FakeAdapter],
        *,
        environment: str,
        telegram: TelegramClient | None = None,
    ) -> None:
        self.config = runtime_config(config)
        self.database = AIDatabase(database, environment=environment, delivery=True)
        if telegram is not None and (
            type(telegram) is not TelegramClient or not telegram.synthetic_ai
        ):
            raise MessagingError(Code.NOT_ALLOWED)
        self.model = model
        self.telegram = telegram

    async def enqueue(self, claim: JobClaim) -> None:
        try:
            await self.database.messaging.enqueue_ai(claim)
        except SQLAlchemyError:
            # Exact source-claim replay, with no controlled consumer execution.
            await self.database.messaging.enqueue_ai(claim)

    async def execute(self, claim: AIJobClaim) -> None:
        try:
            adapter = self.model()
            if (
                not isinstance(adapter, FakeAdapter)
                or adapter.capabilities.route != self.config.route
            ):
                raise MessagingError(Code.NOT_ALLOWED)
            async with asyncio.timeout(self.config.limits.duration_seconds):
                result = await self.database.execute(
                    claim,
                    self.config,
                    adapter,
                    deadline=datetime.now(UTC)
                    + timedelta(seconds=self.config.limits.duration_seconds),
                )
            if not isinstance(result, RuntimeStop):
                return
        except SQLAlchemyError:
            try:
                await self.database.replay(claim, self.config)
                return
            except MessagingError as error:
                if error.code != Code.STALE_CLAIM:
                    raise
        except asyncio.CancelledError:
            await self.stop(claim)
            raise
        except Exception:
            # A bounded synthetic model failure terminalizes this job. It must
            # not cancel the independent inbound/manual worker task.
            pass
        await self.stop(claim)

    async def stop(self, claim: AIJobClaim) -> None:
        # An expired/dead lease is left to the finite DB recovery transition.
        try:
            await self.database._command(claim, "STOP")
        except (MessagingError, SQLAlchemyError):
            pass
