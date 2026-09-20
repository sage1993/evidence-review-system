# Evidence Review System Agent Instructions

## 0. Architecture status and rule of execution

The persistent review-work architecture is merged and executable on current `main`. The mutable work domain is **ReviewMatter**, while the existing Formal Review core remains the authority for immutable review packets and packet-bound Human Decisions. Do not introduce a second persistent domain called `ReviewCase`: `case_id` and `CaseManifest` already identify drawing/case artifacts and are separate semantics.

Always document and execute the behavior that exists at the exact checked-out HEAD. The current runtime includes Evidence Navigation, ReviewMatter mutation/search/selection, Workbench serving, Formalization, and the direct `review-question` Formal Review path. Future commands or modules that are not yet merged must still be treated as target-only and must never be documented as current or reported as PASS.

The repository-level acceptance authority is local exact-HEAD verification. GitHub Actions is not used by policy: `GITHUB_ACTIONS = NOT_USED_BY_POLICY`. Never add or enable a workflow, require an Actions check, or report an unexecuted Actions workflow as a local PASS.

## 1. Authority model

The authority order is:

1. preserved source bytes and source hash;
2. finalized immutable evidence records and exact published `evidence.sqlite` identity;
3. ReviewMatter work state, source bindings, evidence selections, observations and drafts (**work authority only, never evidence/final authority**);
4. immutable FormalizationSnapshot for one exact Matter revision (**control input only**);
5. deterministic retrieval, Math Engine results and approved Rule Engine results;
6. independently produced Track A and Track B outputs after runtime validation;
7. immutable final Review Packet and protected/read-only projection;
8. separate append-only Human Decision bound to the exact packet hash.

A `QuestionPlan` or `ReviewScope` is control input. It is not evidence. Planner-inferred legal anchors are search hypotheses until retrieved evidence supports them.

`READY_FOR_HUMAN_REVIEW` means ready for inspection, not approved, legally compliant, or human-accepted. Machine packets keep `human_decision = null`.

## 2. The three user-work modes

The authority vocabulary is: **Evidence Navigation** for non-authoritative
exploration, **mutable ReviewMatter work state** in Workbench, and
**Formalization** as the only promotion into **Formal Review**. These terms do
not authorize a Navigation or Workbench action to create Planner, Track,
packet, conclusion, or Human Decision authority.

### 2.1 Evidence Navigation

Evidence Navigation is non-authoritative exploration. It may search finalized evidence, open exact citations, inspect pages/regions, compare sources, and allow the user to select evidence for a Matter.

Navigation must not:

- create a compliance/eligibility/legality conclusion;
- emit `READY_FOR_HUMAN_REVIEW`, `PARTIALLY_RESOLVED`, `ABSTAIN`, or Human Decision states;
- create Track A/Track B authority merely because a search was performed;
- promote a stale result without revalidating the current Matter/evidence binding.

A navigation result promoted into Matter work state must be revalidated against the exact finalized evidence snapshot and exact closed-file DB SHA.

### 2.2 ReviewMatter work

ReviewMatter is mutable reviewer work state. It may contain MatterIssues, source bindings, promoted evidence selections, draft observations, draft findings, notes, revision history, stale/invalidation state, and formal-run history.

ReviewMatter must never be stored in `evidence.sqlite` and must never mutate preserved source/evidence bytes. Matter work status is distinct from Formal `IssueStatus` and Finalizer status.

Drafts must be labeled and modeled as non-authoritative. Do not use Formal Review status vocabulary to make a draft appear approved.

### 2.3 Formalization

Formalization is the only allowed promotion boundary from mutable Matter work to Formal Review.

Formalization must:

- require an exact `matter_id` and expected Matter revision;
- fail if the Matter changes before snapshot creation;
- bind the exact finalized evidence logical snapshot and exact `evidence_db_sha256`;
- reject required stale/unresolved MatterIssues according to the formalization policy;
- include only explicitly promoted evidence/confirmed inputs, never arbitrary draft text or AI estimates;
- create an immutable FormalizationSnapshot;
- hand that snapshot into the existing validated Formal Review core.

Formal Review may not mutate Matter history. If a later Matter revision needs another result, create a new snapshot and a new RUN.

## 3. Naming and identity rules

- `matter_id` identifies persistent ReviewMatter work.
- `case_id` retains its existing drawing/case-artifact semantics.
- `run_id` identifies one immutable Formal Review execution.
- `attachment_id`, source/revision/page/bbox/hash identities remain exact and traceable.
- Never derive identity from basename uniqueness, newest-file guessing, recursive workspace search, or previous-run paths.

Do not rename existing drawing `case_id` semantics to Matter IDs. Do not make Review Packet v2 `case_id` silently mean `matter_id` without an explicit versioned contract migration.

## 4. Evidence and source invariants

Preserve original PDFs/images and raw parser outputs. Never overwrite them.

A published evidence database must remain a finalized, self-contained review authority:

```text
ingest
→ deterministic materialization
→ logical snapshot/retrieval verification
→ writer close
→ create-only publish
→ exact closed-file SHA-256
→ read-only review lifecycle
```

Review readers do not repair evidence. Reject unfinalized databases, stale retrieval indexes, logical snapshot mismatch, SQLite integrity failure, and `-wal`, `-shm`, or `-journal` sidecars.

ReviewMatter storage is separate from `evidence/evidence.sqlite`. Do not add Matter tables to the evidence DB.

Every source/evidence-dependent Matter record must retain enough identity to detect staleness. At minimum, formalizable evidence must trace to exact document/revision/page/evidence/bbox/source hash and the bound finalized evidence snapshot.

## 5. ReviewMatter persistence and concurrency

Matter mutations require optimistic-concurrency protection. An update based on stale expected revision must fail closed with no partial write.

Matter events and their projection must commit atomically. Never create separate authorities where a file event says one revision and the database projection says another. Retry/idempotency must not duplicate semantic mutations.

Formalization of Matter revision N is invalid if the current Matter revision is not N at the formalization boundary.

## 6. Invalidation and source revision changes

Source revision changes invalidate dependent work conservatively.

For the initial impact model:

- exact same source identity may retain dependent work;
- changed source hash invalidates every MatterIssue known to depend on that source;
- unknown/unmodelled impact is treated as affected, not retained;
- AI or geometric heuristics must not be used to assert "unaffected" unless a separately approved deterministic contract supports that claim.

A stale required MatterIssue cannot be silently formalized.

## 7. ReviewScope and Question Planner

`ReviewScope` is the canonical downstream control contract for formal review. It may be produced by:

- a validated external Question Planner output;
- explicit user-selected scope;
- validated MatterIssue scope assembled by runtime code.

Downstream retrieval/formalization should consume ReviewScope rather than spreading `if planner ... else ...` branches through the codebase.

Question Planner remains evidence-free and conclusion-free. It may structure issues/search requests, but it must not answer, decide compliance/eligibility/legality, assign confidence, invent evidence, or produce rule status.

Current `main` contains the canonical ReviewScope adapters and ReviewMatter Formalization path. Downstream formal review must consume the validated canonical scope rather than reinterpreting Matter drafts. The direct `review-question prepare-plan → prepare → Track A → Track B` path remains a supported Formal Review entrypoint when persistent Matter work is not being used. Do not bypass either path by hand-authoring internal artifacts.

## 8. Formal Review core - protected boundary

The following semantics are preserved unless a dedicated migration issue explicitly changes them with RED/GREEN acceptance:

- immutable prepared RUN inputs;
- deterministic retrieval/rule/math authority;
- Track A validation before Track B;
- independent Track B audit;
- finalizer ownership of `READY_FOR_HUMAN_REVIEW`, `PARTIALLY_RESOLVED`, and `ABSTAIN`;
- packet/source/citation hash validation;
- read-only final Review projection;
- separate append-only Human Decision.

`review_run.py`, finalizer contracts, evidence finalization, filesystem trust, Math Engine, Rule Engine, and Human Decision storage are not opportunistic refactoring targets during ReviewMatter work.

## 9. Drawing and visual review

Reference documents and case visuals are different source roles. Drawing PDFs meant for visual judgement do not become searchable reference evidence merely because they are PDFs.

Visual source identity must use canonical case/attachment/path/hash binding. Never resolve visual sources by global basename search.

Declared MIME, detected content format and selected decoder must match according to the approved visual-input contract.

External visual analysis may propose observations/candidates. It cannot create authoritative measurements. Measurements or values used by Math/Rule evaluation require the existing confirmed-input/calibration/confirmation boundary.

Reviewer identity must be explicit or server-bound. Never ship a maintainer-specific default reviewer identity.

## 10. Human Decision

Human Decision is not Matter state and is not machine finalizer state.

Decision records remain append-only and bound to the exact Review Packet SHA-256. A decision on an older RUN must never be automatically reused for a newer Matter revision or newer packet.

Allowed decisions remain:

- `SATISFIED`
- `NOT_SATISFIED`
- `CONDITIONAL`
- `ADDITIONAL_REVIEW_REQUIRED`

A new Formal Run requires a new decision if a human decision is required.

## 11. Protected HTTP and browser surfaces

Security-sensitive loopback servers must reuse the canonical shared transport primitives for Host/Origin cardinality, Content-Length, oversized-body response/drain/close, token handling, method rejection and security headers.

Do not add a third independent HTTP rejection/body-drain implementation for Workbench.

Surfaces must be authority-distinct:

- Workbench: mutable Matter work, no Human Decision endpoint;
- Formal Review: immutable packet-derived projection plus packet-bound Human Decision;
- Drawing annotation/calibration: append-only drawing confirmation/calibration actions.

Shared visual styles do not authorize shared mutation semantics.

## 12. CLI and user-facing workflow

Current executable commands must always match the checked-out HEAD and documentation.

### 12.1 Current executable workflow

At this exact HEAD, the current executable workflow is:

```powershell
evidence-review source-batch prepare `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json

evidence-review source-batch ingest `
  --root <workspace> `
  --manifest <workspace>\manifests\source-batch.json `
  --output <workspace>\evidence\evidence.sqlite

evidence-review workspace bind `
  --repository-root . `
  --workspace <workspace>

evidence-review workspace active `
  --repository-root .

evidence-review review-question prepare-plan `
  --workspace <workspace> `
  --question "<question>"

evidence-review review-question prepare `
  --workspace <workspace> `
  --question "<question>" `
  --question-plan-output <question-plan-output.json>

evidence-review review-question submit-track-a `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-a-output <track-a-output.json>

evidence-review review-question submit-track-b `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --track-b-output <track-b-output.json>

evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID>
```

Question Planner handoff remains mandatory before formal retrieval on this HEAD. `QuestionPlan` is evidence-free and conclusion-free. A missing or invalid plan is `PLANNER_FAILED`; a validated plan with no evidence is `RETRIEVAL_NO_EVIDENCE`. Do not bypass the planner by hand-authoring internal artifacts.

### 12.2 Current ReviewMatter workflow

The ReviewMatter interface is executable on current `main`. Use the canonical CLI rather than treating these operations as future interface notation:

```powershell
evidence-review review-matter create `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --title "<title>"

evidence-review review-matter status `
  --workspace <workspace> `
  --matter-id <MATTER-ID>

evidence-review review-matter add-issue `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --expected-revision <N> `
  --issue-id <ISSUE-ID> `
  --question "<question>"

evidence-review review-matter bind-evidence `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --expected-revision <N>

evidence-review review-matter search `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --query "<query>"

evidence-review review-matter select-evidence `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --expected-revision <N> `
  --evidence-id <EVIDENCE-ID> `
  --query "<query>"

evidence-review review-matter formalize `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --expected-revision <N>
```

The protected Workbench is also current:

```powershell
evidence-review review-matter workbench serve `
  --workspace <workspace> `
  --matter-id <MATTER-ID> `
  --reviewer-id <REVIEWER-ID>
```

Evidence Navigation and Workbench state remain non-authoritative. Only `formalize` freezes an exact Matter revision and prepares the immutable Formal Review run. The direct `review-question` / `review-run` interfaces remain supported Formal Review entrypoints and compatibility surfaces.

## 13. Commit / Push / PR policy

The public repository governance contract is:

```text
GITHUB_ACTIONS = NOT_USED_BY_POLICY
LOCAL_EXACT_SHA_VERIFICATION = AUTHORITATIVE_ACCEPTANCE
MAIN_INTEGRATION = PULL_REQUEST_ONLY
REQUIRED_STATUS_CHECKS = NONE
```

Pull-request creation is not acceptance. A PR may be merged only after the
local verifier has passed on the exact candidate and the PR head is rechecked
against that candidate. If remote or PR identity cannot be observed, record
`NOT_VERIFIED` and hold the merge.

All issue work uses an isolated issue-scoped branch (for example `feature/`, `fix/`, or `chore/`) or worktree from the exact latest `origin/main` SHA.

Required flow:

```text
origin/main
→ isolated branch/worktree
→ RED reproduction
→ minimal GREEN implementation
→ focused regression
→ commit
→ exact-HEAD full acceptance
→ push issue branch
→ remote SHA verification
→ Pull Request
→ explicit merge step
```

Prohibited:

- direct push to `main`;
- force push to `main`;
- deleting `main`;
- dirty-worktree acceptance;
- unrelated changes in an issue commit;
- changing source/tests/docs after full acceptance without rerunning the applicable gate;
- claiming a different SHA was tested than the PR head.

The core release/merge invariant is:

```text
TESTED_SHA == COMMITTED_SHA == PUSHED_SHA == PR_HEAD_SHA
```

If the candidate SHA changes, prior full acceptance is stale.

Never delete or overwrite unrelated user changes. Prefer an isolated worktree.

## 14. TDD and issue scope

Production behavior changes follow:

```text
RED
→ verify RED cause
→ minimal implementation
→ GREEN
→ adjacent regression
→ full gate
```

Do not combine independent failure classes in one MIG issue merely because they are nearby. Do not perform opportunistic refactoring. If required production scope expands beyond the issue plan, stop and record `SCOPE_EXPANSION_REQUIRED = YES` before adding files.

Every MIG issue must state:

- BASE_SHA and branch;
- exact files expected to change;
- RED test and expected failure;
- focused GREEN command/result;
- adjacent regression;
- full acceptance requirements;
- manual/browser/platform-specific gates;
- exact candidate/remote/PR SHA identities.

## 15. Mandatory verification

Before claiming merge readiness from a clean checkout at the exact candidate HEAD with Python 3.13, run the applicable gates:

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output tmp\documentation-integrity.json
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
```

Package changes additionally require an isolated Python 3.13 wheel/install/runtime smoke. UI/Viewer/Workbench changes require real browser QA on the supported viewport/lifecycle matrix. HTTP transport changes require the relevant Windows stress matrix. Evidence DB changes require finalized lifecycle, logical/retrieval identity, SQLite integrity, no sidecars, exact closed-file SHA and unchanged bound lifecycle hash.

The one-command local exact-SHA verifier runs these gates and the identity
checks together:

```powershell
py -3.13 scripts/repository_gate.py --issue <N> --json-report "$env:TEMP\ers-repository-gate-<N>.json"
```

It exits nonzero for a dirty worktree, changed candidate, failed or unrun
gate, unknown ancestry, remote/PR SHA mismatch, unavailable identity, or a
missing issue binding. The verifier reports
`GITHUB_ACTIONS = NOT_USED_BY_POLICY` only when no workflow file is observed;
an observed workflow is `POLICY_MISMATCH` and holds the gate. Historical
reports may retain `ACTIONS_NOT_RUN` and must not be rewritten.

`--json-report` must name an absolute path outside the repository so report
creation cannot make an already-computed clean verdict dirty. When the
candidate changes runtime/package or release content, pass an external
`--package-evidence` JSON record bound to the exact candidate SHA. That record
must contain PASS results for wheel build, isolated install, `pip check`, and
runtime smoke plus the wheel SHA-256; missing or stale evidence remains
`PACKAGE_ACCEPTANCE = NOT_RUN` or `NOT_VERIFIED` and holds the gate.

## 16. Release and packaging boundaries

Packaging must include every runtime-required ReviewMatter schema/module, Navigation/Workbench asset and instruction/template used by installed execution. Source-checkout success does not prove wheel/runtime parity.

Release validator must reuse canonical runtime authority checks rather than weaker duplicate semantics. User Matter data is not release package content.

Release state in CHANGELOG, SECURITY policy, tags and GitHub Release must agree before claiming a release version is published.

## 17. Prohibited completion claims

Do not report an issue, MIG, PR, release, or Epic as PASS merely because code was written or focused tests passed.

Any required but unexecuted gate is `NOT_RUN`. Any ambiguous authority, stale candidate SHA, unexpected dirty file, source identity mismatch, evidence hash mismatch, unresolved security boundary, or migration invariant failure results in `MERGE_READINESS = HOLD`.
