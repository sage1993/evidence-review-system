"""Create-only command layer for documentation integrity validation."""
from __future__ import annotations

import sys
from pathlib import Path

from evidence_review.documentation_integrity.contract import report_bytes
from evidence_review.documentation_integrity.validator import (
    DocumentationAuthorityError,
    validate_documentation,
)


def _resolve_under_root(root: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("path must remain under repository root")
    return resolved


def run_documentation_validation(
    repository_root: Path,
    config_path: Path,
    output_path: Path,
) -> int:
    """Validate documentation and write a canonical report without overwrite."""
    try:
        root = repository_root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("repository root must be a directory")
        config = _resolve_under_root(root, config_path)
        output = _resolve_under_root(root, output_path)
        if output.exists():
            raise FileExistsError("documentation report output already exists")
        report = validate_documentation(root, config)
    except (DocumentationAuthorityError, FileExistsError, OSError, ValueError) as error:
        print(f"Documentation integrity error: {error}", file=sys.stderr)
        return 2

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(report_bytes(report))
    except (FileExistsError, OSError) as error:
        print(f"Documentation integrity error: {error}", file=sys.stderr)
        return 2

    relative_output = output.relative_to(root).as_posix()
    print(f"Documentation integrity: {report.status}")
    print(
        f"Documents: {report.document_count} "
        f"current={report.current_document_count} "
        f"historical={report.historical_document_count} "
        f"generated={report.generated_document_count}"
    )
    print(
        f"Findings: errors={report.error_count} warnings={report.warning_count}"
    )
    print(f"Report: {relative_output}")
    return 0 if report.status == "PASS" else 1
