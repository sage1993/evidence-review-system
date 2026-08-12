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


def normalize_query(
    primary: str,
    expansions: Sequence[Mapping[str, object]],
    synonym_manifest: Mapping[str, Sequence[str]],
) -> NormalizedQuery:
    """Build a deterministic query while keeping trusted origins separate."""
    normalized_primary = normalize_text(primary)
    if not normalized_primary:
        raise ValueError("primary query must not be empty")

    by_text: dict[str, QueryTerm] = {
        normalized_primary: QueryTerm(normalized_primary, "primary")
    }
    for text in _normalized_synonyms(normalized_primary, synonym_manifest):
        if text != normalized_primary:
            by_text[text] = QueryTerm(text, "approved_synonym")

    llm_terms: set[str] = set()
    for index, expansion in enumerate(expansions):
        origin = expansion.get("origin")
        if origin not in {"llm", "user"}:
            raise ValueError(f"unsupported expansion origin: {origin}")
        text_value = expansion.get("text")
        if not isinstance(text_value, str):
            raise ValueError(f"expansions[{index}].text must be a string")
        normalized = normalize_text(text_value)
        if normalized:
            llm_terms.add(normalized)
    for text in sorted(llm_terms):
        if text not in by_text:
            by_text[text] = QueryTerm(text, "llm")

    priority = {"primary": 0, "approved_synonym": 1, "user": 2, "llm": 3}
    terms = tuple(
        sorted(
            by_text.values(),
            key=lambda item: (priority[item.origin], item.text),
        )
    )
    return NormalizedQuery(primary=normalized_primary, terms=terms)
