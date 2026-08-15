"""Deterministic review-request and attachment-role contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from evidence_review import canonical_json
from evidence_review.contracts.attachments import (
    AttachmentRole,
    ImmutableAttachment,
    decode_immutable_attachment,
    immutable_attachment_document,
)
from evidence_review.contracts.formats import REVIEW_REQUEST_FORMAT
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_string,
    reject_unknown,
    require_fields,
)

_ROLE_CONFIRMATIONS: tuple[Literal["USER_CONFIRMED"], ...] = (
    "USER_CONFIRMED",
)
_ATTACHMENT_ROLES: tuple[AttachmentRole, ...] = (
    "REFERENCE_DOCUMENT",
    "CASE_DRAWING",
    "CASE_TABLE",
    "SUPPORTING_IMAGE",
)


@dataclass(frozen=True, slots=True)
class RequestAttachment:
    """Immutable attachment metadata with a separately confirmed role."""

    attachment_id: str
    original_name: str
    stored_path: str
    sha256: str
    byte_size: int
    mime: str
    role: AttachmentRole | None
    role_confirmation: Literal["USER_CONFIRMED"] | None
    proposed_role: AttachmentRole | None


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """Deterministic request payload independent of run-time envelopes."""

    format: Literal["evidence-review/review-request"]
    version: Literal[1]
    case_id: str
    question: str
    attachments: tuple[RequestAttachment, ...]


def _optional_role(value: object, field: str) -> AttachmentRole | None:
    if value is None:
        return None
    return expect_literal(value, field, _ATTACHMENT_ROLES)


def _decode_request_attachment(value: object) -> RequestAttachment:
    payload = expect_mapping(value, "attachment")
    required = {
        "attachment_id",
        "original_name",
        "stored_path",
        "sha256",
        "byte_size",
        "mime",
        "role",
        "role_confirmation",
        "proposed_role",
    }
    require_fields(payload, required, "attachment")
    reject_unknown(payload, required, "attachment")

    role = _optional_role(payload.get("role"), "role")
    proposed_role = _optional_role(payload.get("proposed_role"), "proposed_role")
    confirmation_value = payload.get("role_confirmation")
    role_confirmation: Literal["USER_CONFIRMED"] | None
    if confirmation_value is None:
        role_confirmation = None
    else:
        role_confirmation = expect_literal(
            confirmation_value,
            "role_confirmation",
            _ROLE_CONFIRMATIONS,
        )

    if role is None and role_confirmation is not None:
        raise ValueError("role_confirmation requires a confirmed role")
    if role is not None and role_confirmation != "USER_CONFIRMED":
        raise ValueError("role requires USER_CONFIRMED role_confirmation")

    validation_role: AttachmentRole = role or proposed_role or "SUPPORTING_IMAGE"
    validated = decode_immutable_attachment(
        {
            "attachment_id": payload.get("attachment_id"),
            "original_name": payload.get("original_name"),
            "stored_path": payload.get("stored_path"),
            "sha256": payload.get("sha256"),
            "byte_size": payload.get("byte_size"),
            "mime": payload.get("mime"),
            "role": validation_role,
        }
    )
    attachment_id = validate_identifier(validated.attachment_id, "attachment_id")
    return RequestAttachment(
        attachment_id=attachment_id,
        original_name=validated.original_name,
        stored_path=validated.stored_path,
        sha256=validated.sha256,
        byte_size=validated.byte_size,
        mime=validated.mime,
        role=role,
        role_confirmation=role_confirmation,
        proposed_role=proposed_role,
    )


def decode_review_request(value: object) -> ReviewRequest:
    """Decode one strict deterministic review request."""
    payload = expect_mapping(value, "review_request")
    required = {"format", "version", "case_id", "question", "attachments"}
    require_fields(payload, required, "review_request")
    reject_unknown(payload, required, "review_request")
    expect_literal(payload.get("format"), "format", (REVIEW_REQUEST_FORMAT,))
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")

    attachments = tuple(
        _decode_request_attachment(item)
        for item in expect_sequence(payload.get("attachments"), "attachments")
    )
    attachment_ids = tuple(item.attachment_id for item in attachments)
    stored_paths = tuple(item.stored_path for item in attachments)
    if len(attachment_ids) != len(set(attachment_ids)):
        raise ValueError("attachment_id values must be unique")
    if len(stored_paths) != len(set(stored_paths)):
        raise ValueError("stored_path values must be unique")

    return ReviewRequest(
        format=REVIEW_REQUEST_FORMAT,
        version=1,
        case_id=validate_identifier(payload.get("case_id"), "case_id"),
        question=expect_string(payload.get("question"), "question"),
        attachments=tuple(sorted(attachments, key=lambda item: item.attachment_id)),
    )


def _attachment_document(attachment: RequestAttachment) -> dict[str, object]:
    return {
        "attachment_id": attachment.attachment_id,
        "original_name": attachment.original_name,
        "stored_path": attachment.stored_path,
        "sha256": attachment.sha256,
        "byte_size": attachment.byte_size,
        "mime": attachment.mime,
        "role": attachment.role,
        "role_confirmation": attachment.role_confirmation,
        "proposed_role": attachment.proposed_role,
    }


def review_request_document(request: ReviewRequest) -> dict[str, object]:
    """Return the canonical request document without operational fields."""
    return {
        "format": REVIEW_REQUEST_FORMAT,
        "version": request.version,
        "case_id": request.case_id,
        "question": request.question,
        "attachments": [
            _attachment_document(attachment) for attachment in request.attachments
        ],
    }


def review_request_bytes(request: ReviewRequest) -> bytes:
    """Return canonical UTF-8 bytes with one trailing newline."""
    return canonical_json.dump_bytes(review_request_document(request)) + b"\n"


def review_request_sha256(request: ReviewRequest) -> str:
    """Hash only the deterministic request payload."""
    return hashlib.sha256(review_request_bytes(request)).hexdigest()


def requires_role_confirmation(request: ReviewRequest) -> bool:
    """Return whether any attachment still lacks a user-confirmed role."""
    return any(attachment.role is None for attachment in request.attachments)


def confirmed_attachments(request: ReviewRequest) -> tuple[ImmutableAttachment, ...]:
    """Return only user-confirmed attachments using the existing M0 contract."""
    confirmed: list[ImmutableAttachment] = []
    for attachment in request.attachments:
        if attachment.role is None:
            continue
        document = _attachment_document(attachment)
        immutable_document = {
            key: document[key]
            for key in (
                "attachment_id",
                "original_name",
                "stored_path",
                "sha256",
                "byte_size",
                "mime",
                "role",
            )
        }
        confirmed.append(decode_immutable_attachment(immutable_document))
    return tuple(confirmed)


def confirmed_attachment_documents(
    request: ReviewRequest,
) -> tuple[dict[str, object], ...]:
    """Return canonical M0 documents for confirmed attachments."""
    return tuple(
        immutable_attachment_document(attachment)
        for attachment in confirmed_attachments(request)
    )
