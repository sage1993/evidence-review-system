from ansim_review.contracts.common import BBox
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.rule_engine.evaluator import evaluate_rule
from ansim_review.rule_engine.loader import load_rule


def _rule():
    return load_rule(
        {
            "rule_id": "MIN-SITE-AREA",
            "version": "1.0.0",
            "title": "최소 대지면적",
            "input_schema": {"site_area_m2": {"type": "decimal", "required": True}},
            "source_citations": [
                {
                    "citation_id": "C-AREA",
                    "document_id": "LAW1",
                    "revision_id": "REV-1",
                    "page_number": 3,
                    "evidence_id": "E-AREA",
                    "bbox": [1, 2, 3, 4],
                    "source_hash": "a" * 64,
                }
            ],
            "human_decision_required": True,
            "expression": {
                "compare": {
                    "operator": "gte",
                    "left": {"input": "site_area_m2"},
                    "right": {"literal": "1500"},
                }
            },
        }
    )


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="E-AREA",
        document_id="LAW1",
        revision_id="REV-1",
        page_number=3,
        element_id="EL-AREA",
        evidence_type="text",
        bbox=BBox(1, 2, 3, 4),
        source_hash="a" * 64,
    )


def test_missing_required_input_is_exact_and_deterministic() -> None:
    rule = _rule()
    first = evaluate_rule(rule, {}, evidence_records=[_evidence()])
    second = evaluate_rule(rule, {}, evidence_records=[_evidence()])
    assert first.status == "INDETERMINATE"
    assert first.missing_inputs == ("site_area_m2",)
    assert first.result_hash == second.result_hash
    assert first.rule_result_id == second.rule_result_id


def test_boundary_and_false_statuses_use_typed_decimal_comparison() -> None:
    rule = _rule()
    at_boundary = evaluate_rule(
        rule, {"site_area_m2": "1500"}, evidence_records=[_evidence()]
    )
    assert at_boundary.status == "SATISFIED"
    below = evaluate_rule(
        rule, {"site_area_m2": "1499.999"}, evidence_records=[_evidence()]
    )
    assert below.status == "NOT_SATISFIED"
    invalid = evaluate_rule(rule, {"site_area_m2": 1500.0}, evidence_records=[_evidence()])
    assert invalid.status == "ENGINE_ERROR"
    assert invalid.reason_codes == ("INVALID_RULE_INPUT",)
