"""Versioned drawing-evidence and reviewer-confirmed input contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Literal, cast

from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_number,
    expect_sequence,
    expect_sha256,
    expect_string,
    expect_string_tuple,
    reject_unknown,
)

CoordinateSystem = Literal["PDF_BOTTOM_LEFT_POINTS", "IMAGE_TOP_LEFT_PIXELS"]
GeometryType = Literal["POINT", "BBOX", "LINESTRING", "POLYGON"]
CandidateOrigin = Literal["EXTRACTOR", "REVIEWER_MANUAL"]
CandidateStatus = Literal[
    "UNCONFIRMED",
    "ACCEPTED",
    "REJECTED",
    "EDITED",
    "CREATED",
    "CONFLICT",
]
DrawingQualityStatus = Literal["PASS", "REVIEW_REQUIRED", "REJECTED"]
PhysicalSizeTrust = Literal[
    "PDF_MEDIABOX_VERIFIED",
    "USER_CONFIRMED",
    "METADATA_ONLY",
    "UNKNOWN",
]
ConfirmationAction = Literal["ACCEPTED", "REJECTED", "EDITED", "CREATED"]
ConfirmedStatus = Literal["CONFIRMED"]

Position = tuple[float, float]
FlatCoordinates = tuple[float, ...]
PathCoordinates = tuple[Position, ...]
GeometryCoordinates = FlatCoordinates | PathCoordinates

_COORDINATE_SYSTEMS: tuple[CoordinateSystem, ...] = (
    "PDF_BOTTOM_LEFT_POINTS",
    "IMAGE_TOP_LEFT_PIXELS",
)
_GEOMETRY_TYPES: tuple[GeometryType, ...] = ("POINT", "BBOX", "LINESTRING", "POLYGON")
_CANDIDATE_ORIGINS: tuple[CandidateOrigin, ...] = ("EXTRACTOR", "REVIEWER_MANUAL")
_CANDIDATE_STATUSES: tuple[CandidateStatus, ...] = (
    "UNCONFIRMED",
    "ACCEPTED",
    "REJECTED",
    "EDITED",
    "CREATED",
    "CONFLICT",
)
_BINDABLE_STATUSES: tuple[CandidateStatus, ...] = ("ACCEPTED", "EDITED", "CREATED")
_QUALITY_STATUSES: tuple[DrawingQualityStatus, ...] = (
    "PASS",
    "REVIEW_REQUIRED",
    "REJECTED",
)
_PHYSICAL_SIZE_TRUST: tuple[PhysicalSizeTrust, ...] = (
    "PDF_MEDIABOX_VERIFIED",
    "USER_CONFIRMED",
    "METADATA_ONLY",
    "UNKNOWN",
)
_CONFIRMATION_ACTIONS: tuple[ConfirmationAction, ...] = (
    "ACCEPTED",
    "REJECTED",
    "EDITED",
    "CREATED",
)
_CONFIRMED_STATUSES: tuple[ConfirmedStatus, ...] = ("CONFIRMED",)


@dataclass(frozen=True, slots=True)
class Geometry:
    """Immutable drawing geometry in an explicitly declared coordinate system."""

    type: GeometryType
    coordinate_system: CoordinateSystem
    coordinates: GeometryCoordinates


@dataclass(frozen=True, slots=True)
class DrawingCandidate:
    """Extractor-generated or reviewer-created candidate evidence."""

    candidate_id: str
    source_sha256: str
    page: int
    candidate_type: str
    origin: CandidateOrigin
    status: CandidateStatus
    geometry: Geometry
    raw_value: str | None
    normalized_candidate: str | None
    extractor: str | None
    extractor_version: str | None
    annotation_id: str | None


@dataclass(frozen=True, slots=True)
class DrawingQualityAssessment:
    """Input quality result separate from finalizer and human decision states."""

    quality: DrawingQualityStatus
    physical_size_trust: PhysicalSizeTrust
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DrawingConfirmation:
    """One append-only reviewer action against a drawing candidate or annotation."""

    confirmation_id: str
    candidate_id: str
    action: ConfirmationAction
    source_sha256: str
    reviewer: str
    confirmed_at: str
    confirmed_value: str | None
    unit: str | None
    geometry: Geometry | None


@dataclass(frozen=True, slots=True)
class ConfirmedInput:
    """Reviewer-confirmed decimal input eligible for deterministic engines."""

    input_id: str
    field: str
    value: str
    unit: str
    status: ConfirmedStatus
    candidate_status: CandidateStatus
    source_sha256: str
    page: int
    evidence_id: str
    geometry: Geometry
    confirmation_record: str
    confirmation_sha256: str


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return expect_string(value, field, allow_empty=True)


def _position(value: object, field: str) -> Position:
    items = expect_sequence(value, field)
    if len(items) != 2:
        raise ValueError(f"{field} must contain two numbers")
    return (
        expect_number(items[0], f"{field}[0]"),
        expect_number(items[1], f"{field}[1]"),
    )


def decode_geometry(value: object) -> Geometry:
    """Decode and validate one geometry document."""
    payload = expect_mapping(value, "geometry")
    reject_unknown(payload, {"type", "coordinate_system", "coordinates"}, "geometry")
    geometry_type = expect_literal(payload.get("type"), "geometry.type", _GEOMETRY_TYPES)
    coordinate_system = expect_literal(
        payload.get("coordinate_system"),
        "geometry.coordinate_system",
        _COORDINATE_SYSTEMS,
    )
    raw_coordinates = expect_sequence(payload.get("coordinates"), "geometry.coordinates")
    coordinates: GeometryCoordinates
    if geometry_type == "POINT":
        coordinates = _position(raw_coordinates, "geometry.coordinates")
    elif geometry_type == "BBOX":
        if len(raw_coordinates) != 4:
            raise ValueError("BBOX requires four numbers")
        flat = tuple(
            expect_number(item, f"geometry.coordinates[{index}]")
            for index, item in enumerate(raw_coordinates)
        )
        left, first_y, right, second_y = flat
        if left > right or first_y > second_y:
            raise ValueError("bbox coordinates are inverted")
        coordinates = flat
    else:
        positions = tuple(
            _position(item, f"geometry.coordinates[{index}]")
            for index, item in enumerate(raw_coordinates)
        )
        if geometry_type == "LINESTRING" and len(positions) < 2:
            raise ValueError("LINESTRING requires at least two positions")
        if geometry_type == "POLYGON":
            if len(positions) < 4:
                raise ValueError("POLYGON requires at least four positions")
            if positions[0] != positions[-1]:
                raise ValueError("POLYGON ring must be closed")
        coordinates = positions
    return Geometry(
        type=geometry_type,
        coordinate_system=coordinate_system,
        coordinates=coordinates,
    )


def geometry_document(geometry: Geometry) -> dict[str, object]:
    """Return the JSON document for one immutable geometry."""
    if geometry.type in ("POINT", "BBOX"):
        coordinates: object = list(cast(FlatCoordinates, geometry.coordinates))
    else:
        coordinates = [list(position) for position in cast(PathCoordinates, geometry.coordinates)]
    return {
        "type": geometry.type,
        "coordinate_system": geometry.coordinate_system,
        "coordinates": coordinates,
    }


def decode_drawing_candidate(value: object) -> DrawingCandidate:
    """Decode one drawing candidate without reviewer confirmation metadata."""
    payload = expect_mapping(value, "drawing_candidate")
    allowed = {
        "candidate_id",
        "source_sha256",
        "page",
        "candidate_type",
        "origin",
        "status",
        "geometry",
        "raw_value",
        "normalized_candidate",
        "extractor",
        "extractor_version",
        "annotation_id",
    }
    reject_unknown(payload, allowed, "drawing_candidate")
    page = expect_int(payload.get("page"), "page")
    if page < 1:
        raise ValueError("page must be positive")
    origin = expect_literal(payload.get("origin"), "origin", _CANDIDATE_ORIGINS)
    status = expect_literal(payload.get("status"), "status", _CANDIDATE_STATUSES)
    extractor = _optional_string(payload.get("extractor"), "extractor")
    extractor_version = _optional_string(payload.get("extractor_version"), "extractor_version")
    annotation_id = _optional_string(payload.get("annotation_id"), "annotation_id")
    if origin == "EXTRACTOR":
        if not extractor or not extractor_version:
            raise ValueError("extractor candidates require extractor metadata")
        if annotation_id is not None:
            raise ValueError("extractor candidates cannot have annotation_id")
    else:
        if not annotation_id:
            raise ValueError("reviewer manual candidates require annotation_id")
        if extractor is not None or extractor_version is not None:
            raise ValueError("reviewer manual candidates cannot have extractor metadata")
    return DrawingCandidate(
        candidate_id=expect_string(payload.get("candidate_id"), "candidate_id"),
        source_sha256=expect_sha256(payload.get("source_sha256"), "source_sha256"),
        page=page,
        candidate_type=expect_string(payload.get("candidate_type"), "candidate_type"),
        origin=origin,
        status=status,
        geometry=decode_geometry(payload.get("geometry")),
        raw_value=_optional_string(payload.get("raw_value"), "raw_value"),
        normalized_candidate=_optional_string(
            payload.get("normalized_candidate"), "normalized_candidate"
        ),
        extractor=extractor,
        extractor_version=extractor_version,
        annotation_id=annotation_id,
    )


def drawing_candidate_document(candidate: DrawingCandidate) -> dict[str, object]:
    """Return the explicit JSON representation of *candidate*."""
    return {
        "candidate_id": candidate.candidate_id,
        "source_sha256": candidate.source_sha256,
        "page": candidate.page,
        "candidate_type": candidate.candidate_type,
        "origin": candidate.origin,
        "status": candidate.status,
        "geometry": geometry_document(candidate.geometry),
        "raw_value": candidate.raw_value,
        "normalized_candidate": candidate.normalized_candidate,
        "extractor": candidate.extractor,
        "extractor_version": candidate.extractor_version,
        "annotation_id": candidate.annotation_id,
    }


def decode_drawing_quality(value: object) -> DrawingQualityAssessment:
    """Decode drawing quality without reusing final review statuses."""
    payload = expect_mapping(value, "drawing_quality")
    reject_unknown(payload, {"quality", "physical_size_trust", "reason_codes"}, "drawing_quality")
    quality = expect_literal(payload.get("quality"), "quality", _QUALITY_STATUSES)
    trust = expect_literal(
        payload.get("physical_size_trust"),
        "physical_size_trust",
        _PHYSICAL_SIZE_TRUST,
    )
    reasons = expect_string_tuple(payload.get("reason_codes", []), "reason_codes")
    if quality == "PASS" and trust == "METADATA_ONLY":
        raise ValueError("METADATA_ONLY cannot produce PASS")
    if quality == "REJECTED" and not reasons:
        raise ValueError("REJECTED drawing quality requires reason_codes")
    return DrawingQualityAssessment(
        quality=quality,
        physical_size_trust=trust,
        reason_codes=reasons,
    )


def drawing_quality_document(assessment: DrawingQualityAssessment) -> dict[str, object]:
    """Return the JSON representation of one drawing quality assessment."""
    return {
        "quality": assessment.quality,
        "physical_size_trust": assessment.physical_size_trust,
        "reason_codes": list(assessment.reason_codes),
    }


def decode_drawing_confirmation(value: object) -> DrawingConfirmation:
    """Decode one append-only reviewer confirmation action."""
    payload = expect_mapping(value, "drawing_confirmation")
    allowed = {
        "confirmation_id",
        "candidate_id",
        "action",
        "source_sha256",
        "reviewer",
        "confirmed_at",
        "confirmed_value",
        "unit",
        "geometry",
    }
    reject_unknown(payload, allowed, "drawing_confirmation")
    geometry_value = payload.get("geometry")
    return DrawingConfirmation(
        confirmation_id=expect_string(payload.get("confirmation_id"), "confirmation_id"),
        candidate_id=expect_string(payload.get("candidate_id"), "candidate_id"),
        action=expect_literal(payload.get("action"), "action", _CONFIRMATION_ACTIONS),
        source_sha256=expect_sha256(payload.get("source_sha256"), "source_sha256"),
        reviewer=expect_string(payload.get("reviewer"), "reviewer"),
        confirmed_at=expect_string(payload.get("confirmed_at"), "confirmed_at"),
        confirmed_value=_optional_string(payload.get("confirmed_value"), "confirmed_value"),
        unit=_optional_string(payload.get("unit"), "unit"),
        geometry=None if geometry_value is None else decode_geometry(geometry_value),
    )


def _decimal_string(value: object, field: str) -> str:
    text = expect_string(value, field)
    try:
        decimal_value = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{field} must be a decimal string") from error
    if not decimal_value.is_finite():
        raise ValueError(f"{field} must be finite")
    return text


def _relative_confirmation_path(value: object) -> str:
    path = expect_string(value, "confirmation_record")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or not parsed.parts:
        raise ValueError("confirmation_record must be a safe relative path")
    if parsed.parts[0] != "confirmations":
        raise ValueError("confirmation_record must be under confirmations/")
    return path


def decode_confirmed_input(value: object) -> ConfirmedInput:
    """Decode one input that is eligible for Math and Rule Engine binding."""
    payload = expect_mapping(value, "confirmed_input")
    allowed = {
        "input_id",
        "field",
        "value",
        "unit",
        "status",
        "candidate_status",
        "source_sha256",
        "page",
        "evidence_id",
        "geometry",
        "confirmation_record",
        "confirmation_sha256",
    }
    reject_unknown(payload, allowed, "confirmed_input")
    status = expect_literal(payload.get("status"), "status", _CONFIRMED_STATUSES)
    candidate_status = expect_literal(
        payload.get("candidate_status"), "candidate_status", _CANDIDATE_STATUSES
    )
    if candidate_status not in _BINDABLE_STATUSES:
        raise ValueError(f"candidate status cannot bind: {candidate_status}")
    page = expect_int(payload.get("page"), "page")
    if page < 1:
        raise ValueError("page must be positive")
    return ConfirmedInput(
        input_id=expect_string(payload.get("input_id"), "input_id"),
        field=expect_string(payload.get("field"), "field"),
        value=_decimal_string(payload.get("value"), "value"),
        unit=expect_string(payload.get("unit"), "unit"),
        status=status,
        candidate_status=candidate_status,
        source_sha256=expect_sha256(payload.get("source_sha256"), "source_sha256"),
        page=page,
        evidence_id=expect_string(payload.get("evidence_id"), "evidence_id"),
        geometry=decode_geometry(payload.get("geometry")),
        confirmation_record=_relative_confirmation_path(payload.get("confirmation_record")),
        confirmation_sha256=expect_sha256(
            payload.get("confirmation_sha256"), "confirmation_sha256"
        ),
    )


def confirmed_input_document(confirmed: ConfirmedInput) -> dict[str, object]:
    """Return the explicit JSON representation of a confirmed input."""
    return {
        "input_id": confirmed.input_id,
        "field": confirmed.field,
        "value": confirmed.value,
        "unit": confirmed.unit,
        "status": confirmed.status,
        "candidate_status": confirmed.candidate_status,
        "source_sha256": confirmed.source_sha256,
        "page": confirmed.page,
        "evidence_id": confirmed.evidence_id,
        "geometry": geometry_document(confirmed.geometry),
        "confirmation_record": confirmed.confirmation_record,
        "confirmation_sha256": confirmed.confirmation_sha256,
    }
