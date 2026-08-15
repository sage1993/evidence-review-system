"""Case-local drawing workspace primitives and manifest contracts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.formats import CASE_MANIFEST_FORMAT
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.legacy_formats import LEGACY_CASE_MANIFEST_FORMAT
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)


@dataclass(frozen=True, slots=True)
class CaseManifestEntry:
    """Hash-bound index entry for one immutable case artifact."""

    artifact_id: str
    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CaseManifest:
    """Deterministic index of drawing artifacts belonging to one case."""

    format: Literal["evidence-review/case-manifest"]
    version: Literal[1]
    case_id: str
    policy_id: str
    sources: tuple[CaseManifestEntry, ...]
    quality_assessments: tuple[CaseManifestEntry, ...]
    candidates: tuple[CaseManifestEntry, ...]
    confirmations: tuple[CaseManifestEntry, ...]
    confirmed_inputs_path: str | None
    confirmed_inputs_sha256: str | None


def validate_artifact_id(value: str, field: str) -> str:
    """Validate one stable path-safe identifier using the shared policy."""
    return validate_identifier(value, field)


def case_root(cases_root: Path, case_id: str) -> Path:
    """Return the resolved case directory for a validated case identifier."""
    validate_artifact_id(case_id, "case_id")
    return cases_root.resolve() / case_id


def _safe_relative_path(value: object, field: str) -> str:
    path = expect_string(value, field)
    parsed = PurePosixPath(path)
    first = parsed.parts[0] if parsed.parts else ""
    if (
        not parsed.parts
        or parsed.is_absolute()
        or ".." in parsed.parts
        or "\\" in path
        or ":" in first
    ):
        raise ValueError(f"{field} must be a safe relative path")
    return path


def case_artifact_path(case_dir: Path, relative_path: str) -> Path:
    """Resolve one case-relative path and reject traversal or alternate separators."""
    safe = _safe_relative_path(relative_path, "artifact path")
    parsed = PurePosixPath(safe)
    resolved_case = case_dir.resolve()
    target = case_dir.joinpath(*parsed.parts)
    if not target.resolve(strict=False).is_relative_to(resolved_case):
        raise ValueError("artifact path must stay inside the case root")
    return target


def write_canonical_create_only(path: Path, document: object) -> str:
    """Write canonical JSON once and return its byte-level SHA-256 digest."""
    payload = dump_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _decode_entry(value: object, field: str) -> CaseManifestEntry:
    payload = expect_mapping(value, field)
    required = {"artifact_id", "relative_path", "sha256"}
    require_fields(payload, required, field)
    reject_unknown(payload, required, field)
    return CaseManifestEntry(
        artifact_id=validate_artifact_id(
            expect_string(payload.get("artifact_id"), f"{field}.artifact_id"),
            f"{field}.artifact_id",
        ),
        relative_path=_safe_relative_path(
            payload.get("relative_path"), f"{field}.relative_path"
        ),
        sha256=expect_sha256(payload.get("sha256"), f"{field}.sha256"),
    )


def _decode_entries(value: object, field: str) -> tuple[CaseManifestEntry, ...]:
    entries = tuple(
        _decode_entry(item, f"{field}[{index}]")
        for index, item in enumerate(expect_sequence(value, field))
    )
    artifact_ids = [entry.artifact_id for entry in entries]
    relative_paths = [entry.relative_path for entry in entries]
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError(f"{field} contains duplicate artifact_id values")
    if len(set(relative_paths)) != len(relative_paths):
        raise ValueError(f"{field} contains duplicate relative_path values")
    return entries


def decode_case_manifest(value: object) -> CaseManifest:
    """Decode a generic or legacy case manifest into the generic model."""
    payload = expect_mapping(value, "case_manifest")
    required = {
        "format",
        "version",
        "case_id",
        "policy_id",
        "sources",
        "quality_assessments",
        "candidates",
        "confirmations",
        "confirmed_inputs_path",
        "confirmed_inputs_sha256",
    }
    require_fields(payload, required, "case_manifest")
    reject_unknown(payload, required, "case_manifest")
    expect_literal(
        payload.get("format"),
        "format",
        (CASE_MANIFEST_FORMAT, LEGACY_CASE_MANIFEST_FORMAT),
    )
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")

    confirmed_inputs_path_value = payload.get("confirmed_inputs_path")
    confirmed_inputs_hash_value = payload.get("confirmed_inputs_sha256")
    confirmed_inputs_path = (
        None
        if confirmed_inputs_path_value is None
        else _safe_relative_path(confirmed_inputs_path_value, "confirmed_inputs_path")
    )
    confirmed_inputs_sha256 = (
        None
        if confirmed_inputs_hash_value is None
        else expect_sha256(confirmed_inputs_hash_value, "confirmed_inputs_sha256")
    )
    if (confirmed_inputs_path is None) != (confirmed_inputs_sha256 is None):
        raise ValueError(
            "confirmed_inputs_path and confirmed_inputs_sha256 must both be null or present"
        )

    return CaseManifest(
        format=CASE_MANIFEST_FORMAT,
        version=1,
        case_id=validate_artifact_id(
            expect_string(payload.get("case_id"), "case_id"), "case_id"
        ),
        policy_id=expect_string(payload.get("policy_id"), "policy_id"),
        sources=_decode_entries(payload.get("sources"), "sources"),
        quality_assessments=_decode_entries(
            payload.get("quality_assessments"), "quality_assessments"
        ),
        candidates=_decode_entries(payload.get("candidates"), "candidates"),
        confirmations=_decode_entries(payload.get("confirmations"), "confirmations"),
        confirmed_inputs_path=confirmed_inputs_path,
        confirmed_inputs_sha256=confirmed_inputs_sha256,
    )


def _entry_document(entry: CaseManifestEntry) -> dict[str, object]:
    return {
        "artifact_id": entry.artifact_id,
        "relative_path": entry.relative_path,
        "sha256": entry.sha256,
    }


def case_manifest_document(manifest: CaseManifest) -> dict[str, object]:
    """Return the canonical generic JSON representation of one case manifest."""
    return {
        "format": CASE_MANIFEST_FORMAT,
        "version": manifest.version,
        "case_id": manifest.case_id,
        "policy_id": manifest.policy_id,
        "sources": [_entry_document(entry) for entry in manifest.sources],
        "quality_assessments": [
            _entry_document(entry) for entry in manifest.quality_assessments
        ],
        "candidates": [_entry_document(entry) for entry in manifest.candidates],
        "confirmations": [_entry_document(entry) for entry in manifest.confirmations],
        "confirmed_inputs_path": manifest.confirmed_inputs_path,
        "confirmed_inputs_sha256": manifest.confirmed_inputs_sha256,
    }
