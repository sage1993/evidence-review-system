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


@pytest.mark.parametrize("viewport", [None, {"width": 1366, "height": 768},
                                       {"width": 1920, "height": 1080}])
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
