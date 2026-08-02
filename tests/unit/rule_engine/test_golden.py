from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from helpers.rule_governance import GovernanceTree, build_valid_governance_tree

from ansim_review.canonical_json import dump_bytes
from ansim_review.rule_engine.golden import run_rule_golden

SOURCE_COMMIT = "d" * 40
COMMAND = "python -m ansim_review rules run-golden"


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_object(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(dump_bytes(payload))


def _prepare(tree: GovernanceTree) -> None:
    for path in (*tree.actual_paths, *tree.golden_report_paths):
        path.unlink(missing_ok=True)


def _run(tree: GovernanceTree):
    return run_rule_golden(
        tree.root,
        tree.fixture_manifest_paths[0],
        tree.root / "build" / "rules" / "golden" / "actual",
        tree.golden_report_paths[0],
        source_commit=SOURCE_COMMIT,
        command=COMMAND,
    )


def test_golden_runner_publishes_passing_actual_and_report(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    _prepare(tree)

    report = _run(tree)

    assert report.status == "PASS"
    assert report.case_count == 1
    assert report.passed_count == 1
    assert report.failed_count == 0
    assert tree.actual_paths[0].read_bytes() == tree.expected_paths[0].read_bytes()
    assert tree.golden_report_paths[0].is_file()


def test_expected_mismatch_publishes_fail_report_and_actual(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    _prepare(tree)
    tree.expected_paths[0].write_bytes(tree.expected_paths[0].read_bytes() + b" ")

    report = _run(tree)

    assert report.status == "FAIL"
    assert report.passed_count == 0
    assert report.failed_count == 1
    assert tree.actual_paths[0].is_file()
    assert tree.actual_paths[0].read_bytes() != tree.expected_paths[0].read_bytes()


def test_duplicate_case_ids_are_rejected_before_publication(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    _prepare(tree)
    payload = _load_object(tree.fixture_manifest_paths[0])
    cases = payload["cases"]
    assert isinstance(cases, list)
    cases.append(dict(cases[0]))
    _write_object(tree.fixture_manifest_paths[0], payload)

    with pytest.raises(ValueError, match="duplicate case_id"):
        _run(tree)

    assert not tree.actual_paths[0].exists()
    assert not tree.golden_report_paths[0].exists()


def test_unresolved_evidence_is_evaluated_and_reported_as_mismatch(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    _prepare(tree)
    fixture = _load_object(tree.fixture_paths[0])
    fixture["evidence_records"] = []
    _write_object(tree.fixture_paths[0], fixture)

    report = _run(tree)
    actual = _load_object(tree.actual_paths[0])

    assert report.status == "FAIL"
    assert actual["status"] == "ENGINE_ERROR"
    assert actual["reason_codes"] == ["UNRESOLVED_RULE_SOURCE"]


def test_invalid_calculation_reference_is_evaluated_and_reported(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    _prepare(tree)
    approved = _load_object(tree.approved_rule_paths[0])
    approved["expression"] = {
        "calculation": {
            "calculation_result_id": "CALC-MISSING",
            "field": "status",
            "operator": "eq",
            "value": "SUCCESS",
        }
    }
    _write_object(tree.approved_rule_paths[0], approved)

    report = _run(tree)
    actual = _load_object(tree.actual_paths[0])

    assert report.status == "FAIL"
    assert actual["status"] == "ENGINE_ERROR"
    assert actual["reason_codes"] == ["INVALID_CALCULATION_REFERENCE"]


def test_outputs_are_byte_identical_across_separate_roots(tmp_path: Path) -> None:
    first = build_valid_governance_tree(tmp_path / "first")
    second = build_valid_governance_tree(tmp_path / "second")
    _prepare(first)
    _prepare(second)

    _run(first)
    _run(second)

    assert first.actual_paths[0].read_bytes() == second.actual_paths[0].read_bytes()
    assert first.golden_report_paths[0].read_bytes() == second.golden_report_paths[0].read_bytes()


def test_existing_output_blocks_all_publication(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.golden_report_paths[0].unlink()
    existing = tree.actual_paths[0].read_bytes()

    with pytest.raises(FileExistsError):
        _run(tree)

    assert tree.actual_paths[0].read_bytes() == existing
    assert not tree.golden_report_paths[0].exists()


def test_concurrent_publication_never_deletes_competing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    _prepare(tree)
    actual_path = tree.actual_paths[0]
    original_link = os.link
    intercepted = False

    def concurrent_link(source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                        *args: object,
                        **kwargs: object) -> None:
        nonlocal intercepted
        destination_path = Path(destination)
        if destination_path == actual_path and not intercepted:
            intercepted = True
            destination_path.write_bytes(b"competing publisher")
        original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", concurrent_link)

    with pytest.raises(FileExistsError):
        _run(tree)

    assert actual_path.read_bytes() == b"competing publisher"
    assert not tree.golden_report_paths[0].exists()
