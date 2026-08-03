"""Strict contracts for OpenDataLoader run authority and comparison policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, TypeAlias, cast

from ansim_review.contracts.identifiers import validate_identifier, validate_version

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
ParserKind: TypeAlias = Literal["opendataloader"]
NormalizationProfileName: TypeAlias = Literal["opendataloader-v1"]
PlatformFamily: TypeAlias = Literal["windows", "linux", "macos", "other"]

OPENDATALOADER_V1_ALLOWED_FIELDS = frozenset(
    {
        "$.metadata.parsed_at",
        "$.metadata.output_directory",
    }
)

_CONFIG_KEYS = frozenset(
    {
        "format",
        "version",
        "parser_kind",
        "adapter_version",
        "json_artifact_names",
        "markdown_artifact_names",
        "warning_sources",
        "normalization_profile",
        "allowed_nondeterministic_fields",
    }
)
_RUN_KEYS = frozenset(
    {
        "format",
        "version",
        "source_relative_path",
        "source_sha256",
        "source_size",
        "source_page_count",
        "document_id",
        "revision_id",
        "parser_kind",
        "parser_version",
        "adapter_version",
        "parser_configuration",
        "platform_family",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ReproducibilityConfig:
    """Repository-owned comparison policy for OpenDataLoader artifacts."""

    parser_kind: ParserKind
    adapter_version: int
    json_artifact_names: tuple[str, ...]
    markdown_artifact_names: tuple[str, ...]
    warning_sources: tuple[str, ...]
    normalization_profile: NormalizationProfileName
    allowed_nondeterministic_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParserRunMetadata:
    """Immutable parser execution identity stored beside raw artifacts."""

    source_relative_path: str
    source_sha256: str
    source_size: int
    source_page_count: int
    document_id: str
    revision_id: str
    parser_kind: ParserKind
    parser_version: str
    adapter_version: int
    parser_configuration: dict[str, JsonValue]
    platform_family: PlatformFamily


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_object(data: bytes, label: str) -> dict[str, object]:
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8 JSON") from exc
    try:
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _require_exact_keys(value: dict[str, object], expected: frozenset[str]) -> None:
    actual = frozenset(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise ValueError(f"unknown field: {unknown[0]}")
    if missing:
        raise ValueError(f"missing field: {missing[0]}")


def _require_literal(value: object, expected: object, field: str) -> None:
    if value != expected or type(value) is not type(expected):
        raise ValueError(f"unsupported {field}")


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _relative_posix_path(value: object, field: str) -> str:
    text = _nonempty_string(value, field)
    if "\\" in text:
        raise ValueError(f"{field} must not contain a backslash")
    if ":" in text:
        raise ValueError(f"{field} must not contain a drive or scheme")
    if text.startswith("/"):
        raise ValueError(f"{field} must be relative")
    components = text.split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ValueError(f"{field} contains an unsafe path component")
    path = PurePosixPath(text)
    if path.is_absolute():
        raise ValueError(f"{field} must be relative")
    return path.as_posix()


def _path_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    decoded = tuple(
        _relative_posix_path(item, f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(decoded)) != len(decoded):
        raise ValueError(f"{field} contains a duplicate entry")
    return decoded


def _decode_json_value(value: object, field: str) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return cast(JsonScalar, value)
    if isinstance(value, list):
        return [_decode_json_value(item, f"{field}[]") for item in value]
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field} keys must be strings")
            result[key] = _decode_json_value(item, f"{field}.{key}")
        return result
    raise ValueError(f"{field} contains an unsupported JSON value")


def _decode_parser_kind(value: object) -> ParserKind:
    if value != "opendataloader":
        raise ValueError("unsupported parser kind")
    return "opendataloader"


def _decode_profile(value: object) -> NormalizationProfileName:
    if value != "opendataloader-v1":
        raise ValueError("unsupported normalization profile")
    return "opendataloader-v1"


def _decode_allowlist(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("allowed_nondeterministic_fields must be an array")
    result: list[str] = []
    for index, item in enumerate(value):
        field = _nonempty_string(
            item,
            f"allowed_nondeterministic_fields[{index}]",
        )
        if ".." in field:
            raise ValueError("recursive JSON paths are prohibited")
        if "*" in field:
            raise ValueError("wildcard JSON paths are prohibited")
        if field not in OPENDATALOADER_V1_ALLOWED_FIELDS:
            raise ValueError(f"unsupported normalization field: {field}")
        result.append(field)
    if len(set(result)) != len(result):
        raise ValueError(
            "allowed_nondeterministic_fields contains a duplicate entry"
        )
    return tuple(result)


def decode_reproducibility_config(data: bytes) -> ReproducibilityConfig:
    """Decode the exact version 1 repository comparison configuration."""

    payload = _load_object(data, "parser reproducibility configuration")
    _require_exact_keys(payload, _CONFIG_KEYS)
    _require_literal(
        payload["format"],
        "evidence-review/parser-reproducibility-config",
        "configuration format",
    )
    _require_literal(payload["version"], 1, "configuration version")
    adapter_version = _positive_int(
        payload["adapter_version"],
        "adapter_version",
    )
    if adapter_version != 1:
        raise ValueError("unsupported adapter version")
    return ReproducibilityConfig(
        parser_kind=_decode_parser_kind(payload["parser_kind"]),
        adapter_version=adapter_version,
        json_artifact_names=_path_tuple(
            payload["json_artifact_names"],
            "json_artifact_names",
        ),
        markdown_artifact_names=_path_tuple(
            payload["markdown_artifact_names"],
            "markdown_artifact_names",
        ),
        warning_sources=_path_tuple(
            payload["warning_sources"],
            "warning_sources",
        ),
        normalization_profile=_decode_profile(payload["normalization_profile"]),
        allowed_nondeterministic_fields=_decode_allowlist(
            payload["allowed_nondeterministic_fields"]
        ),
    )


def decode_parser_run_metadata(data: bytes) -> ParserRunMetadata:
    """Decode immutable OpenDataLoader run authority without rewriting it."""

    payload = _load_object(data, "parser run metadata")
    _require_exact_keys(payload, _RUN_KEYS)
    _require_literal(
        payload["format"],
        "evidence-review/opendataloader-parser-run",
        "parser run format",
    )
    _require_literal(payload["version"], 1, "parser run version")
    source_sha256 = _nonempty_string(
        payload["source_sha256"],
        "source_sha256",
    )
    if not _SHA256.fullmatch(source_sha256):
        raise ValueError(
            "source_sha256 must be 64 lowercase hexadecimal characters"
        )
    document_id = validate_identifier(payload["document_id"], "document_id")
    revision_id = validate_identifier(payload["revision_id"], "revision_id")
    expected_revision_id = f"{document_id}-{source_sha256[:12]}"
    if revision_id != expected_revision_id:
        raise ValueError(
            "revision_id does not match document_id and source_sha256"
        )
    adapter_version = _positive_int(
        payload["adapter_version"],
        "adapter_version",
    )
    if adapter_version != 1:
        raise ValueError("unsupported adapter version")
    configuration = _decode_json_value(
        payload["parser_configuration"],
        "parser_configuration",
    )
    if not isinstance(configuration, dict):
        raise ValueError("parser_configuration must be an object")
    platform = payload["platform_family"]
    if not isinstance(platform, str) or platform not in {
        "windows",
        "linux",
        "macos",
        "other",
    }:
        raise ValueError("unsupported platform_family")
    return ParserRunMetadata(
        source_relative_path=_relative_posix_path(
            payload["source_relative_path"],
            "source_relative_path",
        ),
        source_sha256=source_sha256,
        source_size=_positive_int(payload["source_size"], "source_size"),
        source_page_count=_positive_int(
            payload["source_page_count"],
            "source_page_count",
        ),
        document_id=document_id,
        revision_id=revision_id,
        parser_kind=_decode_parser_kind(payload["parser_kind"]),
        parser_version=validate_version(
            payload["parser_version"],
            "parser_version",
        ),
        adapter_version=adapter_version,
        parser_configuration=configuration,
        platform_family=cast(PlatformFamily, platform),
    )
