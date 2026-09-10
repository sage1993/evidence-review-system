# SDD ledger — Issue #159 / shared local HTTP transport

## Preflight

| Interface | Producer / consumer | Ruling |
| --- | --- | --- |
| Review Packet local server ↔ shared transport | `/actions` currently owns a hardened oversized-body rejection/drain path. | Preserve its bounded response/flush/drain contract as the canonical behavior. |
| Drawing Review local server ↔ shared transport | `/calibration` has a sibling rejection path with behavior drift. | Route the same helper through both server endpoints; no copied second implementation. |
| Host/Origin/token/CSP security ↔ route handlers | Header/token checks are authority boundaries before route work. | Keep fail-closed cardinality and constant-time/token/origin behavior; shared helper must not weaken existing checks. |
| Windows socket lifecycle ↔ body drain | Client reset/slow sender can race handler response. | Send 413 early, flush/close consistently, and bound drain deadline; prove with stress tests. |

## Acceptance checklist

- [x] RED demonstrates the sibling transport drift without unrelated host failure
- [x] One shared transport primitive is used by both servers
- [x] Duplicate Host/Origin behavior is identical
- [x] Full/header-only/partial slow-body stress gates pass
- [x] Existing security tests pass
- [ ] Focused/adjacent/static/full exact-head gates pass
- [ ] Feature branch remote SHA parity verified
- [ ] PR reviewed with gpt-5.6-sol-high and merged
- [ ] Issue #159 closed and post-merge ancestry verified

## Scope control

- `SCOPE_EXPANSION_REQUIRED = NO` initially.
- Do not modify protected Workbench/UI or unrelated ReviewMatter paths.

## Issue #159 implementation record — 2026-09-10

- RED on Windows/Python 3.13.14 ran against only the new Drawing transport
  regressions. It produced 7 expected failures and 1 control pass: all four
  valid-first duplicate Host/Origin cases were accepted, `/actions` blocked
  before replying to header-only and partial oversized bodies, and
  `/calibration` reset a full oversized sender. The suite collected and ran
  normally; the only initial harness problem was a sandbox ACL preventing
  pytest temporary-directory enumeration, resolved with a fresh system-temp
  `--basetemp` before accepting the RED result.
- GREEN introduces `evidence_review.local_http_transport` as the one shared
  protected-loopback transport boundary. Both servers now use its security
  response headers, Host/Origin cardinality validation, Content-Length
  validation, and early `413` flush / total-deadline drain / close behavior.
  The Review server uses its token comparison; Drawing uses its tokenized route
  comparison and shared tokenized method lookup. No Workbench, ReviewMatter,
  authority, or UI file changed.
- Focused GREEN passed 8 tests in 4.59s; adjacent Drawing/Review local-server
  regression passed 53 tests in 26.04s. Windows stress passed 4 selected tests
  in 4.44s: 500 full oversized requests and 100 header-only requests,
  alternating `/actions` and `/calibration`, plus one bounded slow sender for
  each route.
- Browser/manual acceptance: `NOT_RUN`. GitHub Actions: `ACTIONS_NOT_RUN`.
  Push, PR creation, merge, and issue closure are `NOT_RUN` by request.
