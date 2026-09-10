from __future__ import annotations

import pytest

from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.question_plan import (
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.drawing_review.visual_pages import VisualPageAsset
from evidence_review.drawing_review.visual_submission import validate_visual_analysis_output


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="도면에서 주출입구 위치를 확인해줘",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="ISSUE-1",
                question="주출입구 위치는 어디인가?",
                depends_on=(),
                required_evidence_roles=("supporting_fact",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="SEARCH-1",
                issue_ids=("ISSUE-1",),
                text="주출입구 위치",
                kind="phrase",
                source="planner",
                role="supporting_fact",
            ),
        ),
    )


def _attachment() -> ImmutableAttachment:
    return ImmutableAttachment(
        attachment_id="ATT-DRAWING-1",
        original_name="drawing.png",
        stored_path="inputs/original/ATT-DRAWING-1.png",
        sha256="a" * 64,
        byte_size=100,
        mime="image/png",
        role="CASE_DRAWING",
    )


def _page() -> VisualPageAsset:
    return VisualPageAsset(
        case_id="CASE-1",
        attachment_id="ATT-DRAWING-1",
        source_sha256="a" * 64,
        page=1,
        width=100.0,
        height=80.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=__import__("pathlib").Path("page.png"),
        image_sha256="b" * 64,
    )


def _output(*, source_hash: str = "a" * 64, right: float = 40.0) -> dict[str, object]:
    return {
        "format": "evidence-review/visual-analysis-output",
        "version": 1,
        "visual_analysis_id": "VIS-TEST",
        "observations": [
            {
                "attachment_id": "ATT-DRAWING-1",
                "source_sha256": source_hash,
                "page": 1,
                "issue_ids": ["ISSUE-1"],
                "candidate_type": "MAIN_ENTRY",
                "geometry": {
                    "type": "BBOX",
                    "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                    "coordinates": [10.0, 10.0, right, 40.0],
                },
                "raw_value": None,
                "normalized_candidate": None,
            }
        ],
    }


def test_visual_submission_creates_source_bound_unconfirmed_candidate() -> None:
    result = validate_visual_analysis_output(
        _output(),
        expected_visual_analysis_id="VIS-TEST",
        question_plan=_plan(),
        attachments=(_attachment(),),
        pages=(_page(),),
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.source_sha256 == "a" * 64
    assert candidate.status == "UNCONFIRMED"
    assert candidate.origin == "EXTRACTOR"
    assert result.candidate_issue_ids[candidate.candidate_id] == ("ISSUE-1",)


def test_visual_submission_rejects_source_hash_mismatch() -> None:
    with pytest.raises(ValueError, match="source_sha256 mismatch"):
        validate_visual_analysis_output(
            _output(source_hash="c" * 64),
            expected_visual_analysis_id="VIS-TEST",
            question_plan=_plan(),
            attachments=(_attachment(),),
            pages=(_page(),),
        )


def test_visual_submission_rejects_geometry_outside_rendered_page() -> None:
    with pytest.raises(ValueError, match="outside page bounds"):
        validate_visual_analysis_output(
            _output(right=120.0),
            expected_visual_analysis_id="VIS-TEST",
            question_plan=_plan(),
            attachments=(_attachment(),),
            pages=(_page(),),
        )


def test_visual_submission_allows_completed_analysis_with_no_findings() -> None:
    result = validate_visual_analysis_output(
        {
            "format": "evidence-review/visual-analysis-output",
            "version": 1,
            "visual_analysis_id": "VIS-TEST",
            "observations": [],
        },
        expected_visual_analysis_id="VIS-TEST",
        question_plan=_plan(),
        attachments=(_attachment(),),
        pages=(_page(),),
    )

    assert result.candidates == ()
    assert result.candidate_issue_ids == {}
