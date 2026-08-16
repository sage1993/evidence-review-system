"""Deterministic extraction of explicit Korean legal cross-references."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_REFERENCE_RE = re.compile(
    r"「(?P<title>[^」]+)」"
    r"(?:\s*(?P<article>제\d+조(?:의\d+)?))?"
    r"(?:\s*(?P<paragraph>제\d+항))?"
    r"(?:[^「」\n]{0,40}?(?P<annex>별표\s*\d+))?"
)


@dataclass(frozen=True, slots=True)
class LegalReference:
    authority_title: str
    article: str | None
    paragraph: str | None
    annex: str | None


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    return normalized or None


def extract_legal_references(text: str) -> tuple[LegalReference, ...]:
    """Extract explicit ``「authority」 article/paragraph/annex`` references.

    The extractor deliberately ignores unquoted inferred authorities. This keeps
    reference traversal evidence-bound and prevents the parser from inventing a
    legal source that was not written in the document.
    """
    normalized_text = unicodedata.normalize("NFC", text)
    references: list[LegalReference] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for match in _REFERENCE_RE.finditer(normalized_text):
        title = _normalize(match.group("title"))
        if title is None:
            continue
        article = _normalize(match.group("article"))
        paragraph = _normalize(match.group("paragraph"))
        annex = _normalize(match.group("annex"))
        if annex is not None:
            annex = re.sub(r"\s+", " ", annex)
        key = (title, article, paragraph, annex)
        if key in seen:
            continue
        seen.add(key)
        references.append(
            LegalReference(
                authority_title=title,
                article=article,
                paragraph=paragraph,
                annex=annex,
            )
        )
    return tuple(references)
