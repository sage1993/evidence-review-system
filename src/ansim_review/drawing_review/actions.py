"""Strict browser action contracts for the drawing annotation workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ansim_review.contracts.drawing import Geometry, decode_geometry
from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.validation import (
    expect_mapping,
    expect_string,
    reject_unknown,
    require_fields,
)
from ansim_review.parsing.drawing_confirmation import parse_confirmation_time

ExistingActionType = Literal["ACCEPTED", "REJECTED", "EDITED"]
ManualActionType = Literal["CREATED"]

_MAX_REVIEWER_LENGTH = 128
_MAX_TIMESTAMP_LENGTH = 64
_MAX_VALUE_LENGTH = 256
_MAX_UNIT_LENGTH = 32


@dataclass(frozen=True, slots=True)
class ExistingCandidateAction:
    """Reviewer action against one already persisted candidate."""

    action: ExistingActionType
    candidate_id: str
    reviewer: str
    confirmed_at: str
    confirmed_value: str | None
    unit: str | None
    geometry: Geometry | None


@dataclass(frozen=True, slots=True)
class ManualCreateAction:
    """Reviewer-created annotation without browser authority over candidate identity."""

    action: ManualActionType
    annotation_id: str
    candidate_type: str
    reviewer: str
    confirmed_at: str
    confirmed_value: str | None
    unit: str | None
    geometry: Geometry


AnnotationAction: TypeAlias = ExistingCandidateAction | ManualCreateAction


def _bounded_string(value: object, field: str, maximum: int) -> str:
    text = expect_string(value, field)
    if len(text) > maximum:
        raise ValueError(f"{field} exceeds maximum length {maximum}")
    return text


def _optional_bounded_string(
    value: object,
    field: str,
    maximum: int,
) -> str | None:
    if value is None:
        return None
    return _bounded_string(value, field, maximum)


def _reviewer(value: object) -> str:
    reviewer = _bounded_string(value, "reviewer", _MAX_REVIEWER_LENGTH)
    if reviewer != reviewer.strip():
        raise ValueError("reviewer cannot contain leading or trailing whitespace")
    if "/" in reviewer or "\\" in reviewer:
        raise ValueError("reviewer cannot contain path separators")
    if any(ord(character) < 32 or ord(character) == 127 for character in reviewer):
        raise ValueError("reviewer cannot contain control characters")
    return reviewer


def _confirmed_at(value: object) -> str:
    confirmed_at = _bounded_string(value, "confirmed_at", _MAX_TIMESTAMP_LENGTH)
    parse_confirmation_time(confirmed_at)
    return confirmed_at


def _optional_geometry(value: object) -> Geometry | None:
    return None if value is None else decode_geometry(value)


def _value_and_unit(payload: object) -> tuple[str | None, str | None]:
    mapping = expect_mapping(payload, "annotation_action")
    value = _optional_bounded_string(
        mapping.get("confirmed_value"),
        "confirmed_value",
        _MAX_VALUE_LENGTH,
    )
    unit = _optional_bounded_string(mapping.get("unit"), "unit", _MAX_UNIT_LENGTH)
    if value is not None and unit is None:
        raise ValueError("unit is required when confirmed_value is present")
    if unit is not None and value is None:
        raise ValueError("confirmed_value is required when unit is present")
    return value, unit


def _decode_existing(
    payload: object,
    action: ExistingActionType,
) -> ExistingCandidateAction:
    mapping = expect_mapping(payload, "annotation_action")
    fields = {
        "action",
        "candidate_id",
        "reviewer",
        "confirmed_at",
        "confirmed_value",
        "unit",
        "geometry",
    }
    require_fields(mapping, fields, "annotation_action")
    reject_unknown(mapping, fields, "annotation_action")

    confirmed_value, unit = _value_and_unit(mapping)
    geometry = _optional_geometry(mapping.get("geometry"))
    if action in ("ACCEPTED", "REJECTED"):
        if confirmed_value is not None or unit is not None or geometry is not None:
            raise ValueError(f"{action} action cannot contain confirmed data")
    elif confirmed_value is None and geometry is None:
        raise ValueError("EDITED action requires confirmed value or geometry")

    return ExistingCandidateAction(
        action=action,
        candidate_id=validate_identifier(mapping.get("candidate_id"), "candidate_id"),
        reviewer=_reviewer(mapping.get("reviewer")),
        confirmed_at=_confirmed_at(mapping.get("confirmed_at")),
        confirmed_value=confirmed_value,
        unit=unit,
        geometry=geometry,
    )


def _decode_manual(payload: object) -> ManualCreateAction:
    mapping = expect_mapping(payload, "annotation_action")
    fields = {
        "action",
        "annotation_id",
        "candidate_type",
        "reviewer",
        "confirmed_at",
        "confirmed_value",
        "unit",
        "geometry",
    }
    require_fields(mapping, fields, "annotation_action")
    reject_unknown(mapping, fields, "annotation_action")

    confirmed_value, unit = _value_and_unit(mapping)
    geometry_value = mapping.get("geometry")
    if geometry_value is None:
        raise ValueError("CREATED action requires geometry")

    return ManualCreateAction(
        action="CREATED",
        annotation_id=validate_identifier(mapping.get("annotation_id"), "annotation_id"),
        candidate_type=validate_identifier(
            mapping.get("candidate_type"),
            "candidate_type",
        ),
        reviewer=_reviewer(mapping.get("reviewer")),
        confirmed_at=_confirmed_at(mapping.get("confirmed_at")),
        confirmed_value=confirmed_value,
        unit=unit,
        geometry=decode_geometry(geometry_value),
    )


def decode_annotation_action(value: object) -> AnnotationAction:
    """Decode one action and reject fields that belong to server authority."""
    payload = expect_mapping(value, "annotation_action")
    action = expect_string(payload.get("action"), "action")
    if action == "CREATED":
        return _decode_manual(payload)
    if action == "ACCEPTED":
        return _decode_existing(payload, "ACCEPTED")
    if action == "REJECTED":
        return _decode_existing(payload, "REJECTED")
    if action == "EDITED":
        return _decode_existing(payload, "EDITED")
    raise ValueError(f"unsupported action: {action}")
