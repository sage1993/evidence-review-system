from __future__ import annotations

import pytest

from evidence_review.retrieval.policy import RetrievalPolicy


def test_default_retrieval_policy_matches_pr_budget() -> None:
    policy = RetrievalPolicy()

    assert policy.max_issues == 8
    assert policy.max_queries_per_issue == 4
    assert policy.per_issue_role_limit == 5
    assert policy.global_candidate_cap == 80
    assert policy.max_selected_evidence == 40
    assert policy.max_source_elements_per_clause == 5
    assert policy.reference_max_depth == 2
    assert policy.reference_max_nodes_per_issue == 12
    assert policy.reference_max_fanout == 6


@pytest.mark.parametrize(
    "field",
    [
        "max_issues",
        "max_queries_per_issue",
        "per_issue_role_limit",
        "global_candidate_cap",
        "max_selected_evidence",
        "max_source_elements_per_clause",
        "reference_max_nodes_per_issue",
        "reference_max_fanout",
    ],
)
def test_retrieval_policy_rejects_non_positive_limits(field: str) -> None:
    values = RetrievalPolicy().__dict__ if hasattr(RetrievalPolicy(), "__dict__") else None
    kwargs = {
        "max_issues": 8,
        "max_queries_per_issue": 4,
        "per_issue_role_limit": 5,
        "global_candidate_cap": 80,
        "max_selected_evidence": 40,
        "max_source_elements_per_clause": 5,
        "reference_max_depth": 2,
        "reference_max_nodes_per_issue": 12,
        "reference_max_fanout": 6,
    }
    assert values is None
    kwargs[field] = 0

    with pytest.raises(ValueError, match=field):
        RetrievalPolicy(**kwargs)


def test_retrieval_policy_allows_zero_reference_depth() -> None:
    assert RetrievalPolicy(reference_max_depth=0).reference_max_depth == 0


def test_retrieval_policy_rejects_negative_reference_depth() -> None:
    with pytest.raises(ValueError, match="reference_max_depth"):
        RetrievalPolicy(reference_max_depth=-1)
