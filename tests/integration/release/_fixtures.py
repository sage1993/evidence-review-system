from __future__ import annotations

import hashlib
from pathlib import Path

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.review_run import prepare_review_run, submit_track_a


def write_valid_finalized_run(workspace: Path) -> str:
    """Create one minimal canonical final run for release integration tests."""
    request_path = workspace / "release-fixture-request.json"
    request_path.write_bytes(
        dump_bytes(
            {
                "format": "ansim/review-run-request",
                "version": 1,
                "question": "Release fixture final packet",
                "inputs": {},
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
