from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.fallback import FallbackStage, search_clause_with_fallback
from evidence_review.retrieval.index import build_fts_index


def _snapshot(text: str) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "기준"},),
        revisions=(
            {
                "id": "REV-1",
                "document_id": "DOC-1",
                "source_hash": "a" * 64,
                "byte_size": 100,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "P-1",
                "revision_id": "REV-1",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        clauses=(
            {
                "id": "C-1",
                "revision_id": "REV-1",
                "title": "규정",
                "raw_text": text,
                "normalized_text": text,
                "review_status": "AUTOMATIC",
            },
        ),
    )


def test_user_fact_numeric_literal_does_not_block_rule_threshold_retrieval(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            _snapshot(
                "역세권은 승강장 경계로부터 250m 이내를 원칙으로 하며 "
                "통합심의를 거치는 경우 350m 이내까지 사업대상지로 지정할 수 있다."
            ),
        )
        connection = store.require_connection()
        build_fts_index(connection)

        result = search_clause_with_fallback(
            connection,
            "역세권 승강장 경계 300m 사업대상지 면적 기준",
            fact_texts=("대상 부지는 승강장 경계에서 300m 떨어져 있다.",),
            limit=5,
        )

    assert {hit.clause_id for hit in result.hits} == {"C-1"}
    assert result.success_stage in {
        FallbackStage.FACT_DECONTAMINATED,
        FallbackStage.LEGAL_COMPOUND_DECOMPOSITION,
        FallbackStage.CORE_TOKEN_AND,
    }
    assert result.traces[0].derived_query == "역세권 승강장 경계 300m 사업대상지 면적 기준"
    assert any("300m" not in trace.derived_query for trace in result.traces[1:])


def test_bounded_core_token_fallback_handles_entity_wording_mismatch(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            _snapshot(
                "임대형기숙사를 제외한 안심주택인 경우 주차장 설치기준에 따라 "
                "주차장을 설치하여야 한다."
            ),
        )
        connection = store.require_connection()
        build_fts_index(connection)

        result = search_clause_with_fallback(
            connection,
            "공공지원민간임대주택 주차장 설치기준",
            limit=5,
        )

    assert {hit.clause_id for hit in result.hits} == {"C-1"}
    assert result.success_stage == FallbackStage.CORE_TOKEN_AND
    assert result.successful_query == "주차장 설치기준"


def test_intent_pruning_removes_additional_review_noise(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            _snapshot(
                "지구단위계획으로 주차장 설치기준을 완화하여 적용할 수 있다."
            ),
        )
        connection = store.require_connection()
        build_fts_index(connection)

        result = search_clause_with_fallback(
            connection,
            "지구단위계획 주차장 설치기준 추가 완화 요건 절차",
            limit=5,
        )

    assert {hit.clause_id for hit in result.hits} == {"C-1"}
    assert result.success_stage == FallbackStage.LEGAL_COMPOUND_DECOMPOSITION
    assert result.successful_query == "지구단위계획 주차장 설치기준"
