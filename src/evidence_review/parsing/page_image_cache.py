"""Create-only verified PDF page images for the Review Workspace."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import BytesIO
from math import ceil, floor, isfinite
from pathlib import Path
from typing import Protocol

import pypdfium2 as pdfium  # type: ignore[import-untyped]

if sys.platform != "win32":
    import fcntl
else:
    from evidence_review.workflow.windows_lock import (
        acquire_exclusive_file_lock,
        release_file_lock,
    )

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.legacy_formats import LEGACY_PAGE_IMAGE_FORMAT
from evidence_review.parsing.pdf_page_geometry import PdfPageGeometry, read_pdf_page_geometries
from evidence_review.parsing.source_manifest import sha256_file
from evidence_review.runtime_filesystem import create_inherited_temp_directory

_RENDER_SCALE = 2.0
_PAGE_IMAGE_FORMAT = "evidence-review/page-image"


class _BitmapConverter(Protocol):
    def to_bitmap(self, pos_x: float, pos_y: float) -> tuple[int, int]: ...


@dataclass(frozen=True, slots=True)
class PageImageSource:
    """One immutable PDF revision whose pages must be cached."""

    source_path: Path
    revision_id: str
    source_hash: str
    metadata: Mapping[str, object] = field(default_factory=dict)


def _render_scale(value: float) -> float:
    scale = float(value)
    if not isfinite(scale) or scale <= 0:
        raise ValueError("page image render_scale must be a positive finite number")
    return scale


def _metadata(
    source: PageImageSource,
    page: PdfPageGeometry,
    image: bytes,
    *,
    render_scale: float,
) -> dict[str, object]:
    document: dict[str, object] = {
        "format": _PAGE_IMAGE_FORMAT,
        "version": 1,
        "revision_id": source.revision_id,
        "page_number": page.page_number,
        "source_hash": source.source_hash,
        "pdf_width": page.width,
        "pdf_height": page.height,
        "origin_x": page.origin_x,
        "origin_y": page.origin_y,
        "rotation": page.rotation,
        "box_kind": page.box_kind,
        "image_sha256": hashlib.sha256(image).hexdigest(),
    }
    if render_scale != _RENDER_SCALE:
        document["render_scale"] = render_scale
    for key, value in source.metadata.items():
        if key in document:
            raise ValueError("page image cache metadata field conflicts with core identity")
        document[key] = value
    return document


def _paths(root: Path, revision_id: str, page_number: int) -> tuple[Path, Path]:
    stem = f"page-{page_number:04d}"
    directory = root / revision_id
    return directory / f"{stem}.png", directory / f"{stem}.json"


@contextmanager
def _revision_lock(root: Path, revision_id: str) -> Iterator[None]:
    """Serialize cache creation for one immutable revision."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / f".{revision_id}.lock"
    with path.open("a+b") as stream:
        if sys.platform == "win32":
            acquire_exclusive_file_lock(stream)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                release_file_lock(stream)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _load_existing(
    image_path: Path,
    metadata_path: Path,
    source: PageImageSource,
    page: PdfPageGeometry,
    *,
    render_scale: float,
) -> bool:
    if not image_path.exists() and not metadata_path.exists():
        return False
    if not image_path.is_file() or not metadata_path.is_file():
        raise ValueError("page image cache has incomplete artifacts")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except PermissionError as error:
        raise ValueError("CACHE_NOT_READABLE: page image cache metadata") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("page image cache metadata is invalid") from error
    try:
        image = image_path.read_bytes()
    except PermissionError as error:
        raise ValueError("CACHE_NOT_READABLE: page image cache image") from error
    expected = _metadata(source, page, image, render_scale=render_scale)
    if metadata.get("format") == LEGACY_PAGE_IMAGE_FORMAT:
        expected["format"] = LEGACY_PAGE_IMAGE_FORMAT
    if metadata != expected:
        raise ValueError("page image cache binding does not match source page")
    return True


def _crop_bounds(
    converter: _BitmapConverter,
    page: PdfPageGeometry,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    """Map the selected PDF page box into rendered bitmap coordinates."""
    right = page.origin_x + page.width
    top = page.origin_y + page.height
    points = (
        converter.to_bitmap(page.origin_x, page.origin_y),
        converter.to_bitmap(page.origin_x, top),
        converter.to_bitmap(right, page.origin_y),
        converter.to_bitmap(right, top),
    )
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    left_px = max(0, floor(min(xs)))
    upper_px = max(0, floor(min(ys)))
    right_px = min(image_width, ceil(max(xs)))
    lower_px = min(image_height, ceil(max(ys)))
    if right_px <= left_px or lower_px <= upper_px:
        raise ValueError(f"PAGE_RENDER_GEOMETRY_INVALID: page {page.page_number}")
    return left_px, upper_px, right_px, lower_px


def _render_page(
    source: Path,
    page: PdfPageGeometry,
    destination: Path,
    *,
    render_scale: float,
) -> bytes:
    """Render one page in-process and crop it to the authoritative page geometry."""
    try:
        with pdfium.PdfDocument(source) as document:
            pdf_page = document[page.page_number - 1]
            try:
                bitmap = pdf_page.render(
                    scale=render_scale,
                    rev_byteorder=True,
                    prefer_bgrx=True,
                    maybe_alpha=True,
                )
                try:
                    image = bitmap.to_pil().copy()
                    bounds = _crop_bounds(
                        bitmap.get_posconv(pdf_page),
                        page,
                        image.width,
                        image.height,
                    )
                finally:
                    bitmap.close()
            finally:
                pdf_page.close()
        cropped = image.crop(bounds)
        if cropped.mode == "RGBX":
            cropped = cropped.convert("RGB")
        output = BytesIO()
        cropped.save(output, format="PNG", compress_level=6)
        data = output.getvalue()
        destination.write_bytes(data)
        return data
    except (OSError, IndexError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise ValueError(f"PAGE_RENDER_FAILED: page {page.page_number}") from error


def _verify_revision(
    root: Path,
    source: PageImageSource,
    pages: tuple[PdfPageGeometry, ...],
    *,
    render_scale: float,
) -> bool:
    if sha256_file(source.source_path) != source.source_hash:
        raise ValueError("page image source hash changed")
    for page in pages:
        image_path, metadata_path = _paths(root, source.revision_id, page.page_number)
        if not _load_existing(
            image_path,
            metadata_path,
            source,
            page,
            render_scale=render_scale,
        ):
            return False
    return True


def _write_durable(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _cache_source(
    root: Path,
    source: PageImageSource,
    *,
    render_scale: float,
) -> tuple[Path, ...]:
    pages = read_pdf_page_geometries(source.source_path)
    with _revision_lock(root, source.revision_id):
        if _verify_revision(root, source, pages, render_scale=render_scale):
            return ()
        destination = root / source.revision_id
        if destination.exists():
            raise ValueError("page image cache has incomplete artifacts")
        with create_inherited_temp_directory(
            root,
            prefix=f".{source.revision_id}.tmp-",
        ) as temporary_root:
            for page in pages:
                temporary_image = temporary_root / f"page-{page.page_number:04d}.png"
                image = _render_page(
                    source.source_path,
                    page,
                    temporary_image,
                    render_scale=render_scale,
                )
                _write_durable(
                    temporary_root / f"page-{page.page_number:04d}.json",
                    dump_bytes(
                        _metadata(
                            source,
                            page,
                            image,
                            render_scale=render_scale,
                        )
                    ),
                )
            if sha256_file(source.source_path) != source.source_hash:
                raise ValueError("page image source hash changed during rendering")
            os.rename(temporary_root, destination)
            if sys.platform != "win32":
                directory_descriptor = os.open(root, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            return tuple(path for path in destination.iterdir() if path.is_file())


def cache_page_images(
    root: Path,
    sources: tuple[PageImageSource, ...],
    *,
    render_scale: float = _RENDER_SCALE,
) -> tuple[Path, ...]:
    """Render every missing page after all existing caches have been verified."""
    scale = _render_scale(render_scale)
    published: list[Path] = []
    for source in sources:
        published.extend(_cache_source(root, source, render_scale=scale))
    return tuple(published)


def rollback_page_image_cache(paths: tuple[Path, ...] | list[Path]) -> None:
    """Remove only paths newly published by a failed ingestion transaction."""
    for path in reversed(paths):
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass


def cache_pdf_page_images(
    root: Path,
    source_path: Path,
    revision_id: str,
    source_hash: str,
    *,
    render_scale: float = _RENDER_SCALE,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Convenience boundary for one immutable source revision."""
    cache_page_images(
        root,
        (
            PageImageSource(
                source_path,
                revision_id,
                source_hash,
                metadata or {},
            ),
        ),
        render_scale=render_scale,
    )
