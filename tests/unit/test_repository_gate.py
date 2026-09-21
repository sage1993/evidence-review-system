import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.repository_gate import (
    REQUIRED_GATE_NAMES,
    CommandResult,
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


def integration_manifest(*, candidate_sha: str = SHA) -> dict[str, object]:
    return {
        "format": "evidence-review/integration-gate",
        "version": 1,
        "origin_url": "https://github.com/sage1993/evidence-review-system.git",
        "base_sha": SHA,
        "candidate_sha": candidate_sha,
        "branch": "integration/review-matter-and-policy",
        "issues": [227, 228],
        "commits": [
            {
                "sha": "c" * 40,
                "issues": [227],
                "description": "Preserve the issue-specific verifier behavior.",
            },
            {
                "sha": "d" * 40,
                "issues": [228],
                "description": "Add strict integration manifest verification.",
            },
        ],
    }


def integration_pr(*, body: str) -> dict[str, object]:
    return {
        "number": 229,
        "headRefName": "integration/review-matter-and-policy",
        "headRefOid": SHA,
        "baseRefName": "main",
        "body": body,
    }


def test_integration_binding_requires_exact_inventory_and_visible_closing_references():
    from scripts.repository_gate import _validate_integration_binding

    manifest = integration_manifest()
    manifest_sha = "e" * 64
    result = _validate_integration_binding(
        manifest,
        manifest_sha=manifest_sha,
        origin_url="https://github.com/sage1993/evidence-review-system.git",
        base_sha=SHA,
        candidate_sha=SHA,
        branch="integration/review-matter-and-policy",
        commits=(("c" * 40, "first"), ("d" * 40, "second")),
        pr_payload=integration_pr(
            body=(
                "Closes #227\nFixes #228\n\n"
                f"Integration-Manifest-SHA256: {manifest_sha}"
            )
        ),
    )

    assert result == "PASS"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda value: value["commits"].pop(), "FAIL"),
        (lambda value: value.update(candidate_sha=OTHER_SHA), "FAIL"),
        (lambda value: value.update(base_sha=OTHER_SHA), "FAIL"),
        (lambda value: value.update(branch="integration/other"), "FAIL"),
        (lambda value: value.update(origin_url="https://github.com/other/repo.git"), "FAIL"),
        (lambda value: value.update(issues=[227, 227]), "FAIL"),
        (lambda value: value["commits"][0].update(issues=[999]), "FAIL"),
    ],
)
def test_integration_binding_rejects_manifest_identity_and_inventory_mismatches(
    mutation, expected
):
    from scripts.repository_gate import _validate_integration_binding

    manifest = integration_manifest()
    mutation(manifest)

    assert (
        _validate_integration_binding(
            manifest,
            manifest_sha="e" * 64,
            origin_url="https://github.com/sage1993/evidence-review-system.git",
            base_sha=SHA,
            candidate_sha=SHA,
            branch="integration/review-matter-and-policy",
            commits=(("c" * 40, "first"), ("d" * 40, "second")),
            pr_payload=integration_pr(
                body="Closes #227\nFixes #228\n\nIntegration-Manifest-SHA256: " + "e" * 64
            ),
        )
        == expected
    )


@pytest.mark.parametrize(
    "body",
    [
        "Closes #227\n\nIntegration-Manifest-SHA256: " + "e" * 64,
        "```text\nCloses #227\nFixes #228\nIntegration-Manifest-SHA256: " + "e" * 64 + "\n```",
        "Do not close #227\nFixes #228\n\nIntegration-Manifest-SHA256: " + "e" * 64,
    ],
)
def test_integration_binding_rejects_missing_fenced_or_negated_closing_references(body):
    from scripts.repository_gate import _validate_integration_binding

    assert (
        _validate_integration_binding(
            integration_manifest(),
            manifest_sha="e" * 64,
            origin_url="https://github.com/sage1993/evidence-review-system.git",
            base_sha=SHA,
            candidate_sha=SHA,
            branch="integration/review-matter-and-policy",
            commits=(("c" * 40, "first"), ("d" * 40, "second")),
            pr_payload=integration_pr(body=body),
        )
        == "FAIL"
    )


def test_integration_binding_rejects_fenced_manifest_hash_and_unmapped_issue():
    from scripts.repository_gate import _validate_integration_binding

    manifest = integration_manifest()
    manifest["commits"][1] = {
        "sha": "d" * 40,
        "scope": "integration-policy",
        "description": "Record the integration policy in one place.",
    }
    assert (
        _validate_integration_binding(
            manifest,
            manifest_sha="e" * 64,
            origin_url="https://github.com/sage1993/evidence-review-system.git",
            base_sha=SHA,
            candidate_sha=SHA,
            branch="integration/review-matter-and-policy",
            commits=(("c" * 40, "first"), ("d" * 40, "second")),
            pr_payload=integration_pr(
                body=(
                    "Closes #227\nFixes #228\n```text\n"
                    "Integration-Manifest-SHA256: " + "e" * 64 + "\n```"
                )
            ),
        )
        == "FAIL"
    )


def test_integration_manifest_rejects_duplicate_json_keys(tmp_path: Path):
    from scripts.repository_gate import load_integration_manifest

    repository_root = tmp_path / "checkout"
    repository_root.mkdir()
    manifest_path = tmp_path / "integration.json"
    manifest_path.write_text('{"format":"one","format":"two"}', encoding="utf-8")
    document, manifest_sha, detail = load_integration_manifest(
        manifest_path, repository_root=repository_root
    )

    assert document is None
    assert manifest_sha == "NOT_VERIFIED"
    assert detail == "integration manifest unreadable: ValueError"


@pytest.mark.parametrize("case", ["fenced_hash", "unmapped_issue", "extra_commit",
                                 "duplicate_commit", "bool_version", "additional_scope"])
def test_integration_binding_independent_inventory_and_body_controls(case):
    from scripts.repository_gate import _validate_integration_binding

    manifest = integration_manifest()
    manifest_sha = "e" * 64
    body = f"Closes #227\nFixes #228\nIntegration-Manifest-SHA256: {manifest_sha}"
    commits = [("c" * 40, "first"), ("d" * 40, "second")]
    if case == "fenced_hash":
        body = f"Closes #227\nFixes #228\n```\nIntegration-Manifest-SHA256: {manifest_sha}\n```"
    elif case == "unmapped_issue":
        manifest["issues"].append(229)
        body += "\nCloses #229"
    elif case == "extra_commit":
        manifest["commits"].append({
            "sha": "f" * 40, "scope": "additional-policy",
            "description": "Additional policy outside declared inventory.",
        })
    elif case == "duplicate_commit":
        manifest["commits"][1]["sha"] = "c" * 40
    elif case == "bool_version":
        manifest["version"] = True
    else:
        manifest["commits"].append({
            "sha": "f" * 40, "scope": "additional-policy",
            "description": "Explicitly describe additional integration work.",
        })
        commits.append(("f" * 40, "additional work"))
    result = _validate_integration_binding(
        manifest, manifest_sha=manifest_sha,
        origin_url="https://github.com/sage1993/evidence-review-system.git",
        base_sha=SHA, candidate_sha=SHA, branch="integration/review-matter-and-policy",
        commits=commits, pr_payload=integration_pr(body=body),
    )
    assert result == ("PASS" if case == "additional_scope" else "FAIL")


def test_post_report_recheck_rejects_changed_integration_manifest(tmp_path: Path):
    from scripts.repository_gate import (
        _post_report_recheck,
        load_integration_manifest,
    )

    repository_root = tmp_path / "checkout"
    repository_root.mkdir()
    manifest_path = tmp_path / "integration.json"
    manifest_path.write_text(json.dumps(integration_manifest()), encoding="utf-8")
    _document, manifest_sha, _detail = load_integration_manifest(
        manifest_path, repository_root=repository_root
    )
    manifest_path.write_text('{"changed":true}', encoding="utf-8")

    class Runner:
        def __call__(self, args, _cwd):
            command = tuple(args)
            if command == ("git", "rev-parse", "HEAD"):
                return CommandResult(command, 0, SHA + "\n")
            if command == ("git", "rev-parse", "origin/main"):
                return CommandResult(command, 0, SHA + "\n")
            if command[:3] == ("git", "status", "--porcelain=v1"):
                return CommandResult(command, 0)
            if command[:3] == ("git", "diff", "--check") or command == (
                "git", "diff", "--cached", "--check"
            ):
                return CommandResult(command, 0)
            if command[:3] == ("git", "ls-remote", "origin"):
                return CommandResult(command, 0, f"{SHA}\t{command[3]}\n")
            if command == ("git", "remote", "get-url", "origin"):
                return CommandResult(
                    command, 0, "https://github.com/sage1993/evidence-review-system.git\n"
                )
            if command[:2] == ("git", "log"):
                return CommandResult(
                    command, 0, f"{'c' * 40}\x00first\n{'d' * 40}\x00second\n"
                )
            if command[:3] == ("gh", "pr", "view"):
                return CommandResult(
                    command,
                    0,
                    json.dumps(
                        integration_pr(
                            body=(
                                "Closes #227\nFixes #228\n\n"
                                f"Integration-Manifest-SHA256: {manifest_sha}"
                            )
                        )
                    ),
                )
            raise AssertionError(command)

    verdict = replace(
        complete_verdict(),
        branch="integration/review-matter-and-policy",
        verification_mode="INTEGRATION",
        integration_manifest_sha256=manifest_sha,
    )
    result = _post_report_recheck(
        repository_root,
        verdict,
        issue_number=None,
        integration_manifest_path=manifest_path,
        package_evidence_path=None,
        command_runner=Runner(),
    )

    assert result == "integration manifest changed after report write"


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
