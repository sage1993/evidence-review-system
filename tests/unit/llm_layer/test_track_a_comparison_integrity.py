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
    return Citation("CIT-E1", "DOC-1", "REV-1", 1, "E1", BBox(0, 0, 100, 20), "a" * 64)


def _comparison() -> dict[str, object]:
    return comparison_document(compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="대상 부지는 300m 떨어져 있다.",
        rule_text="승강장 경계로부터 250m 이내를 원칙으로 한다.",
        evidence_ids=("E1",),
    ))


def _bundle(comparison: dict[str, object], issue_ids: tuple[str, ...] = ("I2",)) -> TrackABundle:
    return TrackABundle(
        run_id="RUN-1",
        question="거리 검토",
        inputs={"fact_rule_comparisons": [comparison]},
        evidence=(
            EvidenceExcerpt(
                _citation(),
                "승강장 경계로부터 250미터 이내를 원칙으로 한다.",
                issue_ids,
                "rule",
            ),
        ),
        rules=(), calculations=(), approved_rule_result_ids=(),
    )


def _validated(issue_id: str = "I2") -> ValidatedTrackA:
    claim = Claim(
        "CL-1",
        "300미터는 일반 기준 250미터를 초과한다.",
        ("CIT-E1",),
        ("300", "250"),
        (issue_id,),
    )
    return ValidatedTrackA(
        draft=TrackADraft("RUN-1", (claim,), (), (), (), "comparison"),
        citation_ids=("CIT-E1",),
        calculation_result_ids=(),
        claim_references=(ClaimReferences("CL-1", (), ()),),
    )


def test_track_a_accepts_matching_comparison_value() -> None:
    validate_track_a_integrity(_validated(), _bundle(_comparison()))


def test_track_a_rejects_comparison_value_for_different_issue() -> None:
    with pytest.raises(ValueError, match="unregistered numeric token: 300"):
        validate_track_a_integrity(_validated("I3"), _bundle(_comparison(), ("I2", "I3")))


def test_track_a_rejects_comparison_hash_mismatch() -> None:
    comparison = _comparison()
    comparison["result_hash"] = "f" * 64
    with pytest.raises(ValueError, match="COMPARISON_HASH_MISMATCH"):
        validate_track_a_integrity(_validated(), _bundle(comparison))


def test_track_a_rejects_comparison_value_without_cited_evidence() -> None:
    comparison = comparison_document(compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="대상 부지는 300m 떨어져 있다.",
        rule_text="승강장 경계로부터 250m 이내를 원칙으로 한다.",
        evidence_ids=("E2",),
    ))
    with pytest.raises(ValueError, match="unregistered numeric token: 300"):
        validate_track_a_integrity(_validated(), _bundle(comparison))
