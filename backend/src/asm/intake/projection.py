"""Deterministic candidate reduction; SQL independently repeats admission at commit."""

from asm.configuration.models import ActiveProjection
from asm.intake.models import CandidateSet, Fact, IntakeProjection
from asm.intake.templates import template_revision

COMPLETE_TEXT = "Предварительные сведения собраны. Мастер проверит детали; цена, длительность и запись пока не согласованы."
AMBIGUOUS_QUESTION = "Уточните, к какой услуге или отдельной идее относится сообщение."
OWNER_QUESTION = "Мастер, уточните, можно ли продолжить консультацию по этому запросу."
QUESTIONS = {
    "idea": "Какую идею или сюжет вы хотите?",
    "placement": "На каком месте тела вы хотите татуировку?",
    "approximate_size": "Какой примерный размер вы представляете, в сантиметрах?",
    "style": "Какой стиль вам нравится?",
}


def reduce_candidates(
    current: IntakeProjection, candidates: CandidateSet, active: ActiveProjection
) -> tuple[list[Fact], str, str | None]:
    if candidates.category == "FAQ_ONLY":
        return current.facts, current.status, current.question
    if candidates.category == "AMBIGUOUS":
        return current.facts, "CLARIFY", AMBIGUOUS_QUESTION
    if candidates.switch_request and not any(f.status == "client-stated" for f in candidates.facts):
        raise ValueError("Request change requires current client evidence")
    if (
        current.service_id is not None
        and current.service_id != candidates.service_id
        and not candidates.switch_request
    ):
        raise ValueError("Request change requires clarification")
    bundle = active.bundle
    service = (
        next((s for s in bundle.services if s.id == candidates.service_id and s.active), None)
        if bundle
        else None
    )
    if not service or not bundle or not template_revision(service):
        return [], "OWNER_HANDOFF", "Мастер, уточните подходящую услугу и правила сбора данных."
    facts = {f.field: f for f in ([] if candidates.switch_request else current.facts)}
    for candidate in candidates.facts:
        source = next(
            (
                s
                for s in current.sources
                if s.message_id == candidate.source.message_id
                and s.source_version == candidate.source.source_version
            ),
            None,
        )
        if source is None:
            raise ValueError("Source is not current")
        if candidate.status == "client-stated" and (
            candidate.source.analysis_id is not None
            or not candidate.source.quote
            or candidate.source.quote not in source.text
            or candidate.value not in candidate.source.quote
        ):
            raise ValueError("Explicit evidence required")
        if candidate.status == "observed" and (
            candidate.source.analysis_id is None
            or candidate.field in {"approximate_size", "placement"}
        ):
            raise ValueError("Unscaled image cannot establish dimensions or placement")
        old = facts.get(candidate.field)
        if (
            old is not None
            and old.value == candidate.value
            and (old.status != "observed" or old.conflict or candidate.status == "observed")
        ):
            # Repeating evidence cannot remove the owner's confirmation or
            # resolve an already recorded conflict.
            continue
        if old is not None and old.value != candidate.value and not candidate.explicit_correction:
            facts[candidate.field] = old.model_copy(update={"conflict": True})
        else:
            facts.pop(candidate.field, None)
            facts[candidate.field] = Fact(
                field=candidate.field,
                value=candidate.value,
                status=candidate.status,
                source=candidate.source,
                confirmed_by=None,
                conflict=False,
            )
    if candidates.category in {"COVER_UP", "OTHER_COMPLEX"} or any(
        r.kind == "OWNER_HANDOFF" and r.value is True and r.service_id in {None, service.id}
        for r in bundle.rules
    ):
        return list(facts.values()), "OWNER_HANDOFF", OWNER_QUESTION
    conflicts = [f.field for f in facts.values() if f.conflict]
    missing = [
        f.id
        for f in service.intake_fields
        if f.required
        and (f.id not in facts or facts[f.id].status == "observed" or facts[f.id].conflict)
    ]
    if conflicts:
        return list(facts.values()), "CLARIFY", f"Уточните противоречивое поле: {conflicts[0]}."
    if missing:
        return list(facts.values()), "CLARIFY", QUESTIONS[missing[0]]
    return list(facts.values()), "PRELIMINARILY_COMPLETE", None
