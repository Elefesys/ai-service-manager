"""Owner-facing internal results from the published price policy and saved facts."""

from typing import Literal, Self

from pydantic import Field, model_validator

from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal
from asm.configuration.models import ConfigurationModel, PriceMinor, PricePolicy, SizeMillimetres
from asm.intake.models import Fact


class PriceCommand(ConfigurationModel):
    expected_revision: PositiveDecimal


class PriceCalculation(ConfigurationModel):
    calculation_id: CanonicalUUID
    request_id: CanonicalUUID
    request_revision: PositiveDecimal
    release_id: CanonicalUUID | None
    activation_version: LimitDecimal
    currency: Literal["RUB"]
    current: bool
    policy: PricePolicy | None
    outcome: Literal["EXACT", "RANGE", "NEEDS_INPUT", "NEEDS_HUMAN"]
    authority: Literal["CONFIRMED", "PROVISIONAL"] | None
    reason: Literal[
        "FIXED_PRICE",
        "SIZE_FORMULA",
        "SIZE_REQUIRED",
        "SIZE_OUTSIDE_RULE",
        "OWNER_QUOTE",
        "PRICE_UNPUBLISHED",
        "SERVICE_UNAVAILABLE",
    ]
    amount_minor: PriceMinor | None
    lower_minor: PriceMinor | None
    upper_minor: PriceMinor | None
    size_mm: SizeMillimetres | None
    steps: SizeMillimetres | None
    size_fact: Fact | None

    @model_validator(mode="after")
    def monetary_basis(self) -> Self:
        if self.outcome == "EXACT":
            valid = (
                self.authority == "CONFIRMED"
                and self.amount_minor is not None
                and self.lower_minor is None
                and self.upper_minor is None
            )
        elif self.outcome == "RANGE":
            valid = (
                self.authority == "PROVISIONAL"
                and self.amount_minor is None
                and self.lower_minor is not None
                and self.upper_minor is not None
                and self.lower_minor < self.upper_minor
            )
        else:
            valid = (
                self.authority is None
                and self.amount_minor is None
                and self.lower_minor is None
                and self.upper_minor is None
            )
        if not valid:
            raise ValueError("Inconsistent price authority and amount")
        return self


class PriceHistory(ConfigurationModel):
    items: list[PriceCalculation] = Field(max_length=10)
    next_before_id: CanonicalUUID | None
