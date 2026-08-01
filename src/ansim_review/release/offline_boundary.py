"""Release-time enforcement for the shared application offline policy."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import cast

from ansim_review.offline_policy import (
    APPLICATION_OFFLINE_GUARD,
    POLICY_VERSION,
)
from ansim_review.offline_scanner import scan_source_tree


def resolve_manifest_member(root: Path, value: object) -> Path:
    """Resolve a safe manifest-relative member below *root*."""
    if not isinstance(value, str) or not value:
        raise ValueError("manifest path must be a non-empty string")
    parsed = PurePosixPath(value)
    first = parsed.parts[0] if parsed.parts else ""
    if (
        parsed.is_absolute()
        or not parsed.parts
        or ".." in parsed.parts
        or "\\" in value
        or ":" in first
    ):
        raise ValueError(f"manifest path escapes root: {value}")
    resolved_root = root.resolve()
    candidate = root.joinpath(*parsed.parts).resolve(strict=False)
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"manifest path escapes root: {value}")
    return candidate


def _walk_manifest_paths(value: object) -> Iterator[str]:
    if isinstance(value, Mapping):
        payload = cast(Mapping[object, object], value)
        for key, item in payload.items():
            if key == "path" and isinstance(item, str):
                yield item
            else:
                yield from _walk_manifest_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _walk_manifest_paths(item)


def validate_manifest_path_containment(manifest_path: Path) -> tuple[Path, ...]:
    """Validate every declared manifest `path` before any member is read."""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid release manifest: {manifest_path}") from error
    root = manifest_path.parent
    return tuple(
        resolve_manifest_member(root, value)
        for value in _walk_manifest_paths(payload)
    )


def source_policy_checks(workspace: Path) -> tuple[str, ...]:
    """Return stable shared-policy source findings for the packaged runtime tree."""
    source_root = workspace / "src" / "ansim_review"
    if not source_root.is_dir():
        return ("offline_source_root:missing",)
    findings = scan_source_tree(source_root)
    if not findings:
        return (
            f"offline_policy_version:{POLICY_VERSION}",
            f"offline_assurance:{APPLICATION_OFFLINE_GUARD}",
            "offline_source_scan:pass",
        )
    return tuple(
        "offline_source_scan:"
        f"{finding.path}:{finding.line}:{finding.kind}:{finding.symbol}"
        for finding in findings
    )
