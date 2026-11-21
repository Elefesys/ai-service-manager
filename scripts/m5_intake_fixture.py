"""Finite TEST browser input through real ingest/claim/owner/runtime capabilities.

Only the existing CONTROLLED knowledge fixture, two named viewports, fixed
text events and delivery of a selected synthetic Quote are supported.
"""

import asyncio
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
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
from asm.messaging.database import call
from asm.messaging.errors import MessagingError
from asm.messaging.http_service import OwnerAPIRepository
from asm.messaging.models import OutcomeKind
from asm.messaging.results import (
    AIJobClaim,
    JobClaim,
    QuoteSendJobClaim,
    QuoteSendPermit,
    ScanStep,
    SendPermit,
    parse_claim,
)
from asm.messaging.worker import Worker
from asm.service_requests.quotes import QuoteDeliveryView
from asm.service_requests.repository import ServiceRequestRepository
from asm.tenancy import AuthenticatedAccount, TenantDatabase
from m2_4_browser_fixture import bot, route
from m2_4_browser_worker import KnowledgeBrowserKernel, event, guard, knowledge_config
from provision_local_auth import PrivateArgumentParser, ProvisioningError
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
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
    "quote-second": "Synthetic quote separate swallow shoulder 101 mm linework",
}
QUOTE_JOURNEYS = {"quote-delivery", "quote-guard"}
QUOTE_OPERATIONS = {"deliver-quote": OutcomeKind.SUCCESS, "lose-quote-ack": OutcomeKind.UNKNOWN}
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
    "quote-second": (
        ("idea", "swallow"),
        ("placement", "shoulder"),
        ("approximate_size", "101 mm"),
        ("style", "linework"),
    ),
}
CATEGORIES = {
    "complex": "COVER_UP",
    "late-cover-up": "COVER_UP",
    "complex-message": "COVER_UP",
    "ambiguous": "AMBIGUOUS",
}


class IntakeFixtureRefused(ProvisioningError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Diagnostic:
    stage: str = "ARGS"
    job_kind: str = "NONE"
    matches_expected: bool = False

    def refusal(self, args, error: Exception) -> str:
        if isinstance(error, IntakeFixtureRefused):
            reason = error.reason
        elif isinstance(error, MessagingError):
            reason = error.code.value
        elif isinstance(error, TimeoutError):
            reason = "TIMEOUT"
        elif isinstance(error, SQLAlchemyError):
            reason = "DATABASE_ERROR"
        elif isinstance(error, ValidationError):
            reason = "VALIDATION_FAILED"
        elif isinstance(error, ProvisioningError):
            reason = {
                "ARGS": "INVALID_ARGUMENTS",
                "GUARD": "TEST_GUARD_REFUSED",
                "EXECUTE": "INBOX_PROCESSING_MISMATCH",
            }.get(self.stage, "PROVISIONING_REFUSED")
        else:
            reason = "UNEXPECTED_ERROR"
        operation = args.operation if args is not None else "UNKNOWN"
        journey = args.journey if args is not None else "UNKNOWN"
        variant = args.variant if args is not None else "UNKNOWN"
        line = (
            f"M5_INTAKE_BROWSER_REFUSED:operation={operation};journey={journey};variant={variant};"
            f"stage={self.stage};reason={reason}"
        )
        if self.stage == "CLAIM":
            line += (
                f";job_kind={self.job_kind};matches_expected={str(self.matches_expected).lower()}"
            )
        return line


class IntakeBrowserKernel(KnowledgeBrowserKernel):
    async def claim_intake(
        self,
        cutoff: datetime,
        matches: Callable[[JobClaim], bool],
        validate: Callable[[JobClaim], None],
        diagnostic: Diagnostic,
        *,
        ai: bool = False,
        scan_until: datetime | None = None,
    ) -> JobClaim | None:
        capability = "ai_delivery_claim" if ai else "messaging_claim"
        worker_id = "m5-intake-ai" if ai else "m5-intake-work"
        scan = ScanStep(
            step="BUSY",
            scan_until=scan_until or cutoff + timedelta(seconds=30),
            at=cutoff,
            id=UUID(int=0),
        )
        async with self._transaction() as connection:
            for _ in range(100):
                async with connection.begin_nested() as probe:
                    scan = ScanStep.model_validate(
                        await call(
                            connection,
                            f"SELECT platform.{capability}(:worker, :until, :at, :id)",
                            {"worker": worker_id, **self._scan_parameters(scan)},
                        )
                    )
                    if scan.step == "END":
                        return None
                    self._check_scan_position(scan)
                    if scan.step == "CLAIMED":
                        claim = parse_claim(scan.claim)
                        diagnostic.job_kind = claim.kind
                        diagnostic.matches_expected = False
                        if matches(claim):
                            validate(claim)
                            diagnostic.matches_expected = True
                            return claim
                    # A prior journey's reminder can become due inside this
                    # window. Revert foreign leases and candidate terminalization
                    # before continuing the scan in the same TEST transaction.
                    await probe.rollback()
        raise IntakeFixtureRefused("CLAIM_SCAN_LIMIT_EXCEEDED")


class DescriptionOnlyStorage:
    async def get(self, key):
        raise IntakeFixtureRefused("PRIVATE_IMAGE_READ_REFUSED")

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
            raise IntakeFixtureRefused("MODEL_SOURCE_MISMATCH")
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
                switch_request=self.operation
                in {"second", "assess-second", "price-second", "quote-second"},
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
        raise IntakeFixtureRefused("ISOLATED_TEST_TARGET_REQUIRED")
    return url


async def run(args, diagnostic):
    diagnostic.stage = "TARGET"
    url = target()
    actor, workspace, business = (
        UUID(value) for value in (args.actor, args.workspace, args.business)
    )
    engine = create_async_engine(
        url, hide_parameters=True, pool_size=2, max_overflow=0, connect_args={"connect_timeout": 3}
    )
    worker = None
    try:
        diagnostic.stage = "GUARD"
        await guard(engine)
        async with engine.connect() as c:
            await native_schema_readiness(c)
        tenancy = TenantDatabase(engine)
        kernel = IntakeBrowserKernel(engine, environment="TEST")
        if args.operation in QUOTE_OPERATIONS:
            return await run_quote(
                args, diagnostic, engine, tenancy, kernel, actor, workspace, business
            )

        async def barrier():
            if engine.pool.checkedout() != 0:
                raise IntakeFixtureRefused("DB_CONNECTION_HELD_DURING_MODEL_CALL")

        adapter = ControlledAdapter(environment="TEST", outcome=OutcomeKind.SUCCESS)
        observer = Worker(kernel, adapter)
        diagnostic.stage = "CONFIGURATION"
        cid = UUID(args.conversation) if args.conversation else None
        if args.operation != "seed" and cid is None:
            raise IntakeFixtureRefused("SEEDED_CONVERSATION_REQUIRED")
        service = None
        async with tenancy.transaction(AuthenticatedAccount(actor), workspace, uuid4()) as unit:
            active = ActiveProjection.model_validate(await unit.configuration_active_read(business))
            if args.operation != "seed":
                if not active.bundle:
                    raise IntakeFixtureRefused("OWNER_PUBLICATION_REQUIRED")
                services = [s.id for s in active.bundle.services if template_revision(s)]
                if len(services) != 1:
                    raise IntakeFixtureRefused("PUBLISHED_TEMPLATE_COUNT_MISMATCH")
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
            diagnostic.stage = "MODEL_SETUP"
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
        diagnostic.stage = "INGEST"
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
        correlation = uuid4()
        incoming = await kernel.ingest_event(adapter.source(bot("knowledge")), value, correlation)
        if incoming.code != "ACCEPTED" or incoming.workspace_id != workspace:
            raise IntakeFixtureRefused("FRESH_CANONICAL_INGEST_REQUIRED")
        kernel.question_inbox_id = incoming.inbox_id
        owner_handoff = CATEGORIES.get(args.operation) == "COVER_UP"
        connection_id, seen_observer, ai_claim = None, False, None

        def validate_claim(claim: JobClaim) -> None:
            if claim.workspace_id != workspace:
                raise IntakeFixtureRefused("JOB_WORKSPACE_MISMATCH")
            if claim.kind not in {"PROCESS_INBOX", "PROCESS_TURN", "SEND_AI_TEXT"}:
                raise IntakeFixtureRefused("UNEXPECTED_JOB_KIND")
            if connection_id is None:
                if (
                    claim.kind != "PROCESS_INBOX"
                    or claim.job_id != incoming.job_id
                    or claim.inbox_id != incoming.inbox_id
                ):
                    raise IntakeFixtureRefused("INGEST_JOB_MISMATCH")
            elif claim.connection_id != connection_id or claim.kind == "PROCESS_INBOX":
                raise IntakeFixtureRefused("UNRELATED_JOB")
            if isinstance(claim, AIJobClaim) and (ai_claim is not None or worker is None):
                raise IntakeFixtureRefused("UNEXPECTED_MODEL_JOB")

        async with asyncio.timeout(25):
            for _ in range(512):
                diagnostic.stage = "CLAIM"
                diagnostic.job_kind = "NONE"
                diagnostic.matches_expected = False
                claim = await kernel.claim_intake(
                    cutoff,
                    lambda job: job.correlation_id == correlation,
                    validate_claim,
                    diagnostic,
                    ai=worker is not None,
                )
                if claim is None and worker is not None:
                    claim = await kernel.claim_intake(
                        cutoff,
                        lambda job: job.correlation_id == correlation,
                        validate_claim,
                        diagnostic,
                    )
                if claim is None:
                    await asyncio.sleep(0.025)
                    continue
                if connection_id is None:
                    connection_id = claim.connection_id
                if isinstance(claim, AIJobClaim):
                    ai_claim = claim
                diagnostic.stage = "EXECUTE"
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
                diagnostic.stage = "OWNER_READ"
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
                        raise IntakeFixtureRefused("OWNER_CONVERSATION_MISMATCH")
                    cid = UUID(found[0].conversation_id)
                    summary = await unit.intake_owner(business, cid, "READ", "", {})
                if args.operation != "seed":
                    diagnostic.stage = "REPLAY"
                    receipt = await worker.ai.database.replay(ai_claim, cfg)
                    if (
                        not isinstance(receipt, IntakeRuntimeReceipt)
                        or len(model.requests) != 1
                        or receipt.result.kind != ("handoff" if owner_handoff else "reply")
                    ):
                        raise IntakeFixtureRefused("DURABLE_MODEL_RESULT_MISMATCH")
                diagnostic.stage = "EFFECTS"
                expected = 0 if owner_handoff or args.operation == "seed" else 1
                if adapter.calls != expected or adapter.effects != expected:
                    raise IntakeFixtureRefused("EXTERNAL_EFFECT_COUNT_MISMATCH")
                return dict(
                    conversation_id=str(cid),
                    message_id=str(kernel.question_message_id),
                    model_calls=0 if args.operation == "seed" else 1,
                    calls=adapter.calls,
                    effects=adapter.effects,
                    status=summary["status"],
                )
        raise IntakeFixtureRefused("FINITE_WORK_INCOMPLETE")
    finally:
        if worker is not None:
            await worker.portfolio_delivery.close()
        await engine.dispose()


async def run_quote(args, diagnostic, engine, tenancy, kernel, actor, workspace, business):
    diagnostic.stage = "OWNER_READ"
    if args.journey not in QUOTE_JOURNEYS or not args.conversation or not args.request:
        raise IntakeFixtureRefused("SELECTED_SYNTHETIC_QUOTE_REQUIRED")
    conversation, request_id = UUID(args.conversation), UUID(args.request)
    scenario = f"{args.journey}-{args.variant}"
    recipient = event("knowledge", f"{scenario}-seed", conversation=scenario).chat_id

    async def read() -> QuoteDeliveryView:
        async with tenancy.transaction(AuthenticatedAccount(actor), workspace, uuid4()) as unit:
            return await ServiceRequestRepository(unit).read_quote(
                business, conversation, request_id
            )

    before = await read()
    quote = before.previous.quote if before.previous else before.quote
    if quote is None or not quote.material.service_name.startswith(
        f"Synthetic intake consultation {args.variant} "
    ):
        raise IntakeFixtureRefused("SELECTED_SYNTHETIC_QUOTE_REQUIRED")
    async with tenancy.transaction(AuthenticatedAccount(actor), workspace, uuid4()) as unit:
        messages = await OwnerAPIRepository(unit).messages(conversation, 100, None)
    if not any(
        m.message_id == quote.material.intent_source.message_id
        and m.direction == "INBOUND"
        and m.text in (INPUTS["price-first"], INPUTS["quote-second"])
        for m in messages.items
    ):
        raise IntakeFixtureRefused("QUOTE_SOURCE_MISMATCH")

    quote_id = UUID(quote.quote_id)
    sent_text = None
    dispatch_commands = asyncio.StreamReader(limit=32) if args.observe_dispatch else None

    async def observe(phase: str):
        if dispatch_commands is None or phase not in {"before_call", "before_finalize"}:
            return
        print(
            json.dumps(dict(phase=phase, calls=adapter.calls, effects=adapter.effects)),
            flush=True,
        )
        async with asyncio.timeout(12):
            if await dispatch_commands.readline() != b"continue\n":
                raise IntakeFixtureRefused("QUOTE_DISPATCH_OBSERVATION_ABORTED")

    class QuoteBrowserAdapter(ControlledAdapter):
        async def send(self, permit: SendPermit):
            nonlocal sent_text
            if (
                not isinstance(permit, QuoteSendPermit)
                or permit.quote_id != quote_id
                or permit.workspace_id != workspace
                or permit.provider != "CONTROLLED"
                or permit.bot_identity != bot("knowledge")
                or permit.chat_id != recipient
                or permit.external_connection_id != route("knowledge", 0)
                or permit.text != quote.text
                or engine.pool.checkedout() != 0
            ):
                raise IntakeFixtureRefused("QUOTE_SEND_SCOPE_MISMATCH")
            sent_text = permit.text
            return await super().send(permit)

    def validate_claim(job: JobClaim):
        if job.workspace_id != workspace:
            raise IntakeFixtureRefused("JOB_WORKSPACE_MISMATCH")

    adapter = QuoteBrowserAdapter(
        environment="TEST", outcome=QUOTE_OPERATIONS[args.operation], barrier=observe
    )
    worker = Worker(kernel, adapter, deadline=20 if args.observe_dispatch else 10)
    born = datetime.fromisoformat(quote.created_at)
    async with engine.connect() as connection:
        now = (await connection.execute(text("SELECT clock_timestamp()"))).scalar_one()
    diagnostic.stage = "CLAIM"
    claim = await kernel.claim_intake(
        born - timedelta(seconds=1),
        lambda job: isinstance(job, QuoteSendJobClaim) and job.quote_id == quote_id,
        validate_claim,
        diagnostic,
        scan_until=now,
    )
    if claim is not None:
        diagnostic.stage = "EXECUTE"
        if dispatch_commands is None:
            await worker.execute(claim)
        else:
            pipe, _ = await asyncio.get_running_loop().connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(dispatch_commands), sys.stdin
            )
            try:
                await worker.execute(claim)
            finally:
                pipe.close()
    diagnostic.stage = "OWNER_READ"
    after = await read()
    result = after.previous if before.previous else after
    if result is None or result.quote != quote:
        raise IntakeFixtureRefused("QUOTE_VERSION_CHANGED")
    return dict(
        quote_id=quote.quote_id,
        job_claimed=claim is not None,
        status=result.status,
        reason=result.reason,
        calls=adapter.calls,
        effects=adapter.effects,
        text=sent_text,
    )


def main():
    diagnostic = Diagnostic()
    args = None
    try:
        parser = PrivateArgumentParser()
        parser.add_argument("--operation", choices=(*INPUTS, *QUOTE_OPERATIONS), required=True)
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
                "owner-decision",
                "owner-decision-partial",
                "owner-source-other",
                *sorted(QUOTE_JOURNEYS),
            ),
            default="intake",
        )
        for name in ("actor", "workspace", "business"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--conversation")
        parser.add_argument("--request")
        parser.add_argument("--observe-dispatch", action="store_true")
        args = parser.parse_args()
        if args.observe_dispatch and args.operation not in QUOTE_OPERATIONS:
            raise IntakeFixtureRefused("QUOTE_DISPATCH_OBSERVATION_REFUSED")
        print(json.dumps(asyncio.run(run(args, diagnostic)), sort_keys=True))
        return 0
    except Exception as error:
        print(diagnostic.refusal(args, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
