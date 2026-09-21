from __future__ import annotations

from dataclasses import replace

import pytest

from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    validate_track_a_output,
)
from evidence_review.llm_layer.validators import validate_track_a_integrity


def _bundle(
    *,
    evidence_text: str = "접면 비율은 9.375%이다.",
    calculation: CalculationResult | None = None,
):
    citation = Citation("C1", "DOC1", "REV1", 1, "E1", BBox(0, 0, 10, 10), "a" * 64)
    selected_calculation = calculation or CalculationResult(
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
        evidence=(EvidenceExcerpt(citation, evidence_text),),
        rules=(rule,),
        calculations=(selected_calculation,),
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


def _validate(payload, bundle=None) -> None:
    selected_bundle = bundle or _bundle()
    validated = validate_track_a_output(payload, selected_bundle)
    validate_track_a_integrity(validated, selected_bundle)


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


def test_track_a_rejects_unknown_explicit_required_facet() -> None:
    bundle = _bundle()
    bundle = replace(
        bundle,
        inputs={"question_plan": {"issues": [{"id": "I1", "required_facet_ids": ["basic_far"]}]}},
    )
    payload = _valid_output()
    payload["claims"][0]["issue_ids"] = ["I1"]
    payload["claims"][0]["fulfilled_facet_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="unknown or ambiguous fulfilled facet"):
        validate_track_a_output(payload, bundle)


def test_llm_authored_rounded_percentage_is_rejected() -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = "접면 비율은 9.4%이다."
    payload["claims"][0]["numeric_tokens"] = ["9.4%"]
    validated = validate_track_a_output(payload, _bundle())
    with pytest.raises(ValueError, match="unregistered numeric token: 9.4%"):
        validate_track_a_integrity(validated, _bundle())


@pytest.mark.parametrize("text", ["값은 1e3이다.", "값은 .5이다.", "값은 ½이다."])
def test_numeric_meaning_cannot_bypass_with_empty_declared_tokens(text: str) -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = text
    payload["claims"][0]["numeric_tokens"] = []
    validated = validate_track_a_output(payload, _bundle())

    with pytest.raises(ValueError, match="UNSUPPORTED_NUMERIC_SYNTAX"):
        validate_track_a_integrity(validated, _bundle())


@pytest.mark.parametrize(
    ("text", "declared"),
    [
        ("접면 비율은 9.375%이다.", ["9.375"]),
        ("면적은 1,234이다.", ["1234"]),
        ("값은 -12이다.", ["12"]),
    ],
)
def test_numeric_tokens_must_exactly_match_text(text: str, declared: list[str]) -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = text
    payload["claims"][0]["numeric_tokens"] = declared

    with pytest.raises(ValueError, match="NUMERIC_TOKEN_MISMATCH: CL1"):
        _validate(payload)


def test_exact_evidence_grouped_number_is_accepted() -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = "면적은 1,234이다."
    payload["claims"][0]["numeric_tokens"] = ["1,234"]
    payload["claims"][0]["calculation_result_ids"] = []

    _validate(payload, _bundle(evidence_text="면적은 1,234이다."))


def test_evidence_number_is_not_normalized_for_claim() -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = "면적은 1234이다."
    payload["claims"][0]["numeric_tokens"] = ["1234"]
    payload["claims"][0]["calculation_result_ids"] = []

    with pytest.raises(ValueError, match="unregistered numeric token: 1234"):
        _validate(payload, _bundle(evidence_text="면적은 1,234이다."))


def test_leading_dot_source_does_not_authorize_normalized_claim() -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = "비율은 0.5이다."
    payload["claims"][0]["numeric_tokens"] = ["0.5"]
    payload["claims"][0]["calculation_result_ids"] = []

    with pytest.raises(ValueError, match="unregistered numeric token: 0.5"):
        _validate(payload, _bundle(evidence_text="비율은 .5이다."))


@pytest.mark.parametrize(
    "token",
    ["123", "61.5", "50%", "2", "60"],
)
def test_referenced_successful_calculation_authorizes_exact_tokens(token: str) -> None:
    calculation = CalculationResult(
        calculation_result_id="CALC1",
        status="SUCCESS",
        formula_id="TEST",
        formula_version="1.0.0",
        inputs={"input": "123"},
        substitution="123 / 2",
        raw_result="61.5",
        display_result="50%",
        comparison="61.5 >= 60",
        result_hash="b" * 64,
    )
    payload = _valid_output()
    payload["claims"][0]["text"] = f"계산 근거는 {token}이다."
    payload["claims"][0]["numeric_tokens"] = [token]

    _validate(payload, _bundle(evidence_text="계산 결과를 참고한다.", calculation=calculation))


def test_unreferenced_calculation_does_not_authorize_token() -> None:
    calculation = CalculationResult(
        calculation_result_id="CALC1",
        status="SUCCESS",
        formula_id="TEST",
        formula_version="1.0.0",
        raw_result="61.5",
        result_hash="b" * 64,
    )
    payload = _valid_output()
    payload["claims"][0]["text"] = "계산 근거는 61.5이다."
    payload["claims"][0]["numeric_tokens"] = ["61.5"]
    payload["claims"][0]["calculation_result_ids"] = []

    with pytest.raises(ValueError, match="unregistered numeric token: 61.5"):
        _validate(payload, _bundle(evidence_text="계산 결과를 참고한다.", calculation=calculation))


def test_exact_math_value_and_rule_reference_are_accepted() -> None:
    _validate(_valid_output(), _bundle())


def test_rule_reference_hash_or_status_mismatch_is_rejected() -> None:
    payload = _valid_output()
    payload["claims"][0]["rule_references"][0]["result_hash"] = "d" * 64
    bundle = _bundle()
    validated = validate_track_a_output(payload, bundle)
    with pytest.raises(ValueError, match="rule result reference mismatch"):
        validate_track_a_integrity(validated, bundle)
