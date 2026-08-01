"""Migrate the Ansim PDF/Grist workspace into a deterministic evidence snapshot."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ansim_review.canonical_json import dump_bytes, sha256_json
from ansim_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from ansim_review.evidence.snapshot import compute_snapshot_hash, snapshot_counts
from ansim_review.evidence.store import EvidenceStore
from ansim_review.parsing._ansim_csv import (
    import_clauses,
    import_links,
    import_review_flags,
    import_tables,
    import_visuals,
)
from ansim_review.parsing._ansim_sources import (
    bbox_list,
    document_id,
    document_title,
    page_count,
    page_dimensions,
    source_pairs,
)
from ansim_review.parsing.odl_adapter import load_raw_elements
from ansim_review.parsing.source_manifest import build_source_entry


@dataclass(frozen=True, slots=True)
class MigrationReport:
    output_db: Path
    snapshot_hash: str
    counts: dict[str, int]
    unresolved_link_count: int
    unresolved_links_path: Path


def _source_records(
    root: Path,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, str],
]:
    documents: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    revision_by_document: dict[str, str] = {}

    for pdf_path, parser_path, parser_payload in source_pairs(root):
        current_document_id = document_id(pdf_path.stem)
        provisional_revision = f"{current_document_id}-pending"
        raw_elements = load_raw_elements(
            parser_path,
            document_id=current_document_id,
            revision_id=provisional_revision,
        )
        current_page_count = page_count(parser_payload, raw_elements)
        source_entry = build_source_entry(
            pdf_path,
            document_id=current_document_id,
            page_count=current_page_count,
            parser_artifacts=(parser_path,),
            relative_to=root,
        )
        raw_elements = load_raw_elements(
            parser_path,
            document_id=current_document_id,
            revision_id=source_entry.revision_id,
        )
        revision_by_document[current_document_id] = source_entry.revision_id
        documents.append(
            {
                "id": current_document_id,
                "title": document_title(parser_payload, pdf_path.stem),
            }
        )
        revisions.append(
            {
                "id": source_entry.revision_id,
                "document_id": current_document_id,
                "source_hash": source_entry.source_hash,
                "byte_size": source_entry.byte_size,
                "page_count": current_page_count,
            }
        )
        dimensions: dict[int, tuple[float, float]] = {}
        for page_number in range(1, current_page_count + 1):
            width, height = page_dimensions(parser_payload, page_number)
            dimensions[page_number] = (width, height)
            pages.append(
                {
                    "id": f"{source_entry.revision_id}-P{page_number:04d}",
                    "revision_id": source_entry.revision_id,
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
                    "revision_id": source_entry.revision_id,
                    "page_id": f"{source_entry.revision_id}-P{element.page_number:04d}",
                    "page_number": element.page_number,
                    "element_type": element.element_type,
                    "raw_json": element.raw_payload,
                    "raw_text": element.raw_text,
                    "normalized_text": None,
                    "raw_payload_hash": element.raw_payload_hash,
                    "bbox": bbox_list(element, width, height),
                    "parser_order": element.parser_order,
                }
            )

    sorter = lambda record: str(record["id"])
    return (
        tuple(sorted(documents, key=sorter)),
        tuple(sorted(revisions, key=sorter)),
        tuple(sorted(pages, key=sorter)),
        tuple(sorted(elements, key=sorter)),
        revision_by_document,
    )


def _visual_source_links(
    visuals: tuple[dict[str, Any], ...],
    known_ids: set[str],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, str], ...]]:
    links: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    for visual in visuals:
        visual_id = str(visual["id"])
        source_ids = visual.get("source_evidence_ids", [])
        if not isinstance(source_ids, list):
            continue
        for source_id_value in source_ids:
            source_id = str(source_id_value)
            payload = {
                "source_id": visual_id,
                "target_id": source_id,
                "relation_type": "VISUAL_SOURCE",
            }
            link_id = f"LINK-{sha256_json(payload)[:16].upper()}"
            if source_id not in known_ids:
                unresolved.append(
                    {
                        "link_id": link_id,
                        "source_id": visual_id,
                        "target_id": source_id,
                        "relation_type": "VISUAL_SOURCE",
                        "reason": "MISSING_ENDPOINT",
                        "missing_ids": source_id,
                    }
                )
            else:
                links.append({"id": link_id, **payload})
    return (
        tuple(sorted(links, key=lambda record: str(record["id"]))),
        tuple(sorted(unresolved, key=lambda record: record["link_id"])),
    )


def import_ansim_workspace(root: Path, output_db: Path) -> MigrationReport:
    """Import immutable source and reviewed CSV fields into a new SQLite snapshot."""
    root = root.resolve()
    output_db = output_db.resolve()
    if output_db.exists():
        raise FileExistsError(output_db)

    documents, revisions, pages, elements, revision_by_document = _source_records(root)
    clauses = import_clauses(root, revision_by_document)
    tables = import_tables(root, revision_by_document)
    visuals = import_visuals(root, revision_by_document)
    review_flags = import_review_flags(root)

    known_ids = {
        str(record["id"])
        for collection in (documents, revisions, pages, elements, clauses, tables, visuals)
        for record in collection
    }
    csv_links, csv_unresolved = import_links(root, known_ids)
    visual_links, visual_unresolved = _visual_source_links(visuals, known_ids)
    links_by_id = {str(record["id"]): record for record in (*csv_links, *visual_links)}
    links = tuple(links_by_id[key] for key in sorted(links_by_id))
    unresolved_links = tuple(
        sorted((*csv_unresolved, *visual_unresolved), key=lambda record: record["link_id"])
    )
    unresolved_path = output_db.with_suffix(".unresolved-links.json")
    unresolved_path.write_bytes(dump_bytes(list(unresolved_links)))

    snapshot = EvidenceSnapshot(
        documents=documents,
        revisions=revisions,
        pages=pages,
        elements=elements,
        clauses=clauses,
        tables=tables,
        visuals=visuals,
        links=links,
        review_flags=review_flags,
    )
    with EvidenceStore(output_db) as store:
        ingest_snapshot(store, snapshot)
        snapshot_hash = compute_snapshot_hash(store)
        store.require_connection().execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('database_snapshot_hash', ?)",
            (snapshot_hash,),
        )
        store.require_connection().commit()
        counts = snapshot_counts(store)

    return MigrationReport(
        output_db=output_db,
        snapshot_hash=snapshot_hash,
        counts=counts,
        unresolved_link_count=len(unresolved_links),
        unresolved_links_path=unresolved_path,
    )
