from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.review_packet.decision_record import write_human_decision
from evidence_review.review_run import prepare_review_run


def _finalized_legacy_run(tmp_path: Path) -> Path:
    workspace = tmp_path / "legacy-workspace"
    workspace.mkdir()
    request_path = workspace / "request.json"
    request_path.write_bytes(
        dump_bytes(
            {
                "format": "evidence-review/review-run-request",
                "version": 1,
                "question": "Historical formal review",
                "inputs": {},
                "evidence": [],
                "calculations": [],
                "rules": [],
                "approved_rule_result_ids": [],
                "confidence_input": {
                    "factors": {
                        name: {"value": "1.0", "source": "fixture"}
                        for name in FACTOR_WEIGHTS
                    }
                },
            }
        )
    )
    prepared = prepare_review_run(workspace, request_path)
    run_directory = prepared.run_directory
    bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    (run_directory / "track-a-output.json").write_bytes(
        dump_bytes(
            {
                "run_id": bundle["run_id"],
                "claims": [],
                "citations": [],
                "missing_inputs": [],
                "exceptions": [],
                "conflicts": [],
                "explanation": "No claims are required.",
            }
        )
    )
    (run_directory / "track-b-output.json").write_bytes(
        dump_bytes(
            {
                "run_id": bundle["run_id"],
                "claim_audits": [],
                "overall_disposition": "INCOMPLETE",
            }
        )
    )
    artifacts = {
        name: hashlib.sha256((run_directory / name).read_bytes()).hexdigest()
        for name in (
            "track-a-bundle.json",
            "track-a-output.json",
            "track-b-output.json",
            "confidence-input.json",
        )
    }
    (run_directory / "run-manifest.json").write_bytes(
        dump_bytes({"run_id": bundle["run_id"], "artifacts": artifacts})
    )
    finalize_run(run_directory)
    return run_directory


def test_legacy_run_reference_does_not_invent_matter_history(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_legacy_run(tmp_path)
    packet_path = run_directory / "final-review-packet.json"
    packet_bytes = packet_path.read_bytes()
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    decision_path = write_human_decision(
        run_directory,
        reviewer_id="reviewer-01",
        reviewed_at="2026-09-11T09:00:00+00:00",
        packet_hash=packet_sha256,
        decision="SATISFIED",
        notes="",
    )
    decision_bytes = decision_path.read_bytes()

    reference = legacy_reference_from_run(run_directory)

    assert reference.run_id == run_directory.name
    assert reference.packet_sha256 == packet_sha256
    assert reference.matter_revision is None
    assert reference.matter_issue_ids == ()
    assert reference.source_impact_history == ()
    assert reference.compatibility_status == "LEGACY_FORMAL_RUN"
    assert tuple(field.name for field in fields(reference)) == (
        "run_id",
        "packet_sha256",
        "human_decisions",
        "matter_revision",
        "matter_issue_ids",
        "source_impact_history",
        "compatibility_status",
    )
    assert len(reference.human_decisions) == 1
    assert reference.human_decisions[0].filename == decision_path.name
    assert reference.human_decisions[0].sha256 == hashlib.sha256(decision_bytes).hexdigest()
    assert packet_path.read_bytes() == packet_bytes
    assert decision_path.read_bytes() == decision_bytes
