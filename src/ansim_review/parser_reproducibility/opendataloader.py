"""Read-only decoding helpers for OpenDataLoader JSON artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeAlias

from ansim_review.parser_reproducibility.contract import JsonValue

JsonObject: TypeAlias = dict[str, JsonValue]
_CHILD_KEYS = ("kids", "list items", "list_items", "children")


@dataclass(frozen=True, slots=True)
class OpenDataLoaderArtifact:
    """Decoded raw parser payload and its authoritative page order."""

    raw_payload: JsonObject
    page_numbers: tuple[int, ...]
    page_count: int


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_value(value: object, field: str) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item, f"{field}[]") for item in value]
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field} keys must be strings")
            result[key] = _json_value(item, f"{field}.{key}")
        return result
    raise ValueError(f"{field} contains a non-JSON value")


def _positive_page(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _element_page_number(value: JsonObject) -> int | None:
    return _positive_page(value.get("page number", value.get("page_number")))


def _walk_objects(value: JsonValue) -> tuple[JsonObject, ...]:
    found: list[JsonObject] = []

    def walk(current: JsonValue) -> None:
        if isinstance(current, dict):
            found.append(current)
            for child in current.values():
                walk(child)
        elif isinstance(current, list):
            for child in current:
                walk(child)

    walk(value)
    return tuple(found)


def _declared_page_order(payload: JsonObject) -> tuple[int, ...]:
    pages = payload.get("pages")
    if isinstance(pages, list):
        order: list[int] = []
        for index, page in enumerate(pages):
            if not isinstance(page, dict):
                raise ValueError(f"pages[{index}] must be an object")
            number = _element_page_number(page)
            if number is None:
                raise ValueError(
                    f"pages[{index}] must declare a positive page number"
                )
            order.append(number)
        if order:
            if len(set(order)) != len(order):
                raise ValueError("pages contains duplicate page numbers")
            return tuple(order)

    order = []
    seen: set[int] = set()
    for item in _walk_objects(payload):
        page_number = _element_page_number(item)
        if page_number is not None and page_number not in seen:
            seen.add(page_number)
            order.append(page_number)
    return tuple(order)


def parser_page_count(
    payload: JsonObject,
    page_numbers: tuple[int, ...],
) -> int:
    """Return the declared parser page count with strict fallback behavior."""

    declared = payload.get("number of pages", payload.get("page_count"))
    count = _positive_page(declared)
    if declared is not None and count is None:
        raise ValueError("parser page count must be a positive integer")
    if count is None:
        if not page_numbers:
            raise ValueError("parser output does not declare a positive page count")
        count = max(page_numbers)
    if page_numbers and any(number > count for number in page_numbers):
        raise ValueError("parser element page exceeds declared page count")
    return count


def decode_opendataloader_json(data: bytes) -> OpenDataLoaderArtifact:
    """Decode OpenDataLoader JSON without modifying or normalizing evidence."""

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("OpenDataLoader JSON must be UTF-8") from exc
    try:
        decoded = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError("OpenDataLoader artifact must be valid JSON") from exc
    value = _json_value(decoded, "root")
    if not isinstance(value, dict):
        raise ValueError("OpenDataLoader artifact root must be an object")
    page_numbers = _declared_page_order(value)
    return OpenDataLoaderArtifact(
        raw_payload=value,
        page_numbers=page_numbers,
        page_count=parser_page_count(value, page_numbers),
    )


def child_keys() -> tuple[str, ...]:
    """Expose the parser child-key vocabulary used by ingestion and tests."""

    return _CHILD_KEYS
