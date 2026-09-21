"""Private S3 operations with explicit credentials and bounded synchronous I/O."""

import asyncio
import base64
import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, TypeVar
from urllib.parse import parse_qs, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import Field

from asm.files.config import StorageSettings
from asm.files.models import CleanupClaim, ReadManifest, UploadPermit
from asm.messaging.database import worker_active
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import Result
from asm.tenancy.database import _active as owner_active

T = TypeVar("T")
SIGNED_GET_TTL_SECONDS = 60
MAX_BYTES = 10_485_760


class ReadGrant(Result):
    url: str = Field(repr=False)
    expires_at: datetime


class ObjectInfo(Result):
    size_bytes: int
    mime_type: str
    checksum_sha256: str | None = None


class ObjectStorage(Protocol):
    async def put(self, permit: UploadPermit, data: bytes) -> None: ...
    async def delete(self, permit: CleanupClaim) -> None: ...
    async def head(self, storage_key: str) -> ObjectInfo: ...
    async def get(self, storage_key: str) -> bytes: ...
    def presign_get(self, manifest: ReadManifest) -> ReadGrant: ...


class S3ObjectStorage:
    def __init__(self, settings: StorageSettings) -> None:
        self._settings = settings
        # No credential/region/metadata discovery and no hidden SDK retries.
        self._client = boto3.session.Session().client(
            "s3",
            endpoint_url=settings.endpoint,
            region_name=settings.region,
            aws_access_key_id=settings.access_key.get_secret_value(),
            aws_secret_access_key=settings.secret_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                connect_timeout=2,
                read_timeout=5,
                retries={"total_max_attempts": 1, "mode": "standard"},
                max_pool_connections=2,
                s3={"addressing_style": "path", "payload_signing_enabled": True},
                proxies={},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="asm-s3")
        self._slots = asyncio.Semaphore(2)
        self._pending: set[asyncio.Future[Any]] = set()
        self._closed = False

    async def _io(self, operation: Callable[[], T]) -> T:
        if worker_active() or owner_active.get() is not None:
            raise MessagingError(Code.TRANSACTION_STATE)
        try:
            async with asyncio.timeout(8):
                await self._slots.acquire()
                if self._closed:
                    self._slots.release()
                    raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)
                try:
                    future = asyncio.wrap_future(self._executor.submit(operation))
                except BaseException:
                    self._slots.release()
                    raise
                self._pending.add(future)

                def finished(value: asyncio.Future[T]) -> None:
                    # Await cancellation does not stop a synchronous PUT. Keep
                    # its slot until the actual operation exits, including errors.
                    self._pending.discard(value)
                    self._slots.release()
                    if not value.cancelled():
                        value.exception()

                future.add_done_callback(finished)
                return await asyncio.shield(future)
        except TimeoutError:
            raise MessagingError(Code.DEPENDENCY_TIMEOUT) from None
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise MessagingError(Code.NOT_FOUND) from None
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE) from None
        except BotoCoreError:
            raise MessagingError(Code.DEPENDENCY_UNAVAILABLE) from None

    async def put(self, permit: UploadPermit, data: bytes) -> None:
        if (
            type(permit) is not UploadPermit
            or type(data) is not bytes
            or len(data) != permit.manifest.size_bytes
            or hashlib.sha256(data).hexdigest() != permit.manifest.sha256
        ):
            raise MessagingError(Code.INVALID_INPUT)
        checksum = base64.b64encode(bytes.fromhex(permit.manifest.sha256)).decode("ascii")

        def operation() -> None:
            response = self._client.put_object(
                Bucket=self._settings.bucket,
                Key=permit.storage_key,
                Body=data,
                ContentLength=len(data),
                ContentType=permit.manifest.mime_type,
                CacheControl="private, no-store",
                ChecksumSHA256=checksum,
                IfNoneMatch="*",
            )
            if response.get("ChecksumSHA256") != checksum:
                # A PUT may have happened: durable intent recovery owns cleanup.
                raise MessagingError(Code.DEPENDENCY_UNAVAILABLE)

        await self._io(operation)

    async def delete(self, permit: CleanupClaim) -> None:
        if type(permit) is not CleanupClaim:
            raise MessagingError(Code.INVALID_INPUT)

        def operation() -> None:
            self._client.delete_object(Bucket=self._settings.bucket, Key=permit.storage_key)

        await self._io(operation)

    async def head(self, storage_key: str) -> ObjectInfo:
        def operation() -> ObjectInfo:
            response = self._client.head_object(
                Bucket=self._settings.bucket, Key=storage_key, ChecksumMode="ENABLED"
            )
            return ObjectInfo(
                size_bytes=response["ContentLength"],
                mime_type=response["ContentType"],
                checksum_sha256=response.get("ChecksumSHA256"),
            )

        return await self._io(operation)

    async def get(self, storage_key: str) -> bytes:
        def operation() -> bytes:
            response = self._client.get_object(
                Bucket=self._settings.bucket, Key=storage_key, ChecksumMode="ENABLED"
            )
            body = response["Body"]
            try:
                if response["ContentLength"] > MAX_BYTES:
                    raise MessagingError(Code.INVALID_INPUT)
                data = body.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise MessagingError(Code.INVALID_INPUT)
                return data
            finally:
                body.close()

        return await self._io(operation)

    def presign_get(self, manifest: ReadManifest) -> ReadGrant:
        # Pure local signing with credentials supplied at construction. No DNS,
        # refreshable credentials, metadata service, bucket check or external I/O.
        if type(manifest) is not ReadManifest or self._closed:
            raise MessagingError(Code.INVALID_INPUT)
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
            manifest.manifest.mime_type
        ]
        url = self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._settings.bucket,
                "Key": manifest.storage_key,
                "ResponseContentType": manifest.manifest.mime_type,
                "ResponseContentDisposition": f'inline; filename="{manifest.file_id}.{extension}"',
                "ResponseCacheControl": "private, no-store",
            },
            ExpiresIn=SIGNED_GET_TTL_SECONDS,
            HttpMethod="GET",
        )
        issued = datetime.strptime(
            parse_qs(urlsplit(url).query)["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ"
        ).replace(tzinfo=UTC)
        return ReadGrant(url=url, expires_at=issued + timedelta(seconds=SIGNED_GET_TTL_SECONDS))

    async def close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        pending = tuple(self._pending)
        if pending:
            # Transport deadlines bound ordinary shutdown. Never close a live
            # client's pool under an outstanding synchronous operation.
            await asyncio.gather(*(asyncio.shield(f) for f in pending), return_exceptions=True)
        self._client.close()
