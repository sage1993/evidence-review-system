# ReviewMatter migration acceptance report

Issue: #190 (MIG-20)
Migration plan: `docs/plans/2026-09-08-ers-review-matter-architecture-migration.md`
Purpose: record exact-HEAD, real-environment acceptance evidence for the MIG-01–MIG-19 migration.

This report distinguishes executable evidence from gates that require a human or a
connected GitHub environment. `NOT_RUN` is not a pass. The machine packet remains
the authority for a Formal Review result and its `human_decision` remains `null`;
the human decision is an append-only, packet-hash-bound record.

## Candidate identity

| Field | Value |
| --- | --- |
| Required base | `fa6e8a0098eb06c8afeaa7b306cce25ef412ae2f` (MIG-19 merge) |
| Acceptance branch | `test/mig-20-review-matter-acceptance` |
| Exact candidate commit | `32aa582722dc0d806470104c2b77ed6cf94f14f2` (runtime/test candidate) |
| Python | `3.13` |
| Platform | Windows (`win32`) |
| GitHub Actions | `ACTIONS_NOT_RUN` |
| Overall status | `HOLD` until final-HEAD revalidation, Sol-high review, and merge are complete |

## Executable migration matrix

The focused test creates isolated workspaces and exercises the production service,
workflow, finalizer, protected decision server, source invalidation, and installed
wheel. The drawing scenario also generates a deterministic 17-page PDF fixture so
that page count and `CASE_DRAWING` lineage are asserted without treating generated
bytes as user evidence.

| Scenario | Evidence asserted | Result |
| --- | --- | --- |
| `navigation_only` | finalized evidence search; mutable Matter state; no Formal Run promotion | `PASS` |
| `planner_formal_review` | Question Plan handoff; Track A/B; final packet; claim-to-issue/evidence lineage | `PASS` |
| `explicit_scope_formal_review` | explicit user scope; immutable snapshot; matter revision and evidence DB hash in request inputs | `PASS` |
| `partial_multi_issue` | partial finalization; unresolved retrieval miss; resolved issue results retained | `PASS` |
| `drawing_confirmation` | 17-page `CASE_DRAWING`; source hash on every visual page; confirmation pause and same-run resume | `PASS` |
| `source_revision_invalidation` | direct and transitive stale propagation; independent issue remains ready; event persisted | `PASS` |
| `two_formal_runs` | two distinct snapshots/runs; revision order; exact final packet hashes | `PASS` |
| `packet_specific_human_decision` | protected decision binds one finalized packet hash; second run is untouched; machine packet stays null | `PASS` |
| `restart_recovery` | receipt-bound restart; no duplicate ingestion; idempotent state/events | `PASS` |
| `installed_wheel_runtime` | wheel build/install; ReviewMatter schema; Workbench assets; import from installed target | `PASS` |
| `protected_case_visual_cache_identity` | protected case-page delivery resolves the exact case-scoped cache identity | `PASS` |

Run the focused matrix from the exact checkout:

```powershell
py -3.13 -m pytest -v tests/integration/review_matter/test_end_to_end_matrix.py
```

Executed on the MIG-20 worktree with Python 3.13: `12 passed` in 20.46 seconds.

The text/reference-only lane is exercised by the planner and restart scenarios. In
addition to the generated fixture assertion, the prepared user workspace was run
through exact candidate case intake and rendering:

| Source | Result |
| --- | --- |
| `ATT-C6367EE43EE223059644.pdf` (`CASE_DRAWING`) | `PASS`, 17 PDF pages and 17 rendered visual pages |
| source byte size | `37,000,841` |
| source SHA-256 | `f6a1a4bc96ab0a33d100e3c4b93fc5b1fdee976380f8d2fc8041bf7afd151847` |
| first rendered page SHA-256 | `fa475f0a49d9f15d83b83586b6f262a2781f6859a3843fca62baa3b8d7dfdf8f` |
| last rendered page SHA-256 | `857528185085e0ab73b4a08aeb4580daaa4894b267cdc2a63081aa5cbbf9229e` |

## Exact-HEAD deterministic gates

All commands below must run from a clean checkout at the exact candidate SHA. Record
the command output and artifact hashes beside this report before declaring acceptance.

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output <fresh-output>
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m compileall -q src scripts web_runtime tests
```

| Gate | Result | Evidence |
| --- | --- | --- |
| Focused MIG-20 matrix | `PASS` | `12 passed` in 20.46s |
| Documentation integrity | `PASS` | `51 documents; current=23, historical=26, generated=2; errors=0, warnings=149` |
| Full pytest | `PASS` | `2244 passed, 1 skipped, 1 warning in 590.32s` |
| Ruff | `PASS` | `All checks passed!` |
| Native mypy | `PASS` | `Success: no issues found in 270 source files` |
| `win32` mypy | `PASS` | `Success: no issues found in 270 source files` |
| compileall | `PASS` | exit code 0; no output |
| Wheel/runtime smoke | `PASS` | `evidence_review_system-0.2.0-py3-none-any.whl`; SHA-256 `70f4cac4b33e59d72b9ac3273d3eb922ca80df8b446abdb86f4eefbf3a0b841d`; installed target resource and CLI probe passed |

The documentation command initially resolved an unrelated global checkout and
correctly returned `SOURCE_MISMATCH`; the passing run explicitly bound
`PYTHONPATH` to this clean worktree's `src` directory. The other gates and the
full test run were executed with the same worktree source binding.

The acceptance record must include the finalized evidence snapshot hash, exact
`evidence.sqlite` SHA-256, run IDs, final packet SHA-256 values, and the absence of
unexpected WAL/SHM sidecars. These are identity checks, not prose summaries.

## Protected browser and lifecycle gates

The browser gate is important and cannot be replaced by static HTML tests. On the
exact candidate, exercise both the protected Workbench URL and tokenized Formal
Review URL using the real local loopback server. At each supported viewport record
the URL, HTTP status, screenshot path, console errors, keyboard/focus result, print
result, protected/archive behavior, and server lifecycle status:

| Viewport | Workbench | Formal Review | Case Drawing | Keyboard/focus | Print | Console errors |
| --- | --- | --- | --- | --- | --- | --- |
| `1366×768` | `PASS` (protected URL, HTTP 200) | `PASS` (protected URL, HTTP 200) | `PASS` (p.1 and p.17/17, HTTP 200) | `PASS` | `PASS` | `PASS` |
| `1920×1080` | `PASS` (same protected URL, HTTP 200) | `PASS` (same protected URL, HTTP 200) | `PASS` (p.1 and p.17/17, HTTP 200) | `PASS` | `PASS` | `PASS` |
| `3840×2160` | `PASS` (same protected URL, HTTP 200) | `PASS` (same protected URL, HTTP 200) | `PASS` (p.1 and p.17/17, HTTP 200) | `PASS` | `PASS` | `PASS` |

Browser evidence was captured with Playwright CLI against real tokenized loopback
servers at this exact candidate. The Formal Review page displayed seven real
evidence citations and a verified reference page; selecting a second citation kept
the page identity bound. The Case Drawing page used the prepared
`ATT-C6367EE43EE223059644.pdf` source and navigated `1 / 17` → `2 / 17` → `17 / 17`.
Valid Workbench, Formal Review, and Case Drawing pages returned `200`; valid-page
console output was zero errors/warnings, and keyboard `Tab` moved focus to a real
button. A wrong Case Drawing token returned `403 FORBIDDEN` as required. Print
output was captured at `output/playwright/mig20-final-formal-print.pdf`; screenshots
are in `output/playwright/mig20-final-{workbench,formal,drawing}-{1366x768,1920x1080,3840x2160}.png`.
The detached Workbench lifecycle was started at a bound PID/port, observed as
`running: true`, allowed to reach its configured idle timeout and report `STOPPED`,
and completed with verified `serve-stop`; no unrelated process was signalled.

The archival HTML was served over loopback because the browser harness blocked direct
Playwright `file:` navigation (`about:blank`). Its decision download prompt produced
a five-field envelope, matching import recorded the append-only decision, a
packet-hash mismatch was rejected, and a repeated import was rejected by the
create-only filename collision rule. The static archival page logged the expected
`404` for its unavailable protected `decision/status` endpoint; this is not a valid
protected-page console error and does not alter the archival download/import results.

The exact prepared evidence workspace used for the source/hash check had
`evidence.sqlite` SHA-256
`9b9ee6218207ae24b6ec0d9ef3a89332481237bc419695fac483cb317629df01`, with no
`evidence.sqlite-wal` or `evidence.sqlite-shm` sidecars. Its finalized packet
hashes were:

| Run ID | Final packet SHA-256 |
| --- | --- |
| `RUN-2A9ABF9B241E3D2D9C16` | `5b2778f5f609bbfe20dea2e0e0ba17b7b812b16538e991579e6c3ccc148100ff` |
| `RUN-59044E4A34A124872843` | `63ef1b38211bb4fca04e47b8987e28822df88099c725503f2018a53760c1c7cc` |
| `RUN-D1C8BF42BF9B635E4D05` | `577584212cba21bb0967617884c34e468d10b7110c5bd88f546e9b56021cce6f` |

Also verify that an unauthorized or wrong-token request is rejected, `file:` HTML
does not masquerade as a persistent protected decision path, the archival decision
envelope imports only with the matching current packet hash, and detached server
stop/restart does not signal an unrelated PID. Record lifecycle evidence as
`STARTED`, `STATUS_RUNNING`, `STOPPED`, and `NOT_RUN` as applicable.

## Closure decision

This issue may be closed only when the exact candidate is clean, every required
automated and manual gate is `PASS`, no critical/important blocker remains, the
actual GitHub Actions state is recorded (`ACTIONS_NOT_RUN` is not a pass), and the
candidate SHA is the SHA reviewed and merged by the required pre-merge reviewer.
Until then the closure decision is `HOLD`.
