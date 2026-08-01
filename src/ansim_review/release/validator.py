"""Offline, reproducibility, and integrity validation for release workspaces."""

from __future__ import annotations

import ast
import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from ansim_review.canonical_json import sha256_json
from ansim_review.network_guard import offline_guard_context
from ansim_review.offline_policy import APPLICATION_OFFLINE_GUARD, POLICY_VERSION
from ansim_review.packaging.codex_bundle import (
    CodexBundleReport,
    build_codex_workspace,
)
from ansim_review.packaging.web_bundle import WebBundleReport, build_web_runtime_zip
from ansim_review.release.manifest import validate_release_manifest
from ansim_review.release.offline_boundary import (
    source_policy_checks,
    validate_manifest_path_containment,
)


@dataclass(frozen=True, slots=True)
class ReleaseValidationReport:
    """Deterministic result of the automated release validation gate."""

    candidate_hash: str
    manifest_hash: str
    checks: tuple[str, ...]
    release_status: str
    offline_assurance: str = APPLICATION_OFFLINE_GUARD
    offline_policy_version: int = POLICY_VERSION


def release_validation_document(report: ReleaseValidationReport) -> dict[str, object]:
    """Return the canonical release-validation report document."""
    return {
        "format": "ansim/release-validation",
        "version": 1,
        "candidate_hash": report.candidate_hash,
        "manifest_hash": report.manifest_hash,
        "checks": list(report.checks),
        "release_status": report.release_status,
        "offline_assurance": report.offline_assurance,
        "offline_policy_version": report.offline_policy_version,
        "cryptographic_network_isolation_verified": False,
    }


@contextmanager
def blocked_network() -> Iterator[None]:
    """Apply the production loopback-only guard during release validation."""
    with offline_guard_context():
        yield


def _source_checks(workspace: Path) -> list[str]:
    return list(source_policy_checks(workspace))


def _assert_no_top_level_effects(tree: ast.Module, path: Path) -> None:
    for node in tree.body:
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Assign,
                ast.AnnAssign,
                ast.Pass,
            ),
        ):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.If):
            is_main_guard = (
                isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
            )
            if is_main_guard:
                continue
        raise ValueError(f"executable top-level effect in runtime package: {path}")


def _artifact_checks(workspace: Path) -> list[str]:
    checks: list[str] = []
    agent_files = sorted((workspace / "skills").rglob("*.md"))
    checks.append(f"skills:{len(agent_files)}")
    for skill_file in agent_files:
        _assert_no_top_level_effects(
            ast.parse(skill_file.read_text(encoding="utf-8"), filename=str(skill_file)),
            skill_file,
        )
    evidence = workspace / "evidence" / "ansim-evidence.sqlite"
    if not evidence.is_file():
        raise FileNotFoundError(evidence)
    checks.append(f"evidence_db:{evidence.stat().st_size}")
    return checks


def _manifest_checks(workspace: Path) -> tuple[str, list[str]]:
    manifest_path = workspace / "releases" / "ansim-v1.0" / "manifest.json"
    validate_manifest_path_containment(manifest_path)
    manifest = validate_release_manifest(manifest_path)
    manifest_hash = sha256_json(manifest)
    checks = [f"release_manifest:{manifest_hash}"]
    for member in validate_manifest_path_containment(manifest_path):
        checks.append(
            "release_manifest_member:"
            f"{member.relative_to(manifest_path.parent).as_posix()}"
        )
    return manifest_hash, checks


def _build_reproducible_artifacts(
    workspace: Path,
    output_dir: Path,
) -> tuple[CodexBundleReport, CodexBundleReport, WebBundleReport, WebBundleReport]:
    codex_one = build_codex_workspace(workspace, output_dir / "codex-1")
    codex_two = build_codex_workspace(workspace, output_dir / "codex-2")
    web_one = build_web_runtime_zip(workspace, output_dir / "web-1.zip")
    web_two = build_web_runtime_zip(workspace, output_dir / "web-2.zip")
    return codex_one, codex_two, web_one, web_two


def _reproducibility_checks(
    workspace: Path,
    output_dir: Path,
) -> list[str]:
    codex_one, codex_two, web_one, web_two = _build_reproducible_artifacts(
        workspace,
        output_dir,
    )
    if codex_one.source_tree_hash != codex_two.source_tree_hash:
        raise ValueError("Codex workspace is not reproducible")
    if codex_one.manifest_hash != codex_two.manifest_hash:
        raise ValueError("Codex manifest is not reproducible")
    if web_one.zip_sha256 != web_two.zip_sha256:
        raise ValueError("web runtime ZIP is not reproducible")
    if web_one.manifest_hash != web_two.manifest_hash:
        raise ValueError("web runtime manifest is not reproducible")
    return [
        f"codex_source_tree:{codex_one.source_tree_hash}",
        f"codex_manifest:{codex_one.manifest_hash}",
        f"web_zip:{web_one.zip_sha256}",
        f"web_manifest:{web_one.manifest_hash}",
    ]


def _evidence_snapshot_hash(workspace: Path) -> str:
    database = workspace / "evidence" / "ansim-evidence.sqlite"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT value FROM snapshot_meta WHERE key = 'database_snapshot_hash'"
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT value FROM snapshot_meta WHERE key = 'snapshot_hash'"
            ).fetchone()
    if row is None or not isinstance(row[0], str):
        raise ValueError("database snapshot hash is missing")
    return row[0]


def _cross_runtime_checks(workspace: Path, web_zip: Path) -> list[str]:
    local_hash = _evidence_snapshot_hash(workspace)
    try:
        with ZipFile(web_zip) as archive:
            manifest_name = "runtime-manifest.json"
            if manifest_name not in archive.namelist():
                raise ValueError("web bundle runtime manifest is missing")
            web_manifest_bytes = archive.read(manifest_name)
    except BadZipFile as error:
        raise ValueError("web bundle is not a valid ZIP archive") from error
    web_manifest_hash = hashlib.sha256(web_manifest_bytes).hexdigest()
    return [
        f"evidence_snapshot:{local_hash}",
        f"web_runtime_manifest_bytes:{web_manifest_hash}",
    ]


def validate_release_workspace(
    workspace: Path,
    output_dir: Path,
    *,
    acceptance_ready: bool = False,
) -> ReleaseValidationReport:
    """Run the automated no-network, integrity, and reproducibility gate."""
    checks: list[str] = []
    checks.extend(_source_checks(workspace))
    with blocked_network():
        checks.extend(_artifact_checks(workspace))
        manifest_hash, manifest_checks = _manifest_checks(workspace)
        checks.extend(manifest_checks)
        checks.extend(_reproducibility_checks(workspace, output_dir))
        checks.extend(_cross_runtime_checks(workspace, output_dir / "web-1.zip"))
    candidate_hash = sha256_json(
        {
            "manifest_hash": manifest_hash,
            "checks": checks,
            "offline_assurance": APPLICATION_OFFLINE_GUARD,
            "offline_policy_version": POLICY_VERSION,
        }
    )
    return ReleaseValidationReport(
        candidate_hash=candidate_hash,
        manifest_hash=manifest_hash,
        checks=tuple(checks),
        release_status=("RELEASE_READY" if acceptance_ready else "RELEASE_BLOCKED"),
        offline_assurance=APPLICATION_OFFLINE_GUARD,
        offline_policy_version=POLICY_VERSION,
    )
