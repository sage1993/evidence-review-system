from __future__ import annotations

from decimal import Decimal

from evidence_review.contracts.common import BBox, Citation
from evidence_review.navigation.models import NavigationHit, NavigationResult


def test_navigation_result_is_explicitly_non_authoritative() -> None:
    citation = Citation(
        citation_id="CIT-EVID-001",
        document_id="DOC-001",
        revision_id="REV-001",
        page_number=1,
        evidence_id="EVID-001",
        bbox=BBox(10.0, 20.0, 30.0, 40.0),
        source_hash="a" * 64,
    )
    hit = NavigationHit(
        evidence_id="EVID-001",
        evidence_type="paragraph",
        document_id="DOC-001",
        revision_id="REV-001",
        page_number=1,
        bbox=citation.bbox,
        source_hash=citation.source_hash,
        title="Reference",
        text="Reference text",
        score=Decimal("1.0"),
        citation=citation,
    )

    result = NavigationResult(
        query="Reference",
        evidence_snapshot_hash="b" * 64,
        hits=(hit,),
    )

    assert result.formal_status is None
    assert result.hits[0].citation.source_hash == "a" * 64
