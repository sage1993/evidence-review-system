import hashlib
from pathlib import Path

import pytest
from PIL import Image

import evidence_review.drawing_review.visual_pages as visual_pages


def _large_page(tmp_path: Path) -> visual_pages.VisualPageAsset:
    image_path = tmp_path / "page-0001.png"
    Image.new("RGB", (5000, 4200), "white").save(image_path, format="PNG")
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    return visual_pages.VisualPageAsset(
        case_id="CASE-1",
        attachment_id="ATT-VISUAL-1",
        source_sha256="a" * 64,
        page=1,
        width=5000.0,
        height=4200.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=image_path,
        image_sha256=image_sha256,
    )


def test_large_visual_page_loader_does_not_materialize_missing_cache(
    tmp_path: Path,
) -> None:
    page = _large_page(tmp_path)
    tile_directory = (
        tmp_path
        / "case-page-tiles-v1"
        / visual_pages.visual_cache_identity(
            page.case_id,
            page.attachment_id,
            page.source_sha256,
        )
        / "page-0001"
    )

    with pytest.raises(FileNotFoundError, match="case visual tile cache is missing"):
        visual_pages.load_visual_page_tiles(tmp_path, page)

    assert not tile_directory.exists()


def test_large_visual_page_builds_verified_tile_manifest(tmp_path: Path) -> None:
    assert hasattr(visual_pages, "ensure_visual_page_tiles")

    page = _large_page(tmp_path)

    tiles = visual_pages.ensure_visual_page_tiles(tmp_path, page)

    assert len(tiles) > 1
    assert all(tile.width <= 2048 for tile in tiles)
    assert all(tile.height <= 2048 for tile in tiles)
    assert all(tile.path.is_file() for tile in tiles)
    manifest = (
        tmp_path
        / "case-page-tiles-v1"
        / visual_pages.visual_cache_identity(
            page.case_id,
            page.attachment_id,
            page.source_sha256,
        )
        / "page-0001"
        / "manifest.json"
    )
    assert manifest.is_file()

    second = visual_pages.ensure_visual_page_tiles(tmp_path, page)
    assert second == tiles
    assert visual_pages.load_visual_page_tiles(tmp_path, page) == tiles


def test_small_visual_page_does_not_tile(tmp_path: Path) -> None:
    assert hasattr(visual_pages, "ensure_visual_page_tiles")

    image_path = tmp_path / "page-0001.png"
    Image.new("RGB", (1200, 900), "white").save(image_path, format="PNG")
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    page = visual_pages.VisualPageAsset(
        case_id="CASE-1",
        attachment_id="ATT-VISUAL-2",
        source_sha256="b" * 64,
        page=1,
        width=1200.0,
        height=900.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=image_path,
        image_sha256=image_sha256,
    )

    assert visual_pages.ensure_visual_page_tiles(tmp_path, page) == ()
    assert visual_pages.load_visual_page_tiles(tmp_path, page) == ()
