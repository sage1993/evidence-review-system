from __future__ import annotations

import pytest

from evidence_review.release.builder import _automated_reason_codes


@pytest.mark.parametrize(
    ("workspace", "output", "expected"),
    [
        ({"status": "PASS"}, {"status": "PASS"}, []),
        (
            {"status": "FAIL", "errors": []},
            {"status": "PASS"},
            ["AUTOMATED_VALIDATION_FAILED"],
        ),
        (
            {"status": "PASS"},
            {"status": "FAIL"},
            ["RELEASE_OUTPUT_VALIDATION_FAILED"],
        ),
        (
            {"status": "FAIL", "errors": ["DOCUMENTATION_INTEGRITY_FAILED"]},
            {"status": "PASS"},
            ["AUTOMATED_VALIDATION_FAILED", "DOCUMENTATION_INTEGRITY_FAILED"],
        ),
        (
            {"status": "FAIL", "errors": ["DOCUMENTATION_INTEGRITY_FAILED"]},
            {"status": "FAIL"},
            [
                "AUTOMATED_VALIDATION_FAILED",
                "DOCUMENTATION_INTEGRITY_FAILED",
                "RELEASE_OUTPUT_VALIDATION_FAILED",
            ],
        ),
    ],
)
def test_automated_release_gate_reports_independent_failures(
    workspace: dict[str, object],
    output: dict[str, object],
    expected: list[str],
) -> None:
    assert _automated_reason_codes(workspace, output) == expected
