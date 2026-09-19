from __future__ import annotations

import importlib
from typing import Any

import pytest

from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit


def _evaluate_api() -> Any:
    try:
        module = importlib.import_module("evidence_review.retrieval.relevance")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.retrieval.relevance is not implemented", pytrace=False)
    if not hasattr(module, "evaluate_issue_clause_relevance"):
        pytest.fail("evaluate_issue_clause_relevance is not implemented", pytrace=False)
    return module.evaluate_issue_clause_relevance


def _clause(title: str, text: str) -> ClauseRetrievalHit:
    return ClauseRetrievalHit(
        clause_id="C-EDGE",
        document_id="DOC-1",
        revision_id="REV-1",
        title=title,
        text=text,
    )


def test_station_detail_without_literal_station_area_is_not_rejected() -> None:
    evaluate = _evaluate_api()
    decision = evaluate(
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


def test_explicit_arterial_subject_rejects_station_area_query() -> None:
    evaluate = _evaluate_api()
    decision = evaluate(
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


def test_same_document_clause_without_public_contribution_intent_is_rejected() -> None:
    evaluate = _evaluate_api()
    decision = evaluate(
        issue_id="I-PUBLIC-CONTRIBUTION",
        issue_question="공공기여 산정 방식은 무엇인가?",
        search_request_id="S-PUBLIC-CONTRIBUTION",
        query_text="공공기여 산정 방식",
        clause=_clause(
            "공공기여 일반원칙",
            "사업시행자는 공공기여를 제공할 수 있다.",
        ),
    )

    assert decision.accepted is False
    assert "RETRIEVAL_RELEVANCE_INSUFFICIENT" in decision.reason_codes
