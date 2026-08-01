"""Build a read-only reviewer view model from a finalized machine packet."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast


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


def _packet_document(packet: object) -> Mapping[str, object]:
    if isinstance(packet, Mapping):
        return _mapping(packet, "packet")
    if hasattr(packet, "__dataclass_fields__"):
        from ansim_review.abstention.finalizer import review_packet_document

        return _mapping(review_packet_document(packet), "packet")
    raise ValueError("packet must be a mapping or ReviewPacket")


def _evidence_id(citation_id: str) -> str:
    if not citation_id.startswith("CIT-") or len(citation_id) <= 4:
        raise ValueError(f"unsupported citation id: {citation_id}")
    return citation_id[4:]


def _bbox(value: object) -> list[float]:
    parsed = json.loads(_string(value, "bbox_json"))
    items = _sequence(parsed, "bbox_json")
    if len(items) != 4 or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in items
    ):
        raise ValueError("bbox_json must contain four numbers")
    return [float(item) for item in items]


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


def build_review_view_model(packet: object, evidence_db: Path) -> dict[str, object]:
    """Resolve display evidence from SQLite while preserving machine output unchanged."""
    document = _packet_document(packet)
    if document.get("human_decision") is not None:
        raise ValueError("machine packet human_decision must be null")
    claims: list[dict[str, object]] = []
    connection = sqlite3.connect(evidence_db)
    try:
        for index, item in enumerate(_sequence(document.get("claims", []), "claims")):
            claim = _mapping(item, f"claims[{index}]")
            citation_ids = tuple(
                _string(value, f"claims[{index}].citation_ids")
                for value in _sequence(claim.get("citation_ids", []), "citation_ids")
            )
            claims.append(
                {
                    "claim_id": _string(claim.get("claim_id"), "claim_id"),
                    "text": _string(claim.get("text"), "text", allow_empty=True),
                    "numeric_tokens": list(
                        _sequence(claim.get("numeric_tokens", []), "numeric_tokens")
                    ),
                    "citations": [
                        _resolve_citation(connection, citation_id)
                        for citation_id in citation_ids
                    ],
                }
            )
    finally:
        connection.close()

    reasons = [
        _string(item, "abstention_reason")
        for item in _sequence(
            document.get("abstention_reasons", []), "abstention_reasons"
        )
    ]
    rules = _list_of_mappings(document.get("rules", []), "rules")
    exceptions = sorted(
        {
            code
            for rule in rules
            for code in rule.get("reason_codes", [])
            if isinstance(code, str) and "EXCEPTION" in code
        }
    )
    conflicts = [reason for reason in reasons if "CONFLICT" in reason]
    confidence_value = document.get("confidence")
    confidence = (
        None
        if confidence_value is None
        else dict(_mapping(confidence_value, "confidence"))
    )
    return {
        "run_id": _string(document.get("run_id"), "run_id"),
        "status": _string(document.get("status"), "status"),
        "human_decision": None,
        "decision_options": [],
        "question": _string(document.get("question"), "question"),
        "claims": claims,
        "calculations": _list_of_mappings(
            document.get("calculations", []), "calculations"
        ),
        "rules": rules,
        "confidence": confidence,
        "exceptions": exceptions,
        "conflicts": conflicts,
        "abstention_reasons": reasons,
    }
