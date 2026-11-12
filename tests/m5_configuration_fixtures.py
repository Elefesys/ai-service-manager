"""Small fictional Business bundles; these are never a real master's defaults."""

from copy import deepcopy


def configuration_bundle(kind="tattoo"):
    """Fresh values let API/unit/PG carriers exercise the same two small bundles."""
    value = {
        "schema_version": 1,
        "communication_style": "WARM" if kind == "ceramics" else "NEUTRAL",
        "services": [
            {
                "id": "consultation",
                "name": "Synthetic ceramic consultation"
                if kind == "ceramics"
                else "Synthetic tattoo consultation",
                "description": "Fictional pilot fixture, owner review required.",
                "active": True,
                "intake_fields": [{"id": "idea", "label": "Your idea", "required": True}],
                "price": {"mode": "FIXED", "amount_minor": 120000, "formula_note": None},
                "duration": {"mode": "FIXED", "minutes": 90, "rule_note": None},
                "deposit": {"mode": "FIXED_DEPOSIT", "amount_minor": 20000, "percent": None},
            }
        ],
        "rules": [{"id": "age", "service_id": None, "kind": "MIN_AGE", "value": 18}],
        "faqs": [
            {
                "id": "preparation",
                "service_id": "consultation",
                "question": "How should I prepare?",
                "answer": "Bring your idea; the owner confirms the individual details.",
                "source": "Synthetic owner-confirmed instruction",
                "confirmed": True,
                "rule_ids": ["age"],
            }
        ],
    }
    if kind == "ceramics":
        service = value["services"][0]
        service["price"] = {
            "mode": "CONFIGURED_FORMULA",
            "amount_minor": None,
            "formula_note": "Owner supplies the future bounded formula.",
        }
        service["duration"] = {
            "mode": "CONFIGURED_RULE",
            "minutes": None,
            "rule_note": "Owner confirms the future duration rule.",
        }
        service["deposit"] = {"mode": "PERCENT_DEPOSIT", "amount_minor": None, "percent": 30}
    return deepcopy(value)
