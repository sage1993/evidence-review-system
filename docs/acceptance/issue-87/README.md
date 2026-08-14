# Issue #87 / #93 Acceptance Record

Status: **FAIL / archival HTML download control hidden; do not close #93**

This directory is historical acceptance evidence. It does not grant runtime authority and does not convert unexecuted checks into PASS.

## 1. Scope

Epic: #87 — formal review performance and non-developer Review Workspace

Execution order implemented for this tranche:

- #90 performance telemetry and hard-budget instrumentation
- #89 non-developer Review Workspace
- #91 simplified append-only human decisions
- #93 documentation and Windows 3.11/3.13 manual E2E acceptance

Related prerequisite work:

- #88 formal question pipeline
- #94 verified PDF page-image cache
- #92 detached protected-server idle timeout; implementation verified by focused tests and Windows 3.11/3.13 smoke, with the remaining full acceptance gates tracked below

## 2. Implementation baseline before this acceptance document

| Work | Commit | State |
|---|---|---|
| #88 formal question pipeline | `30431a40cb9b13732423ea4380dd54cc5883287c` | previously reported implemented |
| #94 page-image cache | `2d524e93d64737c43b26daac1cc66baa29af0041` | previously reported implemented |
| #90 telemetry | `fe892b5f89a3ea4c7cd32796ecb660f73f0d15eb` | implemented; acceptance pending |
| #90 telemetry typing | `bb5c0160f1ac1a4075d3f15ccee1b86eefd20ead` | implemented; acceptance pending |
| #89 Review Workspace | `d60e00480a1185ce33d1a97d383ee5095e94bf8a` | implemented; browser acceptance pending |
| #91 human decision simplification | `71228d0747b3e029a4d739367b9a972fbc7f2212` | implemented; Windows/browser acceptance pending |
| #90 retry/wait semantics | `cc4e53f61b05e174b7ba7ff7c8120c398f99d0ff` | implemented; timing acceptance pending |

**Acceptance execution HEAD:** `7ca9c159aa2a533ff27740cf45229e36bc70f5ec`

The final acceptance was executed in the Windows worktree with Python 3.11.9
and Python 3.13.14. Generated evidence is retained under `test-results/` and
is not part of the source commit.

## 3. Known pre-acceptance risk

Issue #92 was separately reopened, fixed, exercised on Windows, and closed.
Its focused explicit-stop regression passed and main's full pytest passed; this
#93 record treats the lifecycle gate as complete and keeps only the archival UI
visibility defect open.

## Issue #92 implementation evidence

The implementation change was developed from starting HEAD `67d27db9553c44342901c493bdbe6f29f0d4f6be` and verified/pushed as implementation commit `ff758ddc4935d857a69a96adcc64a018d1f7c56d`. This subsection records only executed evidence and does not close #92 or #93.

| Evidence | Python 3.11 | Python 3.13 |
|---|---:|---:|
| Version | 3.11.9 | 3.13.14 |
| Configured idle timeout | 2.0 s | 2.0 s |
| Protected URL handoff | 778.18 ms | 755.10 ms |
| Valid protected GET | HTTP 200 | HTTP 200 |
| Wrong-token request | HTTP 403 | HTTP 403 |
| Idle exit / `serve-status` | stopped | stopped |
| State cleanup | observed | observed |
| Old URL invalidation | connection failed | connection failed |
| Explicit `serve-stop` | stopped and cleaned | stopped and cleaned |

Focused Python 3.13 regression suite: **33 passed**. Full pytest: **1268 passed, 7 skipped** on both Python 3.11 (`175.03s`) and Python 3.13 (`175.09s`). Ruff: **PASS**. mypy: **PASS** (`190` source files). compileall: **PASS**. Documentation integrity: **PASS**, `errors=0`, `warnings=105`. GitHub Actions: **ACTIONS_NOT_RUN**. Browser viewport/zoom, three-run timing, exact final-HEAD clean-checkout attestation, and Issue #87/#93 overall acceptance remain separate gates.

## 4. GitHub Actions state

State for this implementation/acceptance session: **ACTIONS_NOT_RUN_BY_THIS_SESSION**.

- No new GitHub Actions workflow was added for #87/#93.
- The available GitHub connector returned no workflow run for the earlier #90 implementation commit when queried.
- Combined commit status could not be inspected through the connector because GitHub returned `403 Resource not accessible by integration`.
- Therefore this record does **not** claim Actions PASS, Actions FAIL, billing-blocked, or repository-wide workflow absence.

When the actual acceptance run is performed, record any independently observed GitHub Actions state exactly. Local/manual PASS must never be described as Actions PASS.

## 5. Clean-checkout preflight

Run in PowerShell from a clean Windows checkout.

```powershell
git status --short
git rev-parse HEAD
python --version
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
```

Record:

| Field | Result |
|---|---|
| Exact HEAD | `7ca9c159aa2a533ff27740cf45229e36bc70f5ec` |
| Worktree clean | PASS for tracked files; generated `test-results/` retained untracked |
| Windows product/version/build | NOT_RUN |
| Python 3.11 executable/version | `py -3.11`, 3.11.9 |
| Python 3.13 executable/version | `py -3.13`, 3.13.14 |

## 6. Automated validation matrix

Run separately on Python 3.11 and Python 3.13 where the environment supports it.

### Documentation integrity

```powershell
evidence-review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output .acceptance\issue-87\documentation-integrity.json
```

Acceptance: status PASS, errors = 0. Warnings must be recorded and reviewed; do not silently discard them.

### Full gates

```powershell
python -m pytest -v
python -m ruff check src tests
python -m mypy src
python -m compileall -q src scripts web_runtime tests
```

### Focused formal-review gates

```powershell
python -m pytest -v tests\integration\review_question
python -m pytest -v tests\integration\review_packet
python -m pytest -v tests\integration\review_run
python -m pytest -v tests\unit\review_packet
python -m pytest -v tests\unit\observability
```

Record:

| Gate | Python 3.11 | Python 3.13 |
|---|---|---|
| Documentation integrity | PASS, errors=0 warnings=105 | PASS, errors=0 warnings=105 |
| Full pytest | 1304 passed, 7 skipped; exit 0 | 1304 passed, 7 skipped; exit 0 |
| Ruff | PASS; exit 0 | PASS; exit 0 |
| mypy | PASS; 191 source files; exit 0 | PASS; 191 source files; exit 0 |
| compileall | PASS; exit 0 | PASS; exit 0 |
| review_question focused | PASS; included in focused 134 | PASS; included in focused 134 |
| review_packet focused | PASS; included in focused 134 | PASS; included in focused 134 |
| review_run focused | PASS; included in focused 134 | PASS; included in focused 134 |
| observability focused | PASS; included in focused 134 | PASS; included in focused 134 |

For every result record command, exit code, test count, skipped count, and output artifact/log path.

## 7. User-facing formal review E2E

The reviewer should start from a workspace already prepared by `$ERS_PDF` with `evidence.sqlite` and verified page-image cache.

### Required user behavior

1. User enters `$ERS_REVIEW <question>` once.
2. User is never asked to hand-write query JSON, review request, Track A output metadata, Track B metadata, packet hash, or timestamp.
3. Runtime creates formal question handoff.
4. Codex produces Track A from the run handoff.
5. Track A is submitted and validated **before** Track B begins.
6. Codex independently audits every Track A claim in Track B exactly once.
7. Track B is submitted and validated.
8. Packet and HTML are created.
9. Protected browser URL opens.
10. Reviewer sees the non-developer workspace, records a decision, and sees the `REVIEW_COMPLETED` projection after a valid append-only decision.
11. Machine packet remains unchanged and `human_decision` remains null.
12. Metrics and hashes are retained.

Record for each Python version:

| Check | 3.11 | 3.13 |
|---|---|---|
| One user question initiates formal review | PASS; same question plus supplied expansion | PASS; same question plus supplied expansion |
| No user-authored intermediate JSON | PASS | PASS |
| Track A early validation | PASS | PASS |
| Track B covers all validated claims exactly once | PASS; 2/2 claims audited | PASS; 2/2 claims audited |
| Packet generated | PASS | PASS |
| HTML generated | PASS | PASS |
| Protected URL/browser opens | PASS; protected browser run | PASS; protected browser run |
| Reviewer decision saved append-only | PASS | PASS |
| `REVIEW_COMPLETED` display projection | PASS | PASS |
| Machine packet unchanged | PASS | PASS |
| Metrics present | PASS | PASS |

## 8. Protected decision E2E

Start with a fixed reviewer ID:

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id reviewer-01
```

Verify:

- reviewer ID is shown/read as session context, not an ordinary editable form field;
- packet hash is not an ordinary form field;
- `reviewed_at` is not an ordinary form field;
- visible user inputs are decision and notes;
- POST request v2 has exactly `reviewer_id`, `packet_hash`, `decision`, `notes`;
- different reviewer ID is rejected when one is configured;
- stale/wrong packet hash is rejected;
- server-generated `reviewed_at` is ISO-8601 and offset-aware;
- success creates a new file under `human-decisions/`;
- a duplicate create-only target is not overwritten;
- packet and HTML bytes/hashes do not change after decision;
- status endpoint projects `REVIEW_COMPLETED` only when a valid decision record matches current packet hash.

Status: **PASS for protected decision path**. A fresh Python 3.13 protected
browser run saved an append-only decision and displayed `REVIEW_COMPLETED`.
The packet and HTML bytes remained unchanged. The fresh Python 3.11 archival
import path is recorded below.

## 9. Archival HTML decision E2E

Open the finalized `review.html` using `file:` without the local server.

Verify:

1. server POST is unavailable and the UI does not falsely report persistent save success;
2. reviewer can choose decision and enter notes;
3. if no reviewer identity is known, the page asks once before envelope creation;
4. **결정 JSON 다운로드** creates exactly five fields:
   - `reviewer_id`
   - `reviewed_at`
   - `packet_hash`
   - `decision`
   - `notes`
5. `reviewed_at` is a fresh offset-bearing ISO-8601 value;
6. invalid/incomplete input does not create a valid download;
7. import succeeds only through:

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

8. changed packet hash is rejected;
9. the decision record is append-only;
10. saving the HTML itself does not count as a recorded decision.

Status: **FAIL / BLOCKED**. The browser could not open `file:` directly in the
Playwright acceptance harness, so archival handler verification used a local
loopback static server. The handler produced a valid five-field envelope and
the official `import-decision` command returned `RECORDED`, but the actual
archival page's `결정 JSON 다운로드` button computed to `display:none` and was
not visible to a reviewer. This is a UI acceptance failure; #93 remains open.

## 10. Browser UX/UI matrix

Use actual browser rendering; static CSS tests are insufficient.

| Viewport | 100% | 200% | Fit/page workflow | Keyboard/focus | Print |
|---|---|---|---|---|---|
| 1366x768 | PASS | PASS | PASS; fit=1 | PASS | PASS |
| 1920x1080 | PASS | PASS | PASS; fit=1 | PASS | PASS |
| 3840x2160 | PASS | PASS | PASS; fit=1 | PASS | PASS |

The protected page was manually checked in a headed browser. Tab navigation
reached the decision textarea, save control, audit details, print control,
evidence controls, and PDF controls. The focused textarea had a 3 px blue
outline; Space selected a decision radio; selecting evidence moved the viewer
to page 32. Print output retained question/result/evidence/decision content
and excluded audit/hash details. The archival download control is the one
failed visual gate described in section 9.

Acceptance checks:

- order is result → evidence → conditional additional review → decision;
- Korean status and concise conclusion are readable first;
- single-claim navigator is absent;
- empty rule/calculation and additional-review sections are absent;
- internal IDs/hashes/confidence internals are collapsed under audit details;
- bbox/source traceability remains visible;
- desktop decision panel does not obscure required evidence;
- below 1100 px the layout stacks to one column;
- 200% zoom does not require avoidable horizontal scrolling for the stacked layout;
- focus indicator is visible and required controls are keyboard reachable;
- print excludes audit/developer clutter and preserves question, result, evidence, applicable additional-review content, and decision area.

## 11. Protected browser open-failure matrix

Exercise both success and failure:

| Scenario | Expected | Result |
|---|---|---|
| valid packet + HTML | protected server ready and browser dispatch succeeds | PASS |
| missing packet/HTML | fail closed before final review route | PASS; exit 2 |
| browser opener returns failure | command reports failure; no false OPENED state | PASS |
| server readiness exceeds 2 s | startup fails | PASS |
| stale state file | stale state removed/ignored safely | PASS |

## 12. Server lifecycle matrix

Run on Windows for both supported Python versions.

| Scenario | 3.11 | 3.13 |
|---|---|---|
| detached serve survives launching CLI process | NOT_RUN | NOT_RUN |
| `serve-status` reports correct run | NOT_RUN | NOT_RUN |
| idle server remains available | NOT_RUN | NOT_RUN |
| `serve-stop` stops only target run | NOT_RUN | NOT_RUN |
| stale state cleanup | NOT_RUN | NOT_RUN |
| unrelated/reused PID is never signaled | NOT_RUN | NOT_RUN |

Any failure here keeps #92/#93 acceptance open.

## 13. Performance timing — three simple questions

Use the same prepared workspace and equivalent simple question class. External Track latency must remain separated from deterministic runtime.

For each run retain `run-metrics-events/` and `run-metrics.json`.

| Python | Run | deterministic_total_ms | external_wait_total_ms | protected server + browser ms | retry_count | slowest deterministic stage |
|---|---:|---:|---:|---:|---:|---|
| 3.11 | 1 | 130 | 69273 | NOT_RUN | 0 | request construction |
| 3.11 | 2 | 50 | 74278 | NOT_RUN | 0 | request construction |
| 3.11 | 3 | 59 | 79232 | NOT_RUN | 0 | request construction |
| 3.13 | 1 | 80 | 84190 | NOT_RUN | 0 | request construction |
| 3.13 | 2 | 320 | 89174 | NOT_RUN | 0 | request construction |
| 3.13 | 3 | 174 | 94207 | NOT_RUN | 0 | request construction |

Calculate actual percentiles from recorded values; do not estimate them.

Example after copying the three deterministic totals into a list:

```powershell
python -c "import statistics; v=[int(x) for x in 'VALUE1 VALUE2 VALUE3'.split()]; print('p50=',statistics.median(v)); print('sorted=',sorted(v))"
```

For three samples, also record the sorted raw values and the exact percentile convention used for p95. Do not conceal the small sample size.

Acceptance targets:

- deterministic non-model total hard gate: `<= 5000 ms` for each acceptance run;
- protected server start + browser dispatch hard gate: `<= 2000 ms`;
- manual JSON retry: 0;
- Track A failure discovered only after Track B: 0;
- repeated page-image re-render: 0;
- metrics missing: 0;
- whole formal review target including external Track work: 45–90 seconds target, reported separately from hard deterministic gates.

Current timing status: **PASS for six formal runs**. The same actual question
(`피난안전구역 설치 위치는?`, with the same supplied expansion) was used three
times per interpreter. External wait was measured from run metrics and kept
separate from deterministic work. Using nearest-rank p95 for n=3:

| Python | external p50 | external p95 | deterministic p50 | deterministic p95 |
|---|---:|---:|---:|---:|
| 3.11 | 74278 ms | 79232 ms | 59 ms | 130 ms |
| 3.13 | 89174 ms | 94207 ms | 174 ms | 320 ms |

All six retry counts were 0 and all deterministic totals were below 5000 ms.
The protected server/browser dispatch timing column was not separately
instrumented in these six metric rows; it is therefore recorded as NOT_RUN.

## 14. Artifact hash record

Use PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 <workspace>\runs\<RUN-ID>\review-request.json
Get-FileHash -Algorithm SHA256 <workspace>\runs\<RUN-ID>\final-review-packet.json
Get-FileHash -Algorithm SHA256 <workspace>\runs\<RUN-ID>\review.html
Get-FileHash -Algorithm SHA256 <workspace>\runs\<RUN-ID>\run-metrics.json
Get-ChildItem <workspace>\runs\<RUN-ID>\human-decisions\*.json | Get-FileHash -Algorithm SHA256
```

Record:

| Artifact | SHA-256 |
|---|---|
| review-request.json | `2cbe62a85d95e0c0fe1be887ccedab7b83c26a9f88e64f183c942f8c9e3c4c2c` |
| final-review-packet.json | `f39afd65e64f9bbc0b64ba7fb46d36c37103c4540fe1a3b865a59ddd6bc300b6` |
| review.html | `bf4c1c4d3d528ea9f197d27cc6f1e3e778309ed6b9dcaa4a66edb2df7184e3db` |
| run-metrics.json | see section 16.5 for all six final metrics hashes |
| human decision record | protected `20cb2fe5b1f0aa9e9f28648ca4dd2d87075df8117b2b10ee5ba5f06080b45291`; imported `ee95fd772152ae2c3cc1ee4872b399840f81594d654f077a4b7ae509958f025c` |

Additionally verify that reading/writing metrics did not change the Run ID or final packet bytes/hash, and that saving a human decision did not change packet/HTML hashes.

## 15. Final acceptance decision

Current decision: **FAIL / DO NOT CLOSE #93**.

Blocker: archival HTML's visible download control is hidden by computed
`display:none`; fix and rerun the archival browser gate before closing #93.

To change this to PASS, attach the exact command outputs and hashes for all required Windows/Python/browser/timing gates. If any required gate fails or remains unexecuted, keep the issue open and record the exact blocker rather than weakening the acceptance criterion.

### Issue #95 — Korean retrieval / formal-review invariants

Scoped result: **PASS — manual Windows verification**

This subsection records Issue #95 only. It does not close or satisfy the remaining
browser, protected-server, lifecycle, timing, or full Issue #87/#93 acceptance gates.

Verification code HEAD:

`4996d941506ac03900148a9563641fb9bfb78c43`

Repository state before verification:

- local HEAD matched `origin/main`
- tracked working tree was clean
- GitHub Actions were not used as evidence for this result

#### Issue #95 focused matrix

Windows / Python 3.11:

- 86 passed in 14.63 s
- exit code 0

Covered retrieval, review-question, Track B validation, abstention/finalization,
review-packet builder, and HTML renderer regression suites.

#### Repository-wide gates

| Gate | Python 3.11 | Python 3.13 |
|---|---|---|
| Full pytest | 1259 passed, 1 skipped in 168.85 s; exit 0 | 1259 passed, 1 skipped in 168.64 s; exit 0 |
| Ruff | PASS; exit 0 | PASS; exit 0 |
| mypy | PASS, 189 source files; exit 0 | PASS, 189 source files; exit 0 |
| compileall | PASS; exit 0 | PASS; exit 0 |

The v1 review-packet compatibility regression was also verified on both supported
Python versions with 67 passed and exit code 0 before repository-wide validation.

#### Documentation integrity

Executed with the Python 3.11 acceptance environment:

- status: PASS
- documents: 37
- current: 26
- historical: 9
- generated: 2
- errors: 0
- warnings: 102
- exit code: 0
- report: `.acceptance/issue-95/documentation-integrity.json`

Warnings were retained as warnings and were not reclassified as errors.

#### Scope boundaries

Issue #95 does **not** claim completion of:

- protected-browser manual QA and browser UX acceptance;
- Windows protected-server lifecycle acceptance;
- three-run performance timing or p50/p95;
- Issue #87 or Issue #93 overall acceptance;
- GitHub Actions PASS.

Those remaining acceptance items continue under their respective issues, including
#89, #90, #92, and #93.

## 16. Issue #93 execution record - merged HEAD

This record documents the Issue #93 work performed after PR #103 was merged.
It is an evidence record, not a completion claim for the full #93 acceptance
gate.

Exact repository HEAD:

`dbad355c11d8413f01fd250d5ceaf06797f1cf23`

The verification was run in the Windows worktree on both supported interpreters:

| Interpreter | Executable | Version |
|---|---|---|
| Python 3.11 | `C:\Users\KSH\AppData\Local\Programs\Python\Python311\python.exe` | 3.11.9 |
| Python 3.13 | `C:\Program Files\Python313\python.exe` | 3.13.14 |

### 16.1 Documentation integrity

The authoritative validation used the source checkout explicitly, so the CLI
could not resolve a stale installed `ansim_review` package:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output <fresh-output>
```

Both Python 3.11 and Python 3.13 returned exit code 0:

- Documentation integrity: **PASS**
- documents: 37; current: 26; historical: 9; generated: 2
- errors: **0**
- warnings: **105**

An unpinned `evidence-review` invocation under Python 3.13 reproduced the
previous stale-install result of 31 errors and 105 warnings. That result is
recorded as an environment mismatch and is not acceptance evidence; the
source-pinned result above is authoritative.

### 16.2 Windows automated matrix

| Gate | Python 3.11 | Python 3.13 |
|---|---|---|
| Full pytest | 1304 passed, 7 skipped in 153.53 s; exit 0 | 1304 passed, 7 skipped in 150.04 s; exit 0 |
| Ruff | PASS; exit 0 | PASS; exit 0 |
| mypy | PASS; 191 source files; exit 0 | PASS; 191 source files; exit 0 |
| compileall | PASS; exit 0 | PASS; exit 0 |
| Focused review suites | 134 passed in 26.77 s; exit 0 | 134 passed in 22.54 s; exit 0 |
| Explicit-stop lifecycle suite | 7 passed in 11.77 s; exit 0 | 7 passed in 11.40 s; exit 0 |

The focused review suites covered `review_question`, `review_packet`,
`review_run`, `unit/review_packet`, and `unit/observability`.

### 16.3 Protected decision E2E

The protected loopback server was exercised on both interpreters. Each run
returned GET 200 and POST 201, appended exactly one decision record, produced
an offset-aware `reviewed_at`, and left the packet and HTML bytes unchanged.

| Interpreter | Packet SHA-256 | HTML SHA-256 | Decision record SHA-256 |
|---|---|---|---|
| Python 3.11 | `7da4c4555142f1e5ccd78c419b60ffaeb5e0675430966f84b40d87068fe4ed51` | `75c06e2b52b2d18c9a890972a67571ee49ba9add4a42eb692882ff9ff3792146` | `1137D2D2273108D57A330FF9E370B99377F3EED74003E9E38685F48276F422E3` |
| Python 3.13 | `7da4c4555142f1e5ccd78c419b60ffaeb5e0675430966f84b40d87068fe4ed51` | `75c06e2b52b2d18c9a890972a67571ee49ba9add4a42eb692882ff9ff3792146` | `179B91B897A24569EC0D3B117253F1E88CB666281AE09E61906401E6455DDAB0` |

### 16.4 Browser viewport and fit-to-page matrix

Actual headed-browser checks used 1366x768, 1920x1080, and 3840x2160 at
page-scale 1 and 2. All six cases had `horizontalOverflow=false` and the
evidence viewer fit-to-page value was `1`. The observed client and scroll
widths were equal in every case:

| Viewport | Page scale | Client/scroll width | Active figure right edge |
|---|---:|---:|---:|
| 1366x768 | 1 / 2 | 1351 / 1351 | 960 |
| 1920x1080 | 1 / 2 | 1905 / 1905 | 1428 |
| 3840x2160 | 1 / 2 | 3825 / 3825 | 2388 |

The separate PR #103 exact-HEAD 200% check also measured
`visualViewport.scale=2`, no horizontal overflow, and an active figure right
edge of 903 px. The fresh headed-browser run reached decision, print,
evidence, and PDF controls by keyboard; focus had a visible 3 px blue outline,
Space selected a decision radio, evidence navigation reached page 32, and the
print PDF retained result/evidence/decision content without audit/hash detail.
The archival download control remains the failed visual gate.

### 16.5 Timing samples

Three formal `$ERS_REVIEW` runs were completed per interpreter with the same
actual question (`피난안전구역 설치 위치는?`) and the same supplied expansion.
Track A and Track B were submitted in order and external wait was read from
each run's metrics, separately from deterministic work.

| Interpreter | External p50 | External p95 | Deterministic p50 | Deterministic p95 |
|---|---:|---:|---:|---:|
| Python 3.11 | 74278 ms | 79232 ms | 59 ms | 130 ms |
| Python 3.13 | 89174 ms | 94207 ms | 174 ms | 320 ms |

The p95 values use nearest-rank for three samples. All six runs had
`retry_count=0`; deterministic totals were below 5000 ms.

Timing metrics SHA-256:

| Run ID | SHA-256 |
|---|---|
| `RUN-2CBE62A85D95E0C0FE1B` py311-1 | `415803ad0ca7f1013b20500419a9e93695434b9b46cae85945b32d3ed78f2c9e` |
| `RUN-2CBE62A85D95E0C0FE1B` py311-2 | `4af2d2bb1d503097fc9d0f7d8ae48766730c35db167b78202ebddc2a3e4f88ce` |
| `RUN-2CBE62A85D95E0C0FE1B` py311-3 | `f35c5ea52a0fdaeb85dbde7bcda2278bf9bb4e59d62a5c5b7da1413386baf3a3` |
| `RUN-2CBE62A85D95E0C0FE1B` py313-1 | `af06affd30613cdf5e322732086e3f4188dad46249e3d27c01fccdbb1c91a96b` |
| `RUN-2CBE62A85D95E0C0FE1B` py313-2 | `35b10d4f5bb53de5395e03be9dca3206230e2b23bf7c32fb472e6d947cf0abbe` |
| `RUN-2CBE62A85D95E0C0FE1B` py313-3 | `3c2b018242e8d405e255a7d1b4c96b0b5d24dd8960298db28f820e9c83d78b38` |

### 16.6 Remaining Issue #93 gates

Formal `$ERS_REVIEW` Track A/B flow: **PASS** on three runs per interpreter;
Track A validated before Track B, two claims were audited exactly once, and
final packet/HTML plus metrics were produced on all six runs.
Protected decision browser flow: **PASS**; append-only decision and
`REVIEW_COMPLETED` projection were observed, with packet/HTML unchanged.
Archival handler/import: **PASS** for five-field envelope creation and the
official `import-decision` command (`RECORDED`), but the actual archival
download button is hidden by computed `display:none`: **FAIL / BLOCKED**.
Browser failure matrix: **PASS** for all five cases. Keyboard/focus/print QA:
**PASS** for the protected page; archival visibility remains the blocker.
Formal timing and full Python 3.11/3.13 validation: **PASS**; each interpreter
had 1304 passed and 7 skipped, documentation errors were 0. Actions:
**ACTIONS_NOT_RUN**.

Current Issue #93 decision: **FAIL / DO NOT CLOSE #93**. The archival UI
visibility defect must be fixed and the affected browser/import gate rerun.
