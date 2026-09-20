from __future__ import annotations

import hashlib
from pathlib import Path

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.evidence.finalization import (
    FinalizedEvidenceState,
    finalize_evidence_database,
    validate_finalized_evidence,
)
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_run import prepare_review_run, submit_track_a


def create_finalized_evidence_database(path: Path) -> FinalizedEvidenceState:
    """Create the canonical finalized evidence authority for release tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(store, EvidenceSnapshot())
        return finalize_evidence_database(store)


def write_valid_finalized_run(
    workspace: Path,
    *,
    evidence_path: Path | None = None,
    packet_snapshot_sha256: str | None = None,
) -> str:
    """Create a final packet bound to a canonical finalized evidence snapshot."""
    if evidence_path is None:
        evidence_path = workspace / "evidence" / "evidence.sqlite"
        legacy_path = workspace / "evidence" / "ansim-evidence.sqlite"
        if legacy_path.is_file() and not evidence_path.exists():
            evidence_path = legacy_path
    if evidence_path.is_file():
        with EvidenceStore(evidence_path, read_only=True) as store:
            evidence_state = validate_finalized_evidence(store)
    else:
        evidence_state = create_finalized_evidence_database(evidence_path)
    bound_snapshot = packet_snapshot_sha256 or evidence_state.snapshot_hash
    evidence_provenance = {
        "evidence_snapshot_hash": bound_snapshot,
        "evidence_db_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "schema_version": evidence_state.schema_version,
        "retrieval_record_count": evidence_state.retrieval_record_count,
        "clause_record_count": evidence_state.clause_record_count,
    }

    request_path = workspace / "release-fixture-request.json"
    request_path.write_bytes(
        dump_bytes(
            {
                "format": "ansim/review-run-request",
                "version": 1,
                "question": "Release fixture final packet",
                "inputs": {
                    "snapshot_hash": bound_snapshot,
                    "evidence_snapshot_provenance": evidence_provenance,
                },
                "evidence": [],
                "calculations": [],
                "rules": [],
                "approved_rule_result_ids": [],
                "confidence_input": {
                    "factors": {
                        name: {
                            "value": "1.0",
                            "source": f"fixture:{name}",
                        }
                        for name in FACTOR_WEIGHTS
                    }
                },
            }
        )
    )
    prepared = prepare_review_run(workspace, request_path)
    track_a_path = workspace / "release-fixture-track-a.json"
    track_a_path.write_bytes(
        dump_bytes(
            {
                "run_id": prepared.run_id,
                "claims": [],
                "citations": [],
                "missing_inputs": [],
                "exceptions": [],
                "conflicts": [],
                "explanation": "The release fixture contains no claims.",
            }
        )
    )
    submit_track_a(workspace, prepared.run_id, track_a_path)

    run_directory = prepared.run_directory
    (run_directory / "track-b-output.json").write_bytes(
        dump_bytes(
            {
                "run_id": prepared.run_id,
                "audited_question": "Release fixture final packet",
                "question_responsiveness": "NOT_VERIFIED",
                "required_facet_completeness": "NOT_APPLICABLE",
                "claim_audits": [],
                "overall_disposition": "INCOMPLETE",
            }
        )
    )
    required = (
        "track-a-bundle.json",
        "track-a-output.json",
        "track-b-output.json",
        "confidence-input.json",
    )
    artifacts = {
        name: hashlib.sha256((run_directory / name).read_bytes()).hexdigest()
        for name in required
    }
    (run_directory / "run-manifest.json").write_bytes(
        dump_bytes({"run_id": prepared.run_id, "artifacts": artifacts})
    )
    finalize_run(run_directory)
    return prepared.run_id
