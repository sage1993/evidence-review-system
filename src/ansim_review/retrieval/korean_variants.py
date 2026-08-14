"""Bounded deterministic Korean query variants for offline retrieval."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ansim_review.retrieval.query import normalize_text

_NUMERIC_TOKEN = re.compile(r"^(?P<number>\d[\d,]*)(?P<unit>제곱미터|㎡)?$")
_TRAILING_PUNCTUATION = ".,!?;:()[]{}<>\"'“”‘’"
_SUFFIXES = (
    "이어야",
    "여야",
    "에서",
    "으로",
    "한다",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "로",
    "와",
    "과",
    "도",
)
_CONCEPT_VARIANTS: dict[str, tuple[str, ...]] = {
    "면적": ("면적", "연면적", "연건축면적"),
    "연면적": ("면적", "연면적", "연건축면적"),
    "연건축면적": ("면적", "연면적", "연건축면적"),
    "이상": ("이상",),
    "이하": ("이하",),
}


_GENERIC_TRAILING_TERMS = frozenset(
    {
        "\uae30\uc900",
        "\uc124\uce58\uae30\uc900",
        "\uad00\uacc4\ubc95\ub839",
        "\uc548\uc804",
        "\uc2dc\uc124",
        "\uaddc\uc815",
        "\uc870\uac74",
    }
)
_ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff")
_HANGUL = re.compile(r"[\uac00-\ud7a3]")


def _search_normalized(value: str) -> str:
    normalized = normalize_text(value)
    for marker in _ZERO_WIDTH:
        normalized = normalized.replace(marker, "")
    return " ".join(normalized.split())


def _hangul_token(value: str) -> bool:
    return bool(value) and _HANGUL.search(value) is not None


def derive_korean_compound_variants(primary: str) -> tuple[str, ...]:
    """Derive a small phrase/compound-only search expansion."""
    normalized = _search_normalized(primary)
    if not normalized:
        raise ValueError("primary query must not be empty")

    tokens = [_strip_suffix(token) for token in normalized.split()]
    while tokens and tokens[-1] in _GENERIC_TRAILING_TERMS:
        tokens.pop()
    tokens = [token for token in tokens if token]
    if not tokens:
        return ()

    if len(tokens) == 1:
        token = tokens[0]
        if len(token) < 2 or not _hangul_token(token):
            return ()
        return (token,)

    if len(tokens) > 3 or not all(_hangul_token(token) for token in tokens):
        return ()

    spaced = " ".join(tokens)
    compact = "".join(tokens)
    return _ordered_unique([spaced, compact])

@dataclass(frozen=True, slots=True)
class GroupedQueryVariants:
    """Bounded retrieval terms derived from one normalized question."""

    entity: tuple[str, ...]
    numeric: tuple[str, ...]
    concept: tuple[str, ...]


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _strip_suffix(token: str) -> str:
    clean = token.strip(_TRAILING_PUNCTUATION)
    for suffix in _SUFFIXES:
        if clean.endswith(suffix):
            stem = clean[: -len(suffix)]
            if len(stem) >= 2:
                return stem
    return clean


def _numeric_variants(token: str) -> tuple[str, ...]:
    match = _NUMERIC_TOKEN.fullmatch(token)
    if match is None:
        return ()
    number = match.group("number")
    unit = match.group("unit")
    plain = number.replace(",", "")
    grouped = f"{int(plain):,}"
    values = [plain, grouped]
    if unit:
        values.extend((f"{plain}{unit}", f"{grouped}{unit}"))
    return _ordered_unique(values)


def derive_korean_query_variants(primary: str) -> GroupedQueryVariants:
    """Derive bounded entity, numeric, and concept terms without token-OR."""
    normalized = normalize_text(primary)
    if not normalized:
        raise ValueError("primary query must not be empty")

    stripped_tokens = tuple(_strip_suffix(token) for token in normalized.split())

    boundary: int | None = None
    numeric: list[str] = []
    concept: list[str] = []
    for index, token in enumerate(stripped_tokens):
        number_terms = _numeric_variants(token)
        concept_terms = _CONCEPT_VARIANTS.get(token, ())
        if boundary is None and (number_terms or concept_terms):
            boundary = index
        numeric.extend(number_terms)
        concept.extend(concept_terms)

    entity: list[str] = []
    if boundary is not None and boundary > 0:
        subject_tokens = [token for token in stripped_tokens[:boundary] if token]
        if subject_tokens:
            spaced = " ".join(subject_tokens)
            entity.append(spaced)
            compact = "".join(subject_tokens)
            if compact != spaced:
                entity.append(compact)

    return GroupedQueryVariants(
        entity=_ordered_unique(entity),
        numeric=_ordered_unique(numeric),
        concept=_ordered_unique(concept),
    )
