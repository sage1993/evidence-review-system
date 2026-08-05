"""Confirmed drawing calibration bound to the deterministic Math Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.validation import expect_sha256
from ansim_review.math_engine.formulas import (
    DRAWING_LENGTH_ID,
    DRAWING_LENGTH_VERSION,
    DRAWING_REGISTRY,
    DRAWING_SCALE_ID,
    DRAWING_SCALE_VERSION,
    run_calculation,
)
from ansim_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    validate_artifact_id,
    write_canonical_create_only,
)

Axis = Literal["x", "y"]
Position = tuple[float, float]


@dataclass(frozen=True, slots=True)
class CalibrationReference:
    """One reviewer-confirmed axis-aligned pixel distance."""

    pixel_points: tuple[Position, Position]
    real_length: str
    unit: str
    axis: Axis

    def __post_init__(self) -> None:
        if len(self.pixel_points) != 2:
            raise ValueError("pixel_points must contain two points")
        if self.axis not in ("x", "y"):
            raise ValueError("axis must be x or y")
        if not isinstance(self.real_length, str) or not self.real_length:
            raise ValueError("real_length must be a decimal string")
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError("unit must be a non-empty string")
        try:
            value = Decimal(self.real_length)
        except InvalidOperation as error:
            raise ValueError("real_length must be a decimal string") from error
        if not value.is_finite() or value <= 0:
            raise ValueError("real_length must be positive and finite")
        for point in self.pixel_points:
            if len(point) != 2:
                raise ValueError("pixel points must contain x and y")
            if any(isinstance(coordinate, bool) for coordinate in point):
                raise ValueError("pixel points must contain numeric values")
            try:
                finite = all(
                    Decimal(str(coordinate)).is_finite() for coordinate in point
                )
            except (InvalidOperation, ValueError):
                raise ValueError("pixel points must be finite") from None
            if not finite:
                raise ValueError("pixel points must be finite")
        first, second = self.pixel_points
        dx = abs(Decimal(str(second[0])) - Decimal(str(first[0])))
        dy = abs(Decimal(str(second[1])) - Decimal(str(first[1])))
        if dx == 0 and dy == 0:
            raise ValueError("pixel points must be distinct")
        if self.axis == "x" and dy != 0:
            raise ValueError("reference must be axis-aligned on x")
        if self.axis == "y" and dx != 0:
            raise ValueError("reference must be axis-aligned on y")


@dataclass(frozen=True, slots=True)
class CalibrationRecord:
    """Immutable, source-bound calibration approved by a reviewer."""

    calibration_id: str
    source_sha256: str
    page: int
    references: tuple[CalibrationReference, ...]
    scale_x: str | None
    scale_y: str | None
    unit: str
    formula_id: str
    formula_version: str
    calculation_result_hash: str
    reviewer: str
    confirmed_at: str
    reviewer_confirmed: bool = True


def _confirmed_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("confirmed_at must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("confirmed_at must include an explicit UTC offset")
    return value


def _pixel_length(reference: CalibrationReference) -> str:
    first, second = reference.pixel_points
    if reference.axis == "x":
        distance = abs(Decimal(str(second[0])) - Decimal(str(first[0])))
    else:
        distance = abs(Decimal(str(second[1])) - Decimal(str(first[1])))
    return format(distance, "f")


def build_calibration(
    *,
    source_sha256: str,
    page: int,
    references: tuple[CalibrationReference, ...],
    reviewer: str,
    confirmed_at: str,
) -> CalibrationRecord:
    """Calculate scale only from explicit reviewer-confirmed references."""
    source = expect_sha256(source_sha256, "source_sha256")
    if isinstance(page, bool) or page < 1:
        raise ValueError("page must be positive")
    if not references:
        raise ValueError("at least one calibration reference is required")
    if len({reference.axis for reference in references}) != len(references):
        raise ValueError("each calibration axis may have only one reference")
    if not reviewer or "/" in reviewer or "\\" in reviewer or any(
        ord(character) < 32 for character in reviewer
    ):
        raise ValueError("reviewer must be path-safe and non-empty")
    timestamp = _confirmed_timestamp(confirmed_at)

    scales: dict[Axis, str] = {}
    result_hashes: list[str] = []
    for reference in references:
        result = run_calculation(
            DRAWING_SCALE_ID,
            DRAWING_SCALE_VERSION,
            {
                "real_length": reference.real_length,
                "pixel_length": _pixel_length(reference),
            },
            registry=DRAWING_REGISTRY,
        )
        if result.status != "SUCCESS" or result.raw_result is None:
            raise ValueError("Math Engine rejected calibration reference")
        scales[reference.axis] = result.raw_result
        if result.result_hash is None:
            raise ValueError("Math Engine result is missing result_hash")
        result_hashes.append(result.result_hash)

    digest = sha256_json(
        {
            "source_sha256": source,
            "page": page,
            "references": [
                {
                    "pixel_points": [list(point) for point in reference.pixel_points],
                    "real_length": reference.real_length,
                    "unit": reference.unit,
                    "axis": reference.axis,
                }
                for reference in references
            ],
            "formula_id": DRAWING_SCALE_ID,
            "formula_version": DRAWING_SCALE_VERSION,
            "calculation_result_hashes": result_hashes,
            "reviewer": reviewer,
            "confirmed_at": timestamp,
        }
    )
    return CalibrationRecord(
        calibration_id=f"CAL-{digest[:24].upper()}",
        source_sha256=source,
        page=page,
        references=references,
        scale_x=scales.get("x"),
        scale_y=scales.get("y"),
        unit=references[0].unit,
        formula_id=DRAWING_SCALE_ID,
        formula_version=DRAWING_SCALE_VERSION,
        calculation_result_hash=sha256_json({"results": result_hashes}),
        reviewer=reviewer,
        confirmed_at=timestamp,
    )


def calibration_document(record: CalibrationRecord) -> dict[str, object]:
    """Return canonical, source-bound calibration data."""
    return {
        "calibration_id": record.calibration_id,
        "source_sha256": record.source_sha256,
        "page": record.page,
        "references": [
            {
                "pixel_points": [list(point) for point in reference.pixel_points],
                "real_length": reference.real_length,
                "unit": reference.unit,
                "axis": reference.axis,
            }
            for reference in record.references
        ],
        "scale_x": record.scale_x,
        "scale_y": record.scale_y,
        "unit": record.unit,
        "formula_id": record.formula_id,
        "formula_version": record.formula_version,
        "calculation_result_hash": record.calculation_result_hash,
        "reviewer": record.reviewer,
        "confirmed_at": record.confirmed_at,
        "reviewer_confirmed": record.reviewer_confirmed,
    }


def persist_calibration(
    case_dir: Path,
    record: CalibrationRecord,
) -> CaseManifestEntry:
    """Persist calibration create-only under the case artifact root."""
    validate_artifact_id(record.calibration_id, "calibration_id")
    relative_path = f"calibrations/{record.calibration_id}.json"
    digest = write_canonical_create_only(
        case_artifact_path(case_dir, relative_path),
        calibration_document(record),
    )
    return CaseManifestEntry(
        artifact_id=record.calibration_id,
        relative_path=relative_path,
        sha256=digest,
    )


def calculate_real_length(
    record: CalibrationRecord,
    *,
    pixel_length: str,
    axis: Axis,
) -> str:
    """Convert a pixel distance only with a previously confirmed axis scale."""
    if not isinstance(pixel_length, str):
        raise ValueError("pixel_length must be a decimal string")
    scale = record.scale_x if axis == "x" else record.scale_y
    if scale is None:
        raise ValueError(f"no confirmed {axis}-axis calibration is available")
    result = run_calculation(
        DRAWING_LENGTH_ID,
        DRAWING_LENGTH_VERSION,
        {"pixel_length": pixel_length, "scale": scale},
        registry=DRAWING_REGISTRY,
    )
    if result.status != "SUCCESS" or result.raw_result is None:
        raise ValueError("Math Engine rejected drawing length conversion")
    return result.raw_result


__all__ = [
    "CalibrationRecord",
    "CalibrationReference",
    "build_calibration",
    "calculate_real_length",
    "calibration_document",
    "persist_calibration",
]
