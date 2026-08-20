"""Integrity validators for untrusted Track A content."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.llm_layer.numeric_grammar import (
    NumericToken,
    extract_numeric_tokens,
    reject_unsupported_numeric_syntax,
    scan_numeric_tokens,
)
from evidence_review.llm_layer.track_a import TrackABundle, ValidatedTrackA
from evidence_review.math_engine.comparison import ComparisonOperator, relation_holds

_SYMBOLIC_COMPARISON = re.compile(r"(?:<=|>=|==|!=|<|>|≤|≥|≠|=)")
_RELATION_KEYWORDS: tuple[tuple[tuple[str, ...], ComparisonOperator], ...] = (
    (("미만", "미달", "작다", "낮다"), "<"),
    (("이하",), "<="),
    (("초과", "넘는다", "크다", "높다"), ">"),
    (("이상",), ">="),
)
_COMPARAND_UNITS = (
    "제곱미터",
    "퍼센트",
    "킬로미터",
    "밀리미터",
    "센티미터",
    "m²",
    "m2",
    "km",
    "mm",
    "cm",
    "㎡",
    "㎥",
    "m",
    "%",
)
_COMPARAND_PARTICLES = frozenset({"", "은", "는", "이", "가"})


def _calculation_tokens(calculation: CalculationResult) -> set[str]:
    values: list[str] = []
    values.extend(calculation.inputs.values())
    for value in (
        calculation.substitution,
        calculation.raw_result,
        calculation.display_result,
        calculation.comparison,
    ):
        if value is not None:
            values.append(value)
    tokens: set[str] = set()
    for value in values:
        tokens.update(extract_numeric_tokens(value))
        tokens.add(value)
    return tokens


def _rule_map(bundle: TrackABundle) -> dict[str, RuleResult]:
    return {result.rule_result_id: result for result in bundle.rules}


def _calculation_map(bundle: TrackABundle) -> dict[str, CalculationResult]:
    return {result.calculation_result_id: result for result in bundle.calculations}


def _citation_issue_ids(bundle: TrackABundle) -> dict[str, frozenset[str]]:
    return {
        item.citation.citation_id: frozenset(item.issue_ids)
        for item in bundle.evidence
    }


def _plan_fact_texts(inputs: Mapping[str, object]) -> tuple[str, ...]:
    plan = inputs.get("question_plan")
    if not isinstance(plan, Mapping):
        return ()
    texts: list[str] = []
    for section_name in ("facts", "assumptions"):
        section = plan.get(section_name, ())
        if isinstance(section, (str, bytes, bytearray)) or not isinstance(section, Sequence):
            continue
        for item in section:
            if not isinstance(item, Mapping):
                continue
            text = item.get("text")
            if isinstance(text, str):
                texts.append(text)
    return tuple(texts)


def _input_numeric_tokens(bundle: TrackABundle) -> set[str]:
    """Return numeric values explicitly supplied by the user/planning boundary."""
    tokens = set(extract_numeric_tokens(bundle.question))
    for text in _plan_fact_texts(bundle.inputs):
        tokens.update(extract_numeric_tokens(text))
    return tokens


def _require_claim_issue_coverage(
    claim_id: str,
    claim_issue_ids: tuple[str, ...],
    citation_ids: tuple[str, ...],
    citation_issue_ids: dict[str, frozenset[str]],
) -> None:
    if not claim_issue_ids or not any(citation_issue_ids.values()):
        return
    supported: set[str] = set()
    for citation_id in citation_ids:
        supported.update(citation_issue_ids.get(citation_id, ()))
    missing = sorted(set(claim_issue_ids) - supported)
    if missing:
        raise ValueError(
            f"UNSUPPORTED_CLAIM_ISSUE: claim {claim_id}: {', '.join(missing)}"
        )


def _symbolic_operator(fragment: str) -> ComparisonOperator | None:
    match = _SYMBOLIC_COMPARISON.search(fragment)
    if match is None:
        return None
    value = match.group(0)
    normalized = {
        "≤": "<=",
        "≥": ">=",
        "==": "=",
        "≠": "!=",
    }.get(value, value)
    if normalized in {"<", "<=", "=", "!=", ">=", ">"}:
        return cast(ComparisonOperator, normalized)
    return None


def _keyword_operator(text: str) -> ComparisonOperator | None:
    for keywords, operator in _RELATION_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return operator
    return None


def _is_direct_comparand_connector(fragment: str) -> bool:
    """Return whether two numeric tokens are directly connected as comparands."""
    value = fragment.strip()
    for unit in _COMPARAND_UNITS:
        if value.startswith(unit):
            value = value[len(unit) :].strip()
            break
    return value in _COMPARAND_PARTICLES


def _validate_two_token_comparison(text: str, tokens: tuple[NumericToken, ...]) -> None:
    if len(tokens) != 2:
        return
    between = text[tokens[0].end : tokens[1].start]
    after = text[tokens[1].end :]
    operator = _symbolic_operator(between)
    if operator is None and _is_direct_comparand_connector(between):
        operator = _keyword_operator(after)
    if operator is None:
        return
    if not relation_holds(tokens[0].text, operator, tokens[1].text):
        raise ValueError(
            "CALCULATION_MISMATCH: deterministic comparison is false: "
            f"{tokens[0].text} {operator} {tokens[1].text}"
        )


def _validate_majority_comparison(text: str, tokens: tuple[NumericToken, ...]) -> None:
    if "과반" not in text or not tokens:
        return
    percent_tokens = [token for token in tokens if token.text.endswith("%")]
    if not percent_tokens:
        return
    value = percent_tokens[0].text
    negative_assertion = any(
        marker in text
        for marker in ("미달", "미만", "충족하지", "충족 못", "아니다", "못한다")
    )
    positive_assertion = any(
        marker in text
        for marker in ("과반이다", "과반을 충족", "과반을 넘", "과반 초과")
    )
    if negative_assertion and not relation_holds(value, "<=", "50%"):
        raise ValueError(
            f"CALCULATION_MISMATCH: {value} does not support a majority shortfall"
        )
    if positive_assertion and not relation_holds(value, ">", "50%"):
        raise ValueError(
            f"CALCULATION_MISMATCH: {value} does not satisfy a majority threshold"
        )


def _validate_deterministic_comparisons(text: str, tokens: tuple[NumericToken, ...]) -> None:
    _validate_two_token_comparison(text, tokens)
    _validate_majority_comparison(text, tokens)


def validate_track_a_integrity(validated: ValidatedTrackA, bundle: TrackABundle) -> None:
    """Reject unsupported claim lineage, numbers, and deterministic references."""
    if validated.draft.run_id != bundle.run_id:
        raise ValueError("track_a run_id does not match bundle")
    evidence_by_citation = {
        item.citation.citation_id: item.text for item in bundle.evidence
    }
    citation_issue_ids = _citation_issue_ids(bundle)
    calculation_by_id = _calculation_map(bundle)
    rule_by_id = _rule_map(bundle)
    references_by_claim = {
        references.claim_id: references for references in validated.claim_references
    }
    input_numeric_tokens = _input_numeric_tokens(bundle)

    for claim in validated.draft.claims:
        _require_claim_issue_coverage(
            claim.claim_id,
            claim.issue_ids,
            claim.citation_ids,
            citation_issue_ids,
        )
        tokens = scan_numeric_tokens(claim.text)
        reject_unsupported_numeric_syntax(claim.text, tokens)
        extracted = tuple(token.text for token in tokens)
        if extracted != claim.numeric_tokens:
            raise ValueError(f"NUMERIC_TOKEN_MISMATCH: {claim.claim_id}")
        _validate_deterministic_comparisons(claim.text, tokens)
        references = references_by_claim[claim.claim_id]
        allowed_tokens: set[str] = set(input_numeric_tokens)
        for citation_id in claim.citation_ids:
            source_text = evidence_by_citation.get(citation_id)
            if source_text is None:
                raise ValueError(f"unresolved citation: {citation_id}")
            allowed_tokens.update(extract_numeric_tokens(source_text))
        for calculation_id in references.calculation_result_ids:
            calculation = calculation_by_id.get(calculation_id)
            if calculation is None or calculation.status != "SUCCESS":
                raise ValueError(f"invalid calculation reference: {calculation_id}")
            allowed_tokens.update(_calculation_tokens(calculation))
        for token in claim.numeric_tokens:
            if token not in allowed_tokens:
                raise ValueError(f"unregistered numeric token: {token}")

        for reference in references.rule_references:
            result = rule_by_id.get(reference.rule_result_id)
            if (
                result is None
                or result.result_hash is None
                or result.result_hash != reference.result_hash
                or result.status != reference.status
            ):
                raise ValueError(
                    f"rule result reference mismatch: {reference.rule_result_id}"
                )
