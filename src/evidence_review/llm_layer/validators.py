"""Integrity validators for untrusted Track A content."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.llm_layer.numeric_grammar import (
    extract_numeric_tokens,
    reject_unsupported_numeric_syntax,
    scan_numeric_tokens,
)
from evidence_review.llm_layer.track_a import TrackABundle, ValidatedTrackA


_REQUIRED_COMPARISON_FIELDS = {
    "comparison_id",
    "issue_id",
    "facet_id",
    "operator",
    "fact_value",
    "threshold_value",
    "unit",
    "satisfied",
    "evidence_ids",
    "result_hash",
}


@dataclass(frozen=True, slots=True)
class _TrustedComparison:
    comparison_id: str
    issue_id: str
    facet_id: str
    operator: str
    fact_value: str
    threshold_value: str
    unit: str
    satisfied: bool
    evidence_ids: tuple[str, ...]


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


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _comparison_documents(bundle: TrackABundle) -> tuple[_TrustedComparison, ...]:
    value = bundle.inputs.get("fact_rule_comparisons")
    if value is None:
        return ()
    evidence_by_id = {item.citation.evidence_id: item for item in bundle.evidence}
    documents: list[_TrustedComparison] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(_sequence(value, "inputs.fact_rule_comparisons")):
        payload = dict(_mapping(raw, f"inputs.fact_rule_comparisons[{index}]"))
        if set(payload) != _REQUIRED_COMPARISON_FIELDS:
            raise ValueError("fact_rule_comparison has invalid fields")
        comparison_id = _string(payload["comparison_id"], "comparison_id")
        issue_id = _string(payload["issue_id"], "issue_id")
        facet_id = _string(payload["facet_id"], "facet_id")
        operator = _string(payload["operator"], "operator")
        fact_value = _string(payload["fact_value"], "fact_value")
        threshold_value = _string(payload["threshold_value"], "threshold_value")
        unit = _string(payload["unit"], "unit")
        result_hash = _string(payload["result_hash"], "result_hash")
        satisfied = payload["satisfied"]
        if not isinstance(satisfied, bool):
            raise ValueError("comparison satisfied must be a boolean")
        evidence_ids = tuple(
            _string(item, f"evidence_ids[{item_index}]")
            for item_index, item in enumerate(
                _sequence(payload["evidence_ids"], "evidence_ids")
            )
        )
        if not evidence_ids or len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("comparison evidence_ids must be unique and non-empty")
        if comparison_id in seen_ids:
            raise ValueError(f"duplicate comparison_id: {comparison_id}")
        seen_ids.add(comparison_id)
        for evidence_id in evidence_ids:
            excerpt = evidence_by_id.get(evidence_id)
            if excerpt is None:
                raise ValueError(f"comparison references unknown evidence: {evidence_id}")
            if excerpt.issue_ids and issue_id not in excerpt.issue_ids:
                raise ValueError(
                    f"COMPARISON_ISSUE_MISMATCH: {comparison_id} -> {evidence_id}"
                )
        try:
            fact_decimal = Decimal(fact_value)
            threshold_decimal = Decimal(threshold_value)
        except InvalidOperation as error:
            raise ValueError("comparison values must be canonical decimals") from error
        if operator == ">=":
            expected_satisfied = fact_decimal >= threshold_decimal
        elif operator == "<=":
            expected_satisfied = fact_decimal <= threshold_decimal
        else:
            raise ValueError(f"unsupported comparison operator: {operator}")
        if expected_satisfied is not satisfied:
            raise ValueError(f"COMPARISON_RESULT_MISMATCH: {comparison_id}")
        hash_payload = {
            "issue_id": issue_id,
            "facet_id": facet_id,
            "operator": operator,
            "fact_value": fact_value,
            "threshold_value": threshold_value,
            "unit": unit,
            "satisfied": satisfied,
            "evidence_ids": list(evidence_ids),
        }
        expected_hash = sha256_json(hash_payload)
        if result_hash != expected_hash or comparison_id != f"CMP-{expected_hash[:20].upper()}":
            raise ValueError(f"COMPARISON_HASH_MISMATCH: {comparison_id}")
        documents.append(
            _TrustedComparison(
                comparison_id=comparison_id,
                issue_id=issue_id,
                facet_id=facet_id,
                operator=operator,
                fact_value=fact_value,
                threshold_value=threshold_value,
                unit=unit,
                satisfied=satisfied,
                evidence_ids=evidence_ids,
            )
        )
    return tuple(documents)


def _comparison_tokens_for_claim(
    claim_issue_ids: tuple[str, ...],
    citation_ids: tuple[str, ...],
    bundle: TrackABundle,
    comparisons: tuple[_TrustedComparison, ...],
) -> set[str]:
    if not claim_issue_ids or not comparisons:
        return set()
    citation_to_evidence = {
        item.citation.citation_id: item.citation.evidence_id
        for item in bundle.evidence
    }
    cited_evidence_ids = {
        citation_to_evidence[citation_id]
        for citation_id in citation_ids
        if citation_id in citation_to_evidence
    }
    issue_ids = set(claim_issue_ids)
    tokens: set[str] = set()
    for comparison in comparisons:
        if comparison.issue_id not in issue_ids:
            continue
        if not set(comparison.evidence_ids).issubset(cited_evidence_ids):
            continue
        tokens.add(comparison.fact_value)
        tokens.add(comparison.threshold_value)
    return tokens


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
    comparisons = _comparison_documents(bundle)
    references_by_claim = {
        references.claim_id: references for references in validated.claim_references
    }

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
        references = references_by_claim[claim.claim_id]
        allowed_tokens: set[str] = _comparison_tokens_for_claim(
            claim.issue_ids,
            claim.citation_ids,
            bundle,
            comparisons,
        )
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
