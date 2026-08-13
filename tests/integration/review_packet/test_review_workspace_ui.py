import json
import re
import subprocess
from pathlib import Path

from ansim_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _write_page_assets


def _inline_controller(html: str) -> str:
    scripts = re.findall(r"<script(?: [^>]*)?>(.*?)</script>", html, re.DOTALL)
    assert scripts
    return scripts[-1]


def _run_node_harness(controller: str, harness: str) -> subprocess.CompletedProcess[str]:
    source = f"const controller = {json.dumps(controller)};\n{harness}"
    return subprocess.run(
        ["node", "-"],
        input=source,
        text=True,
        capture_output=True,
        check=False,
    )


def test_workspace_escapes_content_localizes_status_and_keeps_offline_controls(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    model = _model()
    model["question"] = '<img src=x onerror="alert(1)">&\u2028'
    model["abstention_reasons"] = ["LOW_CONFIDENCE"]

    html = render_review_html(model, tmp_path / "pages")

    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;' in html
    assert '<img src=x onerror="alert(1)">' not in html
    assert "\\u003cimg" in html
    assert "\\u003e" in html
    assert "\\u0026" in html
    assert "\\u2028" in html
    assert "검토 준비 완료" in html
    assert 'id="additional-review"' in html
    assert 'name="decision"' in html
    assert "checked" not in html
    assert 'fetch("./decision"' in html
    assert "https://" not in html
    assert "http://" not in html
    for function_name in (
        "selectReviewItem",
        "activateDetailTab",
        "focusEvidence",
        "setEvidenceZoom",
        "submitDecision",
        "downloadDecisionEnvelope",
    ):
        assert function_name in html


def test_zoom_transforms_shared_page_canvas(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")

    assert 'document.querySelectorAll(".page-canvas")' in html
    assert 'canvas.style.transform = "scale(" + scale + ")"' in html


def test_decision_envelope_still_matches_v1_contract_before_issue_91(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")
    match = re.search(
        r"function decisionEnvelope\(form\) \{.*?return \{(?P<fields>.*?)\n    \};",
        html,
        re.DOTALL,
    )

    assert match is not None
    assert re.findall(r"^      ([a-z_]+):", match.group("fields"), re.MULTILINE) == [
        "reviewer_id",
        "reviewed_at",
        "packet_hash",
        "decision",
        "notes",
    ]


def test_final_decision_controls_are_korean_and_unselected(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")

    html = render_review_html(_model(), tmp_path / "pages")
    decision_form = _decision_form_html(html)

    for value in (
        "최종 결정",
        "내용 확인 완료",
        "내용에 오류 있음",
        "조건부 확인",
        "추가 자료 필요",
        "결정 저장",
        "결정 JSON 다운로드",
    ):
        assert value in decision_form
    assert "checked" not in decision_form


def test_print_lifecycle_reveals_panels_and_restores_hidden_state(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))
    harness = r"""
function node(hidden, dataset) {
  return {
    hidden,
    dataset: dataset || {},
    listeners: {},
    attributes: {},
    addEventListener(type, handler) { this.listeners[type] = handler; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    querySelector() { return null; }
  };
}
const panels = [
  node(false, { tabPanel: "evidence" }),
  node(true, { tabPanel: "rules-calculations" })
];
const tabs = [
  node(false, { detailTab: "evidence" }),
  node(false, { detailTab: "rules-calculations" })
];
tabs[0].attributes["aria-selected"] = "true";
tabs[1].attributes["aria-selected"] = "false";
const printListeners = {};
global.window = {
  addEventListener(type, handler) { printListeners[type] = handler; },
  print() {}
};
global.document = {
  getElementById() { return null; },
  querySelector() { return null; },
  querySelectorAll(selector) {
    if (selector === ".detail-panel [data-tab-panel]") return panels;
    if (selector === "[data-detail-tab]") return tabs;
    return [];
  }
};
eval(controller);
if (typeof printListeners.beforeprint !== "function") throw new Error("beforeprint missing");
if (typeof printListeners.afterprint !== "function") throw new Error("afterprint missing");
printListeners.beforeprint();
if (panels.some((panel) => panel.hidden)) throw new Error("print panel remained hidden");
printListeners.afterprint();
if (JSON.stringify(panels.map((panel) => panel.hidden)) !== JSON.stringify([false, true])) {
  throw new Error("hidden state was not restored exactly");
}
"""

    completed = _run_node_harness(controller, harness)

    assert completed.returncode == 0, completed.stderr


def test_viewer_mode_listener_targets_buttons_not_shell(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))
    harness = r"""
function node(dataset) {
  return {
    dataset,
    listeners: {},
    addEventListener(type, handler) { this.listeners[type] = handler; },
    setAttribute() {}
  };
}
const shell = node({ viewerMode: "compare" });
const button = node({ viewerMode: "compare" });
global.window = { addEventListener() {} };
global.document = {
  getElementById() { return null; },
  querySelector(selector) { return selector === ".app-shell" ? shell : null; },
  querySelectorAll(selector) {
    if (selector === "button[data-viewer-mode]") return [button];
    if (selector === "[data-viewer-mode]") return [shell, button];
    return [];
  }
};
eval(controller);
if (shell.listeners.click) throw new Error("shell received a mode listener");
if (typeof button.listeners.click !== "function") throw new Error("mode button listener missing");
"""

    completed = _run_node_harness(controller, harness)

    assert completed.returncode == 0, completed.stderr
