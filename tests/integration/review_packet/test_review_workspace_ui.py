import json
import re
import subprocess
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html

from .test_html_renderer import _decision_form_html, _model, _write_page_assets


def _inline_controller(html: str) -> str:
    scripts = re.findall(r"<script(?: [^>]*)?>(.*?)</script>", html, re.DOTALL)
    assert scripts
    return scripts[-1]


def _run_node_harness(controller: str, harness: str) -> subprocess.CompletedProcess[str]:
    source = f"const controller = {json.dumps(controller)};\n{harness}"
    return subprocess.run(["node", "-"], input=source, text=True, capture_output=True, check=False)


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
    html = render_review_html(_model(), tmp_path / "pages")
    controller = _inline_controller(html)

    assert "applyReviewerLayout" not in controller
    assert "reviewer-layout-refinement" not in controller
    assert "grid-template-columns: minmax(280px, 360px) minmax(0, 1fr) minmax(320px, 360px)" in html
    assert "max-height: min(60vh, 640px)" in html
    assert "#evidence-zoom" in html and "min-height: 44px" in html
    assert 'original: "원문"' in controller
    assert 'evidence: "근거 강조"' in controller
    assert 'compare: "원문 + 강조"' in controller


def test_detail_activation_does_not_change_protected_mode_or_inject_layout(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))

    start = controller.index("function activateDetailTab")
    end = controller.index("let printPanelStates", start)
    detail_activation = controller[start:end]

    assert "setProtectedMode" not in detail_activation
    assert "applyReviewerLayout" not in detail_activation


def test_review_item_click_focuses_first_citation_on_its_pdf_page(tmp_path: Path) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))
    harness = r"""
function classList() {
  const values = new Set();
  return {
    add(value) { values.add(value); },
    toggle(value, enabled) { if (enabled) values.add(value); else values.delete(value); },
    contains(value) { return values.has(value); }
  };
}
function node(dataset) {
  return {
    dataset: dataset || {},
    classList: classList(),
    listeners: {},
    attributes: {},
    addEventListener(type, handler) { this.listeners[type] = handler; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    querySelector(selector) {
      if (selector === ".citation[data-evidence-id]") return this.citation || null;
      return null;
    },
    querySelectorAll(selector) {
      return selector === ".citation" && this.citation ? [this.citation] : [];
    },
    closest(selector) { return selector === ".detail-panel" ? this.panel || null : null; },
    scrollIntoView() {},
    focus() {}
  };
}
const item1 = node({itemId: "ITEM-1", evidenceId: "EV-1", assetKey: "REV1-P1"});
item1.classList.add("review-item");
const item2 = node({itemId: "ITEM-2", evidenceId: "EV-2", assetKey: "REV1-P2"});
item2.classList.add("review-item");
const panel1 = node({itemId: "ITEM-1"});
const panel2 = node({itemId: "ITEM-2"});
panel1.classList.add("detail-panel");
panel2.classList.add("detail-panel");
const citation1 = node({evidenceId: "EV-1", assetKey: "REV1-P1"});
const citation2 = node({evidenceId: "EV-2", assetKey: "REV1-P2"});
citation1.panel = panel1;
panel1.citation = citation1;
citation2.panel = panel2;
panel2.citation = citation2;
const page1 = node({assetKey: "REV1-P1"});
const page2 = node({assetKey: "REV1-P2"});
page1.classList.add("evidence-page");
page2.classList.add("evidence-page");
page1.classList.add("is-active");
const overlay1 = node({evidenceId: "EV-1"});
const overlay2 = node({evidenceId: "EV-2"});
const allNodes = [item1, item2, panel1, panel2];
global.window = { addEventListener() {}, prompt() { return ""; } };
global.document = {
  head: { appendChild() {} },
  createElement() { return {}; },
  getElementById() { return null; },
  querySelector(selector) {
    if (selector === ".detail-panel.is-selected") {
      return [panel1, panel2].find((panel) => panel.classList.contains("is-selected")) || null;
    }
    if (selector === '[data-detail-tab][aria-selected="true"]') return null;
    if (selector === '.evidence-page[data-asset-key="REV1-P2"]') return page2;
    if (selector === '.evidence-page[data-asset-key="REV1-P1"]') return page1;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === ".review-item, .detail-panel") return allNodes;
    if (selector === ".review-item") return [item1, item2];
    if (selector === ".detail-panel") return [panel1, panel2];
    if (selector === ".citation") return [citation1, citation2];
    if (selector === ".evidence-page") return [page1, page2];
    if (selector === ".citation-overlay") return [overlay1, overlay2];
    return [];
  }
};
eval(controller);
item2.listeners.click();
if (!page2.classList.contains("is-active")) throw new Error("page 2 not activated");
if (!overlay2.classList.contains("is-focused")) throw new Error("bbox not focused");
if (!item2.classList.contains("is-selected")) throw new Error("rail item not selected");
"""
    completed = _run_node_harness(controller, harness)
    assert completed.returncode == 0, completed.stderr


def test_review_item_orchestrator_preserves_no_citation_state_and_supports_keyboard(
    tmp_path: Path,
) -> None:
    _write_page_assets(tmp_path / "pages")
    controller = _inline_controller(render_review_html(_model(), tmp_path / "pages"))
    harness = r"""
function classList() {
  const values = new Set();
  return {
    add(value) { values.add(value); },
    toggle(value, enabled) { if (enabled) values.add(value); else values.delete(value); },
    contains(value) { return values.has(value); }
  };
}
function node(dataset) {
  return {
    dataset: dataset || {}, classList: classList(), listeners: {}, attributes: {},
    addEventListener(type, handler) { this.listeners[type] = handler; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    querySelector(selector) {
      if (selector === ".citation[data-evidence-id]") return this.citation || null;
      return null;
    },
    querySelectorAll(selector) {
      return selector === ".citation" && this.citation ? [this.citation] : [];
    },
    closest(selector) { return selector === ".detail-panel" ? this.panel || null : null; },
    scrollIntoView() {}, focus() {}
  };
}
const item1 = node({itemId: "ITEM-1", evidenceId: "EV-1"}); item1.classList.add("review-item");
const item2 = node({itemId: "ITEM-2", evidenceId: "EV-2"}); item2.classList.add("review-item");
const item3 = node({itemId: "ITEM-3"}); item3.classList.add("review-item");
const panel1 = node({itemId: "ITEM-1"}); panel1.classList.add("detail-panel");
const panel2 = node({itemId: "ITEM-2"}); panel2.classList.add("detail-panel");
const panel3 = node({itemId: "ITEM-3"}); panel3.classList.add("detail-panel");
const citation1 = node({evidenceId: "EV-1", assetKey: "REV1-P1"});
citation1.panel = panel1; panel1.citation = citation1;
const citation2 = node({evidenceId: "EV-2", assetKey: "REV1-P2"});
citation2.panel = panel2; panel2.citation = citation2;
const page1 = node({assetKey: "REV1-P1"}); page1.classList.add("evidence-page");
const page2 = node({assetKey: "REV1-P2"}); page2.classList.add("evidence-page");
page2.classList.add("is-active");
const overlay1 = node({evidenceId: "EV-1"}); const overlay2 = node({evidenceId: "EV-2"});
const all = [item1, item2, item3, panel1, panel2, panel3];
global.window = { addEventListener() {}, prompt() { return ""; } };
global.document = {
  head: { appendChild() {} }, createElement() { return {}; }, getElementById() { return null; },
  querySelector(selector) {
    if (selector === ".detail-panel.is-selected") {
      return all.find((n) => n.classList.contains("is-selected")) || null;
    }
    if (selector === '[data-detail-tab][aria-selected="true"]') return null;
    if (selector.includes("REV1-P1")) return page1;
    if (selector.includes("REV1-P2")) return page2;
    return null;
  },
  querySelectorAll(selector) {
    if (selector === ".review-item, .detail-panel") return all;
    if (selector === ".review-item") return [item1, item2, item3];
    if (selector === ".detail-panel") return [panel1, panel2, panel3];
    if (selector === ".citation") return [citation1, citation2];
    if (selector === ".evidence-page") return [page1, page2];
    if (selector === ".citation-overlay") return [overlay1, overlay2];
    return [];
  }
};
eval(controller);
if (typeof window.activateReviewItem !== "function") throw new Error("orchestrator missing");
if (window.activateReviewItem("ITEM-3") !== false) {
  throw new Error("citation-free activation should report false");
}
if (!page2.classList.contains("is-active")) throw new Error("citation-free item changed PDF page");
item2.listeners.keydown({ key: "Enter", preventDefault() {} });
if (!page2.classList.contains("is-active")) {
  throw new Error("Enter did not activate item 2 evidence");
}
item1.listeners.keydown({ key: " ", preventDefault() {} });
if (!page1.classList.contains("is-active")) {
  throw new Error("Space did not activate item 1 evidence");
}
"""
    completed = _run_node_harness(controller, harness)
    assert completed.returncode == 0, completed.stderr
