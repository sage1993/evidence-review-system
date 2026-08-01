"""Deterministic evaluator for constrained source-backed rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import cast

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.engines import CalculationResult, RuleResult, RuleStatus
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.math_engine.manifest import calculation_result_payload
from ansim_review.rule_engine.operators import (
    RuleInputError,
    apply_operator,
    decode_input,
    decode_literal,
)
from ansim_review.rule_engine.schema import InputType, RuleOperator, RuleSpec


class CalculationReferenceError(ValueError):
    """Raised when a rule references an invalid Math Engine result."""


def _citation_payload(rule: RuleSpec) -> list[dict[str, object]]:
    return [asdict(citation) for citation in rule.source_citations]


def _citation_payload_from_result(result: RuleResult) -> list[dict[str, object]]:
    return [asdict(citation) for citation in result.citations]


def _result_payload(result: RuleResult) -> dict[str, object]:
    return {
        "rule_result_id": result.rule_result_id,
        "rule_id": result.rule_id,
        "rule_version": result.rule_version,
        "status": result.status,
        "citations": _citation_payload_from_result(result),
        "missing_inputs": list(result.missing_inputs),
        "calculation_result_ids": list(result.calculation_result_ids),
        "reason_codes": list(result.reason_codes),
    }


def _finalize(
    rule: RuleSpec,
    status: RuleStatus,
    *,
    missing_inputs: tuple[str, ...] = (),
    calculation_result_ids: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = (),
) -> RuleResult:
    identity_payload = {
        "rule_id": rule.rule_id,
        "rule_version": rule.version,
        "status": status,
        "citations": _citation_payload(rule),
        "missing_inputs": list(missing_inputs),
        "calculation_result_ids": list(calculation_result_ids),
        "reason_codes": list(reason_codes),
    }
    result_id = f"RULE-{sha256_json(identity_payload)[:20].upper()}"
    result = RuleResult(
        rule_result_id=result_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        status=status,
        citations=rule.source_citations,
        missing_inputs=missing_inputs,
        calculation_result_ids=calculation_result_ids,
        reason_codes=reason_codes,
        result_hash=None,
    )
    return replace(result, result_hash=sha256_json(_result_payload(result)))


def _input_names(node: Mapping[str, object]) -> set[str]:
    node_type = next(iter(node))
    body = node[node_type]
    if node_type in {"all", "any"}:
        children = cast(Sequence[object], body)
        return set().union(
            *(_input_names(cast(Mapping[str, object], item)) for item in children)
        )
    if node_type == "not":
        return _input_names(cast(Mapping[str, object], body))
    if node_type == "exists":
        return {str(cast(Mapping[str, object], body)["input"])}
    if node_type == "compare":
        names: set[str] = set()
        compare = cast(Mapping[str, object], body)
        for side in ("left", "right"):
            operand = cast(Mapping[str, object], compare[side])
            if "input" in operand:
                names.add(str(operand["input"]))
        return names
    return set()


def _resolve_operand(
    operand: Mapping[str, object],
    inputs: Mapping[str, object],
    rule: RuleSpec,
    counterpart_type: InputType | None = None,
) -> tuple[object, InputType | None]:
    if "input" in operand:
        name = str(operand["input"])
        spec = rule.input_schema[name]
        return decode_input(inputs[name], spec.value_type, name), spec.value_type
    return decode_literal(operand.get("literal"), counterpart_type, "literal"), counterpart_type


def _evaluate_node(
    node: Mapping[str, object],
    rule: RuleSpec,
    inputs: Mapping[str, object],
    calculations: Mapping[str, CalculationResult],
) -> tuple[bool, tuple[str, ...]]:
    node_type = next(iter(node))
    body = node[node_type]
    if node_type == "all":
        all_calc_ids: set[str] = set()
        for child in cast(Sequence[Mapping[str, object]], body):
            passed, child_ids = _evaluate_node(child, rule, inputs, calculations)
            all_calc_ids.update(child_ids)
            if not passed:
                return False, tuple(sorted(all_calc_ids))
        return True, tuple(sorted(all_calc_ids))
    if node_type == "any":
        any_calc_ids: set[str] = set()
        for child in cast(Sequence[Mapping[str, object]], body):
            passed, child_ids = _evaluate_node(child, rule, inputs, calculations)
            any_calc_ids.update(child_ids)
            if passed:
                return True, tuple(sorted(any_calc_ids))
        return False, tuple(sorted(any_calc_ids))
    if node_type == "not":
        passed, child_calc_ids = _evaluate_node(
            cast(Mapping[str, object], body), rule, inputs, calculations
        )
        return not passed, child_calc_ids
    if node_type == "exists":
        name = str(cast(Mapping[str, object], body)["input"])
        return name in inputs and inputs[name] is not None, ()
    if node_type == "calculation":
        calculation_node = cast(Mapping[str, object], body)
        calculation_id = str(calculation_node["calculation_result_id"])
        calculation = calculations.get(calculation_id)
        if calculation is None:
            raise CalculationReferenceError("calculation result not found")
        field_name = str(calculation_node["field"])
        actual = getattr(calculation, field_name)
        expected = calculation_node.get("value")
        if isinstance(expected, list):
            expected = tuple(expected)
        return (
            apply_operator(
                cast(RuleOperator, calculation_node["operator"]), actual, expected
            ),
            (calculation_id,),
        )
    compare = cast(Mapping[str, object], body)
    left_operand = cast(Mapping[str, object], compare["left"])
    right_operand = cast(Mapping[str, object], compare["right"])
    left_type = (
        rule.input_schema[str(left_operand["input"])].value_type
        if "input" in left_operand
        else None
    )
    right_type = (
        rule.input_schema[str(right_operand["input"])].value_type
        if "input" in right_operand
        else None
    )
    left, resolved_left_type = _resolve_operand(left_operand, inputs, rule, right_type)
    right, _ = _resolve_operand(right_operand, inputs, rule, resolved_left_type or left_type)
    return apply_operator(cast(RuleOperator, compare["operator"]), left, right), ()


def _sources_resolved(rule: RuleSpec, evidence_records: Sequence[EvidenceRecord]) -> bool:
    evidence_map = {record.evidence_id: record for record in evidence_records}
    for citation in rule.source_citations:
        record = evidence_map.get(citation.evidence_id)
        if record is None:
            return False
        if (
            record.document_id != citation.document_id
            or record.revision_id != citation.revision_id
            or record.page_number != citation.page_number
            or record.bbox != citation.bbox
            or record.source_hash != citation.source_hash
        ):
            return False
    return True


def evaluate_rule(
    rule: RuleSpec,
    inputs: Mapping[str, object],
    *,
    calculations: Sequence[CalculationResult] = (),
    expected_formula_manifest_hash: str | None = None,
    evidence_records: Sequence[EvidenceRecord] = (),
) -> RuleResult:
    """Evaluate a rule and return an immutable, canonically hashed result."""
    if not _sources_resolved(rule, evidence_records):
        return _finalize(
            rule,
            "ENGINE_ERROR",
            reason_codes=("UNRESOLVED_RULE_SOURCE",),
        )
    referenced = _input_names(rule.expression)
    required = {name for name, spec in rule.input_schema.items() if spec.required}
    missing = tuple(sorted(name for name in referenced | required if name not in inputs))
    if missing:
        return _finalize(
            rule,
            "INDETERMINATE",
            missing_inputs=missing,
            reason_codes=("MISSING_REQUIRED_INPUT",),
        )
    calculation_map = {item.calculation_result_id: item for item in calculations}
    for calculation in calculation_map.values():
        if (
            calculation.status != "SUCCESS"
            or expected_formula_manifest_hash is None
            or calculation.formula_manifest_hash != expected_formula_manifest_hash
            or calculation.result_hash is None
            or calculation.result_hash != sha256_json(calculation_result_payload(calculation))
        ):
            return _finalize(
                rule,
                "ENGINE_ERROR",
                reason_codes=("INVALID_CALCULATION_REFERENCE",),
            )
    try:
        passed, calculation_ids = _evaluate_node(rule.expression, rule, inputs, calculation_map)
    except CalculationReferenceError:
        return _finalize(
            rule,
            "ENGINE_ERROR",
            reason_codes=("INVALID_CALCULATION_REFERENCE",),
        )
    except RuleInputError:
        return _finalize(rule, "ENGINE_ERROR", reason_codes=("INVALID_RULE_INPUT",))
    return _finalize(
        rule,
        "SATISFIED" if passed else "NOT_SATISFIED",
        calculation_result_ids=calculation_ids,
        reason_codes=("EVALUATED_TRUE" if passed else "EVALUATED_FALSE",),
    )
