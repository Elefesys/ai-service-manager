"""Deterministic preview; SQL independently repeats these checks before publish."""

from pydantic import ValidationError

from asm.configuration.models import Bundle, ValidationIssue, ValidationResult


def validate_bundle(value: object) -> ValidationResult:
    try:
        bundle = Bundle.model_validate(value.model_dump() if isinstance(value, Bundle) else value)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return ValidationResult(
            valid=False,
            issues=[ValidationIssue(severity="ERROR", code="INVALID_SHAPE", path="bundle")],
        )
    issues: list[ValidationIssue] = []

    def issue(code: str, path: str, warning: bool = False) -> None:
        issues.append(
            ValidationIssue.model_validate(
                {
                    "severity": "WARNING" if warning else "ERROR",
                    "code": code,
                    "path": path,
                }
            )
        )

    if bundle.communication_style not in {"NEUTRAL", "WARM", "CONCISE"}:
        issue("INVALID_STYLE", "communication_style")
    if not any(s.active for s in bundle.services):
        issue("NO_ACTIVE_SERVICE", "services")
    for name, items in (
        ("services", bundle.services),
        ("rules", bundle.rules),
        ("faqs", bundle.faqs),
    ):
        if len({i.id for i in items}) != len(items):
            issue("DUPLICATE_ID", name)
    for service in bundle.services:
        prefix = f"services.{service.id}"
        if len({i.id for i in service.intake_fields}) != len(service.intake_fields):
            issue("DUPLICATE_ID", prefix + ".intake_fields")
        price, duration, deposit = service.price, service.duration, service.deposit
        if price.mode not in {"FIXED", "CONFIGURED_FORMULA", "OWNER_QUOTE"}:
            issue("INVALID_MODE", prefix + ".price")
        elif (
            price.mode != "FIXED"
            and price.amount_minor is not None
            or price.mode != "CONFIGURED_FORMULA"
            and price.formula_note is not None
            or price.amount_minor is not None
            and price.amount_minor < 1
        ):
            issue("INVALID_POLICY", prefix + ".price")
        elif price.mode != "FIXED" or price.amount_minor is None:
            issue("OWNER_HANDOFF", prefix + ".price", True)
        if duration.mode not in {"FIXED", "CONFIGURED_RULE", "OWNER_DEFINED"}:
            issue("INVALID_MODE", prefix + ".duration")
        elif (
            duration.mode != "FIXED"
            and duration.minutes is not None
            or duration.mode != "CONFIGURED_RULE"
            and duration.rule_note is not None
            or duration.minutes is not None
            and not 1 <= duration.minutes <= 10080
        ):
            issue("INVALID_POLICY", prefix + ".duration")
        elif duration.mode != "FIXED" or duration.minutes is None:
            issue("OWNER_HANDOFF", prefix + ".duration", True)
        if deposit.mode not in {"NONE", "FIXED_DEPOSIT", "PERCENT_DEPOSIT", "FULL_PREPAYMENT"}:
            issue("INVALID_MODE", prefix + ".deposit")
        elif (
            deposit.mode != "FIXED_DEPOSIT"
            and deposit.amount_minor is not None
            or deposit.mode != "PERCENT_DEPOSIT"
            and deposit.percent is not None
            or deposit.amount_minor is not None
            and deposit.amount_minor < 1
            or deposit.percent is not None
            and not 1 <= deposit.percent <= 100
        ):
            issue("INVALID_POLICY", prefix + ".deposit")
        elif (
            deposit.mode == "FIXED_DEPOSIT"
            and deposit.amount_minor is None
            or deposit.mode == "PERCENT_DEPOSIT"
            and deposit.percent is None
        ):
            issue("OWNER_HANDOFF", prefix + ".deposit", True)
    service_ids = {s.id for s in bundle.services}
    for rule in bundle.rules:
        path = f"rules.{rule.id}"
        if rule.service_id is not None and rule.service_id not in service_ids:
            issue("INVALID_REFERENCE", path + ".service_id")
        if (
            rule.kind not in {"MIN_AGE", "OWNER_HANDOFF"}
            or rule.kind == "MIN_AGE"
            and not (type(rule.value) is int and 1 <= rule.value <= 120)
            or rule.kind == "OWNER_HANDOFF"
            and type(rule.value) is not bool
        ):
            issue("INVALID_RULE", path)
    if any(
        a.model_dump_json() != b.model_dump_json()
        and a.kind == b.kind
        and (a.service_id == b.service_id or a.service_id is None or b.service_id is None)
        and (
            a.service_id == b.service_id or type(a.value) is not type(b.value) or a.value != b.value
        )
        for a in bundle.rules
        for b in bundle.rules
    ):
        issue("CONFLICTING_RULES", "rules")
    for faq in bundle.faqs:
        path = f"faqs.{faq.id}"
        if faq.service_id is not None and faq.service_id not in service_ids:
            issue("INVALID_REFERENCE", path + ".service_id")
        if not faq.confirmed or not faq.source.strip():
            issue("UNCONFIRMED_FAQ", path)
        if len(set(faq.rule_ids)) != len(faq.rule_ids) or any(
            not any(
                r.id == ref and (r.service_id is None or r.service_id == faq.service_id)
                for r in bundle.rules
            )
            for ref in faq.rule_ids
        ):
            issue("INVALID_REFERENCE", path + ".rule_ids")
    return ValidationResult(valid=not any(i.severity == "ERROR" for i in issues), issues=issues)
