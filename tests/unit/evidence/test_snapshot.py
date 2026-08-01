import sqlite3
from pathlib import Path

from ansim_review.canonical_json import dumps
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.snapshot import compute_logical_snapshot_hash
from ansim_review.evidence.store import EvidenceStore

V1_SCHEMA = Path("tests/fixtures/evidence/schema_v1.sql")


def populate_v1(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(V1_SCHEMA.read_text(encoding="utf-8"))
    connection.execute("INSERT INTO documents(id, title) VALUES('DOC-1', 'Document')")
    connection.execute(
        """
        INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
        VALUES('REV-1', 'DOC-1', ?, 10, 1)
        """,
        ("a" * 64,),
    )
    connection.execute(
        """
        INSERT INTO pages(id, revision_id, page_number, width, height)
        VALUES('REV-1-P0001', 'REV-1', 1, 600, 800)
        """
    )
    connection.execute(
        """
        INSERT INTO elements(
            id, revision_id, page_id, page_number, element_type, raw_json,
            raw_text, normalized_text, raw_payload_hash, bbox_json, parser_order
        ) VALUES('E-1', 'REV-1', 'REV-1-P0001', 1, 'paragraph', ?,
                 'content', 'content', ?, ?, 0)
        """,
        (dumps({"text": "content"}), "b" * 64, dumps([10, 20, 30, 40])),
    )
    connection.execute(
        """
        INSERT INTO tables(
            id, revision_id, page_number, bbox_json, raw_json, normalized_json
        ) VALUES('T-1', 'REV-1', 1, ?, ?, NULL)
        """,
        (dumps([40, 50, 100, 120]), dumps({"rows": []})),
    )
    connection.execute(
        """
        INSERT INTO visuals(
            id, revision_id, page_number, kind, relative_path, sha256,
            bbox_json, duplicate_group
        ) VALUES('V-1', 'REV-1', 1, 'diagram', 'visuals/a.png', ?, ?, 'DG-1')
        """,
        ("c" * 64, dumps([120, 130, 200, 220])),
    )
    connection.commit()
    return connection


def populate_v2(path: Path) -> sqlite3.Connection:
    store = EvidenceStore(path, create=True)
    store.__enter__()
    ingest_snapshot(
        store,
        EvidenceSnapshot(
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
            tables=(
                {
                    "id": "T-1",
                    "page_id": "REV-1-P0001",
                    "bbox": [40, 50, 100, 120],
                    "raw_json": {"rows": []},
                    "normalized_json": None,
                },
            ),
            visuals=(
                {
                    "id": "V-1",
                    "page_id": "REV-1-P0001",
                    "kind": "diagram",
                    "relative_path": "visuals/a.png",
                    "sha256": "c" * 64,
                    "bbox": [120, 130, 200, 220],
                    "duplicate_group": "DG-1",
                },
            ),
        ),
    )
    return store.require_connection()


def test_logical_snapshot_hash_matches_across_schema_layouts(tmp_path: Path) -> None:
    v1 = populate_v1(tmp_path / "v1.sqlite")
    v2 = populate_v2(tmp_path / "v2.sqlite")
    try:
        assert compute_logical_snapshot_hash(v1) == compute_logical_snapshot_hash(v2)
    finally:
        v1.close()
        v2.close()
