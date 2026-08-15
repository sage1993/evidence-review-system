"""Traceable deterministic retrieval query normalization."""
from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

QueryOrigin = Literal["primary", "approved_synonym", "llm", "user"]


@dataclass(frozen=True, slots=True)
class QueryTerm:
    text: str
    origin: QueryOrigin
    search_request_ids: tuple[str, ...] = ()
    issue_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    primary: str
    terms: tuple[QueryTerm, ...]


def normalize_text(value: str) -> str:
    """Normalize Unicode to NFC and collapse all whitespace runs."""
    return unicodedata.normalize("NFC", " ".join(value.split()))


def _normalized_synonyms(
    primary: str,
    synonym_manifest: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    synonyms: set[str] = set()
    for key, values in synonym_manifest.items():
        if normalize_text(key) != primary:
            continue
        for value in values:
            normalized = normalize_text(value)
            if normalized:
                synonyms.add(normalized)
    return tuple(sorted(synonyms))


def _lineage_ids(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field}[{index}] must be a non-empty string")
        items.append(item)
    return tuple(sorted(set(items)))


def _merge_term(existing: QueryTerm, incoming: QueryTerm) -> QueryTerm:
    priority = {"primary": 0, "approved_synonym": 1, "user": 2, "llm": 3}
    origin = existing.origin
    if priority[incoming.origin] < priority[existing.origin]:
        origin = incoming.origin
    return QueryTerm(
        text=existing.text,
        origin=origin,
        search_request_ids=tuple(
            sorted(set(existing.search_request_ids).union(incoming.search_request_ids))
        ),
        issue_ids=tuple(sorted(set(existing.issue_ids).union(incoming.issue_ids))),
    )


def normalize_query(
    primary: str,
    expansions: Sequence[Mapping[str, object]],
    synonym_manifest: Mapping[str, Sequence[str]],
) -> NormalizedQuery:
    """Build a deterministic query while keeping trusted origins and lineage separate."""
    normalized_primary = normalize_text(primary)
    if not normalized_primary:
        raise ValueError("primary query must not be empty")

    by_text: dict[str, QueryTerm] = {
        normalized_primary: QueryTerm(normalized_primary, "primary")
    }
    for text in _normalized_synonyms(normalized_primary, synonym_manifest):
        if text != normalized_primary:
            by_text[text] = QueryTerm(text, "approved_synonym")

    for index, expansion in enumerate(expansions):
        origin = expansion.get("origin")
        if origin not in {"llm", "user"}:
            raise ValueError(f"unsupported expansion origin: {origin}")
        text_value = expansion.get("text")
        if not isinstance(text_value, str):
            raise ValueError(f"expansions[{index}].text must be a string")
        normalized = normalize_text(text_value)
        if not normalized:
            continue
        normalized_origin: QueryOrigin = "user" if origin == "user" else "llm"
        incoming = QueryTerm(
            text=normalized,
            origin=normalized_origin,
            search_request_ids=_lineage_ids(
                expansion.get("search_request_ids"),
                f"expansions[{index}].search_request_ids",
            ),
            issue_ids=_lineage_ids(
                expansion.get("issue_ids"),
                f"expansions[{index}].issue_ids",
            ),
        )
        existing = by_text.get(normalized)
        by_text[normalized] = incoming if existing is None else _merge_term(existing, incoming)

    priority = {"primary": 0, "approved_synonym": 1, "user": 2, "llm": 3}
    terms = tuple(
        sorted(
            by_text.values(),
            key=lambda item: (priority[item.origin], item.text),
        )
    )
    return NormalizedQuery(primary=normalized_primary, terms=terms)
