"""Deterministic comparisons between validated user facts and rule thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.question_plan import QuestionPlan
from evidence_review.retrieval.conditional import Measure, extract_measures
from evidence_review.retrieval.facets import FacetCoverageReport
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle


@dataclass(frozen=True, slots=True)
class FactRuleComparison:
    comparison_id: str
    issue_id: str
    facet_id: str
    operator: str
    fact_value: str
    threshold_value: str
    unit: str
    satisfied: bool
    evidence_ids: tuple[str, ...]
    result_hash: str


_COMPARISON_CONFIG: dict[str, tuple[str, str, bool | None]] = {
    "minimum-area-threshold": ("area_m2", ">=", None),
    "distance-normal-threshold": ("length_m", "<=", False),
    "distance-conditional-threshold": ("length_m", "<=", True),
    "semi-industrial-far-threshold": ("percent", "<=", None),
}


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _measures_for_dimension(text: str, dimension: str) -> tuple[Measure, ...]:
    return tuple(item for item in extract_measures(text) if item.dimension == dimension)


def _select_fact(text: str, dimension: str) -> Measure:
    values = _measures_for_dimension(text, dimension)
    if len(values) != 1:
        raise ValueError(
            f"fact must contain exactly one {dimension} measure, found {len(values)}"
        )
    return values[0]


def _select_threshold(
    text: str,
    dimension: str,
    operator: str,
    conditional: bool | None,
) -> Measure:
    values = [
        item
        for item in _measures_for_dimension(text, dimension)
        if conditional is None or item.conditional is conditional
    ]
    if not values:
        raise ValueError(f"rule contains no usable {dimension} threshold")
    if operator == ">=":
        return min(values, key=lambda item: (item.value, item.start))
    return max(values, key=lambda item: (item.value, -item.start))


def compare_fact_to_threshold(
    *,
    issue_id: str,
    facet_id: str,
    fact_text: str,
    rule_text: str,
    evidence_ids: tuple[str, ...],
) -> FactRuleComparison:
    """Compare one fact and one threshold under a facet-owned operator contract."""
    try:
        dimension, operator, conditional = _COMPARISON_CONFIG[facet_id]
    except KeyError as error:
        raise ValueError(f"facet does not define a numeric comparison: {facet_id}") from error
    fact = _select_fact(fact_text, dimension)
    threshold = _select_threshold(rule_text, dimension, operator, conditional)
    if operator == ">=":
        satisfied = fact.value >= threshold.value
    elif operator == "<=":
        satisfied = fact.value <= threshold.value
    else:
        raise ValueError(f"unsupported comparison operator: {operator}")
    normalized_evidence = tuple(sorted(set(evidence_ids)))
    payload = {
        "issue_id": issue_id,
        "facet_id": facet_id,
        "operator": operator,
        "fact_value": _decimal_text(fact.value),
        "threshold_value": _decimal_text(threshold.value),
        "unit": dimension,
        "satisfied": satisfied,
        "evidence_ids": list(normalized_evidence),
    }
    result_hash = sha256_json(payload)
    return FactRuleComparison(
        comparison_id=f"CMP-{result_hash[:20].upper()}",
        issue_id=issue_id,
        facet_id=facet_id,
        operator=operator,
        fact_value=str(payload["fact_value"]),
        threshold_value=str(payload["threshold_value"]),
        unit=dimension,
        satisfied=satisfied,
        evidence_ids=normalized_evidence,
        result_hash=result_hash,
    )


def _evidence_ids_for_facet(
    facet_report: FacetCoverageReport,
    issue_id: str,
    facet_id: str,
) -> tuple[str, ...]:
    issue = facet_report.by_issue_id(issue_id)
    for candidate_facet_id, evidence_ids in issue.evidence_by_facet:
        if candidate_facet_id == facet_id:
            return evidence_ids
    return ()


def _rule_text_for_evidence(
    bundle: IssueRetrievalBundle,
    issue_id: str,
    evidence_ids: tuple[str, ...],
) -> str:
    expected = set(evidence_ids)
    texts: list[str] = []
    for candidate in bundle.candidates:
        if not any(match.issue_id == issue_id for match in candidate.matches):
            continue
        candidate_ids = {hit.evidence_id for hit in candidate.evidence}
        if not candidate_ids.intersection(expected):
            continue
        text = candidate.clause.text.strip()
        if text and text not in texts:
            texts.append(text)
    return " ".join(texts)


def _fact_text_for_issue_dimension(
    plan: QuestionPlan,
    issue_question: str,
    dimension: str,
) -> str | None:
    issue_values = {
        measure.value for measure in _measures_for_dimension(issue_question, dimension)
    }
    if not issue_values:
        return None
    matches: list[str] = []
    for fact in plan.facts:
        measures = _measures_for_dimension(fact.text, dimension)
        if len(measures) != 1 or measures[0].value not in issue_values:
            continue
        matches.append(fact.text)
    if len(matches) != 1:
        return None
    return matches[0]


def evaluate_fact_rule_comparisons(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
    facet_report: FacetCoverageReport,
) -> tuple[FactRuleComparison, ...]:
    """Build comparison artifacts only when an issue preserves the user fact value."""
    results: list[FactRuleComparison] = []
    for issue in plan.issues:
        facet_issue = facet_report.by_issue_id(issue.id)
        for facet_id in facet_issue.covered_facet_ids:
            config = _COMPARISON_CONFIG.get(facet_id)
            if config is None:
                continue
            dimension, _operator, _conditional = config
            fact_text = _fact_text_for_issue_dimension(
                plan,
                issue.question,
                dimension,
            )
            if fact_text is None:
                continue
            evidence_ids = _evidence_ids_for_facet(facet_report, issue.id, facet_id)
            if not evidence_ids:
                continue
            rule_text = _rule_text_for_evidence(bundle, issue.id, evidence_ids)
            if not rule_text:
                continue
            results.append(
                compare_fact_to_threshold(
                    issue_id=issue.id,
                    facet_id=facet_id,
                    fact_text=fact_text,
                    rule_text=rule_text,
                    evidence_ids=evidence_ids,
                )
            )
    return tuple(results)


def comparison_document(result: FactRuleComparison) -> dict[str, object]:
    return {
        "comparison_id": result.comparison_id,
        "issue_id": result.issue_id,
        "facet_id": result.facet_id,
        "operator": result.operator,
        "fact_value": result.fact_value,
        "threshold_value": result.threshold_value,
        "unit": result.unit,
        "satisfied": result.satisfied,
        "evidence_ids": list(result.evidence_ids),
        "result_hash": result.result_hash,
    }


def comparison_documents(
    results: tuple[FactRuleComparison, ...],
) -> list[dict[str, object]]:
    return [comparison_document(item) for item in results]


def bind_comparisons_to_review_request(
    request: dict[str, object],
    results: tuple[FactRuleComparison, ...],
) -> dict[str, object]:
    inputs_value = request.get("inputs")
    if not isinstance(inputs_value, dict) or not all(
        isinstance(key, str) for key in inputs_value
    ):
        raise ValueError("review request inputs must be an object")
    bound = dict(request)
    inputs = dict(inputs_value)
    inputs["fact_rule_comparisons"] = comparison_documents(results)
    bound["inputs"] = inputs
    return bound


def conditional_issue_ids_from_comparisons(
    results: tuple[FactRuleComparison, ...],
) -> tuple[str, ...]:
    by_issue: dict[str, dict[str, bool]] = {}
    for result in results:
        by_issue.setdefault(result.issue_id, {})[result.facet_id] = result.satisfied
    conditional: list[str] = []
    for issue_id, values in sorted(by_issue.items()):
        if (
            values.get("distance-normal-threshold") is False
            and values.get("distance-conditional-threshold") is True
        ):
            conditional.append(issue_id)
    return tuple(conditional)
