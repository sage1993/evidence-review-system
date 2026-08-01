"""CSV, visual, and link import helpers for Ansim workspace migration."""
from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ansim_review.canonical_json import sha256_json
from ansim_review.parsing.source_manifest import sha256_file
from ansim_review.parsing.visual_manifest import load_visual_manifest


def csv_rows(path: Path) -> tuple[dict[str, str], ...]:
    if not path.is_file():
        return ()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return tuple(
            {str(key): value or "" for key, value in row.items() if key is not None}
            for row in csv.DictReader(stream)
        )


def value(row: Mapping[str, str], *names: str) -> str:
    lowered = {key.lower(): item for key, item in row.items()}
    for name in names:
        candidate = lowered.get(name.lower(), "").strip()
        if candidate:
            return candidate
    return ""


def stable_id(prefix: str, payload: Mapping[str, str]) -> str:
    return f"{prefix}-{sha256_json(dict(sorted(payload.items())))[:16].upper()}"


def parse_json_cell(text: str, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def import_clauses(root: Path, revisions: Mapping[str, str]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for row in csv_rows(root / "05_exports" / "Clauses.csv"):
        document_id = value(row, "DocumentID", "Document")
        if document_id not in revisions:
            continue
        clause_id = value(row, "ClauseID", "ID") or stable_id("CLAUSE", row)
        records.append(
            {
                "id": clause_id,
                "revision_id": revisions[document_id],
                "title": value(row, "Title") or clause_id,
                "raw_text": value(row, "RawText") or None,
                "normalized_text": value(row, "NormalizedText") or None,
                "review_status": value(row, "ReviewStatus", "Status") or "AUTOMATIC",
            }
        )
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def import_tables(root: Path, revisions: Mapping[str, str]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for row in csv_rows(root / "05_exports" / "ExtractedTables.csv"):
        document_id = value(row, "DocumentID", "Document")
        if document_id not in revisions:
            continue
        table_id = value(row, "TableID", "ID") or stable_id("TABLE", row)
        records.append(
            {
                "id": table_id,
                "revision_id": revisions[document_id],
                "page_number": int(value(row, "PageNumber", "Page") or "1"),
                "bbox": parse_json_cell(value(row, "BBox"), None),
                "raw_json": parse_json_cell(value(row, "RawJSON", "Data"), {}),
                "normalized_json": parse_json_cell(value(row, "NormalizedJSON"), None),
            }
        )
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def _manifest_document_id(path: Path, payload: object) -> str | None:
    if isinstance(payload, dict):
        candidate = payload.get("document_id")
        if isinstance(candidate, str) and candidate:
            return candidate
    lowered = path.stem.lower()
    if "law-1" in lowered or "law1" in lowered:
        return "LAW1"
    if "law-2" in lowered or "law2" in lowered:
        return "LAW2"
    return None


def import_visuals(root: Path, revisions: Mapping[str, str]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    manifest_dir = root / "04_visuals" / "manifests"
    if manifest_dir.is_dir():
        for path in sorted(manifest_dir.glob("*.json")):
            payload: object = json.loads(path.read_text(encoding="utf-8"))
            document_id = _manifest_document_id(path, payload)
            if document_id is None or document_id not in revisions:
                continue
            result = load_visual_manifest(
                root,
                path,
                document_id=document_id,
                revision_id=revisions[document_id],
            )
            for record in result.records:
                bbox = None
                if record.bbox is not None:
                    bbox = [
                        record.bbox.left,
                        record.bbox.bottom,
                        record.bbox.right,
                        record.bbox.top,
                    ]
                records.append(
                    {
                        "id": record.visual_id,
                        "revision_id": record.revision_id,
                        "page_number": record.page_number,
                        "kind": record.kind,
                        "relative_path": record.relative_path,
                        "sha256": record.sha256,
                        "bbox": bbox,
                        "duplicate_group": record.duplicate_group,
                        "source_evidence_ids": list(record.source_evidence_ids),
                    }
                )
    for row in csv_rows(root / "05_exports" / "Visuals.csv"):
        document_id = value(row, "DocumentID", "Document")
        if document_id not in revisions:
            continue
        relative_path = value(row, "RelativePath", "Path")
        absolute_path = root / relative_path
        if not relative_path or not absolute_path.is_file():
            continue
        digest = value(row, "SHA256") or sha256_file(absolute_path)
        records.append(
            {
                "id": value(row, "VisualID", "ID") or stable_id("VISUAL", row),
                "revision_id": revisions[document_id],
                "page_number": int(value(row, "PageNumber", "Page") or "1"),
                "kind": value(row, "Kind") or "occurrence_crop",
                "relative_path": Path(relative_path).as_posix(),
                "sha256": digest,
                "bbox": parse_json_cell(value(row, "BBox"), None),
                "duplicate_group": value(row, "DuplicateGroup") or f"DUP-{digest[:16]}",
                "source_evidence_ids": parse_json_cell(value(row, "SourceEvidenceIDs"), []),
            }
        )
    unique = {str(record["id"]): record for record in records}
    return tuple(unique[key] for key in sorted(unique))


def import_review_flags(root: Path) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for row in csv_rows(root / "05_exports" / "ReviewFlags.csv"):
        evidence_id = value(row, "EvidenceID")
        code = value(row, "Code")
        if not evidence_id or not code:
            continue
        records.append(
            {
                "id": value(row, "FlagID", "ID") or stable_id("FLAG", row),
                "evidence_id": evidence_id,
                "code": code,
                "status": value(row, "Status") or "OPEN",
                "detail": value(row, "Detail") or None,
            }
        )
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def import_links(
    root: Path,
    known_ids: set[str],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, str], ...]]:
    valid: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    for row in csv_rows(root / "05_exports" / "Links.csv"):
        link_id = value(row, "LinkID", "ID") or stable_id("LINK", row)
        source_id = value(row, "SourceID")
        target_id = value(row, "TargetID")
        relation_type = value(row, "RelationType", "Type")
        missing = tuple(item for item in (source_id, target_id) if item and item not in known_ids)
        if not source_id or not target_id or not relation_type or missing:
            unresolved.append(
                {
                    "link_id": link_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type,
                    "reason": "MISSING_ENDPOINT" if missing else "INCOMPLETE_LINK",
                    "missing_ids": ",".join(sorted(missing)),
                }
            )
            continue
        valid.append(
            {
                "id": link_id,
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
            }
        )
    return (
        tuple(sorted(valid, key=lambda record: str(record["id"]))),
        tuple(sorted(unresolved, key=lambda record: record["link_id"])),
    )
