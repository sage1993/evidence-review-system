"""Two-pass orchestration for repository-wide documentation integrity."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ansim_review.documentation_integrity.classification import (
    DocumentClassificationError,
)
from ansim_review.documentation_integrity.commands import (
    normalize_command_block,
    validate_command_lines,
)
from ansim_review.documentation_integrity.contract import (
    DocumentClassification,
    DocumentationFinding,
    DocumentationIntegrityReport,
    decode_config_bytes,
)
from ansim_review.documentation_integrity.discovery import (
    DocumentDiscoveryError,
    discover_repository_documents,
)
from ansim_review.documentation_integrity.generated import (
    GeneratedDocumentError,
    render_generated_documents,
)
from ansim_review.documentation_integrity.links import (
    DocumentationIndex,
    validate_links,
)
from ansim_review.documentation_integrity.markdown import (
    ParsedMarkdown,
    normalize_heading_anchor,
    parse_markdown,
)


class DocumentationAuthorityError(ValueError):
    """Raised when repository authority bytes cannot be trusted or read."""


class ValidationDocument(Protocol):
    path: str
    classification: DocumentClassification


@dataclass(frozen=True, slots=True)
class _ParsedDocument:
    document: ValidationDocument
    parsed: ParsedMarkdown


def _config_path(root: Path, config_path: Path) -> str:
    try:
        return config_path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return config_path.name or "documentation-integrity.json"


def _finding(
    *,
    severity: str,
    code: str,
    document_path: str,
    target: str,
    message: str,
    line: int = 1,
    column: int = 1,
) -> DocumentationFinding:
    return DocumentationFinding(
        severity=severity,  # type: ignore[arg-type]
        code=code,
        document_path=document_path,
        line=line,
        column=column,
        target=target,
        message=message,
    )


def _empty_failure(
    code: str,
    path: str,
    target: str,
    message: str,
) -> DocumentationIntegrityReport:
    return DocumentationIntegrityReport(
        current_documents=(),
        historical_documents=(),
        generated_documents=(),
        findings=(
            _finding(
                severity="ERROR",
                code=code,
                document_path=path,
                target=target,
                message=message,
            ),
        ),
    )


def _read_repository_document(document: ValidationDocument) -> str:
    filesystem_path = getattr(document, "filesystem_path", None)
    if not isinstance(filesystem_path, Path):
        raise OSError("repository document path is unavailable")
    return filesystem_path.read_text(encoding="utf-8")


def _duplicate_heading_findings(
    document: ValidationDocument,
    parsed: ParsedMarkdown,
) -> tuple[DocumentationFinding, ...]:
    findings: list[DocumentationFinding] = []
    seen: set[str] = set()
    for heading in parsed.headings:
        base = normalize_heading_anchor(heading.text)
        if base in seen:
            findings.append(
                _finding(
                    severity="WARNING",
                    code="DUPLICATE_HEADING_ANCHOR",
                    document_path=document.path,
                    line=heading.line,
                    column=heading.column,
                    target=base,
                    message=(
                        "Document contains a duplicate normalized heading anchor."
                    ),
                )
            )
        seen.add(base)
    return tuple(findings)


def validate_documentation(
    repository_root: Path,
    config_path: Path,
) -> DocumentationIntegrityReport:
    """Validate repository and generated Markdown without writing files."""
    try:
        root = repository_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise DocumentationAuthorityError(
            "repository root is missing or unreadable"
        ) from error
    if not root.is_dir():
        raise DocumentationAuthorityError("repository root must be a directory")
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    try:
        config_bytes = resolved_config.read_bytes()
    except (FileNotFoundError, OSError) as error:
        raise DocumentationAuthorityError(
            "documentation authority configuration is missing or unreadable"
        ) from error
    config_document_path = _config_path(root, resolved_config)
    try:
        config = decode_config_bytes(config_bytes)
    except ValueError:
        return _empty_failure(
            "CONFIG_INVALID",
            config_document_path,
            config_document_path,
            "Documentation integrity configuration is invalid.",
        )

    try:
        repository_documents = discover_repository_documents(root, config)
    except (DocumentClassificationError, DocumentDiscoveryError) as error:
        return _empty_failure(
            error.code,
            error.path,
            error.path,
            "Repository documentation discovery failed closed.",
        )

    findings: list[DocumentationFinding] = []
    try:
        generated_documents = render_generated_documents(config)
    except GeneratedDocumentError as error:
        generated_documents = ()
        findings.append(
            _finding(
                severity="ERROR",
                code=error.code,
                document_path=error.path,
                target=error.generator_id,
                message=error.message,
            )
        )

    parsed_documents: list[_ParsedDocument] = []
    for document in repository_documents:
        try:
            text = _read_repository_document(document)
        except (UnicodeDecodeError, OSError):
            findings.append(
                _finding(
                    severity="ERROR",
                    code="DOCUMENT_READ_FAILED",
                    document_path=document.path,
                    target=document.path,
                    message="Repository Markdown could not be read as UTF-8 text.",
                )
            )
            continue
        parsed_documents.append(_ParsedDocument(document, parse_markdown(text)))
    for document in generated_documents:
        parsed_documents.append(_ParsedDocument(document, parse_markdown(document.text)))

    classifications = {
        item.document.path: item.document.classification for item in parsed_documents
    }
    headings_by_path = {
        item.document.path: frozenset(
            heading.anchor for heading in item.parsed.headings
        )
        for item in parsed_documents
    }
    index = DocumentationIndex(
        classifications=classifications,
        headings_by_path=headings_by_path,
        virtual_paths=frozenset(document.path for document in generated_documents),
        repository_root=root,
    )

    for item in parsed_documents:
        findings.extend(_duplicate_heading_findings(item.document, item.parsed))
        findings.extend(validate_links(item.document, item.parsed, index))
        for block in item.parsed.command_blocks:
            findings.extend(
                validate_command_lines(
                    normalize_command_block(block),
                    root,
                    item.document,
                )
            )

    return DocumentationIntegrityReport(
        current_documents=tuple(
            document.path
            for document in repository_documents
            if document.classification == "CURRENT"
        ),
        historical_documents=tuple(
            document.path
            for document in repository_documents
            if document.classification == "HISTORICAL"
        ),
        generated_documents=tuple(document.path for document in generated_documents),
        findings=findings,
    )
