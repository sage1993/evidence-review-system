"""Bind deterministic issue coverage to immutable review-run inputs."""

from __future__ import annotations

from evidence_review.retrieval.coverage import CoverageReport


def coverage_report_document(report: CoverageReport) -> list[dict[str, object]]:
    """Return canonical issue coverage in QuestionPlan order."""
    return [
        {
            "issue_id": item.issue_id,
            "status": item.status,
            "evidence_ids": list(item.evidence_ids),
            "covered_roles": list(item.covered_roles),
            "missing_roles": list(item.missing_roles),
            "gap_codes": list(item.gap_codes),
        }
        for item in report.issues
    ]


def bind_issue_coverage_to_review_request(
    request: dict[str, object],
    report: CoverageReport,
) -> dict[str, object]:
    """Attach issue coverage without mutating the caller's request."""
    inputs_value = request.get("inputs")
    if not isinstance(inputs_value, dict) or not all(
        isinstance(key, str) for key in inputs_value
    ):
        raise ValueError("review request inputs must be an object")
    bound = dict(request)
    inputs = dict(inputs_value)
    inputs["issue_coverage"] = coverage_report_document(report)
    bound["inputs"] = inputs
    return bound
