from __future__ import annotations

from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.run_context import compute_run_id_from_request


def _base_request() -> dict[str, object]:
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "첨부 도면을 보고 판단해줘",
        "inputs": {"snapshot_hash": "1" * 64},
        "evidence": [],
        "calculations": [],
        "rules": [],
        "approved_rule_result_ids": [],
        "confidence_input": {"factors": {}},
    }


def _drawing(source_hash: str) -> ImmutableAttachment:
    return ImmutableAttachment(
        attachment_id="ATT-DRAWING-001",
        original_name="drawing.pdf",
        stored_path="inputs/original/ATT-DRAWING-001.pdf",
        sha256=source_hash,
        byte_size=1024,
        mime="application/pdf",
        role="CASE_DRAWING",
    )


def test_case_visual_binding_changes_deterministic_run_identity() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    request = _base_request()
    without_visual = compute_run_id_from_request(request)
    with_visual = compute_run_id_from_request(
        bind_case_visual_context_to_review_request(request, [_drawing("a" * 64)])
    )
    changed_source = compute_run_id_from_request(
        bind_case_visual_context_to_review_request(request, [_drawing("b" * 64)])
    )

    assert with_visual != without_visual
    assert changed_source != with_visual


def test_case_drawing_binding_never_adds_reference_parser_metadata() -> None:
    from evidence_review.case_visual import bind_case_visual_context_to_review_request

    bound = bind_case_visual_context_to_review_request(
        _base_request(),
        [_drawing("a" * 64)],
    )

    visual = bound["inputs"]["case_visual_context"]
    attachment = visual["attachments"][0]
    assert attachment["role"] == "CASE_DRAWING"
    assert set(attachment) == {
        "attachment_id",
        "original_name",
        "stored_path",
        "sha256",
        "byte_size",
        "mime",
        "role",
    }
