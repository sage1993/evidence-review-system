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


def test_page_cache_permission_is_not_reported_as_missing_or_stale(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        page_image_verifier,
        "verified_regular_file_below",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("access denied")),
    )

    try:
        page_image_verifier.read_verified_page_image(
            tmp_path,
            "REV-1",
            1,
            "a" * 64,
        )
    except ValueError as error:
        assert str(error).startswith("CACHE_NOT_READABLE:")
    else:
        raise AssertionError("permission-denied cache must fail with CACHE_NOT_READABLE")


def test_verify_review_page_images_reads_each_identity_once_in_first_use_order(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    source_a = "a" * 64
    source_b = "b" * 64
    calls: list[tuple[str, int, str]] = []

    def verified(revision_id: str, page_number: int, source_hash: str) -> object:
        return page_image_verifier.VerifiedPageImage(
            revision_id=revision_id,
            page_number=page_number,
            source_hash=source_hash,
            image_path=tmp_path / f"{revision_id}-{page_number}.png",
            image_sha256="c" * 64,
            image_bytes=b"png",
            pdf_width=100.0,
            pdf_height=200.0,
            origin_x=0.0,
            origin_y=0.0,
            rotation=0,
            box_kind="MEDIA_BOX",
        )

    pages = {
        ("REV-A", 1, source_a): verified("REV-A", 1, source_a),
        ("REV-B", 2, source_b): verified("REV-B", 2, source_b),
    }

    def fake_read(
        page_root: Path,
        revision_id: str,
        page_number: int,
        source_hash: str,
    ) -> object:
        assert page_root == tmp_path
        identity = (revision_id, page_number, source_hash)
        calls.append(identity)
        return pages[identity]

    monkeypatch.setattr(page_image_verifier, "read_verified_page_image", fake_read)  # type: ignore[attr-defined]
    citation_a = {
        "revision_id": "REV-A",
        "page_number": 1,
        "source_hash": source_a,
        "page_width": 100.0,
        "page_height": 200.0,
    }
    citation_b = {
        "revision_id": "REV-B",
        "page_number": 2,
        "source_hash": source_b,
        "page_width": 100.0,
        "page_height": 200.0,
    }
    model = {
        "claims": [
            {"citations": [citation_a, citation_b]},
            {"citations": [dict(citation_a)]},
        ]
    }

    result = page_image_verifier.verify_review_page_images(model, tmp_path)

    assert result == (pages[("REV-A", 1, source_a)], pages[("REV-B", 2, source_b)])
    assert calls == [("REV-A", 1, source_a), ("REV-B", 2, source_b)]
