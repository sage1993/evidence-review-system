"""Integrity validators for untrusted Track A content."""

from __future__ import annotations

import re

from ansim_review.contracts.engines import CalculationResult, RuleResult
from ansim_review.llm_layer.track_a import TrackABundle, ValidatedTrackA

_NUMERIC_TOKEN = re.compile(
    r"(?<![0-9A-Za-z_.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![0-9A-Za-z_.])"
)


def extract_numeric_tokens(text: str) -> tuple[str, ...]:
    """Extract numeric and percent tokens without rounding or normalization."""
    return tuple(match.group(0) for match in _NUMERIC_TOKEN.finditer(text))


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


def validate_track_a_integrity(validated: ValidatedTrackA, bundle: TrackABundle) -> None:
    """Reject LLM-authored numbers and altered deterministic result references."""
    if validated.draft.run_id != bundle.run_id:
        raise ValueError("track_a run_id does not match bundle")
    evidence_by_citation = {
        item.citation.citation_id: item.text for item in bundle.evidence
    }
    calculation_by_id = _calculation_map(bundle)
    rule_by_id = _rule_map(bundle)
    references_by_claim = {
        references.claim_id: references for references in validated.claim_references
    }

    for claim in validated.draft.claims:
        extracted = extract_numeric_tokens(claim.text)
        if extracted != claim.numeric_tokens:
            raise ValueError(
                f"claim {claim.claim_id} numeric_tokens do not exactly match claim text"
            )
        references = references_by_claim[claim.claim_id]
        allowed_tokens: set[str] = set()
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
