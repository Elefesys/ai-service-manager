"""The owner selects evidence from intake. PostgreSQL supplies the saved facts."""

from typing import Literal, Self

from pydantic import Field, model_validator

from asm.billing.validation import CanonicalUUID, LimitDecimal, PositiveDecimal
from asm.configuration.models import ConfigurationModel, Identifier, Nonblank
from asm.intake.models import Digest, Fact, FieldId


class IntentSource(ConfigurationModel):
    message_id: CanonicalUUID
    source_version: Digest


class ServiceRequestCommand(ConfigurationModel):
    expected_version: LimitDecimal
    expected_fingerprint: Digest
    intent_source: IntentSource
    fields: list[FieldId] = Field(max_length=5)
    selection: Literal["ONE_WORK", "UNCLEAR"]

    @model_validator(mode="after")
    def unique_fields(self) -> Self:
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("Duplicate selected field")
        return self


class ServiceRequestRevisionCommand(ConfigurationModel):
    expected_revision: PositiveDecimal
    expected_version: LimitDecimal
    expected_fingerprint: Digest
    field: FieldId
    source: IntentSource
    selection: Literal["ONE_WORK", "UNCLEAR"]


class ServiceRequestReceipt(ConfigurationModel):
    request_id: CanonicalUUID


class ServiceRequestCardSummary(ConfigurationModel):
    request_id: CanonicalUUID
    revision: PositiveDecimal
    service_name: Nonblank = Field(max_length=100)
    intent_source: IntentSource
    idea: Nonblank | None = Field(max_length=300)


class ServiceRequestCards(ConfigurationModel):
    items: list[ServiceRequestCardSummary]


class ServiceRequestDraft(ConfigurationModel):
    request_id: CanonicalUUID
    workspace_id: CanonicalUUID
    business_id: CanonicalUUID
    conversation_id: CanonicalUUID
    client_id: CanonicalUUID
    service_id: Identifier
    service_name: Nonblank = Field(max_length=100)
    release_id: CanonicalUUID
    template_revision: Literal["tattoo_intake_v1"]
    revision: PositiveDecimal
    state: Literal["DRAFT"]
    intent_source: IntentSource
    facts: list[Fact] = Field(max_length=5)
    missing: list[FieldId] = Field(max_length=5)
    conflicts: list[FieldId] = Field(max_length=5)
    question: Nonblank | None = Field(max_length=300)
