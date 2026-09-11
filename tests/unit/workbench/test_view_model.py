"""Deterministic Workbench presentation-model contracts."""

from decimal import Decimal

from evidence_review.contracts.common import BBox, Citation
from evidence_review.navigation.models import NavigationHit, NavigationResult
from evidence_review.review_matter.contracts import (
    MatterIssue,
    MatterSourceBinding,
    ReviewMatter,
)
from evidence_review.workbench.view_model import (
    DraftObservation,
    FormalRunHistory,
    build_workbench_view_model,
)


def test_workbench_model_separates_draft_navigation_provenance_and_formalization() -> None:
    matter = ReviewMatter(
        matter_id="MATTER-001",
        title="Accessible entrance review",
        revision=7,
        issues=(
            MatterIssue("ISSUE-001", "Confirm clear width.", "DRAFT", ()),
            MatterIssue("ISSUE-002", "Recheck changed source.", "STALE", ()),
        ),
        source_bindings=(
            MatterSourceBinding(
                binding_id="BINDING-001",
                document_id="DOC-001",
                revision_id="REV-001",
                page_number=3,
                evidence_id="EVID-001",
                bbox=(10.0, 20.0, 30.0, 40.0),
                source_hash="a" * 64,
                evidence_snapshot_hash="b" * 64,
                evidence_db_sha256="c" * 64,
            ),
        ),
    )
    navigation = NavigationResult(
        query="clear width",
        evidence_snapshot_hash="d" * 64,
        evidence_db_sha256="e" * 64,
        hits=(
            NavigationHit(
                evidence_id="EVID-002",
                document_id="DOC-002",
                revision_id="REV-002",
                page_number=5,
                bbox=BBox(1, 2, 3, 4),
                source_hash="f" * 64,
                title="Width table",
                text="900 mm",
                score=Decimal("1.0"),
                citation=Citation(
                    citation_id="CIT-EVID-002",
                    document_id="DOC-002",
                    revision_id="REV-002",
                    page_number=5,
                    evidence_id="EVID-002",
                    bbox=BBox(1, 2, 3, 4),
                    source_hash="f" * 64,
                ),
            ),
        ),
    )

    model = build_workbench_view_model(
        matter,
        navigation_result=navigation,
        draft_observations=(
            DraftObservation("ISSUE-001", "Width needs source confirmation.", "UNVERIFIED"),
        ),
        formal_run_history=(
            FormalRunHistory("RUN-001", "SNAP-001", 4, "Track A pending"),
        ),
    )

    assert model["issues"][0]["work_state_label"] == "검토 초안"
    assert model["issues"][1]["recheck_required"] is True
    assert model["draft_observations"][0]["verification_label"] == "미확인"
    assert model["evidence"][0]["provenance"] == {
        "document_id": "DOC-001",
        "revision_id": "REV-001",
        "page_number": 3,
        "evidence_id": "EVID-001",
        "bbox": [10.0, 20.0, 30.0, 40.0],
        "source_hash": "a" * 64,
        "evidence_snapshot_hash": "b" * 64,
        "evidence_db_sha256": "c" * 64,
    }
    assert model["navigation"]["recheck_required"] is True
    assert model["navigation"]["hits"][0]["citation_id"] == "CIT-EVID-002"
    assert model["formal_run_history"] == [
        {
            "run_id": "RUN-001",
            "snapshot_id": "SNAP-001",
            "matter_revision": 4,
            "stage_label": "Track A pending",
        },
    ]
    assert model["formalize"] == {
        "expected_revision": 7,
        "enabled": False,
        "blockers": [
            {"issue_id": "ISSUE-001", "label": "검토 초안"},
            {"issue_id": "ISSUE-002", "label": "재확인 필요"},
        ],
        "confirmation_label": "현재 Matter revision 7을(를) 정식화",
    }
