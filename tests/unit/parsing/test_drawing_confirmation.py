from pathlib import Path

import pytest

from ansim_review.contracts.drawing import DrawingConfirmation, Geometry
from ansim_review.parsing.drawing_candidates import create_manual_candidate
from ansim_review.parsing.drawing_confirmation import (
    load_and_verify_confirmation,
    parse_confirmation_time,
    persist_confirmation,
    validate_confirmation_for_candidate,
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
            coordinates=((1.0, 2.0), (3.0, 4.0)),
        ),
        raw_value=None,
        normalized_candidate=None,
    )


def confirmation(
    *,
    action: str = "CREATED",
    confirmed_value: str | None = "8.0",
    unit: str | None = "m",
    geometry: Geometry | None = None,
) -> DrawingConfirmation:
    return DrawingConfirmation(
        confirmation_id="CONF-001",
        candidate_id=candidate().candidate_id,
        action=action,
        source_sha256="a" * 64,
        reviewer="김성현",
        confirmed_at="2026-08-02T01:30:00+09:00",
        confirmed_value=confirmed_value,
        unit=unit,
        geometry=geometry,
    )


def test_confirmation_timestamp_requires_explicit_offset() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_confirmation_time("2026-08-02T01:00:00")


def test_rejected_confirmation_is_not_bindable() -> None:
    assert validate_confirmation_for_candidate(
        candidate(), confirmation(action="REJECTED", confirmed_value=None, unit=None)
    ) == "REJECTED"


def test_created_confirmation_requires_value_or_geometry() -> None:
    with pytest.raises(ValueError, match="confirmed value or geometry"):
        validate_confirmation_for_candidate(
            candidate(),
            confirmation(action="CREATED", confirmed_value=None, unit=None),
        )


def test_confirmed_value_requires_unit() -> None:
    with pytest.raises(ValueError, match="unit is required"):
        validate_confirmation_for_candidate(
            candidate(), confirmation(confirmed_value="8.0", unit=None)
        )


def test_replacement_geometry_keeps_coordinate_system() -> None:
    replacement = Geometry(
        type="LINESTRING",
        coordinate_system="PDF_BOTTOM_LEFT_POINTS",
        coordinates=((1.0, 2.0), (3.0, 4.0)),
    )
    with pytest.raises(ValueError, match="coordinate system"):
        validate_confirmation_for_candidate(
            candidate(), confirmation(geometry=replacement)
        )


def test_confirmation_is_append_only_and_hash_bound(tmp_path: Path) -> None:
    entry = persist_confirmation(
        tmp_path, "kim-sh", candidate(), confirmation()
    )
    loaded = load_and_verify_confirmation(tmp_path, entry)
    assert loaded.action == "CREATED"
    assert entry.relative_path.startswith("confirmations/20260801T163000Z-kim-sh-")
    with pytest.raises(FileExistsError):
        persist_confirmation(tmp_path, "kim-sh", candidate(), confirmation())


def test_confirmation_tamper_is_detected(tmp_path: Path) -> None:
    entry = persist_confirmation(
        tmp_path, "kim-sh", candidate(), confirmation()
    )
    path = tmp_path / entry.relative_path
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation hash mismatch"):
        load_and_verify_confirmation(tmp_path, entry)
