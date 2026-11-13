"""Versioned, bounded projections of owner-published configuration, never draft data."""

import re
from typing import Literal, Self, cast
from uuid import UUID

from pydantic import Field, model_validator

from asm.ai.contracts import DTO
from asm.billing.validation import LimitDecimal
from asm.configuration.models import FAQ, ActiveProjection, Rule, Service
from asm.configuration.validation import validate_bundle

KnowledgeCode = Literal["INVALID_KNOWLEDGE", "KNOWLEDGE_STALE", "KNOWLEDGE_TOO_LARGE"]


class KnowledgeFailure(Exception):
    def __init__(self, code: KnowledgeCode):
        self.code = code
        super().__init__(code)


class KnowledgePin(DTO):
    """Private durable expected state; the authority port must attest its freshness."""

    projection_revision: Literal["business_knowledge_v1"]
    business_id: UUID
    release_id: UUID | None
    activation_version: LimitDecimal

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.activation_version == "0") != (self.release_id is None):
            raise ValueError("Invalid publication pin")
        return self


class PublishedFAQ(DTO):
    fact: FAQ
    authority: Literal["OWNER_CONFIRMED_EXPLANATION"] = "OWNER_CONFIRMED_EXPLANATION"
    selection: Literal["KEYWORD_MATCH", "BOUNDED_DEFAULT"]


class KnowledgeView(DTO):
    """Public facts/provenance only: no tenant, release UUID, publisher or private history."""

    revision: Literal["business_knowledge_v1"] = "business_knowledge_v1"
    status: Literal["UNPUBLISHED", "PUBLISHED"]
    activation_version: LimitDecimal
    source_draft_version: LimitDecimal | None
    authority: Literal["OWNER_PUBLISHED_CONFIGURATION"] = "OWNER_PUBLISHED_CONFIGURATION"
    structured_rules_authoritative: Literal[True] = True
    communication_style: Literal["NEUTRAL", "WARM", "CONCISE"] | None
    services: tuple[Service, ...] = Field(max_length=8)
    rules: tuple[Rule, ...] = Field(max_length=12)
    faqs: tuple[PublishedFAQ, ...] = Field(max_length=4)
    faqs_omitted: int = Field(ge=0, le=12)
    limitations: tuple[
        Literal["NO_PUBLICATION", "FAQ_SELECTION_BOUNDED", "NO_INDIVIDUAL_QUOTE_OR_BOOKING"], ...
    ]


def _words(value: str) -> set[str]:
    # Whole Unicode words; no provider/embedding, regex supplied by the model or I/O.
    return {w for w in re.findall(r"[^\W_]+", value.casefold()) if len(w) > 1}


def project_knowledge(
    value: ActiveProjection, pin: KnowledgePin, query: str, *, max_bytes: int = 6144
) -> KnowledgeView:
    """Only an authority-supplied active projection may be passed to this function.

    Identity equality validates consistency, never supplies the authorization. Keep
    every active structured policy intact; select up to four complete FAQ entries.
    """
    try:
        value = ActiveProjection.model_validate(value)
        pin = KnowledgePin.model_validate(pin)
        if (
            str(pin.business_id) != value.business_id
            or (str(pin.release_id) if pin.release_id else None) != value.release_id
            or pin.activation_version != value.activation_version
        ):
            raise KnowledgeFailure("KNOWLEDGE_STALE")
        if value.bundle is None:
            return KnowledgeView(
                status="UNPUBLISHED",
                activation_version="0",
                source_draft_version=None,
                communication_style=None,
                services=(),
                rules=(),
                faqs=(),
                faqs_omitted=0,
                limitations=("NO_PUBLICATION", "NO_INDIVIDUAL_QUOTE_OR_BOOKING"),
            )
        if not validate_bundle(value.bundle).valid:
            raise KnowledgeFailure("INVALID_KNOWLEDGE")
        services = tuple(s for s in value.bundle.services if s.active)
        ids = {s.id for s in services}
        rules = tuple(r for r in value.bundle.rules if r.service_id is None or r.service_id in ids)
        eligible = [f for f in value.bundle.faqs if f.service_id is None or f.service_id in ids]
        query_words = _words(query)
        ranked = sorted(
            enumerate(eligible),
            key=lambda pair: (
                -len(query_words & _words(pair[1].question + " " + pair[1].answer)),
                pair[0],
            ),
        )
        selected = tuple(
            PublishedFAQ(
                fact=faq,
                selection="KEYWORD_MATCH"
                if query_words & _words(faq.question + " " + faq.answer)
                else "BOUNDED_DEFAULT",
            )
            for _, faq in ranked[:4]
        )
        omitted = len(eligible) - len(selected)
        limitations: tuple[
            Literal["NO_PUBLICATION", "FAQ_SELECTION_BOUNDED", "NO_INDIVIDUAL_QUOTE_OR_BOOKING"],
            ...,
        ] = ("NO_INDIVIDUAL_QUOTE_OR_BOOKING",)
        if omitted:
            limitations += ("FAQ_SELECTION_BOUNDED",)
        view = KnowledgeView(
            status="PUBLISHED",
            activation_version=pin.activation_version,
            source_draft_version=value.source_draft_version,
            communication_style=cast(
                Literal["NEUTRAL", "WARM", "CONCISE"], value.bundle.communication_style
            ),
            services=services,
            rules=rules,
            faqs=selected,
            faqs_omitted=omitted,
            limitations=limitations,
        )
        if len(view.model_dump_json().encode("utf-8")) > max_bytes:
            raise KnowledgeFailure("KNOWLEDGE_TOO_LARGE")
        return view
    except KnowledgeFailure:
        raise
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        raise KnowledgeFailure("INVALID_KNOWLEDGE") from None
