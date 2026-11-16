"""Explicit field identifiers bind a template; labels never select business logic."""

from asm.configuration.models import IntakeField, Service

TATTOO_FIELDS = (
    ("idea", "Идея и сюжет", True),
    ("placement", "Место на теле", True),
    ("approximate_size", "Примерный размер со слов клиента", True),
    ("style", "Стиль", True),
    ("references", "Референсы, если доступны", False),
)


def tattoo_fields() -> list[IntakeField]:
    return [
        IntakeField(id=i, label=label, required=required) for i, label, required in TATTOO_FIELDS
    ]


def template_revision(service: Service) -> str | None:
    fields = [(f.id, f.required) for f in service.intake_fields]
    return "tattoo_intake_v1" if fields == [(i, r) for i, _, r in TATTOO_FIELDS] else None
