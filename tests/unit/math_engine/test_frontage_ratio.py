from ansim_review.math_engine.formulas import run_calculation


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
