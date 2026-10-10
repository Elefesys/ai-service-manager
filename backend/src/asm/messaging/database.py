"""Short PostgreSQL capabilities; worker authority never uses a human principal."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from psycopg import AsyncConnection as PsycopgAsyncConnection
from psycopg.pq import TransactionStatus
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from asm.conversations.turns import ConsumerReceipt, ConsumerResult, TurnProgress, TurnSnapshot
from asm.messaging.adapter import Barrier, TrustedSource
from asm.messaging.errors import Code, MessagingError, database_error
from asm.messaging.models import NormalizedEventV1, SendOutcome, identifier
from asm.messaging.results import (
    FinalizeResult,
    InboxProcessingResult,
    InboxReceipt,
    JobClaim,
    ScanStep,
    SendPermit,
    TerminalRejection,
    parse_claim,
)
from asm.tenancy.database import _active as _owner_active

if TYPE_CHECKING:
    from asm.telegram.database import TelegramProbe

_active: ContextVar["WorkerUnitOfWork | None"] = ContextVar("asm_worker_unit", default=None)


def worker_active() -> bool:
    # Inherited context in another asyncio Task also prevents nested admission.
    return _active.get() is not None


def require_uuid(value: object) -> None:
    if type(value) is not UUID:
        raise MessagingError(Code.INVALID_INPUT)


async def physical_transaction(connection: AsyncConnection) -> None:
    driver = (await connection.get_raw_connection()).driver_connection
    if (
        not isinstance(driver, PsycopgAsyncConnection)
        or driver.autocommit
        or driver.info.transaction_status != TransactionStatus.INTRANS
        or not connection.in_transaction()
    ):
        raise MessagingError(Code.TRANSACTION_STATE)


async def call(connection: AsyncConnection, sql: str, params: dict[str, object]) -> Any:
    try:
        return (await connection.execute(text(sql), params)).scalar_one()
    except DBAPIError as error:
        bounded = database_error(error)
        if bounded is not None:
            raise bounded from None
        raise


class WorkerUnitOfWork:
    def __init__(self, connection: AsyncConnection, claim: JobClaim) -> None:
        self._connection = connection
        self._claim = claim
        self._task = asyncio.current_task()
        self._closed = False
        self._failed = False

    def _assert_active(self) -> None:
        if (
            self._closed
            or self._failed
            or self._task is not asyncio.current_task()
            or _active.get() is not self
            or _owner_active.get() is not None
            or not self._connection.in_transaction()
        ):
            raise MessagingError(Code.TRANSACTION_STATE)

    @property
    def claim(self) -> JobClaim:
        self._assert_active()
        return self._claim

    async def _check(self) -> None:
        self._assert_active()
        await physical_transaction(self._connection)
        binding = (
            (
                await self._connection.execute(
                    text("""
                SELECT current_setting('asm.actor_kind', true) AS kind,
                       nullif(current_setting('asm.actor_id', true), '') AS actor,
                       current_setting('asm.workspace_id', true) AS workspace,
                       current_setting('asm.context_xid', true) AS context_xid,
                       pg_current_xact_id_if_assigned()::text AS xid
            """)
                )
            )
            .mappings()
            .one()
        )
        if (
            binding["kind"] != "worker_job"
            or binding["actor"] is not None
            or binding["workspace"] != str(self._claim.workspace_id)
            or not binding["xid"]
            or binding["xid"] != binding["context_xid"]
        ):
            raise MessagingError(Code.TRANSACTION_STATE)

    async def _execute(self, sql: str, extra: dict[str, object] | None = None) -> Any:
        try:
            await self._check()
            return await call(
                self._connection,
                sql,
                {
                    "job": self._claim.job_id,
                    "token": self._claim.claim_token,
                    **(extra or {}),
                },
            )
        except BaseException:
            self._failed = True
            raise

    async def process_inbox(self) -> InboxProcessingResult:
        return InboxProcessingResult.model_validate(
            await self._execute("SELECT platform.messaging_process_inbox(:job, :token)")
        )

    async def begin_send(self) -> SendPermit | TerminalRejection:
        result = await self._execute("SELECT platform.messaging_begin_send(:job, :token)")
        if result["code"] == "PERMITTED":
            return SendPermit.model_validate(result)
        return TerminalRejection.model_validate(result)

    async def retry(self, code: Code, retryable: bool) -> dict[str, object]:
        if type(code) is not Code or type(retryable) is not bool:
            raise MessagingError(Code.INVALID_INPUT)
        return cast(
            dict[str, object],
            await self._execute(
                "SELECT platform.messaging_retry(:job, :token, :error, :retryable)",
                {"error": code.value, "retryable": retryable},
            ),
        )


class MessagingDatabase:
    def __init__(self, engine: AsyncEngine, *, barrier: Barrier | None = None) -> None:
        if engine.url.drivername != "postgresql+psycopg" or engine.url.username != "asm_runtime":
            raise MessagingError(Code.ACCESS_DENIED)
        self._engine = engine
        self._barrier = barrier
        self._claim_scan: dict[str, ScanStep] = {}
        self._recovery_scan: ScanStep | None = None

    async def checkpoint(self, name: str) -> None:
        if self._barrier is not None:
            await self._barrier(name)

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncConnection]:
        if _owner_active.get() is not None or worker_active():
            raise MessagingError(Code.TRANSACTION_STATE)
        async with self._engine.connect() as connection, connection.begin():
            driver = (await connection.get_raw_connection()).driver_connection
            if not isinstance(driver, PsycopgAsyncConnection) or driver.autocommit:
                raise MessagingError(Code.TRANSACTION_STATE)
            if await call(connection, "SELECT current_user", {}) != "asm_runtime":
                raise MessagingError(Code.ACCESS_DENIED)
            await physical_transaction(connection)
            if await call(connection, "SHOW transaction_isolation", {}) != "read committed":
                raise MessagingError(Code.TRANSACTION_STATE)
            await connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            await connection.execute(text("SET LOCAL lock_timeout = '2s'"))
            yield connection
            await physical_transaction(connection)

    async def ingest_event(
        self,
        trusted_source: TrustedSource,
        event: NormalizedEventV1,
        correlation_id: UUID,
    ) -> InboxReceipt:
        if type(trusted_source) is not TrustedSource or type(event) is not NormalizedEventV1:
            raise MessagingError(Code.INVALID_INPUT)
        trusted_source.validate()
        require_uuid(correlation_id)
        if (event.provider, event.bot_identity) != (
            trusted_source.provider,
            trusted_source.bot_identity,
        ):
            raise MessagingError(Code.ACCESS_DENIED)
        async with self._transaction() as connection:
            result = InboxReceipt.model_validate(
                await call(
                    connection,
                    "SELECT platform.messaging_ingest(:provider, :bot, CAST(:event AS jsonb), :correlation)",
                    {
                        "provider": trusted_source.provider,
                        "bot": trusted_source.bot_identity,
                        "event": event.encoded(),
                        "correlation": correlation_id,
                    },
                )
            )
            await self.checkpoint("ingest_before_commit")
        await self.checkpoint("ingest_after_commit")
        return result

    async def claim_job(self, worker_id: str) -> JobClaim | None:
        identifier(worker_id)
        scan = self._claim_scan.get(worker_id)
        for _ in range(100):
            async with self._transaction() as connection:
                result = ScanStep.model_validate(
                    await call(
                        connection,
                        "SELECT platform.messaging_claim(:worker, :until, :at, :id)",
                        {"worker": worker_id, **self._scan_parameters(scan)},
                    )
                )
            # Only advance after a confirmed commit. A failed commit is not idle success.
            if result.step == "END":
                self._claim_scan.pop(worker_id, None)
                return None
            self._check_scan_position(result)
            scan = result
            self._claim_scan[worker_id] = scan
            if len(self._claim_scan) > 128:
                self._claim_scan.pop(next(iter(self._claim_scan)))
            if result.step == "CLAIMED":
                # A successful public call starts a fresh page next time. Only
                # the bounded BUSY/terminal prefix needs continuation between calls.
                self._claim_scan.pop(worker_id, None)
                return parse_claim(result.claim)
        return None

    @staticmethod
    def _scan_parameters(scan: ScanStep | None) -> dict[str, object]:
        return {
            "until": scan.scan_until if scan else None,
            "at": scan.at if scan else None,
            "id": scan.id if scan else None,
        }

    @staticmethod
    def _check_scan_position(scan: ScanStep) -> None:
        if scan.at is None or scan.id is None:
            raise MessagingError(Code.INVALID_INPUT)

    @asynccontextmanager
    async def admit_job(self, job_id: UUID, claim_token: UUID) -> AsyncIterator[WorkerUnitOfWork]:
        require_uuid(job_id)
        require_uuid(claim_token)
        async with self._transaction() as connection:
            # Caller-supplied workspace/entity/kind fields are never used for admission.
            claim = parse_claim(
                await call(
                    connection,
                    "SELECT platform.messaging_admit(:job, :token)",
                    {"job": job_id, "token": claim_token},
                )
            )
            unit = WorkerUnitOfWork(connection, claim)
            token = _active.set(unit)
            try:
                await unit._check()
                yield unit
                await unit._check()
            finally:
                unit._closed = True
                _active.reset(token)

    async def process_inbox(self, claim: JobClaim) -> InboxProcessingResult:
        async with self.admit_job(claim.job_id, claim.claim_token) as unit:
            result = await unit.process_inbox()
            await self.checkpoint("process_before_commit")
        await self.checkpoint("process_after_commit")
        return result

    async def begin_send(self, claim: JobClaim) -> SendPermit | TerminalRejection:
        async with self.admit_job(claim.job_id, claim.claim_token) as unit:
            result = await unit.begin_send()
            await self.checkpoint("start_before_commit")
        # This is the only method returning a usable permit to the worker.
        await self.checkpoint("start_after_commit")
        return result

    async def telegram_probe(self, claim: JobClaim) -> "TelegramProbe | None":
        from asm.telegram.database import TelegramProbe

        async with self.admit_job(claim.job_id, claim.claim_token) as unit:
            result = await unit._execute("SELECT platform.telegram_worker_probe(:job, :token)")
            return TelegramProbe.model_validate(result) if result is not None else None

    async def telegram_begin_send(
        self, claim: JobClaim, probe: "TelegramProbe", observation: dict[str, object]
    ) -> SendPermit | TerminalRejection:
        async with self.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit._execute(
                "SELECT platform.telegram_begin_send(:job, :token, :generation, :version, CAST(:observation AS jsonb))",
                {
                    "generation": probe.generation,
                    "version": probe.observation_version,
                    "observation": json.dumps(observation),
                },
            )
            result = (
                SendPermit.model_validate(raw)
                if raw["code"] == "PERMITTED"
                else TerminalRejection.model_validate(raw)
            )
            await self.checkpoint("start_before_commit")
        await self.checkpoint("start_after_commit")
        return result

    async def finish_send(
        self, job_id: UUID, claim_token: UUID, attempt_id: UUID, outcome: SendOutcome
    ) -> FinalizeResult:
        for value in (job_id, claim_token, attempt_id):
            require_uuid(value)
        if type(outcome) is not SendOutcome:
            raise MessagingError(Code.INVALID_INPUT)
        async with self._transaction() as connection:
            # DB reads canonical attempt/outcome first. Exact saved replay needs
            # no live lease; a new mutation admits the claim in this transaction.
            result = FinalizeResult.model_validate(
                await call(
                    connection,
                    "SELECT platform.messaging_finish_send(:job, :token, :attempt, :outcome, :provider_id, :error, :delay)",
                    {
                        "job": job_id,
                        "token": claim_token,
                        "attempt": attempt_id,
                        "outcome": outcome.kind.value,
                        "provider_id": outcome.provider_message_id,
                        "error": outcome.error_code.value if outcome.error_code else None,
                        "delay": outcome.retry_after_seconds,
                    },
                )
            )
            await self.checkpoint("finalize_before_commit")
        await self.checkpoint("finalize_after_commit")
        return result

    async def recover_expired(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise MessagingError(Code.INVALID_INPUT)
        recovered = 0
        for _ in range(100):
            async with self._transaction() as connection:
                result = ScanStep.model_validate(
                    await call(
                        connection,
                        "SELECT platform.messaging_recover_expired(:until, :at, :id)",
                        self._scan_parameters(self._recovery_scan),
                    )
                )
            if result.step == "END":
                self._recovery_scan = None
                break
            self._check_scan_position(result)
            self._recovery_scan = result
            if result.step == "RECOVERED":
                recovered += 1
            if recovered == limit:
                break
        return recovered

    async def process_turn(self, claim: JobClaim) -> TurnSnapshot | TurnProgress:
        async with self.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit._execute("SELECT platform.turn_execute(:job, :token)")
            result = (
                TurnSnapshot.model_validate(raw)
                if raw["code"] == "SNAPSHOT"
                else TurnProgress.model_validate(raw)
            )
            await self.checkpoint("turn_before_commit")
        await self.checkpoint("turn_after_commit")
        return result

    async def finish_turn(
        self, claim: JobClaim, result: ConsumerResult
    ) -> ConsumerReceipt | TurnProgress:
        require_uuid(claim.job_id)
        require_uuid(claim.claim_token)
        if type(result) is not ConsumerResult:
            raise MessagingError(Code.INVALID_INPUT)
        async with self._transaction() as connection:
            raw = await call(
                connection,
                "SELECT platform.turn_consumer_finalize(:job, :token, CAST(:result AS jsonb))",
                {
                    "job": claim.job_id,
                    "token": claim.claim_token,
                    "result": result.model_dump_json(),
                },
            )
            receipt = (
                TurnProgress.model_validate(raw)
                if raw["code"] == "SUPERSEDED"
                else ConsumerReceipt.model_validate(raw)
            )
            await self.checkpoint("turn_finalize_before_commit")
        await self.checkpoint("turn_finalize_after_commit")
        return receipt

    async def replay_turn(self, job_id: UUID, claim_token: UUID) -> ConsumerReceipt:
        require_uuid(job_id)
        require_uuid(claim_token)
        async with self._transaction() as connection:
            return ConsumerReceipt.model_validate(
                await call(
                    connection,
                    "SELECT platform.turn_consumer_replay(:job, :token)",
                    {"job": job_id, "token": claim_token},
                )
            )

    async def retry(self, claim: JobClaim, code: Code, retryable: bool = True) -> dict[str, object]:
        async with self.admit_job(claim.job_id, claim.claim_token) as unit:
            return await unit.retry(code, retryable)
