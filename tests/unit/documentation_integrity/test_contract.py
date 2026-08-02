"""Strict contract tests for documentation integrity configuration and reports."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from ansim_review.documentation_integrity.contract import (
    DocumentationFinding,
    DocumentationIntegrityReport,
    decode_config_bytes,
    report_bytes,
    report_document,
)

VALID_CONFIG = b'''{
  "format":"evidence-review/documentation-integrity-config",
  "version":1,
  "current_roots":["README.md","docs"],
  "historical_roots":["docs/acceptance"],
  "current_overrides":[],
  "historical_overrides":[],
  "generated_documents":[]
}'''


def test_config_decodes_exact_valid_document() -> None:
    config = decode_config_bytes(VALID_CONFIG)
    assert config.current_roots == ("README.md", "docs")
    assert config.historical_roots == ("docs/acceptance",)
    assert config.generated_documents == ()


def test_config_rejects_duplicate_json_keys() -> None:
    invalid = VALID_CONFIG.replace(
        b'"version":1',
        b'"version":1,"version":1',
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_config_bytes(invalid)


def test_config_rejects_unknown_top_level_field() -> None:
    invalid = VALID_CONFIG.replace(b'"version":1,', b'"version":1,"extra":true,')
    with pytest.raises(ValueError, match="unknown configuration field"):
        decode_config_bytes(invalid)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (b'"version":1', b'"version":2', "unsupported configuration version"),
        (
            b'evidence-review/documentation-integrity-config',
            b'evidence-review/other',
            "unsupported configuration format",
        ),
        (b'"current_roots":["README.md","docs"]', b'"current_roots":["docs","docs"]', "duplicate path"),
    ],
)
def test_config_rejects_invalid_top_level_values(
    old: bytes,
    new: bytes,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        decode_config_bytes(VALID_CONFIG.replace(old, new))


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "C:/docs",
        "docs\\guide.md",
        "docs/../guide.md",
        "docs/./guide.md",
        "docs//guide.md",
        "docs/",
        "",
    ],
)
def test_config_rejects_noncanonical_repository_paths(path: str) -> None:
    payload = json.loads(VALID_CONFIG)
    payload["current_roots"] = [path]
    with pytest.raises(ValueError, match="repository path"):
        decode_config_bytes(json.dumps(payload).encode("utf-8"))


def test_config_rejects_invalid_generated_document_fields() -> None:
    payload = json.loads(VALID_CONFIG)
    payload["generated_documents"] = [
        {
            "id": "bad-id",
            "generator": "not a generator",
            "virtual_path": "generated/README.md",
            "classification": "CURRENT",
        }
    ]
    with pytest.raises(ValueError, match="generated document id"):
        decode_config_bytes(json.dumps(payload).encode("utf-8"))


def test_config_rejects_unknown_nested_field() -> None:
    payload = json.loads(VALID_CONFIG)
    payload["generated_documents"] = [
        {
            "id": "CODEX_VALIDATE",
            "generator": "ansim_review.packaging.codex_bundle:render_validation_document",
            "virtual_path": "codex-workspace/VALIDATE.md",
            "classification": "CURRENT",
            "extra": True,
        }
    ]
    with pytest.raises(ValueError, match="unknown generated document field"):
        decode_config_bytes(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "lowercase", "generated document id"),
        ("generator", "ansim_review.module", "generator reference"),
        ("generator", "ansim_review.module:not-valid", "generator reference"),
        ("classification", "ARCHIVED", "generated document classification"),
        ("virtual_path", "../outside.md", "repository path"),
    ],
)
def test_config_rejects_invalid_generated_document_value(
    field: str,
    value: str,
    message: str,
) -> None:
    payload = json.loads(VALID_CONFIG)
    generated = {
        "id": "CODEX_VALIDATE",
        "generator": "ansim_review.packaging.codex_bundle:render_validation_document",
        "virtual_path": "codex-workspace/VALIDATE.md",
        "classification": "CURRENT",
    }
    generated[field] = value
    payload["generated_documents"] = [generated]
    with pytest.raises(ValueError, match=message):
        decode_config_bytes(json.dumps(payload).encode("utf-8"))


def test_config_rejects_duplicate_generated_ids_and_paths() -> None:
    payload = json.loads(VALID_CONFIG)
    generated = {
        "id": "CODEX_VALIDATE",
        "generator": "ansim_review.packaging.codex_bundle:render_validation_document",
        "virtual_path": "codex-workspace/VALIDATE.md",
        "classification": "CURRENT",
    }
    payload["generated_documents"] = [generated, generated]
    with pytest.raises(ValueError, match="duplicate generated document id"):
        decode_config_bytes(json.dumps(payload).encode("utf-8"))

    second = dict(generated)
    second["id"] = "WEB_PROJECT_INSTRUCTIONS"
    payload["generated_documents"] = [generated, second]
    with pytest.raises(ValueError, match="duplicate generated document path"):
        decode_config_bytes(json.dumps(payload).encode("utf-8"))


def _finding(
    severity: str,
    code: str,
    path: str,
    line: int,
) -> DocumentationFinding:
    return DocumentationFinding(
        severity=severity,  # type: ignore[arg-type]
        code=code,
        document_path=path,
        line=line,
        column=1,
        target="target",
        message="stable message",
    )


def test_report_is_deduplicated_and_byte_stable() -> None:
    warning = _finding("WARNING", "WARNING_CODE", "docs/z.md", 9)
    error = _finding("ERROR", "ERROR_CODE", "README.md", 2)
    first = DocumentationIntegrityReport(
        current_documents=("README.md",),
        historical_documents=("docs/old.md",),
        generated_documents=("generated/VALIDATE.md",),
        findings=(warning, error, error),
    )
    second = DocumentationIntegrityReport(
        current_documents=("README.md",),
        historical_documents=("docs/old.md",),
        generated_documents=("generated/VALIDATE.md",),
        findings=(error, warning),
    )

    assert report_bytes(first) == report_bytes(second)
    payload = json.loads(report_bytes(first))
    assert payload["status"] == "FAIL"
    assert payload["document_count"] == 3
    assert payload["current_document_count"] == 1
    assert payload["historical_document_count"] == 1
    assert payload["generated_document_count"] == 1
    assert payload["error_count"] == 1
    assert payload["warning_count"] == 1
    assert [finding["severity"] for finding in payload["findings"]] == [
        "ERROR",
        "WARNING",
    ]
    assert report_document(first) == payload


def test_warning_only_report_passes_and_models_are_frozen() -> None:
    warning = _finding("WARNING", "WARNING_CODE", "README.md", 1)
    report = DocumentationIntegrityReport(
        current_documents=("README.md",),
        historical_documents=(),
        generated_documents=(),
        findings=(warning,),
    )
    assert report.status == "PASS"
    with pytest.raises(FrozenInstanceError):
        warning.message = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"severity": "INFO"},
        {"code": "not-valid"},
        {"document_path": "/absolute.md"},
        {"line": 0},
        {"column": 0},
        {"message": ""},
    ],
)
def test_finding_rejects_invalid_fields(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "severity": "ERROR",
        "code": "VALID_CODE",
        "document_path": "README.md",
        "line": 1,
        "column": 1,
        "target": "target",
        "message": "stable message",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        DocumentationFinding(**values)  # type: ignore[arg-type]
