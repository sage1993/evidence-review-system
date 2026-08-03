"""Safe rendering of registered generated Markdown documents."""
from __future__ import annotations

import importlib
from dataclasses import dataclass

from ansim_review.documentation_integrity.contract import (
    DocumentationIntegrityConfig,
    DocumentClassification,
    GeneratedDocumentConfig,
)

_MESSAGES = {
    "GENERATED_DOCUMENT_IMPORT_FAILED": (
        "Generated document module could not be imported."
    ),
    "GENERATED_DOCUMENT_CALLABLE_MISSING": (
        "Generated document callable is missing or invalid."
    ),
    "GENERATED_DOCUMENT_RENDER_FAILED": (
        "Generated document callable failed during rendering."
    ),
    "GENERATED_DOCUMENT_RESULT_INVALID": (
        "Generated document callable must return Markdown text."
    ),
    "GENERATED_DOCUMENT_PATH_DUPLICATE": (
        "Generated document virtual path is registered more than once."
    ),
}


@dataclass(frozen=True, slots=True)
class GeneratedDocument:
    path: str
    classification: DocumentClassification
    text: str
    generator_id: str


class GeneratedDocumentError(ValueError):
    """Stable generated-document failure without exception internals."""

    def __init__(self, code: str, config: GeneratedDocumentConfig) -> None:
        self.code = code
        self.path = config.virtual_path
        self.generator_id = config.id
        self.message = _MESSAGES[code]
        super().__init__(self.message)


def _render_one(config: GeneratedDocumentConfig) -> GeneratedDocument:
    module_name, callable_name = config.generator.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        raise GeneratedDocumentError(
            "GENERATED_DOCUMENT_IMPORT_FAILED",
            config,
        ) from None
    render = getattr(module, callable_name, None)
    if not callable(render):
        raise GeneratedDocumentError(
            "GENERATED_DOCUMENT_CALLABLE_MISSING",
            config,
        )
    try:
        result = render()
    except Exception:
        raise GeneratedDocumentError(
            "GENERATED_DOCUMENT_RENDER_FAILED",
            config,
        ) from None
    if not isinstance(result, str):
        raise GeneratedDocumentError(
            "GENERATED_DOCUMENT_RESULT_INVALID",
            config,
        )
    return GeneratedDocument(
        path=config.virtual_path,
        classification=config.classification,
        text=result,
        generator_id=config.id,
    )


def render_generated_documents(
    config: DocumentationIntegrityConfig,
) -> tuple[GeneratedDocument, ...]:
    """Render registered documents in configuration order."""
    seen_paths: set[str] = set()
    documents: list[GeneratedDocument] = []
    for registered in config.generated_documents:
        if registered.virtual_path in seen_paths:
            raise GeneratedDocumentError(
                "GENERATED_DOCUMENT_PATH_DUPLICATE",
                registered,
            )
        seen_paths.add(registered.virtual_path)
        documents.append(_render_one(registered))
    return tuple(documents)
