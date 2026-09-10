# Issue #165 fix-round report — visual source identity

Date: 2026-09-10
Worktree: `F:\\2026-PJ\\evidence-review-system-test\\.worktrees\\issue-165-visual-source`
Branch: `fix/issue-165-visual-source`
Fix-round base HEAD: `4e5325b0046098e1499cf80cd038cd584ca93ed4`

## Result

The three supplied review findings are implemented without changing drawing
confirmation, decoder, MIME, candidate, or evidence authority semantics.

1. Visual raster and tile caches now use the complete immutable source key
   `case_id--attachment_id--source_sha256`. Image and tile metadata include
   case identity, attachment identity, stored path where applicable, and source
   hash. Two cases can therefore use the same attachment ID without reusing a
   cached raster or tile manifest.
2. `verify_immutable_attachment` rejects a case directory whose basename is not
   the attachment's `case_id` before converting the canonical case-local stored
   path to a physical path.
3. Immutable-attachment decoding and JSON Schema conditions agree: visual
   (`CASE_DRAWING`/`SUPPORTING_IMAGE`) attachments require a case-local
   `cases/<case_id>/sources/drawings/...` path and `case_id`; legacy
   `inputs/original/...` attachments forbid `case_id` and remain valid for
   non-visual reference/table roles.

The page-image cache gained optional additive metadata only. Existing callers
that do not pass metadata retain their previous metadata contract and cache
layout. The case-visual projection uses the same complete cache key to locate
the rendered raster.

## Verification

- RED: the supplied collision, case-directory mismatch, schema, and decoder
  regressions failed against base behavior. The product failures were
  `VisualPageAsset.case_id` absent, no `SOURCE_CASE_MISMATCH`, and acceptance
  of mixed bindings.
- GREEN focused/adjacent: 52 tests passed in 1.36s under Python 3.13.
- Targeted static: Ruff PASS; mypy PASS (`5 source files`); compileall PASS.
- NOT_RUN: full pytest, repository-wide static checks, documentation
  validation, browser/manual acceptance, Actions, push, PR, merge, issue
  closure, and remote verification.

No `gpt-5.6-sol` or `gpt-6-astra` implementation/review run was used. The
findings were user-supplied from a prior `gpt-5.6-sol-high` review.
