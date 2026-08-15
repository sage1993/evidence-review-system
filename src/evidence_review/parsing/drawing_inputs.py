"""Build and persist engine-eligible inputs from reviewer confirmations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.drawing import (
    CandidateStatus,
    ConfirmedInput,
    DrawingCandidate,
    DrawingConfirmation,
    confirmed_input_document,
    decode_confirmed_input,
    geometry_document,
)
from evidence_review.contracts.formats import CONFIRMED_INPUT_SET_FORMAT
from evidence_review.contracts.validation import expect_string
from evidence_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    validate_artifact_id,
    write_canonical_create_only,
)
from evidence_review.parsing.drawing_confirmation import (
    validate_confirmation_for_candidate,
)

ConflictReason = Literal[
    "DIFFERENT_VALUE_OR_UNIT",
    "INCOMPATIBLE_GEOMETRY",
    "DUPLICATE_ACTIVE_FIELD",
]
_BINDABLE_STATUSES: tuple[CandidateStatus, ...] = (
    "ACCEPTED",
    "EDITED",
    "CREATED",
)


@dataclass(frozen=True, slots=True)
class ConfirmedInputBuildRequest:
    """All immutable records needed to build one confirmed input."""

    input_id: str
    field: str
    value: str
    unit: str
    candidate: DrawingCandidate
    effective_status: CandidateStatus
    confirmation: DrawingConfirmation
    confirmation_entry: CaseManifestEntry


@dataclass(frozen=True, slots=True)
class ConfirmedInputConflict:
    """Set-level conflict that must be resolved without selecting a winner."""

    field: str
    input_ids: tuple[str, ...]
    reason: ConflictReason


def _finite_decimal(value: str) -> str:
    text = expect_string(value, "value")
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("value must be a finite decimal string") from error
    if not parsed.is_finite():
        raise ValueError("value must be a finite decimal string")
    return text


def _validate_value_provenance(request: ConfirmedInputBuildRequest) -> None:
    if request.confirmation.confirmed_value is not None:
        if request.value != request.confirmation.confirmed_value:
            raise ValueError("confirmed input value does not match confirmation")
        if request.confirmation.unit != request.unit:
            raise ValueError("confirmed input unit does not match confirmation")
        return
    candidate_value = (
        request.candidate.normalized_candidate
        if request.candidate.normalized_candidate is not None
        else request.candidate.raw_value
    )
    if candidate_value is None or request.value != candidate_value:
        raise ValueError("confirmed input value has no resolved candidate provenance")


def build_confirmed_input(request: ConfirmedInputBuildRequest) -> ConfirmedInput:
    """Build one M0 confirmed input after validating confirmation provenance."""
    validate_artifact_id(request.input_id, "input_id")
    validate_artifact_id(request.field, "field")
    if request.effective_status not in _BINDABLE_STATUSES:
        raise ValueError(f"candidate status cannot bind: {request.effective_status}")
    computed_status = validate_confirmation_for_candidate(
        request.candidate,
        request.confirmation,
    )
    if computed_status != request.effective_status:
        raise ValueError("effective candidate status does not match confirmation")
    if request.confirmation_entry.artifact_id != request.confirmation.confirmation_id:
        raise ValueError("confirmation entry identity does not match confirmation")
    value = _finite_decimal(request.value)
    unit = expect_string(request.unit, "unit")
    _validate_value_provenance(request)
    geometry = (
        request.confirmation.geometry
        if request.confirmation.geometry is not None
        else request.candidate.geometry
    )
    confirmed = ConfirmedInput(
        input_id=request.input_id,
        field=request.field,
        value=value,
        unit=unit,
        status="CONFIRMED",
        candidate_status=request.effective_status,
        source_sha256=request.candidate.source_sha256,
        page=request.candidate.page,
        evidence_id=request.candidate.candidate_id,
        geometry=geometry,
        confirmation_record=request.confirmation_entry.relative_path,
        confirmation_sha256=request.confirmation_entry.sha256,
    )
    return decode_confirmed_input(confirmed_input_document(confirmed))


def validate_confirmed_input_set(
    inputs: Sequence[ConfirmedInput],
) -> tuple[ConfirmedInputConflict, ...]:
    """Return deterministically sorted conflicts without choosing an input."""
    grouped: dict[str, list[ConfirmedInput]] = defaultdict(list)
    for confirmed in inputs:
        validated = decode_confirmed_input(confirmed_input_document(confirmed))
        grouped[validated.field].append(validated)

    conflicts: list[ConfirmedInputConflict] = []
    for field in sorted(grouped):
        active = sorted(grouped[field], key=lambda item: item.input_id)
        if len(active) < 2:
            continue
        input_ids = tuple(item.input_id for item in active)
        value_units = {(item.value, item.unit) for item in active}
        geometries = {
            sha256_json(geometry_document(item.geometry))
            for item in active
        }
        if len(value_units) > 1:
            reason: ConflictReason = "DIFFERENT_VALUE_OR_UNIT"
        elif len(geometries) > 1:
            reason = "INCOMPATIBLE_GEOMETRY"
        else:
            reason = "DUPLICATE_ACTIVE_FIELD"
        conflicts.append(
            ConfirmedInputConflict(
                field=field,
                input_ids=input_ids,
                reason=reason,
            )
        )
    return tuple(conflicts)


def confirmed_inputs_document(
    inputs: Sequence[ConfirmedInput],
) -> dict[str, object]:
    """Return the canonical collection document sorted by field and input ID."""
    validated = [
        decode_confirmed_input(confirmed_input_document(item))
        for item in inputs
    ]
    ordered = sorted(validated, key=lambda item: (item.field, item.input_id))
    return {
        "format": CONFIRMED_INPUT_SET_FORMAT,
        "version": 1,
        "inputs": [confirmed_input_document(item) for item in ordered],
    }


def persist_confirmed_inputs(
    case_dir: Path,
    inputs: Sequence[ConfirmedInput],
) -> CaseManifestEntry:
    """Persist a conflict-free confirmed-input set with create-only semantics."""
    conflicts = validate_confirmed_input_set(inputs)
    if conflicts:
        details = ", ".join(
            f"{conflict.field}:{conflict.reason}" for conflict in conflicts
        )
        raise ValueError(f"confirmed input conflicts: {details}")
    relative_path = "confirmed-inputs.json"
    path = case_artifact_path(case_dir, relative_path)
    digest = write_canonical_create_only(path, confirmed_inputs_document(inputs))
    return CaseManifestEntry(
        artifact_id="CONFIRMED-INPUTS",
        relative_path=relative_path,
        sha256=digest,
    )
