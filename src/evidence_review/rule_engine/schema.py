"""Immutable contracts for constrained executable rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from evidence_review.contracts.common import Citation

InputType = Literal["string", "decimal", "integer", "boolean", "array"]
RuleOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]


@dataclass(frozen=True, slots=True)
class InputFieldSpec:
    """Declared project input accepted by a rule."""

    value_type: InputType
    required: bool


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """Human-approved constrained rule definition."""

    rule_id: str
    version: str
    title: str
    input_schema: dict[str, InputFieldSpec]
    source_citations: tuple[Citation, ...]
    human_decision_required: bool
    expression: dict[str, object]
