from __future__ import annotations

import pytest

from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.confidence.scorer import FactorInput, score_confidence


def _uniform(value: str):
    return {name: FactorInput(value=value, source=f"source:{name}") for name in FACTOR_WEIGHTS}


def test_confidence_weighted_score_is_exact_and_auditable() -> None:
    values = {
        "source completeness": "1.0",
        "traceability": "0.8",
        "parse quality": "0.5",
        "human review status": "0.0",
        "rule coverage": "1.0",
        "input completeness": "0.75",
        "calculation validity": "1.0",
        "Track B agreement": "1.0",
        "source freshness": "0.5",
        "unresolved conflict factor": "1.0",
    }
    result = score_confidence(
        {name: FactorInput(value=value, source=f"metric:{name}") for name, value in values.items()}
    )
    assert result.score == "0.7675"
    assert result.level == "MEDIUM"
    assert tuple(factor.name for factor in result.factors) == tuple(FACTOR_WEIGHTS)
    assert result.factors[0].weight == "0.20"
    assert result.factors[0].contribution == "0.2000"


@pytest.mark.parametrize(
    ("value", "expected_score", "expected_level"),
    [
        ("0.90", "0.9000", "HIGH"),
        ("0.70", "0.7000", "MEDIUM"),
        ("0.69994", "0.6999", "LOW"),
    ],
)
def test_confidence_boundaries(value: str, expected_score: str, expected_level: str) -> None:
    result = score_confidence(_uniform(value))
    assert result.score == expected_score
    assert result.level == expected_level


def test_pending_human_review_caps_high_confidence_at_medium() -> None:
    factors = _uniform("1.0")
    factors["human review status"] = FactorInput(
        value="0.0",
        source="human_review:pending",
    )

    result = score_confidence(factors)

    assert result.score == "0.9000"
    assert result.level == "MEDIUM"


def test_confidence_factor_state_is_preserved_in_auditable_output() -> None:
    factors = _uniform("1.0")
    factors["calculation validity"] = FactorInput(
        value="0.0",
        source="calculation:none",
        state="NOT_APPLICABLE",
    )

    result = score_confidence(factors)

    calculation = next(
        factor for factor in result.factors if factor.name == "calculation validity"
    )
    assert calculation.state == "NOT_APPLICABLE"


def test_confidence_rejects_missing_or_out_of_range_factor() -> None:
    factors = _uniform("1")
    factors.pop("source freshness")
    with pytest.raises(ValueError, match="missing confidence factors"):
        score_confidence(factors)
    with pytest.raises(ValueError, match="between 0 and 1"):
        score_confidence(_uniform("1.01"))
