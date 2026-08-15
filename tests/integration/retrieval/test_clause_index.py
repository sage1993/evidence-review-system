from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index, require_fresh_index


def _snapshot() -> EvidenceSnapshot:
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
        elements=(
            {
                "id": "E-1",
                "revision_id": "REV-1",
                "page_id": "P-1",
                "page_number": 1,
                "element_type": "paragraph",
                "raw_json": {"text": "사업대상지는 1,000㎡ 이상이어야 한다."},
                "raw_text": "사업대상지는 1,000㎡ 이상이어야 한다.",
                "normalized_text": "사업대상지는 1,000㎡ 이상이어야 한다.",
                "raw_payload_hash": "b" * 64,
                "bbox": [10, 20, 300, 40],
                "parser_order": 0,
            },
        ),
        clauses=(
            {
                "id": "C-1",
                "revision_id": "REV-1",
                "title": "사업대상지 일반기준",
                "raw_text": "안심주택 사업대상지는 원칙적으로 대지면적 1,000㎡ 이상이어야 한다.",
                "normalized_text": "안심주택 사업대상지는 원칙적으로 대지면적 1,000㎡ 이상이어야 한다.",
                "review_status": "AUTOMATIC",
            },
        ),
        links=(
            {
                "id": "L-1",
                "source_id": "C-1",
                "target_id": "E-1",
                "relation_type": "source_element",
            },
        ),
    )


def test_build_fts_index_populates_separate_clause_semantic_index(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        snapshot_hash = build_fts_index(connection)

        assert require_fresh_index(connection) == snapshot_hash
        assert connection.execute(
            """
            SELECT clause_id, document_id, revision_id, title, normalized_text
            FROM clause_retrieval_records
            """
        ).fetchall() == [
            (
                "C-1",
                "DOC-1",
                "REV-1",
                "사업대상지 일반기준",
                "안심주택 사업대상지는 원칙적으로 대지면적 1,000㎡ 이상이어야 한다.",
            )
        ]
        assert connection.execute(
            "SELECT clause_id FROM clause_fts WHERE clause_fts MATCH ?",
            ('"대지면적"',),
        ).fetchall() == [("C-1",)]
        assert connection.execute(
            "SELECT clause_id, evidence_id, relation_type FROM clause_evidence_links"
        ).fetchall() == [("C-1", "E-1", "source_element")]


def test_clause_without_verified_element_link_remains_searchable(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot = EvidenceSnapshot(
        documents=snapshot.documents,
        revisions=snapshot.revisions,
        pages=snapshot.pages,
        elements=snapshot.elements,
        clauses=snapshot.clauses,
        links=(),
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, snapshot)
        connection = store.require_connection()
        build_fts_index(connection)

        assert connection.execute(
            "SELECT clause_id FROM clause_retrieval_records"
        ).fetchall() == [("C-1",)]
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_evidence_links"
        ).fetchone() == (0,)
