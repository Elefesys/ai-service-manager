"""Immutable commercial terms and their client-facing representation."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from asm.billing.validation import CanonicalUUID, PositiveDecimal, Timestamp
from asm.configuration.models import (
    ConfigurationModel,
    DepositPolicy,
    Identifier,
    Nonblank,
    OccupiedMinutes,
    PriceMinor,
    Rule,
)
from asm.intake.models import Digest, Fact, FieldId
from asm.service_requests.approvals import ProvisionalPriceRange
from asm.service_requests.assessment import ComplexWork, Reason, confirmed
from asm.service_requests.models import IntentSource
from asm.service_requests.pricing import PriceReason

QuoteCode = Annotated[str, Field(pattern=r"^Q-[0-9A-F]{10}$")]
ClientText = Annotated[Nonblank, Field(max_length=4096)]
QuoteDeliveryStatus = Literal[
    "PREPARED", "QUEUED", "DISPATCHING", "HELD", "SENT", "UNKNOWN", "FAILED"
]
QuoteStatus = Literal[QuoteDeliveryStatus, "NEEDS_CLARIFICATION"]
StatusReason = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]


class QuoteCondition(Rule):
    kind: Literal["MAX_SIZE_MM", "MIN_AGE"]

    @model_validator(mode="after")
    def published_limit(self) -> Self:
        maximum = 120 if self.kind == "MIN_AGE" else 1000
        if type(self.value) is not int or not 1 <= self.value <= maximum:
            raise ValueError("Quote condition requires a published numeric limit")
        return self


class QuoteMaterial(ConfigurationModel):
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    request_id: CanonicalUUID
    request_revision: PositiveDecimal
    service_id: Identifier
    service_name: Nonblank = Field(max_length=100)
    facts: list[Fact] = Field(max_length=5)
    intent_source: IntentSource
    complex_work: ComplexWork | None
    release_id: CanonicalUUID
    activation_version: PositiveDecimal
    assessment_id: CanonicalUUID
    assessment_reason: Reason
    price_calculation_id: CanonicalUUID
    price_reason: PriceReason
    approval_id: CanonicalUUID | None
    decision_id: CanonicalUUID | None
    price_reference_id: CanonicalUUID
    duration_reference_id: CanonicalUUID
    currency: Literal["RUB"]
    amount_minor: PriceMinor | None
    price_range: ProvisionalPriceRange | None
    occupied_minutes: OccupiedMinutes
    deposit_terms_version: CanonicalUUID
    deposit: DepositPolicy
    conditions: list[QuoteCondition] = Field(max_length=12)

    @model_validator(mode="after")
    def coherent_terms(self) -> Self:
        if (self.amount_minor is None) == (self.price_range is None):
            raise ValueError("Quote requires one price representation")
        price_floor = (
            self.price_range.lower_minor if self.price_range is not None else self.amount_minor
        )
        deposit = self.deposit
        if deposit.mode == "FIXED_DEPOSIT":
            valid = (
                deposit.amount_minor is not None
                and price_floor is not None
                and 1 <= deposit.amount_minor <= price_floor
                and deposit.percent is None
            )
        elif deposit.mode == "PERCENT_DEPOSIT":
            valid = (
                self.amount_minor is not None
                and deposit.amount_minor is None
                and deposit.percent is not None
                and 1 <= deposit.percent <= 100
            )
        else:
            valid = (
                deposit.amount_minor is None
                and deposit.percent is None
                and (
                    deposit.mode == "NONE"
                    or deposit.mode == "FULL_PREPAYMENT"
                    and self.amount_minor is not None
                )
            )
        if not valid:
            raise ValueError("Quote price conflicts with the published prepayment terms")
        if (
            self.deposit_terms_version != self.release_id
            or (self.approval_id is None) != (self.decision_id is None)
            or self.price_reference_id not in {self.price_calculation_id, self.decision_id}
            or self.duration_reference_id not in {self.assessment_id, self.decision_id}
            or self.price_range is not None
            and self.price_reference_id != self.price_calculation_id
            or any(rule.service_id not in (self.service_id, None) for rule in self.conditions)
            or self.complex_work is not None
            and not self.complex_work.source_current
        ):
            raise ValueError("Incoherent quote authority")
        return self


class QuoteInput(ConfigurationModel):
    quote_id: CanonicalUUID
    code: QuoteCode
    expires_at: Timestamp
    material: QuoteMaterial


class QuoteVersion(QuoteInput):
    version: PositiveDecimal
    created_at: Timestamp
    terms_sha256: Digest
    text: ClientText = Field(repr=False)

    @model_validator(mode="after")
    def expiry_and_code(self) -> Self:
        if self.created_at >= self.expires_at or not self.text.endswith(f"\nПринимаю {self.code}"):
            raise ValueError("Quote version or acceptance phrase mismatch")
        return self


class QuoteDeliverySnapshot(ConfigurationModel):
    quote: QuoteVersion
    status: QuoteDeliveryStatus
    reason: StatusReason | None


class QuoteDeliveryView(ConfigurationModel):
    quote: QuoteVersion | None
    status: QuoteStatus | None
    reason: StatusReason | None
    previous: QuoteDeliverySnapshot | None = Field(
        default=None, exclude_if=lambda snapshot: snapshot is None
    )

    @model_validator(mode="after")
    def coherent_status(self) -> Self:
        if (self.quote is None) != (self.status in {None, "NEEDS_CLARIFICATION"}):
            raise ValueError("Delivery status requires a quote version")
        if self.previous is not None and (self.status, self.reason) != (
            "NEEDS_CLARIFICATION",
            "EXACT_PRICE_REQUIRED",
        ):
            raise ValueError("Previous delivery requires an exact price clarification")
        return self


_FIELD_LABELS: dict[FieldId, str] = {
    "idea": "Идея",
    "placement": "Место",
    "approximate_size": "Размер",
    "style": "Стиль",
    "references": "Референсы",
}


def _money(amount_minor: int) -> str:
    rubles, kopecks = divmod(amount_minor, 100)
    whole = f"{rubles:,}".replace(",", "\u202f")
    return f"{whole},{kopecks:02d}" if kopecks else whole


def render_quote(quote: QuoteInput) -> str:
    material = quote.material
    service = " ".join(material.service_name.split())
    lines = [f"Предложение по работе «{service}»"]
    if material.complex_work is not None:
        work = material.complex_work.category
        scope = "перекрытие татуировки" if work == "COVER_UP" else "сложная работа"
        lines.append(f"Объём — {scope}.")
    facts = {fact.field: fact for fact in material.facts if confirmed(fact)}
    for field, label in _FIELD_LABELS.items():
        if field in facts:
            value = " ".join(facts[field].value.split())
            lines.append(f"{label} — {value}")
    price_range = material.price_range
    if price_range is not None:
        low, high = _money(price_range.lower_minor), _money(price_range.upper_minor)
        lines.append(f"Предварительный диапазон цены — {low}–{high} ₽.")
    elif material.amount_minor is not None:
        lines.append(f"Цена — {_money(material.amount_minor)} ₽.")
    lines.append(f"Длительность следующего сеанса — {material.occupied_minutes} мин.")
    deposit = material.deposit
    if deposit.mode == "FIXED_DEPOSIT" and deposit.amount_minor is not None:
        lines.append(f"Предоплата — {_money(deposit.amount_minor)} ₽.")
    elif deposit.mode == "PERCENT_DEPOSIT":
        lines.append(f"Предоплата — {deposit.percent}% от указанной цены.")
    elif deposit.mode == "FULL_PREPAYMENT":
        lines.append("Предоплата — полная стоимость работы.")
    else:
        lines.append("Предоплата не требуется.")
    # The published release can declare equally valued general and service rules.
    for kind, limit in dict.fromkeys((rule.kind, rule.value) for rule in material.conditions):
        if kind == "MIN_AGE":
            lines.append(f"Минимальный возраст — {limit}.")
        else:
            lines.append(f"Максимальный размер — {limit} мм.")
    deadline = datetime.fromisoformat(quote.expires_at).strftime("%d.%m.%Y %H:%M:%S UTC")
    lines.extend(
        (
            f"Предложение действует до {deadline}.",
            "",
            "Чтобы принять предложение, отправьте команду",
            f"Принимаю {quote.code}",
        )
    )
    return "\n".join(lines)
