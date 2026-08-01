# Drawing Backend Plan Corrections

> **For agentic workers:** This document is authoritative where it conflicts with `2026-08-02-generic-parser-registry-state-model.md` or `2026-08-02-evidence-review-namespace-fixtures-e2e.md`.

**Reviewed main:** `09f6209ccdcb81dad3a14d32a8efb5165dd723b7`

**Purpose:** Align the remaining #22 plans with the merged M1 drawing backend and the candidate-provenance hotfix.

## 1. Existing boundaries that must be preserved

The current runtime already has two distinct state layers:

```text
source-batch preparation routing
  DRAWING_BACKEND_ONLY

case drawing workflow projection
  PENDING_DRAWING_INGESTION
  INPUT_CONFIRMATION_REQUIRED
  READY_TO_EVALUATE
  BLOCKED
  FAILED
```

`DRAWING_BACKEND_ONLY` is a source-routing result. It is not a workflow state and must not be replaced by `PENDING_DRAWING_INGESTION` inside `source_batch_importer.py`.

`src/ansim_review/parsing/drawing_workflow.py` remains the sole authority for drawing workflow projection. The parser/state PR must not introduce a second implementation of drawing confirmation or drawing workflow transitions.

## 2. Corrections to the parser registry and source-state plan

### 2.1 Source-state responsibility

The planned `source_states.py` module is limited to generic source preparation and aggregate reference readiness:

```text
RECEIVED
CLASSIFYING_INPUTS
PENDING_PARSER_OUTPUT
PENDING_REFERENCE_INGESTION
READY_TO_EVALUATE
BLOCKED
FAILED
```

Drawing-specific projection is delegated to the existing drawing backend:

```python
project_drawing_workflow(run_id, DrawingWorkflowFacts(...))
```

The generic state module may report that a source is routed to the drawing backend, but it may not duplicate these states:

```text
PENDING_DRAWING_INGESTION
INPUT_CONFIRMATION_REQUIRED
```

### 2.2 Required routing matrix

```text
REFERENCE_DOCUMENT + no parser
  -> PENDING_PARSER_OUTPUT

REFERENCE_DOCUMENT + registered parser
  -> PENDING_REFERENCE_INGESTION

CASE_DRAWING + no parser
  -> DRAWING_BACKEND_ONLY
  -> existing drawing backend controls later workflow

CASE_DRAWING + registered parser
  -> parser may emit neutral drawing evidence
  -> source still enters drawing confirmation workflow before values bind to engines

CASE_TABLE or SUPPORTING_IMAGE + no parser
  -> PENDING_PARSER_OUTPUT

batch with no parser-ready evidence source
  -> NO_EVIDENCE_SOURCES
  -> no SQLite database created
```

### 2.3 Parser contribution boundary

A parser adapter may emit neutral elements, tables, and visuals for a drawing. It must not create `ConfirmedInput`, set a confirmation action, or advance drawing workflow to `READY_TO_EVALUATE`.

All engine-eligible drawing values continue through:

```text
immutable source
-> candidate artifact
-> append-only confirmation
-> confirmed input
-> provenance-reverified engine binding
```

### 2.4 Importer task correction

The parser/state plan Task 6 must preserve these existing behaviors from `source_batch_importer.py`:

- parserless `CASE_DRAWING` does not block parser-ready reference ingestion;
- drawing-only batches reject empty evidence DB creation;
- all prepared sources remain in the status report, including `DRAWING_BACKEND_ONLY` sources;
- registry dispatch replaces only the hard-coded ODL parser conditional.

## 3. Candidate and confirmation provenance contract

The following interface is frozen before the remaining #22 work:

```python
bind_confirmed_inputs(
    case_dir,
    inputs,
    source_attachments,
    *,
    candidate_entries,
)
```

The binding step must reverify:

```text
immutable source size and SHA-256
candidate manifest entry identity
candidate file SHA-256
candidate ID, source SHA-256, and page
confirmation file SHA-256
confirmation candidate ID, source SHA-256, action, value, unit, and geometry
```

Confirmation semantics are fixed:

```text
ACCEPTED
  -> no confirmed_value
  -> no unit
  -> no replacement geometry
  -> candidate value and geometry are used unchanged

EDITED
  -> replacement value or geometry required

CREATED
  -> reviewer-manual CREATED candidate only
  -> confirmed value or geometry required
```

The parser registry and namespace migration must preserve the regression tests introduced by PR #29.

## 4. Corrections to the namespace and fixture plan

The namespace migration must explicitly move and update these merged files:

```text
src/ansim_review/parsing/drawing_binding.py
src/ansim_review/parsing/drawing_candidates.py
src/ansim_review/parsing/drawing_case.py
src/ansim_review/parsing/drawing_confirmation.py
src/ansim_review/parsing/drawing_inputs.py
src/ansim_review/parsing/drawing_quality.py
src/ansim_review/parsing/drawing_source.py
src/ansim_review/parsing/drawing_workflow.py
schemas/case-manifest.schema.json
tests/golden/drawing/manual-confirmed-inputs.json
tests/integration/drawing/**
tests/unit/parsing/test_drawing_*.py
```

The canonical package move must update imports without weakening create-only writes, path containment, source MIME checks, resource limits, candidate/confirmation hashing, or engine-binding revalidation.

### 4.1 Format migration

The namespace PR must migrate new drawing artifacts from `ansim/*` to versioned `evidence-review/*` formats. Old artifacts remain readable only through explicit legacy adapters.

At minimum, plan and test migration for:

```text
ansim/case-manifest
ansim/confirmed-input-set
ansim/workflow-state
```

The migration must not silently rewrite stored legacy files in place.

### 4.2 Fixture matrix correction

The generic fixture matrix must include a complete drawing case:

```text
parserless CASE_DRAWING -> DRAWING_BACKEND_ONLY
immutable case-local copy
manual or neutral extractor candidate
append-only confirmation
candidate and confirmation tamper rejection
confirmed input binding
READY_TO_EVALUATE projection
```

The drawing E2E test must pass candidate manifest entries to `bind_confirmed_inputs()` and prove that candidate file tampering blocks engine binding.

## 5. Updated execution precondition

The six-PR roadmap now has this prerequisite:

```text
PR #29 drawing provenance hotfix merged
  -> #19 schema v2
  -> #25 and #26
  -> #20
  -> #22 parser/state
  -> #22 namespace/fixtures/E2E
```

No implementation task may restore the pre-PR #29 binding signature or permit `ACCEPTED` confirmations to replace candidate data.
