"""File capabilities reuse messaging admission and its transaction/task guards."""

from uuid import UUID

from asm.files.models import (
    CleanupClaim,
    CleanupResult,
    FetchPermit,
    FileFinalizeResult,
    ImageManifest,
    UploadPermit,
)
from asm.messaging.database import MessagingDatabase, call, require_uuid
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import JobClaim


class FileDatabase:
    def __init__(self, messaging: MessagingDatabase) -> None:
        self._messaging = messaging

    async def begin_fetch(self, claim: JobClaim) -> FetchPermit:
        async with self._messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            result = FetchPermit.model_validate(
                await unit._execute("SELECT platform.files_begin_fetch(:job,:token)")
            )
        return result

    async def prepare_upload(self, claim: JobClaim, manifest: ImageManifest) -> UploadPermit:
        if type(manifest) is not ImageManifest:
            raise MessagingError(Code.INVALID_INPUT)
        async with self._messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            result = UploadPermit.model_validate(
                await unit._execute(
                    "SELECT platform.files_prepare_upload(:job,:token,CAST(:manifest AS jsonb))",
                    {"manifest": manifest.model_dump_json()},
                )
            )
            await self._messaging.checkpoint("prepare_before_commit")
        await self._messaging.checkpoint("prepare_after_commit")
        return result

    async def finish_fetch(
        self, job_id: UUID, claim_token: UUID, intent_id: UUID
    ) -> FileFinalizeResult:
        for value in (job_id, claim_token, intent_id):
            require_uuid(value)
        async with self._messaging._transaction() as connection:
            result = FileFinalizeResult.model_validate(
                await call(
                    connection,
                    "SELECT platform.files_finish_fetch(:job,:token,:intent)",
                    {"job": job_id, "token": claim_token, "intent": intent_id},
                )
            )
            await self._messaging.checkpoint("fetch_finalize_before_commit")
        await self._messaging.checkpoint("fetch_finalize_after_commit")
        return result

    async def claim_cleanup(self, limit: int = 100) -> tuple[CleanupClaim, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise MessagingError(Code.INVALID_INPUT)
        async with self._messaging._transaction() as connection:
            values = await call(
                connection, "SELECT platform.files_claim_cleanup(:limit)", {"limit": limit}
            )
        return tuple(CleanupClaim.model_validate(value) for value in values)

    async def finish_cleanup(
        self, intent_id: UUID, claim_token: UUID, error: Code | None = None
    ) -> CleanupResult:
        require_uuid(intent_id)
        require_uuid(claim_token)
        if error is not None and error not in (
            Code.DEPENDENCY_TIMEOUT,
            Code.DEPENDENCY_UNAVAILABLE,
        ):
            raise MessagingError(Code.INVALID_INPUT)
        async with self._messaging._transaction() as connection:
            result = await call(
                connection,
                "SELECT platform.files_finish_cleanup(:intent,:token,:error)",
                {
                    "intent": intent_id,
                    "token": claim_token,
                    "error": error.value if error else None,
                },
            )
        return CleanupResult.model_validate(result)
