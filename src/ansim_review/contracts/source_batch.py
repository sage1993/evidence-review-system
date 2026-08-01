"""Strict contracts for arbitrary user-provided PDF source batches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, cast

from ansim_review.contracts.attachments import AttachmentRole
from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_string,
    reject_unknown,
    require_fields,
)

ParserKind = Literal["OPENDATALOADER_JSON"]
SourceBatchFormat = Literal["evidence-review/source-batch"]

_FORMATS: tuple[SourceBatchFormat, ...] = ("evidence-review/source-batch",)
_PARSER_KINDS: tuple[ParserKind, ...] = ("OPENDATALOADER_JSON",)
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
    """Versioned manifest for one or more arbitrary PDF sources."""

    format: SourceBatchFormat
    version: Literal[1]
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


def _decode_parser(value: object) -> ParserBinding | None:
    if value is None:
        return None
    payload = expect_mapping(value, "parser")
    required = {"kind", "artifact_path"}
    require_fields(payload, required, "parser")
    reject_unknown(payload, required, "parser")
    return ParserBinding(
        kind=expect_literal(payload.get("kind"), "parser.kind", _PARSER_KINDS),
        artifact_path=_safe_relative_path(
            payload.get("artifact_path"), "parser.artifact_path"
        ),
    )


def _decode_source(value: object, index: int) -> SourceItem:
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
        parser=_decode_parser(payload.get("parser")),
    )


def decode_source_batch(value: object) -> SourceBatch:
    """Decode a generic PDF source batch without filename inference."""
    payload = expect_mapping(value, "source_batch")
    required = {"format", "version", "sources"}
    require_fields(payload, required, "source_batch")
    reject_unknown(payload, required, "source_batch")
    try:
        format_value = expect_literal(payload.get("format"), "format", _FORMATS)
    except ValueError as error:
        raise ValueError("unsupported format") from error
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    sources = tuple(
        _decode_source(item, index)
        for index, item in enumerate(expect_sequence(payload.get("sources"), "sources"))
    )
    if not sources:
        raise ValueError("sources must not be empty")
    paths = tuple(source.source_path for source in sources)
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate source_path")
    return SourceBatch(
        format=cast(SourceBatchFormat, format_value),
        version=1,
        sources=sources,
    )


def source_batch_document(batch: SourceBatch) -> dict[str, object]:
    """Return the explicit canonical source-batch document."""
    return {
        "format": batch.format,
        "version": batch.version,
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
                    }
                ),
            }
            for source in batch.sources
        ],
    }
