from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ansim_review.workflow.request import ReviewRequest, decode_review_request
from ansim_review.workflow.versioning import (
    compute_versioned_run_id,
    prepare_versioned_review_run,
)


def _request() -> ReviewRequest:
    return decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "媛믪쓣 寃?좏빀?덈뒗媛?",
            "attachments": [],
        }
    )


@pytest.mark.parametrize(
    ("change", "expected_distinct"),
    (
        ("request", True),
        ("evidence_version", True),
        ("rule_version", True),
        ("formula_version", True),
    ),
)
def test_request_and_engine_versions_derive_new_run(
    tmp_path: Path,
    change: str,
    expected_distinct: bool,
) -> None:
    request = _request()
    changed_request = replace(request, question=request.question + "!")
    first = compute_versioned_run_id(
        request,
        evidence_version="evidence-v1",
        rule_version="rules-v1",
        formula_version="formulas-v1",
    )
    second = compute_versioned_run_id(
        changed_request if change == "request" else request,
        evidence_version="evidence-v2" if change == "evidence_version" else "evidence-v1",
        rule_version="rules-v2" if change == "rule_version" else "rules-v1",
        formula_version="formulas-v2" if change == "formula_version" else "formulas-v1",
    )

    assert (first != second) is expected_distinct
    first_layout = prepare_versioned_review_run(
        tmp_path / "runs",
        request,
        evidence_version="evidence-v1",
        rule_version="rules-v1",
        formula_version="formulas-v1",
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    second_layout = prepare_versioned_review_run(
        tmp_path / "runs",
        changed_request if change == "request" else request,
        evidence_version="evidence-v2" if change == "evidence_version" else "evidence-v1",
        rule_version="rules-v2" if change == "rule_version" else "rules-v1",
        formula_version="formulas-v2" if change == "formula_version" else "formulas-v1",
        recorded_at="2026-08-04T00:00:00+09:00",
    )

    assert first_layout.run_id != second_layout.run_id
    assert first_layout.run_dir.is_dir()
    assert second_layout.run_dir.is_dir()


def test_same_request_and_versions_resume_same_run(tmp_path: Path) -> None:
    first = prepare_versioned_review_run(
        tmp_path / "runs",
        _request(),
        evidence_version="evidence-v1",
        rule_version="rules-v1",
        formula_version="formulas-v1",
        recorded_at="2026-08-04T00:00:00+09:00",
    )
    second = prepare_versioned_review_run(
        tmp_path / "runs",
        _request(),
        evidence_version="evidence-v1",
        rule_version="rules-v1",
        formula_version="formulas-v1",
        recorded_at="2026-08-04T00:01:00+09:00",
    )

    assert first.run_id == second.run_id
    assert (first.machine_dir / "version-binding.json").read_bytes() == (
        second.machine_dir / "version-binding.json"
    ).read_bytes()
