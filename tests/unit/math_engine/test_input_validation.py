import pytest

from evidence_review.math_engine.registry import FormulaRegistry, FormulaSpec
from evidence_review.math_engine.requests import decode_calculation_request
from evidence_review.math_engine.runner import run_calculation_request


def test_float_input_is_rejected_by_request_decoder() -> None:
    with pytest.raises(ValueError, match="decimal inputs must be strings"):
        decode_calculation_request(
            {
                "formula_id": "FRONTAGE_RATIO",
                "formula_version": "1.0.0",
                "inputs": {
                    "frontage_length_m": 30.0,
                    "perimeter_length_m": "320",
                    "threshold_ratio": "0.125",
                },
            }
        )


def test_zero_denominator_returns_structured_error() -> None:
    request = decode_calculation_request(
        {
            "formula_id": "FRONTAGE_RATIO",
            "formula_version": "1.0.0",
            "inputs": {
                "frontage_length_m": "30",
                "perimeter_length_m": "0",
                "threshold_ratio": "0.125",
            },
        }
    )
    result = run_calculation_request(request)
    assert result.status == "DIVISION_BY_ZERO"
    assert result.raw_result is None
    assert result.display_result is None
    assert result.error_codes == ("DIVISION_BY_ZERO",)


def test_unknown_formula_returns_formula_not_found() -> None:
    request = decode_calculation_request(
        {"formula_id": "UNKNOWN", "formula_version": "1.0.0", "inputs": {}}
    )
    result = run_calculation_request(request)
    assert result.status == "FORMULA_NOT_FOUND"


def test_unexpected_formula_failure_returns_engine_error() -> None:
    def fail(_inputs: object) -> object:
        raise RuntimeError("unexpected")

    registry = FormulaRegistry()
    registry.register(
        FormulaSpec(
            formula_id="FAIL",
            version="1.0.0",
            precision=28,
            rounding="ROUND_HALF_UP",
            input_schema={},
            output_policy={},
            execute=fail,  # type: ignore[arg-type]
        )
    )
    request = decode_calculation_request(
        {"formula_id": "FAIL", "formula_version": "1.0.0", "inputs": {}}
    )
    result = run_calculation_request(request, registry=registry)
    assert result.status == "ENGINE_ERROR"
    assert result.error_codes == ("ENGINE_ERROR",)
