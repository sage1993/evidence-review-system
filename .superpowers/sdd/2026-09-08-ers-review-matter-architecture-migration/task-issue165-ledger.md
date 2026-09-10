# SDD ledger — Issue #165

## Scope and invariants

- [x] RED reproduces duplicate-basename collision before implementation.
- [x] Source resolution uses authoritative case/attachment stored path.
- [x] Source SHA-256 and attachment identity remain verified before decode.
- [x] Missing, ambiguous, traversal, symlink, and reparse paths fail closed.
- [x] Existing visual confirmation/candidate/decoder semantics remain intact.
- [x] Focused, adjacent, and targeted static gates pass.
- [ ] Full, documentation, browser/manual, and Actions gates run.
- [ ] Independent `gpt-5.6-sol-high` review is APPROVED.
- [ ] Push, PR, merge, Issue #165 closure, and ancestry are verified.

## Preflight ruling

Do not introduce a global basename search, newest-workspace selection, or
filesystem fallback. Reuse the existing immutable attachment/case layout and
filesystem trust helpers. Any required contract change outside
`drawing_review/visual_pages.py` and focused tests must be recorded before
implementation as `SCOPE_EXPANSION_REQUIRED = YES`.

## Execution record

- Base SHA: `02adac0bf81df462b229fc95d437c113c9af60d6`.
- Branch: `fix/issue-165-visual-source`.
- Worktree: `F:\\2026-PJ\\evidence-review-system-test\\.worktrees\\issue-165-visual-source`.
- Fix-round base HEAD: `4e5325b0046098e1499cf80cd038cd584ca93ed4`.
- Implementation agent: Codex (no `gpt-5.6-sol` or `gpt-6-astra` used).
- Independent review: the user supplied three `gpt-5.6-sol-high` findings;
  no additional independent-review model run was performed.
- Browser/manual acceptance and Actions: `NOT_RUN` until explicitly executed.
- `SCOPE_EXPANSION_REQUIRED = YES`: case-local source authority cannot be
  represented by the current `ImmutableAttachment` fields. This issue will add
  an optional `case_id` and a canonical case-local `stored_path` only for new
  CASE_DRAWING/SUPPORTING_IMAGE attachments, update the shared schema and
  drawing intake verification, and keep legacy non-visual attachment documents
  byte-compatible when no case identity is present.
- RED (2026-09-10): under Python 3.13 with an approved isolated temporary
  directory, `test_visual_image_cache_identity_includes_case_id_for_same_attachment_id`
  and `test_visual_pdf_cache_identity_includes_case_id_for_same_attachment_id`
  failed with `AttributeError: VisualPageAsset has no attribute case_id`.
  `test_verify_attachment_rejects_case_directory_identity_mismatch` failed
  because verification returned `()` rather than `SOURCE_CASE_MISMATCH`.
  Schema and decoder regressions failed 5 assertions because mixed legacy/case
  bindings were accepted. Initial sandboxed pytest attempts were blocked before
  execution by Windows temporary-directory permissions; those errors are
  environmental and are not counted as product RED results.
- GREEN focused/adjacent (2026-09-10): `py -3.13 -m pytest -q -p
  no:cacheprovider --basetemp <approved-isolated-dir>` over visual source
  authority, drawing source, immutable-attachment schema, next-action,
  visual-page tile, visual submission, lazy projection, and page-image cache
  suites: `52 passed in 1.36s`.
- Static (2026-09-10): changed-file Ruff: `All checks passed!`; changed-source
  mypy with `--no-incremental`: `Success: no issues found in 5 source files`;
  changed-file `compileall -q`: PASS (exit code 0, no output).
- Full pytest, repository-wide static checks, documentation validation,
  browser/manual acceptance, and Actions: `NOT_RUN` by the user's focused-test
  instruction. No push, PR, merge, Issue closure, or remote verification was
  performed.
- Fix-round report: `task-issue165-report.md` records changed identity,
  compatibility boundaries, and the exact verification outcomes above.
