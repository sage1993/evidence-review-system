from dataclasses import replace

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.common import BBox
from evidence_review.contracts.engines import CalculationResult
from evidence_review.contracts.evidence import EvidenceRecord
from evidence_review.math_engine.manifest import calculation_result_payload
from evidence_review.rule_engine.evaluator import evaluate_rule
from evidence_review.rule_engine.loader import load_rule


def _calculation() -> CalculationResult:
    result = CalculationResult(
        calculation_result_id="CALC-FRONTAGE",
        status="SUCCESS",
        formula_id="FRONTAGE_RATIO",
        formula_version="1.0.0",
        inputs={
            "frontage_length_m": "30",
            "perimeter_length_m": "320",
            "threshold_ratio": "0.125",
        },
        substitution="30 / 320",
        raw_result="0.09375",
        display_result="9.375%",
        comparison="BELOW_THRESHOLD",
        formula_manifest_hash="b" * 64,
    )
    return replace(result, result_hash=sha256_json(calculation_result_payload(result)))


def _unrelated_failed_calculation() -> CalculationResult:
    return CalculationResult(
        calculation_result_id="CALC-UNRELATED",
        status="ENGINE_ERROR",
        formula_id="UNRELATED",
        formula_version="1.0.0",
        inputs={},
        formula_manifest_hash="c" * 64,
        result_hash="d" * 64,
        error_codes=("ENGINE_ERROR",),
    )


def _rule():
    return load_rule(
        {
            "rule_id": "ARTERIAL-FRONTAGE",
            "version": "1.0.0",
            "title": "간선도로 접면 비율",
            "input_schema": {},
            "source_citations": [
                {
                    "citation_id": "C-FRONTAGE",
                    "document_id": "LAW1",
                    "revision_id": "REV-1",
                    "page_number": 4,
                    "evidence_id": "E-FRONTAGE",
                    "bbox": [0, 0, 10, 10],
                    "source_hash": "a" * 64,
                }
            ],
            "human_decision_required": True,
            "expression": {
                "calculation": {
                    "calculation_result_id": "CALC-FRONTAGE",
                    "field": "comparison",
                    "operator": "in",
                    "value": ["AT_THRESHOLD", "ABOVE_THRESHOLD"],
                }
            },
        }
    )


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="E-FRONTAGE",
        document_id="LAW1",
        revision_id="REV-1",
        page_number=4,
        element_id="EL-FRONTAGE",
        evidence_type="text",
        bbox=BBox(0, 0, 10, 10),
        source_hash="a" * 64,
    )


def test_frontage_rule_consumes_registered_calculation_without_recalculation() -> None:
    result = evaluate_rule(
        _rule(),
        {},
        calculations=[_calculation()],
        expected_formula_manifest_hash="b" * 64,
        evidence_records=[_evidence()],
    )
    assert result.status == "NOT_SATISFIED"
    assert result.calculation_result_ids == ("CALC-FRONTAGE",)


def test_tampered_calculation_hash_is_rejected() -> None:
    calculation = replace(_calculation(), raw_result="0.5")
    result = evaluate_rule(
        _rule(),
        {},
        calculations=[calculation],
        expected_formula_manifest_hash="b" * 64,
        evidence_records=[_evidence()],
    )
    assert result.status == "ENGINE_ERROR"
    assert result.reason_codes == ("INVALID_CALCULATION_REFERENCE",)


def test_unrelated_failed_calculation_does_not_change_rule_result() -> None:
    result = evaluate_rule(
        _rule(),
        {},
        calculations=[_calculation(), _unrelated_failed_calculation()],
        expected_formula_manifest_hash="b" * 64,
        evidence_records=[_evidence()],
    )
    assert result.status == "NOT_SATISFIED"
    assert result.calculation_result_ids == ("CALC-FRONTAGE",)
