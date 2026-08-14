# Evidence Review System Public Readiness v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Evidence Review System into a clean, Python 3.13-only, externally understandable and contributable repository, resolve #105–#110, and prepare a verified `v0.2.0` release line without changing repository visibility automatically.

**Architecture:** Move implementation ownership from `ansim_review` into `evidence_review`, retain only minimal legacy CLI compatibility, remove historical/non-product artifacts from the active tree, and keep deterministic/offline/fail-closed review contracts intact. The Review Workspace correctness/security/performance fixes are implemented after the namespace/CLI boundary is stable. Release preparation is the final task and is accepted only on one exact Python 3.13 HEAD.

**Tech Stack:** Python 3.13, setuptools, pytest, Ruff, mypy, stdlib HTTP server, SQLite, Vanilla JS/CSS, GitHub release artifacts.

## Global Constraints

- Branch: `release/public-readiness-v0.2.0`.
- Design baseline: `docs/superpowers/specs/2026-08-15-public-readiness-v0.2.0-design.md`.
- Baseline `main`: `73d0a37c2a4619ea5297766c814549931ab0e6f7`.
- Target package version: `0.2.0`.
- Target release tag: `v0.2.0`.
- Official Python support: `>=3.13,<3.14` only.
- Python 3.11 compatibility and 3.11 validation are not release requirements.
- Canonical Python namespace: `evidence_review`.
- Canonical CLI: `evidence-review` and `python -m evidence_review`.
- `ansim-review` and `python -m ansim_review` may remain only as thin v0.2.0 compatibility entrypoints; they must not own implementation or alternate dispatch logic.
- Runtime remains offline by default; no new remote service/CDN/API dependency.
- Existing source/rule/page/release verification remains fail-closed.
- `final-review-packet.json` remains immutable machine output.
- Human decisions remain separate append-only records.
- `review.html` remains a standalone archival presentation.
- Repository visibility is not changed by this PR.
- `LICENSE` is not added until the repository owner explicitly chooses the license. Public visibility remains blocked until that choice is made.

---

## File Structure After This Plan

The target active tree is:

```text
.github/
  ISSUE_TEMPLATE/
    bug_report.yml
    feature_request.yml
  pull_request_template.md
CHANGELOG.md
CONTRIBUTING.md
SECURITY.md
README.md
AGENTS.md
docs/
  ...current product/developer docs...
  superpowers/
    specs/
    plans/
rules/
schemas/
scripts/                  # current operational/developer scripts only
skills/
  ers-pdf/
  ers-review/
src/
  evidence_review/         # canonical implementation
  ansim_review/            # minimal compatibility shim only, if retained
tests/
web_runtime/
pyproject.toml
documentation-integrity.json
parser-reproducibility.json
```

Do not create a directory merely to match this diagram. Keep the current root `web_runtime/` layout.

---

### Task 1: Lock Python 3.13 policy and clean the active repository tree (#106)

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `documentation-integrity.json`
- Modify: `skills/README.md`
- Delete after reference audit: `docs/acceptance/ANSIM_ACCEPTANCE_CHECKLIST.md`
- Delete after reference audit: `docs/acceptance/ANSIM_ZONING_RULE_CANDIDATE_REVIEW.md`
- Delete after reference audit: `docs/acceptance/issue-46/**`
- Delete after reference audit: `docs/acceptance/issue-48/**`
- Delete after reference audit: `docs/acceptance/issue-50/**`
- Delete after reference audit: `docs/acceptance/issue-6-browser-annotation/**`
- Delete after reference audit: `docs/acceptance/issue-6-completion/**`
- Delete after reference audit: `docs/acceptance/issue-87/**`
- Delete after reference audit: `docs/acceptance/issue-89/**`
- Delete after reference audit: `docs/acceptance/issues-98-101/**`
- Keep temporarily until current-reference audit completes: `docs/acceptance/issue-52/README.md`
- Delete: `scripts/build_issues_98_101_acceptance_workspace.py`
- Delete: `scripts/verify_issue_6_manual.ps1`
- Delete after current-call audit: `docs/GRIST_DESKTOP_QA.md`
- Delete after current-call audit: `scripts/export_grist_csv.py`
- Delete after current-call audit: `scripts/rebuild_visuals_and_grist.py`
- Delete after current-call audit: `scripts/repair_grist_document.py`
- Delete after ERS skill parity check: `skills/01-preserving-and-parsing-pdfs/**`
- Delete after ERS skill parity check: `skills/02-structuring-content-and-visuals/**`
- Delete after ERS skill parity check: `skills/03-cleaning-pdf-derived-data/**`
- Delete after ERS skill parity check: `skills/04-building-and-exporting-grist-databases/**`
- Delete after ERS skill parity check: `skills/05-validating-pdf-database-workflows/**`
- Test: existing documentation-integrity and packaging tests

**Interfaces:**
- Consumes: current repository tree and #106 cleanup policy.
- Produces: a Python 3.13-only repository with only current product/developer artifacts in the active tree; later tasks may rely on no current docs/scripts importing deleted Grist/issue-specific assets.

- [ ] **Step 1: Add RED policy assertions before editing metadata**

Add or update packaging/config tests to require:

```python
assert project_requires_python == ">=3.13,<3.14"
assert mypy_python_version == "3.13"
assert ruff_target_version == "py313"
```

Add a repository-content test or documentation-integrity rule that rejects current-support text matching active Python 3.11 commands such as `py -3.11` outside explicitly historical material.

- [ ] **Step 2: Run the policy tests and confirm RED**

```bash
py -3.13 -m pytest tests/integration/packaging tests/unit/documentation_integrity -k "python or metadata or documentation" -v
```

Expected: FAIL because `pyproject.toml` still declares Python 3.11 support and current docs still contain 3.11 validation instructions.

- [ ] **Step 3: Update `pyproject.toml` to the supported interpreter**

Set exactly:

```toml
[project]
requires-python = ">=3.13,<3.14"

[tool.ruff]
target-version = "py313"

[tool.mypy]
python_version = "3.13"
```

Do not leave `src/ansim_review` in the final mypy file list after Task 2. During Task 1 it may remain temporarily so this commit can validate the pre-migration tree.

- [ ] **Step 4: Inventory every cleanup candidate before deletion**

```bash
git grep -n "docs/acceptance/\|GRIST_DESKTOP_QA\|export_grist_csv\|rebuild_visuals_and_grist\|repair_grist_document\|build_issues_98_101\|verify_issue_6_manual\|01-preserving-and-parsing-pdfs\|02-structuring-content-and-visuals\|03-cleaning-pdf-derived-data\|04-building-and-exporting-grist-databases\|05-validating-pdf-database-workflows" -- .
```

Classify each match as:

```text
current runtime dependency
current automated-test dependency
current documentation link
historical-only reference
```

A file may be deleted only after current runtime/test/doc references are removed or migrated in the same commit.

- [ ] **Step 5: Remove historical acceptance and issue-specific scripts**

Delete the high-confidence historical paths listed in **Files**. Preserve Git history as the archive. Remove root README links that make historical issue acceptance part of current product instructions.

- [ ] **Step 6: Remove Grist/numbered legacy skill paths after parity check**

Before deleting each numbered skill, compare its current-user instructions to `skills/ers-pdf/` and `skills/ers-review/`. If a still-supported ERS behavior exists only in a numbered skill, move that instruction into the appropriate ERS skill first; do not preserve the old directory solely as documentation storage.

- [ ] **Step 7: Resolve `docs/acceptance/issue-52/README.md` current override**

Search all references to issue-52 acceptance. If the parser reproducibility contract depends only on reusable rules contained there, move those reusable rules into `docs/PARSER_REPRODUCIBILITY.md` or the canonical parser reproducibility configuration, update links, then delete `docs/acceptance/issue-52/`. If an executable current contract still requires the file itself, keep only that file and document why in `documentation-integrity.json`.

- [ ] **Step 8: Remove Python 3.11 from current docs/scripts/tests**

```bash
git grep -n -E "3\.11|py -3\.11|Python 3\.11|python3\.11" -- README.md AGENTS.md docs scripts tests pyproject.toml
```

For current requirements, replace dual-version instructions with Python 3.13. Historical facts that remain in intentionally retained history documents must be explicitly labeled historical and must not appear in release gates.

- [ ] **Step 9: Run focused cleanup validation**

```bash
py -3.13 -m pytest tests/unit/documentation_integrity tests/integration/packaging -v
py -3.13 -m compileall -q scripts
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "chore: set Python 3.13 policy and remove historical artifacts"
```

---

### Task 2: Migrate implementation ownership from `ansim_review` to `evidence_review` (#106)

**Files:**
- Move: `src/ansim_review/abstention/**` -> `src/evidence_review/abstention/**`
- Move: `src/ansim_review/confidence/**` -> `src/evidence_review/confidence/**`
- Move: `src/ansim_review/contracts/**` -> `src/evidence_review/contracts/**`
- Move: `src/ansim_review/documentation_integrity/**` -> `src/evidence_review/documentation_integrity/**`
- Move: `src/ansim_review/drawing_review/**` -> `src/evidence_review/drawing_review/**`
- Move: `src/ansim_review/evidence/**` -> `src/evidence_review/evidence/**`
- Move: `src/ansim_review/llm_layer/**` -> `src/evidence_review/llm_layer/**`
- Move: `src/ansim_review/retrieval/**` -> `src/evidence_review/retrieval/**`
- Move: `src/ansim_review/review_packet/**` -> `src/evidence_review/review_packet/**`
- Move: `src/ansim_review/rule_engine/**` -> `src/evidence_review/rule_engine/**`
- Move: `src/ansim_review/release/**` -> `src/evidence_review/release/**`
- Move: all remaining implementation modules under `src/ansim_review/` -> `src/evidence_review/`
- Preserve/refactor existing: `src/evidence_review/__init__.py`, `src/evidence_review/__main__.py`, `src/evidence_review/cli.py`, `src/evidence_review/diagnostics.py`
- Reduce to compatibility only: `src/ansim_review/__init__.py`, `src/ansim_review/__main__.py`
- Delete final implementation copies: `src/ansim_review/cli.py`, `src/ansim_review/cli_parser.py`, `src/ansim_review/entrypoint.py`, and all implementation subpackages after Task 3 canonical dispatch exists
- Modify: all `tests/**` imports
- Modify: all `scripts/**` imports
- Modify: `pyproject.toml` package-data keys
- Test: entire unit suite plus import/packaging tests

**Interfaces:**
- Consumes: Python 3.13-only cleaned tree from Task 1.
- Produces: all production implementation importable from `evidence_review.*`; `ansim_review` contains no business implementation.

- [ ] **Step 1: Add namespace ownership tests**

Create `tests/integration/contracts/test_namespace_ownership.py` with:

```python
import evidence_review.review_packet
import evidence_review.rule_engine
import evidence_review.evidence
import evidence_review.release

assert evidence_review.review_packet.__name__.startswith("evidence_review.")
```

Also assert no production module under `src/evidence_review` imports `ansim_review`:

```python
for path in Path("src/evidence_review").rglob("*.py"):
    assert "ansim_review" not in path.read_text(encoding="utf-8")
```

Compatibility files under `src/ansim_review` are exempt only when they import `evidence_review`.

- [ ] **Step 2: Run the namespace tests and confirm RED**

```bash
py -3.13 -m pytest tests/integration/contracts/test_namespace_ownership.py -v
```

Expected: FAIL because implementation still resides under `ansim_review`.

- [ ] **Step 3: Move implementation directories without semantic edits**

Use `git mv` for implementation modules so history remains readable. Resolve collisions with the existing four `evidence_review` facade files by retaining their public bootstrap behavior and moving only non-duplicate implementation symbols around them.

- [ ] **Step 4: Rewrite internal absolute imports**

```bash
git grep -n "from ansim_review\|import ansim_review" -- src tests scripts
```

Convert production/test/script imports to `evidence_review`. Do not create `sys.modules` aliasing or dual-import machinery inside production modules.

- [ ] **Step 5: Move package data declarations**

Update `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"evidence_review.evidence" = ["schema.sql", "schema_v2.sql"]
"evidence_review.llm_layer" = ["templates/*.md"]
"evidence_review.review_packet" = ["assets/*.css", "assets/*.js"]
"evidence_review.drawing_review" = ["assets/*.css", "assets/*.js"]
```

- [ ] **Step 6: Reduce legacy package to explicit CLI compatibility**

Final compatibility shape:

```python
# src/ansim_review/__main__.py
from evidence_review.cli import main

raise SystemExit(main())
```

`src/ansim_review/__init__.py` contains only a deprecation/compatibility marker and package version exposure if required. It must not alias the entire `evidence_review` module graph.

- [ ] **Step 7: Update mypy scope**

```toml
[tool.mypy]
python_version = "3.13"
strict = true
files = ["src/evidence_review"]
```

- [ ] **Step 8: Run namespace and package-data tests**

```bash
py -3.13 -m pytest tests/unit tests/integration/contracts tests/integration/packaging -v
py -3.13 -m mypy src/evidence_review
```

Expected: PASS for migrated paths.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: migrate implementation to evidence_review namespace"
```

---

### Task 3: Consolidate one canonical CLI dispatcher (#110)

**Files:**
- Create: `src/evidence_review/command_dispatch.py`
- Create if needed to break cycles: `src/evidence_review/cli_handlers.py`
- Modify: `src/evidence_review/cli.py`
- Modify: `src/evidence_review/__main__.py`
- Modify: migrated `src/evidence_review/cli_parser.py`
- Remove alternate runtime branch trees from migrated CLI/entrypoint code
- Compatibility only: `src/ansim_review/__main__.py`
- Add: `tests/integration/contracts/test_cli_dispatch_equivalence.py`
- Modify: production-facing CLI tests under `tests/integration/**`

**Interfaces:**
- Consumes: canonical namespace from Task 2.
- Produces exactly one business dispatcher:

```python
def main(argv: Sequence[str] | None = None) -> int:
    ...
```

in `evidence_review.command_dispatch`.

- [ ] **Step 1: Write RED dispatch-equivalence tests**

Test:

```text
evidence_review.cli.main
python -m evidence_review
python -m ansim_review
console script evidence-review
console script ansim-review
```

for representative help/parse behavior and business commands. Assert compatibility paths delegate to the same dispatcher and do not own another command branch tree.

- [ ] **Step 2: Characterize bootstrap-only behavior**

Keep `--version`, `doctor`, source provenance, and dependency preflight in `evidence_review.cli`. Add tests proving business modules are imported only after preflight passes.

- [ ] **Step 3: Extract the post-preflight branch tree**

`src/evidence_review/command_dispatch.py` owns all business routing. It installs the offline/network guard once at the runtime boundary and invokes existing handlers without changing output schemas or exit codes.

- [ ] **Step 4: Break circular imports mechanically if required**

If migrated `cli.py` mixes handlers and dispatch, move handler functions unchanged to `cli_handlers.py`. Do not duplicate handlers between files.

- [ ] **Step 5: Convert `evidence_review.cli` to bootstrap + local import**

```python
from evidence_review.command_dispatch import main as runtime_main
return runtime_main(arguments)
```

The import occurs only after diagnostic/preflight success.

- [ ] **Step 6: Convert legacy entrypoints to thin delegation**

`python -m ansim_review` and `ansim-review` call `evidence_review.cli.main`; no alternate parser/dispatcher remains.

- [ ] **Step 7: Move production CLI integration tests to the canonical path**

```bash
git grep -n "cli.main(" tests/integration
git grep -n "ansim_review" tests/integration
```

Only compatibility-contract tests may intentionally use the legacy name.

- [ ] **Step 8: Run CLI/provenance tests**

```bash
py -3.13 -m pytest tests/integration/contracts/test_cli_dispatch_equivalence.py tests/integration/packaging/test_cli_runtime_provenance.py tests/integration/review_question -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: consolidate canonical CLI dispatch"
```

---

### Task 4: Add the public collaboration contract

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `CHANGELOG.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/pull_request_template.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `documentation-integrity.json`
- Create only after owner license choice: `LICENSE`
- Add: documentation/public-readiness validation tests if existing documentation integrity cannot express these requirements

**Interfaces:**
- Consumes: canonical namespace/CLI from Tasks 2–3.
- Produces: contributor-facing install/test/report/security contracts that describe the actual repository.

- [ ] **Step 1: Add RED repository-contract checks**

Require these files to exist and contain current canonical commands:

```text
CONTRIBUTING.md
SECURITY.md
CHANGELOG.md
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/pull_request_template.md
```

Require `CONTRIBUTING.md` to use Python 3.13 and canonical `evidence_review` commands.

- [ ] **Step 2: Write `CONTRIBUTING.md`**

Include:

```text
Python 3.13 environment
editable dev install
focused test first
full pytest
Ruff
mypy src/evidence_review
compileall
documentation integrity
wheel smoke when packaging is touched
PR expectations
```

State that user/customer PDFs, parser outputs, DBs, screenshots, and acceptance artifacts must not be committed.

- [ ] **Step 3: Write `SECURITY.md`**

Document the supported release line (`0.2.x` after release), offline/trust-boundary scope, and private vulnerability reporting expectations. Do not invent an email address. Public Issues must not contain unpatched exploit details.

- [ ] **Step 4: Seed `CHANGELOG.md` with v0.2.0 unreleased content**

Use:

```text
Added
Changed
Fixed
Security
Removed
Deprecated
```

Document Python 3.11 removal and any `ansim-review` compatibility deprecation explicitly.

- [ ] **Step 5: Rewrite README as public landing page**

Keep user quick start, but remove current-development Issue-number acceptance narratives. Add architecture/trust-boundary summary, Python 3.13 support, developer/contribution links, security link, release information, and license status.

- [ ] **Step 6: Add issue and PR templates**

Bug template fields: version/commit, OS, Python version, reproduction, expected/actual, sanitized logs, confirmation that no confidential document content is attached.

Feature template fields: problem, proposed outcome, evidence/review contract impact, backward compatibility.

PR template checklist: tests, docs, no sensitive artifacts, no weakened fail-closed checks, issue link.

- [ ] **Step 7: Handle license as an explicit gate**

If the owner has not chosen a license at implementation time, do **not** create a placeholder or guessed license. Add `LICENSE REQUIRED BEFORE PUBLICATION` to the public-readiness checklist. Once the owner selects a license, add the exact standard license text in a dedicated commit or the release metadata commit.

- [ ] **Step 8: Run documentation integrity**

```bash
py -3.13 -m evidence_review documentation validate --repository-root .
py -3.13 -m pytest tests/unit/documentation_integrity -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "docs: add public contribution and security documentation"
```

---

### Task 5: Harden web runtime manifest and path validation (#109)

**Files:**
- Modify: `web_runtime/bootstrap.py`
- Modify: `tests/integration/packaging/test_web_bundle.py`

**Interfaces:**
- Consumes: existing runtime manifest format version 1.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    sha256: str
    size: int


def load_manifest(path: Path) -> tuple[ManifestEntry, ...]: ...
def safe_runtime_file(root: Path, relative: str) -> Path: ...
def sha256_file(path: Path) -> str: ...
```

- [ ] **Step 1: Add RED unsafe-path tests**

Reject before file read:

```text
../outside.txt
rules/../../outside.txt
/absolute/path
C:/Windows/System32/file
C:\Windows\System32\file
\\server\share\file
rules\approved\R1.json
.
..
```

Expected: `UNSAFE_RUNTIME_PATH`.

- [ ] **Step 2: Add RED strict-schema tests**

Reject malformed JSON, wrong format/version, extra/missing top-level fields, non-list `files`, missing/extra entry fields, uppercase/invalid SHA, bool/negative size, duplicate path, and casefold-colliding path with `INVALID_RUNTIME_MANIFEST`.

- [ ] **Step 3: Implement strict manifest decoding**

Require top-level exactly:

```json
{"format":"evidence-review/chatgpt-web-runtime","version":1,"files":[]}
```

and each entry exactly `path`, `sha256`, `size`.

- [ ] **Step 4: Implement safe POSIX-relative resolution**

Use `PurePosixPath`; reject backslash, NUL, colon, absolute path, empty/dot/dotdot components. Resolve below the runtime root and reject symlink/reparse components using `lstat()` before content reads.

- [ ] **Step 5: Require regular file, then size, then hash**

Stable failures:

```text
RUNTIME_FILE_MISSING
RUNTIME_FILE_NOT_REGULAR
RUNTIME_FILE_SIZE_MISMATCH
RUNTIME_FILE_HASH_MISMATCH
```

Hash incrementally in 1 MiB chunks.

- [ ] **Step 6: Preserve SQLite checks after manifest verification**

Existing corrupt-DB and FK-error tests still return `SQLITE_INTEGRITY_FAILED` after manifest values have been intentionally updated to match tampered DB bytes.

- [ ] **Step 7: Run packaging tests**

```bash
py -3.13 -m pytest tests/integration/packaging/test_web_bundle.py -v
```

Expected: PASS, including byte-identical reproducible valid bundle.

- [ ] **Step 8: Commit**

```bash
git add web_runtime/bootstrap.py tests/integration/packaging/test_web_bundle.py
git commit -m "security: harden web runtime manifest validation"
```

---

### Task 6: Make evidence viewer document/revision aware (#105)

**Files:**
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/assets/review.js`
- Modify: `src/evidence_review/review_packet/assets/review.css`
- Modify: `src/evidence_review/review_packet/assets/review_responsive.css`
- Add: `tests/integration/review_packet/test_multi_document_viewer.py`
- Modify: `tests/integration/review_packet/test_review_visual_contract.py`
- Modify: `tests/integration/review_packet/test_issue_89_refinement.py`
- Modify: `tests/integration/review_packet/test_reviewer_workspace_refinement.py`

**Interfaces:**
- Consumes: verified page assets/citations from the existing packet/view-model contract.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class _ViewerDocument:
    document_id: str
    document_name: str
    revision_id: str
    pages: tuple[tuple[str, int, _PageAsset], ...]
```

and:

```javascript
setActiveSource(sourceId)
setActivePage(assetKey)
movePage(delta)
setEvidenceMode(mode)
```

- [ ] **Step 1: Write RED two-document provenance fixture**

Fixture:

```text
DOC-A / REV-A / source page 3 / evidence E-A
DOC-B / REV-B / source page 17 / evidence E-B
```

Require distinct source identities and original-page attributes; assert the UI never presents `3 / 17` as a loaded-page sequence.

- [ ] **Step 2: Build `_ViewerDocument` projection**

Group by `(document_id, revision_id)` in first-citation order, deduplicate cited pages per source, retain authoritative original page number, and fail closed on conflicting non-empty document names for one identity.

- [ ] **Step 3: Replace fake source/sort affordances**

Multiple sources: native `<select data-source-select>`.

Single source: non-interactive label.

Render:

```text
근거 페이지 1 / 2 · 원문 p.3
```

Render `문서별 · 관련도순` as descriptive text until a real sort exists.

- [ ] **Step 4: Expose real viewer-mode buttons**

Render actual `button[data-viewer-mode]` controls for `원문`, `근거 강조`, `원문 + 강조`; maintain `aria-pressed`.

- [ ] **Step 5: Correct source-neutral provenance copy**

Use:

```text
검토에 사용된 원본 문서의 검증된 페이지 이미지를 표시합니다.
```

- [ ] **Step 6: Implement source-bounded JS navigation**

`movePage()` never crosses source boundaries. Citation activation first selects the correct source, then page. Source change selects that source's first cited page unless a citation target is explicit.

- [ ] **Step 7: Run focused viewer tests**

```bash
py -3.13 -m pytest tests/integration/review_packet/test_multi_document_viewer.py tests/integration/review_packet/test_review_visual_contract.py tests/integration/review_packet/test_issue_89_refinement.py tests/integration/review_packet/test_reviewer_workspace_refinement.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/evidence_review/review_packet tests/integration/review_packet
git commit -m "fix: make evidence viewer document aware"
```

---

### Task 7: Surface persisted human-decision state (#107)

**Files:**
- Modify: `src/evidence_review/review_packet/decision_record.py`
- Modify: `src/evidence_review/review_packet/local_server.py`
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/assets/review.js`
- Modify: `src/evidence_review/review_packet/assets/review.css`
- Add: `tests/unit/review_packet/test_decision_state.py`
- Modify: `tests/unit/review_packet/test_decision_record.py`
- Modify: `tests/integration/review_packet/test_local_server.py`
- Modify: `tests/integration/review_packet/test_review_workspace_ui.py`
- Modify: `tests/integration/review_packet/test_archival_decision_visibility.py`

**Interfaces:**
- Consumes: immutable current packet hash and append-only decision directory.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class HumanDecisionRecord:
    run_id: str
    reviewer_id: str
    reviewed_at: str
    packet_hash: str
    decision: str
    notes: str
    path: Path


def load_latest_valid_human_decision(
    run_directory: Path,
    packet_hash: str,
) -> HumanDecisionRecord | None: ...
```

- [ ] **Step 1: Write RED latest-valid-record tests**

Create valid records with different timestamps plus malformed/wrong-run/wrong-packet/invalid-decision candidates. Only the latest validated packet-bound record may be returned.

- [ ] **Step 2: Implement deterministic record loading**

Reuse the existing envelope validator. Sort by parsed offset-aware `reviewed_at`, then filename as deterministic tie-break. `has_valid_human_decision()` delegates to the new reader.

- [ ] **Step 3: Increase filename timestamp precision**

Use:

```text
%Y%m%dT%H%M%S%f%z
```

Two different microsecond timestamps in one second produce different files; the exact same timestamp/reviewer still fails create-only with `FileExistsError`.

- [ ] **Step 4: Extend protected decision status response**

Return only validated public fields:

```json
{
  "display_status": "REVIEW_COMPLETED",
  "reviewer_id": "...",
  "packet_hash": "...",
  "decision_record": {
    "reviewer_id": "...",
    "reviewed_at": "...",
    "decision": "SATISFIED",
    "notes": "..."
  }
}
```

Do not return filesystem paths/filenames.

- [ ] **Step 5: Render read-only completed state**

Add saved-decision fields and `data-record-another-decision`. Protected mode with an existing valid record hides/disables the blank first-time form until the user explicitly chooses to append another decision.

- [ ] **Step 6: Handle 409 append-only conflicts explicitly**

On `DECISION_ALREADY_EXISTS`, refresh status and show the persisted state instead of a generic failure.

- [ ] **Step 7: Preserve standalone archive behavior**

`review.html` opened without the server continues to download a decision envelope and does not claim persistence.

- [ ] **Step 8: Run decision/server/UI tests**

```bash
py -3.13 -m pytest tests/unit/review_packet/test_decision_state.py tests/unit/review_packet/test_decision_record.py tests/integration/review_packet/test_local_server.py tests/integration/review_packet/test_review_workspace_ui.py tests/integration/review_packet/test_archival_decision_visibility.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/evidence_review/review_packet tests/unit/review_packet tests/integration/review_packet
git commit -m "fix: surface persisted human decision state"
```

---

### Task 8: Add lazy protected page-image delivery (#108)

**Files:**
- Modify: `src/evidence_review/review_packet/page_image_verifier.py`
- Modify: `src/evidence_review/review_packet/html_renderer.py`
- Modify: `src/evidence_review/review_packet/local_server.py`
- Modify: `src/evidence_review/review_packet/assets/review.js`
- Modify: `src/evidence_review/review_packet/assets/review.css`
- Modify: `src/evidence_review/review_run.py`
- Add: `tests/integration/review_packet/test_protected_image_delivery.py`
- Modify: `tests/integration/review_packet/test_review_workspace_performance.py`
- Modify: `tests/integration/review_packet/test_local_server.py`
- Modify: `tests/integration/review_packet/test_html_renderer.py`

**Interfaces:**
- Consumes: document-aware active-source/page state from Task 6.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class VerifiedPageImage:
    revision_id: str
    page_number: int
    source_hash: str
    image_path: Path
    image_sha256: str
    image_bytes: bytes
    pdf_width: float
    pdf_height: float
    origin_x: float
    origin_y: float
    rotation: int
    box_kind: str


def read_verified_page_image(...) -> VerifiedPageImage: ...
```

and:

```python
ImageDeliveryMode = Literal["embedded", "protected"]
```

- [ ] **Step 1: Add realistic RED payload-size tests**

Generate deterministic verified PNG fixtures >=1 MiB each. For 10 cited pages require protected-mode HTML to contain no `data:image/png;base64,`, contain `data-page-src`, and remain below 512 KiB regardless of >10 MiB total image bytes.

- [ ] **Step 2: Centralize verified page-image reading**

Move all existing metadata/source-hash/image-SHA/geometry validation behind `read_verified_page_image()`. `html_renderer.py` and the server route use the same verifier.

- [ ] **Step 3: Add explicit `embedded` and `protected` rendering**

Default remains `embedded` so existing `review.html` is standalone. Protected mode renders validated local `data-page-src` URLs and no embedded full-page data URIs.

- [ ] **Step 4: Add protected image route**

Route requires existing review token/loopback authorization, validated revision/page/source hash, serve-time re-verification, and:

```text
Content-Type: image/png
Cache-Control: private, no-store
X-Content-Type-Options: nosniff
```

Traversal, wrong token, wrong source hash, unknown page, or tampered image is rejected before bytes are served.

- [ ] **Step 5: Produce `review-protected.html` as derived display artifact**

Keep `review.html` as archive/finalization artifact. Protected `/review` serves the protected variant derived from the same packet/view model. Tests must detect stale/mismatched derivation.

- [ ] **Step 6: Lazy hydrate active and bounded adjacent pages**

Add:

```javascript
ensurePageImageLoaded(page)
```

Active page loads immediately; at most one previous and one next page within the active source are prefetched. Source switch respects Task 6 boundaries.

- [ ] **Step 7: Run protected-image and regression tests**

```bash
py -3.13 -m pytest tests/integration/review_packet/test_protected_image_delivery.py tests/integration/review_packet/test_review_workspace_performance.py tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_local_server.py tests/integration/review_question -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/evidence_review tests/integration
git commit -m "perf: lazy load protected review page images"
```

---

### Task 9: Normalize rules, legacy names, docs, tests, and package metadata (#106)

**Files:**
- Modify/move: ANSIM-specific rule data under `rules/**` only after exact path/hash dependency audit
- Preferred destination for test-only ANSIM rule data: `tests/fixtures/ansim/rules/**`
- Use `examples/ansim/rules/**` only for a durable runnable contributor example
- Modify: rule manifests/approvals/golden references that point to moved data
- Modify: `docs/RULE_ACTIVATION_GOVERNANCE.md`
- Delete or rename after compatibility audit: `scripts/build_ansim_release.py`
- Delete or rename after compatibility audit: `scripts/migrate_ansim_workspace.py`
- Delete after feature removal: `docs/LEGACY_LINEAGE_MIGRATION.md`
- Delete after feature removal: `docs/LEGACY_VISUALS.md`
- Modify: `README.md`, `AGENTS.md`, `skills/**`, `docs/**`
- Modify: `pyproject.toml`
- Modify: `documentation-integrity.json`
- Modify: tests/golden fixtures referencing ANSIM names

**Interfaces:**
- Consumes: migrated canonical namespace and working rule engine.
- Produces: generic Evidence Review System naming in production paths; any remaining `ansim` string is either a documented compatibility name or explicit fixture/example identity.

- [ ] **Step 1: Inventory every remaining ANSIM reference**

```bash
git grep -n -i "ansim" -- .
```

Classify as:

```text
legacy CLI compatibility
production implementation name
runtime rule data identity
test fixture/example identity
historical text
```

Production implementation names are not allowed after this task.

- [ ] **Step 2: Audit rule data before moving anything**

For every ANSIM-specific file under `rules/`, search exact path and hash references in manifests, approvals, golden reports, CLI defaults, tests, and docs. Do not delete/move a governed rule until all dependent contracts are changed together.

- [ ] **Step 3: Separate product engine from ANSIM example/test data**

Move test-only rule datasets to `tests/fixtures/ansim/rules/`. Use `examples/ansim/rules/` only when the dataset is deliberately retained as a runnable public example. Keep `rules/` only for governed current runtime rules.

- [ ] **Step 4: Remove obsolete ANSIM/Grist migration wrappers**

If canonical CLI already exposes equivalent release/migration behavior, delete `scripts/build_ansim_release.py` and `scripts/migrate_ansim_workspace.py`. If the behavior is still required as a script, rename to generic `build_release.py` / `migrate_legacy_workspace.py` and update all references.

- [ ] **Step 5: Remove legacy docs when the feature is gone**

Delete `LEGACY_LINEAGE_MIGRATION.md` and `LEGACY_VISUALS.md` only after their CLI/code paths no longer exist. Otherwise rewrite them as current compatibility docs under a clearly marked migration section rather than main user navigation.

- [ ] **Step 6: Enforce canonical package metadata**

Final `pyproject.toml`:

```toml
[project]
version = "0.2.0"
requires-python = ">=3.13,<3.14"

[project.scripts]
evidence-review = "evidence_review.cli:main"
ansim-review = "evidence_review.cli:main"
```

If `ansim-review` compatibility is explicitly removed before release, delete that script and document the breaking change in `CHANGELOG.md`; do not silently change it.

- [ ] **Step 7: Run repository-wide name/reference checks**

```bash
git grep -n "src/ansim_review\|from ansim_review\|import ansim_review" -- .
git grep -n -i "grist" -- README.md AGENTS.md docs scripts skills src tests pyproject.toml
git grep -n -i "issue-87\|issue-89\|issues-98-101" -- README.md AGENTS.md docs scripts
```

Every remaining match must be intentionally current, compatibility-only, or fixture/history scoped.

- [ ] **Step 8: Run rules/docs/package tests**

```bash
py -3.13 -m pytest tests/unit/rule_engine tests/integration/rule_engine tests/unit/documentation_integrity tests/integration/packaging -v
py -3.13 -m evidence_review documentation validate --repository-root .
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: normalize rules docs tests and package metadata"
```

---

### Task 10: Prepare reproducible v0.2.0 release artifacts

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `src/evidence_review/release/acceptance.py`
- Modify: `src/evidence_review/release/attestation.py`
- Modify: `src/evidence_review/release/builder.py`
- Modify: `src/evidence_review/release/config.py`
- Modify/delete as appropriate after migration: `src/evidence_review/release/legacy_acceptance.py`
- Modify: `src/evidence_review/release/offline_boundary.py`
- Modify: `src/evidence_review/release/output_verifier.py`
- Modify: `src/evidence_review/release/validator.py`
- Modify/delete: `scripts/build_ansim_release.py`
- Modify: `scripts/validate_release.py`
- Modify: `tests/unit/release/**`
- Modify: `tests/integration/release/**`
- Modify: `tests/integration/packaging/**`
- Generated after acceptance, not committed by default: `dist/evidence_review_system-0.2.0-py3-none-any.whl`
- Generated after acceptance, not committed by default: `dist/evidence-review-system-v0.2.0-runtime.zip`
- Generated after acceptance, not committed by default: `dist/SHA256SUMS.txt`
- Generated when current release governance emits it: `dist/release-manifest.json`

**Interfaces:**
- Consumes: final source/config/docs from Tasks 1–9.
- Produces: reproducible v0.2.0 release candidates whose hashes are recorded and whose contents exclude user/generated/historical artifacts.

- [ ] **Step 1: Add release-content RED tests**

Wheel/runtime artifact tests must reject inclusion of:

```text
docs/acceptance/
source PDFs
parser outputs
page image caches/screenshots
*.sqlite user workspaces
CSV exports
human-decisions/
tests/fixtures development data where not required by runtime
Grist-only scripts/docs
```

Require canonical `evidence_review` package data to be present.

- [ ] **Step 2: Build wheel with Python 3.13**

```bash
py -3.13 -m pip wheel . --no-deps -w dist
```

Expected: `evidence_review_system-0.2.0-py3-none-any.whl`.

- [ ] **Step 3: Smoke test the installed wheel in a clean venv**

```bash
py -3.13 -m venv .venv-release-smoke
.venv-release-smoke\Scripts\python -m pip install dist\evidence_review_system-0.2.0-py3-none-any.whl
.venv-release-smoke\Scripts\python -m evidence_review --help
.venv-release-smoke\Scripts\python -m evidence_review doctor --repository-root .
```

Install runtime dependencies from the approved source appropriate to the acceptance environment before business-command smoke tests.

- [ ] **Step 4: Build runtime ZIP through the canonical release path**

Use migrated `evidence_review.release.builder` / canonical release CLI. Do not invoke `build_ansim_release.py`. Verify the ZIP without extraction through `evidence_review.release.output_verifier`, then extract a copy and run `bootstrap.py --self-test`.

- [ ] **Step 5: Produce deterministic `SHA256SUMS.txt`**

Include wheel, runtime ZIP, and release manifest when present. Use release filenames only, never local absolute paths.

- [ ] **Step 6: Finalize CHANGELOG v0.2.0**

Move unreleased changes under `## [0.2.0] - 2026-08-15` only when exact-head release acceptance is complete. Include Python 3.13-only support, namespace migration, compatibility/deprecation notes, #105–#110 fixes, security hardening, and removed historical/Grist artifacts.

- [ ] **Step 7: Run release tests**

```bash
py -3.13 -m pytest tests/unit/release tests/integration/release tests/integration/packaging -v
```

Expected: PASS.

- [ ] **Step 8: Commit release metadata, not transient build outputs**

```bash
git add pyproject.toml CHANGELOG.md scripts src tests docs
git commit -m "release: prepare v0.2.0 metadata and artifacts"
```

Generated distributions remain untracked unless an existing explicit repository rule requires tracking them.

---

### Task 11: Exact-HEAD integrated acceptance and Draft PR readiness

**Files:**
- Update: PR #111 with exact acceptance evidence.
- Do not recreate issue-number acceptance directories.

**Interfaces:**
- Consumes: candidate exact HEAD after Task 10.
- Produces: one auditable PASS/FAIL decision for whether PR #111 may move from Draft to Ready for review.

- [ ] **Step 1: Record exact candidate identity**

```bash
git rev-parse HEAD
git status --short
py -3.13 --version
py -3.13 -m evidence_review doctor --repository-root .
```

Expected: clean tracked tree; diagnostics point to the intended checkout.

- [ ] **Step 2: Run full pytest**

```bash
py -3.13 -m pytest -v
```

Expected: PASS except only explicitly justified skips.

- [ ] **Step 3: Run static gates**

```bash
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src/evidence_review
py -3.13 -m compileall -q src scripts web_runtime tests
```

Expected: PASS.

- [ ] **Step 4: Run documentation integrity**

```bash
py -3.13 -m evidence_review documentation validate --repository-root .
```

Expected: PASS, `errors=0`. Warnings must not identify broken current links or stale public instructions.

- [ ] **Step 5: Run clean wheel/runtime validation**

Repeat Task 10 wheel build/smoke, runtime ZIP validation, and `bootstrap.py --self-test` from the exact candidate HEAD. Record SHA-256 hashes.

- [ ] **Step 6: Run formal-review E2E on Python 3.13**

Use a sanitized repository fixture/document, not customer/user material. Exercise:

```text
PDF/parser fixture -> evidence.sqlite -> review-question prepare -> Track A handoff/validation -> Track B handoff/validation -> final-review-packet.json -> review.html -> protected review server
```

No Python 3.11 duplicate run is required.

- [ ] **Step 7: Run real-browser Review Workspace acceptance**

Validate:

```text
1366x768
1920x1080
3840x2160
single PDF / one citation
single PDF / multiple cited pages
multiple PDFs / multiple citations
keyboard-only source/page navigation
persisted completed decision + reload
explicit additional decision
protected lazy image loading
standalone archival review.html
print view
```

Confirm browser network traffic is loopback-only for protected review.

- [ ] **Step 8: Run public-tree sensitive-content scan**

Search tracked files for at least:

```text
password
secret
api_key
BEGIN PRIVATE KEY
private-user-images
customer-specific absolute paths/usernames
tracked PDF files outside explicit sanitized test fixtures
tracked SQLite files outside explicit deterministic test fixtures
```

Review every match manually; keyword scan alone is not proof of absence.

- [ ] **Step 9: Verify clean-clone contributor path**

In a fresh clone/venv using Python 3.13, follow `README.md` and `CONTRIBUTING.md` exactly through install, focused test, and documented full validation commands. Fix documentation instead of relying on undocumented local state.

- [ ] **Step 10: Check license/publication gate**

PR may become Ready for code review without a license while the repository remains private, but **repository visibility must remain private** until the owner selects and commits an intentional license. Record unresolved state as `BLOCKED_LICENSE_SELECTION`.

- [ ] **Step 11: Update PR #111 with exact acceptance evidence**

Include exact HEAD, Python version, OS, test counts, Ruff/mypy/compileall/doc status, wheel/runtime filenames and SHA-256, E2E status, browser matrix, remaining blockers, and license state.

- [ ] **Step 12: Mark Draft PR Ready only when implementation gates pass**

Do not mark Ready if any #105–#110 acceptance criterion is incomplete or an exact-head automated/browser test is failing. License selection may remain a separate public-visibility blocker if explicitly recorded.

---

## Post-Merge Release Procedure

This occurs only after the accepted PR is merged to `main`.

1. Confirm merged `main` exact HEAD equals the accepted code line or rerun all release-critical gates if merge changes source identity.
2. Build final wheel/runtime ZIP from merged `main` using Python 3.13.
3. Recompute `SHA256SUMS.txt` and release manifest.
4. Create tag `v0.2.0` at the accepted merged HEAD.
5. Create GitHub Release `Evidence Review System v0.2.0`.
6. Attach:

```text
evidence_review_system-0.2.0-py3-none-any.whl
evidence-review-system-v0.2.0-runtime.zip
SHA256SUMS.txt
release-manifest.json    # when generated by the release-governance path
```

7. Verify every uploaded asset hash against accepted local output.
8. Keep `v0.1.0` historical; do not retag or overwrite it.
9. Change repository visibility to public only after license selection and all public-visibility gates in the approved design pass.

---

## Issue Closure Matrix

| Issue | Primary Tasks | Required closure evidence |
|---|---:|---|
| #105 | 6, 8, 11 | multi-document viewer truthfulness, browser acceptance |
| #106 | 1, 2, 3, 4, 9, 10, 11 | active-tree cleanup, Python 3.13 policy, namespace/generalization, public repo readiness |
| #107 | 7, 11 | persisted decision read/display/append-only UI |
| #108 | 8, 11 | protected lazy image delivery + archive preservation + performance evidence |
| #109 | 5, 11 | strict manifest/path/size/hash validation + runtime self-test |
| #110 | 2, 3, 11 | one canonical dispatcher + entrypoint parity |

## Self-Review Checklist

- [x] Every approved design phase maps to at least one implementation task.
- [x] #105–#110 each have explicit closure evidence.
- [x] Python support is consistently 3.13-only.
- [x] Namespace migration happens before CLI/UI feature work, preventing double refactors.
- [x] `src/ansim_review/release/**` is explicitly migrated to `src/evidence_review/release/**` before release preparation.
- [x] #108 depends on #105 source/page state and therefore follows it.
- [x] Cleanup never deletes governed `rules/` wholesale.
- [x] Historical acceptance material is not recreated as issue-number folders.
- [x] Release artifacts are generated/attached after exact-head acceptance rather than committed casually.
- [x] Repository visibility is separate from code merge.
- [x] License is an explicit owner gate, not an assumed legal choice.
