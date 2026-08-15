from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from helpers.rule_governance import (
    apply_governance_mutation,
    build_valid_governance_tree,
)

from evidence_review.canonical_json import dump_bytes
from evidence_review.rule_engine.governance_contract import (
    ActiveRuleManifest,
    RuleSelectionContext,
    active_rule_manifest_bytes,
)
from evidence_review.rule_engine.manifest import (
    load_active_rules,
    load_governed_active_rules,
)
from evidence_review.rule_engine.selection import load_rule_selection_context_bytes

_CONTEXT = RuleSelectionContext(document_family="ANSIM")


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rebind_unsafe_path(tree) -> None:
    approval_hash = hashlib.sha256(tree.approval_paths[0].read_bytes()).hexdigest()
    manifest = _load_object(tree.manifest_path)
    rules = manifest["rules"]
    assert isinstance(rules, list)
    entry = rules[0]
    assert isinstance(entry, dict)
    entry["approval_sha256"] = approval_hash
    entry["candidate_path"] = "../outside.json"
    tree.manifest_path.write_bytes(dump_bytes(manifest))


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("active_manifest_bytes", "ACTIVE_MANIFEST_INVALID"),
        ("approval_bytes", "APPROVAL_HASH_MISMATCH"),
        ("golden_report_bytes", "GOLDEN_REPORT_HASH_MISMATCH"),
        ("candidate_bytes", "CANDIDATE_HASH_MISMATCH"),
        ("approved_rule_bytes", "ACTIVE_RULE_HASH_MISMATCH"),
        ("fixture_manifest_bytes", "GOLDEN_FIXTURE_MANIFEST_HASH_MISMATCH"),
        ("fixture_bytes", "GOLDEN_FIXTURE_HASH_MISMATCH"),
        ("expected_bytes", "GOLDEN_EXPECTED_HASH_MISMATCH"),
        ("path_traversal", "UNSAFE_ARTIFACT_PATH"),
        ("duplicate_rule_id", "DUPLICATE_ACTIVE_RULE_ID"),
    ],
)
def test_tamper_blocks_all_rules(
    mutation: str,
    expected_reason: str,
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    apply_governance_mutation(tree, mutation)
    if mutation == "path_traversal":
        _rebind_unsafe_path(tree)

    loaded = load_governed_active_rules(tmp_path, tree.manifest_path, _CONTEXT)

    assert loaded.rules == ()
    assert loaded.selection.status == "BLOCKED"
    assert expected_reason in loaded.selection.reasons


@pytest.mark.parametrize(
    "context",
    [
        RuleSelectionContext(),
        RuleSelectionContext(document_family="OTHER"),
        RuleSelectionContext(document_family="ansim"),
    ],
)
def test_normal_scope_nonmatch_abstains_without_blocking(
    context: RuleSelectionContext,
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path, rule_count=2)

    loaded = load_governed_active_rules(tmp_path, tree.manifest_path, context)

    assert loaded.rules == ()
    assert loaded.selection.status == "ABSTAIN"
    assert loaded.selection.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)
    assert [item.rule_id for item in loaded.selection.excluded_rules] == [
        "TEST-RULE-001",
        "TEST-RULE-002",
    ]


def test_empty_v2_manifest_abstains(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    manifest_path = tmp_path / "rules" / "manifests" / "active.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(active_rule_manifest_bytes(ActiveRuleManifest(rules=())))

    loaded = load_governed_active_rules(tmp_path, manifest_path, _CONTEXT)

    assert loaded.rules == ()
    assert loaded.selection.status == "ABSTAIN"
    assert loaded.selection.excluded_rules == ()
    assert loaded.selection.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)


def test_candidates_and_unmanifested_approved_files_are_never_scanned(
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    (tmp_path / "rules" / "candidates" / "UNMANIFESTED.json").write_text(
        "not json",
        encoding="utf-8",
    )
    (tmp_path / "rules" / "approved" / "UNMANIFESTED.json").write_text(
        "not json",
        encoding="utf-8",
    )

    loaded = load_governed_active_rules(tmp_path, tree.manifest_path, _CONTEXT)

    assert loaded.selection.status == "SELECTED"
    assert [item.rule_id for item in loaded.rules] == ["TEST-RULE-001"]


def test_legacy_no_context_loader_cannot_bypass_selection(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)

    with pytest.raises(ValueError, match="explicit RuleSelectionContext is required"):
        load_active_rules(tmp_path, tree.manifest_path)


def test_runtime_manifest_argument_cannot_escape_project_root(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)

    loaded = load_governed_active_rules(
        tmp_path,
        Path("../outside/active.json"),
        _CONTEXT,
    )

    assert loaded.rules == ()
    assert loaded.selection.status == "BLOCKED"
    assert loaded.selection.reasons == ("INVALID_ACTIVE_RULE_MANIFEST_PATH",)


def test_selection_context_rejects_duplicate_json_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key: document_family"):
        load_rule_selection_context_bytes(
            b'{"document_family":"ANSIM","document_family":"OTHER"}'
        )
