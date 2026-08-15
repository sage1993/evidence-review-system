"""Read-only inspection for legacy Grist visual CSV artifacts."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Final

from evidence_review.contracts.legacy_formats import LEGACY_VISUAL_STATUS
from evidence_review.parsing.source_manifest import sha256_file

LEGACY_VISUAL_HEADER: Final[tuple[str, ...]] = (
    "visual_id",
    "document_id",
    "clause_row_id",
    "clause_id",
    "page",
    "visual_type",
    "source_key",
    "related_table_row_id",
    "source_path",
    "crop_path",
    "bbox_left",
    "bbox_bottom",
    "bbox_right",
    "bbox_top",
    "pixel_width",
    "pixel_height",
    "sha256",
)

_CONVERSION_REQUIREMENTS: Final[tuple[str, ...]] = (
    "ASSET_SHA256_MATCH",
    "DB_RESOLVED_PAGE_ID",
    "EXPLICIT_ASSET_PATH_POLICY",
    "EXPLICIT_DOCUMENT_ALIAS",
    "EXPLICIT_REVISION_ID",
    "EXPLICIT_VISUAL_KIND_MAP",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _source_label(manifest_path: Path, root: Path | None) -> str:
    if root is None:
        return manifest_path.name
    root_resolved = root.resolve()
    resolved = manifest_path.resolve()
    if resolved.is_relative_to(root_resolved):
        return resolved.relative_to(root_resolved).as_posix()
    return manifest_path.name


def _safe_posix_path(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    if value.startswith("/") or value.endswith("/"):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _issue(
    row_number: int,
    visual_id: str,
    code: str,
    detail: str,
) -> dict[str, object]:
    return {
        "row_number": row_number,
        "visual_id": visual_id,
        "code": code,
        "detail": detail,
    }


def _issue_sort_key(item: dict[str, object]) -> tuple[int, str]:
    row_number = item.get("row_number")
    code = item.get("code")
    if not isinstance(row_number, int) or isinstance(row_number, bool):
        raise TypeError("legacy visual issue row_number must be an integer")
    if not isinstance(code, str):
        raise TypeError("legacy visual issue code must be a string")
    return row_number, code


def _asset_issue(
    root: Path,
    row_number: int,
    visual_id: str,
    crop_path: str,
    expected_hash: str,
) -> dict[str, object] | None:
    root_resolved = root.resolve()
    target = (root_resolved / Path(crop_path)).resolve()
    if not target.is_relative_to(root_resolved):
        return _issue(
            row_number,
            visual_id,
            "CROP_PATH_INVALID",
            "crop_path escapes workspace root",
        )
    if not target.is_file():
        return _issue(
            row_number,
            visual_id,
            "ASSET_MISSING",
            f"asset does not exist: {crop_path}",
        )
    actual_hash = sha256_file(target)
    if actual_hash != expected_hash:
        return _issue(
            row_number,
            visual_id,
            "ASSET_HASH_MISMATCH",
            f"expected {expected_hash}, actual {actual_hash}",
        )
    return None


def inspect_legacy_visual_manifest(
    manifest_path: Path,
    *,
    root: Path | None = None,
) -> dict[str, object]:
    """Inspect legacy rows without creating canonical visual identities."""
    raw = manifest_path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    issues: list[dict[str, object]] = []
    document_ids: set[str] = set()
    seen_visual_ids: set[str] = set()
    row_count = 0

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != LEGACY_VISUAL_HEADER:
            raise ValueError("LEGACY_VISUAL_HEADER_INVALID")

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            values = [row.get(name) for name in LEGACY_VISUAL_HEADER]
            if all(value in {None, ""} for value in values):
                issues.append(
                    _issue(row_number, "", "EMPTY_ROW", "row is empty")
                )
                continue
            if None in row or any(value is None for value in values):
                issues.append(
                    _issue(
                        row_number,
                        str(row.get("visual_id") or ""),
                        "ROW_COLUMN_COUNT_INVALID",
                        "row column count does not match legacy header",
                    )
                )
                continue

            visual_id = str(row["visual_id"] or "")
            document_id = str(row["document_id"] or "")
            page = str(row["page"] or "")
            source_path = str(row["source_path"] or "")
            crop_path = str(row["crop_path"] or "")
            expected_hash = str(row["sha256"] or "")

            if not visual_id:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "VISUAL_ID_MISSING",
                        "visual_id is empty",
                    )
                )
            elif visual_id in seen_visual_ids:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "DUPLICATE_VISUAL_ID",
                        f"visual_id already appeared: {visual_id}",
                    )
                )
            else:
                seen_visual_ids.add(visual_id)

            if not document_id:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "DOCUMENT_ID_MISSING",
                        "document_id is empty",
                    )
                )
            else:
                document_ids.add(document_id)

            try:
                page_number = int(page)
            except ValueError:
                page_number = 0
            if page_number <= 0 or str(page_number) != page:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "PAGE_INVALID",
                        "page must be a canonical positive integer",
                    )
                )

            source_path_valid = _safe_posix_path(source_path)
            if not source_path_valid:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "SOURCE_PATH_INVALID",
                        "source_path must be a workspace-relative POSIX path",
                    )
                )

            crop_path_valid = _safe_posix_path(crop_path)
            if not crop_path_valid:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "CROP_PATH_INVALID",
                        "crop_path must be a workspace-relative POSIX path",
                    )
                )

            hash_valid = _SHA256.fullmatch(expected_hash) is not None
            if not hash_valid:
                issues.append(
                    _issue(
                        row_number,
                        visual_id,
                        "SHA256_INVALID",
                        "sha256 must be a lowercase SHA-256 digest",
                    )
                )

            if root is not None and crop_path_valid and hash_valid:
                asset_issue = _asset_issue(
                    root,
                    row_number,
                    visual_id,
                    crop_path,
                    expected_hash,
                )
                if asset_issue is not None:
                    issues.append(asset_issue)

    ordered_issues = sorted(issues, key=_issue_sort_key)
    issue_counts = Counter(str(item["code"]) for item in ordered_issues)
    return {
        "format": "evidence-review/legacy-visual-inspection",
        "version": 1,
        "status": LEGACY_VISUAL_STATUS,
        "source_path": _source_label(manifest_path, root),
        "source_sha256": source_hash,
        "row_count": row_count,
        "header": list(LEGACY_VISUAL_HEADER),
        "identity_gaps": ["page_id", "revision_id"],
        "document_ids": sorted(document_ids),
        "issue_counts": {
            code: issue_counts[code] for code in sorted(issue_counts)
        },
        "issues": ordered_issues,
        "conversion_supported": False,
        "conversion_requirements": list(_CONVERSION_REQUIREMENTS),
    }
