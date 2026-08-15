"""Two-pass documentation integrity orchestration tests."""

from __future__ import annotations

import json
from pathlib import Path

from evidence_review.documentation_integrity.contract import report_bytes
from evidence_review.documentation_integrity.validator import validate_documentation


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _config(root: Path, *, generator: str | None = None) -> Path:
    generated_documents: list[dict[str, object]] = []
    if generator is not None:
        generated_documents.append(
            {
                "id": "GENERATED_TEST",
                "generator": generator,
                "virtual_path": "generated/PROJECT_INSTRUCTIONS.md",
                "classification": "CURRENT",
            }
        )
    payload = {
        "format": "evidence-review/documentation-integrity-config",
        "version": 1,
        "current_roots": ["README.md", "docs"],
        "historical_roots": ["docs/acceptance"],
        "current_overrides": [],
        "historical_overrides": [],
        "generated_documents": generated_documents,
    }
    path = root / "documentation-integrity.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _repository(root: Path, *, broken: bool = False) -> None:
    target = "docs/missing.md" if broken else "docs/guide.md#guide"
    _write(root / "README.md", f"# Project\n\n[Guide]({target})\n")
    _write(root / "docs" / "guide.md", "# Guide\n")
    _write(root / "docs" / "acceptance" / "old.md", "# Old record\n")


def test_warning_only_repository_passes_with_exact_counts(tmp_path: Path) -> None:
    _repository(tmp_path)
    config = _config(
        tmp_path,
        generator=(
            "evidence_review.packaging.project_instructions:"
            "render_project_instructions"
        ),
    )

    report = validate_documentation(tmp_path, config)

    assert report.status == "PASS"
    assert report.document_count == 4
    assert report.current_document_count == 2
    assert report.historical_document_count == 1
    assert report.generated_document_count == 1
    assert report.error_count == 0
    assert report.warning_count == 1
    assert [finding.code for finding in report.findings] == [
        "HISTORICAL_MARKER_MISSING"
    ]


def test_repository_error_fails_and_reports_are_byte_identical(tmp_path: Path) -> None:
    _repository(tmp_path, broken=True)
    config = _config(tmp_path)

    first = validate_documentation(tmp_path, config)
    second = validate_documentation(tmp_path, config)

    assert first.status == "FAIL"
    assert [finding.code for finding in first.findings] == [
        "INTERNAL_LINK_TARGET_MISSING",
        "HISTORICAL_MARKER_MISSING",
    ]
    assert report_bytes(first) == report_bytes(second)


def test_readable_invalid_config_becomes_canonical_finding(tmp_path: Path) -> None:
    _repository(tmp_path)
    config = tmp_path / "documentation-integrity.json"
    config.write_text(
        '{"format":"wrong","version":1}',
        encoding="utf-8",
    )

    report = validate_documentation(tmp_path, config)

    assert report.status == "FAIL"
    assert report.document_count == 0
    assert [finding.code for finding in report.findings] == ["CONFIG_INVALID"]
    assert "unsupported configuration format" not in report.findings[0].message


def test_generated_document_failure_becomes_canonical_finding(tmp_path: Path) -> None:
    _repository(tmp_path)
    config = _config(tmp_path, generator="missing.generator.module:render")

    report = validate_documentation(tmp_path, config)

    assert report.status == "FAIL"
    assert "GENERATED_DOCUMENT_IMPORT_FAILED" in {
        finding.code for finding in report.findings
    }
