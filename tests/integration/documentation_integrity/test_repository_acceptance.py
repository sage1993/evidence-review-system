"""Repository-wide documentation integrity acceptance gate."""

from pathlib import Path

from ansim_review.documentation_integrity.contract import report_bytes
from ansim_review.documentation_integrity.validator import validate_documentation

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_repository_documentation_has_no_errors() -> None:
    report = validate_documentation(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / "documentation-integrity.json",
    )
    assert report.status == "PASS", report_bytes(report).decode("utf-8")
    assert report.error_count == 0
