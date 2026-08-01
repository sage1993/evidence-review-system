"""Typed operators for constrained rule evaluation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ansim_review.rule_engine.schema import InputType, RuleOperator


class RuleInputError(ValueError):
    """Raised when a declared rule input has an invalid runtime type."""


def decode_input(value: object, value_type: InputType, field: str) -> object:
    """Decode a project input without truthy or numeric coercion."""
    if value_type == "decimal":
        if not isinstance(value, str):
            raise RuleInputError(f"{field} decimal input must be a string")
        try:
            parsed = Decimal(value)
        except InvalidOperation as error:
            raise RuleInputError(f"{field} is not a decimal") from error
        if not parsed.is_finite():
            raise RuleInputError(f"{field} must be finite")
        return parsed
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuleInputError(f"{field} must be an integer")
        return value
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise RuleInputError(f"{field} must be boolean")
        return value
    if value_type == "string":
        if not isinstance(value, str):
            raise RuleInputError(f"{field} must be a string")
        return value
    if not isinstance(value, (list, tuple)):
        raise RuleInputError(f"{field} must be an array")
    return tuple(value)


def decode_literal(value: object, value_type: InputType | None, field: str) -> object:
    """Decode a rule literal using the declared counterpart type when available."""
    if value_type is None:
        return tuple(value) if isinstance(value, list) else value
    return decode_input(value, value_type, field)


def apply_operator(operator: RuleOperator, left: object, right: object) -> bool:
    """Apply one explicitly declared operator without truthy coercion."""
    if operator == "eq":
        return type(left) is type(right) and left == right
    if operator == "ne":
        return not (type(left) is type(right) and left == right)
    if operator in {"gt", "gte", "lt", "lte"}:
        if type(left) is not type(right) or not isinstance(left, (Decimal, int, str)):
            raise RuleInputError("ordered comparison requires matching scalar types")
        if operator == "gt":
            return left > right  # type: ignore[operator]
        if operator == "gte":
            return left >= right  # type: ignore[operator]
        if operator == "lt":
            return left < right  # type: ignore[operator]
        return left <= right  # type: ignore[operator]
    if operator == "in":
        if not isinstance(right, (tuple, list, str)):
            raise RuleInputError("in requires an array or string on the right")
        return left in right  # type: ignore[operator]
    if not isinstance(left, (tuple, list, str)):
        raise RuleInputError("contains requires an array or string on the left")
    return right in left  # type: ignore[operator]
