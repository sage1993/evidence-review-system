from __future__ import annotations

from pathlib import Path

import pytest

from ansim_review.review_packet.builder import build_review_view_model
from ansim_review.review_packet.decision_record import validate_human_decision_request
from ansim_review.review_packet.presentation import conclusion_text

from .test_builder import _db, _packet


def test_citation_projection_includes_document_title_without_changing_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.sqlite"
    _db(database)

    model = build_review_view_model(_packet(), database)
    citation = model["claims"][0]["citations"][0]

    assert citation["document_name"] == "Document"
    assert citation["document_id"] == "DOC1"
    assert citation["revision_id"] == "REV1"
    assert citation["source_hash"] == "a" * 64


def test_answer_summary_precedes_claim_fallback_and_never_uses_status_as_conclusion() -> None:
    model = {
        "status": "READY_FOR_HUMAN_REVIEW",
        "answer_summary": "정식 결론입니다.",
        "claims": [{"text": "주장 fallback"}],
    }

    assert conclusion_text(model) == "정식 결론입니다."
    fallback = (
        "\uC9C8\uBB38\uC5D0 \uB300\uD55C \uACB0\uB860\uC774 \uC81C\uACF5\uB418\uC9C0 "
        "\uC54A\uC558\uC2B5\uB2C8\uB2E4."
    )
    assert conclusion_text({**model, "answer_summary": None}) == fallback
    assert conclusion_text({"status": "ABSTAIN", "claims": []}) != "추가 자료 필요"


def test_decision_notes_policy_allows_satisfied_blank_but_requires_other_notes() -> None:
    base = {
        "reviewer_id": "reviewer-01",
        "packet_hash": "a" * 64,
        "notes": "",
    }

    assert validate_human_decision_request({**base, "decision": "SATISFIED"})["notes"] == ""
    for decision in ("NOT_SATISFIED", "CONDITIONAL", "ADDITIONAL_REVIEW_REQUIRED"):
        with pytest.raises(ValueError, match="notes is required"):
            validate_human_decision_request({**base, "decision": decision})
