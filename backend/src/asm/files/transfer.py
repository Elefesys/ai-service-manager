"""Bounded FETCH and orphan cleanup, using only committed canonical DB permits."""

import asyncio

from sqlalchemy.exc import SQLAlchemyError

from asm.files.database import FileDatabase
from asm.files.models import CleanupClaim, UploadPermit
from asm.files.provider import ImageProvider
from asm.files.storage import ObjectStorage
from asm.files.validation import ImageValidator, read_image
from asm.messaging.adapter import Barrier
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import JobClaim


class FetchTransfer:
    def __init__(
        self,
        database: FileDatabase,
        messaging: MessagingDatabase,
        provider: ImageProvider,
        storage: ObjectStorage,
        *,
        validator: ImageValidator | None = None,
        deadline: float = 20,
        barrier: Barrier | None = None,
    ) -> None:
        if not 0 < deadline <= 20:
            raise MessagingError(Code.INVALID_INPUT)
        self.database = database
        self.messaging = messaging
        self.provider = provider
        self.storage = storage
        self.validator = validator or ImageValidator()
        self.deadline = deadline
        self.barrier = barrier

    async def _checkpoint(self, name: str) -> None:
        if self.barrier is not None:
            await self.barrier(name)

    async def _finish(self, permit: UploadPermit) -> None:
        try:
            await self.database.finish_fetch(permit.job_id, permit.claim_token, permit.intent_id)
        except SQLAlchemyError:
            # The DB first reads the exact durable winner, even after expiry.
            # One recovery query: never repeat download/PUT after a lost ACK.
            await self.database.finish_fetch(permit.job_id, permit.claim_token, permit.intent_id)

    async def _retry(self, claim: JobClaim, code: Code, *, retryable: bool = True) -> None:
        try:
            await self.messaging.retry(claim, code, retryable)
        except SQLAlchemyError:
            # Durable RUNNING/intent state remains for existing lease recovery.
            pass
        except MessagingError as error:
            if error.code not in {
                Code.STALE_CLAIM,
                Code.DEPENDENCY_UNAVAILABLE,
                Code.DEPENDENCY_TIMEOUT,
            }:
                raise

    async def execute(self, claim: JobClaim) -> None:
        try:
            # Overall wall budget, including DB admission, provider stream,
            # decode, committed intent, transport, and bounded finalize recovery.
            # A cancelled synchronous PUT can still arrive later; only durable
            # ABANDONED cleanup handles it, never ad-hoc worker DELETE.
            async with asyncio.timeout(self.deadline):
                source = await self.database.begin_fetch(claim)
                content = await read_image(self.provider.open_image(source))
                manifest = await self.validator.validate(content)
                await self._checkpoint("fetch_after_validation")
                permit = await self.database.prepare_upload(claim, manifest)
                await self._checkpoint("fetch_after_intent")
                await self.storage.put(permit, content)
                await self._checkpoint("fetch_after_put")
                await self._finish(permit)
                await self._checkpoint("fetch_after_ready")
        except asyncio.CancelledError:
            await self._retry(claim, Code.DEPENDENCY_TIMEOUT)
            raise
        except TimeoutError:
            await self._retry(claim, Code.DEPENDENCY_TIMEOUT)
        except SQLAlchemyError:
            await self._retry(claim, Code.DEPENDENCY_UNAVAILABLE)
        except MessagingError as error:
            if error.code == Code.STALE_CLAIM:
                return
            if error.code in {Code.INVALID_INPUT, Code.NOT_FOUND}:
                await self._retry(claim, Code.INVALID_INPUT, retryable=False)
            elif error.code in {Code.DEPENDENCY_TIMEOUT, Code.DEPENDENCY_UNAVAILABLE}:
                await self._retry(claim, error.code)
            else:
                raise

    async def close(self) -> None:
        await self.validator.close()


class CleanupSweep:
    """Two bounded DELETEs per iteration; tombstones survive every success."""

    def __init__(
        self, database: FileDatabase, storage: ObjectStorage, *, deadline: float = 20
    ) -> None:
        if not 0 < deadline <= 20:
            raise MessagingError(Code.INVALID_INPUT)
        self.database = database
        self.storage = storage
        self.deadline = deadline

    async def _one(self, claim: CleanupClaim) -> None:
        error: Code | None = None
        try:
            async with asyncio.timeout(self.deadline):
                await self.storage.delete(claim)
        except TimeoutError:
            error = Code.DEPENDENCY_TIMEOUT
        except MessagingError as exc:
            if exc.code not in {Code.DEPENDENCY_TIMEOUT, Code.DEPENDENCY_UNAVAILABLE}:
                raise
            error = exc.code
        try:
            # Success schedules another check in one hour; late PUT remains
            # discoverable. Outage records a bounded error and bounded backoff.
            await self.database.finish_cleanup(claim.intent_id, claim.claim_token, error)
        except SQLAlchemyError:
            pass  # token lease is reclaimable; no unproven deletion recorded
        except MessagingError as exc:
            if exc.code not in {Code.STALE_CLAIM, Code.DEPENDENCY_UNAVAILABLE}:
                raise

    async def run_once(self) -> bool:
        claims = await self.database.claim_cleanup(limit=2)
        if not claims:
            return False
        await asyncio.gather(*(self._one(claim) for claim in claims))
        return True
