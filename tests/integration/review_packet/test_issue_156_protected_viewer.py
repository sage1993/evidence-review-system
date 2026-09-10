from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from evidence_review.review_packet import case_visual_asset_server
from evidence_review.review_packet.html_renderer import (
    render_protected_review_html,
    render_review_html,
)

RUN_ID = "RUN-156-PROTECTED-VIEWER"
ASSET_HASH = "a" * 64


def _visual_model() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "status": "READY_FOR_HUMAN_REVIEW",
        "display_status": "READY_FOR_HUMAN_REVIEW",
        "question": "case drawing review",
        "claims": [],
        "review_items": [],
        "calculations": [],
        "rules": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "summary": {},
        "audit": {},
        "case_visual_review": {
            "status": "VISUAL_ANALYSIS_VALIDATED",
            "pages": [
                {
                    "asset_key": "ATT-156-p1",
                    "attachment_id": "ATT-156",
                    "page": 1,
                    "width": 1.0,
                    "height": 1.0,
                    "document_name": "case.png",
                    "image_sha256": ASSET_HASH,
                    "data_uri": "data:image/png;base64,AAAA",
                    "tiles": [],
                    "candidates": [],
                }
            ],
            "reference_pages": [],
            "findings": [],
            "related_references": [],
        },
    }


def _route() -> case_visual_asset_server._CaseAssetRoute:
    return case_visual_asset_server._CaseAssetRoute(
        run_id=RUN_ID,
        token="a" * 43,
        kind="page",
        attachment_id="ATT-156",
        page_number=1,
        image_sha256=ASSET_HASH,
    )


def _write_case_page(root: Path, image_bytes: bytes) -> Path:
    path = root / "case-page-images-hq-v1" / "ATT-156" / "page-0001.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(image_bytes)
    return path


def test_issue_156_archival_visual_review_declares_static_mode_and_launcher(
    tmp_path: Path,
) -> None:
    html = render_review_html(_visual_model(), tmp_path / "page-images")

    assert 'data-archival-static-mode="true"' in html
    assert "보관용 정적 HTML" in html
    assert "evidence-review review-run serve" in html
    assert "--run-id RUN-156-PROTECTED-VIEWER" in html


def test_issue_156_protected_projection_declares_file_launcher_fallback(
    tmp_path: Path,
) -> None:
    model = _visual_model()
    visual = model["case_visual_review"]
    assert isinstance(visual, dict)
    page = visual["pages"][0]
    assert isinstance(page, dict)
    page.pop("data_uri")
    html = render_protected_review_html(model, tmp_path / "page-images")

    assert 'data-protected-presentation="true"' in html
    assert 'data-protected-file-guidance hidden' in html
    assert "보호된 검토기는 파일로 열 수 없습니다" in html
    assert 'window.location.protocol === "file:"' in html


def test_issue_156_file_opened_protected_viewer_does_not_load_protected_rasters() -> None:
    repository_root = Path(__file__).parents[3]
    controller = (
        repository_root / "src" / "evidence_review" / "review_packet" / "assets" / "review.js"
    ).read_text(encoding="utf-8")
    harness = r'''
function image(source) {
  return {
    dataset: {pageSrc: source},
    attributes: {},
    getAttribute(name) { return this.attributes[name] || null; },
    setAttribute(name, value) { this.attributes[name] = value; }
  };
}
function page(sourceId, source) {
  const pageImage = image(source);
  return {
    dataset: {sourceId},
    querySelector(selector) {
      return selector === "img[data-page-image-source]" ? pageImage : null;
    },
    pageImage
  };
}
const protectedPresentation = {};
const guidance = {hidden: true};
const pages = [
  page("REV-156", "./page-images/REV-156/1/hash"),
  page("REV-156", "./page-images/REV-156/2/hash"),
  page("REV-156", "./page-images/REV-156/3/hash")
];
global.window = {
  location: {protocol: "file:"},
  addEventListener() {},
  print() {},
  prompt() { return ""; }
};
global.fetch = async () => { throw new Error("offline"); };
global.document = {
  head: {appendChild() {}},
  createElement() { return {}; },
  getElementById() { return null; },
  querySelector(selector) {
    if (selector === '[data-protected-presentation="true"]') return protectedPresentation;
    if (selector === "[data-protected-file-guidance]") return guidance;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === '.evidence-page[data-source-id="REV-156"]') return pages;
    return [];
  }
};
eval(controller);
if (guidance.hidden) throw new Error("file launcher warning was not shown");
window.ensurePageImageLoaded(pages[0]);
window.prefetchAdjacentPages(pages[1]);
if (pages.some((page) => page.pageImage.getAttribute("src"))) {
  throw new Error("file-opened protected viewer loaded a raster");
}
window.location.protocol = "http:";
window.ensurePageImageLoaded(pages[0]);
window.prefetchAdjacentPages(pages[1]);
if (pages.some((page) => !page.pageImage.getAttribute("src"))) {
  throw new Error("HTTP protected viewer did not load active and adjacent rasters");
}
'''

    completed = subprocess.run(
        ["node", "-"],
        input=f"const controller = {json.dumps(controller)};\n{harness}",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_issue_156_case_asset_distinguishes_cold_cache_from_readable_cache(
    tmp_path: Path,
) -> None:
    missing = case_visual_asset_server._page_asset(tmp_path, _route())

    image_bytes = b"case raster"
    route = case_visual_asset_server._CaseAssetRoute(
        run_id=RUN_ID,
        token="a" * 43,
        kind="page",
        attachment_id="ATT-156",
        page_number=1,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
    )
    _write_case_page(tmp_path, image_bytes)
    existing = case_visual_asset_server._page_asset(tmp_path, route)

    assert missing == ("ASSET_MISSING", None)
    assert existing == ("AVAILABLE", image_bytes)


def test_issue_156_case_asset_reports_elevated_created_cache_denial(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_bytes = b"elevated cache raster"
    route = case_visual_asset_server._CaseAssetRoute(
        run_id=RUN_ID,
        token="a" * 43,
        kind="page",
        attachment_id="ATT-156",
        page_number=1,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
    )
    path = _write_case_page(tmp_path, image_bytes)
    monkeypatch.setattr(
        case_visual_asset_server,
        "_trusted_file",
        lambda *_: ("AVAILABLE", path),
    )

    def deny_read(_path: Path) -> bytes:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "read_bytes", deny_read)

    denied = case_visual_asset_server._page_asset(tmp_path, route)

    assert denied == ("ASSET_PERMISSION_DENIED", None)


def test_issue_156_case_asset_reports_trusted_path_permission_denial(
    monkeypatch,
    tmp_path: Path,
) -> None:
    route = _route()

    def deny_trusted_path(*_args, **_kwargs):
        raise PermissionError("access denied")

    monkeypatch.setattr(
        case_visual_asset_server,
        "verified_regular_file_below",
        deny_trusted_path,
    )

    denied = case_visual_asset_server._page_asset(tmp_path, route)

    assert denied == ("ASSET_PERMISSION_DENIED", None)


def test_issue_156_tile_manifest_read_permission_denial_is_not_invalid(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest_path = (
        tmp_path
        / "case-page-tiles-v1"
        / "ATT-156"
        / "page-0001"
        / "manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"tiles": []}', encoding="utf-8")
    route = case_visual_asset_server._CaseAssetRoute(
        run_id=RUN_ID,
        token="a" * 43,
        kind="tile",
        attachment_id="ATT-156",
        page_number=1,
        image_sha256=ASSET_HASH,
        tile_x=0,
        tile_y=0,
    )

    def deny_manifest_read(_path: Path, *, encoding: str) -> str:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "read_text", deny_manifest_read)

    denied = case_visual_asset_server._tile_asset(tmp_path, route)

    assert denied == ("ASSET_PERMISSION_DENIED", None)
