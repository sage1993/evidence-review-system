from pathlib import Path

from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index


def test_index_derives_page_metadata_from_page_id(tmp_path: Path) -> None:
    snapshot = EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "Document"},),
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
                "id": "REV-1-P0001",
                "revision_id": "REV-1",
                "page_number": 1,
                "width": 600,
                "height": 800,
            },
        ),
        elements=(
            {
                "id": "E-1",
                "page_id": "REV-1-P0001",
                "element_type": "paragraph",
                "raw_json": {"text": "content"},
                "raw_text": "content",
                "normalized_text": "content",
                "raw_payload_hash": "b" * 64,
                "bbox": [10, 20, 30, 40],
                "parser_order": 0,
            },
        ),
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, snapshot)
        build_fts_index(store.require_connection())
        row = store.require_connection().execute(
            """
            SELECT document_id, revision_id, page_id, page_number, source_hash
            FROM retrieval_records
            WHERE evidence_id = 'E-1'
            """
        ).fetchone()

    assert tuple(row) == (
        "DOC-1",
        "REV-1",
        "REV-1-P0001",
        1,
        "a" * 64,
    )
