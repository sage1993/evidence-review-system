"""Registered generated Markdown rendering tests."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest

from evidence_review.contracts.formats import DOCUMENTATION_INTEGRITY_CONFIG_FORMAT
from evidence_review.documentation_integrity.contract import (
    DocumentationIntegrityConfig,
    GeneratedDocumentConfig,
)
from evidence_review.documentation_integrity.generated import (
    GeneratedDocumentError,
    render_generated_documents,
)
from evidence_review.packaging.codex_bundle import render_validation_document


def _config(*documents: GeneratedDocumentConfig) -> DocumentationIntegrityConfig:
    return DocumentationIntegrityConfig(
        format=DOCUMENTATION_INTEGRITY_CONFIG_FORMAT,
        version=1,
        current_roots=(),
        historical_roots=(),
        current_overrides=(),
        historical_overrides=(),
        generated_documents=documents,
    )


def _document(
    generator: str,
    *,
    document_id: str = "GENERATED_TEST",
    virtual_path: str = "generated/TEST.md",
) -> GeneratedDocumentConfig:
    return GeneratedDocumentConfig(
        id=document_id,
        generator=generator,
        virtual_path=virtual_path,
        classification="CURRENT",
    )


def test_missing_generator_module_is_stable_error() -> None:
    with pytest.raises(GeneratedDocumentError) as captured:
        render_generated_documents(
            _config(_document("missing_documentation_module:render"))
        )
    assert captured.value.code == "GENERATED_DOCUMENT_IMPORT_FAILED"
    assert captured.value.generator_id == "GENERATED_TEST"
    assert "missing_documentation_module" not in captured.value.message


def test_missing_callable_is_stable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("test_generated_missing_callable")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(GeneratedDocumentError) as captured:
        render_generated_documents(
            _config(_document(f"{module.__name__}:render"))
        )
    assert captured.value.code == "GENERATED_DOCUMENT_CALLABLE_MISSING"


def test_generator_exception_is_stable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("test_generated_exception")

    def render() -> str:
        raise RuntimeError("nondeterministic internal detail")

    module.render = render  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(GeneratedDocumentError) as captured:
        render_generated_documents(
            _config(_document(f"{module.__name__}:render"))
        )
    assert captured.value.code == "GENERATED_DOCUMENT_RENDER_FAILED"
    assert "nondeterministic" not in captured.value.message


def test_non_string_result_is_stable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("test_generated_invalid_result")
    module.render = lambda: b"markdown"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(GeneratedDocumentError) as captured:
        render_generated_documents(
            _config(_document(f"{module.__name__}:render"))
        )
    assert captured.value.code == "GENERATED_DOCUMENT_RESULT_INVALID"


def test_duplicate_virtual_path_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = ModuleType("test_generated_duplicate")
    module.render = lambda: "# Generated\n"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    first = _document(f"{module.__name__}:render")
    second = _document(
        f"{module.__name__}:render",
        document_id="GENERATED_SECOND",
    )
    with pytest.raises(GeneratedDocumentError) as captured:
        render_generated_documents(_config(first, second))
    assert captured.value.code == "GENERATED_DOCUMENT_PATH_DUPLICATE"


def test_successful_render_preserves_registered_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("test_generated_success")
    module.render = lambda: "# Generated\n"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)

    rendered = render_generated_documents(
        _config(_document(f"{module.__name__}:render"))
    )

    assert len(rendered) == 1
    assert rendered[0].path == "generated/TEST.md"
    assert rendered[0].classification == "CURRENT"
    assert rendered[0].text == "# Generated\n"
    assert rendered[0].generator_id == "GENERATED_TEST"


def test_codex_validation_document_contains_full_offline_sequence() -> None:
    text = render_validation_document()
    assert "python -m evidence_review --help" in text
    assert "python -m evidence_review source-batch --help" in text
    assert "python -m evidence_review rules --help" in text
    assert "python -m evidence_review documentation validate --help" in text
    assert "python -m compileall -q src" in text
    assert "\r" not in text
