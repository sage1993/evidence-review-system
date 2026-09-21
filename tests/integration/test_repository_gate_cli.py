import hashlib
import json
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import repository_gate
from scripts.repository_gate import (
    REQUIRED_GATE_NAMES,
    CommandResult,
    GateStatus,
    GateVerdict,
)

SHA = "a" * 40


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


def test_cli_returns_zero_for_clean_ready_verdict(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: complete_verdict(),
    )
    monkeypatch.setattr(repository_gate, "_post_report_recheck", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        repository_gate,
        "run_command",
        lambda args, _cwd: CommandResult(tuple(args), 0, f"{SHA}\n"),
    )

    assert repository_gate.main(
        [
            "--repository-root",
            ".",
            "--issue",
            "227",
            "--json-report",
            str(tmp_path / "repository-gate-report.json"),
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "SHA_PARITY = PASS" in output
    assert "GITHUB_ACTIONS = NOT_USED_BY_POLICY" in output
    assert "MERGE_READINESS = READY_FOR_REVIEW" in output


def test_cli_requires_explicit_issue_binding(monkeypatch, capsys):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: complete_verdict(),
    )

    assert repository_gate.main(["--repository-root", "."]) == 1
    output = capsys.readouterr().out
    assert "ISSUE_BINDING = NOT_VERIFIED" in output
    assert "MERGE_READINESS = HOLD" in output


def test_cli_rejects_issue_and_integration_manifest_together():
    with pytest.raises(SystemExit):
        repository_gate.main(
            [
                "--repository-root",
                ".",
                "--issue",
                "227",
                "--integration-manifest",
                "C:\\integration.json",
            ]
        )


@pytest.mark.parametrize("mutate_manifest", [False, True])
def test_integration_cli_runs_all_gates_and_rechecks_manifest(
    monkeypatch, tmp_path, mutate_manifest
):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    branch = "codex/integration-test"
    origin = "https://github.com/sage1993/evidence-review-system.git"
    manifest_path = tmp_path / "integration.json"
    manifest_path.write_text(json.dumps({
        "format": "evidence-review/integration-gate", "version": 1,
        "origin_url": origin, "base_sha": "b" * 40, "candidate_sha": SHA,
        "branch": branch, "issues": [227], "commits": [{
            "sha": SHA, "issues": [227], "description": "Integrate the verified policy change.",
        }],
    }), encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    gates = []

    def runner(args, _cwd):
        command = tuple(args)
        output = ""
        if command == ("git", "branch", "--show-current"):
            output = branch
        elif command == ("git", "rev-parse", "HEAD"):
            output = SHA
        elif command == ("git", "rev-parse", "origin/main"):
            output = "b" * 40
        elif command == ("git", "remote", "get-url", "origin"):
            output = origin
        elif command[:3] == ("git", "ls-remote", "origin"):
            remote_sha = "b" * 40 if command[3] == "refs/heads/main" else SHA
            output = f"{remote_sha}\t{command[3]}"
        elif command[:2] == ("git", "log"):
            output = f"{SHA}\x00Integration change without single-issue title"
        elif command[:3] == ("gh", "pr", "view"):
            output = json.dumps({
                "number": 250, "headRefName": branch, "headRefOid": SHA,
                "baseRefName": "main",
                "body": f"Closes #227\nIntegration-Manifest-SHA256: {manifest_sha}",
            })
        elif "-m" in command:
            gates.append(command[command.index("-m") + 1:])
            if mutate_manifest and "pytest" in command:
                manifest_path.write_text('{"changed":true}', encoding="utf-8")
        elif command[:2] in {("git", "status"), ("git", "diff"), ("git", "merge-base")}:
            pass
        else:
            raise AssertionError(command)
        return CommandResult(command, 0, output)

    collect = repository_gate.collect_repository_state
    recheck = repository_gate._post_report_recheck
    collected = []

    def observed_collect(root, **kwargs):
        verdict = collect(root, command_runner=runner, **kwargs)
        collected.append(verdict)
        return verdict

    monkeypatch.setattr(repository_gate, "collect_repository_state", observed_collect)
    monkeypatch.setattr(repository_gate, "_post_report_recheck",
                        lambda root, verdict, **kwargs: recheck(
                            root, verdict, command_runner=runner, **kwargs))
    report = tmp_path / "report.json"
    code = repository_gate.main([
        "--repository-root", str(checkout), "--integration-manifest", str(manifest_path),
        "--json-report", str(report),
    ])
    result = json.loads(report.read_text(encoding="utf-8"))
    assert [command[0] for command in gates] == [
        "evidence_review", "pytest", "ruff", "mypy", "mypy", "compileall",
    ]
    assert all(item["status"] == "PASS" for item in result["gate_statuses"])
    assert result["integration_manifest_sha256"] == manifest_sha
    assert result["verification_mode"] == "INTEGRATION"
    assert code == (1 if mutate_manifest else 0)
    assert result["merge_readiness"] == ("HOLD" if mutate_manifest else "READY_FOR_REVIEW")
    if mutate_manifest:
        assert collected[0].issue_binding == "FAIL"
        assert repository_gate.evaluate_verdict(collected[0]).merge_readiness == "HOLD"


def test_cli_requires_external_report_for_a_ready_verdict(monkeypatch, capsys):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: complete_verdict(),
    )

    assert repository_gate.main(["--repository-root", ".", "--issue", "227"]) == 1
    output = capsys.readouterr().out
    assert "MERGE_READINESS = READY_FOR_REVIEW" not in output
    assert "MERGE_READINESS = HOLD" in output


def test_cli_returns_nonzero_for_dirty_worktree(monkeypatch, capsys):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: replace(complete_verdict(), worktree="DIRTY"),
    )

    assert repository_gate.main(["--repository-root", "."]) == 1
    output = capsys.readouterr().out
    assert "WORKTREE = DIRTY" in output
    assert "MERGE_READINESS = HOLD" in output


def test_cli_holds_when_remote_or_pr_identity_is_unverified(monkeypatch, capsys):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: replace(
            complete_verdict(),
            remote_sha="NOT_VERIFIED",
            pr_head_sha="NOT_VERIFIED",
        ),
    )

    assert repository_gate.main(["--repository-root", "."]) == 1
    output = capsys.readouterr().out
    assert "REMOTE_SHA = NOT_VERIFIED" in output
    assert "PR_HEAD_SHA = NOT_VERIFIED" in output
    assert "GITHUB_ACTIONS = NOT_USED_BY_POLICY" in output
    assert "MERGE_READINESS = HOLD" in output


def test_required_gate_failure_holds(monkeypatch, capsys):
    statuses = tuple(
        GateStatus(name, "FAIL" if name == "PYTEST" else "PASS")
        for name in REQUIRED_GATE_NAMES
    )
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: replace(complete_verdict(), gate_statuses=statuses),
    )

    assert repository_gate.main(["--repository-root", "."]) == 1
    output = capsys.readouterr().out
    assert "PYTEST = FAIL" in output
    assert "MERGE_READINESS = HOLD" in output


def test_report_inside_tracked_repository_is_rejected():
    repository_root = Path.cwd()
    with pytest.raises(ValueError, match="outside the repository"):
        repository_gate._write_report(
            repository_root / "report.json",
            repository_gate.evaluate_verdict(complete_verdict()),
            repository_root,
        )


def test_report_inside_ignored_acceptance_directory_is_rejected(tmp_path):
    repository_root = tmp_path / "checkout"
    repository_root.mkdir()
    with pytest.raises(ValueError, match="outside the repository"):
        repository_gate._write_report(
            repository_root / ".acceptance" / "report.json",
            repository_gate.evaluate_verdict(complete_verdict()),
            repository_root,
        )


def test_report_path_must_be_absolute_even_when_it_resolves_outside(tmp_path):
    repository_root = tmp_path / "checkout"
    repository_root.mkdir()
    with pytest.raises(ValueError, match="absolute path"):
        repository_gate._write_report(
            Path("..") / "relative-report.json",
            repository_gate.evaluate_verdict(complete_verdict()),
            repository_root,
        )


def test_external_report_does_not_dirty_ready_verdict(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: complete_verdict(),
    )
    monkeypatch.setattr(repository_gate, "_post_report_recheck", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        repository_gate,
        "run_command",
        lambda args, _cwd: CommandResult(tuple(args), 0, f"{SHA}\n"),
    )
    report_path = tmp_path / "repository-gate-report.json"

    assert repository_gate.main(
        [
            "--repository-root",
            ".",
            "--issue",
            "227",
            "--json-report",
            str(report_path),
        ]
    ) == 0
    assert report_path.exists()
    assert "MERGE_READINESS = READY_FOR_REVIEW" in capsys.readouterr().out


def test_report_write_failure_cannot_print_ready(monkeypatch, capsys):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: complete_verdict(),
    )

    def fail_report(*_args, **_kwargs):
        raise OSError("report output unavailable")

    monkeypatch.setattr(repository_gate, "_write_report", fail_report)

    assert repository_gate.main(["--repository-root", ".", "--json-report", "report.json"]) == 1
    output = capsys.readouterr().out
    assert "MERGE_READINESS = READY_FOR_REVIEW" not in output
    assert "MERGE_READINESS = HOLD" in output


class RecheckingRunner:
    def __init__(self) -> None:
        self.status_calls = 0
        self.pr_command: tuple[str, ...] | None = None

    def __call__(self, args: list[str], _cwd: Path) -> CommandResult:
        command = tuple(args)
        if command == ("git", "branch", "--show-current"):
            return CommandResult(command, 0, "chore/issue-227-public-repository-governance\n")
        if command == ("git", "rev-parse", "HEAD"):
            return CommandResult(command, 0, f"{SHA}\n")
        if command == ("git", "rev-parse", "origin/main"):
            return CommandResult(command, 0, f"{SHA}\n")
        if command == ("git", "merge-base", "--is-ancestor", "origin/main", "HEAD"):
            return CommandResult(command, 0)
        if command[:3] == ("git", "merge-base", "--is-ancestor"):
            return CommandResult(command, 0)
        if command[:3] == ("git", "status", "--porcelain=v1"):
            self.status_calls += 1
            output = "" if self.status_calls == 1 else "?? .verification/report.json\n"
            return CommandResult(command, 0, output)
        if command[:3] == ("git", "diff", "--check"):
            return CommandResult(command, 0)
        if command == ("git", "diff", "--cached", "--check"):
            return CommandResult(command, 0)
        if command[:3] == ("git", "diff", "--name-only"):
            return CommandResult(command, 0)
        if command[0] == "py":
            return CommandResult(command, 0)
        if command[0:2] == ("git", "log"):
            return CommandResult(command, 0, f"{SHA}\x00chore(issue-227): test\n")
        if command[:3] == ("git", "ls-remote", "origin"):
            return CommandResult(command, 0, f"{SHA}\t{command[3]}\n")
        if command == ("git", "remote", "get-url", "origin"):
            return CommandResult(command, 0, "https://github.com/sage1993/evidence-review-system.git\n")
        if command[:3] == ("gh", "pr", "view"):
            self.pr_command = command
            return CommandResult(
                command,
                0,
                '{"headRefName":"chore/issue-227-public-repository-governance",'
                f'"headRefOid":"{SHA}"}}',
            )
        raise AssertionError(f"unexpected command: {command}")


class CandidateDiffFailureRunner(RecheckingRunner):
    def __call__(self, args: list[str], cwd: Path) -> CommandResult:
        command = tuple(args)
        if command[:3] == ("git", "diff", "--check") and len(command) > 3:
            return CommandResult(command, 1, stderr="candidate whitespace error")
        return super().__call__(args, cwd)


def test_collector_rechecks_worktree_after_gates(monkeypatch, tmp_path):
    runner = RecheckingRunner()
    temporary_arguments: dict[str, object] = {}

    def fake_temporary_directory(**kwargs):
        temporary_arguments.update(kwargs)
        return nullcontext(str(tmp_path))

    monkeypatch.setattr(
        repository_gate.tempfile,
        "TemporaryDirectory",
        fake_temporary_directory,
    )

    result = repository_gate.collect_repository_state(
        tmp_path,
        command_runner=runner,
    )
    evaluated = repository_gate.evaluate_verdict(result)

    assert runner.status_calls == 2
    assert temporary_arguments["dir"] == tmp_path
    assert evaluated.worktree == "DIRTY"
    assert evaluated.acceptance_artifacts == (".verification/report.json",)
    assert evaluated.merge_readiness == "HOLD"


def test_collector_detects_ignored_acceptance_artifact(tmp_path):
    artifact = tmp_path / ".acceptance" / "ignored-report.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")

    class CleanStatusRunner:
        def __call__(self, args: list[str], _cwd: Path) -> CommandResult:
            command = tuple(args)
            if command[:3] == ("git", "status", "--porcelain=v1"):
                return CommandResult(command, 0, "")
            raise AssertionError(f"unexpected command: {command}")

    status, paths, artifacts = repository_gate._observe_worktree(
        tmp_path,
        CleanStatusRunner(),
    )

    assert status == "CLEAN"
    assert paths == ()
    assert artifacts == (".acceptance/ignored-report.json",)


def test_collector_uses_explicit_branch_when_querying_pr(monkeypatch, tmp_path):
    runner = RecheckingRunner()
    monkeypatch.setattr(
        repository_gate.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: nullcontext(str(tmp_path)),
    )

    repository_gate.collect_repository_state(tmp_path, command_runner=runner)

    assert runner.pr_command is not None
    assert runner.pr_command[3] == "chore/issue-227-public-repository-governance"


def test_collector_uses_remote_main_authority_and_records_tracking_ref(monkeypatch, tmp_path):
    runner = RecheckingRunner()

    def remote_main_runner(args: list[str], cwd: Path) -> CommandResult:
        command = tuple(args)
        if command == ("git", "ls-remote", "origin", "refs/heads/main"):
            return CommandResult(command, 0, f"{SHA}\trefs/heads/main\n")
        if command == ("git", "rev-parse", "origin/main"):
            return CommandResult(command, 0, f"{'b' * 40}\n")
        return runner(args, cwd)

    monkeypatch.setattr(
        repository_gate.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: nullcontext(str(tmp_path)),
    )
    result = repository_gate.collect_repository_state(
        tmp_path,
        command_runner=remote_main_runner,
    )

    assert result.base_sha == SHA
    assert result.remote_base_sha == SHA
    assert result.local_remote_base_sha == "b" * 40
    assert repository_gate.evaluate_verdict(result).merge_readiness == "HOLD"


def test_collector_requires_external_package_evidence_for_package_change(
    monkeypatch, tmp_path
):
    class PackageChangeRunner(RecheckingRunner):
        def __call__(self, args: list[str], cwd: Path) -> CommandResult:
            command = tuple(args)
            if command[:3] == ("git", "diff", "--name-only"):
                return CommandResult(command, 0, "pyproject.toml\n")
            return super().__call__(args, cwd)

    monkeypatch.setattr(
        repository_gate.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: nullcontext(str(tmp_path)),
    )
    runner = PackageChangeRunner()

    result = repository_gate.collect_repository_state(
        tmp_path,
        command_runner=runner,
    )

    assert result.package_acceptance == "NOT_RUN"
    assert repository_gate.evaluate_verdict(result).merge_readiness == "HOLD"

    evidence_path = tmp_path.parent / "package-acceptance-evidence.json"
    evidence_path.write_text(
        '{"format":"evidence-review/package-acceptance",'
        '"version":1,'
        f'"candidate_sha":"{SHA}",'
        f'"wheel_sha256":"{"c" * 64}",'
        '"checks":{"WHEEL_BUILD":"PASS","ISOLATED_INSTALL":"PASS",'
        '"PIP_CHECK":"PASS","RUNTIME_SMOKE":"PASS"}}',
        encoding="utf-8",
    )
    accepted = repository_gate.collect_repository_state(
        tmp_path,
        package_evidence_path=evidence_path,
        command_runner=runner,
    )

    assert accepted.package_acceptance == "PASS"
    assert accepted.wheel_sha256 == "c" * 64


def test_collector_checks_committed_candidate_diff(monkeypatch, tmp_path):
    runner = CandidateDiffFailureRunner()
    monkeypatch.setattr(
        repository_gate.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: nullcontext(str(tmp_path)),
    )

    result = repository_gate.collect_repository_state(
        tmp_path,
        command_runner=runner,
    )
    evaluated = repository_gate.evaluate_verdict(result)

    assert evaluated.diff_check == "FAIL"
    assert evaluated.merge_readiness == "HOLD"


def test_collector_rechecks_head_after_remote_and_pr_collection(monkeypatch, tmp_path):
    class FinalHeadMutationRunner(RecheckingRunner):
        def __init__(self) -> None:
            super().__init__()
            self.head_calls = 0

        def __call__(self, args: list[str], cwd: Path) -> CommandResult:
            command = tuple(args)
            if command == ("git", "rev-parse", "HEAD"):
                self.head_calls += 1
                value = SHA if self.head_calls < 3 else "b" * 40
                return CommandResult(command, 0, f"{value}\n")
            return super().__call__(args, cwd)

    monkeypatch.setattr(
        repository_gate.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: nullcontext(str(tmp_path)),
    )
    result = repository_gate.collect_repository_state(
        tmp_path,
        command_runner=FinalHeadMutationRunner(),
    )

    assert result.candidate_stable_after_testing == "FAIL"


def test_post_report_head_change_holds_and_rewrites_report(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        repository_gate,
        "collect_repository_state",
        lambda _root, **_kwargs: complete_verdict(),
    )
    report_path = tmp_path / "repository-gate-report.json"
    monkeypatch.setattr(
        repository_gate,
        "run_command",
        lambda args, _cwd: CommandResult(tuple(args), 0, f"{'b' * 40}\n"),
    )

    assert repository_gate.main(
        [
            "--repository-root",
            ".",
            "--issue",
            "227",
            "--json-report",
            str(report_path),
        ]
    ) == 1
    output = capsys.readouterr().out
    assert "MERGE_READINESS = HOLD" in output
    assert "VERIFIER_ERROR = candidate HEAD changed after report write" in output
    assert '"merge_readiness": "HOLD"' in report_path.read_text(encoding="utf-8")
