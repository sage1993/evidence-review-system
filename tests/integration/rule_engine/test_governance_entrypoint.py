from __future__ import annotations

import json
from pathlib import Path

from helpers.rule_governance import build_valid_governance_tree

from evidence_review.cli import main


def _stdout(capfd) -> dict[str, object]:
    captured = capfd.readouterr()
    value = json.loads(captured.out)
    assert isinstance(value, dict)
    return value


def test_canonical_select_rejects_duplicate_context_keys(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    context_path = tmp_path / "context.json"
    context_path.write_bytes(
        b'{"document_family":"ANSIM","document_family":"OTHER"}'
    )

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
    captured = capfd.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "duplicate JSON key: document_family" in captured.err


def test_canonical_select_preserves_normal_abstention_exit_zero(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    context_path = tmp_path / "context.json"
    context_path.write_text('{"document_family":"OTHER"}', encoding="utf-8")

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

    assert exit_code == 0
    assert status["status"] == "ABSTAIN"
    assert status["reasons"] == ["NO_APPLICABLE_ACTIVE_RULE"]


def test_canonical_activation_does_not_hide_json_symlink(
    tmp_path: Path,
    capfd,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.unlink()
    symlink_path = tree.approval_paths[0].parent / "linked.json"
    try:
        symlink_path.symlink_to(tree.approval_paths[0].name)
    except OSError:
        return
    output = tree.manifest_path
    report = tmp_path / "build" / "rules" / "activation" / "report.json"

    exit_code = main(
        [
            "rules",
            "build-active-manifest",
            "--repository-root",
            str(tmp_path),
            "--approvals",
            str(tree.approval_paths[0].parent),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )
    status = _stdout(capfd)

    assert exit_code == 2
    assert status["status"] == "BLOCKED"
    assert not output.exists()
    assert any(item["code"] == "UNSAFE_ARTIFACT_PATH" for item in status["findings"])
