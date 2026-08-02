from __future__ import annotations

import pytest

from ansim_review.release.builder import _automated_reason_codes


@pytest.mark.parametrize(
    ("workspace_status", "output_status", "expected"),
    [
        ("PASS", "PASS", []),
        ("FAIL", "PASS", ["AUTOMATED_VALIDATION_FAILED"]),
        ("PASS", "FAIL", ["RELEASE_OUTPUT_VALIDATION_FAILED"]),
        (
            "FAIL",
            "FAIL",
            ["AUTOMATED_VALIDATION_FAILED", "RELEASE_OUTPUT_VALIDATION_FAILED"],
        ),
    ],
)
def test_automated_release_gate_reports_independent_failures(
    workspace_status: str,
    output_status: str,
    expected: list[str],
) -> None:
    assert _automated_reason_codes(
        {"status": workspace_status},
        {"status": output_status},
    ) == expected
