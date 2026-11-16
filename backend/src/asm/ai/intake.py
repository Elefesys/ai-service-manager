"""Explicit v7 candidate extraction, sharing the bounded knowledge/photo agent."""

from typing import Literal

from pydantic import Field

from asm.ai.agent import AnyAgentOutcome, ConversationAgent, StopCode
from asm.ai.context import ContextBinding
from asm.ai.contracts import (
    DTO,
    AnyConversationResult,
    IntakeHandoff,
    IntakeNoReply,
    IntakePhoto,
    IntakeReply,
    Message,
)
from asm.ai.knowledge import KnowledgeFailure
from asm.ai.portfolio_delivery import (
    PortfolioDeliveryContextRead,
    PortfolioDeliveryContextView,
    PortfolioDeliveryConversationAgent,
    PreparedPortfolioDeliveryContext,
)
from asm.intake.models import CandidateSet, Fact, IntakeProjection, SourceMessage
from asm.intake.projection import COMPLETE_TEXT, reduce_candidates
from asm.intake.templates import template_revision


class ClientIntakeView(DTO):
    revision: Literal["conversation_intake_v1"] = "conversation_intake_v1"
    service_id: str | None
    template_revision: str | None
    facts: tuple[Fact, ...] = Field(max_length=5)
    missing: tuple[str, ...] = Field(max_length=5)
    question: str | None
    sources: tuple[SourceMessage, ...] = Field(max_length=8)
    preliminary: Literal[True] = True


class IntakeContextView(PortfolioDeliveryContextView):
    intake: ClientIntakeView

    def messages(self) -> tuple[Message, ...]:
        return super().messages() + (Message(role="context", text=self.intake.model_dump_json()),)


class PreparedIntakeContext(PreparedPortfolioDeliveryContext):
    view: IntakeContextView = Field(repr=False)


class IntakeContextRead(PortfolioDeliveryContextRead):
    intake: IntakeProjection


class IntakeConversationAgent(PortfolioDeliveryConversationAgent):
    prompt_revision = "conversation_v7"
    intake: IntakeProjection

    def _project(self, snapshot: object, binding: ContextBinding) -> PreparedIntakeContext:
        base = super()._project(snapshot, binding)
        current = self.intake
        # Source identities are deliberately new in v7. Actor IDs/DurationCase are absent.
        facts = tuple(f.model_copy(update={"confirmed_by": None}) for f in current.facts)
        sources = tuple(s.model_copy(update={"text": s.text[:500]}) for s in current.sources[-8:])
        view = IntakeContextView(
            **base.view.model_dump(),
            intake=ClientIntakeView(
                service_id=current.service_id,
                template_revision=current.template_revision,
                facts=facts,
                missing=tuple(current.missing),
                question=current.question,
                sources=sources,
            ),
        )
        if (
            sum(len(m.text.encode("utf-8")) for m in view.messages())
            > self.config.limits.input_bytes
        ):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        self.shown = view
        return PreparedIntakeContext(
            binding=base.binding, snapshot_fingerprint=base.snapshot_fingerprint, view=view
        )

    def _outcome(
        self, *, reason: StopCode | None = None, candidate: AnyConversationResult | None = None
    ) -> AnyAgentOutcome:
        if candidate is not None:
            if not isinstance(candidate, (IntakeReply, IntakeHandoff, IntakeNoReply, IntakePhoto)):
                reason, candidate = "INVALID_OUTPUT", None
            else:
                try:
                    proposed = candidate.intake
                    service = (
                        next(
                            (
                                s
                                for s in self.active.bundle.services
                                if s.active and s.id == proposed.service_id
                            ),
                            None,
                        )
                        if self.active.bundle
                        else None
                    )
                    if proposed.service_id is not None and service is None:
                        raise ValueError("Service is not published")
                    if self.search.status == "CONFLICT" or (
                        service is None and proposed.category == "NEW_TATTOO"
                    ):
                        proposed = CandidateSet(
                            service_id=proposed.service_id,
                            category="OTHER_COMPLEX",
                            switch_request=proposed.switch_request,
                            facts=(),
                        )
                    if proposed.facts and (service is None or not template_revision(service)):
                        # Unbound fields cannot be persisted under an arbitrary old service.
                        proposed = proposed.model_copy(update={"facts": ()})
                    candidate = candidate.model_copy(update={"intake": proposed})
                    if any(
                        f.status == "observed"
                        and (
                            f.source.message_id != str(self.media_pin.message_id)
                            or f.source.analysis_id != str(self.media_pin.analysis_id)
                            or f.source.analysis_sha256 != self.media_pin.analysis_sha256
                        )
                        for f in candidate.intake.facts
                    ):
                        raise ValueError("Observation source does not match current analysis")
                    _, state, question = reduce_candidates(
                        self.intake, candidate.intake, self.active
                    )
                    body = candidate.model_dump(mode="json")
                    if state == "OWNER_HANDOFF" and candidate.intake.category != "FAQ_ONLY":
                        body = {
                            "kind": "handoff",
                            "text": None,
                            "reason": question or "Требуется решение мастера.",
                            "intake": body["intake"],
                        }
                    elif candidate.intake.category != "FAQ_ONLY" and state == "CLARIFY":
                        body = {
                            "kind": "reply",
                            "text": question,
                            "reason": None,
                            "intake": body["intake"],
                        }
                    elif candidate.intake.category != "FAQ_ONLY" and not isinstance(
                        candidate, IntakePhoto
                    ):
                        body = {
                            "kind": "reply",
                            "text": COMPLETE_TEXT,
                            "reason": None,
                            "intake": body["intake"],
                        }
                    from asm.ai.contracts import validate_conversation_result

                    candidate = validate_conversation_result(self.config, body)
                    if isinstance(candidate, IntakePhoto) and (
                        self.attested is None
                        or candidate.selection not in self.attested
                        or self._reads != 1
                    ):
                        raise ValueError("Photo not attested")
                except ValueError:
                    reason, candidate = "INVALID_OUTPUT", None
        return ConversationAgent._outcome(self, reason=reason, candidate=candidate)
