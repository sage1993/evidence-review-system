"""Evidence-only Track A bundle and untrusted-output validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import cast

from evidence_review.contracts.common import Citation
from evidence_review.contracts.engines import CalculationResult, RuleResult, RuleStatus
from evidence_review.contracts.question_plan import EvidenceRole
from evidence_review.contracts.review import Claim, TrackADraft

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
    """One source excerpt exposed to Track A with optional issue lineage."""

    citation: Citation
    text: str
    issue_ids: tuple[str, ...] = ()
    role: EvidenceRole | None = None


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


def _unique_string_tuple(value: object, field: str) -> tuple[str, ...]:
    items = _string_tuple(value, field)
    if len(items) != len(set(items)):
        raise ValueError(f"{field} must contain unique values")
    return items


def _lineage_by_citation(
    inputs: Mapping[str, object],
) -> dict[str, tuple[str, tuple[str, ...], EvidenceRole | None]]:
    value = inputs.get("retrieval_lineage")
    if value is None:
        return {}
    result: dict[str, tuple[str, tuple[str, ...], EvidenceRole | None]] = {}
    for index, item in enumerate(_sequence(value, "inputs.retrieval_lineage")):
        entry = _mapping(item, f"inputs.retrieval_lineage[{index}]")
        evidence_id = _string(
            entry.get("evidence_id"), f"inputs.retrieval_lineage[{index}].evidence_id"
        )
        citation_id = _string(
            entry.get("citation_id"), f"inputs.retrieval_lineage[{index}].citation_id"
        )
        issue_ids: set[str] = set()
        roles: set[EvidenceRole] = set()
        for match_index, match_value in enumerate(
            _sequence(entry.get("matches", []), f"inputs.retrieval_lineage[{index}].matches")
        ):
            match = _mapping(
                match_value,
                f"inputs.retrieval_lineage[{index}].matches[{match_index}]",
            )
            match_issue_ids = _unique_string_tuple(
                match.get("issue_ids", []),
                f"inputs.retrieval_lineage[{index}].matches[{match_index}].issue_ids",
            )
            issue_ids.update(match_issue_ids)
            role_value = match.get("role")
            if role_value is not None:
                role = _string(
                    role_value,
                    f"inputs.retrieval_lineage[{index}].matches[{match_index}].role",
                )
                if role not in {"supporting_fact", "rule"}:
                    raise ValueError(f"unsupported retrieval lineage role: {role}")
                roles.add(cast(EvidenceRole, role))
        role = next(iter(roles)) if len(roles) == 1 else None
        normalized = (evidence_id, tuple(sorted(issue_ids)), role)
        existing = result.get(citation_id)
        if existing is not None and existing != normalized:
            raise ValueError(f"conflicting retrieval lineage for citation {citation_id}")
        result[citation_id] = normalized
    return result


def _enrich_evidence_from_lineage(
    evidence: tuple[EvidenceExcerpt, ...],
    inputs: Mapping[str, object],
) -> tuple[EvidenceExcerpt, ...]:
    lineage = _lineage_by_citation(inputs)
    if not lineage:
        return evidence
    enriched: list[EvidenceExcerpt] = []
    for index, item in enumerate(evidence):
        entry = lineage.get(item.citation.citation_id)
        if entry is None:
            enriched.append(item)
            continue
        evidence_id, issue_ids, role = entry
        if evidence_id != item.citation.evidence_id:
            raise ValueError(
                f"evidence[{index}] retrieval lineage evidence_id does not match citation"
            )
        if item.issue_ids and tuple(sorted(item.issue_ids)) != issue_ids:
            raise ValueError(f"evidence[{index}] issue lineage conflicts with request inputs")
        if item.role is not None and role is not None and item.role != role:
            raise ValueError(f"evidence[{index}] role conflicts with request inputs")
        enriched.append(
            replace(
                item,
                issue_ids=issue_ids or item.issue_ids,
                role=role if role is not None else item.role,
            )
        )
    return tuple(enriched)


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
    evidence_items = _enrich_evidence_from_lineage(tuple(evidence), inputs)
    citation_ids = [item.citation.citation_id for item in evidence_items]
    if len(citation_ids) != len(set(citation_ids)):
        raise ValueError("evidence citation IDs must be unique")
    for index, item in enumerate(evidence_items):
        if len(item.issue_ids) != len(set(item.issue_ids)):
            raise ValueError(f"evidence[{index}].issue_ids must contain unique values")
        if item.role not in (None, "supporting_fact", "rule"):
            raise ValueError(f"unsupported evidence[{index}].role: {item.role}")
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


def _validate_claim_issue_relevance(
    *,
    claim_id: str,
    claim_issue_ids: tuple[str, ...],
    citation_ids: tuple[str, ...],
    evidence_by_citation: Mapping[str, EvidenceExcerpt],
) -> None:
    known_issue_ids = {
        issue_id
        for evidence in evidence_by_citation.values()
        for issue_id in evidence.issue_ids
    }
    if not known_issue_ids:
        return
    if not claim_issue_ids:
        raise ValueError(f"UNRELATED_CLAIM: claim {claim_id} requires issue_ids")
    unknown_issue_ids = sorted(set(claim_issue_ids) - known_issue_ids)
    if unknown_issue_ids:
        raise ValueError(
            f"UNKNOWN_CLAIM_ISSUE: claim {claim_id}: {', '.join(unknown_issue_ids)}"
        )
    claim_issue_set = set(claim_issue_ids)
    for citation_id in citation_ids:
        evidence = evidence_by_citation[citation_id]
        if evidence.issue_ids and not claim_issue_set.intersection(evidence.issue_ids):
            raise ValueError(
                f"CROSS_ISSUE_CITATION: claim {claim_id} cites {citation_id}"
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

    evidence_by_citation = {item.citation.citation_id: item for item in bundle.evidence}
    known_citations = set(evidence_by_citation)
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
            "issue_ids",
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
        issue_ids = _unique_string_tuple(
            claim_payload.get("issue_ids", []), f"claims[{index}].issue_ids"
        )
        _validate_claim_issue_relevance(
            claim_id=claim_id,
            claim_issue_ids=issue_ids,
            citation_ids=citation_ids,
            evidence_by_citation=evidence_by_citation,
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
                issue_ids=issue_ids,
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


def _evidence_document(item: EvidenceExcerpt) -> dict[str, object]:
    document: dict[str, object] = {
        "citation": _citation_document(item.citation),
        "text": item.text,
    }
    if item.issue_ids:
        document["issue_ids"] = list(item.issue_ids)
    if item.role is not None:
        document["role"] = item.role
    return document


def track_a_bundle_document(bundle: TrackABundle) -> dict[str, object]:
    """Return the canonical JSON-ready Track A input document."""
    return {
        "run_id": bundle.run_id,
        "question": bundle.question,
        "inputs": dict(bundle.inputs),
        "evidence": [_evidence_document(item) for item in bundle.evidence],
        "rules": [
            {
                "rule_result_id": item.rule_result_id,
                "rule_id": item.rule_id,
                "rule_version": item.rule_version,
                "status": item.status,
                "citations": [_citation_document(citation) for citation in item.citations],
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
