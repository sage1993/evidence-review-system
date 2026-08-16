"""Deterministic conditional-threshold inference for issue coverage."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from evidence_review.contracts.question_plan import QuestionPlan
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle

_MEASURE_RE = re.compile(
    r"(?<![0-9])(?P<value>[0-9][0-9,]*(?:\.[0-9]+)?)\s*"
    r"(?P<unit>㎡|m²|m2|제곱미터|미터|m|퍼센트|%)",
    re.IGNORECASE,
)
_CONDITIONAL_CUES = (
    "다만",
    "심의",
    "조건",
    "경우",
    "거쳐",
    "특례",
    "완화",
    "예외",
    "지정할 수",
)
_CONDITIONAL_LOOKBACK = 80


@dataclass(frozen=True, slots=True)
class Measure:
    value: Decimal
    dimension: str
    start: int
    conditional: bool


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _dimension(unit: str) -> str:
    normalized = unicodedata.normalize("NFKC", unit).casefold()
    if normalized in {"m", "미터"}:
        return "length_m"
    if normalized in {"m2", "제곱미터"}:
        return "area_m2"
    if normalized in {"%", "퍼센트"}:
        return "percent"
    raise ValueError(f"unsupported measure unit: {unit}")


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise ValueError(f"invalid measure value: {value}") from error


def extract_measures(text: str) -> tuple[Measure, ...]:
    """Extract metric/percentage values and whether local text marks them conditional."""
    normalized = _normalize(text)
    measures: list[Measure] = []
    for match in _MEASURE_RE.finditer(normalized):
        prefix = normalized[max(0, match.start() - _CONDITIONAL_LOOKBACK) : match.start()]
        measures.append(
            Measure(
                value=_decimal(match.group("value")),
                dimension=_dimension(match.group("unit")),
                start=match.start(),
                conditional=any(cue in prefix for cue in _CONDITIONAL_CUES),
            )
        )
    return tuple(measures)


def conditional_range_satisfied(fact_text: str, rule_text: str) -> bool:
    """Return true only for a value above an ordinary limit but within a conditional one."""
    facts = extract_measures(fact_text)
    if len(facts) != 1:
        return False
    fact = facts[0]
    thresholds = [
        item for item in extract_measures(rule_text) if item.dimension == fact.dimension
    ]
    if len(thresholds) < 2:
        return False

    ordinary_below = sorted(
        (item for item in thresholds if not item.conditional and item.value < fact.value),
        key=lambda item: item.value,
    )
    conditional_above = sorted(
        (item for item in thresholds if item.conditional and item.value >= fact.value),
        key=lambda item: item.value,
    )
    if not ordinary_below or not conditional_above:
        return False
    return ordinary_below[-1].value < fact.value <= conditional_above[0].value


def _issue_rule_text(bundle: IssueRetrievalBundle, issue_id: str) -> str:
    texts: list[str] = []
    for candidate in bundle.candidates:
        if not any(
            match.issue_id == issue_id and match.role == "rule"
            for match in candidate.matches
        ):
            continue
        text = candidate.clause.text.strip()
        if text and text not in texts:
            texts.append(text)
    return " ".join(texts)


def infer_conditional_issue_ids(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
) -> tuple[str, ...]:
    """Infer conditional issue states from explicit question values and retrieved rules.

    The inference is intentionally narrow: the issue question must contain exactly
    one measurable value, retrieved rule evidence must provide both an ordinary
    lower threshold and a conditionally-worded upper threshold of the same
    dimension, and the user value must fall strictly above the ordinary threshold
    while remaining within the conditional threshold.
    """
    conditional: list[str] = []
    for issue in plan.issues:
        issue_measures = extract_measures(issue.question)
        if len(issue_measures) != 1:
            continue
        rule_text = _issue_rule_text(bundle, issue.id)
        if not rule_text:
            continue
        if conditional_range_satisfied(issue.question, rule_text):
            conditional.append(issue.id)
    return tuple(conditional)
