# Issues #98–#101 Integrated Fix Design

Issues: #98, #99, #100, #101  
Related: #92, #95  
PR: #102  
Original PR base: `820fff52c568ec860cc2d92459e4502fccfc14e3`  
Target implementation baseline: current `main` observed at `cf9a7f6c3868eab52c918f7de86bb032dc9ebf1b` on 2026-08-14  
Date: 2026-08-14

## 1. Decision

Keep #98–#101 in one integration PR, but do not execute the original implementation plan unchanged.

PR #102 was planned against an older `main`. Current `main` is materially ahead and already changed `review.js`, review workspace tests, browser behavior, and protected-review acceptance. The first implementation gate is therefore to synchronize the PR branch with current `main` and re-characterize all four failures before editing production code.

The implementation order is:

```text
Phase 0  Sync to current main + re-characterize failures
   |
   +--> Phase 1  Runtime provenance (#99)
   |
   +--> Phase 2  Track B ownership/retry (#101)
   |
   +--> Phase 3  Korean deterministic retrieval (#100)
   |
   +--> Phase 4  Formal-review integration (#98)
   |
   +--> Phase 5  Combined E2E + Windows/browser acceptance
```

#99 remains first because no later acceptance result is trustworthy if the executed CLI can silently come from another checkout. #101 is next because its failure contract is currently explicit and isolated. #100 follows only after the exact FTS failure mode is characterized. #98 is integrated last because it consumes the existing #92 protected-server lifecycle and the retrieval behavior from #100.

## 2. Problem statement

Four P1 issues were discovered during real `$ERS_REVIEW` operation.

- #99: the CLI can execute a stale installed checkout instead of the active development checkout.
- #101: a valid run-local `track-b-output.json` is treated as a finalizer-generated collision.
- #100: Korean compound terms and exact phrases can exist in evidence records but miss deterministic FTS retrieval.
- #98: the formal-review path does not consistently return/open the protected result view, and item-to-evidence focus behavior must be coherent across mouse, keyboard, and multiple citations.

These problems share a trust boundary: the user must be able to verify that the intended source, query, Track B artifact, review item, and citation produced the displayed result.

## 3. Current-main observations that change the previous design

### 3.1 PR #102 is stale relative to main

The PR branch contains only the design and implementation-plan documents but was created from `main` at `820fff52...`. Current `main` has advanced substantially. Implementation must not begin until the branch is synchronized and RED tests are rerun on the synchronized code.

### 3.2 #98 review-item behavior is partially implemented on current main

Current `review.js` already handles review-item click by calling both `selectReviewItem(...)` and `focusEvidence(...)`.

At the same time, `focusEvidence(itemId, evidenceId)` can call `selectReviewItem(itemId, evidenceId)` internally.

Therefore the previous proposal—calling `focusEvidence()` from inside `selectReviewItem()`—is no longer safe. It would create bidirectional coupling and can lead to recursive or duplicated state transitions.

The revised design introduces one orchestration boundary instead:

```text
activateReviewItem(itemId, requestedEvidenceId?)
    |
    +--> selectReviewItem(...)   # rail/detail state only
    |
    +--> resolve citation
    |
    +--> focusEvidence(...)      # PDF page/bbox state only
```

`selectReviewItem()` and `focusEvidence()` must not call each other after the refactor.

### 3.3 #99 remains unresolved

`src/evidence_review/cli.py` still imports runtime modules eagerly. A missing heavy dependency can therefore prevent diagnostics from running, and a stale package source can enter business logic before provenance is checked.

### 3.4 #101 remains unresolved

`finalize_review_run()` still classifies `track-b-output.json` together with generated finalizer artifacts and fails when that run-local file already exists.

### 3.5 #100 remains unresolved, but implementation mechanism is not yet proven

Current Korean query helpers provide grouped entity/numeric/concept variants. The FTS layer does not yet have a proven general solution for the reported compound/exact-phrase miss.

The fix must be selected only after characterization distinguishes among:

1. SQLite FTS5 `unicode61` token behavior;
2. embedded whitespace, line-break, or zero-width format characters;
3. mismatch between authoritative normalized evidence and FTS searchable representation;
4. missing bounded Korean lexical variants.

Do not introduce an FTS schema or shadow representation until tests prove it is required.

## 4. Goals

1. Make runtime provenance observable and fail closed for development-checkout source mismatch.
2. Allow diagnostics to execute even when heavy runtime dependencies are missing.
3. Treat validated Track B as an input artifact with deterministic same-path and retry behavior.
4. Retrieve bounded Korean compound/spacing variants without weakening evidence authority.
5. Make `review-question submit-track-b --open` return a bounded protected review handoff using #92 infrastructure.
6. Make review-item, citation, keyboard, and PDF page/bbox state transition through one coherent UI orchestration path.
7. Preserve original query origin and provide deterministic zero-hit guidance without fabricating evidence.
8. Finish with exact-HEAD Windows Python 3.11/3.13 validation and real-browser acceptance.

## 5. Non-goals

- No LLM/API query rewriting.
- No external Korean morphology service or heavyweight NLP dependency.
- No redesign of #92 protected loopback server lifecycle.
- No citation, page, bbox, evidence text, evidence hash, source hash, snapshot hash, or packet-authority rewriting for search convenience.
- No weakening of Track A/Track B validation.
- No unrelated parser, rules, release, or broad UI refactor.
- No automatic overwrite of immutable run artifacts.
- No new UI redesign beyond the interaction correction required for #98.

## 6. Phase 0 — synchronize and characterize before implementation

### 6.1 Branch synchronization gate

Before production edits:

1. synchronize `agent/issues-98-101-integrated-fix` with current `main`;
2. record the exact synchronized HEAD;
3. verify tracked worktree state is clean before characterization;
4. rerun relevant current-main focused tests.

If merge/rebase conflicts touch review workspace files, preserve current-main behavior first and reapply only issue-specific changes after characterization.

### 6.2 RED characterization matrix

Add or refresh tests proving the failures on the synchronized baseline.

| Issue | Required characterization |
|---|---|
| #99 | stale checkout source is detected before business logic; missing runtime dependency still permits diagnostics |
| #101 | valid run-local Track B fails under the current finalizer ownership contract |
| #100 | authoritative record exists but representative Korean query misses; inspect exact indexed representation/token behavior |
| #98 | `submit-track-b --open` is absent/incomplete; item/citation/keyboard behavior is tested against current main rather than assumed |

Production code must not be changed until each still-open issue has a failing test or a documented finding that current main already fixed that subproblem.

## 7. Phase 1 — runtime provenance and dependency-safe bootstrap (#99)

### 7.1 Bootstrap boundary

`src/evidence_review/cli.py` becomes a stdlib-only bootstrap for diagnostic/preflight work.

Allowed bootstrap dependencies include standard-library modules such as:

- `argparse`;
- `dataclasses`;
- `importlib.metadata`;
- `importlib.util`;
- `pathlib`;
- `shutil`;
- `subprocess`;
- `sys`.

Do not import `ansim_review.cli`, parser modules, PDF libraries, or other heavy business modules until preflight passes.

### 7.2 Diagnostic model

Create `src/evidence_review/diagnostics.py` with an immutable diagnostic result containing:

- Python executable;
- resolved console-script path when available;
- distribution version;
- current working directory;
- detected or explicitly supplied repository root;
- repository HEAD when available;
- actual `ansim_review` package source path discovered without heavy imports;
- package/checkout match state;
- required dependency availability/version;
- stable status.

Stable statuses:

```text
OK
SOURCE_MISMATCH
DEPENDENCY_MISSING
NOT_A_CHECKOUT
```

### 7.3 Development-checkout policy

When running inside or explicitly targeting this repository checkout:

- actual package source must resolve to `<repository>/src/ansim_review`;
- if it resolves to another checkout, fail before business logic with `SOURCE_MISMATCH`;
- output must include the requested checkout, actual package source, Python executable, and command path.

A normal installed wheel executed outside a development checkout is not rejected merely because Git metadata is unavailable.

### 7.4 Missing dependency policy

`doctor` must remain runnable when `pypdfium2`, `pypdf`, Pillow, or another declared runtime dependency is missing.

Normal business commands fail with stable `DEPENDENCY_MISSING` diagnostics rather than an eager-import traceback.

### 7.5 CLI surface

Support a dependency-safe diagnostic command such as:

```text
python -m evidence_review doctor --repository-root <repo>
```

and a dependency-safe version surface.

Development and acceptance documentation should prefer interpreter-pinned commands (`python -m evidence_review ...`) after running `doctor`, rather than relying on a bare PATH console script.

## 8. Phase 2 — Track B artifact ownership and retry (#101)

### 8.1 Artifact ownership

Validated run inputs:

```text
track-a-output.json
track-b-output.json
```

Finalizer-generated artifacts:

```text
run-manifest.json
final-review-packet.json
review.html
```

Track B must no longer be treated as a finalizer-generated collision merely because the validated input already exists at the canonical run-local path.

### 8.2 Submission contract

#### Run-local Track B

If the submitted source resolves to `<run>/track-b-output.json`:

1. validate it against the immutable validated Track A;
2. do not rewrite it;
3. continue finalization.

#### External Track B

If Track B is outside the run directory:

1. validate it;
2. publish to run-local `track-b-output.json` with create-or-identical semantics;
3. continue finalization.

### 8.3 Retry identity

The transition into `FINALIZING` must record the validated Track B identity/hash used for the attempt.

- identical retry may resume;
- differing retry fails before finalizer execution;
- a differing pre-existing run-local Track B fails as an input mismatch rather than a raw `FileExistsError`.

Required stable distinctions include:

```text
TRACK_B_INPUT_MISMATCH
TRACK_B_RETRY_MISMATCH
TRACK_B_VALIDATION_FAILED
FINALIZER_ARTIFACT_COLLISION
```

Exact representation may use existing project error/status conventions, but the states must remain distinguishable.

### 8.4 Recovery contract

Interrupted finalization recovery may remove only restartable finalizer outputs:

```text
run-manifest.json
final-review-packet.json
review.html
```

Validated Track A and Track B inputs are preserved.

## 9. Phase 3 — bounded Korean deterministic retrieval (#100)

### 9.1 Characterization-first rule

Before choosing a production mechanism, the regression fixture must prove:

- the authoritative record exists in `retrieval_records`;
- its exact authoritative text and Unicode representation;
- what is stored in/searchable through `evidence_fts`;
- how FTS tokenization behaves for the representative string.

`fts5vocab` may be used in tests or diagnostics for characterization, but production retrieval must not depend on it.

### 9.2 Permitted normalization

Search-only representation may perform bounded evidence-insensitive normalization:

- NFC normalization;
- repeated whitespace collapse;
- explicit known zero-width format-character removal;
- bounded Hangul spacing compaction;
- existing safe suffix/particle handling.

It must not mutate authoritative evidence fields or citation lineage.

### 9.3 Retrieval order

Preserve high-precision channels first:

```text
fts_phrase
-> fts_token_and
-> bounded Korean lexical fallback
-> existing grouped entity/numeric/concept channels
-> fusion
```

The fallback must be traceable by origin and derived term.

### 9.4 Mechanism selection

Use the smallest mechanism proven sufficient by characterization.

1. If query-side bounded variants solve the miss, do not change the index schema.
2. If hidden format/spacing normalization in the FTS representation solves it, change only the search representation.
3. If FTS tokenization prevents the required match, add a derived searchable shadow representation while leaving authoritative retrieval records unchanged.
4. Add a schema migration only if the existing FTS structure cannot support the required representation.

### 9.5 Required regressions

Representative terms include:

```text
주차구획선
소방차 전용구역
소방차전용구역
피난안전구역
청소년 문화의집 설치기준
청소년문화의집 설치기준
청소년수련관 설치기준
```

Existing English and numeric retrieval must remain compatible.

## 10. Phase 4 — formal-review integration (#98)

### 10.1 Protected handoff

Add `--open` to:

```text
review-question submit-track-b
```

Reuse the existing #92 `open_review_run()` / detached protected loopback lifecycle. Do not create another server implementation.

After successful finalization, stdout always includes at least:

- format/version/stage;
- final status;
- `run_id`;
- `review_html` path.

When `--open` is requested, also include a display outcome and protected URL when available.

Browser dispatch failure after packet/HTML creation is a display failure, not a finalization failure. The successful review artifacts remain visible in the command result.

### 10.2 Review-item/evidence orchestration

Refactor UI responsibilities into three non-recursive layers.

#### `selectReviewItem(...)`

Owns only:

- selected rail item;
- selected detail panel;
- ARIA selected/pressed state;
- detail-tab state.

It does not move the PDF viewer.

#### `focusEvidence(...)`

Owns only:

- active evidence page;
- bbox overlay focus;
- page scrolling/focus;
- related viewer state.

It does not select review items.

#### `activateReviewItem(...)`

Owns orchestration:

1. select the review item;
2. resolve an explicitly requested citation or the first valid citation;
3. activate evidence context as needed;
4. call `focusEvidence(...)` once;
5. leave PDF state unchanged if no valid citation exists.

### 10.3 Unified event routes

Mouse and keyboard routes must use the same orchestration behavior.

Required routes:

- review-item click;
- review-item keyboard activation;
- citation click;
- citation keyboard activation;
- evidence-link click.

For a review item with multiple citations:

- item activation focuses the first valid citation;
- direct activation of another citation focuses that citation;
- selected review item remains coherent.

### 10.4 Zero-hit guidance

If no authoritative evidence is returned but bounded deterministic variants were attempted, the formal-review handoff may expose:

- original query;
- normalized/derived attempted terms;
- origin of each term.

This is guidance only. It must not fabricate a hit or suppress a legitimate `ABSTAIN` result.

## 11. Error contract

Prefer stable reason/status codes over incidental Python exception names in user-facing surfaces.

Required distinguishable states:

- `SOURCE_MISMATCH`;
- `DEPENDENCY_MISSING`;
- deterministic Korean no-hit with attempted-term trace;
- Track B structural/integrity validation failure;
- `TRACK_B_INPUT_MISMATCH`;
- `TRACK_B_RETRY_MISMATCH`;
- generated finalizer artifact collision;
- review finalization success plus browser/display failure.

Existing security-sensitive path checks, immutable artifact semantics, stale-index checks, offline/network policy, and #92 process-identity/token rules remain authoritative.

## 12. TDD strategy

TDD is mandatory for production behavior changes.

1. Sync/re-characterize current main.
2. #99 provenance RED tests, then bootstrap implementation.
3. #101 run-local Track B and retry RED tests, then ownership/recovery implementation.
4. #100 exact FTS characterization RED tests, then smallest sufficient Korean retrieval fix.
5. #98 `submit-track-b --open` RED test, then protected handoff integration.
6. #98 current-main UI behavior test, then non-recursive orchestration refactor only where required.
7. Multi-citation and keyboard regressions.
8. Formal-review Korean E2E using #100 behavior.
9. Full repository gates.
10. Windows and real-browser acceptance at exact final HEAD.

## 13. Combined formal-review E2E

The final integrated path must exercise:

```text
doctor
  -> review-question prepare
  -> Track A validation
  -> run-local Track B validation
  -> submit-track-b --open
  -> protected review page
  -> review-item/citation activation
  -> PDF page + bbox focus
```

Run representative Korean questions without user-supplied expansion when relevant evidence exists.

The E2E must prove the visible result remains tied to the same authoritative citation/source/snapshot lineage.

## 14. Authority and compatibility invariants

The implementation is unacceptable if it changes any of these merely to make tests pass:

- citation ID derivation;
- page number or bbox authority;
- evidence/source hashes;
- evidence snapshot hash;
- final packet authority semantics;
- Track A/Track B validation strictness;
- offline/network guard policy;
- protected review loopback/token/process-identity security;
- existing English/numeric retrieval behavior.

## 15. Acceptance gates

All issue-level gates must pass at one exact final HEAD.

### Automated

- focused regression suites PASS;
- full pytest PASS;
- Ruff PASS;
- mypy PASS;
- compileall PASS;
- documentation integrity PASS with zero errors.

### Windows

Run with Python 3.11 and 3.13:

- `doctor` current checkout;
- intentional stale source mismatch;
- missing-dependency diagnostic scenario;
- run-local Track B submission;
- byte-identical Track B retry;
- differing Track B retry;
- Korean retrieval regressions;
- formal-review protected handoff.

### Browser

Real browser acceptance must include:

- 1366×768;
- 200% zoom;
- keyboard item/citation activation;
- multiple citations;
- PDF page and bbox focus;
- print.

## 16. Delivery gates

PR #102 remains Draft until:

1. the branch is synchronized with current `main`;
2. all still-open failures are characterized on the synchronized baseline;
3. implementation is complete;
4. all acceptance gates pass at one exact HEAD;
5. the acceptance record contains the exact HEAD and command results.

Recommended implementation commit sequence after the synchronized RED baseline:

```text
1. test: recharacterize issues 98 through 101 on current main
2. fix: add dependency-safe runtime provenance diagnostics
3. fix: treat Track B as a validated run input
4. fix: retrieve bounded Korean compound terms
5. fix: return protected formal-review handoff
6. fix: unify review selection and evidence focus
7. test: cover issues 98 through 101 end to end
8. docs: record issues 98 through 101 acceptance
```

Do not close #98–#101 and do not mark PR #102 Ready for review until the combined exact-HEAD acceptance passes.
