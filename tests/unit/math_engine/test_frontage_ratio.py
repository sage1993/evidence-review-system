from evidence_review.math_engine.formulas import run_calculation


def test_frontage_ratio_exact_result() -> None:
    result = run_calculation(
        "FRONTAGE_RATIO",
        "1.0.0",
        {
            "frontage_length_m": "30",
            "perimeter_length_m": "320",
            "threshold_ratio": "0.125",
        },
    )
    assert result.status == "SUCCESS"
    assert result.raw_result == "0.09375"
    assert result.display_result == "9.375%"
    assert result.comparison == "BELOW_THRESHOLD"


def test_frontage_ratio_boundary_and_display_rounding() -> None:
    at_threshold = run_calculation(
        "FRONTAGE_RATIO",
        "1.0.0",
        {
            "frontage_length_m": "1",
            "perimeter_length_m": "8",
            "threshold_ratio": "0.125",
        },
    )
    above = run_calculation(
        "FRONTAGE_RATIO",
        "1.0.0",
        {
            "frontage_length_m": "1",
            "perimeter_length_m": "3",
            "threshold_ratio": "0.125",
        },
    )
    assert at_threshold.comparison == "AT_THRESHOLD"
    assert at_threshold.display_result == "12.5%"
    assert above.comparison == "ABOVE_THRESHOLD"
    assert above.display_result == "33.333%"


def test_frontage_ratio_zero_perimeter_has_no_numeric_result() -> None:
    result = run_calculation(
        "FRONTAGE_RATIO",
        "1.0.0",
        {
            "frontage_length_m": "30",
            "perimeter_length_m": "0",
            "threshold_ratio": "0.125",
        },
    )
    assert result.status == "DIVISION_BY_ZERO"
    assert result.raw_result is None
    assert result.display_result is None


def test_calculation_result_preserves_authoritative_operands_and_rounding_policy() -> None:
    result = run_calculation(
        "FRONTAGE_RATIO",
        "1.0.0",
        {
            "frontage_length_m": "7140.85555",
            "perimeter_length_m": "4879.3",
            "threshold_ratio": "0.125",
        },
        input_sources={
            "frontage_length_m": "drawing-confirmation:CONF-001",
            "perimeter_length_m": "drawing-confirmation:CONF-001",
            "threshold_ratio": "approved-rule:ANSIM-001",
        },
        input_units={
            "frontage_length_m": "m",
            "perimeter_length_m": "m",
            "threshold_ratio": "ratio",
        },
    )

    assert result.raw_result == "1.4635"
    assert result.display_result == "146.35%"
    assert result.input_sources["frontage_length_m"].startswith("drawing-confirmation:")
    assert result.input_units["perimeter_length_m"] == "m"
    assert result.precision == 28
    assert result.rounding == "ROUND_HALF_UP"
    assert result.intermediate_rounding_policy == "NO_INTERMEDIATE_ROUNDING"
