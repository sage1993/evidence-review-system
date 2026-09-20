"""Lossless OpenDataLoader warning extraction and stable warning identity."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from evidence_review.canonical_json import dump_bytes
from evidence_review.parser_reproducibility.contract import JsonValue
from evidence_review.parser_reproducibility.normalization import (
    normalize_run_root_references,
)
from evidence_review.parser_reproducibility.opendataloader import (
    JsonObject,
    OpenDataLoaderArtifact,
)

type WarningCode = Literal[
    "PARSER_WARNING_TEXT_EXTRACTION",
    "PARSER_WARNING_TABLE_EXTRACTION",
    "PARSER_WARNING_IMAGE_EXTRACTION",
    "PARSER_WARNING_LAYOUT",
    "PARSER_WARNING_PAGE",
    "PARSER_WARNING_UNKNOWN",
]

WARNING_CODE_MAP: dict[str, WarningCode] = {
    "TEXT_EXTRACTION_FAILED": "PARSER_WARNING_TEXT_EXTRACTION",
    "TABLE_EXTRACTION_FAILED": "PARSER_WARNING_TABLE_EXTRACTION",
    "IMAGE_EXTRACTION_FAILED": "PARSER_WARNING_IMAGE_EXTRACTION",
    "LAYOUT_WARNING": "PARSER_WARNING_LAYOUT",
    "PAGE_WARNING": "PARSER_WARNING_PAGE",
}
_PAGE_PATTERNS = (
    re.compile(r"\bpage (?P<page>[1-9][0-9]*)\b", re.IGNORECASE),
    re.compile(r"\bpage=(?P<page>[1-9][0-9]*)\b", re.IGNORECASE),
    re.compile(r"\[page (?P<page>[1-9][0-9]*)\]", re.IGNORECASE),
)
_CODE_PREFIX = re.compile(
    r"^(?:\[(?P<bracket>[A-Z_]+)\]|(?P<plain>[A-Z_]+):)\s*(?P<message>.*)$"
)
_LOG_LEVEL = r"WARN|WARNING|ERROR|SEVERE|FATAL|INFO|DEBUG|TRACE|경고|심각"
_PYTHON_LOG_PREFIX = re.compile(
    rf"^\d{{4}}-\d{{2}}-\d{{2}}[ T]\d{{2}}:\d{{2}}:\d{{2}}(?:[,.]\d{{1,9}})?"
    rf"\s+-\s+(?P<severity>{_LOG_LEVEL})\s+-\s+(?P<message>.*)$",
    re.IGNORECASE,
)
_SEVERITY_PREFIX = re.compile(
    rf"^(?:\[(?P<bracket>{_LOG_LEVEL})\]|(?P<plain>{_LOG_LEVEL}))"
    r"\s*:\s*(?P<message>.*)$",
    re.IGNORECASE,
)
_WARNING_SEVERITY_CANONICAL = {
    "WARN": "WARNING",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "SEVERE": "ERROR",
    "FATAL": "ERROR",
    "경고": "WARNING",
    "심각": "ERROR",
}
_RUN_TOKEN_PATH = re.compile(r"<RUN_ROOT>(?P<suffix>(?:[\\/][^\s)\]}>;,]+)*)")


@dataclass(frozen=True, slots=True)
class WarningContext:
    source_sha256: str
    document_id: str
    revision_id: str
    parser_kind: str
    parser_version: str
    configuration_sha256: str
    run_id: str
    run_root: Path
    parser_page_count: int


@dataclass(frozen=True, slots=True)
class ParserWarning:
    warning_id: str
    severity: Literal["WARNING"]
    code: WarningCode
    document_id: str
    revision_id: str
    source_sha256: str
    parser_kind: str
    parser_version: str
    configuration_sha256: str
    page_number: int | None
    raw_source_relative_path: str
    raw_location: str
    raw_message: str
    normalized_message_sha256: str
    run_id: str


@dataclass(frozen=True, slots=True)
class ParserWarningReport:
    format: Literal["evidence-review/parser-warning-report"]
    version: Literal[1]
    source_sha256: str
    parser_version: str
    configuration_sha256: str
    warnings: tuple[ParserWarning, ...]


def _page_from_message(message: str, page_count: int) -> int | None:
    for pattern in _PAGE_PATTERNS:
        match = pattern.search(message)
        if match is None:
            continue
        page = int(match.group("page"))
        return page if page <= page_count else None
    return None


def _normalized_message(message: str, run_root: Path) -> str:
    normalized = message.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalize_run_root_references(normalized, run_root)
    return _RUN_TOKEN_PATH.sub(
        lambda match: "<RUN_ROOT>" + match.group("suffix").replace("\\", "/"),
        normalized,
    )


def _warning_code(value: object) -> WarningCode:
    if isinstance(value, str):
        return WARNING_CODE_MAP.get(value, "PARSER_WARNING_UNKNOWN")
    return "PARSER_WARNING_UNKNOWN"


def _page_from_record(
    record: JsonObject,
    message: str,
    context: WarningContext,
) -> int | None:
    value = record.get("page_number", record.get("page number"))
    if isinstance(value, int) and not isinstance(value, bool):
        if 1 <= value <= context.parser_page_count:
            return value
        return None
    return _page_from_message(message, context.parser_page_count)


def _new_warning(
    *,
    code: WarningCode,
    message: str,
    identity_message: str | None = None,
    page_number: int | None,
    raw_source_relative_path: str,
    raw_location: str,
    context: WarningContext,
) -> ParserWarning:
    normalized = _normalized_message(
        message if identity_message is None else identity_message,
        context.run_root,
    )
    normalized_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()
    provisional = ParserWarning(
        warning_id="",
        severity="WARNING",
        code=code,
        document_id=context.document_id,
        revision_id=context.revision_id,
        source_sha256=context.source_sha256,
        parser_kind=context.parser_kind,
        parser_version=context.parser_version,
        configuration_sha256=context.configuration_sha256,
        page_number=page_number,
        raw_source_relative_path=raw_source_relative_path,
        raw_location=raw_location,
        raw_message=message,
        normalized_message_sha256=normalized_hash,
        run_id=context.run_id,
    )
    return replace(provisional, warning_id=warning_id_for(provisional))


def warning_id_for(warning: ParserWarning) -> str:
    """Return a stable warning identity independent of run-local locations."""

    authority = {
        "source_sha256": warning.source_sha256,
        "parser_kind": warning.parser_kind,
        "parser_version": warning.parser_version,
        "configuration_sha256": warning.configuration_sha256,
        "page_number": warning.page_number,
        "code": warning.code,
        "normalized_message_sha256": warning.normalized_message_sha256,
    }
    digest = hashlib.sha256(dump_bytes(authority)).hexdigest()[:24].upper()
    return f"PWRN-{digest}"


def _warning_lists(
    value: JsonValue,
    path: str = "$",
) -> tuple[tuple[str, list[JsonValue]], ...]:
    found: list[tuple[str, list[JsonValue]]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "warnings":
                if not isinstance(child, list):
                    raise ValueError(f"{child_path} must be an array")
                found.append((child_path, child))
            else:
                found.extend(_warning_lists(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_warning_lists(child, f"{path}[{index}]"))
    return tuple(found)


def _warnings_from_json(
    artifact: OpenDataLoaderArtifact,
    context: WarningContext,
) -> list[ParserWarning]:
    warnings: list[ParserWarning] = []
    for path, records in _warning_lists(artifact.raw_payload):
        for index, value in enumerate(records):
            location = f"{path}[{index}]"
            if isinstance(value, str):
                warnings.append(
                    _new_warning(
                        code="PARSER_WARNING_UNKNOWN",
                        message=value,
                        page_number=_page_from_message(
                            value,
                            context.parser_page_count,
                        ),
                        raw_source_relative_path="document.json",
                        raw_location=location,
                        context=context,
                    )
                )
                continue
            if not isinstance(value, dict):
                raise ValueError(f"{location} must be a string or object")
            message_value = value.get("message")
            if not isinstance(message_value, str) or not message_value:
                raise ValueError(
                    f"{location}.message must be a non-empty string"
                )
            warnings.append(
                _new_warning(
                    code=_warning_code(value.get("code")),
                    message=message_value,
                    page_number=_page_from_record(
                        value,
                        message_value,
                        context,
                    ),
                    raw_source_relative_path="document.json",
                    raw_location=location,
                    context=context,
                )
            )
    return warnings


def _warnings_from_log(
    log_text: str,
    context: WarningContext,
) -> list[ParserWarning]:
    warnings: list[ParserWarning] = []
    for line_number, raw_line in enumerate(log_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        python_match = _PYTHON_LOG_PREFIX.match(raw_line)
        severity_match = (
            None if python_match is not None else _SEVERITY_PREFIX.match(raw_line)
        )
        if python_match is not None:
            raw_severity = python_match.group("severity")
            message = python_match.group("message")
        elif severity_match is not None:
            raw_severity = severity_match.group("plain") or severity_match.group("bracket")
            message = severity_match.group("message")
        else:
            continue
        if raw_severity is None:
            continue
        canonical_severity = _WARNING_SEVERITY_CANONICAL.get(raw_severity.upper())
        if canonical_severity is None:
            continue
        code_match = _CODE_PREFIX.match(message)
        raw_code = (
            None
            if code_match is None
            else (code_match.group("bracket") or code_match.group("plain"))
        )
        warnings.append(
            _new_warning(
                code=_warning_code(raw_code),
                message=raw_line,
                identity_message=(
                    f"{canonical_severity}: {message}"
                ),
                page_number=_page_from_message(
                    message,
                    context.parser_page_count,
                ),
                raw_source_relative_path="parser.log",
                raw_location=f"line:{line_number}",
                context=context,
            )
        )
    return warnings


def warning_sort_key(warning: ParserWarning) -> tuple[object, ...]:
    return (
        -1 if warning.page_number is None else warning.page_number,
        warning.code,
        warning.normalized_message_sha256,
        warning.raw_source_relative_path,
        warning.raw_location,
        warning.warning_id,
    )


def extract_opendataloader_warnings(
    artifact: OpenDataLoaderArtifact,
    log_text: str | None,
    context: WarningContext,
) -> tuple[ParserWarning, ...]:
    """Extract explicit parser warnings and preserve every raw message."""

    collected = _warnings_from_json(artifact, context)
    if log_text is not None:
        collected.extend(_warnings_from_log(log_text, context))
    by_id: dict[str, ParserWarning] = {}
    for warning in collected:
        by_id.setdefault(warning.warning_id, warning)
    return tuple(sorted(by_id.values(), key=warning_sort_key))


def build_warning_report(
    warnings: tuple[ParserWarning, ...],
    context: WarningContext,
) -> ParserWarningReport:
    return ParserWarningReport(
        format="evidence-review/parser-warning-report",
        version=1,
        source_sha256=context.source_sha256,
        parser_version=context.parser_version,
        configuration_sha256=context.configuration_sha256,
        warnings=tuple(sorted(warnings, key=warning_sort_key)),
    )
