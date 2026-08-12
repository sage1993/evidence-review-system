"""Create-only verified PDF page images for the Review Workspace."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from ansim_review.canonical_json import dump_bytes
from ansim_review.parsing.pdf_page_geometry import PdfPageGeometry, read_pdf_page_geometries
from ansim_review.parsing.source_manifest import sha256_file


@dataclass(frozen=True, slots=True)
class PageImageSource:
    """One immutable PDF revision whose pages must be cached."""

    source_path: Path
    revision_id: str
    source_hash: str


def _metadata(source: PageImageSource, page: PdfPageGeometry, image: bytes) -> dict[str, object]:
    return {
        "format": "ansim/page-image",
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


def _paths(root: Path, revision_id: str, page_number: int) -> tuple[Path, Path]:
    stem = f"page-{page_number:04d}"
    directory = root / revision_id
    return directory / f"{stem}.png", directory / f"{stem}.json"


def _load_existing(
    image_path: Path,
    metadata_path: Path,
    source: PageImageSource,
    page: PdfPageGeometry,
) -> bool:
    if not image_path.exists() and not metadata_path.exists():
        return False
    if not image_path.is_file() or not metadata_path.is_file():
        raise ValueError("page image cache has incomplete artifacts")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("page image cache metadata is invalid") from error
    image = image_path.read_bytes()
    if metadata != _metadata(source, page, image):
        raise ValueError("page image cache binding does not match source page")
    return True


def _render_page(source: Path, page_number: int, destination: Path) -> bytes:
    prefix = destination.with_suffix("")
    command = (
        "pdftoppm",
        "-png",
        "-cropbox",
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        "-singlefile",
        str(source),
        str(prefix),
    )
    try:
        completed = subprocess.run(command, check=False, capture_output=True)
    except OSError as error:
        raise ValueError("PAGE_RENDERER_UNAVAILABLE: pdftoppm") from error
    if completed.returncode != 0 or not destination.is_file():
        raise ValueError(f"PAGE_RENDER_FAILED: page {page_number}")
    return destination.read_bytes()


def _stage_source(
    root: Path,
    source: PageImageSource,
    pages: tuple[PdfPageGeometry, ...],
) -> list[tuple[Path, bytes]]:
    if sha256_file(source.source_path) != source.source_hash:
        raise ValueError("page image source hash changed")
    missing: list[PdfPageGeometry] = []
    for page in pages:
        image_path, metadata_path = _paths(root, source.revision_id, page.page_number)
        if not _load_existing(image_path, metadata_path, source, page):
            missing.append(page)
    if not missing:
        return []
    staged: list[tuple[Path, bytes]] = []
    with TemporaryDirectory(prefix=".page-image-cache-") as temporary:
        temporary_root = Path(temporary)
        for page in missing:
            temporary_image = temporary_root / f"page-{page.page_number:04d}.png"
            image = _render_page(source.source_path, page.page_number, temporary_image)
            destination_image, destination_metadata = _paths(
                root,
                source.revision_id,
                page.page_number,
            )
            staged.append((destination_image, image))
            staged.append((destination_metadata, dump_bytes(_metadata(source, page, image))))
    if sha256_file(source.source_path) != source.source_hash:
        raise ValueError("page image source hash changed during rendering")
    return staged


def cache_page_images(root: Path, sources: tuple[PageImageSource, ...]) -> tuple[Path, ...]:
    """Render every missing page after all existing caches have been verified."""
    staged: list[tuple[Path, bytes]] = []
    for source in sources:
        staged.extend(_stage_source(root, source, read_pdf_page_geometries(source.source_path)))
    published: list[Path] = []
    try:
        for path, data in staged:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as error:
                raise ValueError("page image cache changed during publication") from error
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            published.append(path)
    except Exception:
        rollback_page_image_cache(published)
        raise
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
) -> None:
    """Convenience boundary for one immutable source revision."""
    cache_page_images(
        root,
        (PageImageSource(source_path, revision_id, source_hash),),
    )
