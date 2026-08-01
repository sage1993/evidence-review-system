from __future__ import annotations

from ansim_review.abstention.gates import AbstentionContext, evaluate_abstention_gates


def test_unresolved_conflict_abstains_even_at_high_confidence() -> None:
    reasons = evaluate_abstention_gates(
        AbstentionContext(confidence_score="0.99", unresolved_conflict=True)
    )
    assert reasons == ("UNRESOLVED_CONFLICT",)


def test_all_hard_gates_are_returned_in_declared_order() -> None:
    context = AbstentionContext(
        confidence_score="0.60",
        missing_required_input=True,
        uncited_or_unresolved_claim=True,
        unapproved_rule=True,
        math_engine_error=True,
        source_hash_mismatch=True,
        unresolved_conflict=True,
        track_b_rejection=True,
        machine_set_human_decision=True,
        unregistered_numeric_value=True,
    )
    assert evaluate_abstention_gates(context) == (
        "MISSING_REQUIRED_INPUT",
        "UNCITED_OR_UNRESOLVED_CLAIM",
        "UNAPPROVED_RULE",
        "MATH_ENGINE_ERROR",
        "SOURCE_HASH_MISMATCH",
        "UNRESOLVED_CONFLICT",
        "TRACK_B_REJECTION",
        "MACHINE_SET_HUMAN_DECISION",
        "UNREGISTERED_NUMERIC_VALUE",
        "LOW_CONFIDENCE",
    )


def test_no_gate_for_medium_confidence_complete_run() -> None:
    assert evaluate_abstention_gates(AbstentionContext(confidence_score="0.70")) == ()
