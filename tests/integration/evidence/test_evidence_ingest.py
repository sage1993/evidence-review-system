import sqlite3
from pathlib import Path

import pytest

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore


def test_duplicate_element_rolls_back_entire_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    snapshot = EvidenceSnapshot(
        documents=({"id": "LAW1", "title": "Law One"},),
        revisions=(
            {
                "id": "LAW1-r1",
                "document_id": "LAW1",
                "source_hash": "a" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "LAW1-r1-P0001",
                "revision_id": "LAW1-r1",
                "page_number": 1,
                "width": 600,
                "height": 800,
            },
        ),
        elements=(
            {
                "id": "E1",
                "revision_id": "LAW1-r1",
                "page_id": "LAW1-r1-P0001",
                "page_number": 1,
                "element_type": "paragraph",
                "raw_json": {"content": "first"},
                "raw_text": "first",
                "normalized_text": None,
                "raw_payload_hash": "b" * 64,
                "bbox": [10, 20, 30, 40],
                "parser_order": 0,
            },
            {
                "id": "E1",
                "revision_id": "LAW1-r1",
                "page_id": "LAW1-r1-P0001",
                "page_number": 1,
                "element_type": "paragraph",
                "raw_json": {"content": "duplicate"},
                "raw_text": "duplicate",
                "normalized_text": None,
                "raw_payload_hash": "c" * 64,
                "bbox": [10, 50, 30, 70],
                "parser_order": 1,
            },
        ),
    )

    with EvidenceStore(database) as store:
        with pytest.raises(sqlite3.IntegrityError):
            ingest_snapshot(store, snapshot)

        assert store.scalar("SELECT COUNT(*) FROM documents") == 0
        assert store.scalar("SELECT COUNT(*) FROM revisions") == 0
        assert store.scalar("SELECT COUNT(*) FROM pages") == 0
        assert store.scalar("SELECT COUNT(*) FROM elements") == 0
        assert store.scalar("PRAGMA foreign_key_check") is None
        assert store.scalar("PRAGMA integrity_check") == "ok"


def test_snapshot_hash_is_independent_of_record_order(tmp_path: Path) -> None:
    first_snapshot = EvidenceSnapshot(
        documents=(
            {"id": "LAW2", "title": "Law Two"},
            {"id": "LAW1", "title": "Law One"},
        )
    )
    second_snapshot = EvidenceSnapshot(
        documents=tuple(reversed(first_snapshot.documents))
    )

    with EvidenceStore(tmp_path / "first-order.sqlite") as first_store:
        first_hash = ingest_snapshot(first_store, first_snapshot)
    with EvidenceStore(tmp_path / "second-order.sqlite") as second_store:
        second_hash = ingest_snapshot(second_store, second_snapshot)

    assert first_hash == second_hash
