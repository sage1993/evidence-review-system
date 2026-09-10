# Issue #159 / shared local HTTP transport report

## Scope

`SCOPE_EXPANSION_REQUIRED = NO`. The change is limited to one shared protected
loopback transport module, the Review Packet and Drawing Review local servers,
their local-server regression coverage, and this Issue #159 SDD record. It does
not alter Workbench, ReviewMatter, UI, evidence authority, or human decision
authority.

Base/current `origin/main`: `ad57418122f432363b5fd03469737456141b376f`.
Branch: `fix/issue-159-shared-http-transport`.
Python: `3.13.14` on Windows.
Code candidate: `4e1d4438de2465c99b76b88b4fef9af8fbbdbb35`.

## Implementation

- Added `evidence_review.local_http_transport`, the canonical fail-closed
  protected-loopback primitive for response security headers, Host/Origin
  cardinality, constant-time token checks, tokenized method lookup,
  Content-Length validation, and early oversized-body `413` response, flush,
  bounded drain, and close.
- Review Packet now delegates its response, authorization, body-length, and
  oversized rejection path to the shared module.
- Drawing Review now delegates the corresponding response, authorization,
  tokenized route/method, body-length, and oversized rejection paths. Both
  `/annotation/<token>/actions` and `/calibration/<token>` receive the same
  `413 BODY_TOO_LARGE` transport behavior.

## TDD and focused verification

- RED: 7 failed, 1 passed in 6.52s. All failures were the intended transport
  gaps: four valid-first duplicate Host/Origin requests were not rejected,
  `/actions` did not reply promptly to header-only/partial oversized bodies,
  and both routes did not cleanly drain a full oversized sender. The run used a
  fresh system-temporary pytest base because the sandbox ACL prevented
  worktree-local pytest temp cleanup; no unrelated host/collection failure was
  accepted as RED evidence.
- GREEN: 8 passed in 4.59s for the initial duplicate-header, header-only, and
  full-body regression set.
- Adjacent Drawing/Review local-server suite: 53 passed in 26.04s.

## Windows transport stress

All required socket gates passed in one focused run: 4 passed in 4.44s.

- Full oversized bodies: 500 requests total, alternating `/actions` and
  `/calibration`.
- Header-only oversized requests: 100 total, alternating the same two routes.
- Partial/slow sender: bounded completion passed independently for each route.

## Final acceptance

| Gate | Status |
| --- | --- |
| Focused GREEN | PASS — 8 passed in 4.59s |
| Adjacent local-server regression | PASS — 53 passed in 26.04s |
| Windows full-body stress | PASS — 500 alternating `/actions` and `/calibration` requests |
| Windows header-only stress | PASS — 100 alternating requests |
| Partial/slow sender | PASS — bounded completion for each route |
| Ruff `src tests web_runtime` | PASS |
| mypy `src` | PASS — 259 source files |
| mypy `--platform win32 src` | PASS — 259 source files |
| compileall | PASS |
| Source-tree documentation validation | PASS — 50 documents, errors=0, warnings=145 |
| Installed documentation command | `SOURCE_MISMATCH` — installed executable resolves another checkout |
| Full Python 3.13 pytest | `NOT_RUN` for the documentation-correction candidate; the prior background run was stopped before a summary |
| Final `git diff --check` | `NOT_RUN` for the documentation-correction candidate |
| Browser/manual | `NOT_RUN` |
| GitHub Actions | `ACTIONS_NOT_RUN` |

Controller review and the GitHub workflow are pending. Remote SHA verification,
pull request creation, merge, issue closure, and post-merge ancestry are not
claimed or performed.
