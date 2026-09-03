"""Contract tests for the verified reference-page presentation projection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from evidence_review.review_packet import reference_pages
from evidence_review.review_packet.reference_pages import build_reference_projection


@dataclass(frozen=True)
class _VerifiedPage:
    revision_id: str = "REV1"
    page: int = 3
    source_hash: str = "a" * 64
    width: float = 120.0
    height: float = 200.0
    origin_x: float = 0.0
    origin_y: float = 0.0
    rotation: int = 0
    box_kind: str = "MEDIA_BOX"
    image_sha256: str = "b" * 64


@pytest.fixture
def verified_page(monkeypatch: pytest.MonkeyPatch) -> _VerifiedPage:
    page = _VerifiedPage()

    def read_verified_page_image(
        page_root: Path,
        revision_id: str,
        page_number: int,
        source_hash: str,
    ) -> _VerifiedPage:
        assert page_root
        assert (revision_id, page_number, source_hash) == (
            page.revision_id,
            page.page,
            page.source_hash,
        )
        return page

    monkeypatch.setattr(
        reference_pages,
        "read_verified_page_image",
        read_verified_page_image,
    )
    return page


@pytest.fixture
def citation() -> dict[str, object]:
    return {
        "citation_id": "CIT-E1",
        "type": "TEXT",
        "document_id": "DOC1",
        "revision_id": "REV1",
        "document_name": "Document",
        "document_page_count": 5,
        "page_number": 3,
        "page_width": 120.0,
        "page_height": 200.0,
        "page_origin_x": 0.0,
        "page_origin_y": 0.0,
        "page_rotation": 0,
        "page_box_kind": "MEDIA_BOX",
        "source_hash": "a" * 64,
        "title": "제3조",
        "quote": "정확한 인용문",
        "bbox": [10.0, 20.0, 110.0, 40.0],
        "table": None,
        "visual": None,
    }


def test_verified_page_and_anchor_projection(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
) -> None:
    documents, pages, anchors = build_reference_projection(
        [citation],
        page_root=tmp_path,
    )

    assert len(documents) == 1
    assert len(pages) == 1

    page = pages[0]
    assert page["asset_key"] == "reference-page-1"
    assert page["revision_id"] == "REV1"
    assert page["page"] == 3
    assert page["source_hash"] == "a" * 64
    assert page["image_sha256"] == verified_page.image_sha256

    anchor = anchors["CIT-E1"]
    assert anchor["page_asset_key"] == "reference-page-1"
    assert anchor["bbox"] == {
        "coordinate_system": "PDF_BOTTOM_LEFT_POINTS",
        "coordinates": [10.0, 20.0, 110.0, 40.0],
    }


def test_same_verified_raster_is_deduplicated(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
) -> None:
    second = dict(citation)
    second.update({"citation_id": "CIT-E2", "bbox": [20.0, 30.0, 100.0, 50.0]})

    documents, pages, anchors = build_reference_projection(
        [citation, second],
        page_root=tmp_path,
    )

    assert len(pages) == 1
    assert set(anchors) == {"CIT-E1", "CIT-E2"}
    assert anchors["CIT-E1"]["page_asset_key"] == pages[0]["asset_key"]
    assert anchors["CIT-E2"]["page_asset_key"] == pages[0]["asset_key"]
    assert documents[0]["page_asset_keys"] == ["reference-page-1"]


def test_reference_projection_does_not_embed_raster_bytes(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
) -> None:
    documents, pages, anchors = build_reference_projection(
        [citation],
        page_root=tmp_path,
    )

    assert "data_uri" not in pages[0]
    assert "image_bytes" not in pages[0]
    assert "image_path" not in pages[0]

    serialized = json.dumps(
        {"documents": documents, "pages": pages, "anchors": anchors},
        sort_keys=True,
    )

    assert "data:image/png;base64" not in serialized
    assert str(tmp_path) not in serialized


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page_width", 120.6),
        ("page_height", 200.6),
        ("page_origin_x", 1.0),
        ("page_origin_y", 1.0),
        ("page_rotation", 90),
        ("page_box_kind", "CROP_BOX"),
    ],
)
def test_page_geometry_mismatch_fails_closed(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
    field: str,
    value: object,
) -> None:
    mismatched = dict(citation)
    mismatched[field] = value

    with pytest.raises(ValueError, match="PAGE_RENDER_GEOMETRY_MISMATCH"):
        build_reference_projection([mismatched], page_root=tmp_path)


def test_citation_bbox_out_of_bounds_fails_closed(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
) -> None:
    out_of_bounds = dict(citation)
    out_of_bounds["bbox"] = [0.0, 0.0, 9999.0, 40.0]

    with pytest.raises(
        ValueError,
        match="citation bbox is outside the verified page bounds",
    ):
        build_reference_projection([out_of_bounds], page_root=tmp_path)


def test_source_hash_mismatch_preserves_verifier_error_contract(
    tmp_path: Path,
    citation: dict[str, object],
) -> None:
    image_bytes = b"verified-page-fixture"
    revision_root = tmp_path / "REV1"
    revision_root.mkdir()
    (revision_root / "page-0003.png").write_bytes(image_bytes)
    (revision_root / "page-0003.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/page-image",
                "version": 1,
                "revision_id": "REV1",
                "page_number": 3,
                "source_hash": "c" * 64,
                "pdf_width": 120.0,
                "pdf_height": 200.0,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="page image source hash mismatch"):
        build_reference_projection([citation], page_root=tmp_path)


def test_duplicate_reference_citation_id_fails_closed(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
) -> None:
    duplicate = dict(citation)
    duplicate["bbox"] = [20.0, 30.0, 100.0, 50.0]

    with pytest.raises(ValueError, match="duplicate reference citation id"):
        build_reference_projection([citation, duplicate], page_root=tmp_path)


@pytest.mark.parametrize("field", ["document_name", "document_page_count"])
def test_document_metadata_conflict_fails_closed(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
    field: str,
) -> None:
    conflicting = dict(citation)
    conflicting["citation_id"] = "CIT-E2"
    conflicting[field] = "Other" if field == "document_name" else 6

    with pytest.raises(ValueError, match="conflicting document metadata"):
        build_reference_projection([citation, conflicting], page_root=tmp_path)


def test_same_page_key_with_conflicting_document_identity_fails_closed(
    tmp_path: Path,
    citation: dict[str, object],
    verified_page: _VerifiedPage,
) -> None:
    conflicting = dict(citation)
    conflicting.update({"citation_id": "CIT-E2", "document_id": "DOC2"})

    with pytest.raises(ValueError, match="reference page has conflicting document identity"):
        build_reference_projection([citation, conflicting], page_root=tmp_path)
