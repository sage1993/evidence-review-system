"""Verification boundary for cached Review Workspace page images."""
from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from evidence_review.contracts.legacy_formats import LEGACY_PAGE_IMAGE_FORMAT
from evidence_review.review_packet.html_renderer import _mapping, _page_assets, _sequence

_PAGE_IMAGE_FORMAT = "evidence-review/page-image"
_REPARSE_POINT_ATTRIBUTE = 0x400


@dataclass(frozen=True, slots=True)
class VerifiedPageImage:
    revision_id: str
    page_number: int
    source_hash: str
    image_path: Path
    image_sha256: str
    image_bytes: bytes
    pdf_width: float
    pdf_height: float
    origin_x: float
    origin_y: float
    rotation: int
    box_kind: str


def _regular_file(path: Path) -> Path:
    try:
        status = path.lstat()
    except OSError as error:
        raise FileNotFoundError(path) from error
    if (
        stat.S_ISLNK(status.st_mode)
        or not stat.S_ISREG(status.st_mode)
        or getattr(status, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    ):
        raise ValueError("page image path must be a regular file")
    return path.resolve(strict=True)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be finite")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return number


def read_verified_page_image(
    page_root: Path,
    revision_id: str,
    page_number: int,
    source_hash: str,
) -> VerifiedPageImage:
    """Read one cached page image only after exact metadata/hash validation."""
    if not revision_id or "/" in revision_id or "\\" in revision_id or revision_id in {".", ".."}:
        raise ValueError("invalid revision_id")
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise ValueError("invalid page_number")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(character not in "0123456789abcdef" for character in source_hash)
    ):
        raise ValueError("invalid source_hash")

    root = page_root.resolve(strict=True)
    directory = page_root / revision_id
    stem = f"page-{page_number:04d}"
    image_path = _regular_file(directory / f"{stem}.png")
    metadata_path = _regular_file(directory / f"{stem}.json")
    try:
        image_path.relative_to(root)
        metadata_path.relative_to(root)
    except ValueError as error:
        raise ValueError("page image escaped page root") from error

    document = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata = _mapping(document, "page image metadata")
    required = {
        "format",
        "version",
        "revision_id",
        "page_number",
        "source_hash",
        "pdf_width",
        "pdf_height",
        "image_sha256",
    }
    optional = {"origin_x", "origin_y", "rotation", "box_kind"}
    if not required.issubset(metadata) or set(metadata) - required - optional:
        raise ValueError("page image metadata fields are invalid")
    if metadata["format"] not in {_PAGE_IMAGE_FORMAT, LEGACY_PAGE_IMAGE_FORMAT}:
        raise ValueError("unsupported page image metadata")
    if metadata["version"] != 1:
        raise ValueError("unsupported page image metadata")
    if metadata["revision_id"] != revision_id or metadata["page_number"] != page_number:
        raise ValueError("page image identity mismatch")
    if metadata["source_hash"] != source_hash:
        raise ValueError("page image source hash mismatch")
    image_sha256 = metadata["image_sha256"]
    if (
        not isinstance(image_sha256, str)
        or len(image_sha256) != 64
        or any(character not in "0123456789abcdef" for character in image_sha256)
    ):
        raise ValueError("page image hash is invalid")
    image_bytes = image_path.read_bytes()
    if hashlib.sha256(image_bytes).hexdigest() != image_sha256:
        raise ValueError("page image hash mismatch")

    pdf_width = _number(metadata["pdf_width"], "pdf_width")
    pdf_height = _number(metadata["pdf_height"], "pdf_height")
    if pdf_width <= 0 or pdf_height <= 0:
        raise ValueError("page image dimensions must be positive")
    origin_x = _number(metadata.get("origin_x", 0.0), "origin_x")
    origin_y = _number(metadata.get("origin_y", 0.0), "origin_y")
    rotation = metadata.get("rotation", 0)
    if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in {0, 90, 180, 270}:
        raise ValueError("page image rotation is invalid")
    box_kind = metadata.get("box_kind", "MEDIA_BOX")
    if box_kind not in {"CROP_BOX", "MEDIA_BOX"}:
        raise ValueError("page image box kind is invalid")

    return VerifiedPageImage(
        revision_id=revision_id,
        page_number=page_number,
        source_hash=source_hash,
        image_path=image_path,
        image_sha256=image_sha256,
        image_bytes=image_bytes,
        pdf_width=pdf_width,
        pdf_height=pdf_height,
        origin_x=origin_x,
        origin_y=origin_y,
        rotation=rotation,
        box_kind=box_kind,
    )


def verify_review_page_images(
    view_model: Mapping[str, object],
    page_image_root: Path,
) -> None:
    """Verify every cited page image and citation geometry without rendering HTML."""
    model = _mapping(view_model, "view_model")
    claims = _sequence(model.get("claims", []), "claims")
    _page_assets(claims, page_image_root)


__all__ = ["VerifiedPageImage", "read_verified_page_image", "verify_review_page_images"]
