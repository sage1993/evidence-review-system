from __future__ import annotations

import pytest

from evidence_review.contracts.attachments import ImmutableAttachment


def _attachment(
    *,
    role: str,
    sha256: str = "a" * 64,
    mime: str = "application/pdf",
    name: str = "case-drawing.pdf",
) -> ImmutableAttachment:
    return ImmutableAttachment(
        attachment_id="ATT-CASE-001",
        original_name=name,
        stored_path="inputs/original/ATT-CASE-001.pdf",
        sha256=sha256,
        byte_size=128,
        mime=mime,
        role=role,  # type: ignore[arg-type]
    )


def test_case_drawing_pdf_binds_as_visual_context_not_reference() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    request = {"inputs": {"snapshot_hash": "f" * 64}}

    bound = bind_case_visual_context_to_review_request(
        request,
        [_attachment(role="CASE_DRAWING")],
    )

    visual = bound["inputs"]["case_visual_context"]
    assert visual == {
        "attachments": [
            {
                "attachment_id": "ATT-CASE-001",
                "original_name": "case-drawing.pdf",
                "stored_path": "inputs/original/ATT-CASE-001.pdf",
                "sha256": "a" * 64,
                "byte_size": 128,
                "mime": "application/pdf",
                "role": "CASE_DRAWING",
            }
        ],
        "drawing_candidates": [],
        "visual_status": "VISUAL_ANALYSIS_REQUIRED",
        "reason_codes": ["VISUAL_ANALYSIS_REQUIRED"],
    }
    assert "parser" not in visual["attachments"][0]
    assert bound["inputs"]["snapshot_hash"] == "f" * 64


def test_supporting_image_binds_as_case_visual_context() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    image = ImmutableAttachment(
        attachment_id="ATT-IMAGE-001",
        original_name="floor-plan.png",
        stored_path="inputs/original/ATT-IMAGE-001.png",
        sha256="b" * 64,
        byte_size=256,
        mime="image/png",
        role="SUPPORTING_IMAGE",
    )

    bound = bind_case_visual_context_to_review_request({"inputs": {}}, [image])

    attachment = bound["inputs"]["case_visual_context"]["attachments"][0]
    assert attachment["role"] == "SUPPORTING_IMAGE"
    assert attachment["mime"] == "image/png"
    assert attachment["sha256"] == "b" * 64


def test_reference_document_is_rejected_from_case_visual_context() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    with pytest.raises(ValueError, match="REFERENCE_DOCUMENT"):
        bind_case_visual_context_to_review_request(
            {"inputs": {}},
            [_attachment(role="REFERENCE_DOCUMENT")],
        )


def test_no_visual_attachments_preserves_request_exactly() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    request = {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "기존 복합질문",
        "inputs": {"snapshot_hash": "c" * 64},
        "evidence": [],
        "calculations": [],
        "rules": [],
        "approved_rule_result_ids": [],
        "confidence_input": {"factors": {}},
    }

    assert bind_case_visual_context_to_review_request(request, []) == request


def test_question_text_does_not_create_visual_candidates() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    request = {
        "question": "49.91㎡ A형, 2Bay, 2R+1B인지 첨부 이미지를 보고 확인해줘",
        "inputs": {},
    }

    bound = bind_case_visual_context_to_review_request(
        request,
        [_attachment(role="CASE_DRAWING")],
    )

    visual = bound["inputs"]["case_visual_context"]
    assert visual["drawing_candidates"] == []
    assert visual["visual_status"] == "VISUAL_ANALYSIS_REQUIRED"
