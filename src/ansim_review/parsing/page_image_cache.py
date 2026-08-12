"""Create-only verified PDF page images for the Review Workspace."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

if os.name != "nt":
    import fcntl
else:
    from ansim_review.workflow.windows_lock import (
        acquire_exclusive_file_lock,
        release_file_lock,
    )

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


@contextmanager
def _revision_lock(root: Path, revision_id: str) -> Iterator[None]:
    """Serialize cache creation for one immutable revision."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / f".{revision_id}.lock"
    with path.open("a+b") as stream:
        if os.name == "nt":
            acquire_exclusive_file_lock(stream)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                release_file_lock(stream)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


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


def _verify_revision(
    root: Path,
    source: PageImageSource,
    pages: tuple[PdfPageGeometry, ...],
) -> bool:
    if sha256_file(source.source_path) != source.source_hash:
        raise ValueError("page image source hash changed")
    for page in pages:
        image_path, metadata_path = _paths(root, source.revision_id, page.page_number)
        if not _load_existing(image_path, metadata_path, source, page):
            return False
    return True


def _write_durable(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _cache_source(root: Path, source: PageImageSource) -> tuple[Path, ...]:
    pages = read_pdf_page_geometries(source.source_path)
    with _revision_lock(root, source.revision_id):
        if _verify_revision(root, source, pages):
            return ()
        destination = root / source.revision_id
        if destination.exists():
            raise ValueError("page image cache has incomplete artifacts")
        temporary_root = Path(mkdtemp(prefix=f".{source.revision_id}.tmp-", dir=root))
        try:
            for page in pages:
                temporary_image = temporary_root / f"page-{page.page_number:04d}.png"
                image = _render_page(source.source_path, page.page_number, temporary_image)
                _write_durable(
                    temporary_root / f"page-{page.page_number:04d}.json",
                    dump_bytes(_metadata(source, page, image)),
                )
            if sha256_file(source.source_path) != source.source_hash:
                raise ValueError("page image source hash changed during rendering")
            os.rename(temporary_root, destination)
            if os.name != "nt":
                directory_descriptor = os.open(root, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
            return tuple(path for path in destination.iterdir() if path.is_file())
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise


def cache_page_images(root: Path, sources: tuple[PageImageSource, ...]) -> tuple[Path, ...]:
    """Render every missing page after all existing caches have been verified."""
    published: list[Path] = []
    try:
        for source in sources:
            published.extend(_cache_source(root, source))
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
