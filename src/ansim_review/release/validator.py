"""Deterministic no-network and reproducibility release audit."""
from __future__ import annotations

import ast
import hashlib
import json
import socket
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from ansim_review.canonical_json import dump_bytes
from ansim_review.packaging.web_bundle import build_web_runtime_zip

_FORBIDDEN_IMPORTS = {
    "requests",
    "httpx",
    "aiohttp",
    "openai",
    "anthropic",
    "urllib.request",
}


@contextmanager
def blocked_network() -> Iterator[None]:
    """Make any accidental outbound socket use fail immediately."""

    class BlockedSocket(socket.socket):
        def connect(self, address: object) -> None:
            raise RuntimeError(f"network disabled: {address}")

        def connect_ex(self, address: object) -> int:
            raise RuntimeError(f"network disabled: {address}")

    def blocked_create_connection(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network disabled")

    with (
        patch.object(socket, "socket", BlockedSocket),
        patch.object(socket, "create_connection", blocked_create_connection),
    ):
        yield


def _forbidden_imports(source_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                line_number = node.lineno
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
                line_number = node.lineno
            else:
                continue
            for name in names:
                if any(
                    name == item or name.startswith(item + ".")
                    for item in _FORBIDDEN_IMPORTS
                ):
                    findings.append(
                        {
                            "path": path.relative_to(source_root).as_posix(),
                            "line": line_number,
                            "import": name,
                        }
                    )
    return findings


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


def _manifest_checks(workspace_root: Path) -> dict[str, object]:
    checked = 0
    errors: list[str] = []
    for path in sorted(workspace_root.rglob("*manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(
                f"INVALID_JSON:{path.relative_to(workspace_root).as_posix()}"
            )
            continue
        if not isinstance(payload, dict) or "files" not in payload:
            continue
        files = payload.get("files")
        if not isinstance(files, list):
            errors.append(
                f"INVALID_FILES:{path.relative_to(workspace_root).as_posix()}"
            )
            continue
        checked += 1
        for item in files:
            if not isinstance(item, dict):
                errors.append(
                    f"INVALID_ENTRY:{path.relative_to(workspace_root).as_posix()}"
                )
                continue
            relative = item.get("path")
            expected = item.get("sha256")
            if not isinstance(relative, str) or not isinstance(expected, str):
                errors.append(
                    f"INVALID_ENTRY:{path.relative_to(workspace_root).as_posix()}"
                )
                continue
            target = path.parent / relative
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


def validate_release_workspace(
    workspace_root: Path,
    output_path: Path | None = None,
) -> dict[str, object]:
    """Run canonical release checks and optionally write their JSON report."""
    forbidden = _forbidden_imports(workspace_root / "src" / "ansim_review")
    sqlite_result = _sqlite_checks(
        workspace_root / "evidence" / "ansim-evidence.sqlite"
    )
    manifests = _manifest_checks(workspace_root)
    with tempfile.TemporaryDirectory(
        prefix="ansim-release-validation-"
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
        errors.append("FORBIDDEN_NETWORK_IMPORT")
    if sqlite_result["status"] != "PASS":
        errors.append("SQLITE_VALIDATION_FAILED")
    if manifests["status"] != "PASS":
        errors.append("MANIFEST_VALIDATION_FAILED")
    if not reproducible:
        errors.append("NON_REPRODUCIBLE_WEB_ZIP")
    report = {
        "format": "ansim/release-validation",
        "version": 1,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "forbidden_imports": forbidden,
        "sqlite": sqlite_result,
        "manifests": manifests,
        "web_zip": {
            "first_hash": first_hash,
            "second_hash": second_hash,
            "byte_identical": reproducible,
        },
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(dump_bytes(report))
    return report
