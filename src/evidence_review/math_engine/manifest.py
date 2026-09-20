"""Canonical formula manifests and calculation-result hashes."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.engines import CalculationResult
from evidence_review.math_engine.registry import FormulaSpec


def formula_manifest_payload(specs: Sequence[FormulaSpec]) -> dict[str, object]:
    """Return order-independent canonical metadata for registered formulas."""
    formulas: list[dict[str, object]] = [
        {
            "formula_id": spec.formula_id,
            "version": spec.version,
            "precision": spec.precision,
            "rounding": spec.rounding,
            "input_schema": dict(sorted(spec.input_schema.items())),
            "output_policy": dict(sorted(spec.output_policy.items())),
        }
        for spec in specs
    ]
    formulas.sort(
        key=lambda item: (str(item["formula_id"]), str(item["version"]))
    )
    return {"formulas": formulas}


def formula_manifest_hash(specs: Sequence[FormulaSpec]) -> str:
    """Hash formula metadata independently of registration order."""
    return sha256_json(formula_manifest_payload(specs))


def calculation_result_payload(result: CalculationResult) -> dict[str, object]:
    """Return the canonical payload used for result hashing."""
    payload: dict[str, object] = {
        "calculation_result_id": result.calculation_result_id,
        "status": result.status,
        "formula_id": result.formula_id,
        "formula_version": result.formula_version,
        "inputs": dict(sorted(result.inputs.items())),
        "substitution": result.substitution,
        "raw_result": result.raw_result,
        "display_result": result.display_result,
        "comparison": result.comparison,
        "formula_manifest_hash": result.formula_manifest_hash,
        "error_codes": list(result.error_codes),
    }
    if result.input_sources:
        payload["input_sources"] = dict(sorted(result.input_sources.items()))
    if result.input_units:
        payload["input_units"] = dict(sorted(result.input_units.items()))
    if result.precision is not None:
        payload["precision"] = result.precision
    if result.rounding is not None:
        payload["rounding"] = result.rounding
    if result.intermediate_rounding_policy is not None:
        payload["intermediate_rounding_policy"] = result.intermediate_rounding_policy
    return payload


def finalize_result(result: CalculationResult, manifest_hash: str) -> CalculationResult:
    """Attach manifest and canonical result hashes to an immutable result."""
    with_manifest = replace(
        result,
        formula_manifest_hash=manifest_hash,
        result_hash=None,
    )
    return replace(
        with_manifest,
        result_hash=sha256_json(calculation_result_payload(with_manifest)),
    )


def calculation_result_document(result: CalculationResult) -> dict[str, object]:
    """Return the complete canonical JSON result document."""
    payload = calculation_result_payload(result)
    payload["result_hash"] = result.result_hash
    return payload
