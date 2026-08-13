# Issues #98–#101 Integrated Fix Design

Issues: #98, #99, #100, #101  
Related: #92, #95  
Base: `main` at `820fff52c568ec860cc2d92459e4502fccfc14e3`  
Date: 2026-08-14

## 1. Problem statement

Four P1 issues were discovered during real `$ERS_REVIEW` operation. They look separate at the UI level, but they share one critical property: each can make the user distrust whether the final review result was produced from the intended source, query, Track B artifact, or review item.

- #99: the CLI may execute a stale installed checkout instead of the active development checkout.
- #100: Korean compound terms and exact phrases can exist in the evidence database but still miss deterministic FTS retrieval.
- #101: a valid run-local `track-b-output.json` is treated as a generated-output collision during finalization.
- #98: the formal-review path does not consistently open/return the protected result view, and selecting a review item does not move the PDF viewer to that item's first citation; its Korean-spacing symptom depends on #100.

The integrated fix must restore end-to-end trust without weakening the system's evidence-first and fail-closed guarantees.

## 2. Goals

1. Make the runtime provenance observable and fail closed when a development checkout is executing code from another checkout.
2. Retrieve bounded Korean compound/spacing variants deterministically while preserving existing English/numeric behavior.
3. Treat validated Track B output as an input artifact, not as a finalizer-generated artifact, with deterministic retry semantics.
4. Make `review-question submit-track-b --open` return a usable protected review handoff using the already-implemented #92 detached server lifecycle.
5. Make review-item selection and PDF page/bbox focus one coherent interaction for mouse and keyboard users.
6. Preserve citation IDs, evidence/source hashes, snapshot hash, packet authority, and fail-closed validation semantics.
7. Finish with Windows Python 3.11/3.13 acceptance and real-browser checks at 1366×768, 200% zoom, and print.

## 3. Non-goals

- No LLM/API query rewrite.
- No external Korean morphology service or new heavyweight NLP dependency.
- No redesign of the protected loopback server lifecycle already completed in #92.
- No evidence text, citation, source hash, or packet authority rewriting for search convenience.
- No unrelated parser, rule-engine, release, or broad UI refactor.
- No automatic overwrite of immutable run artifacts.

## 4. Chosen architecture

The integrated PR is one delivery vehicle, but implementation remains four bounded subsystems with explicit dependencies.

```text
Phase A: Runtime provenance (#99)
        |
        +--> trusted execution environment
               |
               +--> Phase B1: Korean lexical retrieval (#100)
               |
               +--> Phase B2: Track B ownership/retry (#101)
                              |
                              +--> Phase C: Formal-review UX integration (#98)
                                      - protected handoff
                                      - item -> citation -> PDF focus
                                      - zero-hit guidance / #100 E2E
```

#99 lands first because later acceptance results are not trustworthy if the executable can silently come from another checkout. #100 and #101 are functionally independent and may be implemented in parallel after the provenance gate exists. #98 is the final integration phase because it consumes the retrieval fix and the #92 protected-server contract.

## 5. Component design

### 5.1 Runtime provenance and dependency-safe bootstrap (#99)

The console-script entrypoint must become diagnostic-safe before importing heavy runtime modules.

Current packaging binds `evidence-review` to `evidence_review.cli:main`. The bootstrap layer should therefore remain under `src/evidence_review/` and use only the Python standard library until it has handled `doctor`, `--version`, and provenance preflight.

Create `src/evidence_review/diagnostics.py` with a small immutable diagnostic model and functions that report:

- `sys.executable`;
- resolved console-script path when available;
- distribution version;
- current working directory;
- requested/detected repository root;
- repository HEAD when Git metadata is available;
- actual imported `ansim_review` package path without importing heavy submodules;
- whether the package path matches `<repository>/src/ansim_review` for development checkout execution;
- required dependency availability and version;
- status: `OK`, `SOURCE_MISMATCH`, `DEPENDENCY_MISSING`, or `NOT_A_CHECKOUT`.

Development-checkout semantics:

- If the process is inside or explicitly pointed at this repository checkout and the package source is from another checkout, normal commands fail before business logic executes.
- A wheel/install used outside a checkout is not rejected merely because no Git commit is available.
- Missing runtime dependencies produce a structured `DEPENDENCY_MISSING` diagnostic rather than an eager-import traceback.

Normal commands then lazy-import `ansim_review.entrypoint` only after preflight succeeds.

### 5.2 Bounded Korean lexical fallback (#100)

The existing #95 grouped-variant design remains authoritative. This change extends it rather than replacing it.

Before implementation, characterization tests must determine whether the representative misses come from:

1. FTS `unicode61` token boundaries;
2. embedded whitespace/line-break/format characters in indexed text;
3. missing derived variants for independent Korean lexical terms.

The fix adds one deterministic Korean compound channel without removing or weakening existing channels.

Recommended search order:

1. `fts_phrase`;
2. `fts_token_and`;
3. bounded `fts_korean_compound`;
4. existing grouped entity/numeric/concept channels;
5. existing fusion.

The Korean helper may normalize only evidence-insensitive search representations: NFC, repeated whitespace, known zero-width format characters, bounded Hangul spacing compaction, and the existing suffix/particle rules. It must not mutate `retrieval_records.raw_text`, authoritative normalized evidence text, citation fields, or snapshot lineage.

If FTS tokenization itself prevents a correct bounded match, add derived searchable terms to the FTS search representation only. Do not add a schema migration unless characterization proves the existing FTS table cannot support the required behavior.

Every fallback hit keeps an origin trace such as `derived:korean_compound:<term>` so the bundle remains auditable.

### 5.3 Track B artifact ownership and retry contract (#101)

`track-b-output.json` is reclassified conceptually as a validated input artifact, symmetric with `track-a-output.json`.

Validated inputs:

- `track-a-output.json`
- `track-b-output.json`

Finalizer-generated artifacts:

- `run-manifest.json`
- `final-review-packet.json`
- `review.html`

Submission semantics:

- same-path run-local Track B: validate and reuse without rewriting;
- external Track B path: validate, then publish to run-local `track-b-output.json` using create-or-identical semantics;
- existing run-local Track B with different canonical bytes: fail closed with a contract-specific mismatch error;
- `FINALIZING` retry: compare the submitted Track B hash with the hash journaled when entering `FINALIZING`; identical retry may continue, differing retry must fail before finalizer execution;
- incomplete-finalization recovery removes only restartable finalizer outputs and preserves validated Track A/B inputs.

Raw `FileExistsError` must no longer represent a valid run-local submission. Validation failures, input mismatch, generated-artifact collision, and publish collision must remain distinguishable.

### 5.4 Formal-review protected handoff (#98, result display)

Do not create another server lifecycle. Reuse the completed #92 `open_review_run()` / detached protected loopback path.

Extend `review-question submit-track-b` with `--open`.

On successful finalization, stdout always includes at least:

- format/version/stage;
- `status`;
- `run_id`;
- `review_html` path.

When `--open` is requested, also return a display outcome and protected URL when available. If browser dispatch fails after packet/HTML creation, the CLI must clearly report that display failed while preserving the successful review result and HTML path. It must not make the user infer that finalization failed.

The command must remain bounded and inherit #92's loopback/token/idle-timeout/process-identity rules.

### 5.5 Review-item to PDF evidence focus (#98, workspace interaction)

`focusEvidence()` remains the single source of truth for PDF page/bbox movement.

`selectReviewItem()` should:

1. select the review item and update the detail panel;
2. resolve the item's first valid citation/evidence link;
3. activate the evidence/PDF context as needed;
4. call the existing `focusEvidence()` path;
5. leave PDF state unchanged when the item has no citation.

Mouse and keyboard item changes must flow through the same selection function. For multiple citations, item selection focuses the first citation; clicking another citation continues to focus that citation normally.

No page/bbox positioning logic should be duplicated inside `selectReviewItem()`.

### 5.6 Zero-hit user guidance (#98 consuming #100)

The retrieval engine remains fail closed. If the original query returns no authoritative evidence but bounded deterministic Korean variants were derived, the formal-review handoff may expose the attempted normalized/derived terms as guidance.

The guidance must:

- preserve the original query and each query origin;
- never fabricate a hit;
- never alter evidence authority;
- remain compatible with an eventual `ABSTAIN` result when no evidence is found.

The representative formal-review regressions are:

- `청소년 문화의집 설치기준`;
- `청소년문화의집 설치기준`;
- `청소년수련관 설치기준`.

They must succeed without user-supplied expansion when relevant evidence exists.

## 6. Cross-cutting error contract

The integrated PR should prefer stable reason/status codes over leaking incidental Python exception names to end users.

Required distinguishable states:

- `SOURCE_MISMATCH`
- `DEPENDENCY_MISSING`
- Korean retrieval no-hit with deterministic attempted-term trace
- Track B structural/integrity validation failure
- `TRACK_B_INPUT_MISMATCH`
- `TRACK_B_RETRY_MISMATCH`
- finalizer generated-artifact collision
- review finalization success + browser/display failure

Existing security-sensitive path validation, immutable artifact semantics, and stale retrieval index checks remain authoritative.

## 7. Testing strategy

TDD is mandatory for each subsystem.

1. Provenance RED tests before bootstrap changes.
2. Korean lexical characterization RED tests before retrieval changes.
3. Run-local Track B collision/retry RED tests before finalizer ownership changes.
4. Review-item/PDF focus RED test before `review.js` changes.
5. `review-question submit-track-b --open` subprocess RED test before CLI integration.
6. Focused suites after each subsystem.
7. Combined formal-review E2E after #100 and #98 are both implemented.
8. Full pytest, Ruff, mypy, compileall, documentation integrity.
9. Windows Python 3.11 and 3.13 smoke/acceptance.
10. Real browser acceptance at 1366×768, 200% zoom, and print.

## 8. Authority and compatibility invariants

The implementation is unacceptable if it changes any of these merely to make the tests pass:

- citation ID derivation;
- page number or bbox authority;
- evidence/source hashes;
- evidence snapshot hash;
- final packet authority semantics;
- Track A/B validation strictness;
- offline/network guard policy;
- protected review loopback/token security rules;
- existing English/numeric retrieval behavior.

## 9. Delivery and review gates

The PR remains Draft until all four issue-level acceptance sets pass together.

Recommended commit gates:

1. `fix: add CLI runtime provenance diagnostics`
2. `fix: retrieve bounded Korean compound terms`
3. `fix: make Track B run-local submission idempotent`
4. `fix: synchronize review items with PDF evidence`
5. `fix: return protected review handoff from review-question`
6. `test: cover issues 98 through 101 integration`
7. `docs: record issues 98 through 101 acceptance`

Do not close #98–#101 until the exact final HEAD used for acceptance is recorded and the combined regression suite passes.

## 10. Acceptance

- Development checkout execution identifies Python, package source, repository HEAD, and dependency state.
- A stale package source is blocked before business logic.
- Missing dependencies do not prevent `doctor` diagnostics.
- `주차구획선`, `소방차 전용구역`/compact variant, and `피난안전구역` retrieve the correct authoritative evidence when present.
- Existing English/numeric retrieval remains unchanged.
- Run-local Track B submission succeeds without rewriting the validated same-path input.
- Byte-identical retry succeeds; differing retry fails closed before finalizer execution.
- Partial finalizer recovery preserves validated Track B input.
- `review-question submit-track-b --open` returns a bounded protected result handoff or an explicit display-failure state plus `review_html`.
- Selecting a review item focuses its first citation page and bbox; multiple citations and keyboard navigation remain coherent.
- The three Korean formal-review questions work without user expansion when evidence exists.
- Citation/evidence/source/snapshot/packet authority remains unchanged.
- Focused tests, full pytest, Ruff, mypy, compileall, and documentation integrity pass.
- Windows Python 3.11/3.13 acceptance passes.
- Browser acceptance passes at 1366×768, 200% zoom, and print.
