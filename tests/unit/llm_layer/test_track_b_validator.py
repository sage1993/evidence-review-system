from __future__ import annotations

import pytest

from ansim_review.contracts.common import BBox, Citation
from ansim_review.contracts.engines import CalculationResult, RuleResult
from ansim_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    validate_track_a_output,
)
from ansim_review.llm_layer.track_b import validate_track_b_output


def _track_a():
    citation = Citation(
        "C1", "DOC1", "REV1", 1, "E1", BBox(0, 0, 1, 1), "a" * 64
    )
    bundle = build_track_a_bundle(
        run_id="RUN-0123456789ABCDEF0123",
        question="검토",
        inputs={},
        evidence=(EvidenceExcerpt(citation, "근거 1,500㎡"),),
        rules=(
            RuleResult(
                "RULE1", "R1", "1.0.0", "SATISFIED", result_hash="b" * 64
            ),
        ),
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


def test_track_b_rejects_unaudited_track_a_claim() -> None:
    payload = {
        "run_id": "RUN-0123456789ABCDEF0123",
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
