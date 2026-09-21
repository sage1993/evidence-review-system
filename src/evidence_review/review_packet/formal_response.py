"""Read-only user response projection bound to the verified final packet."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from evidence_review.abstention.finalizer import verify_finalized_run_with_snapshot
from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.codecs import decode_review_packet
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def build_formal_response(workspace_root: Path, run_id: str) -> dict[str, object]:
    """Copy only packet claims and their manifest-verified citation identities."""
    workspace = verified_regular_directory(workspace_root, field="workspace")
    runs = verified_regular_directory(workspace / "runs", field="runs")
    run = verified_regular_directory(
        runs / validate_identifier(run_id, "run_id"), field="run",
    )
    packet, snapshot = verify_finalized_run_with_snapshot(run)
    packet_path = verified_regular_file_below(
        run, ("final-review-packet.json",), field="final packet",
    )
    packet_bytes = packet_path.read_bytes()
    if decode_review_packet(json.loads(packet_bytes)) != packet:
        raise ValueError("packet changed during formal response generation")
    if packet.run_id != run_id or snapshot.run_id != run_id:
        raise ValueError("formal response run does not match packet")

    bundle = _object(snapshot.document("track-a-bundle.json"), "verified bundle")
    evidence = bundle.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("verified bundle evidence must be an array")
    citations: dict[str, dict[str, object]] = {}
    for item in evidence:
        citation = dict(_object(_object(item, "evidence").get("citation"), "citation"))
        citation_id = citation.get("citation_id")
        if not isinstance(citation_id, str) or not citation.get("evidence_id"):
            raise ValueError("formal citation lacks evidence identity")
        if citation_id in citations and citations[citation_id] != citation:
            raise ValueError("formal citation identity is ambiguous")
        citations[citation_id] = citation

    statements: list[dict[str, object]] = []
    for claim in packet.claims:
        if not claim.citation_ids or any(key not in citations for key in claim.citation_ids):
            raise ValueError("formal claim is not bound to verified evidence")
        statements.append({
            "classification": "FORMAL_FINDING",
            "claim_id": claim.claim_id,
            "text": claim.text,
            "issue_ids": list(claim.issue_ids),
            "citations": [citations[key] for key in claim.citation_ids],
        })
    return {
        "format": "evidence-review/formal-response",
        "version": 1,
        "run_id": run_id,
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "status": packet.status,
        "human_decision": None,
        "question": packet.question,
        "abstention_reasons": list(packet.abstention_reasons),
        "missing_inputs": list(packet.missing_inputs),
        "statements": statements,
    }


def validate_formal_response(
    response: object, workspace_root: Path, run_id: str,
) -> dict[str, object]:
    """Reject expanded prose, substituted lineage and non-formal categories."""
    expected = build_formal_response(workspace_root, run_id)
    if dump_bytes(response) != dump_bytes(expected):
        raise ValueError("formal response is not the exact packet-bound projection")
    return expected
