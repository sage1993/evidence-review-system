from pathlib import Path

import pytest

from evidence_review.contracts.run_context import (
    compute_run_id,
    compute_run_id_from_request,
    create_run_directory,
)


def test_equivalent_input_order_yields_same_run_id() -> None:
    first = compute_run_id(
        question="기준 충족 여부",
        inputs={"b": 2, "a": 1},
        evidence_hash="e" * 64,
        rule_hash="r" * 64,
        formula_hash="f" * 64,
    )
    second = compute_run_id(
        question="기준 충족 여부",
        inputs={"a": 1, "b": 2},
        evidence_hash="e" * 64,
        rule_hash="r" * 64,
        formula_hash="f" * 64,
    )

    assert first == second
    assert first.startswith("RUN-")
    assert len(first) == 24


def _request() -> dict[str, object]:
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": "기준 충족 여부",
        "inputs": {"site_area_m2": "1500"},
        "evidence": [],
        "calculations": [],
        "rules": [],
        "approved_rule_result_ids": ["RULE-1"],
        "confidence_input": {
            "factors": {
                "citation_completeness": {
                    "value": "1",
                    "source": "deterministic-audit",
                }
            }
        },
    }


def test_run_id_changes_when_approved_rules_change() -> None:
    first = _request()
    second = _request()
    second["approved_rule_result_ids"] = ["RULE-1", "RULE-2"]
    assert compute_run_id_from_request(first) != compute_run_id_from_request(second)


def test_run_id_changes_when_confidence_input_changes() -> None:
    first = _request()
    second = _request()
    confidence = second["confidence_input"]
    assert isinstance(confidence, dict)
    factors = confidence["factors"]
    assert isinstance(factors, dict)
    factor = factors["citation_completeness"]
    assert isinstance(factor, dict)
    factor["value"] = "0.5"
    assert compute_run_id_from_request(first) != compute_run_id_from_request(second)


def test_request_key_order_does_not_change_run_id() -> None:
    request = _request()
    reordered = {key: request[key] for key in reversed(tuple(request))}
    assert compute_run_id_from_request(request) == compute_run_id_from_request(reordered)


def test_existing_run_directory_is_never_overwritten(tmp_path: Path) -> None:
    run_id = "RUN-0123456789ABCDEF0123"
    created = create_run_directory(tmp_path, run_id)

    assert created == tmp_path / run_id
    with pytest.raises(FileExistsError):
        create_run_directory(tmp_path, run_id)


def test_invalid_run_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid run_id"):
        create_run_directory(tmp_path, "../escape")
