from __future__ import annotations

import re
from pathlib import Path


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 exact match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, replacement: str, *, label: str) -> str:
    result, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 regex match, found {count}")
    return result


def patch_html_renderer() -> None:
    path = Path("src/evidence_review/review_packet/html_renderer.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "import hashlib\n", "", label="html hashlib import")
    text = replace_once(
        text,
        "from evidence_review.contracts.legacy_formats import LEGACY_PAGE_IMAGE_FORMAT\n",
        "",
        label="html legacy format import",
    )
    text = replace_once(
        text,
        "from evidence_review.review_packet.icons import icon_svg\n",
        "from evidence_review.review_packet.icons import icon_svg\n"
        "from evidence_review.review_packet.page_image_verifier import (\n"
        "    VerifiedPageImage,\n"
        "    verify_review_page_images,\n"
        ")\n",
        label="html verifier import",
    )
    text = replace_once(
        text,
        '_GEOMETRY_TOLERANCE = 0.5\n_PAGE_IMAGE_FORMAT = "evidence-review/page-image"\n\n',
        "",
        label="html verifier constants",
    )
    text = regex_once(
        text,
        r"\ndef _positive_number\(.*?(?=\ndef _bbox)",
        "\n",
        label="html duplicate positive-number helper",
    )
    text = regex_once(
        text,
        r"\ndef _verified_page_image\(.*?(?=\ndef _citation_identity)",
        "\n",
        label="html duplicate verifier",
    )
    new_page_assets = '''
def _page_assets(
    verified_pages: Sequence[VerifiedPageImage],
) -> dict[tuple[str, int, str], tuple[str, _PageAsset]]:
    """Project already-verified pages into renderer-only data URIs."""
    assets: dict[tuple[str, int, str], tuple[str, _PageAsset]] = {}
    for index, verified in enumerate(verified_pages, start=1):
        identity = (
            verified.revision_id,
            verified.page_number,
            verified.source_hash,
        )
        if identity in assets:
            raise ValueError("duplicate verified page image identity")
        assets[identity] = (
            f"page-{index}",
            _PageAsset(
                data_uri="data:image/png;base64,"
                + base64.b64encode(verified.image_bytes).decode("ascii"),
                pdf_width=verified.pdf_width,
                pdf_height=verified.pdf_height,
                rotation=verified.rotation,
                origin_x=verified.origin_x,
                origin_y=verified.origin_y,
                box_kind=verified.box_kind,
            ),
        )
    return assets

'''
    text = regex_once(
        text,
        r"\ndef _page_assets\(.*?(?=\ndef _viewer_documents)",
        new_page_assets,
        label="html page asset projection",
    )
    text = replace_once(
        text,
        "    assets = _page_assets(claims, page_image_root)\n",
        "    verified_pages = verify_review_page_images(model, page_image_root)\n"
        "    assets = _page_assets(verified_pages)\n",
        label="html render verifier call",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_case_visual_projection() -> None:
    path = Path("src/evidence_review/review_packet/case_visual_projection.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from evidence_review.drawing_review.visual_pages import (\n"
        "    VisualPageAsset,\n"
        "    load_visual_page_tiles,\n"
        ")\n",
        "from evidence_review.drawing_review.visual_pages import (\n"
        "    VisualPageAsset,\n"
        "    load_visual_page_tiles,\n"
        ")\n"
        "from evidence_review.filesystem_trust import verified_regular_file_below\n",
        label="case trust import",
    )
    replacement = '''def _resolve_visual_raster_path(
    workspace_root: Path,
    attachment_id: str,
    page_number: int,
    expected_sha256: str,
) -> Path:
    """Resolve an exact regular raster below one of the trusted CASE cache roots."""
    filename = f"page-{page_number:04d}.png"
    found_regular = False
    for cache_name in (_CASE_PDF_CACHE_DIR, _CASE_IMAGE_CACHE_DIR):
        cache_root = workspace_root / cache_name
        try:
            path = verified_regular_file_below(
                cache_root,
                (attachment_id, filename),
                field="case visual raster",
            )
        except FileNotFoundError:
            continue
        found_regular = True
        if hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256:
            return path
    if found_regular:
        raise ValueError("case visual raster hash mismatch")
    raise FileNotFoundError(
        workspace_root
        / _CASE_PDF_CACHE_DIR
        / attachment_id
        / filename
    )


'''
    text = regex_once(
        text,
        r"def _resolve_visual_raster_path\(.*?(?=def _page_tile_documents)",
        replacement,
        label="case raster resolver",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_local_server() -> None:
    path = Path("src/evidence_review/review_packet/local_server.py")
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "import stat\n", "", label="local server stat import")
    text = replace_once(
        text,
        "from evidence_review.contracts.identifiers import validate_identifier\n",
        "from evidence_review.contracts.identifiers import validate_identifier\n"
        "from evidence_review.filesystem_trust import (\n"
        "    verified_regular_directory,\n"
        "    verified_regular_file_below,\n"
        ")\n",
        label="local server trust import",
    )
    text = replace_once(
        text,
        "_REPARSE_POINT_ATTRIBUTE = 0x400\n",
        "",
        label="local server reparse constant",
    )
    text = regex_once(
        text,
        r"\ndef _is_reparse_point\(.*?(?=\ndef _validated_workspace_root)",
        "\n",
        label="local server reparse helper",
    )
    workspace_replacement = '''def _validated_workspace_root(workspace_root: Path) -> Path:
    try:
        return verified_regular_directory(workspace_root, field="workspace_root")
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ValueError("workspace_root must be an existing regular directory") from error


'''
    text = regex_once(
        text,
        r"def _validated_workspace_root\(.*?(?=def _validated_tokens)",
        workspace_replacement,
        label="local server workspace root",
    )
    child_replacement = '''def _regular_child(root: Path, *parts: str, final_is_file: bool) -> Path | None:
    try:
        verified_root = verified_regular_directory(root, field="workspace root")
        if final_is_file:
            return verified_regular_file_below(
                verified_root,
                parts,
                field="protected artifact",
            )
        candidate = verified_regular_directory(
            verified_root.joinpath(*parts),
            field="protected directory",
        )
        candidate.relative_to(verified_root)
        return candidate
    except (FileNotFoundError, OSError, ValueError):
        return None


'''
    text = regex_once(
        text,
        r"def _regular_child\(.*?(?=def _strict_object)",
        child_replacement,
        label="local server regular child",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_case_visual_test() -> None:
    path = Path("tests/unit/review_packet/test_case_visual_projection.py")
    text = path.read_text(encoding="utf-8")
    marker = "def test_projection_rejects_case_raster_symlink_escape"
    if marker in text:
        return
    addition = '''\n\ndef test_projection_rejects_case_raster_symlink_escape(tmp_path: Path) -> None:
    view_model, workspace = _fixture(tmp_path)
    raster = workspace / "case-page-images" / "ATT-VISUAL-1" / "page-0001.png"
    outside = tmp_path / "outside.png"
    outside.write_bytes(raster.read_bytes())
    raster.unlink()
    try:
        raster.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"case raster symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        build_case_visual_projection(view_model, workspace_root=workspace)
'''
    path.write_text(text.rstrip() + addition + "\n", encoding="utf-8", newline="\n")


def patch_workspace_test() -> None:
    path = Path("tests/unit/test_active_workspace_binding.py")
    text = path.read_text(encoding="utf-8")
    marker = "def test_binding_rejects_workspace_symlink"
    if marker in text:
        return
    addition = '''\n\ndef test_binding_rejects_workspace_symlink(tmp_path: Path) -> None:
    _binding_format, bind_active_workspace, _resolve_active_workspace = _workspace_api()
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    target = _ready_workspace(tmp_path / "workspace-target")
    link = tmp_path / "workspace-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"workspace symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        bind_active_workspace(repository_root, link)
'''
    path.write_text(text.rstrip() + addition + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    patch_html_renderer()
    patch_case_visual_projection()
    patch_local_server()
    patch_case_visual_test()
    patch_workspace_test()


if __name__ == "__main__":
    main()
