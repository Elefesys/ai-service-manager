"""Synthetic AI authority. Every capability owns a short committed transaction.

The historical 0014 API remains DB-only. Explicit 0015 delivery composition
selects a separate capability; a replayed result is never a send permit.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from asm.ai.agent import (
    AuthorityDecision,
    Boundary,
    ContextRead,
    ConversationAgent,
    KnowledgeAuthorityDecision,
    KnowledgeContextRead,
    KnowledgeConversationAgent,
    SearchAuthorityDecision,
    SearchContextRead,
    SearchConversationAgent,
)
from asm.ai.context import ContextBinding
from asm.ai.contracts import (
    DTO,
    AdapterRequest,
    AdapterResponse,
    AnyConversationResult,
    AnyGatewayConfig,
    Budget,
    IntakeGatewayConfig,
    IntakeReply,
    PortfolioDeliveryGatewayConfig,
    PortfolioGatewayConfig,
    PortfolioPhoto,
    PortfolioPhotoSelection,
    Reply,
    SchedulingIntentGatewayConfig,
    SchedulingIntentResult,
    ServiceIntentGatewayConfig,
    ServiceIntentResult,
    validate_conversation_result,
    validate_gateway_config,
)
from asm.ai.gateway import ModelAdapter
from asm.ai.knowledge import KnowledgePin, SearchPin, SearchProjection
from asm.ai.portfolio import (
    MediaPin,
    PortfolioAuthorityDecision,
    PortfolioContextRead,
    PortfolioConversationAgent,
    PortfolioPin,
)
from asm.ai.portfolio_delivery import (
    PortfolioDeliveryContextRead,
    PortfolioDeliveryConversationAgent,
)
from asm.ai.runtime_contracts import (
    AnyPortfolioQueryData,
    AnyPortfolioRun,
    AnyPreparedRun,
    AnyRuntimeReceipt,
    CallCompletion,
    IntakeRuntimeReceipt,
    KnowledgeRuntimeReceipt,
    PortfolioDeliveryQueryData,
    PortfolioDeliveryRuntimeReceipt,
    PortfolioQueryData,
    PortfolioQueryReservation,
    PortfolioRuntimeReceipt,
    PreparedIntakeRun,
    PreparedKnowledgeRun,
    PreparedPortfolioDeliveryRun,
    PreparedPortfolioRun,
    PreparedRun,
    PreparedSearchRun,
    QueryReservation,
    RuntimeReceipt,
    RuntimeStop,
    SearchRuntimeReceipt,
    ServiceIntentRuntimeReceipt,
)
from asm.intake.models import CandidateSet
from asm.intake.projection import AMBIGUOUS_QUESTION
from asm.knowledge.embeddings import EmbeddingClient, EmbeddingFailure, unavailable
from asm.knowledge.errors import KnowledgeError
from asm.messaging.database import MessagingDatabase
from asm.messaging.errors import Code, MessagingError
from asm.messaging.results import JobClaim

if TYPE_CHECKING:
    from asm.ai.runtime_settings import RuntimeSettings
    from asm.telegram.client import TelegramClient


def decoded[T: DTO](model: type[T], value: Any) -> T:
    # PostgreSQL JSON is wire JSON. Strict DTO UUID/datetime/Decimal conversion
    # uses JSON mode, without ever dumping/re-signing the original snapshot.
    return model.model_validate_json(json.dumps(value, allow_nan=False))


def runtime_config(config: AnyGatewayConfig) -> AnyGatewayConfig:
    config = validate_gateway_config(config)
    if (
        config.route.execution != "FAKE"
        or config.route.adapter != "fake"
        or config.route.endpoint != "https://fake.invalid/v1"
        or config.route.eligibility != "EVAL_ONLY"
        or config.prompt_revision not in {"conversation_v2", "conversation_v3", "conversation_v4"}
        or config.limits.model_calls > 2
        or config.limits.read_executions > 1
    ):
        raise MessagingError(Code.NOT_ALLOWED)
    return config


class AIDatabase:
    def __init__(
        self,
        messaging: MessagingDatabase,
        *,
        environment: str,
        delivery: bool = False,
        provider: "RuntimeSettings | None" = None,
        embeddings: EmbeddingClient | None = None,
        portfolio_session_id: UUID | None = None,
        portfolio_delivery: bool = False,
        intake: bool = False,
    ):
        if environment not in {"LOCAL", "TEST"}:
            raise MessagingError(Code.NOT_ALLOWED)
        self.messaging = messaging
        if type(delivery) is not bool:
            raise MessagingError(Code.INVALID_INPUT)
        self.delivery = delivery
        if provider is not None and not delivery:
            raise MessagingError(Code.NOT_ALLOWED)
        if portfolio_session_id is not None and (
            type(portfolio_session_id) is not UUID
            or environment != "TEST"
            or not delivery
            or provider is not None
        ):
            raise MessagingError(Code.NOT_ALLOWED)
        if (
            type(portfolio_delivery) is not bool
            or portfolio_delivery
            and portfolio_session_id is None
        ):
            raise MessagingError(Code.NOT_ALLOWED)
        if type(intake) is not bool or intake and not portfolio_delivery:
            raise MessagingError(Code.NOT_ALLOWED)
        self.intake = intake
        self.portfolio_delivery = portfolio_delivery
        self.portfolio_session_id = portfolio_session_id
        self.provider = provider
        if embeddings is not None and type(embeddings) is not EmbeddingClient:
            raise MessagingError(Code.NOT_ALLOWED)
        self.embeddings = embeddings if embeddings is not None else EmbeddingClient()

    def config(self, config: AnyGatewayConfig) -> AnyGatewayConfig:
        if self.intake:
            if not isinstance(
                config,
                (IntakeGatewayConfig, ServiceIntentGatewayConfig, SchedulingIntentGatewayConfig),
            ):
                raise MessagingError(Code.NOT_ALLOWED)
            return validate_gateway_config(config)
        if self.portfolio_delivery:
            if not isinstance(config, PortfolioDeliveryGatewayConfig):
                raise MessagingError(Code.NOT_ALLOWED)
            return PortfolioDeliveryGatewayConfig.model_validate(config)
        if self.portfolio_session_id is not None:
            if not isinstance(config, PortfolioGatewayConfig):
                raise MessagingError(Code.NOT_ALLOWED)
            return PortfolioGatewayConfig.model_validate(config)
        if self.provider is None:
            return runtime_config(config)
        config = validate_gateway_config(config)
        if config != self.provider.gateway():
            raise MessagingError(Code.NOT_ALLOWED)
        return config

    async def _command(self, claim: JobClaim, operation: str, **payload: Any) -> Any:
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            return await unit.ai_runtime(
                operation,
                payload,
                delivery=self.delivery,
                provider_session=self.provider.session_id if self.provider else None,
            )

    async def enqueue(self, source_claim: JobClaim) -> UUID:
        """Explicit synthetic setup from an admitted TEST_CONSUME job; no scheduler hook."""
        raw = await self._command(source_claim, "ENQUEUE")
        return UUID(raw["job_id"])

    async def prepare(
        self, claim: JobClaim, config: AnyGatewayConfig, *, deadline: datetime
    ) -> AnyPreparedRun:
        config = self.config(config)
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise MessagingError(Code.INVALID_INPUT)
        payload: dict[str, Any] = {
            "config": config.model_dump(mode="json"),
            "deadline": deadline.isoformat(),
        }
        if isinstance(
            config,
            (
                PortfolioGatewayConfig,
                PortfolioDeliveryGatewayConfig,
                IntakeGatewayConfig,
                ServiceIntentGatewayConfig,
                SchedulingIntentGatewayConfig,
            ),
        ):
            if self.portfolio_session_id is None:
                raise MessagingError(Code.NOT_ALLOWED)
            payload["portfolio_session_id"] = str(self.portfolio_session_id)
        raw = await self._command(claim, "PREPARE", **payload)
        if config.prompt_revision in {
            "conversation_v5",
            "conversation_v6",
            "conversation_v7",
            "conversation_v8",
            "conversation_v9",
        }:
            run = (
                decoded(PreparedIntakeRun, raw)
                if isinstance(
                    config,
                    (
                        IntakeGatewayConfig,
                        ServiceIntentGatewayConfig,
                        SchedulingIntentGatewayConfig,
                    ),
                )
                else decoded(PreparedPortfolioDeliveryRun, raw)
                if isinstance(config, PortfolioDeliveryGatewayConfig)
                else decoded(PreparedPortfolioRun, raw)
            )
            if run.portfolio_session_id != self.portfolio_session_id or run.config != config:
                raise MessagingError(Code.AI_STALE)
            return run
        if config.prompt_revision == "conversation_v4":
            return decoded(PreparedSearchRun, raw)
        if config.prompt_revision == "conversation_v3":
            return decoded(PreparedKnowledgeRun, raw)
        return decoded(PreparedRun, raw)

    def authority(
        self, claim: JobClaim, run: AnyPreparedRun
    ) -> "PostgresAuthority | PostgresKnowledgeAuthority | PostgresSearchAuthority | PostgresPortfolioAuthority":
        if isinstance(run, (PreparedPortfolioDeliveryRun, PreparedIntakeRun)):
            return PostgresPortfolioDeliveryAuthority(self, claim, run)
        if isinstance(run, (PreparedPortfolioRun, PreparedPortfolioDeliveryRun, PreparedIntakeRun)):
            return PostgresPortfolioAuthority(self, claim, run)
        if isinstance(run, PreparedSearchRun):
            return PostgresSearchAuthority(self, claim, run)
        if isinstance(run, PreparedKnowledgeRun):
            return PostgresKnowledgeAuthority(self, claim, run)
        return PostgresAuthority(self, claim, run)

    def receipt(self, config: AnyGatewayConfig, raw: Any) -> AnyRuntimeReceipt:
        if isinstance(config, (ServiceIntentGatewayConfig, SchedulingIntentGatewayConfig)):
            return decoded(ServiceIntentRuntimeReceipt, raw)
        if isinstance(config, IntakeGatewayConfig):
            return decoded(IntakeRuntimeReceipt, raw)
        if isinstance(config, PortfolioDeliveryGatewayConfig):
            return decoded(PortfolioDeliveryRuntimeReceipt, raw)
        return decoded(
            PortfolioRuntimeReceipt
            if config.prompt_revision == "conversation_v5"
            else SearchRuntimeReceipt
            if config.prompt_revision == "conversation_v4"
            else KnowledgeRuntimeReceipt
            if config.prompt_revision == "conversation_v3"
            else RuntimeReceipt,
            raw,
        )

    async def reserve(self, claim: JobClaim, run: AnyPreparedRun, budget: Budget) -> int:
        raw = await self._command(
            claim, "RESERVE", run_id=str(run.run_id), budget=budget.model_dump(mode="json")
        )
        return int(raw["sequence"])

    async def complete(
        self, claim: JobClaim, run: AnyPreparedRun, sequence: int, completion: CallCompletion
    ) -> None:
        await self._command(
            claim,
            "COMPLETE",
            run_id=str(run.run_id),
            sequence=sequence,
            completion=completion.model_dump(mode="json"),
        )

    async def replay(
        self, claim: JobClaim, config: AnyGatewayConfig, result: AnyConversationResult | None = None
    ) -> AnyRuntimeReceipt:
        payload: dict[str, object] = {"config": self.config(config).model_dump(mode="json")}
        if result is not None:
            payload["result"] = validate_conversation_result(config, result).model_dump(mode="json")
        return self.receipt(
            config,
            await self.messaging.replay_ai(claim.job_id, claim.claim_token, payload),
        )

    async def commit(
        self, claim: JobClaim, run: AnyPreparedRun, result: AnyConversationResult
    ) -> AnyRuntimeReceipt:
        result = validate_conversation_result(run.config, result)
        try:
            return await self.replay(
                claim, run.config, None if isinstance(result, SchedulingIntentResult) else result
            )
        except MessagingError as error:
            if error.code != Code.STALE_CLAIM:
                raise
        try:
            if isinstance(result, SchedulingIntentResult):
                return await self._commit_scheduling_intent(claim, run, result)
            if isinstance(result, ServiceIntentResult):
                return await self._commit_service_intents(claim, run, result)
            return self.receipt(
                run.config,
                await self._command(
                    claim, "COMMIT", run_id=str(run.run_id), result=result.model_dump(mode="json")
                ),
            )
        except MessagingError as error:
            if error.code != Code.STALE_CLAIM:
                raise
            # Admission may have waited behind the winning commit. Historical
            # replay still requires that winning capability, not just a run ID.
            return await self.replay(
                claim, run.config, None if isinstance(result, SchedulingIntentResult) else result
            )

    async def _commit_scheduling_intent(
        self, claim: JobClaim, run: AnyPreparedRun, result: SchedulingIntentResult
    ) -> AnyRuntimeReceipt:
        from asm.scheduling.conversation import finish_scheduling_intent

        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:

            async def command(stage: str, payload: dict[str, object]) -> Any:
                return await unit.scheduling_intent(run.run_id, stage, payload)

            raw = await finish_scheduling_intent(result, command)
            receipt = self.receipt(run.config, raw)
            await self.messaging.checkpoint("scheduling_intent_before_commit")
        await self.messaging.checkpoint("scheduling_intent_after_commit")
        return receipt

    async def _commit_service_intents(
        self, claim: JobClaim, run: AnyPreparedRun, result: ServiceIntentResult
    ) -> ServiceIntentRuntimeReceipt:
        from asm.service_requests.agent import finish_service_intents

        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit.ai_runtime(
                "COMMIT",
                {"run_id": str(run.run_id), "result": result.model_dump(mode="json")},
                delivery=self.delivery,
            )

            async def continue_intents(stage: str, payload: dict[str, object]) -> object:
                return await unit.continue_service_intents(run.run_id, stage, payload)

            effects = await finish_service_intents(continue_intents)
            receipt = decoded(ServiceIntentRuntimeReceipt, raw | {"service_intents": effects})
            await self.messaging.checkpoint("service_intents_before_commit")
        await self.messaging.checkpoint("service_intents_after_commit")
        return receipt

    async def execute(
        self,
        claim: JobClaim,
        config: AnyGatewayConfig,
        adapter: ModelAdapter,
        *,
        deadline: datetime,
        telegram: "TelegramClient | None" = None,
    ) -> AnyRuntimeReceipt | RuntimeStop:
        config = self.config(config)
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
        projection: SearchProjection | None = None
        portfolio_data: AnyPortfolioQueryData | None = None
        if isinstance(run, (PreparedPortfolioRun, PreparedPortfolioDeliveryRun, PreparedIntakeRun)):
            portfolio_data = await self.portfolio_query(claim, run)
            if portfolio_data is None:
                return RuntimeStop(run_id=run.run_id, reason="INCOMPLETE")
            # The shared QUERY has a durable hold. Re-read the same saved run so
            # Gateway starts with all auxiliary cost under the original budget.
            refreshed = await self.prepare(claim, config, deadline=run.deadline)
            if not isinstance(
                refreshed, (PreparedPortfolioRun, PreparedPortfolioDeliveryRun, PreparedIntakeRun)
            ):
                raise MessagingError(Code.AI_STALE)
            run = refreshed
            self._portfolio_data_current(run, portfolio_data)
        if isinstance(run, PreparedSearchRun):
            projection = await self.query(claim, run)
            if projection is None:
                return RuntimeStop(run_id=run.run_id, reason="INCOMPLETE")
            run = PreparedSearchRun.model_validate(
                run.model_dump() | {"search_refs": projection.refs()}
            )
        wrapped = DurableAdapter(self, claim, run, adapter)
        agent: ConversationAgent
        if isinstance(run, (PreparedPortfolioDeliveryRun, PreparedIntakeRun)):
            if not isinstance(portfolio_data, PortfolioDeliveryQueryData):
                raise MessagingError(Code.AI_STALE)
            from asm.ai.intake import (
                IntakeConversationAgent,
                SchedulingIntentConversationAgent,
                ServiceIntentConversationAgent,
            )

            agent_class = (
                SchedulingIntentConversationAgent
                if isinstance(config, SchedulingIntentGatewayConfig)
                else ServiceIntentConversationAgent
                if isinstance(config, ServiceIntentGatewayConfig)
                else IntakeConversationAgent
                if isinstance(run, PreparedIntakeRun)
                else PortfolioDeliveryConversationAgent
            )
            agent = agent_class(
                config,
                wrapped,
                PostgresPortfolioDeliveryAuthority(self, claim, run),
                knowledge_pin=run.knowledge_pin,
                active_projection=run.active_projection,
                search_pin=run.search_pin,
                portfolio_pin=run.portfolio_pin,
                media_pin=run.media_pin,
                search_projection=portfolio_data.knowledge,
                portfolio_projection=portfolio_data.portfolio,
                vision_analysis=run.vision_analysis,
                search_query=run.search_query,
                delivery_eligible=portfolio_data.delivery_eligible,
                initial_budget=run.budget,
            )
            if isinstance(run, PreparedIntakeRun) and isinstance(agent, IntakeConversationAgent):
                agent.intake = run.intake
        elif isinstance(run, PreparedPortfolioRun):
            assert portfolio_data is not None
            agent = PortfolioConversationAgent(
                config,
                wrapped,
                PostgresPortfolioAuthority(self, claim, run),
                knowledge_pin=run.knowledge_pin,
                active_projection=run.active_projection,
                search_pin=run.search_pin,
                portfolio_pin=run.portfolio_pin,
                media_pin=run.media_pin,
                search_projection=portfolio_data.knowledge,
                portfolio_projection=portfolio_data.portfolio,
                vision_analysis=run.vision_analysis,
                search_query=run.search_query,
                initial_budget=run.budget,
            )
        elif isinstance(run, PreparedSearchRun):
            assert projection is not None
            agent = SearchConversationAgent(
                config,
                wrapped,
                PostgresSearchAuthority(self, claim, run),
                knowledge_pin=run.knowledge_pin,
                active_projection=run.active_projection,
                search_pin=run.search_pin,
                search_projection=projection,
            )
        elif isinstance(run, PreparedKnowledgeRun):
            agent = KnowledgeConversationAgent(
                config,
                wrapped,
                PostgresKnowledgeAuthority(self, claim, run),
                knowledge_pin=run.knowledge_pin,
                active_projection=run.active_projection,
            )
        else:
            agent = ConversationAgent(config, wrapped, PostgresAuthority(self, claim, run))
        outcome = await agent.run(
            run.binding, run.snapshot, run_id=str(run.run_id), deadline=run.deadline
        )
        if outcome.reason == "CANCELLED":
            # The agent deliberately returns a terminal outcome. At the worker
            # boundary cancellation must still unwind the parent TaskGroup (or
            # asyncio.timeout); otherwise the AI lane starts another iteration.
            raise asyncio.CancelledError
        if outcome.candidate is None:
            return RuntimeStop(run_id=run.run_id, reason="AGENT_STOP")
        if self.delivery and isinstance(outcome.candidate, (Reply, PortfolioPhoto)):
            return await self._commit_reply(claim, run, outcome.candidate, telegram)
        try:
            return await self.commit(claim, run, outcome.candidate)
        except MessagingError as intent_error:
            if intent_error.code != Code.AI_INTENT_AMBIGUOUS or not isinstance(
                outcome.candidate, ServiceIntentResult
            ):
                raise
            return await self._commit_reply(
                claim,
                run,
                IntakeReply(
                    kind="reply",
                    text=AMBIGUOUS_QUESTION,
                    reason=None,
                    intake=CandidateSet(
                        service_id=None, category="AMBIGUOUS", switch_request=False, facts=()
                    ),
                ),
                telegram,
            )

    async def _commit_reply(
        self,
        claim: JobClaim,
        run: AnyPreparedRun,
        result: Reply | PortfolioPhoto,
        telegram: "TelegramClient | None",
    ) -> AnyRuntimeReceipt | RuntimeStop:
        # The persisted run deadline also bounds HTTP after the agent returns.
        # Probe commits before I/O; observation CAS and canonical selection share
        # the second transaction. A rejected observation still commits as negative.
        try:
            async with asyncio.timeout((run.deadline - datetime.now(UTC)).total_seconds()):
                probe = await self.messaging.ai_reply_probe(claim, run.run_id)
                if probe is None:
                    return await self.commit(claim, run, result)
                if telegram is None:
                    raise MessagingError(Code.NOT_ALLOWED)
                observation = await telegram.observe(
                    probe.bot_identity, probe.external_connection_id, probe.owner_user_id
                )
                raw = await self.messaging.commit_ai_reply(
                    claim, run.run_id, probe, observation, result.model_dump(mode="json")
                )
                if raw == {"code": "RIGHTS_REJECTED"}:
                    return RuntimeStop(run_id=run.run_id, reason="AGENT_STOP")
                return self.receipt(run.config, raw)
        except MessagingError as error:
            if error.code != Code.STALE_CLAIM:
                raise
            # Concurrent/lost-ACK recognition never repeats the observation/model.
            return await self.replay(claim, run.config, result)

    async def _search_read(self, claim: JobClaim, run: PreparedSearchRun) -> SearchProjection:
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit.knowledge_runtime_read(
                run.run_id, run.search_pin.model_dump(mode="json")
            )
        return decoded(SearchProjection, raw)

    async def query(self, claim: JobClaim, run: PreparedSearchRun) -> SearchProjection | None:
        """One committed query reservation; no ticket/wire is recoverable on replay."""
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit.knowledge_query_reserve(
                run.run_id, run.search_pin.model_dump(mode="json")
            )
        reservation = decoded(QueryReservation, raw)
        if reservation.status == "REPLAY":
            try:
                return await self._search_read(claim, run)
            except MessagingError as error:
                if error.code == Code.AI_INCOMPLETE:
                    return None
                raise
        assert reservation.call_id is not None and reservation.ticket is not None
        assert (
            reservation.wire is not None
            and reservation.wire_sha256 is not None
            and reservation.deadline is not None
        )
        call, ticket = reservation.call_id, reservation.ticket
        try:
            try:
                outcome = await self.embeddings.complete(
                    reservation.wire,
                    deadline=datetime.strptime(
                        reservation.deadline, "%Y-%m-%dT%H:%M:%S.%fZ"
                    ).replace(tzinfo=UTC),
                    wire_sha256=reservation.wire_sha256,
                )
            except EmbeddingFailure as error:
                outcome = unavailable(error.code)
            # Completion has only the opaque accounting capability, not the
            # current job or owner privilege that may have changed during HTTP.
            completed = await self.messaging.complete_embedding(call, ticket, outcome)
        except asyncio.CancelledError:
            try:
                async with asyncio.timeout(1):
                    await self.messaging.complete_embedding(
                        call, ticket, unavailable("CANCELLED", unknown=True)
                    )
            except (
                KnowledgeError,
                MessagingError,
                SQLAlchemyError,
                TimeoutError,
                asyncio.CancelledError,
            ):
                pass
            raise
        if outcome["kind"] != "SUCCESS" or completed["state"] != "SUCCESS":
            return None
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            projection = await unit.knowledge_query_apply(
                run.run_id, call, ticket, outcome["vectors"]
            )
        return decoded(SearchProjection, projection)

    @staticmethod
    def _portfolio_pins(run: AnyPortfolioRun) -> dict[str, Any]:
        return {
            "search_pin": run.search_pin.model_dump(mode="json"),
            "portfolio_pin": run.portfolio_pin.model_dump(mode="json"),
            "media_pin": run.media_pin.model_dump(mode="json"),
        }

    @staticmethod
    def _portfolio_data_current(run: AnyPortfolioRun, data: AnyPortfolioQueryData) -> None:
        if (
            (
                data.portfolio_pin,
                data.media_pin,
                data.portfolio_session_id,
                data.search_query,
                data.vision_analysis,
            )
            != (
                run.portfolio_pin,
                run.media_pin,
                run.portfolio_session_id,
                run.search_query,
                run.vision_analysis,
            )
            or data.knowledge.profile_id != run.search_pin.profile_id
            or data.portfolio.profile_id != run.portfolio_pin.profile_id
        ):
            raise MessagingError(Code.AI_STALE)

    async def _portfolio_read(self, claim: JobClaim, run: AnyPortfolioRun) -> AnyPortfolioQueryData:
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit.portfolio_runtime_read(run.run_id, self._portfolio_pins(run))
        value = (
            decoded(PortfolioDeliveryQueryData, raw)
            if isinstance(run, (PreparedPortfolioDeliveryRun, PreparedIntakeRun))
            else decoded(PortfolioQueryData, raw)
        )
        self._portfolio_data_current(run, value)
        return value

    async def portfolio_query(
        self, claim: JobClaim, run: AnyPortfolioRun
    ) -> AnyPortfolioQueryData | None:
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit.portfolio_query_reserve(run.run_id, self._portfolio_pins(run))
        reservation = decoded(PortfolioQueryReservation, raw)
        if reservation.status == "REPLAY":
            try:
                return await self._portfolio_read(claim, run)
            except MessagingError as error:
                if error.code == Code.AI_INCOMPLETE:
                    return None
                raise
        assert reservation.call_id is not None and reservation.ticket is not None
        assert (
            reservation.wire is not None
            and reservation.wire_sha256 is not None
            and reservation.deadline is not None
        )
        call, ticket = reservation.call_id, reservation.ticket
        try:
            try:
                outcome = await self.embeddings.complete(
                    reservation.wire,
                    deadline=reservation.deadline,
                    wire_sha256=reservation.wire_sha256,
                )
            except EmbeddingFailure as error:
                outcome = unavailable(error.code)
            # Opaque private accounting, even if OWNER/HUMAN/media changes during HTTP.
            completed = await self.messaging.complete_embedding(call, ticket, outcome)
        except asyncio.CancelledError:
            try:
                async with asyncio.timeout(1):
                    await self.messaging.complete_embedding(
                        call, ticket, unavailable("CANCELLED", unknown=True)
                    )
            except (
                KnowledgeError,
                MessagingError,
                SQLAlchemyError,
                TimeoutError,
                asyncio.CancelledError,
            ):
                pass
            raise
        if outcome["kind"] != "SUCCESS" or completed["state"] != "SUCCESS":
            return None
        async with self.messaging.admit_job(claim.job_id, claim.claim_token) as unit:
            raw = await unit.portfolio_query_apply(run.run_id, call, ticket, outcome["vectors"])
        value = (
            decoded(PortfolioDeliveryQueryData, raw)
            if isinstance(run, (PreparedPortfolioDeliveryRun, PreparedIntakeRun))
            else decoded(PortfolioQueryData, raw)
        )
        self._portfolio_data_current(run, value)
        return value


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


class PostgresKnowledgeAuthority:
    """The admitted claim and persisted publication jointly authorize v3 reads."""

    def __init__(self, database: AIDatabase, claim: JobClaim, run: PreparedKnowledgeRun):
        self.database, self.claim, self.run = database, claim, run

    async def authorize(
        self, binding: ContextBinding, pin: KnowledgePin, boundary: Boundary
    ) -> KnowledgeAuthorityDecision:
        status: str = "ALLOWED"
        try:
            await self.database._command(
                self.claim,
                "AUTHORIZE",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
                knowledge_pin=pin.model_dump(mode="json"),
                boundary=boundary,
            )
        except MessagingError as error:
            if error.code in {Code.AI_STALE, Code.STALE_CLAIM}:
                status = "STALE"
            elif error.code in {
                Code.NOT_ALLOWED,
                Code.ACCESS_DENIED,
                Code.AI_BUDGET,
                Code.AI_INCOMPLETE,
            }:
                status = "DENIED"
            else:
                raise
        return decoded(
            KnowledgeAuthorityDecision,
            {
                "status": status,
                "binding": binding.model_dump(mode="json"),
                "knowledge_pin": pin.model_dump(mode="json"),
            },
        )

    async def read_current(
        self, binding: ContextBinding, pin: KnowledgePin
    ) -> KnowledgeContextRead:
        return decoded(
            KnowledgeContextRead,
            await self.database._command(
                self.claim,
                "READ",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
                knowledge_pin=pin.model_dump(mode="json"),
            ),
        )


class PostgresSearchAuthority:
    """A fresh admitted job checks the original publication and availability pin."""

    def __init__(self, database: AIDatabase, claim: JobClaim, run: PreparedSearchRun):
        self.database, self.claim, self.run = database, claim, run

    async def authorize(
        self, binding: ContextBinding, pin: KnowledgePin, search_pin: SearchPin, boundary: Boundary
    ) -> SearchAuthorityDecision:
        status = "ALLOWED"
        try:
            await self.database._command(
                self.claim,
                "AUTHORIZE",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
                knowledge_pin=pin.model_dump(mode="json"),
                search_pin=search_pin.model_dump(mode="json"),
                boundary=boundary,
            )
        except MessagingError as error:
            if error.code in {Code.AI_STALE, Code.STALE_CLAIM}:
                status = "STALE"
            elif error.code in {
                Code.NOT_ALLOWED,
                Code.ACCESS_DENIED,
                Code.AI_BUDGET,
                Code.AI_INCOMPLETE,
            }:
                status = "DENIED"
            else:
                raise
        return decoded(
            SearchAuthorityDecision,
            {
                "status": status,
                "binding": binding.model_dump(mode="json"),
                "knowledge_pin": pin.model_dump(mode="json"),
                "search_pin": search_pin.model_dump(mode="json"),
            },
        )

    async def read_current(
        self, binding: ContextBinding, pin: KnowledgePin, search_pin: SearchPin
    ) -> SearchContextRead:
        return decoded(
            SearchContextRead,
            await self.database._command(
                self.claim,
                "READ",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
                knowledge_pin=pin.model_dump(mode="json"),
                search_pin=search_pin.model_dump(mode="json"),
            ),
        )


class PostgresPortfolioAuthority:
    def __init__(self, database: AIDatabase, claim: JobClaim, run: AnyPortfolioRun):
        self.database, self.claim, self.run = database, claim, run

    async def authorize(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
        boundary: Boundary,
    ) -> PortfolioAuthorityDecision:
        status = "ALLOWED"
        try:
            await self.database._command(
                self.claim,
                "AUTHORIZE",
                run_id=str(self.run.run_id),
                binding=binding.model_dump(mode="json"),
                knowledge_pin=knowledge_pin.model_dump(mode="json"),
                search_pin=search_pin.model_dump(mode="json"),
                portfolio_pin=portfolio_pin.model_dump(mode="json"),
                media_pin=media_pin.model_dump(mode="json"),
                boundary=boundary,
            )
        except MessagingError as error:
            if error.code in {Code.AI_STALE, Code.STALE_CLAIM}:
                status = "STALE"
            elif error.code in {
                Code.NOT_ALLOWED,
                Code.ACCESS_DENIED,
                Code.AI_BUDGET,
                Code.AI_INCOMPLETE,
            }:
                status = "DENIED"
            else:
                raise
        return decoded(
            PortfolioAuthorityDecision,
            {
                "status": status,
                "binding": binding.model_dump(mode="json"),
                "knowledge_pin": knowledge_pin.model_dump(mode="json"),
                "search_pin": search_pin.model_dump(mode="json"),
                "portfolio_pin": portfolio_pin.model_dump(mode="json"),
                "media_pin": media_pin.model_dump(mode="json"),
            },
        )

    async def read_current(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
    ) -> PortfolioContextRead:
        raw = await self.database._command(
            self.claim,
            "READ",
            run_id=str(self.run.run_id),
            binding=binding.model_dump(mode="json"),
            knowledge_pin=knowledge_pin.model_dump(mode="json"),
            search_pin=search_pin.model_dump(mode="json"),
            portfolio_pin=portfolio_pin.model_dump(mode="json"),
            media_pin=media_pin.model_dump(mode="json"),
        )
        if type(raw) is not dict or raw.get("portfolio_session_id") != str(
            self.run.portfolio_session_id
        ):
            raise MessagingError(Code.AI_STALE)
        # Admission metadata is private to this authority adapter, not a READ fact.
        return decoded(
            PortfolioContextRead, {k: v for k, v in raw.items() if k != "portfolio_session_id"}
        )


class PostgresPortfolioDeliveryAuthority(PostgresPortfolioAuthority):
    async def read_current(
        self,
        binding: ContextBinding,
        knowledge_pin: KnowledgePin,
        search_pin: SearchPin,
        portfolio_pin: PortfolioPin,
        media_pin: MediaPin,
    ) -> PortfolioDeliveryContextRead:
        raw = await self.database._command(
            self.claim,
            "READ",
            run_id=str(self.run.run_id),
            binding=binding.model_dump(mode="json"),
            knowledge_pin=knowledge_pin.model_dump(mode="json"),
            search_pin=search_pin.model_dump(mode="json"),
            portfolio_pin=portfolio_pin.model_dump(mode="json"),
            media_pin=media_pin.model_dump(mode="json"),
        )
        if type(raw) is not dict or raw.get("portfolio_session_id") != str(
            self.run.portfolio_session_id
        ):
            raise MessagingError(Code.AI_STALE)
        if isinstance(self.run, PreparedIntakeRun):
            from asm.ai.intake import IntakeContextRead

            value = decoded(
                IntakeContextRead, {k: v for k, v in raw.items() if k != "portfolio_session_id"}
            )
            if value.intake != self.run.intake:
                raise MessagingError(Code.AI_STALE)
            return decoded(
                PortfolioDeliveryContextRead, value.model_dump(mode="json", exclude={"intake"})
            )
        return decoded(
            PortfolioDeliveryContextRead,
            {k: v for k, v in raw.items() if k != "portfolio_session_id"},
        )

    async def attest_read(
        self,
        binding: ContextBinding,
        context_sha256: str,
        shown_refs: tuple[PortfolioPhotoSelection, ...],
    ) -> None:
        await self.database._command(
            self.claim,
            "DELIVERY_READ",
            run_id=str(self.run.run_id),
            binding=binding.model_dump(mode="json"),
            knowledge_pin=self.run.knowledge_pin.model_dump(mode="json"),
            search_pin=self.run.search_pin.model_dump(mode="json"),
            portfolio_pin=self.run.portfolio_pin.model_dump(mode="json"),
            media_pin=self.run.media_pin.model_dump(mode="json"),
            context_sha256=context_sha256,
            shown_refs=[v.model_dump(mode="json") for v in shown_refs],
        )


class DurableAdapter:
    """Reservation commits before entering the inner adapter; no connection crosses await."""

    def __init__(
        self, database: AIDatabase, claim: JobClaim, run: AnyPreparedRun, inner: ModelAdapter
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
                async with asyncio.timeout(1):
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
