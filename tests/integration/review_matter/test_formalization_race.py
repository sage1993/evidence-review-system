from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import MatterIssue, MatterSourceBinding
from evidence_review.review_matter.snapshot import create_formalization_snapshot
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore


def _finalized_database(path: Path) -> None:
    with EvidenceStore(path, create=True) as store:
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


def test_formalization_rejects_stale_expected_matter_revision(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.sqlite"
    _finalized_database(evidence)
    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )

    with pytest.raises(ValueError, match="MATTER_CHANGED_DURING_FORMALIZATION"):
        create_formalization_snapshot(
            matter,
            matter_id="MATTER-001",
            expected_revision=1,
            evidence_db=evidence,
        )


def test_formalization_requires_explicit_evidence_selection(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.sqlite"
    _finalized_database(evidence)
    provenance = finalized_evidence_provenance(evidence)
    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
        source_bindings=(
            MatterSourceBinding(
                binding_id="BIND-BASELINE",
                document_id="DOC-001",
                revision_id="REV-001",
                page_number=1,
                evidence_id="EVID-001",
                bbox=(10.0, 10.0, 500.0, 30.0),
                source_hash="a" * 64,
                evidence_snapshot_hash=str(provenance["evidence_snapshot_hash"]),
                evidence_db_sha256=str(provenance["evidence_db_sha256"]),
            ),
        ),
    )
    bound = bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )

    with pytest.raises(ValueError, match="FORMALIZATION_SELECTED_EVIDENCE_EMPTY"):
        create_formalization_snapshot(
            matter,
            matter_id="MATTER-001",
            expected_revision=bound.revision,
            evidence_db=evidence,
        )
