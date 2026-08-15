from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from tests.helpers.pdf_fixtures import write_pdf_fixture


def test_page_image_cache_writes_and_reuses_verified_pngs(tmp_path: Path) -> None:
    from evidence_review.parsing.page_image_cache import cache_pdf_page_images

    source = write_pdf_fixture(tmp_path / "source.pdf", page_sizes=((100, 200), (300, 400)))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "page-images"

    cache_pdf_page_images(cache_root, source, "REV-1", source_hash)

    image = cache_root / "REV-1" / "page-0001.png"
    metadata = cache_root / "REV-1" / "page-0001.json"
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert payload == {
        "format": "evidence-review/page-image",
        "version": 1,
        "revision_id": "REV-1",
        "page_number": 1,
        "source_hash": source_hash,
        "pdf_width": 100.0,
        "pdf_height": 200.0,
        "origin_x": 0.0,
        "origin_y": 0.0,
        "rotation": 0,
        "box_kind": "MEDIA_BOX",
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
    }
    before = (image.read_bytes(), image.stat().st_mtime_ns, metadata.stat().st_mtime_ns)

    cache_pdf_page_images(cache_root, source, "REV-1", source_hash)

    assert before == (image.read_bytes(), image.stat().st_mtime_ns, metadata.stat().st_mtime_ns)


def test_page_image_cache_reuses_verified_legacy_metadata_without_rewriting(tmp_path: Path) -> None:
    from evidence_review.parsing.page_image_cache import cache_pdf_page_images

    source = write_pdf_fixture(tmp_path / "legacy.pdf", page_sizes=((100, 200),))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "page-images"
    cache_pdf_page_images(cache_root, source, "REV-LEGACY", source_hash)
    metadata_path = cache_root / "REV-LEGACY" / "page-0001.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["format"] = "ansim/page-image"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    before = metadata_path.read_bytes()

    cache_pdf_page_images(cache_root, source, "REV-LEGACY", source_hash)

    assert metadata_path.read_bytes() == before


def test_page_image_cache_renders_cropbox_and_rotation_in_process(tmp_path: Path) -> None:
    from evidence_review.parsing.page_image_cache import cache_pdf_page_images

    source = write_pdf_fixture(
        tmp_path / "rotated.pdf",
        page_sizes=((100, 200),),
        crop_boxes={1: (10, 20, 90, 180)},
        rotations={1: 90},
    )
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "page-images"

    cache_pdf_page_images(cache_root, source, "REV-CROP", source_hash)

    image = cache_root / "REV-CROP" / "page-0001.png"
    metadata = json.loads(
        (cache_root / "REV-CROP" / "page-0001.json").read_text(encoding="utf-8")
    )
    assert metadata["pdf_width"] == 80.0
    assert metadata["pdf_height"] == 160.0
    assert metadata["origin_x"] == 10.0
    assert metadata["origin_y"] == 20.0
    assert metadata["rotation"] == 90
    assert metadata["box_kind"] == "CROP_BOX"
    with Image.open(image) as rendered:
        assert rendered.size == (320, 160)
        assert rendered.mode in {"RGB", "RGBA"}


def test_page_image_cache_rejects_tampered_existing_artifact(tmp_path: Path) -> None:
    from evidence_review.parsing.page_image_cache import cache_pdf_page_images

    source = write_pdf_fixture(tmp_path / "source.pdf", page_sizes=((100, 200),))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "page-images"
    cache_pdf_page_images(cache_root, source, "REV-1", source_hash)
    (cache_root / "REV-1" / "page-0001.png").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="page image cache"):
        cache_pdf_page_images(cache_root, source, "REV-1", source_hash)
