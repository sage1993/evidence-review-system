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
        ["node", "-"], input=source, text=True, capture_output=True, check=False
    )


def test_decision_form_exposes_only_decision_and_notes_as_human_inputs(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    form = _decision_form_html(render_review_html(_model(), tmp_path / "pages"))

    assert 'name="decision"' in form
    assert 'name="notes"' in form
    assert 'type="hidden" name="packet_sha256"' in form
    assert 'name="reviewer_id"' not in form
    assert 'name="reviewed_at"' not in form
    assert "검토 결과를 선택하고 필요한 의견을 입력하십시오." in form
    assert "data-protected-only" in form
    assert "data-archive-only" in form
    assert "append-only" not in form
    assert "checked" not in form


def test_browser_request_v2_and_archival_envelope_contract_are_distinct(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    request = re.search(
        r"function decisionRequest\(form\) \{.*?return \{(?P<fields>.*?)\n    \};",
        html,
        re.DOTALL,
    )
    envelope = re.search(
        r"function decisionEnvelope\(form\) \{.*?return \{(?P<fields>.*?)\n    \};",
        html,
        re.DOTALL,
    )
    assert request is not None and envelope is not None
    assert re.findall(r"^      ([a-z_]+):", request.group("fields"), re.MULTILINE) == [
        "reviewer_id",
        "packet_hash",
        "decision",
        "notes",
    ]
    assert re.findall(r"^      ([a-z_]+):", envelope.group("fields"), re.MULTILINE) == [
        "reviewer_id",
        "reviewed_at",
        "packet_hash",
        "decision",
        "notes",
    ]
    assert "reviewed_at: new Date().toISOString()" in envelope.group("fields")
    assert "validDecisionRequest" in html
    assert "notesRequired" in html
    assert "유효한 결정 JSON을 만들 수 없습니다" in html


def test_protected_status_supplies_reviewer_and_packet_context(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")

    assert 'fetch("./decision/status")' in html
    assert "payload.reviewer_id" in html
    assert "payload.packet_hash" in html
    assert "setProtectedMode(true)" in html
    assert '"검토자: " + decisionContext.reviewer_id' in html


def test_final_decision_controls_are_korean_and_unselected(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    decision_form = _decision_form_html(render_review_html(_model(), tmp_path / "pages"))

    for value in (
        "최종 결정",
        "검토 결과에 동의",
        "검토 결과에 오류 있음",
        "조건 충족 시 동의",
        "추가 자료 검토 필요",
        "결정 저장",
        "결정 JSON 다운로드",
    ):
        assert value in decision_form
    assert "checked" not in decision_form


def test_conditional_notes_error_is_connected_to_textarea(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    html = render_review_html(_model(), tmp_path / "pages")
    form = _decision_form_html(html)

    assert 'id="review-notes"' in form
    assert 'aria-describedby="decision-notes-error notes-help notes-error"' in form
    assert 'id="notes-error"' in form
    assert 'setAttribute("aria-invalid", required' in html
    assert 'decision !== "SATISFIED"' in html


def test_print_lifecycle_reveals_panels_and_restores_hidden_state(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))
    harness = r"""
function node(hidden, dataset) {
  return {
    hidden,
    dataset: dataset || {},
    listeners: {}, attributes: {},
    addEventListener(type, handler) { this.listeners[type] = handler; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    querySelector() { return null; }
  };
}
const panels = [node(false, {tabPanel: "evidence"}), node(true, {tabPanel: "rules-calculations"})];
const tabs = [node(false, {detailTab: "evidence"}), node(false, {detailTab: "rules-calculations"})];
tabs[0].attributes["aria-selected"] = "true";
tabs[1].attributes["aria-selected"] = "false";
const printListeners = {};
global.window = {
  addEventListener(type, handler) { printListeners[type] = handler; },
  print() {},
  prompt() { return ""; }
};
global.document = {
  head: { appendChild() {} },
  createElement() { return {}; },
  getElementById() { return null; }, querySelector() { return null; },
  querySelectorAll(selector) {
    if (selector === ".detail-panel [data-tab-panel]") return panels;
    if (selector === "[data-detail-tab]") return tabs;
    return [];
  }
};
eval(controller);
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
const shell = node({viewerMode: "compare"});
const button = node({viewerMode: "compare"});
global.window = { addEventListener() {}, prompt() { return ""; } };
global.document = {
  head: { appendChild() {} },
  createElement() { return {}; },
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


def test_reviewer_layout_and_viewer_labels_are_applied_by_controller(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))

    assert "minmax(320px,360px) minmax(0,1fr) minmax(320px,360px)" in controller
    assert "max-height:min(60vh,640px)" in controller
    assert "#evidence-zoom{min-height:44px}" in controller
    assert 'original: "원문"' in controller
    assert 'evidence: "근거 강조"' in controller
    assert 'compare: "원문 + 강조"' in controller
    assert ".bbox-location,.citation-audit,.item-audit{display:none!important}" in controller
