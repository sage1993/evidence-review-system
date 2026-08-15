"""Deterministic calculation and rule-engine contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from evidence_review.contracts.common import Citation

CalculationStatus = Literal[
    "SUCCESS",
    "INVALID_INPUT",
    "DIVISION_BY_ZERO",
    "FORMULA_NOT_FOUND",
    "ENGINE_ERROR",
]
CalculationComparison = Literal[
    "BELOW_THRESHOLD",
    "AT_THRESHOLD",
    "ABOVE_THRESHOLD",
    "EQUAL",
    "NOT_EQUAL",
    "NOT_APPLICABLE",
]
RuleStatus = Literal[
    "SATISFIED",
    "NOT_SATISFIED",
    "INDETERMINATE",
    "NOT_APPLICABLE",
    "ENGINE_ERROR",
]


@dataclass(frozen=True, slots=True)
class CalculationResult:
    """Versioned Math Engine result with a complete calculation trace."""

    calculation_result_id: str
    status: CalculationStatus
    formula_id: str
    formula_version: str
    inputs: dict[str, str] = field(default_factory=dict)
    substitution: str | None = None
    raw_result: str | None = None
    display_result: str | None = None
    comparison: CalculationComparison | None = None
    formula_manifest_hash: str | None = None
    result_hash: str | None = None
    error_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleResult:
    """Source-backed deterministic rule evaluation."""

    rule_result_id: str
    rule_id: str
    rule_version: str
    status: RuleStatus
    citations: tuple[Citation, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    calculation_result_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    result_hash: str | None = None
