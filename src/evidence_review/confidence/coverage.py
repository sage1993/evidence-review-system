"""Derive Confidence V1 factor inputs from deterministic issue coverage."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from evidence_review.retrieval.coverage import CoverageReport

_QUANTUM = Decimal("0.0001")
_SOURCE_GAPS = {
    "SOURCE_NOT_INGESTED",
    "REFERENCE_TARGET_MISSING",
    "RETRIEVAL_MISS",
    "RELEVANCE_INSUFFICIENT",
}
_COMPLETE_STATUSES = {"RESOLVED", "CONDITIONAL"}


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        raise ValueError("confidence ratio denominator must be positive")
    value = Decimal(numerator) / Decimal(denominator)
    return format(value.quantize(_QUANTUM, rounding=ROUND_HALF_UP), ".4f")


def _coverage_state(numerator: int, denominator: int) -> str:
    return "VERIFIED" if numerator == denominator else "FAILED"


def _factor(value: str, source: str, state: str) -> dict[str, object]:
    return {"value": value, "source": source, "state": state}


def apply_issue_coverage_factors(
    request: dict[str, object],
    report: CoverageReport,
) -> dict[str, object]:
    """Bind measured coverage factors without changing policy weights.

    The review request is prepared before a human decision exists, so human
    review status is explicitly pending rather than optimistically complete.
    Retrieval/source gaps reduce completeness even when a local citing rule was
    found, because the issue still lacks the authority needed for a full answer.
    """
    if not report.issues:
        raise ValueError("issue coverage report must not be empty")

    confidence_value = request.get("confidence_input")
    if not isinstance(confidence_value, dict):
        raise ValueError("review request confidence_input must be an object")
    factors_value = confidence_value.get("factors")
    if not isinstance(factors_value, dict):
        raise ValueError("review request confidence_input.factors must be an object")

    required_names = {
        "source completeness",
        "traceability",
        "parse quality",
        "human review status",
        "rule coverage",
        "input completeness",
        "unresolved conflict factor",
    }
    missing = sorted(required_names - set(factors_value))
    if missing:
        raise ValueError(
            "review request confidence factors are missing: " + ", ".join(missing)
        )

    total_issues = len(report.issues)
    source_complete = sum(
        not (_SOURCE_GAPS & set(item.gap_codes)) for item in report.issues
    )
    traceable = sum(
        item.status in _COMPLETE_STATUSES
        and bool(item.covered_roles)
        and not item.missing_roles
        for item in report.issues
    )
    complete_inputs = sum(
        item.status in _COMPLETE_STATUSES and not item.missing_roles
        for item in report.issues
    )
    parse_gap_free = sum("PARSE_GAP" not in item.gap_codes for item in report.issues)
    conflicts = sum(item.status == "CONFLICT" for item in report.issues)
    covered_roles = sum(len(item.covered_roles) for item in report.issues)
    required_roles = sum(
        len(item.covered_roles) + len(item.missing_roles) for item in report.issues
    )
    if required_roles <= 0:
        raise ValueError("issue coverage must declare at least one required evidence role")

    factors = {
        str(name): dict(cast(dict[str, object], value))
        for name, value in factors_value.items()
        if isinstance(name, str) and isinstance(value, dict)
    }
    if len(factors) != len(factors_value):
        raise ValueError("review request confidence factors must be objects")

    factors["source completeness"] = _factor(
        _ratio(source_complete, total_issues),
        f"issue_coverage:source_complete={source_complete}/{total_issues}",
        _coverage_state(source_complete, total_issues),
    )
    factors["traceability"] = _factor(
        _ratio(traceable, total_issues),
        f"issue_coverage:traceable={traceable}/{total_issues}",
        _coverage_state(traceable, total_issues),
    )
    factors["rule coverage"] = _factor(
        _ratio(covered_roles, required_roles),
        f"issue_coverage:required_roles={covered_roles}/{required_roles}",
        _coverage_state(covered_roles, required_roles),
    )
    factors["input completeness"] = _factor(
        _ratio(complete_inputs, total_issues),
        f"issue_coverage:complete_inputs={complete_inputs}/{total_issues}",
        _coverage_state(complete_inputs, total_issues),
    )
    factors["parse quality"] = _factor(
        _ratio(parse_gap_free, total_issues),
        f"issue_coverage:parse_gap_free={parse_gap_free}/{total_issues}",
        _coverage_state(parse_gap_free, total_issues),
    )
    factors["human review status"] = _factor(
        "0.0000", "human_review:pending", "NOT_VERIFIED"
    )
    factors["unresolved conflict factor"] = _factor(
        "0.0000" if conflicts else "1.0000",
        f"issue_coverage:conflicts={conflicts}/{total_issues}",
        "FAILED" if conflicts else "VERIFIED",
    )

    freshness = factors["source freshness"]
    if not (
        freshness.get("state") == "VERIFIED"
        and str(freshness.get("source", "")).startswith("source_freshness:verified")
    ):
        factors["source freshness"] = _factor(
            "0.0000", "source_freshness:not_verified", "NOT_VERIFIED"
        )

    bound = dict(request)
    confidence = dict(confidence_value)
    confidence["factors"] = factors
    bound["confidence_input"] = confidence
    return bound
