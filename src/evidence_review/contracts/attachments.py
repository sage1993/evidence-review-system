"""Immutable attachment metadata contracts for review runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from evidence_review.contracts.identifiers import validate_identifier
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
    case_id: str | None = None


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
    return path


def case_visual_source_relative_parts(
    attachment: ImmutableAttachment,
) -> tuple[str, ...]:
    """Validate and return the authoritative workspace-relative visual source path."""
    if attachment.case_id is None:
        raise ValueError("case visual attachment identity requires case_id")
    case_id = validate_identifier(attachment.case_id, "case_id")
    attachment_id = validate_identifier(attachment.attachment_id, "attachment_id")
    parts = PurePosixPath(_safe_stored_path(attachment.stored_path)).parts
    expected_prefix = ("cases", case_id, "sources", "drawings")
    if (
        attachment.role not in {"CASE_DRAWING", "SUPPORTING_IMAGE"}
        or len(parts) != 5
        or parts[:4] != expected_prefix
        or PurePosixPath(parts[4]).stem != attachment_id
        or not PurePosixPath(parts[4]).suffix
    ):
        raise ValueError("case visual source identity is invalid")
    return tuple(parts)


def decode_immutable_attachment(value: object) -> ImmutableAttachment:
    """Decode immutable attachment metadata and reject mutable source paths."""
    payload = expect_mapping(value, "immutable_attachment")
    allowed = {
        "case_id",
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
    case_id_value = payload.get("case_id")
    case_id = (
        None
        if case_id_value is None
        else validate_identifier(expect_string(case_id_value, "case_id"), "case_id")
    )
    attachment = ImmutableAttachment(
        attachment_id=expect_string(payload.get("attachment_id"), "attachment_id"),
        original_name=expect_string(payload.get("original_name"), "original_name"),
        stored_path=_safe_stored_path(payload.get("stored_path")),
        sha256=expect_sha256(payload.get("sha256"), "sha256"),
        byte_size=byte_size,
        mime=expect_string(payload.get("mime"), "mime"),
        role=expect_literal(payload.get("role"), "role", _ATTACHMENT_ROLES),
        case_id=case_id,
    )
    if case_id is None:
        parsed = PurePosixPath(attachment.stored_path)
        if parsed.parts[:2] != ("inputs", "original") or len(parsed.parts) < 3:
            raise ValueError("stored_path must be under inputs/original/")
    else:
        case_visual_source_relative_parts(attachment)
    return attachment


def immutable_attachment_document(attachment: ImmutableAttachment) -> dict[str, object]:
    """Return the explicit canonical attachment document."""
    document: dict[str, object] = {
        "attachment_id": attachment.attachment_id,
        "original_name": attachment.original_name,
        "stored_path": attachment.stored_path,
        "sha256": attachment.sha256,
        "byte_size": attachment.byte_size,
        "mime": attachment.mime,
        "role": attachment.role,
    }
    if attachment.case_id is not None:
        document["case_id"] = attachment.case_id
    return document
