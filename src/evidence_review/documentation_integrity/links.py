"""Offline validation for documentation links, paths, anchors, and URLs."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import unquote, urlsplit

from evidence_review.documentation_integrity.contract import (
    DocumentationFinding,
    DocumentClassification,
)
from evidence_review.documentation_integrity.markdown import (
    MarkdownLink,
    ParsedMarkdown,
    normalize_heading_anchor,
)

_HISTORICAL_MARKER = "> Document status: HISTORICAL RECORD"
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[/\\]")
_EXTERNAL_PREFIXES = ("https://", "http://", "ftp://", "//")


class LinkDocument(Protocol):
    @property
    def path(self) -> str: ...

    @property
    def classification(self) -> DocumentClassification: ...


@dataclass(frozen=True, slots=True)
class DocumentationIndex:
    classifications: Mapping[str, DocumentClassification]
    headings_by_path: Mapping[str, frozenset[str]]
    virtual_paths: frozenset[str]
    repository_root: Path | None = None


def _finding(
    document: LinkDocument,
    *,
    severity: str,
    code: str,
    line: int,
    column: int,
    target: str,
    message: str,
) -> DocumentationFinding:
    return DocumentationFinding(
        severity=severity,  # type: ignore[arg-type]
        code=code,
        document_path=document.path,
        line=line,
        column=column,
        target=target,
        message=message,
    )


def _external_finding(
    document: LinkDocument,
    target: str,
    line: int,
    column: int,
) -> DocumentationFinding | None:
    if not target.casefold().startswith(_EXTERNAL_PREFIXES):
        return None
    parsed = urlsplit(target)
    if parsed.scheme.casefold() == "https" and bool(parsed.netloc):
        return None
    return _finding(
        document,
        severity="WARNING",
        code="EXTERNAL_URL_SCHEME_INVALID",
        line=line,
        column=column,
        target=target,
        message="External URLs must use https:// with a non-empty host.",
    )


def _resolve_repository_path(
    document_path: str,
    target_path: str,
) -> tuple[str | None, str | None]:
    decoded = unquote(target_path)
    if "\\" in decoded:
        return None, "BACKSLASH_REPOSITORY_REFERENCE"
    if decoded.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(decoded):
        return None, "ABSOLUTE_REPOSITORY_PATH"
    if not decoded:
        return document_path, None
    stack = list(PurePosixPath(document_path).parent.parts)
    for component in decoded.split("/"):
        if component in ("", "."):
            continue
        if component == "..":
            if not stack:
                return None, "REPOSITORY_PATH_ESCAPE"
            stack.pop()
            continue
        stack.append(component)
    if not stack:
        return None, "REPOSITORY_PATH_ESCAPE"
    return PurePosixPath(*stack).as_posix(), None


def _path_error(
    document: LinkDocument,
    link: MarkdownLink,
    code: str,
) -> DocumentationFinding:
    messages = {
        "BACKSLASH_REPOSITORY_REFERENCE": (
            "Repository references must use forward slashes."
        ),
        "ABSOLUTE_REPOSITORY_PATH": (
            "Repository references must be relative to the containing document."
        ),
        "REPOSITORY_PATH_ESCAPE": (
            "Repository reference escapes the repository root."
        ),
    }
    return _finding(
        document,
        severity="ERROR",
        code=code,
        line=link.line,
        column=link.column,
        target=link.target,
        message=messages[code],
    )


def _root_for(document: LinkDocument, index: DocumentationIndex) -> Path | None:
    if index.repository_root is not None:
        return index.repository_root.resolve()
    filesystem_path = getattr(document, "filesystem_path", None)
    if not isinstance(filesystem_path, Path):
        return None
    root = filesystem_path.resolve()
    for _ in PurePosixPath(document.path).parts:
        root = root.parent
    return root


def _target_exists(
    target_path: str,
    document: LinkDocument,
    index: DocumentationIndex,
) -> bool:
    if target_path in index.virtual_paths:
        return True
    root = _root_for(document, index)
    if root is None:
        return target_path in index.classifications
    candidate = root / PurePosixPath(target_path)
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    if not resolved.is_relative_to(root):
        return False
    return resolved.exists()


def _validate_internal_link(
    document: LinkDocument,
    link: MarkdownLink,
    index: DocumentationIndex,
) -> tuple[DocumentationFinding, ...]:
    split = urlsplit(link.target)
    target_path, path_error = _resolve_repository_path(document.path, split.path)
    if path_error is not None:
        return (_path_error(document, link, path_error),)
    assert target_path is not None

    if document.classification == "HISTORICAL":
        return ()

    if not _target_exists(target_path, document, index):
        return (
            _finding(
                document,
                severity="ERROR",
                code="INTERNAL_LINK_TARGET_MISSING",
                line=link.line,
                column=link.column,
                target=link.target,
                message="Referenced repository target does not exist.",
            ),
        )

    findings: list[DocumentationFinding] = []
    fragment = unquote(split.fragment)
    if fragment:
        anchor = normalize_heading_anchor(fragment)
        headings = index.headings_by_path.get(target_path, frozenset())
        if anchor not in headings:
            findings.append(
                _finding(
                    document,
                    severity="ERROR",
                    code="INTERNAL_LINK_ANCHOR_MISSING",
                    line=link.line,
                    column=link.column,
                    target=link.target,
                    message="Referenced Markdown heading anchor does not exist.",
                )
            )
    if (
        index.classifications.get(target_path) == "HISTORICAL"
        and not link.label.startswith(("Historical:", "과거 기록:"))
    ):
        findings.append(
            _finding(
                document,
                severity="ERROR",
                code="CURRENT_TO_HISTORICAL_REFERENCE_UNMARKED",
                line=link.line,
                column=link.column,
                target=link.target,
                message="Current documents must explicitly label historical references.",
            )
        )
    return tuple(findings)


def _validate_link(
    document: LinkDocument,
    link: MarkdownLink,
    index: DocumentationIndex,
) -> tuple[DocumentationFinding, ...]:
    if _WINDOWS_ABSOLUTE_RE.match(link.target):
        return (_path_error(document, link, "ABSOLUTE_REPOSITORY_PATH"),)
    external = _external_finding(document, link.target, link.line, link.column)
    if external is not None:
        return (external,)
    split = urlsplit(link.target)
    if split.scheme or link.target.startswith("mailto:"):
        return ()
    return _validate_internal_link(document, link, index)


def validate_links(
    document: LinkDocument,
    parsed: ParsedMarkdown,
    index: DocumentationIndex,
) -> tuple[DocumentationFinding, ...]:
    """Validate one parsed document without network access."""
    findings: list[DocumentationFinding] = []
    for link in parsed.links:
        findings.extend(_validate_link(document, link, index))
    for raw_url in parsed.raw_urls:
        finding = _external_finding(
            document,
            raw_url.target,
            raw_url.line,
            raw_url.column,
        )
        if finding is not None:
            findings.append(finding)
    if (
        document.classification == "HISTORICAL"
        and parsed.first_non_empty_line != _HISTORICAL_MARKER
    ):
        findings.append(
            _finding(
                document,
                severity="WARNING",
                code="HISTORICAL_MARKER_MISSING",
                line=1,
                column=1,
                target="",
                message="Historical documents should declare their record status first.",
            )
        )
    return tuple(findings)
