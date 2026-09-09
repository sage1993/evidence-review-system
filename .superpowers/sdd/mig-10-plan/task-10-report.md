# MIG-10 Formalization Adapter Report

## Scope

- Base SHA: `e4ec7cc2ce7bb05c74c82300e051328ab31ce9ea`
- Branch: `feat/mig-10-formalization-adapter-sequential`
- Implemented the adapter specified by `task-10-brief.md`; `review_run.py`,
  finalization, Track A/Track B, Review Packet, Human Decision, and evidence
  storage remain authoritative and unchanged.

## Files

- `src/evidence_review/review_matter/formalization.py` — accepts only a frozen
  `FormalizationSnapshot`, reloads and byte-compares its persisted artifact,
  verifies current Matter revision, finalized evidence identity, and every
  selected evidence record, then builds the existing strict review-run request
  and delegates preparation through the canonical `PreparedReviewQuestion`
  handoff in `review_question.py`.
- `src/evidence_review/review_question.py` — provides the strict-request
  preparation façade that creates the existing Track A next-action artifact and
  workflow journal before returning the prepared question.
- `tests/unit/review_matter/test_formalization_adapter.py` — supplied controller
  RED tests for input and snapshot authority.
- `tests/integration/review_matter/test_existing_formal_core_adapter.py` —
  supplied controller RED tests for strict-core preparation, deterministic
  resume identity, and immutable Matter state, plus round-1 regressions for
  approved-ID ordering and Matter/evidence promotion races.

## Decisions

- Matter storage is resolved as the workspace-local `matter.sqlite` and must
  already exist as a verified regular file; the adapter never creates Matter
  state.
- Run inputs retain the strict `evidence-review/review-run-request` schema and
  place snapshot/Matter provenance only inside its existing `inputs` object.
- An identical request resumes an existing prepared run only after canonical
  request-byte and required-artifact verification; a differing existing run
  fails closed.
- The adapter returns the existing `PreparedReviewQuestion` contract at
  `WAITING_TRACK_A`; it does not reimplement Track A/B or finalizer behavior.
- FormalizationSnapshot is the only source for Matter-selected evidence and
  scope. Calculations, rules, and approved rule IDs are empty at this one-way
  boundary and cannot be supplied by the adapter caller.

## Round 1 fixes

- P1-1: approved rule result IDs are validated and sorted with the same
  canonical order as the strict `review_run.py` decoder before run identity and
  resume lookup.
- P1-2: the existing Matter store `BEGIN IMMEDIATE` transaction now covers the
  final Matter revision check and strict preparation. A revision changed before
  the boundary is rejected; a writer arriving after the boundary is serialized
  behind the completed promotion.
- P1-3: finalized evidence provenance is checked before and after selected-row
  verification and again immediately before preparation. The request uses the
  post-selection verified provenance, and any final drift fails before run
  creation.

## Round 2 fix

- The strict request contract already permits arbitrary canonical keys inside
  its existing `inputs` mapping, so no decoder/version change was required.
- The adapter now carries `review_scope_document(snapshot.review_scope)` at
  `inputs.review_scope`. This preserves facts, assumptions, issues, legal
  anchors, and search-request lineage through the strict request decoder and
  into the Track A bundle.
- The regression compares canonical JSON bytes from prepared
  `review-request.json` with the snapshot's canonical scope document.

## Round 3 fix

- The strict request decoder permits arbitrary nested `inputs` keys, so the
  adapter now strictly decodes `review_scope_document(snapshot.review_scope)`
  and re-encodes it before request construction.
- The adapter compares the supplied and persisted scope documents by canonical
  bytes and uses only the validated canonical document for the request and
  Track A bundle. Existing prepared Track A bundles are re-decoded and compared
  with that same canonical document before resume.
- Existing prepared requests remain fail-closed through canonical request-byte
  equality, while malformed or mismatched scope serialization is rejected
  before any new run is created or resumed.

## Round 4 fix

- Existing-run resume now re-runs the strict `_decode_request` decoder against
  the stored `review-request.json` and requires its normalized request bytes to
  match both the stored canonical request and the expected request document.
- It rebuilds `track-a-bundle.json` with the existing deterministic
  `build_track_a_bundle`/`track_a_bundle_document` path and compares canonical
  bytes, while retaining the prior canonical ReviewScope check.
- It decodes and normalizes `confidence-input.json` with the existing strict
  confidence decoder and compares its canonical bytes with the stored and
  expected confidence documents. Any mismatch fails before `WAITING_TRACK_A`
  is returned.

## Review blocker fixes

- Caller-supplied calculations, rules, and approved rule IDs were removed from
  `formalize_snapshot`; the request authority is now limited to the persisted
  `FormalizationSnapshot` and canonical empty engine-result collections.
- Formalization now uses the existing `PreparedReviewQuestion` handoff so
  `next-action-track-a.json` and the append-only workflow journal are created;
  normal `submit-track-a` resume behavior remains available.
- Evidence provenance is revalidated after preparation. If a newly created run
  fails that final check, its exact run directory is removed; an existing stale
  run is retained but remains fail-closed.

## Verification

- RED: `py -3.13 -c "import evidence_review.review_matter.formalization"` —
  failed with the expected missing-module error before implementation.
- GREEN: `py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_matter/test_formalization_adapter.py tests/integration/review_matter/test_existing_formal_core_adapter.py` — `6 passed`.
- Adjacent: `py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_matter/test_formalization_snapshot.py tests/unit/review_question/test_request_builder.py tests/unit/review_question/test_planned_snapshot_provenance.py tests/integration/review_run/test_review_run.py tests/integration/review_question/test_real_review_full_e2e.py` — `28 passed`.
- Static: `py -3.13 -m ruff check src/evidence_review/review_matter/formalization.py` and `py -3.13 -m mypy src/evidence_review/review_matter/formalization.py` — passed.
- Round-1 RED: the three new regression tests failed on the pre-fix adapter with
  the observed nondeterministic run identity, Matter race, and provenance drift
  behaviors.
- Round-1 GREEN: focused adapter tests — `9 passed`.
- Round-2 RED: the new scope-preservation regression failed with `KeyError:
  'review_scope'` before the compatibility field was added.
- Round-2 GREEN: relevant ReviewMatter, review-run, and scope-provenance tests
  — `121 passed`.
- Round-2 static checks: Ruff, mypy, and compileall passed for the adapter and
  regression tests.
- Round-3 RED: malformed snapshot scope and tampered prepared Track A scope
  regressions both reproduced successful acceptance (`DID NOT RAISE`) before
  boundary validation was added; the exact-byte bundle regression established
  the required canonical output.
- Round-3 GREEN: focused and adjacent suites — `124 passed in 18.41s`.
- Round-3 static checks: Ruff, mypy, and compileall passed for the adapter and
  regression tests.
- Round-4 RED: the non-scope Track A bundle tamper regression reproduced
  successful resume (`DID NOT RAISE`) before deterministic artifact validation
  was added.
- Round-4 GREEN: adapter regression file — `11 passed`; focused and adjacent
  suites — `125 passed in 18.70s`.
- Round-4 static checks: Ruff, mypy, and compileall passed for the adapter and
  regression tests.
- Round-5 RED: caller-supplied authority inputs, missing canonical Track A
  handoff artifacts, and post-preparation provenance drift were reproduced
  before the blocker fixes.
- Round-5 GREEN: focused adapter suite — `16 passed in 15.18s`; adjacent
  regression suite — `28 passed in 8.70s`.
- Round-5 targeted static checks: Ruff and mypy passed for the changed runtime
  modules and regression tests.

## Concerns

- Repository-wide exact-HEAD acceptance is recorded separately in the PR
  acceptance evidence; GitHub Actions are `ACTIONS_NOT_RUN`.
- Windows platform stress and browser QA remain `NOT_RUN` for this focused MIG
  task. Existing untracked MIG-09 pytest temp directories were preserved, so a
  clean-worktree acceptance was not established here.
- Sandboxed pytest temporary directories were permission-denied. The focused and
  adjacent tests above were run with approved normal Windows temporary-directory
  permissions.
