from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.fallback import (
    FallbackStage,
    approved_alias_queries,
    legal_compound_queries,
    search_clause_with_fallback,
)
from evidence_review.retrieval.index import build_fts_index


def _snapshot() -> EvidenceSnapshot:
    clauses = (
        (
            "C-AREA",
            "사업대상지 일반기준",
            "안심주택 사업대상지는 원칙적으로 대지면적 1,000㎡ 이상이어야 한다.",
        ),
        (
            "C-STATION",
            "역세권 범위",
            "역세권은 승강장 경계로부터 250m 이내를 원칙으로 하며 통합심의를 거치는 경우 350m 이내까지 검토할 수 있다.",
        ),
        (
            "C-PARKING-PRIVATE",
            "공공지원민간임대주택 주차기준",
            "임대형기숙사를 제외한 안심주택의 주차장 설치기준은 해당 주택 유형에 적용되는 기준을 따른다.",
        ),
        (
            "C-PARKING-DORM",
            "임대형기숙사 주차기준",
            "임대형기숙사와 다른 주택용도를 복합하는 경우 주차장 설치기준은 각 주택용도별 기준을 각각 적용한다.",
        ),
        (
            "C-FAR",
            "준공업지역 용적률",
            "준공업지역에서 공동주택을 포함하는 안심주택의 기본용적률은 400% 이하로 정할 수 있다.",
        ),
        (
            "C-INDUSTRIAL",
            "산업부지 확보비율",
            "준공업지역에서는 산업부지 확보비율을 적용하며 통합심의 결과에 따라 확보비율을 완화할 수 있다.",
        ),
        (
            "C-DUP",
            "지구단위계획 주차완화",
            "지구단위계획으로 정하는 경우 안심주택의 주차장 설치기준을 추가로 완화할 수 있다.",
        ),
    )
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "안심주택 검토기준"},),
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
        clauses=tuple(
            {
                "id": clause_id,
                "revision_id": "REV-1",
                "title": title,
                "raw_text": text,
                "normalized_text": text,
                "review_status": "AUTOMATIC",
            }
            for clause_id, title, text in clauses
        ),
    )


def test_approved_aliases_are_bounded_and_domain_generic() -> None:
    assert "준공업지역 기본용적률 완화" in approved_alias_queries(
        "준공업지역 용적률 완화"
    )
    assert "공공지원민간임대주택 주차기준" in approved_alias_queries(
        "공공지원민간임대주택 주차장 설치기준"
    )
    assert "안심주택 사업대상지 대지면적" in approved_alias_queries(
        "안심주택 사업대상지 최소 면적"
    )
    assert len(approved_alias_queries("준공업지역 용적률 완화")) <= 4


def test_compound_decomposition_removes_generic_intent_without_inventing_tokens() -> None:
    variants = legal_compound_queries("역세권 승강장 경계 거리 기준")

    assert "역세권 승강장 경계" in variants
    source_tokens = set("역세권 승강장 경계 거리 기준".split())
    assert all(set(variant.split()) <= source_tokens for variant in variants)
    assert len(variants) <= 4


def test_real_shaped_queries_reach_expected_clause_with_deterministic_stage(tmp_path: Path) -> None:
    cases = (
        ("안심주택 사업대상지 최소 면적", "C-AREA", FallbackStage.APPROVED_ALIAS),
        ("역세권 승강장 경계 거리 기준", "C-STATION", FallbackStage.LEGAL_COMPOUND_DECOMPOSITION),
        ("공공지원민간임대주택 주차장 설치기준", "C-PARKING-PRIVATE", FallbackStage.TOKEN_PREFIX),
        ("임대형기숙사 주차장 설치기준 복합 적용", "C-PARKING-DORM", FallbackStage.TOKEN_PREFIX),
        ("준공업지역 공동주택 기본용적률", "C-FAR", FallbackStage.TOKEN_PREFIX),
        ("준공업지역 산업부지 확보비율", "C-INDUSTRIAL", FallbackStage.TOKEN_PREFIX),
        ("지구단위계획 주차장 설치기준 완화", "C-DUP", FallbackStage.TOKEN_PREFIX),
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        for query, expected_clause_id, expected_stage in cases:
            result = search_clause_with_fallback(connection, query, limit=5)
            assert expected_clause_id in {hit.clause_id for hit in result.hits}
            assert result.success_stage == expected_stage
            assert result.traces[-1].stage == expected_stage
            assert result.traces[-1].hit_count > 0


def test_fallback_stops_after_first_successful_stage(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        result = search_clause_with_fallback(connection, "산업부지 확보비율", limit=5)

    assert result.success_stage == FallbackStage.TOKEN_PREFIX
    assert result.traces[-1].hit_count > 0
    assert FallbackStage.APPROVED_ALIAS not in {trace.stage for trace in result.traces}
    assert FallbackStage.LEGAL_COMPOUND_DECOMPOSITION not in {
        trace.stage for trace in result.traces
    }
