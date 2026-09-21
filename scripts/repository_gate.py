"""Run the repository's local exact-SHA acceptance gate.

This module deliberately has no third-party runtime dependencies.  The
verdict model is kept separate from command execution so that every
fail-closed identity rule is directly testable without a GitHub connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
HOLD = "HOLD"
NOT_RUN = "NOT_RUN"
NOT_REQUIRED = "NOT_REQUIRED"
NOT_VERIFIED = "NOT_VERIFIED"
NOT_APPLICABLE = "NOT_APPLICABLE"
READY_FOR_REVIEW = "READY_FOR_REVIEW"
NOT_USED_BY_POLICY = "NOT_USED_BY_POLICY"
POLICY_MISMATCH = "POLICY_MISMATCH"

REQUIRED_GATE_NAMES = (
    "DOCUMENTATION_INTEGRITY",
    "PYTEST",
    "RUFF",
    "MYPY",
    "MYPY_WIN32",
    "COMPILEALL",
)
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
PACKAGE_CHECK_NAMES = (
    "WHEEL_BUILD",
    "ISOLATED_INSTALL",
    "PIP_CHECK",
    "RUNTIME_SMOKE",
)


@dataclass(frozen=True)
class CommandResult:
    """Captured result of one subprocess invocation."""

    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class GateStatus:
    """Status of one required repository gate."""

    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class GateVerdict:
    """All inputs required to decide local merge readiness."""

    branch: str
    base_sha: str
    base_ancestry: str
    candidate_sha: str
    committed_sha: str
    tested_sha: str
    remote_sha: str
    pr_head_sha: str
    worktree: str
    diff_check: str
    candidate_stable_after_testing: str
    unexpected_files: tuple[str, ...]
    acceptance_artifacts: tuple[str, ...]
    gate_statuses: tuple[GateStatus, ...]
    package_acceptance: str
    wheel_sha256: str
    github_actions: str
    sha_parity: str = HOLD
    merge_readiness: str = HOLD
    verifier_error: str = ""
    remote_base_sha: str = NOT_VERIFIED
    local_remote_base_sha: str = NOT_VERIFIED
    issue_binding: str = NOT_VERIFIED
    verification_mode: str = NOT_VERIFIED
    integration_manifest_sha256: str = NOT_APPLICABLE


CommandRunner = Callable[[Sequence[str], Path], CommandResult]


def _command_environment(cwd: Path) -> dict[str, str]:
    environment = os.environ.copy()
    source_path = str((cwd / "src").resolve())
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_path
        if not existing_pythonpath
        else f"{source_path}{os.pathsep}{existing_pythonpath}"
    )
    temporary_root = Path(tempfile.gettempdir())
    environment["RUFF_CACHE_DIR"] = str(temporary_root / "evidence-review-system-ruff-cache")
    environment["MYPY_CACHE_DIR"] = str(temporary_root / "evidence-review-system-mypy-cache")
    environment["PYTHONPYCACHEPREFIX"] = str(temporary_root / "evidence-review-system-pycache")
    return environment


def run_command(args: Sequence[str], cwd: Path) -> CommandResult:
    """Run one argument-vector command without invoking a shell."""

    normalized = tuple(str(arg) for arg in args)
    try:
        completed = subprocess.run(
            normalized,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=_command_environment(cwd),
        )
    except OSError as exc:
        return CommandResult(normalized, 127, "", str(exc))
    return CommandResult(normalized, completed.returncode, completed.stdout, completed.stderr)


def _status_by_name(verdict: GateVerdict, name: str) -> GateStatus:
    for status in verdict.gate_statuses:
        if status.name == name:
            return status
    return GateStatus(name, NOT_RUN, "missing from verifier result")


def _is_sha(value: str) -> bool:
    return bool(SHA_PATTERN.fullmatch(value))


def _sha_parity(verdict: GateVerdict) -> str:
    identities = (
        verdict.tested_sha,
        verdict.committed_sha,
        verdict.remote_sha,
        verdict.pr_head_sha,
    )
    if any(not _is_sha(value) for value in identities):
        return HOLD
    return PASS if len(set(identities)) == 1 else FAIL


def evaluate_verdict(verdict: GateVerdict) -> GateVerdict:
    """Apply the repository's fail-closed readiness rules."""

    sha_parity = _sha_parity(verdict)
    required_pass = all(
        _status_by_name(verdict, name).status == PASS for name in REQUIRED_GATE_NAMES
    )
    stable_branch = bool(verdict.branch) and verdict.branch not in {"main", "master"}
    remote_base_parity = (
        _is_sha(verdict.remote_base_sha)
        and verdict.remote_base_sha == verdict.base_sha
        and verdict.local_remote_base_sha == verdict.remote_base_sha
    )
    clean_state = (
        verdict.worktree == "CLEAN"
        and verdict.diff_check == PASS
        and verdict.base_ancestry == PASS
        and verdict.candidate_stable_after_testing == PASS
        and not verdict.unexpected_files
        and not verdict.acceptance_artifacts
    )
    package_pass = verdict.package_acceptance in {PASS, NOT_REQUIRED}
    ready = (
        stable_branch
        and _is_sha(verdict.base_sha)
        and remote_base_parity
        and clean_state
        and required_pass
        and package_pass
        and verdict.github_actions == NOT_USED_BY_POLICY
        and verdict.issue_binding == PASS
        and sha_parity == PASS
        and not verdict.verifier_error
    )
    return replace(
        verdict,
        sha_parity=sha_parity,
        merge_readiness=READY_FOR_REVIEW if ready else HOLD,
    )


def _display_files(files: tuple[str, ...]) -> str:
    return "NONE" if not files else ", ".join(files)


def format_summary(verdict: GateVerdict) -> str:
    """Render the stable operator-facing acceptance summary."""

    values = {
        "BASE_SHA": verdict.base_sha,
        "BRANCH": verdict.branch,
        "CANDIDATE_SHA": verdict.candidate_sha,
        "WORKTREE": verdict.worktree,
        "DIFF_CHECK": verdict.diff_check,
        "UNEXPECTED_FILES": _display_files(verdict.unexpected_files),
        "ACCEPTANCE_ARTIFACTS": _display_files(verdict.acceptance_artifacts),
        "BASE_ANCESTRY": verdict.base_ancestry,
        "CANDIDATE_STABLE_AFTER_TESTING": verdict.candidate_stable_after_testing,
        "REMOTE_MAIN_SHA": verdict.remote_base_sha,
        "LOCAL_REMOTE_MAIN_SHA": verdict.local_remote_base_sha,
        "TESTED_SHA": verdict.tested_sha,
        "COMMITTED_SHA": verdict.committed_sha,
        "DOCUMENTATION_INTEGRITY": _status_by_name(verdict, "DOCUMENTATION_INTEGRITY").status,
        "PYTEST": _status_by_name(verdict, "PYTEST").status,
        "RUFF": _status_by_name(verdict, "RUFF").status,
        "MYPY": _status_by_name(verdict, "MYPY").status,
        "MYPY_WIN32": _status_by_name(verdict, "MYPY_WIN32").status,
        "COMPILEALL": _status_by_name(verdict, "COMPILEALL").status,
        "PACKAGE_ACCEPTANCE": verdict.package_acceptance,
        "WHEEL_SHA256": verdict.wheel_sha256,
        "PUSHED_SHA": verdict.remote_sha,
        "REMOTE_SHA": verdict.remote_sha,
        "PR_HEAD_SHA": verdict.pr_head_sha,
        "SHA_PARITY": verdict.sha_parity,
        "GITHUB_ACTIONS": verdict.github_actions,
        "ISSUE_BINDING": verdict.issue_binding,
        "VERIFICATION_MODE": verdict.verification_mode,
        "INTEGRATION_MANIFEST_SHA256": verdict.integration_manifest_sha256,
        "MERGE_READINESS": verdict.merge_readiness,
    }
    lines = [f"{key} = {value}" for key, value in values.items()]
    if verdict.verifier_error:
        lines.append(f"VERIFIER_ERROR = {verdict.verifier_error}")
    return "\n".join(lines)


def _python_command(*args: str) -> list[str]:
    if os.name == "nt":
        return ["py", "-3.13", *args]
    return [sys.executable, *args]


def _gate_status(name: str, result: CommandResult) -> GateStatus:
    if result.returncode == 0:
        return GateStatus(name, PASS)
    detail = result.stderr.strip() or result.stdout.strip()
    detail = detail.splitlines()[-1][:300] if detail else f"exit code {result.returncode}"
    return GateStatus(name, FAIL, detail)


def _git_result(
    repository_root: Path,
    args: Sequence[str],
    command_runner: CommandRunner,
) -> CommandResult:
    return command_runner(["git", *args], repository_root)


def _git_text(
    repository_root: Path,
    args: Sequence[str],
    command_runner: CommandRunner,
) -> str:
    result = _git_result(repository_root, args, command_runner)
    return result.stdout.strip() if result.returncode == 0 else ""


def _path_from_status_line(line: str) -> str:
    payload = line[3:] if len(line) >= 3 else line
    if " -> " in payload:
        payload = payload.rsplit(" -> ", 1)[-1]
    return payload.strip().strip('"')


def _observe_worktree(
    repository_root: Path,
    command_runner: CommandRunner,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    result = _git_result(
        repository_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
        command_runner,
    )
    lines = tuple(line for line in result.stdout.splitlines() if line.strip())
    paths = tuple(_path_from_status_line(line) for line in lines)
    status = "CLEAN" if result.returncode == 0 and not lines else "DIRTY"
    status_artifacts = tuple(path for path in paths if _is_acceptance_artifact(path))
    artifacts = _unique((*status_artifacts, *_filesystem_acceptance_artifacts(repository_root)))
    return status, paths, artifacts


def _observe_diff_check(
    repository_root: Path,
    command_runner: CommandRunner,
    *,
    base_sha: str = "",
    head_sha: str = "",
) -> str:
    commands: list[Sequence[str]] = [
        ["diff", "--check"],
        ["diff", "--cached", "--check"],
    ]
    if _is_sha(base_sha) and _is_sha(head_sha):
        commands.append(["diff", "--check", base_sha, head_sha])
    results = (_git_result(repository_root, args, command_runner) for args in commands)
    return PASS if all(result.returncode == 0 for result in results) else FAIL


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _filesystem_acceptance_artifacts(repository_root: Path) -> tuple[str, ...]:
    """Find ignored acceptance artifacts without trusting git status."""

    artifacts: list[str] = []

    def visit(path: Path) -> None:
        relative = path.relative_to(repository_root).as_posix()
        try:
            path_stat = os.lstat(path)
        except FileNotFoundError:
            return
        except OSError:
            artifacts.append(f"{relative}/<unreadable>")
            return
        if _is_reparse_point(path):
            artifacts.append(f"{relative}/<reparse-point>")
            return
        if stat.S_ISREG(path_stat.st_mode):
            artifacts.append(relative)
            return
        if not stat.S_ISDIR(path_stat.st_mode):
            artifacts.append(f"{relative}/<not-directory>")
            return
        try:
            children = tuple(path.iterdir())
        except OSError:
            artifacts.append(f"{relative}/<unreadable>")
            return
        for child in children:
            visit(child)

    for relative_root in (".acceptance", "acceptance", ".verification"):
        visit(repository_root / relative_root)
    return _unique(artifacts)


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError:
        return True


def _is_acceptance_artifact(path: str) -> bool:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.startswith((".acceptance/", "acceptance/", ".verification/"))


def _remote_ref(branch: str, explicit_ref: str | None) -> str:
    expected_ref = f"refs/heads/{branch}"
    if explicit_ref:
        normalized = (
            explicit_ref
            if explicit_ref.startswith("refs/")
            else f"refs/heads/{explicit_ref.removeprefix('origin/')}"
        )
        if normalized != expected_ref:
            raise ValueError("remote ref must identify the current branch")
    return expected_ref


def _lookup_remote_sha(
    repository_root: Path,
    remote: str,
    branch: str,
    explicit_ref: str | None,
    command_runner: CommandRunner,
) -> str:
    ref = _remote_ref(branch, explicit_ref)
    result = command_runner(["git", "ls-remote", remote, ref], repository_root)
    if result.returncode != 0:
        return NOT_VERIFIED
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == ref and _is_sha(fields[0]):
            return fields[0]
    return NOT_VERIFIED


def _repository_slug(repository_root: Path, command_runner: CommandRunner) -> str | None:
    result = _git_result(repository_root, ["remote", "get-url", "origin"], command_runner)
    if result.returncode != 0:
        return None
    remote = result.stdout.strip().removesuffix(".git")
    match = re.search(r"github\.com[:/]([^/]+/[^/]+)$", remote, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _lookup_pr_metadata(
    repository_root: Path,
    branch: str,
    command_runner: CommandRunner,
) -> dict[str, object] | None:
    slug = _repository_slug(repository_root, command_runner)
    if not slug:
        return None
    result = command_runner(
        [
            "gh",
            "pr",
            "view",
            branch,
            "--repo",
            slug,
            "--json",
            "number,headRefName,headRefOid,baseRefName,body",
        ],
        repository_root,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("headRefName") != branch:
        return None
    return payload


def _lookup_pr_head_sha(
    repository_root: Path,
    branch: str,
    command_runner: CommandRunner,
) -> str:
    payload = _lookup_pr_metadata(repository_root, branch, command_runner)
    if payload is None:
        return NOT_VERIFIED
    value = payload.get("headRefOid")
    return value if isinstance(value, str) and _is_sha(value) else NOT_VERIFIED


def _package_change(paths: tuple[str, ...]) -> bool:
    package_prefixes = (
        "src/",
        "web_runtime/",
        "scripts/build_release.py",
        "scripts/validate_release.py",
        "pyproject.toml",
    )
    return any(path.replace("\\", "/").startswith(package_prefixes) for path in paths)


def observe_github_actions(repository_root: Path) -> str:
    """Observe whether this no-Actions repository contains workflow files."""

    github_root = repository_root / ".github"
    try:
        github_stat = os.lstat(github_root)
    except FileNotFoundError:
        return NOT_USED_BY_POLICY
    except OSError:
        return NOT_VERIFIED
    if _is_reparse_point(github_root) or not stat.S_ISDIR(github_stat.st_mode):
        return NOT_VERIFIED

    workflow_root = repository_root / ".github" / "workflows"
    try:
        root_stat = os.lstat(workflow_root)
    except FileNotFoundError:
        return NOT_USED_BY_POLICY
    except OSError:
        return NOT_VERIFIED
    if _is_reparse_point(workflow_root) or not stat.S_ISDIR(root_stat.st_mode):
        return NOT_VERIFIED

    def visit(path: Path) -> str:
        try:
            path_stat = os.lstat(path)
        except FileNotFoundError:
            return NOT_VERIFIED
        except OSError:
            return NOT_VERIFIED
        if _is_reparse_point(path):
            return NOT_VERIFIED
        if stat.S_ISREG(path_stat.st_mode):
            return (
                POLICY_MISMATCH
                if path.suffix.lower() in {".yml", ".yaml"}
                else NOT_USED_BY_POLICY
            )
        if not stat.S_ISDIR(path_stat.st_mode):
            return NOT_VERIFIED
        try:
            children = tuple(path.iterdir())
        except OSError:
            return NOT_VERIFIED
        for child in children:
            result = visit(child)
            if result != NOT_USED_BY_POLICY:
                return result
        return NOT_USED_BY_POLICY

    return visit(workflow_root)


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except AttributeError:
        return str(path).lower().startswith(str(root).lower() + os.sep)


def load_package_evidence(
    path: Path,
    *,
    repository_root: Path,
    candidate_sha: str,
) -> tuple[str, str, str]:
    """Validate exact-candidate external wheel/install/runtime evidence."""

    if not path.is_absolute():
        return NOT_VERIFIED, NOT_VERIFIED, "package evidence must be an absolute path"
    resolved = path.resolve()
    root = repository_root.resolve()
    if _path_is_inside(resolved, root):
        return NOT_VERIFIED, NOT_VERIFIED, "package evidence must be outside the repository"
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return NOT_VERIFIED, NOT_VERIFIED, f"package evidence unreadable: {type(exc).__name__}"
    if not isinstance(document, dict):
        return NOT_VERIFIED, NOT_VERIFIED, "package evidence must be a JSON object"
    if document.get("format") != "evidence-review/package-acceptance":
        return NOT_VERIFIED, NOT_VERIFIED, "invalid package evidence format"
    if document.get("version") != 1:
        return NOT_VERIFIED, NOT_VERIFIED, "unsupported package evidence version"
    evidence_sha = document.get("candidate_sha")
    if not isinstance(evidence_sha, str) or evidence_sha != candidate_sha:
        return NOT_VERIFIED, NOT_VERIFIED, "package evidence candidate SHA does not match"
    wheel_sha = document.get("wheel_sha256")
    if not isinstance(wheel_sha, str) or not SHA256_PATTERN.fullmatch(wheel_sha):
        return NOT_VERIFIED, NOT_VERIFIED, "package evidence wheel SHA-256 is invalid"
    checks = document.get("checks")
    if not isinstance(checks, dict):
        return NOT_VERIFIED, NOT_VERIFIED, "package evidence checks must be an object"
    for name in PACKAGE_CHECK_NAMES:
        if checks.get(name) != PASS:
            return FAIL, wheel_sha, f"package check failed: {name}"
    return PASS, wheel_sha, ""


def _validate_issue_binding(
    issue_number: int | None,
    branch: str,
    commit_subjects: Sequence[str],
    pr_payload: dict[str, object] | None,
) -> str:
    if issue_number is None or issue_number <= 0:
        return NOT_VERIFIED
    issue_token = str(issue_number)
    branch_pattern = re.compile(
        rf"(?:^|[/_.-])issue[-_/ ]?{re.escape(issue_token)}(?:$|[/_.-])",
        flags=re.IGNORECASE,
    )
    if not branch_pattern.search(branch):
        return FAIL
    if not commit_subjects:
        return NOT_VERIFIED
    commit_pattern = re.compile(
        rf"^[a-z][a-z0-9-]*\(issue-{re.escape(issue_token)}\):\s+\S.*$",
        flags=re.IGNORECASE,
    )
    if any(not commit_pattern.fullmatch(subject) for subject in commit_subjects):
        return FAIL
    if pr_payload is None:
        return NOT_VERIFIED
    required_fields = {
        "number",
        "headRefName",
        "headRefOid",
        "baseRefName",
        "body",
    }
    if not required_fields.issubset(pr_payload):
        return NOT_VERIFIED
    pr_number = pr_payload.get("number")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        return NOT_VERIFIED
    if pr_payload.get("headRefName") != branch:
        return FAIL
    if pr_payload.get("baseRefName") != "main":
        return FAIL
    head_ref_oid = pr_payload.get("headRefOid")
    if not isinstance(head_ref_oid, str) or not _is_sha(head_ref_oid):
        return NOT_VERIFIED
    body = pr_payload.get("body")
    if not isinstance(body, str):
        return NOT_VERIFIED
    closing_pattern = re.compile(
        rf"^[ \t]{{0,3}}(?:[-*][ \t]+)?"
        rf"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
        rf"#{re.escape(issue_token)}\b",
        flags=re.IGNORECASE,
    )
    fence_pattern = re.compile(r"^[ \t]*(`{3,}|~{3,})")
    fence: tuple[str, int] | None = None
    for line in body.splitlines():
        fence_match = fence_pattern.match(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_state = (marker[0], len(marker))
            if fence is None:
                fence = marker_state
            elif marker_state[0] == fence[0] and marker_state[1] >= fence[1]:
                fence = None
            continue
        if fence is None and closing_pattern.match(line):
            return PASS
    return FAIL


def _visible_pr_lines(body: str) -> tuple[str, ...]:
    """Return PR body lines that are outside fenced code blocks."""

    fence_pattern = re.compile(r"^[ \t]*(`{3,}|~{3,})")
    visible: list[str] = []
    fence: tuple[str, int] | None = None
    for line in body.splitlines():
        fence_match = fence_pattern.match(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_state = (marker[0], len(marker))
            if fence is None:
                fence = marker_state
            elif marker_state[0] == fence[0] and marker_state[1] >= fence[1]:
                fence = None
            continue
        if fence is None:
            visible.append(line)
    return tuple(visible)


def _closing_references(body: str, issues: Sequence[int]) -> set[int]:
    """Return valid closing references outside fenced code blocks."""

    closing_pattern = re.compile(
        r"^[ \t]{0,3}(?:[-*][ \t]+)?(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b",
        flags=re.IGNORECASE,
    )
    expected = set(issues)
    found: set[int] = set()
    for line in _visible_pr_lines(body):
        match = closing_pattern.match(line)
        if match and int(match.group(1)) in expected:
            found.add(int(match.group(1)))
    return found


def _validate_integration_binding(
    manifest: object,
    *,
    manifest_sha: str,
    origin_url: str,
    base_sha: str,
    candidate_sha: str,
    branch: str,
    commits: Sequence[tuple[str, str]],
    pr_payload: dict[str, object] | None,
) -> str:
    """Validate a multi-issue integration manifest against live identities."""

    if not isinstance(manifest, dict) or not SHA256_PATTERN.fullmatch(manifest_sha):
        return NOT_VERIFIED
    if (
        manifest.get("format") != "evidence-review/integration-gate"
        or type(manifest.get("version")) is not int
        or manifest.get("version") != 1
        or manifest.get("origin_url") != origin_url
        or manifest.get("base_sha") != base_sha
        or manifest.get("candidate_sha") != candidate_sha
        or manifest.get("branch") != branch
        or not _is_sha(base_sha)
        or not _is_sha(candidate_sha)
        or not branch
        or not origin_url
    ):
        return FAIL
    issues = manifest.get("issues")
    if (
        not isinstance(issues, list)
        or not issues
        or any(
            not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0
            for issue in issues
        )
        or len(set(issues)) != len(issues)
    ):
        return FAIL
    entries = manifest.get("commits")
    if not isinstance(entries, list) or not entries or len(entries) != len(commits):
        return FAIL
    actual_shas = tuple(sha for sha, _subject in commits)
    manifest_shas: list[str] = []
    mapped_issue_ids: set[int] = set()
    known_issues = set(issues)
    for entry in entries:
        if not isinstance(entry, dict):
            return FAIL
        sha = entry.get("sha")
        description = entry.get("description")
        mapped_issues = entry.get("issues")
        scope = entry.get("scope")
        if (
            not isinstance(sha, str)
            or not _is_sha(sha)
            or not isinstance(description, str)
            or len(description.strip()) < 12
            or (mapped_issues is None) == (scope is None)
        ):
            return FAIL
        if mapped_issues is not None:
            if (
                not isinstance(mapped_issues, list)
                or not mapped_issues
                or any(
                    not isinstance(issue, int)
                    or isinstance(issue, bool)
                    or issue not in known_issues
                    for issue in mapped_issues
                )
                or len(set(mapped_issues)) != len(mapped_issues)
            ):
                return FAIL
            mapped_issue_ids.update(mapped_issues)
        elif not isinstance(scope, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", scope):
            return FAIL
        manifest_shas.append(sha)
    if (
        len(set(manifest_shas)) != len(manifest_shas)
        or tuple(manifest_shas) != actual_shas
        or mapped_issue_ids != known_issues
    ):
        return FAIL
    if pr_payload is None:
        return NOT_VERIFIED
    if not {"number", "headRefName", "headRefOid", "baseRefName", "body"}.issubset(pr_payload):
        return NOT_VERIFIED
    if (
        not isinstance(pr_payload.get("number"), int)
        or isinstance(pr_payload.get("number"), bool)
        or pr_payload.get("number", 0) <= 0
        or pr_payload.get("headRefName") != branch
        or pr_payload.get("baseRefName") != "main"
        or pr_payload.get("headRefOid") != candidate_sha
        or not isinstance(pr_payload.get("body"), str)
    ):
        return FAIL
    body = pr_payload["body"]
    assert isinstance(body, str)
    if _closing_references(body, issues) != known_issues:
        return FAIL
    hash_pattern = re.compile(
        rf"^[ \t]*Integration-Manifest-SHA256:\s*{re.escape(manifest_sha)}\s*$",
        flags=re.IGNORECASE,
    )
    if not any(hash_pattern.fullmatch(line) for line in _visible_pr_lines(body)):
        return FAIL
    return PASS


def load_integration_manifest(
    path: Path,
    *,
    repository_root: Path,
) -> tuple[object | None, str, str]:
    """Read an external integration manifest and preserve its exact byte hash."""

    if not path.is_absolute():
        return None, NOT_VERIFIED, "integration manifest must be an absolute path"
    resolved = path.resolve()
    if _path_is_inside(resolved, repository_root.resolve()):
        return None, NOT_VERIFIED, "integration manifest must be outside the repository"
    try:
        raw = resolved.read_bytes()
        document = json.loads(raw, object_pairs_hook=_reject_duplicate_json_object)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return None, NOT_VERIFIED, f"integration manifest unreadable: {type(exc).__name__}"
    return document, hashlib.sha256(raw).hexdigest(), ""


def _reject_duplicate_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def _commits(
    repository_root: Path,
    base_sha: str,
    head_sha: str,
    command_runner: CommandRunner,
) -> tuple[tuple[str, str], ...]:
    commit_log = _git_text(
        repository_root,
        ["log", f"{base_sha}..{head_sha}", "--format=%H%x00%s"],
        command_runner,
    )
    entries: list[tuple[str, str]] = []
    for line in commit_log.splitlines():
        sha, separator, subject = line.partition("\x00")
        if not separator or not _is_sha(sha):
            return ()
        entries.append((sha, subject))
    return tuple(entries)


def _commit_subjects(
    repository_root: Path,
    base_sha: str,
    head_sha: str,
    command_runner: CommandRunner,
) -> tuple[str, ...]:
    commits = _commits(repository_root, base_sha, head_sha, command_runner)
    return tuple(subject for _sha, subject in commits)


def _empty_verdict(*, branch: str = "", error: str = "") -> GateVerdict:
    return GateVerdict(
        branch=branch,
        base_sha=NOT_VERIFIED,
        base_ancestry=NOT_VERIFIED,
        candidate_sha=NOT_VERIFIED,
        committed_sha=NOT_VERIFIED,
        tested_sha=NOT_VERIFIED,
        remote_sha=NOT_VERIFIED,
        pr_head_sha=NOT_VERIFIED,
        worktree="UNKNOWN",
        diff_check=NOT_VERIFIED,
        candidate_stable_after_testing=NOT_VERIFIED,
        unexpected_files=(),
        acceptance_artifacts=(),
        gate_statuses=tuple(GateStatus(name, NOT_VERIFIED) for name in REQUIRED_GATE_NAMES),
        package_acceptance=NOT_RUN,
        wheel_sha256=NOT_VERIFIED,
        github_actions=NOT_USED_BY_POLICY,
        remote_base_sha=NOT_VERIFIED,
        local_remote_base_sha=NOT_VERIFIED,
        issue_binding=NOT_VERIFIED,
        verifier_error=error,
    )


def collect_repository_state(
    repository_root: Path,
    *,
    tested_sha: str | None = None,
    remote_ref: str | None = None,
    pr_head_sha: str | None = None,
    issue_number: int | None = None,
    integration_manifest_path: Path | None = None,
    package_evidence_path: Path | None = None,
    command_runner: CommandRunner = run_command,
) -> GateVerdict:
    """Collect local, remote, PR, and canonical gate evidence."""

    branch = _git_text(repository_root, ["branch", "--show-current"], command_runner)
    head_before = _git_text(repository_root, ["rev-parse", "HEAD"], command_runner)
    if not branch or not _is_sha(head_before):
        return _empty_verdict(branch=branch, error="could not resolve branch or HEAD")
    origin_url = _git_text(repository_root, ["remote", "get-url", "origin"], command_runner)
    integration_manifest_document: object | None = None
    integration_manifest_sha256 = NOT_APPLICABLE
    if integration_manifest_path is not None:
        (
            integration_manifest_document,
            integration_manifest_sha256,
            _manifest_detail,
        ) = load_integration_manifest(
            integration_manifest_path,
            repository_root=repository_root,
        )

    local_remote_base_sha = _git_text(
        repository_root,
        ["rev-parse", "origin/main"],
        command_runner,
    )
    remote_base_sha = _lookup_remote_sha(
        repository_root,
        "origin",
        "main",
        "refs/heads/main",
        command_runner,
    )
    base_sha = remote_base_sha
    if _is_sha(remote_base_sha):
        ancestry_result = _git_result(
            repository_root,
            ["merge-base", "--is-ancestor", remote_base_sha, "HEAD"],
            command_runner,
        )
        if ancestry_result.returncode == 0:
            base_ancestry = PASS
        elif ancestry_result.returncode == 1:
            base_ancestry = FAIL
        else:
            base_ancestry = NOT_VERIFIED
    else:
        base_ancestry = NOT_VERIFIED

    initial_worktree, initial_paths, initial_artifacts = _observe_worktree(
        repository_root,
        command_runner,
    )
    initial_diff_check = _observe_diff_check(
        repository_root,
        command_runner,
        base_sha=base_sha,
        head_sha=head_before,
    )

    changed_paths: tuple[str, ...] = ()
    if _is_sha(base_sha):
        changed_result = _git_result(
            repository_root,
            ["diff", "--name-only", base_sha, head_before],
            command_runner,
        )
        if changed_result.returncode == 0:
            changed_paths = tuple(
                line.strip() for line in changed_result.stdout.splitlines() if line.strip()
            )

    with tempfile.TemporaryDirectory(
        prefix="evidence-review-documentation-",
        dir=repository_root,
        ignore_cleanup_errors=True,
    ) as temporary:
        temporary_output = Path(temporary) / "documentation-integrity.json"
        commands = (
            (
                "DOCUMENTATION_INTEGRITY",
                _python_command(
                    "-m",
                    "evidence_review",
                    "documentation",
                    "validate",
                    "--repository-root",
                    str(repository_root),
                    "--config",
                    str(repository_root / "documentation-integrity.json"),
                    "--output",
                    str(temporary_output),
                ),
            ),
            ("PYTEST", _python_command("-m", "pytest", "-v")),
            ("RUFF", _python_command("-m", "ruff", "check", "src", "tests", "web_runtime")),
            ("MYPY", _python_command("-m", "mypy", "src")),
            ("MYPY_WIN32", _python_command("-m", "mypy", "--platform", "win32", "src")),
            (
                "COMPILEALL",
                _python_command("-m", "compileall", "-q", "src", "scripts", "web_runtime", "tests"),
            ),
        )
        gate_statuses = tuple(
            _gate_status(name, command_runner(args, repository_root)) for name, args in commands
        )

    head_after = _git_text(repository_root, ["rev-parse", "HEAD"], command_runner)
    resolved_remote_sha = _lookup_remote_sha(
        repository_root,
        "origin",
        branch,
        remote_ref,
        command_runner,
    )
    pr_payload = _lookup_pr_metadata(repository_root, branch, command_runner)
    resolved_pr_head_sha = pr_head_sha
    if resolved_pr_head_sha is None:
        if pr_payload is None:
            resolved_pr_head_sha = NOT_VERIFIED
        else:
            value = pr_payload.get("headRefOid")
            resolved_pr_head_sha = (
                value if isinstance(value, str) and _is_sha(value) else NOT_VERIFIED
            )
    commits = _commits(
        repository_root,
        base_sha,
        head_before,
        command_runner,
    )
    issue_binding = _validate_issue_binding(
        issue_number,
        branch,
        tuple(subject for _sha, subject in commits),
        pr_payload,
    )
    verification_mode = "ISSUE" if issue_number is not None else NOT_VERIFIED
    if integration_manifest_path is not None:
        verification_mode = "INTEGRATION"
        issue_binding = _validate_integration_binding(
            integration_manifest_document,
            manifest_sha=integration_manifest_sha256,
            origin_url=origin_url,
            base_sha=base_sha,
            candidate_sha=head_before,
            branch=branch,
            commits=commits,
            pr_payload=pr_payload,
        )
        _current_manifest, current_manifest_sha, _manifest_detail = load_integration_manifest(
            integration_manifest_path,
            repository_root=repository_root,
        )
        if current_manifest_sha != integration_manifest_sha256:
            issue_binding = FAIL
    if _package_change(changed_paths):
        if package_evidence_path is None:
            package_acceptance = NOT_RUN
            wheel_sha256 = NOT_VERIFIED
        else:
            package_acceptance, wheel_sha256, _package_detail = load_package_evidence(
                package_evidence_path,
                repository_root=repository_root,
                candidate_sha=head_before,
            )
    else:
        package_acceptance = NOT_REQUIRED
        wheel_sha256 = NOT_APPLICABLE
    final_worktree, final_paths, final_artifacts = _observe_worktree(
        repository_root,
        command_runner,
    )
    final_diff_check = _observe_diff_check(
        repository_root,
        command_runner,
        base_sha=base_sha,
        head_sha=head_after,
    )
    head_final = _git_text(repository_root, ["rev-parse", "HEAD"], command_runner)
    candidate_stable_after_testing = (
        PASS
        if head_after == head_before == head_final and _is_sha(head_final)
        else FAIL
    )
    status_paths = _unique((*initial_paths, *final_paths))
    acceptance_artifacts = _unique((*initial_artifacts, *final_artifacts))
    worktree = "CLEAN" if initial_worktree == "CLEAN" and final_worktree == "CLEAN" else "DIRTY"
    diff_check = PASS if initial_diff_check == PASS and final_diff_check == PASS else FAIL
    resolved_tested_sha = tested_sha if tested_sha is not None else head_final
    return GateVerdict(
        branch=branch,
        base_sha=base_sha or NOT_VERIFIED,
        base_ancestry=base_ancestry,
        candidate_sha=head_before,
        committed_sha=head_before,
        tested_sha=resolved_tested_sha or NOT_VERIFIED,
        remote_sha=resolved_remote_sha,
        pr_head_sha=resolved_pr_head_sha or NOT_VERIFIED,
        worktree=worktree,
        diff_check=diff_check,
        candidate_stable_after_testing=candidate_stable_after_testing,
        unexpected_files=status_paths,
        acceptance_artifacts=acceptance_artifacts,
        gate_statuses=gate_statuses,
        package_acceptance=package_acceptance,
        wheel_sha256=wheel_sha256,
        github_actions=observe_github_actions(repository_root),
        remote_base_sha=remote_base_sha,
        local_remote_base_sha=local_remote_base_sha or NOT_VERIFIED,
        issue_binding=issue_binding,
        verification_mode=verification_mode,
        integration_manifest_sha256=integration_manifest_sha256,
    )


def _post_report_recheck(
    repository_root: Path,
    verdict: GateVerdict,
    *,
    issue_number: int | None,
    integration_manifest_path: Path | None,
    package_evidence_path: Path | None,
    command_runner: CommandRunner = run_command,
) -> str | None:
    """Recheck all readiness inputs after writing an external report."""

    current_head = _git_text(repository_root, ["rev-parse", "HEAD"], command_runner)
    if current_head != verdict.candidate_sha:
        return "candidate HEAD changed after report write"

    worktree, paths, artifacts = _observe_worktree(repository_root, command_runner)
    if worktree != "CLEAN" or paths or artifacts:
        return "worktree changed after report write"
    if (
        _observe_diff_check(
            repository_root,
            command_runner,
            base_sha=verdict.base_sha,
            head_sha=current_head,
        )
        != PASS
    ):
        return "diff check changed after report write"

    remote_base_sha = _lookup_remote_sha(
        repository_root,
        "origin",
        "main",
        "refs/heads/main",
        command_runner,
    )
    local_remote_base_sha = _git_text(
        repository_root,
        ["rev-parse", "origin/main"],
        command_runner,
    )
    if (
        remote_base_sha != verdict.remote_base_sha
        or local_remote_base_sha != verdict.local_remote_base_sha
    ):
        return "main base identity changed after report write"

    remote_sha = _lookup_remote_sha(
        repository_root,
        "origin",
        verdict.branch,
        None,
        command_runner,
    )
    if remote_sha != verdict.remote_sha:
        return "remote candidate identity changed after report write"

    pr_payload = _lookup_pr_metadata(repository_root, verdict.branch, command_runner)
    if pr_payload is None:
        return "PR metadata unavailable after report write"
    pr_head_sha = pr_payload.get("headRefOid")
    if not isinstance(pr_head_sha, str) or pr_head_sha != verdict.pr_head_sha:
        return "PR head identity changed after report write"
    commits = _commits(
        repository_root, verdict.base_sha, verdict.candidate_sha, command_runner
    )
    if integration_manifest_path is None:
        issue_binding = _validate_issue_binding(
            issue_number,
            verdict.branch,
            tuple(subject for _sha, subject in commits),
            pr_payload,
        )
    else:
        manifest, manifest_sha, _manifest_detail = load_integration_manifest(
            integration_manifest_path,
            repository_root=repository_root,
        )
        if manifest_sha != verdict.integration_manifest_sha256:
            return "integration manifest changed after report write"
        origin_url = _git_text(repository_root, ["remote", "get-url", "origin"], command_runner)
        issue_binding = _validate_integration_binding(
            manifest,
            manifest_sha=manifest_sha,
            origin_url=origin_url,
            base_sha=verdict.base_sha,
            candidate_sha=verdict.candidate_sha,
            branch=verdict.branch,
            commits=commits,
            pr_payload=pr_payload,
        )
    if issue_binding != verdict.issue_binding:
        return "issue binding changed after report write"

    if observe_github_actions(repository_root) != verdict.github_actions:
        return "GitHub Actions observation changed after report write"

    if verdict.package_acceptance == PASS:
        if package_evidence_path is None:
            return "package evidence unavailable after report write"
        package_acceptance, wheel_sha256, _detail = load_package_evidence(
            package_evidence_path,
            repository_root=repository_root,
            candidate_sha=verdict.candidate_sha,
        )
        if (
            package_acceptance != verdict.package_acceptance
            or wheel_sha256 != verdict.wheel_sha256
        ):
            return "package evidence changed after report write"
    return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--tested-sha")
    parser.add_argument("--remote-ref")
    binding = parser.add_mutually_exclusive_group()
    binding.add_argument("--issue", type=int)
    binding.add_argument("--integration-manifest", type=Path)
    parser.add_argument("--package-evidence", type=Path)
    parser.add_argument("--json-report", type=Path)
    return parser


def _write_report(path: Path, verdict: GateVerdict, repository_root: Path) -> None:
    if not path.is_absolute():
        raise ValueError("--json-report must be an absolute path outside the repository")
    resolved = path
    resolved = resolved.resolve()
    root = repository_root.resolve()
    if _path_is_inside(resolved, root):
        raise ValueError("--json-report must be outside the repository")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(asdict(verdict), indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = args.repository_root.resolve()
    try:
        raw = collect_repository_state(
            repository_root,
            tested_sha=args.tested_sha,
            remote_ref=args.remote_ref,
            issue_number=args.issue,
            integration_manifest_path=args.integration_manifest,
            package_evidence_path=args.package_evidence,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raw = _empty_verdict(error=f"{type(exc).__name__}: {exc}")
    if args.issue is None and args.integration_manifest is None:
        raw = replace(raw, issue_binding=NOT_VERIFIED)
    verdict = evaluate_verdict(raw)
    if args.json_report is None and verdict.merge_readiness == READY_FOR_REVIEW:
        verdict = replace(
            verdict,
            merge_readiness=HOLD,
            verifier_error="--json-report is required for READY_FOR_REVIEW",
        )
    report_written = False
    if args.json_report:
        try:
            _write_report(args.json_report, verdict, repository_root)
            report_written = True
        except (OSError, ValueError) as exc:
            verdict = replace(
                verdict,
                merge_readiness=HOLD,
                verifier_error=f"report write failed: {type(exc).__name__}: {exc}",
            )
    if report_written and verdict.merge_readiness == READY_FOR_REVIEW:
        try:
            recheck_error = _post_report_recheck(
                repository_root,
                verdict,
                issue_number=args.issue,
                integration_manifest_path=args.integration_manifest,
                package_evidence_path=args.package_evidence,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            recheck_error = f"post-report recheck failed: {type(exc).__name__}: {exc}"
        if recheck_error:
            verdict = replace(verdict, merge_readiness=HOLD, verifier_error=recheck_error)
            try:
                _write_report(args.json_report, verdict, repository_root)
            except (OSError, ValueError) as exc:
                verdict = replace(
                    verdict,
                    merge_readiness=HOLD,
                    verifier_error=f"report write failed: {type(exc).__name__}: {exc}",
                )
    print(format_summary(verdict))
    return 0 if verdict.merge_readiness == READY_FOR_REVIEW else 1


if __name__ == "__main__":
    raise SystemExit(main())
