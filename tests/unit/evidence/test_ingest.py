from pathlib import Path

import pytest

from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.store import EvidenceStore


def base_snapshot(**overrides) -> EvidenceSnapshot:
    values = {
        "documents": ({"id": "DOC-1", "title": "Document"},),
        "revisions": (
            {
                "id": "REV-1",
                "document_id": "DOC-1",
                "source_hash": "a" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
            {
                "id": "REV-2",
                "document_id": "DOC-1",
                "source_hash": "b" * 64,
                "byte_size": 10,
                "page_count": 1,
            },
        ),
        "pages": (
            {
                "id": "REV-1-P0001",
                "revision_id": "REV-1",
                "page_number": 1,
                "width": 600,
                "height": 800,
            },
            {
                "id": "REV-2-P0001",
                "revision_id": "REV-2",
                "page_number": 1,
                "width": 600,
                "height": 800,
            },
        ),
    }
    values.update(overrides)
    return EvidenceSnapshot(**values)


def element(**overrides):
    values = {
        "id": "E-1",
        "revision_id": "REV-1",
        "page_id": "REV-1-P0001",
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": "content"},
        "raw_text": "content",
        "normalized_text": "content",
        "raw_payload_hash": "c" * 64,
        "bbox": [10, 20, 30, 40],
        "parser_order": 0,
    }
    values.update(overrides)
    return values


def test_element_page_id_revision_mismatch_rolls_back(tmp_path: Path) -> None:
    snapshot = base_snapshot(elements=(element(revision_id="REV-2"),))
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        with pytest.raises(ValueError, match="PAGE_REFERENCE_MISMATCH"):
            ingest_snapshot(store, snapshot)
        assert store.scalar("SELECT COUNT(*) FROM documents") == 0
        assert store.scalar("SELECT COUNT(*) FROM pages") == 0


def test_element_page_number_mismatch_is_rejected(tmp_path: Path) -> None:
    snapshot = base_snapshot(elements=(element(page_number=2),))
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        with pytest.raises(ValueError, match="PAGE_REFERENCE_MISMATCH"):
            ingest_snapshot(store, snapshot)


def test_table_missing_page_is_rejected(tmp_path: Path) -> None:
    snapshot = base_snapshot(
        tables=(
            {
                "id": "T-1",
                "revision_id": "REV-1",
                "page_number": 2,
                "bbox": [10, 20, 30, 40],
                "raw_json": {"rows": []},
                "normalized_json": None,
            },
        )
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        with pytest.raises(ValueError, match="PAGE_REFERENCE_NOT_FOUND"):
            ingest_snapshot(store, snapshot)


def test_visual_explicit_page_mismatch_is_rejected(tmp_path: Path) -> None:
    snapshot = base_snapshot(
        visuals=(
            {
                "id": "V-1",
                "page_id": "REV-1-P0001",
                "revision_id": "REV-2",
                "page_number": 1,
                "kind": "diagram",
                "relative_path": "visuals/diagram.png",
                "sha256": "d" * 64,
                "bbox": [10, 20, 30, 40],
                "duplicate_group": "DG-1",
            },
        )
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        with pytest.raises(ValueError, match="PAGE_REFERENCE_MISMATCH"):
            ingest_snapshot(store, snapshot)


def test_bbox_outside_bound_page_is_rejected(tmp_path: Path) -> None:
    snapshot = base_snapshot(elements=(element(bbox=[0, 0, 601, 10]),))
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        with pytest.raises(ValueError, match="BBOX_OUT_OF_PAGE"):
            ingest_snapshot(store, snapshot)


def test_v2_storage_uses_page_id_as_only_page_authority(tmp_path: Path) -> None:
    snapshot = base_snapshot(
        elements=(element(),),
        tables=(
            {
                "id": "T-1",
                "revision_id": "REV-1",
                "page_number": 1,
                "bbox": [10, 20, 30, 40],
                "raw_json": {"rows": []},
                "normalized_json": None,
            },
        ),
        visuals=(
            {
                "id": "V-1",
                "revision_id": "REV-1",
                "page_number": 1,
                "kind": "diagram",
                "relative_path": "visuals/diagram.png",
                "sha256": "d" * 64,
                "bbox": [10, 20, 30, 40],
                "duplicate_group": "DG-1",
            },
        ),
    )
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, snapshot)
        connection = store.require_connection()
        assert connection.execute("SELECT page_id FROM elements").fetchone()[0] == "REV-1-P0001"
        assert connection.execute("SELECT page_id FROM tables").fetchone()[0] == "REV-1-P0001"
        assert connection.execute("SELECT page_id FROM visuals").fetchone()[0] == "REV-1-P0001"
        for table in ("elements", "tables", "visuals"):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert "page_id" in columns
            assert "page_number" not in columns
            assert "revision_id" not in columns
