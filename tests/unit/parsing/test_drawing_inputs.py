import json
from pathlib import Path

import pytest

from ansim_review.contracts.drawing import (
    CandidateStatus,
    DrawingConfirmation,
    Geometry,
)
from ansim_review.parsing.drawing_candidates import create_manual_candidate
from ansim_review.parsing.drawing_case import CaseManifestEntry
from ansim_review.parsing.drawing_inputs import (
    ConfirmedInputBuildRequest,
    ConfirmedInputConflict,
    build_confirmed_input,
    confirmed_inputs_document,
    persist_confirmed_inputs,
    validate_confirmed_input_set,
)


def candidate():
    return create_manual_candidate(
        case_id="CASE-001",
        source_sha256="a" * 64,
        page=1,
        annotation_id="ANN-001",
        candidate_type="ROAD_WIDTH_TEXT",
        geometry=Geometry(
            type="LINESTRING",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=((100.0, 200.0), (900.0, 200.0)),
        ),
        raw_value=None,
        normalized_candidate=None,
    )


def confirmation() -> DrawingConfirmation:
    return DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate().candidate_id,
        action="CREATED",
        source_sha256="a" * 64,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value="8.0",
        unit="m",
        geometry=None,
    )


def confirmation_entry() -> CaseManifestEntry:
    return CaseManifestEntry(
        artifact_id="CONF-001",
        relative_path="confirmations/20260801T163000Z-kim-sh-CONF-001.json",
        sha256="c" * 64,
    )


def request(
    *,
    input_id: str = "INPUT-ROAD-WIDTH",
    field: str = "road_width_m",
    value: str = "8.0",
    unit: str = "m",
    effective_status: CandidateStatus = "CREATED",
) -> ConfirmedInputBuildRequest:
    return ConfirmedInputBuildRequest(
        input_id=input_id,
        field=field,
        value=value,
        unit=unit,
        candidate=candidate(),
        effective_status=effective_status,
        confirmation=confirmation(),
        confirmation_entry=confirmation_entry(),
    )


def test_manual_created_candidate_builds_confirmed_input() -> None:
    confirmed = build_confirmed_input(request())
    assert confirmed.status == "CONFIRMED"
    assert confirmed.candidate_status == "CREATED"
    assert confirmed.value == "8.0"
    assert confirmed.evidence_id == candidate().candidate_id
    assert confirmed.confirmation_sha256 == "c" * 64


@pytest.mark.parametrize("status", ["UNCONFIRMED", "REJECTED", "CONFLICT"])
def test_non_bindable_candidate_status_is_rejected(status: CandidateStatus) -> None:
    with pytest.raises(ValueError, match="cannot bind"):
        build_confirmed_input(request(effective_status=status))


def test_non_finite_decimal_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite decimal"):
        build_confirmed_input(request(value="NaN"))


def test_conflicting_field_values_are_reported_without_winner() -> None:
    first = build_confirmed_input(request(input_id="INPUT-A", value="8.0"))
    second = build_confirmed_input(request(input_id="INPUT-B", value="10.0"))
    assert validate_confirmed_input_set([first, second]) == (
        ConfirmedInputConflict(
            field="road_width_m",
            input_ids=("INPUT-A", "INPUT-B"),
            reason="DIFFERENT_VALUE_OR_UNIT",
        ),
    )


def test_duplicate_identical_values_are_rejected() -> None:
    first = build_confirmed_input(request(input_id="INPUT-A"))
    second = build_confirmed_input(request(input_id="INPUT-B"))
    conflicts = validate_confirmed_input_set([first, second])
    assert conflicts[0].reason == "DUPLICATE_ACTIVE_FIELD"


def test_confirmed_inputs_document_is_sorted_and_matches_golden() -> None:
    confirmed = build_confirmed_input(request())
    document = confirmed_inputs_document([confirmed])
    golden_path = Path("tests/golden/drawing/manual-confirmed-inputs.json")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    assert document == golden


def test_persist_confirmed_inputs_is_create_only(tmp_path: Path) -> None:
    confirmed = build_confirmed_input(request())
    entry = persist_confirmed_inputs(tmp_path, [confirmed])
    assert entry.artifact_id == "CONFIRMED-INPUTS"
    assert entry.relative_path == "confirmed-inputs.json"
    with pytest.raises(FileExistsError):
        persist_confirmed_inputs(tmp_path, [confirmed])


def test_conflicting_set_cannot_be_persisted(tmp_path: Path) -> None:
    first = build_confirmed_input(request(input_id="INPUT-A", value="8.0"))
    second = build_confirmed_input(request(input_id="INPUT-B", value="10.0"))
    with pytest.raises(ValueError, match="confirmed input conflicts"):
        persist_confirmed_inputs(tmp_path, [first, second])
