from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from helpers.rule_governance import build_valid_governance_tree

from evidence_review.rule_engine.governance_contract import (
    RuleScope,
    RuleSelectionContext,
    load_active_rule_manifest_bytes,
)
from evidence_review.rule_engine.selection import (
    load_rule_selection_context,
    select_active_rules,
)

MANIFEST_HASH = "a" * 64


def _entries(tmp_path: Path):
    tree = build_valid_governance_tree(tmp_path, rule_count=2)
    return load_active_rule_manifest_bytes(tree.manifest_path.read_bytes()).rules


def test_exact_case_sensitive_scope_selects_multiple_rules(tmp_path: Path) -> None:
    entries = _entries(tmp_path)

    selected = select_active_rules(
        entries,
        RuleSelectionContext(document_family="ANSIM"),
        MANIFEST_HASH,
    )
    mismatch = select_active_rules(
        entries,
        RuleSelectionContext(document_family="ansim"),
        MANIFEST_HASH,
    )

    assert selected.status == "SELECTED"
    assert [item.rule_id for item in selected.selected_rules] == [
        "TEST-RULE-001",
        "TEST-RULE-002",
    ]
    assert mismatch.status == "ABSTAIN"
    assert mismatch.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)
    assert {item.code for item in mismatch.excluded_rules} == {"SCOPE_MISMATCH"}


def test_missing_required_scope_value_abstains_deterministically(tmp_path: Path) -> None:
    entries = _entries(tmp_path)

    result = select_active_rules(entries, RuleSelectionContext(), MANIFEST_HASH)

    assert result.status == "ABSTAIN"
    assert result.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)
    assert [item.code for item in result.excluded_rules] == [
        "MISSING_SCOPE_VALUE",
        "MISSING_SCOPE_VALUE",
    ]


def test_optional_scope_dimension_mismatch_is_excluded(tmp_path: Path) -> None:
    entries = _entries(tmp_path)
    scoped = (
        replace(
            entries[0],
            scope=RuleScope(document_family="ANSIM", jurisdiction="Seoul"),
        ),
    )

    missing = select_active_rules(
        scoped,
        RuleSelectionContext(document_family="ANSIM"),
        MANIFEST_HASH,
    )
    mismatch = select_active_rules(
        scoped,
        RuleSelectionContext(document_family="ANSIM", jurisdiction="Busan"),
        MANIFEST_HASH,
    )

    assert missing.excluded_rules[0].code == "MISSING_SCOPE_VALUE"
    assert mismatch.excluded_rules[0].code == "SCOPE_MISMATCH"


def test_empty_manifest_abstains_without_inventing_exclusions() -> None:
    result = select_active_rules(
        (),
        RuleSelectionContext(document_family="ANSIM"),
        MANIFEST_HASH,
    )

    assert result.status == "ABSTAIN"
    assert result.selected_rules == ()
    assert result.excluded_rules == ()
    assert result.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)


def test_exclusions_are_sorted_by_rule_identity(tmp_path: Path) -> None:
    entries = tuple(reversed(_entries(tmp_path)))

    result = select_active_rules(
        entries,
        RuleSelectionContext(document_family="OTHER"),
        MANIFEST_HASH,
    )

    assert [item.rule_id for item in result.excluded_rules] == [
        "TEST-RULE-001",
        "TEST-RULE-002",
    ]


def test_context_loader_rejects_unsupported_keys() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        load_rule_selection_context(
            {"document_family": "ANSIM", "unsupported": "value"}
        )


def test_context_loader_preserves_explicit_case_sensitive_values() -> None:
    context = load_rule_selection_context(
        {
            "document_family": "ANSIM",
            "document_kind": None,
            "jurisdiction": "Seoul",
            "program": None,
        }
    )

    assert context == RuleSelectionContext(
        document_family="ANSIM",
        jurisdiction="Seoul",
    )
