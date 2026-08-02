"""Deterministic create-only activation for hash-bound approved rules."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.formats import RULE_ACTIVATION_REPORT_FORMAT
from ansim_review.rule_engine.governance_contract import (
    ActiveRuleEntry,
    ActiveRuleManifest,
    ActivationFinding,
    ActivationReport,
    active_rule_manifest_bytes,
    load_active_rule_manifest_bytes,
)
from ansim_review.rule_engine.governance_verify import (
    GovernanceVerificationError,
    VerifiedApproval,
    verify_approval,
)


@dataclass(frozen=True, slots=True)
class _PreparedPublication:
    private_path: Path
    destination: Path


@dataclass(frozen=True, slots=True)
class _PublishedInode:
    destination: Path
    device: int
    inode: int


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path(value: str, field: str) -> str:
    if not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    return value


def _resolved_root(repository_root: Path) -> Path:
    resolved = repository_root.resolve(strict=True)
    if repository_root.is_symlink() or not resolved.is_dir():
        raise ValueError("repository_root must be a real directory")
    return resolved


def _argument_relative(root: Path, path: Path, field: str) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"{field} must be below repository_root") from error
    return _safe_path(relative, field)


def _output_target(root: Path, relative: str) -> Path:
    destination = root / PurePosixPath(relative)
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"output path traverses a symlink: {relative}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"output parent is not a directory: {relative}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    return destination


def _prepare_publication(destination: Path, payload: bytes) -> _PreparedPublication:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".private",
        dir=destination.parent,
    )
    private_path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        private_path.unlink(missing_ok=True)
        raise
    return _PreparedPublication(private_path=private_path, destination=destination)


def _same_inode(path: Path, published: _PublishedInode) -> bool:
    try:
        current = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (
        not path.is_symlink()
        and current.st_dev == published.device
        and current.st_ino == published.inode
    )


def _publish_create_only(publications: Sequence[tuple[Path, bytes]]) -> None:
    prepared: list[_PreparedPublication] = []
    published: list[_PublishedInode] = []
    try:
        for destination, payload in publications:
            prepared.append(_prepare_publication(destination, payload))
        for item in prepared:
            os.link(item.private_path, item.destination)
            status = item.destination.stat(follow_symlinks=False)
            published.append(
                _PublishedInode(
                    destination=item.destination,
                    device=status.st_dev,
                    inode=status.st_ino,
                )
            )
    except BaseException:
        for item in reversed(published):
            if _same_inode(item.destination, item):
                item.destination.unlink(missing_ok=True)
        raise
    finally:
        for item in prepared:
            item.private_path.unlink(missing_ok=True)


def _finding_payload(finding: ActivationFinding) -> dict[str, object]:
    return {
        "artifact_path": finding.artifact_path,
        "rule_id": finding.rule_id,
        "code": finding.code,
        "message": finding.message,
    }


def activation_report_bytes(report: ActivationReport) -> bytes:
    """Serialize one activation report to canonical JSON bytes."""
    return dump_bytes(
        {
            "format": RULE_ACTIVATION_REPORT_FORMAT,
            "version": 1,
            "status": report.status,
            "approval_count": report.approval_count,
            "activated_rule_count": report.activated_rule_count,
            "approval_files": list(report.approval_files),
            "findings": [_finding_payload(item) for item in report.findings],
            "active_manifest_sha256": report.active_manifest_sha256,
        }
    )


def _semantic_version_key(version: str) -> tuple[int, int, int, int, tuple[str, ...]]:
    without_build = version.split("+", 1)[0]
    base, separator, prerelease = without_build.partition("-")
    major, minor, patch = (int(part) for part in base.split("."))
    return (major, minor, patch, 1 if not separator else 0, tuple(prerelease.split(".")))


def _verified_sort_key(
    verified: VerifiedApproval,
) -> tuple[str, tuple[int, int, int, int, tuple[str, ...]], str]:
    approval = verified.approval
    return (
        approval.rule_id,
        _semantic_version_key(approval.rule_version),
        verified.approval_path,
    )


def _entry(root: Path, verified: VerifiedApproval) -> ActiveRuleEntry:
    approval = verified.approval
    approval_file = root / PurePosixPath(verified.approval_path)
    return ActiveRuleEntry(
        rule_id=approval.rule_id,
        rule_version=approval.rule_version,
        candidate_path=approval.candidate_path,
        candidate_sha256=approval.candidate_sha256,
        approved_rule_path=approval.approved_rule_path,
        approved_rule_sha256=approval.approved_rule_sha256,
        golden_report_path=approval.golden_report_path,
        golden_report_sha256=approval.golden_report_sha256,
        approval_path=verified.approval_path,
        approval_sha256=_sha256_file(approval_file),
        scope=approval.scope,
        reviewer_id=approval.reviewer_id,
        reviewed_at=approval.reviewed_at,
        reason=approval.reason,
    )


def _blocked_report(
    approval_files: tuple[str, ...],
    findings: Sequence[ActivationFinding],
) -> ActivationReport:
    return ActivationReport(
        status="BLOCKED",
        approval_count=len(approval_files),
        activated_rule_count=0,
        approval_files=approval_files,
        findings=tuple(findings),
        active_manifest_sha256=None,
    )


def _path_findings(paths: Sequence[str]) -> tuple[ActivationFinding, ...]:
    counts = Counter(paths)
    duplicates = sorted(path for path, count in counts.items() if count > 1)
    if duplicates:
        return (
            ActivationFinding(
                artifact_path=duplicates[0],
                rule_id=None,
                code="DUPLICATE_APPROVAL_PATH",
                message="approval path is listed more than once",
            ),
        )
    by_folded: dict[str, str] = {}
    for path in paths:
        previous = by_folded.get(path.casefold())
        if previous is not None and previous != path:
            return (
                ActivationFinding(
                    artifact_path=path,
                    rule_id=None,
                    code="CASEFOLD_PATH_COLLISION",
                    message=f"approval path collides with {previous}",
                ),
            )
        by_folded[path.casefold()] = path
    return ()


def _normalize_approval_paths(
    root: Path,
    approval_paths: Sequence[Path],
) -> tuple[tuple[str, ...], tuple[ActivationFinding, ...]]:
    normalized: list[str] = []
    for path in approval_paths:
        try:
            normalized.append(_argument_relative(root, path, "approval_path"))
        except ValueError as error:
            return (
                tuple(sorted(item.as_posix() for item in approval_paths)),
                (
                    ActivationFinding(
                        artifact_path=path.as_posix(),
                        rule_id=None,
                        code="UNSAFE_APPROVAL_PATH",
                        message=str(error),
                    ),
                ),
            )
    normalized_tuple = tuple(sorted(normalized))
    return normalized_tuple, _path_findings(normalized_tuple)


def build_active_manifest(
    repository_root: Path,
    approval_paths: Sequence[Path],
    output_manifest: Path,
    output_report: Path,
) -> ActivationReport:
    """Verify all approvals and publish a complete scoped active manifest."""
    root = _resolved_root(repository_root)
    manifest_relative = _argument_relative(root, output_manifest, "output_manifest")
    report_relative = _argument_relative(root, output_report, "output_report")
    if manifest_relative.casefold() == report_relative.casefold():
        raise ValueError("output manifest and report paths must be distinct")
    manifest_destination = _output_target(root, manifest_relative)
    report_destination = _output_target(root, report_relative)

    approval_files, findings = _normalize_approval_paths(root, approval_paths)
    if not findings:
        verification_findings: list[ActivationFinding] = []
        verified: list[VerifiedApproval] = []
        for relative in approval_files:
            try:
                verified.append(verify_approval(root, Path(relative), mode="ACTIVATION"))
            except GovernanceVerificationError as error:
                verification_findings.append(
                    ActivationFinding(
                        artifact_path=error.artifact_path or relative,
                        rule_id=None,
                        code=error.code,
                        message=str(error),
                    )
                )
        findings = tuple(
            sorted(
                verification_findings,
                key=lambda item: (
                    item.artifact_path or "",
                    item.rule_id or "",
                    item.code,
                    item.message,
                ),
            )
        )
    else:
        verified = []

    if not findings:
        rule_counts = Counter(item.approval.rule_id for item in verified)
        duplicate_rule_ids = sorted(
            rule_id for rule_id, count in rule_counts.items() if count > 1
        )
        if duplicate_rule_ids:
            findings = (
                ActivationFinding(
                    artifact_path=None,
                    rule_id=duplicate_rule_ids[0],
                    code="DUPLICATE_ACTIVE_RULE_ID",
                    message="more than one approval activates the same rule_id",
                ),
            )

    if findings:
        report = _blocked_report(approval_files, findings)
        _publish_create_only(((report_destination, activation_report_bytes(report)),))
        return report

    ordered = tuple(sorted(verified, key=_verified_sort_key))
    manifest = ActiveRuleManifest(rules=tuple(_entry(root, item) for item in ordered))
    manifest_bytes = active_rule_manifest_bytes(manifest)
    load_active_rule_manifest_bytes(manifest_bytes)
    manifest_sha256 = _sha256_bytes(manifest_bytes)
    report = ActivationReport(
        status="ACTIVATED",
        approval_count=len(approval_files),
        activated_rule_count=len(ordered),
        approval_files=approval_files,
        findings=(),
        active_manifest_sha256=manifest_sha256,
    )
    _publish_create_only(
        (
            (manifest_destination, manifest_bytes),
            (report_destination, activation_report_bytes(report)),
        )
    )
    return report
