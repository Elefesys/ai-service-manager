"""M2-A07/A08: real private S3 and PostgreSQL owner/entity authorization."""

import asyncio
import base64
import hashlib
from datetime import UTC, datetime
from io import BytesIO
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from asm.files.config import StorageSettings
from asm.files.database import FileDatabase
from asm.files.provider import ControlledImageProvider
from asm.files.service import read_image
from asm.files.storage import S3ObjectStorage
from asm.files.transfer import FetchTransfer
from asm.messaging.errors import Code, MessagingError
from asm.messaging.worker import Worker
from asm.tenancy import AuthenticatedAccount, TenancyError
from botocore.exceptions import ClientError
from PIL import Image
from test_m2_1_models import event
from test_m2_1_postgres import messaging as messaging
from test_m2_1_postgres import query, receive
from test_tenancy_postgres import PROVIDER, UA, UB, A, B
from test_tenancy_postgres import db as db
from test_tenancy_postgres import seeded as seeded

pytestmark = pytest.mark.integration


def image_bytes(kind="PNG"):
    stream = BytesIO()
    Image.new("RGB", (23, 17), (21, 90, 153)).save(stream, format=kind)
    return stream.getvalue()


async def request(method, url, **kwargs):
    # Failed HTTP diagnostics must not print the bearer URL into CI artifacts.
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            return await client.request(method, url, **kwargs)
    except httpx.HTTPError:
        pytest.fail("PRIVATE_S3_HTTP_UNAVAILABLE", pytrace=False)


@pytest_asyncio.fixture
async def images(messaging):
    h = messaging
    h.storage = S3ObjectStorage(StorageSettings())
    h.files = FileDatabase(h.kernel)

    async def no_transaction(_):
        assert h.runtime.engine.pool.checkedout() == 0

    h.provider = ControlledImageProvider(environment="TEST", barrier=no_transaction)
    h.transfer = FetchTransfer(h.files, h.kernel, h.provider, h.storage)
    h.image_worker = Worker(h.kernel, h.adapter, files=h.transfer)
    try:
        yield h
    finally:
        # Delete exactly this fixture's recorded TEST keys, before FK teardown.
        rows = await query(
            h, "SELECT storage_key FROM platform.file_object_uploads WHERE workspace_id=:ws", ws=A
        )
        for row in rows:
            await h.storage._io(
                lambda key=row["storage_key"]: h.storage._client.delete_object(
                    Bucket=h.storage._settings.bucket, Key=key
                )
            )
        await h.transfer.close()
        await h.storage.close()


async def plan(h, content, suffix="one", *, chat="chat-a", connection="conn-a"):
    ref = "opaque-" + suffix
    if content is not None:
        h.provider.register("bot-a", ref, content, content_length=1, content_type="text/plain")
    _, result = await receive(
        h,
        event(
            event_id="event-" + suffix,
            message_id="message-" + suffix,
            external_connection_id=connection,
            chat_id=chat,
            text=None,
            image_file_id=ref,
        ),
    )
    return (
        await query(
            h, "SELECT * FROM app.file_objects WHERE message_id=:message", message=result.message_id
        )
    )[0]


async def grant(h, row, *, actor=UA, workspace=A, **overrides):
    return await read_image(
        h.runtime.tenancy,
        AuthenticatedAccount(actor),
        workspace,
        uuid4(),
        overrides.get("conversation_id", row["conversation_id"]),
        overrides.get("message_id", row["message_id"]),
        overrides.get("file_id", row["id"]),
        h.storage,
    )


@pytest.mark.parametrize(
    "kind,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
async def test_original_roundtrip_validated_manifest_and_private_signed_http(images, kind, mime):
    h = images
    content = image_bytes(kind)
    row = await plan(h, content)
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await grant(h, row)
    # Assert both sides of the real S3 transport boundary have released DB pool.
    original_io = h.storage._io

    async def checked_io(operation):
        assert h.runtime.engine.pool.checkedout() == 0
        return await original_io(operation)

    h.storage._io = checked_io
    assert await h.image_worker.run_once()
    ready = (await query(h, "SELECT * FROM app.file_objects WHERE id=:id", id=row["id"]))[0]
    assert ready["status"] == "READY"
    assert (
        ready["mime_type"],
        ready["size_bytes"],
        ready["sha256"],
        ready["width"],
        ready["height"],
    ) == (
        mime,
        len(content),
        hashlib.sha256(content).hexdigest(),
        23,
        17,
    )
    info = await h.storage.head(ready["storage_key"])
    assert info.size_bytes == len(content) and info.mime_type == mime
    assert info.checksum_sha256 == base64.b64encode(hashlib.sha256(content).digest()).decode()
    assert await h.storage.get(ready["storage_key"]) == content
    signed = await grant(h, row)
    parts = urlsplit(signed.url)
    assert parse_qs(parts.query)["X-Amz-Expires"] == ["60"]
    assert 58 <= (signed.expires_at - datetime.now(UTC)).total_seconds() <= 60
    result = await request("GET", signed.url)
    assert result.status_code == 200
    assert result.content == content
    assert result.headers["content-type"] == mime
    assert result.headers["cache-control"] == "private, no-store"
    assert str(row["id"]) in result.headers["content-disposition"]
    assert "provider" not in repr(signed) and "X-Amz" not in repr(signed)

    unsigned = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    assert (await request("GET", unsigned)).status_code == 403
    assert (await request("PUT", unsigned + "-anonymous", content=b"no")).status_code == 403
    bucket_url = h.storage._settings.endpoint + "/" + h.storage._settings.bucket
    assert (await request("GET", bucket_url + "?list-type=2")).status_code == 403
    params = parse_qs(parts.query)
    params["X-Amz-Signature"] = ["0" * 64]
    tampered = urlunsplit(parts._replace(query=urlencode(params, doseq=True)))
    assert (await request("GET", tampered)).status_code == 403


async def test_live_owner_relation_workspace_role_and_failed_file_negatives(images):
    h = images
    first = await plan(h, image_bytes(), "first")
    assert await h.image_worker.run_once()
    second = await plan(h, image_bytes(), "second", chat="other-chat", connection="conn-a2")
    assert await h.image_worker.run_once()
    assert (await request("GET", (await grant(h, second)).url)).status_code == 200
    for overrides in (
        {"workspace": B},
        {"actor": UB, "workspace": B},
        {"actor": PROVIDER},
        {"conversation_id": second["conversation_id"]},
        {"message_id": second["message_id"]},
        {"file_id": second["id"]},
        {"file_id": uuid4()},
    ):
        with pytest.raises((MessagingError, TenancyError)):
            await grant(h, first, **overrides)
    for role in ("ADMIN", "PROVIDER"):
        await query(
            h,
            "UPDATE platform.workspace_memberships SET role=:role WHERE workspace_id=:ws AND user_account_id=:actor RETURNING role",
            role=role,
            ws=A,
            actor=UA,
        )
        with pytest.raises((MessagingError, TenancyError)):
            await grant(h, first)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET role='OWNER' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING role",
        ws=A,
        actor=UA,
    )
    # Disconnect does not revoke access to durably accepted historical media.
    await query(
        h,
        "UPDATE app.channel_connections SET status='INACTIVE' WHERE workspace_id=:ws RETURNING id",
        ws=A,
    )
    assert (await request("GET", (await grant(h, first)).url)).status_code == 200
    await query(
        h,
        "UPDATE app.channel_connections SET status='ACTIVE' WHERE workspace_id=:ws RETURNING id",
        ws=A,
    )
    # Missing provider ref reaches terminal FAILED without losing Message.
    failed = await plan(h, None, "missing")
    assert await h.image_worker.run_once()
    assert (await query(h, "SELECT status FROM app.file_objects WHERE id=:id", id=failed["id"]))[0][
        "status"
    ] == "FAILED"
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await grant(h, failed)


async def test_revoke_denies_new_grant_existing_bearer_expires_at_real_s3(images):
    h = images
    row = await plan(h, image_bytes())
    assert await h.image_worker.run_once()
    signed = await grant(h, row)
    await query(
        h,
        "UPDATE platform.workspace_memberships SET status='REVOKED' WHERE workspace_id=:ws AND user_account_id=:actor RETURNING status",
        ws=A,
        actor=UA,
    )
    with pytest.raises((MessagingError, TenancyError)):
        await grant(h, row)
    assert (await request("GET", signed.url)).status_code == 200
    # Actual server expiry, no changed client/server clock and no fake signature.
    await asyncio.sleep(max(0, (signed.expires_at - datetime.now(UTC)).total_seconds()) + 2)
    assert (await request("GET", signed.url)).status_code == 403


async def test_s3_checksum_conditional_put_and_runtime_privilege_boundaries(images):
    h = images
    content = image_bytes()
    await plan(h, content)
    claim = await h.kernel.claim_job("checksum-test")
    manifest = await h.transfer.validator.validate(content)
    permit = await h.files.prepare_upload(claim, manifest)
    # Server must reject a checksum mismatch; metadata/ETag are not evidence.
    with pytest.raises(ClientError) as bad:
        await asyncio.to_thread(
            h.storage._client.put_object,
            Bucket=h.storage._settings.bucket,
            Key=permit.storage_key,
            Body=content,
            ChecksumSHA256=base64.b64encode(b"x" * 32).decode(),
        )
    # This pinned MinIO release reports the SHA-256 mismatch with the S3
    # checksum-specific code. Still require an actual server-side rejection
    # and prove that the invalid write left no object below.
    assert bad.value.response["Error"]["Code"] == "XAmzContentChecksumMismatch"
    assert bad.value.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    with pytest.raises(MessagingError, match="NOT_FOUND"):
        await h.storage.head(permit.storage_key)
    await h.storage.put(permit, content)
    with pytest.raises(MessagingError, match="DEPENDENCY_UNAVAILABLE"):
        await h.storage.put(permit, content)
    for operation in (
        lambda: h.storage._client.list_objects_v2(Bucket="asm-other-tenant-bucket"),
        lambda: h.storage._client.create_bucket(Bucket="asm-forbidden-bucket"),
        lambda: h.storage._client.put_object(
            Bucket=h.storage._settings.bucket, Key="outside-prefix", Body=b"x"
        ),
    ):
        with pytest.raises(ClientError) as denied:
            await asyncio.to_thread(operation)
        assert denied.value.response["Error"]["Code"] == "AccessDenied"
    await h.kernel.retry(claim, Code.DEPENDENCY_UNAVAILABLE)
