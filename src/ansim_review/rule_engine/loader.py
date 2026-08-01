"""Strict JSON loader for constrained Rule-as-Code documents."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from ansim_review.contracts.common import BBox, Citation
from ansim_review.rule_engine.schema import InputFieldSpec, InputType, RuleOperator, RuleSpec

_ALLOWED_NODES = frozenset({"all", "any", "not", "compare", "exists", "calculation"})
_ALLOWED_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"})
_ALLOWED_INPUT_TYPES = frozenset({"string", "decimal", "integer", "boolean", "array"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _reject_unknown(payload: Mapping[str, object], allowed: set[str], field: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")


def _load_citation(value: object, index: int) -> Citation:
    payload = _mapping(value, f"source_citations[{index}]")
    _reject_unknown(
        payload,
        {
            "citation_id",
            "document_id",
            "revision_id",
            "page_number",
            "evidence_id",
            "bbox",
            "source_hash",
        },
        f"source_citations[{index}]",
    )
    page_number = payload.get("page_number")
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise ValueError("source citation page_number must be a positive integer")
    bbox_items = _sequence(payload.get("bbox"), f"source_citations[{index}].bbox")
    if len(bbox_items) != 4 or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in bbox_items
    ):
        raise ValueError("source citation bbox must contain four numbers")
    source_hash = _string(payload.get("source_hash"), "source_hash")
    if not _SHA256.fullmatch(source_hash):
        raise ValueError("source citation source_hash must be a lowercase SHA-256 digest")
    return Citation(
        citation_id=_string(payload.get("citation_id"), "citation_id"),
        document_id=_string(payload.get("document_id"), "document_id"),
        revision_id=_string(payload.get("revision_id"), "revision_id"),
        page_number=page_number,
        evidence_id=_string(payload.get("evidence_id"), "evidence_id"),
        bbox=BBox(
            left=float(cast(int | float, bbox_items[0])),
            bottom=float(cast(int | float, bbox_items[1])),
            right=float(cast(int | float, bbox_items[2])),
            top=float(cast(int | float, bbox_items[3])),
        ),
        source_hash=source_hash,
    )


def _validate_operand(value: object, field: str) -> dict[str, object]:
    payload = _mapping(value, field)
    if len(payload) != 1:
        raise ValueError(f"{field} must contain exactly one operand type")
    kind = next(iter(payload))
    if kind == "input":
        return {"input": _string(payload[kind], f"{field}.input")}
    if kind == "literal":
        literal = payload[kind]
        if isinstance(literal, (dict, tuple, set)):
            raise ValueError(f"{field}.literal has unsupported value")
        if isinstance(literal, list):
            if any(isinstance(item, (dict, list, tuple, set)) for item in literal):
                raise ValueError(f"{field}.literal array must contain scalar values")
            return {"literal": list(literal)}
        return {"literal": literal}
    raise ValueError(f"unsupported rule operand: {kind}")


def _validate_node(value: object, field: str = "expression") -> dict[str, object]:
    payload = _mapping(value, field)
    if len(payload) != 1:
        raise ValueError(f"{field} must contain exactly one rule node")
    node_type = next(iter(payload))
    if node_type not in _ALLOWED_NODES:
        raise ValueError(f"unsupported rule node: {node_type}")
    body = payload[node_type]
    if node_type in {"all", "any"}:
        children = _sequence(body, f"{field}.{node_type}")
        if not children:
            raise ValueError(f"{node_type} requires at least one child")
        return {node_type: [_validate_node(child, f"{field}.{node_type}") for child in children]}
    if node_type == "not":
        return {"not": _validate_node(body, f"{field}.not")}
    node = _mapping(body, f"{field}.{node_type}")
    if node_type == "exists":
        _reject_unknown(node, {"input"}, f"{field}.exists")
        return {"exists": {"input": _string(node.get("input"), f"{field}.exists.input")}}
    if node_type == "compare":
        _reject_unknown(node, {"operator", "left", "right"}, f"{field}.compare")
        operator = _string(node.get("operator"), f"{field}.compare.operator")
        if operator not in _ALLOWED_OPERATORS:
            raise ValueError(f"unsupported rule operator: {operator}")
        return {
            "compare": {
                "operator": cast(RuleOperator, operator),
                "left": _validate_operand(node.get("left"), f"{field}.compare.left"),
                "right": _validate_operand(node.get("right"), f"{field}.compare.right"),
            }
        }
    _reject_unknown(
        node,
        {"calculation_result_id", "field", "operator", "value"},
        f"{field}.calculation",
    )
    operator = _string(node.get("operator"), f"{field}.calculation.operator")
    if operator not in _ALLOWED_OPERATORS:
        raise ValueError(f"unsupported rule operator: {operator}")
    field_name = _string(node.get("field"), f"{field}.calculation.field")
    if field_name not in {"status", "raw_result", "display_result", "comparison"}:
        raise ValueError(f"unsupported calculation field: {field_name}")
    expected = node.get("value")
    if isinstance(expected, (dict, tuple, set)):
        raise ValueError("calculation value must be a scalar or scalar array")
    return {
        "calculation": {
            "calculation_result_id": _string(
                node.get("calculation_result_id"), f"{field}.calculation.calculation_result_id"
            ),
            "field": field_name,
            "operator": cast(RuleOperator, operator),
            "value": expected,
        }
    }


def load_rule(value: object) -> RuleSpec:
    """Decode and validate one constrained rule document."""
    payload = _mapping(value, "rule")
    _reject_unknown(
        payload,
        {
            "rule_id",
            "version",
            "title",
            "input_schema",
            "source_citations",
            "human_decision_required",
            "expression",
            "approval",
        },
        "rule",
    )
    if payload.get("human_decision_required") is not True:
        raise ValueError("human_decision_required must be true")
    schema_payload = _mapping(payload.get("input_schema"), "input_schema")
    input_schema: dict[str, InputFieldSpec] = {}
    for name, item in sorted(schema_payload.items()):
        field_payload = _mapping(item, f"input_schema.{name}")
        _reject_unknown(field_payload, {"type", "required"}, f"input_schema.{name}")
        value_type = _string(field_payload.get("type"), f"input_schema.{name}.type")
        if value_type not in _ALLOWED_INPUT_TYPES:
            raise ValueError(f"unsupported input type: {value_type}")
        required = field_payload.get("required")
        if not isinstance(required, bool):
            raise ValueError(f"input_schema.{name}.required must be boolean")
        input_schema[name] = InputFieldSpec(cast(InputType, value_type), required)
    citation_items = _sequence(payload.get("source_citations"), "source_citations")
    if not citation_items:
        raise ValueError("source_citations must not be empty")
    citations = tuple(_load_citation(item, index) for index, item in enumerate(citation_items))
    return RuleSpec(
        rule_id=_string(payload.get("rule_id"), "rule_id"),
        version=_string(payload.get("version"), "version"),
        title=_string(payload.get("title"), "title"),
        input_schema=input_schema,
        source_citations=citations,
        human_decision_required=True,
        expression=_validate_node(payload.get("expression")),
    )
