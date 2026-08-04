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
from ansim_review.math_engine.manifest import finalize_result, formula_manifest_hash
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


DRAWING_SCALE_ID = "DRAWING_SCALE"
DRAWING_SCALE_VERSION = "1.0.0"


def _drawing_scale(inputs: Mapping[str, str]) -> CalculationResult:
    required = ("real_length", "pixel_length")
    if any(name not in inputs for name in required):
        return _error_result(
            DRAWING_SCALE_ID,
            DRAWING_SCALE_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="MISSING_INPUT",
        )
    try:
        real_length = Decimal(inputs["real_length"])
        pixel_length = Decimal(inputs["pixel_length"])
    except (InvalidOperation, ValueError):
        return _error_result(
            DRAWING_SCALE_ID,
            DRAWING_SCALE_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="INVALID_DECIMAL",
        )
    if not all(value.is_finite() for value in (real_length, pixel_length)):
        return _error_result(
            DRAWING_SCALE_ID,
            DRAWING_SCALE_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="NON_FINITE_DECIMAL",
        )
    if real_length <= 0 or pixel_length <= 0:
        return _error_result(
            DRAWING_SCALE_ID,
            DRAWING_SCALE_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="NON_POSITIVE_VALUE",
        )
    with decimal_context(precision=28, rounding="ROUND_HALF_UP"):
        scale = real_length / pixel_length
    raw_text = _decimal_text(scale)
    return CalculationResult(
        calculation_result_id=_calculation_id(
            DRAWING_SCALE_ID,
            DRAWING_SCALE_VERSION,
            inputs,
        ),
        status="SUCCESS",
        formula_id=DRAWING_SCALE_ID,
        formula_version=DRAWING_SCALE_VERSION,
        inputs=dict(sorted(inputs.items())),
        substitution=(
            f"{inputs['real_length']} / {inputs['pixel_length']} = {raw_text}"
        ),
        raw_result=raw_text,
        display_result=raw_text,
        comparison="NOT_APPLICABLE",
    )


DRAWING_SCALE_SPEC = FormulaSpec(
    formula_id=DRAWING_SCALE_ID,
    version=DRAWING_SCALE_VERSION,
    precision=28,
    rounding="ROUND_HALF_UP",
    input_schema={
        "real_length": "decimal-string",
        "pixel_length": "decimal-string",
    },
    output_policy={
        "comparison_basis": "raw_result",
        "display": "decimal-scale",
    },
    execute=_drawing_scale,
)


DRAWING_LENGTH_ID = "DRAWING_LENGTH"
DRAWING_LENGTH_VERSION = "1.0.0"


def _drawing_length(inputs: Mapping[str, str]) -> CalculationResult:
    required = ("pixel_length", "scale")
    if any(name not in inputs for name in required):
        return _error_result(
            DRAWING_LENGTH_ID,
            DRAWING_LENGTH_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="MISSING_INPUT",
        )
    try:
        pixel_length = Decimal(inputs["pixel_length"])
        scale = Decimal(inputs["scale"])
    except (InvalidOperation, ValueError):
        return _error_result(
            DRAWING_LENGTH_ID,
            DRAWING_LENGTH_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="INVALID_DECIMAL",
        )
    if not all(value.is_finite() for value in (pixel_length, scale)):
        return _error_result(
            DRAWING_LENGTH_ID,
            DRAWING_LENGTH_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="NON_FINITE_DECIMAL",
        )
    if pixel_length < 0 or scale <= 0:
        return _error_result(
            DRAWING_LENGTH_ID,
            DRAWING_LENGTH_VERSION,
            inputs,
            status="INVALID_INPUT",
            error_code="INVALID_RANGE",
        )
    with decimal_context(precision=28, rounding="ROUND_HALF_UP"):
        result_value = pixel_length * scale
    raw_text = _decimal_text(result_value)
    return CalculationResult(
        calculation_result_id=_calculation_id(
            DRAWING_LENGTH_ID,
            DRAWING_LENGTH_VERSION,
            inputs,
        ),
        status="SUCCESS",
        formula_id=DRAWING_LENGTH_ID,
        formula_version=DRAWING_LENGTH_VERSION,
        inputs=dict(sorted(inputs.items())),
        substitution=(
            f"{inputs['pixel_length']} * {inputs['scale']} = {raw_text}"
        ),
        raw_result=raw_text,
        display_result=raw_text,
        comparison="NOT_APPLICABLE",
    )


DRAWING_LENGTH_SPEC = FormulaSpec(
    formula_id=DRAWING_LENGTH_ID,
    version=DRAWING_LENGTH_VERSION,
    precision=28,
    rounding="ROUND_HALF_UP",
    input_schema={
        "pixel_length": "decimal-string",
        "scale": "decimal-string",
    },
    output_policy={
        "comparison_basis": "raw_result",
        "display": "decimal-length",
    },
    execute=_drawing_length,
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

DRAWING_REGISTRY = FormulaRegistry()
DRAWING_REGISTRY.register(DRAWING_SCALE_SPEC)
DRAWING_REGISTRY.register(DRAWING_LENGTH_SPEC)


def run_calculation(
    formula_id: str,
    version: str,
    inputs: Mapping[str, str],
    *,
    registry: FormulaRegistry = DEFAULT_REGISTRY,
) -> CalculationResult:
    """Run a registered deterministic calculation."""
    manifest_hash = formula_manifest_hash(registry.values())
    spec = registry.get(formula_id, version)
    if spec is None or spec.execute is None:
        result = _error_result(
            formula_id,
            version,
            inputs,
            status="FORMULA_NOT_FOUND",
            error_code="FORMULA_NOT_FOUND",
        )
    else:
        result = spec.execute(inputs)
    return finalize_result(result, manifest_hash)
