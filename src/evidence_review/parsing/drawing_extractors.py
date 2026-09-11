"""Deterministic, staged drawing candidate extraction.

Extractors produce unconfirmed evidence only. They never infer a confirmed
measurement, select a boundary, or bypass the drawing quality gate.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from evidence_review.contracts.drawing import (
    CoordinateSystem,
    DrawingCandidate,
    DrawingQualityAssessment,
    Geometry,
    decode_geometry,
)
from evidence_review.contracts.validation import expect_sha256
from evidence_review.parsing.drawing_candidates import extractor_candidate_id
from evidence_review.parsing.odl_adapter import RawElement

ExtractionStage = Literal[1, 2, 3]

_SCALE_RE = re.compile(r"(?:축척|scale)\s*[:：]?\s*\d+\s*[:：]\s*\d+", re.IGNORECASE)
_DIMENSION_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:m|mm|cm)\b|(?:폭|길이|거리)\s*[:：]?\s*\d+)",
    re.IGNORECASE,
)
_DRAWING_NUMBER_RE = re.compile(
    r"(?:도면번호|drawing\s*(?:no|number))\s*[:：#-]?\s*\S+",
    re.IGNORECASE,
)
_REVISION_RE = re.compile(r"(?:revision|rev\.?|개정)\s*[:：#-]?\s*\S+", re.IGNORECASE)
_ALLOWED_SEMANTIC_TYPES = {
    "SITE_BOUNDARY",
    "ROAD_BOUNDARY",
    "BUILDING_OUTLINE",
    "VEHICLE_ENTRANCE",
    "SETBACK_LINE",
}

_STAGE_ONE_ORDER = {
    "DRAWING_NUMBER": 0,
    "REVISION": 1,
    "SCALE_TEXT": 2,
    "DIMENSION_TEXT": 3,
    "AREA_TABLE": 4,
    "ROOM_OR_ZONE_LABEL": 5,
}
_COORDINATE_SYSTEM: CoordinateSystem = "PDF_BOTTOM_LEFT_POINTS"


def _stage(value: int) -> ExtractionStage:
    if isinstance(value, bool) or value not in (1, 2, 3):
        raise ValueError("stage must be 1, 2, or 3")
    return value  # type: ignore[return-value]


def _candidate_type(raw: RawElement, stage: ExtractionStage) -> str | None:
    text = raw.raw_text or ""
    if stage == 1:
        kind = raw.element_type.lower()
        if kind == "table":
            return "AREA_TABLE"
        if not text.strip():
            return None
        if _DRAWING_NUMBER_RE.search(text):
            return "DRAWING_NUMBER"
        if _REVISION_RE.search(text):
            return "REVISION"
        if _SCALE_RE.search(text):
            return "SCALE_TEXT"
        if _DIMENSION_RE.search(text):
            return "DIMENSION_TEXT"
        return "ROOM_OR_ZONE_LABEL"
    if stage == 2:
        return (
            "DIMENSION_LINE"
            if raw.element_type.lower() in {"line", "path", "polyline"}
            else None
        )
    semantic = raw.raw_payload.get("semantic_type")
    if not isinstance(semantic, str):
        return None
    normalized = semantic.strip().upper()
    return normalized if normalized in _ALLOWED_SEMANTIC_TYPES else None


def _geometry(raw: RawElement) -> Geometry | None:
    explicit = raw.raw_payload.get("geometry")
    if explicit is not None:
        return decode_geometry(explicit)
    if raw.raw_bbox is None:
        return None
    return Geometry(
        type="BBOX",
        coordinate_system=_COORDINATE_SYSTEM,
        coordinates=raw.raw_bbox,
    )


def extract_drawing_candidates(
    *,
    case_id: str,
    attachment_id: str | None = None,
    source_sha256: str,
    elements: Sequence[RawElement],
    stage: int,
    quality: DrawingQualityAssessment,
    extractor_version: str = "1.0.0",
) -> tuple[DrawingCandidate, ...]:
    """Extract stable, unconfirmed candidates for one quality-approved stage."""
    selected_stage = _stage(stage)
    source = expect_sha256(source_sha256, "source_sha256")
    if quality.quality != "PASS":
        return ()
    candidates: list[DrawingCandidate] = []
    for raw in elements:
        candidate_type = _candidate_type(raw, selected_stage)
        geometry = _geometry(raw)
        if candidate_type is None or geometry is None:
            continue
        candidate = DrawingCandidate(
            candidate_id=extractor_candidate_id(
                case_id,
                source,
                raw.page_number,
                f"DRAWING_STAGE_{selected_stage}",
                extractor_version,
                raw.element_id,
            ),
            source_sha256=source,
            page=raw.page_number,
            candidate_type=candidate_type,
            origin="EXTRACTOR",
            status="UNCONFIRMED",
            geometry=geometry,
            raw_value=raw.raw_text,
            normalized_candidate=None,
            extractor=f"DRAWING_STAGE_{selected_stage}",
            extractor_version=extractor_version,
            annotation_id=None,
            case_id=case_id,
            attachment_id=attachment_id,
        )
        candidates.append(candidate)
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                _STAGE_ONE_ORDER.get(candidate.candidate_type, 99),
                candidate.candidate_type,
                candidate.candidate_id,
            ),
        )
    )


__all__ = ["ExtractionStage", "extract_drawing_candidates"]
