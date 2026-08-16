from __future__ import annotations

from evidence_review.retrieval.facets import FacetCoverageReport, IssueFacetCoverage
from evidence_review.rule_engine.fact_rule_comparison import (
    FactRuleComparison,
    compare_fact_to_threshold,
    conditional_issue_ids_from_comparisons,
)


def test_area_fact_is_compared_against_minimum_threshold_deterministically() -> None:
    result = compare_fact_to_threshold(
        issue_id="I1",
        facet_id="minimum-area-threshold",
        fact_text="대상 부지 면적은 1,500㎡이다.",
        rule_text="사업대상지의 최소 면적 기준은 1,000㎡로 한다.",
        evidence_ids=("E-MIN-AREA",),
    )

    assert result.operator == ">="
    assert result.fact_value == "1500"
    assert result.threshold_value == "1000"
    assert result.unit == "area_m2"
    assert result.satisfied is True
    assert result.evidence_ids == ("E-MIN-AREA",)
    assert len(result.result_hash) == 64


def test_distance_fact_exceeds_normal_threshold_but_meets_conditional_threshold() -> None:
    normal = compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="대상 부지는 역 승강장 경계에서 300m 떨어져 있다.",
        rule_text="역세권은 승강장 경계로부터 250m 이내를 원칙으로 한다.",
        evidence_ids=("E-250",),
    )
    conditional = compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-conditional-threshold",
        fact_text="대상 부지는 역 승강장 경계에서 300m 떨어져 있다.",
        rule_text="통합심의를 거치는 경우 승강장 경계로부터 350m 이내까지 검토할 수 있다.",
        evidence_ids=("E-350",),
    )

    assert normal.operator == "<="
    assert normal.fact_value == "300"
    assert normal.threshold_value == "250"
    assert normal.satisfied is False
    assert conditional.operator == "<="
    assert conditional.fact_value == "300"
    assert conditional.threshold_value == "350"
    assert conditional.satisfied is True


def test_far_fact_at_threshold_is_satisfied() -> None:
    result = compare_fact_to_threshold(
        issue_id="I5",
        facet_id="semi-industrial-far-threshold",
        fact_text="공동주택 부분에 용적률 400% 완화를 적용한다.",
        rule_text="준공업지역 공동주택의 기본용적률은 400% 이하로 정할 수 있다.",
        evidence_ids=("E-FAR",),
    )

    assert result.operator == "<="
    assert result.fact_value == "400"
    assert result.threshold_value == "400"
    assert result.unit == "percent"
    assert result.satisfied is True


def test_comparison_hash_is_reproducible() -> None:
    left = compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="300m",
        rule_text="250m 이내",
        evidence_ids=("E-250",),
    )
    right = compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="300m",
        rule_text="250m 이내",
        evidence_ids=("E-250",),
    )

    assert left == right
    assert left.result_hash == right.result_hash


def _comparison(facet_id: str, satisfied: bool) -> FactRuleComparison:
    return FactRuleComparison(
        comparison_id=f"CMP-{facet_id}",
        issue_id="I2",
        facet_id=facet_id,
        operator=">=" if facet_id == "minimum-area-threshold" else "<=",
        fact_value="1500" if facet_id == "minimum-area-threshold" else "300",
        threshold_value=(
            "1000"
            if facet_id == "minimum-area-threshold"
            else "250"
            if facet_id == "distance-normal-threshold"
            else "350"
        ),
        unit="area_m2" if facet_id == "minimum-area-threshold" else "length_m",
        satisfied=satisfied,
        evidence_ids=(f"E-{facet_id}",),
        result_hash="a" * 64,
    )


def _compound_distance_coverage() -> FacetCoverageReport:
    facets = (
        "minimum-area-threshold",
        "distance-normal-threshold",
        "distance-conditional-threshold",
    )
    return FacetCoverageReport(
        issues=(
            IssueFacetCoverage(
                issue_id="I2",
                covered_facet_ids=facets,
                missing_facet_ids=(),
                evidence_by_facet=tuple((facet_id, (f"E-{facet_id}",)) for facet_id in facets),
            ),
        )
    )


def test_conditional_status_requires_other_required_numeric_facets_to_pass() -> None:
    coverage = _compound_distance_coverage()
    distance_only = (
        _comparison("distance-normal-threshold", False),
        _comparison("distance-conditional-threshold", True),
    )
    failed_area = (
        _comparison("minimum-area-threshold", False),
        *distance_only,
    )
    passing = (
        _comparison("minimum-area-threshold", True),
        *distance_only,
    )

    assert conditional_issue_ids_from_comparisons(distance_only, coverage) == ()
    assert conditional_issue_ids_from_comparisons(failed_area, coverage) == ()
    assert conditional_issue_ids_from_comparisons(passing, coverage) == ("I2",)
