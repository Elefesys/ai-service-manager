"""Owned synthetic portfolio fixture; actual PG with explicit controlled/S3 bytes."""
# ruff: noqa: E402 -- Direct finite CLI needs the project root before fixture imports.

import asyncio
import base64
import hashlib
import io
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

if __name__ == "__main__":
    # Python file execution places only /app/tests on sys.path. Keep the
    # development image unchanged and resolve its owned scripts package before
    # loading the shared fixtures. The CLI's exact TEST target guard still runs
    # before constructing any database or S3 client.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest_asyncio
from asm.ai.contracts import PortfolioDeliveryGatewayConfig
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_settings import PortfolioDeliveryRuntimeSettings
from asm.files.config import StorageSettings
from asm.files.storage import S3ObjectStorage
from asm.foundation import create_worker
from asm.messaging.database import worker_active
from m5_knowledge_search_fixtures import db as db
from m5_knowledge_search_fixtures import publication
from m5_knowledge_search_fixtures import search_pg as search_pg
from m5_knowledge_search_fixtures import seeded as seeded
from m5_portfolio_fixtures import call, command
from PIL import Image
from test_m2_1_postgres import query
from test_m3_1_native_context_postgres import scalar
from test_m4_agent import config
from test_m4_delivery_postgres import run_turn, source_turn
from test_m5_portfolio_runtime_postgres import bridge, publish_portfolio
from test_m5_portfolio_runtime_postgres import portfolio_runtime_pg as portfolio_runtime_pg
from test_tenancy_postgres import BA, A

CAPTION = "Подтверждённая тестовая работа мастера 🎨"


class PhotoBytes:
    def __init__(self, h, actual=False):
        self.h = h
        self.storage = S3ObjectStorage(StorageSettings()) if actual else None
        self.values = {}
        self.keys = set()
        self.gets = 0
        self.after_get = None
        self.corrupt = False

    async def seed(self, key, data):
        # TEST-owned original source fixture. Production reads still require the
        # exact DB-issued delivery permit; this setup grants no read/send permit.
        self.keys.add(key)
        if self.storage is None:
            self.values[key] = data
        else:
            await asyncio.to_thread(
                self.storage._client.put_object,
                Bucket=self.storage._settings.bucket,
                Key=key,
                Body=data,
                ContentLength=len(data),
                ContentType="image/png",
                ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode(),
                IfNoneMatch="*",
            )

    async def get(self, key):
        assert not worker_active()
        # If a DB publication lock crossed S3 I/O this independent transaction
        # would fail, rather than a mocked assertion declaring the lock absent.
        async with self.h.migrator.begin() as c:
            from sqlalchemy import text

            await c.execute(text("SET LOCAL lock_timeout='1s'"))
            await c.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,2018))"),
                {"scope": f"{A}:{BA}|CONFIGURATION_V1"},
            )
        self.gets += 1
        data = await self.storage.get(key) if self.storage else self.values[key]
        if self.after_get is not None:
            await self.after_get()
        return data + b"corrupt" if self.corrupt else data

    async def close(self):
        if self.storage:
            for key in self.keys:
                await asyncio.to_thread(
                    self.storage._client.delete_object,
                    Bucket=self.storage._settings.bucket,
                    Key=key,
                )
            await self.storage.close()


class PhotoModel(FakeAdapter):
    def __init__(self, route, *, photo=True, direct=False, mutate=None):
        super().__init__(route, ("reply",) if direct else ("tools", "reply"))
        self.photo = photo
        self.mutate = mutate

    async def complete(self, request):
        result = await super().complete(request)
        if result.kind == "OUTPUT" and self.photo:
            supplied = next(
                json.loads(m.text)
                for m in request.request.messages
                if m.role == "context"
                and json.loads(m.text).get("revision") == "business_knowledge_v3"
            )
            refs = supplied["delivery"]["references"]
            assert refs, "A source fixture must be eligible before a photo is proposed"
            value = {"kind": "portfolio_photo", "selection": dict(refs[0]), "caption": CAPTION}
            if self.mutate is not None:
                self.mutate(value)
            result = result.model_copy(
                update={"output_json": json.dumps(value, ensure_ascii=False)}
            )
        return result


@pytest_asyncio.fixture
async def photo_pg(portfolio_runtime_pg, request):
    h = portfolio_runtime_pg
    h.photo_store = PhotoBytes(h, actual=getattr(request, "param", "controlled") == "s3")
    h.photo_workers = []
    try:
        _, _, h.photo_embeddings = await publication(h, ["Synthetic flower preparation"])
        h.photo_state = await publish_portfolio(h, h.photo_embeddings)
        source = (
            await query(
                h,
                "SELECT v.* FROM platform.portfolio_asset_versions v WHERE v.workspace_id=:ws AND v.business_id=:b AND v.state='READY' ORDER BY v.id DESC LIMIT 1",
                ws=A,
                b=BA,
            )
        )[0]
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), (50, 80, 110)).save(buffer, "PNG")
        h.photo_content = buffer.getvalue()
        assert hashlib.sha256(h.photo_content).hexdigest() == source["sha256"]
        h.photo_source = source
        await h.photo_store.seed(source["storage_key"], h.photo_content)
        yield h
    finally:
        for worker in h.photo_workers:
            await worker.portfolio_delivery.close()
        await h.photo_store.close()


async def application(
    h,
    *,
    photo=True,
    direct=False,
    mutate=None,
    native=True,
    telegram=False,
    db_hook=None,
    telegram_client=None,
):
    cid, source, scope = await source_turn(
        h, native=native, telegram=telegram, message_text="Покажи flower из портфолио"
    )
    if telegram:
        from test_m4_delivery_postgres import refresh_synthetic_observation

        await refresh_synthetic_observation(h, cid)
    admission = await call(
        bridge(h),
        "portfolio_session_admit",
        [
            BA,
            cid,
            {
                "profile_id": "SYNTHETIC_PORTFOLIO_PHOTO_V1",
                "execution": "CONTROLLED",
                "eligibility": "EVAL_ONLY",
                "max_calls": 4,
                "max_cost": "10",
                "duration_seconds": 900,
            },
        ],
    )
    cfg = PortfolioDeliveryGatewayConfig.model_validate(
        config(
            duration_seconds=120,
            cost_budget=Decimal(5),
            input_bytes=24576,
            output_tokens=512,
            total_tokens=66560,
        ).model_dump()
        | {"prompt_revision": "conversation_v6", "schema_revision": "conversation_result_v2"}
    )
    model = PhotoModel(cfg.route, photo=photo, direct=direct, mutate=mutate)
    settings = PortfolioDeliveryRuntimeSettings(
        session_id=UUID(admission["session_id"]),
        workspace_id=A,
        business_id=BA,
        client_id=await scalar(h, "SELECT client_id FROM app.conversations WHERE id=:id", id=cid),
        conversation_id=cid,
        data_profile="SYNTHETIC_PORTFOLIO_PHOTO_V1",
        expires_at=datetime.fromisoformat(admission["expires_at"]),
        max_calls=4,
        max_cost=Decimal(10),
        config=cfg,
    )
    worker = create_worker(
        h.kernel,
        h.adapter,
        environment="TEST",
        portfolio_delivery_settings=settings,
        portfolio_storage=h.photo_store,
        model=lambda: model,
        ai_embeddings=h.photo_embeddings.client,
        ai_telegram=telegram_client,
    )
    h.photo_workers.append(worker)
    if db_hook is not None:
        db_hook(worker.ai.database)
    claim, delivery = await run_turn(h, worker, source)
    return cid, worker, model, claim, delivery, scope


async def revoke(h):
    state = await call(bridge(h), "portfolio_owner_read", [BA])
    item = state["items"][0]
    return await command(
        bridge(h),
        "PORTFOLIO_REVOKE",
        {
            "item_id": item["item_id"],
            "expected_item_version": item["version"],
            "expected_activation_version": state["activation_version"],
        },
    )


# Finite browser TEST entrypoint. Existing PG fixtures above retain their own
# lifecycle. This path has runtime credentials only and never inserts canonical
# Message/receipt/Outbox/Job rows. Browser owner HTTP uploads supply the source.
async def browser_action(operation, viewport, scenario):
    import sys
    from contextlib import asynccontextmanager
    from dataclasses import replace
    from datetime import UTC
    from pathlib import Path
    from uuid import uuid4

    from asm.messaging.adapter import ControlledAdapter
    from asm.messaging.http_service import OwnerAPIRepository
    from asm.messaging.models import OutcomeKind
    from asm.messaging.results import AIJobClaim
    from asm.messaging.worker import Worker
    from asm.portfolio.repository import PortfolioRepository
    from asm.tenancy import AuthenticatedAccount, MembershipRole, TenantDatabase
    from m5_configuration_fixtures import configuration_bundle
    from m5_knowledge_search_fixtures import ControlledEmbeddings
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from m2_4_browser_worker import (
        KnowledgeBrowserKernel,
        ProvisioningError,
        bot,
        event,
        guard,
        target,
    )

    if (
        operation not in {"publish", "prepare", "answer"}
        or viewport not in {"desktop", "narrow"}
        or scenario not in {"sent", "unknown"}
    ):
        raise ProvisioningError("Finite portfolio browser action required")
    # Validate before constructing a database or S3 client. No arbitrary scope,
    # model payload, storage key, URL or credentials can be passed to this CLI.
    url, storage_settings = target()
    engine = create_async_engine(
        url,
        hide_parameters=True,
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 3},
    )
    storage = None
    worker = None
    preset = "portfolio_photo"
    try:
        async with asyncio.timeout(100):
            await guard(engine)
            kernel = KnowledgeBrowserKernel(engine, environment="TEST")

            async def outside_transaction(_):
                if engine.pool.checkedout() != 0:
                    raise ProvisioningError("Portfolio browser I/O holds a DB connection")

            class Transport(ControlledAdapter):
                async def send_photo(self, permit, content):
                    if permit.bot_identity != bot(preset) or permit.text != CAPTION:
                        raise ProvisioningError("Finite portfolio browser photo required")
                    await outside_transaction("photo")
                    return await super().send_photo(permit, content)

            transport = Transport(
                environment="TEST",
                outcome=OutcomeKind.SUCCESS if scenario == "sent" else OutcomeKind.UNKNOWN,
                barrier=outside_transaction,
            )
            # The trusted route fixes Workspace. The fixed synthetic login is
            # resolved through auth capability; no claimed account ID is trusted.
            async with engine.connect() as c:
                bootstrap_cutoff = (await c.execute(text("SELECT clock_timestamp()"))).scalar_one()
            seed = event(preset, "main")
            ingress = await kernel.ingest_event(transport.source(seed.bot_identity), seed, uuid4())
            if ingress.code == "ACCEPTED":
                bootstrap = Worker(kernel, transport)
                for _ in range(1024):
                    claim = await kernel.claim_knowledge(bootstrap_cutoff)
                    if claim is None:
                        await asyncio.sleep(0.025)
                        continue
                    if claim.workspace_id != ingress.workspace_id or claim.kind not in {
                        "PROCESS_INBOX",
                        "PROCESS_TURN",
                    }:
                        raise ProvisioningError("Exclusive portfolio browser bootstrap required")
                    await bootstrap.execute(claim)
                    if claim.kind == "PROCESS_TURN" and claim.step == "TEST_CONSUME":
                        break
                else:
                    raise ProvisioningError("Bounded canonical browser bootstrap required")
            async with engine.connect() as c:
                actor_id = (
                    await c.execute(
                        text("SELECT user_account_id FROM platform.auth_password_lookup(:login)"),
                        {"login": "browser.m24-portfolio_photo"},
                    )
                ).scalar_one()
            tenancy = TenantDatabase(engine)

            @asynccontextmanager
            async def owner():
                async with tenancy.transaction(
                    AuthenticatedAccount(actor_id), ingress.workspace_id, uuid4()
                ) as unit:
                    if await unit.billing_membership_role() != MembershipRole.OWNER:
                        raise ProvisioningError("Current synthetic portfolio OWNER required")
                    yield unit

            async with owner() as unit:
                businesses = await unit.list_businesses()
                if len(businesses) != 1:
                    raise ProvisioningError("One synthetic portfolio Business required")
                business = businesses[0]["id"]
            embeddings = ControlledEmbeddings()
            if operation == "publish":
                async with owner() as unit:
                    repository = PortfolioRepository(unit)
                    state = await repository.state(business)
                    items = [i for i in state.items if i.state == "CONFIRMED" and i.show_permission]
                    if len(items) != 1:
                        raise ProvisioningError("One owner-confirmed HTTP source required")
                    draft = await unit.configuration_owner_read(business)
                    # Explicit fictional configuration remains confined to this
                    # disposable identity; API default AI modes stay DISABLED.
                    await unit.configuration_command(
                        business,
                        "EDIT",
                        str(uuid4()),
                        {
                            "expected_draft_version": draft["draft_version"],
                            "bundle": configuration_bundle(),
                        },
                    )
                    created = await repository.command(
                        business,
                        "PORTFOLIO_BUILD_CREATE",
                        str(uuid4()),
                        {
                            "schema_version": 1,
                            "expected_items_hash": state.items_hash,
                            "revision_ids": [items[0].head.revision_id],
                        },
                    )
                    build_id = UUID(created.result.build_id)
                async with owner() as unit:
                    repository = PortfolioRepository(unit)
                    session_id = await repository.session(business, None)
                    reservation = await repository.build_reserve(business, build_id, session_id)
                await outside_transaction("embedding")
                outcome = await embeddings.client.complete(
                    reservation.wire,
                    deadline=reservation.deadline,
                    wire_sha256=reservation.wire_sha256,
                )
                recorded = await kernel.complete_embedding(
                    reservation.call_id, reservation.ticket, outcome
                )
                if recorded["state"] != "SUCCESS":
                    raise ProvisioningError("Controlled portfolio build accounting required")
                async with owner() as unit:
                    await PortfolioRepository(unit).build_apply(
                        business, reservation.call_id, reservation.ticket, outcome["vectors"]
                    )
                async with owner() as unit:
                    repository = PortfolioRepository(unit)
                    state = await repository.state(business)
                    build = next(b for b in state.builds if b.build_id == str(build_id))
                    draft = await unit.configuration_owner_read(business)
                    if state.active_knowledge_build_id is not None:
                        raise ProvisioningError("Fresh portfolio-only browser publication required")
                    await repository.command(
                        business,
                        "PORTFOLIO_PUBLISH",
                        str(uuid4()),
                        {
                            "schema_version": 1,
                            "expected_draft_version": draft["draft_version"],
                            "expected_activation_version": state.activation_version,
                            "knowledge_build_id": None,
                            "expected_knowledge_build_version": None,
                            "portfolio_build_id": str(build_id),
                            "expected_portfolio_build_version": build.version,
                        },
                    )
                async with owner() as unit:
                    main = (
                        await unit._execute(
                            "SELECT id FROM app.conversations WHERE workspace_id=:ws "
                            "AND provider_chat_id=:chat",
                            {"ws": ingress.workspace_id, "chat": f"m24-{preset}-main"},
                        )
                    ).scalar_one()
                return {
                    "published": True,
                    "embedding_calls": len(embeddings.requests),
                    "main_conversation_id": str(main),
                }

            chat = f"photo-{viewport}-{scenario}"
            async with engine.connect() as c:
                cutoff = (await c.execute(text("SELECT clock_timestamp()"))).scalar_one()
            value = replace(
                event(preset, f"{chat}-{operation}", conversation=chat),
                occurred_at=datetime.now(UTC),
                text="Покажи flower из портфолио",
            )
            incoming = await kernel.ingest_event(
                transport.source(value.bot_identity), value, uuid4()
            )
            if incoming.code != "ACCEPTED" or incoming.workspace_id != ingress.workspace_id:
                raise ProvisioningError("Fresh finite portfolio browser question required")
            kernel.question_inbox_id = incoming.inbox_id
            observer = Worker(kernel, transport)
            ai_claim = None
            model = None
            if operation == "answer":
                async with owner() as unit:
                    rows = await unit._execute(
                        "SELECT id,client_id FROM app.conversations "
                        "WHERE workspace_id=:ws AND provider_chat_id=:chat",
                        {"ws": ingress.workspace_id, "chat": f"m24-{preset}-{chat}"},
                    )
                    conversation, client = rows.one()
                    admission = await unit._portfolio_execute(
                        "SELECT platform.portfolio_session_admit(:business,:conversation,CAST(:body AS jsonb))",
                        {
                            "business": business,
                            "conversation": conversation,
                            "body": json.dumps(
                                {
                                    "profile_id": "SYNTHETIC_PORTFOLIO_PHOTO_V1",
                                    "execution": "CONTROLLED",
                                    "eligibility": "EVAL_ONLY",
                                    "max_calls": 4,
                                    "max_cost": "10",
                                    "duration_seconds": 120,
                                }
                            ),
                        },
                    )
                cfg = PortfolioDeliveryGatewayConfig.model_validate(
                    config(
                        duration_seconds=120,
                        cost_budget=Decimal(5),
                        input_bytes=24576,
                        output_tokens=512,
                        total_tokens=66560,
                    ).model_dump()
                    | {
                        "prompt_revision": "conversation_v6",
                        "schema_revision": "conversation_result_v2",
                    }
                )
                model = PhotoModel(cfg.route)
                settings = PortfolioDeliveryRuntimeSettings(
                    session_id=UUID(admission["session_id"]),
                    workspace_id=ingress.workspace_id,
                    business_id=business,
                    client_id=client,
                    conversation_id=conversation,
                    data_profile="SYNTHETIC_PORTFOLIO_PHOTO_V1",
                    expires_at=datetime.fromisoformat(admission["expires_at"]),
                    max_calls=4,
                    max_cost=Decimal(10),
                    config=cfg,
                )
                storage = S3ObjectStorage(storage_settings)
                worker = create_worker(
                    kernel,
                    transport,
                    environment="TEST",
                    portfolio_delivery_settings=settings,
                    portfolio_storage=storage,
                    model=lambda: model,
                    ai_embeddings=embeddings.client,
                )

            for _ in range(2048):
                claim = await kernel.claim_knowledge(
                    cutoff, ai=operation == "answer" and ai_claim is None
                )
                if claim is None:
                    claim = await kernel.claim_knowledge(cutoff)
                if claim is None:
                    await asyncio.sleep(0.025)
                    continue
                if claim.workspace_id != ingress.workspace_id or claim.kind not in {
                    "PROCESS_INBOX",
                    "PROCESS_TURN",
                    "SEND_AI_PHOTO",
                }:
                    raise ProvisioningError("Exclusive portfolio browser work required")
                if isinstance(claim, AIJobClaim):
                    if ai_claim is not None:
                        raise ProvisioningError("One portfolio browser model job required")
                    ai_claim = claim
                selected = (
                    observer
                    if worker is None
                    or (claim.kind == "PROCESS_TURN" and claim.step == "TEST_CONSUME")
                    else worker
                )
                await selected.execute(claim)
                if (
                    operation == "prepare"
                    and claim.kind == "PROCESS_TURN"
                    and claim.step == "TEST_CONSUME"
                ):
                    async with owner() as unit:
                        rows = await unit._execute(
                            "SELECT id,client_id FROM app.conversations "
                            "WHERE workspace_id=:ws AND provider_chat_id=:chat",
                            {"ws": ingress.workspace_id, "chat": f"m24-{preset}-{chat}"},
                        )
                        conversation, client = rows.one()
                    return {"conversation_id": str(conversation), "client_id": str(client)}
                if kernel.finalized is not None:
                    if model is None or len(model.requests) != 2 or ai_claim is None:
                        raise ProvisioningError("Fresh READ and one bounded model action required")
                    async with owner() as unit:
                        messages = (
                            await OwnerAPIRepository(unit).messages(conversation, 25, None)
                        ).items
                        photos = [m for m in messages if m.content_type == "PORTFOLIO_PHOTO"]
                    if len(photos) != 1 or photos[0].delivery.status != scenario.upper():
                        raise ProvisioningError("Canonical portfolio browser delivery required")
                    if transport.calls != 1 or transport.effects != 1:
                        raise ProvisioningError("One controlled photo effect required")
                    return {
                        "message_id": photos[0].message_id,
                        "model_calls": len(model.requests),
                        "calls": transport.calls,
                        "effects": transport.effects,
                        "status": photos[0].delivery.status,
                    }
            raise ProvisioningError("Bounded portfolio browser work exhausted")
    finally:
        if worker is not None:
            await worker.portfolio_delivery.close()
        if storage is not None:
            await storage.close()
        await engine.dispose()


def browser_main():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from provision_local_auth import PrivateArgumentParser

    parser = PrivateArgumentParser()
    parser.add_argument("--action", required=True, choices=("publish", "prepare", "answer"))
    parser.add_argument("--viewport", required=True, choices=("desktop", "narrow"))
    parser.add_argument("--scenario", required=True, choices=("sent", "unknown"))
    try:
        args = parser.parse_args()
        result = asyncio.run(browser_action(args.action, args.viewport, args.scenario))
        print(json.dumps(result, sort_keys=True))
    except Exception:
        # CLI errors never echo passwords, private keys, DSNs, model payloads or
        # signed URLs. Detailed canonical assertions belong to PG test fixtures.
        print("M5_PORTFOLIO_BROWSER_FAILED", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    browser_main()
