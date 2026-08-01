"""Prepare and ingest arbitrary PDF batches without filename assumptions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ansim_review.contracts.attachments import AttachmentRole
from ansim_review.contracts.identifiers import validate_identifier
from ansim_review.contracts.source_batch import ParserKind, SourceBatch, SourceItem
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.snapshot import compute_snapshot_hash, snapshot_counts
from ansim_review.evidence.store import EvidenceStore
from ansim_review.parsing.parser_registry import (
    ParserContext,
    ParserRegistry,
    build_default_parser_registry,
)
from ansim_review.parsing.source_manifest import build_source_entry, sha256_file
from ansim_review.parsing.source_states import (
    SourceReadiness,
    SourceState,
    evaluate_source_readiness,
)
from ansim_review.retrieval.index import build_fts_index

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceBatchNotReady(ValueError):
    """Raised when source lanes cannot produce a complete evidence snapshot."""


class PendingParserOutputError(SourceBatchNotReady):
    """Raised when one or more reference sources have no parser artifact."""


@dataclass(frozen=True, slots=True)
class PreparedSource:
    """Resolved source bytes, parser binding, identity, and readiness."""

    source_path: Path
    parser_path: Path | None
    parser_kind: ParserKind | None
    parser_options: dict[str, object]
    role: AttachmentRole
    document_id: str
    revision_id: str
    source_sha256: str
    display_title: str
    state: SourceState
    reason_codes: tuple[str, ...]
    can_ingest_reference: bool
    can_evaluate: bool


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


def _readiness(
    item: SourceItem,
    *,
    parser_path: Path | None,
    registry: ParserRegistry,
) -> SourceReadiness:
    parser_declared = item.parser is not None
    parser_supported = (
        item.parser is not None and item.parser.kind in registry.kinds()
    )
    return evaluate_source_readiness(
        role=item.role,
        parser_declared=parser_declared,
        parser_artifact_available=parser_path is not None,
        parser_supported=parser_supported,
    )


def _prepare_item(
    root: Path,
    item: SourceItem,
    registry: ParserRegistry,
) -> PreparedSource:
    source_path = _resolved_file(root, item.source_path, "source_path")
    source_sha256 = sha256_file(source_path)
    document_id = derive_document_id(source_sha256, item.document_id)
    parser_path: Path | None = None
    parser_kind: ParserKind | None = None
    parser_options: dict[str, object] = {}
    if item.parser is not None:
        parser_path = _resolved_file(root, item.parser.artifact_path, "parser.artifact_path")
        parser_kind = item.parser.kind
        parser_options = dict(item.parser.options)
    readiness = _readiness(item, parser_path=parser_path, registry=registry)
    return PreparedSource(
        source_path=source_path,
        parser_path=parser_path,
        parser_kind=parser_kind,
        parser_options=parser_options,
        role=item.role,
        document_id=document_id,
        revision_id=f"{document_id}-{source_sha256[:12]}",
        source_sha256=source_sha256,
        display_title=item.display_title or source_path.stem,
        state=readiness.state,
        reason_codes=readiness.reason_codes,
        can_ingest_reference=readiness.can_ingest_reference,
        can_evaluate=readiness.can_evaluate,
    )


def _merge_duplicate(first: PreparedSource, second: PreparedSource) -> PreparedSource:
    if first.document_id != second.document_id:
        raise ValueError("source hash maps to multiple document_ids")
    if first.role != second.role:
        raise ValueError("duplicate source hash has conflicting roles")
    if first.parser_path is not None and second.parser_path is not None:
        if (
            first.parser_kind != second.parser_kind
            or first.parser_options != second.parser_options
            or sha256_file(first.parser_path) != sha256_file(second.parser_path)
        ):
            raise ValueError("duplicate source hash has conflicting parser bindings")
    if first.parser_path is None and second.parser_path is not None:
        return second
    return first


def prepare_source_batch(
    batch_root: Path,
    batch: SourceBatch,
    registry: ParserRegistry | None = None,
) -> tuple[PreparedSource, ...]:
    """Resolve, hash, identify, deduplicate, and route one generic source batch."""
    root = batch_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    selected_registry = registry or build_default_parser_registry()
    prepared_by_hash: dict[str, PreparedSource] = {}
    hash_by_document: dict[str, str] = {}
    for item in sorted(batch.sources, key=lambda source: source.source_path):
        prepared = _prepare_item(root, item, selected_registry)
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


def _source_records(
    batch_root: Path,
    sources: tuple[PreparedSource, ...],
    registry: ParserRegistry,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    documents: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    visuals: list[dict[str, Any]] = []
    for source in sources:
        if source.parser_path is None or source.parser_kind is None:
            raise PendingParserOutputError(
                f"PENDING_PARSER_OUTPUT: {source.source_path.name}"
            )
        contribution = registry.parse(
            source.parser_kind,
            ParserContext(
                source_path=source.source_path,
                parser_artifact_path=source.parser_path,
                options=source.parser_options,
            ),
        )
        if sha256_file(source.parser_path) != contribution.parser_artifact_sha256:
            raise ValueError("PARSER_ARTIFACT_CHANGED")
        entry = build_source_entry(
            source.source_path,
            document_id=source.document_id,
            page_count=contribution.page_count,
            parser_artifacts=(source.parser_path,),
            relative_to=batch_root,
        )
        if entry.source_hash != source.source_sha256 or entry.revision_id != source.revision_id:
            raise ValueError("source bytes changed after batch preparation")
        documents.append(
            {
                "id": source.document_id,
                "title": contribution.document_title or source.display_title,
            }
        )
        revisions.append(
            {
                "id": source.revision_id,
                "document_id": source.document_id,
                "source_hash": source.source_sha256,
                "byte_size": source.source_path.stat().st_size,
                "page_count": contribution.page_count,
            }
        )
        for page in contribution.page_dimensions:
            page_id = f"{source.revision_id}-P{page.page_number:04d}"
            pages.append(
                {
                    "id": page_id,
                    "revision_id": source.revision_id,
                    "page_number": page.page_number,
                    "width": page.width,
                    "height": page.height,
                }
            )
        for element in contribution.elements:
            elements.append(
                {
                    "id": f"{source.revision_id}-{element.element_key}",
                    "page_id": f"{source.revision_id}-P{element.page_number:04d}",
                    "element_type": element.element_type,
                    "raw_json": element.raw_payload,
                    "raw_text": element.raw_text,
                    "normalized_text": None,
                    "raw_payload_hash": element.raw_payload_hash,
                    "bbox": element.bbox,
                    "parser_order": element.parser_order,
                }
            )
        for table in contribution.tables:
            tables.append(
                {
                    "id": f"{source.revision_id}-{table.table_key}",
                    "page_id": f"{source.revision_id}-P{table.page_number:04d}",
                    "bbox": table.bbox,
                    "raw_json": table.raw_payload,
                    "normalized_json": None,
                }
            )
        for visual in contribution.visuals:
            visuals.append(
                {
                    "id": f"{source.revision_id}-{visual.visual_key}",
                    "page_id": f"{source.revision_id}-P{visual.page_number:04d}",
                    "kind": visual.kind,
                    "relative_path": visual.relative_path,
                    "sha256": visual.sha256,
                    "bbox": visual.bbox,
                    "duplicate_group": visual.sha256,
                }
            )

    def by_id(record: dict[str, Any]) -> str:
        return str(record["id"])

    return (
        tuple(sorted(documents, key=by_id)),
        tuple(sorted(revisions, key=by_id)),
        tuple(sorted(pages, key=by_id)),
        tuple(sorted(elements, key=by_id)),
        tuple(sorted(tables, key=by_id)),
        tuple(sorted(visuals, key=by_id)),
    )


def import_source_batch(
    batch_root: Path,
    batch: SourceBatch,
    output_db: Path,
    registry: ParserRegistry | None = None,
) -> SourceBatchImportReport:
    """Create an evidence snapshot from parser-ready reference lanes only."""
    root = batch_root.resolve()
    output = output_db.resolve()
    if output.exists():
        raise FileExistsError(output)
    selected_registry = registry or build_default_parser_registry()
    sources = prepare_source_batch(root, batch, selected_registry)
    pending = tuple(
        source
        for source in sources
        if source.role in {"REFERENCE_DOCUMENT", "CASE_TABLE"}
        and source.state == SourceState.PENDING_PARSER_OUTPUT
    )
    if pending:
        names = ", ".join(source.source_path.name for source in pending)
        raise PendingParserOutputError(f"PENDING_PARSER_OUTPUT: {names}")
    blocked = tuple(
        source
        for source in sources
        if source.role in {"REFERENCE_DOCUMENT", "CASE_TABLE"}
        and source.state in {SourceState.BLOCKED, SourceState.FAILED}
    )
    if blocked:
        reasons = ", ".join(
            f"{source.source_path.name}:{'|'.join(source.reason_codes)}"
            for source in blocked
        )
        raise SourceBatchNotReady(f"SOURCE_BATCH_BLOCKED: {reasons}")
    ingestible = tuple(source for source in sources if source.can_ingest_reference)
    if not ingestible:
        raise SourceBatchNotReady(
            "NO_EVIDENCE_SOURCES: source batch contains no parser-ready evidence sources"
        )
    documents, revisions, pages, elements, tables, visuals = _source_records(
        root,
        ingestible,
        selected_registry,
    )
    snapshot = EvidenceSnapshot(
        documents=documents,
        revisions=revisions,
        pages=pages,
        elements=elements,
        tables=tables,
        visuals=visuals,
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
    ingested_ids = {source.revision_id for source in ingestible}
    completed = tuple(
        replace(
            source,
            state=SourceState.READY_TO_EVALUATE,
            reason_codes=(),
            can_ingest_reference=False,
            can_evaluate=True,
        )
        if source.revision_id in ingested_ids
        else source
        for source in sources
    )
    return SourceBatchImportReport(
        output_db=output,
        snapshot_hash=snapshot_hash,
        counts=counts,
        sources=completed,
    )
