"""Prepare deterministic page-image assets for case-specific visual analysis."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import mkdtemp
from typing import cast

from PIL import Image, ImageOps

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.attachments import (
    ImmutableAttachment,
    case_visual_source_relative_parts,
)
from evidence_review.contracts.drawing import CoordinateSystem
from evidence_review.filesystem_trust import verified_regular_file_below
from evidence_review.parsing.page_image_cache import cache_pdf_page_images
from evidence_review.parsing.source_manifest import sha256_file

_VISUAL_PAGE_FORMAT = "evidence-review/case-visual-page"
_VISUAL_TILE_FORMAT = "evidence-review/case-visual-tile-manifest"
_MAX_IMAGE_PIXELS = 150_000_000
_CASE_PDF_RENDER_SCALE = 4.0
_CASE_PDF_CACHE_DIR = "case-page-images-hq-v1"
_TILE_CACHE_DIR = "case-page-tiles-v1"
_TILE_SIZE = 2048
_TILE_TRIGGER_PIXELS = 16_000_000
_TILE_TRIGGER_DIMENSION = 4096


@dataclass(frozen=True, slots=True)
class VisualPageAsset:
    """One verified raster page presented to the external visual analyzer."""

    attachment_id: str
    source_sha256: str
    page: int
    width: float
    height: float
    coordinate_system: CoordinateSystem
    image_path: Path
    image_sha256: str


@dataclass(frozen=True, slots=True)
class VisualPageTile:
    """One hash-bound raster tile for lazy browser decode."""

    path: Path
    x: int
    y: int
    width: int
    height: int
    image_sha256: str


def _source_path(workspace: Path, attachment: ImmutableAttachment) -> Path:
    source = verified_regular_file_below(
        workspace,
        case_visual_source_relative_parts(attachment),
        field="case visual source",
    )
    if source.stat().st_size != attachment.byte_size:
        raise ValueError("case visual source size mismatch")
    if sha256_file(source) != attachment.sha256:
        raise ValueError("case visual source hash mismatch")
    return source


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
    if width < 1 or height < 1 or width * height > _MAX_IMAGE_PIXELS:
        raise ValueError("CASE_VISUAL_IMAGE_SIZE_INVALID")
    return width, height


def _pdf_assets(
    workspace: Path,
    attachment: ImmutableAttachment,
    source: Path,
) -> tuple[VisualPageAsset, ...]:
    # CASE_DRAWING PDFs need materially more raster detail than the normal reference
    # document viewer because reviewers zoom into dimensions, notes, and linework.
    # Keep this cache isolated so reference/legal-document rendering remains unchanged.
    root = workspace / _CASE_PDF_CACHE_DIR
    cache_pdf_page_images(
        root,
        source,
        attachment.attachment_id,
        attachment.sha256,
        render_scale=_CASE_PDF_RENDER_SCALE,
    )
    directory = root / attachment.attachment_id
    images = sorted(directory.glob("page-*.png"))
    if not images:
        raise ValueError("VISUAL_SOURCE_RENDER_FAILED")
    assets: list[VisualPageAsset] = []
    for image_path in images:
        try:
            page = int(image_path.stem.split("-")[-1])
        except ValueError as error:
            raise ValueError("case visual page filename is invalid") from error
        width, height = _image_size(image_path)
        assets.append(
            VisualPageAsset(
                attachment_id=attachment.attachment_id,
                source_sha256=attachment.sha256,
                page=page,
                width=float(width),
                height=float(height),
                coordinate_system="IMAGE_TOP_LEFT_PIXELS",
                image_path=image_path,
                image_sha256=sha256_file(image_path),
            )
        )
    return tuple(assets)


def _image_metadata(
    attachment: ImmutableAttachment,
    *,
    width: int,
    height: int,
    image_sha256: str,
) -> dict[str, object]:
    return {
        "format": _VISUAL_PAGE_FORMAT,
        "version": 1,
        "attachment_id": attachment.attachment_id,
        "source_sha256": attachment.sha256,
        "page": 1,
        "width": width,
        "height": height,
        "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
        "image_sha256": image_sha256,
    }


def _normalized_image_asset(
    workspace: Path,
    attachment: ImmutableAttachment,
    source: Path,
) -> VisualPageAsset:
    directory = workspace / "case-page-images" / attachment.attachment_id
    image_path = directory / "page-0001.png"
    metadata_path = directory / "page-0001.json"
    if image_path.exists() or metadata_path.exists():
        if not image_path.is_file() or not metadata_path.is_file():
            raise ValueError("case visual image cache is incomplete")
        width, height = _image_size(image_path)
        image_sha256 = sha256_file(image_path)
        expected = _image_metadata(
            attachment,
            width=width,
            height=height,
            image_sha256=image_sha256,
        )
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("case visual image metadata is invalid") from error
        if existing != expected:
            raise ValueError("case visual image cache binding mismatch")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source) as opened:
                normalized = ImageOps.exif_transpose(opened).convert("RGB")
                width, height = normalized.size
                if width < 1 or height < 1 or width * height > _MAX_IMAGE_PIXELS:
                    raise ValueError("CASE_VISUAL_IMAGE_SIZE_INVALID")
                output = BytesIO()
                normalized.save(output, format="PNG", compress_level=6)
            image_bytes = output.getvalue()
            image_sha256 = hashlib.sha256(image_bytes).hexdigest()
            with image_path.open("xb") as stream:
                stream.write(image_bytes)
            with metadata_path.open("xb") as stream:
                stream.write(
                    dump_bytes(
                        _image_metadata(
                            attachment,
                            width=width,
                            height=height,
                            image_sha256=image_sha256,
                        )
                    )
                )
        except Exception:
            image_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            try:
                directory.rmdir()
            except OSError:
                pass
            raise
    return VisualPageAsset(
        attachment_id=attachment.attachment_id,
        source_sha256=attachment.sha256,
        page=1,
        width=float(width),
        height=float(height),
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=image_path,
        image_sha256=image_sha256,
    )


def _tile_directory(workspace: Path, page: VisualPageAsset) -> Path:
    return (
        workspace
        / _TILE_CACHE_DIR
        / page.attachment_id
        / f"page-{page.page:04d}"
    )


def _tile_required(page: VisualPageAsset) -> bool:
    width = int(page.width)
    height = int(page.height)
    return (
        width * height >= _TILE_TRIGGER_PIXELS
        and max(width, height) > _TILE_TRIGGER_DIMENSION
    )


def _tile_manifest_header(page: VisualPageAsset) -> dict[str, object]:
    return {
        "format": _VISUAL_TILE_FORMAT,
        "version": 1,
        "attachment_id": page.attachment_id,
        "source_sha256": page.source_sha256,
        "page": page.page,
        "page_width": int(page.width),
        "page_height": int(page.height),
        "page_image_sha256": page.image_sha256,
        "tile_size": _TILE_SIZE,
    }


def _record_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError("case visual tile record is invalid")
    return cast(Mapping[str, object], value)


def _record_int(record: Mapping[str, object], field: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("case visual tile geometry is invalid")
    return value


def _load_visual_page_tiles(
    directory: Path,
    page: VisualPageAsset,
) -> tuple[VisualPageTile, ...]:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("case visual tile cache is incomplete")
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("case visual tile manifest is invalid") from error
    if not isinstance(raw_manifest, Mapping):
        raise ValueError("case visual tile manifest is invalid")
    manifest = cast(Mapping[str, object], raw_manifest)
    expected = _tile_manifest_header(page)
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError("case visual tile cache binding mismatch")
    records = manifest.get("tiles")
    if not isinstance(records, list) or not records:
        raise ValueError("case visual tile manifest has no tiles")
    tiles: list[VisualPageTile] = []
    for raw_record in records:
        record = _record_mapping(raw_record)
        filename = record.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("case visual tile filename is invalid")
        tile_path = directory / filename
        if not tile_path.is_file():
            raise ValueError("case visual tile file is missing")
        expected_hash = record.get("image_sha256")
        if (
            not isinstance(expected_hash, str)
            or sha256_file(tile_path) != expected_hash
        ):
            raise ValueError("case visual tile hash mismatch")
        x = _record_int(record, "x")
        y = _record_int(record, "y")
        width = _record_int(record, "width")
        height = _record_int(record, "height")
        if x < 0 or y < 0 or width < 1 or height < 1:
            raise ValueError("case visual tile geometry is invalid")
        if x + width > int(page.width) or y + height > int(page.height):
            raise ValueError("case visual tile is outside page bounds")
        tiles.append(
            VisualPageTile(
                path=tile_path,
                x=x,
                y=y,
                width=width,
                height=height,
                image_sha256=expected_hash,
            )
        )
    tiles.sort(key=lambda item: (item.y, item.x))
    return tuple(tiles)


def load_visual_page_tiles(
    workspace: Path,
    page: VisualPageAsset,
) -> tuple[VisualPageTile, ...]:
    """Load and verify precomputed tiles without materializing cache state."""
    if not _tile_required(page):
        return ()
    directory = _tile_directory(workspace, page)
    if not directory.exists():
        raise FileNotFoundError(f"case visual tile cache is missing: {directory}")
    if not directory.is_dir():
        raise ValueError("case visual tile cache path is invalid")
    return _load_visual_page_tiles(directory, page)


def ensure_visual_page_tiles(
    workspace: Path,
    page: VisualPageAsset,
) -> tuple[VisualPageTile, ...]:
    """Create/reuse hash-bound 2048px tiles only for large visual pages."""
    if not _tile_required(page):
        return ()
    if sha256_file(page.image_path) != page.image_sha256:
        raise ValueError("case visual tile source hash mismatch")
    directory = _tile_directory(workspace, page)
    if directory.exists():
        return load_visual_page_tiles(workspace, page)

    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(mkdtemp(prefix=f".{directory.name}.tmp-", dir=parent))
    records: list[dict[str, object]] = []
    try:
        with Image.open(page.image_path) as opened:
            image = opened.convert("RGB")
            image_width, image_height = image.size
            if (image_width, image_height) != (int(page.width), int(page.height)):
                raise ValueError("case visual tile source dimensions mismatch")
            row = 0
            for y in range(0, image_height, _TILE_SIZE):
                column = 0
                for x in range(0, image_width, _TILE_SIZE):
                    right = min(image_width, x + _TILE_SIZE)
                    bottom = min(image_height, y + _TILE_SIZE)
                    crop = image.crop((x, y, right, bottom))
                    output = BytesIO()
                    crop.save(output, format="PNG", compress_level=6)
                    data = output.getvalue()
                    filename = f"tile-r{row:03d}-c{column:03d}.png"
                    tile_path = temporary / filename
                    with tile_path.open("xb") as stream:
                        stream.write(data)
                    records.append(
                        {
                            "filename": filename,
                            "x": x,
                            "y": y,
                            "width": right - x,
                            "height": bottom - y,
                            "image_sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
                    column += 1
                row += 1
        manifest = _tile_manifest_header(page)
        manifest["tiles"] = records
        with (temporary / "manifest.json").open("xb") as stream:
            stream.write(dump_bytes(manifest))
        try:
            os.rename(temporary, directory)
        except FileExistsError:
            shutil.rmtree(temporary, ignore_errors=True)
        return load_visual_page_tiles(workspace, page)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def prepare_visual_page_assets(
    workspace: Path,
    attachments: tuple[ImmutableAttachment, ...],
) -> tuple[VisualPageAsset, ...]:
    """Render/canonicalize every visual attachment without reference parsing."""
    assets: list[VisualPageAsset] = []
    identities: set[tuple[str, str]] = set()
    for attachment in attachments:
        if attachment.case_id is None:
            raise ValueError("case visual attachment identity requires case_id")
        identity = (attachment.case_id, attachment.attachment_id)
        if identity in identities:
            raise ValueError("case visual source binding is ambiguous")
        identities.add(identity)
        source = _source_path(workspace, attachment)
        if attachment.mime == "application/pdf":
            assets.extend(_pdf_assets(workspace, attachment, source))
        elif attachment.mime in {"image/png", "image/jpeg", "image/tiff"}:
            assets.append(_normalized_image_asset(workspace, attachment, source))
        else:
            raise ValueError(f"unsupported case visual MIME: {attachment.mime}")
    assets.sort(key=lambda item: (item.attachment_id, item.page))
    return tuple(assets)


__all__ = [
    "VisualPageAsset",
    "VisualPageTile",
    "ensure_visual_page_tiles",
    "load_visual_page_tiles",
    "prepare_visual_page_assets",
]
