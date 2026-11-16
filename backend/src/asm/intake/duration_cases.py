"""Bounded owner comparison, no estimates or aggregation of case times."""

from asm.intake.models import CaseMatch, DurationCase


def compare_cases(cases: list[DurationCase], query: dict[str, str]) -> list[CaseMatch]:
    selected = []
    for case in cases:
        if case.state != "CONFIRMED" or not case.source_current:
            continue
        matches, differences, unknown = [], [], []
        for field in ("placement", "style", "detail", "fill"):
            value = getattr(case.data, field)
            if not value or not query.get(field):
                unknown.append(field)
            elif value.casefold() == query[field].casefold():
                matches.append(field)
            else:
                differences.append(field)
        selected.append(
            CaseMatch(case=case, matches=matches, differences=differences, unknown=unknown)
        )
    return sorted(selected, key=lambda m: (-len(m.matches), m.case.case_id))[:5]
