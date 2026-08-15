"""Manifest-verified review-packet finalization with deterministic abstention."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

from evidence_review.abstention.gates import AbstentionContext, evaluate_abstention_gates
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.scorer import FactorInput, score_confidence
from evidence_review.contracts.codecs import (
    decode_calculation_result,
    decode_citation,
    decode_review_packet,
    decode_rule_result,
)
from evidence_review.contracts.common import Citation
from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.contracts.review import ConfidenceResult, ReviewPacket
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    TrackABundle,
    build_track_a_bundle,
    validate_track_a_output,
)
from evidence_review.llm_layer.track_b import validate_track_b_output
from evidence_review.llm_layer.validators import validate_track_a_integrity

_REQUIRED_ARTIFACTS = (
    "track-a-bundle.json",
    "track-a-output.json",
    "track-b-output.json",
    "confidence-input.json",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{field} must be {qualifier}")
    return value


def _json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON artifact: {path.name}") from error


def _verify_manifest(run_directory: Path) -> tuple[str, dict[str, Path]]:
    manifest = _mapping(_json_file(run_directory / "run-manifest.json"), "run_manifest")
    unknown = sorted(set(manifest) - {"run_id", "artifacts"})
    if unknown:
        raise ValueError(f"run_manifest has unknown fields: {', '.join(unknown)}")
    run_id = _string(manifest.get("run_id"), "run_manifest.run_id")
    if run_directory.name != run_id:
        raise ValueError("run directory name does not match manifest run_id")
    artifacts = _mapping(manifest.get("artifacts"), "run_manifest.artifacts")
    missing = sorted(set(_REQUIRED_ARTIFACTS) - set(artifacts))
    if missing:
        raise ValueError(f"run manifest is missing artifacts: {', '.join(missing)}")
    verified: dict[str, Path] = {}
    for name in _REQUIRED_ARTIFACTS:
        if Path(name).name != name:
            raise ValueError(f"invalid artifact path: {name}")
        expected = _string(artifacts.get(name), f"run_manifest.artifacts.{name}")
        if not _SHA256.fullmatch(expected):
            raise ValueError(f"invalid artifact hash: {name}")
        artifact_path = run_directory / name
        try:
            data = artifact_path.read_bytes()
        except OSError as error:
            raise ValueError(f"missing artifact: {name}") from error
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"artifact hash mismatch: {name}")
        verified[name] = artifact_path
    return run_id, verified


def _decode_bundle(value: object) -> TrackABundle:
    payload = _mapping(value, "track_a_bundle")
    allowed = {
        "run_id",
        "question",
        "inputs",
        "evidence",
        "rules",
        "calculations",
        "approved_rule_result_ids",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"track_a_bundle has unknown fields: {', '.join(unknown)}")
    evidence: list[EvidenceExcerpt] = []
    for index, item in enumerate(_sequence(payload.get("evidence"), "evidence")):
        evidence_payload = _mapping(item, f"evidence[{index}]")
        if set(evidence_payload) != {"citation", "text"}:
            raise ValueError(f"evidence[{index}] must contain citation and text")
        evidence.append(
            EvidenceExcerpt(
                citation=decode_citation(evidence_payload.get("citation")),
                text=_string(evidence_payload.get("text"), f"evidence[{index}].text"),
            )
        )
    rules = tuple(
        decode_rule_result(item)
        for item in _sequence(payload.get("rules"), "rules")
    )
    calculations = tuple(
        decode_calculation_result(item)
        for item in _sequence(payload.get("calculations"), "calculations")
    )
    inputs = _mapping(payload.get("inputs"), "inputs")
    approved = tuple(
        _string(item, f"approved_rule_result_ids[{index}]")
        for index, item in enumerate(
            _sequence(payload.get("approved_rule_result_ids", []), "approved_rule_result_ids")
        )
    )
    return build_track_a_bundle(
        run_id=_string(payload.get("run_id"), "run_id"),
        question=_string(payload.get("question"), "question"),
        inputs=dict(inputs),
        evidence=tuple(evidence),
        rules=rules,
        calculations=calculations,
        approved_rule_result_ids=approved,
    )


def _decode_confidence_inputs(value: object) -> dict[str, FactorInput]:
    payload = _mapping(value, "confidence_input")
    if set(payload) != {"factors"}:
        raise ValueError("confidence_input must contain only factors")
    factors_payload = _mapping(payload.get("factors"), "confidence_input.factors")
    factors: dict[str, FactorInput] = {}
    for name, item in factors_payload.items():
        factor = _mapping(item, f"confidence_input.factors.{name}")
        if set(factor) != {"value", "source"}:
            raise ValueError(f"confidence factor {name} must contain value and source")
        factors[name] = FactorInput(
            value=_string(factor.get("value"), f"confidence_input.factors.{name}.value"),
            source=_string(factor.get("source"), f"confidence_input.factors.{name}.source"),
        )
    return factors


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


def review_packet_document(packet: ReviewPacket) -> dict[str, object]:
    """Return the canonical final machine packet with a null human decision."""
    document: dict[str, object] = {
        "run_id": packet.run_id,
        "status": packet.status,
        "human_decision": None,
        "question": packet.question,
        "claims": [
            {
                "claim_id": claim.claim_id,
                "text": claim.text,
                "citation_ids": list(claim.citation_ids),
                "numeric_tokens": list(claim.numeric_tokens),
            }
            for claim in packet.claims
        ],
        "calculations": [_calculation_document(result) for result in packet.calculations],
        "rules": [_rule_document(result) for result in packet.rules],
        "confidence": (
            None
            if packet.confidence is None
            else _confidence_document(packet.confidence)
        ),
        "abstention_reasons": list(packet.abstention_reasons),
    }
    if "snapshot_sha256" in packet._serialized_lineage_fields:
        document["snapshot_sha256"] = packet.snapshot_sha256
    if "missing_inputs" in packet._serialized_lineage_fields:
        document["missing_inputs"] = list(packet.missing_inputs)
    return document


def _finding_codes(track_b_output: object) -> set[str]:
    payload = _mapping(track_b_output, "track_b")
    codes: set[str] = set()
    for item in _sequence(payload.get("claim_audits"), "claim_audits"):
        audit = _mapping(item, "claim_audit")
        for code in _sequence(audit.get("finding_codes", []), "finding_codes"):
            codes.add(_string(code, "finding_code"))
    return codes


def expected_final_review_packet(run_directory: Path) -> ReviewPacket:
    """Derive the only valid machine packet from manifest-bound artifacts."""
    manifest_run_id, paths = _verify_manifest(run_directory)
    bundle = _decode_bundle(_json_file(paths["track-a-bundle.json"]))
    if bundle.run_id != manifest_run_id:
        raise ValueError("bundle run_id does not match manifest")
    track_a_output = _json_file(paths["track-a-output.json"])
    validated_a = validate_track_a_output(track_a_output, bundle)
    validate_track_a_integrity(validated_a, bundle)
    track_b_output = _json_file(paths["track-b-output.json"])
    audit = validate_track_b_output(track_b_output, validated_a)
    confidence = score_confidence(
        _decode_confidence_inputs(_json_file(paths["confidence-input.json"]))
    )

    snapshot_value = bundle.inputs.get("snapshot_hash")
    snapshot_sha256: str | None
    if snapshot_value is None:
        snapshot_sha256 = None
    else:
        snapshot_sha256 = _string(snapshot_value, "snapshot_hash")
        if not _SHA256.fullmatch(snapshot_sha256):
            raise ValueError("snapshot_hash must be a lowercase SHA-256 digest")
    missing_inputs = tuple(
        sorted(
            set(validated_a.draft.missing_inputs)
            | {item for result in bundle.rules for item in result.missing_inputs}
        )
    )
    finding_codes = _finding_codes(track_b_output)
    approved = set(bundle.approved_rule_result_ids)
    context = AbstentionContext(
        confidence_score=confidence.score,
        missing_required_input=bool(missing_inputs),
        uncited_or_unresolved_claim=audit.overall_disposition == "INCOMPLETE"
        or bool({"CITATION_MISMATCH", "UNSUPPORTED_CLAIM", "MISSING_EXCEPTION"} & finding_codes),
        unapproved_rule=any(result.rule_result_id not in approved for result in bundle.rules),
        math_engine_error=any(result.status != "SUCCESS" for result in bundle.calculations)
        or any(result.status == "ENGINE_ERROR" for result in bundle.rules),
        source_hash_mismatch=False,
        unresolved_conflict=bool(validated_a.draft.conflicts) or "SOURCE_CONFLICT" in finding_codes,
        track_b_rejection=audit.overall_disposition == "REJECT",
        machine_set_human_decision=False,
        unregistered_numeric_value=False,
    )
    reasons = evaluate_abstention_gates(context)
    if reasons:
        confidence = replace(confidence, level="LOW", hard_gate_failures=reasons)
    packet = ReviewPacket(
        run_id=manifest_run_id,
        status="ABSTAIN" if reasons else "READY_FOR_HUMAN_REVIEW",
        human_decision=None,
        question=bundle.question,
        claims=validated_a.draft.claims,
        calculations=bundle.calculations,
        rules=bundle.rules,
        confidence=confidence,
        abstention_reasons=reasons,
        snapshot_sha256=snapshot_sha256,
        missing_inputs=missing_inputs,
    )
    return packet


def verify_finalized_run(run_directory: Path) -> ReviewPacket:
    """Fail closed unless the stored final packet equals the derived packet."""
    output_path = run_directory / "final-review-packet.json"
    if not output_path.is_file():
        raise ValueError("final review packet is missing")
    packet = decode_review_packet(_json_file(output_path))
    expected = expected_final_review_packet(run_directory)
    if packet != expected:
        raise ValueError("final review packet does not match manifest-bound artifacts")
    return packet


def finalize_run(run_directory: Path) -> ReviewPacket:
    """Validate manifest-bound artifacts and exclusively write a final packet."""
    output_path = run_directory / "final-review-packet.json"
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    packet = expected_final_review_packet(run_directory)
    data = dump_bytes(review_packet_document(packet))
    try:
        with output_path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        raise
    return packet
