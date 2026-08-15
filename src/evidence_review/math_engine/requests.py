"""Strict decoding for untrusted Math Engine requests."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalculationRequest:
    """Validated request containing only string-encoded decimal inputs."""

    formula_id: str
    formula_version: str
    inputs: dict[str, str]


def decode_calculation_request(value: object) -> CalculationRequest:
    """Decode a calculation request without coercing values."""
    if not isinstance(value, Mapping):
        raise ValueError("calculation request must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError("calculation request keys must be strings")
    payload = dict(value)
    unknown = sorted(set(payload) - {"formula_id", "formula_version", "inputs"})
    if unknown:
        raise ValueError(
            f"calculation request has unknown fields: {', '.join(unknown)}"
        )
    formula_id = payload.get("formula_id")
    formula_version = payload.get("formula_version")
    inputs = payload.get("inputs")
    if not isinstance(formula_id, str) or not formula_id:
        raise ValueError("formula_id must be a non-empty string")
    if not isinstance(formula_version, str) or not formula_version:
        raise ValueError("formula_version must be a non-empty string")
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs must be an object")
    decoded: dict[str, str] = {}
    for key, item in inputs.items():
        if not isinstance(key, str) or not key:
            raise ValueError("input names must be non-empty strings")
        if not isinstance(item, str):
            raise ValueError("decimal inputs must be strings")
        decoded[key] = item
    return CalculationRequest(
        formula_id=formula_id,
        formula_version=formula_version,
        inputs=dict(sorted(decoded.items())),
    )
