"""Deterministic decimal threshold comparisons for review claims."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

ComparisonOperator = Literal["<", "<=", "=", "!=", ">=", ">"]
ComparisonResult = Literal["BELOW", "EQUAL", "ABOVE"]


def decimal_from_token(token: str) -> Decimal:
    """Parse a canonical numeric token without floating-point coercion."""
    if not isinstance(token, str) or not token:
        raise ValueError("numeric token must be a non-empty string")
    value = token.strip().replace(",", "")
    if value.endswith("%"):
        value = value[:-1]
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"invalid decimal token: {token}") from error
    if not result.is_finite():
        raise ValueError(f"non-finite decimal token: {token}")
    return result


def compare_decimal_tokens(left: str, right: str) -> ComparisonResult:
    """Compare two canonical numeric tokens using Decimal semantics."""
    left_value = decimal_from_token(left)
    right_value = decimal_from_token(right)
    if left_value < right_value:
        return "BELOW"
    if left_value > right_value:
        return "ABOVE"
    return "EQUAL"


def relation_holds(left: str, operator: ComparisonOperator, right: str) -> bool:
    """Return whether a deterministic decimal relation is true."""
    result = compare_decimal_tokens(left, right)
    if operator == "<":
        return result == "BELOW"
    if operator == "<=":
        return result in {"BELOW", "EQUAL"}
    if operator == "=":
        return result == "EQUAL"
    if operator == "!=":
        return result != "EQUAL"
    if operator == ">=":
        return result in {"ABOVE", "EQUAL"}
    if operator == ">":
        return result == "ABOVE"
    raise ValueError(f"unsupported comparison operator: {operator}")
