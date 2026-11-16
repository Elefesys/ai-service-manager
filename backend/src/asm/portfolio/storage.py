"""Separate owner permits on the existing bounded private S3 transport."""

import asyncio
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from asm.files.models import OwnerCleanupPermit, OwnerDeletePermit, OwnerUploadPermit
from asm.files.storage import ObjectInfo
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.portfolio.errors import PortfolioError
from asm.portfolio.repository import decoded, private_call


class PortfolioStorage(Protocol):
    async def put_owner(self, permit: OwnerUploadPermit, data: bytes) -> None: ...
    async def delete_owner(self, permit: OwnerCleanupPermit | OwnerDeletePermit) -> None: ...
    async def head(self, storage_key: str) -> ObjectInfo: ...
    async def get(self, storage_key: str) -> bytes: ...


class PortfolioCleanupSweep:
    """At most two own unfinished DELETEs; durable tombstones retain late PUT checks."""

    def __init__(self, database: MessagingDatabase, storage: PortfolioStorage):
        self.database, self.storage = database, storage

    async def _one(self, permit: OwnerCleanupPermit) -> None:
        error = None
        cancelled = False
        try:
            async with asyncio.timeout(10):
                await self.storage.delete_owner(permit)
        except TimeoutError:
            error = "DEPENDENCY_TIMEOUT"
        except asyncio.CancelledError:
            error = "DEPENDENCY_TIMEOUT"
            cancelled = True
        except MessagingError as exc:
            error = (
                "DEPENDENCY_TIMEOUT"
                if exc.code == Code.DEPENDENCY_TIMEOUT
                else "DEPENDENCY_UNAVAILABLE"
            )
        try:
            async with (
                asyncio.timeout(1 if cancelled else 4),
                self.database._transaction() as connection,
            ):
                await private_call(
                    connection,
                    "SELECT platform.portfolio_cleanup_complete(:version,:claim,:error)",
                    dict(version=permit.version_id, claim=permit.claim_token, error=error),
                )
        except (PortfolioError, MessagingError, SQLAlchemyError, TimeoutError):
            pass  # Durable lease/backoff remains; no success is invented.
        if cancelled:
            raise asyncio.CancelledError

    async def run_once(self) -> bool:
        async with self.database._transaction() as connection:
            raw = await private_call(
                connection, "SELECT platform.portfolio_cleanup_claim(:maximum)", {"maximum": 2}
            )
        permits = tuple(decoded(OwnerCleanupPermit, value) for value in raw)
        await asyncio.gather(*(self._one(permit) for permit in permits))
        return bool(permits)
