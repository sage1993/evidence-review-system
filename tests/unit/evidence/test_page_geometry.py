from pathlib import Path

import pytest

from ansim_review.contracts.common import BBox
from ansim_review.evidence.page_geometry import (
    PageGeometry,
    load_page_geometry,
    validate_bbox_within_page,
)
from ansim_review.evidence.store import EvidenceStore


def page() -> PageGeometry:
    return PageGeometry(
        page_id="REV-1-P0001",
        revision_id="REV-1",
        page_number=1,
        width=600.0,
        height=800.0,
    )


def test_load_page_geometry_uses_authoritative_page_record(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        connection = store.require_connection()
        connection.execute("INSERT INTO documents(id, title) VALUES('DOC-1', 'Document')")
        connection.execute(
            """
            INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
            VALUES('REV-1', 'DOC-1', ?, 1, 1)
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO pages(id, revision_id, page_number, width, height)
            VALUES('REV-1-P0001', 'REV-1', 1, 600, 800)
            """
        )
        connection.commit()

        assert load_page_geometry(connection, "REV-1-P0001") == page()


def test_load_page_geometry_rejects_missing_page(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        with pytest.raises(ValueError, match="PAGE_REFERENCE_NOT_FOUND"):
            load_page_geometry(store.require_connection(), "MISSING")


def test_bbox_on_exact_page_boundary_is_valid() -> None:
    assert validate_bbox_within_page([0, 0, 600, 800], page()) == BBox(
        0.0, 0.0, 600.0, 800.0
    )


@pytest.mark.parametrize(
    ("bbox", "message"),
    [
        ([-0.01, 0, 10, 10], "BBOX_OUT_OF_PAGE"),
        ([0, 0, 600.01, 10], "BBOX_OUT_OF_PAGE"),
        ([0, 0, 10, 800.01], "BBOX_OUT_OF_PAGE"),
        ([10, 0, 5, 10], "inverted"),
        ([0, 0, float("inf"), 10], "finite"),
    ],
)
def test_invalid_bbox_is_rejected(bbox: list[float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_bbox_within_page(bbox, page())


def test_null_bbox_is_preserved() -> None:
    assert validate_bbox_within_page(None, page()) is None
