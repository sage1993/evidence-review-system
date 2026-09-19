"""Shared Review Workspace shell for reference-only and visual review modes."""

from __future__ import annotations

from collections.abc import Mapping


def workspace_mode(model: Mapping[str, object]) -> str:
    """Return the presentation mode without changing packet authority."""
    return "reference-subject" if model.get("case_visual_review") is not None else "reference-only"


def workspace_capabilities(model: Mapping[str, object]) -> dict[str, bool]:
    """Return capability flags used by the shared shell, not template modes."""
    value = model.get("capabilities")
    if isinstance(value, Mapping):
        return {
            key: bool(value.get(key, False))
            for key in ("has_reference", "has_subject", "has_comparison")
        }
    return {
        "has_reference": bool(model.get("reference_citations")),
        "has_subject": model.get("case_visual_review") is not None,
        "has_comparison": bool(model.get("comparisons")),
    }


def render_workspace(
    model: Mapping[str, object],
    *,
    status_question: str,
    evidence_workspace: str,
    detail_issue_results: str,
    human_decision: str,
    audit: str,
) -> str:
    """Render the common reviewer landmarks for every review presentation."""
    capabilities = workspace_capabilities(model)
    return (
        '<main class="review-workspace" data-review-workspace="unified" '
        'data-review-shell="unified" '
        f'data-has-reference="{str(capabilities["has_reference"]).lower()}" '
        f'data-has-subject="{str(capabilities["has_subject"]).lower()}" '
        f'data-has-comparison="{str(capabilities["has_comparison"]).lower()}">'
        '<section class="review-shell-region" data-review-shell-region="status-question" '
        'data-review-region="status-question">'
        f"{status_question}</section>"
        '<section class="review-shell-region" data-review-shell-region="evidence-workspace" '
        'data-review-region="evidence-workspace">'
        f"{evidence_workspace}</section>"
        '<section class="review-shell-region" data-review-shell-region="detail-issue-results" '
        'data-review-region="detail-issue-results">'
        f"{detail_issue_results}</section>"
        '<section class="review-shell-region" data-review-shell-region="human-decision" '
        'data-review-region="human-decision">'
        f"{human_decision}</section>"
        '<section class="review-shell-region" data-review-shell-region="audit" '
        'data-review-region="audit">'
        f"{audit}</section>"
        "</main>"
    )


__all__ = ["render_workspace", "workspace_capabilities", "workspace_mode"]
