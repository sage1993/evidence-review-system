"""Deterministic Decimal confidence scorer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from evidence_review.confidence.policy import (
    FACTOR_WEIGHTS,
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    POLICY_VERSION,
)
from evidence_review.contracts.review import (
    ConfidenceFactor,
    ConfidenceLevel,
    ConfidenceResult,
)

_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class FactorInput:
    """One measured confidence factor and its evidence source."""

    value: str
    source: str


def _decimal(value: str, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field} must be a decimal string") from error
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if result < 0 or result > 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return result


def _format_decimal(value: Decimal) -> str:
    return format(value.quantize(_QUANTUM, rounding=ROUND_HALF_UP), ".4f")


def score_confidence(
    factors: Mapping[str, FactorInput],
    *,
    hard_gate_failures: Sequence[str] = (),
) -> ConfidenceResult:
    """Apply Confidence Policy V1 with explicit auditable contributions."""
    expected = set(FACTOR_WEIGHTS)
    supplied = set(factors)
    missing = sorted(expected - supplied)
    extra = sorted(supplied - expected)
    if missing:
        raise ValueError(f"missing confidence factors: {', '.join(missing)}")
    if extra:
        raise ValueError(f"unknown confidence factors: {', '.join(extra)}")

    output_factors: list[ConfidenceFactor] = []
    with localcontext() as context:
        context.prec = 28
        total = Decimal("0")
        for name, weight in FACTOR_WEIGHTS.items():
            factor = factors[name]
            if not factor.source:
                raise ValueError(f"confidence factor source is required: {name}")
            value = _decimal(factor.value, name)
            contribution = value * weight
            total += contribution
            output_factors.append(
                ConfidenceFactor(
                    name=name,
                    value=_format_decimal(value),
                    weight=format(weight, ".2f"),
                    contribution=_format_decimal(contribution),
                    source=factor.source,
                )
            )
        quantized_score = total.quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    failures = tuple(hard_gate_failures)
    human_review_pending = (
        factors["human review status"].source == "human_review:pending"
    )
    level: ConfidenceLevel
    if failures or quantized_score < MEDIUM_THRESHOLD:
        level = "LOW"
    elif human_review_pending:
        level = "MEDIUM"
    elif quantized_score >= HIGH_THRESHOLD:
        level = "HIGH"
    else:
        level = "MEDIUM"
    return ConfidenceResult(
        policy_version=POLICY_VERSION,
        score=format(quantized_score, ".4f"),
        level=level,
        factors=tuple(output_factors),
        hard_gate_failures=failures,
    )
