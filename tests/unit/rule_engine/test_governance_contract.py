from __future__ import annotations

import json

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.rule_engine.governance_contract import (
    ActiveRuleManifest,
    RuleActivationApproval,
    RuleGoldenReport,
    active_rule_manifest_bytes,
    load_active_rule_manifest_bytes,
    load_rule_activation_approval_bytes,
    load_rule_golden_report_bytes,
    rule_activation_approval_bytes,
    rule_golden_report_bytes,
)


def _case(case_id: str = "CASE-001") -> dict[str, object]:
    return {
        "case_id": case_id,
        "fixture_path": f"rules/golden/cases/{case_id}.json",
        "fixture_sha256": "1" * 64,
        "expected_path": f"rules/golden/expected/{case_id}.json",
        "expected_sha256": "2" * 64,
        "actual_path": f"build/rules/golden/actual/{case_id}.json",
        "actual_sha256": "2" * 64,
        "status": "PASS",
    }


def _golden_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/rule-golden-report",
        "version": 1,
        "rule_id": "TEST-RULE",
        "rule_version": "1.0.0",
        "candidate_path": "rules/candidates/TEST-RULE@1.0.0.json",
        "candidate_sha256": "a" * 64,
        "approved_rule_path": "rules/approved/TEST-RULE@1.0.0.json",
        "approved_rule_sha256": "b" * 64,
        "runner_version": "1",
        "source_commit": "c" * 40,
        "command": "python -m evidence_review rules run-golden",
        "fixture_manifest_path": "rules/golden/fixtures/TEST-RULE@1.0.0.json",
        "fixture_manifest_sha256": "d" * 64,
        "case_count": 1,
        "passed_count": 1,
        "failed_count": 0,
        "status": "PASS",
        "cases": [_case()],
    }


def _scope() -> dict[str, str]:
    return {
        "document_family": "ANSIM",
        "document_kind": "OPERATING_STANDARD",
        "jurisdiction": "Seoul",
        "program": "Public Housing",
    }


def _approval_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/rule-activation-approval",
        "version": 1,
        "rule_id": "TEST-RULE",
        "rule_version": "1.0.0",
        "candidate_path": "rules/candidates/TEST-RULE@1.0.0.json",
        "candidate_sha256": "a" * 64,
        "approved_rule_path": "rules/approved/TEST-RULE@1.0.0.json",
        "approved_rule_sha256": "b" * 64,
        "golden_report_path": "rules/golden/reports/TEST-RULE@1.0.0.json",
        "golden_report_sha256": "e" * 64,
        "scope": _scope(),
        "reviewer_id": "reviewer-1",
        "reviewed_at": "2026-08-02T21:52:00+09:00",
        "decision": "APPROVED",
        "reason": "Golden evidence and explicit scope reviewed.",
    }


def _entry(rule_id: str = "TEST-RULE") -> dict[str, object]:
    payload = _approval_payload()
    return {
        "rule_id": rule_id,
        "rule_version": payload["rule_version"],
        "candidate_path": payload["candidate_path"],
        "candidate_sha256": payload["candidate_sha256"],
        "approved_rule_path": payload["approved_rule_path"],
        "approved_rule_sha256": payload["approved_rule_sha256"],
        "golden_report_path": payload["golden_report_path"],
        "golden_report_sha256": payload["golden_report_sha256"],
        "approval_path": f"rules/activation/approvals/{rule_id}@1.0.0.json",
        "approval_sha256": "f" * 64,
        "scope": payload["scope"],
        "reviewer_id": payload["reviewer_id"],
        "reviewed_at": payload["reviewed_at"],
        "reason": payload["reason"],
    }


def _manifest_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/active-rule-manifest",
        "version": 2,
        "rules": [_entry()],
    }


def test_active_manifest_rejects_legacy_shape() -> None:
    with pytest.raises(ValueError, match="legacy active rule manifest"):
        load_active_rule_manifest_bytes(b'{"rules":[]}')


def test_duplicate_json_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key: format"):
        load_active_rule_manifest_bytes(
            b'{"format":"evidence-review/active-rule-manifest",'
            b'"format":"evidence-review/active-rule-manifest",'
            b'"version":2,"rules":[]}'
        )


def test_scope_requires_document_family() -> None:
    payload = _approval_payload()
    payload["scope"] = {"jurisdiction": "Seoul"}
    with pytest.raises(ValueError, match="scope.document_family"):
        load_rule_activation_approval_bytes(dump_bytes(payload))


def test_scope_rejects_unknown_dimensions() -> None:
    payload = _approval_payload()
    payload["scope"] = {"document_family": "ANSIM", "filename": "law.pdf"}
    with pytest.raises(ValueError, match="scope has unknown fields"):
        load_rule_activation_approval_bytes(dump_bytes(payload))


def test_hashes_must_be_lowercase_sha256() -> None:
    payload = _approval_payload()
    payload["candidate_sha256"] = "A" * 64
    with pytest.raises(ValueError, match="candidate_sha256"):
        load_rule_activation_approval_bytes(dump_bytes(payload))


def test_reviewed_at_requires_timezone() -> None:
    payload = _approval_payload()
    payload["reviewed_at"] = "2026-08-02T21:52:00"
    with pytest.raises(ValueError, match="reviewed_at"):
        load_rule_activation_approval_bytes(dump_bytes(payload))


def test_paths_must_be_repository_relative_posix_paths() -> None:
    payload = _approval_payload()
    payload["candidate_path"] = "../outside.json"
    with pytest.raises(ValueError, match="candidate_path"):
        load_rule_activation_approval_bytes(dump_bytes(payload))


@pytest.mark.parametrize("field", ["reviewer_id", "reason"])
def test_human_fields_must_be_trimmed_and_nonempty(field: str) -> None:
    payload = _approval_payload()
    payload[field] = "  "
    with pytest.raises(ValueError, match=field):
        load_rule_activation_approval_bytes(dump_bytes(payload))


def test_unknown_top_level_fields_are_rejected() -> None:
    payload = _golden_payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="golden report has unknown fields"):
        load_rule_golden_report_bytes(dump_bytes(payload))


def test_golden_counts_must_match_cases() -> None:
    payload = _golden_payload()
    payload["passed_count"] = 0
    with pytest.raises(ValueError, match="golden report counts"):
        load_rule_golden_report_bytes(dump_bytes(payload))


def test_golden_case_ids_are_unique() -> None:
    payload = _golden_payload()
    payload["cases"] = [_case(), _case()]
    payload["case_count"] = 2
    payload["passed_count"] = 2
    with pytest.raises(ValueError, match="duplicate golden case_id"):
        load_rule_golden_report_bytes(dump_bytes(payload))


def test_passing_case_hashes_must_match() -> None:
    payload = _golden_payload()
    case = _case()
    case["actual_sha256"] = "3" * 64
    payload["cases"] = [case]
    with pytest.raises(ValueError, match="PASS golden case hashes"):
        load_rule_golden_report_bytes(dump_bytes(payload))


def test_active_manifest_rejects_duplicate_rule_ids() -> None:
    payload = _manifest_payload()
    payload["rules"] = [_entry(), _entry()]
    with pytest.raises(ValueError, match="duplicate active rule_id"):
        load_active_rule_manifest_bytes(dump_bytes(payload))


def test_active_manifest_requires_deterministic_sort_order() -> None:
    payload = _manifest_payload()
    payload["rules"] = [_entry("RULE-B"), _entry("RULE-A")]
    with pytest.raises(ValueError, match="rules must be sorted"):
        load_active_rule_manifest_bytes(dump_bytes(payload))


def test_contracts_round_trip_to_canonical_bytes() -> None:
    golden = load_rule_golden_report_bytes(dump_bytes(_golden_payload()))
    approval = load_rule_activation_approval_bytes(dump_bytes(_approval_payload()))
    manifest = load_active_rule_manifest_bytes(dump_bytes(_manifest_payload()))

    assert isinstance(golden, RuleGoldenReport)
    assert isinstance(approval, RuleActivationApproval)
    assert isinstance(manifest, ActiveRuleManifest)
    assert rule_golden_report_bytes(golden) == dump_bytes(_golden_payload())
    assert rule_activation_approval_bytes(approval) == dump_bytes(_approval_payload())
    assert active_rule_manifest_bytes(manifest) == dump_bytes(_manifest_payload())


def test_serialized_contracts_are_valid_json() -> None:
    manifest = load_active_rule_manifest_bytes(dump_bytes(_manifest_payload()))
    assert json.loads(active_rule_manifest_bytes(manifest)) == _manifest_payload()
