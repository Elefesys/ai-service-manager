"""Owner DTO and private transport unit checks; not PG/S3/browser evidence."""

import base64
import hashlib
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from asm.ai.vision import VisionClient
from asm.files.config import StorageSettings
from asm.files.models import (
    CleanupClaim,
    OwnerCleanupPermit,
    OwnerDeletePermit,
    OwnerUploadPermit,
    UploadPermit,
)
from asm.files.storage import S3ObjectStorage
from asm.files.validation import decode_image
from asm.knowledge.embeddings import EmbeddingClient
from asm.portfolio.errors import PortfolioCode, database_error
from asm.portfolio.models import ConfirmItem, InitUpload, OwnerState, SaveItem
from asm.portfolio.service import PortfolioService
from botocore.stub import Stubber
from PIL import Image
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import DBAPIError


def init_body(**changes):
    return {
        "schema_version": 1,
        "asset_id": None,
        "expected_asset_version": "0",
        "origin": "MY_WORK",
        "mime_type": "image/png",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"origin": "CLIENT_REFERENCE"},
        {"origin": "OTHER"},
        {"size_bytes": True},
        {"size_bytes": 10485761},
        {"asset_id": str(uuid4())},
        {"expected_asset_version": "01"},
        {"storage_key": "user-chosen"},
        {"actor_id": str(uuid4())},
        {"schema_version": True},
    ],
)
def test_owner_upload_is_closed_and_cannot_promote_reference_or_choose_authority(changes):
    with pytest.raises(ValidationError):
        InitUpload.model_validate(init_body(**changes))


@pytest.mark.parametrize(
    "change",
    [
        {"confirm_my_work": 1},
        {"show_permission": 1},
        {"show_permission": False},
        {"client_id": str(uuid4())},
        {"origin": "MY_WORK"},
    ],
)
def test_confirmation_is_explicit_for_exact_reviewed_revision(change):
    body = {
        "schema_version": 1,
        "expected_item_version": "1",
        "revision_id": str(uuid4()),
        "canonical_sha256": "a" * 64,
        "confirm_my_work": True,
        "show_permission": True,
        **change,
    }
    with pytest.raises(ValidationError):
        ConfirmItem.model_validate(body)


@pytest.mark.parametrize("text", ["я" * 257, "x\0y", " x", "x\r\ny", "e\u0301"])
def test_canonical_owner_description_has_utf8_and_control_bounds(text):
    body = {
        "schema_version": 1,
        "item_id": None,
        "expected_item_version": "0",
        "asset_id": str(uuid4()),
        "description": text,
        "attributes": {"subject": None, "styles": [], "placement": None},
        "service_id": None,
        "analysis_id": None,
    }
    with pytest.raises(ValidationError):
        SaveItem.model_validate(body)


def test_disabled_is_default_and_only_exact_controlled_clients_are_composable():
    service = PortfolioService(object())
    assert not service.vision.enabled and not service.embeddings.enabled

    class OtherVision(VisionClient):
        pass

    class OtherEmbedding(EmbeddingClient):
        pass

    for kwargs in ({"vision": OtherVision()}, {"embeddings": OtherEmbedding()}):
        with pytest.raises(ValueError):
            PortfolioService(object(), **kwargs)
    with pytest.raises(ValueError, match="CONTROLLED_TEST_PROFILE_REQUIRED"):
        PortfolioService(
            object(),
            environment="LOCAL",
            vision=VisionClient(httpx.MockTransport(lambda r: httpx.Response(200))),
        )


def test_portfolio_public_schema_has_no_private_permits_keys_or_urls():
    raw = OwnerState.model_json_schema()
    for model in [raw, *raw.get("$defs", {}).values()]:
        assert not {"storage_key", "ticket", "claim_token", "url", "session_id"} & set(
            model.get("properties", {})
        )


def test_only_known_sql_error_labels_are_exposed():
    for state, primary, expected in [
        ("P2901", "MY_WORK_REQUIRED", "MY_WORK_REQUIRED"),
        ("P2901", "secret_sql_or_payload", "UNAVAILABLE"),
        ("XX000", "ACCESS_DENIED", "UNAVAILABLE"),
    ]:
        original = Exception("private diagnostic sentinel")
        original.sqlstate = state
        original.diag = SimpleNamespace(message_primary=primary)
        error = database_error(
            DBAPIError("private SQL", {"secret": "synthetic sentinel"}, original, False)
        )
        assert error.code == PortfolioCode(expected)
        assert "sentinel" not in str(error) and "private" not in str(error)


def owner_permit():
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(stream, format="PNG")
    data = stream.getvalue()
    ws, b, a, v, u = (uuid4() for _ in range(5))
    key = f"workspaces/{ws}/portfolio/{a}/versions/{v}/uploads/{u}"
    permit = OwnerUploadPermit(
        workspace_id=ws,
        business_id=b,
        asset_id=a,
        version_id=v,
        upload_id=u,
        ticket=uuid4(),
        storage_key=key,
        manifest=decode_image(data),
        operation_deadline=datetime.now(UTC) + timedelta(seconds=20),
    )
    return permit, data


def storage():
    return S3ObjectStorage(
        StorageSettings(
            environment="TEST",
            endpoint="http://127.0.0.1:1",
            bucket="asm-unit-private",
            access_key=SecretStr("synthetic-unit-access-key"),
            secret_key=SecretStr("synthetic-unit-secret-key"),
        )
    )


async def test_owner_put_uses_new_permit_and_same_exact_private_s3_wire():
    s = storage()
    permit, data = owner_permit()
    checksum = base64.b64encode(hashlib.sha256(data).digest()).decode()
    try:
        with Stubber(s._client) as stub:
            stub.add_response(
                "put_object",
                {"ChecksumSHA256": checksum},
                {
                    "Bucket": "asm-unit-private",
                    "Key": permit.storage_key,
                    "Body": data,
                    "ContentLength": len(data),
                    "ContentType": "image/png",
                    "CacheControl": "private, no-store",
                    "ChecksumSHA256": checksum,
                    "IfNoneMatch": "*",
                },
            )
            await s.put_owner(permit, data)
            stub.assert_no_pending_responses()
    finally:
        await s.close()


async def test_owner_permits_never_replace_inbound_job_and_cleanup_capabilities():
    from asm.messaging.errors import MessagingError

    s = storage()
    permit, data = owner_permit()
    old = UploadPermit(
        intent_id=uuid4(),
        job_id=uuid4(),
        claim_token=uuid4(),
        workspace_id=permit.workspace_id,
        file_id=uuid4(),
        storage_key=permit.storage_key,
        manifest=permit.manifest,
    )
    cleanup = CleanupClaim(
        intent_id=uuid4(),
        claim_token=uuid4(),
        workspace_id=permit.workspace_id,
        file_id=uuid4(),
        storage_key=permit.storage_key,
        lease_until=datetime.now(UTC) + timedelta(seconds=15),
    )
    try:
        for action in (
            s.put(permit, data),
            s.put_owner(old, data),
            s.put_owner(permit.model_copy(update={"storage_key": "foreign/key"}), data),
            s.delete_owner(cleanup),
        ):
            with pytest.raises(MessagingError):
                await action
    finally:
        await s.close()


async def test_owner_cleanup_and_explicit_accepted_delete_have_distinct_permits():
    s = storage()
    upload, _ = owner_permit()
    base = upload.model_dump(exclude={"ticket", "manifest", "operation_deadline"})
    cleanup = OwnerCleanupPermit(
        **base, claim_token=uuid4(), lease_until=datetime.now(UTC) + timedelta(seconds=15)
    )
    accepted = OwnerDeletePermit(
        **base,
        ticket=uuid4(),
        operation="OWNER_ACCEPTED_DELETE",
        purge_deadline=datetime.now(UTC) + timedelta(seconds=15),
    )
    try:
        with Stubber(s._client) as stub:
            for _ in range(2):
                stub.add_response(
                    "delete_object", {}, {"Bucket": "asm-unit-private", "Key": upload.storage_key}
                )
            await s.delete_owner(cleanup)
            await s.delete_owner(accepted)
            stub.assert_no_pending_responses()
    finally:
        await s.close()
