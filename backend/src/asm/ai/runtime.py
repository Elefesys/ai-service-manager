"""Explicit LOCAL/TEST composition. No provider key, probe CLI or live transport."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from asm.ai.contracts import GatewayConfig
from asm.ai.database import AIDatabase, runtime_config
from asm.ai.fake import FakeAdapter
from asm.ai.gateway import ModelAdapter
from asm.ai.runtime_contracts import RuntimeStop
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import AIJobClaim, JobClaim
from asm.telegram.client import TelegramClient


class RuntimeExecution:
    config: GatewayConfig
    database: AIDatabase
    telegram: TelegramClient | None

    def new_adapter(self) -> ModelAdapter:
        raise NotImplementedError

    async def execute(self, claim: AIJobClaim) -> None:
        try:
            adapter = self.new_adapter()
            if adapter.capabilities.route != self.config.route:
                raise MessagingError(Code.NOT_ALLOWED)
            async with asyncio.timeout(self.config.limits.duration_seconds):
                try:
                    result = await self.database.execute(
                        claim,
                        self.config,
                        adapter,
                        deadline=datetime.now(UTC)
                        + timedelta(seconds=self.config.limits.duration_seconds),
                        telegram=self.telegram,
                    )
                except SQLAlchemyError:
                    try:
                        await self.database.replay(claim, self.config)
                        return
                    except MessagingError as error:
                        if error.code != Code.STALE_CLAIM:
                            raise
                    # A missing receipt after a lost ACK permits only STOP.
                    await self.stop(claim)
                    return
            if not isinstance(result, RuntimeStop):
                return
        except asyncio.CancelledError as cancelled:
            try:
                await self.stop(claim)
            finally:
                # A second cancellation or failed STOP cannot replace the
                # original cancellation with successful completion.
                raise cancelled
        except Exception:
            # A bounded synthetic model failure terminalizes this job. It must
            # not cancel the independent inbound/manual worker task.
            pass
        await self.stop(claim)

    async def stop(self, claim: AIJobClaim) -> None:
        # The reservation already prevents regeneration. If this bounded attempt
        # fails, finite lease recovery owns terminalization; never retry a model.
        try:
            async with asyncio.timeout(2):
                await self.database._command(claim, "STOP")
        except (MessagingError, SQLAlchemyError, TimeoutError):
            pass


class SyntheticRuntime(RuntimeExecution):
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

    def new_adapter(self) -> ModelAdapter:
        adapter = self.model()
        if not isinstance(adapter, FakeAdapter):
            raise MessagingError(Code.NOT_ALLOWED)
        return adapter
