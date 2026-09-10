# Issue #164 / reviewer binding report

## Scope

`SCOPE_EXPANSION_REQUIRED = NO`. This change is limited to Drawing Review
calibration rendering and reviewer validation, their focused regressions, and
the Issue #164 SDD record. It does not change ReviewMatter, Workbench,
evidence authority, or historical fixture identities.

Base SHA: `b17b8fe7a257d5aafdc4a08f83f132a79191483d` (`origin/main`).
Branch: `fix/issue-164-reviewer-binding`. Python: `3.13.14` on Windows.

## Implementation

- The calibration HTML no longer preloads a maintainer identity. Once a
  confirmation exists, it displays that confirmation's server-recorded
  reviewer as a read-only value; otherwise the required input is blank.
- Calibration construction rejects blank, whitespace-padded, overlong,
  path-containing, and control-character reviewer values before a record can
  be persisted.
- The existing calibration POST binding remains authoritative: a reviewer in
  a client payload must exactly equal the indexed confirmation reviewer, or
  the server returns `BINDING_MISMATCH` without a calibration write.

## TDD and verification

- RED: 2 failed, 1 passed in 1.44s on a fresh Windows pytest base. The new
  tests exposed the hard-coded `ksh` calibration value and whitespace-only
  direct calibration reviewer acceptance. The missing-reviewer annotation
  POST already returned 400 without creating a confirmation.
- GREEN: 3 passed in 1.35s; a separate reviewer-override regression passed
  in 0.82s.
- Focused/adjacent suites: 121 passed in 17.98s. This includes the existing
  Unicode reviewer filename-token regression and append-only confirmation and
  calibration coverage.
- Full Python 3.13 pytest: 2095 passed, 1 skipped in 391.31s.
- Ruff: PASS. Mypy `src`: PASS (259 source files). Mypy `--platform win32
  src`: PASS (259 source files). Compileall: PASS.
- Source-tree documentation validation: PASS — 50 documents, errors=0,
  warnings=145. The literal installed-module invocation reported
  `SOURCE_MISMATCH` because it resolves another checkout; the recorded PASS
  is the required source-tree invocation with `PYTHONPATH=src`.

## Manual and remote gates

| Gate | Status |
| --- | --- |
| Browser/manual | `NOT_RUN` |
| GitHub Actions | `ACTIONS_NOT_RUN` |
| Independent gpt-5.6-sol-high review | `NOT_RUN` — not authorized for this implementer |
| Push, remote SHA parity, PR, merge, issue closure | `NOT_RUN` — explicitly out of scope |
