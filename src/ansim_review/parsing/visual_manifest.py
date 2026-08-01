"""Traceable visual and table manifest loading."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ansim_review.contracts.common import BBox
from ansim_review.parsing.source_manifest import sha256_file

_KIND_PREFIX = {
    "unique_image": "PDF",
    "occurrence_crop": "OCC",
    "table_crop": "TBL",
    "composite_diagram": "COMP",
    "page_render": "PAGE",
}


@dataclass(frozen=True, slots=True)
class VisualRecord:
    visual_id: str
    document_id: str
    revision_id: str
    kind: str
    page_number: int
    relative_path: str
    sha256: str
    duplicate_group: str
    bbox: BBox | None
    source_evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManifestIssue:
    code: str
    relative_path: str
    detail: str


@dataclass(frozen=True, slots=True)
class VisualManifestResult:
    records: tuple[VisualRecord, ...]
    issues: tuple[ManifestIssue, ...]


def _relative_posix_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("visual path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("visual path must be a workspace-relative POSIX path")
    return path.as_posix()


def _bbox(value: object) -> BBox | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("visual bbox must contain four numbers")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("visual bbox must contain four numbers")
        numbers.append(float(item))
    return BBox(*numbers)


def _source_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError("source_evidence_ids must be an array of non-empty strings")
    return tuple(value)


def _generated_id(kind: str, document_id: str, page_number: int, sequence: int) -> str:
    prefix = _KIND_PREFIX[kind]
    if kind == "unique_image":
        return f"PDF-{document_id}-U{sequence:03d}"
    if kind == "page_render":
        return f"PAGE-{document_id}-{page_number:03d}"
    return f"{prefix}-{document_id}-{sequence:03d}"


def load_visual_manifest(
    root: Path,
    manifest_path: Path,
    *,
    document_id: str,
    revision_id: str,
) -> VisualManifestResult:
    """Load and verify visual occurrences without collapsing duplicates."""
    payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("visual manifest must be an array or contain a records array")

    staged: list[
        tuple[int, str, int, str, str, BBox | None, tuple[str, ...], str | None]
    ] = []
    issues: list[ManifestIssue] = []
    root_resolved = root.resolve()
    for order, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"visual manifest entry {order} must be an object")
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in _KIND_PREFIX:
            raise ValueError(f"unsupported visual kind: {kind}")
        page_number = entry.get("page_number")
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
            raise ValueError("visual page_number must be a positive integer")
        explicit_id = entry.get("id")
        if explicit_id is not None and (not isinstance(explicit_id, str) or not explicit_id):
            raise ValueError("visual id must be a non-empty string")
        relative_path = _relative_posix_path(entry.get("path"))
        absolute_path = (root_resolved / Path(relative_path)).resolve()
        try:
            absolute_path.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError("visual path escapes workspace root") from exc
        if not absolute_path.is_file():
            issues.append(ManifestIssue("MISSING_FILE", relative_path, "file does not exist"))
            continue
        actual_hash = sha256_file(absolute_path)
        expected_hash = entry.get("sha256")
        if expected_hash is not None:
            if not isinstance(expected_hash, str):
                raise ValueError("visual sha256 must be a string")
            if expected_hash != actual_hash:
                issues.append(
                    ManifestIssue(
                        "HASH_MISMATCH",
                        relative_path,
                        f"expected {expected_hash}, actual {actual_hash}",
                    )
                )
                continue
        staged.append(
            (
                order,
                kind,
                page_number,
                relative_path,
                actual_hash,
                _bbox(entry.get("bbox")),
                _source_ids(entry.get("source_evidence_ids")),
                explicit_id,
            )
        )

    counters: dict[str, int] = {}
    records: list[VisualRecord] = []
    used_ids: set[str] = set()
    for _, kind, page_number, relative_path, digest, bbox, source_ids, explicit_id in sorted(
        staged,
        key=lambda item: (item[1], item[2], item[3], item[0]),
    ):
        counters[kind] = counters.get(kind, 0) + 1
        visual_id = explicit_id or _generated_id(
            kind,
            document_id,
            page_number,
            counters[kind],
        )
        if visual_id in used_ids:
            raise ValueError(f"duplicate visual id: {visual_id}")
        used_ids.add(visual_id)
        records.append(
            VisualRecord(
                visual_id=visual_id,
                document_id=document_id,
                revision_id=revision_id,
                kind=kind,
                page_number=page_number,
                relative_path=relative_path,
                sha256=digest,
                duplicate_group=f"DUP-{digest[:16]}",
                bbox=bbox,
                source_evidence_ids=source_ids,
            )
        )
    return VisualManifestResult(
        records=tuple(records),
        issues=tuple(sorted(issues, key=lambda issue: (issue.code, issue.relative_path))),
    )
