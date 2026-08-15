"""Issue-scoped finalization policy for partial review results."""

from __future__ import annotations

from collections.abc import Sequence

from evidence_review.contracts.review import IssueResult

_SUPPORTED_STATUSES = frozenset({"RESOLVED", "CONDITIONAL"})


def issue_results_require_global_abstain(issue_results: Sequence[IssueResult]) -> bool:
    """Return True only when issue-aware coverage exists and none is supported.

    Empty issue results mean a legacy/non-planned run and therefore do not override
    the existing missing-input abstention policy.
    """
    if not issue_results:
        return False
    return not any(item.status in _SUPPORTED_STATUSES for item in issue_results)
