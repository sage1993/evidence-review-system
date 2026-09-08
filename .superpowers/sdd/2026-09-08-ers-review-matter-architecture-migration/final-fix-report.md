# Final whole-branch review fix report

## Scope and baseline

- Candidate before this fix: `51e41e845cff634ad39419b265e2f2e605bc5998` (`51e41e8`).
- This change addresses all four findings in `final-fix-brief.md`.
- User-owned `AGENTS.md`, the migration plan, DOCX report, and Korean report were not modified or staged.

## Implemented fixes

1. `MatterStore.rename()` now delegates to `append_matter_event()` with a
   `TITLE_CHANGED` event.  The append, projection, sequence, revision CAS, and
   metadata boundary are therefore the sole mutation authority for a rename.
   The new regression verifies that a renamed Matter rebuilds to the renamed
   title at revision 2 and retains the exact journal event.
2. `pyproject.toml` now packages `review_matter/schema.sql`.  The package-data
   test asserts the declaration.  An isolated Python 3.13 wheel build, install,
   and runtime smoke verified that the installed package can load the resource
   and create a `MatterStore`.
3. `REVIEW_MATTER_FORMAT` and `MATTER_SOURCE_BINDING_FORMAT` are imported from
   `evidence_review.contracts.formats`; `MATTER_EVENT_FORMAT` was added there
   and is imported by the event contract.  No ReviewMatter module now owns a
   duplicate literal definition of those shared formats.
4. `decode_matter_event()` uses `expect_string()` for `kind`, eliminating
   arbitrary `str(...)` coercion.  The regression supplies a non-string object
   whose `__str__` returns `TITLE_CHANGED` and verifies fail-closed rejection.

## TDD evidence

The newly added strict-kind and package-data checks were run before production
changes and failed as expected:

- strict kind: `Failed: DID NOT RAISE ValueError`;
- package data: `KeyError: 'evidence_review.review_matter'`.

The first rename RED invocation was blocked before its fixture started by the
pre-existing Windows ACL failure in the default `pytest-of-KSH` temporary root.
The same regression passed after using an isolated, task-scoped `--basetemp`.

## Verification

| Check | Result |
| --- | --- |
| `py -3.13 -m pytest -q --basetemp <task-scoped> -p no:cacheprovider tests/unit/review_matter tests/integration/review_matter tests/integration/packaging/test_runtime_package_data.py` | PASS — 42 passed in 1.56s |
| `py -3.13 -m ruff check src/evidence_review/contracts/formats.py src/evidence_review/review_matter tests/unit/review_matter tests/integration/review_matter tests/integration/packaging/test_runtime_package_data.py` | PASS — All checks passed |
| `py -3.13 -m pip wheel --no-deps --no-build-isolation --wheel-dir <task-scoped>/wheel .` | PASS — built `evidence_review_system-0.2.0-py3-none-any.whl` |
| Isolated `py -3.13 -m venv`, local wheel install, then `MatterStore` smoke | PASS — resource loaded from `venv/Lib/site-packages/evidence_review/review_matter/schema.sql`; created `MATTER-SMOKE` |

The wheel/install smoke directory and all task-scoped pytest directories were
removed after verification.

## Gates not run

The full repository pytest suite, documentation-integrity validation, both mypy
variants, compileall, and GitHub Actions were not run.  This report does not
claim merge readiness; `ACTIONS_NOT_RUN`.

## Commit boundary

Only the following implementation-owned files are intended for the commit:

- `pyproject.toml`
- `src/evidence_review/contracts/formats.py`
- `src/evidence_review/review_matter/contracts.py`
- `src/evidence_review/review_matter/events.py`
- `src/evidence_review/review_matter/store.py`
- `tests/integration/packaging/test_runtime_package_data.py`
- `tests/unit/review_matter/test_events.py`
- `tests/unit/review_matter/test_store.py`
- `.superpowers/sdd/2026-09-08-ers-review-matter-architecture-migration/final-fix-report.md`
