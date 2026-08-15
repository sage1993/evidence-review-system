"""LLM-boundary, confidence, and final review contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from evidence_review.contracts.engines import CalculationResult, RuleResult

FinalizerStatus = Literal["READY_FOR_HUMAN_REVIEW", "ABSTAIN"]
HumanDecision = Literal[
    "SATISFIED",
    "NOT_SATISFIED",
    "CONDITIONAL",
    "ADDITIONAL_REVIEW_REQUIRED",
]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
AuditDisposition = Literal["ACCEPT", "REJECT", "INCOMPLETE"]


@dataclass(frozen=True, slots=True)
class Claim:
    """Track A factual claim tied to citation identifiers."""

    claim_id: str
    text: str
    citation_ids: tuple[str, ...]
    numeric_tokens: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrackADraft:
    """Untrusted explanatory output produced outside the runtime."""

    run_id: str
    claims: tuple[Claim, ...]
    missing_inputs: tuple[str, ...]
    exceptions: tuple[str, ...]
    conflicts: tuple[str, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class ClaimAudit:
    """Track B disposition for one Track A claim."""

    claim_id: str
    disposition: AuditDisposition
    finding_codes: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class TrackBAudit:
    """Independent audit of every Track A claim."""

    run_id: str
    claim_audits: tuple[ClaimAudit, ...]
    overall_disposition: AuditDisposition


@dataclass(frozen=True, slots=True)
class ConfidenceFactor:
    """One auditable confidence contribution."""

    name: str
    value: str
    weight: str
    contribution: str
    source: str


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    """Deterministic confidence-policy output."""

    policy_version: str
    score: str
    level: ConfidenceLevel
    factors: tuple[ConfidenceFactor, ...]
    hard_gate_failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewPacket:
    """Machine-produced packet awaiting a separate human decision record."""

    run_id: str
    status: FinalizerStatus
    human_decision: HumanDecision | None
    question: str
    claims: tuple[Claim, ...]
    calculations: tuple[CalculationResult, ...]
    rules: tuple[RuleResult, ...]
    confidence: ConfidenceResult | None
    abstention_reasons: tuple[str, ...]
    snapshot_sha256: str | None = None
    missing_inputs: tuple[str, ...] = ()
    _serialized_lineage_fields: tuple[str, ...] = field(
        default=("snapshot_sha256", "missing_inputs"),
        compare=False,
        repr=False,
    )
