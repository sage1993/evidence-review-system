"""Prepare deterministic page-image assets for case-specific visual analysis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.drawing import CoordinateSystem
from evidence_review.parsing.page_image_cache import cache_pdf_page_images
from evidence_review.parsing.source_manifest import sha256_file

_VISUAL_PAGE_FORMAT = "evidence-review/case-visual-page"
_MAX_IMAGE_PIXELS = 150_000_000
_CASE_PDF_RENDER_SCALE = 4.0
_CASE_PDF_CACHE_DIR = "case-page-images-hq-v1"


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


def _source_path(workspace: Path, attachment: ImmutableAttachment) -> Path:
    filename = Path(attachment.stored_path).name
    matches = sorted(workspace.glob(f"cases/*/sources/drawings/{filename}"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"case visual source path is not uniquely resolvable: {attachment.attachment_id}"
        )
    source = matches[0]
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


def prepare_visual_page_assets(
    workspace: Path,
    attachments: tuple[ImmutableAttachment, ...],
) -> tuple[VisualPageAsset, ...]:
    """Render/canonicalize every visual attachment without reference parsing."""
    assets: list[VisualPageAsset] = []
    for attachment in attachments:
        source = _source_path(workspace, attachment)
        if attachment.mime == "application/pdf":
            assets.extend(_pdf_assets(workspace, attachment, source))
        elif attachment.mime in {"image/png", "image/jpeg", "image/tiff"}:
            assets.append(_normalized_image_asset(workspace, attachment, source))
        else:
            raise ValueError(f"unsupported case visual MIME: {attachment.mime}")
    assets.sort(key=lambda item: (item.attachment_id, item.page))
    return tuple(assets)


__all__ = ["VisualPageAsset", "prepare_visual_page_assets"]
