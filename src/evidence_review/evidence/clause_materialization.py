"""Deterministically derive legal clauses and lineage from parser elements."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_ARTICLE_RE = re.compile(r"^\s*(제\d+조(?:의\d+)?)(?:\s*\(([^)]*)\))?\s*(.*)$", re.DOTALL)
_OPERATION_RE = re.compile(r"^\s*(\d+(?:-\d+){1,3})\.\s*(.*)$", re.DOTALL)
_PARAGRAPH_CHARS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_PARAGRAPH_INDEX = {value: index + 1 for index, value in enumerate(_PARAGRAPH_CHARS)}
_PARAGRAPH_RE = re.compile(f"([{_PARAGRAPH_CHARS}])")


@dataclass(frozen=True, slots=True)
class DerivedClause:
    id: str
    revision_id: str
    title: str
    raw_text: str
    normalized_text: str
    structural_key: str
    source_element_ids: tuple[str, ...]
    article_key: str | None = None


@dataclass(frozen=True, slots=True)
class DerivedLink:
    id: str
    source_id: str
    target_id: str
    relation_type: str


@dataclass(frozen=True, slots=True)
class ClauseMaterialization:
    clauses: tuple[DerivedClause, ...]
    links: tuple[DerivedLink, ...]


def _normalize(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFC", " ".join(value.split()))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24].upper()
    return f"{prefix}-{digest}"


def _paragraph_parts(value: str) -> tuple[tuple[int, str], ...]:
    matches = tuple(_PARAGRAPH_RE.finditer(value))
    if not matches:
        return ()
    parts: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        paragraph = _normalize(value[match.start():end])
        if paragraph:
            parts.append((_PARAGRAPH_INDEX[match.group(1)], paragraph))
    return tuple(parts)


def _element_value(row: Mapping[str, object], key: str, default: object = "") -> object:
    return row[key] if key in row else default


def derive_legal_clauses(elements: Sequence[Mapping[str, object]]) -> ClauseMaterialization:
    """Derive generic article/paragraph and operational-standard clauses.

    The input is citation-grade parser output. Unrecognized prose is never promoted
    to a standalone clause; it only extends the immediately preceding recognized
    structural clause in the same revision.
    """
    ordered = sorted(
        elements,
        key=lambda row: (
            _normalize(_element_value(row, "revision_id")),
            int(_element_value(row, "page_number", 0) or 0),
            int(_element_value(row, "parser_order", 0) or 0),
            _normalize(_element_value(row, "id")),
        ),
    )

    builders: list[dict[str, object]] = []
    current_revision: str | None = None
    current_article: str | None = None
    current_article_title: str | None = None
    active_builder: dict[str, object] | None = None

    def start_clause(
        *,
        revision_id: str,
        structural_key: str,
        title: str,
        text: str,
        source_id: str,
        article_key: str | None,
    ) -> dict[str, object]:
        builder: dict[str, object] = {
            "revision_id": revision_id,
            "structural_key": structural_key,
            "title": title,
            "parts": [text],
            "source_ids": [source_id],
            "article_key": article_key,
        }
        builders.append(builder)
        return builder

    for row in ordered:
        revision_id = _normalize(_element_value(row, "revision_id"))
        element_id = _normalize(_element_value(row, "id"))
        raw_text = _normalize(_element_value(row, "normalized_text")) or _normalize(
            _element_value(row, "raw_text")
        )
        if not revision_id or not element_id or not raw_text:
            continue
        if revision_id != current_revision:
            current_revision = revision_id
            current_article = None
            current_article_title = None
            active_builder = None

        article_match = _ARTICLE_RE.match(raw_text)
        if article_match:
            current_article = article_match.group(1)
            heading = _normalize(article_match.group(2))
            current_article_title = (
                f"{current_article}({heading})" if heading else current_article
            )
            active_builder = None
            remainder = _normalize(article_match.group(3))
            paragraph_source = remainder
            if remainder:
                paragraph_parts = _paragraph_parts(paragraph_source)
                if paragraph_parts:
                    for paragraph_number, paragraph_text in paragraph_parts:
                        active_builder = start_clause(
                            revision_id=revision_id,
                            structural_key=f"{current_article}#{paragraph_number}",
                            title=f"{current_article_title} 제{paragraph_number}항",
                            text=paragraph_text,
                            source_id=element_id,
                            article_key=current_article,
                        )
                else:
                    active_builder = start_clause(
                        revision_id=revision_id,
                        structural_key=current_article,
                        title=current_article_title,
                        text=remainder,
                        source_id=element_id,
                        article_key=current_article,
                    )
            continue

        if current_article is not None:
            paragraph_parts = _paragraph_parts(raw_text)
            if paragraph_parts:
                for paragraph_number, paragraph_text in paragraph_parts:
                    active_builder = start_clause(
                        revision_id=revision_id,
                        structural_key=f"{current_article}#{paragraph_number}",
                        title=(
                            f"{current_article_title or current_article} "
                            f"제{paragraph_number}항"
                        ),
                        text=paragraph_text,
                        source_id=element_id,
                        article_key=current_article,
                    )
                continue

        operation_match = _OPERATION_RE.match(raw_text)
        if operation_match:
            current_article = None
            current_article_title = None
            structural_key = operation_match.group(1)
            remainder = _normalize(operation_match.group(2))
            active_builder = start_clause(
                revision_id=revision_id,
                structural_key=structural_key,
                title=structural_key,
                text=remainder or raw_text,
                source_id=element_id,
                article_key=None,
            )
            continue

        if active_builder is not None:
            parts = active_builder["parts"]
            source_ids = active_builder["source_ids"]
            assert isinstance(parts, list)
            assert isinstance(source_ids, list)
            parts.append(raw_text)
            if element_id not in source_ids:
                source_ids.append(element_id)

    clauses: list[DerivedClause] = []
    for builder in builders:
        parts = tuple(str(value) for value in builder["parts"])
        source_ids = tuple(str(value) for value in builder["source_ids"])
        normalized_text = _normalize(" ".join(parts))
        revision_id = str(builder["revision_id"])
        structural_key = str(builder["structural_key"])
        clause_id = _stable_id(
            "AUTO-CLAUSE",
            revision_id,
            structural_key,
            normalized_text,
        )
        clauses.append(
            DerivedClause(
                id=clause_id,
                revision_id=revision_id,
                title=str(builder["title"]),
                raw_text=normalized_text,
                normalized_text=normalized_text,
                structural_key=structural_key,
                source_element_ids=source_ids,
                article_key=(
                    None if builder["article_key"] is None else str(builder["article_key"])
                ),
            )
        )

    links: list[DerivedLink] = []
    for clause in clauses:
        for source_id in clause.source_element_ids:
            links.append(
                DerivedLink(
                    id=_stable_id("AUTO-LINK", clause.id, source_id, "source_element"),
                    source_id=clause.id,
                    target_id=source_id,
                    relation_type="source_element",
                )
            )

    by_article: dict[tuple[str, str], list[DerivedClause]] = {}
    for clause in clauses:
        if clause.article_key is not None:
            by_article.setdefault((clause.revision_id, clause.article_key), []).append(clause)
    for siblings in by_article.values():
        for left, right in zip(siblings, siblings[1:], strict=False):
            links.append(
                DerivedLink(
                    id=_stable_id("AUTO-LINK", left.id, right.id, "next_sibling"),
                    source_id=left.id,
                    target_id=right.id,
                    relation_type="next_sibling",
                )
            )
            links.append(
                DerivedLink(
                    id=_stable_id("AUTO-LINK", right.id, left.id, "previous_sibling"),
                    source_id=right.id,
                    target_id=left.id,
                    relation_type="previous_sibling",
                )
            )
            left_source = left.source_element_ids[-1]
            right_source = right.source_element_ids[0]
            if left_source != right_source:
                links.append(
                    DerivedLink(
                        id=_stable_id(
                            "AUTO-LINK", left_source, right_source, "next_sibling"
                        ),
                        source_id=left_source,
                        target_id=right_source,
                        relation_type="next_sibling",
                    )
                )
                links.append(
                    DerivedLink(
                        id=_stable_id(
                            "AUTO-LINK", right_source, left_source, "previous_sibling"
                        ),
                        source_id=right_source,
                        target_id=left_source,
                        relation_type="previous_sibling",
                    )
                )

    return ClauseMaterialization(clauses=tuple(clauses), links=tuple(links))
