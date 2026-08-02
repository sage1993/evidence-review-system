from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from helpers.rule_governance import (
    apply_governance_mutation,
    build_valid_governance_tree,
)

from ansim_review.canonical_json import dump_bytes
from ansim_review.rule_engine.governance_contract import (
    load_active_rule_manifest_bytes,
)
from ansim_review.rule_engine.governance_verify import (
    GovernanceVerificationError,
    resolve_governance_path,
    verify_approval,
    verify_manifest_entry,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(dump_bytes(payload))


def _assert_code(error: pytest.ExceptionInfo[GovernanceVerificationError], code: str) -> None:
    assert error.value.code == code
    assert code in str(error.value)


def test_valid_approval_verifies_in_activation_and_runtime_modes(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)

    activation = verify_approval(tmp_path, tree.approval_paths[0], mode="ACTIVATION")
    runtime = verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")

    assert activation.rule.rule_id == "TEST-RULE-001"
    assert activation.approval == runtime.approval
    assert activation.golden_report.status == "PASS"
    assert activation.approval_path == "rules/activation/approvals/TEST-RULE-001@1.0.0.json"


def test_runtime_does_not_require_generated_actual_output(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.actual_paths[0].unlink()

    verified = verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")
    assert verified.rule.rule_id == "TEST-RULE-001"

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tmp_path, tree.approval_paths[0], mode="ACTIVATION")
    _assert_code(error, "GOLDEN_ACTUAL_MISSING")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("candidate_bytes", "CANDIDATE_HASH_MISMATCH"),
        ("approved_rule_bytes", "ACTIVE_RULE_HASH_MISMATCH"),
        ("golden_report_bytes", "GOLDEN_REPORT_HASH_MISMATCH"),
        ("fixture_manifest_bytes", "GOLDEN_FIXTURE_MANIFEST_HASH_MISMATCH"),
        ("fixture_bytes", "GOLDEN_FIXTURE_HASH_MISMATCH"),
        ("expected_bytes", "GOLDEN_EXPECTED_HASH_MISMATCH"),
    ],
)
def test_linked_artifact_tampering_is_rejected(
    mutation: str,
    expected_code: str,
    tmp_path: Path,
) -> None:
    tree = build_valid_governance_tree(tmp_path)
    apply_governance_mutation(tree, mutation)

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")
    _assert_code(error, expected_code)


def test_path_traversal_and_absolute_paths_are_rejected_before_file_access(
    tmp_path: Path,
) -> None:
    traversal = build_valid_governance_tree(tmp_path / "traversal")
    apply_governance_mutation(traversal, "path_traversal")
    with pytest.raises(GovernanceVerificationError) as traversal_error:
        verify_approval(
            traversal.root,
            traversal.approval_paths[0],
            mode="RUNTIME",
        )
    _assert_code(traversal_error, "UNSAFE_ARTIFACT_PATH")

    absolute = build_valid_governance_tree(tmp_path / "absolute")
    approval = _load(absolute.approval_paths[0])
    approval["candidate_path"] = "/tmp/outside.json"
    _write(absolute.approval_paths[0], approval)
    with pytest.raises(GovernanceVerificationError) as absolute_error:
        verify_approval(absolute.root, absolute.approval_paths[0], mode="RUNTIME")
    _assert_code(absolute_error, "UNSAFE_ARTIFACT_PATH")


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path / "tree")
    outside = tmp_path / "outside.json"
    outside.write_bytes(tree.candidate_paths[0].read_bytes())
    tree.candidate_paths[0].unlink()
    try:
        tree.candidate_paths[0].symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not available")

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tree.root, tree.approval_paths[0], mode="RUNTIME")
    _assert_code(error, "UNSAFE_ARTIFACT_PATH")


def test_casefold_colliding_declared_paths_are_rejected(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    fixture_manifest = _load(tree.fixture_manifest_paths[0])
    cases = fixture_manifest["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    colliding_path = str(case["expected_path"]).upper()
    case["actual_path"] = colliding_path
    _write(tree.fixture_manifest_paths[0], fixture_manifest)

    report = _load(tree.golden_report_paths[0])
    report["fixture_manifest_sha256"] = _sha256(tree.fixture_manifest_paths[0])
    report_cases = report["cases"]
    assert isinstance(report_cases, list)
    report_case = report_cases[0]
    assert isinstance(report_case, dict)
    report_case["actual_path"] = colliding_path
    _write(tree.golden_report_paths[0], report)

    approval = _load(tree.approval_paths[0])
    approval["golden_report_sha256"] = _sha256(tree.golden_report_paths[0])
    _write(tree.approval_paths[0], approval)

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tmp_path, tree.approval_paths[0], mode="ACTIVATION")
    _assert_code(error, "CASEFOLD_PATH_COLLISION")


def test_rule_identity_mismatch_is_rejected_after_hash_rebinding(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    candidate = _load(tree.candidate_paths[0])
    candidate["rule_id"] = "OTHER-RULE"
    _write(tree.candidate_paths[0], candidate)

    report = _load(tree.golden_report_paths[0])
    report["candidate_sha256"] = _sha256(tree.candidate_paths[0])
    _write(tree.golden_report_paths[0], report)

    approval = _load(tree.approval_paths[0])
    approval["candidate_sha256"] = _sha256(tree.candidate_paths[0])
    approval["golden_report_sha256"] = _sha256(tree.golden_report_paths[0])
    _write(tree.approval_paths[0], approval)

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")
    _assert_code(error, "RULE_IDENTITY_MISMATCH")


def test_non_passing_golden_report_is_not_activation_authority(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    report = _load(tree.golden_report_paths[0])
    report["passed_count"] = 0
    report["failed_count"] = 1
    report["status"] = "FAIL"
    cases = report["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    case["status"] = "FAIL"
    case["actual_sha256"] = "9" * 64
    _write(tree.golden_report_paths[0], report)

    approval = _load(tree.approval_paths[0])
    approval["golden_report_sha256"] = _sha256(tree.golden_report_paths[0])
    _write(tree.approval_paths[0], approval)

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")
    _assert_code(error, "GOLDEN_REPORT_NOT_PASSING")


def test_manifest_entry_binds_exact_approval_bytes_and_fields(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    entry = load_active_rule_manifest_bytes(tree.manifest_path.read_bytes()).rules[0]

    verified = verify_manifest_entry(tmp_path, entry, mode="RUNTIME")
    assert verified.rule.rule_id == entry.rule_id

    apply_governance_mutation(tree, "approval_bytes")
    with pytest.raises(GovernanceVerificationError) as hash_error:
        verify_manifest_entry(tmp_path, entry, mode="RUNTIME")
    _assert_code(hash_error, "APPROVAL_HASH_MISMATCH")

    rebuilt = build_valid_governance_tree(tmp_path / "field")
    field_entry = load_active_rule_manifest_bytes(
        rebuilt.manifest_path.read_bytes()
    ).rules[0]
    mismatched = replace(field_entry, candidate_sha256="f" * 64)
    with pytest.raises(GovernanceVerificationError) as field_error:
        verify_manifest_entry(rebuilt.root, mismatched, mode="RUNTIME")
    _assert_code(field_error, "ACTIVE_ENTRY_MISMATCH")


def test_missing_committed_artifact_is_rejected(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    tree.candidate_paths[0].unlink()

    with pytest.raises(GovernanceVerificationError) as error:
        verify_approval(tmp_path, tree.approval_paths[0], mode="RUNTIME")
    _assert_code(error, "ARTIFACT_MISSING")


def test_resolve_governance_path_returns_exact_repository_member(tmp_path: Path) -> None:
    tree = build_valid_governance_tree(tmp_path)
    resolved = resolve_governance_path(
        tmp_path,
        "rules/candidates/TEST-RULE-001@1.0.0.json",
    )
    assert resolved == tree.candidate_paths[0].resolve()
