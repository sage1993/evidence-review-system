from __future__ import annotations

import importlib
from decimal import Decimal
from typing import Any

import pytest

from evidence_review.contracts.common import BBox
from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.fallback import FallbackStage
from evidence_review.retrieval.issue_bundle import (
    IssueCandidateMatch,
    IssueClauseCandidate,
    IssueRetrievalBundle,
)
from evidence_review.retrieval.models import ChannelScore, RetrievalHit


def _evaluate_facet_coverage() -> Any:
    try:
        module = importlib.import_module("evidence_review.retrieval.facets")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.retrieval.facets is not implemented", pytrace=False)
    if not hasattr(module, "evaluate_facet_coverage"):
        pytest.fail("evaluate_facet_coverage is not implemented", pytrace=False)
    return module.evaluate_facet_coverage


def _plan():
    question = "준공업지역의 산업부지 확보비율과 완화 절차는 무엇인가?"
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I6",
                    "question": question,
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S6",
                    "issue_ids": ["I6"],
                    "text": "준공업지역 산업부지 확보비율 완화 절차",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                }
            ],
        },
        question,
    )


def _bundle(text: str) -> IssueRetrievalBundle:
    clause = ClauseRetrievalHit(
        clause_id="C-I6",
        document_id="DOC-1",
        revision_id="REV-1",
        title="산업부지 확보비율",
        text=text,
        channel_scores=(ChannelScore("clause_phrase", Decimal("1"), text),),
    )
    match = IssueCandidateMatch(
        search_request_id="S6",
        issue_id="I6",
        role="rule",
        query_text="준공업지역 산업부지 확보비율 완화 절차",
        retrieval_query="준공업지역 산업부지 확보비율",
        fallback_stage=FallbackStage.PHRASE,
    )
    hit = RetrievalHit(
        evidence_id="E-I6",
        evidence_type="paragraph",
        document_id="DOC-1",
        revision_id="REV-1",
        page_number=1,
        bbox=BBox(0, 0, 100, 20),
        source_hash="a" * 64,
        title="산업부지 확보비율",
        text=text,
        channel_scores=(ChannelScore("clause_citation", Decimal("1"), "C-I6"),),
        final_score=Decimal("1"),
    )
    return IssueRetrievalBundle(
        candidates=(IssueClauseCandidate(clause=clause, matches=(match,), evidence=(hit,)),),
        selected_evidence=(hit,),
        budget_drops=(),
    )


def test_vague_review_procedure_does_not_cover_industrial_site_ratio_value() -> None:
    evaluate = _evaluate_facet_coverage()

    issue = evaluate(
        _plan(),
        _bundle(
            "공장비율 10% 이상인 경우 산업부지 확보비율은 관련 위원회 심의를 통해 "
            "완화할 수 있다."
        ),
    ).by_issue_id("I6")

    assert "industrial-site-relaxation-procedure" in issue.covered_facet_ids
    assert "industrial-site-ratio" in issue.missing_facet_ids


def test_direct_half_ratio_covers_industrial_site_ratio_value() -> None:
    evaluate = _evaluate_facet_coverage()

    issue = evaluate(
        _plan(),
        _bundle(
            "공장비율 10% 이상인 경우 산업부지 확보비율은 관련 위원회 심의를 통해 "
            "2분의 1까지 완화할 수 있다."
        ),
    ).by_issue_id("I6")

    assert issue.missing_facet_ids == ()
    assert set(issue.covered_facet_ids) == {
        "industrial-site-ratio",
        "industrial-site-relaxation-procedure",
    }
