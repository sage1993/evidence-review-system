import sqlite3
from pathlib import Path

from ansim_review.canonical_json import dumps
from ansim_review.retrieval.index import build_fts_index
from ansim_review.retrieval.structured import retrieve_structured

SCHEMA = Path("src/ansim_review/evidence/schema.sql")


def _page_only_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute("INSERT INTO documents(id, title) VALUES(?, ?)", ("DOC1", "Test"))
    connection.execute(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES(?, ?, ?, ?, ?)
        """,
        ("REV1", "DOC1", "a" * 64, 1, 1),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES(?, ?, ?, ?, ?)
        """,
        ("PAGE1", "REV1", 1, 595.0, 842.0),
    )
    connection.execute(
        """
        INSERT INTO elements(
            id, page_id, element_type, raw_json, raw_text, normalized_text,
            raw_payload_hash, bbox_json, parser_order
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "E-PAGE",
            "PAGE1",
            "clause",
            dumps({"text": "pageonlystructured"}),
            "pageonlystructured",
            "pageonlystructured",
            "c" * 64,
            None,
            0,
        ),
    )
    connection.execute(
        "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
        ("b" * 64,),
    )
    connection.commit()
    build_fts_index(connection)
    return connection


def test_structured_retrieval_preserves_page_only_hit() -> None:
    connection = _page_only_connection()
    try:
        hits = retrieve_structured(connection, {"evidence_id": "E-PAGE"})

        assert [hit.evidence_id for hit in hits] == ["E-PAGE"]
        assert hits[0].bbox is None
        assert hits[0].citation_quality.value == "PAGE_ONLY"
    finally:
        connection.close()
