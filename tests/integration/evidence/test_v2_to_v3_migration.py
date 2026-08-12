import sqlite3
from pathlib import Path

from ansim_review.evidence.migrations.v2_to_v3 import migrate_v2_to_v3
from ansim_review.evidence.schema_version import detect_schema_version


def _create_v2(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        Path("src/ansim_review/evidence/schema_v2.sql").read_text(
            encoding="utf-8"
        )
    )
    connection.execute("INSERT INTO documents(id, title) VALUES('DOC-1', 'Policy')")
    connection.execute(
        """
        INSERT INTO revisions(
            id, document_id, source_hash, byte_size, page_count
        ) VALUES('REV-1', 'DOC-1', ?, 3, 1)
        """,
        ("a" * 64,),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES('REV-1-P0001', 'REV-1', 1, 500, 700)
        """
    )
    connection.commit()
    connection.close()


def test_v2_to_v3_preserves_source_and_adds_default_page_geometry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "v2.sqlite"
    output = tmp_path / "v3.sqlite"
    _create_v2(source)
    source_bytes = source.read_bytes()

    report = migrate_v2_to_v3(source, output)

    assert source.read_bytes() == source_bytes
    assert report.source_schema_version == 2
    assert report.output_schema_version == 3
    connection = sqlite3.connect(output)
    try:
        assert detect_schema_version(connection) == 3
        row = connection.execute(
            """
            SELECT width, height, origin_x, origin_y, rotation, box_kind
            FROM pages WHERE id = 'REV-1-P0001'
            """
        ).fetchone()
        assert row == (500.0, 700.0, 0.0, 0.0, 0, "MEDIA_BOX")
    finally:
        connection.close()