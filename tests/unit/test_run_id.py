from pathlib import Path

import pytest

from ansim_review.contracts.run_context import compute_run_id, create_run_directory


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


def test_existing_run_directory_is_never_overwritten(tmp_path: Path) -> None:
    run_id = "RUN-0123456789ABCDEF0123"
    created = create_run_directory(tmp_path, run_id)

    assert created == tmp_path / run_id
    with pytest.raises(FileExistsError):
        create_run_directory(tmp_path, run_id)


def test_invalid_run_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid run_id"):
        create_run_directory(tmp_path, "../escape")
