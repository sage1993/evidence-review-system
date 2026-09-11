"""UI authority-boundary contracts for the mutable Matter Workbench."""

import pytest

from evidence_review.review_matter.contracts import MatterIssue, ReviewMatter
from evidence_review.workbench.html_renderer import render_workbench_html
from evidence_review.workbench.view_model import build_workbench_view_model


@pytest.fixture
def matter_with_draft() -> ReviewMatter:
    return ReviewMatter(
        matter_id="MATTER-001",
        title="Accessible entrance review",
        revision=2,
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Is the entrance width supported by selected evidence?",
                work_state="DRAFT",
                depends_on=(),
            ),
        ),
        source_bindings=(),
    )


def test_workbench_draft_cannot_render_as_formal_approval(matter_with_draft) -> None:
    """Mutable draft work never borrows formal-review or human-decision status."""
    model = build_workbench_view_model(matter_with_draft)
    html = render_workbench_html(model)

    assert 'data-surface="workbench"' in html
    assert "검토 초안" in html
    assert "READY_FOR_HUMAN_REVIEW" not in html
    assert "human-decision" not in html


def test_workbench_renderer_exposes_provenance_focus_and_disabled_exact_revision_action() -> None:
    html = render_workbench_html(
        {
            "surface": "workbench",
            "matter_id": "MATTER-001",
            "title": "Accessible entrance review",
            "revision": 7,
            "issues": [
                {
                    "issue_id": "ISSUE-001",
                    "question": "Confirm clear width.",
                    "work_state_label": "재확인 필요",
                    "recheck_required": True,
                },
            ],
            "evidence": [
                {
                    "binding_id": "BINDING-001",
                    "provenance": {
                        "document_id": "DOC-001",
                        "revision_id": "REV-001",
                        "page_number": 3,
                        "evidence_id": "EVID-001",
                        "bbox": [10.0, 20.0, 30.0, 40.0],
                        "source_hash": "a" * 64,
                        "evidence_snapshot_hash": "b" * 64,
                        "evidence_db_sha256": "c" * 64,
                    },
                },
            ],
            "navigation": {
                "query": "clear width",
                "promotion_label": "탐색 결과 — 정식 근거로 확정되지 않음",
                "recheck_required": True,
                "hits": [],
            },
            "draft_observations": [
                {
                    "issue_id": "ISSUE-001",
                    "text": "Width needs source confirmation.",
                    "verification_label": "미확인",
                    "draft_label": "검토 초안",
                },
            ],
            "formal_run_history": [
                {
                    "run_id": "RUN-001",
                    "snapshot_id": "SNAP-001",
                    "matter_revision": 4,
                    "stage_label": "Track A pending",
                },
            ],
            "formalize": {
                "expected_revision": 7,
                "enabled": False,
                "blockers": [{"issue_id": "ISSUE-001", "label": "재확인 필요"}],
                "confirmation_label": "현재 Matter revision 7을(를) 정식화",
            },
        }
    )

    assert 'data-evidence-id="EVID-001"' in html
    assert "DOC-001 · REV-001 · p. 3" in html
    assert 'data-formalize-expected-revision="7"' in html
    assert 'data-workbench-formalize disabled' in html
    assert 'aria-describedby="formalize-blockers"' in html
    assert 'tabindex="-1"' in html
    assert ":focus-visible" in html
    assert "@media (max-width: 700px)" in html
    assert "workbench:formalize" in html
    assert "human-decision" not in html


def test_workbench_renderer_discloses_exact_navigation_hit_provenance() -> None:
    html = render_workbench_html(
        {
            "surface": "workbench",
            "matter_id": "MATTER-001",
            "title": "Navigation evidence review",
            "revision": 3,
            "issues": [],
            "evidence": [],
            "navigation": {
                "query": "width",
                "evidence_snapshot_hash": "a" * 64,
                "evidence_db_sha256": "b" * 64,
                "promotion_label": "탐색 결과",
                "recheck_required": True,
                "hits": [
                    {
                        "citation_id": "CIT-EVID-002",
                        "evidence_id": "EVID-002",
                        "document_id": "DOC-002",
                        "revision_id": "REV-002",
                        "page_number": 5,
                        "bbox": [1.0, 2.0, 3.0, 4.0],
                        "source_hash": "c" * 64,
                        "title": "<unsafe navigation title>",
                        "text": "900 mm",
                    },
                ],
            },
            "draft_observations": [],
            "formal_run_history": [],
            "formalize": {
                "expected_revision": 3,
                "enabled": False,
                "blockers": [{"issue_id": "", "label": "선택 근거 없음"}],
                "confirmation_label": "현재 Matter revision 3을(를) 정식화",
            },
        }
    )

    assert 'data-navigation-evidence-id="EVID-002"' in html
    assert 'id="navigation-provenance-CIT-EVID-002" tabindex="-1"' in html
    assert "&lt;unsafe navigation title&gt;" in html
    assert "Bounding box: 1.0, 2.0, 3.0, 4.0" in html
    assert f"Source hash: {'c' * 64}" in html
    assert f"Evidence snapshot: {'a' * 64}" in html
    assert f"Evidence DB: {'b' * 64}" in html


def test_workbench_renderer_labels_issue_and_draft_identity_for_multi_issue_work() -> None:
    html = render_workbench_html(
        {
            "surface": "workbench",
            "matter_id": "MATTER-001",
            "title": "Multi-issue review",
            "revision": 3,
            "issues": [
                {
                    "issue_id": "ISSUE-001",
                    "question": "Confirm the width.",
                    "work_state_label": "검토 초안",
                    "recheck_required": False,
                },
                {
                    "issue_id": "ISSUE-002",
                    "question": "Confirm the width.",
                    "work_state_label": "검토 중",
                    "recheck_required": False,
                },
            ],
            "evidence": [],
            "navigation": None,
            "draft_observations": [
                {
                    "issue_id": "ISSUE-001",
                    "text": "First draft.",
                    "verification_label": "미확인",
                    "draft_label": "검토 초안",
                },
                {
                    "issue_id": "ISSUE-002",
                    "text": "Second draft.",
                    "verification_label": "확인 필요",
                    "draft_label": "검토 초안",
                },
            ],
            "formal_run_history": [],
            "formalize": {
                "expected_revision": 3,
                "enabled": False,
                "blockers": [{"issue_id": "ISSUE-001", "label": "검토 초안"}],
                "confirmation_label": "현재 Matter revision 3을(를) 정식화",
            },
        }
    )

    assert '<p class="issue-identifier">MatterIssue ISSUE-001</p>' in html
    assert '<p class="issue-identifier">MatterIssue ISSUE-002</p>' in html
    assert '<p class="draft-issue-identifier">MatterIssue ISSUE-001</p>' in html
    assert '<p class="draft-issue-identifier">MatterIssue ISSUE-002</p>' in html
