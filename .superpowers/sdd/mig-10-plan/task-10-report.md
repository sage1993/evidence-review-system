# MIG-10 Formalization Adapter Report

## Scope

- Base SHA: `3b99dbcf939d4fe52638d2a594112522f3510dd6`
- Branch: `feat/mig-10-formalization-adapter`
- Implemented the adapter specified by `task-10-brief.md`; `review_run.py`,
  finalization, Track A/Track B, Review Packet, Human Decision, and evidence
  storage were not changed.

## Files

- `src/evidence_review/review_matter/formalization.py` — accepts only a frozen
  `FormalizationSnapshot`, reloads and byte-compares its persisted artifact,
  verifies current Matter revision, finalized evidence identity, and every
  selected evidence record, then builds the existing strict review-run request
  and delegates preparation through `review_question._prepare_from_document`.
- `tests/unit/review_matter/test_formalization_adapter.py` — supplied controller
  RED tests for input and snapshot authority.
- `tests/integration/review_matter/test_existing_formal_core_adapter.py` —
  supplied controller RED tests for strict-core preparation, deterministic
  resume identity, and immutable Matter state.

## Decisions

- Matter storage is resolved as the workspace-local `matter.sqlite` and must
  already exist as a verified regular file; the adapter never creates Matter
  state.
- Run inputs retain the strict `evidence-review/review-run-request` schema and
  place snapshot/Matter provenance only inside its existing `inputs` object.
- An identical request resumes an existing prepared run only after canonical
  request-byte and required-artifact verification; a differing existing run
  fails closed.
- The adapter returns `WAITING_TRACK_A` as a façade state while retaining the
  strict core's prepared-run artifact result. No Track A/B or finalizer behavior
  is reimplemented.

## Verification

- RED: `py -3.13 -c "import evidence_review.review_matter.formalization"` —
  failed with the expected missing-module error before implementation.
- GREEN: `py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_matter/test_formalization_adapter.py tests/integration/review_matter/test_existing_formal_core_adapter.py` — `6 passed`.
- Adjacent: `py -3.13 -m pytest -q -p no:cacheprovider tests/unit/review_matter/test_formalization_snapshot.py tests/unit/review_question/test_request_builder.py tests/unit/review_question/test_planned_snapshot_provenance.py tests/integration/review_run/test_review_run.py tests/integration/review_question/test_real_review_full_e2e.py` — `28 passed`.
- Static: `py -3.13 -m ruff check src/evidence_review/review_matter/formalization.py` and `py -3.13 -m mypy src/evidence_review/review_matter/formalization.py` — passed.

## Concerns

- Full repository acceptance, documentation validation, Windows platform stress,
  and browser QA were not run; they remain `NOT_RUN` for this focused MIG task.
- Sandboxed pytest temporary directories were permission-denied. The focused and
  adjacent tests above were run with approved normal Windows temporary-directory
  permissions.
