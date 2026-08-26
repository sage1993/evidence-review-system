import hashlib
from pathlib import Path

from PIL import Image

import evidence_review.drawing_review.visual_pages as visual_pages


def test_large_visual_page_builds_verified_tile_manifest(tmp_path: Path) -> None:
    assert hasattr(visual_pages, "ensure_visual_page_tiles")

    image_path = tmp_path / "page-0001.png"
    Image.new("RGB", (5000, 4200), "white").save(image_path, format="PNG")
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    page = visual_pages.VisualPageAsset(
        attachment_id="ATT-VISUAL-1",
        source_sha256="a" * 64,
        page=1,
        width=5000.0,
        height=4200.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=image_path,
        image_sha256=image_sha256,
    )

    tiles = visual_pages.ensure_visual_page_tiles(tmp_path, page)

    assert len(tiles) > 1
    assert all(tile.width <= 2048 for tile in tiles)
    assert all(tile.height <= 2048 for tile in tiles)
    assert all(tile.path.is_file() for tile in tiles)
    manifest = (
        tmp_path
        / "case-page-tiles-v1"
        / page.attachment_id
        / "page-0001"
        / "manifest.json"
    )
    assert manifest.is_file()

    second = visual_pages.ensure_visual_page_tiles(tmp_path, page)
    assert second == tiles


def test_small_visual_page_does_not_tile(tmp_path: Path) -> None:
    assert hasattr(visual_pages, "ensure_visual_page_tiles")

    image_path = tmp_path / "page-0001.png"
    Image.new("RGB", (1200, 900), "white").save(image_path, format="PNG")
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    page = visual_pages.VisualPageAsset(
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