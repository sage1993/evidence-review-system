"""Deterministic offline and reproducibility release audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.formats import RELEASE_VALIDATION_FORMAT
from ansim_review.documentation_integrity.contract import (
    DocumentationFinding,
    DocumentationIntegrityReport,
    report_document,
)
from ansim_review.documentation_integrity.validator import (
    DocumentationAuthorityError,
    validate_documentation,
)
from ansim_review.network_guard import offline_guard_context
from ansim_review.offline_policy import APPLICATION_OFFLINE_GUARD, POLICY_VERSION
from ansim_review.offline_scanner import scan_source_tree
from ansim_review.packaging.web_bundle import build_web_runtime_zip
from ansim_review.release.config import (
    DEFAULT_RELEASE_CONFIG,
    resolve_evidence_database,
)
from ansim_review.release.offline_boundary import resolve_manifest_member


@contextmanager
def blocked_network() -> Iterator[None]:
    """Apply the production loopback-only guard during release validation."""
    with offline_guard_context():
        yield


def _forbidden_capabilities(source_root: Path) -> list[dict[str, object]]:
    if not source_root.is_dir():
        return [
            {
                "path": ".",
                "line": 0,
                "kind": "SCAN_ERROR",
                "symbol": "SOURCE_ROOT_MISSING",
            }
        ]
    return [finding.document() for finding in scan_source_tree(source_root)]


def _sqlite_checks(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "FAIL", "error": "MISSING_EVIDENCE_DB"}
    try:
        connection = sqlite3.connect(path)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        connection.close()
    except sqlite3.DatabaseError as error:
        return {"status": "FAIL", "error": f"SQLITE_ERROR:{type(error).__name__}"}
    integrity_value = None if integrity is None else integrity[0]
    return {
        "status": "PASS" if integrity_value == "ok" and not foreign_keys else "FAIL",
        "integrity_check": integrity_value,
        "foreign_key_errors": len(foreign_keys),
    }


def _manifest_target(
    workspace_root: Path,
    manifest_path: Path,
    item: dict[str, object],
) -> tuple[str, Path] | None:
    path_value = item.get("path")
    relative_value = item.get("relative_path")
    if isinstance(path_value, str):
        return path_value, resolve_manifest_member(manifest_path.parent, path_value)
    if isinstance(relative_value, str):
        return relative_value, resolve_manifest_member(workspace_root, relative_value)
    return None


def _manifest_checks(workspace_root: Path) -> dict[str, object]:
    checked = 0
    errors: list[str] = []
    for path in sorted(workspace_root.rglob("*manifest.json")):
        manifest_label = path.relative_to(workspace_root).as_posix()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"INVALID_JSON:{manifest_label}")
            continue
        if not isinstance(payload, dict) or "files" not in payload:
            continue
        files = payload.get("files")
        if not isinstance(files, list):
            errors.append(f"INVALID_FILES:{manifest_label}")
            continue
        checked += 1
        for item in files:
            if not isinstance(item, dict) or not all(
                isinstance(key, str) for key in item
            ):
                errors.append(f"INVALID_ENTRY:{manifest_label}")
                continue
            expected = item.get("sha256")
            target_info = _manifest_target(workspace_root, path, item)
            if target_info is None or not isinstance(expected, str):
                errors.append(f"INVALID_ENTRY:{manifest_label}")
                continue
            relative, target = target_info
            if not target.is_file():
                errors.append(f"MISSING:{relative}")
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                errors.append(f"HASH_MISMATCH:{relative}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "checked": checked,
        "errors": errors,
    }


def _documentation_checks(workspace_root: Path) -> dict[str, object]:
    try:
        report = validate_documentation(
            workspace_root,
            workspace_root / "documentation-integrity.json",
        )
    except DocumentationAuthorityError:
        report = DocumentationIntegrityReport(
            current_documents=(),
            historical_documents=(),
            generated_documents=(),
            findings=(
                DocumentationFinding(
                    severity="ERROR",
                    code="DOCUMENTATION_AUTHORITY_UNAVAILABLE",
                    document_path="documentation-integrity.json",
                    line=1,
                    column=1,
                    target="documentation-integrity.json",
                    message=(
                        "Documentation integrity authority is missing or unreadable."
                    ),
                ),
            ),
        )
    return report_document(report)


def validate_release_workspace(
    workspace_root: Path,
    output_path: Path | None = None,
) -> dict[str, object]:
    """Run canonical release checks and optionally write their JSON report."""
    forbidden = _forbidden_capabilities(
        workspace_root / "src" / "ansim_review"
    )
    sqlite_result = _sqlite_checks(
        resolve_evidence_database(workspace_root, DEFAULT_RELEASE_CONFIG)
    )
    manifests = _manifest_checks(workspace_root)
    documentation = _documentation_checks(workspace_root)
    with tempfile.TemporaryDirectory(
        prefix="evidence-review-release-validation-"
    ) as temporary:
        first = Path(temporary) / "first.zip"
        second = Path(temporary) / "second.zip"
        with blocked_network():
            first_hash = build_web_runtime_zip(workspace_root, first)
            second_hash = build_web_runtime_zip(workspace_root, second)
        reproducible = (
            first_hash == second_hash and first.read_bytes() == second.read_bytes()
        )
    errors: list[str] = []
    if forbidden:
        errors.append("FORBIDDEN_RUNTIME_CAPABILITY")
    if sqlite_result["status"] != "PASS":
        errors.append("SQLITE_VALIDATION_FAILED")
    if manifests["status"] != "PASS":
        errors.append("MANIFEST_VALIDATION_FAILED")
    if documentation["status"] != "PASS":
        errors.append("DOCUMENTATION_INTEGRITY_FAILED")
    if not reproducible:
        errors.append("NON_REPRODUCIBLE_WEB_ZIP")
    report: dict[str, object] = {
        "format": RELEASE_VALIDATION_FORMAT,
        "version": 1,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "forbidden_imports": forbidden,
        "sqlite": sqlite_result,
        "manifests": manifests,
        "documentation": documentation,
        "web_zip": {
            "first_hash": first_hash,
            "second_hash": second_hash,
            "byte_identical": reproducible,
        },
        "offline_assurance": APPLICATION_OFFLINE_GUARD,
        "offline_policy_version": POLICY_VERSION,
        "cryptographic_network_isolation_verified": False,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(dump_bytes(report))
    return report
