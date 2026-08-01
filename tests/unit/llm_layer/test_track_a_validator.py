from __future__ import annotations

import pytest

from ansim_review.contracts.common import BBox, Citation
from ansim_review.contracts.engines import CalculationResult, RuleResult
from ansim_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    validate_track_a_output,
)


def _bundle():
    citation = Citation("C1", "DOC1", "REV1", 1, "E1", BBox(0, 0, 10, 10), "a" * 64)
    calculation = CalculationResult(
        calculation_result_id="CALC1",
        status="SUCCESS",
        formula_id="FRONTAGE_RATIO",
        formula_version="1.0.0",
        display_result="9.375%",
        result_hash="b" * 64,
    )
    rule = RuleResult(
        rule_result_id="RULE1",
        rule_id="R1",
        rule_version="1.0.0",
        status="SATISFIED",
        result_hash="c" * 64,
    )
    return build_track_a_bundle(
        run_id="RUN-0123456789ABCDEF0123",
        question="기준 충족 여부",
        inputs={"site_area": "1500"},
        evidence=(EvidenceExcerpt(citation, "접면 비율은 9.375%이다."),),
        rules=(rule,),
        calculations=(calculation,),
        approved_rule_result_ids=("RULE1",),
    )


def _valid_output():
    return {
        "run_id": "RUN-0123456789ABCDEF0123",
        "claims": [
            {
                "claim_id": "CL1",
                "text": "접면 비율은 9.375%이다.",
                "citation_ids": ["C1"],
                "numeric_tokens": ["9.375%"],
                "calculation_result_ids": ["CALC1"],
                "rule_references": [
                    {
                        "rule_result_id": "RULE1",
                        "result_hash": "c" * 64,
                        "status": "SATISFIED",
                    }
                ],
            }
        ],
        "citations": ["C1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "근거와 계산 결과를 설명한다.",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("human_decision", "SATISFIED"),
        ("confidence", "0.95"),
        ("rule_results", [{"status": "SATISFIED"}]),
    ],
)
def test_track_a_rejects_forbidden_machine_authority(field: str, value: object) -> None:
    payload = _valid_output()
    payload[field] = value
    with pytest.raises(ValueError, match="forbidden|unknown"):
        validate_track_a_output(payload, _bundle())


def test_track_a_requires_all_declared_sections() -> None:
    payload = _valid_output()
    del payload["conflicts"]
    with pytest.raises(ValueError, match="conflicts"):
        validate_track_a_output(payload, _bundle())


def test_valid_track_a_output_is_reduced_to_claim_contract() -> None:
    result = validate_track_a_output(_valid_output(), _bundle())
    assert result.draft.claims[0].claim_id == "CL1"
    assert result.citation_ids == ("C1",)
    assert result.calculation_result_ids == ("CALC1",)
