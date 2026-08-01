"""Review Packet v2 contracts with resolved evidence and drawing inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from ansim_review.contracts.codecs import (
    decode_calculation_result,
    decode_citation,
    decode_claim,
    decode_confidence_result,
    decode_rule_result,
)
from ansim_review.contracts.common import Citation
from ansim_review.contracts.drawing import (
    ConfirmedInput,
    DrawingCandidate,
    confirmed_input_document,
    decode_confirmed_input,
    decode_drawing_candidate,
    drawing_candidate_document,
)
from ansim_review.contracts.engines import CalculationResult, RuleResult
from ansim_review.contracts.review import (
    Claim,
    ConfidenceResult,
    FinalizerStatus,
)
from ansim_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    expect_string_tuple,
    reject_unknown,
)

_FORMATS: tuple[Literal["ansim/review-packet"], ...] = ("ansim/review-packet",)
_FINALIZER_STATUSES: tuple[FinalizerStatus, ...] = (
    "READY_FOR_HUMAN_REVIEW",
    "ABSTAIN",
)


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Resolved immutable evidence used by one or more claims."""

    evidence_id: str
    citation: Citation
    quote: str
    numeric_tokens: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewPacketV2:
    """Versioned final machine packet awaiting a separate human decision."""

    format: Literal["ansim/review-packet"]
    version: Literal[2]
    run_id: str
    case_id: str
    question: str
    finalizer_status: FinalizerStatus
    snapshot_sha256: str
    rule_manifest_sha256: str
    formula_manifest_sha256: str
    claims: tuple[Claim, ...]
    evidence: tuple[EvidenceRecord, ...]
    drawing_evidence: tuple[DrawingCandidate, ...]
    confirmed_inputs: tuple[ConfirmedInput, ...]
    calculations: tuple[CalculationResult, ...]
    rule_evaluations: tuple[RuleResult, ...]
    exceptions: tuple[str, ...]
    conflicts: tuple[str, ...]
    confidence: ConfidenceResult | None
    abstention_reasons: tuple[str, ...]
    human_decision: None
    compatibility_source_version: int | None


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


def _claim_document(claim: Claim) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "text": claim.text,
        "citation_ids": list(claim.citation_ids),
        "numeric_tokens": list(claim.numeric_tokens),
    }


def _calculation_document(result: CalculationResult) -> dict[str, object]:
    return {
        "calculation_result_id": result.calculation_result_id,
        "status": result.status,
        "formula_id": result.formula_id,
        "formula_version": result.formula_version,
        "inputs": dict(result.inputs),
        "substitution": result.substitution,
        "raw_result": result.raw_result,
        "display_result": result.display_result,
        "comparison": result.comparison,
        "formula_manifest_hash": result.formula_manifest_hash,
        "result_hash": result.result_hash,
        "error_codes": list(result.error_codes),
    }


def _rule_document(result: RuleResult) -> dict[str, object]:
    return {
        "rule_result_id": result.rule_result_id,
        "rule_id": result.rule_id,
        "rule_version": result.rule_version,
        "status": result.status,
        "citations": [_citation_document(citation) for citation in result.citations],
        "missing_inputs": list(result.missing_inputs),
        "calculation_result_ids": list(result.calculation_result_ids),
        "reason_codes": list(result.reason_codes),
        "result_hash": result.result_hash,
    }


def _confidence_document(result: ConfidenceResult) -> dict[str, object]:
    return {
        "policy_version": result.policy_version,
        "score": result.score,
        "level": result.level,
        "factors": [
            {
                "name": factor.name,
                "value": factor.value,
                "weight": factor.weight,
                "contribution": factor.contribution,
                "source": factor.source,
            }
            for factor in result.factors
        ],
        "hard_gate_failures": list(result.hard_gate_failures),
    }


def _decode_evidence_record(value: object) -> EvidenceRecord:
    payload = expect_mapping(value, "evidence")
    reject_unknown(payload, {"evidence_id", "citation", "quote", "numeric_tokens"}, "evidence")
    citation = decode_citation(payload.get("citation"))
    evidence_id = expect_string(payload.get("evidence_id"), "evidence_id")
    if citation.evidence_id != evidence_id:
        raise ValueError("evidence_id does not match citation evidence_id")
    return EvidenceRecord(
        evidence_id=evidence_id,
        citation=citation,
        quote=expect_string(payload.get("quote"), "quote"),
        numeric_tokens=expect_string_tuple(payload.get("numeric_tokens", []), "numeric_tokens"),
    )


def _evidence_document(record: EvidenceRecord) -> dict[str, object]:
    return {
        "evidence_id": record.evidence_id,
        "citation": _citation_document(record.citation),
        "quote": record.quote,
        "numeric_tokens": list(record.numeric_tokens),
    }


def _require_unique(values: tuple[str, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must contain unique identifiers")


def _validate_claims(
    claims: tuple[Claim, ...],
    evidence: tuple[EvidenceRecord, ...],
    calculations: tuple[CalculationResult, ...],
    compatibility_source_version: int | None,
) -> None:
    evidence_by_citation = {record.citation.citation_id: record for record in evidence}
    _require_unique(tuple(record.evidence_id for record in evidence), "evidence")
    _require_unique(tuple(claim.claim_id for claim in claims), "claims")
    calculation_tokens = {
        value
        for result in calculations
        for value in (result.raw_result, result.display_result)
        if value is not None
    }
    for claim in claims:
        if not claim.citation_ids:
            raise ValueError("claim must contain at least one citation")
        cited_records: list[EvidenceRecord] = []
        for citation_id in claim.citation_ids:
            record = evidence_by_citation.get(citation_id)
            if record is None:
                if compatibility_source_version == 1:
                    continue
                raise ValueError(f"unresolved claim citation: {citation_id}")
            cited_records.append(record)
        evidence_tokens = {
            token for record in cited_records for token in record.numeric_tokens
        }
        for token in claim.numeric_tokens:
            if token not in evidence_tokens and token not in calculation_tokens:
                raise ValueError(f"unregistered numeric token: {token}")


def decode_review_packet_v2(value: object) -> ReviewPacketV2:
    """Decode a strict Review Packet v2 document."""
    payload = expect_mapping(value, "review_packet_v2")
    if payload.get("human_decision") is not None:
        raise ValueError("human_decision must be null in a machine review packet")
    allowed = {
        "format",
        "version",
        "run_id",
        "case_id",
        "question",
        "finalizer_status",
        "snapshot_sha256",
        "rule_manifest_sha256",
        "formula_manifest_sha256",
        "claims",
        "evidence",
        "drawing_evidence",
        "confirmed_inputs",
        "calculations",
        "rule_evaluations",
        "exceptions",
        "conflicts",
        "confidence",
        "abstention_reasons",
        "human_decision",
        "compatibility_source_version",
    }
    reject_unknown(payload, allowed, "review_packet_v2")
    format_value = expect_literal(payload.get("format"), "format", _FORMATS)
    version = expect_int(payload.get("version"), "version")
    if version != 2:
        raise ValueError(f"unsupported version: {version}")
    compatibility_value = payload.get("compatibility_source_version")
    compatibility_source_version: int | None
    if compatibility_value is None:
        compatibility_source_version = None
    else:
        compatibility_source_version = expect_int(
            compatibility_value, "compatibility_source_version"
        )
        if compatibility_source_version != 1:
            raise ValueError("compatibility_source_version must be 1 or null")
    claims = tuple(
        decode_claim(item) for item in expect_sequence(payload.get("claims", []), "claims")
    )
    evidence = tuple(
        _decode_evidence_record(item)
        for item in expect_sequence(payload.get("evidence", []), "evidence")
    )
    drawing_evidence = tuple(
        decode_drawing_candidate(item)
        for item in expect_sequence(payload.get("drawing_evidence", []), "drawing_evidence")
    )
    confirmed_inputs = tuple(
        decode_confirmed_input(item)
        for item in expect_sequence(payload.get("confirmed_inputs", []), "confirmed_inputs")
    )
    calculations = tuple(
        decode_calculation_result(item)
        for item in expect_sequence(payload.get("calculations", []), "calculations")
    )
    rules = tuple(
        decode_rule_result(item)
        for item in expect_sequence(payload.get("rule_evaluations", []), "rule_evaluations")
    )
    confidence_value = payload.get("confidence")
    confidence = None if confidence_value is None else decode_confidence_result(confidence_value)
    _validate_claims(claims, evidence, calculations, compatibility_source_version)
    return ReviewPacketV2(
        format=cast(Literal["ansim/review-packet"], format_value),
        version=2,
        run_id=expect_string(payload.get("run_id"), "run_id"),
        case_id=expect_string(payload.get("case_id"), "case_id", allow_empty=True),
        question=expect_string(payload.get("question"), "question"),
        finalizer_status=expect_literal(
            payload.get("finalizer_status"), "finalizer_status", _FINALIZER_STATUSES
        ),
        snapshot_sha256=expect_sha256(payload.get("snapshot_sha256"), "snapshot_sha256"),
        rule_manifest_sha256=expect_sha256(
            payload.get("rule_manifest_sha256"), "rule_manifest_sha256"
        ),
        formula_manifest_sha256=expect_sha256(
            payload.get("formula_manifest_sha256"), "formula_manifest_sha256"
        ),
        claims=claims,
        evidence=evidence,
        drawing_evidence=drawing_evidence,
        confirmed_inputs=confirmed_inputs,
        calculations=calculations,
        rule_evaluations=rules,
        exceptions=expect_string_tuple(payload.get("exceptions", []), "exceptions"),
        conflicts=expect_string_tuple(payload.get("conflicts", []), "conflicts"),
        confidence=confidence,
        abstention_reasons=expect_string_tuple(
            payload.get("abstention_reasons", []), "abstention_reasons"
        ),
        human_decision=None,
        compatibility_source_version=compatibility_source_version,
    )


def review_packet_v2_document(packet: ReviewPacketV2) -> dict[str, object]:
    """Return the explicit canonical document for Review Packet v2."""
    return {
        "format": packet.format,
        "version": packet.version,
        "run_id": packet.run_id,
        "case_id": packet.case_id,
        "question": packet.question,
        "finalizer_status": packet.finalizer_status,
        "snapshot_sha256": packet.snapshot_sha256,
        "rule_manifest_sha256": packet.rule_manifest_sha256,
        "formula_manifest_sha256": packet.formula_manifest_sha256,
        "claims": [_claim_document(claim) for claim in packet.claims],
        "evidence": [_evidence_document(record) for record in packet.evidence],
        "drawing_evidence": [
            drawing_candidate_document(candidate) for candidate in packet.drawing_evidence
        ],
        "confirmed_inputs": [
            confirmed_input_document(confirmed) for confirmed in packet.confirmed_inputs
        ],
        "calculations": [_calculation_document(result) for result in packet.calculations],
        "rule_evaluations": [_rule_document(result) for result in packet.rule_evaluations],
        "exceptions": list(packet.exceptions),
        "conflicts": list(packet.conflicts),
        "confidence": (
            None if packet.confidence is None else _confidence_document(packet.confidence)
        ),
        "abstention_reasons": list(packet.abstention_reasons),
        "human_decision": None,
        "compatibility_source_version": packet.compatibility_source_version,
    }
