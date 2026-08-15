"""Canonical frozen contracts shared by review subsystems."""

from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.contracts.evidence import EvidenceRecord
from evidence_review.contracts.review import (
    Claim,
    ConfidenceFactor,
    ConfidenceResult,
    ReviewPacket,
    TrackADraft,
    TrackBAudit,
)

__all__ = [
    "BBox",
    "CalculationResult",
    "Citation",
    "Claim",
    "ConfidenceFactor",
    "ConfidenceResult",
    "EvidenceRecord",
    "ReviewPacket",
    "RuleResult",
    "TrackADraft",
    "TrackBAudit",
]
