import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.repository_gate import (
    REQUIRED_GATE_NAMES,
    GateStatus,
    GateVerdict,
    evaluate_verdict,
    format_summary,
    run_command,
)

SHA = "a" * 40
OTHER_SHA = "b" * 40


def complete_verdict() -> GateVerdict:
    return GateVerdict(
        branch="chore/issue-227-public-repository-governance",
        base_sha=SHA,
        base_ancestry="PASS",
        candidate_sha=SHA,
        committed_sha=SHA,
        tested_sha=SHA,
        remote_sha=SHA,
        pr_head_sha=SHA,
        worktree="CLEAN",
        diff_check="PASS",
        candidate_stable_after_testing="PASS",
        unexpected_files=(),
        acceptance_artifacts=(),
        gate_statuses=tuple(GateStatus(name, "PASS") for name in REQUIRED_GATE_NAMES),
        package_acceptance="NOT_REQUIRED",
        wheel_sha256="NOT_APPLICABLE",
        github_actions="NOT_USED_BY_POLICY",
        remote_base_sha=SHA,
        local_remote_base_sha=SHA,
        issue_binding="PASS",
    )


def test_clean_all_pass_and_equal_shas_is_ready():
    result = evaluate_verdict(complete_verdict())

    assert result.merge_readiness == "READY_FOR_REVIEW"
    assert result.sha_parity == "PASS"


def test_dirty_worktree_holds():
    result = evaluate_verdict(replace(complete_verdict(), worktree="DIRTY"))

    assert result.merge_readiness == "HOLD"


def test_current_head_different_from_tested_sha_holds():
    result = evaluate_verdict(replace(complete_verdict(), tested_sha=OTHER_SHA))

    assert result.sha_parity == "FAIL"
    assert result.merge_readiness == "HOLD"


def test_remote_sha_mismatch_holds():
    result = evaluate_verdict(replace(complete_verdict(), remote_sha=OTHER_SHA))

    assert result.sha_parity == "FAIL"
    assert result.merge_readiness == "HOLD"


def test_pr_head_mismatch_holds():
    result = evaluate_verdict(replace(complete_verdict(), pr_head_sha=OTHER_SHA))

    assert result.sha_parity == "FAIL"
    assert result.merge_readiness == "HOLD"


def test_required_gate_failure_holds():
    statuses = tuple(
        GateStatus(name, "FAIL" if name == "PYTEST" else "PASS")
        for name in REQUIRED_GATE_NAMES
    )
    result = evaluate_verdict(replace(complete_verdict(), gate_statuses=statuses))

    assert result.merge_readiness == "HOLD"


def test_post_acceptance_edit_holds():
    result = evaluate_verdict(
        replace(complete_verdict(), candidate_stable_after_testing="FAIL")
    )

    assert result.merge_readiness == "HOLD"


def test_unknown_ancestry_holds():
    result = evaluate_verdict(replace(complete_verdict(), base_ancestry="NOT_VERIFIED"))

    assert result.merge_readiness == "HOLD"


def test_untracked_acceptance_artifact_holds():
    result = evaluate_verdict(
        replace(complete_verdict(), acceptance_artifacts=(".verification/report.json",))
    )

    assert result.merge_readiness == "HOLD"


def test_external_identity_unverified_holds_without_actions_dependency():
    result = evaluate_verdict(
        replace(complete_verdict(), remote_sha="NOT_VERIFIED", pr_head_sha="NOT_VERIFIED")
    )

    assert result.sha_parity == "HOLD"
    assert result.github_actions == "NOT_USED_BY_POLICY"
    assert result.merge_readiness == "HOLD"


def test_summary_contains_required_identity_and_policy_fields():
    summary = format_summary(evaluate_verdict(complete_verdict()))

    assert "TESTED_SHA = " + SHA in summary
    assert "COMMITTED_SHA = " + SHA in summary
    assert "PUSHED_SHA = " + SHA in summary
    assert "PR_HEAD_SHA = " + SHA in summary
    assert "GITHUB_ACTIONS = NOT_USED_BY_POLICY" in summary
    assert "MERGE_READINESS = READY_FOR_REVIEW" in summary


def test_summary_names_candidate_stability_after_testing():
    summary = format_summary(evaluate_verdict(complete_verdict()))

    assert "CANDIDATE_STABLE_AFTER_TESTING = PASS" in summary
    assert "CANDIDATE_CHANGED_AFTER_TESTING" not in summary


def test_workflow_presence_is_observed_as_policy_mismatch(tmp_path: Path):
    workflow = tmp_path / ".github" / "workflows" / "build.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: build\n", encoding="utf-8")

    from scripts.repository_gate import observe_github_actions

    assert observe_github_actions(tmp_path) == "POLICY_MISMATCH"


def test_issue_binding_requires_issue_scoped_branch_commit_and_closing_reference():
    from scripts.repository_gate import _validate_issue_binding

    pull_request = {
        "number": 228,
        "headRefName": "chore/issue-227-public-repository-governance",
        "headRefOid": "a" * 40,
        "baseRefName": "main",
        "body": "Hardens the local gate.\n\nCloses #227",
    }

    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            ("chore(issue-227): harden repository governance",),
            pull_request,
        )
        == "PASS"
    )
    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            ("fix: unrelated issue-227",),
            pull_request,
        )
        == "FAIL"
    )


def test_issue_binding_rejects_missing_pr_base_metadata():
    from scripts.repository_gate import _validate_issue_binding

    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            ("chore(issue-227): harden repository governance",),
            {
                "headRefName": "chore/issue-227-public-repository-governance",
                "baseRefName": None,
                "body": "Closes #227",
            },
        )
        == "NOT_VERIFIED"
    )


def test_issue_binding_checks_every_contributor_commit_subject():
    from scripts.repository_gate import _validate_issue_binding

    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            (
                "chore(issue-227): harden repository governance",
                "docs: unrelated contributor commit",
            ),
            {
                "number": 228,
                "headRefName": "chore/issue-227-public-repository-governance",
                "headRefOid": "a" * 40,
                "baseRefName": "main",
                "body": "Closes #227",
            },
        )
        == "FAIL"
    )


def test_issue_binding_rejects_merge_subject_without_exact_issue_scope():
    from scripts.repository_gate import _validate_issue_binding

    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            ("Merge pull request #228 from contributor/other",),
            {
                "number": 228,
                "headRefName": "chore/issue-227-public-repository-governance",
                "headRefOid": "a" * 40,
                "baseRefName": "main",
                "body": "Closes #227",
            },
        )
        == "FAIL"
    )


def test_issue_binding_rejects_negated_closing_reference():
    from scripts.repository_gate import _validate_issue_binding

    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            ("chore(issue-227): harden repository governance",),
            {
                "number": 228,
                "headRefName": "chore/issue-227-public-repository-governance",
                "headRefOid": "a" * 40,
                "baseRefName": "main",
                "body": "Do not close #227",
            },
        )
        == "FAIL"
    )


def test_issue_binding_rejects_fenced_closing_reference():
    from scripts.repository_gate import _validate_issue_binding

    assert (
        _validate_issue_binding(
            227,
            "chore/issue-227-public-repository-governance",
            ("chore(issue-227): harden repository governance",),
            {
                "number": 228,
                "headRefName": "chore/issue-227-public-repository-governance",
                "headRefOid": "a" * 40,
                "baseRefName": "main",
                "body": "```text\nCloses #227\n```",
            },
        )
        == "FAIL"
    )


def test_package_change_includes_runtime_modules_and_web_assets():
    from scripts.repository_gate import _package_change

    assert _package_change(("src/evidence_review/cli.py",))
    assert _package_change(("src/other_runtime/cli.py",))
    assert _package_change(("web_runtime/workbench/index.html",))


def test_remote_ref_must_be_the_current_branch():
    from scripts.repository_gate import _remote_ref

    with pytest.raises(ValueError, match="current branch"):
        _remote_ref("chore/issue-227-public-repository-governance", "refs/tags/v0.2.0")


def test_remote_tracking_ref_mismatch_holds_even_when_other_fields_pass():
    result = evaluate_verdict(
        replace(complete_verdict(), local_remote_base_sha=OTHER_SHA)
    )

    assert result.merge_readiness == "HOLD"


def test_package_evidence_requires_exact_candidate_and_all_package_checks(tmp_path: Path):
    from scripts.repository_gate import load_package_evidence

    evidence_path = tmp_path / "package-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "format": "evidence-review/package-acceptance",
                "version": 1,
                "candidate_sha": SHA,
                "wheel_sha256": "c" * 64,
                "checks": {
                    "WHEEL_BUILD": "PASS",
                    "ISOLATED_INSTALL": "PASS",
                    "PIP_CHECK": "PASS",
                    "RUNTIME_SMOKE": "PASS",
                },
            }
        ),
        encoding="utf-8",
    )

    status, wheel_sha, detail = load_package_evidence(
        evidence_path,
        repository_root=tmp_path / "checkout",
        candidate_sha=SHA,
    )

    assert status == "PASS"
    assert wheel_sha == "c" * 64
    assert detail == ""


def test_package_evidence_rejects_stale_candidate(tmp_path: Path):
    from scripts.repository_gate import load_package_evidence

    evidence_path = tmp_path / "package-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "format": "evidence-review/package-acceptance",
                "version": 1,
                "candidate_sha": OTHER_SHA,
                "wheel_sha256": "c" * 64,
                "checks": {
                    "WHEEL_BUILD": "PASS",
                    "ISOLATED_INSTALL": "PASS",
                    "PIP_CHECK": "PASS",
                    "RUNTIME_SMOKE": "PASS",
                },
            }
        ),
        encoding="utf-8",
    )

    status, wheel_sha, detail = load_package_evidence(
        evidence_path,
        repository_root=tmp_path / "checkout",
        candidate_sha=SHA,
    )

    assert status == "NOT_VERIFIED"
    assert wheel_sha == "NOT_VERIFIED"
    assert "candidate SHA" in detail


def test_run_command_prefers_checkout_source_and_external_tool_caches(monkeypatch):
    repository_root = Path.cwd()
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_command(["py", "-3.13", "-m", "evidence_review"], repository_root)

    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["PYTHONPATH"].split(";")[0] == str(repository_root / "src")
    assert environment["RUFF_CACHE_DIR"] != str(repository_root / ".ruff_cache")
    assert environment["MYPY_CACHE_DIR"] != str(repository_root / ".mypy_cache")
    assert environment["PYTHONPYCACHEPREFIX"] != str(repository_root / "__pycache__")
