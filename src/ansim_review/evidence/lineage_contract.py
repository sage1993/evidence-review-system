"""Strict contract for explicit legacy-to-canonical document lineage mappings."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from ansim_review.contracts.formats import LEGACY_LINEAGE_MANIFEST_FORMAT
from ansim_review.contracts.identifiers import validate_identifier

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_KEYS = {
    "format",
    "version",
    "source_database_sha256",
    "reviewer_id",
    "reviewed_at",
    "mappings",
}
_MAPPING_KEYS = {
    "legacy_document_id",
    "canonical_document_id",
    "source_sha256",
    "reason",
    "revision_mappings",
}
_REVISION_KEYS = {"legacy_revision_id", "canonical_revision_id"}


@dataclass(frozen=True, slots=True)
class RevisionMapping:
    """One explicit legacy revision to canonical revision mapping."""

    legacy_revision_id: str
    canonical_revision_id: str


@dataclass(frozen=True, slots=True)
class DocumentLineageMapping:
    """One reviewed legacy document alias binding."""

    legacy_document_id: str
    canonical_document_id: str
    source_sha256: str
    reason: str
    revision_mappings: tuple[RevisionMapping, ...]


@dataclass(frozen=True, slots=True)
class LegacyLineageManifest:
    """Human-reviewed authority for one copy-on-write lineage migration."""

    source_database_sha256: str
    reviewer_id: str
    reviewed_at: datetime
    mappings: tuple[DocumentLineageMapping, ...]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field: str,
) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise ValueError(f"{field} contains unknown fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{field} is missing fields: {', '.join(missing)}")


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field} must not contain leading or trailing whitespace")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _reviewed_at(value: object) -> datetime:
    text = _nonempty_string(value, "reviewed_at")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError("reviewed_at must be an ISO 8601 timestamp") from error
    if parsed.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone offset")
    return parsed


def _decode_revision(value: object, field: str) -> RevisionMapping:
    payload = _mapping(value, field)
    _require_exact_keys(payload, _REVISION_KEYS, field)
    legacy_revision_id = validate_identifier(
        payload.get("legacy_revision_id"),
        f"{field}.legacy_revision_id",
    )
    canonical_revision_id = validate_identifier(
        payload.get("canonical_revision_id"),
        f"{field}.canonical_revision_id",
    )
    if legacy_revision_id == canonical_revision_id:
        raise ValueError(f"{field} revision IDs must differ")
    return RevisionMapping(
        legacy_revision_id=legacy_revision_id,
        canonical_revision_id=canonical_revision_id,
    )


def _decode_document_mapping(
    value: object,
    field: str,
) -> DocumentLineageMapping:
    payload = _mapping(value, field)
    _require_exact_keys(payload, _MAPPING_KEYS, field)
    legacy_document_id = validate_identifier(
        payload.get("legacy_document_id"),
        f"{field}.legacy_document_id",
    )
    canonical_document_id = validate_identifier(
        payload.get("canonical_document_id"),
        f"{field}.canonical_document_id",
    )
    if legacy_document_id == canonical_document_id:
        raise ValueError(f"{field} legacy and canonical document IDs must differ")
    revisions_payload = _sequence(
        payload.get("revision_mappings"),
        f"{field}.revision_mappings",
    )
    if not revisions_payload:
        raise ValueError(f"{field}.revision_mappings must not be empty")
    revisions = tuple(
        sorted(
            (
                _decode_revision(item, f"{field}.revision_mappings[{index}]")
                for index, item in enumerate(revisions_payload)
            ),
            key=lambda item: item.legacy_revision_id,
        )
    )
    legacy_ids = [item.legacy_revision_id for item in revisions]
    canonical_ids = [item.canonical_revision_id for item in revisions]
    if len(legacy_ids) != len(set(legacy_ids)):
        raise ValueError(f"{field} contains duplicate legacy_revision_id")
    if len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError(f"{field} contains duplicate canonical_revision_id")
    return DocumentLineageMapping(
        legacy_document_id=legacy_document_id,
        canonical_document_id=canonical_document_id,
        source_sha256=_sha256(payload.get("source_sha256"), f"{field}.source_sha256"),
        reason=_nonempty_string(payload.get("reason"), f"{field}.reason"),
        revision_mappings=revisions,
    )


def decode_legacy_lineage_manifest(payload: object) -> LegacyLineageManifest:
    """Decode one strict version 1 legacy lineage manifest."""

    document = _mapping(payload, "manifest")
    _require_exact_keys(document, _TOP_LEVEL_KEYS, "manifest")
    if document.get("format") != LEGACY_LINEAGE_MANIFEST_FORMAT:
        raise ValueError("unsupported format for legacy lineage manifest")
    version = document.get("version")
    if isinstance(version, bool) or version != 1:
        raise ValueError("unsupported version for legacy lineage manifest")
    mappings_payload = _sequence(document.get("mappings"), "mappings")
    if not mappings_payload:
        raise ValueError("mappings must not be empty")
    mappings = tuple(
        sorted(
            (
                _decode_document_mapping(item, f"mappings[{index}]")
                for index, item in enumerate(mappings_payload)
            ),
            key=lambda item: item.legacy_document_id,
        )
    )

    legacy_document_ids = [item.legacy_document_id for item in mappings]
    canonical_document_ids = [item.canonical_document_id for item in mappings]
    if len(legacy_document_ids) != len(set(legacy_document_ids)):
        raise ValueError("manifest contains duplicate legacy_document_id")
    if len(canonical_document_ids) != len(set(canonical_document_ids)):
        raise ValueError("manifest contains duplicate canonical_document_id")

    legacy_revision_ids = [
        revision.legacy_revision_id
        for mapping in mappings
        for revision in mapping.revision_mappings
    ]
    canonical_revision_ids = [
        revision.canonical_revision_id
        for mapping in mappings
        for revision in mapping.revision_mappings
    ]
    if len(legacy_revision_ids) != len(set(legacy_revision_ids)):
        raise ValueError("manifest contains duplicate legacy_revision_id")
    if len(canonical_revision_ids) != len(set(canonical_revision_ids)):
        raise ValueError("manifest contains duplicate canonical_revision_id")

    return LegacyLineageManifest(
        source_database_sha256=_sha256(
            document.get("source_database_sha256"),
            "source_database_sha256",
        ),
        reviewer_id=_nonempty_string(document.get("reviewer_id"), "reviewer_id"),
        reviewed_at=_reviewed_at(document.get("reviewed_at")),
        mappings=mappings,
    )


def legacy_lineage_manifest_document(
    manifest: LegacyLineageManifest,
) -> dict[str, object]:
    """Project a decoded manifest to canonical external JSON data."""

    return {
        "format": LEGACY_LINEAGE_MANIFEST_FORMAT,
        "version": 1,
        "source_database_sha256": manifest.source_database_sha256,
        "reviewer_id": manifest.reviewer_id,
        "reviewed_at": manifest.reviewed_at.isoformat(),
        "mappings": [
            {
                "legacy_document_id": mapping.legacy_document_id,
                "canonical_document_id": mapping.canonical_document_id,
                "source_sha256": mapping.source_sha256,
                "reason": mapping.reason,
                "revision_mappings": [
                    {
                        "legacy_revision_id": revision.legacy_revision_id,
                        "canonical_revision_id": revision.canonical_revision_id,
                    }
                    for revision in mapping.revision_mappings
                ],
            }
            for mapping in manifest.mappings
        ],
    }
