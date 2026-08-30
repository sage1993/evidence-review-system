from __future__ import annotations

import importlib
from typing import Any

import pytest

from evidence_review.retrieval.facets import FacetCoverageReport, IssueFacetCoverage


def _comparison_api() -> Any:
    try:
        module = importlib.import_module("evidence_review.rule_engine.fact_rule_comparison")
    except ModuleNotFoundError:
        pytest.fail(
            "evidence_review.rule_engine.fact_rule_comparison is not implemented",
            pytrace=False,
        )
    required = (
        "FactRuleComparison",
        "compare_fact_to_threshold",
        "conditional_issue_ids_from_comparisons",
    )
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail(f"fact-rule comparison API missing: {missing}", pytrace=False)
    return module


def test_area_fact_is_compared_against_minimum_threshold_deterministically() -> None:
    module = _comparison_api()
    result = module.compare_fact_to_threshold(
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


def test_distance_fact_exceeds_normal_but_meets_conditional_threshold() -> None:
    module = _comparison_api()
    normal = module.compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="대상 부지는 역 승강장 경계에서 300m 떨어져 있다.",
        rule_text="역세권은 승강장 경계로부터 250m 이내를 원칙으로 한다.",
        evidence_ids=("E-250",),
    )
    conditional = module.compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-conditional-threshold",
        fact_text="대상 부지는 역 승강장 경계에서 300m 떨어져 있다.",
        rule_text="통합심의를 거치는 경우 승강장 경계로부터 350m 이내까지 검토할 수 있다.",
        evidence_ids=("E-350",),
    )

    assert (normal.operator, normal.fact_value, normal.threshold_value, normal.satisfied) == (
        "<=",
        "300",
        "250",
        False,
    )
    assert (
        conditional.operator,
        conditional.fact_value,
        conditional.threshold_value,
        conditional.satisfied,
    ) == ("<=", "300", "350", True)


def test_far_fact_at_threshold_is_satisfied() -> None:
    module = _comparison_api()
    result = module.compare_fact_to_threshold(
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
    module = _comparison_api()
    left = module.compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="300m",
        rule_text="250m 이내",
        evidence_ids=("E-250",),
    )
    right = module.compare_fact_to_threshold(
        issue_id="I2",
        facet_id="distance-normal-threshold",
        fact_text="300m",
        rule_text="250m 이내",
        evidence_ids=("E-250",),
    )

    assert left == right
    assert left.result_hash == right.result_hash


def _coverage() -> FacetCoverageReport:
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
                evidence_by_facet=tuple(
                    (facet_id, (f"E-{facet_id}",)) for facet_id in facets
                ),
            ),
        )
    )


def _comparison(module: Any, facet_id: str, satisfied: bool) -> Any:
    return module.FactRuleComparison(
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


def test_conditional_status_requires_all_other_numeric_facets_to_pass() -> None:
    module = _comparison_api()
    coverage = _coverage()
    distance_only = (
        _comparison(module, "distance-normal-threshold", False),
        _comparison(module, "distance-conditional-threshold", True),
    )
    failed_area = (
        _comparison(module, "minimum-area-threshold", False),
        *distance_only,
    )
    passing = (
        _comparison(module, "minimum-area-threshold", True),
        *distance_only,
    )

    assert module.conditional_issue_ids_from_comparisons(distance_only, coverage) == ()
    assert module.conditional_issue_ids_from_comparisons(failed_area, coverage) == ()
    assert module.conditional_issue_ids_from_comparisons(passing, coverage) == ("I2",)
