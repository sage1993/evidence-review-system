from __future__ import annotations

from decimal import Decimal

from evidence_review.retrieval.conditional import (
    Measure,
    conditional_range_satisfied,
    extract_measures,
)


def test_extracts_equivalent_metric_units() -> None:
    assert extract_measures("대상은 300m이고 기준은 250미터, 350 m이다.") == (
        Measure(value=Decimal("300"), dimension="length_m", start=4, conditional=False),
        Measure(value=Decimal("250"), dimension="length_m", start=16, conditional=False),
        Measure(value=Decimal("350"), dimension="length_m", start=23, conditional=False),
    )


def test_detects_fact_between_ordinary_and_conditional_threshold() -> None:
    rule_text = (
        "승강장 경계로부터 250미터 이내를 원칙으로 한다. "
        "다만 통합심의위원회의 심의를 거쳐 350미터 이내의 토지를 "
        "사업대상지로 지정할 수 있다."
    )

    assert conditional_range_satisfied("300m", rule_text) is True
    assert conditional_range_satisfied("200m", rule_text) is False
    assert conditional_range_satisfied("400m", rule_text) is False


def test_does_not_infer_condition_without_conditional_language() -> None:
    assert conditional_range_satisfied(
        "300m",
        "거리기준은 250미터 이상 350미터 이하이다.",
    ) is False


def test_does_not_mix_dimensions() -> None:
    assert conditional_range_satisfied(
        "1500㎡",
        "일반 기준은 1000㎡이고 조건부 거리기준은 350미터 이내이다.",
    ) is False
