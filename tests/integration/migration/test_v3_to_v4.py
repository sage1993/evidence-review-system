from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from evidence_review.evidence.migrations.v3_to_v4 import migrate_v3_to_v4
from evidence_review.evidence.schema_version import detect_schema_version
from evidence_review.retrieval.index import StaleRetrievalIndexError, require_fresh_index

V3_SCHEMA = Path("src/evidence_review/evidence/schema_v3.sql")


def _create_v3(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(V3_SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO documents(id, title) VALUES('DOC-1', '법규')"
        )
        connection.execute(
            """
            INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
            VALUES('REV-1', 'DOC-1', ?, 10, 1)
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO pages(
                id, revision_id, page_number, width, height,
                origin_x, origin_y, rotation, box_kind
            ) VALUES('P-1', 'REV-1', 1, 595, 842, 0, 0, 0, 'MEDIA_BOX')
            """
        )
        connection.execute(
            """
            INSERT INTO clauses(id, revision_id, title, raw_text, normalized_text, review_status)
            VALUES(
                'C-1', 'REV-1', '제1조', '최소면적은 1,000㎡이다.',
                '최소면적은 1,000㎡이다.', 'AUTOMATIC'
            )
            """
        )
        connection.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
            ("b" * 64,),
        )
        connection.execute(
            "INSERT INTO retrieval_meta(key, value) VALUES('snapshot_hash', ?)",
            ("b" * 64,),
        )
        connection.commit()
    finally:
        connection.close()


def test_v3_to_v4_is_copy_on_write_and_invalidates_retrieval_freshness(tmp_path: Path) -> None:
    source = tmp_path / "source-v3.sqlite"
    output = tmp_path / "output-v4.sqlite"
    _create_v3(source)
    source_bytes = source.read_bytes()

    report = migrate_v3_to_v4(source, output)

    assert report.source_schema_version == 3
    assert report.output_schema_version == 4
    assert source.read_bytes() == source_bytes

    connection = sqlite3.connect(output)
    try:
        assert detect_schema_version(connection) == 4
        assert connection.execute(
            "SELECT COUNT(*) FROM clauses WHERE id='C-1'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_retrieval_records"
        ).fetchone() == (0,)
        with pytest.raises(StaleRetrievalIndexError):
            require_fresh_index(connection)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
