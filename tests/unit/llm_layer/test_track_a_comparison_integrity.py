from __future__ import annotations

import pytest

from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.review import Claim, TrackADraft
from evidence_review.llm_layer.track_a import (
    ClaimReferences,
    EvidenceExcerpt,
    TrackABundle,
    ValidatedTrackA,
)
from evidence_review.llm_layer.validators import validate_track_a_integrity
from evidence_review.rule_engine.fact_rule_comparison import (
    compare_fact_to_threshold,
    comparison_document,
)


def _citation() -> Citation:
    return Citation(
        citation_id="CIT-E1",
        document_id="DOC-1",
        revision_id="REV-1",
        page_number=1,
        evidence_id="E1",
        bbox=BBox(0, 0, 100, 20),
        source_hash="a" * 64,
    )


def _comparison() -> dict[str, object]:
    return comparison_document(
        compare_fact_to_threshold(
            issue_id="I2",
            facet_id="distance-normal-threshold",
            fact_text="대상 부지는 300m 떨어져 있다.",
            rule_text="승강장 경계로부터 250m 이내를 원칙으로 한다.",
            evidence_ids=("E1",),
        )
    )


def _bundle(comparison: dict[str, object]) -> TrackABundle:
    return TrackABundle(
        run_id="RUN-1",
        question="거리 검토",
        inputs={"fact_rule_comparisons": [comparison]},
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text="승강장 경계로부터 250미터 이내를 원칙으로 한다.",
                issue_ids=("I2",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
        approved_rule_result_ids=(),
    )


def _validated(issue_id: str = "I2") -> ValidatedTrackA:
    claim = Claim(
        claim_id="CL-1",
        text="300미터는 일반 기준 250미터를 초과한다.",
        citation_ids=("CIT-E1",),
        numeric_tokens=("300", "250"),
        issue_ids=(issue_id,),
    )
    return ValidatedTrackA(
        draft=TrackADraft(
            run_id="RUN-1",
            claims=(claim,),
            missing_inputs=(),
            exceptions=(),
            conflicts=(),
            explanation="comparison",
        ),
        citation_ids=("CIT-E1",),
        calculation_result_ids=(),
        claim_references=(
            ClaimReferences(
                claim_id="CL-1",
                calculation_result_ids=(),
                rule_references=(),
            ),
        ),
    )


def test_track_a_may_use_comparison_fact_value_only_with_matching_issue_and_evidence() -> None:
    validate_track_a_integrity(_validated(), _bundle(_comparison()))


def test_track_a_rejects_comparison_fact_value_for_different_issue() -> None:
    with pytest.raises(ValueError, match="unregistered numeric token: 300"):
        validate_track_a_integrity(_validated("I3"), _bundle(_comparison()))


def test_track_a_rejects_tampered_comparison_hash() -> None:
    comparison = _comparison()
    comparison["result_hash"] = "f" * 64

    with pytest.raises(ValueError, match="COMPARISON_HASH_MISMATCH"):
        validate_track_a_integrity(_validated(), _bundle(comparison))
