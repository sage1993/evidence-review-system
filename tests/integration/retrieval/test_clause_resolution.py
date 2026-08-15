from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.clause_resolution import (
    resolve_clause_to_evidence,
    search_clause_exact,
    search_clause_phrase,
    search_clause_token_and,
    search_clause_token_prefix_and,
)
from evidence_review.retrieval.index import build_fts_index


def _element(evidence_id: str, text: str, order: int) -> dict[str, object]:
    return {
        "id": evidence_id,
        "revision_id": "REV-1",
        "page_id": "P-1",
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": format(order + 1, "x")[-1] * 64,
        "bbox": [10.0, float(10 + order * 20), 500.0, float(20 + order * 20)],
        "parser_order": order,
    }


def _snapshot(*, include_links: bool = True) -> EvidenceSnapshot:
    elements = (
        _element("E-1", "제8조 제1항", 0),
        _element("E-2", "준공업지역 검토 근거 위치 2", 1),
        _element("E-3", "준공업지역 검토 근거 위치 3", 2),
    )
    links: tuple[dict[str, object], ...] = ()
    if include_links:
        links = tuple(
            {
                "id": f"L-{index}",
                "source_id": "C-FAR",
                "target_id": evidence_id,
                "relation_type": "source_element",
            }
            for index, evidence_id in enumerate(("E-1", "E-2", "E-3"), start=1)
        )
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "안심주택 운영기준"},),
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
        elements=elements,
        clauses=(
            {
                "id": "C-FAR",
                "revision_id": "REV-1",
                "title": "준공업지역 용적률",
                "raw_text": "준공업지역에서 공동주택을 포함하는 경우 기본용적률은 400% 이하로 정할 수 있다.",
                "normalized_text": "준공업지역에서 공동주택을 포함하는 경우 기본용적률은 400% 이하로 정할 수 있다.",
                "review_status": "AUTOMATIC",
            },
            {
                "id": "C-INDUSTRIAL",
                "revision_id": "REV-1",
                "title": "산업부지 확보비율",
                "raw_text": "산업부지 확보비율은 통합심의 결과에 따라 완화할 수 있다.",
                "normalized_text": "산업부지 확보비율은 통합심의 결과에 따라 완화할 수 있다.",
                "review_status": "AUTOMATIC",
            },
        ),
        links=links,
    )


def test_clause_phrase_search_uses_semantic_clause_text_not_element_text(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        hits = search_clause_phrase(connection, "기본용적률은 400% 이하")

        assert [hit.clause_id for hit in hits] == ["C-FAR"]
        assert hits[0].title == "준공업지역 용적률"
        assert "400% 이하" in hits[0].text
        assert hits[0].channel_scores[0].channel == "clause_phrase"


def test_clause_search_primitives_are_deterministic(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        assert [hit.clause_id for hit in search_clause_exact(connection, "준공업지역 용적률")] == [
            "C-FAR"
        ]
        assert [hit.clause_id for hit in search_clause_token_and(connection, "산업부지 확보비율")] == [
            "C-INDUSTRIAL"
        ]
        assert [
            hit.clause_id
            for hit in search_clause_token_prefix_and(connection, "산업부지 확보")
        ] == ["C-INDUSTRIAL"]


def test_resolver_materializes_only_verified_citation_grade_evidence(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        clause_hit = search_clause_phrase(connection, "기본용적률은 400% 이하")[0]

        evidence = resolve_clause_to_evidence(connection, clause_hit, max_source_elements=2)

        assert [hit.evidence_id for hit in evidence] == ["E-1", "E-2"]
        assert all(hit.revision_id == clause_hit.revision_id for hit in evidence)
        assert all(hit.bbox is not None for hit in evidence)
        assert all(hit.channel_scores[0].channel == "clause_citation" for hit in evidence)
        assert all("C-FAR" in hit.channel_scores[0].detail for hit in evidence)


def test_unlinked_clause_remains_searchable_but_cannot_fabricate_citation(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot(include_links=False))
        connection = store.require_connection()
        build_fts_index(connection)
        clause_hit = search_clause_phrase(connection, "산업부지 확보비율")[0]

        assert clause_hit.clause_id == "C-INDUSTRIAL"
        assert resolve_clause_to_evidence(connection, clause_hit) == ()


def test_resolver_rejects_invalid_limit(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        clause_hit = search_clause_phrase(connection, "기본용적률은 400% 이하")[0]

        assert resolve_clause_to_evidence(connection, clause_hit, max_source_elements=0) == ()
