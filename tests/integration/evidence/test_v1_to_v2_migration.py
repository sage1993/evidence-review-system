import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from evidence_review.canonical_json import dumps
from evidence_review.evidence.migrations.v1_to_v2 import migrate_v1_to_v2
from evidence_review.evidence.schema_version import detect_schema_version
from evidence_review.evidence.snapshot import compute_logical_snapshot_hash
from evidence_review.evidence.store import EvidenceStore

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_v1_database(path: Path, *, defect: str | None = None) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.execute("INSERT INTO documents(id, title) VALUES('DOC-1', 'Document')")
    connection.executemany(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES(?, 'DOC-1', ?, 10, 1)
        """,
        (("REV-1", "a" * 64), ("REV-2", "b" * 64)),
    )
    connection.executemany(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES(?, ?, 1, 600, 800)
        """,
        (("REV-1-P0001", "REV-1"), ("REV-2-P0001", "REV-2")),
    )
    element_revision = "REV-2" if defect == "element_mismatch" else "REV-1"
    connection.execute(
        """
        INSERT INTO elements(
            id, revision_id, page_id, page_number, element_type, raw_json,
            raw_text, normalized_text, raw_payload_hash, bbox_json, parser_order
        ) VALUES('E-1', ?, 'REV-1-P0001', 1, 'paragraph', ?,
                 'content', 'content', ?, ?, 0)
        """,
        (
            element_revision,
            dumps({"text": "content"}),
            "c" * 64,
            dumps([10, 20, 30, 40]),
        ),
    )
    table_page = 2 if defect == "missing_table_page" else 1
    connection.execute(
        """
        INSERT INTO tables(
            id, revision_id, page_number, bbox_json, raw_json, normalized_json
        ) VALUES('T-1', 'REV-1', ?, ?, ?, ?)
        """,
        (
            table_page,
            dumps([40, 50, 100, 120]),
            dumps({"rows": [["a", "b"]]}),
            dumps({"rows": [["a", "b"]]}),
        ),
    )
    visual_bbox = (
        [120, 130, 601, 220]
        if defect == "visual_bbox"
        else [120, 130, 200, 220]
    )
    connection.execute(
        """
        INSERT INTO visuals(
            id, revision_id, page_number, kind, relative_path, sha256,
            bbox_json, duplicate_group
        ) VALUES('V-1', 'REV-1', 1, 'diagram', 'visuals/a.png', ?, ?, 'DG-1')
        """,
        ("d" * 64, dumps(visual_bbox)),
    )
    connection.execute(
        """
        INSERT INTO retrieval_records(
            evidence_id, evidence_type, document_id, revision_id, page_number,
            bbox_json, source_hash, title, raw_text, normalized_text
        ) VALUES('STALE', 'element', 'DOC-1', 'REV-1', 1, ?, ?,
                 'stale', 'stale', 'stale')
        """,
        (dumps([0, 0, 1, 1]), "a" * 64),
    )
    connection.execute(
        """
        INSERT INTO evidence_fts(evidence_id, title, raw_text, normalized_text)
        VALUES('STALE', 'stale', 'stale', 'stale')
        """
    )
    connection.execute(
        "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
        ("e" * 64,),
    )
    connection.commit()
    connection.close()


def test_valid_v1_database_migrates_copy_on_write(tmp_path: Path) -> None:
    source = tmp_path / "v1.sqlite"
    output = tmp_path / "v2.sqlite"
    create_v1_database(source)
    source_before = source.read_bytes()
    source_connection = sqlite3.connect(source)
    source_connection.row_factory = sqlite3.Row
    expected_logical_hash = compute_logical_snapshot_hash(source_connection)
    source_connection.close()

    report = migrate_v1_to_v2(source, output)

    assert source.read_bytes() == source_before
    assert report.source_schema_version == 1
    assert report.output_schema_version == 2
    assert report.logical_snapshot_hash == expected_logical_hash
    assert report.source_sha256 == hashlib.sha256(source_before).hexdigest()
    assert report.output_sha256 == sha256_file(output)
    assert report.report_path.is_file()
    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["format"] == "evidence-review/evidence-migration-report"
    assert payload["logical_snapshot_hash"] == expected_logical_hash

    with EvidenceStore(
        output,
        schema_resource="schema_v2.sql",
        require_current=False,
    ) as store:
        connection = store.require_connection()
        assert detect_schema_version(connection) == 2
        assert compute_logical_snapshot_hash(connection) == expected_logical_hash
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        row = connection.execute(
            """
            SELECT page_id, revision_id, page_number
            FROM retrieval_records
            WHERE evidence_id = 'E-1'
            """
        ).fetchone()
        assert tuple(row) == ("REV-1-P0001", "REV-1", 1)
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_records WHERE evidence_id = 'STALE'"
        ).fetchone()[0] == 0
        for table in ("elements", "tables", "visuals"):
            columns = {
                info[1] for info in connection.execute(f"PRAGMA table_info({table})")
            }
            assert "page_id" in columns
            assert "revision_id" not in columns
            assert "page_number" not in columns


def test_migration_refuses_existing_output_without_touching_files(tmp_path: Path) -> None:
    source = tmp_path / "v1.sqlite"
    output = tmp_path / "v2.sqlite"
    create_v1_database(source)
    output.write_bytes(b"existing")
    source_before = source.read_bytes()

    with pytest.raises(FileExistsError):
        migrate_v1_to_v2(source, output)

    assert source.read_bytes() == source_before
    assert output.read_bytes() == b"existing"


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("element_mismatch", "PAGE_REFERENCE_MISMATCH"),
        ("missing_table_page", "PAGE_REFERENCE_NOT_FOUND"),
        ("visual_bbox", "BBOX_OUT_OF_PAGE"),
    ],
)
def test_invalid_v1_database_leaves_no_output(
    tmp_path: Path,
    defect: str,
    message: str,
) -> None:
    source = tmp_path / "v1.sqlite"
    output = tmp_path / "v2.sqlite"
    create_v1_database(source, defect=defect)
    source_before = source.read_bytes()

    with pytest.raises(ValueError, match=message):
        migrate_v1_to_v2(source, output)

    assert source.read_bytes() == source_before
    assert not output.exists()
    assert not output.with_name(f"{output.name}.migration-report.json").exists()
    assert not output.with_name(f".{output.name}.tmp").exists()
