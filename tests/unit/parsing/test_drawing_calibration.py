from __future__ import annotations

import pytest

from evidence_review.parsing.drawing_calibration import (
    CalibrationReference,
    build_calibration,
    calculate_real_length,
    calibration_document,
    decode_calibration,
)

SOURCE_HASH = "a" * 64


def test_build_calibration_uses_confirmed_reference_and_math_formula() -> None:
    result = build_calibration(
        source_sha256=SOURCE_HASH,
        page=1,
        references=(
            CalibrationReference(
                pixel_points=((10, 20), (110, 20)),
                real_length="35.0",
                unit="m",
                axis="x",
            ),
        ),
        reviewer="kim-sh",
        confirmed_at="2026-08-05T10:00:00+09:00",
    )

    assert result.reviewer_confirmed is True
    assert result.scale_x == "0.35"
    assert result.scale_y is None
    assert result.formula_id == "DRAWING_SCALE"
    assert result.formula_version == "1.0.0"
    assert result.calculation_result_hash
    assert result.source_sha256 == SOURCE_HASH
    assert calculate_real_length(result, pixel_length="20", axis="x") == "7"


def test_calibration_rejects_missing_or_ambiguous_reference() -> None:
    with pytest.raises(ValueError, match="decimal string"):
        CalibrationReference(
            pixel_points=((10, 20), (110, 20)),
            real_length=35.0,  # type: ignore[arg-type]
            unit="m",
            axis="x",
        )


def test_calibration_rejects_whitespace_only_reviewer_before_persistence() -> None:
    with pytest.raises(ValueError, match="reviewer"):
        build_calibration(
            source_sha256=SOURCE_HASH,
            page=1,
            references=(
                CalibrationReference(
                    pixel_points=((10, 20), (110, 20)),
                    real_length="35.0",
                    unit="m",
                    axis="x",
                ),
            ),
            reviewer="   ",
            confirmed_at="2026-08-05T10:00:00+09:00",
        )


def test_browser_calibration_persists_candidate_and_confirmation_bindings() -> None:
    result = build_calibration(
        source_sha256=SOURCE_HASH,
        page=1,
        references=(
            CalibrationReference(
                pixel_points=((10, 20), (110, 20)),
                real_length="35.0",
                unit="m",
                axis="x",
            ),
        ),
        reviewer="kim-sh",
        confirmed_at="2026-08-05T10:00:00+09:00",
        candidate_id="CAND-EXISTING",
        confirmation_id="CONF-EXISTING",
    )

    document = calibration_document(result)
    assert document["candidate_id"] == "CAND-EXISTING"
    assert document["confirmation_id"] == "CONF-EXISTING"

    assert decode_calibration(document) == result

    with pytest.raises(ValueError, match="at least one"):
        build_calibration(
            source_sha256=SOURCE_HASH,
            page=1,
            references=(),
            reviewer="kim-sh",
            confirmed_at="2026-08-05T10:00:00+09:00",
        )

    with pytest.raises(ValueError, match="axis"):
        build_calibration(
            source_sha256=SOURCE_HASH,
            page=1,
            references=(
                CalibrationReference(
                    pixel_points=((10, 20), (110, 120)),
                    real_length="35.0",
                    unit="m",
                    axis="x",
                ),
            ),
            reviewer="kim-sh",
            confirmed_at="2026-08-05T10:00:00+09:00",
        )
