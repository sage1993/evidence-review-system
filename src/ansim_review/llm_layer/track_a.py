"""Evidence-only Track A bundle and untrusted-output validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from ansim_review.contracts.common import Citation
from ansim_review.contracts.engines import CalculationResult, RuleResult, RuleStatus
from ansim_review.contracts.review import Claim, TrackADraft

_REQUIRED_SECTIONS = (
    "run_id",
    "claims",
    "citations",
    "missing_inputs",
    "exceptions",
    "conflicts",
    "explanation",
)
_FORBIDDEN_FIELDS = frozenset(
    {
        "human_decision",
        "confidence",
        "confidence_level",
        "abstention",
        "abstention_reasons",
        "final_decision",
        "status",
        "rule_results",
        "rules",
        "calculations",
    }
)
_ALLOWED_RULE_STATUSES = frozenset(
    {"SATISFIED", "NOT_SATISFIED", "INDETERMINATE", "NOT_APPLICABLE", "ENGINE_ERROR"}
)


@dataclass(frozen=True, slots=True)
class EvidenceExcerpt:
    """One source excerpt exposed to Track A."""

    citation: Citation
    text: str


@dataclass(frozen=True, slots=True)
class TrackABundle:
    """Trusted deterministic input bundle presented to Track A."""

    run_id: str
    question: str
    inputs: Mapping[str, object]
    evidence: tuple[EvidenceExcerpt, ...]
    rules: tuple[RuleResult, ...]
    calculations: tuple[CalculationResult, ...]
    approved_rule_result_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleReference:
    """Track A reference to an existing deterministic rule result."""

    rule_result_id: str
    result_hash: str
    status: RuleStatus


@dataclass(frozen=True, slots=True)
class ClaimReferences:
    """Non-authoritative references attached to one Track A claim."""

    claim_id: str
    calculation_result_ids: tuple[str, ...]
    rule_references: tuple[RuleReference, ...]


@dataclass(frozen=True, slots=True)
class ValidatedTrackA:
    """Structurally validated Track A output awaiting integrity checks."""

    draft: TrackADraft
    citation_ids: tuple[str, ...]
    calculation_result_ids: tuple[str, ...]
    claim_references: tuple[ClaimReferences, ...]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        suffix = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{field} must be {suffix}")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{field}[{index}]")
        for index, item in enumerate(_sequence(value, field))
    )


def build_track_a_bundle(
    *,
    run_id: str,
    question: str,
    inputs: Mapping[str, object],
    evidence: Sequence[EvidenceExcerpt],
    rules: Sequence[RuleResult],
    calculations: Sequence[CalculationResult],
    approved_rule_result_ids: Sequence[str] = (),
) -> TrackABundle:
    """Build an immutable Track A input bundle without invoking a model."""
    if not run_id or not question:
        raise ValueError("run_id and question are required")
    evidence_items = tuple(evidence)
    citation_ids = [item.citation.citation_id for item in evidence_items]
    if len(citation_ids) != len(set(citation_ids)):
        raise ValueError("evidence citation IDs must be unique")
    rule_items = tuple(rules)
    calculation_items = tuple(calculations)
    return TrackABundle(
        run_id=run_id,
        question=question,
        inputs=dict(inputs),
        evidence=evidence_items,
        rules=rule_items,
        calculations=calculation_items,
        approved_rule_result_ids=tuple(sorted(set(approved_rule_result_ids))),
    )


def _decode_rule_reference(value: object, field: str) -> RuleReference:
    payload = _mapping(value, field)
    allowed = {"rule_result_id", "result_hash", "status"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")
    status = _string(payload.get("status"), f"{field}.status")
    if status not in _ALLOWED_RULE_STATUSES:
        raise ValueError(f"unsupported rule status: {status}")
    return RuleReference(
        rule_result_id=_string(payload.get("rule_result_id"), f"{field}.rule_result_id"),
        result_hash=_string(payload.get("result_hash"), f"{field}.result_hash"),
        status=cast(RuleStatus, status),
    )


def validate_track_a_output(value: object, bundle: TrackABundle) -> ValidatedTrackA:
    """Validate Track A structure while preserving deterministic authority boundaries."""
    payload = _mapping(value, "track_a")
    forbidden = sorted(set(payload) & _FORBIDDEN_FIELDS)
    if forbidden:
        raise ValueError(f"track_a contains forbidden fields: {', '.join(forbidden)}")
    missing_sections = [section for section in _REQUIRED_SECTIONS if section not in payload]
    if missing_sections:
        raise ValueError(f"track_a is missing required sections: {', '.join(missing_sections)}")
    unknown = sorted(set(payload) - set(_REQUIRED_SECTIONS))
    if unknown:
        raise ValueError(f"track_a has unknown fields: {', '.join(unknown)}")
    run_id = _string(payload.get("run_id"), "run_id")
    if run_id != bundle.run_id:
        raise ValueError("track_a run_id does not match bundle")

    known_citations = {item.citation.citation_id for item in bundle.evidence}
    declared_citations = _string_tuple(payload.get("citations"), "citations")
    if len(declared_citations) != len(set(declared_citations)):
        raise ValueError("track_a citations must be unique")
    unknown_citations = sorted(set(declared_citations) - known_citations)
    if unknown_citations:
        raise ValueError(f"track_a cites unknown citations: {', '.join(unknown_citations)}")

    claims: list[Claim] = []
    claim_references: list[ClaimReferences] = []
    seen_claim_ids: set[str] = set()
    used_citations: set[str] = set()
    used_calculations: set[str] = set()
    for index, item in enumerate(_sequence(payload.get("claims"), "claims")):
        claim_payload = _mapping(item, f"claims[{index}]")
        allowed = {
            "claim_id",
            "text",
            "citation_ids",
            "numeric_tokens",
            "calculation_result_ids",
            "rule_references",
        }
        claim_unknown = sorted(set(claim_payload) - allowed)
        if claim_unknown:
            raise ValueError(f"claims[{index}] has unknown fields: {', '.join(claim_unknown)}")
        claim_id = _string(claim_payload.get("claim_id"), f"claims[{index}].claim_id")
        if claim_id in seen_claim_ids:
            raise ValueError(f"duplicate claim_id: {claim_id}")
        seen_claim_ids.add(claim_id)
        citation_ids = _string_tuple(
            claim_payload.get("citation_ids"), f"claims[{index}].citation_ids"
        )
        if not citation_ids:
            raise ValueError(f"claim {claim_id} requires at least one citation")
        unknown_claim_citations = sorted(set(citation_ids) - known_citations)
        if unknown_claim_citations:
            raise ValueError(
                f"claim {claim_id} cites unknown citations: {', '.join(unknown_claim_citations)}"
            )
        numeric_tokens = _string_tuple(
            claim_payload.get("numeric_tokens", []), f"claims[{index}].numeric_tokens"
        )
        calculation_ids = _string_tuple(
            claim_payload.get("calculation_result_ids", []),
            f"claims[{index}].calculation_result_ids",
        )
        rule_references = tuple(
            _decode_rule_reference(reference, f"claims[{index}].rule_references[{ref_index}]")
            for ref_index, reference in enumerate(
                _sequence(
                    claim_payload.get("rule_references", []),
                    f"claims[{index}].rule_references",
                )
            )
        )
        claims.append(
            Claim(
                claim_id=claim_id,
                text=_string(claim_payload.get("text"), f"claims[{index}].text"),
                citation_ids=citation_ids,
                numeric_tokens=numeric_tokens,
            )
        )
        claim_references.append(
            ClaimReferences(
                claim_id=claim_id,
                calculation_result_ids=calculation_ids,
                rule_references=rule_references,
            )
        )
        used_citations.update(citation_ids)
        used_calculations.update(calculation_ids)

    if tuple(sorted(declared_citations)) != tuple(sorted(used_citations)):
        raise ValueError("track_a citations must exactly match claim citations")
    return ValidatedTrackA(
        draft=TrackADraft(
            run_id=run_id,
            claims=tuple(claims),
            missing_inputs=_string_tuple(payload.get("missing_inputs"), "missing_inputs"),
            exceptions=_string_tuple(payload.get("exceptions"), "exceptions"),
            conflicts=_string_tuple(payload.get("conflicts"), "conflicts"),
            explanation=_string(payload.get("explanation"), "explanation"),
        ),
        citation_ids=tuple(sorted(declared_citations)),
        calculation_result_ids=tuple(sorted(used_calculations)),
        claim_references=tuple(claim_references),
    )


def _citation_document(citation: Citation) -> dict[str, object]:
    return {
        "citation_id": citation.citation_id,
        "document_id": citation.document_id,
        "revision_id": citation.revision_id,
        "page_number": citation.page_number,
        "evidence_id": citation.evidence_id,
        "bbox": [citation.bbox.left, citation.bbox.bottom, citation.bbox.right, citation.bbox.top],
        "source_hash": citation.source_hash,
    }


def track_a_bundle_document(bundle: TrackABundle) -> dict[str, object]:
    """Return the canonical JSON-ready Track A input document."""
    return {
        "run_id": bundle.run_id,
        "question": bundle.question,
        "inputs": dict(bundle.inputs),
        "evidence": [
            {"citation": _citation_document(item.citation), "text": item.text}
            for item in bundle.evidence
        ],
        "rules": [
            {
                "rule_result_id": item.rule_result_id,
                "rule_id": item.rule_id,
                "rule_version": item.rule_version,
                "status": item.status,
                "result_hash": item.result_hash,
                "missing_inputs": list(item.missing_inputs),
                "calculation_result_ids": list(item.calculation_result_ids),
                "reason_codes": list(item.reason_codes),
            }
            for item in bundle.rules
        ],
        "calculations": [
            {
                "calculation_result_id": item.calculation_result_id,
                "status": item.status,
                "formula_id": item.formula_id,
                "formula_version": item.formula_version,
                "inputs": dict(item.inputs),
                "substitution": item.substitution,
                "raw_result": item.raw_result,
                "display_result": item.display_result,
                "comparison": item.comparison,
                "formula_manifest_hash": item.formula_manifest_hash,
                "result_hash": item.result_hash,
                "error_codes": list(item.error_codes),
            }
            for item in bundle.calculations
        ],
        "approved_rule_result_ids": list(bundle.approved_rule_result_ids),
    }
