"""Prepare and ingest arbitrary PDF batches without sample filename assumptions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from ansim_review.contracts.attachments import AttachmentRole
from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.source_batch import ParserKind, SourceBatch, SourceItem
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.snapshot import compute_snapshot_hash, snapshot_counts
from ansim_review.evidence.store import EvidenceStore
from ansim_review.parsing.odl_adapter import load_raw_elements
from ansim_review.parsing.odl_source import (
    parser_bbox,
    parser_document_title,
    parser_page_count,
    parser_page_dimensions,
    read_parser_json,
)
from ansim_review.parsing.source_manifest import build_source_entry, sha256_file
from ansim_review.retrieval.index import build_fts_index

SourcePreparationState = Literal[
    "PENDING_PARSER_OUTPUT",
    "READY_FOR_INGESTION",
    "DRAWING_BACKEND_ONLY",
]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PendingParserOutputError(ValueError):
    """Raised when one or more registered evidence PDFs have no parser artifact."""


@dataclass(frozen=True, slots=True)
class PreparedSource:
    """Resolved source bytes and optional parser artifact ready for routing."""

    source_path: Path
    parser_path: Path | None
    parser_kind: ParserKind | None
    role: AttachmentRole
    document_id: str
    revision_id: str
    source_sha256: str
    display_title: str
    state: SourcePreparationState


@dataclass(frozen=True, slots=True)
class SourceBatchImportReport:
    """Deterministic result of one generic source-batch ingestion."""

    output_db: Path
    snapshot_hash: str
    counts: dict[str, int]
    sources: tuple[PreparedSource, ...]


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
    state: SourcePreparationState = (
        "DRAWING_BACKEND_ONLY"
        if item.role == "CASE_DRAWING"
        else "PENDING_PARSER_OUTPUT"
    )
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
            source_path=second.source_path,
            parser_path=second.parser_path,
            parser_kind=second.parser_kind,
            display_title=second.display_title,
            state="READY_FOR_INGESTION",
        )
    return first


def prepare_source_batch(batch_root: Path, batch: SourceBatch) -> tuple[PreparedSource, ...]:
    """Resolve, hash, identify, deduplicate, and route one generic source batch."""
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


def _validate_parser_source_binding(
    parser_payload: dict[str, Any], source_path: Path
) -> None:
    declared_name = parser_payload.get("file name")
    if declared_name is None:
        return
    if not isinstance(declared_name, str) or not declared_name.strip():
        raise ValueError("parser file name must be a non-empty string")
    if Path(declared_name).name != source_path.name:
        raise ValueError("parser file name does not match source PDF")


def _source_records(
    batch_root: Path,
    sources: tuple[PreparedSource, ...],
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    documents: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    for source in sources:
        if source.parser_path is None or source.parser_kind is None:
            raise PendingParserOutputError(
                f"PENDING_PARSER_OUTPUT: {source.source_path.name}"
            )
        if source.parser_kind != "OPENDATALOADER_JSON":
            raise ValueError(f"unsupported parser kind: {source.parser_kind}")
        parser_payload = read_parser_json(source.parser_path)
        _validate_parser_source_binding(parser_payload, source.source_path)
        raw_elements = load_raw_elements(
            source.parser_path,
            document_id=source.document_id,
            revision_id=source.revision_id,
        )
        current_page_count = parser_page_count(parser_payload, raw_elements)
        entry = build_source_entry(
            source.source_path,
            document_id=source.document_id,
            page_count=current_page_count,
            parser_artifacts=(source.parser_path,),
            relative_to=batch_root,
        )
        if entry.source_hash != source.source_sha256 or entry.revision_id != source.revision_id:
            raise ValueError("source bytes changed after batch preparation")
        documents.append(
            {
                "id": source.document_id,
                "title": parser_document_title(parser_payload, source.display_title),
            }
        )
        revisions.append(
            {
                "id": source.revision_id,
                "document_id": source.document_id,
                "source_hash": source.source_sha256,
                "byte_size": source.source_path.stat().st_size,
                "page_count": current_page_count,
            }
        )
        dimensions: dict[int, tuple[float, float]] = {}
        for page_number in range(1, current_page_count + 1):
            width, height = parser_page_dimensions(parser_payload, page_number)
            dimensions[page_number] = (width, height)
            pages.append(
                {
                    "id": f"{source.revision_id}-P{page_number:04d}",
                    "revision_id": source.revision_id,
                    "page_number": page_number,
                    "width": width,
                    "height": height,
                }
            )
        for element in raw_elements:
            width, height = dimensions[element.page_number]
            elements.append(
                {
                    "id": element.element_id,
                    "revision_id": source.revision_id,
                    "page_id": f"{source.revision_id}-P{element.page_number:04d}",
                    "page_number": element.page_number,
                    "element_type": element.element_type,
                    "raw_json": element.raw_payload,
                    "raw_text": element.raw_text,
                    "normalized_text": None,
                    "raw_payload_hash": element.raw_payload_hash,
                    "bbox": parser_bbox(element, width, height),
                    "parser_order": element.parser_order,
                }
            )

    def by_id(record: dict[str, Any]) -> str:
        return str(record["id"])

    return (
        tuple(sorted(documents, key=by_id)),
        tuple(sorted(revisions, key=by_id)),
        tuple(sorted(pages, key=by_id)),
        tuple(sorted(elements, key=by_id)),
    )


def import_source_batch(
    batch_root: Path,
    batch: SourceBatch,
    output_db: Path,
) -> SourceBatchImportReport:
    """Create an evidence snapshot while routing parserless drawings separately."""
    root = batch_root.resolve()
    output = output_db.resolve()
    if output.exists():
        raise FileExistsError(output)
    sources = prepare_source_batch(root, batch)
    pending = tuple(source for source in sources if source.state == "PENDING_PARSER_OUTPUT")
    if pending:
        names = ", ".join(source.source_path.name for source in pending)
        raise PendingParserOutputError(f"PENDING_PARSER_OUTPUT: {names}")
    ingestible = tuple(
        source for source in sources if source.state == "READY_FOR_INGESTION"
    )
    if not ingestible:
        raise ValueError(
            "NO_EVIDENCE_SOURCES: source batch contains no parser-ready evidence sources"
        )
    documents, revisions, pages, elements = _source_records(root, ingestible)
    snapshot = EvidenceSnapshot(
        documents=documents,
        revisions=revisions,
        pages=pages,
        elements=elements,
    )
    with EvidenceStore(output, create=True) as store:
        ingest_snapshot(store, snapshot)
        snapshot_hash = compute_snapshot_hash(store)
        connection = store.require_connection()
        connection.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('database_snapshot_hash', ?)",
            (snapshot_hash,),
        )
        connection.commit()
        build_fts_index(connection)
        counts = snapshot_counts(store)
    return SourceBatchImportReport(
        output_db=output,
        snapshot_hash=snapshot_hash,
        counts=counts,
        sources=sources,
    )
