"""Factual-claim citation and issue-lineage enforcement."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evidence_review.contracts.common import Citation
from evidence_review.contracts.evidence import EvidenceRecord
from evidence_review.contracts.review import Claim
from evidence_review.retrieval.citations import resolve_citation


@dataclass(frozen=True, slots=True)
class ClaimCitationIssue:
    claim_id: str
    code: str
    citation_id: str | None = None


def validate_claims(
    claims: Sequence[Claim],
    citations: Sequence[Citation],
    evidence_records: Sequence[EvidenceRecord],
    *,
    citation_issue_ids: Mapping[str, Sequence[str]] | None = None,
    valid_issue_ids: Sequence[str] | None = None,
) -> tuple[ClaimCitationIssue, ...]:
    """Return deterministic citation and issue-lineage failures for claims.

    ``valid_issue_ids`` is authoritative when a QuestionPlan is available. Legacy
    callers without that plan can still enforce missing issue ids and cross-issue
    citations, but cannot classify an otherwise unseen issue id as unknown.
    """
    citation_map = {citation.citation_id: citation for citation in citations}
    evidence_map = {record.evidence_id: record for record in evidence_records}
    issue_map = {
        citation_id: tuple(sorted(set(issue_ids)))
        for citation_id, issue_ids in (citation_issue_ids or {}).items()
    }
    authoritative_issue_ids = set(valid_issue_ids) if valid_issue_ids is not None else None

    issues: list[ClaimCitationIssue] = []
    for claim in claims:
        unknown: list[str] = []
        if issue_map:
            if not claim.issue_ids:
                issues.append(ClaimCitationIssue(claim.claim_id, "UNRELATED_CLAIM"))
            elif authoritative_issue_ids is not None:
                unknown = sorted(set(claim.issue_ids) - authoritative_issue_ids)
                if unknown:
                    issues.append(
                        ClaimCitationIssue(claim.claim_id, "UNKNOWN_CLAIM_ISSUE")
                    )

        if not claim.citation_ids:
            issues.append(ClaimCitationIssue(claim.claim_id, "UNCITED_CLAIM"))
            continue

        claim_issue_set = set(claim.issue_ids)
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

            citation_issues = issue_map.get(citation_id, ())
            if (
                issue_map
                and claim.issue_ids
                and citation_issues
                and not claim_issue_set.intersection(citation_issues)
                and not unknown
            ):
                issues.append(
                    ClaimCitationIssue(
                        claim.claim_id,
                        "CROSS_ISSUE_CITATION",
                        citation_id,
                    )
                )

            resolution = resolve_citation(citation, evidence_map)
            issues.extend(
                ClaimCitationIssue(claim.claim_id, code, citation_id)
                for code in resolution.error_codes
            )
    return tuple(issues)
