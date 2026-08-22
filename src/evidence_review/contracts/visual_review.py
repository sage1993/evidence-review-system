"""Strict contract for externally authored case-visual observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from evidence_review.contracts.drawing import (
    Geometry,
    decode_geometry,
    geometry_document,
)
from evidence_review.contracts.validation import (
    expect_int,
    expect_mapping,
    expect_sha256,
    expect_string,
    reject_unknown,
)

VISUAL_ANALYSIS_OUTPUT_FORMAT = "evidence-review/visual-analysis-output"
VISUAL_ANALYSIS_OUTPUT_VERSION = 1


@dataclass(frozen=True, slots=True)
class VisualObservation:
    """One source-bound, non-conclusive visual observation."""

    attachment_id: str
    source_sha256: str
    page: int
    issue_ids: tuple[str, ...]
    candidate_type: str
    geometry: Geometry
    raw_value: str | None
    normalized_candidate: str | None


@dataclass(frozen=True, slots=True)
class VisualAnalysisOutput:
    """Validated external visual-analysis response before candidate projection."""

    visual_analysis_id: str
    observations: tuple[VisualObservation, ...]


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value, Sequence
    ):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return expect_string(value, field, allow_empty=True)


def _observation(value: object, field: str) -> VisualObservation:
    payload = expect_mapping(value, field)
    allowed = {
        "attachment_id",
        "source_sha256",
        "page",
        "issue_ids",
        "candidate_type",
        "geometry",
        "raw_value",
        "normalized_candidate",
    }
    reject_unknown(payload, allowed, field)
    page = expect_int(payload.get("page"), f"{field}.page")
    if page < 1:
        raise ValueError(f"{field}.page must be positive")
    issue_values = _sequence(
        payload.get("issue_ids"),
        f"{field}.issue_ids",
    )
    issue_ids = tuple(
        expect_string(item, f"{field}.issue_ids[{index}]")
        for index, item in enumerate(issue_values)
    )
    if not issue_ids:
        raise ValueError(f"{field}.issue_ids must not be empty")
    if len(issue_ids) != len(set(issue_ids)):
        raise ValueError(f"{field}.issue_ids must contain unique values")
    return VisualObservation(
        attachment_id=expect_string(
            payload.get("attachment_id"),
            f"{field}.attachment_id",
        ),
        source_sha256=expect_sha256(
            payload.get("source_sha256"),
            f"{field}.source_sha256",
        ),
        page=page,
        issue_ids=issue_ids,
        candidate_type=expect_string(
            payload.get("candidate_type"),
            f"{field}.candidate_type",
        ),
        geometry=decode_geometry(payload.get("geometry")),
        raw_value=_optional_string(
            payload.get("raw_value"),
            f"{field}.raw_value",
        ),
        normalized_candidate=_optional_string(
            payload.get("normalized_candidate"),
            f"{field}.normalized_candidate",
        ),
    )


def decode_visual_analysis_output(value: object) -> VisualAnalysisOutput:
    """Decode a visual-analysis response and reject conclusion-like extras."""
    payload = expect_mapping(value, "visual_analysis_output")
    allowed = {"format", "version", "visual_analysis_id", "observations"}
    reject_unknown(payload, allowed, "visual_analysis_output")
    if payload.get("format") != VISUAL_ANALYSIS_OUTPUT_FORMAT:
        raise ValueError("unsupported visual analysis output format")
    version = expect_int(
        payload.get("version"),
        "visual_analysis_output.version",
    )
    if version != VISUAL_ANALYSIS_OUTPUT_VERSION:
        raise ValueError("unsupported visual analysis output version")
    observation_values = _sequence(
        payload.get("observations"),
        "visual_analysis_output.observations",
    )
    observations = tuple(
        _observation(item, f"observations[{index}]")
        for index, item in enumerate(observation_values)
    )
    return VisualAnalysisOutput(
        visual_analysis_id=expect_string(
            payload.get("visual_analysis_id"),
            "visual_analysis_output.visual_analysis_id",
        ),
        observations=observations,
    )


def visual_observation_document(
    observation: VisualObservation,
) -> dict[str, object]:
    return {
        "attachment_id": observation.attachment_id,
        "source_sha256": observation.source_sha256,
        "page": observation.page,
        "issue_ids": list(observation.issue_ids),
        "candidate_type": observation.candidate_type,
        "geometry": geometry_document(observation.geometry),
        "raw_value": observation.raw_value,
        "normalized_candidate": observation.normalized_candidate,
    }


def visual_analysis_output_document(
    output: VisualAnalysisOutput,
) -> dict[str, object]:
    return {
        "format": VISUAL_ANALYSIS_OUTPUT_FORMAT,
        "version": VISUAL_ANALYSIS_OUTPUT_VERSION,
        "visual_analysis_id": output.visual_analysis_id,
        "observations": [
            visual_observation_document(item) for item in output.observations
        ],
    }


__all__ = [
    "VISUAL_ANALYSIS_OUTPUT_FORMAT",
    "VISUAL_ANALYSIS_OUTPUT_VERSION",
    "VisualAnalysisOutput",
    "VisualObservation",
    "decode_visual_analysis_output",
    "visual_analysis_output_document",
    "visual_observation_document",
]
