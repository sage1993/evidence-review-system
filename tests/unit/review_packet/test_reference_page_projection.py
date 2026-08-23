from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest


def _write_page(
    root: Path,
    *,
    revision_id: str = "REV-TEXT",
    page_number: int = 5,
    source_hash: str = "a" * 64,
) -> bytes:
    directory = root / revision_id
    directory.mkdir(parents=True)
    image_bytes = b"\x89PNG\r\n\x1a\nreference-page"
    (directory / f"page-{page_number:04d}.png").write_bytes(image_bytes)
    (directory / f"page-{page_number:04d}.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/page-image",
                "version": 1,
                "revision_id": revision_id,
                "page_number": page_number,
                "source_hash": source_hash,
                "pdf_width": 595.0,
                "pdf_height": 842.0,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return image_bytes


def _citation(
    citation_id: str,
    *,
    bbox: list[float] | None = None,
) -> dict[str, object]:
    return {
        "citation_id": citation_id,
        "evidence_id": citation_id.removeprefix("CIT-"),
        "document_id": "DOC-TEXT",
        "document_name": "서울특별시 건축조례",
        "document_page_count": 24,
        "revision_id": "REV-TEXT",
        "page_number": 5,
        "source_hash": "a" * 64,
        "page_width": 595.0,
        "page_height": 842.0,
        "page_origin_x": 0.0,
        "page_origin_y": 0.0,
        "page_rotation": 0,
        "page_box_kind": "MEDIA_BOX",
        "bbox": bbox or [72.0, 420.0, 510.0, 460.0],
        "title": "제8조",
        "quote": "3미터 이상의 거리를 확보한다.",
        "reference": {"type": "TEXT", "table": None, "visual": None},
    }


def test_reference_projection_materializes_one_verified_page_for_two_anchors(
    tmp_path: Path,
) -> None:
    _write_page(tmp_path)
    module = importlib.import_module(
        "evidence_review.review_packet.reference_projection"
    )

    documents, pages, anchors = module.build_reference_projection(
        (
            _citation("CIT-TEXT-1"),
            _citation(
                "CIT-TEXT-2",
                bbox=[80.0, 300.0, 400.0, 330.0],
            ),
        ),
        page_root=tmp_path,
    )

    assert len(pages) == 1
    assert pages[0]["page"] == 5
    assert str(pages[0]["data_uri"]).startswith("data:image/png;base64,")
    assert documents == [
        {
            "document_id": "DOC-TEXT",
            "revision_id": "REV-TEXT",
            "document_name": "서울특별시 건축조례",
            "page_count": 24,
            "page_asset_keys": [pages[0]["asset_key"]],
        }
    ]
    assert set(anchors) == {"CIT-TEXT-1", "CIT-TEXT-2"}
    assert anchors["CIT-TEXT-1"]["page_asset_key"] == pages[0]["asset_key"]
    assert anchors["CIT-TEXT-1"]["bbox"] == {
        "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
        "coordinates": [72.0, 420.0, 510.0, 460.0],
    }


def test_reference_projection_fails_closed_on_page_geometry_mismatch(
    tmp_path: Path,
) -> None:
    _write_page(tmp_path)
    module = importlib.import_module(
        "evidence_review.review_packet.reference_projection"
    )
    citation = _citation("CIT-TEXT-1")
    citation["page_width"] = 594.0

    with pytest.raises(ValueError, match="PAGE_RENDER_GEOMETRY_MISMATCH"):
        module.build_reference_projection((citation,), page_root=tmp_path)
