from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.fallback import (
    FallbackStage,
    _heading_scoped_search,
    search_clause_with_fallback,
)
from evidence_review.retrieval.index import build_fts_index


def _relevance_api() -> Any:
    try:
        module = importlib.import_module("evidence_review.retrieval.relevance")
    except ModuleNotFoundError:
        pytest.fail("evidence_review.retrieval.relevance is not implemented", pytrace=False)
    if not hasattr(module, "evaluate_issue_clause_relevance"):
        pytest.fail("evaluate_issue_clause_relevance is not implemented", pytrace=False)
    return module.evaluate_issue_clause_relevance


def _clause(title: str, text: str) -> ClauseRetrievalHit:
    return ClauseRetrievalHit(
        clause_id="C-1",
        document_id="DOC-1",
        revision_id="REV-1",
        title=title,
        text=text,
    )


def test_rejects_arterial_road_section_for_station_area_zoning_issue() -> None:
    evaluate = _relevance_api()
    decision = evaluate(
        issue_id="I-ZONE",
        issue_question="역세권 부지의 제2종일반주거지역을 준주거지역으로 변경하는 요건은?",
        search_request_id="S-ZONE",
        query_text="역세권 용도지역 변경 기준",
        clause=_clause(
            "2-3-2. 간선도로변의 용도지역 변경 기준",
            "간선도로변에서 용도지역을 변경하는 경우 적용하는 기준이다.",
        ),
    )

    assert decision.accepted is False
    assert "REJECT_SUBJECT_CONFLICT" in decision.reason_codes


def test_rejects_minimum_area_candidate_missing_required_anchor() -> None:
    evaluate = _relevance_api()
    decision = evaluate(
        issue_id="I1",
        issue_question="안심주택의 일반적인 사업대상지 최소 면적은 얼마인가?",
        search_request_id="S1",
        query_text="안심주택 일반 사업대상지 최소 면적",
        clause=_clause(
            "2-3-1. 용도지역 변경 기준",
            "안심주택 사업대상지의 용도지역 변경과 도로 조건을 정한다.",
        ),
    )

    assert decision.accepted is False
    assert "REJECT_REQUIRED_ANCHOR_MISSING" in decision.reason_codes


def _fallback_snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "Fallback relevance"},),
        revisions=(
            {
                "id": "REV-1",
                "document_id": "DOC-1",
                "source_hash": "a" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "P-1",
                "revision_id": "REV-1",
                "page_number": 1,
                "width": 600.0,
                "height": 800.0,
            },
        ),
        clauses=(
            {
                "id": "C-INDUSTRIAL",
                "revision_id": "REV-1",
                "title": "산업부지 확보비율",
                "raw_text": "산업부지 확보비율은 심의를 거쳐 완화할 수 있다.",
                "normalized_text": "산업부지 확보비율은 심의를 거쳐 완화할 수 있다.",
                "review_status": "AUTOMATIC",
            },
        ),
    )


def test_fallback_continues_when_nonempty_stage_is_rejected_by_filter(
    tmp_path: Path,
) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _fallback_snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        try:
            result = search_clause_with_fallback(
                connection,
                "산업부지 확보비율",
                limit=5,
                hit_filter=lambda hit: hit.channel_scores[0].channel != "clause_exact",
            )
        except TypeError as error:
            pytest.fail(f"fallback relevance filter is not implemented: {error}", pytrace=False)

    assert result.success_stage == FallbackStage.PHRASE
    assert [trace.stage for trace in result.traces[:2]] == [
        FallbackStage.EXACT_CLAUSE,
        FallbackStage.PHRASE,
    ]
    assert result.traces[0].hit_count == 0
    assert result.traces[1].hit_count > 0


def test_heading_scope_scores_all_tokens_before_applying_limit() -> None:
    snapshot = EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "Heading ranking"},),
        revisions=(
            {
                "id": "REV-1",
                "document_id": "DOC-1",
                "source_hash": "b" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "P-1",
                "revision_id": "REV-1",
                "page_number": 1,
                "width": 600.0,
                "height": 800.0,
            },
        ),
        clauses=(
            {
                "id": "C-GENERAL",
                "revision_id": "REV-1",
                "title": "공공기여 일반원칙",
                "raw_text": "공공기여 원칙",
                "normalized_text": "공공기여 원칙",
                "review_status": "AUTOMATIC",
            },
            {
                "id": "C-SPECIFIC",
                "revision_id": "REV-1",
                "title": "공공기여 산정 방식",
                "raw_text": "공공기여 산정 방식을 정한다.",
                "normalized_text": "공공기여 산정 방식을 정한다.",
                "review_status": "AUTOMATIC",
            },
        ),
    )

    with EvidenceStore(Path(":memory:"), create=True) as store:
        ingest_snapshot(store, snapshot)
        connection = store.require_connection()
        build_fts_index(connection)
        hits = _heading_scoped_search(
            connection,
            "공공기여 산정 방식",
            limit=1,
        )

    assert hits[0].clause_id == "C-SPECIFIC"
