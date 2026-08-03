"""Fail-closed comparison of two verified OpenDataLoader parser runs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, TypeAlias

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.contract import (
    JsonValue,
    ReproducibilityConfig,
)
from ansim_review.parser_reproducibility.normalization import (
    AppliedNormalization,
    NormalizedJson,
    NormalizedMarkdown,
    normalize_json_artifact,
    normalize_markdown_artifact,
)
from ansim_review.parser_reproducibility.run_manifest import LoadedParserRun
from ansim_review.parser_reproducibility.warnings import ParserWarning

ReproducibilityStatus: TypeAlias = Literal[
    "BYTE_IDENTICAL",
    "SEMANTICALLY_IDENTICAL",
    "MISMATCH",
    "ENVIRONMENT_MISMATCH",
    "PARSER_FAILED",
]
DifferenceKind: TypeAlias = Literal[
    "PAGE_COUNT_CHANGED",
    "PAGE_ORDER_CHANGED",
    "ELEMENT_ADDED",
    "ELEMENT_REMOVED",
    "ELEMENT_TYPE_CHANGED",
    "TEXT_CONTENT_CHANGED",
    "TABLE_STRUCTURE_CHANGED",
    "TABLE_CELL_VALUE_CHANGED",
    "IMAGE_OCCURRENCE_CHANGED",
    "BOUNDING_BOX_CHANGED",
    "RELATIONSHIP_CHANGED",
    "MARKDOWN_CONTENT_CHANGED",
    "WARNING_ADDED",
    "WARNING_REMOVED",
    "WARNING_CHANGED",
    "UNAPPROVED_NONDETERMINISM",
]


@dataclass(frozen=True, slots=True)
class ParsedRun:
    loaded: LoadedParserRun
    normalized_json: NormalizedJson
    normalized_markdown: NormalizedMarkdown


@dataclass(frozen=True, slots=True)
class ParsedRunPair:
    left: ParsedRun
    right: ParsedRun


@dataclass(frozen=True, slots=True)
class StructuralDifference:
    kind: DifferenceKind
    artifact: str
    page_number: int | None
    path: str
    left_hash: str | None
    right_hash: str | None


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    status: ReproducibilityStatus
    canonical_equivalent: bool | None
    left_json_sha256: str
    right_json_sha256: str
    left_markdown_sha256: str
    right_markdown_sha256: str
    applied_normalizations: tuple[AppliedNormalization, ...]
    differences: tuple[StructuralDifference, ...]


def parse_loaded_run(
    loaded: LoadedParserRun,
    config: ReproducibilityConfig,
) -> ParsedRun:
    return ParsedRun(
        loaded=loaded,
        normalized_json=normalize_json_artifact(
            loaded.artifact.raw_payload,
            config,
            loaded.run_root,
        ),
        normalized_markdown=normalize_markdown_artifact(
            loaded.markdown_bytes,
            loaded.run_root,
        ),
    )


def _value_hash(value: JsonValue) -> str:
    return hashlib.sha256(dump_bytes(value)).hexdigest().upper()


def _difference_kind(path: str, left: JsonValue, right: JsonValue) -> DifferenceKind:
    lowered = path.casefold()
    final = path.rsplit(".", 1)[-1].casefold()
    if "bounding box" in lowered or "bbox" in lowered:
        return "BOUNDING_BOX_CHANGED"
    if any(token in lowered for token in (".rows", ".cells", "table")):
        if final in {"content", "text", "value"}:
            return "TABLE_CELL_VALUE_CHANGED"
        return "TABLE_STRUCTURE_CHANGED"
    if any(token in lowered for token in ("image", "visual", "figure")):
        return "IMAGE_OCCURRENCE_CHANGED"
    if final in {"previous", "next", "parent", "children", "kids"}:
        return "RELATIONSHIP_CHANGED"
    if final == "type":
        return "ELEMENT_TYPE_CHANGED"
    if final in {"content", "text", "raw_text"}:
        return "TEXT_CONTENT_CHANGED"
    if isinstance(left, list) and isinstance(right, list):
        return "TABLE_STRUCTURE_CHANGED" if "table" in lowered else "UNAPPROVED_NONDETERMINISM"
    return "UNAPPROVED_NONDETERMINISM"


def _page_from_path(path: str) -> int | None:
    marker = "$.pages["
    if not path.startswith(marker):
        return None
    closing = path.find("]", len(marker))
    if closing < 0:
        return None
    try:
        return int(path[len(marker) : closing]) + 1
    except ValueError:
        return None


def _recursive_differences(
    left: JsonValue,
    right: JsonValue,
    path: str = "$",
) -> list[StructuralDifference]:
    if type(left) is not type(right):
        return [
            StructuralDifference(
                kind=_difference_kind(path, left, right),
                artifact="document.json",
                page_number=_page_from_path(path),
                path=path,
                left_hash=_value_hash(left),
                right_hash=_value_hash(right),
            )
        ]
    if isinstance(left, dict) and isinstance(right, dict):
        differences: list[StructuralDifference] = []
        for key in sorted(set(left) | set(right)):
            child_path = f"{path}.{key}"
            if key not in left:
                differences.append(
                    StructuralDifference(
                        kind="ELEMENT_ADDED",
                        artifact="document.json",
                        page_number=_page_from_path(child_path),
                        path=child_path,
                        left_hash=None,
                        right_hash=_value_hash(right[key]),
                    )
                )
            elif key not in right:
                differences.append(
                    StructuralDifference(
                        kind="ELEMENT_REMOVED",
                        artifact="document.json",
                        page_number=_page_from_path(child_path),
                        path=child_path,
                        left_hash=_value_hash(left[key]),
                        right_hash=None,
                    )
                )
            else:
                differences.extend(
                    _recursive_differences(left[key], right[key], child_path)
                )
        return differences
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        common = min(len(left), len(right))
        for index in range(common):
            differences.extend(
                _recursive_differences(
                    left[index],
                    right[index],
                    f"{path}[{index}]",
                )
            )
        for index in range(common, len(left)):
            differences.append(
                StructuralDifference(
                    kind="ELEMENT_REMOVED",
                    artifact="document.json",
                    page_number=_page_from_path(path),
                    path=f"{path}[{index}]",
                    left_hash=_value_hash(left[index]),
                    right_hash=None,
                )
            )
        for index in range(common, len(right)):
            differences.append(
                StructuralDifference(
                    kind="ELEMENT_ADDED",
                    artifact="document.json",
                    page_number=_page_from_path(path),
                    path=f"{path}[{index}]",
                    left_hash=None,
                    right_hash=_value_hash(right[index]),
                )
            )
        return differences
    if left == right:
        return []
    return [
        StructuralDifference(
            kind=_difference_kind(path, left, right),
            artifact="document.json",
            page_number=_page_from_path(path),
            path=path,
            left_hash=_value_hash(left),
            right_hash=_value_hash(right),
        )
    ]


def _warning_key(warning: ParserWarning) -> tuple[object, ...]:
    return (
        warning.code,
        warning.normalized_message_sha256,
        warning.page_number,
    )


def _warning_differences(
    left: tuple[ParserWarning, ...],
    right: tuple[ParserWarning, ...],
) -> list[StructuralDifference]:
    left_by_id = {warning.warning_id: warning for warning in left}
    right_by_id = {warning.warning_id: warning for warning in right}
    removed = [left_by_id[key] for key in sorted(set(left_by_id) - set(right_by_id))]
    added = [right_by_id[key] for key in sorted(set(right_by_id) - set(left_by_id))]
    differences: list[StructuralDifference] = []

    consumed_added: set[str] = set()
    for warning in removed:
        counterpart = next(
            (
                candidate
                for candidate in added
                if candidate.warning_id not in consumed_added
                and candidate.code == warning.code
                and candidate.normalized_message_sha256
                == warning.normalized_message_sha256
            ),
            None,
        )
        if counterpart is not None:
            consumed_added.add(counterpart.warning_id)
            differences.append(
                StructuralDifference(
                    kind="WARNING_CHANGED",
                    artifact="warnings",
                    page_number=counterpart.page_number,
                    path=warning.warning_id,
                    left_hash=warning.warning_id,
                    right_hash=counterpart.warning_id,
                )
            )
            continue
        differences.append(
            StructuralDifference(
                kind="WARNING_REMOVED",
                artifact="warnings",
                page_number=warning.page_number,
                path=warning.warning_id,
                left_hash=warning.warning_id,
                right_hash=None,
            )
        )
    for warning in added:
        if warning.warning_id in consumed_added:
            continue
        differences.append(
            StructuralDifference(
                kind="WARNING_ADDED",
                artifact="warnings",
                page_number=warning.page_number,
                path=warning.warning_id,
                left_hash=None,
                right_hash=warning.warning_id,
            )
        )
    return differences


def difference_sort_key(difference: StructuralDifference) -> tuple[object, ...]:
    return (
        difference.artifact,
        -1 if difference.page_number is None else difference.page_number,
        difference.path,
        difference.kind,
        difference.left_hash or "",
        difference.right_hash or "",
    )


def _environment_matches(pair: ParsedRunPair, config: ReproducibilityConfig) -> bool:
    left = pair.left.loaded.manifest
    right = pair.right.loaded.manifest
    return (
        left.source_sha256 == right.source_sha256
        and left.parser_kind == right.parser_kind == config.parser_kind
        and left.parser_version == right.parser_version
        and left.adapter_version == right.adapter_version == config.adapter_version
        and left.configuration_sha256 == right.configuration_sha256
        and left.source_page_count == right.source_page_count
        and left.parser_page_count == right.parser_page_count
    )


def compare_parser_runs(
    pair: ParsedRunPair,
    config: ReproducibilityConfig,
) -> ComparisonResult:
    """Compare two verified runs and select one exact status."""

    left = pair.left
    right = pair.right
    applied = tuple(
        sorted(
            set(left.normalized_json.applied)
            | set(right.normalized_json.applied)
            | set(left.normalized_markdown.applied)
            | set(right.normalized_markdown.applied),
            key=lambda item: (item.path, item.kind),
        )
    )
    base = {
        "left_json_sha256": left.normalized_json.sha256,
        "right_json_sha256": right.normalized_json.sha256,
        "left_markdown_sha256": left.normalized_markdown.sha256,
        "right_markdown_sha256": right.normalized_markdown.sha256,
        "applied_normalizations": applied,
    }
    if not _environment_matches(pair, config):
        return ComparisonResult(
            status="ENVIRONMENT_MISMATCH",
            canonical_equivalent=None,
            differences=(),
            **base,
        )

    warning_differences = _warning_differences(
        left.loaded.warnings,
        right.loaded.warnings,
    )
    raw_equal = (
        left.loaded.json_bytes == right.loaded.json_bytes
        and left.loaded.markdown_bytes == right.loaded.markdown_bytes
        and not warning_differences
    )
    if raw_equal:
        return ComparisonResult(
            status="BYTE_IDENTICAL",
            canonical_equivalent=True,
            differences=(),
            **base,
        )

    differences: list[StructuralDifference] = []
    if left.loaded.artifact.page_count != right.loaded.artifact.page_count:
        differences.append(
            StructuralDifference(
                kind="PAGE_COUNT_CHANGED",
                artifact="document.json",
                page_number=None,
                path="$.page_count",
                left_hash=str(left.loaded.artifact.page_count),
                right_hash=str(right.loaded.artifact.page_count),
            )
        )
    if left.loaded.artifact.page_numbers != right.loaded.artifact.page_numbers:
        differences.append(
            StructuralDifference(
                kind="PAGE_ORDER_CHANGED",
                artifact="document.json",
                page_number=None,
                path="$.pages",
                left_hash=_value_hash(list(left.loaded.artifact.page_numbers)),
                right_hash=_value_hash(list(right.loaded.artifact.page_numbers)),
            )
        )
    differences.extend(
        _recursive_differences(
            left.normalized_json.value,
            right.normalized_json.value,
        )
    )
    if (
        left.normalized_markdown.canonical_bytes
        != right.normalized_markdown.canonical_bytes
    ):
        differences.append(
            StructuralDifference(
                kind="MARKDOWN_CONTENT_CHANGED",
                artifact="document.md",
                page_number=None,
                path="$",
                left_hash=left.normalized_markdown.sha256,
                right_hash=right.normalized_markdown.sha256,
            )
        )
    differences.extend(warning_differences)
    ordered = tuple(sorted(set(differences), key=difference_sort_key))
    if not ordered:
        return ComparisonResult(
            status="SEMANTICALLY_IDENTICAL",
            canonical_equivalent=True,
            differences=(),
            **base,
        )
    return ComparisonResult(
        status="MISMATCH",
        canonical_equivalent=False,
        differences=ordered,
        **base,
    )
