from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path

import pytest

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import MatterIssue, MatterSourceBinding
from evidence_review.review_matter.formalization import formalize_snapshot
from evidence_review.review_matter.snapshot import create_formalization_snapshot
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore
from evidence_review.review_packet.decision_record import write_human_decision
from evidence_review.review_run import prepare_review_run


def _finalize_prepared_run(run_directory: Path) -> Path:
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
                "audited_question": bundle["question"],
                "question_responsiveness": "NOT_VERIFIED",
                "required_facet_completeness": "NOT_APPLICABLE",
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
    return _finalize_prepared_run(prepared.run_directory)


def _evidence_database(path: Path) -> dict[str, object]:
    text = "Exact reference text"
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-SNAP-1", "title": "Snapshot source"},),
                revisions=(
                    {
                        "id": "REV-SNAP-1",
                        "document_id": "DOC-SNAP-1",
                        "source_hash": "a" * 64,
                        "byte_size": len(text.encode("utf-8")),
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "PAGE-SNAP-1",
                        "revision_id": "REV-SNAP-1",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "EVID-SNAP-1",
                        "page_id": "PAGE-SNAP-1",
                        "element_type": "paragraph",
                        "raw_json": {"text": text},
                        "raw_text": text,
                        "normalized_text": text,
                        "raw_payload_hash": "d" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        finalize_evidence_database(store)
    return finalized_evidence_provenance(path)


def _matter_store(path: Path, provenance: dict[str, object]) -> MatterStore:
    store = MatterStore(path)
    store.create(
        matter_id="MATTER-SNAP-1",
        title="Snapshot review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-SNAP-1",
                question="Does the exact source support the review?",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
        source_bindings=(
            MatterSourceBinding(
                binding_id="BIND-SNAP-1",
                document_id="DOC-SNAP-1",
                revision_id="REV-SNAP-1",
                page_number=1,
                evidence_id="EVID-SNAP-1",
                bbox=(10.0, 10.0, 500.0, 30.0),
                source_hash="a" * 64,
                evidence_snapshot_hash=str(provenance["evidence_snapshot_hash"]),
                evidence_db_sha256=str(provenance["evidence_db_sha256"]),
            ),
        ),
    )
    bind_finalized_evidence(
        store,
        matter_id="MATTER-SNAP-1",
        expected_revision=1,
        evidence_db=Path(provenance["database_path"]),
    )
    return store


def _finalized_matter_run(tmp_path: Path) -> Path:
    workspace = tmp_path / "matter-workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(workspace / "matter.sqlite", provenance)
    snapshot = create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)
    prepared = formalize_snapshot(workspace, snapshot)
    return _finalize_prepared_run(workspace / "runs" / prepared.run_id)


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


def test_legacy_run_reference_rejects_valid_matter_bound_run(tmp_path: Path) -> None:
    from evidence_review.migration.review_matter import legacy_reference_from_run

    run_directory = _finalized_matter_run(tmp_path)
    packet_path = run_directory / "final-review-packet.json"
    packet_bytes = packet_path.read_bytes()

    with pytest.raises(ValueError, match="LEGACY_FORMAL_RUN_INVALID"):
        legacy_reference_from_run(run_directory)

    assert packet_path.read_bytes() == packet_bytes
