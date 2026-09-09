from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.navigation.service import navigate_evidence


def _finalized_workspace(root: Path) -> Path:
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


def test_navigation_returns_traceable_hits_without_creating_formal_run(tmp_path: Path) -> None:
    workspace = _finalized_workspace(tmp_path / "workspace")
    runs = workspace / "runs"
    runs.mkdir()
    before = tuple(runs.glob("RUN-*"))

    result = navigate_evidence(workspace / "evidence" / "evidence.sqlite", "reference")

    assert result.hits
    assert all(hit.citation.source_hash for hit in result.hits)
    assert result.formal_status is None
    assert tuple(runs.glob("RUN-*")) == before
