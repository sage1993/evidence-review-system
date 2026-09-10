"""Shared Review Workspace shell for reference-only and visual review modes."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape


def workspace_mode(model: Mapping[str, object]) -> str:
    """Return the presentation mode without changing packet authority."""
    return "reference-subject" if model.get("case_visual_review") is not None else "reference-only"


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
    mode = escape(workspace_mode(model), quote=True)
    return (
        '<main class="review-workspace" data-review-workspace="unified" '
        f'data-review-workspace-mode="{mode}" data-review-shell="unified">'
        '<section class="review-shell-region" data-review-shell-region="status-question">'
        f"{status_question}</section>"
        '<section class="review-shell-region" data-review-shell-region="evidence-workspace">'
        f"{evidence_workspace}</section>"
        '<section class="review-shell-region" data-review-shell-region="detail-issue-results">'
        f"{detail_issue_results}</section>"
        '<section class="review-shell-region" data-review-shell-region="human-decision">'
        f"{human_decision}</section>"
        '<section class="review-shell-region" data-review-shell-region="audit">'
        f"{audit}</section>"
        "</main>"
    )


__all__ = ["render_workspace", "workspace_mode"]
