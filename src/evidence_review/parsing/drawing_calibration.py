"""Confirmed drawing calibration bound to the deterministic Math Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.validation import (
    expect_bool,
    expect_int,
    expect_literal,
    expect_mapping,
    expect_number,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.math_engine.formulas import (
    DRAWING_LENGTH_ID,
    DRAWING_LENGTH_VERSION,
    DRAWING_REGISTRY,
    DRAWING_SCALE_ID,
    DRAWING_SCALE_VERSION,
    run_calculation,
)
from evidence_review.parsing.drawing_case import (
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
    candidate_id: str | None = None
    confirmation_id: str | None = None


def _optional_calibration_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return expect_string(value, field)


def _decode_reference(value: object, index: int) -> CalibrationReference:
    field = f"references[{index}]"
    payload = expect_mapping(value, field)
    required = {"pixel_points", "real_length", "unit", "axis"}
    require_fields(payload, required, field)
    reject_unknown(payload, required, field)
    points = expect_sequence(payload["pixel_points"], f"{field}.pixel_points")
    if len(points) != 2:
        raise ValueError(f"{field}.pixel_points must contain two points")
    decoded_points: list[Position] = []
    for point_index, point in enumerate(points):
        coordinates = expect_sequence(point, f"{field}.pixel_points[{point_index}]")
        if len(coordinates) != 2:
            raise ValueError(
                f"{field}.pixel_points[{point_index}] must contain two numbers"
            )
        decoded_points.append(
            (
                expect_number(
                    coordinates[0],
                    f"{field}.pixel_points[{point_index}][0]",
                ),
                expect_number(
                    coordinates[1],
                    f"{field}.pixel_points[{point_index}][1]",
                ),
            )
        )
    return CalibrationReference(
        pixel_points=(decoded_points[0], decoded_points[1]),
        real_length=expect_string(payload["real_length"], f"{field}.real_length"),
        unit=expect_string(payload["unit"], f"{field}.unit"),
        axis=expect_literal(payload["axis"], f"{field}.axis", ("x", "y")),
    )


def decode_calibration(value: object) -> CalibrationRecord:
    """Decode one canonical calibration document, including browser bindings."""
    payload = expect_mapping(value, "calibration")
    required = {
        "calibration_id", "source_sha256", "page", "references", "scale_x",
        "scale_y", "unit", "formula_id", "formula_version",
        "calculation_result_hash", "reviewer", "confirmed_at", "reviewer_confirmed",
    }
    allowed = required | {"candidate_id", "confirmation_id"}
    require_fields(payload, required, "calibration")
    reject_unknown(payload, allowed, "calibration")
    calibration_id = validate_artifact_id(
        expect_string(payload["calibration_id"], "calibration.calibration_id"),
        "calibration.calibration_id",
    )
    references = tuple(
        _decode_reference(item, index)
        for index, item in enumerate(
            expect_sequence(payload["references"], "calibration.references")
        )
    )
    if not references:
        raise ValueError("calibration.references must not be empty")
    candidate_id = payload.get("candidate_id")
    confirmation_id = payload.get("confirmation_id")
    if candidate_id is not None:
        candidate_id = validate_artifact_id(
            expect_string(candidate_id, "calibration.candidate_id"),
            "calibration.candidate_id",
        )
    if confirmation_id is not None:
        confirmation_id = validate_artifact_id(
            expect_string(confirmation_id, "calibration.confirmation_id"),
            "calibration.confirmation_id",
        )
    return CalibrationRecord(
        calibration_id=calibration_id,
        source_sha256=expect_sha256(payload["source_sha256"], "calibration.source_sha256"),
        page=expect_int(payload["page"], "calibration.page"),
        references=references,
        scale_x=_optional_calibration_string(payload["scale_x"], "calibration.scale_x"),
        scale_y=_optional_calibration_string(payload["scale_y"], "calibration.scale_y"),
        unit=expect_string(payload["unit"], "calibration.unit"),
        formula_id=expect_string(payload["formula_id"], "calibration.formula_id"),
        formula_version=expect_string(
            payload["formula_version"], "calibration.formula_version"
        ),
        calculation_result_hash=expect_sha256(
            payload["calculation_result_hash"],
            "calibration.calculation_result_hash",
        ),
        reviewer=expect_string(payload["reviewer"], "calibration.reviewer"),
        confirmed_at=expect_string(payload["confirmed_at"], "calibration.confirmed_at"),
        reviewer_confirmed=expect_bool(
            payload["reviewer_confirmed"], "calibration.reviewer_confirmed"
        ),
        candidate_id=candidate_id,
        confirmation_id=confirmation_id,
    )


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
    candidate_id: str | None = None,
    confirmation_id: str | None = None,
) -> CalibrationRecord:
    """Calculate scale only from explicit reviewer-confirmed references."""
    source = expect_sha256(source_sha256, "source_sha256")
    if isinstance(page, bool) or page < 1:
        raise ValueError("page must be positive")
    if not references:
        raise ValueError("at least one calibration reference is required")
    if len({reference.axis for reference in references}) != len(references):
        raise ValueError("each calibration axis may have only one reference")
    if (
        not isinstance(reviewer, str)
        or not reviewer
        or reviewer != reviewer.strip()
        or len(reviewer) > 128
        or "/" in reviewer
        or "\\" in reviewer
        or any(ord(character) < 32 or ord(character) == 127 for character in reviewer)
    ):
        raise ValueError("reviewer must be path-safe and non-empty")
    timestamp = _confirmed_timestamp(confirmed_at)
    if candidate_id is not None:
        validate_artifact_id(candidate_id, "candidate_id")
    if confirmation_id is not None:
        validate_artifact_id(confirmation_id, "confirmation_id")

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
        candidate_id=candidate_id,
        confirmation_id=confirmation_id,
    )


def calibration_document(record: CalibrationRecord) -> dict[str, object]:
    """Return canonical, source-bound calibration data."""
    document: dict[str, object] = {
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
    if record.candidate_id is not None:
        document["candidate_id"] = record.candidate_id
    if record.confirmation_id is not None:
        document["confirmation_id"] = record.confirmation_id
    return document


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
    "decode_calibration",
    "persist_calibration",
]
