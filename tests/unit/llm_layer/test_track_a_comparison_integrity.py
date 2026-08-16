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


def _bundle(
    comparison: dict[str, object],
    *,
    evidence_issue_ids: tuple[str, ...] = ("I2",),
) -> TrackABundle:
    return TrackABundle(
        run_id="RUN-1",
        question="거리 검토",
        inputs={"fact_rule_comparisons": [comparison]},
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text="승강장 경계로부터 250미터 이내를 원칙으로 한다.",
                issue_ids=evidence_issue_ids,
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


def _validated_claim(text: str, numeric_tokens: tuple[str, ...]) -> ValidatedTrackA:
    claim = Claim(
        claim_id="CL-1",
        text=text,
        citation_ids=("CIT-E1",),
        numeric_tokens=numeric_tokens,
        issue_ids=("I2",),
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
    bundle = _bundle(_comparison(), evidence_issue_ids=("I2", "I3"))

    with pytest.raises(ValueError, match="unregistered numeric token: 300"):
        validate_track_a_integrity(_validated("I3"), bundle)


def test_track_a_rejects_tampered_comparison_hash() -> None:
    comparison = _comparison()
    comparison["result_hash"] = "f" * 64

    with pytest.raises(ValueError, match="COMPARISON_HASH_MISMATCH"):
        validate_track_a_integrity(_validated(), _bundle(comparison))


def test_track_a_accepts_grouped_area_fact_equivalent_to_canonical_comparison() -> None:
    comparison = comparison_document(
        compare_fact_to_threshold(
            issue_id="I2",
            facet_id="minimum-area-threshold",
            fact_text="대상 부지 면적은 1,500㎡이다.",
            rule_text="사업대상지의 최소 면적 기준은 1,000㎡로 한다.",
            evidence_ids=("E1",),
        )
    )
    bundle = TrackABundle(
        run_id="RUN-1",
        question="면적 검토",
        inputs={"fact_rule_comparisons": [comparison]},
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text="사업대상지의 최소 면적 기준은 1,000㎡로 한다.",
                issue_ids=("I2",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
        approved_rule_result_ids=(),
    )

    validate_track_a_integrity(
        _validated_claim(
            "대상 부지 1,500㎡는 최소 기준 1,000㎡ 이상이다.",
            ("1,500", "1,000"),
        ),
        bundle,
    )


def test_track_a_preserves_percent_unit_for_comparison_fact_tokens() -> None:
    comparison = comparison_document(
        compare_fact_to_threshold(
            issue_id="I2",
            facet_id="semi-industrial-far-threshold",
            fact_text="계획 용적률은 450%이다.",
            rule_text="기준 용적률은 400% 이하이다.",
            evidence_ids=("E1",),
        )
    )
    bundle = TrackABundle(
        run_id="RUN-1",
        question="용적률 검토",
        inputs={"fact_rule_comparisons": [comparison]},
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text="기준 용적률은 400% 이하이다.",
                issue_ids=("I2",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
        approved_rule_result_ids=(),
    )

    validate_track_a_integrity(
        _validated_claim(
            "계획 용적률 450%는 기준 400%를 초과한다.",
            ("450%", "400%"),
        ),
        bundle,
    )
