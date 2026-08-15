"""Hard abstention gates overriding confidence scores."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_GATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("missing_required_input", "MISSING_REQUIRED_INPUT"),
    ("uncited_or_unresolved_claim", "UNCITED_OR_UNRESOLVED_CLAIM"),
    ("unapproved_rule", "UNAPPROVED_RULE"),
    ("math_engine_error", "MATH_ENGINE_ERROR"),
    ("source_hash_mismatch", "SOURCE_HASH_MISMATCH"),
    ("unresolved_conflict", "UNRESOLVED_CONFLICT"),
    ("track_b_rejection", "TRACK_B_REJECTION"),
    ("machine_set_human_decision", "MACHINE_SET_HUMAN_DECISION"),
    ("unregistered_numeric_value", "UNREGISTERED_NUMERIC_VALUE"),
)
_LOW_THRESHOLD = Decimal("0.70")


@dataclass(frozen=True, slots=True)
class AbstentionContext:
    """Boolean hard-gate observations plus deterministic confidence score."""

    confidence_score: str
    missing_required_input: bool = False
    uncited_or_unresolved_claim: bool = False
    unapproved_rule: bool = False
    math_engine_error: bool = False
    source_hash_mismatch: bool = False
    unresolved_conflict: bool = False
    track_b_rejection: bool = False
    machine_set_human_decision: bool = False
    unregistered_numeric_value: bool = False


def _score(value: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("confidence_score must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("confidence_score must be a decimal string") from error
    if not result.is_finite() or result < 0 or result > 1:
        raise ValueError("confidence_score must be between 0 and 1")
    return result


def evaluate_abstention_gates(context: AbstentionContext) -> tuple[str, ...]:
    """Return every hard-gate reason in the declared policy order."""
    reasons = [code for field, code in _GATE_FIELDS if getattr(context, field)]
    if _score(context.confidence_score) < _LOW_THRESHOLD:
        reasons.append("LOW_CONFIDENCE")
    return tuple(reasons)
