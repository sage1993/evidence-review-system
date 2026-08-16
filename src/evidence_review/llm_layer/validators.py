"""Integrity validators for untrusted Track A content."""

from __future__ import annotations

from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.llm_layer.numeric_grammar import (
    extract_numeric_tokens,
    reject_unsupported_numeric_syntax,
    scan_numeric_tokens,
)
from evidence_review.llm_layer.track_a import TrackABundle, ValidatedTrackA


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