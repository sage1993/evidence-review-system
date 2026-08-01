"""Structured Math Engine request execution."""
from __future__ import annotations

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.engines import CalculationResult
from ansim_review.math_engine.formulas import DEFAULT_REGISTRY, run_calculation
from ansim_review.math_engine.registry import FormulaRegistry
from ansim_review.math_engine.requests import CalculationRequest, decode_calculation_request


def _engine_error(request: CalculationRequest) -> CalculationResult:
    digest = sha256_json(
        {
            "formula_id": request.formula_id,
            "formula_version": request.formula_version,
            "inputs": request.inputs,
        }
    )
    return CalculationResult(
        calculation_result_id=f"CALC-{digest[:20].upper()}",
        status="ENGINE_ERROR",
        formula_id=request.formula_id,
        formula_version=request.formula_version,
        inputs=request.inputs,
        error_codes=("ENGINE_ERROR",),
    )


def run_calculation_request(
    request: CalculationRequest,
    *,
    registry: FormulaRegistry = DEFAULT_REGISTRY,
) -> CalculationResult:
    """Execute one request and convert unexpected failures to ENGINE_ERROR."""
    try:
        return run_calculation(
            request.formula_id,
            request.formula_version,
            request.inputs,
            registry=registry,
        )
    except Exception:
        return _engine_error(request)


def run_calculation_payload(
    payload: object,
    *,
    registry: FormulaRegistry = DEFAULT_REGISTRY,
) -> CalculationResult:
    """Decode and execute one untrusted JSON-compatible payload."""
    request = decode_calculation_request(payload)
    return run_calculation_request(request, registry=registry)
