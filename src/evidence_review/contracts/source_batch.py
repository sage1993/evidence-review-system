"""Strict contracts for arbitrary user-provided PDF source batches."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from evidence_review.contracts.attachments import AttachmentRole
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_string,
    reject_unknown,
    require_fields,
)

ParserKind = str
SourceBatchFormat = Literal["evidence-review/source-batch"]

_FORMATS: tuple[SourceBatchFormat, ...] = ("evidence-review/source-batch",)
_LEGACY_PARSER_KINDS = ("OPENDATALOADER_JSON",)
_PARSER_KIND = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_ATTACHMENT_ROLES: tuple[AttachmentRole, ...] = (
    "REFERENCE_DOCUMENT",
    "CASE_DRAWING",
    "CASE_TABLE",
    "SUPPORTING_IMAGE",
)


@dataclass(frozen=True, slots=True)
class ParserBinding:
    """One declared parser artifact associated with a source PDF."""

    kind: ParserKind
    artifact_path: str
    options: dict[str, object]


@dataclass(frozen=True, slots=True)
class SourceItem:
    """One immutable PDF source declaration."""

    source_path: str
    role: AttachmentRole
    document_id: str | None
    display_title: str | None
    parser: ParserBinding | None


@dataclass(frozen=True, slots=True)
class SourceBatch:
    """Canonical internal source-batch model; writers always emit version 2."""

    format: SourceBatchFormat
    version: Literal[2]
    sources: tuple[SourceItem, ...]


def _safe_relative_path(value: object, field: str) -> str:
    path = expect_string(value, field)
    parsed = PurePosixPath(path)
    first = parsed.parts[0] if parsed.parts else ""
    if (
        parsed.is_absolute()
        or not parsed.parts
        or ".." in parsed.parts
        or ":" in first
        or "\\" in path
    ):
        raise ValueError(f"{field} must be a safe relative path")
    return path


def _optional_display_title(value: object) -> str | None:
    if value is None:
        return None
    return expect_string(value, "display_title")


def _optional_document_id(value: object) -> str | None:
    if value is None:
        return None
    return validate_identifier(value, "document_id")


def _parser_kind(value: object, *, legacy: bool) -> str:
    if legacy:
        return expect_literal(value, "parser.kind", _LEGACY_PARSER_KINDS)
    kind = expect_string(value, "parser.kind")
    if _PARSER_KIND.fullmatch(kind) is None:
        raise ValueError("parser.kind must be a stable machine identifier")
    return kind


def _decode_parser(value: object, *, version: int) -> ParserBinding | None:
    if value is None:
        return None
    payload = expect_mapping(value, "parser")
    required = {"kind", "artifact_path"}
    if version == 2:
        required.add("options")
    require_fields(payload, required, "parser")
    reject_unknown(payload, required, "parser")
    options: dict[str, object] = {}
    if version == 2:
        options = dict(expect_mapping(payload.get("options"), "parser.options"))
    return ParserBinding(
        kind=_parser_kind(payload.get("kind"), legacy=version == 1),
        artifact_path=_safe_relative_path(
            payload.get("artifact_path"), "parser.artifact_path"
        ),
        options=options,
    )


def _decode_source(value: object, index: int, *, version: int) -> SourceItem:
    field = f"sources[{index}]"
    payload = expect_mapping(value, field)
    required = {
        "source_path",
        "role",
        "document_id",
        "display_title",
        "parser",
    }
    require_fields(payload, required, field)
    reject_unknown(payload, required, field)
    return SourceItem(
        source_path=_safe_relative_path(payload.get("source_path"), "source_path"),
        role=expect_literal(payload.get("role"), "role", _ATTACHMENT_ROLES),
        document_id=_optional_document_id(payload.get("document_id")),
        display_title=_optional_display_title(payload.get("display_title")),
        parser=_decode_parser(payload.get("parser"), version=version),
    )


def decode_source_batch(value: object) -> SourceBatch:
    """Decode source-batch versions 1 and 2 without filename inference."""
    payload = expect_mapping(value, "source_batch")
    required = {"format", "version", "sources"}
    require_fields(payload, required, "source_batch")
    reject_unknown(payload, required, "source_batch")
    try:
        format_value = expect_literal(payload.get("format"), "format", _FORMATS)
    except ValueError as error:
        raise ValueError("unsupported format") from error
    version = expect_int(payload.get("version"), "version")
    if version not in (1, 2):
        raise ValueError(f"unsupported version: {version}")
    sources = tuple(
        _decode_source(item, index, version=version)
        for index, item in enumerate(expect_sequence(payload.get("sources"), "sources"))
    )
    if not sources:
        raise ValueError("sources must not be empty")
    paths = tuple(source.source_path for source in sources)
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate source_path")
    return SourceBatch(
        format=format_value,
        version=2,
        sources=sources,
    )


def source_batch_document(batch: SourceBatch) -> dict[str, object]:
    """Return the canonical version 2 source-batch document."""
    return {
        "format": batch.format,
        "version": 2,
        "sources": [
            {
                "source_path": source.source_path,
                "role": source.role,
                "document_id": source.document_id,
                "display_title": source.display_title,
                "parser": (
                    None
                    if source.parser is None
                    else {
                        "kind": source.parser.kind,
                        "artifact_path": source.parser.artifact_path,
                        "options": dict(source.parser.options),
                    }
                ),
            }
            for source in batch.sources
        ],
    }
