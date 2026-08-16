"""Issue-scoped finalization policy for partial review results."""

from __future__ import annotations

from collections.abc import Sequence

from evidence_review.contracts.review import IssueResult

_SUPPORTED_STATUSES = frozenset({"RESOLVED", "CONDITIONAL"})


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
