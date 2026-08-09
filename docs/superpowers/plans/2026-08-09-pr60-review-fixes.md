# PR #60 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the latest `main` into PR #60 and close the review findings without mutating machine packets or weakening the evidence-review boundary.

**Architecture:** Keep the immutable machine packet authoritative and store human decisions as separate append-only records. Expose a token-protected display-status projection from the local review server, with the browser updating only presentation state after verifying that a valid decision record exists. Preserve the existing calibration handoff in the merged drawing workspace.

**Tech Stack:** Python 3.11+, `http.server`, pytest, inline HTML/JavaScript assets, Ruff, mypy, compileall, documentation-integrity CLI.

---

### Task 1: Integrate latest `main` and preserve calibration handoff

**Files:**
- Modify: `tests/integration/drawing_review/test_browser_contract.py`
- Modify: merge result across the PR #60 branch and `origin/main`

- [ ] Resolve the merge conflict by retaining both the PR #60 display-mode/UI contract tests and the `test_javascript_resolves_late_injected_calibration_link` regression test.
- [ ] Verify `annotation.js` still contains the late calibration-link lookup and candidate/confirmation query binding.
- [ ] Run the focused drawing browser-contract tests and commit the merge result.

### Task 2: Require non-blank human-decision notes

**Files:**
- Modify: `src/ansim_review/review_packet/decision_record.py`
- Modify: `src/ansim_review/review_packet/html_renderer.py`
- Test: `tests/unit/review_packet/test_decision_record.py`
- Test: `tests/integration/review_packet/test_html_renderer.py`
- Test: `tests/integration/test_review_routes.py`

- [ ] Add failing unit coverage for empty and whitespace-only notes.
- [ ] Add failing route coverage for a blank-notes POST.
- [ ] Add the minimal server-side `notes.strip()` validation and require the HTML textarea field.
- [ ] Run unit and route tests, then update any callers to pass explicit notes.

### Task 3: Add `REVIEW_COMPLETED` display projection

**Files:**
- Modify: `src/ansim_review/review_packet/decision_record.py`
- Modify: `src/ansim_review/review_packet/builder.py`
- Modify: `src/ansim_review/review_packet/html_renderer.py`
- Modify: `src/ansim_review/review_packet/assets/review.js`
- Modify: `src/ansim_review/review_packet/local_server.py`
- Test: `tests/integration/review_packet/test_view_model.py`
- Test: `tests/integration/review_packet/test_html_renderer.py`
- Test: `tests/integration/test_review_routes.py`

- [ ] Add failing tests proving the view model starts with `display_status` equal to the machine finalizer status and that a valid decision changes only the served display projection.
- [ ] Implement validation-backed detection of a decision record whose packet hash matches the immutable packet.
- [ ] Add a token-protected decision-status endpoint and include `display_status` in the decision response.
- [ ] Update the browser projection without changing `final-review-packet.json` or the archival `review.html` bytes.
- [ ] Verify invalid or foreign-packet decision records do not produce `REVIEW_COMPLETED`.

### Task 4: Protect the confirmation route and align documentation

**Files:**
- Modify: `src/ansim_review/review_packet/local_server.py`
- Modify: `tests/integration/test_review_routes.py`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `docs/REVIEWER_WORKFLOW.md`

- [ ] Add failing tests for tokenized confirmation access and rejection of the unprotected legacy path.
- [ ] Implement `/runs/<RUN-ID>/<TOKEN>/confirmation` using the same token authorization as review, packet, and decision routes.
- [ ] Update current documentation to show the tokenized route and its fail-closed behavior.

### Task 5: Run repository acceptance gates

- [ ] Run focused tests after each implementation task.
- [ ] Run documentation validation to a fresh output path.
- [ ] Run full `pytest`, `ruff check src tests`, `mypy src`, and `python -m compileall -q src scripts web_runtime tests`.
- [ ] Run available wheel smoke checks and browser QA; report unavailable Python versions or GitHub Actions separately.

