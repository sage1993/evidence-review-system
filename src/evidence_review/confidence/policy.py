"""Auditable Confidence Policy V1 constants."""

from __future__ import annotations

from decimal import Decimal

POLICY_VERSION = "CONFIDENCE_V1"
FACTOR_WEIGHTS: dict[str, Decimal] = {
    "source completeness": Decimal("0.20"),
    "traceability": Decimal("0.15"),
    "parse quality": Decimal("0.10"),
    "human review status": Decimal("0.10"),
    "rule coverage": Decimal("0.15"),
    "input completeness": Decimal("0.15"),
    "calculation validity": Decimal("0.05"),
    "Track B agreement": Decimal("0.05"),
    "source freshness": Decimal("0.03"),
    "unresolved conflict factor": Decimal("0.02"),
}
HIGH_THRESHOLD = Decimal("0.90")
MEDIUM_THRESHOLD = Decimal("0.70")
