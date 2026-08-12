from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.helpers.pdf_fixtures import write_pdf_fixture


def test_page_image_cache_writes_and_reuses_verified_pngs(tmp_path: Path) -> None:
    from ansim_review.parsing.page_image_cache import cache_pdf_page_images

    source = write_pdf_fixture(tmp_path / "source.pdf", page_sizes=((100, 200), (300, 400)))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "page-images"

    cache_pdf_page_images(cache_root, source, "REV-1", source_hash)

    image = cache_root / "REV-1" / "page-0001.png"
    metadata = cache_root / "REV-1" / "page-0001.json"
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert payload == {
        "format": "ansim/page-image",
        "version": 1,
        "revision_id": "REV-1",
        "page_number": 1,
        "source_hash": source_hash,
        "pdf_width": 100.0,
        "pdf_height": 200.0,
        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
    }
    before = (image.read_bytes(), image.stat().st_mtime_ns, metadata.stat().st_mtime_ns)

    cache_pdf_page_images(cache_root, source, "REV-1", source_hash)

    assert before == (image.read_bytes(), image.stat().st_mtime_ns, metadata.stat().st_mtime_ns)


def test_page_image_cache_rejects_tampered_existing_artifact(tmp_path: Path) -> None:
    from ansim_review.parsing.page_image_cache import cache_pdf_page_images

    source = write_pdf_fixture(tmp_path / "source.pdf", page_sizes=((100, 200),))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cache_root = tmp_path / "page-images"
    cache_pdf_page_images(cache_root, source, "REV-1", source_hash)
    (cache_root / "REV-1" / "page-0001.png").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="page image cache"):
        cache_pdf_page_images(cache_root, source, "REV-1", source_hash)
