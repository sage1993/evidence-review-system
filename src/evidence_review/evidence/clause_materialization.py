"""Deterministically derive legal clauses and lineage from parser elements."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

_ARTICLE_RE = re.compile(
    r"^\s*(제\d+조(?:의\d+)?)(?:\s*\(([^)]*)\))?\s*(.*)$",
    re.DOTALL,
)
_OPERATION_RE = re.compile(r"^\s*(\d+(?:-\d+){1,3})\.\s*(.*)$", re.DOTALL)
_OPERATION_ALPHA_DOT_RE = re.compile(r"^\s*([가-힣])\.\s*(.*)$", re.DOTALL)
_OPERATION_NUMBER_PAREN_RE = re.compile(r"^\s*(\d+)\)\s*(.*)$", re.DOTALL)
_OPERATION_ALPHA_PAREN_RE = re.compile(r"^\s*([가-힣])\)\s*(.*)$", re.DOTALL)
_PARAGRAPH_CHARS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_PARAGRAPH_INDEX = {value: index + 1 for index, value in enumerate(_PARAGRAPH_CHARS)}
_PARAGRAPH_RE = re.compile(f"([{_PARAGRAPH_CHARS}])")
_PARAGRAPH_REFERENCE_RE = re.compile(r"제(\d+)항")


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


def _order_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24].upper()}"


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


def _element_value(
    row: Mapping[str, object],
    key: str,
    default: object = "",
) -> object:
    return row[key] if key in row else default


def derive_legal_clauses(
    elements: Sequence[Mapping[str, object]],
) -> ClauseMaterialization:
    """Derive generic article/paragraph and operational-standard clauses.

    Parser elements remain citation-grade source truth. Only recognized legal or
    operational structure is promoted to semantic clauses; plain text may extend
    a recognized structure but is never promoted independently.
    """
    ordered = sorted(
        elements,
        key=lambda row: (
            _normalize(_element_value(row, "revision_id")),
            _order_int(_element_value(row, "page_number", 0)),
            _order_int(_element_value(row, "parser_order", 0)),
            _normalize(_element_value(row, "id")),
        ),
    )

    builders: list[dict[str, object]] = []
    current_revision: str | None = None
    current_article: str | None = None
    current_article_title: str | None = None
    operation_root: str | None = None
    operation_alpha: str | None = None
    operation_number: str | None = None
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

    def start_operational_leaf(
        *,
        path: tuple[str, ...],
        remainder: str,
        revision_id: str,
        element_id: str,
        raw_text: str,
    ) -> dict[str, object]:
        structural_key = "/".join(path)
        text = remainder or raw_text
        return start_clause(
            revision_id=revision_id,
            structural_key=structural_key,
            title=f"{structural_key} {remainder}".strip(),
            text=text,
            source_id=element_id,
            article_key=None,
        )

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
            operation_root = None
            operation_alpha = None
            operation_number = None
            active_builder = None

        article_match = _ARTICLE_RE.match(raw_text)
        if article_match:
            current_article = article_match.group(1)
            heading = _normalize(article_match.group(2))
            current_article_title = (
                f"{current_article}({heading})" if heading else current_article
            )
            operation_root = None
            operation_alpha = None
            operation_number = None
            active_builder = None
            remainder = _normalize(article_match.group(3))
            if remainder:
                paragraph_parts = _paragraph_parts(remainder)
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
            operation_root = operation_match.group(1)
            operation_alpha = None
            operation_number = None
            remainder = _normalize(operation_match.group(2))
            active_builder = start_operational_leaf(
                path=(operation_root,),
                remainder=remainder,
                revision_id=revision_id,
                element_id=element_id,
                raw_text=raw_text,
            )
            continue

        if current_article is None and operation_root is not None:
            alpha_dot_match = _OPERATION_ALPHA_DOT_RE.match(raw_text)
            if alpha_dot_match:
                operation_alpha = alpha_dot_match.group(1)
                operation_number = None
                active_builder = start_operational_leaf(
                    path=(operation_root, operation_alpha),
                    remainder=_normalize(alpha_dot_match.group(2)),
                    revision_id=revision_id,
                    element_id=element_id,
                    raw_text=raw_text,
                )
                continue

            number_match = _OPERATION_NUMBER_PAREN_RE.match(raw_text)
            if number_match:
                operation_number = number_match.group(1)
                path = (
                    (operation_root, operation_number)
                    if operation_alpha is None
                    else (operation_root, operation_alpha, operation_number)
                )
                active_builder = start_operational_leaf(
                    path=path,
                    remainder=_normalize(number_match.group(2)),
                    revision_id=revision_id,
                    element_id=element_id,
                    raw_text=raw_text,
                )
                continue

            alpha_paren_match = _OPERATION_ALPHA_PAREN_RE.match(raw_text)
            if alpha_paren_match:
                leaf = alpha_paren_match.group(1)
                path_parts = [operation_root]
                if operation_alpha is not None:
                    path_parts.append(operation_alpha)
                if operation_number is not None:
                    path_parts.append(operation_number)
                path_parts.append(leaf)
                active_builder = start_operational_leaf(
                    path=tuple(path_parts),
                    remainder=_normalize(alpha_paren_match.group(2)),
                    revision_id=revision_id,
                    element_id=element_id,
                    raw_text=raw_text,
                )
                continue

        if current_article is not None and active_builder is None:
            active_builder = start_clause(
                revision_id=revision_id,
                structural_key=current_article,
                title=current_article_title or current_article,
                text=raw_text,
                source_id=element_id,
                article_key=current_article,
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
        parts_value = cast(list[object], builder["parts"])
        source_ids_value = cast(list[object], builder["source_ids"])
        parts = tuple(str(value) for value in parts_value)
        source_ids = tuple(str(value) for value in source_ids_value)
        normalized_text = _normalize(" ".join(parts))
        revision_id = str(builder["revision_id"])
        structural_key = str(builder["structural_key"])
        clause_id = _stable_id(
            "AUTO-CLAUSE",
            revision_id,
            structural_key,
            normalized_text,
        )
        article_key_value = builder["article_key"]
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
                    None if article_key_value is None else str(article_key_value)
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
            by_article.setdefault(
                (clause.revision_id, clause.article_key),
                [],
            ).append(clause)

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

        paragraph_by_number = {
            int(clause.structural_key.rsplit("#", 1)[1]): clause
            for clause in siblings
            if "#" in clause.structural_key
            and clause.structural_key.rsplit("#", 1)[1].isdigit()
        }
        for source_clause in siblings:
            referenced_numbers = {
                int(match.group(1))
                for match in _PARAGRAPH_REFERENCE_RE.finditer(
                    source_clause.normalized_text
                )
            }
            for paragraph_number in sorted(referenced_numbers):
                target_clause = paragraph_by_number.get(paragraph_number)
                if target_clause is None or target_clause.id == source_clause.id:
                    continue
                links.append(
                    DerivedLink(
                        id=_stable_id(
                            "AUTO-LINK",
                            source_clause.id,
                            target_clause.id,
                            "cited_clause",
                        ),
                        source_id=source_clause.id,
                        target_id=target_clause.id,
                        relation_type="cited_clause",
                    )
                )
                for source_id in source_clause.source_element_ids:
                    for target_id in target_clause.source_element_ids:
                        if source_id == target_id:
                            continue
                        links.append(
                            DerivedLink(
                                id=_stable_id(
                                    "AUTO-LINK",
                                    source_id,
                                    target_id,
                                    "cited_clause",
                                ),
                                source_id=source_id,
                                target_id=target_id,
                                relation_type="cited_clause",
                            )
                        )

    return ClauseMaterialization(
        clauses=tuple(clauses),
        links=tuple(links),
    )
