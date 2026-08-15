from __future__ import annotations

from pathlib import Path

from helpers.rule_governance import (
    apply_governance_mutation,
    build_valid_governance_tree,
)

from evidence_review.rule_engine.governance_contract import RuleSelectionContext
from evidence_review.rule_engine.manifest import load_governed_active_rules


def test_runtime_verifies_all_authority_then_loads_selected_rules(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    for path in tree.actual_paths:
        path.unlink()

    loaded = load_governed_active_rules(
        tmp_path,
        tree.manifest_path,
        RuleSelectionContext(document_family="ANSIM"),
    )

    assert loaded.selection.status == "SELECTED"
    assert [rule.rule_id for rule in loaded.rules] == [
        "TEST-RULE-001",
        "TEST-RULE-002",
    ]


def test_scope_mismatch_abstains_without_loading_rules(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)

    loaded = load_governed_active_rules(
        tmp_path,
        tree.manifest_path,
        RuleSelectionContext(document_family="OTHER"),
    )

    assert loaded.selection.status == "ABSTAIN"
    assert loaded.selection.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)
    assert loaded.rules == ()


def test_legacy_manifest_is_blocked_without_fallback(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.manifest_path.write_bytes(b'{"rules":[]}')

    loaded = load_governed_active_rules(
        tmp_path,
        tree.manifest_path,
        RuleSelectionContext(document_family="ANSIM"),
    )

    assert loaded.selection.status == "BLOCKED"
    assert loaded.selection.reasons == ("RULE_GOVERNANCE_LEGACY_MANIFEST",)
    assert loaded.rules == ()


def test_one_tampered_entry_blocks_every_rule(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    apply_governance_mutation(tree, "candidate_bytes")

    loaded = load_governed_active_rules(
        tmp_path,
        tree.manifest_path,
        RuleSelectionContext(document_family="ANSIM"),
    )

    assert loaded.selection.status == "BLOCKED"
    assert "CANDIDATE_HASH_MISMATCH" in loaded.selection.reasons
    assert loaded.rules == ()


def test_missing_manifest_is_blocked_not_treated_as_empty(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)

    loaded = load_governed_active_rules(
        tmp_path,
        tmp_path / "rules" / "manifests" / "active.json",
        RuleSelectionContext(document_family="ANSIM"),
    )

    assert loaded.selection.status == "BLOCKED"
    assert loaded.selection.reasons == ("ACTIVE_RULE_MANIFEST_MISSING",)
    assert loaded.rules == ()
