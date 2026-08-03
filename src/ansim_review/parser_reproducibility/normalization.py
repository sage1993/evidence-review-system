"""Closed, comparison-only normalization for parser artifacts."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.contract import (
    JsonValue,
    ReproducibilityConfig,
)


@dataclass(frozen=True, slots=True)
class AppliedNormalization:
    path: str
    kind: str


@dataclass(frozen=True, slots=True)
class NormalizedJson:
    value: JsonValue
    canonical_bytes: bytes
    sha256: str
    applied: tuple[AppliedNormalization, ...]


@dataclass(frozen=True, slots=True)
class NormalizedMarkdown:
    text: str
    canonical_bytes: bytes
    sha256: str
    applied: tuple[AppliedNormalization, ...]


def _root_forms(run_root: Path) -> tuple[str, ...]:
    resolved = run_root.resolve()
    values = {
        str(resolved),
        resolved.as_posix(),
        str(resolved).replace("/", "\\"),
    }
    return tuple(sorted((value for value in values if value), key=len, reverse=True))


def _path_parts(path: str) -> tuple[str, ...]:
    if not path.startswith("$."):
        raise ValueError(f"unsupported normalization path: {path}")
    parts = tuple(path[2:].split("."))
    if not parts or any(not part for part in parts):
        raise ValueError(f"unsupported normalization path: {path}")
    return parts


def _replace_object_path(
    root: JsonValue,
    path: str,
    replacement: str,
) -> bool:
    current = root
    parts = _path_parts(path)
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    current[parts[-1]] = replacement
    return True


def normalize_json_artifact(
    payload: JsonValue,
    config: ReproducibilityConfig,
    run_root: Path,
) -> NormalizedJson:
    """Normalize only explicitly approved operational metadata in memory."""

    value = copy.deepcopy(payload)
    applied: list[AppliedNormalization] = []
    for path in config.allowed_nondeterministic_fields:
        if path == "$.metadata.parsed_at":
            if _replace_object_path(value, path, "<NONDETERMINISTIC>"):
                applied.append(AppliedNormalization(path, "EXECUTION_TIMESTAMP"))
            continue
        if path == "$.metadata.output_directory":
            if _replace_object_path(value, path, "<RUN_ROOT>"):
                applied.append(AppliedNormalization(path, "RUN_ROOT"))
            continue
        raise ValueError(f"unsupported normalization path: {path}")

    def replace_run_paths(current: JsonValue, path: str) -> JsonValue:
        if isinstance(current, str):
            replaced = current
            for root_form in _root_forms(run_root):
                replaced = replaced.replace(root_form, "<RUN_ROOT>")
            replaced = replaced.replace("<RUN_ROOT>\\", "<RUN_ROOT>/")
            if replaced != current:
                applied.append(AppliedNormalization(path, "RUN_LOCAL_PATH"))
            return replaced
        if isinstance(current, list):
            return [
                replace_run_paths(item, f"{path}[{index}]")
                for index, item in enumerate(current)
            ]
        if isinstance(current, dict):
            return {
                key: replace_run_paths(item, f"{path}.{key}")
                for key, item in current.items()
            }
        return current

    value = replace_run_paths(value, "$")
    encoded = dump_bytes(value)
    return NormalizedJson(
        value=value,
        canonical_bytes=encoded,
        sha256=hashlib.sha256(encoded).hexdigest().upper(),
        applied=tuple(sorted(set(applied), key=lambda item: (item.path, item.kind))),
    )


def normalize_markdown_artifact(
    data: bytes,
    run_root: Path,
) -> NormalizedMarkdown:
    """Normalize encoding, line endings, and approved run-root references only."""

    had_bom = data.startswith(b"\xef\xbb\xbf")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("OpenDataLoader Markdown must be UTF-8") from exc
    text = decoded.replace("\r\n", "\n").replace("\r", "\n")
    applied: list[AppliedNormalization] = []
    if had_bom:
        applied.append(AppliedNormalization("$", "UTF8_BOM"))
    if "\r" in decoded:
        applied.append(AppliedNormalization("$", "LINE_ENDINGS"))
    for root_form in _root_forms(run_root):
        replaced = text.replace(root_form, "<RUN_ROOT>")
        if replaced != text:
            applied.append(AppliedNormalization("$", "RUN_ROOT"))
        text = replaced
    replaced = text.replace("<RUN_ROOT>\\", "<RUN_ROOT>/")
    if replaced != text:
        applied.append(AppliedNormalization("$", "PATH_SEPARATOR"))
    text = replaced
    encoded = text.encode("utf-8")
    return NormalizedMarkdown(
        text=text,
        canonical_bytes=encoded,
        sha256=hashlib.sha256(encoded).hexdigest().upper(),
        applied=tuple(sorted(set(applied), key=lambda item: (item.path, item.kind))),
    )
