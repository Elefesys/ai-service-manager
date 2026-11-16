"""Actual private S3 + PG/auth/API; controlled provider protocol only.

No skip or fake store fallback: these cases require the configured owned TEST
MinIO service. They are NOT_RUN where that pinned service cannot start.
"""

import io
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import pytest
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.portfolio.storage import PortfolioCleanupSweep
from m5_portfolio_fixtures import portfolio_pg as portfolio_pg
from PIL import Image
from sqlalchemy import text
from test_m5_portfolio_api_postgres import api as api
from test_m5_portfolio_api_postgres import (
    headers,
    init,
    ready,
    route,
    upload_path,
)
from test_m5_portfolio_api_postgres import (
    test_actual_auth_pg_upload_finalize_preview_no_fake_jobs_and_default_zero_provider as _roundtrip,
)
from test_m5_portfolio_api_postgres import (
    test_controlled_vision_actual_pixels_private_accounting_and_replay as _vision,
)
from test_m5_portfolio_api_postgres import (
    test_cors_preflight_put_and_foreign_origin_refusal_then_real_handler as _cors,
)
from test_m5_portfolio_api_postgres import (
    test_delete_receipt_replay_get_and_reload_never_repeat_purge as _purge,
)
from test_m5_portfolio_api_postgres import (
    test_http_owner_review_build_publish_settings_reload_and_empty_withdrawal as _journey,
)
from test_m5_portfolio_api_postgres import (
    test_uncertain_put_is_not_retried_and_only_head_get_recovery_can_finalize as _unknown,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_owner_roundtrip_and_zero_provider_default(api):
    await _roundtrip(api)


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_cors_options_and_real_png_put(api):
    await _cors(api)


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_lost_put_ack_recovers_same_hash_without_second_put(api):
    await _unknown(api)


@pytest.mark.parametrize("api", ["s3_controlled"], indirect=True)
async def test_actual_s3_review_index_joint_publication_and_empty_withdrawal(api):
    await _journey(api)


@pytest.mark.parametrize("api", ["s3_controlled"], indirect=True)
async def test_actual_s3_original_pixels_reach_controlled_vision_only_once(api):
    await _vision(api)


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_fresh_accepted_purge_and_receipt_replay(api):
    await _purge(api)


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_cleanup_rechecks_tombstone_after_late_put(api):
    h = api
    r, data = await init(h)
    abandoned = await h.client.post(
        upload_path(h, r) + "/abandon",
        json={"schema_version": 1, "expected_asset_version": r["asset_version"]},
        headers=headers(h, **{"Idempotency-Key": str(uuid4())}),
    )
    assert abandoned.status_code == 200
    sweep = PortfolioCleanupSweep(MessagingDatabase(h.runtime, environment="TEST"), h.store)
    assert await sweep.run_once()
    async with h.migrator.begin() as c:
        key, state = (
            await c.execute(
                text(
                    "SELECT storage_key,state FROM platform.portfolio_asset_versions WHERE workspace_id=:ws AND id=:id"
                ),
                {"ws": h.ws, "id": UUID(r["version_id"])},
            )
        ).one()
    assert state == "ABANDONED"
    # Explicit TEST late arrival after the first actual S3 DELETE acknowledgement.
    await h.store.storage._io(
        lambda: h.store.storage._client.put_object(
            Bucket=h.store.storage._settings.bucket, Key=key, Body=data, ContentType="image/png"
        )
    )
    assert await h.store.storage.get(key) == data
    async with h.migrator.begin() as c:
        await c.execute(
            text(
                "UPDATE platform.portfolio_asset_versions SET next_check_at=clock_timestamp()-interval '1 second' WHERE workspace_id=:ws AND id=:id"
            ),
            {"ws": h.ws, "id": UUID(r["version_id"])},
        )
    assert await sweep.run_once()
    with pytest.raises(MessagingError) as deleted:
        await h.store.storage.head(key)
    assert deleted.value.code == Code.NOT_FOUND
    assert h.store.calls.count("DELETE") == 2


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_object_is_private_and_foreign_business_refuses_before_get(api):
    h = api
    r, _ = await ready(h)
    async with h.migrator.connect() as c:
        key = (
            await c.execute(
                text(
                    "SELECT storage_key FROM platform.portfolio_asset_versions WHERE workspace_id=:ws AND id=CAST(:id AS uuid)"
                ),
                {"ws": h.ws, "id": r["version_id"]},
            )
        ).scalar_one()
    endpoint = h.store.storage._settings.endpoint
    bucket = h.store.storage._settings.bucket
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as unsigned:
            denied = await unsigned.get(endpoint + "/" + bucket + "/" + quote(key, safe="/"))
    except httpx.HTTPError:
        pytest.fail("PRIVATE_S3_HTTP_UNAVAILABLE", pytrace=False)
    assert denied.status_code in {403, 404}, "Unsigned private original must not be public"
    calls = list(h.store.calls)
    response = await h.client.get(
        route(
            h,
            f"/assets/{r['asset_id']}/versions/{r['version_id']}/preview",
            business=h.other_business,
        )
    )
    assert response.status_code == 404 and h.store.calls == calls
    state = await h.client.get(route(h))
    assert key not in state.text and endpoint not in state.text


@pytest.mark.parametrize("api", ["s3"], indirect=True)
async def test_actual_s3_replaced_object_hash_cannot_be_previewed_as_accepted_version(api):
    h = api
    r, original = await ready(h)
    async with h.migrator.connect() as c:
        key = (
            await c.execute(
                text(
                    "SELECT storage_key FROM platform.portfolio_asset_versions WHERE workspace_id=:ws AND id=CAST(:id AS uuid)"
                ),
                {"ws": h.ws, "id": r["version_id"]},
            )
        ).scalar_one()
    with Image.open(io.BytesIO(original)) as image:
        image.putpixel((0, 0), (0, 0, 0))
        target = io.BytesIO()
        image.save(target, format="PNG")
    replacement = target.getvalue()
    assert replacement != original
    # Deliberate TEST object corruption outside the application capability.
    await h.store.storage._io(
        lambda: h.store.storage._client.put_object(
            Bucket=h.store.storage._settings.bucket,
            Key=key,
            Body=replacement,
            ContentType="image/png",
        )
    )
    response = await h.client.get(
        route(h, f"/assets/{r['asset_id']}/versions/{r['version_id']}/preview")
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "MANIFEST_MISMATCH"
    assert key not in response.text and h.posts == {"vision": 0, "embedding": 0}
