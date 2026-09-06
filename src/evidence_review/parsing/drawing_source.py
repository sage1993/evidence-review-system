"""Safe, immutable intake for case-specific drawing sources."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from evidence_review.contracts.attachments import (
    AttachmentRole,
    ImmutableAttachment,
)
from evidence_review.filesystem_trust import (
    verified_regular_file,
    verified_regular_file_below,
)
from evidence_review.parsing.drawing_case import (
    CaseManifestEntry,
    validate_artifact_id,
)
from evidence_review.parsing.source_manifest import sha256_file

_CHUNK_SIZE = 1024 * 1024
_MIME_EXTENSIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "application/pdf": (".pdf", (".pdf",)),
    "image/png": (".png", (".png",)),
    "image/tiff": (".tif", (".tif", ".tiff")),
    "image/jpeg": (".jpg", (".jpg", ".jpeg")),
}


@dataclass(frozen=True, slots=True)
class DrawingIntakePolicy:
    """Versioned resource limits applied before drawing parsing."""

    policy_id: str = "DRAWING-INTAKE-1"
    max_file_bytes: int = 262_144_000
    max_pdf_pages: int = 200
    max_image_pixels: int = 150_000_000
    max_case_image_pixels: int = 500_000_000

    def __post_init__(self) -> None:
        validate_artifact_id(self.policy_id, "policy_id")
        for field, value in (
            ("max_file_bytes", self.max_file_bytes),
            ("max_pdf_pages", self.max_pdf_pages),
            ("max_image_pixels", self.max_image_pixels),
            ("max_case_image_pixels", self.max_case_image_pixels),
        ):
            if isinstance(value, bool) or value < 1:
                raise ValueError(f"{field} must be positive")


def sniff_drawing_mime(header: bytes) -> tuple[str, str]:
    """Return canonical MIME and extension for one supported file signature."""
    if header.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff", ".tif"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    raise ValueError("unsupported drawing signature")


def validate_source_path(path: Path) -> None:
    """Reject directories, links, and Windows reparse points before opening."""
    verified_regular_file(path, field="source")


def _extension_matches(source_path: Path, mime: str) -> None:
    suffix = source_path.suffix.lower()
    aliases = _MIME_EXTENSIONS[mime][1]
    if suffix not in aliases:
        raise ValueError("source extension does not match MIME")


def _logical_stored_path(attachment_id: str, extension: str) -> str:
    return f"inputs/original/{attachment_id}{extension}"


def _physical_relative_path(attachment: ImmutableAttachment) -> str:
    parsed = PurePosixPath(attachment.stored_path)
    expected_prefix = ("inputs", "original")
    if parsed.parts[:2] != expected_prefix or len(parsed.parts) != 3:
        raise ValueError("attachment stored_path is not a canonical original path")
    filename = parsed.parts[2]
    canonical_extension = _MIME_EXTENSIONS.get(attachment.mime, ("", ()))[0]
    expected_filename = f"{attachment.attachment_id}{canonical_extension}"
    if not canonical_extension or filename != expected_filename:
        raise ValueError("attachment stored_path does not match attachment metadata")
    return f"sources/drawings/{filename}"


def drawing_source_manifest_entry(
    attachment: ImmutableAttachment,
) -> CaseManifestEntry:
    """Return the case-manifest index entry for one immutable source."""
    return CaseManifestEntry(
        artifact_id=attachment.attachment_id,
        relative_path=_physical_relative_path(attachment),
        sha256=attachment.sha256,
    )


def _copy_source_to_temporary(
    source_path: Path,
    temporary_path: Path,
    max_file_bytes: int,
) -> tuple[int, str]:
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    digest = hashlib.sha256()
    byte_size = 0
    try:
        with source_path.open("rb") as source, os.fdopen(descriptor, "wb") as target:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                byte_size += len(chunk)
                if byte_size > max_file_bytes:
                    raise ValueError("FILE_SIZE_LIMIT_EXCEEDED")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return byte_size, digest.hexdigest()


def _publish_create_only(temporary_path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with temporary_path.open("rb") as source, os.fdopen(descriptor, "wb") as target:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def ingest_drawing_source(
    source_path: Path,
    case_dir: Path,
    attachment_id: str,
    role: AttachmentRole,
    policy: DrawingIntakePolicy,
) -> ImmutableAttachment:
    """Copy one supported source into immutable case storage and hash copied bytes."""
    validate_artifact_id(attachment_id, "attachment_id")
    if role == "REFERENCE_DOCUMENT":
        raise ValueError("reference documents must use the reference ingestion pipeline")
    validate_source_path(source_path)

    temporary_path = case_dir / ".intake" / f"{attachment_id}.tmp"
    byte_size, source_hash = _copy_source_to_temporary(
        source_path,
        temporary_path,
        policy.max_file_bytes,
    )
    try:
        with temporary_path.open("rb") as stream:
            header = stream.read(16)
        mime, canonical_extension = sniff_drawing_mime(header)
        _extension_matches(source_path, mime)
        destination = (
            case_dir
            / "sources"
            / "drawings"
            / f"{attachment_id}{canonical_extension}"
        )
        _publish_create_only(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    return ImmutableAttachment(
        attachment_id=attachment_id,
        original_name=source_path.name,
        stored_path=_logical_stored_path(attachment_id, canonical_extension),
        sha256=source_hash,
        byte_size=byte_size,
        mime=mime,
        role=role,
    )


def verify_immutable_attachment(
    case_dir: Path,
    attachment: ImmutableAttachment,
) -> tuple[str, ...]:
    """Return deterministic integrity errors for one case-local source."""
    try:
        path = verified_regular_file_below(
            case_dir,
            tuple(_physical_relative_path(attachment).split("/")),
            field="immutable drawing source",
        )
    except (FileNotFoundError, OSError, ValueError):
        return ("SOURCE_MISSING",)
    errors: list[str] = []
    if path.stat().st_size != attachment.byte_size:
        errors.append("SOURCE_SIZE_MISMATCH")
    if sha256_file(path) != attachment.sha256:
        errors.append("SOURCE_HASH_MISMATCH")
    return tuple(errors)
