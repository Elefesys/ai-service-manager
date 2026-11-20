"""Finite TEST browser input through real ingest/claim/owner/runtime capabilities.

Only the existing CONTROLLED knowledge fixture, two named viewports and fixed
text events are supported. No arbitrary messages, SQL state writes, paid
provider, private photo read or real channel adapter is constructed.
"""

import asyncio
import json
import os
import sys
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from asm.ai.contracts import IntakeGatewayConfig
from asm.ai.fake import FakeAdapter
from asm.ai.runtime_contracts import IntakeRuntimeReceipt
from asm.ai.runtime_settings import IntakeRuntimeSettings
from asm.configuration.models import ActiveProjection
from asm.foundation import create_worker, native_schema_readiness
from asm.intake.templates import template_revision
from asm.messaging.adapter import ControlledAdapter
from asm.messaging.http_service import OwnerAPIRepository
from asm.messaging.models import OutcomeKind
from asm.messaging.results import AIJobClaim
from asm.messaging.worker import Worker
from asm.tenancy import AuthenticatedAccount, TenantDatabase
from m2_4_browser_fixture import bot
from m2_4_browser_worker import KnowledgeBrowserKernel, event, guard, knowledge_config
from provision_local_auth import PrivateArgumentParser, ProvisioningError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

INPUTS = {
    "seed": "Synthetic intake seed",
    "collect": "Synthetic intake flower forearm",
    "collect-sized": "Synthetic intake flower forearm 8 cm",
    "complex": "Synthetic intake cover up",
    "ambiguous": "Synthetic intake flower and swallow, shared size unclear",
    "second": "Synthetic intake separate swallow shoulder",
    "late-size": "Synthetic intake for the first work, flower size 12 cm",
    "late-cover-up": "Synthetic intake for the first flower, size 12 cm, covering an old tattoo",
    "complex-message": "I forgot to say, this flower will cover an old tattoo",
    "assess-first": "Synthetic assessment flower forearm 8 cm linework",
    "assess-second": "Synthetic assessment separate swallow shoulder linework",
    "price-first": "Synthetic price flower forearm 20 mm linework",
    "price-second": "Synthetic price separate swallow shoulder linework",
    "price-size": "The swallow will be 21 mm",
    "price-oversize": "The swallow will be 100,1 cm",
}
VALUES = {
    "collect": (("idea", "flower"), ("placement", "forearm")),
    "collect-sized": (("idea", "flower"), ("placement", "forearm"), ("approximate_size", "8 cm")),
    "second": (("idea", "swallow"), ("placement", "shoulder")),
    "late-size": (("approximate_size", "12 cm"),),
    "late-cover-up": (("approximate_size", "12 cm"),),
    "assess-first": (
        ("idea", "flower"),
        ("placement", "forearm"),
        ("approximate_size", "8 cm"),
        ("style", "linework"),
    ),
    "assess-second": (("idea", "swallow"), ("placement", "shoulder"), ("style", "linework")),
    "price-first": (
        ("idea", "flower"),
        ("placement", "forearm"),
        ("approximate_size", "20 mm"),
        ("style", "linework"),
    ),
    "price-second": (("idea", "swallow"), ("placement", "shoulder"), ("style", "linework")),
    "price-size": (("approximate_size", "21 mm"),),
    "price-oversize": (("approximate_size", "100,1 cm"),),
}
CATEGORIES = {
    "complex": "COVER_UP",
    "late-cover-up": "COVER_UP",
    "complex-message": "COVER_UP",
    "ambiguous": "AMBIGUOUS",
}


class DescriptionOnlyStorage:
    async def get(self, key):
        raise ProvisioningError("This finite journey cannot read private image bytes")

    async def close(self):
        pass


class IntakeModel(FakeAdapter):
    def __init__(self, route, service, operation, barrier):
        super().__init__(route, ("reply",))
        self.service, self.operation, self.barrier = service, operation, barrier

    async def complete(self, request):
        await self.barrier()
        response = await super().complete(request)
        contexts = [json.loads(m.text) for m in request.request.messages if m.role == "context"]
        current = next(c for c in contexts if c.get("revision") == "conversation_intake_v1")
        source = current["sources"][-1]
        if source["text"] != INPUTS[self.operation]:
            raise ProvisioningError("Current finite source required")
        facts = [
            dict(
                field=field,
                value=value,
                status="client-stated",
                source=dict(
                    message_id=source["message_id"],
                    source_version=source["source_version"],
                    quote=value,
                    analysis_id=None,
                    analysis_sha256=None,
                ),
                explicit_correction=self.operation in {"late-cover-up", "price-oversize"},
            )
            for field, value in VALUES.get(self.operation, ())
        ]
        result = dict(
            kind="reply",
            text="Untrusted synthetic wording",
            reason=None,
            intake=dict(
                service_id=self.service,
                category=CATEGORIES.get(self.operation, "NEW_TATTOO"),
                switch_request=self.operation in {"second", "assess-second", "price-second"},
                facts=facts,
            ),
        )
        return response.model_copy(update={"output_json": json.dumps(result)})


def target():
    url = make_url(os.environ.get("ASM_DATABASE_URL", ""))
    if (
        os.environ.get("ASM_ENVIRONMENT") != "TEST"
        or url.drivername != "postgresql+psycopg"
        or url.username != "asm_runtime"
        or url.database != "asm_test"
        or url.host not in {"postgres", "127.0.0.1", "localhost"}
        or url.query
        or any(
            os.environ.get(k)
            for k in (
                "ASM_MIGRATION_DATABASE_URL",
                "ASM_ADMIN_DATABASE_URL",
                "ASM_NATIVE_TEST_ADMIN_URL",
                "PGPASSWORD",
                "PG_ADMIN_PASSWORD",
                "PG_MIGRATION_PASSWORD",
            )
        )
    ):
        raise ProvisioningError("Isolated runtime-only TEST target required")
    return url


async def run(args):
    url = target()
    actor, workspace, business = (
        UUID(value) for value in (args.actor, args.workspace, args.business)
    )
    engine = create_async_engine(
        url, hide_parameters=True, pool_size=2, max_overflow=0, connect_args={"connect_timeout": 3}
    )
    worker = None
    try:
        await guard(engine)
        async with engine.connect() as c:
            await native_schema_readiness(c)
        tenancy = TenantDatabase(engine)
        kernel = KnowledgeBrowserKernel(engine, environment="TEST")

        async def barrier():
            if engine.pool.checkedout() != 0:
                raise ProvisioningError("External TEST work holds a DB connection")

        adapter = ControlledAdapter(environment="TEST", outcome=OutcomeKind.SUCCESS)
        observer = Worker(kernel, adapter)
        cid = UUID(args.conversation) if args.conversation else None
        if args.operation != "seed" and cid is None:
            raise ProvisioningError("Seeded conversation required")
        service = None
        async with tenancy.transaction(AuthenticatedAccount(actor), workspace, uuid4()) as unit:
            active = ActiveProjection.model_validate(await unit.configuration_active_read(business))
            if args.operation != "seed":
                if not active.bundle:
                    raise ProvisioningError("Explicit owner publication required")
                services = [s.id for s in active.bundle.services if template_revision(s)]
                if len(services) != 1:
                    raise ProvisioningError("One explicitly published template required")
                service = services[0]
                admission = await unit._portfolio_execute(
                    "SELECT platform.portfolio_session_admit(:business,:conversation,CAST(:body AS jsonb))",
                    dict(
                        business=business,
                        conversation=cid,
                        body=json.dumps(
                            dict(
                                profile_id="SYNTHETIC_INTAKE_V1",
                                execution="CONTROLLED",
                                eligibility="EVAL_ONLY",
                                max_calls=2,
                                max_cost="1",
                                duration_seconds=120,
                            )
                        ),
                    ),
                )
        if cid is not None:
            cfg = IntakeGatewayConfig.model_validate(
                knowledge_config().model_dump()
                | dict(prompt_revision="conversation_v7", schema_revision="conversation_result_v3")
            )
            model = IntakeModel(cfg.route, service, args.operation, barrier)
            settings = IntakeRuntimeSettings(
                session_id=UUID(admission["session_id"]),
                workspace_id=workspace,
                business_id=business,
                client_id=UUID(admission["client_id"]),
                conversation_id=cid,
                data_profile="SYNTHETIC_INTAKE_V1",
                expires_at=datetime.fromisoformat(admission["expires_at"]),
                max_calls=2,
                max_cost=Decimal(1),
                config=cfg,
            )
            worker = create_worker(
                kernel,
                adapter,
                environment="TEST",
                intake_settings=settings,
                model=lambda: model,
                portfolio_storage=DescriptionOnlyStorage(),
            )
        async with engine.connect() as c:
            cutoff = (await c.execute(text("SELECT clock_timestamp()"))).scalar_one()
        scenario = f"{args.journey}-{args.variant}"
        value = replace(
            event(
                "knowledge",
                f"{scenario}-{args.operation}",
                conversation=scenario,
            ),
            text=INPUTS[args.operation],
        )
        incoming = await kernel.ingest_event(adapter.source(bot("knowledge")), value, uuid4())
        if incoming.code != "ACCEPTED" or incoming.workspace_id != workspace:
            raise ProvisioningError("Fresh canonical finite input required; no retries/resend")
        kernel.question_inbox_id = incoming.inbox_id
        owner_handoff = CATEGORIES.get(args.operation) == "COVER_UP"
        seen_inbox, seen_observer, ai_claim = False, False, None
        async with asyncio.timeout(25):
            for _ in range(512):
                claim = await kernel.claim_knowledge(cutoff, ai=worker is not None)
                if claim is None:
                    claim = await kernel.claim_knowledge(cutoff)
                if claim is None:
                    await asyncio.sleep(0.025)
                    continue
                if claim.workspace_id != workspace or claim.kind not in {
                    "PROCESS_INBOX",
                    "PROCESS_TURN",
                    "SEND_AI_TEXT",
                }:
                    raise ProvisioningError("Exclusive finite text-only claim required")
                if not seen_inbox:
                    if claim.kind != "PROCESS_INBOX" or claim.job_id != incoming.job_id:
                        raise ProvisioningError("Original input must be first")
                    connection_id = claim.connection_id
                    seen_inbox = True
                elif claim.connection_id != connection_id or claim.kind == "PROCESS_INBOX":
                    raise ProvisioningError("Unrelated fixture job refused")
                if isinstance(claim, AIJobClaim):
                    if ai_claim is not None or worker is None:
                        raise ProvisioningError("One finite model job required")
                    ai_claim = claim
                selected = (
                    observer
                    if worker is None or getattr(claim, "step", None) == "TEST_CONSUME"
                    else worker
                )
                await selected.execute(claim)
                if getattr(claim, "step", None) == "TEST_CONSUME":
                    seen_observer = True
                done = (
                    seen_observer
                    if args.operation == "seed"
                    else seen_observer
                    and ai_claim is not None
                    and (owner_handoff or kernel.finalized is not None)
                )
                if not done:
                    continue
                async with tenancy.transaction(
                    AuthenticatedAccount(actor), workspace, uuid4()
                ) as unit:
                    conversations = await OwnerAPIRepository(unit).conversations(100, None)
                    found = []
                    for conversation in conversations.items:
                        if conversation.business_id != str(business):
                            continue
                        messages = await OwnerAPIRepository(unit).messages(
                            UUID(conversation.conversation_id), 100, None
                        )
                        if any(
                            m.message_id == str(kernel.question_message_id) for m in messages.items
                        ):
                            found.append(conversation)
                    if len(found) != 1 or cid is not None and found[0].conversation_id != str(cid):
                        raise ProvisioningError("Canonical owner-scoped conversation required")
                    cid = UUID(found[0].conversation_id)
                    summary = await unit.intake_owner(business, cid, "READ", "", {})
                if args.operation != "seed":
                    receipt = await worker.ai.database.replay(ai_claim, cfg)
                    if (
                        not isinstance(receipt, IntakeRuntimeReceipt)
                        or len(model.requests) != 1
                        or receipt.result.kind != ("handoff" if owner_handoff else "reply")
                    ):
                        raise ProvisioningError("One durable bounded v7 result required")
                expected = 0 if owner_handoff or args.operation == "seed" else 1
                if adapter.calls != expected or adapter.effects != expected:
                    raise ProvisioningError("Unexpected finite external effect count")
                return dict(
                    conversation_id=str(cid),
                    message_id=str(kernel.question_message_id),
                    model_calls=0 if args.operation == "seed" else 1,
                    calls=adapter.calls,
                    effects=adapter.effects,
                    status=summary["status"],
                )
        raise ProvisioningError("Finite intake browser work did not finish")
    finally:
        if worker is not None:
            await worker.portfolio_delivery.close()
        await engine.dispose()


def main():
    try:
        parser = PrivateArgumentParser()
        parser.add_argument("--operation", choices=tuple(INPUTS), required=True)
        parser.add_argument("--variant", choices=("desktop", "narrow"), required=True)
        parser.add_argument(
            "--journey",
            choices=(
                "intake",
                "request",
                "request-deferred",
                "assessment",
                "assessment-complex",
                "assessment-complex-source",
                "pricing",
            ),
            default="intake",
        )
        for name in ("actor", "workspace", "business"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--conversation")
        print(json.dumps(asyncio.run(run(parser.parse_args())), sort_keys=True))
        return 0
    except Exception as error:
        print("M5_INTAKE_BROWSER_REFUSED:" + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
