from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from helpers.rule_governance import (
    apply_governance_mutation,
    build_valid_governance_tree,
)

from ansim_review.rule_engine.activation import build_active_manifest
from ansim_review.rule_engine.governance_contract import load_active_rule_manifest_bytes


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _outputs(root: Path) -> tuple[Path, Path]:
    return (
        root / "rules" / "manifests" / "active.json",
        root / "build" / "rules" / "activation" / "activation-report.json",
    )


def test_activation_sorts_verified_approvals_deterministically(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    tree.manifest_path.unlink()
    manifest_path, report_path = _outputs(tmp_path)

    report = build_active_manifest(
        tmp_path,
        tuple(reversed(tree.approval_paths)),
        manifest_path,
        report_path,
    )
    manifest = load_active_rule_manifest_bytes(manifest_path.read_bytes())

    assert report.status == "ACTIVATED"
    assert [item.rule_id for item in manifest.rules] == [
        "TEST-RULE-001",
        "TEST-RULE-002",
    ]
    assert report.active_manifest_sha256 is not None


def test_duplicate_approval_path_blocks_without_manifest(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.unlink()
    manifest_path, report_path = _outputs(tmp_path)

    report = build_active_manifest(
        tmp_path,
        (tree.approval_paths[0], tree.approval_paths[0]),
        manifest_path,
        report_path,
    )

    assert report.status == "BLOCKED"
    assert not manifest_path.exists()
    assert report_path.is_file()
    assert [item.code for item in report.findings] == ["DUPLICATE_APPROVAL_PATH"]


def test_casefold_collision_blocks_before_artifact_access(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    manifest_path, report_path = _outputs(tmp_path)

    report = build_active_manifest(
        tmp_path,
        (Path("Rules/Approval.json"), Path("rules/approval.json")),
        manifest_path,
        report_path,
    )

    assert report.status == "BLOCKED"
    assert not manifest_path.exists()
    assert [item.code for item in report.findings] == ["CASEFOLD_PATH_COLLISION"]


def test_duplicate_rule_id_across_distinct_approval_files_blocks(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.unlink()
    copied = tmp_path / "rules" / "activation" / "approvals" / "copy.json"
    copied.write_bytes(tree.approval_paths[0].read_bytes())
    manifest_path, report_path = _outputs(tmp_path)

    report = build_active_manifest(
        tmp_path,
        (tree.approval_paths[0], copied),
        manifest_path,
        report_path,
    )

    assert report.status == "BLOCKED"
    assert not manifest_path.exists()
    assert [item.code for item in report.findings] == ["DUPLICATE_ACTIVE_RULE_ID"]


def test_one_bad_approval_blocks_every_rule_and_publishes_report_only(
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    tree.manifest_path.unlink()
    apply_governance_mutation(tree, "approval_bytes")
    manifest_path, report_path = _outputs(tmp_path)

    report = build_active_manifest(
        tmp_path,
        tree.approval_paths,
        manifest_path,
        report_path,
    )

    assert report.status == "BLOCKED"
    assert report.activated_rule_count == 0
    assert not manifest_path.exists()
    assert report_path.is_file()
    assert _load(report_path)["status"] == "BLOCKED"


def test_valid_empty_activation_publishes_empty_v2_manifest(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    manifest_path, report_path = _outputs(tmp_path)

    report = build_active_manifest(tmp_path, (), manifest_path, report_path)
    manifest = load_active_rule_manifest_bytes(manifest_path.read_bytes())

    assert report.status == "ACTIVATED"
    assert report.approval_count == 0
    assert report.activated_rule_count == 0
    assert manifest.rules == ()


@pytest.mark.parametrize("collision", ["manifest", "report"])
def test_existing_output_collision_creates_no_partial_outputs(
    tmp_path: Path,
    collision: str,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.unlink()
    manifest_path, report_path = _outputs(tmp_path)
    collision_path = manifest_path if collision == "manifest" else report_path
    collision_path.parent.mkdir(parents=True, exist_ok=True)
    collision_path.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        build_active_manifest(
            tmp_path,
            tree.approval_paths,
            manifest_path,
            report_path,
        )

    assert collision_path.read_bytes() == b"existing"
    other = report_path if collision == "manifest" else manifest_path
    assert not other.exists()


def test_concurrent_report_publication_rolls_back_only_own_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.unlink()
    manifest_path, report_path = _outputs(tmp_path)
    original_link = os.link
    intercepted = False

    def concurrent_link(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal intercepted
        destination_path = Path(destination)
        if destination_path == report_path and not intercepted:
            intercepted = True
            destination_path.write_bytes(b"competing report")
        original_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", concurrent_link)

    with pytest.raises(FileExistsError):
        build_active_manifest(
            tmp_path,
            tree.approval_paths,
            manifest_path,
            report_path,
        )

    assert not manifest_path.exists()
    assert report_path.read_bytes() == b"competing report"
