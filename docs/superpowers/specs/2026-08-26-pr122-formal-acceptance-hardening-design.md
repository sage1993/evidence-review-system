# PR #122 Formal Acceptance Hardening Design

## Goal

Resolve every product, contract, and acceptance-harness defect discovered during the formal acceptance of PR #122, while preserving the Issue #119 fail-closed authority boundaries and keeping external PowerShell/Codex transport failures separate from ERS product logic.

## Scope

This design covers five defect groups discovered during the exact-HEAD acceptance run for PR #122:

1. Related-reference routing selects irrelevant evidence by input order and can drop the actually relevant clause when the five-reference limit is reached.
2. External LLM instruction templates are weaker than their strict validators and allow structurally invalid outputs that the product later rejects.
3. Track A numeric-token grammar disagrees with ordinary attached-unit notation such as `2.4m`.
4. CLI/workflow preconditions and help/entry-point behavior are not surfaced early or consistently enough for an operator running the formal workflow.
5. The manual acceptance procedure is too shell-fragile and permits invalid PASS strings after an earlier failed check.

The changes remain in PR #122 and the PR stays Draft until a new exact-HEAD automated gate, formal pipeline run, artifact-level acceptance, and browser acceptance all pass.

## Non-goals

- Do not weaken Track A, Track B, finalizer, or human-decision authority boundaries.
- Do not promote related references to direct references.
- Do not convert `not_comparable` into PASS/FAIL merely because a relevant retrieved clause exists.
- Do not add product workarounds for PowerShell 5.1 native-pipe encoding behavior.
- Do not change the source evidence corpus or rely on reordered fixtures to make acceptance pass.
- Do not increase the related-reference limit as a substitute for relevance ranking.

## 1. Related-reference routing

### Problem

The current routing algorithm uses issue/search-request lineage as an eligibility gate, then iterates `track-a-bundle.json` evidence in input order and stops after five references. In the formal run, five unrelated `REF-002` business-plan excerpts matched the same broad search-request lineage before `REF-001` p.24 §2-5-8, so the five-reference limit was exhausted before the relevant clause was considered.

This proves two defects:

- eligibility alone is too broad to establish finding-level semantic relevance;
- applying the limit before deterministic relevance ranking makes the result order-dependent.

### Design

Keep issue/search-request lineage as the hard eligibility boundary. For every eligible evidence item, compute deterministic semantic relevance against the visual Finding before applying the limit.

Finding-side semantic text is built from:

- `finding.title`;
- `finding.subject_value`.

Evidence-side semantic text is built from:

- evidence excerpt `text`;
- the matched QuestionPlan search-request text.

Tokenization stays deterministic and language-agnostic within the existing lightweight tokenizer. The ranking key is deterministic and independent of input order:

1. positive finding ↔ evidence token overlap, descending;
2. finding ↔ matched-search-request overlap, descending;
3. evidence ID, ascending.

An evidence item with zero finding/evidence overlap is excluded from related references even if issue/search-request lineage is valid. The maximum remains five and is applied only after ranking.

The routing result must preserve the current authority boundary:

- `direct_claim_ids` remain derived only from deterministic rule-bound claim status;
- retrieved evidence is added only to `related_evidence_ids` / render-only related claims;
- the Finding remains `not_comparable` when no direct claim exists;
- machine claims, Track B input, finalizer status, and human-decision state are unchanged.

### Required regression coverage

The unit fixture must reproduce the formal failure shape:

- five `REF-002` distractor excerpts and one `REF-001` §2-5-8 excerpt;
- all share the same issue;
- distractors may share the same search-request lineage as the target;
- distractors appear before the target in the bundle.

Required assertions:

- §2-5-8 is retained;
- unrelated `REF-002` excerpts are excluded from the `공간 구성` Finding;
- reversing input evidence order yields the same related-reference result;
- direct reference remains empty and status remains `not_comparable`.

## 2. External LLM instruction contracts

### Visual Analysis

The validator already requires strict field types, but `VISUAL_ANALYSIS_INSTRUCTIONS.md` does not make the type contract explicit enough. The template must state:

- `raw_value` is `string | null`;
- `normalized_candidate` is `string | null`;
- `normalized_candidate` must never be object, array, number, or boolean;
- `POLYGON` coordinates must form a closed ring whose final point exactly equals the first point;
- every geometry must remain inside page bounds;
- `asset_path` is relative to the review workspace, not the visual-analysis directory.

The template continues to require semantic reviewable observations rather than OCR token dumps and continues to prohibit legal/compliance conclusions.

### Question Planner

The QuestionPlan instructions must enumerate the actual version-2 JSON contract and allowed enum values so an external planner can produce a valid artifact without out-of-band prompt repair.

Top-level fields are exactly:

- `format`;
- `version`;
- `original_question`;
- `facts`;
- `assumptions`;
- `issues`;
- `legal_anchors`;
- `search_requests`.

The template must explicitly distinguish `legal_anchors` from evidence citations and state the structures for facts, issues, legal anchors, and search requests.

### Track B

The Track B template must contain the actual strict output schema:

- top-level `run_id`, `claim_audits`, `overall_disposition` only;
- one audit per Track A claim exactly once;
- audit fields `claim_id`, `disposition`, `finding_codes`, `notes` only;
- allowed dispositions and finding codes;
- `ACCEPT` requires no finding codes;
- deterministic overall derivation: any REJECT -> REJECT; else any INCOMPLETE -> INCOMPLETE; else ACCEPT;
- Track B cannot rewrite Track A, set confidence, final status, abstention, or human decision.

If the Track B bundle does not contain enough immutable support material to perform the audit described by this template, the bundle contract must be corrected rather than encouraging the model to infer missing evidence.

## 3. Numeric grammar consistency

### Problem

During formal Track A validation, the claim text contained `2.4m` and the model correctly declared numeric token `2.4`, but the canonical Track A scanner did not recognize a number followed immediately by an ASCII letter, producing `NUMERIC_TOKEN_MISMATCH`.

### Design

Align Track A numeric extraction with the repository's existing explicit-unit semantics. Recognize a numeric literal followed by an allowed measurement/unit suffix such as:

- `m`, `m2`, `m²`;
- `km`, `mm`, `cm`;
- `%`, `㎡`;
- existing Korean unit suffixes already supported by the canonical grammar.

Do not treat arbitrary identifier suffixes as units. Examples such as `3F`, model numbers, candidate IDs, and arbitrary alphanumeric identifiers must not become numeric tokens solely because they contain digits.

Regression coverage must include at least:

- `2.4m` -> numeric token `2.4`;
- `1500mm` -> `1500`;
- `300cm` -> `300`;
- `3F` remains non-numeric for Track A token purposes unless the existing grammar explicitly defines it as a unit-bearing quantity.

## 4. Workflow and CLI hardening

### Preflight

A formal review that requires retrieval must fail before expensive external visual/Track work if the workspace does not contain the required `evidence/evidence.sqlite` corpus. The error must identify the missing prerequisite deterministically.

The selected insertion point must avoid breaking workflows that legitimately create or populate evidence after initial workspace creation; the preflight belongs at the earliest stage where retrieval is guaranteed to be required.

### CLI discoverability and module entry point

Verify and, if necessary, correct:

- `python -m evidence_review.cli` executes the canonical CLI rather than exiting silently;
- `review-question --help` exposes the actual visual-analysis submission stage when supported;
- stage-specific CLI status remains JSON on success and deterministic stderr/exit code on prerequisite failure.

### Track B support material

The formal Track B run reported every claim as `UNSUPPORTED_CLAIM` because the model stated that only citation IDs, not citation excerpt content, were available. Before changing the bundle, reproduce this against the actual `track-b-bundle.json` contract.

If immutable citation excerpts are in fact absent, add only the minimal support material required for independent audit and bind it to existing citation IDs/source hashes. If excerpts are already present and the result was prompt/model behavior, do not alter the product bundle unnecessarily.

## 5. Acceptance tooling

### Principle

Formal acceptance should not depend on fragile interactive PowerShell sequencing. Product validation remains in ERS; the acceptance helper only orchestrates existing CLI stages and verifies artifacts.

### Windows UTF-8 transport

Do not modify ERS product behavior to compensate for PowerShell 5.1 native-pipeline encoding. The acceptance helper must invoke external Codex using UTF-8 prompt files and byte-preserving stdin transport on Windows, equivalent to the proven `cmd.exe type <prompt> | codex.cmd ...` approach.

### Single-command checks

Move formal acceptance checks out of manually pasted `if/elseif` fragments into script functions or Python helpers that:

- stop on first failed condition;
- emit PASS markers only after the condition actually succeeds;
- verify exact target SHA/provenance;
- resolve `asset_path` relative to workspace;
- verify raster SHA before visual analysis;
- verify required evidence and page-image fixtures before finalization;
- distinguish `PASS`, `FAIL`, `NOT_RUN`, and environment/tooling blockers.

The harness must never print a PASS marker after a thrown/failed condition merely because subsequent lines were executed manually.

## 6. Verification strategy

Every production behavior change follows red-green TDD.

### Targeted gates

- related-reference ranking/filtering/order-independence tests;
- Visual Analysis template contract tests;
- QuestionPlan template/schema tests;
- Track B template/schema/overall derivation tests;
- numeric grammar attached-unit tests;
- CLI entry/help/preflight tests;
- Track B bundle-support reproduction test;
- acceptance-helper tests where practical.

### Full gates

On Python 3.13 exact HEAD:

```text
python -m pytest -q
python -m ruff check src tests
python -m mypy src/evidence_review
python -m compileall -q src
```

No gate is inferred from a prior SHA.

### Formal acceptance

Run the complete pipeline again in a new workspace bound to the new exact HEAD. Reuse only the immutable reference corpus fixture as explicitly recorded; do not reuse prior run, visual, Track A/B, final packet, or review HTML artifacts.

Required artifact-level acceptance:

- final status remains ABSTAIN when no deterministic direct comparison exists;
- `공간 구성` is `not_comparable`;
- direct references remain empty;
- related references include `REF-001` p.24 §2-5-8;
- unrelated `REF-002` business-plan evidence is excluded from that Finding;
- related evidence does not mutate machine claims;
- review HTML contains lazy raster URLs and no embedded case-raster base64.

Required browser acceptance:

- Reference pane shows §2-5-8 as related evidence for the corresponding Finding;
- direct-reference empty state remains visible when appropriate;
- Finding click focuses both Reference and Subject correctly;
- black/opaque overlay regression is absent;
- selected-only, zoom/pan/Fit, drawer click behavior, pagination/lazy loading, and responsive layouts remain regression-free.

## 7. Release/PR state

PR #122 remains Draft throughout implementation and verification. Issue #119 remains open. The PR may leave Draft only after exact-HEAD automated gates, formal artifact acceptance, and browser P0 acceptance are all observed PASS. Any newly discovered unrelated defect is classified separately and does not get silently converted into a PASS condition for this PR.
