"""Prepare arbitrary PDF batches without sample filename assumptions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from ansim_review.contracts.attachments import AttachmentRole
from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.source_batch import ParserKind, SourceBatch, SourceItem
from ansim_review.parsing.source_manifest import sha256_file

SourcePreparationState = Literal["PENDING_PARSER_OUTPUT", "READY_FOR_INGESTION"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PreparedSource:
    """Resolved source bytes and optional parser artifact ready for ingestion."""

    source_path: Path
    parser_path: Path | None
    parser_kind: ParserKind | None
    role: AttachmentRole
    document_id: str
    revision_id: str
    source_sha256: str
    display_title: str
    state: SourcePreparationState


def derive_document_id(source_sha256: str, explicit: str | None) -> str:
    """Derive a stable document identity from explicit metadata or source bytes."""
    if not _SHA256.fullmatch(source_sha256):
        raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
    if explicit is not None:
        return validate_identifier(explicit, "document_id")
    return f"DOC-{source_sha256[:20].upper()}"


def _resolved_file(root: Path, relative: str, field: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"{field} escapes the source batch root")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def _prepare_item(root: Path, item: SourceItem) -> PreparedSource:
    source_path = _resolved_file(root, item.source_path, "source_path")
    source_sha256 = sha256_file(source_path)
    document_id = derive_document_id(source_sha256, item.document_id)
    parser_path: Path | None = None
    parser_kind: ParserKind | None = None
    state: SourcePreparationState = "PENDING_PARSER_OUTPUT"
    if item.parser is not None:
        parser_path = _resolved_file(root, item.parser.artifact_path, "parser.artifact_path")
        parser_kind = item.parser.kind
        state = "READY_FOR_INGESTION"
    return PreparedSource(
        source_path=source_path,
        parser_path=parser_path,
        parser_kind=parser_kind,
        role=item.role,
        document_id=document_id,
        revision_id=f"{document_id}-{source_sha256[:12]}",
        source_sha256=source_sha256,
        display_title=item.display_title or source_path.stem,
        state=state,
    )


def _merge_duplicate(first: PreparedSource, second: PreparedSource) -> PreparedSource:
    if first.document_id != second.document_id:
        raise ValueError("source hash maps to multiple document_ids")
    if first.role != second.role:
        raise ValueError("duplicate source hash has conflicting roles")
    if first.parser_path is not None and second.parser_path is not None:
        if (
            first.parser_kind != second.parser_kind
            or sha256_file(first.parser_path) != sha256_file(second.parser_path)
        ):
            raise ValueError("duplicate source hash has conflicting parser bindings")
    if first.parser_path is None and second.parser_path is not None:
        return replace(
            first,
            parser_path=second.parser_path,
            parser_kind=second.parser_kind,
            state="READY_FOR_INGESTION",
        )
    return first


def prepare_source_batch(batch_root: Path, batch: SourceBatch) -> tuple[PreparedSource, ...]:
    """Resolve, hash, identify, and deduplicate one generic source batch."""
    root = batch_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    prepared_by_hash: dict[str, PreparedSource] = {}
    hash_by_document: dict[str, str] = {}
    for item in sorted(batch.sources, key=lambda source: source.source_path):
        prepared = _prepare_item(root, item)
        existing_hash = hash_by_document.get(prepared.document_id)
        if existing_hash is not None and existing_hash != prepared.source_sha256:
            raise ValueError("document_id maps to multiple source hashes")
        hash_by_document[prepared.document_id] = prepared.source_sha256
        existing = prepared_by_hash.get(prepared.source_sha256)
        prepared_by_hash[prepared.source_sha256] = (
            prepared if existing is None else _merge_duplicate(existing, prepared)
        )
    return tuple(
        sorted(
            prepared_by_hash.values(),
            key=lambda source: (
                source.document_id,
                source.revision_id,
                source.source_path.as_posix(),
            ),
        )
    )
