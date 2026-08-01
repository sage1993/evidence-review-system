"""Deterministic Ansim golden-case orchestration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ansim_review.abstention.gates import AbstentionContext, evaluate_abstention_gates
from ansim_review.confidence.policy import FACTOR_WEIGHTS
from ansim_review.confidence.scorer import FactorInput, score_confidence
from ansim_review.math_engine.runner import run_calculation_payload


def _bool(flags: Mapping[str, object], name: str) -> bool:
    value = flags.get(name, False)
    if not isinstance(value, bool):
        raise ValueError(f"flag {name} must be boolean")
    return value


def run_golden_case(case: Mapping[str, object]) -> dict[str, object]:
    """Run deterministic calculation, confidence, and abstention fields."""
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case_id is required")
    confidence_value = case.get("confidence_value", "1")
    if not isinstance(confidence_value, str):
        raise ValueError("confidence_value must be a decimal string")
    factors = {
        name: FactorInput(confidence_value, f"golden:{case_id}:{name}")
        for name in FACTOR_WEIGHTS
    }
    confidence = score_confidence(factors)
    flags_value = case.get("flags", {})
    if not isinstance(flags_value, Mapping):
        raise ValueError("flags must be an object")
    flags = cast(Mapping[str, object], flags_value)
    calculation_payload = case.get("calculation")
    calculation_document: dict[str, object] | None = None
    math_error = _bool(flags, "math_engine_error")
    if calculation_payload is not None:
        calculation = run_calculation_payload(calculation_payload)
        math_error = math_error or calculation.status != "SUCCESS"
        calculation_document = {
            "calculation_result_id": calculation.calculation_result_id,
            "status": calculation.status,
            "raw_result": calculation.raw_result,
            "display_result": calculation.display_result,
            "comparison": calculation.comparison,
        }
    context = AbstentionContext(
        confidence_score=confidence.score,
        missing_required_input=_bool(flags, "missing_required_input"),
        uncited_or_unresolved_claim=_bool(flags, "uncited_or_unresolved_claim"),
        unapproved_rule=_bool(flags, "unapproved_rule"),
        math_engine_error=math_error,
        source_hash_mismatch=_bool(flags, "source_hash_mismatch"),
        unresolved_conflict=_bool(flags, "unresolved_conflict"),
        track_b_rejection=_bool(flags, "track_b_rejection"),
        machine_set_human_decision=False,
        unregistered_numeric_value=_bool(flags, "unregistered_numeric_value"),
    )
    reasons = evaluate_abstention_gates(context)
    retrieval_ids = case.get("retrieval_ids", [])
    if not isinstance(retrieval_ids, list) or not all(
        isinstance(item, str) for item in retrieval_ids
    ):
        raise ValueError("retrieval_ids must be an array of strings")
    rule_status = case.get("rule_status")
    if not isinstance(rule_status, str):
        raise ValueError("rule_status is required")
    return {
        "case_id": case_id,
        "retrieval_ids": retrieval_ids,
        "calculation": calculation_document,
        "rule_status": rule_status,
        "confidence": {
            "score": confidence.score,
            "level": "LOW" if reasons else confidence.level,
            "factors": [
                {
                    "name": factor.name,
                    "value": factor.value,
                    "weight": factor.weight,
                    "contribution": factor.contribution,
                    "source": factor.source,
                }
                for factor in confidence.factors
            ],
        },
        "abstention_reasons": list(reasons),
        "final_status": "ABSTAIN" if reasons else "READY_FOR_HUMAN_REVIEW",
        "human_decision": None,
    }
