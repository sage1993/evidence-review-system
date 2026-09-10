# SDD ledger — Issue #164 / reviewer binding

## Preflight rulings

| Boundary | Ruling |
| --- | --- |
| Production calibration HTML | Never prefill a maintainer-specific reviewer identity. |
| Confirmation/calibration persistence | Require a non-empty validated reviewer identity before append-only storage. |
| Server-bound reviewer | Treat server identity as authoritative; reject client override or mismatch. |
| Existing fixtures/history | Do not rewrite historical fixture identities unless required by the production contract. |

## Checklist

- [x] RED reproduces hard-coded default / missing-reviewer persistence gap
- [x] Production default removed and explicit reviewer required
- [x] Server-side binding cannot be overridden
- [x] Unicode regression and append-only semantics retained
- [x] Focused/adjacent tests pass
- [x] Exact Python 3.13 full/static/docs gates pass
- [x] Independent gpt-5.6-sol-high review PASS/APPROVED; no findings
- [ ] Remote SHA parity, PR, merge, issue closure, ancestry verified

## Scope control

- `SCOPE_EXPANSION_REQUIRED = NO` initially.
- Do not modify ReviewMatter, Workbench, evidence authority, or unrelated historical fixtures.

## Independent review record

- Exact candidate reviewed: `b17b8fe7a257d5aafdc4a08f83f132a79191483d` →
  `1d5c2d41087ef11cfb68e0675f376a08d86956bf`.
- `gpt-5.6-sol-high`: Spec compliance PASS; Task quality APPROVED; Critical,
  Important, and Minor findings: none.
- Review confirmed no maintainer-specific production reviewer identity,
  explicit/validated reviewer persistence, server-bound mismatch rejection,
  Unicode coverage, append-only semantics, and no unrelated authority/history
  changes.

## Execution record

- Base SHA: `b17b8fe7a257d5aafdc4a08f83f132a79191483d` (`origin/main`); branch:
  `fix/issue-164-reviewer-binding`.
- RED (Python 3.13.14, fresh Windows temp base): 2 failed, 1 passed in 1.44s.
  The calibration form rendered the hard-coded `ksh` instead of the confirmed
  Unicode reviewer, and direct calibration construction accepted a
  whitespace-only reviewer. The missing-reviewer action POST already failed
  closed without a confirmation write.
- GREEN: 3 passed in 1.35s; reviewer-override regression: 1 passed in 0.82s.
- Adjacent Drawing Review/calibration suites: 121 passed in 17.98s, including
  existing Unicode reviewer-token and append-only confirmation coverage.
- Full Python 3.13 pytest: 2095 passed, 1 skipped in 391.31s.
- Ruff, mypy (`src`), mypy (`--platform win32 src`), compileall, and
  source-tree documentation validation: PASS (50 documents, errors=0,
  warnings=145).
- Browser/manual acceptance: `NOT_RUN`. GitHub Actions: `ACTIONS_NOT_RUN`.
- Independent `gpt-5.6-sol-high` review, remote parity, PR, merge, and issue
  closure: `NOT_RUN` (outside this implementer authorization).
