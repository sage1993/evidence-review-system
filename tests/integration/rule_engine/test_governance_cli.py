from __future__ import annotations

import json
from pathlib import Path

from helpers.rule_governance import build_valid_governance_tree

from ansim_review.canonical_json import dump_bytes
from ansim_review.cli import main

SOURCE_COMMIT = "e" * 40
COMMAND = "python -m ansim_review rules run-golden"


def _stdout(capfd) -> dict[str, object]:
    captured = capfd.readouterr()
    value = json.loads(captured.out)
    assert isinstance(value, dict)
    return value


def test_run_golden_cli_prints_one_canonical_status_object(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.actual_paths[0].unlink()
    tree.golden_report_paths[0].unlink()

    exit_code = main(
        [
            "rules",
            "run-golden",
            "--repository-root",
            str(tmp_path),
            "--fixture-manifest",
            str(tree.fixture_manifest_paths[0]),
            "--actual-root",
            str(tmp_path / "build" / "rules" / "golden" / "actual"),
            "--report",
            str(tree.golden_report_paths[0]),
            "--source-commit",
            SOURCE_COMMIT,
            "--command",
            COMMAND,
        ]
    )
    status = _stdout(capfd)

    assert exit_code == 0
    assert status["format"] == "evidence-review/rule-golden-cli-status"
    assert status["status"] == "PASS"
    assert status["case_count"] == 1


def test_build_active_manifest_cli_outputs_activation_report(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.unlink()
    report_path = tmp_path / "build" / "rules" / "activation" / "report.json"

    exit_code = main(
        [
            "rules",
            "build-active-manifest",
            "--repository-root",
            str(tmp_path),
            "--approvals",
            str(tmp_path / "rules" / "activation" / "approvals"),
            "--output",
            str(tree.manifest_path),
            "--report",
            str(report_path),
        ]
    )
    status = _stdout(capfd)

    assert exit_code == 0
    assert status["format"] == "evidence-review/rule-activation-report"
    assert status["status"] == "ACTIVATED"
    assert status["activated_rule_count"] == 1


def test_select_cli_returns_zero_for_selected_and_abstain(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    context_path = tmp_path / "context.json"
    context_path.write_bytes(dump_bytes({"document_family": "ANSIM"}))

    selected_exit = main(
        [
            "rules",
            "select",
            "--repository-root",
            str(tmp_path),
            "--manifest",
            str(tree.manifest_path),
            "--context",
            str(context_path),
        ]
    )
    selected = _stdout(capfd)

    context_path.write_bytes(dump_bytes({"document_family": "OTHER"}))
    abstain_exit = main(
        [
            "rules",
            "select",
            "--repository-root",
            str(tmp_path),
            "--manifest",
            str(tree.manifest_path),
            "--context",
            str(context_path),
        ]
    )
    abstain = _stdout(capfd)

    assert selected_exit == 0
    assert selected["status"] == "SELECTED"
    assert abstain_exit == 0
    assert abstain["status"] == "ABSTAIN"
    assert abstain["reasons"] == ["NO_APPLICABLE_ACTIVE_RULE"]


def test_select_cli_returns_two_for_blocked_governance(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.candidate_paths[0].write_bytes(tree.candidate_paths[0].read_bytes() + b" ")
    context_path = tmp_path / "context.json"
    context_path.write_bytes(dump_bytes({"document_family": "ANSIM"}))

    exit_code = main(
        [
            "rules",
            "select",
            "--repository-root",
            str(tmp_path),
            "--manifest",
            str(tree.manifest_path),
            "--context",
            str(context_path),
        ]
    )
    status = _stdout(capfd)

    assert exit_code == 2
    assert status["status"] == "BLOCKED"
    assert "CANDIDATE_HASH_MISMATCH" in status["reasons"]
