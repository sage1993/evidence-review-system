"""Build a read-only reviewer view model from a finalized machine packet."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.review import ReviewPacket
from ansim_review.evidence.store import EvidenceStore

_DECISION_OPTIONS = (
    "SATISFIED",
    "NOT_SATISFIED",
    "CONDITIONAL",
    "ADDITIONAL_REVIEW_REQUIRED",
)


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
        raise ValueError(f"{field} must be a string")
    return value


def _packet_document(packet: object) -> tuple[Mapping[str, object], bytes]:
    if isinstance(packet, bytes):
        try:
            document = json.loads(packet.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("packet bytes must contain UTF-8 JSON") from error
        return _mapping(document, "packet"), packet
    if isinstance(packet, Mapping):
        document = _mapping(packet, "packet")
        return document, dump_bytes(document)
    if isinstance(packet, ReviewPacket):
        from ansim_review.abstention.finalizer import review_packet_document

        document = _mapping(review_packet_document(packet), "packet")
        return document, dump_bytes(document)
    raise ValueError("packet must be bytes, a mapping, or ReviewPacket")


def _evidence_id(citation_id: str) -> str:
    if not citation_id.startswith("CIT-") or len(citation_id) <= 4:
        raise ValueError(f"unsupported citation id: {citation_id}")
    return citation_id[4:]


def _bbox(value: object) -> list[float]:
    parsed = json.loads(_string(value, "bbox_json"))
    items = _sequence(parsed, "bbox_json")
    if len(items) != 4:
        raise ValueError("bbox_json must contain four numbers")
    result: list[float] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("bbox_json must contain four numbers")
        result.append(float(item))
    return result


def _resolve_citation(
    connection: sqlite3.Connection, citation_id: str
) -> dict[str, object]:
    evidence_id = _evidence_id(citation_id)
    row = connection.execute(
        """SELECT evidence_id, document_id, revision_id, page_number, bbox_json,
                  source_hash, title, raw_text, evidence_type
             FROM retrieval_records WHERE evidence_id = ?""",
        (evidence_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unresolved citation: {citation_id}")
    if not isinstance(row[6], str) or not isinstance(row[7], str):
        raise ValueError(f"incomplete evidence record: {evidence_id}")
    return {
        "citation_id": citation_id,
        "evidence_id": row[0],
        "document_id": row[1],
        "revision_id": row[2],
        "page_number": row[3],
        "bbox": _bbox(row[4]),
        "source_hash": row[5],
        "title": row[6],
        "quote": row[7],
        "evidence_type": row[8],
    }


def _list_of_mappings(value: object, field: str) -> list[dict[str, object]]:
    return [
        dict(_mapping(item, f"{field}[{index}]"))
        for index, item in enumerate(_sequence(value, field))
    ]


def _exception_codes(rules: Sequence[Mapping[str, object]]) -> list[str]:
    codes: set[str] = set()
    for index, rule in enumerate(rules):
        for item in _sequence(rule.get("reason_codes", []), f"rules[{index}].reason_codes"):
            code = _string(item, f"rules[{index}].reason_codes")
            if "EXCEPTION" in code:
                codes.add(code)
    return sorted(codes)


def _strings(value: object, field: str) -> list[str]:
    return [
        _string(item, f"{field}[{index}]")
        for index, item in enumerate(_sequence(value, field))
    ]


def _packet_sha256(packet_bytes: bytes) -> str:
    """Hash the exact packet bytes supplied to the projection."""
    return hashlib.sha256(packet_bytes).hexdigest()


def _status(document: Mapping[str, object]) -> str:
    if document.get("version") == 2:
        return _string(document.get("finalizer_status"), "finalizer_status")
    return _string(document.get("status"), "status")


def _rules(document: Mapping[str, object]) -> list[dict[str, object]]:
    field = "rule_evaluations" if document.get("version") == 2 else "rules"
    return _list_of_mappings(document.get(field, []), field)


def _citation_identity(citation: Mapping[str, object]) -> dict[str, object]:
    return {
        "citation_id": _string(citation.get("citation_id"), "citation.citation_id"),
        "evidence_id": _string(citation.get("evidence_id"), "citation.evidence_id"),
        "document_id": _string(citation.get("document_id"), "citation.document_id"),
        "revision_id": _string(citation.get("revision_id"), "citation.revision_id"),
        "page_number": citation.get("page_number"),
        "bbox": _sequence(citation.get("bbox"), "citation.bbox"),
        "source_hash": _string(citation.get("source_hash"), "citation.source_hash"),
    }


def _verify_citation_identity(
    citation: Mapping[str, object], resolved: Mapping[str, object]
) -> None:
    identity = _citation_identity(citation)
    for field, value in identity.items():
        if value != resolved[field]:
            raise ValueError("citation identity does not match evidence database")


def _v2_citations(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    if document.get("version") != 2:
        return {}
    citations: dict[str, Mapping[str, object]] = {}
    for index, item in enumerate(_sequence(document.get("evidence", []), "evidence")):
        record = _mapping(item, f"evidence[{index}]")
        evidence_id = _string(record.get("evidence_id"), f"evidence[{index}].evidence_id")
        citation = _mapping(record.get("citation"), f"evidence[{index}].citation")
        identity = _citation_identity(citation)
        if identity["evidence_id"] != evidence_id:
            raise ValueError("citation identity does not match evidence record")
        citation_id = cast(str, identity["citation_id"])
        prior = citations.get(citation_id)
        if prior is not None and _citation_identity(prior) != identity:
            raise ValueError("conflicting citation identity")
        citations[citation_id] = citation
    return citations


def _build_review_items(
    claims: Sequence[Mapping[str, object]],
    calculations: Sequence[Mapping[str, object]],
    rules: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Build deterministic claim-first review items from resolved relationships."""
    calculation_ids = {
        _string(item.get("calculation_result_id"), "calculation_result_id")
        for item in calculations
    }
    items: list[dict[str, object]] = []
    for claim in claims:
        claim_id = _string(claim.get("claim_id"), "claim_id")
        citation_ids = _strings(claim.get("citation_ids", []), "citation_ids")
        related_rules = [
            rule
            for rule in rules
            if set(citation_ids)
            & {
                _string(citation.get("citation_id"), "rule.citation_id")
                for citation in _list_of_mappings(rule.get("citations", []), "rule.citations")
            }
        ]
        if not related_rules and len(claims) == 1:
            related_rules = list(rules)
        rule_result_ids = [
            _string(rule.get("rule_result_id"), "rule_result_id")
            for rule in related_rules
        ]
        calculation_result_ids = [
            calculation_id
            for rule in related_rules
            for calculation_id in _strings(
                rule.get("calculation_result_ids", []), "calculation_result_ids"
            )
            if calculation_id in calculation_ids
        ]
        missing_inputs = [
            value
            for rule in related_rules
            for value in _strings(rule.get("missing_inputs", []), "missing_inputs")
        ]
        complete = bool(citation_ids) and not missing_inputs
        if len(related_rules) == 1:
            status = _string(related_rules[0].get("status"), "rule.status")
            evaluation_id: str | None = rule_result_ids[0]
        elif related_rules:
            status = "INDETERMINATE"
            evaluation_id = None
        else:
            status = "INDETERMINATE"
            evaluation_id = None
        items.append(
            {
                "item_id": f"ITEM-{claim_id}",
                "claim_id": claim_id,
                "evaluation_id": evaluation_id,
                "status": status,
                "completeness": "COMPLETE" if complete else "INCOMPLETE",
                "citation_ids": citation_ids,
                "calculation_ids": calculation_result_ids,
                "rule_ids": [
                    _string(rule.get("rule_id"), "rule_id") for rule in related_rules
                ],
                "confirmation_required": bool(missing_inputs),
            }
        )
    return items


def _summary(
    citations: Sequence[Mapping[str, object]],
    calculations: Sequence[Mapping[str, object]],
    rules: Sequence[Mapping[str, object]],
    confidence: Mapping[str, object] | None,
    exceptions: Sequence[str],
    conflicts: Sequence[str],
) -> dict[str, object]:
    """Summarize only records that reached the resolved projection."""
    resolved_citation_ids = {
        _string(citation.get("citation_id"), "citation_id") for citation in citations
    }
    resolved_calculations = [
        calculation
        for calculation in calculations
        if _string(calculation.get("status"), "calculation.status") == "SUCCESS"
    ]
    missing_inputs = {
        value
        for rule in rules
        for value in _strings(rule.get("missing_inputs", []), "missing_inputs")
    }
    return {
        "citation_count": len(resolved_citation_ids),
        "approved_rule_count": len(rules),
        "calculation_count": len(resolved_calculations),
        "missing_input_count": len(missing_inputs),
        "exception_count": len(exceptions),
        "conflict_count": len(conflicts),
        "confidence_score": None if confidence is None else confidence.get("score"),
        "confidence_level": None if confidence is None else confidence.get("level"),
    }


def build_review_view_model(packet: object, evidence_db: Path) -> dict[str, object]:
    """Resolve display evidence from packet bytes or compatible packet objects."""
    document, packet_bytes = _packet_document(packet)
    if document.get("human_decision") is not None:
        raise ValueError("machine packet human_decision must be null")
    status = _status(document)
    packet_sha256 = _packet_sha256(packet_bytes)
    rule_documents = _rules(document)
    provided_citations = _v2_citations(document)
    claims: list[dict[str, object]] = []
    resolved_citations: dict[str, dict[str, object]] = {}
    with EvidenceStore(evidence_db) as store:
        connection = store.require_connection()
        for index, item in enumerate(_sequence(document.get("claims", []), "claims")):
            claim = _mapping(item, f"claims[{index}]")
            citation_ids = tuple(
                _string(value, f"claims[{index}].citation_ids")
                for value in _sequence(claim.get("citation_ids", []), "citation_ids")
            )
            citations = []
            for citation_id in citation_ids:
                resolved = _resolve_citation(connection, citation_id)
                provided = provided_citations.get(citation_id)
                if provided is not None:
                    _verify_citation_identity(provided, resolved)
                resolved_citations.setdefault(citation_id, resolved)
                citations.append(resolved)
            claims.append(
                {
                    "claim_id": _string(claim.get("claim_id"), "claim_id"),
                    "text": _string(claim.get("text"), "text", allow_empty=True),
                    "citation_ids": list(citation_ids),
                    "numeric_tokens": list(
                        _sequence(claim.get("numeric_tokens", []), "numeric_tokens")
                    ),
                    "citations": citations,
                }
            )

        for rule in rule_documents:
            for citation in _list_of_mappings(rule.get("citations", []), "rule.citations"):
                citation_id = _string(citation.get("citation_id"), "rule.citation_id")
                resolved = _resolve_citation(connection, citation_id)
                _verify_citation_identity(citation, resolved)
                resolved_citations.setdefault(citation_id, resolved)
        for citation_id, provided_citation in provided_citations.items():
            resolved = _resolve_citation(connection, citation_id)
            _verify_citation_identity(provided_citation, resolved)

    reasons = [
        _string(item, "abstention_reason")
        for item in _sequence(
            document.get("abstention_reasons", []), "abstention_reasons"
        )
    ]
    exceptions = (
        _strings(document.get("exceptions", []), "exceptions")
        if document.get("version") == 2
        else _exception_codes(rule_documents)
    )
    conflicts = (
        _strings(document.get("conflicts", []), "conflicts")
        if document.get("version") == 2
        else [reason for reason in reasons if "CONFLICT" in reason]
    )
    confidence_value = document.get("confidence")
    confidence = (
        None
        if confidence_value is None
        else dict(_mapping(confidence_value, "confidence"))
    )
    calculations = _list_of_mappings(document.get("calculations", []), "calculations")
    review_items = _build_review_items(claims, calculations, rule_documents)
    metadata = {
        "run_id": _string(document.get("run_id"), "run_id"),
        "case_id": document.get("case_id"),
        "status": status,
        "snapshot_sha256": document.get("snapshot_sha256"),
        "rule_manifest_sha256": document.get("rule_manifest_sha256"),
        "formula_manifest_sha256": document.get("formula_manifest_sha256"),
        "packet_sha256": packet_sha256,
    }
    model: dict[str, object] = {
        "run_id": metadata["run_id"],
        "status": status,
        "display_status": status,
        "human_decision": None,
        "decision_options": [],
        "question": _string(document.get("question"), "question"),
        "claims": claims,
        "calculations": calculations,
        "rules": rule_documents,
        "confidence": confidence,
        "exceptions": exceptions,
        "conflicts": conflicts,
        "abstention_reasons": reasons,
        "metadata": metadata,
        "summary": _summary(
            list(resolved_citations.values()),
            calculations,
            rule_documents,
            confidence,
            exceptions,
            conflicts,
        ),
        "review_items": review_items,
        "audit": {
            "track_a_status": document.get("track_a_status"),
            "track_b_status": document.get("track_b_status"),
            "uncited_count": sum(
                not _strings(claim.get("citation_ids", []), "citation_ids")
                for claim in claims
            ),
            "confidence_factors": []
            if confidence is None
            else list(_sequence(confidence.get("factors", []), "confidence.factors")),
            "exceptions": exceptions,
            "conflicts": conflicts,
            "abstention_reasons": reasons,
        },
        "decision": {
            "allowed_values": list(_DECISION_OPTIONS),
            "human_decision": None,
            "packet_sha256": packet_sha256,
        },
    }
    if document.get("version") == 2:
        model.update(
            {
                "format": document.get("format"),
                "version": 2,
                "case_id": metadata["case_id"],
                "finalizer_status": status,
                "snapshot_sha256": metadata["snapshot_sha256"],
                "rule_manifest_sha256": metadata["rule_manifest_sha256"],
                "formula_manifest_sha256": metadata["formula_manifest_sha256"],
                "evidence": _list_of_mappings(document.get("evidence", []), "evidence"),
                "drawing_evidence": _list_of_mappings(
                    document.get("drawing_evidence", []), "drawing_evidence"
                ),
                "confirmed_inputs": _list_of_mappings(
                    document.get("confirmed_inputs", []), "confirmed_inputs"
                ),
                "rule_evaluations": rule_documents,
                "compatibility_source_version": document.get(
                    "compatibility_source_version"
                ),
            }
        )
    return model
