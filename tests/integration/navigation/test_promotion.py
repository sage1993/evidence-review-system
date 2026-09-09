from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.navigation.promotion import promote_navigation_hit
from evidence_review.navigation.service import navigate_evidence
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore


def _finalized_database(path: Path, *, source_hash: str, text: str) -> None:
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-001", "title": "Reference"},),
                revisions=({
                    "id": "REV-001",
                    "document_id": "DOC-001",
                    "source_hash": source_hash,
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
                    "raw_json": {"text": text},
                    "raw_text": text,
                    "normalized_text": text,
                    "raw_payload_hash": "d" * 64,
                    "bbox": [10.0, 10.0, 500.0, 30.0],
                    "parser_order": 0,
                },),
            ),
        )
        finalize_evidence_database(store)


def test_stale_navigation_result_is_rejected_before_matter_mutation(tmp_path: Path) -> None:
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"
    _finalized_database(first, source_hash="a" * 64, text="reference")
    _finalized_database(second, source_hash="b" * 64, text="reference")
    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(matter_id="MATTER-001", title="Review")
    bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=first,
    )
    navigation = navigate_evidence(first, "reference")

    with pytest.raises(ValueError, match="NAVIGATION_RESULT_STALE"):
        promote_navigation_hit(
            matter,
            matter_id="MATTER-001",
            expected_revision=2,
            evidence_db=second,
            navigation_result=navigation,
            evidence_id="EVID-001",
        )

    assert matter.load("MATTER-001").revision == 2


def test_navigation_promotion_is_projected_and_rebuildable(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.sqlite"
    _finalized_database(evidence, source_hash="a" * 64, text="reference")
    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(matter_id="MATTER-001", title="Review")
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

    assert promoted.revision == 3
    assert promoted.source_bindings[0].evidence_id == "EVID-001"
    assert matter.rebuild_projection("MATTER-001").source_bindings == promoted.source_bindings
