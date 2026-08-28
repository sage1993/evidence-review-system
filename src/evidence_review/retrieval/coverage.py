"""Deterministic issue coverage and source-gap classification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from evidence_review.contracts.question_plan import EvidenceRole, QuestionPlan
from evidence_review.retrieval.facets import FacetCoverageReport
from evidence_review.retrieval.graph import MissingReference
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle

IssueStatus = Literal[
    "RESOLVED",
    "CONDITIONAL",
    "CONFLICT",
    "SOURCE_MISSING",
    "UNRESOLVED",
]
GapCode = Literal[
    "RETRIEVAL_MISS",
    "SOURCE_NOT_INGESTED",
    "REFERENCE_TARGET_MISSING",
    "PARSE_GAP",
    "MISSING_REQUIRED_FACET",
    "AMBIGUOUS_RULE",
    "CONFLICTING_RULES",
]

_GAP_ORDER: dict[GapCode, int] = {
    "CONFLICTING_RULES": 0,
    "AMBIGUOUS_RULE": 1,
    "SOURCE_NOT_INGESTED": 2,
    "REFERENCE_TARGET_MISSING": 3,
    "PARSE_GAP": 4,
    "MISSING_REQUIRED_FACET": 5,
    "RETRIEVAL_MISS": 6,
}


@dataclass(frozen=True, slots=True)
class IssueSupport:
    issue_id: str
    status: IssueStatus
    evidence_ids: tuple[str, ...]
    covered_roles: tuple[EvidenceRole, ...]
    missing_roles: tuple[EvidenceRole, ...]
    gap_codes: tuple[GapCode, ...]


@dataclass(frozen=True, slots=True)
class CoverageReport:
    issues: tuple[IssueSupport, ...]

    def by_issue_id(self, issue_id: str) -> IssueSupport:
        for issue in self.issues:
            if issue.issue_id == issue_id:
                return issue
        raise KeyError(issue_id)

    @property
    def resolved_issue_count(self) -> int:
        return sum(
            issue.status in {"RESOLVED", "CONDITIONAL"}
            for issue in self.issues
        )


def _ordered_gap_codes(values: Sequence[GapCode]) -> tuple[GapCode, ...]:
    return tuple(sorted(set(values), key=lambda item: (_GAP_ORDER[item], item)))


def _candidate_role_state(
    bundle: IssueRetrievalBundle,
    issue_id: str,
) -> tuple[set[EvidenceRole], set[EvidenceRole], set[str]]:
    semantic_roles: set[EvidenceRole] = set()
    citation_roles: set[EvidenceRole] = set()
    evidence_ids: set[str] = set()
    for candidate in bundle.candidates:
        issue_matches = tuple(
            match for match in candidate.matches if match.issue_id == issue_id
        )
        if not issue_matches:
            continue
        roles = {match.role for match in issue_matches}
        semantic_roles.update(roles)
        if not candidate.evidence:
            continue
        citation_roles.update(roles)
        evidence_ids.update(hit.evidence_id for hit in candidate.evidence)
    for reference in bundle.reference_matches:
        if reference.issue_id != issue_id:
            continue
        semantic_roles.add(reference.role)
        citation_roles.add(reference.role)
        evidence_ids.add(reference.evidence_id)
    return semantic_roles, citation_roles, evidence_ids


def _bundle_reference_missing(
    bundle: IssueRetrievalBundle,
) -> dict[str, tuple[MissingReference, ...]]:
    grouped: dict[str, list[MissingReference]] = {}
    for item in bundle.reference_missing:
        grouped.setdefault(item.issue_id, []).append(item.reference)
    return {
        issue_id: tuple(values)
        for issue_id, values in sorted(grouped.items())
    }


def _complete_facet_evidence_ids(
    facet_report: FacetCoverageReport,
    issue_id: str,
) -> set[str] | None:
    issue = facet_report.by_issue_id(issue_id)
    if issue.missing_facet_ids:
        return None
    evidence_ids = {
        evidence_id
        for _facet_id, facet_evidence_ids in issue.evidence_by_facet
        for evidence_id in facet_evidence_ids
    }
    return evidence_ids or None


def evaluate_issue_coverage(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
    *,
    facet_report: FacetCoverageReport | None = None,
    reference_missing_by_issue: Mapping[str, tuple[MissingReference, ...]] | None = None,
    source_missing_issue_ids: Sequence[str] = (),
    ambiguous_issue_ids: Sequence[str] = (),
    conflicting_issue_ids: Sequence[str] = (),
    conditional_issue_ids: Sequence[str] = (),
) -> CoverageReport:
    """Classify every planned issue after retrieval/fallback/reference expansion.

    Precedence is fail-closed and diagnostic:
    conflict > ambiguity > source/reference missing > retrieval/parse failure
    > required facet completeness > complete evidence (resolved/conditional).

    A required facet is only meaningful after the required evidence role has
    citation-grade support. When no candidate exists, retain ``RETRIEVAL_MISS``
    rather than masking the retrieval failure as ``MISSING_REQUIRED_FACET``.

    When all required facets are already supported by direct citation-grade
    evidence, a missing external reference only taints the issue if it originates
    from evidence that directly supports one of those facets. This prevents
    unrelated context selected in the same issue from creating a false source gap.
    """
    reference_missing = (
        _bundle_reference_missing(bundle)
        if reference_missing_by_issue is None
        else dict(reference_missing_by_issue)
    )
    source_missing = set(source_missing_issue_ids)
    ambiguous = set(ambiguous_issue_ids)
    conflicting = set(conflicting_issue_ids)
    conditional = set(conditional_issue_ids)
    known_issue_ids = {issue.id for issue in plan.issues}

    supplied_ids = (
        set(reference_missing)
        | source_missing
        | ambiguous
        | conflicting
        | conditional
    )
    unknown = sorted(supplied_ids - known_issue_ids)
    if unknown:
        raise ValueError("coverage input references unknown issue ids: " + ", ".join(unknown))
    if facet_report is not None:
        facet_issue_ids = {item.issue_id for item in facet_report.issues}
        if facet_issue_ids != known_issue_ids:
            raise ValueError("facet coverage issue ids must exactly match question plan issues")

    supports: list[IssueSupport] = []
    for issue in plan.issues:
        semantic_roles, citation_roles, evidence_ids = _candidate_role_state(
            bundle,
            issue.id,
        )
        required = set(issue.required_evidence_roles)
        covered = required & citation_roles
        missing = required - covered
        missing_facets = (
            ()
            if facet_report is None
            else facet_report.by_issue_id(issue.id).missing_facet_ids
        )
        gaps: list[GapCode] = []

        if issue.id in conflicting:
            status: IssueStatus = "CONFLICT"
            gaps.append("CONFLICTING_RULES")
        elif issue.id in ambiguous:
            status = "UNRESOLVED"
            gaps.append("AMBIGUOUS_RULE")
        else:
            missing_references = reference_missing.get(issue.id, ())
            if facet_report is not None:
                facet_evidence_ids = _complete_facet_evidence_ids(
                    facet_report,
                    issue.id,
                )
                if facet_evidence_ids is not None:
                    missing_references = tuple(
                        item
                        for item in missing_references
                        if item.source_id in facet_evidence_ids
                    )
            if issue.id in source_missing or any(
                item.reason_code == "SOURCE_NOT_INGESTED"
                for item in missing_references
            ):
                gaps.append("SOURCE_NOT_INGESTED")
            if any(
                item.reason_code
                in {"REFERENCE_TARGET_MISSING", "STALE_SAME_DOCUMENT_REVISION"}
                for item in missing_references
            ):
                gaps.append("REFERENCE_TARGET_MISSING")

            if gaps:
                status = "SOURCE_MISSING"
            elif missing:
                if missing & semantic_roles:
                    status = "UNRESOLVED"
                    gaps.append("PARSE_GAP")
                else:
                    status = "UNRESOLVED"
                    gaps.append("RETRIEVAL_MISS")
            elif missing_facets:
                status = "UNRESOLVED"
                gaps.append("MISSING_REQUIRED_FACET")
            elif issue.id in conditional:
                status = "CONDITIONAL"
            else:
                status = "RESOLVED"

        supports.append(
            IssueSupport(
                issue_id=issue.id,
                status=status,
                evidence_ids=tuple(sorted(evidence_ids)),
                covered_roles=tuple(sorted(covered)),
                missing_roles=tuple(sorted(missing)),
                gap_codes=_ordered_gap_codes(gaps),
            )
        )

    return CoverageReport(issues=tuple(supports))
