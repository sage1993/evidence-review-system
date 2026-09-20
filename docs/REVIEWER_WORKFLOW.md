# Reviewer Workflow

## ReviewMatter authority modes

Use **Evidence Navigation** to explore finalized evidence without creating a
conclusion or decision. The Workbench records **mutable ReviewMatter work
state**, not evidence or Formal Review output. **Formalization** is the only
promotion into **Formal Review**; the latter alone produces immutable packets
and accepts a packet-bound, append-only Human Decision.

The machine packet is evidence for review, not a decision. The reviewer confirms the visible conclusion against source evidence, page/bbox, deterministic calculation/rule results, and any additional-review items. The human decision is always stored separately as an append-only record.

## 1. Confirm source identity

Before deciding, confirm that:

- cited evidence belongs to the registered source and revision;
- the source SHA-256 is the one bound to the parser/evidence revision;
- the cited page exists;
- the displayed bbox/geometry is inside the verified PDF page geometry;
- the embedded/cached page image hash and source binding are valid;
- calculation and rule results are the deterministic artifacts referenced by the packet.

A filename or title is not proof of document identity or authority.

## 2. Understand status domains

Do not mix machine progress with a human decision.

| Domain | Meaning |
|---|---|
| Workflow state | processing progress such as `WAITING_TRACK_A`, `WAITING_TRACK_B`, `FINALIZING`, `READY_FOR_REVIEW`, `BLOCKED` |
| Finalizer status | `READY_FOR_HUMAN_REVIEW` or `ABSTAIN` |
| Rule status | one approved Rule Engine result |
| Human decision | separate append-only reviewer record |
| Display projection | may become `REVIEW_COMPLETED` after a valid human decision |

`READY_FOR_HUMAN_REVIEW` means the packet can be inspected. It is not approval. `ABSTAIN` means the recorded reasons must remain visible and reviewed.

## 3. Review the non-developer workspace

The normal screen is intentionally ordered for a reviewer rather than a developer:

1. **검토 결과** — Korean status and one concise conclusion;
2. **판단 근거** — quote, page, bbox, and verified page image;
3. **추가 확인** — only when missing/conflict/exception/abstention data exists;
4. **검토자 의견** — human decision and notes.

For a single claim, no redundant claim list should appear. A rules/calculations section should appear only when records exist. Internal run/citation/evidence/revision IDs, hashes, and confidence internals should remain under collapsed audit details rather than the default surface.

Do not skip the audit details when a discrepancy needs tracing. Hidden-by-default does not mean discarded.

## 4. Verify evidence and deterministic results

For each claim:

- compare the displayed quote to the verified source page;
- use the displayed bbox to locate the exact source region;
- confirm that every numeric token is grounded in evidence or a recorded CalculationResult;
- inspect RuleResult status, citations, version, and reason data when applicable;
- inspect missing inputs, conflicts, exceptions, and abstention reasons before deciding.

Do not recalculate a governed value in prose and substitute a different answer for the recorded engine result.

## 5. Protected browser route

The preferred review session is opened with a named reviewer when available:

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id <REVIEWER-ID> `
  --detach `
  --idle-timeout-seconds 5
```

The detached server defaults to a 1800-second monotonic idle timeout. Valid protected activity extends the deadline; rejected requests do not.

The protected review route is tokenized and loopback-only:

```text
http://127.0.0.1:<port>/runs/<RUN-ID>/<TOKEN>/review
```

The packet, packet-hash, decision, and decision-status endpoints share the protected prefix. The final review route must not be served before `final-review-packet.json` and `review.html` both exist.

When a reviewer ID is supplied at server start, the browser treats it as read-only session context. A POST using a different reviewer ID must be rejected.

## 6. Record the human decision

The Human Decision form always includes a reviewer-ID field in addition to decision and notes.

- If the protected server was started with `--reviewer-id`, that field is populated from the protected session and is read-only.
- If no reviewer ID is bound to the protected session, the reviewer enters it directly in the form. The accepted syntax is `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`.
- Decision and notes remain the reviewer-authored decision content; notes are required only for the decision states that require explanation.

Allowed decisions:

| Value | Display label |
|---|---|
| `SATISFIED` | 검토 결과에 동의 |
| `NOT_SATISFIED` | 검토 결과에 오류 있음 |
| `CONDITIONAL` | 조건 충족 시 동의 |
| `ADDITIONAL_REVIEW_REQUIRED` | 추가 자료 검토 필요 |

The protected browser request contains four fields: `reviewer_id`, `packet_hash`, `decision`, and `notes`. Reviewer ID is supplied from the protected session when configured; packet hash is supplied from the current immutable packet. The server independently revalidates both and creates `reviewed_at` as an offset-aware ISO-8601 server timestamp.

A successful request creates a new JSON file under:

```text
runs/<RUN-ID>/human-decisions/
```

The write is create-only. The machine packet and HTML remain unchanged, including `human_decision: null` in the machine packet. `REVIEW_COMPLETED` is only a browser/display projection derived from a valid separate decision record.

## 7. Archival HTML

Before presenting a final user answer, obtain the read-only packet projection:

```powershell
evidence-review review-run response --workspace <workspace> --run-id <RUN-ID>
```

The response retains the exact packet byte SHA, machine status, missing inputs,
abstention reasons and claim text. Every `FORMAL_FINDING` traces to its packet
claim and manifest-verified citation/evidence identity. Adding
`--response-input <response.json>` validates an existing response against that
exact projection and rejects expanded prose, substituted citations or stale hashes.
External checks belong in a separately labeled `SUPPLEMENTARY_EXTERNAL_CHECK`
section (`추가 확인 — Formal Review packet 외 자료`). Neither external checks nor
`UNBOUND_ANALYSIS` belong in the default Formal response artifact.

A retained `review.html` opened with `file:` has no protected local server and therefore cannot persist a decision through POST.

The archival page is an explicit static presentation. A protected-only projection opened with `file:` shows a launcher warning instead of silently attempting to load protected raster routes. Start the protected viewer with:

```powershell
evidence-review review-run serve `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --reviewer-id <REVIEWER-ID>
```

Use **결정 JSON 다운로드** only after reviewer ID, decision, and notes are valid. The archival page uses the same visible reviewer-ID form field; it does not open a prompt dialog. The downloaded envelope contains exactly:

```json
{
  "reviewer_id": "reviewer-01",
  "reviewed_at": "2026-08-13T03:00:00.000Z",
  "packet_hash": "<sha256>",
  "decision": "SATISFIED",
  "notes": "review notes"
}
```

The timestamp is generated immediately before download using an ISO-8601 offset-bearing browser time. A malformed or incomplete envelope must not be downloaded.

Import through the approved path:

```powershell
evidence-review review-run import-decision `
  --workspace <workspace> `
  --run-id <RUN-ID> `
  --envelope <human-decision-envelope.json>
```

Import recomputes the current packet SHA-256, rejects mismatch, validates the envelope, and creates a new append-only record. Saving or copying the HTML file is not decision persistence.

## 8. Browser and accessibility acceptance

Static CSS/unit tests do not replace reviewer browser QA. On the exact acceptance commit verify:

- 1366×768, 1920×1080, 2560×1440, 3840×2160, 768×1024, and 390×844;
- responsive layout behavior across all six required viewports;
- keyboard navigation and visible focus;
- evidence link focuses the correct page/overlay;
- print output contains result, evidence, additional review when present, and decision area without developer audit clutter;
- decision panel remains usable without obscuring evidence.

## 9. Server lifecycle

Run-scoped lifecycle commands are:

```powershell
evidence-review review-run serve-status --workspace <workspace> --run-id <RUN-ID>
evidence-review review-run serve-stop --workspace <workspace> --run-id <RUN-ID>
```

Acceptance must include normal start, open failure, stale state cleanup, idle server, stop, and protection against unrelated PID signaling. Windows behavior must be tested separately from POSIX behavior.

## 10. Performance evidence

The reviewer acceptance record should include `run-metrics.json` and event files for three simple-question runs. Confirm:

- metrics exist for every run;
- Track external wait is separate from deterministic time;
- deterministic total is within the applicable 5-second hard budget;
- protected server + browser dispatch is within the 2-second hard budget;
- retries are explained by failed attempts rather than normal resume;
- p50/p95 are calculated from actual Windows runs, not inferred from unit tests.

## 11. Release attestation remains separate

A review decision for one packet is not a release process attestation and **cannot authorize a new release**. Release authorization uses the `evidence-review/human-attestation` contract and a create-only `human-attestation.json`. A completed release process may record `REVIEWED_AND_ACCEPTED_FOR_RELEASE` only after the exact release candidate hash, packet hash, and required automated/manual evidence have been verified.

`PROCESS_ATTESTATION` is process evidence and is **not cryptographic proof of reviewer identity**. `cryptographic_identity_verified` therefore remains `false` in the current design. The legacy `ansim/human-acceptance` format is read-only compatibility evidence and cannot authorize a new release.

### Threat model and operational assumptions

The process attestation prevents accidental reuse of **stale or mismatched release artifacts** by binding exact hashes, but it does not defend against a **malicious reviewer**, a **stolen or copied JSON file**, or compromised host/account credentials. Those threats require **external access control** and, if needed, a future independent cryptographic identity mechanism.

## 12. Executable smoke checks

These checks only verify that the documented local CLI surfaces exist; they do not constitute review acceptance.

```bash smoke
python -m ansim_review --help
```

```bash smoke
python -m ansim_review review-run --help
```

## 13. Acceptance record

Record exact commit, Windows version, Python 3.13 version, command, exit code, browser/view matrix, timing values, and SHA-256 hashes in the review acceptance record. Any unexecuted check is `NOT_RUN`; it is not PASS.

## Protected formal-review handoff

After Track B validation and finalization, open the protected loopback review workspace with the interpreter-pinned command:

```powershell
py -3.13 -m evidence_review review-question submit-track-b `
  --workspace $Workspace `
  --run-id $RunId `
  --track-b-output $TrackB `
  --open
```

Successful finalization always returns `review_html`. `display_status=OPENED` means the protected URL was dispatched; `display_status=OPEN_FAILED` means finalization succeeded but browser display failed, so inspect `display_error` and open `review_html` through the protected route. The command does not wait for the server's full idle lifetime.
