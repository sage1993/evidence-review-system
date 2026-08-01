"""Built-in deterministic formulas."""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import cast

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.engines import (
    CalculationComparison,
    CalculationResult,
    CalculationStatus,
)
from ansim_review.math_engine.decimal_context import decimal_context
from ansim_review.math_engine.registry import FormulaRegistry, FormulaSpec

FRONTAGE_RATIO_ID = "FRONTAGE_RATIO"
FRONTAGE_RATIO_VERSION = "1.0.0"


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _calculation_id(formula_id: str, version: str, inputs: Mapping[str, str]) -> str:
    digest = sha256_json(
        {
            "formula_id": formula_id,
            "formula_version": version,
            "inputs": dict(sorted(inputs.items())),
        }
    )
    return f"CALC-{digest[:20].upper()}"


def _error_result(
    formula_id: str,
    version: str,
    inputs: Mapping[str, str],
    *,
    status: str,
    error_code: str,
) -> CalculationResult:
    return CalculationResult(
        calculation_result_id=_calculation_id(formula_id, version, inputs),
        status=cast(CalculationStatus, status),
        formula_id=formula_id,
        formula_version=version,
        inputs=dict(sorted(inputs.items())),
        error_codes=(error_code,),
    )


def _frontage_ratio(inputs: Mapping[str, str]) -> CalculationResult:
    required = ("frontage_length_m", "perimeter_length_m", "threshold_ratio")
    if any(name not in inputs for name in required):
        return _error_result(
            FRONTAGE_RATIO_ID,
            FRONTAGE_RATIO_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="MISSING_INPUT",
        )
    try:
        frontage = Decimal(inputs["frontage_length_m"])
        perimeter = Decimal(inputs["perimeter_length_m"])
        threshold = Decimal(inputs["threshold_ratio"])
    except (InvalidOperation, ValueError):
        return _error_result(
            FRONTAGE_RATIO_ID,
            FRONTAGE_RATIO_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="INVALID_DECIMAL",
        )
    if not all(value.is_finite() for value in (frontage, perimeter, threshold)):
        return _error_result(
            FRONTAGE_RATIO_ID,
            FRONTAGE_RATIO_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="NON_FINITE_DECIMAL",
        )
    if perimeter == 0:
        return _error_result(
            FRONTAGE_RATIO_ID,
            FRONTAGE_RATIO_VERSION,
            inputs,
            status="DIVISION_BY_ZERO",
            error_code="DIVISION_BY_ZERO",
        )
    if frontage < 0 or perimeter < 0 or threshold < 0:
        return _error_result(
            FRONTAGE_RATIO_ID,
            FRONTAGE_RATIO_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="NEGATIVE_VALUE",
        )

    with decimal_context(precision=28, rounding="ROUND_HALF_UP"):
        ratio = frontage / perimeter
        display_percent = (ratio * Decimal("100")).quantize(Decimal("0.001"))
    if ratio < threshold:
        comparison: CalculationComparison = "BELOW_THRESHOLD"
    elif ratio > threshold:
        comparison = "ABOVE_THRESHOLD"
    else:
        comparison = "AT_THRESHOLD"
    raw_text = _decimal_text(ratio)
    return CalculationResult(
        calculation_result_id=_calculation_id(
            FRONTAGE_RATIO_ID,
            FRONTAGE_RATIO_VERSION,
            inputs,
        ),
        status="SUCCESS",
        formula_id=FRONTAGE_RATIO_ID,
        formula_version=FRONTAGE_RATIO_VERSION,
        inputs=dict(sorted(inputs.items())),
        substitution=(
            f"{inputs['frontage_length_m']} / "
            f"{inputs['perimeter_length_m']} = {raw_text}"
        ),
        raw_result=raw_text,
        display_result=f"{_decimal_text(display_percent)}%",
        comparison=comparison,
    )


FRONTAGE_RATIO_SPEC = FormulaSpec(
    formula_id=FRONTAGE_RATIO_ID,
    version=FRONTAGE_RATIO_VERSION,
    precision=28,
    rounding="ROUND_HALF_UP",
    input_schema={
        "frontage_length_m": "decimal-string",
        "perimeter_length_m": "decimal-string",
        "threshold_ratio": "decimal-string",
    },
    output_policy={
        "comparison_basis": "raw_result",
        "display": "percent-max-3-decimals-strip-trailing-zeros",
    },
    execute=_frontage_ratio,
)

DEFAULT_REGISTRY = FormulaRegistry()
DEFAULT_REGISTRY.register(FRONTAGE_RATIO_SPEC)


def run_calculation(
    formula_id: str,
    version: str,
    inputs: Mapping[str, str],
    *,
    registry: FormulaRegistry = DEFAULT_REGISTRY,
) -> CalculationResult:
    """Run a registered deterministic calculation."""
    spec = registry.get(formula_id, version)
    if spec is None or spec.execute is None:
        return _error_result(
            formula_id,
            version,
            inputs,
            status="FORMULA_NOT_FOUND",
            error_code="FORMULA_NOT_FOUND",
        )
    return spec.execute(inputs)
