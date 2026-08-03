"""Strict configuration and canonical report contracts."""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, TypeAlias, cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.formats import (
    DOCUMENTATION_INTEGRITY_CONFIG_FORMAT,
    DOCUMENTATION_INTEGRITY_REPORT_FORMAT,
)

DocumentClassification: TypeAlias = Literal["CURRENT", "HISTORICAL"]
FindingSeverity: TypeAlias = Literal["ERROR", "WARNING"]
ReportStatus: TypeAlias = Literal["PASS", "FAIL"]

_CONFIG_KEYS = frozenset(
    {
        "format",
        "version",
        "current_roots",
        "historical_roots",
        "current_overrides",
        "historical_overrides",
        "generated_documents",
    }
)
_GENERATED_KEYS = frozenset({"id", "generator", "virtual_path", "classification"})
_IDENTIFIER_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_GENERATOR_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+:[A-Za-z_][A-Za-z0-9_]*$"
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class GeneratedDocumentConfig:
    id: str
    generator: str
    virtual_path: str
    classification: DocumentClassification


@dataclass(frozen=True, slots=True)
class DocumentationIntegrityConfig:
    format: Literal["evidence-review/documentation-integrity-config"]
    version: Literal[1]
    current_roots: tuple[str, ...]
    historical_roots: tuple[str, ...]
    current_overrides: tuple[str, ...]
    historical_overrides: tuple[str, ...]
    generated_documents: tuple[GeneratedDocumentConfig, ...]


@dataclass(frozen=True, slots=True)
class DocumentationFinding:
    severity: FindingSeverity
    code: str
    document_path: str
    line: int
    column: int
    target: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in ("ERROR", "WARNING"):
            raise ValueError("finding severity must be ERROR or WARNING")
        if not isinstance(self.code, str) or _CODE_RE.fullmatch(self.code) is None:
            raise ValueError("finding code must use uppercase snake case")
        _validate_repository_path(self.document_path)
        if type(self.line) is not int or self.line < 1:
            raise ValueError("finding line must be a positive integer")
        if type(self.column) is not int or self.column < 1:
            raise ValueError("finding column must be a positive integer")
        if not isinstance(self.target, str):
            raise ValueError("finding target must be a string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("finding message must be non-empty")


@dataclass(frozen=True, slots=True, init=False)
class DocumentationIntegrityReport:
    status: ReportStatus
    document_count: int
    current_document_count: int
    historical_document_count: int
    generated_document_count: int
    error_count: int
    warning_count: int
    findings: tuple[DocumentationFinding, ...]

    def __init__(
        self,
        *,
        current_documents: Sequence[str],
        historical_documents: Sequence[str],
        generated_documents: Sequence[str],
        findings: Sequence[DocumentationFinding],
    ) -> None:
        current = _normalize_document_paths(current_documents)
        historical = _normalize_document_paths(historical_documents)
        generated = _normalize_document_paths(generated_documents)
        if (set(current) & set(historical)) or (set(current) & set(generated)) or (
            set(historical) & set(generated)
        ):
            raise ValueError("document path appears in more than one report class")
        normalized_findings = tuple(sorted(set(findings), key=finding_sort_key))
        errors = sum(finding.severity == "ERROR" for finding in normalized_findings)
        warnings = sum(finding.severity == "WARNING" for finding in normalized_findings)
        object.__setattr__(self, "status", "FAIL" if errors else "PASS")
        object.__setattr__(
            self,
            "document_count",
            len(current) + len(historical) + len(generated),
        )
        object.__setattr__(self, "current_document_count", len(current))
        object.__setattr__(self, "historical_document_count", len(historical))
        object.__setattr__(self, "generated_document_count", len(generated))
        object.__setattr__(self, "error_count", errors)
        object.__setattr__(self, "warning_count", warnings)
        object.__setattr__(self, "findings", normalized_findings)


def _duplicate_rejecting_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_exact_keys(
    value: dict[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    unknown = sorted(set(value) - expected)
    if unknown:
        raise ValueError(f"unknown {label} field: {unknown[0]}")
    missing = sorted(expected - set(value))
    if missing:
        raise ValueError(f"missing {label} field: {missing[0]}")


def _validate_repository_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("repository path must be a non-empty string")
    if "\\" in value:
        raise ValueError("repository path must use POSIX separators")
    if value.startswith("/") or _WINDOWS_DRIVE_RE.match(value):
        raise ValueError("repository path must be relative")
    components = value.split("/")
    if any(component in ("", ".", "..") for component in components):
        raise ValueError("repository path contains an invalid component")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value:
        raise ValueError("repository path is not canonical")
    return value


def _decode_path_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    result = tuple(_validate_repository_path(item) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"duplicate path in {field}")
    return result


def _decode_generated(value: object) -> tuple[GeneratedDocumentConfig, ...]:
    if not isinstance(value, list):
        raise ValueError("generated_documents must be an array")
    documents: list[GeneratedDocumentConfig] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("generated document must be an object")
        item = cast(dict[str, object], raw)
        _require_exact_keys(item, _GENERATED_KEYS, "generated document")
        document_id = item["id"]
        if (
            not isinstance(document_id, str)
            or _IDENTIFIER_RE.fullmatch(document_id) is None
        ):
            raise ValueError("generated document id must use uppercase snake case")
        if document_id in seen_ids:
            raise ValueError(f"duplicate generated document id: {document_id}")
        seen_ids.add(document_id)
        generator = item["generator"]
        if not isinstance(generator, str) or _GENERATOR_RE.fullmatch(generator) is None:
            raise ValueError("invalid generator reference")
        virtual_path = _validate_repository_path(item["virtual_path"])
        if virtual_path in seen_paths:
            raise ValueError(f"duplicate generated document path: {virtual_path}")
        seen_paths.add(virtual_path)
        classification = item["classification"]
        if classification not in ("CURRENT", "HISTORICAL"):
            raise ValueError("invalid generated document classification")
        documents.append(
            GeneratedDocumentConfig(
                id=document_id,
                generator=generator,
                virtual_path=virtual_path,
                classification=classification,
            )
        )
    return tuple(documents)


def decode_config_bytes(data: bytes) -> DocumentationIntegrityConfig:
    """Decode strict v1 documentation-integrity configuration bytes."""
    try:
        raw = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_duplicate_rejecting_object,
        )
    except UnicodeDecodeError as error:
        raise ValueError("configuration must be UTF-8") from error
    if not isinstance(raw, dict):
        raise ValueError("configuration must be a JSON object")
    payload = cast(dict[str, object], raw)
    _require_exact_keys(payload, _CONFIG_KEYS, "configuration")
    if payload["format"] != DOCUMENTATION_INTEGRITY_CONFIG_FORMAT:
        raise ValueError("unsupported configuration format")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("unsupported configuration version")
    return DocumentationIntegrityConfig(
        format=DOCUMENTATION_INTEGRITY_CONFIG_FORMAT,
        version=1,
        current_roots=_decode_path_list(payload["current_roots"], "current_roots"),
        historical_roots=_decode_path_list(
            payload["historical_roots"],
            "historical_roots",
        ),
        current_overrides=_decode_path_list(
            payload["current_overrides"],
            "current_overrides",
        ),
        historical_overrides=_decode_path_list(
            payload["historical_overrides"],
            "historical_overrides",
        ),
        generated_documents=_decode_generated(payload["generated_documents"]),
    )


def finding_sort_key(finding: DocumentationFinding) -> tuple[object, ...]:
    """Return the stable ordering key for one finding."""
    return (
        0 if finding.severity == "ERROR" else 1,
        finding.document_path.encode("utf-8"),
        finding.line,
        finding.column,
        finding.code,
        finding.target,
        finding.message,
    )


def _normalize_document_paths(paths: Sequence[str]) -> tuple[str, ...]:
    validated = tuple(_validate_repository_path(path) for path in paths)
    return tuple(sorted(set(validated), key=lambda item: item.encode("utf-8")))


def report_document(report: DocumentationIntegrityReport) -> dict[str, object]:
    """Return the strict canonical report document."""
    return {
        "format": DOCUMENTATION_INTEGRITY_REPORT_FORMAT,
        "version": 1,
        "status": report.status,
        "document_count": report.document_count,
        "current_document_count": report.current_document_count,
        "historical_document_count": report.historical_document_count,
        "generated_document_count": report.generated_document_count,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "findings": [
            {
                "severity": finding.severity,
                "code": finding.code,
                "document_path": finding.document_path,
                "line": finding.line,
                "column": finding.column,
                "target": finding.target,
                "message": finding.message,
            }
            for finding in report.findings
        ],
    }


def report_bytes(report: DocumentationIntegrityReport) -> bytes:
    """Serialize a report to byte-stable canonical JSON."""
    return dump_bytes(report_document(report))
