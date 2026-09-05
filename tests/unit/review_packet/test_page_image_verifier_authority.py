from __future__ import annotations

import ast
from pathlib import Path

import evidence_review.review_packet.html_renderer as html_renderer
import evidence_review.review_packet.page_image_verifier as page_image_verifier


def _tree(module_file: str | None) -> ast.Module:
    assert module_file is not None
    return ast.parse(Path(module_file).read_text(encoding="utf-8"))


def test_page_image_verifier_does_not_import_renderer_private_helpers() -> None:
    tree = _tree(page_image_verifier.__file__)
    imported_private_helpers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "evidence_review.review_packet.html_renderer":
            continue
        imported_private_helpers.update(
            alias.name for alias in node.names if alias.name.startswith("_")
        )

    assert imported_private_helpers == set()


def test_html_renderer_contains_no_page_image_verifier_copy() -> None:
    tree = _tree(html_renderer.__file__)
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "_verified_page_image" not in function_names
    assert "hashlib" not in imported_modules
