"""Release workspace documentation gate integration tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review.release import validator

from ._fixtures import write_valid_finalized_run


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _prepare(root: Path, *, broken: bool = False, warning: bool = False) -> str:
    target = "docs/missing.md" if broken else "docs/OFFLINE_EXECUTION.md"
    external = "\nRaw http://example.com/path.\n" if warning else ""
    _write(root / "README.md", f"# Project\n\n[Offline]({target}){external}")
    _write(root / "AGENTS.md", "# Agents\n")
    _write(root / "docs" / "OFFLINE_EXECUTION.md", "# Offline Execution\n")
    (root / "documentation-integrity.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/documentation-integrity-config",
                "version": 1,
                "current_roots": [
                    "README.md",
                    "AGENTS.md",
                    "docs/OFFLINE_EXECUTION.md",
                ],
                "historical_roots": [],
                "current_overrides": [],
                "historical_overrides": [],
                "generated_documents": [],
            }
        ),
        encoding="utf-8",
    )
    return write_valid_finalized_run(root)


def _isolate_non_documentation_checks(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        validator,
        "_forbidden_capabilities",
        lambda path: [],
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        validator,
        "_sqlite_checks",
        lambda path: {"status": "PASS"},
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        validator,
        "_manifest_checks",
        lambda path: {"status": "PASS", "checked": 0, "errors": []},
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        validator,
        "_governed_rule_checks",
        lambda path: {"status": "ABSTAIN"},
    )

    def build_zip(root: Path, output: Path) -> str:
        output.write_bytes(b"deterministic")
        return hashlib.sha256(b"deterministic").hexdigest()

    monkeypatch.setattr(  # type: ignore[attr-defined]
        validator,
        "build_web_runtime_zip",
        build_zip,
    )


def test_documentation_error_fails_workspace(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    run_id = _prepare(tmp_path, broken=True)
    _isolate_non_documentation_checks(monkeypatch)

    report = validator.validate_release_workspace(tmp_path, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "DOCUMENTATION_INTEGRITY_FAILED" in report["errors"]
    assert report["documentation"]["status"] == "FAIL"  # type: ignore[index]


def test_warning_only_documentation_keeps_workspace_pass(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    run_id = _prepare(tmp_path, warning=True)
    _isolate_non_documentation_checks(monkeypatch)

    report = validator.validate_release_workspace(tmp_path, run_id=run_id)

    assert report["status"] == "PASS"
    assert report["documentation"]["status"] == "PASS"  # type: ignore[index]
    assert report["documentation"]["warning_count"] == 1  # type: ignore[index]


def test_missing_authority_config_is_stable_documentation_failure(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    _write(tmp_path / "README.md", "# Project\n")
    run_id = write_valid_finalized_run(tmp_path)
    _isolate_non_documentation_checks(monkeypatch)

    report = validator.validate_release_workspace(tmp_path, run_id=run_id)

    assert report["status"] == "FAIL"
    assert report["documentation"]["status"] == "FAIL"  # type: ignore[index]
    assert "DOCUMENTATION_INTEGRITY_FAILED" in report["errors"]
