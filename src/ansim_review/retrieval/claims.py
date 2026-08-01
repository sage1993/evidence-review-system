"""Factual-claim citation enforcement."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ansim_review.contracts.common import Citation
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.contracts.review import Claim
from ansim_review.retrieval.citations import resolve_citation


@dataclass(frozen=True, slots=True)
class ClaimCitationIssue:
    claim_id: str
    code: str
    citation_id: str | None = None


def validate_claims(
    claims: Sequence[Claim],
    citations: Sequence[Citation],
    evidence_records: Sequence[EvidenceRecord],
) -> tuple[ClaimCitationIssue, ...]:
    """Return deterministic citation failures for every factual claim."""
    citation_map = {
        citation.citation_id: citation for citation in citations
    }
    evidence_map = {
        record.evidence_id: record for record in evidence_records
    }
    issues: list[ClaimCitationIssue] = []
    for claim in claims:
        if not claim.citation_ids:
            issues.append(
                ClaimCitationIssue(claim.claim_id, "UNCITED_CLAIM")
            )
            continue
        for citation_id in claim.citation_ids:
            citation = citation_map.get(citation_id)
            if citation is None:
                issues.append(
                    ClaimCitationIssue(
                        claim.claim_id,
                        "UNRESOLVED_CITATION",
                        citation_id,
                    )
                )
                continue
            resolution = resolve_citation(citation, evidence_map)
            issues.extend(
                ClaimCitationIssue(claim.claim_id, code, citation_id)
                for code in resolution.error_codes
            )
    return tuple(issues)
