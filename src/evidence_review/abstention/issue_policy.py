"""Issue-scoped finalization policy for partial review results."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from evidence_review.contracts.review import Claim, IssueResult, IssueStatus

_SUPPORTED_STATUSES = frozenset({"RESOLVED", "CONDITIONAL"})


def _missing_input_targets_issue(value: str, issue_id: str) -> bool:
    """Return whether a Track A missing-input entry is explicitly issue-scoped."""
    return re.match(
        rf"^\s*{re.escape(issue_id)}(?:\s*[:：\-–—]\s*|\s+)",
        value,
        flags=re.IGNORECASE,
    ) is not None


def reconcile_issue_results(
    issue_results: Sequence[IssueResult],
    *,
    claims: Sequence[Claim],
    track_a_missing_inputs: Sequence[str],
) -> tuple[IssueResult, ...]:
    """Reconcile retrieval coverage with the evidence Track A actually used.

    Retrieval coverage is necessary but not sufficient for final resolution. A
    RESOLVED/CONDITIONAL issue must have at least one Track A claim linked to the
    issue. An explicitly issue-scoped missing input prevents a final RESOLVED
    state even when retrieval coverage looked complete.
    """
    claim_counts: dict[str, int] = {}
    for claim in claims:
        for issue_id in claim.issue_ids:
            claim_counts[issue_id] = claim_counts.get(issue_id, 0) + 1

    reconciled: list[IssueResult] = []
    for result in issue_results:
        if result.status not in _SUPPORTED_STATUSES:
            reconciled.append(result)
            continue
        has_claim = claim_counts.get(result.issue_id, 0) > 0
        has_blocking_missing = any(
            _missing_input_targets_issue(value, result.issue_id)
            for value in track_a_missing_inputs
        )
        status: IssueStatus
        if not has_claim:
            status = "SOURCE_MISSING" if has_blocking_missing else "UNRESOLVED"
        elif result.status == "RESOLVED" and has_blocking_missing:
            status = "CONDITIONAL"
        else:
            status = result.status
        reconciled.append(replace(result, status=status))
    return tuple(reconciled)


def has_partial_issue_resolution(issue_results: Sequence[IssueResult]) -> bool:
    """Return whether determinate and unresolved issue states coexist."""
    if not issue_results:
        return False
    supported = [item.status in _SUPPORTED_STATUSES for item in issue_results]
    return any(supported) and not all(supported)


def issue_results_require_global_abstain(
    issue_results: Sequence[IssueResult],
    *,
    deterministic_missing_inputs: bool = False,
) -> bool:
    """Return whether missing-input policy requires a global abstention.

    Deterministic rule-engine missing inputs remain a global hard gate. Issue-aware
    coverage only relaxes issue-scoped insufficiency when at least one issue is
    RESOLVED or CONDITIONAL. Empty issue results are legacy/non-planned and do not
    override the existing missing-input policy at the caller.
    """
    if deterministic_missing_inputs:
        return True
    if not issue_results:
        return False
    return not any(item.status in _SUPPORTED_STATUSES for item in issue_results)
