from dataclasses import replace

from ansim_review.contracts.common import BBox
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.rule_engine.evaluator import evaluate_rule
from ansim_review.rule_engine.loader import load_rule


def _rule():
    return load_rule(
        {
            "rule_id": "SOURCE-GATED",
            "version": "1.0.0",
            "title": "출처 게이트",
            "input_schema": {"applies": {"type": "boolean", "required": True}},
            "source_citations": [
                {
                    "citation_id": "C-SOURCE",
                    "document_id": "LAW1",
                    "revision_id": "REV-1",
                    "page_number": 8,
                    "evidence_id": "E-SOURCE",
                    "bbox": [10, 20, 30, 40],
                    "source_hash": "a" * 64,
                }
            ],
            "human_decision_required": True,
            "expression": {
                "compare": {
                    "operator": "eq",
                    "left": {"input": "applies"},
                    "right": {"literal": True},
                }
            },
        }
    )


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="E-SOURCE",
        document_id="LAW1",
        revision_id="REV-1",
        page_number=8,
        element_id="ELEMENT-1",
        evidence_type="text",
        bbox=BBox(10, 20, 30, 40),
        source_hash="a" * 64,
    )


def test_matching_source_identity_allows_execution() -> None:
    result = evaluate_rule(_rule(), {"applies": True}, evidence_records=[_evidence()])
    assert result.status == "SATISFIED"


def test_unresolved_or_hash_mismatched_source_blocks_execution() -> None:
    mismatched = replace(_evidence(), source_hash="b" * 64)
    result = evaluate_rule(_rule(), {"applies": True}, evidence_records=[mismatched])
    assert result.status == "ENGINE_ERROR"
    assert result.reason_codes == ("UNRESOLVED_RULE_SOURCE",)

    absent = evaluate_rule(_rule(), {"applies": True}, evidence_records=[])
    assert absent.status == "ENGINE_ERROR"
    assert absent.reason_codes == ("UNRESOLVED_RULE_SOURCE",)
