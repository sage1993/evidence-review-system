from evidence_review.math_engine.formulas import FRONTAGE_RATIO_SPEC, run_calculation
from evidence_review.math_engine.manifest import formula_manifest_hash
from evidence_review.math_engine.registry import FormulaSpec


def test_formula_registration_order_does_not_change_manifest_hash() -> None:
    other = FormulaSpec(
        formula_id="OTHER",
        version="1.0.0",
        precision=16,
        rounding="ROUND_HALF_EVEN",
        input_schema={"value": "decimal-string"},
        output_policy={"kind": "decimal"},
    )
    assert formula_manifest_hash((FRONTAGE_RATIO_SPEC, other)) == formula_manifest_hash(
        (other, FRONTAGE_RATIO_SPEC)
    )


def test_calculation_result_contains_manifest_and_result_hashes() -> None:
    inputs = {
        "frontage_length_m": "30",
        "perimeter_length_m": "320",
        "threshold_ratio": "0.125",
    }
    first = run_calculation("FRONTAGE_RATIO", "1.0.0", inputs)
    second = run_calculation(
        "FRONTAGE_RATIO",
        "1.0.0",
        dict(reversed(tuple(inputs.items()))),
    )
    assert first.formula_manifest_hash is not None
    assert first.result_hash is not None
    assert first.formula_manifest_hash == second.formula_manifest_hash
    assert first.result_hash == second.result_hash
