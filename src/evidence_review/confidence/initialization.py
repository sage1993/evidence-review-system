"""Shared initial confidence-factor semantics for review request builders."""

from __future__ import annotations

from collections.abc import Sequence

from evidence_review.confidence.policy import FACTOR_WEIGHTS

_EVIDENCE_DEPENDENT_FACTORS = frozenset(
    {
        "source completeness",
        "traceability",
        "input completeness",
    }
)


def initial_confidence_factors(
    *,
    evidence_available: bool,
    evidence_source: str,
    calculation_statuses: Sequence[object] = (),
) -> dict[str, dict[str, str]]:
    """Build one honest pre-finalization confidence input for every review path."""
    if not evidence_source:
        raise ValueError("evidence_source must be non-empty")

    statuses = tuple(calculation_statuses)
    factors: dict[str, dict[str, str]] = {}
    for name in FACTOR_WEIGHTS:
        if name in _EVIDENCE_DEPENDENT_FACTORS:
            factors[name] = {
                "value": "1.0" if evidence_available else "0.0",
                "source": evidence_source,
                "state": "VERIFIED" if evidence_available else "FAILED",
            }
        elif name == "calculation validity":
            if not statuses:
                factors[name] = {
                    "value": "0.0",
                    "source": "calculation:none",
                    "state": "NOT_APPLICABLE",
                }
            else:
                valid = all(status == "SUCCESS" for status in statuses)
                factors[name] = {
                    "value": "1.0" if valid else "0.0",
                    "source": "calculation:approved_results",
                    "state": "VERIFIED" if valid else "FAILED",
                }
        elif name == "Track B agreement":
            factors[name] = {
                "value": "0.0",
                "source": "track_b:not_submitted",
                "state": "NOT_VERIFIED",
            }
        elif name == "source freshness":
            factors[name] = {
                "value": "0.0",
                "source": "source_freshness:not_verified",
                "state": "NOT_VERIFIED",
            }
        elif name == "human review status":
            factors[name] = {
                "value": "0.0",
                "source": "human_review:pending",
                "state": "NOT_VERIFIED",
            }
        else:
            factors[name] = {
                "value": "1.0",
                "source": evidence_source,
                "state": "VERIFIED",
            }
    return factors


__all__ = ["initial_confidence_factors"]
