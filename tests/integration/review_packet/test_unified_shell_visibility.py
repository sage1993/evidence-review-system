"""Real Chromium DOM regression; provide ERS_PLAYWRIGHT_MODULE for browser QA."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from evidence_review.review_packet.html_renderer import render_review_html
from evidence_review.review_packet.render_summary import visual_shell_css
from tests.unit.review_packet.test_case_visual_renderer import (
    _model as _visual_model,
)
from tests.unit.review_packet.test_case_visual_renderer import _typed_reference_model
from tests.unit.review_packet.test_unified_workspace_renderer import _generic_model

from .test_html_renderer import _model as _reference_model
from .test_html_renderer import _write_page_assets


@pytest.mark.parametrize("collapsed", [True, False])
def test_print_keeps_all_observations_and_restores_screen_state(
    tmp_path: Path, collapsed: bool,
) -> None:
    module = os.environ.get("ERS_PLAYWRIGHT_MODULE")
    if not module:
        pytest.skip("Browser QA requires ERS_PLAYWRIGHT_MODULE pointing to Playwright")
    model = _generic_model()
    visual = _visual_model()["case_visual_review"]
    first = visual["findings"][0]
    visual["findings"] = [
        {**first, "finding_id": f"VF-{index}", "title": f"Observation {index}"}
        for index in range(1, 9)
    ]
    model["case_visual_review"] = visual
    script = r'''
const {chromium} = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', async () => {
  const data = JSON.parse(input);
  const browser = await chromium.launch({headless: true,
    ...(process.env.ERS_PLAYWRIGHT_CHANNEL ? {channel: process.env.ERS_PLAYWRIGHT_CHANNEL} : {})});
  try {
    const page = await browser.newPage();
    await page.setContent(data.html);
    if (!data.collapsed) await page.locator('[data-findings-toggle]').click();
    const panel = page.locator('.findings-panel');
    const before = await panel.isVisible();
    await page.emulateMedia({media: 'print'});
    if (!(await panel.isVisible())) throw new Error('Print omits the observation panel');
    const clipped = await page.locator('.findings-body').evaluate(n =>
      n.scrollHeight > n.clientHeight + 1 && getComputedStyle(n).overflowY !== 'visible');
    if (clipped) throw new Error('Printed observations are clipped');
    await page.pdf({path: data.pdf, format: 'A4'});
    await page.emulateMedia({media: 'screen'});
    if (await panel.isVisible() !== before) throw new Error('Print changed screen collapse state');
  } finally { await browser.close(); }
});
'''
    pdf = tmp_path / "review.pdf"
    result = subprocess.run(
        ["node", "-e", script, module],
        input=json.dumps({"html": render_review_html(model, tmp_path),
                          "collapsed": collapsed, "pdf": str(pdf)}),
        text=True, capture_output=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    from pypdf import PdfReader

    printed = "\n".join(page.extract_text() for page in PdfReader(pdf).pages)
    for index in range(1, 9):
        assert f"Observation {index}" in printed


@pytest.mark.parametrize("viewport", [None, {"width": 1366, "height": 768},
                                       {"width": 1920, "height": 1080},
                                       {"width": 390, "height": 844}])
@pytest.mark.parametrize(
    "mode", ["no-visual", "reference-only", "subject-only", "reference-subject"]
)
@pytest.mark.parametrize("status", ["ABSTAIN", "READY_FOR_HUMAN_REVIEW", "decision-present"])
def test_unified_regions_are_visible_and_reachable(
    tmp_path: Path, viewport: dict[str, int] | None, mode: str, status: str,
) -> None:
    module = os.environ.get("ERS_PLAYWRIGHT_MODULE")
    if not module:
        pytest.skip("Browser QA requires ERS_PLAYWRIGHT_MODULE pointing to Playwright")
    model = _reference_model() if mode == "reference-only" else _generic_model()
    if mode == "reference-only":
        _write_page_assets(tmp_path)
        model["issue_results"] = _generic_model()["issue_results"]
    model["status"] = model["display_status"] = (
        "READY_FOR_HUMAN_REVIEW" if status == "decision-present" else status
    )
    if status == "decision-present":
        model["human_decision"] = {"decision": "SATISFIED", "reviewer_id": "qa-reviewer"}
    if mode in {"subject-only", "reference-subject"}:
        visual = (_visual_model() if mode == "subject-only" else _typed_reference_model())[
            "case_visual_review"
        ]
        if mode == "subject-only":
            first = visual["findings"][0]
            visual["findings"] = [
                {**first, "finding_id": f"VF-{index}", "title": f"Observation {index}"}
                for index in range(1, 9)
            ]
        model["case_visual_review"] = visual
    html = render_review_html(model, tmp_path)
    script = r'''
const {chromium} = require(process.argv[1]);
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.ERS_PLAYWRIGHT_CHANNEL ? {channel: process.env.ERS_PLAYWRIGHT_CHANNEL} : {})});
  try {
    const data = JSON.parse(input);
    const page = await browser.newPage(data.viewport ? {viewport: data.viewport} : {});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent(data.html);
    const results = await page.locator('[data-review-shell-region]').evaluateAll(nodes =>
      nodes.map(node => ({region: node.dataset.reviewShellRegion,
        visible: node.checkVisibility(), height: node.getBoundingClientRect().height})));
    if (results.length !== 5 || results.some(item => !item.visible || item.height <= 0))
      throw new Error(JSON.stringify(results));
    const decision = page.locator('#decision-form');
    if (await decision.getAttribute('aria-hidden') === 'true')
      throw new Error('Visible human decision is hidden from assistive technology');
    const editor = page.locator('[data-decision-editor]');
    if (await editor.isVisible()) throw new Error('Decision editor starts expanded');
    await page.locator('[data-add-decision]').click();
    if (!(await editor.isVisible())) throw new Error('Decision editor did not open');
    await page.locator('[data-cancel-decision]').click();
    if (await editor.isVisible()) throw new Error('Decision editor did not close');
    if (!(await page.locator('[data-add-decision]').evaluate(n=>n===document.activeElement)))
      throw new Error('Cancel failed to restore focus');
    if (await page.locator('#review-details').getAttribute('open') !== null)
      throw new Error('Secondary results start expanded');
    await page.locator('#review-details > summary').click();
    if (!(await page.locator('#review-issue-results').isVisible()))
      throw new Error('Deferred issue results are inaccessible');
    await page.locator('#review-details > summary').click();
    if (data.mode === 'subject-only' || data.mode === 'reference-subject') {
      const left = await page.locator('.reference-viewer').boundingBox();
      const right = await page.locator('.subject-viewer').boundingBox();
      if (!left || !right || Math.abs(left.y-right.y)>1 || left.x+left.width>right.x)
        throw new Error('References must stay beside the drawing');
      const divider = page.locator('[data-case-divider]');
      await divider.focus(); await divider.press('ArrowRight');
      if (await divider.getAttribute('aria-valuenow') !== '52')
        throw new Error('Divider keyboard adjustment failed');
      const toggle = page.locator('[data-findings-toggle]');
      if (await page.locator('.findings-panel').isVisible())
        throw new Error('Panel must start collapsed for comparison');
      await toggle.click();
      if (!(await page.locator('.findings-panel').isVisible()))
        throw new Error('Panel did not expand');
      await toggle.click();
      if (await page.locator('.findings-panel').isVisible())
        throw new Error('Panel did not collapse');
    }
    if (data.mode === 'reference-subject') {
      const images = page.locator('[data-reference-page-image]');
      await images.evaluateAll(nodes=>nodes.forEach(n=>n.dataset.referencePageSrc=
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA'+
        'C0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='));
      const selector = page.locator('.reference-focus.is-active select');
      const count = await selector.locator('option').count();
      await selector.selectOption(String(count-1));
      const current = page.locator('.reference-focus.is-active .reference-viewer-item.is-active');
      if (!(await current.isVisible()) || !(await current.locator('image').getAttribute('href')))
        throw new Error('Selected second/related image was not loaded');
      const shown = page.locator('.reference-focus.is-active .reference-viewer-item:visible');
      if (await shown.count()!==1)
        throw new Error('More than one reference consumes the pane');
      const subject = page.locator('.case-visual-page.is-active [data-case-transform]');
      const before = await subject.getAttribute('style');
      await current.locator('[data-reference-zoom="in"]').click();
      if (await subject.getAttribute('style') !== before)
        throw new Error('Independent zoom moved the other pane');
      await page.locator('[data-view-sync]').check();
      await current.locator('[data-reference-zoom="in"]').click();
      if (await subject.getAttribute('style') === before)
        throw new Error('Opt-in synchronized movement failed');
    }
    if (data.mode === 'subject-only') {
      await page.locator('[data-findings-toggle]').click();
      const findings = page.locator('[data-case-finding]');
      if (await findings.count() !== 8) throw new Error('Missing finding');
      for (let i = 0; i < 8; i++) {
        const finding = findings.nth(i);
        await finding.click();
        if (!(await finding.isVisible())) throw new Error('Unreachable finding ' + i);
        const clipped = await finding.evaluate(n => n.scrollHeight > n.clientHeight + 1);
        if (clipped) throw new Error('Clipped finding ' + i);
      }
      const geometry = page.locator('.case-visual-overlay.is-active .case-visual-geometry');
      if (await geometry.first().evaluate(n => getComputedStyle(n).stroke) !== 'rgb(217, 45, 32)')
        throw new Error('Selected geometry not highlighted');
    }
    await page.screenshot({path: data.screenshot});
    const audit = page.locator('[data-review-shell-region="audit"]');
    await audit.scrollIntoViewIfNeeded();
    const reachable = await audit.evaluate(node => {
      const rect = node.getBoundingClientRect();
      return rect.top < innerHeight && rect.bottom > 0;
    });
    if (!reachable) throw new Error('audit not reachable');
    const overflow = await page.locator('body').evaluate(node => getComputedStyle(node).overflowY);
    if (overflow === 'hidden') throw new Error('body traps scrolling to review regions');
    const auditToggle = audit.locator('summary').first();
    if (await auditToggle.count()) {
      await auditToggle.click();
      if (!(await auditToggle.evaluate(node => node.parentElement.open)))
        throw new Error('audit disclosure did not open');
    }
    if (errors.length) throw new Error(JSON.stringify(errors));
    process.stdout.write(JSON.stringify(results));
  } finally { await browser.close(); }
}).on('error', error => {console.error(error); process.exitCode = 1;});
'''
    completed = subprocess.run(
        ["node", "-e", script, module], input=json.dumps({
            "html": html, "viewport": viewport, "screenshot": str(tmp_path / "review.png"),
            "mode": mode,
        }),
        text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_legacy_visual_shell_still_hides_duplicate_sections() -> None:
    module = os.environ.get("ERS_PLAYWRIGHT_MODULE")
    if not module:
        pytest.skip("Browser QA requires ERS_PLAYWRIGHT_MODULE pointing to Playwright")
    html = (
        f"<style>{visual_shell_css()}</style><div class='app-shell'>"
        "<main class='review-workspace'><section id='legacy-duplicate'>duplicate</section>"
        "<section class='visual-review-grid-span'><div id='case-visual-review'>drawing</div>"
        "</section><form id='decision-form'>decision</form></main></div>"
    )
    script = r'''
const {chromium} = require(process.argv[1]);
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.ERS_PLAYWRIGHT_CHANNEL ? {channel: process.env.ERS_PLAYWRIGHT_CHANNEL} : {})});
  try {
    const page = await browser.newPage();
    await page.setContent(process.argv[2]);
    if (await page.locator('#legacy-duplicate').isVisible()) throw new Error('duplicate visible');
    if (!(await page.locator('#case-visual-review').isVisible())) throw new Error('drawing hidden');
    if (!(await page.locator('#decision-form').isVisible())) throw new Error('decision hidden');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
    completed = subprocess.run(
        ["node", "-e", script, module, html], text=True, encoding="utf-8",
        capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
