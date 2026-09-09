from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.navigation.promotion import promote_navigation_hit
from evidence_review.navigation.service import navigate_evidence
from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.formalization import formalize_snapshot
from evidence_review.review_matter.snapshot import (
    FormalizedEvidence,
    create_formalization_snapshot,
)
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore


def _workspace(root: Path) -> Path:
    evidence = root / "evidence" / "evidence.sqlite"
    evidence.parent.mkdir(parents=True)
    with EvidenceStore(evidence, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-001", "title": "Reference"},),
                revisions=({
                    "id": "REV-001",
                    "document_id": "DOC-001",
                    "source_hash": "a" * 64,
                    "byte_size": 10,
                    "page_count": 1,
                },),
                pages=({
                    "id": "PAGE-001",
                    "revision_id": "REV-001",
                    "page_number": 1,
                    "width": 600.0,
                    "height": 800.0,
                },),
                elements=({
                    "id": "EVID-001",
                    "page_id": "PAGE-001",
                    "element_type": "paragraph",
                    "raw_json": {"text": "reference"},
                    "raw_text": "reference",
                    "normalized_text": "reference",
                    "raw_payload_hash": "d" * 64,
                    "bbox": [10.0, 10.0, 500.0, 30.0],
                    "parser_order": 0,
                },),
            ),
        )
        finalize_evidence_database(store)
    return root


def test_formalization_does_not_promote_unselected_draft_text(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    evidence = workspace / "evidence" / "evidence.sqlite"
    matter = MatterStore(workspace / "matter.sqlite")
    matter.create(
        matter_id="MATTER-001",
        title="Review question",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Is the reference sufficient?",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    bound = bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )
    navigation = navigate_evidence(evidence, "reference")
    promoted = promote_navigation_hit(
        matter,
        matter_id="MATTER-001",
        expected_revision=bound.revision,
        evidence_db=evidence,
        navigation_result=navigation,
        evidence_id="EVID-001",
    )
    snapshot = create_formalization_snapshot(
        matter,
        matter_id="MATTER-001",
        expected_revision=promoted.revision,
        evidence_db=evidence,
    )

    prepared = formalize_snapshot(workspace, snapshot)
    request = json.loads(
        (prepared.run_directory / "review-request.json").read_text(encoding="utf-8")
    )
    request_text = json.dumps(request, ensure_ascii=False)

    assert prepared.run_id.startswith("RUN-")
    assert "approximately 900 mm" not in request_text
    assert len(tuple((workspace / "runs").glob("RUN-*"))) == 1


def test_formalization_rejects_unpersisted_fabricated_snapshot(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    evidence = workspace / "evidence" / "evidence.sqlite"
    matter = MatterStore(workspace / "matter.sqlite")
    matter.create(
        matter_id="MATTER-001",
        title="Review question",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Is the reference sufficient?",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    bound = bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )
    navigation = navigate_evidence(evidence, "reference")
    promoted = promote_navigation_hit(
        matter,
        matter_id="MATTER-001",
        expected_revision=bound.revision,
        evidence_db=evidence,
        navigation_result=navigation,
        evidence_id="EVID-001",
    )
    snapshot = create_formalization_snapshot(
        matter,
        matter_id="MATTER-001",
        expected_revision=promoted.revision,
        evidence_db=evidence,
    )
    fabricated = replace(
        snapshot,
        snapshot_id="SNAP-" + "F" * 20,
        selected_evidence=(
            FormalizedEvidence(
                binding=snapshot.selected_evidence[0].binding,
                text="approximately 900 mm",
            ),
        ),
    )

    with pytest.raises(ValueError, match="FORMALIZATION_SNAPSHOT_NOT_FOUND"):
        formalize_snapshot(workspace, fabricated)
    assert not tuple((workspace / "runs").glob("RUN-*"))
