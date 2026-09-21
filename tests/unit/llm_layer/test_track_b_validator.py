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
from evidence_review.llm_layer.track_b import validate_track_b_output


def _track_a():
    citation = Citation("C1", "DOC1", "REV1", 1, "E1", BBox(0, 0, 1, 1), "a" * 64)
    bundle = build_track_a_bundle(
        run_id="RUN-0123456789ABCDEF0123",
        question="검토",
        inputs={},
        evidence=(EvidenceExcerpt(citation, "근거 1,500㎡"),),
        rules=(RuleResult("RULE1", "R1", "1.0.0", "SATISFIED", result_hash="b" * 64),),
        calculations=(
            CalculationResult(
                "CALC1",
                "SUCCESS",
                "F1",
                "1.0.0",
                display_result="1,500",
                result_hash="c" * 64,
            ),
        ),
        approved_rule_result_ids=("RULE1",),
    )
    output = {
        "run_id": bundle.run_id,
        "claims": [
            {
                "claim_id": "CL1",
                "text": "대지면적은 1,500㎡이다.",
                "citation_ids": ["C1"],
                "numeric_tokens": ["1,500"],
                "calculation_result_ids": ["CALC1"],
                "rule_references": [],
            },
            {
                "claim_id": "CL2",
                "text": "기준을 검토했다.",
                "citation_ids": ["C1"],
                "numeric_tokens": [],
                "calculation_result_ids": [],
                "rule_references": [],
            },
        ],
        "citations": ["C1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "설명",
    }
    return validate_track_a_output(output, bundle)


def _empty_track_a():
    bundle = build_track_a_bundle(
        run_id="RUN-EMPTY0123456789ABCDE",
        question="근거가 없는 질문",
        inputs={},
        evidence=(),
        rules=(),
        calculations=(),
    )
    output = {
        "run_id": bundle.run_id,
        "claims": [],
        "citations": [],
        "missing_inputs": ["근거 자료"],
        "exceptions": [],
        "conflicts": [],
        "explanation": "근거가 없어 주장하지 않는다.",
    }
    return validate_track_a_output(output, bundle)


def test_track_b_rejects_unaudited_track_a_claim() -> None:
    payload = {
        "run_id": "RUN-0123456789ABCDEF0123",
        "audited_question": "검토",
        "question_responsiveness": "PASS",
        "required_facet_completeness": "NOT_APPLICABLE",
        "claim_audits": [
            {"claim_id": "CL1", "disposition": "ACCEPT", "finding_codes": [], "notes": ""}
        ],
        "overall_disposition": "ACCEPT",
    }
    with pytest.raises(ValueError, match="unaudited claims: CL2"):
        validate_track_b_output(payload, _track_a())


def test_track_b_requires_consistent_overall_disposition() -> None:
    payload = {
        "run_id": "RUN-0123456789ABCDEF0123",
        "audited_question": "검토",
        "question_responsiveness": "PASS",
        "required_facet_completeness": "NOT_APPLICABLE",
        "claim_audits": [
            {
                "claim_id": "CL1",
                "disposition": "REJECT",
                "finding_codes": ["UNSUPPORTED_CLAIM"],
                "notes": "근거 부족",
            },
            {"claim_id": "CL2", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
        ],
        "overall_disposition": "ACCEPT",
    }
    with pytest.raises(ValueError, match="overall_disposition must be REJECT"):
        validate_track_b_output(payload, _track_a())


def test_track_b_accepts_complete_independent_audit() -> None:
    payload = {
        "run_id": "RUN-0123456789ABCDEF0123",
        "audited_question": "검토",
        "question_responsiveness": "PASS",
        "required_facet_completeness": "NOT_APPLICABLE",
        "claim_audits": [
            {"claim_id": "CL1", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
            {
                "claim_id": "CL2",
                "disposition": "INCOMPLETE",
                "finding_codes": ["MISSING_EXCEPTION"],
                "notes": "예외 검토 필요",
            },
        ],
        "overall_disposition": "INCOMPLETE",
    }
    audit = validate_track_b_output(payload, _track_a())
    assert audit.overall_disposition == "INCOMPLETE"
    assert tuple(item.claim_id for item in audit.claim_audits) == ("CL1", "CL2")


def test_track_b_requires_explicit_question_and_facet_semantics() -> None:
    payload = {
        "run_id": "RUN-0123456789ABCDEF0123",
        "audited_question": "검토",
        "question_responsiveness": "PASS",
        "required_facet_completeness": "NOT_APPLICABLE",
        "claim_audits": [
            {"claim_id": "CL1", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
            {"claim_id": "CL2", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
        ],
        "overall_disposition": "ACCEPT",
    }

    audit = validate_track_b_output(
        payload,
        _track_a(),
        expected_question="검토",
        expected_facet_completeness="NOT_APPLICABLE",
    )

    assert audit.question_responsiveness == "PASS"
    assert audit.required_facet_completeness == "NOT_APPLICABLE"


def test_track_b_question_mismatch_is_an_explicit_failed_gate() -> None:
    payload = {
        "run_id": "RUN-0123456789ABCDEF0123",
        "audited_question": "다른 질문",
        "question_responsiveness": "FAIL",
        "required_facet_completeness": "NOT_APPLICABLE",
        "claim_audits": [
            {"claim_id": "CL1", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
            {"claim_id": "CL2", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
        ],
        "overall_disposition": "ACCEPT",
    }

    audit = validate_track_b_output(
        payload,
        _track_a(),
        expected_question="검토",
        expected_facet_completeness="NOT_APPLICABLE",
    )

    assert audit.question_responsiveness == "FAIL"


def test_track_b_rejects_accept_for_empty_track_a_claim_set() -> None:
    track_a = _empty_track_a()

    with pytest.raises(ValueError, match="empty Track A claim set must be INCOMPLETE"):
        validate_track_b_output(
            {
                "run_id": track_a.draft.run_id,
                "audited_question": "근거가 없는 질문",
                "question_responsiveness": "NOT_VERIFIED",
                "required_facet_completeness": "NOT_APPLICABLE",
                "claim_audits": [],
                "overall_disposition": "ACCEPT",
            },
            track_a,
        )


def test_track_b_accepts_incomplete_for_empty_track_a_claim_set() -> None:
    track_a = _empty_track_a()

    audit = validate_track_b_output(
        {
            "run_id": track_a.draft.run_id,
            "audited_question": "근거가 없는 질문",
            "question_responsiveness": "NOT_VERIFIED",
            "required_facet_completeness": "NOT_APPLICABLE",
            "claim_audits": [],
            "overall_disposition": "INCOMPLETE",
        },
        track_a,
    )

    assert audit.claim_audits == ()
    assert audit.overall_disposition == "INCOMPLETE"


def test_required_facets_need_accepted_cited_claims_for_each_obligation() -> None:
    track_a = _track_a()
    claims = (
        replace(track_a.draft.claims[0], issue_ids=("I1",), fulfilled_facet_ids=("basic_far",)),
        replace(track_a.draft.claims[1], issue_ids=("I1",), fulfilled_facet_ids=("maximum_far",)),
    )
    track_a = replace(track_a, draft=replace(track_a.draft, claims=claims))
    payload = {
        "run_id": track_a.draft.run_id,
        "audited_question": "검토",
        "question_responsiveness": "PASS",
        "required_facet_completeness": "INCOMPLETE",
        "claim_audits": [
            {"claim_id": "CL1", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
            {"claim_id": "CL2", "disposition": "ACCEPT", "finding_codes": [], "notes": ""},
        ],
        "overall_disposition": "ACCEPT",
    }
    audit = validate_track_b_output(
        payload,
        track_a,
        required_facets_by_issue={"I1": frozenset({"basic_far", "maximum_far", "delivery_method"})},
    )
    assert audit.required_facet_completeness == "INCOMPLETE"
    payload["required_facet_completeness"] = "COMPLETE"
    with pytest.raises(ValueError, match="cited accepted claim facets"):
        validate_track_b_output(payload, track_a, required_facets_by_issue={
            "I1": frozenset({"basic_far", "maximum_far", "delivery_method"})
        })
    complete = validate_track_b_output(payload, track_a, required_facets_by_issue={
        "I1": frozenset({"basic_far", "maximum_far"})
    })
    assert complete.required_facet_completeness == "COMPLETE"


@pytest.mark.parametrize("reported", ["COMPLETE", "NOT_APPLICABLE"])
def test_no_claim_cannot_satisfy_explicit_required_facets(reported) -> None:
    track_a = _empty_track_a()
    with pytest.raises(ValueError, match="cited accepted claim facets"):
        validate_track_b_output({
            "run_id": track_a.draft.run_id,
            "audited_question": "근거가 없는 질문",
            "question_responsiveness": "NOT_VERIFIED",
            "required_facet_completeness": reported,
            "claim_audits": [],
            "overall_disposition": "INCOMPLETE",
        }, track_a, required_facets_by_issue={"I1": frozenset({"source_support"})})
