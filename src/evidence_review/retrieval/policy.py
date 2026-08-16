"""Deterministic retrieval budgets shared across issue-aware review stages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """Hard bounds for issue retrieval, citation materialization, and references."""

    max_issues: int = 8
    max_queries_per_issue: int = 4
    per_issue_role_limit: int = 5
    global_candidate_cap: int = 80
    max_selected_evidence: int = 40
    max_source_elements_per_clause: int = 5
    reference_max_depth: int = 2
    reference_max_nodes_per_issue: int = 12
    reference_max_fanout: int = 6

    def __post_init__(self) -> None:
        positive_fields = (
            "max_issues",
            "max_queries_per_issue",
            "per_issue_role_limit",
            "global_candidate_cap",
            "max_selected_evidence",
            "max_source_elements_per_clause",
            "reference_max_nodes_per_issue",
            "reference_max_fanout",
        )
        for field in positive_fields:
            if getattr(self, field) < 1:
                raise ValueError(f"{field} must be at least 1")
        if self.reference_max_depth < 0:
            raise ValueError("reference_max_depth must be at least 0")
