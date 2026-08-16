from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.clause_resolution import ClauseRetrievalHit
from evidence_review.retrieval.fallback import FallbackStage, search_clause_with_fallback
from evidence_review.retrieval.index import build_fts_index
from evidence_review.retrieval.relevance import evaluate_issue_clause_relevance


def _clause(title: str, text: str) -> ClauseRetrievalHit:
    return ClauseRetrievalHit(
        clause_id="C-1",
        document_id="DOC-1",
        revision_id="REV-1",
        title=title,
        text=text,
    )


def test_rejects_arterial_road_section_for_station_area_zoning_issue() -> None:
    decision = evaluate_issue_clause_relevance(
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


def test_accepts_station_area_section_for_station_area_zoning_issue() -> None:
    decision = evaluate_issue_clause_relevance(
        issue_id="I-ZONE",
        issue_question="역세권 부지의 제2종일반주거지역을 준주거지역으로 변경하는 요건은?",
        search_request_id="S-ZONE",
        query_text="역세권 용도지역 변경 기준",
        clause=_clause(
            "역세권의 용도지역 변경 기준",
            "역세권에서 제2종일반주거지역을 준주거지역으로 변경하는 기준이다.",
        ),
    )

    assert decision.accepted is True
    assert "ACCEPT_SUBJECT_MATCH" in decision.reason_codes


def test_accepts_clause_that_explicitly_governs_both_station_and_arterial_subjects() -> None:
    decision = evaluate_issue_clause_relevance(
        issue_id="I-ZONE",
        issue_question="역세권 용도지역 변경 기준은?",
        search_request_id="S-ZONE",
        query_text="역세권 용도지역 변경 기준",
        clause=_clause(
            "역세권 및 간선도로변의 용도지역 변경 공통기준",
            "역세권과 간선도로변에 공통으로 적용하는 용도지역 변경 기준이다.",
        ),
    )

    assert decision.accepted is True
    assert "ACCEPT_SUBJECT_MATCH" in decision.reason_codes


def test_rejects_minimum_area_candidate_missing_minimum_area_anchor() -> None:
    decision = evaluate_issue_clause_relevance(
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


def test_fallback_continues_when_nonempty_stage_is_rejected_by_relevance_filter(
    tmp_path: Path,
) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _fallback_snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        result = search_clause_with_fallback(
            connection,
            "산업부지 확보비율",
            limit=5,
            hit_filter=lambda hit: hit.channel_scores[0].channel != "clause_exact",
        )

    assert result.success_stage == FallbackStage.PHRASE
    assert [trace.stage for trace in result.traces[:2]] == [
        FallbackStage.EXACT_CLAUSE,
        FallbackStage.PHRASE,
    ]
    assert result.traces[0].hit_count == 0
    assert result.traces[1].hit_count > 0
