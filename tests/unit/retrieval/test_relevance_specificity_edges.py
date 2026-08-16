from __future__ import annotations

from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.relevance import evaluate_issue_clause_relevance


def _clause(title: str, text: str) -> ClauseRetrievalHit:
    return ClauseRetrievalHit(
        clause_id="C-EDGE",
        document_id="DOC-1",
        revision_id="REV-1",
        title=title,
        text=text,
    )


def test_station_detail_without_literal_station_area_is_not_rejected_when_no_conflicting_subject() -> None:
    decision = evaluate_issue_clause_relevance(
        issue_id="I2",
        issue_question="역세권 승강장 경계 거리 기준은 무엇인가?",
        search_request_id="S2",
        query_text="역세권 승강장 경계 거리 기준",
        clause=_clause(
            "사업대상지의 범위",
            "각 승강장 경계로부터 직각으로 250미터 이내로 한다.",
        ),
    )

    assert decision.accepted is True
    assert "REJECT_SUBJECT_CONFLICT" not in decision.reason_codes


def test_explicit_arterial_road_subject_still_rejects_station_area_query() -> None:
    decision = evaluate_issue_clause_relevance(
        issue_id="I2",
        issue_question="역세권 용도지역 변경 기준은 무엇인가?",
        search_request_id="S2",
        query_text="역세권 용도지역 변경 기준",
        clause=_clause(
            "간선도로변의 용도지역 변경 기준",
            "간선도로변에 적용하는 용도지역 변경 기준이다.",
        ),
    )

    assert decision.accepted is False
    assert decision.reason_codes == ("REJECT_SUBJECT_CONFLICT",)
