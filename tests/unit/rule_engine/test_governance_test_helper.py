from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ansim_review.rule_engine.governance_contract import (
    load_active_rule_manifest_bytes,
    load_rule_activation_approval_bytes,
    load_rule_golden_report_bytes,
)
from tests.helpers.rule_governance import (
    GOVERNANCE_MUTATIONS,
    GovernanceTree,
    apply_governance_mutation,
    build_valid_governance_tree,
)


def _all_paths(tree: GovernanceTree) -> tuple[Path, ...]:
    return (
        tree.manifest_path,
        *tree.approval_paths,
        *tree.golden_report_paths,
        *tree.candidate_paths,
        *tree.approved_rule_paths,
        *tree.fixture_manifest_paths,
        *tree.fixture_paths,
        *tree.expected_paths,
        *tree.actual_paths,
    )


def _digests(tree: GovernanceTree) -> dict[Path, str]:
    return {
        path.relative_to(tree.root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _all_paths(tree)
    }


def _expected_changed_paths(tree: GovernanceTree, mutation: str) -> set[Path]:
    mapping = {
        "active_manifest_bytes": {tree.manifest_path},
        "approval_bytes": {tree.approval_paths[0]},
        "golden_report_bytes": {tree.golden_report_paths[0]},
        "candidate_bytes": {tree.candidate_paths[0]},
        "approved_rule_bytes": {tree.approved_rule_paths[0]},
        "fixture_manifest_bytes": {tree.fixture_manifest_paths[0]},
        "fixture_bytes": {tree.fixture_paths[0]},
        "expected_bytes": {tree.expected_paths[0]},
        "path_traversal": {tree.approval_paths[0]},
        "duplicate_rule_id": {tree.manifest_path},
    }
    return {path.relative_to(tree.root) for path in mapping[mutation]}


def test_builder_creates_complete_strict_governance_graph(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)

    assert tree.root == tmp_path
    assert len(tree.approval_paths) == 2
    assert len(tree.golden_report_paths) == 2
    assert len(tree.candidate_paths) == 2
    assert len(tree.approved_rule_paths) == 2
    assert len(tree.fixture_manifest_paths) == 2
    assert len(tree.fixture_paths) == 2
    assert len(tree.expected_paths) == 2
    assert len(tree.actual_paths) == 2
    assert all(path.is_file() for path in _all_paths(tree))

    manifest = load_active_rule_manifest_bytes(tree.manifest_path.read_bytes())
    assert [entry.rule_id for entry in manifest.rules] == [
        "TEST-RULE-001",
        "TEST-RULE-002",
    ]
    for approval_path, report_path in zip(
        tree.approval_paths, tree.golden_report_paths, strict=True
    ):
        approval = load_rule_activation_approval_bytes(approval_path.read_bytes())
        report = load_rule_golden_report_bytes(report_path.read_bytes())
        assert approval.rule_id == report.rule_id
        assert approval.rule_version == report.rule_version
        assert approval.scope.document_family == "ANSIM"
        assert report.status == "PASS"
        assert report.case_count == 1


@pytest.mark.parametrize("mutation", GOVERNANCE_MUTATIONS)
def test_mutation_changes_only_declared_artifact(
    mutation: str,
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path / mutation, rule_count=2)
    before = _digests(tree)

    apply_governance_mutation(tree, mutation)

    after = _digests(tree)
    changed = {path for path in before if before[path] != after[path]}
    assert changed == _expected_changed_paths(tree, mutation)
    assert all(path.is_file() for path in _all_paths(tree))


def test_builder_is_byte_deterministic_across_roots(tmp_path: Path) -> None:
    first = build_valid_governance_tree(tmp_path / "first", rule_count=2)
    second = build_valid_governance_tree(tmp_path / "second", rule_count=2)

    assert _digests(first) == _digests(second)


def test_builder_rejects_invalid_rule_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rule_count must be positive"):
        build_valid_governance_tree(tmp_path, rule_count=0)
