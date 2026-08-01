"""Stable drawing-candidate construction and create-only persistence."""

from __future__ import annotations

import json
from pathlib import Path

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.drawing import (
    CoordinateSystem,
    DrawingCandidate,
    Geometry,
    decode_drawing_candidate,
    drawing_candidate_document,
)
from ansim_review.contracts.validation import expect_sha256, expect_string
from ansim_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    validate_artifact_id,
    write_canonical_create_only,
)
from ansim_review.parsing.odl_adapter import RawElement

_NEUTRAL_TYPES = {
    "text": "TEXT_ELEMENT",
    "table": "TABLE_ELEMENT",
    "path": "VECTOR_ELEMENT",
    "line": "VECTOR_ELEMENT",
}


def _stable_id(prefix: str, payload: dict[str, object]) -> str:
    return f"{prefix}-{sha256_json(payload)[:24].upper()}"


def extractor_candidate_id(
    case_id: str,
    source_sha256: str,
    page: int,
    extractor: str,
    extractor_version: str,
    element_id: str,
) -> str:
    """Derive an extractor candidate ID without timestamps or arrival order."""
    validate_artifact_id(case_id, "case_id")
    expect_sha256(source_sha256, "source_sha256")
    if isinstance(page, bool) or page < 1:
        raise ValueError("page must be positive")
    expect_string(extractor, "extractor")
    expect_string(extractor_version, "extractor_version")
    expect_string(element_id, "element_id")
    return _stable_id(
        "CAND",
        {
            "case_id": case_id,
            "source_sha256": source_sha256,
            "page": page,
            "extractor": extractor,
            "extractor_version": extractor_version,
            "element_id": element_id,
        },
    )


def manual_candidate_id(case_id: str, annotation_id: str) -> str:
    """Derive a manual candidate ID from its stable annotation identity."""
    validate_artifact_id(case_id, "case_id")
    validate_artifact_id(annotation_id, "annotation_id")
    return _stable_id(
        "CAND",
        {"case_id": case_id, "annotation_id": annotation_id},
    )


def _validated(candidate: DrawingCandidate) -> DrawingCandidate:
    return decode_drawing_candidate(drawing_candidate_document(candidate))


def candidate_from_raw_element(
    *,
    case_id: str,
    source_sha256: str,
    raw: RawElement,
    extractor: str,
    extractor_version: str,
    coordinate_system: CoordinateSystem,
) -> DrawingCandidate:
    """Convert one explicit parser element into neutral candidate evidence."""
    neutral_type = _NEUTRAL_TYPES.get(raw.element_type.lower())
    if neutral_type is None:
        raise ValueError("unsupported neutral parser element type")
    if raw.raw_bbox is None:
        raise ValueError("parser element requires a bounding box")
    candidate = DrawingCandidate(
        candidate_id=extractor_candidate_id(
            case_id,
            source_sha256,
            raw.page_number,
            extractor,
            extractor_version,
            raw.element_id,
        ),
        source_sha256=expect_sha256(source_sha256, "source_sha256"),
        page=raw.page_number,
        candidate_type=neutral_type,
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system=coordinate_system,
            coordinates=raw.raw_bbox,
        ),
        raw_value=raw.raw_text,
        normalized_candidate=None,
        extractor=extractor,
        extractor_version=extractor_version,
        annotation_id=None,
    )
    return _validated(candidate)


def create_manual_candidate(
    *,
    case_id: str,
    source_sha256: str,
    page: int,
    annotation_id: str,
    candidate_type: str,
    geometry: Geometry,
    raw_value: str | None,
    normalized_candidate: str | None,
) -> DrawingCandidate:
    """Create reviewer-manual candidate evidence for an explicit annotation."""
    validate_artifact_id(annotation_id, "annotation_id")
    candidate = DrawingCandidate(
        candidate_id=manual_candidate_id(case_id, annotation_id),
        source_sha256=expect_sha256(source_sha256, "source_sha256"),
        page=page,
        candidate_type=expect_string(candidate_type, "candidate_type"),
        origin="REVIEWER_MANUAL",
        status="CREATED",
        geometry=geometry,
        raw_value=raw_value,
        normalized_candidate=normalized_candidate,
        extractor=None,
        extractor_version=None,
        annotation_id=annotation_id,
    )
    return _validated(candidate)


def persist_candidate(case_dir: Path, candidate: DrawingCandidate) -> CaseManifestEntry:
    """Persist one immutable candidate document with create-only semantics."""
    validated = _validated(candidate)
    relative_path = f"candidates/{validated.candidate_id}.json"
    path = case_artifact_path(case_dir, relative_path)
    digest = write_canonical_create_only(path, drawing_candidate_document(validated))
    return CaseManifestEntry(
        artifact_id=validated.candidate_id,
        relative_path=relative_path,
        sha256=digest,
    )


def load_candidate(case_dir: Path, candidate_id: str) -> DrawingCandidate:
    """Load one candidate and verify its filename identity."""
    validate_artifact_id(candidate_id, "candidate_id")
    relative_path = f"candidates/{candidate_id}.json"
    path = case_artifact_path(case_dir, relative_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate = decode_drawing_candidate(payload)
    if candidate.candidate_id != candidate_id:
        raise ValueError("candidate file identity mismatch")
    return candidate
