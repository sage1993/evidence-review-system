import sqlite3
from pathlib import Path

from ansim_review.canonical_json import dumps
from ansim_review.retrieval.index import build_fts_index, search_fts

SCHEMA = Path("src/ansim_review/evidence/schema.sql")


def _connection() -> sqlite3.Connection:
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
        "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
        ("b" * 64,),
    )
    connection.commit()
    return connection


def _insert_element(
    connection: sqlite3.Connection,
    *,
    evidence_id: str,
    text: str,
    bbox: list[float] | None,
) -> None:
    connection.execute(
        """
        INSERT INTO elements(
            id, page_id, element_type, raw_json, raw_text, normalized_text,
            raw_payload_hash, bbox_json, parser_order
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id,
            "PAGE1",
            "clause",
            dumps({"text": text}),
            text,
            text,
            "c" * 64,
            None if bbox is None else dumps(bbox),
            0,
        ),
    )
    connection.commit()


def test_bboxless_element_is_lexically_retrievable() -> None:
    connection = _connection()
    try:
        _insert_element(
            connection,
            evidence_id="E-PAGE",
            text="bboxlessneedle",
            bbox=None,
        )
        build_fts_index(connection)

        hits = search_fts(connection, "bboxlessneedle")

        assert [hit.evidence_id for hit in hits] == ["E-PAGE"]
        assert hits[0].page_number == 1
        assert hits[0].bbox is None
    finally:
        connection.close()
