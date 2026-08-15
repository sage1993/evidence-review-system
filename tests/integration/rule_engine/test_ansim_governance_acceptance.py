from __future__ import annotations

import hashlib
from pathlib import Path

from evidence_review.rule_engine.governance_contract import (
    RuleSelectionContext,
    load_active_rule_manifest_bytes,
    load_rule_activation_approval_bytes,
    load_rule_golden_report_bytes,
)
from evidence_review.rule_engine.governance_verify import verify_manifest_entry
from evidence_review.rule_engine.manifest import load_governed_active_rules

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "ansim"
MANIFEST = FIXTURE_ROOT / "rules" / "manifests" / "active.json"
EXPECTED_RULE_IDS = (
    "ANSIM-ARTERIAL-FRONTAGE-ONE-EIGHTH",
    "ANSIM-MINIMUM-SITE-AREA-1500",
    "ANSIM-TWO-ROAD-SIDES-6M",
    "ANSIM-ZONING-CHANGE-FAR-MAX-400",
    "ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15",
    "ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ansim_rules_have_complete_passing_governance_authority() -> None:
    manifest = load_active_rule_manifest_bytes(MANIFEST.read_bytes())

    assert tuple(item.rule_id for item in manifest.rules) == EXPECTED_RULE_IDS
    assert len(manifest.rules) == 6
    for entry in manifest.rules:
        assert entry.scope.document_family == "ANSIM"
        assert entry.scope.document_kind is None
        assert entry.scope.jurisdiction is None
        assert entry.scope.program is None

        approval_path = FIXTURE_ROOT / entry.approval_path
        report_path = FIXTURE_ROOT / entry.golden_report_path
        assert _sha256(approval_path) == entry.approval_sha256
        assert _sha256(report_path) == entry.golden_report_sha256

        approval = load_rule_activation_approval_bytes(approval_path.read_bytes())
        report = load_rule_golden_report_bytes(report_path.read_bytes())
        assert approval.scope.document_family == "ANSIM"
        assert report.status == "PASS"
        assert report.case_count >= 2
        assert report.passed_count == report.case_count
        assert report.failed_count == 0
        verify_manifest_entry(FIXTURE_ROOT, entry, mode="RUNTIME")


def test_ansim_scope_selects_six_and_other_scope_abstains() -> None:
    selected = load_governed_active_rules(
        FIXTURE_ROOT,
        MANIFEST,
        RuleSelectionContext(document_family="ANSIM"),
    )
    abstained = load_governed_active_rules(
        FIXTURE_ROOT,
        MANIFEST,
        RuleSelectionContext(document_family="OTHER"),
    )

    assert selected.selection.status == "SELECTED"
    assert tuple(rule.rule_id for rule in selected.rules) == EXPECTED_RULE_IDS
    assert abstained.selection.status == "ABSTAIN"
    assert abstained.selection.reasons == ("NO_APPLICABLE_ACTIVE_RULE",)
    assert abstained.rules == ()
