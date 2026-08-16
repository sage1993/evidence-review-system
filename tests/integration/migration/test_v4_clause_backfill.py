from __future__ import annotations

from pathlib import Path

from evidence_review.evidence.clause_rebuild import ensure_clause_index
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index, require_fresh_index


def _element_only_snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "주차 기준 조례"},),
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
        elements=tuple(
            {
                "id": f"E-{index}",
                "revision_id": "REV-1",
                "page_id": "P-1",
                "page_number": 1,
                "element_type": "paragraph",
                "raw_json": {"text": text},
                "raw_text": text,
                "normalized_text": text,
                "raw_payload_hash": str(index) * 64,
                "bbox": [10.0, 10.0 + index * 20, 500.0, 25.0 + index * 20],
                "parser_order": index,
            }
            for index, text in enumerate(
                (
                    "제13조(주차장 설치기준 완화)",
                    "① 임대형기숙사를 제외한 안심주택인 경우 주차장을 설치하여야 한다.",
                    "② 임대형기숙사인 경우 별표 2에 따라 주차장을 설치하여야 한다.",
                    "③ 복합으로 계획하는 경우 주택용도에 따라 제1항 및 제2항을 각각 적용한다.",
                    "④ 지구단위계획으로 주차장 설치기준을 완화하여 적용할 수 있다.",
                ),
                start=1,
            )
        ),
    )


def test_existing_v4_element_only_workspace_backfills_clause_index(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _element_only_snapshot())
        connection = store.require_connection()
        snapshot_hash = build_fts_index(connection)

        assert connection.execute("SELECT COUNT(*) FROM elements").fetchone() == (5,)
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_retrieval_records"
        ).fetchone() == (0,)

        changed = ensure_clause_index(connection)

        assert changed is True
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone() == (4,)
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_retrieval_records"
        ).fetchone() == (4,)
        assert connection.execute("SELECT COUNT(*) FROM clause_fts").fetchone() == (4,)
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_evidence_links"
        ).fetchone() == (4,)
        assert require_fresh_index(connection) == snapshot_hash
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

        second = ensure_clause_index(connection)
        assert second is False
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone() == (4,)
