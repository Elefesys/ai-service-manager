"""DB-only synthetic runtime. Every capability owns a short, committed transaction.

Application dispatch/readiness stays on 0013. There is no send, provider setup,
automatic retry, recovery generation, or permission derived from ContextBinding.
"""

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from asm.ai.agent import AuthorityDecision, Boundary, ContextRead, ConversationAgent
from asm.ai.context import ContextBinding
from asm.ai.contracts import (
    CONVERSATION_RESULT,
    DTO,
    AdapterRequest,
    AdapterResponse,
    Budget,
    ConversationResult,
    GatewayConfig,
)
from asm.ai.gateway import ModelAdapter
from asm.ai.runtime_contracts import CallCompletion, PreparedRun, RuntimeReceipt, RuntimeStop
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import JobClaim


def decoded[T: DTO](model: type[T], value: Any) -> T:
    # PostgreSQL JSON is wire JSON. Strict DTO UUID/datetime/Decimal conversion
    # uses JSON mode, without ever dumping/re-signing the original snapshot.
    return model.model_validate_json(json.dumps(value, allow_nan=False))


def runtime_config(config: GatewayConfig) -> GatewayConfig:
    config = GatewayConfig.model_validate(config)
    if (
        config.route.execution != "FAKE"
        or config.route.adapter != "fake"
        or config.route.endpoint != "https://fake.invalid/v1"
        or config.route.eligibility != "EVAL_ONLY"
        or config.prompt_revision != "conversation_v2"
        or config.limits.model_calls > 2
        or config.limits.read_executions > 1
    ):
        raise MessagingError(Code.NOT_ALLOWED)
    return config


class AIDatabase:
    def __init__(self, messaging: MessagingDatabase, *, environment: str):
        if environment not in {"LOCAL", "TEST"}:
            raise MessagingError(Code.NOT_ALLOWED)
        self.messaging = messaging

    async def _command(self, claim: JobClaim, operation: str, **payload: Any) -> Any:
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            return await unit.ai_runtime(operation, payload)

    async def enqueue(self, source_claim: JobClaim) -> UUID:
        """Explicit synthetic setup from an admitted TEST_CONSUME job; no scheduler hook."""
        raw = await self._command(source_claim, "ENQUEUE")
        return UUID(raw["job_id"])

    async def prepare(
        self, claim: JobClaim, config: GatewayConfig, *, deadline: datetime
    ) -> PreparedRun:
        config = runtime_config(config)
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise MessagingError(Code.INVALID_INPUT)
        return decoded(
            PreparedRun,
            await self._command(
                claim,
                "PREPARE",
                config=config.model_dump(mode="json"),
                deadline=deadline.isoformat(),
            ),
        )

    def authority(self, claim: JobClaim, run: PreparedRun) -> "PostgresAuthority":
        return PostgresAuthority(self, claim, run)

    async def reserve(self, claim: JobClaim, run: PreparedRun, budget: Budget) -> int:
        raw = await self._command(
            claim, "RESERVE", run_id=str(run.run_id), budget=budget.model_dump(mode="json")
        )
        return int(raw["sequence"])

    async def complete(
        self, claim: JobClaim, run: PreparedRun, sequence: int, completion: CallCompletion
    ) -> None:
        await self._command(
            claim,
            "COMPLETE",
            run_id=str(run.run_id),
            sequence=sequence,
            completion=completion.model_dump(mode="json"),
        )

    async def replay(
        self, claim: JobClaim, config: GatewayConfig, result: ConversationResult | None = None
    ) -> RuntimeReceipt:
        payload: dict[str, object] = {"config": runtime_config(config).model_dump(mode="json")}
        if result is not None:
            payload["result"] = CONVERSATION_RESULT.validate_python(result).model_dump(mode="json")
        return decoded(
            RuntimeReceipt,
            await self.messaging.replay_ai(claim.job_id, claim.claim_token, payload),
        )

    async def commit(
        self, claim: JobClaim, run: PreparedRun, result: ConversationResult
    ) -> RuntimeReceipt:
        result = CONVERSATION_RESULT.validate_python(result)
        try:
            return await self.replay(claim, run.config, result)
        except MessagingError as error:
            if error.code != Code.STALE_CLAIM:
                raise
        try:
            return decoded(
                RuntimeReceipt,
                await self._command(
                    claim, "COMMIT", run_id=str(run.run_id), result=result.model_dump(mode="json")
                ),
            )
        except MessagingError as error:
            if error.code != Code.STALE_CLAIM:
                raise
            # Admission may have waited behind the winning commit. Historical
            # replay still requires that winning capability, not just a run ID.
            return await self.replay(claim, run.config, result)

    async def execute(
        self,
        claim: JobClaim,
        config: GatewayConfig,
        adapter: ModelAdapter,
        *,
        deadline: datetime,
    ) -> RuntimeReceipt | RuntimeStop:
        config = runtime_config(config)
        try:
            return await self.replay(claim, config)
        except MessagingError as error:
            if error.code != Code.STALE_CLAIM:
                raise
        run = await self.prepare(claim, config, deadline=deadline)
        if run.budget.calls_used:
            # No durable wire exchanges are stored. An interrupted invocation
            # cannot reconstruct its Gateway and never starts another POST.
            return RuntimeStop(run_id=run.run_id, reason="INCOMPLETE")
        agent = ConversationAgent(
            config, DurableAdapter(self, claim, run, adapter), self.authority(claim, run)
        )
        outcome = await agent.run(
            run.binding, run.snapshot, run_id=str(run.run_id), deadline=run.deadline
        )
        if outcome.candidate is None:
            return RuntimeStop(run_id=run.run_id, reason="AGENT_STOP")
        return await self.commit(claim, run, outcome.candidate)


class PostgresAuthority:
    def __init__(self, database: AIDatabase, claim: JobClaim, run: PreparedRun):
        self.database, self.claim, self.run = database, claim, run

    async def authorize(self, binding: ContextBinding, boundary: Boundary) -> AuthorityDecision:
        try:
            await self.database._command(
                self.claim,
                "AUTHORIZE",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
                boundary=boundary,
            )
        except MessagingError as error:
            if error.code in {Code.AI_STALE, Code.STALE_CLAIM}:
                return AuthorityDecision(status="STALE", binding=binding)
            if error.code in {
                Code.NOT_ALLOWED,
                Code.ACCESS_DENIED,
                Code.AI_BUDGET,
                Code.AI_INCOMPLETE,
            }:
                return AuthorityDecision(status="DENIED", binding=binding)
            raise
        return AuthorityDecision(status="ALLOWED", binding=binding)

    async def read_current(self, binding: ContextBinding) -> ContextRead:
        return decoded(
            ContextRead,
            await self.database._command(
                self.claim,
                "READ",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
            ),
        )


class DurableAdapter:
    """Reservation commits before entering the inner adapter; no connection crosses await."""

    def __init__(
        self, database: AIDatabase, claim: JobClaim, run: PreparedRun, inner: ModelAdapter
    ):
        self.database, self.claim, self.run, self.inner = database, claim, run, inner
        self.capabilities = inner.capabilities

    def count_input_tokens(self, request: AdapterRequest) -> int | None:
        return self.inner.count_input_tokens(request)

    async def complete(self, request: AdapterRequest) -> AdapterResponse:
        if request.config != self.run.config:
            raise MessagingError(Code.IDEMPOTENCY_KEY_CONFLICT)
        sequence = await self.database.reserve(self.claim, self.run, request.budget)
        try:
            response = AdapterResponse.model_validate(await self.inner.complete(request))
        except BaseException as primary:
            # The durable reservation already says UNKNOWN. Recording a bounded
            # error is best effort; cancellation/lease loss cannot erase it.
            try:
                await self.database.complete(
                    self.claim,
                    self.run,
                    sequence,
                    CallCompletion(
                        kind="UNKNOWN",
                        error="CANCELLED"
                        if isinstance(primary, asyncio.CancelledError)
                        else "ADAPTER_ERROR",
                    ),
                )
            except BaseException:
                pass
            raise
        await self.database.complete(
            self.claim,
            self.run,
            sequence,
            CallCompletion(kind=response.kind, usage=response.usage, cost=response.cost),
        )
        return response
