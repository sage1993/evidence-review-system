"""Immutable attachment metadata contracts for review runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sha256,
    expect_string,
    reject_unknown,
)

AttachmentRole = Literal[
    "REFERENCE_DOCUMENT",
    "CASE_DRAWING",
    "CASE_TABLE",
    "SUPPORTING_IMAGE",
]
_ATTACHMENT_ROLES: tuple[AttachmentRole, ...] = (
    "REFERENCE_DOCUMENT",
    "CASE_DRAWING",
    "CASE_TABLE",
    "SUPPORTING_IMAGE",
)


@dataclass(frozen=True, slots=True)
class ImmutableAttachment:
    """One copied attachment whose bytes are fixed before processing."""

    attachment_id: str
    original_name: str
    stored_path: str
    sha256: str
    byte_size: int
    mime: str
    role: AttachmentRole


def _safe_stored_path(value: object) -> str:
    path = expect_string(value, "stored_path")
    parsed = PurePosixPath(path)
    first = parsed.parts[0] if parsed.parts else ""
    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or not parsed.parts
        or ":" in first
        or "\\" in path
    ):
        raise ValueError("stored_path must be a safe relative path")
    if parsed.parts[:2] != ("inputs", "original"):
        raise ValueError("stored_path must be under inputs/original/")
    if len(parsed.parts) < 3:
        raise ValueError("stored_path must identify a file under inputs/original/")
    return path


def decode_immutable_attachment(value: object) -> ImmutableAttachment:
    """Decode immutable attachment metadata and reject mutable source paths."""
    payload = expect_mapping(value, "immutable_attachment")
    allowed = {
        "attachment_id",
        "original_name",
        "stored_path",
        "sha256",
        "byte_size",
        "mime",
        "role",
    }
    reject_unknown(payload, allowed, "immutable_attachment")
    byte_size = expect_int(payload.get("byte_size"), "byte_size")
    if byte_size < 1:
        raise ValueError("byte_size must be positive")
    return ImmutableAttachment(
        attachment_id=expect_string(payload.get("attachment_id"), "attachment_id"),
        original_name=expect_string(payload.get("original_name"), "original_name"),
        stored_path=_safe_stored_path(payload.get("stored_path")),
        sha256=expect_sha256(payload.get("sha256"), "sha256"),
        byte_size=byte_size,
        mime=expect_string(payload.get("mime"), "mime"),
        role=expect_literal(payload.get("role"), "role", _ATTACHMENT_ROLES),
    )


def immutable_attachment_document(attachment: ImmutableAttachment) -> dict[str, object]:
    """Return the explicit canonical attachment document."""
    return {
        "attachment_id": attachment.attachment_id,
        "original_name": attachment.original_name,
        "stored_path": attachment.stored_path,
        "sha256": attachment.sha256,
        "byte_size": attachment.byte_size,
        "mime": attachment.mime,
        "role": attachment.role,
    }
