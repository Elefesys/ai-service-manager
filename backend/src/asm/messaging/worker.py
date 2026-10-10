"""Durable one-job-at-a-time worker and bounded scheduler, no adapter retries."""

import asyncio
import json
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from asm.conversations.turns import ConsumerResult, TurnSnapshot, consume
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.models import OutcomeKind, SendOutcome
from asm.messaging.results import JobClaim, SendPermit

if TYPE_CHECKING:
    from asm.files.transfer import CleanupSweep, FetchTransfer
    from asm.telegram.client import TelegramClient


class Worker:
    def __init__(
        self,
        database: MessagingDatabase,
        adapter: ControlledAdapter,
        *,
        deadline: float = 10,
        files: "FetchTransfer | None" = None,
        telegram: "TelegramClient | None" = None,
    ) -> None:
        if not 0 < deadline < 30:
            raise MessagingError(Code.INVALID_INPUT)
        self.database = database
        self.adapter = adapter
        self.deadline = deadline
        self.files = files
        self.telegram = telegram
        self.worker_id = "controlled-" + str(uuid4())

    async def _finish(self, permit: SendPermit, outcome: SendOutcome) -> None:
        try:
            await self.database.finish_send(
                permit.job_id, permit.claim_token, permit.attempt_id, outcome
            )
        except SQLAlchemyError as primary:
            # Includes a lost commit ACK: the narrow DB function first reads
            # the canonical attempt/result. Never downgrade saved success and
            # never call the adapter from this recovery path. One bounded DB retry.
            try:
                await self.database.finish_send(
                    permit.job_id, permit.claim_token, permit.attempt_id, outcome
                )
            except (SQLAlchemyError, MessagingError) as secondary:
                raise secondary from primary

    async def _retry_error(self, claim: JobClaim, primary: Exception) -> None:
        try:
            await self.database.retry(claim, Code.DEPENDENCY_UNAVAILABLE)
        except (SQLAlchemyError, MessagingError) as secondary:
            raise secondary from primary

    async def _finish_turn(self, claim: JobClaim, result: ConsumerResult) -> None:
        try:
            await self.database.finish_turn(claim, result)
        except SQLAlchemyError as primary:
            try:
                await self.database.replay_turn(claim.job_id, claim.claim_token)
                return
            except MessagingError as miss:
                if miss.code != Code.STALE_CLAIM:
                    raise miss from primary
            except SQLAlchemyError as secondary:
                raise secondary from primary
            # No committed receipt. A second mutation must still pass fresh live
            # claim/XID admission; an expired/reclaimed token cannot finalize.
            try:
                await self.database.finish_turn(claim, result)
            except (SQLAlchemyError, MessagingError) as secondary:
                raise secondary from primary

    async def execute(self, claim: JobClaim) -> None:
        if claim.kind == "PROCESS_INBOX":
            try:
                await self.database.process_inbox(claim)
            except SQLAlchemyError as error:
                await self._retry_error(claim, error)
            except MessagingError as error:
                if error.code == Code.DEPENDENCY_UNAVAILABLE:
                    await self._retry_error(claim, error)
                else:
                    raise
            return

        if claim.kind == "PROCESS_TURN":
            try:
                snapshot = await self.database.process_turn(claim)
            except SQLAlchemyError as error:
                await self._retry_error(claim, error)
                return
            except MessagingError as error:
                if error.code == Code.DEPENDENCY_UNAVAILABLE:
                    await self._retry_error(claim, error)
                    return
                raise
            if isinstance(snapshot, TurnSnapshot):
                await self.database.checkpoint("turn_before_consume")
                result = consume(snapshot)
                await self.database.checkpoint("turn_after_consume")
                await self._finish_turn(claim, result)
            return

        if claim.kind == "FETCH_IMAGE":
            if self.files is None:
                await self.database.retry(claim, Code.DEPENDENCY_UNAVAILABLE)
            else:
                await self.files.execute(claim)
            return

        if claim.kind != "SEND_MANUAL_TEXT":
            raise MessagingError(Code.INVALID_INPUT)

        # If start commit ACK is lost, no permit reaches this code: recovery
        # conservatively marks the durable DISPATCHING attempt UNKNOWN.
        probe = await self.database.telegram_probe(claim)
        if probe is None:
            permit = await self.database.begin_send(claim)
        else:
            observation: dict[str, object] = (
                await self.telegram.observe(
                    probe.bot_identity, probe.external_connection_id, probe.owner_user_id
                )
                if self.telegram is not None
                else {
                    "bot_identity": None,
                    "external_connection_id": None,
                    "owner_user_id": None,
                    "is_enabled": None,
                    "can_reply": None,
                    "error_code": Code.DEPENDENCY_UNAVAILABLE.value,
                }
            )
            permit = await self.database.telegram_begin_send(claim, probe, observation)
        if not isinstance(permit, SendPermit):
            return
        try:
            async with asyncio.timeout(self.deadline):
                await self.adapter.checkpoint("before_call")
                if permit.provider == "TELEGRAM":
                    if self.telegram is None:
                        raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
                    outcome = await self.telegram.send(permit)
                else:
                    outcome = await self.adapter.send(permit)
        except asyncio.CancelledError:
            try:
                await self._finish(
                    permit,
                    SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT),
                )
            except (SQLAlchemyError, MessagingError):
                pass  # durable DISPATCHING is left for scheduler recovery
            raise
        except Exception:
            # Any unclassified/timeout error may follow a provider effect.
            outcome = SendOutcome(OutcomeKind.UNKNOWN, error_code=Code.UNKNOWN_EXTERNAL_RESULT)
        await self.adapter.checkpoint("before_finalize")
        await self._finish(permit, outcome)

    async def run_once(self, stop: asyncio.Event | None = None) -> bool:
        if stop is not None and stop.is_set():
            return False
        claim = await self.database.claim_job(self.worker_id)
        if claim is None:
            return False
        if stop is not None and stop.is_set():
            # No external start; the scheduler can safely reclaim this lease.
            return False
        await self.execute(claim)
        return True


async def run(
    role: Literal["worker", "scheduler"],
    database: MessagingDatabase,
    adapter: ControlledAdapter,
    stop: asyncio.Event,
    *,
    files: "FetchTransfer | None" = None,
    cleanup: "CleanupSweep | None" = None,
    telegram: "TelegramClient | None" = None,
) -> None:
    worker = Worker(database, adapter, files=files, telegram=telegram)
    while not stop.is_set():
        try:
            if role == "worker":
                worked = await worker.run_once(stop)
            else:
                worked = bool(await database.recover_expired())
                if cleanup is not None:
                    worked = await cleanup.run_once() or worked
        except (SQLAlchemyError, MessagingError):
            # Diagnostics contain no exception text, keys, provider data or IDs.
            print(json.dumps({"component": role, "event": "iteration_unavailable"}), flush=True)
            worked = False
        if not worked:
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.25)
            except TimeoutError:
                pass
