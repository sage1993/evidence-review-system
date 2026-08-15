"""Strict visual manifest loading with explicit document, revision, and page identity."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from evidence_review.contracts.common import BBox
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.parsing.source_manifest import sha256_file

_KINDS = frozenset(
    {
        "unique_image",
        "occurrence_crop",
        "table_crop",
        "composite_diagram",
        "page_render",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORMAT = "evidence-review/visual-manifest"


@dataclass(frozen=True, slots=True)
class VisualRecord:
    visual_id: str
    document_id: str
    revision_id: str
    page_id: str
    kind: str
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
    first = path.parts[0] if path.parts else ""
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "\\" in value
        or ":" in first
    ):
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
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError("source_evidence_ids must be an array of non-empty strings")
    return tuple(value)


def _entry(value: object, index: int) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"visual manifest record {index} must be an object")
    required = {
        "id",
        "document_id",
        "revision_id",
        "page_id",
        "kind",
        "path",
        "sha256",
        "bbox",
        "source_evidence_ids",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"visual manifest record {index} missing {missing[0]}")
    unknown = sorted(set(value) - required)
    if unknown:
        raise ValueError(f"visual manifest record {index} has unknown field {unknown[0]}")
    return value


def load_visual_manifest(root: Path, manifest_path: Path) -> VisualManifestResult:
    """Load explicit visual identities without filename or folder inference."""
    payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("visual manifest format must be an object")
    if set(payload) != {"format", "version", "records"}:
        raise ValueError("visual manifest format fields are invalid")
    if payload.get("format") != _FORMAT or payload.get("version") != 1:
        raise ValueError("visual manifest format is unsupported")
    entries = payload.get("records")
    if not isinstance(entries, list):
        raise ValueError("visual manifest records must be an array")

    records: list[VisualRecord] = []
    issues: list[ManifestIssue] = []
    used_ids: set[str] = set()
    root_resolved = root.resolve()
    for index, value in enumerate(entries):
        entry = _entry(value, index)
        visual_id = validate_identifier(entry.get("id"), "id")
        document_id = validate_identifier(entry.get("document_id"), "document_id")
        revision_id = validate_identifier(entry.get("revision_id"), "revision_id")
        page_id = validate_identifier(entry.get("page_id"), "page_id")
        if visual_id in used_ids:
            raise ValueError(f"duplicate visual id: {visual_id}")
        used_ids.add(visual_id)
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in _KINDS:
            raise ValueError(f"unsupported visual kind: {kind}")
        relative_path = _relative_posix_path(entry.get("path"))
        absolute_path = (root_resolved / Path(relative_path)).resolve()
        if not absolute_path.is_relative_to(root_resolved):
            raise ValueError("visual path escapes workspace root")
        expected_hash = entry.get("sha256")
        if not isinstance(expected_hash, str) or _SHA256.fullmatch(expected_hash) is None:
            raise ValueError("visual sha256 must be a lowercase SHA-256 digest")
        if not absolute_path.is_file():
            issues.append(ManifestIssue("MISSING_FILE", relative_path, "file does not exist"))
            continue
        actual_hash = sha256_file(absolute_path)
        if expected_hash != actual_hash:
            issues.append(
                ManifestIssue(
                    "HASH_MISMATCH",
                    relative_path,
                    f"expected {expected_hash}, actual {actual_hash}",
                )
            )
            continue
        records.append(
            VisualRecord(
                visual_id=visual_id,
                document_id=document_id,
                revision_id=revision_id,
                page_id=page_id,
                kind=kind,
                relative_path=relative_path,
                sha256=actual_hash,
                duplicate_group=f"DUP-{actual_hash[:16]}",
                bbox=_bbox(entry.get("bbox")),
                source_evidence_ids=_source_ids(entry.get("source_evidence_ids")),
            )
        )
    return VisualManifestResult(
        records=tuple(sorted(records, key=lambda record: record.visual_id)),
        issues=tuple(sorted(issues, key=lambda issue: (issue.code, issue.relative_path))),
    )


def validate_visual_page_identity(
    connection: sqlite3.Connection,
    record: VisualRecord,
) -> None:
    """Require the explicit page to belong to the declared revision and document."""
    row = connection.execute(
        """
        SELECT d.id, r.id, p.id
        FROM pages AS p
        JOIN revisions AS r ON r.id = p.revision_id
        JOIN documents AS d ON d.id = r.document_id
        WHERE p.id = ?
        """,
        (record.page_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"VISUAL_PAGE_NOT_FOUND: {record.page_id}")
    actual = (str(row[0]), str(row[1]), str(row[2]))
    declared = (record.document_id, record.revision_id, record.page_id)
    if actual != declared:
        raise ValueError(
            "VISUAL_PAGE_IDENTITY_MISMATCH: "
            f"declared={declared[0]}/{declared[1]}/{declared[2]} "
            f"actual={actual[0]}/{actual[1]}/{actual[2]}"
        )
