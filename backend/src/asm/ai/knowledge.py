"""Versioned, bounded projections of owner-published configuration, never draft data."""

import re
import unicodedata as _unicodedata
from hashlib import sha256 as _sha256
from typing import Annotated as _Annotated
from typing import Literal, Self, cast
from uuid import UUID

from pydantic import Field, model_validator

from asm.ai.contracts import DTO
from asm.billing.validation import LimitDecimal
from asm.billing.validation import Timestamp as _Timestamp
from asm.configuration.models import FAQ, ActiveProjection, Rule, Service
from asm.configuration.models import Identifier as _Slug
from asm.configuration.models import Nonblank as _Nonblank
from asm.configuration.models import Text as _ScalarText
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


# M5.2B: the persisted references contain no source text.

_SearchDigest = _Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SearchProfile = Literal["polza_openai_text_embedding3small_1536_cosine_v1"]


class SearchPin(DTO):
    projection_revision: Literal["business_knowledge_search_v1"]
    business_id: UUID
    release_id: UUID | None
    activation_version: LimitDecimal
    build_id: UUID | None
    profile_id: SearchProfile
    preprocessing: Literal["nfc_crlf_ascii_trim_v1"]
    visible_revisions_sha256: _SearchDigest
    next_transition_at: _Timestamp | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (
            (self.activation_version == "0") != (self.release_id is None)
            or self.release_id is None
            and self.build_id is not None
        ):
            raise ValueError("Invalid search publication pin")
        return self


class SearchReference(DTO):
    chunk_id: UUID
    sha256: _SearchDigest
    rank: int = Field(ge=1, le=4)
    score: float = Field(ge=-1, le=1)


class SearchConflict(DTO):
    claim_key: _Slug
    revision_ids: tuple[UUID, ...] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def unique_revisions(self) -> Self:
        if len(set(self.revision_ids)) != len(self.revision_ids):
            raise ValueError("Duplicate conflict revision")
        return self


class _SearchResult(DTO):
    revision: Literal["business_knowledge_search_result_v1"]
    profile_id: SearchProfile
    query_sha256: _SearchDigest
    status: Literal["RESULTS", "EMPTY", "CONFLICT"]
    reason_code: (
        Literal[
            "NO_ACTIVE_BUILD", "NO_QUERY", "NO_ELIGIBLE_SOURCE", "NO_MATCH", "OWNER_LABEL_CONFLICT"
        ]
        | None
    )
    conflicts: tuple[SearchConflict, ...] = Field(max_length=8)

    def check_items(self, references: tuple[SearchReference, ...]) -> None:
        if (
            len({r.chunk_id for r in references}) != len(references)
            or [r.rank for r in references] != list(range(1, len(references) + 1))
            or len({c.claim_key for c in self.conflicts}) != len(self.conflicts)
        ):
            raise ValueError("Invalid search order")
        if self.status == "RESULTS":
            valid = bool(references) and not self.conflicts and self.reason_code is None
        elif self.status == "EMPTY":
            valid = (
                not references
                and not self.conflicts
                and self.reason_code
                in {"NO_ACTIVE_BUILD", "NO_QUERY", "NO_ELIGIBLE_SOURCE", "NO_MATCH"}
            )
        else:
            valid = (
                not references
                and bool(self.conflicts)
                and self.reason_code == "OWNER_LABEL_CONFLICT"
            )
        if not valid:
            raise ValueError("Incoherent search result")


class SearchRefs(_SearchResult):
    references: tuple[SearchReference, ...] = Field(max_length=4)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self.check_items(self.references)
        return self


class SearchFragment(SearchReference):
    source_id: UUID
    revision_id: UUID
    ordinal: int = Field(ge=0, le=3)
    text: _ScalarText = Field(min_length=1, max_length=512, repr=False)
    title: _Nonblank = Field(max_length=120)
    source_label: _Nonblank = Field(max_length=120)
    author_label: _ScalarText | None = Field(max_length=80)
    service_id: _Slug | None
    category: _Slug | None
    claim_key: _Slug | None
    authority: Literal["OWNER_CONFIRMED_EXPLANATION"]

    @model_validator(mode="after")
    def content_hash(self) -> Self:
        raw = self.text.encode("utf-8")
        if len(raw) > 512 or _sha256(raw).hexdigest() != self.sha256:
            raise ValueError("Invalid fragment content")
        return self

    def reference(self) -> SearchReference:
        return SearchReference(
            chunk_id=self.chunk_id, sha256=self.sha256, rank=self.rank, score=self.score
        )


class SearchProjection(_SearchResult):
    fragments: tuple[SearchFragment, ...] = Field(max_length=4)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        self.check_items(tuple(f.reference() for f in self.fragments))
        return self

    def refs(self) -> SearchRefs:
        return SearchRefs.model_validate(
            self.model_dump(exclude={"fragments"})
            | {"references": tuple(f.reference() for f in self.fragments)}
        )


class SearchKnowledgeView(DTO):
    """Only authorized public source provenance and the existing complete policy."""

    revision: Literal["business_knowledge_v2"] = "business_knowledge_v2"
    configuration: KnowledgeView
    search: SearchProjection
    fragments_omitted: int = Field(ge=0, le=3)
    structured_rules_authoritative: Literal[True] = True


def reduce_search_view(view: SearchKnowledgeView) -> SearchKnowledgeView | None:
    """Drop complete explanatory entries; never a policy or the last matched fragment."""
    config, search = view.configuration, view.search
    if config.faqs:
        limits = config.limitations
        if "FAQ_SELECTION_BOUNDED" not in limits:
            limits += ("FAQ_SELECTION_BOUNDED",)
        config = KnowledgeView.model_validate(
            config.model_dump()
            | {
                "faqs": config.faqs[:-1],
                "faqs_omitted": config.faqs_omitted + 1,
                "limitations": limits,
            }
        )
    elif len(search.fragments) > 1:
        search = SearchProjection.model_validate(
            search.model_dump() | {"fragments": search.fragments[:-1]}
        )
        return SearchKnowledgeView(
            configuration=config, search=search, fragments_omitted=view.fragments_omitted + 1
        )
    else:
        return None
    return SearchKnowledgeView(
        configuration=config, search=search, fragments_omitted=view.fragments_omitted
    )


def project_search_knowledge(
    active: ActiveProjection,
    pin: KnowledgePin,
    search_pin: SearchPin,
    projection: SearchProjection,
    query: str,
) -> SearchKnowledgeView:
    search_pin = SearchPin.model_validate(search_pin)
    projection = SearchProjection.model_validate(projection)
    if (
        search_pin.business_id != pin.business_id
        or search_pin.release_id != pin.release_id
        or search_pin.activation_version != pin.activation_version
        or search_pin.profile_id != projection.profile_id
    ):
        raise KnowledgeFailure("KNOWLEDGE_STALE")
    canonical = _unicodedata.normalize("NFC", query.replace("\r\n", "\n")).strip(" \t\n\r\f\v")
    if _sha256(canonical.encode("utf-8")).hexdigest() != projection.query_sha256:
        raise KnowledgeFailure("KNOWLEDGE_STALE")
    view = SearchKnowledgeView(
        configuration=project_knowledge(active, pin, query), search=projection, fragments_omitted=0
    )
    while len(view.model_dump_json().encode("utf-8")) > 6144:
        reduced = reduce_search_view(view)
        if reduced is None:
            raise KnowledgeFailure("KNOWLEDGE_TOO_LARGE")
        view = reduced
    return view
