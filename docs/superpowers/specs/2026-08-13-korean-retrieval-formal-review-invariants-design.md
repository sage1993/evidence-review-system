# Korean Retrieval and Formal Review Invariants Design

Issue: #95  
Parent: #87  
Date: 2026-08-13

## 1. Problem statement

A real formal-review E2E question, `청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다.`, produced `hits=[]` even though the parsed evidence database contained relevant source text. The failure occurred at deterministic retrieval before Track A.

The same run exposed four downstream fail-closed inconsistencies and one retry defect:

1. zero evidence still produced confidence factors initialized to `1.0`;
2. zero Track A claims allowed Track B `overall_disposition=ACCEPT`;
3. finalization reported `MISSING_REQUIRED_INPUT` while the review summary reported `missing_input_count=0`;
4. snapshot lineage was present in the request/bundle but absent from the final packet and UI audit metadata;
5. the first Track A submission produced `FILEEXISTSERROR`, making `retry_count=1`.

The parser and evidence database are not the primary failure point. The design therefore changes retrieval and formal-review invariants without adding model/API query rewriting.

## 2. Goals

- Retrieve relevant Korean evidence despite spacing, particles, compound nouns, and numeric punctuation differences.
- Keep retrieval deterministic and traceable.
- Avoid broad token-OR behavior that would substantially reduce precision.
- Preserve source/table context needed to distinguish similarly named facilities and different applicability rows.
- Fail closed when no evidence or no auditable claims exist.
- Keep review summary and finalizer reasons consistent.
- Preserve snapshot lineage through the final packet and review UI.
- Eliminate the observed normal-path Track A artifact collision/retry.

## 3. Non-goals

- LLM/API query rewriting.
- External search engines.
- A quick-review mode.
- Broad morphology/NLP dependency introduction for Korean.
- Review Workspace visual redesign beyond correcting inconsistent summary data.

## 4. Chosen approach

### 4.1 Deterministic grouped query variants

Add a small deterministic query-expansion layer before lexical retrieval. It produces traceable variants in three groups:

- **entity**: compound noun and spacing variants, e.g. `청소년문화의집`, `청소년 문화의집`;
- **numeric**: punctuation/unit variants, e.g. `1500`, `1,500`, `1,500제곱미터`;
- **predicate/concept**: bounded approved concept variants relevant to indexed terminology, e.g. `면적`, `연면적`, `연건축면적`, `이상`.

The expansion layer must be deterministic, ordered, and origin-labelled. It must not use arbitrary token OR.

The initial implementation should use explicit normalization rules and a small approved concept-variant map rather than a general Korean morphological analyzer. This keeps the offline/runtime footprint small and makes every generated term inspectable.

### 4.2 Retrieval strategy

Keep exact phrase and token-AND channels for precision, then add grouped fallback channels:

1. exact phrase on the normalized primary query;
2. token-AND on the normalized primary query;
3. entity variant search;
4. numeric variant search;
5. approved predicate/concept variant search;
6. fusion that rewards evidence hit by multiple groups.

A result found only by a weak concept variant should rank below a result matching both the facility entity and numeric constraint. The fusion trace must retain which variant/group produced each score.

No channel may return uncitable evidence. Existing page/revision/source-hash requirements remain mandatory.

### 4.3 Context expansion

After candidate retrieval, expand evidence context only within deterministic structural boundaries already represented in the evidence database.

For table-backed evidence, prefer the complete indexed table/row representation or the smallest available record that includes both the row label and the criterion text. For non-table evidence, keep the existing element text and do not synthesize surrounding prose.

The representative regression must expose both:

- the `청소년수련관` row containing `연건축면적이 1,500제곱미터 이상...`;
- the separate `청소년문화의집` row/definition.

This permits Track A to determine applicability instead of seeing a detached `1,500㎡` sentence.

## 5. Formal-review invariants

### 5.1 Zero-evidence confidence

`build_review_run_request()` must derive confidence input from evidence availability rather than assigning all factors `1.0` unconditionally.

For zero retrieval hits, evidence-dependent confidence factors must be zero or otherwise explicitly fail the confidence hard gate. The exact factor mapping must remain compatible with the existing confidence scorer and must not fabricate a high numeric score that is later merely relabelled LOW.

### 5.2 Zero-claim Track B

Track B may not vacuously accept an empty claim set.

If Track A yields zero auditable claims, Track B validation must produce/require `INCOMPLETE` semantics or stop before Track B with an explicit no-auditable-claims state. The implementation should choose the smallest contract change that preserves existing serialized formats where possible.

`ACCEPT` with `claim_audits=[]` is invalid.

### 5.3 Missing-input projection consistency

The review view model must include missing inputs originating from Track A/finalization, not only rule results. `missing_input_count`, additional-review copy, and the finalizer hard-gate reason must describe the same underlying set.

Deduplicate missing input labels deterministically before counting.

### 5.4 Snapshot lineage preservation

The authoritative snapshot hash already bound into the review request must survive finalization. Add it to the final review packet contract or a compatible v2 projection and expose it in audit metadata.

The snapshot hash remains audit data; it must not be promoted to the nondeveloper default screen.

### 5.5 Track A retry/idempotency

Reproduce the observed `FILEEXISTSERROR` with a focused test before changing code. Determine which create-only artifact is being written twice during normal submission/resume.

The fix must preserve immutable/create-only semantics. It must not solve the retry by silently overwriting an existing artifact. If an identical artifact already exists due an interrupted/resumed valid transition, treat it as idempotent only after byte/hash equality validation.

## 6. Components and boundaries

Expected touch points:

- `src/ansim_review/retrieval/query.py`
  - deterministic variant generation and trace metadata;
- `src/ansim_review/retrieval/index.py`
  - variant-safe lexical helpers if needed;
- `src/ansim_review/retrieval/bundle.py`
  - grouped channels, fusion inputs, context expansion;
- `src/ansim_review/review_question.py`
  - evidence-aware confidence input and retry/idempotency fix if root cause is here;
- `src/ansim_review/llm_layer/track_b.py`
  - reject empty vacuous ACCEPT;
- final packet contract/finalizer codec files
  - snapshot lineage preservation;
- `src/ansim_review/review_packet/builder.py`
  - missing-input projection and audit metadata;
- focused retrieval/review-question/Track B/review-packet tests.

Changes must remain narrowly scoped. Do not refactor unrelated parser, rule-engine, release, or UI code.

## 7. Data flow

```text
natural-language question
  -> canonical normalization
  -> deterministic grouped variants
  -> phrase/token-AND/grouped lexical channels
  -> fusion with origin trace
  -> structural context expansion
  -> evidence bundle
  -> evidence-aware review request/confidence input
  -> Track A
  -> immediate Track A validation
  -> non-empty auditable claims required for ACCEPT audit
  -> Track B
  -> finalizer with snapshot lineage
  -> view model with consistent missing-input projection
  -> Review HTML
```

## 8. Error handling

- Empty primary question: existing fail-fast behavior remains.
- Invalid generated variant: generator must not emit it; no runtime best-effort fallback.
- No retrieval hits: produce a valid fail-closed review request, never a high-confidence normal request.
- No auditable claims: cannot produce Track B ACCEPT.
- Stale retrieval index: existing `StaleRetrievalIndexError` remains authoritative.
- Missing citation identity/bbox/source hash: existing citation fail-closed behavior remains.
- Existing Track A artifact differs: keep `FileExistsError`/conflict behavior.
- Existing Track A artifact is byte-identical during a valid resume: allow idempotent continuation without incrementing retry.

## 9. Test design

TDD order:

1. add Korean normalization/variant unit tests;
2. add retrieval regression fixture reproducing the exact E2E question and source rows;
3. prove current code returns zero or insufficient hits;
4. implement grouped variant retrieval and context expansion;
5. add zero-evidence confidence regression;
6. add empty-claims Track B ACCEPT rejection regression;
7. add finalizer/view-model missing-input consistency regression;
8. add snapshot lineage final-packet/UI regression;
9. reproduce Track A `FILEEXISTSERROR` and implement idempotent identical-artifact resume;
10. run focused suites, then Ruff, mypy, compileall, and full pytest.

The representative retrieval test must assert evidence relevance, not only `hits > 0`: at minimum one hit/context must identify `청소년문화의집`, and one must expose the `청소년수련관` 1,500㎡ criterion so Track A can distinguish applicability.

## 10. Acceptance

- Representative Korean question returns relevant traceable evidence.
- Generated variants are deterministic across repeated runs.
- No broad token-OR fallback.
- Zero-evidence run cannot report nominal 1.0 confidence factors.
- Empty claim set cannot be audited as ACCEPT.
- Missing-input count and finalizer reason agree.
- Snapshot hash is visible in audit metadata and preserved in the final packet lineage.
- Normal valid Track A submission/resume produces retry count 0.
- Focused tests pass.
- Ruff, mypy, compileall pass.
- Full pytest passes before claiming implementation complete.
- Windows Python 3.11/3.13 E2E remains part of #93 integration acceptance.
